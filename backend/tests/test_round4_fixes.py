"""Tests for Round 4 bug fixes: WMLT null statement guard, reset_for_new_game clears,
mlt_engine import cleanup."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from socket_manager import Room


class TestResetForNewGame:
    """reset_for_new_game() should clear all transient state."""

    def _make_room(self):
        game_data = {"statements": [{"id": 1, "text": "test"}]}
        room = Room("ABCDEF", game_data=game_data, game_type="wmlt")
        room.mlt_round_history = [{"round": 1, "votes": {}}]
        room.msg_timestamps = {"client1": [1.0, 2.0]}
        return room

    def test_clears_mlt_round_history(self):
        room = self._make_room()
        assert len(room.mlt_round_history) == 1
        room.reset_for_new_game(
            {"statements": [{"id": 1, "text": "new"}]},
            new_time_limit=20,
        )
        assert room.mlt_round_history == []

    def test_clears_msg_timestamps(self):
        room = self._make_room()
        assert len(room.msg_timestamps) == 1
        room.reset_for_new_game(
            {"statements": [{"id": 1, "text": "new"}]},
            new_time_limit=20,
        )
        assert room.msg_timestamps == {}

    def test_clears_votes(self):
        room = self._make_room()
        room.votes = {"Alice": "Bob"}
        room.reset_for_new_game(
            {"statements": [{"id": 1, "text": "new"}]},
            new_time_limit=20,
        )
        assert room.votes == {}

    def test_resets_scores_and_streaks(self):
        room = self._make_room()
        room.players = {
            "c1": {"nickname": "Alice", "score": 500, "streak": 3, "prev_rank": 1},
        }
        room.connections = {"c1": "mock_ws"}
        room.reset_for_new_game(
            {"statements": [{"id": 1, "text": "new"}]},
            new_time_limit=20,
        )
        assert room.players["c1"]["score"] == 0
        assert room.players["c1"]["streak"] == 0

    def test_removes_stale_players(self):
        room = self._make_room()
        room.players = {
            "c1": {"nickname": "Alice", "score": 0, "streak": 0, "prev_rank": 0},
            "c2": {"nickname": "Bob", "score": 0, "streak": 0, "prev_rank": 0},
        }
        room.connections = {"c1": "mock_ws"}  # c2 not connected
        room.player_tokens = {"Alice": "tok1", "Bob": "tok2"}
        room.reset_for_new_game(
            {"statements": [{"id": 1, "text": "new"}]},
            new_time_limit=20,
        )
        assert "c1" in room.players
        assert "c2" not in room.players
        assert "Bob" not in room.player_tokens


class TestWMLTNullStatementGuard:
    """start_question should not broadcast if WMLT statement is None."""

    def test_current_round_data_returns_none_for_out_of_bounds(self):
        game_data = {"statements": [{"id": 1, "text": "test"}]}
        room = Room("XYZXYZ", game_data=game_data, game_type="wmlt")
        room.current_question_index = 99  # out of bounds
        assert room.current_round_data() is None

    def test_current_round_data_returns_statement(self):
        game_data = {"statements": [{"id": 1, "text": "test"}]}
        room = Room("XYZXYZ", game_data=game_data, game_type="wmlt")
        room.current_question_index = 0
        data = room.current_round_data()
        assert data is not None
        assert data["text"] == "test"


class TestMLTEngineImport:
    """MLTEngine should use proper datetime import."""

    def test_daily_limit_check_works(self):
        from mlt_engine import MLTEngine
        engine = MLTEngine()
        # Should not raise — datetime import works
        result = engine._check_daily_limit()
        assert isinstance(result, bool)
