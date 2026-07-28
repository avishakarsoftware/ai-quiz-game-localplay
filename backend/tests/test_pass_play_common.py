"""Shared pass-and-play mechanics (SPEC-PASS-AND-PLAY §1)."""
import pass_play_common as pp


class TestSeatRoster:
    def test_builds_seats_from_host_typed_names(self):
        seats = pp.build_seats(["Maya", "Leo", "Ada"])
        assert [s["id"] for s in seats] == ["s0", "s1", "s2"]
        assert [s["name"] for s in seats] == ["Maya", "Leo", "Ada"]

    def test_blank_names_get_a_positional_label_not_an_empty_string(self):
        """An empty label renders a pass screen reading "Pass the phone to" with nothing after
        it — the one screen in the game that must never be ambiguous."""
        seats = pp.build_seats(["Maya", "   ", ""])
        assert seats[1]["name"] == "Player 2"
        assert seats[2]["name"] == "Player 3"

    def test_duplicate_names_are_allowed_because_ids_are_the_key(self):
        # Two guests really can both be "Sam"; the id disambiguates, not the name.
        seats = pp.build_seats(["Sam", "Sam"])
        assert seats[0]["id"] != seats[1]["id"]

    def test_roster_is_capped_and_junk_input_never_raises(self):
        assert len(pp.build_seats([f"P{i}" for i in range(50)])) == pp.MAX_SEATS
        assert pp.build_seats(None) == []
        assert pp.build_seats("not a list") == []
        assert pp.build_seats([{"weird": 1}, 42]) != []      # coerced, not crashed

    def test_names_are_sanitised(self):
        seats = pp.build_seats(["<script>bad</script>Maya"])
        assert "<" not in seats[0]["name"]

    def test_min_and_max_seats_gate_the_start(self):
        assert pp.can_start(pp.build_seats(["a", "b"])) is False       # 2 is too few
        assert pp.can_start(pp.build_seats(["a", "b", "c"])) is True
        assert pp.can_start([]) is False
        assert pp.can_start("nope") is False


class TestTurnOrder:
    def _turn(self, n=3):
        return pp.create_turn_order(pp.build_seats([f"P{i}" for i in range(n)]))

    def test_starts_at_the_first_seat(self):
        assert pp.current_turn(self._turn()) == "s0"

    def test_advances_and_counts_completed_rounds_on_wrap(self):
        t = self._turn(3)
        assert pp.rounds_completed(t) == 0
        pp.advance_turn(t); assert pp.current_turn(t) == "s1"
        pp.advance_turn(t); assert pp.current_turn(t) == "s2"
        pp.advance_turn(t)
        assert pp.current_turn(t) == "s0"
        assert pp.rounds_completed(t) == 1

    def test_removing_the_current_seat_hands_the_turn_on_without_skipping_anyone(self):
        """The bug this guards: with an integer index, removing the current seat silently shifts
        everyone after it, so a player loses their turn and it looks like a UI glitch."""
        t = self._turn(4)
        pp.advance_turn(t)                       # current = s1
        pp.remove_from_turn_order(t, "s1")
        assert pp.current_turn(t) == "s2"        # s2 gets it — nobody skipped
        assert t["order"] == ["s0", "s2", "s3"]

    def test_removing_the_last_seat_while_current_wraps_to_the_start(self):
        t = self._turn(3)
        pp.advance_turn(t); pp.advance_turn(t)   # current = s2 (last)
        pp.remove_from_turn_order(t, "s2")
        assert pp.current_turn(t) == "s0"

    def test_removing_a_non_current_seat_leaves_the_turn_alone(self):
        t = self._turn(3)
        pp.advance_turn(t)                       # current = s1
        pp.remove_from_turn_order(t, "s0")
        assert pp.current_turn(t) == "s1"

    def test_removing_everyone_leaves_no_current_seat(self):
        t = self._turn(2)
        for sid in ("s0", "s1"):
            pp.remove_from_turn_order(t, sid)
        assert pp.current_turn(t) == ""

    def test_a_vanished_current_seat_restarts_rather_than_stalling(self):
        t = self._turn(3)
        t["current"] = "ghost"
        pp.advance_turn(t)
        assert pp.current_turn(t) == "s0"

    def test_latecomer_joins_the_end_of_the_rotation(self):
        t = self._turn(2)
        pp.insert_into_turn_order(t, "s9")
        assert t["order"] == ["s0", "s1", "s9"]

    def test_inserting_into_an_empty_rotation_gives_that_seat_the_turn(self):
        t = {"order": [], "current": "", "completed_rounds": 0}
        pp.insert_into_turn_order(t, "s0")
        assert pp.current_turn(t) == "s0"


class TestVoteTallying:
    def test_counts_votes_per_accused(self):
        assert pp.tally_votes({"s0": "s2", "s1": "s2", "s2": "s0"}) == {"s2": 2, "s0": 1}

    def test_strict_majority_requires_more_than_half(self):
        # 3 of 5 is a majority; 2 of 5 is not.
        assert pp.strict_majority({"s1": 3}, 5) == "s1"
        assert pp.strict_majority({"s1": 2, "s2": 1}, 5) == ""

    def test_exactly_half_is_not_a_majority(self):
        assert pp.strict_majority({"s1": 2}, 4) == ""

    def test_a_tie_convicts_nobody(self):
        """Plurality convictions feel arbitrary to everyone who didn't vote for them, so a split
        table means the impostor survives."""
        assert pp.strict_majority({"s1": 2, "s2": 2}, 4) == ""

    def test_empty_and_degenerate_inputs(self):
        assert pp.strict_majority({}, 5) == ""
        assert pp.strict_majority({"s1": 1}, 0) == ""
