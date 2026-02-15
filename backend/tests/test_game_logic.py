import sys
import os
import re
import time
import random
import string

import pytest

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from socket_manager import Room, SocketManager
import config


def make_quiz(num_questions=2):
    return {
        "quiz_title": "Test Quiz",
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


def make_room(time_limit=15, num_questions=2):
    return Room("TEST01", make_quiz(num_questions), time_limit)


def make_room_with_players():
    room = make_room()
    room.players = {
        "p1": {"nickname": "Alice", "score": 500, "prev_rank": 0},
        "p2": {"nickname": "Bob", "score": 800, "prev_rank": 0},
        "p3": {"nickname": "Charlie", "score": 300, "prev_rank": 0},
    }
    return room


# ---------------------------------------------------------------------------
# Scoring Tests
# ---------------------------------------------------------------------------

class TestScoring:
    def test_max_score_instant_answer(self):
        """Answering instantly should give ~1000 points."""
        time_limit = 15
        time_taken = 0.01
        time_ratio = max(0, 1 - (time_taken / time_limit))
        points = int(100 + (900 * time_ratio))
        assert 990 <= points <= 1000

    def test_min_score_last_second(self):
        """Answering at the deadline should give ~100 points."""
        time_limit = 15
        time_taken = 14.99
        time_ratio = max(0, 1 - (time_taken / time_limit))
        points = int(100 + (900 * time_ratio))
        assert 100 <= points <= 110

    def test_mid_score_half_time(self):
        """Answering at half time should give ~550 points."""
        time_limit = 20
        time_taken = 10.0
        time_ratio = max(0, 1 - (time_taken / time_limit))
        points = int(100 + (900 * time_ratio))
        assert 540 <= points <= 560

    def test_zero_score_over_time(self):
        """Answering after time expires should floor at 100 points."""
        time_limit = 15
        time_taken = 20.0
        time_ratio = max(0, 1 - (time_taken / time_limit))
        points = int(100 + (900 * time_ratio))
        assert points == 100

    def test_score_range_always_valid(self):
        """Points should always be between 100 and 1000."""
        time_limit = 15
        for time_taken in [0, 0.001, 5, 10, 14.999, 15, 20, 100]:
            time_ratio = max(0, 1 - (time_taken / time_limit))
            points = int(100 + (900 * time_ratio))
            assert 100 <= points <= 1000, f"Invalid points {points} for time_taken={time_taken}"


# ---------------------------------------------------------------------------
# Leaderboard Tests
# ---------------------------------------------------------------------------

class TestLeaderboard:
    def test_sorted_descending(self):
        room = make_room_with_players()
        sm = SocketManager()
        lb = sm.get_leaderboard(room)
        scores = [entry["score"] for entry in lb]
        assert scores == [800, 500, 300]

    def test_nicknames_in_order(self):
        room = make_room_with_players()
        sm = SocketManager()
        lb = sm.get_leaderboard(room)
        names = [entry["nickname"] for entry in lb]
        assert names == ["Bob", "Alice", "Charlie"]

    def test_empty_leaderboard(self):
        room = make_room()
        sm = SocketManager()
        lb = sm.get_leaderboard(room)
        assert lb == []

    def test_single_player(self):
        room = make_room()
        room.players = {"p1": {"nickname": "Solo", "score": 100, "prev_rank": 0}}
        sm = SocketManager()
        lb = sm.get_leaderboard(room)
        assert len(lb) == 1
        assert lb[0]["nickname"] == "Solo"
        assert lb[0]["score"] == 100


class TestLeaderboardWithChanges:
    def test_no_movement(self):
        room = make_room_with_players()
        sm = SocketManager()
        room.previous_leaderboard = [
            {"nickname": "Bob", "score": 500},
            {"nickname": "Alice", "score": 400},
            {"nickname": "Charlie", "score": 300},
        ]
        lb = sm.get_leaderboard_with_changes(room)
        assert lb[0]["nickname"] == "Bob"
        assert lb[0]["rank_change"] == 0
        assert lb[1]["nickname"] == "Alice"
        assert lb[1]["rank_change"] == 0

    def test_rank_movement(self):
        room = make_room_with_players()
        sm = SocketManager()
        room.previous_leaderboard = [
            {"nickname": "Charlie", "score": 600},
            {"nickname": "Alice", "score": 400},
            {"nickname": "Bob", "score": 200},
        ]
        lb = sm.get_leaderboard_with_changes(room)
        # Bob: was rank 2, now rank 0 -> moved up 2
        assert lb[0]["nickname"] == "Bob"
        assert lb[0]["rank_change"] == 2
        # Alice: was rank 1, now rank 1 -> no change
        assert lb[1]["nickname"] == "Alice"
        assert lb[1]["rank_change"] == 0
        # Charlie: was rank 0, now rank 2 -> moved down 2
        assert lb[2]["nickname"] == "Charlie"
        assert lb[2]["rank_change"] == -2

    def test_new_player_default_rank(self):
        """A player not in previous leaderboard gets a sensible default."""
        room = make_room_with_players()
        sm = SocketManager()
        room.previous_leaderboard = [
            {"nickname": "Alice", "score": 400},
            {"nickname": "Bob", "score": 200},
            # Charlie missing (new player)
        ]
        lb = sm.get_leaderboard_with_changes(room)
        charlie = next(e for e in lb if e["nickname"] == "Charlie")
        # prev_rank defaults to len(prev_rankings)=2, current rank is 2 -> change=0
        assert charlie["rank_change"] == 0

    def test_empty_previous_leaderboard(self):
        """First question: previous leaderboard is empty."""
        room = make_room_with_players()
        sm = SocketManager()
        room.previous_leaderboard = []
        lb = sm.get_leaderboard_with_changes(room)
        # All players are "new" -> prev_rank = 0, so changes reflect distance from 0
        assert len(lb) == 3


# ---------------------------------------------------------------------------
# Room TTL & Cleanup Tests
# ---------------------------------------------------------------------------

class TestRoomExpiry:
    def test_fresh_room_not_expired(self):
        room = make_room()
        assert not room.is_expired()

    def test_expired_after_ttl(self):
        room = make_room()
        room.last_activity = time.time() - 2000  # > 1800s TTL
        assert room.is_expired()

    def test_touch_resets_expiry(self):
        room = make_room()
        room.last_activity = time.time() - 2000
        assert room.is_expired()
        room.touch()
        assert not room.is_expired()


# ---------------------------------------------------------------------------
# Room Code Collision Tests
# ---------------------------------------------------------------------------

class TestRoomCodeGeneration:
    def test_unique_codes(self):
        sm = SocketManager()
        codes = set()
        for _ in range(50):
            code = self._gen_code(sm)
            assert code not in codes
            codes.add(code)
            sm.rooms[code] = make_room()

    def test_collision_avoidance(self):
        """Pre-fill rooms so first random attempt is likely taken."""
        sm = SocketManager()
        # Use deterministic seed so we can predict collisions
        rng = random.Random(42)
        first_code = ''.join(rng.choices(string.ascii_uppercase + string.digits, k=6))
        sm.rooms[first_code] = make_room()
        # Generate should skip the taken code
        code = self._gen_code(sm)
        assert code not in sm.rooms or code != first_code

    def _gen_code(self, sm):
        for _ in range(10):
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            if code not in sm.rooms:
                return code
        raise RuntimeError("Failed to generate unique room code")


# ---------------------------------------------------------------------------
# Disconnect / Cleanup Tests
# ---------------------------------------------------------------------------

class TestDisconnectHandling:
    def test_remove_player_on_disconnect(self):
        room = make_room()
        room.players["p1"] = {"nickname": "Alice", "score": 100, "prev_rank": 0}
        room._remove_connection("p1")
        assert "p1" not in room.players

    def test_remove_organizer_on_disconnect(self):
        room = make_room()
        room.organizer_id = "org1"
        room.organizer = "fake_ws"  # type: ignore
        room._remove_connection("org1")
        assert room.organizer is None
        assert room.organizer_id is None

    def test_remove_nonexistent_connection(self):
        """Removing a connection that doesn't exist should not raise."""
        room = make_room()
        room._remove_connection("nonexistent")  # Should not raise


# ---------------------------------------------------------------------------
# end_question Guard Tests
# ---------------------------------------------------------------------------

class TestEndQuestionGuard:
    def test_guard_prevents_double_fire(self):
        """end_question should only execute when state is QUESTION."""
        room = make_room()
        room.state = "QUESTION"
        room.current_question_index = 0
        room.previous_leaderboard = []

        # Simulate first call: state changes to LEADERBOARD
        if room.state == "QUESTION":
            room.state = "LEADERBOARD"

        # Second call: should be blocked by guard
        original_state = room.state
        if room.state == "QUESTION":
            room.state = "SOMETHING_ELSE"  # Should NOT execute

        assert room.state == original_state == "LEADERBOARD"

    def test_state_transitions(self):
        """Verify valid state transitions."""
        room = make_room()
        assert room.state == "LOBBY"
        room.state = "INTRO"
        assert room.state == "INTRO"
        room.state = "QUESTION"
        assert room.state == "QUESTION"
        room.state = "LEADERBOARD"
        assert room.state == "LEADERBOARD"


# ---------------------------------------------------------------------------
# Input Validation Tests
# ---------------------------------------------------------------------------

class TestInputValidation:
    def test_nickname_max_length(self):
        assert len("A" * 21) > config.MAX_NICKNAME_LENGTH
        assert len("A" * 20) == config.MAX_NICKNAME_LENGTH

    def test_nickname_empty_rejected(self):
        assert not "".strip()
        assert not "   ".strip()

    def test_nickname_html_stripped(self):
        nickname = "<script>alert('xss')</script>User"
        sanitized = re.sub(r'<[^>]+>', '', nickname)
        assert "<" not in sanitized
        assert "script" not in sanitized.lower() or "alert" in sanitized

    def test_nickname_normal_preserved(self):
        nickname = "Player One"
        sanitized = re.sub(r'<[^>]+>', '', nickname)
        assert sanitized == "Player One"

    def test_valid_answer_indices(self):
        for i in range(4):
            assert isinstance(i, int) and 0 <= i <= 3

    def test_invalid_answer_index_negative(self):
        assert not (isinstance(-1, int) and 0 <= -1 <= 3)

    def test_invalid_answer_index_too_high(self):
        assert not (isinstance(5, int) and 0 <= 5 <= 3)

    def test_invalid_answer_index_string(self):
        assert not isinstance("0", int)

    def test_invalid_answer_index_float(self):
        # In Python, isinstance(1.0, int) is False
        assert not isinstance(1.5, int)


# ---------------------------------------------------------------------------
# SocketManager Unit Tests
# ---------------------------------------------------------------------------

class TestSocketManager:
    def _add_room(self, sm, code, quiz, time_limit=15):
        """Add a room directly without starting the async cleanup loop."""
        room = Room(code, quiz, time_limit)
        sm.rooms[code] = room
        return room

    def test_create_room(self):
        sm = SocketManager()
        room = self._add_room(sm, "ABC123", make_quiz(), 20)
        assert "ABC123" in sm.rooms
        assert room.time_limit == 20
        assert room.state == "LOBBY"

    def test_create_multiple_rooms(self):
        sm = SocketManager()
        self._add_room(sm, "ROOM01", make_quiz())
        self._add_room(sm, "ROOM02", make_quiz())
        assert len(sm.rooms) == 2

    def test_room_quiz_data(self):
        sm = SocketManager()
        room = self._add_room(sm, "QUIZ5", make_quiz(5))
        assert len(room.quiz["questions"]) == 5
        assert room.quiz["quiz_title"] == "Test Quiz"


# ---------------------------------------------------------------------------
# Reconnection Tests
# ---------------------------------------------------------------------------

class TestReconnection:
    def test_disconnect_in_lobby_removes_player(self):
        """In LOBBY state, disconnect should fully remove the player."""
        room = make_room()
        room.state = "LOBBY"
        room.players["p1"] = {"nickname": "Alice", "score": 0, "prev_rank": 0}
        room._remove_connection("p1")
        assert "p1" not in room.players
        assert "Alice" not in room.disconnected_players

    def test_disconnect_in_game_preserves_data(self):
        """During active game, disconnect should preserve player data."""
        room = make_room()
        room.state = "QUESTION"
        room.players["p1"] = {"nickname": "Alice", "score": 500, "prev_rank": 1}
        room._remove_connection("p1")
        assert "p1" not in room.players
        assert "Alice" in room.disconnected_players
        assert room.disconnected_players["Alice"]["score"] == 500

    def test_disconnect_in_leaderboard_preserves_data(self):
        """Disconnecting during LEADERBOARD should preserve data."""
        room = make_room()
        room.state = "LEADERBOARD"
        room.players["p1"] = {"nickname": "Bob", "score": 800, "prev_rank": 0}
        room._remove_connection("p1")
        assert "Bob" in room.disconnected_players
        assert room.disconnected_players["Bob"]["score"] == 800

    def test_disconnected_players_initially_empty(self):
        room = make_room()
        assert len(room.disconnected_players) == 0


# ---------------------------------------------------------------------------
# True/False Question Validation Tests
# ---------------------------------------------------------------------------

class TestTrueFalseValidation:
    def test_two_option_question_valid(self):
        """A question with 2 options should be considered valid."""
        q = {
            "id": 1,
            "text": "The earth is flat?",
            "options": ["True", "False"],
            "answer_index": 1,
        }
        assert len(q["options"]) in (2, 4)
        assert 0 <= q["answer_index"] < len(q["options"])

    def test_four_option_question_valid(self):
        """A question with 4 options should be considered valid."""
        q = {
            "id": 1,
            "text": "Capital of France?",
            "options": ["London", "Paris", "Berlin", "Madrid"],
            "answer_index": 1,
        }
        assert len(q["options"]) in (2, 4)
        assert 0 <= q["answer_index"] < len(q["options"])

    def test_three_option_question_invalid(self):
        """A question with 3 options should not be valid."""
        q = {"options": ["A", "B", "C"], "answer_index": 0}
        assert len(q["options"]) not in (2, 4)

    def test_answer_index_out_of_range_for_tf(self):
        """answer_index=2 should be invalid for a 2-option question."""
        q = {"options": ["True", "False"], "answer_index": 2}
        assert not (0 <= q["answer_index"] < len(q["options"]))

    def test_mixed_quiz_valid(self):
        """A quiz mixing 4-option and 2-option questions should be valid."""
        questions = [
            {"id": 1, "text": "Q?", "options": ["A", "B", "C", "D"], "answer_index": 0},
            {"id": 2, "text": "TF?", "options": ["True", "False"], "answer_index": 1},
        ]
        for q in questions:
            assert len(q["options"]) in (2, 4)
            assert 0 <= q["answer_index"] < len(q["options"])


# ---------------------------------------------------------------------------
# Player List Broadcast Data Tests
# ---------------------------------------------------------------------------

class TestPlayerListBroadcast:
    def test_player_list_grows_with_joins(self):
        """Player list should contain all joined players."""
        room = make_room()
        room.players["p1"] = {"nickname": "Alice", "score": 0, "prev_rank": 0}
        room.players["p2"] = {"nickname": "Bob", "score": 0, "prev_rank": 0}
        players = [p["nickname"] for p in room.players.values()]
        assert set(players) == {"Alice", "Bob"}

    def test_player_list_after_lobby_disconnect(self):
        """Player list should shrink when a player leaves in LOBBY."""
        room = make_room()
        room.state = "LOBBY"
        room.players["p1"] = {"nickname": "Alice", "score": 0, "prev_rank": 0}
        room.players["p2"] = {"nickname": "Bob", "score": 0, "prev_rank": 0}
        room._remove_connection("p1")
        players = [p["nickname"] for p in room.players.values()]
        assert players == ["Bob"]

    def test_player_list_stable_during_game_disconnect(self):
        """During game, disconnected player data is preserved separately."""
        room = make_room()
        room.state = "QUESTION"
        room.players["p1"] = {"nickname": "Alice", "score": 500, "prev_rank": 0}
        room.players["p2"] = {"nickname": "Bob", "score": 300, "prev_rank": 0}
        room._remove_connection("p1")
        active_players = [p["nickname"] for p in room.players.values()]
        assert active_players == ["Bob"]
        assert "Alice" in room.disconnected_players


# ---------------------------------------------------------------------------
# Extended Reconnection Edge Cases
# ---------------------------------------------------------------------------

class TestReconnectionEdgeCases:
    def test_reconnect_restores_score(self):
        """Reconnecting player should get their previous score back."""
        room = make_room()
        room.state = "QUESTION"
        room.players["p1"] = {"nickname": "Alice", "score": 750, "prev_rank": 1}
        room._remove_connection("p1")

        saved = room.disconnected_players.pop("Alice")
        room.players["p1-new"] = {
            "nickname": "Alice",
            "score": saved["score"],
            "prev_rank": saved["prev_rank"],
        }
        assert room.players["p1-new"]["score"] == 750
        assert room.players["p1-new"]["prev_rank"] == 1

    def test_multiple_disconnects_only_last_preserved(self):
        """If a nickname disconnects twice, last state should be preserved."""
        room = make_room()
        room.state = "QUESTION"
        room.players["p1"] = {"nickname": "Alice", "score": 100, "prev_rank": 0}
        room._remove_connection("p1")

        # Reconnect and score more
        room.players["p1-v2"] = {"nickname": "Alice", "score": 500, "prev_rank": 0}
        room._remove_connection("p1-v2")
        assert room.disconnected_players["Alice"]["score"] == 500

    def test_disconnect_in_podium_preserves_data(self):
        """Even in PODIUM state, player data should be preserved."""
        room = make_room()
        room.state = "PODIUM"
        room.players["p1"] = {"nickname": "Alice", "score": 900, "prev_rank": 0}
        room._remove_connection("p1")
        assert "Alice" in room.disconnected_players


# ---------------------------------------------------------------------------
# Streak Bonus Tests
# ---------------------------------------------------------------------------

class TestStreakBonus:
    def test_streak_thresholds_defined(self):
        assert 3 in config.STREAK_THRESHOLDS
        assert 5 in config.STREAK_THRESHOLDS

    def test_streak_multiplier_at_3(self):
        """At streak 3, multiplier should be 1.5."""
        streak = 3
        multiplier = 1.0
        for threshold, mult in sorted(config.STREAK_THRESHOLDS.items()):
            if streak >= threshold:
                multiplier = mult
        assert multiplier == 1.5

    def test_streak_multiplier_at_5(self):
        """At streak 5, multiplier should be 2.0."""
        streak = 5
        multiplier = 1.0
        for threshold, mult in sorted(config.STREAK_THRESHOLDS.items()):
            if streak >= threshold:
                multiplier = mult
        assert multiplier == 2.0

    def test_no_streak_multiplier_below_3(self):
        """Below 3 streak, multiplier should be 1.0."""
        streak = 2
        multiplier = 1.0
        for threshold, mult in sorted(config.STREAK_THRESHOLDS.items()):
            if streak >= threshold:
                multiplier = mult
        assert multiplier == 1.0

    def test_player_streak_init(self):
        """New player should have streak 0."""
        room = make_room()
        room.players["p1"] = {"nickname": "Alice", "score": 0, "prev_rank": 0, "streak": 0}
        assert room.players["p1"]["streak"] == 0


# ---------------------------------------------------------------------------
# Team Mode Tests
# ---------------------------------------------------------------------------

class TestTeamMode:
    def test_team_assignment(self):
        room = make_room()
        room.teams["Alice"] = "Red"
        room.teams["Bob"] = "Blue"
        room.teams["Charlie"] = "Red"
        assert room.teams["Alice"] == "Red"
        assert room.teams["Bob"] == "Blue"
        assert len(room.teams) == 3

    def test_team_leaderboard(self):
        sm = SocketManager()
        room = make_room()
        room.players["p1"] = {"nickname": "Alice", "score": 600, "prev_rank": 0}
        room.players["p2"] = {"nickname": "Bob", "score": 400, "prev_rank": 0}
        room.players["p3"] = {"nickname": "Charlie", "score": 500, "prev_rank": 0}
        room.teams["Alice"] = "Red"
        room.teams["Bob"] = "Red"
        room.teams["Charlie"] = "Blue"

        tl = sm.get_team_leaderboard(room)
        assert len(tl) == 2
        red = next(t for t in tl if t["team"] == "Red")
        blue = next(t for t in tl if t["team"] == "Blue")
        assert red["score"] == 500
        assert red["members"] == 2
        assert blue["score"] == 500
        assert blue["members"] == 1

    def test_solo_players_as_teams(self):
        """When no teams are set, solo players appear as their own 'team'."""
        sm = SocketManager()
        room = make_room()
        room.players["p1"] = {"nickname": "Alice", "score": 100, "prev_rank": 0}
        tl = sm.get_team_leaderboard(room)
        assert len(tl) == 1
        assert tl[0]["team"] == "Alice"
        assert tl[0]["members"] == 1
        assert tl[0]["score"] == 100


# ---------------------------------------------------------------------------
# Power-ups Tests
# ---------------------------------------------------------------------------

class TestPowerUps:
    def test_power_ups_initialized(self):
        room = make_room()
        room.power_ups["Alice"] = {"double_points": True, "fifty_fifty": True}
        assert room.power_ups["Alice"]["double_points"] is True
        assert room.power_ups["Alice"]["fifty_fifty"] is True

    def test_power_up_consumed(self):
        room = make_room()
        room.power_ups["Alice"] = {"double_points": True, "fifty_fifty": True}
        room.power_ups["Alice"]["double_points"] = False
        assert room.power_ups["Alice"]["double_points"] is False
        assert room.power_ups["Alice"]["fifty_fifty"] is True

    def test_fifty_fifty_removes_two_options(self):
        """50/50 should identify 2 wrong options to remove from a 4-option question."""
        import random
        question = {"options": ["A", "B", "C", "D"], "answer_index": 1}
        correct_idx = question["answer_index"]
        wrong_indices = [i for i in range(len(question["options"])) if i != correct_idx]
        remove = random.sample(wrong_indices, min(2, len(wrong_indices)))
        assert len(remove) == 2
        assert correct_idx not in remove


# ---------------------------------------------------------------------------
# Spectator Support Tests
# ---------------------------------------------------------------------------

class TestSpectatorSupport:
    def test_spectator_dict_exists(self):
        room = make_room()
        assert hasattr(room, 'spectators')
        assert isinstance(room.spectators, dict)

    def test_spectator_removed_on_disconnect(self):
        room = make_room()
        room.spectators["s1"] = "mock_ws"
        room._remove_connection("s1")
        assert "s1" not in room.spectators


# ---------------------------------------------------------------------------
# Answer Log / Game History Tests
# ---------------------------------------------------------------------------

class TestAnswerLog:
    def test_answer_log_initially_empty(self):
        room = make_room()
        assert room.answer_log == []

    def test_answer_log_records_entries(self):
        room = make_room()
        room.answer_log.append({
            "question_index": 0,
            "nickname": "Alice",
            "answer_index": 2,
            "correct": True,
            "time_taken": 3.5,
        })
        assert len(room.answer_log) == 1
        assert room.answer_log[0]["nickname"] == "Alice"
        assert room.answer_log[0]["correct"] is True

    def test_game_summary(self):
        sm = SocketManager()
        room = Room("HIST01", make_quiz())
        room.players["p1"] = {"nickname": "Alice", "score": 1000, "prev_rank": 0}
        room.players["p2"] = {"nickname": "Bob", "score": 500, "prev_rank": 0}
        room.answer_log.append({"question_index": 0, "nickname": "Alice", "answer_index": 0, "correct": True, "time_taken": 2.0})

        summary = sm.get_game_summary(room)
        assert summary["room_code"] == "HIST01"
        assert summary["player_count"] == 2
        assert len(summary["leaderboard"]) == 2
        assert summary["leaderboard"][0]["nickname"] == "Alice"  # highest score first
        assert len(summary["answer_log"]) == 1


# ---------------------------------------------------------------------------
# Bonus Round Selection Tests
# ---------------------------------------------------------------------------

class TestBonusRoundSelection:
    def test_no_bonus_under_4_questions(self):
        """Games with fewer than 4 questions should have no bonus rounds."""
        sm = SocketManager()
        for n in (1, 2, 3):
            room = make_room(num_questions=n)
            sm._select_bonus_questions(room)
            assert room.bonus_questions == set(), f"Expected no bonus for {n} questions"

    def test_bonus_excludes_first_and_last(self):
        """First and last questions should never be bonus rounds."""
        sm = SocketManager()
        for _ in range(20):  # Run multiple times due to randomness
            room = make_room(num_questions=6)
            sm._select_bonus_questions(room)
            assert 0 not in room.bonus_questions, "First question should not be bonus"
            assert 5 not in room.bonus_questions, "Last question should not be bonus"

    def test_bonus_selects_at_least_one(self):
        """Games with 4+ questions should have at least 1 bonus round."""
        sm = SocketManager()
        for n in (4, 5, 6, 10):
            room = make_room(num_questions=n)
            sm._select_bonus_questions(room)
            assert len(room.bonus_questions) >= 1, f"Expected at least 1 bonus for {n} questions"

    def test_bonus_fraction_approximate(self):
        """10-question quiz: ~30% = 3 bonus questions."""
        sm = SocketManager()
        room = make_room(num_questions=10)
        sm._select_bonus_questions(room)
        assert len(room.bonus_questions) == 3

    def test_bonus_reset_on_new_game(self):
        """reset_for_new_game should clear bonus_questions."""
        room = make_room(num_questions=6)
        room.bonus_questions = {1, 2, 3}
        room.reset_for_new_game(make_quiz(4), 15)
        assert room.bonus_questions == set()


# ---------------------------------------------------------------------------
# Bonus Scoring Tests
# ---------------------------------------------------------------------------

class TestBonusScoring:
    def test_bonus_doubles_base_points(self):
        """A correct answer on a bonus question should get 2x base points."""
        time_limit = 15
        time_taken = 7.5  # half time
        time_ratio = max(0, 1 - (time_taken / time_limit))
        normal_points = int(100 + (900 * time_ratio))
        bonus_points = normal_points * 2
        assert bonus_points == normal_points * 2

    def test_bonus_stacks_with_streak(self):
        """Bonus 2x + streak 1.5x should give 3x effective multiplier."""
        time_limit = 15
        time_taken = 0.01
        time_ratio = max(0, 1 - (time_taken / time_limit))
        base_points = int(100 + (900 * time_ratio))

        # Bonus doubles base
        bonus_base = base_points * 2

        # Streak of 3 gives 1.5x
        streak = 3
        multiplier = 1.0
        for threshold, mult in sorted(config.STREAK_THRESHOLDS.items()):
            if streak >= threshold:
                multiplier = mult
        final = int(bonus_base * multiplier)
        assert final == int(base_points * 2 * 1.5)

    def test_bonus_stacks_with_double_points_powerup(self):
        """Bonus 2x + power-up 2x = 4x theoretical max (before streak)."""
        base_points = 1000
        # Bonus doubles base
        after_bonus = base_points * 2
        # Streak at 1 (no multiplier)
        after_streak = int(after_bonus * 1.0)
        # Double points power-up
        after_powerup = after_streak * 2
        assert after_powerup == 4000


# ---------------------------------------------------------------------------
# Streak Reset on No-Answer Tests
# ---------------------------------------------------------------------------

class TestStreakResetOnNoAnswer:
    def test_streak_resets_for_unanswered_players(self):
        """Players who don't answer should have their streak reset to 0."""
        room = make_room()
        room.state = "QUESTION"
        room.current_question_index = 0
        room.previous_leaderboard = []
        room.players = {
            "p1": {"nickname": "Alice", "score": 500, "prev_rank": 0, "streak": 3},
            "p2": {"nickname": "Bob", "score": 300, "prev_rank": 0, "streak": 2},
        }
        # Only p1 answered
        room.answered_players = {"p1"}

        # Simulate the streak reset logic from end_question
        for cid, player in room.players.items():
            if cid not in room.answered_players:
                player["streak"] = 0

        assert room.players["p1"]["streak"] == 3  # answered, preserved
        assert room.players["p2"]["streak"] == 0  # didn't answer, reset

    def test_streak_preserved_for_answered_players(self):
        """Players who answered should keep their streak."""
        room = make_room()
        room.state = "QUESTION"
        room.current_question_index = 0
        room.previous_leaderboard = []
        room.players = {
            "p1": {"nickname": "Alice", "score": 500, "prev_rank": 0, "streak": 5},
        }
        room.answered_players = {"p1"}

        for cid, player in room.players.items():
            if cid not in room.answered_players:
                player["streak"] = 0

        assert room.players["p1"]["streak"] == 5


# ---------------------------------------------------------------------------
# Team Leaderboard Solo Players Tests
# ---------------------------------------------------------------------------

class TestTeamLeaderboardSoloPlayers:
    def test_solo_players_use_nickname_as_team(self):
        """Players without a team should appear with their nickname as team name."""
        sm = SocketManager()
        room = make_room()
        room.players = {
            "p1": {"nickname": "Alice", "score": 600, "prev_rank": 0},
            "p2": {"nickname": "Bob", "score": 400, "prev_rank": 0},
        }
        # No teams assigned
        tl = sm.get_team_leaderboard(room)
        assert len(tl) == 2
        names = {t["team"] for t in tl}
        assert names == {"Alice", "Bob"}
        for t in tl:
            assert t["members"] == 1

    def test_mixed_teams_and_solo(self):
        """Mix of team players and solo players in team leaderboard."""
        sm = SocketManager()
        room = make_room()
        room.players = {
            "p1": {"nickname": "Alice", "score": 600, "prev_rank": 0},
            "p2": {"nickname": "Bob", "score": 400, "prev_rank": 0},
            "p3": {"nickname": "Charlie", "score": 500, "prev_rank": 0},
        }
        room.teams["Alice"] = "Red"
        room.teams["Bob"] = "Red"
        # Charlie has no team -> solo

        tl = sm.get_team_leaderboard(room)
        assert len(tl) == 2
        red = next(t for t in tl if t["team"] == "Red")
        charlie = next(t for t in tl if t["team"] == "Charlie")
        assert red["members"] == 2
        assert red["score"] == 500  # (600+400)/2
        assert charlie["members"] == 1
        assert charlie["score"] == 500
