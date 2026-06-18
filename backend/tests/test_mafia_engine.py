import pytest

from mafia_engine import (
    PHASE_DAY_DISCUSSION,
    PHASE_DAY_VOTE,
    PHASE_NIGHT,
    PHASE_PODIUM,
    PHASE_ROLE_REVEAL,
    PHASE_VOTE_RESULT,
    advance_after_role_reveal,
    advance_after_vote_result,
    all_living_votes_submitted,
    all_required_night_actions_submitted,
    create_initial_state,
    private_sync,
    public_sync,
    resolve_night,
    resolve_vote,
    result_summary,
    role_distribution,
    start_day_vote,
    submit_night_action,
    submit_night_read,
    submit_vote,
    validate_config,
)


def _state_with_roles(roles: dict[str, str]):
    state = create_initial_state(list(roles), {"night_timer_seconds": 30}, seed="roles", now=100)
    for player in state["players"]:
        player["role"] = roles[player["id"]]
        player["team"] = "mafia" if player["role"] == "mafia" else "town"
    return state


def _day_vote_after_saved_night(state):
    state = advance_after_role_reveal(state, now=110)
    state = submit_night_action(state, "Maf", "A")
    state = submit_night_action(state, "Doctor", "A")
    for voter in ["Maf", "Detective", "Doctor", "A", "B", "C"]:
        state = submit_night_read(state, voter, "Maf" if voter != "Maf" else "A")
    return start_day_vote(resolve_night(state, now=120), now=130)


def test_validate_config_clamps_and_sanitizes():
    config = validate_config({
        "game_title": "<script>Bad</script> Mystery",
        "theme": "bad",
        "night_timer_seconds": 5,
        "discussion_timer_seconds": 999,
        "vote_timer_seconds": "bad",
        "role_reveal_seconds": 1,
        "tie_behavior": "bad",
    })

    assert config["game_title"] == "Bad Mystery"
    assert config["theme"] == "classic"
    assert config["night_timer_seconds"] == 15
    assert config["discussion_timer_seconds"] == 180
    assert config["vote_timer_seconds"] == 30
    assert config["role_reveal_seconds"] == 5
    assert config["tie_behavior"] == "no_elimination"


def test_role_distribution_table_and_disabled_roles():
    assert role_distribution(6) == {"mafia": 1, "detective": 1, "doctor": 1, "villager": 3}
    assert role_distribution(10) == {"mafia": 3, "detective": 1, "doctor": 1, "villager": 5}
    assert role_distribution(7, include_detective=False, include_doctor=False) == {
        "mafia": 2,
        "detective": 0,
        "doctor": 0,
        "villager": 5,
    }
    with pytest.raises(ValueError, match="6 to 15"):
        role_distribution(5)


def test_seeded_assignment_is_stable_and_rejects_bad_counts():
    first = create_initial_state([f"p{i}" for i in range(6)], seed="same", now=100)
    second = create_initial_state([f"p{i}" for i in range(6)], seed="same", now=100)

    assert [p["role"] for p in first["players"]] == [p["role"] for p in second["players"]]
    assert first["phase"] == PHASE_ROLE_REVEAL

    with pytest.raises(ValueError, match="6 to 15"):
        create_initial_state(["a", "b", "c"])
    with pytest.raises(ValueError, match="unique"):
        create_initial_state(["a", "a", "b", "c", "d", "e"])


def test_night_resolution_kills_when_doctor_does_not_save():
    state = _state_with_roles({
        "Maf": "mafia",
        "Detective": "detective",
        "Doctor": "doctor",
        "A": "villager",
        "B": "villager",
        "C": "villager",
    })
    state = advance_after_role_reveal(state, now=110)
    state = submit_night_action(state, "Maf", "A")
    state = submit_night_action(state, "Detective", "Maf")
    state = submit_night_action(state, "Doctor", "B")
    for voter in ["Maf", "Detective", "Doctor", "A", "B", "C"]:
        state = submit_night_read(state, voter, "Maf" if voter != "Maf" else "A")

    state = resolve_night(state, now=120)

    assert state["phase"] == PHASE_DAY_DISCUSSION
    assert state["night_log"][-1]["killed"] == "A"
    assert state["night_log"][-1]["killed_role"] == "villager"
    assert next(p for p in state["players"] if p["id"] == "A")["alive"] is False
    detective = private_sync(state, "Detective")
    assert detective["my_investigations"] == [{"round": 1, "target": "Maf", "result": "mafia"}]


def test_doctor_save_prevents_kill_and_public_sync_hides_private_details():
    state = _state_with_roles({
        "Maf": "mafia",
        "Detective": "detective",
        "Doctor": "doctor",
        "A": "villager",
        "B": "villager",
        "C": "villager",
    })
    state = advance_after_role_reveal(state, now=110)
    state = submit_night_action(state, "Maf", "A")
    state = submit_night_action(state, "Doctor", "A")
    for voter in ["Maf", "Detective", "Doctor", "A", "B", "C"]:
        state = submit_night_read(state, voter, "Maf" if voter != "Maf" else "A")
    state = resolve_night(state, now=120)

    public = public_sync(state)

    assert state["night_log"][-1]["saved"] is True
    assert all(player["alive"] for player in state["players"])
    assert "saved" not in public["last_night"]
    assert "mafia_target" not in public["last_night"]
    assert all(player["role"] is None for player in public["players"])
    assert public["last_night"]["night_read_highlights"]


def test_night_action_validation_and_private_mafia_teammates():
    state = _state_with_roles({
        "Maf1": "mafia",
        "Maf2": "mafia",
        "Detective": "detective",
        "Doctor": "doctor",
        "A": "villager",
        "B": "villager",
        "C": "villager",
    })
    state = advance_after_role_reveal(state, now=110)

    with pytest.raises(ValueError, match="Invalid"):
        submit_night_action(state, "Maf1", "Maf2")
    with pytest.raises(ValueError, match="Invalid"):
        submit_night_action(state, "Detective", "Detective")

    private = private_sync(state, "Maf1")
    assert private["my_action"]["kind"] == "mafia_kill"
    assert private["my_action"]["mafia_teammates"] == ["Maf2"]
    assert "Detective" in private["my_action"]["eligible_targets"]


def test_vote_majority_eliminates_and_tie_skips_elimination():
    state = _state_with_roles({
        "Maf": "mafia",
        "Detective": "detective",
        "Doctor": "doctor",
        "A": "villager",
        "B": "villager",
        "C": "villager",
    })
    state = _day_vote_after_saved_night(state)
    for voter in ["Maf", "Detective", "Doctor", "B"]:
        state = submit_vote(state, voter, "A")
    for voter in ["A", "C"]:
        state = submit_vote(state, voter, "skip")
    state = resolve_vote(state, now=140)

    assert state["phase"] == PHASE_VOTE_RESULT
    assert state["vote_log"][-1]["eliminated"] == "A"
    assert next(p for p in state["players"] if p["id"] == "A")["alive"] is False
    assert public_sync(state)["players"][3]["role"] == "villager"

    tie_state = _state_with_roles({
        "Maf": "mafia",
        "Detective": "detective",
        "Doctor": "doctor",
        "A": "villager",
        "B": "villager",
        "C": "villager",
    })
    tie_state = _day_vote_after_saved_night(tie_state)
    tie_state = submit_vote(tie_state, "Maf", "A")
    tie_state = submit_vote(tie_state, "Detective", "B")
    tie_state = submit_vote(tie_state, "Doctor", "A")
    tie_state = submit_vote(tie_state, "A", "B")
    tie_state = submit_vote(tie_state, "B", "skip")
    tie_state = submit_vote(tie_state, "C", "skip")
    tie_state = resolve_vote(tie_state, now=140)

    assert tie_state["vote_log"][-1]["tied"] is True
    assert tie_state["vote_log"][-1]["eliminated"] is None


def test_win_conditions_and_result_summary_are_safe():
    town_win = _state_with_roles({
        "Maf": "mafia",
        "Detective": "detective",
        "Doctor": "doctor",
        "A": "villager",
        "B": "villager",
        "C": "villager",
    })
    town_win = _day_vote_after_saved_night(town_win)
    for voter in ["Detective", "Doctor", "A", "B"]:
        town_win = submit_vote(town_win, voter, "Maf")
    town_win = resolve_vote(town_win, now=140)

    assert town_win["phase"] == PHASE_PODIUM
    assert town_win["winner"] == "town"
    summary = result_summary(town_win)
    assert summary["winner"] == "town"
    assert "mafia_target" not in str(summary)
    assert "detective_result" not in str(summary)

    mafia_win = _state_with_roles({
        "Maf1": "mafia",
        "Maf2": "mafia",
        "Maf3": "mafia",
        "Detective": "detective",
        "Doctor": "doctor",
        "A": "villager",
    })
    mafia_win = advance_after_role_reveal(mafia_win, now=110)
    mafia_win = submit_night_action(mafia_win, "Maf1", "A")
    mafia_win = submit_night_action(mafia_win, "Maf2", "A")
    mafia_win = submit_night_action(mafia_win, "Maf3", "A")
    mafia_win = resolve_night(mafia_win, now=120)

    assert mafia_win["winner"] == "mafia"
    assert mafia_win["phase"] == PHASE_PODIUM


def test_progress_helpers():
    state = _state_with_roles({
        "Maf": "mafia",
        "Detective": "detective",
        "Doctor": "doctor",
        "A": "villager",
        "B": "villager",
        "C": "villager",
    })
    state = advance_after_role_reveal(state, now=110)
    assert all_required_night_actions_submitted(state) is False
    state = submit_night_action(state, "Maf", "A")
    state = submit_night_action(state, "Detective", "Maf")
    state = submit_night_action(state, "Doctor", "B")
    assert all_required_night_actions_submitted(state) is False
    for voter in ["Maf", "Detective", "Doctor", "A", "B", "C"]:
        state = submit_night_read(state, voter, "Maf" if voter != "Maf" else "A")
    assert all_required_night_actions_submitted(state) is True

    state = submit_night_action(state, "Maf", "A")
    state = submit_night_action(state, "Doctor", "A")
    state = start_day_vote(resolve_night(state, now=120), now=130)
    assert all_living_votes_submitted(state) is False
    for voter in ["Maf", "Detective", "Doctor", "A", "B", "C"]:
        state = submit_vote(state, voter, "skip")
    assert all_living_votes_submitted(state) is True

    state = resolve_vote(state, now=140)
    assert advance_after_vote_result(state, now=150)["phase"] in {PHASE_NIGHT, PHASE_PODIUM}
