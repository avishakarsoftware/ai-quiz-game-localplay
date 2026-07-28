"""Impostor engine (SPEC-GAME-IMPOSTOR).

The invariant that matters most is the prompt leak: if a non-odd player can see the minority prompt
anywhere in their payload, the game is over before it starts. That gets its own explicit tests.
"""
import impostor_engine as imp


def _state(players=("p1", "p2", "p3", "p4"), config=None):
    return imp.create_initial_state(list(players), config=config, now=1000.0)


def _answer_all(state, text="thing"):
    for pid in imp.eligible_voters(state):
        imp.submit_answer(state, pid, f"{text}-{pid}")
    return state


# --- setup / config ---

def test_defaults_to_the_curated_deck():
    state = _state()
    assert len(state["config"]["prompt_pairs"]) == len(imp.DEFAULT_PROMPT_PAIRS)
    assert state["phase"] == imp.PHASE_ANSWERING


def test_malformed_custom_deck_degrades_to_the_curated_one():
    """A bad custom deck must produce a playable game, not a dead room."""
    state = _state(config={"prompt_pairs": [{"majority": ""}, "nonsense", {"minority": "only"}]})
    assert state["config"]["prompt_pairs"] == imp.DEFAULT_PROMPT_PAIRS


def test_custom_pairs_are_accepted_and_sanitized():
    state = _state(config={"prompt_pairs": [
        {"id": "x", "majority": "<b>Beach</b> thing", "minority": "Gym thing"},
    ]})
    pair = state["config"]["prompt_pairs"][0]
    assert pair["majority"] == "Beach thing"      # HTML stripped by engine_common
    assert state["config"]["total_rounds"] == 1   # can't exceed the deck size


def test_total_rounds_cannot_exceed_the_deck():
    state = _state(config={"prompt_pairs": [{"majority": "a", "minority": "b"}], "total_rounds": 99})
    assert state["config"]["total_rounds"] == 1


def test_minimum_players_enforced():
    """At 2 players the vote is trivial — you can't vote for yourself, so there's one option."""
    assert imp.can_start(["p1", "p2"]) is False
    assert imp.can_start(["p1", "p2", "p3"]) is True
    assert imp.can_start(["p1", "p1", "p2"]) is False   # dedupes before counting


# --- the prompt-leak invariant ---

def test_only_the_odd_one_sees_the_minority_prompt():
    state = _state()
    odd = state["odd_player_id"]
    pair = imp.current_pair(state)

    odd_view = imp.public_state(state, viewer_id=odd)
    assert odd_view["prompt"] == pair["minority"]
    assert odd_view["you_are_odd"] is True

    for other in [p for p in state["scores"] if p != odd]:
        view = imp.public_state(state, viewer_id=other)
        assert view["prompt"] == pair["majority"]
        assert view["you_are_odd"] is False
        # The minority prompt must not appear ANYWHERE in a non-odd player's payload.
        assert pair["minority"] not in str(view)


def test_host_view_leaks_neither_prompt_during_play():
    """The host screen is usually visible to the whole room."""
    state = _state()
    pair = imp.current_pair(state)
    view = imp.public_state(state, viewer_id=None, host=True)
    assert pair["minority"] not in str(view)
    assert pair["majority"] not in str(view)


def test_answers_are_hidden_until_voting():
    state = _answer_all(_state())
    assert "answers" not in imp.public_state(state, viewer_id="p2")
    imp.start_voting(state)
    assert len(imp.public_state(state, viewer_id="p2")["answers"]) == 4


# --- answering ---

def test_resubmitting_overwrites_instead_of_stacking():
    state = _state()
    imp.submit_answer(state, "p1", "first")
    imp.submit_answer(state, "p1", "second")
    assert state["answers"]["p1"] == "second"
    assert len(state["answers"]) == 1


def test_blank_and_unknown_player_answers_are_ignored():
    state = _state()
    imp.submit_answer(state, "p1", "   ")
    imp.submit_answer(state, "ghost", "hello")
    assert state["answers"] == {}


def test_answers_rejected_outside_the_answering_phase():
    state = _answer_all(_state())
    imp.start_voting(state)
    imp.submit_answer(state, "p1", "late")
    assert state["answers"]["p1"] != "late"


def test_all_answered_tracks_eligible_voters():
    state = _state()
    assert imp.all_answered(state) is False
    _answer_all(state)
    assert imp.all_answered(state) is True


# --- voting ---

def test_self_votes_are_rejected():
    state = imp.start_voting(_answer_all(_state()))
    imp.submit_vote(state, "p1", "p1")
    assert "p1" not in state["votes"]


def test_votes_for_unknown_players_are_rejected():
    state = imp.start_voting(_answer_all(_state()))
    imp.submit_vote(state, "p1", "ghost")
    assert state["votes"] == {}


def test_revote_overwrites():
    state = imp.start_voting(_answer_all(_state()))
    imp.submit_vote(state, "p1", "p2")
    imp.submit_vote(state, "p1", "p3")
    assert state["votes"]["p1"] == "p3"


# --- scoring ---

def test_catching_the_odd_one_needs_a_strict_majority_not_a_plurality():
    """At 4 voters, 2 votes is a plurality but not a majority — the odd one survives."""
    state = imp.start_voting(_answer_all(_state()))
    odd = state["odd_player_id"]                       # p1 by rotation
    others = [p for p in state["scores"] if p != odd]
    imp.submit_vote(state, others[0], odd)
    imp.submit_vote(state, others[1], odd)             # 2 of 4 — not > half
    imp.submit_vote(state, others[2], others[0])
    imp.reveal_round(state)
    assert state["round_result"]["caught"] is False
    assert state["scores"][odd] >= imp.POINTS_ODD_SURVIVES


def test_a_strict_majority_catches_the_odd_one():
    state = imp.start_voting(_answer_all(_state()))
    odd = state["odd_player_id"]
    others = [p for p in state["scores"] if p != odd]
    for voter in others:                               # 3 of 4 > half
        imp.submit_vote(state, voter, odd)
    imp.reveal_round(state)
    assert state["round_result"]["caught"] is True
    assert state["scores"][odd] == 0
    for voter in others:
        assert state["scores"][voter] == imp.POINTS_CORRECT_VOTE


def test_odd_one_earns_a_misdirect_bonus_for_piling_on_the_leader():
    state = imp.start_voting(_answer_all(_state()))
    odd = state["odd_player_id"]
    others = [p for p in state["scores"] if p != odd]
    # Everyone (including the odd one) converges on an innocent player.
    imp.submit_vote(state, others[0], others[1])
    imp.submit_vote(state, others[1], others[2])
    imp.submit_vote(state, others[2], others[1])
    imp.submit_vote(state, odd, others[1])
    imp.reveal_round(state)
    assert state["round_result"]["caught"] is False
    assert state["scores"][odd] == imp.POINTS_ODD_SURVIVES + imp.POINTS_ODD_MISDIRECT


def test_reveal_is_idempotent():
    """Both a host action and an all-voted auto-advance can reach reveal."""
    state = imp.start_voting(_answer_all(_state()))
    odd = state["odd_player_id"]
    for voter in [p for p in state["scores"] if p != odd]:
        imp.submit_vote(state, voter, odd)
    imp.reveal_round(state)
    scores_once = dict(state["scores"])
    imp.reveal_round(state)
    assert state["scores"] == scores_once


def test_reveal_shows_both_prompts_so_the_round_is_legible_in_hindsight():
    state = imp.start_voting(_answer_all(_state()))
    pair = imp.current_pair(state)
    imp.reveal_round(state)
    result = state["round_result"]
    assert result["majority_prompt"] == pair["majority"]
    assert result["minority_prompt"] == pair["minority"]


def test_round_resolves_even_with_no_votes_at_all():
    """A stalled room must not wedge the game."""
    state = imp.start_voting(_answer_all(_state()))
    imp.reveal_round(state)
    assert state["round_result"]["caught"] is False
    assert state["phase"] == imp.PHASE_REVEAL


# --- rotation / rounds ---

def test_the_odd_one_rotates_rather_than_repeating_randomly():
    state = _state(config={"total_rounds": 4})
    seen = []
    for _ in range(4):
        seen.append(state["odd_player_id"])
        _answer_all(state)
        imp.start_voting(state)
        imp.reveal_round(state)
        imp.next_round(state)
    assert seen == ["p1", "p2", "p3", "p4"]   # everyone gets a turn


def test_next_round_clears_the_previous_round_state():
    state = _state(config={"total_rounds": 3})
    _answer_all(state)
    imp.start_voting(state)
    imp.submit_vote(state, "p1", "p2")
    imp.reveal_round(state)
    imp.next_round(state)
    assert state["answers"] == {}
    assert state["votes"] == {}
    assert state["round_result"] is None
    assert state["phase"] == imp.PHASE_ANSWERING


def test_final_round_ends_at_podium():
    state = _state(config={"total_rounds": 1})
    _answer_all(state)
    imp.start_voting(state)
    imp.reveal_round(state)
    imp.next_round(state)
    assert state["phase"] == imp.PHASE_PODIUM


def test_scores_accumulate_across_rounds():
    state = _state(config={"total_rounds": 2})
    for _ in range(2):
        _answer_all(state)
        imp.start_voting(state)
        odd = state["odd_player_id"]
        for voter in [p for p in state["scores"] if p != odd]:
            imp.submit_vote(state, voter, odd)
        imp.reveal_round(state)
        imp.next_round(state)
    # Every non-odd player scored in the round they weren't the odd one.
    assert sum(state["scores"].values()) > 0
    assert imp.standings(state)[0]["score"] >= imp.POINTS_CORRECT_VOTE


# --- late joiners / leavers ---

def test_late_joiner_cannot_act_in_the_round_already_underway():
    """They may have seen this round's answers on the host screen, so letting them answer or vote
    would let them play with information nobody else had."""
    state = _state(("p1", "p2", "p3"), config={"total_rounds": 4})
    _answer_all(state)
    imp.add_player(state, "p4")

    assert "p4" in state["rotation"]          # they DO get a turn as the odd one later
    assert imp.is_eligible(state, "p4") is False
    assert "p4" not in imp.eligible_voters(state)

    imp.submit_answer(state, "p4", "sneaky")
    assert "p4" not in state["answers"]

    imp.start_voting(state)
    imp.submit_vote(state, "p4", "p1")
    assert "p4" not in state["votes"]

    # Seating them must not stall the round: the three original players are still "all answered".
    assert imp.all_answered(state) is True


def test_late_joiner_becomes_eligible_next_round():
    state = _state(("p1", "p2", "p3"), config={"total_rounds": 4})
    _answer_all(state)
    imp.add_player(state, "p4")
    imp.start_voting(state)
    imp.reveal_round(state)
    imp.next_round(state)
    assert imp.is_eligible(state, "p4") is True
    imp.submit_answer(state, "p4", "now allowed")
    assert state["answers"]["p4"] == "now allowed"


def test_rotation_skips_a_player_who_is_not_eligible_yet():
    """Otherwise round 2 could hand the minority prompt to someone still sitting out."""
    state = _state(("p1", "p2"), config={"total_rounds": 3})
    imp.add_player(state, "p3")              # seated from round 1
    _answer_all(state)
    imp.start_voting(state)
    imp.reveal_round(state)
    imp.next_round(state)
    assert imp.is_eligible(state, state["odd_player_id"]) is True


def test_adding_an_existing_player_is_a_no_op():
    state = _state(("p1", "p2", "p3"))
    before = list(state["rotation"])
    imp.add_player(state, "p1")
    assert state["rotation"] == before


def test_round_resolves_when_the_odd_one_never_answered():
    """If the odd one drops out, the round must still resolve rather than hanging."""
    state = _state()
    odd = state["odd_player_id"]
    for pid in [p for p in imp.eligible_voters(state) if p != odd]:
        imp.submit_answer(state, pid, "answer")
    imp.start_voting(state)
    for voter in [p for p in state["scores"] if p != odd]:
        imp.submit_vote(state, voter, odd)
    imp.reveal_round(state)
    assert state["round_result"]["caught"] is True
    assert state["phase"] == imp.PHASE_REVEAL
