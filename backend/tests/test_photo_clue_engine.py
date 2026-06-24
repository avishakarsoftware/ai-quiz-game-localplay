import pytest

from photo_clue_engine import (
    PHASE_GUESSING,
    PHASE_PODIUM,
    PHASE_REVEAL,
    PHASE_WAITING_FOR_PHOTO,
    create_initial_state,
    next_round,
    private_prompt_for_player,
    public_state,
    reveal_round,
    submit_guess,
    submit_photo,
    validate_config,
)


def test_validate_config_sanitizes_prompt_pack():
    config = validate_config({
        "game_title": "Birthday Snaps",
        "prompts": [
            {"answer": "Birthday Cake", "aliases": ["cake"], "category": "party"},
            {"answer": "Party Lights"},
            {"answer": "Dancing Shoes"},
        ],
    })

    assert config["game_title"] == "Birthday Snaps"
    assert config["round_count"] == 3
    assert config["prompts"][0]["answer"] == "Birthday Cake"


def test_photo_clue_round_flow_scores_guessers_and_clue_giver():
    state = create_initial_state(
        ["alice", "bob"],
        {
            "prompts": [
                {"answer": "Birthday Cake", "aliases": ["cake"]},
                {"answer": "Party Lights"},
                {"answer": "Dancing Shoes"},
            ],
            "correct_guess_points": 100,
            "clue_giver_points": 40,
        },
        now=100,
    )

    assert state["phase"] == PHASE_WAITING_FOR_PHOTO
    assert private_prompt_for_player(state, "alice")[0]["prompt"]["answer"] == "Birthday Cake"
    assert public_state(state)["answer"] == ""

    state = submit_photo(state, "alice", "asset_1", "/media/asset_1", now=110)
    assert state["phase"] == PHASE_GUESSING
    assert public_state(state)["image_url"] == "/media/asset_1"

    state, correct = submit_guess(state, "bob", "cake", now=120)
    assert correct is True
    assert state["scores"]["bob"] == 100
    assert state["scores"]["alice"] == 40

    state = reveal_round(state)
    assert state["phase"] == PHASE_REVEAL
    assert public_state(state)["answer"] == "Birthday Cake"

    state = next_round(state, now=130)
    assert state["phase"] == PHASE_WAITING_FOR_PHOTO
    assert state["current_round_index"] == 1


def test_photo_clue_rejects_wrong_actor_and_self_guess():
    state = create_initial_state(["alice", "bob"], {}, now=100)

    with pytest.raises(ValueError, match="Only the clue giver"):
        submit_photo(state, "bob", "asset_1")

    state = submit_photo(state, "alice", "asset_1")
    with pytest.raises(ValueError, match="cannot guess"):
        submit_guess(state, "alice", "cake")


def test_photo_clue_completes_after_last_reveal():
    state = create_initial_state(["alice", "bob"], {
        "prompts": [
            {"answer": "One"},
            {"answer": "Two"},
            {"answer": "Three"},
        ],
    }, now=100)
    for index in range(3):
        giver = "alice" if index in (0, 2) else "bob"
        state = submit_photo(state, giver, f"asset_{index}")
        state = reveal_round(state)
        state = next_round(state, now=200 + index)

    assert state["phase"] == PHASE_PODIUM
    assert state["completed_at"]
