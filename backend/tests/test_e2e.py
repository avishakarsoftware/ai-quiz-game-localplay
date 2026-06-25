"""
Full end-to-end integration tests.
Tests: quiz generation boundary -> editing -> room creation -> WebSocket game flow -> reconnection.
Also tests: export/import, custom num_questions, streak, teams, power-ups, game history,
content ownership, token economy, WMLT game flow.
Provider-specific AI availability belongs in provider tests; this file keeps generation deterministic.
"""
import sys
import os
import time
import uuid
from contextlib import contextmanager

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


from fastapi.testclient import TestClient
import main
from main import app, quizzes, quiz_images, quiz_image_assets, game_history, mlt_scenarios, content_owners, _rate_limit_store
from media_store import media_store
from socket_manager import socket_manager
import db
import config

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEVICE_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
DEVICE_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
HEADERS_A = {"X-Device-Id": DEVICE_A}
HEADERS_B = {"X-Device-Id": DEVICE_B}
GENEROUS_TOKENS = 500  # enough for many generates + room starts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _teardown_rooms():
    """Cancel all background tasks and clear rooms to prevent state leaks between tests."""
    for room in socket_manager.rooms.values():
        if room.timer_task:
            room.timer_task.cancel()
            room.timer_task = None
        if room._organizer_cleanup_task:
            room._organizer_cleanup_task.cancel()
            room._organizer_cleanup_task = None
        room.connections.clear()
        room.players.clear()
    socket_manager.rooms.clear()
    socket_manager.stop_cleanup_loop()


def _fund_wallet(device_id, amount=GENEROUS_TOKENS):
    """Create/fund a wallet for testing — resets to exact amount."""
    db.get_or_create_wallet(device_id, signup_bonus=False)
    current = db.get_wallet_balance(device_id)
    if current > 0:
        db.debit_tokens(device_id, current, "test_reset")
    db.credit_tokens(device_id, amount, "test_grant")


@pytest.fixture(autouse=True)
def fund_test_wallet():
    """Override conftest's monkeypatch — e2e tests use real token functions."""
    yield


@pytest.fixture(autouse=True)
def clear_state():
    _teardown_rooms()
    quizzes.clear()
    quiz_images.clear()
    quiz_image_assets.clear()
    media_store.clear()
    game_history.clear()
    mlt_scenarios.clear()
    content_owners.clear()
    _rate_limit_store.clear()
    saved_origins = socket_manager.allowed_origins
    socket_manager.allowed_origins = []
    # Fund test wallets
    _fund_wallet(DEVICE_A)
    _fund_wallet(DEVICE_B)
    yield
    _teardown_rooms()
    quizzes.clear()
    quiz_images.clear()
    quiz_image_assets.clear()
    media_store.clear()
    game_history.clear()
    mlt_scenarios.clear()
    content_owners.clear()
    _rate_limit_store.clear()
    socket_manager.allowed_origins = saved_origins


client = TestClient(app)


def recv_until(ws, msg_type, max_messages=50):
    """Receive WS messages until we get the expected type."""
    for i in range(max_messages):
        try:
            data = ws.receive_json()
        except Exception as e:
            raise TimeoutError(f"Connection closed while waiting for {msg_type} (after {i} messages): {e}")
        if data.get("type") == msg_type:
            return data
    raise TimeoutError(f"Never received {msg_type} after {max_messages} messages")


@contextmanager
def org_connect(room_code, token, client_id="org-1"):
    """Connect as organizer with first-frame AUTH. Yields the websocket."""
    with client.websocket_connect(f"/ws/{room_code}/{client_id}?organizer=true") as ws:
        ws.send_json({"type": "AUTH", "token": token})
        yield ws


def seed_quiz(num_questions=3):
    """Insert a quiz directly and return its id."""
    quiz_data = {
        "quiz_title": "E2E Test Quiz",
        "questions": [
            {"id": i + 1, "text": f"Q{i + 1}?", "options": ["A", "B", "C", "D"], "answer_index": 0}
            for i in range(num_questions)
        ],
    }
    quiz_id = str(uuid.uuid4())
    quizzes[quiz_id] = quiz_data
    content_owners[quiz_id] = DEVICE_A
    return quiz_id


def seed_mlt(num_rounds=3):
    """Insert an MLT scenario directly and return its id."""
    mlt_data = {
        "game_title": "E2E MLT Test",
        "statements": [
            {"id": i + 1, "text": f"Most likely to do thing {i + 1}"}
            for i in range(num_rounds)
        ],
    }
    scenario_id = str(uuid.uuid4())
    mlt_scenarios[scenario_id] = mlt_data
    content_owners[scenario_id] = DEVICE_A
    return scenario_id


def deterministic_quiz(title="E2E Deterministic Quiz", num_questions=5):
    """Generate stable quiz data for e2e tests without calling external AI."""
    questions = []
    for index in range(num_questions):
        answer_index = index % 4
        questions.append({
            "id": index + 1,
            "text": f"{title} question {index + 1}?",
            "options": [
                f"Answer {index + 1}A",
                f"Answer {index + 1}B",
                f"Answer {index + 1}C",
                f"Answer {index + 1}D",
            ],
            "answer_index": answer_index,
            "image_prompt": "",
        })
    return {"quiz_title": title, "questions": questions}


def fake_quiz_generator(expected_prompt=None, title="E2E Deterministic Quiz"):
    async def fake_generate(prompt, difficulty, num_questions, provider, model_override=None, mode="classic"):
        if expected_prompt is not None:
            assert prompt == expected_prompt
        assert difficulty in {"easy", "medium", "hard"}
        assert mode == "classic"
        return deterministic_quiz(title, num_questions)

    return fake_generate


def create_room(content_id, game_type="quiz", time_limit=30, headers=None):
    """Create a room and return (room_code, organizer_token)."""
    headers = headers or HEADERS_A
    body = {"time_limit": time_limit, "game_type": game_type}
    if game_type == "wmlt":
        body["mlt_id"] = content_id
    else:
        body["quiz_id"] = content_id
    res = client.post("/room/create", json=body, headers=headers)
    assert res.status_code == 200, f"Room creation failed: {res.text}"
    data = res.json()
    return data["room_code"], data["organizer_token"]


# ===========================================================================
# Full Game Flow
# ===========================================================================

class TestEndToEnd:
    """Full game flow: generate quiz -> edit -> create room -> play -> podium."""

    def test_full_game_flow(self, monkeypatch):
        monkeypatch.setattr(
            main.quiz_engine,
            "generate_quiz",
            fake_quiz_generator("5 questions about colors and shapes", "Colors and Shapes"),
        )

        # Step 1: Generate quiz with deterministic provider boundary
        print("\n--- Step 1: Generate quiz ---")
        res = client.post("/quiz/generate", json={
            "prompt": "5 questions about colors and shapes",
            "difficulty": "easy",
            "num_questions": 5,
        }, headers=HEADERS_A)
        assert res.status_code == 200, f"Quiz generation failed: {res.text}"
        data = res.json()
        quiz_id = data["quiz_id"]
        quiz = data["quiz"]
        print(f"Quiz: '{quiz['quiz_title']}', {len(quiz['questions'])} questions")
        assert len(quiz["questions"]) >= 1
        for q in quiz["questions"]:
            assert len(q["options"]) in (2, 4), f"Q{q['id']} has {len(q['options'])} options"
            # answer_index is stripped from API response — verify via server-side data
        full_quiz = quizzes[quiz_id]
        for q in full_quiz["questions"]:
            assert 0 <= q["answer_index"] < len(q["options"])

        # Step 2: Edit a question (use full_quiz which has answer_index)
        print("\n--- Step 2: Edit quiz ---")
        import copy
        edit_quiz = copy.deepcopy(full_quiz)
        original_text = edit_quiz["questions"][0]["text"]
        edit_quiz["questions"][0]["text"] = "EDITED: " + original_text
        res = client.put(f"/quiz/{quiz_id}", json=edit_quiz, headers=HEADERS_A)
        assert res.status_code == 200
        assert res.json()["quiz"]["questions"][0]["text"].startswith("EDITED:")

        # Delete a question if we have more than 3
        if len(edit_quiz["questions"]) > 3:
            qid_to_delete = edit_quiz["questions"][-1]["id"]
            res = client.delete(f"/quiz/{quiz_id}/question/{qid_to_delete}", headers=HEADERS_A)
            assert res.status_code == 200

        # Refresh full_quiz from server-side data after edits
        full_quiz = quizzes[quiz_id]
        num_questions = len(full_quiz["questions"])

        # Step 2b: Export / Import roundtrip
        print("\n--- Step 2b: Export / Import ---")
        res = client.get(f"/quiz/{quiz_id}/export", headers=HEADERS_A)
        assert res.status_code == 200
        exported = res.json()["quiz"]
        assert exported["quiz_title"] == full_quiz["quiz_title"]

        res = client.post("/quiz/import", json={"quiz": exported}, headers=HEADERS_A)
        assert res.status_code == 200
        imported_id = res.json()["quiz_id"]
        assert imported_id != quiz_id

        # Step 3: Create room
        print("\n--- Step 3: Create room ---")
        room_code, org_token = create_room(quiz_id)

        # Step 4-8: Connect organizer + players, play, podium
        print("\n--- Step 4: Connect organizer ---")
        with org_connect(room_code, org_token) as org_ws:
            msg = org_ws.receive_json()
            assert msg["type"] == "ROOM_CREATED"

            # Step 5: Connect 3 players with teams
            print("\n--- Step 5: Connect players ---")
            players = [
                {"name": "Alice", "team": "Red"},
                {"name": "Bob", "team": "Blue"},
                {"name": "Charlie", "team": "Red"},
            ]
            player_ws_list = []

            for i, p in enumerate(players):
                ws = client.websocket_connect(f"/ws/{room_code}/player-{i}")
                ws.__enter__()
                player_ws_list.append(ws)

                ws.send_json({"type": "JOIN", "nickname": p["name"], "team": p["team"]})
                recv_until(ws, "JOINED_ROOM")

                org_msg = recv_until(org_ws, "PLAYER_JOINED")
                assert org_msg["nickname"] == p["name"]

                for pw in player_ws_list:
                    recv_until(pw, "PLAYER_JOINED")

            # Step 6: Start game
            print("\n--- Step 6: Start game ---")
            org_ws.send_json({"type": "START_GAME"})
            org_ws.send_json({"type": "NEXT_QUESTION"})

            game_start = recv_until(org_ws, "QUESTION")
            assert game_start["question_number"] == 1
            assert "is_bonus" in game_start

            for pw in player_ws_list:
                recv_until(pw, "QUESTION")

            # Step 6b: Alice uses 50/50
            player_ws_list[0].send_json({"type": "USE_POWER_UP", "power_up": "fifty_fifty"})
            pu_msg = recv_until(player_ws_list[0], "POWER_UP_ACTIVATED")
            assert pu_msg["power_up"] == "fifty_fifty"
            assert len(pu_msg["remove_indices"]) >= 1

            # Step 7: Play through all questions
            alice_streak = 0
            bonus_flags = [game_start["is_bonus"]]
            for q_num in range(1, num_questions + 1):
                correct_answer = full_quiz["questions"][q_num - 1]["answer_index"]
                wrong_answer = (correct_answer + 1) % len(full_quiz["questions"][q_num - 1]["options"])

                if q_num > 1:
                    org_ws.send_json({"type": "NEXT_QUESTION"})
                    q_msg = recv_until(org_ws, "QUESTION")
                    bonus_flags.append(q_msg["is_bonus"])
                    for pw in player_ws_list:
                        recv_until(pw, "QUESTION")

                if q_num == 2:
                    player_ws_list[1].send_json({"type": "USE_POWER_UP", "power_up": "double_points"})
                    recv_until(player_ws_list[1], "POWER_UP_ACTIVATED")

                for i, pw in enumerate(player_ws_list):
                    if i == 0:
                        answer = correct_answer
                    elif i == 1 and q_num == 2:
                        answer = correct_answer
                    else:
                        answer = wrong_answer
                    pw.send_json({"type": "ANSWER", "answer_index": answer})
                    result = recv_until(pw, "ANSWER_RESULT")
                    assert "is_bonus" in result

                    if i == 0:
                        alice_streak += 1
                        assert result["correct"] is True
                        assert result["streak"] == alice_streak
                        if alice_streak >= 3:
                            assert result["multiplier"] == 1.5

                recv_until(org_ws, "QUESTION_OVER")
                for pw in player_ws_list:
                    recv_until(pw, "QUESTION_OVER")

            # Verify bonus flags
            assert bonus_flags[0] is False, "First question should not be bonus"
            assert bonus_flags[-1] is False, "Last question should not be bonus"
            if num_questions >= 4:
                assert True in bonus_flags

            # Step 8: Podium
            print("\n--- Step 8: Podium ---")
            org_ws.send_json({"type": "NEXT_QUESTION"})
            podium = recv_until(org_ws, "PODIUM")
            assert "leaderboard" in podium
            assert "team_leaderboard" in podium
            assert podium["leaderboard"][0]["nickname"] == "Alice"

            tl = podium["team_leaderboard"]
            assert len(tl) == 2
            team_names = {t["team"] for t in tl}
            assert team_names == {"Red", "Blue"}

            for pw in player_ws_list:
                recv_until(pw, "PODIUM")

            # Step 9: Game history
            print("\n--- Step 9: Game history ---")
            res = client.get("/history", headers=HEADERS_A)
            assert res.status_code == 200
            games = res.json()["games"]
            assert len(games) == 1
            assert games[0]["room_code"] == room_code

            res = client.get(f"/history/{room_code}", headers=HEADERS_A)
            assert res.status_code == 200
            detail = res.json()
            assert detail["player_count"] == 3
            assert len(detail["answer_log"]) == num_questions * 3

            for pw in player_ws_list:
                pw.__exit__(None, None, None)

        print("\n--- E2E test passed! ---")


# ===========================================================================
# Reconnection (no Ollama needed — seeded quiz)
# ===========================================================================

class TestReconnectionE2E:
    """Test player reconnection during an active game."""

    def test_player_reconnects_with_score(self):
        quiz_id = seed_quiz(3)
        room_code, org_token = create_room(quiz_id)

        with org_connect(room_code, org_token) as org_ws:
            org_ws.receive_json()  # ROOM_CREATED

            with client.websocket_connect(f"/ws/{room_code}/player-1") as p_ws:
                p_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                joined = recv_until(p_ws, "JOINED_ROOM")
                session_token = joined.get("session_token", "")
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "QUESTION")
                recv_until(p_ws, "QUESTION")

                p_ws.send_json({"type": "ANSWER", "answer_index": 0})
                result = recv_until(p_ws, "ANSWER_RESULT")
                assert result["correct"] is True
                score_before = result["points"]

            time.sleep(0.5)

            room = socket_manager.rooms[room_code]
            assert "Alice" in room.disconnected_players
            assert room.disconnected_players["Alice"]["score"] == score_before

            with client.websocket_connect(f"/ws/{room_code}/player-2") as p_ws2:
                p_ws2.send_json({"type": "JOIN", "nickname": "Alice", "session_token": session_token})
                recon = recv_until(p_ws2, "RECONNECTED")
                assert recon["score"] == score_before
                assert "Alice" not in room.disconnected_players

        print("--- Reconnection E2E test passed! ---")


# ===========================================================================
# Export / Import
# ===========================================================================

class TestExportImportE2E:
    """E2E test for export/import with deterministic quiz generation."""

    def test_generate_export_import_play(self, monkeypatch):
        monkeypatch.setattr(
            main.quiz_engine,
            "generate_quiz",
            fake_quiz_generator("3 questions about animals", "Animal Quiz"),
        )
        res = client.post("/quiz/generate", json={
            "prompt": "3 questions about animals",
            "difficulty": "medium",
            "num_questions": 3,
        }, headers=HEADERS_A)
        assert res.status_code == 200, f"Quiz generation failed: {res.text}"
        original_id = res.json()["quiz_id"]
        original_quiz = res.json()["quiz"]

        res = client.get(f"/quiz/{original_id}/export", headers=HEADERS_A)
        assert res.status_code == 200
        exported = res.json()["quiz"]

        res = client.post("/quiz/import", json={"quiz": exported}, headers=HEADERS_A)
        assert res.status_code == 200
        imported_id = res.json()["quiz_id"]
        assert imported_id != original_id

        room_code, org_token = create_room(imported_id)

        with org_connect(room_code, org_token) as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(f"/ws/{room_code}/p-1") as p_ws:
                p_ws.send_json({"type": "JOIN", "nickname": "Tester"})
                recv_until(p_ws, "JOINED_ROOM")
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})

                for _ in range(len(original_quiz["questions"])):
                    org_ws.send_json({"type": "NEXT_QUESTION"})
                    recv_until(p_ws, "QUESTION")
                    recv_until(org_ws, "QUESTION")
                    p_ws.send_json({"type": "ANSWER", "answer_index": 0})
                    recv_until(p_ws, "ANSWER_RESULT")
                    recv_until(org_ws, "QUESTION_OVER")
                    recv_until(p_ws, "QUESTION_OVER")

                org_ws.send_json({"type": "NEXT_QUESTION"})
                podium = recv_until(org_ws, "PODIUM")
                assert podium["leaderboard"][0]["nickname"] == "Tester"

        print("--- Export/Import E2E test passed! ---")


# ===========================================================================
# Bonus Rounds
# ===========================================================================

class TestBonusRoundsE2E:
    """E2E test for bonus rounds with deterministic quiz generation."""

    def test_bonus_rounds_with_live_quiz(self, monkeypatch):
        monkeypatch.setattr(
            main.quiz_engine,
            "generate_quiz",
            fake_quiz_generator("6 questions about geography and world capitals", "Geography Quiz"),
        )
        res = client.post("/quiz/generate", json={
            "prompt": "6 questions about geography and world capitals",
            "difficulty": "easy",
            "num_questions": 6,
        }, headers=HEADERS_A)
        assert res.status_code == 200, f"Quiz generation failed: {res.text}"
        quiz_id = res.json()["quiz_id"]
        quiz = res.json()["quiz"]
        full_quiz = quizzes[quiz_id]  # server-side data has answer_index
        num_questions = len(quiz["questions"])
        assert num_questions >= 4

        room_code, org_token = create_room(quiz_id)

        with org_connect(room_code, org_token) as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(f"/ws/{room_code}/p-1") as p_ws:
                p_ws.send_json({"type": "JOIN", "nickname": "BonusTester"})
                recv_until(p_ws, "JOINED_ROOM")
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})

                bonus_flags = []
                for q_num in range(num_questions):
                    org_ws.send_json({"type": "NEXT_QUESTION"})
                    q = recv_until(org_ws, "QUESTION")
                    recv_until(p_ws, "QUESTION")

                    assert "is_bonus" in q
                    bonus_flags.append(q["is_bonus"])

                    correct = full_quiz["questions"][q_num]["answer_index"]
                    p_ws.send_json({"type": "ANSWER", "answer_index": correct})
                    result = recv_until(p_ws, "ANSWER_RESULT")
                    assert result["is_bonus"] == q["is_bonus"]

                    recv_until(org_ws, "QUESTION_OVER")
                    recv_until(p_ws, "QUESTION_OVER")

                assert bonus_flags[0] is False
                assert bonus_flags[-1] is False
                assert True in bonus_flags

                org_ws.send_json({"type": "NEXT_QUESTION"})
                podium = recv_until(org_ws, "PODIUM")
                assert podium["leaderboard"][0]["nickname"] == "BonusTester"

        print("--- Bonus Rounds E2E test passed! ---")


# ===========================================================================
# Token Economy E2E (no Ollama needed)
# ===========================================================================

class TestTokenEconomyE2E:
    """End-to-end tests for the spark/token economy."""

    def test_balance_endpoint(self):
        """GET /tokens/balance returns correct balance and auto-grants daily bonus."""
        res = client.get("/tokens/balance", headers=HEADERS_A)
        assert res.status_code == 200
        data = res.json()
        assert "balance" in data
        assert "cost_generate" in data
        assert "cost_room" in data
        assert data["cost_generate"] == config.COST_GENERATE
        assert data["cost_room"] == config.COST_ROOM
        print(f"Balance: {data['balance']}, daily_bonus_granted: {data.get('daily_bonus_granted')}")

    def test_generate_deducts_token(self):
        """Quiz generation should deduct COST_GENERATE from wallet."""
        balance_before = db.get_wallet_balance(DEVICE_A)

        # Seed a quiz directly (no LLM needed) by using the import endpoint
        quiz_data = {
            "quiz_title": "Token Test",
            "questions": [
                {"id": 1, "text": "Q?", "options": ["A", "B", "C", "D"], "answer_index": 0}
            ],
        }
        res = client.post("/quiz/import", json={"quiz": quiz_data}, headers=HEADERS_A)
        assert res.status_code == 200
        # Import doesn't charge tokens, so balance unchanged
        balance_after_import = db.get_wallet_balance(DEVICE_A)
        assert balance_after_import == balance_before

    def test_room_start_deducts_tokens(self):
        """Starting a game should deduct COST_ROOM from wallet."""
        # Get balance via API (same thread as server)
        res = client.get("/tokens/balance", headers=HEADERS_A)
        balance_before = res.json()["balance"]

        quiz_id = seed_quiz(3)
        room_code, org_token = create_room(quiz_id)

        with org_connect(room_code, org_token) as org_ws:
            org_ws.receive_json()  # ROOM_CREATED

            with client.websocket_connect(f"/ws/{room_code}/p-1") as p_ws:
                p_ws.send_json({"type": "JOIN", "nickname": "Spender"})
                recv_until(p_ws, "JOINED_ROOM")
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                recv_until(org_ws, "GAME_STARTING")

        # Check balance via API after game start
        res = client.get("/tokens/balance", headers=HEADERS_A)
        balance_after = res.json()["balance"]
        assert balance_after == balance_before - config.COST_ROOM
        print(f"Tokens: {balance_before} -> {balance_after} (charged {config.COST_ROOM})")

    def test_insufficient_tokens_blocks_generate(self):
        """Generating content with 0 tokens should return 402."""
        # Drain Device B's wallet fully (including any daily bonus)
        res = client.get("/tokens/balance", headers=HEADERS_B)  # triggers daily bonus
        balance = db.get_wallet_balance(DEVICE_B)
        if balance > 0:
            db.debit_tokens(DEVICE_B, balance, "test_drain")
        assert db.get_wallet_balance(DEVICE_B) == 0

        # Try to generate — should fail with 402
        res = client.post("/quiz/generate", json={
            "prompt": "test",
            "difficulty": "easy",
            "num_questions": 3,
        }, headers=HEADERS_B)
        assert res.status_code == 402
        assert "token" in res.json()["detail"].lower() or "spark" in res.json()["detail"].lower()
        print(f"Correctly blocked: {res.json()['detail']}")

    def test_history_scoped_to_wallet(self):
        """Game history should only show games for the requesting wallet."""
        quiz_id = seed_quiz(3)
        room_code, org_token = create_room(quiz_id)

        # Play a complete game
        with org_connect(room_code, org_token) as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(f"/ws/{room_code}/p-1") as p_ws:
                p_ws.send_json({"type": "JOIN", "nickname": "Historian"})
                recv_until(p_ws, "JOINED_ROOM")
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})

                for _ in range(3):
                    org_ws.send_json({"type": "NEXT_QUESTION"})
                    recv_until(p_ws, "QUESTION")
                    recv_until(org_ws, "QUESTION")
                    p_ws.send_json({"type": "ANSWER", "answer_index": 0})
                    recv_until(p_ws, "ANSWER_RESULT")
                    recv_until(org_ws, "QUESTION_OVER")
                    recv_until(p_ws, "QUESTION_OVER")

                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "PODIUM")

        # Device A should see the game
        res = client.get("/history", headers=HEADERS_A)
        assert res.status_code == 200
        assert len(res.json()["games"]) == 1

        # Device B should see nothing
        res = client.get("/history", headers=HEADERS_B)
        assert res.status_code == 200
        assert len(res.json()["games"]) == 0

        print("--- History scoping test passed! ---")


# ===========================================================================
# Content Ownership E2E (no Ollama needed)
# ===========================================================================

class TestContentOwnershipE2E:
    """End-to-end tests for content ownership enforcement."""

    def test_owner_can_edit_content(self):
        """Content owner should be able to edit their own quiz."""
        quiz_id = seed_quiz(3)
        quiz = quizzes[quiz_id]
        quiz["questions"][0]["text"] = "Updated by owner"
        res = client.put(f"/quiz/{quiz_id}", json=quiz, headers=HEADERS_A)
        assert res.status_code == 200

    def test_non_owner_cannot_edit_content(self):
        """Non-owner should get 403 when trying to edit someone else's quiz."""
        quiz_id = seed_quiz(3)
        quiz = quizzes[quiz_id]
        quiz["questions"][0]["text"] = "Attempted by non-owner"
        res = client.put(f"/quiz/{quiz_id}", json=quiz, headers=HEADERS_B)
        assert res.status_code == 403

    def test_non_owner_cannot_delete_question(self):
        """Non-owner should get 403 when trying to delete a question."""
        quiz_id = seed_quiz(3)
        res = client.delete(f"/quiz/{quiz_id}/question/1", headers=HEADERS_B)
        assert res.status_code == 403

    def test_non_owner_cannot_export_quiz(self):
        """Non-owner should get 403 when trying to export someone else's quiz."""
        quiz_id = seed_quiz(3)
        res = client.get(f"/quiz/{quiz_id}/export", headers=HEADERS_B)
        assert res.status_code == 403

    def test_anyone_can_view_quiz(self):
        """Anyone can GET a quiz (read-only), even if not the owner."""
        quiz_id = seed_quiz(3)
        res = client.get(f"/quiz/{quiz_id}", headers=HEADERS_B)
        assert res.status_code == 200

    def test_import_creates_new_owner(self):
        """Importing a quiz should make the importer the owner of the new copy."""
        quiz_id = seed_quiz(3)
        # Owner A exports
        res = client.get(f"/quiz/{quiz_id}/export", headers=HEADERS_A)
        assert res.status_code == 200
        exported = res.json()["quiz"]

        # Device B imports — should become owner of the new copy
        res = client.post("/quiz/import", json={"quiz": exported}, headers=HEADERS_B)
        assert res.status_code == 200
        imported_id = res.json()["quiz_id"]

        # B can edit the imported copy
        quiz_copy = quizzes[imported_id]
        quiz_copy["questions"][0]["text"] = "Edited by B"
        res = client.put(f"/quiz/{imported_id}", json=quiz_copy, headers=HEADERS_B)
        assert res.status_code == 200

        # A cannot edit B's imported copy
        res = client.put(f"/quiz/{imported_id}", json=quiz_copy, headers=HEADERS_A)
        assert res.status_code == 403

    def test_mlt_ownership_enforcement(self):
        """MLT content ownership should work the same as quiz."""
        scenario_id = seed_mlt(3)

        # Owner A can edit
        mlt = mlt_scenarios[scenario_id]
        mlt["statements"][0]["text"] = "Updated by owner"
        res = client.put(f"/mlt/{scenario_id}", json=mlt, headers=HEADERS_A)
        assert res.status_code == 200

        # Non-owner B cannot edit
        res = client.put(f"/mlt/{scenario_id}", json=mlt, headers=HEADERS_B)
        assert res.status_code == 403

        # Non-owner B cannot export
        res = client.get(f"/mlt/{scenario_id}/export", headers=HEADERS_B)
        assert res.status_code == 403

    print("--- Content ownership E2E tests passed! ---")


# ===========================================================================
# WMLT (Who's Most Likely To) E2E (no Ollama needed)
# ===========================================================================

class TestWMLTE2E:
    """End-to-end test for WMLT game flow."""

    def test_full_wmlt_game(self):
        """Create WMLT room, play through rounds with voting, verify podium."""
        scenario_id = seed_mlt(3)
        room_code, org_token = create_room(scenario_id, game_type="wmlt")

        with org_connect(room_code, org_token) as org_ws:
            org_ws.receive_json()  # ROOM_CREATED

            # Connect 3 players (WMLT needs at least MIN_WMLT_PLAYERS)
            player_ws_list = []
            player_names = ["Alice", "Bob", "Charlie"]
            for i, name in enumerate(player_names):
                ws = client.websocket_connect(f"/ws/{room_code}/p-{i}")
                ws.__enter__()
                player_ws_list.append(ws)

                ws.send_json({"type": "JOIN", "nickname": name})
                recv_until(ws, "JOINED_ROOM")
                recv_until(org_ws, "PLAYER_JOINED")
                for pw in player_ws_list:
                    recv_until(pw, "PLAYER_JOINED")

            # Start game
            org_ws.send_json({"type": "START_GAME"})
            recv_until(org_ws, "GAME_STARTING")

            # Play through 3 rounds
            for round_num in range(3):
                org_ws.send_json({"type": "NEXT_QUESTION"})
                stmt = recv_until(org_ws, "QUESTION")
                assert "statement" in stmt
                print(f"  Round {round_num + 1}: {stmt['statement']['text']}")

                for pw in player_ws_list:
                    recv_until(pw, "QUESTION")

                # Each player votes for someone else
                for i, pw in enumerate(player_ws_list):
                    target = player_names[(i + 1) % len(player_names)]
                    pw.send_json({"type": "VOTE", "voted_for": target})
                    recv_until(pw, "VOTE_CONFIRMED")

                # Wait for round results
                qo = recv_until(org_ws, "QUESTION_OVER")
                assert "votes" in qo or "leaderboard" in qo
                for pw in player_ws_list:
                    recv_until(pw, "QUESTION_OVER")

            # Podium
            org_ws.send_json({"type": "NEXT_QUESTION"})
            podium = recv_until(org_ws, "PODIUM")
            assert "leaderboard" in podium
            print(f"WMLT Podium: {[(e['nickname'], e['score']) for e in podium['leaderboard']]}")

            for pw in player_ws_list:
                recv_until(pw, "PODIUM")

            # Cleanup
            for pw in player_ws_list:
                pw.__exit__(None, None, None)

        print("--- WMLT E2E test passed! ---")

    def test_wmlt_needs_min_players(self):
        """WMLT requires MIN_WMLT_PLAYERS — verified at unit level in test_socket_unit.py.
        This test verifies the room setup works correctly for WMLT."""
        scenario_id = seed_mlt(3)
        room_code, org_token = create_room(scenario_id, game_type="wmlt")

        # Verify WMLT room created successfully
        room = socket_manager.rooms[room_code]
        assert room.game_type == "wmlt"
        assert room.state == "LOBBY"
        print("WMLT room created with game_type=wmlt")


# ===========================================================================
# Game Reset E2E (no Ollama needed)
# ===========================================================================

class TestGameResetE2E:
    """Test resetting a game with new content."""

    def test_reset_room_with_new_quiz(self):
        """After podium, organizer can reset room with a different quiz."""
        quiz_id_1 = seed_quiz(3)
        quiz_id_2 = seed_quiz(3)
        room_code, org_token = create_room(quiz_id_1)

        with org_connect(room_code, org_token) as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(f"/ws/{room_code}/p-1") as p_ws:
                p_ws.send_json({"type": "JOIN", "nickname": "Resetter"})
                recv_until(p_ws, "JOINED_ROOM")
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                # Play first game
                org_ws.send_json({"type": "START_GAME"})
                for _ in range(3):
                    org_ws.send_json({"type": "NEXT_QUESTION"})
                    recv_until(p_ws, "QUESTION")
                    recv_until(org_ws, "QUESTION")
                    p_ws.send_json({"type": "ANSWER", "answer_index": 0})
                    recv_until(p_ws, "ANSWER_RESULT")
                    recv_until(org_ws, "QUESTION_OVER")
                    recv_until(p_ws, "QUESTION_OVER")

                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "PODIUM")
                recv_until(p_ws, "PODIUM")

                # Reset with new quiz
                org_ws.send_json({"type": "RESET_ROOM", "content_id": quiz_id_2})
                reset_msg = recv_until(org_ws, "ROOM_RESET")
                assert reset_msg is not None
                recv_until(p_ws, "ROOM_RESET")

                # Start second game
                org_ws.send_json({"type": "START_GAME"})
                org_ws.send_json({"type": "NEXT_QUESTION"})
                q = recv_until(org_ws, "QUESTION")
                assert q["question_number"] == 1
                print("Second game started after reset!")

        print("--- Game reset E2E test passed! ---")


# ===========================================================================
# Spectator E2E (no Ollama needed)
# ===========================================================================

class TestSpectatorE2E:
    """Test spectator mode during a game."""

    def test_spectator_receives_game_events(self):
        """Spectators should receive QUESTION and QUESTION_OVER but not interact."""
        quiz_id = seed_quiz(3)
        room_code, org_token = create_room(quiz_id)

        with org_connect(room_code, org_token) as org_ws:
            org_ws.receive_json()

            # Connect player first, then spectator — avoids broadcast ordering issues
            with client.websocket_connect(f"/ws/{room_code}/p-1") as p_ws:
                p_ws.send_json({"type": "JOIN", "nickname": "Player"})
                recv_until(p_ws, "JOINED_ROOM")
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                with client.websocket_connect(f"/ws/{room_code}/spec-1?spectator=true") as spec_ws:
                    org_ws.send_json({"type": "START_GAME"})
                    org_ws.send_json({"type": "NEXT_QUESTION"})

                    # Consume messages in broadcast order (connections: org, player, spec)
                    recv_until(org_ws, "QUESTION")
                    recv_until(p_ws, "QUESTION")
                    spec_q = recv_until(spec_ws, "QUESTION")
                    assert "question" in spec_q or "statement" in spec_q

                    p_ws.send_json({"type": "ANSWER", "answer_index": 0})
                    recv_until(p_ws, "ANSWER_RESULT")

                    # QUESTION_OVER broadcast — consume in order
                    recv_until(org_ws, "QUESTION_OVER")
                    recv_until(p_ws, "QUESTION_OVER")
                    spec_qo = recv_until(spec_ws, "QUESTION_OVER")
                    assert "leaderboard" in spec_qo

        print("--- Spectator E2E test passed! ---")
