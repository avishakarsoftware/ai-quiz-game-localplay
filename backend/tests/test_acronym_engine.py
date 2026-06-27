import pytest

from acronym_engine import (
    PHASE_PODIUM,
    PHASE_REVEAL,
    PHASE_SUBMITTING,
    PHASE_VOTING,
    create_initial_state,
    expansion_matches,
    next_round,
    public_state,
    reveal_round,
    start_voting,
    submit_expansion,
    submit_vote,
    validate_config,
)


def test_validate_config_sanitizes_acronyms():
    config = validate_config({
        "game_title": "Tiny Acronyms",
        "prompts": [
            {"acronym": "FUN", "hint": "Keep it silly."},
            {"acronym": "CAKE"},
            {"acronym": "PARTY"},
        ],
    })

    assert config["game_title"] == "Tiny Acronyms"
    assert config["round_count"] == 3
    assert config["prompts"][0]["acronym"] == "FUN"


def test_expansion_validation_matches_letters():
    assert expansion_matches("FUN", "Fancy Umbrella Night")
    assert not expansion_matches("FUN", "Fancy Night")
    assert not expansion_matches("FUN", "Fancy Apple Night")


def test_public_state_exposes_your_vote_so_the_ui_can_lock_voting():
    state = create_initial_state(
        ["alice", "bob"],
        {"prompts": [{"acronym": "FUN"}, {"acronym": "CAKE"}, {"acronym": "PARTY"}]},
        now=100,
    )
    state = submit_expansion(state, "alice", "Fancy Umbrella Night")
    state = submit_expansion(state, "bob", "Fast Unicorn Nap")
    state = start_voting(state)
    bob_entry = state["rounds"][0]["submissions"]["bob"]["entry_id"]
    state = submit_vote(state, "alice", bob_entry)

    # The voter's own choice comes back so the client can highlight/lock it.
    assert public_state(state, viewer_id="alice")["your_vote"] == bob_entry
    # A player who hasn't voted yet has no your_vote.
    assert "your_vote" not in public_state(state, viewer_id="bob")


def test_submit_vote_reveal_scores_and_redacts_authors_before_reveal():
    state = create_initial_state(
        ["alice", "bob", "cara"],
        {
            "prompts": [
                {"acronym": "FUN"},
                {"acronym": "CAKE"},
                {"acronym": "PARTY"},
            ],
        },
        now=100,
    )

    state = submit_expansion(state, "alice", "Fancy Umbrella Night")
    state = submit_expansion(state, "bob", "Fast Unicorn Nap")
    state = submit_expansion(state, "cara", "Fuzzy Ukulele Noise")

    public = public_state(state)
    assert public["phase"] == PHASE_SUBMITTING
    assert public["submitted_count"] == 3
    assert "entries" not in public

    state = start_voting(state)
    assert state["phase"] == PHASE_VOTING
    voting = public_state(state, viewer_id="alice")
    # Entry ids must be unique and must NOT embed the author's nickname (blind voting).
    entry_ids = {entry["entry_id"] for entry in voting["entries"]}
    assert len(entry_ids) == 3
    for name in ("alice", "bob", "cara"):
        assert not any(name in entry_id for entry_id in entry_ids)
    submissions = state["rounds"][0]["submissions"]
    alice_entry = submissions["alice"]["entry_id"]
    bob_entry = submissions["bob"]["entry_id"]
    cara_entry = submissions["cara"]["entry_id"]
    assert voting["your_entry_id"] == alice_entry

    with pytest.raises(ValueError, match="own entry"):
        submit_vote(state, "alice", alice_entry)

    state = submit_vote(state, "alice", bob_entry)
    state = submit_vote(state, "bob", cara_entry)
    state = submit_vote(state, "cara", bob_entry)
    state = reveal_round(state, now=120)

    assert state["phase"] == PHASE_REVEAL
    assert state["rounds"][0]["vote_counts"][bob_entry] == 2
    assert state["scores"]["bob"] == 2
    assert public_state(state)["submissions"]["bob"]["text"] == "Fast Unicorn Nap"


def test_invalid_expansion_and_empty_voting_are_rejected():
    state = create_initial_state(["alice"], {}, now=100)

    with pytest.raises(ValueError, match="match the acronym"):
        submit_expansion(state, "alice", "Wrong Words")

    with pytest.raises(ValueError, match="At least one"):
        start_voting(state)


def test_completion_flow():
    state = create_initial_state(["alice", "bob"], {}, now=100)
    expansions = ["Proud Ants Run Tiny Yachts", "Cool Ants Keep Eating", "Daring Ants Never Chase Eggs"]

    for expansion in expansions:
        state = submit_expansion(state, "alice", expansion)
        state = start_voting(state)
        state = reveal_round(state)
        state = next_round(state)

    assert state["phase"] == PHASE_PODIUM
    assert state["completed_at"]
