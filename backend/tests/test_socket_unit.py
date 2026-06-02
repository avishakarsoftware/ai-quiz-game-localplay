"""
Unit tests for socket_manager.py — Room class and SocketManager methods.
Uses mock WebSockets to test state guards, disconnect handling,
reconnection logic, spectator sync, and bonus round mechanics.
"""
import sys
import os
import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from socket_manager import Room, SocketManager
from housie_engine import default_housie_game, ticket_numbers
import config


# ---------------------------------------------------------------------------
# Mock WebSocket
# ---------------------------------------------------------------------------

class MockWebSocket:
    """Lightweight mock for fastapi.WebSocket."""
    def __init__(self):
        self.sent_messages: list[dict] = []
        self.closed = False
        self.close_code = None

    async def send_json(self, data: dict):
        self.sent_messages.append(data)

    async def close(self, code: int = 1000):
        self.closed = True
        self.close_code = code

    async def accept(self):
        pass

    @property
    def headers(self):
        return {"origin": ""}

    def last(self, msg_type: str) -> dict | None:
        """Return the last sent message of a given type."""
        for msg in reversed(self.sent_messages):
            if msg.get("type") == msg_type:
                return msg
        return None

    def all(self, msg_type: str) -> list[dict]:
        """Return all sent messages of a given type."""
        return [m for m in self.sent_messages if m.get("type") == msg_type]


class FailingWebSocket(MockWebSocket):
    async def send_json(self, data: dict):
        raise RuntimeError("socket is gone")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_quiz(num_questions=5):
    return {
        "quiz_title": "Unit Test Quiz",
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


def make_room(num_questions=5, time_limit=15, token="test-token"):
    room = Room("UNIT01", make_quiz(num_questions), time_limit, organizer_token=token)
    room.wallet_id = "test-wallet-id"  # Required for spark charging in START_GAME/RESET_ROOM
    return room


def add_player(room, client_id, nickname, score=0, team=None):
    """Add a player to the room with a mock WebSocket connection."""
    ws = MockWebSocket()
    room.connections[client_id] = ws
    room.players[client_id] = {
        "nickname": nickname,
        "score": score,
        "prev_rank": 0,
        "streak": 0,
        "avatar": "",
    }
    room.power_ups[nickname] = {"double_points": True, "fifty_fifty": True}
    if team:
        room.teams[nickname] = team
    return ws


def add_organizer(room, client_id="org-1"):
    ws = MockWebSocket()
    room.connections[client_id] = ws
    room.organizer = ws
    room.organizer_id = client_id
    return ws


def add_spectator(room, client_id="spec-1"):
    ws = MockWebSocket()
    room.spectators[client_id] = ws
    return ws


def make_housie_room():
    game = default_housie_game("Unit Housie")
    game["auto_pause_on_claim"] = True
    room = Room("HOU001", game, game_type="housie")
    room.wallet_id = "test-wallet-id"
    room.state = "BINGO_CALLING"
    return room


# ===========================================================================
# Room._remove_connection
# ===========================================================================

class TestRemoveConnectionLobby:
    """Removing a player in LOBBY should fully delete them and clean up teams/power_ups."""

    def test_player_removed_from_players_dict(self):
        room = make_room()
        add_player(room, "p1", "Alice")
        room.state = "LOBBY"
        room._remove_connection("p1")
        assert "p1" not in room.players

    def test_teams_cleaned_on_lobby_leave(self):
        room = make_room()
        add_player(room, "p1", "Alice", team="Red")
        room.state = "LOBBY"
        assert "Alice" in room.teams
        room._remove_connection("p1")
        assert "Alice" not in room.teams

    def test_power_ups_cleaned_on_lobby_leave(self):
        room = make_room()
        add_player(room, "p1", "Alice")
        room.state = "LOBBY"
        assert "Alice" in room.power_ups
        room._remove_connection("p1")
        assert "Alice" not in room.power_ups

    def test_player_event_set_to_left(self):
        room = make_room()
        add_player(room, "p1", "Alice")
        room.state = "LOBBY"
        room._remove_connection("p1")
        assert room._player_event == ("left", "Alice")


class TestRemoveConnectionDuringGame:
    """Removing a player during game should preserve data for reconnection."""

    def test_player_data_preserved_in_disconnected_players(self):
        room = make_room()
        add_player(room, "p1", "Alice", score=500)
        room.players["p1"]["streak"] = 3
        room.state = "QUESTION"
        room._remove_connection("p1")
        assert "Alice" in room.disconnected_players
        assert room.disconnected_players["Alice"]["score"] == 500
        assert room.disconnected_players["Alice"]["streak"] == 3

    def test_answered_client_id_saved_if_answered(self):
        room = make_room()
        add_player(room, "p1", "Alice")
        room.state = "QUESTION"
        room.answered_players.add("p1")
        room._remove_connection("p1")
        assert room.disconnected_players["Alice"]["_answered_client_id"] == "p1"

    def test_answered_client_id_none_if_not_answered(self):
        room = make_room()
        add_player(room, "p1", "Alice")
        room.state = "QUESTION"
        room._remove_connection("p1")
        assert room.disconnected_players["Alice"]["_answered_client_id"] is None

    def test_player_event_set_to_disconnected(self):
        room = make_room()
        add_player(room, "p1", "Alice")
        room.state = "QUESTION"
        room._remove_connection("p1")
        assert room._player_event == ("disconnected", "Alice")

    def test_teams_not_cleaned_during_game(self):
        """Teams should stay so they can be restored on reconnect."""
        room = make_room()
        add_player(room, "p1", "Alice", team="Red")
        room.state = "QUESTION"
        room._remove_connection("p1")
        assert "Alice" in room.teams


class TestRemoveConnectionOrganizer:
    def test_organizer_cleared(self):
        room = make_room()
        add_organizer(room, "org-1")
        room._remove_connection("org-1")
        assert room.organizer is None
        assert room.organizer_id is None

    def test_organizer_disconnect_flag_set(self):
        room = make_room()
        add_organizer(room, "org-1")
        room._remove_connection("org-1")
        assert room._organizer_just_disconnected is True


# ===========================================================================
# Room.reset_for_new_game
# ===========================================================================

class TestResetForNewGame:
    def test_state_reset_to_lobby(self):
        room = make_room()
        room.state = "PODIUM"
        room.reset_for_new_game(make_quiz(3), 20)
        assert room.state == "LOBBY"

    def test_question_index_reset(self):
        room = make_room()
        room.current_question_index = 4
        room.reset_for_new_game(make_quiz(3), 20)
        assert room.current_question_index == -1

    def test_scores_reset_to_zero(self):
        room = make_room()
        add_player(room, "p1", "Alice", score=999)
        room.state = "PODIUM"
        room.reset_for_new_game(make_quiz(3), 20)
        assert room.players["p1"]["score"] == 0

    def test_disconnected_players_cleared(self):
        room = make_room()
        room.disconnected_players["Alice"] = {"score": 100}
        room.reset_for_new_game(make_quiz(3), 20)
        assert len(room.disconnected_players) == 0

    def test_bonus_questions_cleared(self):
        room = make_room()
        room.bonus_questions = {1, 2, 3}
        room.reset_for_new_game(make_quiz(3), 20)
        assert len(room.bonus_questions) == 0

    def test_stale_players_removed(self):
        """Players no longer connected should be removed on reset."""
        room = make_room()
        add_player(room, "p1", "Alice")
        # p2 has no connection
        room.players["p2"] = {"nickname": "Bob", "score": 100, "prev_rank": 0, "streak": 0}
        room.teams["Bob"] = "Blue"
        room.power_ups["Bob"] = {"double_points": True, "fifty_fifty": True}
        room.reset_for_new_game(make_quiz(3), 20)
        assert "p2" not in room.players
        assert "Bob" not in room.teams
        assert "p1" in room.players

    def test_new_quiz_applied(self):
        room = make_room(num_questions=5)
        new_quiz = make_quiz(3)
        room.reset_for_new_game(new_quiz, 25)
        assert len(room.quiz["questions"]) == 3
        assert room.time_limit == 25


# ===========================================================================
# State Guards — handle_message
# ===========================================================================

class TestStateGuardStartGame:
    @pytest.mark.asyncio
    async def test_start_game_only_from_lobby(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        add_player(room, "p1", "Alice")

        room.state = "LOBBY"
        await sm.handle_message(room, "org-1", {"type": "START_GAME"}, is_organizer=True)
        assert room.state == "INTRO"

    @pytest.mark.asyncio
    async def test_start_game_blocked_from_question(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        room.state = "QUESTION"
        await sm.handle_message(room, "org-1", {"type": "START_GAME"}, is_organizer=True)
        assert room.state == "QUESTION"

    @pytest.mark.asyncio
    async def test_start_game_blocked_from_podium(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        room.state = "PODIUM"
        await sm.handle_message(room, "org-1", {"type": "START_GAME"}, is_organizer=True)
        assert room.state == "PODIUM"


class TestStateGuardNextQuestion:
    @pytest.mark.asyncio
    async def test_next_question_from_intro_starts_question(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        add_player(room, "p1", "Alice")
        room.state = "INTRO"
        await sm.handle_message(room, "org-1", {"type": "NEXT_QUESTION"}, is_organizer=True)
        # Should have advanced to QUESTION (after start_question)
        assert room.state == "QUESTION"
        assert room.current_question_index == 0

    @pytest.mark.asyncio
    async def test_next_question_from_leaderboard_starts_question(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        add_player(room, "p1", "Alice")
        room.state = "LEADERBOARD"
        room.current_question_index = 0
        await sm.handle_message(room, "org-1", {"type": "NEXT_QUESTION"}, is_organizer=True)
        assert room.state == "QUESTION"
        assert room.current_question_index == 1

    @pytest.mark.asyncio
    async def test_next_question_from_question_ends_it(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        add_player(room, "p1", "Alice")
        room.state = "QUESTION"
        room.current_question_index = 0
        room.question_start_time = time.time()
        await sm.handle_message(room, "org-1", {"type": "NEXT_QUESTION"}, is_organizer=True)
        assert room.state == "LEADERBOARD"

    @pytest.mark.asyncio
    async def test_next_question_blocked_from_podium(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        room.state = "PODIUM"
        room.current_question_index = 4
        await sm.handle_message(room, "org-1", {"type": "NEXT_QUESTION"}, is_organizer=True)
        assert room.state == "PODIUM"

    @pytest.mark.asyncio
    async def test_next_question_blocked_from_lobby(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        room.state = "LOBBY"
        await sm.handle_message(room, "org-1", {"type": "NEXT_QUESTION"}, is_organizer=True)
        assert room.state == "LOBBY"


class TestStateGuardSetTimeLimit:
    @pytest.mark.asyncio
    async def test_set_time_limit_from_lobby(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        room.state = "LOBBY"
        await sm.handle_message(room, "org-1", {"type": "SET_TIME_LIMIT", "time_limit": 30}, is_organizer=True)
        assert room.time_limit == 30

    @pytest.mark.asyncio
    async def test_set_time_limit_blocked_from_question(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        room.state = "QUESTION"
        old_limit = room.time_limit
        await sm.handle_message(room, "org-1", {"type": "SET_TIME_LIMIT", "time_limit": 60}, is_organizer=True)
        assert room.time_limit == old_limit

    @pytest.mark.asyncio
    async def test_set_time_limit_bounds(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        room.state = "LOBBY"
        # Too low
        await sm.handle_message(room, "org-1", {"type": "SET_TIME_LIMIT", "time_limit": 2}, is_organizer=True)
        assert room.time_limit == 15  # unchanged
        # Too high
        await sm.handle_message(room, "org-1", {"type": "SET_TIME_LIMIT", "time_limit": 120}, is_organizer=True)
        assert room.time_limit == 15  # unchanged
        # Non-integer
        await sm.handle_message(room, "org-1", {"type": "SET_TIME_LIMIT", "time_limit": "abc"}, is_organizer=True)
        assert room.time_limit == 15


class TestStateGuardEndQuiz:
    @pytest.mark.asyncio
    async def test_end_quiz_from_question(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        add_player(room, "p1", "Alice")
        room.state = "QUESTION"
        room.current_question_index = 2
        room.question_start_time = time.time()
        await sm.handle_message(room, "org-1", {"type": "END_QUIZ"}, is_organizer=True)
        assert room.state == "PODIUM"

    @pytest.mark.asyncio
    async def test_end_quiz_from_leaderboard(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        add_player(room, "p1", "Alice")
        room.state = "LEADERBOARD"
        await sm.handle_message(room, "org-1", {"type": "END_QUIZ"}, is_organizer=True)
        assert room.state == "PODIUM"

    @pytest.mark.asyncio
    async def test_end_quiz_blocked_from_lobby(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        room.state = "LOBBY"
        await sm.handle_message(room, "org-1", {"type": "END_QUIZ"}, is_organizer=True)
        assert room.state == "LOBBY"

    @pytest.mark.asyncio
    async def test_end_quiz_blocked_from_podium(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        room.state = "PODIUM"
        await sm.handle_message(room, "org-1", {"type": "END_QUIZ"}, is_organizer=True)
        assert room.state == "PODIUM"


class TestStateGuardUsePowerUp:
    @pytest.mark.asyncio
    async def test_power_up_blocked_outside_question(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        ws = add_player(room, "p1", "Alice")
        for state in ("LOBBY", "INTRO", "LEADERBOARD", "PODIUM"):
            room.state = state
            ws.sent_messages.clear()
            await sm.handle_message(room, "p1", {"type": "USE_POWER_UP", "power_up": "double_points"}, is_organizer=False)
            assert not ws.all("POWER_UP_ACTIVATED")

    @pytest.mark.asyncio
    async def test_power_up_works_in_question(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        ws = add_player(room, "p1", "Alice")
        room.state = "QUESTION"
        room.current_question_index = 0
        await sm.handle_message(room, "p1", {"type": "USE_POWER_UP", "power_up": "double_points"}, is_organizer=False)
        assert ws.last("POWER_UP_ACTIVATED") is not None


class TestStateGuardResetRoom:
    @pytest.mark.asyncio
    async def test_reset_room_only_from_podium(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        new_quiz = make_quiz(3)

        for state in ("LOBBY", "INTRO", "QUESTION", "LEADERBOARD"):
            room.state = state
            await sm.handle_message(room, "org-1", {
                "type": "RESET_ROOM", "quiz_data": new_quiz, "time_limit": 20
            }, is_organizer=True)
            assert room.state == state  # unchanged

    @pytest.mark.asyncio
    async def test_reset_room_works_from_podium(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        add_player(room, "p1", "Alice")
        room.state = "PODIUM"
        new_quiz = make_quiz(3)
        # Register quiz in content store so RESET_ROOM can find it
        from main import quizzes
        quizzes["test-reset-quiz"] = new_quiz
        try:
            await sm.handle_message(room, "org-1", {
                "type": "RESET_ROOM", "content_id": "test-reset-quiz", "time_limit": 20
            }, is_organizer=True)
            assert room.state == "LOBBY"
            assert len(room.quiz["questions"]) == 3
            assert room.content_id == "test-reset-quiz"
        finally:
            quizzes.pop("test-reset-quiz", None)

    @pytest.mark.asyncio
    async def test_reset_room_rejects_missing_content(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        room.state = "PODIUM"
        await sm.handle_message(room, "org-1", {
            "type": "RESET_ROOM", "content_id": "nonexistent-id", "time_limit": 20
        }, is_organizer=True)
        assert room.state == "PODIUM"  # unchanged, rejected


# ===========================================================================
# ANSWER handler
# ===========================================================================

class TestAnswerHandler:
    @pytest.mark.asyncio
    async def test_correct_answer_awards_points(self):
        room = make_room()
        sm = SocketManager()
        org_ws = add_organizer(room, "org-1")
        p_ws = add_player(room, "p1", "Alice")
        room.state = "QUESTION"
        room.current_question_index = 0
        room.question_start_time = time.time()

        await sm.handle_message(room, "p1", {"type": "ANSWER", "answer_index": 0}, is_organizer=False)
        result = p_ws.last("ANSWER_RESULT")
        assert result is not None
        assert result["correct"] is True
        assert result["points"] > 0

    @pytest.mark.asyncio
    async def test_wrong_answer_gives_zero_points(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        p_ws = add_player(room, "p1", "Alice")
        room.state = "QUESTION"
        room.current_question_index = 0
        room.question_start_time = time.time()

        await sm.handle_message(room, "p1", {"type": "ANSWER", "answer_index": 1}, is_organizer=False)
        result = p_ws.last("ANSWER_RESULT")
        assert result["correct"] is False
        assert result["points"] == 0

    @pytest.mark.asyncio
    async def test_double_answer_rejected(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        p_ws = add_player(room, "p1", "Alice")
        room.state = "QUESTION"
        room.current_question_index = 0
        room.question_start_time = time.time()

        await sm.handle_message(room, "p1", {"type": "ANSWER", "answer_index": 0}, is_organizer=False)
        first_score = room.players["p1"]["score"]
        p_ws.sent_messages.clear()

        await sm.handle_message(room, "p1", {"type": "ANSWER", "answer_index": 0}, is_organizer=False)
        assert room.players["p1"]["score"] == first_score  # no change
        assert p_ws.last("ANSWER_RESULT") is None  # no second result

    @pytest.mark.asyncio
    async def test_answer_rejected_outside_question_state(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        p_ws = add_player(room, "p1", "Alice")
        room.current_question_index = 0
        room.question_start_time = time.time()

        for state in ("LOBBY", "INTRO", "LEADERBOARD", "PODIUM"):
            room.state = state
            room.answered_players.clear()
            p_ws.sent_messages.clear()
            await sm.handle_message(room, "p1", {"type": "ANSWER", "answer_index": 0}, is_organizer=False)
            assert p_ws.last("ANSWER_RESULT") is None

    @pytest.mark.asyncio
    async def test_answer_from_non_player_rejected(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        room.state = "QUESTION"
        room.current_question_index = 0
        room.question_start_time = time.time()
        # "spectator-1" is not in room.players
        add_spectator(room, "spectator-1")
        await sm.handle_message(room, "spectator-1", {"type": "ANSWER", "answer_index": 0}, is_organizer=False)
        # No crash, no result sent

    @pytest.mark.asyncio
    async def test_answer_out_of_bounds_rejected(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        p_ws = add_player(room, "p1", "Alice")
        room.state = "QUESTION"
        room.current_question_index = 0
        room.question_start_time = time.time()

        await sm.handle_message(room, "p1", {"type": "ANSWER", "answer_index": 99}, is_organizer=False)
        assert p_ws.last("ANSWER_RESULT") is None

    @pytest.mark.asyncio
    async def test_all_answered_triggers_end_question(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        add_player(room, "p1", "Alice")
        add_player(room, "p2", "Bob")
        room.state = "QUESTION"
        room.current_question_index = 0
        room.question_start_time = time.time()

        await sm.handle_message(room, "p1", {"type": "ANSWER", "answer_index": 0}, is_organizer=False)
        assert room.state == "QUESTION"  # not yet

        await sm.handle_message(room, "p2", {"type": "ANSWER", "answer_index": 0}, is_organizer=False)
        assert room.state == "LEADERBOARD"  # all answered → ended


# ===========================================================================
# End question guard
# ===========================================================================

class TestEndQuestionGuard:
    @pytest.mark.asyncio
    async def test_double_fire_prevented(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        add_player(room, "p1", "Alice")
        room.state = "QUESTION"
        room.current_question_index = 0
        room.question_start_time = time.time()

        await sm.end_question(room)
        assert room.state == "LEADERBOARD"
        org_ws = room.connections["org-1"]
        count_before = len(org_ws.sent_messages)

        # Second call should be a no-op
        await sm.end_question(room)
        assert room.state == "LEADERBOARD"
        assert len(org_ws.sent_messages) == count_before


# ===========================================================================
# JOIN handler — reconnection paths
# ===========================================================================

class TestJoinReconnection:
    @pytest.mark.asyncio
    async def test_reconnect_from_disconnected_players(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        room.state = "LEADERBOARD"
        room.current_question_index = 2
        room.disconnected_players["Alice"] = {
            "score": 500,
            "prev_rank": 1,
            "streak": 3,
            "avatar": "",
            "_answered_client_id": None,
        }
        new_ws = MockWebSocket()
        room.connections["p2"] = new_ws
        await sm.handle_message(room, "p2", {
            "type": "JOIN", "nickname": "Alice", "avatar": ""
        }, is_organizer=False)

        assert "p2" in room.players
        assert room.players["p2"]["score"] == 500
        assert room.players["p2"]["streak"] == 3
        assert "Alice" not in room.disconnected_players
        reconnected = new_ws.last("RECONNECTED")
        assert reconnected is not None
        assert reconnected["score"] == 500

    @pytest.mark.asyncio
    async def test_reconnect_transfers_answered_status(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        room.state = "QUESTION"
        room.current_question_index = 0
        room.answered_players.add("old-p1")
        room.disconnected_players["Alice"] = {
            "score": 300,
            "prev_rank": 0,
            "streak": 1,
            "avatar": "",
            "_answered_client_id": "old-p1",
        }
        new_ws = MockWebSocket()
        room.connections["new-p1"] = new_ws
        await sm.handle_message(room, "new-p1", {
            "type": "JOIN", "nickname": "Alice"
        }, is_organizer=False)

        assert "old-p1" not in room.answered_players
        assert "new-p1" in room.answered_players

    @pytest.mark.asyncio
    async def test_duplicate_nickname_kicks_old_connection(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        old_ws = add_player(room, "p1", "Alice")
        room.state = "QUESTION"
        room.current_question_index = 0

        new_ws = MockWebSocket()
        room.connections["p2"] = new_ws
        await sm.handle_message(room, "p2", {
            "type": "JOIN", "nickname": "Alice"
        }, is_organizer=False)

        # Old connection should have been kicked
        kicked = old_ws.last("KICKED")
        assert kicked is not None
        assert old_ws.closed
        # New connection has the player data
        assert "p2" in room.players
        assert room.players["p2"]["nickname"] == "Alice"
        assert "p1" not in room.players

    @pytest.mark.asyncio
    async def test_duplicate_nickname_transfers_answered_status(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        add_player(room, "p1", "Alice")
        room.state = "QUESTION"
        room.current_question_index = 0
        room.answered_players.add("p1")

        new_ws = MockWebSocket()
        room.connections["p2"] = new_ws
        await sm.handle_message(room, "p2", {
            "type": "JOIN", "nickname": "Alice"
        }, is_organizer=False)

        assert "p1" not in room.answered_players
        assert "p2" in room.answered_players

    @pytest.mark.asyncio
    async def test_reconnect_during_question_includes_question_data(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        room.state = "QUESTION"
        room.current_question_index = 1
        room.disconnected_players["Alice"] = {
            "score": 200, "prev_rank": 0, "streak": 0, "avatar": "",
            "_answered_client_id": None,
        }
        new_ws = MockWebSocket()
        room.connections["p1"] = new_ws
        await sm.handle_message(room, "p1", {"type": "JOIN", "nickname": "Alice"}, is_organizer=False)

        reconnected = new_ws.last("RECONNECTED")
        assert "question" in reconnected
        assert "answer_index" not in reconnected["question"]  # answer stripped
        assert reconnected["time_limit"] == room.time_limit


# ===========================================================================
# JOIN handler — validation
# ===========================================================================

class TestJoinValidation:
    @pytest.mark.asyncio
    async def test_empty_nickname_rejected(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        ws = MockWebSocket()
        room.connections["p1"] = ws
        await sm.handle_message(room, "p1", {"type": "JOIN", "nickname": ""}, is_organizer=False)
        assert "p1" not in room.players
        err = ws.last("ERROR")
        assert err is not None

    @pytest.mark.asyncio
    async def test_long_nickname_rejected(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        ws = MockWebSocket()
        room.connections["p1"] = ws
        await sm.handle_message(room, "p1", {
            "type": "JOIN", "nickname": "A" * (config.MAX_NICKNAME_LENGTH + 1)
        }, is_organizer=False)
        assert "p1" not in room.players

    @pytest.mark.asyncio
    async def test_html_in_nickname_stripped(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        ws = MockWebSocket()
        room.connections["p1"] = ws
        await sm.handle_message(room, "p1", {
            "type": "JOIN", "nickname": "<b>Alice</b>"
        }, is_organizer=False)
        assert room.players["p1"]["nickname"] == "Alice"

    @pytest.mark.asyncio
    async def test_max_players_enforced(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        # Fill to max
        for i in range(config.MAX_PLAYERS_PER_ROOM):
            add_player(room, f"p{i}", f"Player{i}")
        # Try one more
        ws = MockWebSocket()
        room.connections["extra"] = ws
        await sm.handle_message(room, "extra", {
            "type": "JOIN", "nickname": "Overflow"
        }, is_organizer=False)
        assert "extra" not in room.players
        err = ws.last("ERROR")
        assert err is not None
        assert "full" in err["message"].lower()

    @pytest.mark.asyncio
    async def test_common_ground_allows_new_player_join_during_active_game(self):
        room = Room("COM001", {
            "game_title": "Common Ground",
            "team_size": 2,
            "rounds": 2,
            "discussion_time_seconds": 90,
            "vote_time_seconds": 30,
            "voting_enabled": True,
        }, game_type="common_ground")
        sm = SocketManager()
        for index, name in enumerate(["Alice", "Bob", "Cara", "Dee"], start=1):
            add_player(room, f"p{index}", name)
        sm._start_common_ground_game(room)
        room.locked = True

        ws = MockWebSocket()
        room.connections["late"] = ws
        await sm.handle_message(room, "late", {
            "type": "JOIN",
            "nickname": "Fara",
            "avatar": "🦊",
        }, is_organizer=False)

        joined = ws.last("JOINED_ROOM")
        assert joined is not None
        assert joined["game_type"] == "common_ground"
        assert joined["common_ground"]["my_team_id"]
        assert "late" in room.players
        assert any("Fara" in team["player_ids"] for team in room.common_state["teams"])
        assert ws.last("ERROR") is None


# ===========================================================================
# Spectator sync
# ===========================================================================

class TestSpectatorSync:
    def test_spectator_sync_includes_team_leaderboard(self):
        """SPECTATOR_SYNC should include team_leaderboard (recent fix)."""
        room = make_room()
        sm = SocketManager()
        add_player(room, "p1", "Alice", score=500, team="Red")
        add_player(room, "p2", "Bob", score=300, team="Blue")
        room.state = "PODIUM"

        # Build what the sync message would contain
        sync = {
            "type": "SPECTATOR_SYNC",
            "room_code": room.room_code,
            "state": room.state,
            "player_count": len(room.players),
            "leaderboard": sm.get_leaderboard(room),
            "team_leaderboard": sm.get_team_leaderboard(room),
        }
        assert "team_leaderboard" in sync
        assert len(sync["team_leaderboard"]) == 2
        assert sync["team_leaderboard"][0]["team"] == "Red"


# ===========================================================================
# Bonus round selection
# ===========================================================================

class TestBonusRoundSelection:
    def test_no_bonus_for_small_quiz(self):
        room = make_room(num_questions=3)
        sm = SocketManager()
        sm._select_bonus_questions(room)
        assert len(room.bonus_questions) == 0

    def test_bonus_excludes_first_and_last(self):
        room = make_room(num_questions=10)
        sm = SocketManager()
        sm._select_bonus_questions(room)
        assert 0 not in room.bonus_questions
        assert 9 not in room.bonus_questions

    def test_bonus_count_reasonable(self):
        room = make_room(num_questions=10)
        sm = SocketManager()
        sm._select_bonus_questions(room)
        expected = max(1, int(10 * config.BONUS_ROUND_FRACTION))
        assert len(room.bonus_questions) == expected


# ===========================================================================
# Bonus scoring
# ===========================================================================

class TestBonusScoring:
    @pytest.mark.asyncio
    async def test_bonus_doubles_base_points(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        p_ws = add_player(room, "p1", "Alice")
        room.state = "QUESTION"
        room.current_question_index = 0
        room.question_start_time = time.time()
        room.bonus_questions = {0}  # this question is bonus

        await sm.handle_message(room, "p1", {"type": "ANSWER", "answer_index": 0}, is_organizer=False)
        result = p_ws.last("ANSWER_RESULT")
        assert result["correct"] is True
        assert result["is_bonus"] is True
        # Bonus points should be roughly 2x normal (instant answer ≈ 2000)
        assert result["points"] >= 1800

    @pytest.mark.asyncio
    async def test_non_bonus_normal_points(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        p_ws = add_player(room, "p1", "Alice")
        room.state = "QUESTION"
        room.current_question_index = 0
        room.question_start_time = time.time()
        room.bonus_questions = set()  # not bonus

        await sm.handle_message(room, "p1", {"type": "ANSWER", "answer_index": 0}, is_organizer=False)
        result = p_ws.last("ANSWER_RESULT")
        assert result["is_bonus"] is False
        assert result["points"] <= 1000


# ===========================================================================
# Organizer sync on reconnect
# ===========================================================================

class TestOrganizerSync:
    @pytest.mark.asyncio
    async def test_send_organizer_sync_contents(self):
        room = make_room()
        sm = SocketManager()
        org_ws = add_organizer(room, "org-1")
        add_player(room, "p1", "Alice", score=400)
        room.state = "LEADERBOARD"
        room.current_question_index = 2

        await sm._send_organizer_sync(room)
        sync = org_ws.last("ORGANIZER_RECONNECTED")
        assert sync is not None
        assert sync["state"] == "LEADERBOARD"
        assert sync["question_number"] == 3
        assert sync["player_count"] == 1
        assert "leaderboard" in sync
        assert "team_leaderboard" in sync
        assert "quiz" in sync

    @pytest.mark.asyncio
    async def test_send_organizer_sync_during_question(self):
        room = make_room()
        sm = SocketManager()
        org_ws = add_organizer(room, "org-1")
        add_player(room, "p1", "Alice")
        room.state = "QUESTION"
        room.current_question_index = 1
        room.question_start_time = time.time()
        room.answered_players.add("p1")

        await sm._send_organizer_sync(room)
        sync = org_ws.last("ORGANIZER_RECONNECTED")
        assert "question" in sync
        assert sync["answered_count"] == 1
        assert "is_bonus" in sync
        assert "time_remaining" in sync


# ===========================================================================
# start_question / end_question flow
# ===========================================================================

class TestStartEndQuestion:
    @pytest.mark.asyncio
    async def test_start_question_advances_index(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        add_player(room, "p1", "Alice")
        room.state = "INTRO"
        await sm.start_question(room)
        assert room.current_question_index == 0
        assert room.state == "QUESTION"

    @pytest.mark.asyncio
    async def test_start_question_clears_answered(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        add_player(room, "p1", "Alice")
        room.answered_players = {"p1"}
        room.state = "INTRO"
        await sm.start_question(room)
        assert len(room.answered_players) == 0

    @pytest.mark.asyncio
    async def test_start_question_broadcasts_question(self):
        room = make_room()
        sm = SocketManager()
        org_ws = add_organizer(room, "org-1")
        p_ws = add_player(room, "p1", "Alice")
        room.state = "INTRO"
        await sm.start_question(room)
        q_msg = org_ws.last("QUESTION")
        assert q_msg is not None
        assert "question" in q_msg
        assert "answer_index" not in q_msg["question"]  # stripped for players
        assert q_msg["question_number"] == 1

    @pytest.mark.asyncio
    async def test_end_question_broadcasts_question_over(self):
        room = make_room()
        sm = SocketManager()
        org_ws = add_organizer(room, "org-1")
        p_ws = add_player(room, "p1", "Alice")
        room.state = "QUESTION"
        room.current_question_index = 0
        room.question_start_time = time.time()
        await sm.end_question(room)
        qo = org_ws.last("QUESTION_OVER")
        assert qo is not None
        assert "leaderboard" in qo
        assert "answer" in qo

    @pytest.mark.asyncio
    async def test_final_question_is_final_flag(self):
        room = make_room(num_questions=2)
        sm = SocketManager()
        add_organizer(room, "org-1")
        p_ws = add_player(room, "p1", "Alice")
        room.state = "QUESTION"
        room.current_question_index = 1  # last question (index 1 of 2)
        room.question_start_time = time.time()
        await sm.end_question(room)
        qo = p_ws.last("QUESTION_OVER")
        assert qo["is_final"] is True

    @pytest.mark.asyncio
    async def test_last_question_next_goes_to_podium(self):
        room = make_room(num_questions=2)
        sm = SocketManager()
        org_ws = add_organizer(room, "org-1")
        p_ws = add_player(room, "p1", "Alice")
        room.state = "LEADERBOARD"
        room.current_question_index = 1  # already on last question
        await sm.start_question(room)
        # index now 2, which >= len(questions)=2 → PODIUM
        assert room.state == "PODIUM"
        podium = org_ws.last("PODIUM")
        assert podium is not None
        assert "leaderboard" in podium
        assert "team_leaderboard" in podium

    @pytest.mark.asyncio
    async def test_streak_reset_for_unanswered_players(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        add_player(room, "p1", "Alice")
        add_player(room, "p2", "Bob")
        room.players["p1"]["streak"] = 3
        room.players["p2"]["streak"] = 5
        room.state = "QUESTION"
        room.current_question_index = 0
        room.question_start_time = time.time()
        room.answered_players = {"p1"}  # only Alice answered

        await sm.end_question(room)
        assert room.players["p1"]["streak"] == 3  # preserved
        assert room.players["p2"]["streak"] == 0  # reset


# ===========================================================================
# Broadcast routing
# ===========================================================================

class TestBroadcastRouting:
    @pytest.mark.asyncio
    async def test_broadcast_reaches_players_and_spectators(self):
        room = make_room()
        org_ws = add_organizer(room, "org-1")
        p_ws = add_player(room, "p1", "Alice")
        spec_ws = add_spectator(room, "spec-1")
        await room.broadcast({"type": "TEST"})
        assert org_ws.last("TEST") is not None
        assert p_ws.last("TEST") is not None
        assert spec_ws.last("TEST") is not None

    @pytest.mark.asyncio
    async def test_broadcast_dead_lobby_player_sends_updated_roster(self):
        room = make_room()
        room.state = "LOBBY"
        org_ws = add_organizer(room, "org-1")
        add_player(room, "p1", "Alice")
        add_player(room, "p2", "Bob")
        room.connections["p1"] = FailingWebSocket()

        await room.broadcast({"type": "ROOM_RESET", "player_count": 2, "players": []})

        assert "p1" not in room.players
        assert "p2" in room.players
        update = org_ws.last("PLAYER_LEFT")
        assert update is not None
        assert update["nickname"] == "Alice"
        assert update["player_count"] == 1
        assert update["players"] == [{"nickname": "Bob", "avatar": ""}]

    @pytest.mark.asyncio
    async def test_housie_sync_dead_player_sends_updated_roster(self):
        room = make_housie_room()
        sm = SocketManager()
        org_ws = add_organizer(room, "org-1")
        add_player(room, "p1", "Alice")
        add_player(room, "p2", "Bob")
        room.connections["p1"] = FailingWebSocket()
        sm._start_housie_round(room)

        await sm._broadcast_housie_sync(room)

        assert "p1" not in room.players
        assert "Alice" in room.disconnected_players
        update = org_ws.last("PLAYER_DISCONNECTED")
        assert update is not None
        assert update["nickname"] == "Alice"
        assert update["player_count"] == 1
        assert update["players"] == [{"nickname": "Bob", "avatar": ""}]

    @pytest.mark.asyncio
    async def test_broadcast_to_players_excludes_organizer_and_spectators(self):
        room = make_room()
        org_ws = add_organizer(room, "org-1")
        p_ws = add_player(room, "p1", "Alice")
        spec_ws = add_spectator(room, "spec-1")
        await room.broadcast_to_players({"type": "PLAYER_ONLY"})
        assert p_ws.last("PLAYER_ONLY") is not None
        assert org_ws.last("PLAYER_ONLY") is None
        assert spec_ws.last("PLAYER_ONLY") is None

    @pytest.mark.asyncio
    async def test_send_to_organizer_only(self):
        room = make_room()
        org_ws = add_organizer(room, "org-1")
        p_ws = add_player(room, "p1", "Alice")
        await room.send_to_organizer({"type": "ORG_ONLY"})
        assert org_ws.last("ORG_ONLY") is not None
        assert p_ws.last("ORG_ONLY") is None


# ===========================================================================
# Spark Charging — START_GAME
# ===========================================================================

class TestSparkChargingStartGame:
    @pytest.mark.asyncio
    async def test_start_game_charges_sparks(self):
        room = make_room()
        sm = SocketManager()
        org_ws = add_organizer(room, "org-1")
        add_player(room, "p1", "Alice")
        room.state = "LOBBY"
        room.wallet_id = "test-wallet-id"
        with patch("socket_manager.token_module.spend_room", return_value=(True, 10)):
            await sm.handle_message(room, "org-1", {"type": "START_GAME"}, is_organizer=True)
        assert room.state == "INTRO"

    @pytest.mark.asyncio
    async def test_start_game_insufficient_sparks(self):
        room = make_room()
        sm = SocketManager()
        org_ws = add_organizer(room, "org-1")
        add_player(room, "p1", "Alice")
        room.state = "LOBBY"
        room.wallet_id = "test-wallet-id"
        with patch("socket_manager.token_module.spend_room", return_value=(False, 0)):
            await sm.handle_message(room, "org-1", {"type": "START_GAME"}, is_organizer=True)
        assert room.state == "LOBBY"
        assert org_ws.last("INSUFFICIENT_SPARKS") is not None

    @pytest.mark.asyncio
    async def test_housie_start_prunes_dead_players_before_minimum_check(self):
        room = Room("HOU002", default_housie_game("Unit Housie"), game_type="housie")
        room.wallet_id = "test-wallet-id"
        room.state = "LOBBY"
        sm = SocketManager()
        org_ws = add_organizer(room, "org-1")
        add_player(room, "p1", "Alice")
        add_player(room, "p2", "Bob")
        room.connections["p1"] = FailingWebSocket()

        with patch("socket_manager.token_module.spend_room", return_value=(True, 10)) as spend_room:
            await sm.handle_message(room, "org-1", {"type": "START_GAME"}, is_organizer=True)

        spend_room.assert_not_called()
        assert room.state == "LOBBY"
        assert "p1" not in room.players
        assert "p2" in room.players
        roster = org_ws.last("PLAYER_LEFT")
        assert roster is not None
        assert roster["player_count"] == 1
        error = org_ws.last("ERROR")
        assert error is not None
        assert "at least" in error["message"]

    @pytest.mark.asyncio
    async def test_start_game_no_wallet_sends_error(self):
        room = make_room()
        sm = SocketManager()
        org_ws = add_organizer(room, "org-1")
        add_player(room, "p1", "Alice")
        room.state = "LOBBY"
        room.wallet_id = None
        await sm.handle_message(room, "org-1", {"type": "START_GAME"}, is_organizer=True)
        assert room.state == "LOBBY"
        assert org_ws.last("ERROR") is not None


# ===========================================================================
# Spark Charging — RESET_ROOM
# ===========================================================================

class TestSparkChargingResetRoom:
    @pytest.mark.asyncio
    async def test_reset_room_charges_sparks(self):
        room = make_room()
        sm = SocketManager()
        org_ws = add_organizer(room, "org-1")
        add_player(room, "p1", "Alice")
        room.state = "PODIUM"
        room.wallet_id = "test-wallet-id"
        new_quiz = make_quiz(3)
        from main import quizzes
        quizzes["spark-reset-quiz"] = new_quiz
        try:
            with patch("socket_manager.token_module.spend_room", return_value=(True, 10)):
                await sm.handle_message(room, "org-1", {
                    "type": "RESET_ROOM", "content_id": "spark-reset-quiz", "time_limit": 20
                }, is_organizer=True)
            assert room.state == "LOBBY"
        finally:
            quizzes.pop("spark-reset-quiz", None)

    @pytest.mark.asyncio
    async def test_reset_room_insufficient_sparks(self):
        room = make_room()
        sm = SocketManager()
        org_ws = add_organizer(room, "org-1")
        add_player(room, "p1", "Alice")
        room.state = "PODIUM"
        room.wallet_id = "test-wallet-id"
        # Seed valid content so validation passes, then charge fails
        new_quiz = make_quiz(3)
        from main import quizzes
        quizzes["insuff-quiz"] = new_quiz
        try:
            with patch("socket_manager.token_module.spend_room", return_value=(False, 0)):
                await sm.handle_message(room, "org-1", {
                    "type": "RESET_ROOM", "content_id": "insuff-quiz", "time_limit": 20
                }, is_organizer=True)
            assert room.state == "PODIUM"
            assert org_ws.last("INSUFFICIENT_SPARKS") is not None
        finally:
            quizzes.pop("insuff-quiz", None)

    @pytest.mark.asyncio
    async def test_reset_room_skips_sparks_for_host_app_managed_rooms(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        add_player(room, "p1", "Alice")
        room.state = "PODIUM"
        room.wallet_id = "revelry:party:test"
        room.billing_mode = "host_app_managed"
        new_quiz = make_quiz(3)
        from main import quizzes
        quizzes["host-app-reset-quiz"] = new_quiz
        try:
            with patch("socket_manager.token_module.spend_room") as spend_room:
                await sm.handle_message(room, "org-1", {
                    "type": "RESET_ROOM", "content_id": "host-app-reset-quiz", "time_limit": 20
                }, is_organizer=True)
            spend_room.assert_not_called()
            assert room.state == "LOBBY"
        finally:
            quizzes.pop("host-app-reset-quiz", None)


# ---------------------------------------------------------------------------
# Reset deepcopy isolation
# ---------------------------------------------------------------------------

class TestResetDeepcopy:
    """reset_for_new_game must deepcopy game data so mutations don't corrupt the original."""

    def test_reset_deepcopy_isolates_quiz(self):
        original = make_quiz(2)
        room = Room("DCPY", original, 15)
        new_data = make_quiz(3)
        room.reset_for_new_game(new_data, 20)
        # Mutate the room's quiz in-place (simulates gameplay adding image URLs etc)
        room.quiz["questions"][0]["image_url"] = "http://injected.png"
        room.quiz["mutated"] = True
        # Original data must be untouched
        assert "image_url" not in new_data["questions"][0]
        assert "mutated" not in new_data

    def test_reset_deepcopy_nested_lists(self):
        original = make_quiz(2)
        room = Room("DCPY", original, 15)
        new_data = make_quiz(2)
        room.reset_for_new_game(new_data, 20)
        # Mutate nested option list
        room.quiz["questions"][0]["options"].append("EXTRA")
        assert len(new_data["questions"][0]["options"]) == 4  # unchanged


# ---------------------------------------------------------------------------
# RESET_ROOM content ownership check
# ---------------------------------------------------------------------------

class TestResetRoomContentOwnership:
    """RESET_ROOM should reject content owned by another wallet."""

    @pytest.mark.asyncio
    async def test_reset_room_rejects_foreign_content(self):
        from main import quizzes, content_owners
        sm = SocketManager()
        quiz = make_quiz(3)
        room = sm.create_room("OWNR", quiz, 15, organizer_token="tok")
        room.state = "PODIUM"
        room.wallet_id = "wallet-A"

        # Seed content owned by wallet-B
        foreign_quiz = make_quiz(2)
        quizzes["foreign-quiz"] = foreign_quiz
        content_owners["foreign-quiz"] = "wallet-B"

        org_ws = MockWebSocket()
        room.connections["org-1"] = org_ws
        try:
            with patch("socket_manager.token_module.spend_room", return_value=(True, 10)):
                await sm.handle_message(room, "org-1", {
                    "type": "RESET_ROOM", "content_id": "foreign-quiz", "time_limit": 20
                }, is_organizer=True)
            # Should stay in PODIUM (rejected)
            assert room.state == "PODIUM"
            assert org_ws.last("ERROR") is not None
        finally:
            quizzes.pop("foreign-quiz", None)
            content_owners.pop("foreign-quiz", None)

    @pytest.mark.asyncio
    async def test_reset_room_allows_own_content(self):
        from main import quizzes, content_owners
        sm = SocketManager()
        quiz = make_quiz(3)
        room = sm.create_room("OWNR", quiz, 15, organizer_token="tok")
        room.state = "PODIUM"
        room.wallet_id = "wallet-A"

        own_quiz = make_quiz(2)
        quizzes["own-quiz"] = own_quiz
        content_owners["own-quiz"] = "wallet-A"

        org_ws = MockWebSocket()
        room.connections["org-1"] = org_ws
        try:
            with patch("socket_manager.token_module.spend_room", return_value=(True, 10)):
                await sm.handle_message(room, "org-1", {
                    "type": "RESET_ROOM", "content_id": "own-quiz", "time_limit": 20
                }, is_organizer=True)
            assert room.state == "LOBBY"
        finally:
            quizzes.pop("own-quiz", None)
            content_owners.pop("own-quiz", None)


# ---------------------------------------------------------------------------
# Housie auto-caller claim pause behavior
# ---------------------------------------------------------------------------

class TestHousieAutoPauseOnClaim:
    def _seed_player_ticket(self, room):
        sm = SocketManager()
        add_player(room, "p1", "Alice")
        sm._start_housie_round(room)
        ticket = room.housie_tickets["Alice"]
        numbers = ticket_numbers(ticket)
        room.housie_called = [
            {"kind": "number", "value": number, "display": str(number), "sort_value": number}
            for number in numbers[:5]
        ]
        room.housie_deck = []  # Avoid starting a background auto task when tests resume.
        room.housie_auto_status = "running"
        return sm, ticket

    @pytest.mark.asyncio
    async def test_valid_claim_pauses_before_acceptance_and_resumes(self):
        room = make_housie_room()
        sm, _ticket = self._seed_player_ticket(room)

        await sm._handle_housie_claim(room, "p1", {"pattern_id": "quick_5"})

        player_ws = room.connections["p1"]
        auto_statuses = [msg["auto_status"] for msg in player_ws.all("BINGO_AUTO_STATUS")]
        assert auto_statuses[:2] == ["paused", "running"]
        assert player_ws.last("BINGO_CLAIM_ACCEPTED") is not None
        assert room.housie_auto_status == "running"

    @pytest.mark.asyncio
    async def test_invalid_claim_pauses_during_validation_then_resumes(self):
        room = make_housie_room()
        sm, _ticket = self._seed_player_ticket(room)
        room.housie_called = room.housie_called[:4]

        await sm._handle_housie_claim(room, "p1", {"pattern_id": "quick_5"})

        player_ws = room.connections["p1"]
        auto_statuses = [msg["auto_status"] for msg in player_ws.all("BINGO_AUTO_STATUS")]
        assert auto_statuses[:2] == ["paused", "running"]
        rejected = player_ws.last("BINGO_CLAIM_REJECTED")
        assert rejected is not None
        assert rejected["reason"] == "not_complete"
        assert rejected["message"] == "Quick 5 is not complete yet. Keep playing!"
        assert room.housie_auto_status == "running"


class TestHousieFinalClaimWindow:
    @pytest.mark.asyncio
    async def test_final_call_keeps_claim_window_open(self):
        room = make_housie_room()
        sm = SocketManager()
        add_player(room, "p1", "Alice")
        sm._start_housie_round(room)
        last_item = room.housie_deck[-1]
        room.housie_deck = [last_item]
        room.housie_auto_status = "running"

        await sm._housie_call_next(room)

        assert room.state == "BINGO_CALLING"
        assert room.housie_deck == []
        assert room.housie_auto_status == "stopped"
        assert room.connections["p1"].last("BINGO_COMPLETE") is None

    @pytest.mark.asyncio
    async def test_terminal_claim_stops_calls_but_allows_same_call_ties(self):
        room = make_housie_room()
        sm = SocketManager()
        add_player(room, "p1", "Alice")
        add_player(room, "p2", "Bob")
        sm._start_housie_round(room)
        alice_ticket = room.housie_tickets["Alice"]
        room.housie_tickets["Bob"] = alice_ticket
        room.housie_called = [
            {"kind": "number", "value": number, "display": str(number), "sort_value": number}
            for number in ticket_numbers(alice_ticket)
        ]
        room.housie_deck = [{"kind": "number", "value": 91, "display": "91", "sort_value": 91}]
        room.housie_auto_status = "running"

        await sm._handle_housie_claim(room, "p1", {"pattern_id": "full_house"})

        assert room.state == "BINGO_CALLING"
        assert room.housie_auto_status == "stopped"
        assert sm._housie_public_state(room)["terminal_claim_pending"] is True
        assert room.connections["p1"].last("BINGO_COMPLETE") is None

        await sm._housie_call_next(room)

        assert room.housie_deck == [{"kind": "number", "value": 91, "display": "91", "sort_value": 91}]

        await sm._handle_housie_claim(room, "p2", {"pattern_id": "full_house"})

        winners = [winner for winner in room.housie_winners if winner["pattern_id"] == "full_house"]
        assert [winner["nickname"] for winner in winners] == ["Alice", "Bob"]
        assert room.connections["p2"].last("BINGO_CLAIM_ACCEPTED") is not None

    @pytest.mark.asyncio
    async def test_same_player_cannot_claim_terminal_twice_on_same_call(self):
        room = make_housie_room()
        sm = SocketManager()
        add_player(room, "p1", "Alice")
        sm._start_housie_round(room)
        ticket = room.housie_tickets["Alice"]
        room.housie_called = [
            {"kind": "number", "value": number, "display": str(number), "sort_value": number}
            for number in ticket_numbers(ticket)
        ]

        await sm._handle_housie_claim(room, "p1", {"pattern_id": "full_house"})
        await sm._handle_housie_claim(room, "p1", {"pattern_id": "full_house"})

        rejected = room.connections["p1"].last("BINGO_CLAIM_REJECTED")
        assert rejected is not None
        assert rejected["reason"] == "already_claimed_by_you"
        assert rejected["message"] == "You already claimed Full House for this call."


class TestHousieUndo:
    @pytest.mark.asyncio
    async def test_undo_pauses_auto_caller_before_rewinding(self):
        room = make_housie_room()
        sm = SocketManager()
        add_player(room, "p1", "Alice")
        sm._start_housie_round(room)
        first_item = room.housie_deck[0]
        await sm._housie_call_next(room)
        room.housie_auto_status = "running"

        await sm._housie_undo_last_call(room)

        assert room.housie_auto_status == "paused"
        assert room.housie_called == []
        assert room.housie_deck[0] == first_item
        assert room.connections["p1"].last("BINGO_AUTO_STATUS")["auto_status"] == "paused"
        sync = room.connections["p1"].last("BINGO_SYNC")
        assert sync is not None
        assert sync["bingo"]["can_undo_last_call"] is False

    @pytest.mark.asyncio
    async def test_blocked_undo_does_not_pause_auto_caller(self):
        room = make_housie_room()
        sm = SocketManager()
        add_player(room, "p1", "Alice")
        sm._start_housie_round(room)
        await sm._housie_call_next(room)
        room.housie_winners.append({"pattern_id": "quick_5", "called_count": 1})
        room.housie_auto_status = "running"

        await sm._housie_undo_last_call(room)

        assert room.housie_auto_status == "running"
        assert len(room.housie_called) == 1
        assert room.connections["p1"].last("BINGO_AUTO_STATUS") is None

    @pytest.mark.asyncio
    async def test_call_and_claim_publish_can_undo_flag(self):
        room = make_housie_room()
        sm = SocketManager()
        add_player(room, "p1", "Alice")
        sm._start_housie_round(room)

        await sm._housie_call_next(room)

        call = room.connections["p1"].last("BINGO_CALL")
        assert call is not None
        assert call["can_undo_last_call"] is True

        room.housie_winners.append({"pattern_id": "quick_5", "called_count": 1})
        sync = sm._housie_public_state(room)
        assert sync["can_undo_last_call"] is False
