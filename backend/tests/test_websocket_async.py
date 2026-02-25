"""
Async WebSocket integration tests using a real uvicorn server.

Covers gaps that the sync TestClient can't test:
- Timer expiry ending questions
- Spectator receiving broadcasts
- Bonus splash delay rejecting early answers
- Streak reset when a player doesn't answer (timer fires)

Requires: pytest-asyncio, httpx, websockets
"""
import sys
import os
import uuid
import json
import asyncio

import pytest
import pytest_asyncio
import httpx
import websockets

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import uvicorn
from main import app, quizzes, game_history
from socket_manager import socket_manager


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(autouse=True)
async def server_port():
    """Start a real uvicorn server on a random port, yield the port, shut down."""
    # Clear state
    quizzes.clear()
    game_history.clear()
    socket_manager.rooms.clear()
    saved_origins = socket_manager.allowed_origins
    socket_manager.allowed_origins = []

    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    serve_task = asyncio.create_task(server.serve())

    # Wait for server to start
    while not server.started:
        await asyncio.sleep(0.01)

    # Extract the OS-assigned port
    port = server.servers[0].sockets[0].getsockname()[1]
    yield port

    # Teardown
    server.should_exit = True
    await serve_task
    quizzes.clear()
    game_history.clear()
    socket_manager.rooms.clear()
    socket_manager.allowed_origins = saved_origins


def seed_quiz(num_questions=3):
    """Insert a quiz directly into module-level storage and return its id."""
    quiz_data = {
        "quiz_title": "Async Test Quiz",
        "questions": [
            {
                "id": i + 1,
                "text": f"Question {i + 1}?",
                "options": ["A", "B", "C", "D"],
                "answer_index": 0,
            }
            for i in range(num_questions)
        ],
    }
    quiz_id = str(uuid.uuid4())
    quizzes[quiz_id] = quiz_data
    return quiz_id


async def create_room(port, quiz_id, time_limit=50):
    """Create a room via HTTP and return (room_code, organizer_token)."""
    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as http:
        res = await http.post("/room/create", json={"quiz_id": quiz_id, "time_limit": time_limit})
        assert res.status_code == 200
        data = res.json()
        return data["room_code"], data["organizer_token"]


async def send_json(ws, msg):
    """Send a JSON message over a websockets connection."""
    await ws.send(json.dumps(msg))


async def recv_json(ws, timeout=10.0):
    """Receive and parse a JSON message with timeout."""
    data = await asyncio.wait_for(ws.recv(), timeout=timeout)
    return json.loads(data)


async def recv_until(ws, msg_type, timeout=15.0, max_messages=100):
    """Drain messages until we get the expected type, with timeout."""
    deadline = asyncio.get_event_loop().time() + timeout
    for _ in range(max_messages):
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise TimeoutError(f"Never received {msg_type} within {timeout}s")
        data = await asyncio.wait_for(ws.recv(), timeout=remaining)
        msg = json.loads(data)
        if msg.get("type") == msg_type:
            return msg
    raise TimeoutError(f"Never received {msg_type} after {max_messages} messages")


async def collect_until(ws, msg_type, timeout=15.0, max_messages=200):
    """Collect all messages until we get the target type. Returns (collected, target_msg)."""
    collected = []
    deadline = asyncio.get_event_loop().time() + timeout
    for _ in range(max_messages):
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise TimeoutError(f"Never received {msg_type} within {timeout}s")
        data = await asyncio.wait_for(ws.recv(), timeout=remaining)
        msg = json.loads(data)
        if msg.get("type") == msg_type:
            return collected, msg
        collected.append(msg)
    raise TimeoutError(f"Never received {msg_type} after {max_messages} messages")


def ws_url(port, room_code, client_id, **params):
    """Build a WebSocket URL with query params."""
    base = f"ws://127.0.0.1:{port}/ws/{room_code}/{client_id}"
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        base += f"?{qs}"
    return base


# ---------------------------------------------------------------------------
# Timer Expiry Tests
# ---------------------------------------------------------------------------

class TestTimerExpiry:
    """Test that asyncio timer tasks actually fire and end questions."""

    @pytest.mark.asyncio
    async def test_timer_ends_question(self, server_port):
        """When no one answers, timer should expire and send QUESTION_OVER."""
        quiz_id = seed_quiz(num_questions=1)
        room_code, org_token = await create_room(server_port, quiz_id, time_limit=5)

        async with websockets.connect(ws_url(server_port, room_code, "org-1", organizer="true", token=org_token)) as org_ws:
            await recv_until(org_ws, "ROOM_CREATED")

            async with websockets.connect(ws_url(server_port, room_code, "p-1")) as p_ws:
                await send_json(p_ws, {"type": "JOIN", "nickname": "Alice"})
                await recv_until(p_ws, "JOINED_ROOM")
                await recv_until(org_ws, "PLAYER_JOINED")
                await recv_until(p_ws, "PLAYER_JOINED")

                # Start game, don't answer
                await send_json(org_ws, {"type": "START_GAME"})
                await send_json(org_ws, {"type": "NEXT_QUESTION"})
                await recv_until(org_ws, "QUESTION")
                await recv_until(p_ws, "QUESTION")

                # Wait for timer to expire — QUESTION_OVER should arrive
                qo = await recv_until(org_ws, "QUESTION_OVER", timeout=10)
                assert len(qo["leaderboard"]) == 1
                assert qo["leaderboard"][0]["score"] == 0

    @pytest.mark.asyncio
    async def test_timer_ticks_received(self, server_port):
        """Verify TIMER messages count down before QUESTION_OVER."""
        quiz_id = seed_quiz(num_questions=1)
        room_code, org_token = await create_room(server_port, quiz_id, time_limit=5)

        async with websockets.connect(ws_url(server_port, room_code, "org-1", organizer="true", token=org_token)) as org_ws:
            await recv_until(org_ws, "ROOM_CREATED")

            async with websockets.connect(ws_url(server_port, room_code, "p-1")) as p_ws:
                await send_json(p_ws, {"type": "JOIN", "nickname": "Alice"})
                await recv_until(p_ws, "JOINED_ROOM")
                await recv_until(org_ws, "PLAYER_JOINED")
                await recv_until(p_ws, "PLAYER_JOINED")

                await send_json(org_ws, {"type": "START_GAME"})
                await send_json(org_ws, {"type": "NEXT_QUESTION"})
                await recv_until(p_ws, "QUESTION")

                # Collect all messages until QUESTION_OVER on player side
                collected, qo = await collect_until(p_ws, "QUESTION_OVER", timeout=10)
                timer_msgs = [m for m in collected if m.get("type") == "TIMER"]
                remaining_values = [m["remaining"] for m in timer_msgs]

                # Should have countdown ticks including 0
                assert 0 in remaining_values, f"Expected tick 0, got {remaining_values}"
                assert 5 in remaining_values, f"Expected tick 5, got {remaining_values}"
                # Ticks should be in descending order
                assert remaining_values == sorted(remaining_values, reverse=True)


# ---------------------------------------------------------------------------
# Streak Reset on Timeout Tests
# ---------------------------------------------------------------------------

class TestStreakResetOnTimeout:
    """Test streak resets when a player doesn't answer and the timer expires."""

    @pytest.mark.asyncio
    async def test_streak_resets_when_player_does_not_answer(self, server_port):
        """Player answers Q1 correctly (streak=1), misses Q2 (timer), answers Q3 → streak=1."""
        quiz_id = seed_quiz(num_questions=3)
        room_code, org_token = await create_room(server_port, quiz_id, time_limit=5)

        async with websockets.connect(ws_url(server_port, room_code, "org-1", organizer="true", token=org_token)) as org_ws:
            await recv_until(org_ws, "ROOM_CREATED")

            async with websockets.connect(ws_url(server_port, room_code, "p-1")) as p_ws:
                await send_json(p_ws, {"type": "JOIN", "nickname": "Alice"})
                await recv_until(p_ws, "JOINED_ROOM")
                await recv_until(org_ws, "PLAYER_JOINED")
                await recv_until(p_ws, "PLAYER_JOINED")

                await send_json(org_ws, {"type": "START_GAME"})

                # Q1: answer correctly
                await send_json(org_ws, {"type": "NEXT_QUESTION"})
                await recv_until(org_ws, "QUESTION")
                await recv_until(p_ws, "QUESTION")
                await send_json(p_ws, {"type": "ANSWER", "answer_index": 0})
                r1 = await recv_until(p_ws, "ANSWER_RESULT")
                assert r1["streak"] == 1
                assert r1["correct"] is True
                await recv_until(org_ws, "QUESTION_OVER")
                await recv_until(p_ws, "QUESTION_OVER")

                # Q2: DON'T answer — let timer expire
                await send_json(org_ws, {"type": "NEXT_QUESTION"})
                await recv_until(org_ws, "QUESTION")
                await recv_until(p_ws, "QUESTION")
                # Wait for timer to end the question
                await recv_until(org_ws, "QUESTION_OVER", timeout=10)
                await recv_until(p_ws, "QUESTION_OVER", timeout=5)

                # Q3: answer correctly — streak should be 1 (reset), not 2
                await send_json(org_ws, {"type": "NEXT_QUESTION"})
                await recv_until(org_ws, "QUESTION")
                await recv_until(p_ws, "QUESTION")
                await send_json(p_ws, {"type": "ANSWER", "answer_index": 0})
                r3 = await recv_until(p_ws, "ANSWER_RESULT")
                assert r3["correct"] is True
                assert r3["streak"] == 1, f"Expected streak=1 after timeout reset, got {r3['streak']}"


# ---------------------------------------------------------------------------
# Spectator Broadcast Tests
# ---------------------------------------------------------------------------

class TestSpectatorBroadcasts:
    """Test that spectators actually receive game broadcasts."""

    @pytest.mark.asyncio
    async def test_spectator_receives_question_and_timer(self, server_port):
        """Spectator should receive QUESTION and TIMER broadcasts during a game."""
        quiz_id = seed_quiz(num_questions=1)
        room_code, org_token = await create_room(server_port, quiz_id, time_limit=5)

        async with websockets.connect(ws_url(server_port, room_code, "org-1", organizer="true", token=org_token)) as org_ws:
            await recv_until(org_ws, "ROOM_CREATED")

            async with websockets.connect(ws_url(server_port, room_code, "p-1")) as p_ws:
                await send_json(p_ws, {"type": "JOIN", "nickname": "Alice"})
                await recv_until(p_ws, "JOINED_ROOM")
                await recv_until(org_ws, "PLAYER_JOINED")
                await recv_until(p_ws, "PLAYER_JOINED")

                # Connect spectator
                async with websockets.connect(ws_url(server_port, room_code, "spec-1", spectator="true")) as spec_ws:
                    sync = await recv_json(spec_ws)
                    assert sync["type"] == "SPECTATOR_SYNC"
                    assert sync["state"] == "LOBBY"

                    # Start game
                    await send_json(org_ws, {"type": "START_GAME"})

                    # Spectator should get GAME_STARTING
                    gs = await recv_until(spec_ws, "GAME_STARTING", timeout=5)
                    assert gs["type"] == "GAME_STARTING"

                    await send_json(org_ws, {"type": "NEXT_QUESTION"})

                    # Spectator should get QUESTION
                    q = await recv_until(spec_ws, "QUESTION", timeout=5)
                    assert q["question_number"] == 1
                    assert "question" in q

                    # Spectator should get TIMER ticks
                    timer = await recv_until(spec_ws, "TIMER", timeout=5)
                    assert "remaining" in timer

    @pytest.mark.asyncio
    async def test_spectator_receives_question_over_and_podium(self, server_port):
        """Spectator should receive QUESTION_OVER and PODIUM broadcasts."""
        quiz_id = seed_quiz(num_questions=1)
        room_code, org_token = await create_room(server_port, quiz_id, time_limit=50)

        async with websockets.connect(ws_url(server_port, room_code, "org-1", organizer="true", token=org_token)) as org_ws:
            await recv_until(org_ws, "ROOM_CREATED")

            async with websockets.connect(ws_url(server_port, room_code, "p-1")) as p_ws:
                await send_json(p_ws, {"type": "JOIN", "nickname": "Alice"})
                await recv_until(p_ws, "JOINED_ROOM")
                await recv_until(org_ws, "PLAYER_JOINED")
                await recv_until(p_ws, "PLAYER_JOINED")

                async with websockets.connect(ws_url(server_port, room_code, "spec-1", spectator="true")) as spec_ws:
                    await recv_json(spec_ws)  # SPECTATOR_SYNC

                    await send_json(org_ws, {"type": "START_GAME"})
                    await recv_until(spec_ws, "GAME_STARTING", timeout=5)

                    await send_json(org_ws, {"type": "NEXT_QUESTION"})
                    await recv_until(spec_ws, "QUESTION", timeout=5)
                    await recv_until(p_ws, "QUESTION")

                    # Player answers
                    await send_json(p_ws, {"type": "ANSWER", "answer_index": 0})
                    await recv_until(p_ws, "ANSWER_RESULT")

                    # Spectator should get QUESTION_OVER
                    qo = await recv_until(spec_ws, "QUESTION_OVER", timeout=5)
                    assert "leaderboard" in qo
                    assert qo["leaderboard"][0]["nickname"] == "Alice"

                    # Advance to PODIUM
                    await send_json(org_ws, {"type": "NEXT_QUESTION"})
                    podium = await recv_until(spec_ws, "PODIUM", timeout=5)
                    assert "leaderboard" in podium
                    assert podium["leaderboard"][0]["nickname"] == "Alice"


# ---------------------------------------------------------------------------
# Bonus Splash Delay Tests
# ---------------------------------------------------------------------------

class TestBonusSplashDelay:
    """Test that answers are rejected during the 2s bonus splash animation."""

    @pytest.mark.asyncio
    async def test_answer_rejected_during_bonus_splash(self, server_port):
        """Answering immediately after QUESTION broadcast on a bonus round should be ignored."""
        quiz_id = seed_quiz(num_questions=5)
        room_code, org_token = await create_room(server_port, quiz_id, time_limit=10)

        async with websockets.connect(ws_url(server_port, room_code, "org-1", organizer="true", token=org_token)) as org_ws:
            await recv_until(org_ws, "ROOM_CREATED")

            async with websockets.connect(ws_url(server_port, room_code, "p-1")) as p_ws:
                await send_json(p_ws, {"type": "JOIN", "nickname": "Alice"})
                await recv_until(p_ws, "JOINED_ROOM")
                await recv_until(org_ws, "PLAYER_JOINED")
                await recv_until(p_ws, "PLAYER_JOINED")

                await send_json(org_ws, {"type": "START_GAME"})

                # Find a bonus question
                found_bonus = False
                for q_num in range(5):
                    await send_json(org_ws, {"type": "NEXT_QUESTION"})
                    q = await recv_until(org_ws, "QUESTION")
                    await recv_until(p_ws, "QUESTION")

                    if q["is_bonus"]:
                        found_bonus = True
                        # Immediately send answer — should be ignored during splash
                        await send_json(p_ws, {"type": "ANSWER", "answer_index": 0})
                        # Wait a moment, then send answer again after splash completes
                        await asyncio.sleep(2.5)
                        await send_json(p_ws, {"type": "ANSWER", "answer_index": 0})
                        r = await recv_until(p_ws, "ANSWER_RESULT")
                        assert r["correct"] is True
                        # Only one ANSWER_RESULT — the splash-period answer was ignored
                        await recv_until(org_ws, "QUESTION_OVER")
                        await recv_until(p_ws, "QUESTION_OVER")
                        break

                    # Answer normally on non-bonus questions
                    await send_json(p_ws, {"type": "ANSWER", "answer_index": 0})
                    await recv_until(p_ws, "ANSWER_RESULT")
                    await recv_until(org_ws, "QUESTION_OVER")
                    await recv_until(p_ws, "QUESTION_OVER")

                assert found_bonus, "No bonus question found in 5-question quiz (expected at least 1)"
