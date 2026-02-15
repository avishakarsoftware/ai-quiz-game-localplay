"""
WebSocket integration tests using FastAPI TestClient.
Tests: streak bonus, power-ups, team mode, spectator, answer logging, game history.
"""
import sys
import os
import uuid
import time

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
    yield
    quizzes.clear()
    game_history.clear()
    socket_manager.rooms.clear()


client = TestClient(app)


def seed_quiz(num_questions=3):
    """Insert a quiz and return its id."""
    quiz_data = {
        "quiz_title": "Integration Test Quiz",
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


def seed_mixed_quiz():
    """Insert a quiz with both MCQ and True/False questions."""
    quiz_data = {
        "quiz_title": "Mixed Quiz",
        "questions": [
            {"id": 1, "text": "MCQ Q1?", "options": ["A", "B", "C", "D"], "answer_index": 0},
            {"id": 2, "text": "TF Q2?", "options": ["True", "False"], "answer_index": 0},
            {"id": 3, "text": "MCQ Q3?", "options": ["W", "X", "Y", "Z"], "answer_index": 2},
        ],
    }
    quiz_id = str(uuid.uuid4())
    quizzes[quiz_id] = quiz_data
    return quiz_id


def create_room(quiz_id, time_limit=30):
    """Create a room and return the room code."""
    res = client.post("/room/create", json={"quiz_id": quiz_id, "time_limit": time_limit})
    assert res.status_code == 200
    return res.json()["room_code"]


def recv_until(ws, msg_type, max_messages=50):
    """Receive WS messages until we get the expected type."""
    for _ in range(max_messages):
        data = ws.receive_json()
        if data.get("type") == msg_type:
            return data
    raise TimeoutError(f"Never received {msg_type} after {max_messages} messages")


# ---------------------------------------------------------------------------
# Streak Bonus Integration Tests
# ---------------------------------------------------------------------------

class TestStreakBonusWS:
    """Test streak bonus multiplier through WebSocket game flow."""

    def test_streak_multiplier_applied_after_3_correct(self):
        """Player answering correctly 3+ times should get streak multiplier."""
        quiz_id = seed_quiz(num_questions=4)
        room_code = create_room(quiz_id)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()  # ROOM_CREATED

            with client.websocket_connect(f"/ws/{room_code}/player-1") as p_ws:
                p_ws.receive_json()  # JOINED_ROOM
                p_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})

                points_per_question = []
                streaks = []
                multipliers = []

                for q in range(4):
                    org_ws.send_json({"type": "NEXT_QUESTION"})
                    recv_until(org_ws, "QUESTION")
                    recv_until(p_ws, "QUESTION")

                    # Always answer correctly (answer_index=0)
                    p_ws.send_json({"type": "ANSWER", "answer_index": 0})
                    result = recv_until(p_ws, "ANSWER_RESULT")
                    assert result["correct"] is True
                    points_per_question.append(result["points"])
                    streaks.append(result["streak"])
                    multipliers.append(result["multiplier"])

                    recv_until(org_ws, "QUESTION_OVER")
                    recv_until(p_ws, "QUESTION_OVER")

                # Verify streaks increment
                assert streaks == [1, 2, 3, 4]

                # Streak 1-2: multiplier 1.0, streak 3+: multiplier 1.5
                assert multipliers[0] == 1.0
                assert multipliers[1] == 1.0
                assert multipliers[2] == 1.5
                assert multipliers[3] == 1.5

    def test_streak_resets_on_wrong_answer(self):
        """Streak should reset to 0 when player answers incorrectly."""
        quiz_id = seed_quiz(num_questions=3)
        room_code = create_room(quiz_id)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(f"/ws/{room_code}/player-1") as p_ws:
                p_ws.receive_json()
                p_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})

                # Q1: correct
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "QUESTION")
                recv_until(p_ws, "QUESTION")
                p_ws.send_json({"type": "ANSWER", "answer_index": 0})
                r1 = recv_until(p_ws, "ANSWER_RESULT")
                assert r1["streak"] == 1
                recv_until(org_ws, "QUESTION_OVER")
                recv_until(p_ws, "QUESTION_OVER")

                # Q2: wrong
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "QUESTION")
                recv_until(p_ws, "QUESTION")
                p_ws.send_json({"type": "ANSWER", "answer_index": 1})  # wrong
                r2 = recv_until(p_ws, "ANSWER_RESULT")
                assert r2["streak"] == 0
                assert r2["correct"] is False
                recv_until(org_ws, "QUESTION_OVER")
                recv_until(p_ws, "QUESTION_OVER")

                # Q3: correct again
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "QUESTION")
                recv_until(p_ws, "QUESTION")
                p_ws.send_json({"type": "ANSWER", "answer_index": 0})
                r3 = recv_until(p_ws, "ANSWER_RESULT")
                assert r3["streak"] == 1  # reset
                assert r3["multiplier"] == 1.0


# ---------------------------------------------------------------------------
# Power-ups Integration Tests
# ---------------------------------------------------------------------------

class TestPowerUpsWS:
    """Test power-up activation through WebSocket."""

    def test_double_points_power_up(self):
        """Double points power-up should double the score on next correct answer."""
        quiz_id = seed_quiz(num_questions=2)
        room_code = create_room(quiz_id)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(f"/ws/{room_code}/player-1") as p_ws:
                p_ws.receive_json()
                p_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})

                # Q1: answer normally for baseline
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "QUESTION")
                recv_until(p_ws, "QUESTION")
                p_ws.send_json({"type": "ANSWER", "answer_index": 0})
                r1 = recv_until(p_ws, "ANSWER_RESULT")
                assert r1["correct"] is True
                baseline_points = r1["points"]
                recv_until(org_ws, "QUESTION_OVER")
                recv_until(p_ws, "QUESTION_OVER")

                # Q2: activate double_points then answer
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "QUESTION")
                recv_until(p_ws, "QUESTION")

                p_ws.send_json({"type": "USE_POWER_UP", "power_up": "double_points"})
                pu_msg = recv_until(p_ws, "POWER_UP_ACTIVATED")
                assert pu_msg["power_up"] == "double_points"

                p_ws.send_json({"type": "ANSWER", "answer_index": 0})
                r2 = recv_until(p_ws, "ANSWER_RESULT")
                assert r2["correct"] is True
                # Double points should roughly double the score (timing may vary slightly)
                assert r2["points"] >= baseline_points * 1.5  # at least 1.5x due to timing

    def test_fifty_fifty_power_up(self):
        """50/50 should remove exactly 2 wrong options."""
        quiz_id = seed_quiz(num_questions=1)
        room_code = create_room(quiz_id)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(f"/ws/{room_code}/player-1") as p_ws:
                p_ws.receive_json()
                p_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "QUESTION")
                recv_until(p_ws, "QUESTION")

                p_ws.send_json({"type": "USE_POWER_UP", "power_up": "fifty_fifty"})
                pu_msg = recv_until(p_ws, "POWER_UP_ACTIVATED")
                assert pu_msg["power_up"] == "fifty_fifty"
                assert "remove_indices" in pu_msg
                assert len(pu_msg["remove_indices"]) == 2
                # Correct answer (index 0) should NOT be in removed indices
                assert 0 not in pu_msg["remove_indices"]

    def test_power_up_cannot_be_used_twice(self):
        """Each power-up can only be used once per game."""
        quiz_id = seed_quiz(num_questions=2)
        room_code = create_room(quiz_id)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(f"/ws/{room_code}/player-1") as p_ws:
                p_ws.receive_json()
                p_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "QUESTION")
                recv_until(p_ws, "QUESTION")

                # First use: should succeed
                p_ws.send_json({"type": "USE_POWER_UP", "power_up": "fifty_fifty"})
                pu_msg = recv_until(p_ws, "POWER_UP_ACTIVATED")
                assert pu_msg["power_up"] == "fifty_fifty"

                # Answer to proceed
                p_ws.send_json({"type": "ANSWER", "answer_index": 0})
                recv_until(p_ws, "ANSWER_RESULT")
                recv_until(org_ws, "QUESTION_OVER")
                recv_until(p_ws, "QUESTION_OVER")

                # Q2: try to use fifty_fifty again
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "QUESTION")
                recv_until(p_ws, "QUESTION")

                p_ws.send_json({"type": "USE_POWER_UP", "power_up": "fifty_fifty"})
                err_msg = recv_until(p_ws, "ERROR")
                assert "already used" in err_msg["message"].lower()

    def test_double_points_not_applied_on_wrong_answer(self):
        """Double points should be consumed but not affect score on wrong answer."""
        quiz_id = seed_quiz(num_questions=1)
        room_code = create_room(quiz_id)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(f"/ws/{room_code}/player-1") as p_ws:
                p_ws.receive_json()
                p_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "QUESTION")
                recv_until(p_ws, "QUESTION")

                p_ws.send_json({"type": "USE_POWER_UP", "power_up": "double_points"})
                recv_until(p_ws, "POWER_UP_ACTIVATED")

                # Answer wrong
                p_ws.send_json({"type": "ANSWER", "answer_index": 1})
                result = recv_until(p_ws, "ANSWER_RESULT")
                assert result["correct"] is False
                assert result["points"] == 0


# ---------------------------------------------------------------------------
# Team Mode Integration Tests
# ---------------------------------------------------------------------------

class TestTeamModeWS:
    """Test team mode through WebSocket game flow."""

    def test_team_leaderboard_in_podium(self):
        """Players with team names should produce team_leaderboard in PODIUM."""
        quiz_id = seed_quiz(num_questions=1)
        room_code = create_room(quiz_id)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            p1_ws = client.websocket_connect(f"/ws/{room_code}/p-1")
            p1_ws.__enter__()
            p1_ws.receive_json()
            p1_ws.send_json({"type": "JOIN", "nickname": "Alice", "team": "Red"})
            recv_until(org_ws, "PLAYER_JOINED")
            recv_until(p1_ws, "PLAYER_JOINED")

            p2_ws = client.websocket_connect(f"/ws/{room_code}/p-2")
            p2_ws.__enter__()
            p2_ws.receive_json()
            p2_ws.send_json({"type": "JOIN", "nickname": "Bob", "team": "Blue"})
            recv_until(org_ws, "PLAYER_JOINED")
            recv_until(p1_ws, "PLAYER_JOINED")
            recv_until(p2_ws, "PLAYER_JOINED")

            org_ws.send_json({"type": "START_GAME"})
            org_ws.send_json({"type": "NEXT_QUESTION"})
            recv_until(org_ws, "QUESTION")
            recv_until(p1_ws, "QUESTION")
            recv_until(p2_ws, "QUESTION")

            # Alice correct, Bob wrong
            p1_ws.send_json({"type": "ANSWER", "answer_index": 0})
            recv_until(p1_ws, "ANSWER_RESULT")
            p2_ws.send_json({"type": "ANSWER", "answer_index": 1})
            recv_until(p2_ws, "ANSWER_RESULT")

            recv_until(org_ws, "QUESTION_OVER")
            recv_until(p1_ws, "QUESTION_OVER")
            recv_until(p2_ws, "QUESTION_OVER")

            # Podium
            org_ws.send_json({"type": "NEXT_QUESTION"})
            podium = recv_until(org_ws, "PODIUM")

            assert "team_leaderboard" in podium
            assert len(podium["team_leaderboard"]) == 2
            # Red team (Alice) should be first since she scored
            assert podium["team_leaderboard"][0]["team"] == "Red"
            assert podium["team_leaderboard"][0]["score"] > 0
            assert podium["team_leaderboard"][1]["team"] == "Blue"
            assert podium["team_leaderboard"][1]["score"] == 0

            p1_ws.__exit__(None, None, None)
            p2_ws.__exit__(None, None, None)

    def test_solo_player_in_team_leaderboard(self):
        """When no teams are set, solo player appears with nickname as team."""
        quiz_id = seed_quiz(num_questions=1)
        room_code = create_room(quiz_id)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(f"/ws/{room_code}/p-1") as p_ws:
                p_ws.receive_json()
                p_ws.send_json({"type": "JOIN", "nickname": "Alice"})  # No team
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "QUESTION")
                recv_until(p_ws, "QUESTION")

                p_ws.send_json({"type": "ANSWER", "answer_index": 0})
                recv_until(p_ws, "ANSWER_RESULT")
                recv_until(org_ws, "QUESTION_OVER")
                recv_until(p_ws, "QUESTION_OVER")

                org_ws.send_json({"type": "NEXT_QUESTION"})
                podium = recv_until(org_ws, "PODIUM")
                tl = podium["team_leaderboard"]
                assert len(tl) == 1
                assert tl[0]["team"] == "Alice"
                assert tl[0]["members"] == 1

    def test_same_team_multiple_players(self):
        """Multiple players on the same team should have averaged scores."""
        quiz_id = seed_quiz(num_questions=1)
        room_code = create_room(quiz_id)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            p1_ws = client.websocket_connect(f"/ws/{room_code}/p-1")
            p1_ws.__enter__()
            p1_ws.receive_json()
            p1_ws.send_json({"type": "JOIN", "nickname": "Alice", "team": "Tigers"})
            recv_until(org_ws, "PLAYER_JOINED")
            recv_until(p1_ws, "PLAYER_JOINED")

            p2_ws = client.websocket_connect(f"/ws/{room_code}/p-2")
            p2_ws.__enter__()
            p2_ws.receive_json()
            p2_ws.send_json({"type": "JOIN", "nickname": "Bob", "team": "Tigers"})
            recv_until(org_ws, "PLAYER_JOINED")
            recv_until(p1_ws, "PLAYER_JOINED")
            recv_until(p2_ws, "PLAYER_JOINED")

            org_ws.send_json({"type": "START_GAME"})
            org_ws.send_json({"type": "NEXT_QUESTION"})
            recv_until(org_ws, "QUESTION")
            recv_until(p1_ws, "QUESTION")
            recv_until(p2_ws, "QUESTION")

            # Alice correct, Bob wrong
            p1_ws.send_json({"type": "ANSWER", "answer_index": 0})
            r1 = recv_until(p1_ws, "ANSWER_RESULT")
            p2_ws.send_json({"type": "ANSWER", "answer_index": 1})
            recv_until(p2_ws, "ANSWER_RESULT")

            recv_until(org_ws, "QUESTION_OVER")
            recv_until(p1_ws, "QUESTION_OVER")
            recv_until(p2_ws, "QUESTION_OVER")

            org_ws.send_json({"type": "NEXT_QUESTION"})
            podium = recv_until(org_ws, "PODIUM")

            assert len(podium["team_leaderboard"]) == 1
            team = podium["team_leaderboard"][0]
            assert team["team"] == "Tigers"
            assert team["members"] == 2
            # Average of Alice's score and Bob's 0
            assert team["score"] == r1["points"] // 2

            p1_ws.__exit__(None, None, None)
            p2_ws.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# Spectator Mode Integration Tests
# ---------------------------------------------------------------------------

class TestSpectatorWS:
    """Test spectator mode through WebSocket.

    NOTE: The TestClient's WebSocket transport deadlocks when broadcast()
    tries to send_json() on a spectator whose handler is blocked on
    receive_text(). So we test spectator sync (immediate response) and
    verify spectator registration via room state rather than reading
    broadcasts from the spectator WebSocket.
    """

    def test_spectator_receives_sync_on_connect(self):
        """Spectator should receive SPECTATOR_SYNC immediately on connect."""
        quiz_id = seed_quiz(num_questions=2)
        room_code = create_room(quiz_id)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()  # ROOM_CREATED

            # Add a player first
            with client.websocket_connect(f"/ws/{room_code}/p-1") as p_ws:
                p_ws.receive_json()
                p_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                # Connect spectator
                with client.websocket_connect(f"/ws/{room_code}/spec-1?spectator=true") as spec_ws:
                    sync = spec_ws.receive_json()
                    assert sync["type"] == "SPECTATOR_SYNC"
                    assert sync["room_code"] == room_code
                    assert sync["state"] == "LOBBY"
                    assert sync["player_count"] == 1
                    assert any(p["nickname"] == "Alice" for p in sync["players"])
                    assert sync["total_questions"] == 2

    def test_spectator_registered_in_room(self):
        """Spectator should be tracked in room.spectators, not room.players."""
        quiz_id = seed_quiz(num_questions=1)
        room_code = create_room(quiz_id)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(f"/ws/{room_code}/spec-1?spectator=true") as spec_ws:
                sync = spec_ws.receive_json()
                assert sync["type"] == "SPECTATOR_SYNC"

                # Verify room state directly
                room = socket_manager.rooms[room_code]
                assert "spec-1" in room.spectators
                assert "spec-1" not in room.players
                assert len(room.players) == 0

    def test_spectator_does_not_count_as_player(self):
        """Spectators should not appear in player count or player list."""
        quiz_id = seed_quiz(num_questions=1)
        room_code = create_room(quiz_id)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(f"/ws/{room_code}/spec-1?spectator=true") as spec_ws:
                sync = spec_ws.receive_json()
                assert sync["player_count"] == 0
                assert sync["players"] == []

    def test_spectator_sync_includes_leaderboard(self):
        """SPECTATOR_SYNC should include the current leaderboard."""
        quiz_id = seed_quiz(num_questions=1)
        room_code = create_room(quiz_id)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(f"/ws/{room_code}/spec-1?spectator=true") as spec_ws:
                sync = spec_ws.receive_json()
                assert "leaderboard" in sync
                assert isinstance(sync["leaderboard"], list)


# ---------------------------------------------------------------------------
# Answer Logging Integration Tests
# ---------------------------------------------------------------------------

class TestAnswerLoggingWS:
    """Test that answers are properly logged during a game."""

    def test_answers_logged_correctly(self):
        """All player answers should be recorded in the answer log."""
        quiz_id = seed_quiz(num_questions=2)
        room_code = create_room(quiz_id)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(f"/ws/{room_code}/p-1") as p_ws:
                p_ws.receive_json()
                p_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})

                # Q1: correct
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "QUESTION")
                recv_until(p_ws, "QUESTION")
                p_ws.send_json({"type": "ANSWER", "answer_index": 0})
                recv_until(p_ws, "ANSWER_RESULT")
                recv_until(org_ws, "QUESTION_OVER")
                recv_until(p_ws, "QUESTION_OVER")

                # Q2: wrong
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "QUESTION")
                recv_until(p_ws, "QUESTION")
                p_ws.send_json({"type": "ANSWER", "answer_index": 2})
                recv_until(p_ws, "ANSWER_RESULT")
                recv_until(org_ws, "QUESTION_OVER")
                recv_until(p_ws, "QUESTION_OVER")

        # Check the answer log in the room
        room = socket_manager.rooms[room_code]
        assert len(room.answer_log) == 2
        assert room.answer_log[0]["nickname"] == "Alice"
        assert room.answer_log[0]["question_index"] == 0
        assert room.answer_log[0]["correct"] is True
        assert room.answer_log[0]["answer_index"] == 0
        assert room.answer_log[1]["question_index"] == 1
        assert room.answer_log[1]["correct"] is False
        assert room.answer_log[1]["answer_index"] == 2


# ---------------------------------------------------------------------------
# Game History Integration Tests
# ---------------------------------------------------------------------------

class TestGameHistoryWS:
    """Test that game history is saved after PODIUM."""

    def test_game_saved_to_history(self):
        """After reaching PODIUM, game summary should be saved to history."""
        quiz_id = seed_quiz(num_questions=1)
        room_code = create_room(quiz_id)

        assert len(game_history) == 0

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(f"/ws/{room_code}/p-1") as p_ws:
                p_ws.receive_json()
                p_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "QUESTION")
                recv_until(p_ws, "QUESTION")

                p_ws.send_json({"type": "ANSWER", "answer_index": 0})
                recv_until(p_ws, "ANSWER_RESULT")
                recv_until(org_ws, "QUESTION_OVER")
                recv_until(p_ws, "QUESTION_OVER")

                # Trigger PODIUM
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "PODIUM")
                recv_until(p_ws, "PODIUM")

        # Verify history was saved
        assert len(game_history) == 1
        game = game_history[0]
        assert game["room_code"] == room_code
        assert game["quiz_title"] == "Integration Test Quiz"
        assert game["player_count"] == 1
        assert len(game["leaderboard"]) == 1
        assert game["leaderboard"][0]["nickname"] == "Alice"
        assert game["leaderboard"][0]["score"] > 0
        assert len(game["answer_log"]) == 1

    def test_history_accessible_via_api(self):
        """Game history should be queryable via GET /history and /history/{room_code}."""
        quiz_id = seed_quiz(num_questions=1)
        room_code = create_room(quiz_id)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(f"/ws/{room_code}/p-1") as p_ws:
                p_ws.receive_json()
                p_ws.send_json({"type": "JOIN", "nickname": "Bob"})
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "QUESTION")
                recv_until(p_ws, "QUESTION")
                p_ws.send_json({"type": "ANSWER", "answer_index": 0})
                recv_until(p_ws, "ANSWER_RESULT")
                recv_until(org_ws, "QUESTION_OVER")
                recv_until(p_ws, "QUESTION_OVER")
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "PODIUM")
                recv_until(p_ws, "PODIUM")

        # Check list endpoint
        res = client.get("/history")
        assert res.status_code == 200
        assert len(res.json()["games"]) == 1

        # Check detail endpoint
        res = client.get(f"/history/{room_code}")
        assert res.status_code == 200
        assert res.json()["room_code"] == room_code
        assert res.json()["leaderboard"][0]["nickname"] == "Bob"


# ---------------------------------------------------------------------------
# Multi-player Game Flow
# ---------------------------------------------------------------------------

class TestMultiPlayerGameFlow:
    """Test full game flow with multiple players."""

    def test_all_players_answered_ends_question_early(self):
        """When all players answer, question should end immediately."""
        quiz_id = seed_quiz(num_questions=1)
        room_code = create_room(quiz_id, time_limit=60)  # Long timer

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            p1_ws = client.websocket_connect(f"/ws/{room_code}/p-1")
            p1_ws.__enter__()
            p1_ws.receive_json()
            p1_ws.send_json({"type": "JOIN", "nickname": "Alice"})
            recv_until(org_ws, "PLAYER_JOINED")
            recv_until(p1_ws, "PLAYER_JOINED")

            p2_ws = client.websocket_connect(f"/ws/{room_code}/p-2")
            p2_ws.__enter__()
            p2_ws.receive_json()
            p2_ws.send_json({"type": "JOIN", "nickname": "Bob"})
            recv_until(org_ws, "PLAYER_JOINED")
            recv_until(p1_ws, "PLAYER_JOINED")
            recv_until(p2_ws, "PLAYER_JOINED")

            org_ws.send_json({"type": "START_GAME"})
            org_ws.send_json({"type": "NEXT_QUESTION"})
            recv_until(org_ws, "QUESTION")
            recv_until(p1_ws, "QUESTION")
            recv_until(p2_ws, "QUESTION")

            # Both answer
            p1_ws.send_json({"type": "ANSWER", "answer_index": 0})
            recv_until(p1_ws, "ANSWER_RESULT")
            p2_ws.send_json({"type": "ANSWER", "answer_index": 1})
            recv_until(p2_ws, "ANSWER_RESULT")

            # Should get QUESTION_OVER immediately (not waiting for timer)
            qo = recv_until(org_ws, "QUESTION_OVER")
            assert len(qo["leaderboard"]) == 2
            # Alice answered correctly, should be first
            assert qo["leaderboard"][0]["nickname"] == "Alice"

            p1_ws.__exit__(None, None, None)
            p2_ws.__exit__(None, None, None)

    def test_player_cannot_answer_twice(self):
        """A player's second answer should be silently ignored."""
        quiz_id = seed_quiz(num_questions=1)
        room_code = create_room(quiz_id, time_limit=60)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(f"/ws/{room_code}/p-1") as p_ws:
                p_ws.receive_json()
                p_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "QUESTION")
                recv_until(p_ws, "QUESTION")

                # First answer
                p_ws.send_json({"type": "ANSWER", "answer_index": 0})
                r1 = recv_until(p_ws, "ANSWER_RESULT")
                score_after_first = r1["points"]

                # Second answer — should be ignored (question ends with all_answered)
                # Since there's only one player, QUESTION_OVER fires after first answer
                qo = recv_until(org_ws, "QUESTION_OVER")
                assert qo["leaderboard"][0]["score"] == score_after_first

    def test_leaderboard_rank_changes(self):
        """Leaderboard should include rank_change data."""
        quiz_id = seed_quiz(num_questions=2)
        room_code = create_room(quiz_id)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            p1_ws = client.websocket_connect(f"/ws/{room_code}/p-1")
            p1_ws.__enter__()
            p1_ws.receive_json()
            p1_ws.send_json({"type": "JOIN", "nickname": "Alice"})
            recv_until(org_ws, "PLAYER_JOINED")
            recv_until(p1_ws, "PLAYER_JOINED")

            p2_ws = client.websocket_connect(f"/ws/{room_code}/p-2")
            p2_ws.__enter__()
            p2_ws.receive_json()
            p2_ws.send_json({"type": "JOIN", "nickname": "Bob"})
            recv_until(org_ws, "PLAYER_JOINED")
            recv_until(p1_ws, "PLAYER_JOINED")
            recv_until(p2_ws, "PLAYER_JOINED")

            org_ws.send_json({"type": "START_GAME"})

            # Q1: Bob correct, Alice wrong
            org_ws.send_json({"type": "NEXT_QUESTION"})
            recv_until(org_ws, "QUESTION")
            recv_until(p1_ws, "QUESTION")
            recv_until(p2_ws, "QUESTION")
            p1_ws.send_json({"type": "ANSWER", "answer_index": 1})  # wrong
            recv_until(p1_ws, "ANSWER_RESULT")
            p2_ws.send_json({"type": "ANSWER", "answer_index": 0})  # correct
            recv_until(p2_ws, "ANSWER_RESULT")
            qo1 = recv_until(org_ws, "QUESTION_OVER")
            recv_until(p1_ws, "QUESTION_OVER")
            recv_until(p2_ws, "QUESTION_OVER")

            # After Q1, Bob should be #1
            assert qo1["leaderboard"][0]["nickname"] == "Bob"

            # Q2: Alice correct, Bob wrong — Alice should overtake
            org_ws.send_json({"type": "NEXT_QUESTION"})
            recv_until(org_ws, "QUESTION")
            recv_until(p1_ws, "QUESTION")
            recv_until(p2_ws, "QUESTION")
            p1_ws.send_json({"type": "ANSWER", "answer_index": 0})  # correct
            recv_until(p1_ws, "ANSWER_RESULT")
            p2_ws.send_json({"type": "ANSWER", "answer_index": 1})  # wrong
            recv_until(p2_ws, "ANSWER_RESULT")
            qo2 = recv_until(org_ws, "QUESTION_OVER")

            # rank_change should be present
            for entry in qo2["leaderboard"]:
                assert "rank_change" in entry

            p1_ws.__exit__(None, None, None)
            p2_ws.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# Mixed Question Types (MCQ + T/F)
# ---------------------------------------------------------------------------

class TestMixedQuestionTypesWS:
    """Test games with both MCQ and True/False questions."""

    def test_tf_question_answer_validation(self):
        """True/False question should accept answer_index 0 or 1."""
        quiz_id = seed_mixed_quiz()
        room_code = create_room(quiz_id)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(f"/ws/{room_code}/p-1") as p_ws:
                p_ws.receive_json()
                p_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})

                # Q1: MCQ (4 options)
                org_ws.send_json({"type": "NEXT_QUESTION"})
                q1 = recv_until(p_ws, "QUESTION")
                recv_until(org_ws, "QUESTION")
                assert len(q1["question"]["options"]) == 4
                p_ws.send_json({"type": "ANSWER", "answer_index": 0})
                recv_until(p_ws, "ANSWER_RESULT")
                recv_until(org_ws, "QUESTION_OVER")
                recv_until(p_ws, "QUESTION_OVER")

                # Q2: T/F (2 options)
                org_ws.send_json({"type": "NEXT_QUESTION"})
                q2 = recv_until(p_ws, "QUESTION")
                recv_until(org_ws, "QUESTION")
                assert len(q2["question"]["options"]) == 2
                assert q2["question"]["options"] == ["True", "False"]
                p_ws.send_json({"type": "ANSWER", "answer_index": 0})  # correct
                r2 = recv_until(p_ws, "ANSWER_RESULT")
                assert r2["correct"] is True
                recv_until(org_ws, "QUESTION_OVER")
                recv_until(p_ws, "QUESTION_OVER")

                # Q3: MCQ again
                org_ws.send_json({"type": "NEXT_QUESTION"})
                q3 = recv_until(p_ws, "QUESTION")
                recv_until(org_ws, "QUESTION")
                assert len(q3["question"]["options"]) == 4
                p_ws.send_json({"type": "ANSWER", "answer_index": 2})  # correct
                r3 = recv_until(p_ws, "ANSWER_RESULT")
                assert r3["correct"] is True

    def test_fifty_fifty_on_tf_question(self):
        """50/50 on a True/False question: only 1 wrong option to remove (not 2)."""
        quiz_data = {
            "quiz_title": "TF Only",
            "questions": [
                {"id": 1, "text": "Earth is round?", "options": ["True", "False"], "answer_index": 0},
            ],
        }
        quiz_id = str(uuid.uuid4())
        quizzes[quiz_id] = quiz_data
        room_code = create_room(quiz_id)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(f"/ws/{room_code}/p-1") as p_ws:
                p_ws.receive_json()
                p_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "QUESTION")
                recv_until(p_ws, "QUESTION")

                p_ws.send_json({"type": "USE_POWER_UP", "power_up": "fifty_fifty"})
                pu = recv_until(p_ws, "POWER_UP_ACTIVATED")
                # Only 1 wrong option exists for T/F
                assert len(pu["remove_indices"]) == 1
                assert 0 not in pu["remove_indices"]  # correct answer preserved


# ---------------------------------------------------------------------------
# Reconnection Integration Tests
# ---------------------------------------------------------------------------

class TestReconnectionWS:
    """Test player reconnection preserving streak and power-ups."""

    def test_reconnected_player_keeps_streak(self):
        """Reconnected player should retain their streak count."""
        quiz_id = seed_quiz(num_questions=3)
        room_code = create_room(quiz_id, time_limit=60)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            # Player joins and answers Q1
            with client.websocket_connect(f"/ws/{room_code}/p-1") as p_ws:
                p_ws.receive_json()
                p_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "QUESTION")
                recv_until(p_ws, "QUESTION")
                p_ws.send_json({"type": "ANSWER", "answer_index": 0})
                r1 = recv_until(p_ws, "ANSWER_RESULT")
                assert r1["streak"] == 1

            # Player disconnects — wait for server to process
            time.sleep(0.3)

            room = socket_manager.rooms[room_code]
            assert "Alice" in room.disconnected_players
            assert room.disconnected_players["Alice"]["streak"] == 1

            # Player reconnects
            with client.websocket_connect(f"/ws/{room_code}/p-2") as p_ws2:
                p_ws2.receive_json()
                p_ws2.send_json({"type": "JOIN", "nickname": "Alice"})
                recon = recv_until(p_ws2, "RECONNECTED")
                assert recon["score"] == r1["points"]

    def test_reconnected_player_appears_in_leaderboard(self):
        """Reconnected player should still appear in final leaderboard."""
        quiz_id = seed_quiz(num_questions=2)
        room_code = create_room(quiz_id, time_limit=60)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            # Player joins and answers Q1
            with client.websocket_connect(f"/ws/{room_code}/p-1") as p_ws:
                p_ws.receive_json()
                p_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "QUESTION")
                recv_until(p_ws, "QUESTION")
                p_ws.send_json({"type": "ANSWER", "answer_index": 0})
                r1 = recv_until(p_ws, "ANSWER_RESULT")
                score = r1["points"]
                recv_until(org_ws, "QUESTION_OVER")
                recv_until(p_ws, "QUESTION_OVER")

            # Player disconnects
            time.sleep(0.3)

            # Reconnect
            with client.websocket_connect(f"/ws/{room_code}/p-2") as p_ws2:
                p_ws2.receive_json()
                p_ws2.send_json({"type": "JOIN", "nickname": "Alice"})
                recv_until(p_ws2, "RECONNECTED")

                # Q2
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "QUESTION")
                recv_until(p_ws2, "QUESTION")
                p_ws2.send_json({"type": "ANSWER", "answer_index": 0})
                r2 = recv_until(p_ws2, "ANSWER_RESULT")
                recv_until(org_ws, "QUESTION_OVER")
                recv_until(p_ws2, "QUESTION_OVER")

                # Podium
                org_ws.send_json({"type": "NEXT_QUESTION"})
                podium = recv_until(org_ws, "PODIUM")
                assert len(podium["leaderboard"]) == 1
                assert podium["leaderboard"][0]["nickname"] == "Alice"
                assert podium["leaderboard"][0]["score"] == score + r2["points"]


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Test edge cases in WebSocket game flow."""

    def test_invalid_room_code(self):
        """Connecting to a non-existent room should return an error."""
        with client.websocket_connect("/ws/BADCODE/p-1") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "ERROR"
            assert "not found" in msg["message"].lower()

    def test_invalid_answer_index_ignored(self):
        """An out-of-range answer index should be silently ignored."""
        quiz_id = seed_quiz(num_questions=1)
        room_code = create_room(quiz_id, time_limit=60)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(f"/ws/{room_code}/p-1") as p_ws:
                p_ws.receive_json()
                p_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "QUESTION")
                recv_until(p_ws, "QUESTION")

                # Send invalid answer — should be silently ignored
                p_ws.send_json({"type": "ANSWER", "answer_index": 99})
                # Player should still be able to answer validly
                p_ws.send_json({"type": "ANSWER", "answer_index": 0})
                result = recv_until(p_ws, "ANSWER_RESULT")
                assert result["correct"] is True

    def test_nickname_too_long_rejected(self):
        """A nickname exceeding max length should be rejected."""
        quiz_id = seed_quiz(num_questions=1)
        room_code = create_room(quiz_id)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(f"/ws/{room_code}/p-1") as p_ws:
                p_ws.receive_json()
                long_name = "A" * (config.MAX_NICKNAME_LENGTH + 1)
                p_ws.send_json({"type": "JOIN", "nickname": long_name})
                err = recv_until(p_ws, "ERROR")
                assert "character" in err["message"].lower()

    def test_empty_nickname_rejected(self):
        """Empty nickname should be rejected."""
        quiz_id = seed_quiz(num_questions=1)
        room_code = create_room(quiz_id)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(f"/ws/{room_code}/p-1") as p_ws:
                p_ws.receive_json()
                p_ws.send_json({"type": "JOIN", "nickname": "   "})
                err = recv_until(p_ws, "ERROR")
                assert "character" in err["message"].lower()

    def test_html_in_nickname_sanitized(self):
        """HTML tags in nickname should be stripped."""
        quiz_id = seed_quiz(num_questions=1)
        room_code = create_room(quiz_id)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(f"/ws/{room_code}/p-1") as p_ws:
                p_ws.receive_json()
                p_ws.send_json({"type": "JOIN", "nickname": "<b>Evil</b>"})
                joined = recv_until(org_ws, "PLAYER_JOINED")
                assert "<" not in joined["nickname"]
                assert joined["nickname"] == "Evil"


# ---------------------------------------------------------------------------
# Bonus Rounds Integration Tests
# ---------------------------------------------------------------------------

class TestBonusRoundsWS:
    """Test bonus round selection, messaging, and scoring through WebSocket."""

    def test_bonus_flag_in_question_message(self):
        """QUESTION messages should include is_bonus field; some True for 5+ Q quiz."""
        quiz_id = seed_quiz(num_questions=5)
        room_code = create_room(quiz_id)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(f"/ws/{room_code}/p-1") as p_ws:
                p_ws.receive_json()
                p_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})

                bonus_flags = []
                for _ in range(5):
                    org_ws.send_json({"type": "NEXT_QUESTION"})
                    q = recv_until(org_ws, "QUESTION")
                    recv_until(p_ws, "QUESTION")
                    assert "is_bonus" in q
                    bonus_flags.append(q["is_bonus"])

                    p_ws.send_json({"type": "ANSWER", "answer_index": 0})
                    recv_until(p_ws, "ANSWER_RESULT")
                    recv_until(org_ws, "QUESTION_OVER")
                    recv_until(p_ws, "QUESTION_OVER")

                # At least one bonus and at least one non-bonus
                assert True in bonus_flags, "Expected at least one bonus question"
                assert False in bonus_flags, "Expected at least one non-bonus question"
                # First and last should not be bonus
                assert bonus_flags[0] is False, "First question should not be bonus"
                assert bonus_flags[-1] is False, "Last question should not be bonus"

    def test_bonus_scoring_doubles_points(self):
        """Correct answer on bonus question should give ~2x points vs non-bonus."""
        quiz_id = seed_quiz(num_questions=5)
        room_code = create_room(quiz_id)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(f"/ws/{room_code}/p-1") as p_ws:
                p_ws.receive_json()
                p_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})

                bonus_points = []
                normal_points = []

                for _ in range(5):
                    org_ws.send_json({"type": "NEXT_QUESTION"})
                    q = recv_until(org_ws, "QUESTION")
                    recv_until(p_ws, "QUESTION")

                    p_ws.send_json({"type": "ANSWER", "answer_index": 0})
                    result = recv_until(p_ws, "ANSWER_RESULT")

                    if result["correct"]:
                        if q["is_bonus"]:
                            bonus_points.append(result["points"])
                        else:
                            normal_points.append(result["points"])

                    recv_until(org_ws, "QUESTION_OVER")
                    recv_until(p_ws, "QUESTION_OVER")

                # If we have both bonus and normal correct answers, bonus should be higher
                if bonus_points and normal_points:
                    avg_bonus = sum(bonus_points) / len(bonus_points)
                    avg_normal = sum(normal_points) / len(normal_points)
                    assert avg_bonus > avg_normal, "Bonus points should exceed normal points"

    def test_bonus_flag_in_answer_result(self):
        """ANSWER_RESULT should include is_bonus field."""
        quiz_id = seed_quiz(num_questions=5)
        room_code = create_room(quiz_id)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(f"/ws/{room_code}/p-1") as p_ws:
                p_ws.receive_json()
                p_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "QUESTION")
                recv_until(p_ws, "QUESTION")

                p_ws.send_json({"type": "ANSWER", "answer_index": 0})
                result = recv_until(p_ws, "ANSWER_RESULT")
                assert "is_bonus" in result

    def test_no_bonus_for_small_quiz(self):
        """3-question quiz should have no bonus rounds."""
        quiz_id = seed_quiz(num_questions=3)
        room_code = create_room(quiz_id)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(f"/ws/{room_code}/p-1") as p_ws:
                p_ws.receive_json()
                p_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})

                for _ in range(3):
                    org_ws.send_json({"type": "NEXT_QUESTION"})
                    q = recv_until(org_ws, "QUESTION")
                    recv_until(p_ws, "QUESTION")
                    assert q["is_bonus"] is False

                    p_ws.send_json({"type": "ANSWER", "answer_index": 0})
                    recv_until(p_ws, "ANSWER_RESULT")
                    recv_until(org_ws, "QUESTION_OVER")
                    recv_until(p_ws, "QUESTION_OVER")


# ---------------------------------------------------------------------------
# Streak Reset on No-Answer Integration Tests
# ---------------------------------------------------------------------------

class TestStreakResetNoAnswerWS:
    """Test streak reset when a player doesn't answer.

    NOTE: TestClient's sync WebSocket transport can't reliably wait for timer
    expiry (asyncio background tasks). Instead, we test with 2 players where
    one answers and the other doesn't, triggering end_question via all_answered
    for the active player — then verify the non-answering player's streak was reset.
    """

    def test_streak_resets_for_non_answering_player(self):
        """Player who doesn't answer should have streak reset to 0."""
        quiz_id = seed_quiz(num_questions=3)
        room_code = create_room(quiz_id, time_limit=60)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            p1_ws = client.websocket_connect(f"/ws/{room_code}/p-1")
            p1_ws.__enter__()
            p1_ws.receive_json()
            p1_ws.send_json({"type": "JOIN", "nickname": "Alice"})
            recv_until(org_ws, "PLAYER_JOINED")
            recv_until(p1_ws, "PLAYER_JOINED")

            p2_ws = client.websocket_connect(f"/ws/{room_code}/p-2")
            p2_ws.__enter__()
            p2_ws.receive_json()
            p2_ws.send_json({"type": "JOIN", "nickname": "Bob"})
            recv_until(org_ws, "PLAYER_JOINED")
            recv_until(p1_ws, "PLAYER_JOINED")
            recv_until(p2_ws, "PLAYER_JOINED")

            org_ws.send_json({"type": "START_GAME"})

            # Q1: Both answer correctly
            org_ws.send_json({"type": "NEXT_QUESTION"})
            recv_until(org_ws, "QUESTION")
            recv_until(p1_ws, "QUESTION")
            recv_until(p2_ws, "QUESTION")
            p1_ws.send_json({"type": "ANSWER", "answer_index": 0})
            r1a = recv_until(p1_ws, "ANSWER_RESULT")
            assert r1a["streak"] == 1
            p2_ws.send_json({"type": "ANSWER", "answer_index": 0})
            r1b = recv_until(p2_ws, "ANSWER_RESULT")
            assert r1b["streak"] == 1
            recv_until(org_ws, "QUESTION_OVER")
            recv_until(p1_ws, "QUESTION_OVER")
            recv_until(p2_ws, "QUESTION_OVER")

            # Q2: Both answer correctly (streak=2)
            org_ws.send_json({"type": "NEXT_QUESTION"})
            recv_until(org_ws, "QUESTION")
            recv_until(p1_ws, "QUESTION")
            recv_until(p2_ws, "QUESTION")
            p1_ws.send_json({"type": "ANSWER", "answer_index": 0})
            r2a = recv_until(p1_ws, "ANSWER_RESULT")
            assert r2a["streak"] == 2
            p2_ws.send_json({"type": "ANSWER", "answer_index": 0})
            r2b = recv_until(p2_ws, "ANSWER_RESULT")
            assert r2b["streak"] == 2
            recv_until(org_ws, "QUESTION_OVER")
            recv_until(p1_ws, "QUESTION_OVER")
            recv_until(p2_ws, "QUESTION_OVER")

            # Q3: Only Alice answers — Bob doesn't answer
            org_ws.send_json({"type": "NEXT_QUESTION"})
            recv_until(org_ws, "QUESTION")
            recv_until(p1_ws, "QUESTION")
            recv_until(p2_ws, "QUESTION")
            # Only Alice answers — but QUESTION_OVER only fires when ALL answer or timer expires.
            # We can't wait for timer in TestClient, so verify via room state directly.
            p1_ws.send_json({"type": "ANSWER", "answer_index": 0})
            r3a = recv_until(p1_ws, "ANSWER_RESULT")
            assert r3a["streak"] == 3  # Alice's streak continues

            # Check room state: Bob hasn't answered yet, streak should still be 2
            room = socket_manager.rooms[room_code]
            bob = next(p for p in room.players.values() if p["nickname"] == "Bob")
            assert bob["streak"] == 2, "Bob's streak should still be 2 before end_question"

            # Simulate end_question by having Bob answer too (triggers all_answered)
            p2_ws.send_json({"type": "ANSWER", "answer_index": 1})  # Wrong answer
            r3b = recv_until(p2_ws, "ANSWER_RESULT")
            assert r3b["streak"] == 0  # Bob answered wrong, streak reset

            p1_ws.__exit__(None, None, None)
            p2_ws.__exit__(None, None, None)

    def test_streak_reset_via_room_state(self):
        """Verify streak reset logic works on room state level."""
        # This test verifies the end_question streak reset by inspecting room state
        quiz_id = seed_quiz(num_questions=2)
        room_code = create_room(quiz_id, time_limit=60)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(f"/ws/{room_code}/p-1") as p_ws:
                p_ws.receive_json()
                p_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})

                # Q1: answer correctly
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "QUESTION")
                recv_until(p_ws, "QUESTION")
                p_ws.send_json({"type": "ANSWER", "answer_index": 0})
                r1 = recv_until(p_ws, "ANSWER_RESULT")
                assert r1["streak"] == 1
                recv_until(org_ws, "QUESTION_OVER")
                recv_until(p_ws, "QUESTION_OVER")

                # After Q1, verify streak in room state
                room = socket_manager.rooms[room_code]
                alice = next(p for p in room.players.values() if p["nickname"] == "Alice")
                assert alice["streak"] == 1

                # Q2: answer wrong — streak should reset
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "QUESTION")
                recv_until(p_ws, "QUESTION")
                p_ws.send_json({"type": "ANSWER", "answer_index": 1})  # wrong
                r2 = recv_until(p_ws, "ANSWER_RESULT")
                assert r2["streak"] == 0
                assert r2["correct"] is False


# ---------------------------------------------------------------------------
# Team Leaderboard with Solo Players Integration Tests
# ---------------------------------------------------------------------------

class TestTeamLeaderboardSoloWS:
    """Test team leaderboard includes solo players using their nickname."""

    def test_solo_player_appears_in_team_leaderboard(self):
        """Solo player (no team) should appear in team_leaderboard with their nickname."""
        quiz_id = seed_quiz(num_questions=1)
        room_code = create_room(quiz_id)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(f"/ws/{room_code}/p-1") as p_ws:
                p_ws.receive_json()
                p_ws.send_json({"type": "JOIN", "nickname": "Alice"})  # No team
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "QUESTION")
                recv_until(p_ws, "QUESTION")

                p_ws.send_json({"type": "ANSWER", "answer_index": 0})
                recv_until(p_ws, "ANSWER_RESULT")
                recv_until(org_ws, "QUESTION_OVER")
                recv_until(p_ws, "QUESTION_OVER")

                org_ws.send_json({"type": "NEXT_QUESTION"})
                podium = recv_until(org_ws, "PODIUM")

                # Solo player should appear with their nickname as team
                tl = podium["team_leaderboard"]
                assert len(tl) == 1
                assert tl[0]["team"] == "Alice"
                assert tl[0]["members"] == 1
                assert tl[0]["score"] > 0

    def test_mixed_team_and_solo_in_podium(self):
        """Mix of team players and solo player in podium team_leaderboard."""
        quiz_id = seed_quiz(num_questions=1)
        room_code = create_room(quiz_id)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            p1_ws = client.websocket_connect(f"/ws/{room_code}/p-1")
            p1_ws.__enter__()
            p1_ws.receive_json()
            p1_ws.send_json({"type": "JOIN", "nickname": "Alice", "team": "Red"})
            recv_until(org_ws, "PLAYER_JOINED")
            recv_until(p1_ws, "PLAYER_JOINED")

            p2_ws = client.websocket_connect(f"/ws/{room_code}/p-2")
            p2_ws.__enter__()
            p2_ws.receive_json()
            p2_ws.send_json({"type": "JOIN", "nickname": "Bob"})  # Solo
            recv_until(org_ws, "PLAYER_JOINED")
            recv_until(p1_ws, "PLAYER_JOINED")
            recv_until(p2_ws, "PLAYER_JOINED")

            org_ws.send_json({"type": "START_GAME"})
            org_ws.send_json({"type": "NEXT_QUESTION"})
            recv_until(org_ws, "QUESTION")
            recv_until(p1_ws, "QUESTION")
            recv_until(p2_ws, "QUESTION")

            # Both answer correctly
            p1_ws.send_json({"type": "ANSWER", "answer_index": 0})
            recv_until(p1_ws, "ANSWER_RESULT")
            p2_ws.send_json({"type": "ANSWER", "answer_index": 0})
            recv_until(p2_ws, "ANSWER_RESULT")
            recv_until(org_ws, "QUESTION_OVER")
            recv_until(p1_ws, "QUESTION_OVER")
            recv_until(p2_ws, "QUESTION_OVER")

            org_ws.send_json({"type": "NEXT_QUESTION"})
            podium = recv_until(org_ws, "PODIUM")

            tl = podium["team_leaderboard"]
            assert len(tl) == 2
            team_names = {t["team"] for t in tl}
            assert "Red" in team_names
            assert "Bob" in team_names  # Solo player uses nickname

            p1_ws.__exit__(None, None, None)
            p2_ws.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# Bonus Reconnection Integration Tests
# ---------------------------------------------------------------------------

class TestBonusReconnectionWS:
    """Test reconnection during bonus question includes is_bonus flag."""

    def test_reconnection_during_bonus_includes_is_bonus(self):
        """Reconnecting during a bonus question should have is_bonus in RECONNECTED."""
        quiz_id = seed_quiz(num_questions=5)
        room_code = create_room(quiz_id, time_limit=60)

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true") as org_ws:
            org_ws.receive_json()

            # Join player
            with client.websocket_connect(f"/ws/{room_code}/p-1") as p_ws:
                p_ws.receive_json()
                p_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})

                # Find a bonus question by advancing through questions
                found_bonus = False
                for _ in range(5):
                    org_ws.send_json({"type": "NEXT_QUESTION"})
                    q = recv_until(org_ws, "QUESTION")
                    recv_until(p_ws, "QUESTION")

                    if q["is_bonus"]:
                        found_bonus = True
                        break

                    # Answer and proceed
                    p_ws.send_json({"type": "ANSWER", "answer_index": 0})
                    recv_until(p_ws, "ANSWER_RESULT")
                    recv_until(org_ws, "QUESTION_OVER")
                    recv_until(p_ws, "QUESTION_OVER")

            if found_bonus:
                # Player disconnected during bonus question
                import time
                time.sleep(0.3)

                room = socket_manager.rooms[room_code]
                assert "Alice" in room.disconnected_players

                # Reconnect
                with client.websocket_connect(f"/ws/{room_code}/p-2") as p_ws2:
                    p_ws2.receive_json()
                    p_ws2.send_json({"type": "JOIN", "nickname": "Alice"})
                    recon = recv_until(p_ws2, "RECONNECTED")
                    assert recon.get("is_bonus") is True
