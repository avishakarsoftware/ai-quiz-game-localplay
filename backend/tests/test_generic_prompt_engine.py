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


def test_entry_ids_unique_for_nicknames_that_normalize_alike():
    # "Bob!" and "Bob?" both normalize to "bob"; the old entry-id scheme gave
    # them the same id, merging their vote buckets and corrupting the tally.
    state = create_initial_state(["Bob!", "Bob?", "Cara"], "caption_contest", {"round_count": 1}, now=1)
    state = submit_text(state, "Bob!", "First caption.")
    state = submit_text(state, "Bob?", "Second caption.")
    state = start_voting(state)

    submissions = state["rounds"][0]["submissions"]
    bang_entry = submissions["Bob!"]["entry_id"]
    quest_entry = submissions["Bob?"]["entry_id"]
    assert bang_entry != quest_entry

    # Two voters back "Bob!"; only that entry should be credited.
    state = submit_vote(state, "Bob?", bang_entry)
    state = submit_vote(state, "Cara", bang_entry)
    state = reveal_round(state, now=2)

    assert state["scores"]["Bob!"] == 2
    assert state["scores"]["Bob?"] == 0
    assert state["rounds"][0]["result"]["vote_counts"][bang_entry] == 2
    assert state["rounds"][0]["result"]["vote_counts"][quest_entry] == 0


def test_voting_entries_are_anonymous_to_non_authors():
    state = create_initial_state(["Avi", "Ruchi", "Ashu"], "caption_contest", {"round_count": 1}, now=1)
    state = submit_text(state, "Avi", "The cake is doing yoga.")
    state = submit_text(state, "Ruchi", "Structural frosting issue.")
    state = start_voting(state)

    viewer = public_state(state, "Ashu")
    assert len(viewer["entries"]) == 2
    for entry in viewer["entries"]:
        # Blind voting: no author info leaks during the voting phase.
        assert "player_id" not in entry
        assert "normalized" not in entry
        assert entry["is_mine"] is False
        assert entry["text"]

    # An author sees is_mine on their own entry so the UI can disable self-votes.
    avi_view = public_state(state, "Avi")
    mine = [e for e in avi_view["entries"] if e["is_mine"]]
    assert len(mine) == 1

    # Authorship is restored once the round is revealed.
    state = reveal_round(state, now=2)
    revealed = public_state(state, "Ashu")
    assert all("player_id" in entry for entry in revealed["entries"])


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
