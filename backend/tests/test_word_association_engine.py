import pytest

from word_association_engine import (
    PHASE_PODIUM,
    PHASE_REVEAL,
    PHASE_SUBMITTING,
    add_player,
    create_initial_state,
    next_round,
    normalize_submission,
    public_state,
    reveal_round,
    submit_word,
    validate_config,
)


def test_validate_config_sanitizes_seed_pack():
    config = validate_config({
        "game_title": "Quick Links",
        "seeds": [
            {"seed": "Birthday"},
            {"seed": "Music"},
            {"seed": "Vacation"},
        ],
    })

    assert config["game_title"] == "Quick Links"
    assert config["round_count"] == 3
    assert config["seeds"][0]["seed"] == "Birthday"


def test_normalize_submission_groups_case_and_punctuation():
    assert normalize_submission(" Cake!! ") == "cake"
    assert normalize_submission("Café") == "cafe"


def test_reveal_groups_majority_and_redacts_before_reveal():
    state = create_initial_state(["alice", "bob", "cara"], {}, now=100)
    state = submit_word(state, "alice", "Cake")
    state = submit_word(state, "bob", "cake!")
    state = submit_word(state, "cara", "music")

    public = public_state(state)
    assert public["phase"] == PHASE_SUBMITTING
    assert public["submitted_count"] == 3
    assert "submissions" not in public
    assert public_state(state, viewer_id="bob")["your_submission"] == "cake!"

    state = reveal_round(state, now=120)

    assert state["phase"] == PHASE_REVEAL
    assert state["rounds"][0]["groups"][0]["normalized"] == "cake"
    assert state["rounds"][0]["groups"][0]["count"] == 2
    assert state["scores"]["alice"] == 1
    assert state["scores"]["bob"] == 1
    assert state["scores"]["cara"] == 0


def test_all_unique_answers_award_no_majority_score():
    state = create_initial_state(["alice", "bob", "cara"], {}, now=100)
    state = submit_word(state, "alice", "cake")
    state = submit_word(state, "bob", "music")
    state = submit_word(state, "cara", "travel")
    state = reveal_round(state)

    assert state["scores"] == {"alice": 0, "bob": 0, "cara": 0}


def test_submission_changes_can_be_disabled():
    state = create_initial_state(["alice"], {"allow_submission_changes": False})
    state = submit_word(state, "alice", "cake")

    with pytest.raises(ValueError, match="Submission changes"):
        submit_word(state, "alice", "music")


def test_late_join_and_completion_flow():
    state = create_initial_state(["alice"], {}, now=100)
    state = add_player(state, "bob")
    assert state["players"] == ["alice", "bob"]

    for index in range(3):
        state = submit_word(state, "alice", f"word {index}")
        state = reveal_round(state)
        state = next_round(state)

    assert state["phase"] == PHASE_PODIUM
    assert state["completed_at"]
