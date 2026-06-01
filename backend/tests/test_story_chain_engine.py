import pytest

from story_chain_engine import (
    PHASE_PODIUM,
    PHASE_REVEAL,
    PHASE_TURN,
    create_initial_state,
    create_turn_order,
    next_reveal_step,
    private_sync,
    public_sync,
    submit_sentence,
    timeout_turn,
    validate_config,
)


def test_validate_config_clamps_and_defaults():
    config = validate_config({
        "starter_prompt": "Hi",
        "visibility_mode": "hidden_chain",
        "turn_time_seconds": 5,
        "sentence_max_chars": 999,
    })

    assert config["starter_prompt"] == "The birthday cake started glowing at midnight."
    assert config["visibility_mode"] == "last_sentence_only"
    assert config["turn_time_seconds"] == 20
    assert config["sentence_max_chars"] == 280


def test_turn_order_is_deterministic():
    players = ["Alice", "Bob", "Cara", "Dee"]

    assert create_turn_order(players, seed="room") == create_turn_order(players, seed="room")


def test_private_payload_respects_last_sentence_only():
    state = create_initial_state(
        ["Alice", "Bob", "Cara"],
        {"starter_prompt": "A suitcase started singing.", "visibility_mode": "last_sentence_only"},
        now=100,
        seed=1,
    )
    active = state["active_player_id"]
    state = submit_sentence(state, active, "The first song was about missing socks.", now=101)
    next_active = state["active_player_id"]

    sync = private_sync(state, next_active)
    assert sync["is_active"] is True
    assert sync["visible_context"] == ["The first song was about missing socks."]
    assert public_sync(state)["sentences"] == []


def test_full_context_shows_all_previous_sentences_to_active_player():
    state = create_initial_state(
        ["Alice", "Bob", "Cara"],
        {"visibility_mode": "full_context"},
        now=100,
        seed=2,
    )
    state = submit_sentence(state, state["active_player_id"], "The cake hummed a suspicious tune.", now=101)
    state = submit_sentence(state, state["active_player_id"], "Then everyone grabbed a fork and waited.", now=102)

    sync = private_sync(state, state["active_player_id"])
    assert sync["visible_context"] == [
        "The cake hummed a suspicious tune.",
        "Then everyone grabbed a fork and waited.",
    ]


def test_only_active_player_can_submit():
    state = create_initial_state(["Alice", "Bob", "Cara"], {}, now=100, seed=3)
    inactive = next(name for name in state["turn_order"] if name != state["active_player_id"])

    with pytest.raises(ValueError, match="not your turn"):
        submit_sentence(state, inactive, "I should not be allowed to write.", now=101)


def test_timeout_adds_placeholder_and_reveal_steps_to_podium():
    state = create_initial_state(["Alice", "Bob", "Cara"], {}, now=100, seed=4)
    for _ in range(3):
        state = timeout_turn(state, now=101)

    assert state["phase"] == PHASE_REVEAL
    assert len(state["sentences"]) == 3

    state = next_reveal_step(state)
    assert state["phase"] == PHASE_REVEAL
    assert len(public_sync(state)["sentences"]) == 1
    state = next_reveal_step(state)
    state = next_reveal_step(state)
    state = next_reveal_step(state)
    assert state["phase"] == PHASE_PODIUM


def test_valid_submission_scores_player_and_advances_turn():
    state = create_initial_state(["Alice", "Bob", "Cara"], {}, now=100, seed=5)
    active = state["active_player_id"]
    state = submit_sentence(state, active, "The dragon politely asked for directions.", now=101)

    assert state["phase"] == PHASE_TURN
    assert state["scores"][active] == 125
    assert state["active_player_id"] != active
