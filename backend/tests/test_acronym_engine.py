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
    assert {entry["entry_id"] for entry in voting["entries"]} == {"entry_alice", "entry_bob", "entry_cara"}
    assert voting["your_entry_id"] == "entry_alice"

    with pytest.raises(ValueError, match="own entry"):
        submit_vote(state, "alice", "entry_alice")

    state = submit_vote(state, "alice", "entry_bob")
    state = submit_vote(state, "bob", "entry_cara")
    state = submit_vote(state, "cara", "entry_bob")
    state = reveal_round(state, now=120)

    assert state["phase"] == PHASE_REVEAL
    assert state["rounds"][0]["vote_counts"]["entry_bob"] == 2
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
