import pytest

from two_truths_engine import (
    PHASE_PODIUM,
    PHASE_RESULT,
    PHASE_SUBMISSION,
    PHASE_VOTING,
    create_initial_state,
    private_sync,
    public_sync,
    score_current_round,
    start_reveal,
    submit_statements,
    submit_vote,
    validate_config,
    validate_submission,
)


def sample_submission(lie_index: int = 2):
    return [
        {"text": "I once sang karaoke in public.", "is_lie": lie_index == 0},
        {"text": "I have visited three countries.", "is_lie": lie_index == 1},
        {"text": "I can solve a cube blindfolded.", "is_lie": lie_index == 2},
    ]


def test_validate_config_clamps_timing_and_title():
    config = validate_config({"game_title": " Confessions ", "submission_time_seconds": 10, "vote_time_seconds": 999})

    assert config["game_title"] == "Confessions"
    assert config["submission_time_seconds"] == 60
    assert config["vote_time_seconds"] == 90


def test_validate_submission_requires_three_unique_statements_and_one_lie():
    statements = validate_submission(sample_submission())

    assert len(statements) == 3
    assert sum(1 for item in statements if item["is_lie"]) == 1

    with pytest.raises(ValueError):
        validate_submission(sample_submission()[:2])
    with pytest.raises(ValueError):
        validate_submission([
            {"text": "This statement is duplicated.", "is_lie": True},
            {"text": "This statement is duplicated.", "is_lie": False},
            {"text": "This third one is different.", "is_lie": False},
        ])


def test_validate_submission_accepts_short_party_statements():
    statements = validate_submission([
        {"text": "Hehe", "is_lie": False},
        {"text": "Motu", "is_lie": False},
        {"text": "Pakalu", "is_lie": True},
    ])

    assert [item["text"] for item in statements] == ["Hehe", "Motu", "Pakalu"]


def test_flow_hides_answers_until_result_and_scores_votes():
    state = create_initial_state(["Avi", "Ruchi", "Maya"], validate_config({}), seed=1)
    state = submit_statements(state, "Avi", sample_submission(lie_index=1), now=1)
    state = submit_statements(state, "Ruchi", sample_submission(lie_index=2), now=1)

    assert state["phase"] == PHASE_SUBMISSION

    state = start_reveal(state)
    assert state["phase"] == PHASE_VOTING
    public = public_sync(state)
    assert all("is_lie" not in item for item in public["statements"])

    author = state["current_author_id"]
    lie_id = next(item["id"] for item in state["submissions_by_player"][author]["statements"] if item["is_lie"])
    voter = "Ruchi" if author == "Avi" else "Avi"
    state = submit_vote(state, voter, lie_id)
    state = score_current_round(state)

    assert state["phase"] == PHASE_RESULT
    assert state["scores"][voter] == 500
    public = public_sync(state)
    assert any(item.get("is_lie") for item in public["statements"])
    private = private_sync(state, voter)
    assert private["my_vote"] == lie_id


def test_author_cannot_vote():
    state = create_initial_state(["Avi", "Ruchi", "Maya"], validate_config({}), seed=1)
    state = submit_statements(state, "Avi", sample_submission(), now=1)
    state = start_reveal(state)

    with pytest.raises(ValueError):
        submit_vote(state, state["current_author_id"], "stmt_1")
