import pytest

from would_you_rather_engine import (
    PHASE_PODIUM,
    PHASE_REVEAL,
    PHASE_VOTING,
    add_player,
    create_initial_state,
    next_round,
    public_state,
    reveal_round,
    submit_vote,
    validate_config,
)


def test_validate_config_sanitizes_prompt_pack():
    config = validate_config({
        "game_title": "Party Choices",
        "prompts": [
            {"question": "Would you rather pick snacks or songs?", "option_a": "Snacks", "option_b": "Songs"},
            {"question": "Would you rather teleport or fly?", "option_a": "Teleport", "option_b": "Fly"},
            {"question": "Would you rather dance or sing?", "option_a": "Dance", "option_b": "Sing"},
        ],
    })

    assert config["game_title"] == "Party Choices"
    assert config["round_count"] == 3
    assert config["prompts"][0]["option_a"] == "Snacks"


def test_vote_reveal_scores_majority_and_redacts_before_reveal():
    state = create_initial_state(
        ["alice", "bob", "cara"],
        {
            "prompts": [
                {"question": "Would you rather teleport or fly?", "option_a": "Teleport", "option_b": "Fly"},
                {"question": "Would you rather dance or sing?", "option_a": "Dance", "option_b": "Sing"},
                {"question": "Would you rather snacks or music?", "option_a": "Snacks", "option_b": "Music"},
            ],
        },
        now=100,
    )

    state = submit_vote(state, "alice", "A")
    state = submit_vote(state, "bob", "B")
    state = submit_vote(state, "cara", "A")

    public = public_state(state)
    assert public["phase"] == PHASE_VOTING
    assert public["submitted_votes"] == 3
    assert "votes" not in public
    assert public_state(state, viewer_id="alice")["your_vote"] == "A"

    state = reveal_round(state, now=120)

    assert state["phase"] == PHASE_REVEAL
    assert state["rounds"][0]["result"]["majority"] == "A"
    assert state["scores"]["alice"] == 1
    assert state["scores"]["cara"] == 1
    assert state["scores"]["bob"] == 0
    assert public_state(state)["votes"] == {"alice": "A", "bob": "B", "cara": "A"}


def test_tie_awards_no_majority_score():
    state = create_initial_state(["alice", "bob"], {}, now=100)
    state = submit_vote(state, "alice", "A")
    state = submit_vote(state, "bob", "B")
    state = reveal_round(state, now=120)

    assert state["rounds"][0]["result"]["tie"] is True
    assert state["scores"] == {"alice": 0, "bob": 0}


def test_vote_changes_can_be_disabled():
    state = create_initial_state(["alice"], {"allow_vote_changes": False})
    state = submit_vote(state, "alice", "A")

    with pytest.raises(ValueError, match="Vote changes"):
        submit_vote(state, "alice", "B")


def test_late_join_and_completion_flow():
    state = create_initial_state(["alice"], {}, now=100)
    state = add_player(state, "bob")
    assert state["players"] == ["alice", "bob"]
    state = submit_vote(state, "bob", "B")

    for _ in range(3):
        state = reveal_round(state)
        state = next_round(state)
        if state["phase"] != PHASE_PODIUM:
            state = submit_vote(state, "alice", "A")

    assert state["phase"] == PHASE_PODIUM
    assert state["completed_at"]
