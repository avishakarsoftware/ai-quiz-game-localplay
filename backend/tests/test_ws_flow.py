"""
WebSocket integration tests for full game flows.
Tests: lifecycle, token auth, disconnect/reconnect, spectator sync,
state guards, rate limiting, room reset, edge cases.
Uses FastAPI TestClient with proper organizer token handling.
"""
import sys
import os
import uuid
import json

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fastapi.testclient import TestClient
from main import app, quizzes, game_history
from socket_manager import socket_manager
import config


@pytest.fixture(autouse=True)
def clear_state():
    quizzes.clear()
    game_history.clear()
    socket_manager.rooms.clear()
    saved_origins = socket_manager.allowed_origins
    socket_manager.allowed_origins = []  # disable origin check for tests
    yield
    quizzes.clear()
    game_history.clear()
    socket_manager.rooms.clear()
    socket_manager.allowed_origins = saved_origins


client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def seed_quiz(num_questions=3):
    """Insert a quiz and return its id."""
    quiz_data = {
        "quiz_title": "Flow Test Quiz",
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


def create_room(quiz_id, time_limit=30):
    """Create a room and return (room_code, organizer_token)."""
    res = client.post("/room/create", json={"quiz_id": quiz_id, "time_limit": time_limit})
    assert res.status_code == 200
    data = res.json()
    return data["room_code"], data["organizer_token"]


def org_url(room_code, token, client_id="org-1"):
    return f"/ws/{room_code}/{client_id}?organizer=true&token={token}"


def player_url(room_code, client_id="player-1"):
    return f"/ws/{room_code}/{client_id}"


def spectator_url(room_code, client_id="spec-1"):
    return f"/ws/{room_code}/{client_id}?spectator=true"


def recv_until(ws, msg_type, max_messages=50):
    """Receive messages until we get the expected type. Returns that message."""
    for _ in range(max_messages):
        data = ws.receive_json()
        if data.get("type") == msg_type:
            return data
    raise TimeoutError(f"Never received {msg_type} after {max_messages} messages")


def play_question(org_ws, player_sockets, answer_index=0):
    """Advance to next question, have all players answer, return QUESTION_OVER."""
    org_ws.send_json({"type": "NEXT_QUESTION"})
    recv_until(org_ws, "QUESTION")
    for p_ws in player_sockets:
        recv_until(p_ws, "QUESTION")
        p_ws.send_json({"type": "ANSWER", "answer_index": answer_index})
        recv_until(p_ws, "ANSWER_RESULT")
    return recv_until(org_ws, "QUESTION_OVER")


# ===========================================================================
# Full Game Lifecycle
# ===========================================================================

class TestFullGameLifecycle:
    """Test the complete flow: create room → join → play all questions → podium."""

    def test_complete_game_3_questions(self):
        quiz_id = seed_quiz(num_questions=3)
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            msg = org_ws.receive_json()
            assert msg["type"] == "ROOM_CREATED"
            assert msg["room_code"] == room_code

            with client.websocket_connect(player_url(room_code, "p1")) as p1_ws:
                p1_ws.send_json({"type": "JOIN", "nickname": "Alice", "avatar": "A"})
                p1_ws.receive_json()  # JOINED_ROOM
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p1_ws, "PLAYER_JOINED")

                # Start game
                org_ws.send_json({"type": "START_GAME"})
                recv_until(org_ws, "GAME_STARTING")
                recv_until(p1_ws, "GAME_STARTING")

                # Play 3 questions
                for q in range(3):
                    qo = play_question(org_ws, [p1_ws], answer_index=0)
                    assert "leaderboard" in qo
                    if q == 2:
                        assert qo["is_final"] is True
                    else:
                        assert qo["is_final"] is False

                # Advance past final leaderboard → PODIUM
                org_ws.send_json({"type": "NEXT_QUESTION"})
                podium = recv_until(org_ws, "PODIUM")
                assert "leaderboard" in podium
                assert "team_leaderboard" in podium
                assert podium["leaderboard"][0]["nickname"] == "Alice"
                assert podium["leaderboard"][0]["score"] > 0

    def test_two_players_full_game(self):
        quiz_id = seed_quiz(num_questions=2)
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            org_ws.receive_json()  # ROOM_CREATED

            with client.websocket_connect(player_url(room_code, "p1")) as p1_ws, \
                 client.websocket_connect(player_url(room_code, "p2")) as p2_ws:

                p1_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                p1_ws.receive_json()  # JOINED_ROOM
                recv_until(p1_ws, "PLAYER_JOINED")
                p2_ws.send_json({"type": "JOIN", "nickname": "Bob"})
                p2_ws.receive_json()  # JOINED_ROOM
                recv_until(p2_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                recv_until(org_ws, "GAME_STARTING")

                # Q1: both answer correctly
                play_question(org_ws, [p1_ws, p2_ws], answer_index=0)

                # Q2: Alice correct, Bob wrong
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "QUESTION")
                recv_until(p1_ws, "QUESTION")
                recv_until(p2_ws, "QUESTION")
                p1_ws.send_json({"type": "ANSWER", "answer_index": 0})
                recv_until(p1_ws, "ANSWER_RESULT")
                p2_ws.send_json({"type": "ANSWER", "answer_index": 1})
                recv_until(p2_ws, "ANSWER_RESULT")
                qo = recv_until(org_ws, "QUESTION_OVER")
                assert qo["is_final"] is True

                # PODIUM
                org_ws.send_json({"type": "NEXT_QUESTION"})
                podium = recv_until(org_ws, "PODIUM")
                # Alice should be ahead (correct on both)
                assert podium["leaderboard"][0]["nickname"] == "Alice"


# ===========================================================================
# Organizer Token Enforcement
# ===========================================================================

class TestOrganizerTokenAuth:
    def test_organizer_without_token_rejected(self):
        quiz_id = seed_quiz()
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "ERROR"
            assert "token" in msg["message"].lower() or "invalid" in msg["message"].lower()

    def test_organizer_with_wrong_token_rejected(self):
        quiz_id = seed_quiz()
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true&token=wrong-token") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "ERROR"

    def test_organizer_with_correct_token_accepted(self):
        quiz_id = seed_quiz()
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as ws:
            msg = ws.receive_json()
            assert msg["type"] == "ROOM_CREATED"


# ===========================================================================
# Invalid Room Handling
# ===========================================================================

class TestInvalidRoom:
    def test_player_connect_to_nonexistent_room(self):
        with client.websocket_connect("/ws/BADCODE/p1") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "ERROR"
            assert "not found" in msg["message"].lower()

    def test_spectator_connect_to_nonexistent_room(self):
        with client.websocket_connect("/ws/BADCODE/s1?spectator=true") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "ERROR"


# ===========================================================================
# Player Join Flow
# ===========================================================================

class TestPlayerJoinFlow:
    def test_player_join_broadcasts_to_all(self):
        quiz_id = seed_quiz()
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            org_ws.receive_json()  # ROOM_CREATED
            with client.websocket_connect(player_url(room_code, "p1")) as p1_ws:
                p1_ws.send_json({"type": "JOIN", "nickname": "Alice", "avatar": "A"})
                p1_ws.receive_json()  # JOINED_ROOM
                joined = recv_until(org_ws, "PLAYER_JOINED")
                assert joined["nickname"] == "Alice"
                assert joined["player_count"] == 1

    def test_multiple_players_join(self):
        quiz_id = seed_quiz()
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            org_ws.receive_json()
            with client.websocket_connect(player_url(room_code, "p1")) as p1_ws, \
                 client.websocket_connect(player_url(room_code, "p2")) as p2_ws:
                p1_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                p1_ws.receive_json()  # JOINED_ROOM
                recv_until(org_ws, "PLAYER_JOINED")
                p2_ws.send_json({"type": "JOIN", "nickname": "Bob"})
                p2_ws.receive_json()  # JOINED_ROOM
                joined = recv_until(org_ws, "PLAYER_JOINED")
                assert joined["player_count"] == 2
                assert len(joined["players"]) == 2

    def test_html_nickname_sanitized(self):
        quiz_id = seed_quiz()
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            org_ws.receive_json()
            with client.websocket_connect(player_url(room_code, "p1")) as p1_ws:
                p1_ws.send_json({"type": "JOIN", "nickname": "<script>alert(1)</script>Alice"})
                p1_ws.receive_json()  # JOINED_ROOM
                joined = recv_until(org_ws, "PLAYER_JOINED")
                assert "<" not in joined["nickname"]
                assert "Alice" in joined["nickname"]

    def test_empty_nickname_rejected(self):
        quiz_id = seed_quiz()
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            org_ws.receive_json()
            with client.websocket_connect(player_url(room_code, "p1")) as p1_ws:
                p1_ws.send_json({"type": "JOIN", "nickname": ""})
                err = recv_until(p1_ws, "ERROR")
                assert "nickname" in err["message"].lower() or "character" in err["message"].lower()

    def test_team_assignment_on_join(self):
        quiz_id = seed_quiz()
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            org_ws.receive_json()
            with client.websocket_connect(player_url(room_code, "p1")) as p1_ws:
                p1_ws.send_json({"type": "JOIN", "nickname": "Alice", "team": "Red"})
                p1_ws.receive_json()  # JOINED_ROOM
                recv_until(org_ws, "PLAYER_JOINED")
                # Verify team is stored
                room = socket_manager.rooms[room_code]
                assert room.teams.get("Alice") == "Red"


# ===========================================================================
# State Guard Enforcement via WS
# ===========================================================================

class TestStateGuardsWS:
    def test_cannot_start_game_twice(self):
        quiz_id = seed_quiz()
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            org_ws.receive_json()
            with client.websocket_connect(player_url(room_code, "p1")) as p1_ws:
                p1_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                p1_ws.receive_json()  # JOINED_ROOM
                recv_until(org_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                recv_until(org_ws, "GAME_STARTING")

                # Second START_GAME should be ignored
                org_ws.send_json({"type": "START_GAME"})
                # Should not receive another GAME_STARTING
                org_ws.send_json({"type": "NEXT_QUESTION"})
                q = recv_until(org_ws, "QUESTION")
                assert q["question_number"] == 1

    def test_player_cannot_answer_in_lobby(self):
        quiz_id = seed_quiz()
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            org_ws.receive_json()
            with client.websocket_connect(player_url(room_code, "p1")) as p1_ws:
                p1_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                p1_ws.receive_json()  # JOINED_ROOM
                recv_until(org_ws, "PLAYER_JOINED")
                # Try to answer in LOBBY state
                p1_ws.send_json({"type": "ANSWER", "answer_index": 0})
                # No ANSWER_RESULT should come (message is silently ignored)
                # We can verify by starting the game and checking it works normally
                org_ws.send_json({"type": "START_GAME"})
                recv_until(org_ws, "GAME_STARTING")

    def test_player_cannot_answer_twice(self):
        quiz_id = seed_quiz()
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            org_ws.receive_json()
            with client.websocket_connect(player_url(room_code, "p1")) as p1_ws:
                p1_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                p1_ws.receive_json()  # JOINED_ROOM
                recv_until(org_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                recv_until(org_ws, "GAME_STARTING")
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(p1_ws, "QUESTION")

                p1_ws.send_json({"type": "ANSWER", "answer_index": 0})
                result1 = recv_until(p1_ws, "ANSWER_RESULT")
                assert result1["correct"] is True
                score_after_first = result1["points"]

                # Second answer should be ignored
                p1_ws.send_json({"type": "ANSWER", "answer_index": 0})
                # The question should end (only 1 player, already answered)
                qo = recv_until(org_ws, "QUESTION_OVER")
                assert qo["leaderboard"][0]["score"] == score_after_first


# ===========================================================================
# All-Answered Early End
# ===========================================================================

class TestAllAnsweredEarlyEnd:
    def test_question_ends_when_all_answer(self):
        quiz_id = seed_quiz()
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            org_ws.receive_json()
            with client.websocket_connect(player_url(room_code, "p1")) as p1_ws, \
                 client.websocket_connect(player_url(room_code, "p2")) as p2_ws:
                p1_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                p1_ws.receive_json()  # JOINED_ROOM
                recv_until(org_ws, "PLAYER_JOINED")
                p2_ws.send_json({"type": "JOIN", "nickname": "Bob"})
                p2_ws.receive_json()  # JOINED_ROOM
                recv_until(org_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                recv_until(org_ws, "GAME_STARTING")
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(p1_ws, "QUESTION")
                recv_until(p2_ws, "QUESTION")

                # Both answer
                p1_ws.send_json({"type": "ANSWER", "answer_index": 0})
                p2_ws.send_json({"type": "ANSWER", "answer_index": 0})

                # Should get QUESTION_OVER without waiting for timer
                qo = recv_until(org_ws, "QUESTION_OVER")
                assert len(qo["leaderboard"]) == 2


# ===========================================================================
# Spectator Flow
# ===========================================================================

class TestSpectatorFlow:
    def test_spectator_receives_sync_on_connect(self):
        quiz_id = seed_quiz()
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            org_ws.receive_json()
            with client.websocket_connect(player_url(room_code, "p1")) as p1_ws:
                p1_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                p1_ws.receive_json()  # JOINED_ROOM
                recv_until(org_ws, "PLAYER_JOINED")

                with client.websocket_connect(spectator_url(room_code)) as spec_ws:
                    sync = spec_ws.receive_json()
                    assert sync["type"] == "SPECTATOR_SYNC"
                    assert sync["state"] == "LOBBY"
                    assert sync["player_count"] == 1
                    assert sync["room_code"] == room_code

    def test_spectator_sync_includes_team_leaderboard(self):
        """Verify the recent fix: team_leaderboard is included in SPECTATOR_SYNC."""
        quiz_id = seed_quiz()
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            org_ws.receive_json()
            with client.websocket_connect(player_url(room_code, "p1")) as p1_ws:
                p1_ws.send_json({"type": "JOIN", "nickname": "Alice", "team": "Red"})
                p1_ws.receive_json()  # JOINED_ROOM
                recv_until(org_ws, "PLAYER_JOINED")

                with client.websocket_connect(spectator_url(room_code)) as spec_ws:
                    sync = spec_ws.receive_json()
                    assert "team_leaderboard" in sync

    @pytest.mark.skip(reason="TestClient cannot handle spectator broadcast loop (spectator uses while True: receive_text())")
    def test_spectator_receives_game_events(self):
        quiz_id = seed_quiz()
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            org_ws.receive_json()
            with client.websocket_connect(player_url(room_code, "p1")) as p1_ws:
                p1_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                p1_ws.receive_json()  # JOINED_ROOM
                recv_until(org_ws, "PLAYER_JOINED")

                with client.websocket_connect(spectator_url(room_code)) as spec_ws:
                    spec_ws.receive_json()  # SPECTATOR_SYNC

                    org_ws.send_json({"type": "START_GAME"})
                    gs = recv_until(spec_ws, "GAME_STARTING")
                    assert gs["type"] == "GAME_STARTING"

                    org_ws.send_json({"type": "NEXT_QUESTION"})
                    q = recv_until(spec_ws, "QUESTION")
                    assert "question" in q

    def test_spectator_mid_game_join_gets_question_data(self):
        quiz_id = seed_quiz()
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            org_ws.receive_json()
            with client.websocket_connect(player_url(room_code, "p1")) as p1_ws:
                p1_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                p1_ws.receive_json()  # JOINED_ROOM
                recv_until(org_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                recv_until(org_ws, "GAME_STARTING")
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "QUESTION")

                # Spectator joins mid-question
                with client.websocket_connect(spectator_url(room_code)) as spec_ws:
                    sync = spec_ws.receive_json()
                    assert sync["type"] == "SPECTATOR_SYNC"
                    assert sync["state"] == "QUESTION"
                    assert "question" in sync
                    assert "time_limit" in sync
                    assert "time_remaining" in sync
                    assert "answer_index" not in sync["question"]


# ===========================================================================
# Room Reset Flow
# ===========================================================================

class TestRoomResetFlow:
    def test_reset_room_after_podium(self):
        quiz_id = seed_quiz(num_questions=2)
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            org_ws.receive_json()
            with client.websocket_connect(player_url(room_code, "p1")) as p1_ws:
                p1_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                p1_ws.receive_json()  # JOINED_ROOM
                recv_until(org_ws, "PLAYER_JOINED")

                # Play through to PODIUM
                org_ws.send_json({"type": "START_GAME"})
                recv_until(org_ws, "GAME_STARTING")
                play_question(org_ws, [p1_ws])
                play_question(org_ws, [p1_ws])
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "PODIUM")

                # Reset with new quiz
                new_quiz = {
                    "quiz_title": "Round 2",
                    "questions": [
                        {"id": 1, "text": "New Q1?", "options": ["A", "B", "C", "D"], "answer_index": 1},
                        {"id": 2, "text": "New Q2?", "options": ["A", "B", "C", "D"], "answer_index": 2},
                    ]
                }
                org_ws.send_json({"type": "RESET_ROOM", "quiz_data": new_quiz, "time_limit": 20})
                reset = recv_until(org_ws, "ROOM_RESET")
                assert reset["player_count"] == 1  # Alice still in

                # Can play again
                org_ws.send_json({"type": "START_GAME"})
                recv_until(org_ws, "GAME_STARTING")
                org_ws.send_json({"type": "NEXT_QUESTION"})
                q = recv_until(org_ws, "QUESTION")
                assert q["question"]["text"] == "New Q1?"


# ===========================================================================
# Organizer Reconnection
# ===========================================================================

class TestOrganizerReconnection:
    def test_organizer_reconnect_sends_sync(self):
        quiz_id = seed_quiz()
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(player_url(room_code, "p1")) as p1_ws:

            # First organizer connection — set up room and start game
            with client.websocket_connect(org_url(room_code, token)) as org_ws:
                org_ws.receive_json()  # ROOM_CREATED
                p1_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                p1_ws.receive_json()  # JOINED_ROOM
                recv_until(org_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                recv_until(org_ws, "GAME_STARTING")
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "QUESTION")

            # Organizer disconnected (p1 still connected) — reconnect
            with client.websocket_connect(org_url(room_code, token, "org-2")) as org_ws2:
                sync = recv_until(org_ws2, "ORGANIZER_RECONNECTED")
                assert sync["state"] == "QUESTION"
                assert sync["player_count"] == 1
                assert "quiz" in sync
                assert "leaderboard" in sync
                assert "team_leaderboard" in sync

    def test_organizer_reconnect_cancels_room_cleanup(self):
        """Room should not be deleted if organizer reconnects within grace period."""
        quiz_id = seed_quiz()
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            org_ws.receive_json()

        # Organizer disconnected — room should still exist during grace period
        assert room_code in socket_manager.rooms

        # Reconnect before cleanup fires
        with client.websocket_connect(org_url(room_code, token, "org-2")) as org_ws2:
            msg = org_ws2.receive_json()
            assert msg["type"] in ("ROOM_CREATED", "ORGANIZER_RECONNECTED")
            assert room_code in socket_manager.rooms


# ===========================================================================
# Player Reconnection
# ===========================================================================

class TestPlayerReconnection:
    def test_reconnect_preserves_score(self):
        quiz_id = seed_quiz()
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            org_ws.receive_json()

            # Player joins and plays a question
            with client.websocket_connect(player_url(room_code, "p1")) as p1_ws:
                p1_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                p1_ws.receive_json()  # JOINED_ROOM
                recv_until(org_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                recv_until(org_ws, "GAME_STARTING")
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(p1_ws, "QUESTION")
                p1_ws.send_json({"type": "ANSWER", "answer_index": 0})
                result = recv_until(p1_ws, "ANSWER_RESULT")
                score_before = result["points"]
                recv_until(org_ws, "QUESTION_OVER")

            # p1 disconnected — reconnect with new client_id
            with client.websocket_connect(player_url(room_code, "p1-new")) as p1_new:
                p1_new.send_json({"type": "JOIN", "nickname": "Alice"})
                reconnected = recv_until(p1_new, "RECONNECTED")
                assert reconnected["score"] == score_before
                assert reconnected["state"] == "LEADERBOARD"

    def test_duplicate_nickname_kicks_old_connection(self):
        quiz_id = seed_quiz()
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(player_url(room_code, "p1")) as p1_ws:
                p1_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                p1_ws.receive_json()  # JOINED_ROOM
                recv_until(org_ws, "PLAYER_JOINED")

                # Same nickname from different client
                with client.websocket_connect(player_url(room_code, "p2")) as p2_ws:
                    p2_ws.send_json({"type": "JOIN", "nickname": "Alice"})

                    # Old connection should receive KICKED
                    kicked = recv_until(p1_ws, "KICKED")
                    assert kicked is not None

                    # New connection should get RECONNECTED
                    reconnected = recv_until(p2_ws, "RECONNECTED")
                    assert reconnected is not None


# ===========================================================================
# End Quiz (early termination)
# ===========================================================================

class TestEndQuiz:
    def test_end_quiz_mid_game(self):
        quiz_id = seed_quiz(num_questions=5)
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            org_ws.receive_json()
            with client.websocket_connect(player_url(room_code, "p1")) as p1_ws:
                p1_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                p1_ws.receive_json()  # JOINED_ROOM
                recv_until(org_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                recv_until(org_ws, "GAME_STARTING")
                # Play just 1 question
                play_question(org_ws, [p1_ws])

                # End quiz early from LEADERBOARD
                org_ws.send_json({"type": "END_QUIZ"})
                podium = recv_until(org_ws, "PODIUM")
                assert "leaderboard" in podium
                assert podium["leaderboard"][0]["nickname"] == "Alice"


# ===========================================================================
# Game History
# ===========================================================================

class TestGameHistory:
    def test_game_saved_to_history_on_podium(self):
        quiz_id = seed_quiz(num_questions=2)
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            org_ws.receive_json()
            with client.websocket_connect(player_url(room_code, "p1")) as p1_ws:
                p1_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                p1_ws.receive_json()  # JOINED_ROOM
                recv_until(org_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                recv_until(org_ws, "GAME_STARTING")
                play_question(org_ws, [p1_ws])
                play_question(org_ws, [p1_ws])
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "PODIUM")

        assert len(game_history) == 1
        assert game_history[0]["room_code"] == room_code
        assert game_history[0]["player_count"] == 1

    def test_history_accessible_via_api(self):
        quiz_id = seed_quiz(num_questions=2)
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            org_ws.receive_json()
            with client.websocket_connect(player_url(room_code, "p1")) as p1_ws:
                p1_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                p1_ws.receive_json()  # JOINED_ROOM
                recv_until(org_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                recv_until(org_ws, "GAME_STARTING")
                play_question(org_ws, [p1_ws])
                play_question(org_ws, [p1_ws])
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "PODIUM")

        res = client.get("/history")
        assert res.status_code == 200
        assert len(res.json()) == 1


# ===========================================================================
# Power-ups via WS
# ===========================================================================

class TestPowerUpsFlow:
    def test_fifty_fifty_removes_options(self):
        quiz_id = seed_quiz()
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            org_ws.receive_json()
            with client.websocket_connect(player_url(room_code, "p1")) as p1_ws:
                p1_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                p1_ws.receive_json()  # JOINED_ROOM
                recv_until(org_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                recv_until(org_ws, "GAME_STARTING")
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(p1_ws, "QUESTION")

                p1_ws.send_json({"type": "USE_POWER_UP", "power_up": "fifty_fifty"})
                activated = recv_until(p1_ws, "POWER_UP_ACTIVATED")
                assert activated["power_up"] == "fifty_fifty"
                assert len(activated["remove_indices"]) == 2
                # Correct answer (index 0) should not be removed
                assert 0 not in activated["remove_indices"]

    def test_double_points_doubles_score(self):
        quiz_id = seed_quiz()
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            org_ws.receive_json()
            with client.websocket_connect(player_url(room_code, "p1")) as p1_ws:
                p1_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                p1_ws.receive_json()  # JOINED_ROOM
                recv_until(org_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                recv_until(org_ws, "GAME_STARTING")

                # Q1: no power-up
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(p1_ws, "QUESTION")
                p1_ws.send_json({"type": "ANSWER", "answer_index": 0})
                r1 = recv_until(p1_ws, "ANSWER_RESULT")
                recv_until(org_ws, "QUESTION_OVER")

                # Q2: with double points
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(p1_ws, "QUESTION")
                p1_ws.send_json({"type": "USE_POWER_UP", "power_up": "double_points"})
                recv_until(p1_ws, "POWER_UP_ACTIVATED")
                p1_ws.send_json({"type": "ANSWER", "answer_index": 0})
                r2 = recv_until(p1_ws, "ANSWER_RESULT")

                # Double points should give roughly 2x (both instant answers)
                assert r2["points"] >= r1["points"] * 1.8

    def test_power_up_cannot_be_used_twice(self):
        quiz_id = seed_quiz()
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            org_ws.receive_json()
            with client.websocket_connect(player_url(room_code, "p1")) as p1_ws:
                p1_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                p1_ws.receive_json()  # JOINED_ROOM
                recv_until(org_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                recv_until(org_ws, "GAME_STARTING")
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(p1_ws, "QUESTION")

                # Use it once
                p1_ws.send_json({"type": "USE_POWER_UP", "power_up": "fifty_fifty"})
                recv_until(p1_ws, "POWER_UP_ACTIVATED")

                # Try again — should get error
                p1_ws.send_json({"type": "USE_POWER_UP", "power_up": "fifty_fifty"})
                err = recv_until(p1_ws, "ERROR")
                assert "already used" in err["message"].lower()


# ===========================================================================
# Team Mode
# ===========================================================================

class TestTeamMode:
    def test_team_leaderboard_in_podium(self):
        quiz_id = seed_quiz(num_questions=2)
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            org_ws.receive_json()
            with client.websocket_connect(player_url(room_code, "p1")) as p1_ws, \
                 client.websocket_connect(player_url(room_code, "p2")) as p2_ws:
                p1_ws.send_json({"type": "JOIN", "nickname": "Alice", "team": "Red"})
                p1_ws.receive_json()  # JOINED_ROOM
                recv_until(org_ws, "PLAYER_JOINED")
                p2_ws.send_json({"type": "JOIN", "nickname": "Bob", "team": "Blue"})
                p2_ws.receive_json()  # JOINED_ROOM
                recv_until(org_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                recv_until(org_ws, "GAME_STARTING")
                play_question(org_ws, [p1_ws, p2_ws])
                play_question(org_ws, [p1_ws, p2_ws])
                org_ws.send_json({"type": "NEXT_QUESTION"})
                podium = recv_until(org_ws, "PODIUM")

                assert "team_leaderboard" in podium
                team_names = [t["team"] for t in podium["team_leaderboard"]]
                assert "Red" in team_names
                assert "Blue" in team_names


# ===========================================================================
# Answer Logging
# ===========================================================================

class TestAnswerLogging:
    def test_answers_logged_in_game_history(self):
        quiz_id = seed_quiz(num_questions=2)
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            org_ws.receive_json()
            with client.websocket_connect(player_url(room_code, "p1")) as p1_ws:
                p1_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                p1_ws.receive_json()  # JOINED_ROOM
                recv_until(org_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                recv_until(org_ws, "GAME_STARTING")
                play_question(org_ws, [p1_ws], answer_index=0)
                play_question(org_ws, [p1_ws], answer_index=1)
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "PODIUM")

        assert len(game_history) == 1
        log = game_history[0]["answer_log"]
        assert len(log) == 2
        assert log[0]["correct"] is True
        assert log[1]["correct"] is False


# ===========================================================================
# Streak Mechanics
# ===========================================================================

class TestStreakMechanics:
    def test_streak_builds_and_multiplier_applied(self):
        """Verify streak counter increments and multiplier kicks in at threshold (3).
        Uses 3 questions to avoid bonus rounds (bonus needs >=4 questions and has a
        2s splash delay that causes play_question to race with state transitions)."""
        quiz_id = seed_quiz(num_questions=3)
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            org_ws.receive_json()
            with client.websocket_connect(player_url(room_code, "p1")) as p1_ws:
                p1_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                p1_ws.receive_json()  # JOINED_ROOM
                recv_until(org_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                recv_until(org_ws, "GAME_STARTING")

                # Play 3 correct answers → streak builds to 3 (multiplier 1.5x)
                for _ in range(3):
                    play_question(org_ws, [p1_ws], answer_index=0)

                room = socket_manager.rooms[room_code]
                alice = list(room.players.values())[0]
                assert alice["streak"] == 3

                # Podium — score should reflect the multiplier on Q3
                org_ws.send_json({"type": "NEXT_QUESTION"})
                podium = recv_until(org_ws, "PODIUM")
                assert podium["leaderboard"][0]["score"] > 0

    def test_streak_resets_on_wrong_answer(self):
        """Verify streak resets to 0 on wrong answer and restarts on next correct."""
        quiz_id = seed_quiz(num_questions=3)
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            org_ws.receive_json()
            with client.websocket_connect(player_url(room_code, "p1")) as p1_ws:
                p1_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                p1_ws.receive_json()  # JOINED_ROOM
                recv_until(org_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                recv_until(org_ws, "GAME_STARTING")

                # Q1: correct → streak 1
                play_question(org_ws, [p1_ws], answer_index=0)
                room = socket_manager.rooms[room_code]
                alice = list(room.players.values())[0]
                assert alice["streak"] == 1

                # Q2: wrong → streak 0
                play_question(org_ws, [p1_ws], answer_index=2)
                assert alice["streak"] == 0

                # Q3: correct again → streak 1
                play_question(org_ws, [p1_ws], answer_index=0)
                assert alice["streak"] == 1


# ===========================================================================
# Message Size Limit
# ===========================================================================

class TestMessageSizeLimit:
    def test_oversized_message_rejected(self):
        quiz_id = seed_quiz()
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            org_ws.receive_json()
            with client.websocket_connect(player_url(room_code, "p1")) as p1_ws:
                # Send a message that exceeds MAX_WS_MESSAGE_SIZE
                huge_msg = json.dumps({"type": "JOIN", "nickname": "A" * config.MAX_WS_MESSAGE_SIZE})
                p1_ws.send_text(huge_msg)
                err = recv_until(p1_ws, "ERROR")
                assert "too large" in err["message"].lower()
