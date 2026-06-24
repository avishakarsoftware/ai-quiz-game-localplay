import pytest

from generic_prompt_engine import (
    MODE_CHOICE,
    MODE_TEXT_GROUP,
    MODE_TEXT_VOTE,
    PHASE_CHOICE,
    PHASE_PODIUM,
    PHASE_REVEAL,
    PHASE_SUBMITTING,
    PHASE_VOTING,
    add_player,
    create_initial_state,
    next_round,
    public_state,
    reveal_round,
    start_voting,
    standings,
    submit_choice,
    submit_text,
    submit_vote,
    validate_config,
)


def test_choice_vote_reveals_majority_and_scores():
    state = create_initial_state(["Avi", "Ruchi", "Ashu"], "hot_takes", {"round_count": 3}, now=1)

    assert state["phase"] == PHASE_CHOICE
    assert state["config"]["mode"] == MODE_CHOICE

    state = submit_choice(state, "Avi", "Agree")
    state = submit_choice(state, "Ruchi", "Agree")
    state = submit_choice(state, "Ashu", "Disagree")
    state = reveal_round(state, now=2)

    assert state["phase"] == PHASE_REVEAL
    assert state["scores"]["Avi"] == 1
    assert state["scores"]["Ruchi"] == 1
    assert state["scores"]["Ashu"] == 0
    assert state["rounds"][0]["result"]["winners"] == ["Agree"]


def test_text_vote_flow_scores_entry_author():
    state = create_initial_state(["Avi", "Ruchi", "Ashu"], "caption_contest", {"round_count": 3}, now=1)

    assert state["phase"] == PHASE_SUBMITTING
    assert state["config"]["mode"] == MODE_TEXT_VOTE

    state = submit_text(state, "Avi", "The cake is just doing yoga.")
    state = submit_text(state, "Ruchi", "Structural frosting issue.")
    state = start_voting(state)
    assert state["phase"] == PHASE_VOTING

    avi_entry = state["rounds"][0]["submissions"]["Avi"]["entry_id"]
    state = submit_vote(state, "Ruchi", avi_entry)
    state = submit_vote(state, "Ashu", avi_entry)
    state = reveal_round(state, now=2)

    assert state["scores"]["Avi"] == 2
    assert state["rounds"][0]["result"]["vote_counts"][avi_entry] == 2


def test_text_group_scores_largest_matching_group():
    state = create_initial_state(["Avi", "Ruchi", "Ashu"], "rapid_fire", {"round_count": 3}, now=1)

    assert state["config"]["mode"] == MODE_TEXT_GROUP
    state = submit_text(state, "Avi", "Pizza")
    state = submit_text(state, "Ruchi", "pizza!")
    state = submit_text(state, "Ashu", "Cake")
    state = reveal_round(state, now=2)

    assert state["scores"]["Avi"] == 1
    assert state["scores"]["Ruchi"] == 1
    assert state["scores"]["Ashu"] == 0
    groups = state["rounds"][0]["result"]["groups"]
    assert groups[0]["normalized"] == "pizza"
    assert groups[0]["count"] == 2


def test_public_state_redacts_entries_until_voting_or_reveal():
    state = create_initial_state(["Avi", "Ruchi"], "pitch_battle", {"round_count": 3}, now=1)
    state = submit_text(state, "Avi", "An app that apologizes for being late.")

    viewer = public_state(state, "Ruchi")
    host = public_state(state, host=True)

    assert viewer["entries"] == []
    assert len(host["entries"]) == 1
    assert public_state(state, "Avi")["your_submission"].startswith("An app")


def test_late_join_and_podium():
    state = create_initial_state(["Avi", "Ruchi"], "this_or_that", {"round_count": 3}, now=1)
    state = add_player(state, "Ashu")

    assert "Ashu" in state["players"]
    assert state["scores"]["Ashu"] == 0

    for _ in range(3):
        option = state["rounds"][state["current_round_index"]]["prompt"]["options"][0]
        state = submit_choice(state, "Avi", option)
        state = reveal_round(state)
        state = next_round(state)

    assert state["phase"] == PHASE_PODIUM
    assert standings(state)[0]["player_id"] == "Avi"


def test_rejects_self_vote():
    state = create_initial_state(["Avi", "Ruchi"], "emoji_story", {"round_count": 3}, now=1)
    state = submit_text(state, "Avi", "Cake panic, then everyone wins.")
    state = start_voting(state)
    entry_id = state["rounds"][0]["submissions"]["Avi"]["entry_id"]

    with pytest.raises(ValueError):
        submit_vote(state, "Avi", entry_id)


def test_validation_uses_requested_game_metadata():
    config = validate_config({}, "roast_toast")

    assert config["game_title"] == "Roast & Toast"
    assert config["mode"] == MODE_TEXT_VOTE
    assert len(config["rounds"]) >= 3
