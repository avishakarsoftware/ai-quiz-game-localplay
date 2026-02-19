"""
Unit tests for socket_manager.py — Room class and SocketManager methods.
Uses mock WebSockets to test state guards, disconnect handling,
reconnection logic, spectator sync, and bonus round mechanics.
"""
import sys
import os
import asyncio
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from socket_manager import Room, SocketManager
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
    return Room("UNIT01", make_quiz(num_questions), time_limit, organizer_token=token)


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
        await sm.handle_message(room, "org-1", {
            "type": "RESET_ROOM", "quiz_data": new_quiz, "time_limit": 20
        }, is_organizer=True)
        assert room.state == "LOBBY"
        assert len(room.quiz["questions"]) == 3

    @pytest.mark.asyncio
    async def test_reset_room_rejects_invalid_quiz(self):
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        room.state = "PODIUM"
        await sm.handle_message(room, "org-1", {
            "type": "RESET_ROOM", "quiz_data": {"bad": "data"}, "time_limit": 20
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
