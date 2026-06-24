import pytest

from survey_says_engine import (
    PHASE_ANSWERING,
    PHASE_PODIUM,
    PHASE_REVEAL,
    PHASE_STEAL,
    add_player,
    add_strike,
    create_initial_state,
    next_round,
    public_sync,
    reveal_answer,
    standings,
    submit_guess,
    validate_config,
)


def test_validate_config_sanitizes_rounds_and_clamps_values():
    config = validate_config({
        "game_title": "<b>Survey</b>",
        "round_count": 99,
        "max_strikes": 99,
        "guess_time_seconds": 1,
        "rounds": [
            {
                "question": "Name a party snack people reach for first.",
                "answers": [
                    {"text": "Chips", "points": 40, "aliases": ["crisps"]},
                    {"text": "Cake", "points": 30},
                    {"text": "Pizza", "points": 20},
                ],
            }
        ],
    })

    assert config["game_title"] == "Survey"
    assert config["round_count"] == 1
    assert config["max_strikes"] == 5
    assert config["guess_time_seconds"] == 10
    assert config["rounds"][0]["answers"][0]["aliases"] == ["crisps"]


def test_answer_reveal_builds_bank_and_scores_when_board_is_cleared():
    state = create_initial_state(["Avi", "Ruchi"], {
        "rounds": [{
            "question": "Name a color.",
            "answers": [
                {"id": "red", "text": "Red", "points": 40},
                {"id": "blue", "text": "Blue", "points": 30},
                {"id": "green", "text": "Green", "points": 20},
            ],
        }],
    }, now=100)

    state = reveal_answer(state, "red", now=101)
    assert state["phase"] == PHASE_ANSWERING
    assert state["round_bank"] == 40

    state = reveal_answer(state, "blue", now=102)
    state = reveal_answer(state, "green", now=103)

    assert state["phase"] == PHASE_REVEAL
    assert state["scores"][state["active_team_id"]] == 90
    assert standings(state)[0]["score"] == 90


def test_three_strikes_move_to_steal_and_failed_steal_awards_active_team():
    state = create_initial_state(["Avi", "Ruchi", "Ashu", "Maya"], {}, now=100)
    active_team = state["active_team_id"]

    state = reveal_answer(state, state["config"]["rounds"][0]["answers"][0]["id"], now=101)
    state = add_strike(state, now=102)
    state = add_strike(state, now=103)
    state = add_strike(state, now=104)

    assert state["phase"] == PHASE_STEAL
    assert state["stealing_team_id"] and state["stealing_team_id"] != active_team

    state = add_strike(state, now=105)

    assert state["phase"] == PHASE_REVEAL
    assert state["scores"][active_team] == state["round_bank"]


def test_successful_steal_awards_bank_to_stealing_team():
    state = create_initial_state(["Avi", "Ruchi", "Ashu", "Maya"], {}, now=100)
    state = reveal_answer(state, state["config"]["rounds"][0]["answers"][0]["id"], now=101)
    state = add_strike(add_strike(add_strike(state, now=102), now=103), now=104)
    stealing_team = state["stealing_team_id"]
    unrevealed = next(answer["id"] for answer in state["config"]["rounds"][0]["answers"] if answer["id"] not in state["revealed_answer_ids"])

    state = reveal_answer(state, unrevealed, now=105)

    assert state["phase"] == PHASE_REVEAL
    assert state["scores"][stealing_team] == state["round_bank"]


def test_player_guesses_are_private_but_host_sees_all_answers():
    state = create_initial_state(["Avi", "Ruchi"], {}, now=100)
    state = submit_guess(state, "Avi", "cake", now=101)

    player_view = public_sync(state, viewer_id="Ruchi")
    avi_view = public_sync(state, viewer_id="Avi")
    host_view = public_sync(state, host=True)

    assert player_view["guesses"] == []
    assert avi_view["guesses"][0]["guess"] == "cake"
    assert host_view["guesses"][0]["player_id"] == "Avi"
    assert host_view["answers"][0]["text"]
    assert not player_view["answers"][0]["text"]


def test_late_join_balances_teams_and_next_round_reaches_podium():
    state = create_initial_state(["Avi", "Ruchi"], {"round_count": 1}, now=100)
    state = add_player(state, "Ashu")

    assert "Ashu" in state["players"]
    assert sum(team["player_ids"].count("Ashu") for team in state["teams"]) == 1

    for answer in state["config"]["rounds"][0]["answers"]:
        if state["phase"] == PHASE_ANSWERING:
            state = reveal_answer(state, answer["id"])

    state = next_round(state)
    assert state["phase"] == PHASE_PODIUM


def test_submit_guess_rejects_unknown_players():
    state = create_initial_state(["Avi", "Ruchi"], {}, now=100)
    with pytest.raises(ValueError, match="Unknown player"):
        submit_guess(state, "Ghost", "cake")
