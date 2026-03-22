"""Tests for Round 1 bug fixes: nickname hijacking, import validation,
game_type validation, WMLT vote edge cases, decrement race condition."""
import sys
import os
import uuid
import threading
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fastapi.testclient import TestClient
from main import app, quizzes, mlt_scenarios, mlt_timestamps
from socket_manager import socket_manager
import config
import db


# --- Fixtures ---

def _teardown_rooms():
    for room in socket_manager.rooms.values():
        if room.timer_task:
            room.timer_task.cancel()
            room.timer_task = None
        if room._organizer_cleanup_task:
            room._organizer_cleanup_task.cancel()
            room._organizer_cleanup_task = None
    socket_manager.rooms.clear()
    socket_manager.stop_cleanup_loop()


@pytest.fixture(autouse=True)
def clear_state(tmp_path, monkeypatch):
    _teardown_rooms()
    quizzes.clear()
    mlt_scenarios.clear()
    mlt_timestamps.clear()
    saved_origins = socket_manager.allowed_origins
    socket_manager.allowed_origins = []
    # Fresh DB per test
    monkeypatch.setattr(config, "JWT_SECRET", "test-secret-32bytes-long-enough!!")
    monkeypatch.setattr(db, "_local", threading.local())
    monkeypatch.setattr(db, "DB_DIR", str(tmp_path))
    monkeypatch.setattr(db, "DB_PATH", os.path.join(str(tmp_path), "revelry.db"))
    db.init_db()
    yield
    _teardown_rooms()
    quizzes.clear()
    mlt_scenarios.clear()
    mlt_timestamps.clear()
    socket_manager.allowed_origins = saved_origins


client = TestClient(app)
_DEVICE_HEADERS = {"X-Device-Id": str(uuid.uuid4())}


# --- Helpers ---

def seed_quiz(num_questions=3):
    quiz_data = {
        "quiz_title": "Test Quiz",
        "questions": [
            {"id": i + 1, "text": f"Question {i + 1}?",
             "options": ["A", "B", "C", "D"], "answer_index": 0}
            for i in range(num_questions)
        ],
    }
    quiz_id = str(uuid.uuid4())
    quizzes[quiz_id] = quiz_data
    return quiz_id


def seed_mlt(num_statements=3):
    mlt_data = {
        "game_title": "Test MLT",
        "statements": [
            {"id": i + 1, "text": f"Who's most likely to do thing {i + 1}?"}
            for i in range(num_statements)
        ],
    }
    mlt_id = str(uuid.uuid4())
    mlt_scenarios[mlt_id] = mlt_data
    mlt_timestamps[mlt_id] = time.time()
    return mlt_id


def create_room(quiz_id=None, mlt_id=None, game_type="quiz", time_limit=30):
    body = {"time_limit": time_limit, "game_type": game_type}
    if game_type == "wmlt" and mlt_id:
        body["mlt_id"] = mlt_id
    elif quiz_id:
        body["quiz_id"] = quiz_id
    res = client.post("/room/create", json=body)
    assert res.status_code == 200
    data = res.json()
    return data["room_code"], data["organizer_token"]


def org_url(room_code, token, client_id="org-1"):
    return f"/ws/{room_code}/{client_id}?organizer=true&token={token}"


def player_url(room_code, client_id):
    return f"/ws/{room_code}/{client_id}"


def recv_until(ws, msg_type, max_messages=50):
    for i in range(max_messages):
        try:
            data = ws.receive_json()
        except Exception as e:
            raise TimeoutError(f"Closed waiting for {msg_type} (after {i}): {e}")
        if data.get("type") == msg_type:
            return data
    raise TimeoutError(f"Never received {msg_type} after {max_messages} messages")


# ===========================================================================
# Nickname Case-Insensitive Hijacking Prevention
# ===========================================================================

class TestNicknameCaseSensitivity:
    def test_same_nickname_different_case_rejected(self):
        """Player 'alice' should not be able to join if 'Alice' already exists."""
        quiz_id = seed_quiz()
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            org_ws.receive_json()  # ROOM_CREATED
            with client.websocket_connect(player_url(room_code, "p1")) as p1_ws:
                p1_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                recv_until(p1_ws, "JOINED_ROOM")
                recv_until(org_ws, "PLAYER_JOINED")

                # Second player with different case should be rejected
                with client.websocket_connect(player_url(room_code, "p2")) as p2_ws:
                    p2_ws.send_json({"type": "JOIN", "nickname": "alice"})
                    # Should get ERROR then connection closed
                    msg = p2_ws.receive_json()
                    assert msg["type"] == "ERROR"
                    assert "taken" in msg["message"].lower() or "Nickname" in msg["message"]


# ===========================================================================
# Quiz Import Validation
# ===========================================================================

class TestImportValidation:
    def test_import_valid_quiz(self):
        res = client.post("/quiz/import", json={
            "quiz": {
                "quiz_title": "Imported",
                "questions": [
                    {"id": 1, "text": "Q1?", "options": ["A", "B", "C", "D"], "answer_index": 0}
                ]
            }
        })
        assert res.status_code == 200

    def test_import_invalid_answer_index_rejected(self):
        """answer_index out of bounds should be rejected."""
        res = client.post("/quiz/import", json={
            "quiz": {
                "quiz_title": "Bad Quiz",
                "questions": [
                    {"id": 1, "text": "Q1?", "options": ["A", "B", "C", "D"], "answer_index": 99}
                ]
            }
        })
        assert res.status_code == 422

    def test_import_missing_options_rejected(self):
        """Questions without options should be rejected."""
        res = client.post("/quiz/import", json={
            "quiz": {
                "quiz_title": "No Options",
                "questions": [
                    {"id": 1, "text": "Q1?", "answer_index": 0}
                ]
            }
        })
        assert res.status_code == 422

    def test_import_empty_questions_rejected(self):
        res = client.post("/quiz/import", json={
            "quiz": {"quiz_title": "Empty", "questions": []}
        })
        assert res.status_code == 422


# ===========================================================================
# RESET_ROOM Game Type Validation
# ===========================================================================

class TestResetRoomGameType:
    def test_reset_room_rejects_invalid_game_type(self):
        """Invalid game_type should fall back to current room type."""
        quiz_id = seed_quiz(num_questions=2)
        room_code, token = create_room(quiz_id)

        with client.websocket_connect(org_url(room_code, token)) as org_ws:
            org_ws.receive_json()  # ROOM_CREATED
            with client.websocket_connect(player_url(room_code, "p1")) as p1_ws:
                p1_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                recv_until(p1_ws, "JOINED_ROOM")
                recv_until(org_ws, "PLAYER_JOINED")

                # Play to podium
                org_ws.send_json({"type": "START_GAME"})
                recv_until(org_ws, "GAME_STARTING")
                # Play 2 questions
                for _ in range(2):
                    org_ws.send_json({"type": "NEXT_QUESTION"})
                    recv_until(org_ws, "QUESTION")
                    recv_until(p1_ws, "QUESTION")
                    p1_ws.send_json({"type": "ANSWER", "answer_index": 0})
                    recv_until(p1_ws, "ANSWER_RESULT")
                    recv_until(org_ws, "QUESTION_OVER")
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "PODIUM")

                # Reset with invalid game_type
                new_quiz_id = seed_quiz(num_questions=2)
                org_ws.send_json({
                    "type": "RESET_ROOM",
                    "content_id": new_quiz_id,
                    "game_type": "invalid_type",
                    "time_limit": 20,
                })
                reset = recv_until(org_ws, "ROOM_RESET")
                # Should fall back to original game type
                assert reset["game_type"] == "quiz"


# ===========================================================================
# Decrement Entitlement Race Condition
# ===========================================================================

class TestDecrementEntitlement:
    def test_decrement_cannot_go_negative(self):
        """Even with concurrent calls, games_remaining should never go below 0."""
        device_id = str(uuid.uuid4())
        ent_id = str(uuid.uuid4())
        db.create_entitlement(ent_id, device_id, games=1)

        # Try to decrement twice concurrently
        results = []

        def decrement():
            results.append(db.decrement_entitlement(ent_id))

        t1 = threading.Thread(target=decrement)
        t2 = threading.Thread(target=decrement)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Exactly one should succeed
        assert results.count(True) == 1
        assert results.count(False) == 1

        # Verify games_remaining is 0 via active entitlement check (should be exhausted)
        ent = db.get_active_entitlement(device_id)
        assert ent is None  # exhausted, so no active entitlement

    def test_decrement_exhausted_entitlement_fails(self):
        """Decrementing an already-exhausted entitlement should fail."""
        device_id = str(uuid.uuid4())
        ent_id = str(uuid.uuid4())
        db.create_entitlement(ent_id, device_id, games=1)
        assert db.decrement_entitlement(ent_id) is True  # 1 -> 0
        assert db.decrement_entitlement(ent_id) is False  # already exhausted


# ===========================================================================
# Round 2: Session Token Type Validation
# ===========================================================================

class TestSessionTokenTypeValidation:
    def test_session_token_rejects_non_string_user_id(self):
        """Token with integer user_id should be rejected."""
        import jwt as pyjwt
        from datetime import datetime, timezone, timedelta
        token = pyjwt.encode(
            {"user_id": 12345, "device_id": "valid-device", "type": "session",
             "exp": datetime.now(timezone.utc) + timedelta(days=1)},
            config.JWT_SECRET, algorithm="HS256",
        )
        import auth
        assert auth.verify_session_token(token) is None

    def test_session_token_rejects_premium_token(self):
        """A premium token should not pass session verification."""
        import jwt as pyjwt
        from datetime import datetime, timezone, timedelta
        token = pyjwt.encode(
            {"device_id": "some-device", "type": "party_pass",
             "exp": datetime.now(timezone.utc) + timedelta(days=1)},
            config.JWT_SECRET, algorithm="HS256",
        )
        import auth
        assert auth.verify_session_token(token) is None

    def test_valid_session_token_passes(self):
        import auth
        token = auth.create_session_token("user-123", "device-456")
        result = auth.verify_session_token(token)
        assert result is not None
        assert result["user_id"] == "user-123"
        assert result["device_id"] == "device-456"


# ===========================================================================
# Round 2: MLT Import Validation
# ===========================================================================

class TestMLTImportValidation:
    def test_import_valid_mlt(self):
        res = client.post("/mlt/import", json={
            "game": {
                "game_title": "Test MLT",
                "statements": [
                    {"id": 1, "text": "Who's most likely to do X?"}
                ]
            }
        })
        assert res.status_code == 200

    def test_import_mlt_empty_statements_rejected(self):
        res = client.post("/mlt/import", json={
            "game": {"game_title": "Empty", "statements": []}
        })
        assert res.status_code == 422

    def test_import_mlt_missing_text_rejected(self):
        res = client.post("/mlt/import", json={
            "game": {
                "game_title": "Bad",
                "statements": [{"id": 1}]
            }
        })
        assert res.status_code == 422
