"""Impostor — the pass-and-play secret-word game (SPEC-PASS-AND-PLAY §2)."""
import random

import impostor_engine as imp
import pass_play_common as pp


def _seats(n=4):
    return pp.build_seats([f"P{i}" for i in range(n)])


def _state(n=4, seed=1, **cfg):
    return imp.create_initial_state(_seats(n), cfg or None, rng=random.Random(seed))


def _reveal_all(state):
    for sid in pp.seat_ids(state["seats"]):
        imp.mark_revealed(state, sid)
    return state


def _run_clues(state):
    """Speak clues until the configured number of rounds is done."""
    guard = 0
    while state["phase"] == imp.PHASE_CLUES and guard < 100:
        imp.record_clue(state, pp.current_turn(state["turn"]), "word")
        guard += 1
    return state


class TestSetup:
    def test_needs_three_players(self):
        assert imp.can_start(_seats(2)) is False
        assert imp.can_start(_seats(3)) is True

    def test_assigns_exactly_one_impostor(self):
        s = _state(5)
        assert s["impostor_id"] in pp.seat_ids(s["seats"])

    def test_starts_in_role_reveal(self):
        assert _state()["phase"] == imp.PHASE_REVEAL_ROLES

    def test_config_defaults_and_clamping(self):
        cfg = imp.validate_config({"clue_rounds": 99, "pack": "nope"})
        assert cfg["clue_rounds"] == imp.MAX_CLUE_ROUNDS
        assert cfg["pack"] == imp.DEFAULT_PACK
        assert cfg["pairs"]

    def test_junk_config_never_raises(self):
        for bad in (None, {}, {"pairs": "nope"}, {"pairs": [1, None, {}]}):
            assert imp.validate_config(bad)["pairs"]

    def test_a_decoy_equal_to_the_secret_is_dropped(self):
        """An identical decoy hands the impostor the answer outright."""
        cfg = imp.validate_config({"pairs": [{"secret": "Pizza", "decoy": "pizza"}]})
        assert cfg["pairs"][0]["decoy"] == ""


class TestRoleReveal:
    def test_knowers_see_the_secret_and_the_impostor_does_not(self):
        s = _state(4)
        imposter = s["impostor_id"]
        for sid in pp.seat_ids(s["seats"]):
            role = imp.role_for(s, sid)
            if sid == imposter:
                assert role["is_impostor"] is True
                assert role["word"] != s["secret_word"]
            else:
                assert role["is_impostor"] is False
                assert role["word"] == s["secret_word"]

    def test_hint_mode_gives_the_impostor_the_decoy(self):
        s = _state(4, impostor_hint=True)
        assert imp.role_for(s, s["impostor_id"])["word"] == s["decoy_word"]

    def test_hint_mode_off_gives_the_impostor_nothing(self):
        s = _state(4, impostor_hint=False)
        role = imp.role_for(s, s["impostor_id"])
        assert role["word"] == "" and role["hint_mode"] is False

    def test_clues_start_only_after_everyone_has_seen_their_role(self):
        s = _state(3)
        imp.mark_revealed(s, "s0")
        assert s["phase"] == imp.PHASE_REVEAL_ROLES     # still passing
        imp.mark_revealed(s, "s1")
        imp.mark_revealed(s, "s2")
        assert s["phase"] == imp.PHASE_CLUES

    def test_next_unrevealed_drives_the_pass_screen(self):
        s = _state(3)
        assert imp.next_unrevealed(s) == "s0"
        imp.mark_revealed(s, "s0")
        assert imp.next_unrevealed(s) == "s1"

    def test_revealing_twice_does_not_double_count(self):
        s = _state(3)
        imp.mark_revealed(s, "s0")
        imp.mark_revealed(s, "s0")
        assert s["revealed_to"] == ["s0"]
        assert s["phase"] == imp.PHASE_REVEAL_ROLES

    def test_unknown_seat_cannot_mark_itself_revealed(self):
        s = _state(3)
        imp.mark_revealed(s, "ghost")
        assert s["revealed_to"] == []


class TestClues:
    def test_only_the_seat_whose_turn_it_is_can_speak(self):
        s = _reveal_all(_state(3))
        current = pp.current_turn(s["turn"])
        other = next(x for x in pp.seat_ids(s["seats"]) if x != current)
        imp.record_clue(s, other, "nope")
        assert s["clues"] == []

    def test_clue_rounds_advance_to_voting(self):
        s = _reveal_all(_state(3, clue_rounds=2))
        _run_clues(s)
        assert s["phase"] == imp.PHASE_VOTING
        assert len(s["clues"]) == 6          # 3 seats x 2 rounds

    def test_clue_word_is_optional_because_clues_are_spoken_aloud(self):
        s = _reveal_all(_state(3))
        imp.record_clue(s, pp.current_turn(s["turn"]))
        assert s["clues"][0]["word"] == ""

    def test_clues_are_ignored_outside_the_clue_phase(self):
        s = _state(3)                        # still in role reveal
        imp.record_clue(s, "s0", "early")
        assert s["clues"] == []


class TestVoting:
    def _voting(self, n=5, seed=1):
        return _run_clues(_reveal_all(_state(n, seed=seed, clue_rounds=1)))

    def test_self_votes_are_rejected(self):
        s = self._voting()
        imp.submit_vote(s, "s0", "s0")
        assert s["votes"] == {}

    def test_unknown_seats_cannot_vote_or_be_voted_for(self):
        s = self._voting()
        imp.submit_vote(s, "ghost", "s1")
        imp.submit_vote(s, "s0", "ghost")
        assert s["votes"] == {}

    def test_a_split_vote_lets_the_impostor_survive(self):
        s = self._voting(n=4)
        ids = pp.seat_ids(s["seats"])
        # 2-2 split: no strict majority.
        imp.submit_vote(s, ids[0], ids[1])
        imp.submit_vote(s, ids[1], ids[0])
        imp.submit_vote(s, ids[2], ids[3])
        imp.submit_vote(s, ids[3], ids[2])
        imp.close_vote(s)
        assert s["outcome"] == "impostor_survived"
        assert s["phase"] == imp.PHASE_REVEAL

    def test_convicting_a_knower_lets_the_impostor_survive(self):
        s = self._voting(n=5)
        innocent = next(x for x in pp.seat_ids(s["seats"]) if x != s["impostor_id"])
        for voter in pp.seat_ids(s["seats"]):
            if voter != innocent:
                imp.submit_vote(s, voter, innocent)
        imp.close_vote(s)
        assert s["outcome"] == "impostor_survived"
        assert s["scores"][s["impostor_id"]] == imp.POINTS_IMPOSTOR_SURVIVED

    def test_convicting_the_impostor_opens_their_one_guess(self):
        s = self._voting(n=5)
        for voter in pp.seat_ids(s["seats"]):
            if voter != s["impostor_id"]:
                imp.submit_vote(s, voter, s["impostor_id"])
        imp.close_vote(s)
        assert s["phase"] == imp.PHASE_ACCUSED_GUESS
        assert s["outcome"] == ""            # not decided until they guess


class TestTheComebackRule:
    """A caught impostor who names the secret word still wins the round. Without this their best
    play once suspected is to go quiet, which is boring for everyone."""

    def _caught(self, n=5):
        s = _run_clues(_reveal_all(_state(n, clue_rounds=1)))
        for voter in pp.seat_ids(s["seats"]):
            if voter != s["impostor_id"]:
                imp.submit_vote(s, voter, s["impostor_id"])
        return imp.close_vote(s)

    def test_a_correct_guess_wins_the_round(self):
        s = self._caught()
        imp.submit_accused_guess(s, s["secret_word"])
        assert s["outcome"] == "impostor_guessed"
        assert s["scores"][s["impostor_id"]] == imp.POINTS_IMPOSTOR_GUESSED

    def test_the_guess_is_case_and_space_insensitive(self):
        s = self._caught()
        imp.submit_accused_guess(s, f"  {s['secret_word'].upper()}  ")
        assert s["outcome"] == "impostor_guessed"

    def test_a_wrong_guess_scores_every_knower(self):
        s = self._caught(n=5)
        imp.submit_accused_guess(s, "definitely not it")
        assert s["outcome"] == "impostor_caught"
        for sid in pp.seat_ids(s["seats"]):
            expected = 0 if sid == s["impostor_id"] else imp.POINTS_CAUGHT_IMPOSTOR
            assert s["scores"][sid] == expected

    def test_a_guess_outside_the_guess_phase_is_ignored(self):
        s = _state(3)
        imp.submit_accused_guess(s, "anything")
        assert s["outcome"] == ""


class TestRoundsAndScoring:
    def test_the_secret_is_withheld_until_the_round_resolves(self):
        """The clue phase is face-up on a table; there's no reason to ship the answer to it."""
        s = _reveal_all(_state(3))
        assert imp.public_state(s)["secret_word"] == ""
        assert imp.public_state(s)["impostor_id"] == ""
        _run_clues(s)
        for voter in pp.seat_ids(s["seats"]):
            if voter != s["impostor_id"]:
                imp.submit_vote(s, voter, s["impostor_id"])
        imp.close_vote(s)
        imp.submit_accused_guess(s, "wrong")
        pub = imp.public_state(s)
        assert pub["secret_word"] == s["secret_word"]
        assert pub["impostor_id"] == s["impostor_id"]

    def test_word_pairs_do_not_repeat_until_the_deck_is_exhausted(self):
        pairs = [{"secret": f"W{i}", "decoy": f"D{i}"} for i in range(4)]
        s = _state(3, pairs=pairs, total_rounds=10)
        seen = [s["secret_word"]]
        for _ in range(3):
            imp.start_round(s, rng=random.Random(7))
            seen.append(s["secret_word"])
        assert len(set(seen)) == 4                  # all four before any repeat

    def test_a_new_round_rotates_the_impostor_and_resets_state(self):
        s = _reveal_all(_state(4))
        imp.start_round(s, rng=random.Random(99))
        assert s["phase"] == imp.PHASE_REVEAL_ROLES
        assert s["revealed_to"] == [] and s["votes"] == {} and s["clues"] == []

    def test_scores_accumulate_across_rounds(self):
        s = _state(3, total_rounds=3)
        s["scores"]["s0"] = 5
        imp.start_round(s, rng=random.Random(3))
        assert s["scores"]["s0"] == 5            # a new round must not wipe the scoreboard

    def test_the_game_ends_at_the_configured_round_count(self):
        s = _state(3, total_rounds=1)
        imp.next_round(s)
        assert s["phase"] == imp.PHASE_PODIUM

    def test_standings_are_sorted_and_carry_display_names(self):
        s = _state(3)
        s["scores"] = {"s0": 1, "s1": 9, "s2": 5}
        rows = imp.standings(s)
        assert [r["seat_id"] for r in rows] == ["s1", "s2", "s0"]
        assert rows[0]["nickname"] == "P1"

    def test_history_records_each_resolved_round(self):
        s = _run_clues(_reveal_all(_state(3, clue_rounds=1)))
        for voter in pp.seat_ids(s["seats"]):
            if voter != s["impostor_id"]:
                imp.submit_vote(s, voter, s["impostor_id"])
        imp.close_vote(s)
        imp.submit_accused_guess(s, "no")
        assert len(s["history"]) == 1
        assert s["history"][0]["outcome"] == "impostor_caught"


class TestPhaseScopedDisclosure:
    """Roles travel exactly when a UI privacy gate is mounted to hold them, and not otherwise.

    This resolves what looked like two contradictory requirements: the client MUST have every
    role during the reveal pass (it renders them one at a time behind the gate, and per-viewer
    scoping is meaningless with one device), but the phone is FACE-UP during clues and voting,
    where shipping a secret buys nothing and risks a screenshot or a network log exposing it.
    """

    def test_roles_are_sent_during_the_gated_reveal_phase(self):
        s = _state(4)
        pub = imp.public_state(s)
        assert s["phase"] == imp.PHASE_REVEAL_ROLES
        assert set(pub["roles"]) == set(pp.seat_ids(s["seats"]))
        # Exactly one impostor among them.
        assert sum(1 for r in pub["roles"].values() if r["is_impostor"]) == 1

    def test_roles_are_withheld_once_the_phone_is_face_up(self):
        s = _reveal_all(_state(3))
        assert s["phase"] == imp.PHASE_CLUES
        assert imp.public_state(s)["roles"] == {}

    def test_roles_stay_withheld_through_voting(self):
        s = _run_clues(_reveal_all(_state(3, clue_rounds=1)))
        assert s["phase"] == imp.PHASE_VOTING
        assert imp.public_state(s)["roles"] == {}

    def test_the_secret_is_never_in_the_payload_before_the_round_resolves(self):
        s = _state(3, clue_rounds=1)
        for stage in ("reveal", "clues", "voting"):
            pub = imp.public_state(s)
            assert pub["secret_word"] == "", f"secret leaked during {stage}"
            assert pub["impostor_id"] == "", f"impostor leaked during {stage}"
            if stage == "reveal":
                _reveal_all(s)
            elif stage == "clues":
                _run_clues(s)
