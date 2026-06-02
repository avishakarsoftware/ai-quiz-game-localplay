import pytest

from common_ground_engine import (
    PHASE_DISCUSSION,
    PHASE_PODIUM,
    PHASE_REVEAL,
    PHASE_ROUND_RESULT,
    PHASE_VOTING,
    create_initial_state,
    final_standings,
    private_sync,
    public_sync,
    score_round,
    start_reveal,
    start_voting,
    submit_fact,
    submit_vote,
    validate_config,
    next_round,
)


def test_validate_config_clamps_and_prepares_prompts():
    config = validate_config({
        "game_title": "<script>Bad</script>Common Ground",
        "team_size": 99,
        "rounds": 12,
        "discussion_time_seconds": 5,
        "vote_time_seconds": 5,
        "vote_category": "wildest",
        "prompts": ["Find one food everyone likes."],
    })

    assert config["game_title"] == "BadCommon Ground"
    assert config["team_size"] == 6
    assert config["rounds"] == 10
    assert config["discussion_time_seconds"] == 30
    assert config["vote_time_seconds"] == 10
    assert config["vote_category"] == "most_surprising"
    assert len(config["prompts"]) == 10


def test_submit_fact_auto_reveals_when_all_teams_are_ready():
    state = create_initial_state(["Alice", "Bob", "Cara", "Dee"], {"team_size": 2, "rounds": 1}, now=100, seed=1)

    assert state["phase"] == PHASE_DISCUSSION
    assert len(state["teams"]) == 2
    team_a_player = state["teams"][0]["player_ids"][0]
    team_b_player = state["teams"][1]["player_ids"][0]

    state = submit_fact(state, team_a_player, "We all like mangoes.", now=101)
    assert state["phase"] == PHASE_DISCUSSION

    state = submit_fact(state, team_b_player, "We all enjoy beach trips.", now=102)
    assert state["phase"] == PHASE_REVEAL
    assert all(item["has_submission"] for item in public_sync(state)["submissions"])


def test_discussion_sync_hides_other_team_text_but_keeps_own_submission_private():
    state = create_initial_state(["Alice", "Bob", "Cara", "Dee"], {"team_size": 2}, now=100, seed=2)
    alice = state["teams"][0]["player_ids"][0]

    state = submit_fact(state, alice, "We all have watched cricket.", now=101)
    public = public_sync(state)
    private = private_sync(state, alice)

    assert "text" not in public["submissions"][0]
    assert private["my_submission"]["text"] == "We all have watched cricket."


def test_voting_rejects_own_team_and_scores_round():
    state = create_initial_state(["Alice", "Bob", "Cara", "Dee"], {"team_size": 2, "rounds": 1}, now=100, seed=3)
    team_one, team_two = state["teams"]
    state = submit_fact(state, team_one["player_ids"][0], "We all prefer window seats.", now=101)
    state = submit_fact(state, team_two["player_ids"][0], "We all own blue shirts.", now=102)
    state = start_voting(start_reveal(state), now=103)

    own_submission = state["submissions"][team_one["id"]]["id"]
    other_submission = state["submissions"][team_two["id"]]["id"]
    with pytest.raises(ValueError, match="another team"):
        submit_vote(state, team_one["player_ids"][0], own_submission)

    state = submit_vote(state, team_one["player_ids"][0], other_submission)
    state = score_round(state, now=104)

    assert state["phase"] == PHASE_ROUND_RESULT
    assert state["scores"][team_two["id"]] > state["scores"][team_one["id"]]


def test_next_round_resets_round_inputs_then_podiums_after_final_round():
    state = create_initial_state(["Alice", "Bob", "Cara", "Dee"], {"team_size": 2, "rounds": 2}, now=100, seed=4)
    for team in state["teams"]:
        state = submit_fact(state, team["player_ids"][0], f"{team['name']} shared fact", now=101)
    state = score_round(state, now=102)

    state = next_round(state, now=103)
    assert state["phase"] == PHASE_DISCUSSION
    assert state["round_index"] == 1
    assert state["submissions"] == {}
    assert state["votes_by_player"] == {}

    for team in state["teams"]:
        state = submit_fact(state, team["player_ids"][0], f"{team['name']} final fact", now=104)
    state = score_round(state, now=105)
    state = next_round(state, now=106)

    assert state["phase"] == PHASE_PODIUM
    assert final_standings(state)
