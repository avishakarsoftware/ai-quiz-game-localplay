import pytest

from find_someone_engine import (
    PHASE_PODIUM,
    claim_pattern,
    confirm_match,
    create_initial_state,
    mark_cell,
    private_sync,
    validate_config,
)


def _first_prompt(card):
    return next(cell for row in card["cells"] for cell in row if not cell.get("free"))


def test_validate_config_supports_first_guest_checkin_defaults():
    config = validate_config({})

    assert config["layout"] == "bingo_5x5_free"
    assert config["confirmation_mode"] == "tap_confirm"
    assert len(config["prompts"]) >= 24
    assert [pattern["id"] for pattern in config["claim_patterns"]] == ["first_line", "four_corners", "blackout"]
    assert config["default_for_checkin"] is False
    assert config["auto_start_on_first_checkin"] is True
    assert config["checkin_join_policy"] == "resume_or_join"


def test_validate_config_preserves_checkin_overrides():
    config = validate_config({
        "default_for_checkin": True,
        "auto_start_on_first_checkin": False,
        "checkin_join_policy": "host_started_only",
    })

    assert config["default_for_checkin"] is True
    assert config["auto_start_on_first_checkin"] is False
    assert config["checkin_join_policy"] == "host_started_only"


def test_mark_cell_requires_matched_player_confirmation():
    state = create_initial_state(["Avi", "Ruchi"], validate_config({}), now=1000, seed=1)
    prompt_id = _first_prompt(state["cards_by_player"]["Avi"])["prompt_id"]

    state, request = mark_cell(state, "Avi", prompt_id, "Ruchi", now=1001)

    assert request is not None
    assert private_sync(state, "Ruchi")["my_pending_confirmations"][0]["id"] == request["id"]

    state = confirm_match(state, "Ruchi", request["id"], True, now=1002)
    cell = _first_prompt(state["cards_by_player"]["Avi"])
    assert cell["marked"] is True
    assert cell["confirmation_status"] == "confirmed"


def test_same_matched_player_cannot_fill_multiple_cells_by_default():
    state = create_initial_state(["Avi", "Ruchi"], validate_config({"confirmation_mode": "honor"}), now=1000, seed=2)
    cells = [cell for row in state["cards_by_player"]["Avi"]["cells"] for cell in row if not cell.get("free")]

    state, _ = mark_cell(state, "Avi", cells[0]["prompt_id"], "Ruchi", now=1001)

    with pytest.raises(ValueError, match="Use each person only once"):
        mark_cell(state, "Avi", cells[1]["prompt_id"], "Ruchi", now=1002)


def test_blackout_claim_moves_game_to_podium():
    config = validate_config({
        "layout": "bingo_4x4",
        "confirmation_mode": "honor",
        "allow_same_person_multiple_cells": True,
    })
    state = create_initial_state(["Avi", "Ruchi"], config, now=1000, seed=3)
    for cell in [cell for row in state["cards_by_player"]["Avi"]["cells"] for cell in row]:
        state, _ = mark_cell(state, "Avi", cell["prompt_id"], "Ruchi", now=1001)

    state, claim = claim_pattern(state, "Avi", "blackout", now=1002)

    assert claim["pattern_label"] == "Blackout"
    assert state["phase"] == PHASE_PODIUM
