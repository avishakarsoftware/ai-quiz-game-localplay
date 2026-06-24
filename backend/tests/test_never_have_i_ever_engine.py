import pytest

from never_have_i_ever_engine import (
    PHASE_ANSWERING,
    PHASE_PODIUM,
    PHASE_REVEAL,
    add_player,
    create_initial_state,
    next_round,
    public_state,
    reveal_round,
    submit_answer,
    validate_config,
)


def test_validate_config_sanitizes_prompts():
    config = validate_config({
        "game_title": "Clean Confessions",
        "safe_level": "work",
        "prompts": [
            {"statement": "Never have I ever joined a meeting on mute."},
            {"statement": "Never have I ever eaten cake for breakfast."},
            {"statement": "Never have I ever laughed during a serious moment."},
        ],
    })

    assert config["game_title"] == "Clean Confessions"
    assert config["safe_level"] == "work"
    assert config["round_count"] == 3


def test_answer_reveal_scores_minority_and_redacts_before_reveal():
    state = create_initial_state(
        ["alice", "bob", "cara"],
        {
            "scoring_mode": "minority",
            "prompts": [
                {"statement": "Never have I ever sung karaoke in public."},
                {"statement": "Never have I ever forgotten why I walked into a room."},
                {"statement": "Never have I ever laughed at the worst possible moment."},
            ],
        },
        now=100,
    )

    state = submit_answer(state, "alice", "have")
    state = submit_answer(state, "bob", "never")
    state = submit_answer(state, "cara", "never")

    public = public_state(state)
    assert public["phase"] == PHASE_ANSWERING
    assert public["submitted_answers"] == 3
    assert "answers" not in public
    assert public_state(state, viewer_id="alice")["your_answer"] == "have"

    state = reveal_round(state, now=120)

    assert state["phase"] == PHASE_REVEAL
    assert state["rounds"][0]["result"]["minority"] == "have"
    assert state["scores"] == {"alice": 1, "bob": 0, "cara": 0}
    assert public_state(state)["answers"] == {"alice": "have", "bob": "never", "cara": "never"}


def test_tie_awards_no_minority_score():
    state = create_initial_state(["alice", "bob"], {"scoring_mode": "minority"}, now=100)
    state = submit_answer(state, "alice", "have")
    state = submit_answer(state, "bob", "never")
    state = reveal_round(state)

    assert state["rounds"][0]["result"]["tie"] is True
    assert state["scores"] == {"alice": 0, "bob": 0}


def test_answer_changes_can_be_disabled():
    state = create_initial_state(["alice"], {"allow_answer_changes": False})
    state = submit_answer(state, "alice", "have")

    with pytest.raises(ValueError, match="Answer changes"):
        submit_answer(state, "alice", "never")


def test_late_join_and_completion_flow():
    state = create_initial_state(["alice"], {}, now=100)
    state = add_player(state, "bob")
    assert state["players"] == ["alice", "bob"]

    for _ in range(3):
        state = submit_answer(state, "alice", "never")
        state = reveal_round(state)
        state = next_round(state)

    assert state["phase"] == PHASE_PODIUM
    assert state["completed_at"]
