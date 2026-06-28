from party_quests_engine import (
    PHASE_ACTIVE,
    PHASE_FINAL_CALL,
    PHASE_PODIUM,
    PHASE_REVEAL,
    add_player,
    apply_confirmation,
    complete,
    create_confirmation_request,
    create_initial_state,
    private_sync,
    public_sync,
    reveal,
    start_final_call,
    validate_config,
)
from main import PartyQuestsGenerateRequest, _normalize_party_quests_generated


def test_validate_config_adds_default_quests_and_clamps_settings():
    config = validate_config({
        "game_title": "<b>Party</b>",
        "quests": ["Meet someone new"],
        "quests_per_player": 50,
        "duration_minutes": 5,
        "confirmation_mode": "weird",
    })

    assert config["game_title"] == "Party"
    assert config["confirmation_mode"] == "tap_confirm"
    assert config["duration_minutes"] == 10
    assert config["quests_per_player"] <= 25
    assert len(config["quests"]) >= config["quests_per_player"]


def test_confirmation_flow_scores_requester():
    state = create_initial_state(
        ["Avi", "Ruchi"],
        {"quests": ["Find someone who likes cake", "Meet someone who sings", "Ask for a song"], "quests_per_player": 3},
        now=1000,
        seed="fixed",
    )
    quest_id = state["quest_boards_by_player"]["Avi"][0]["quest_id"]

    state, request = create_confirmation_request(state, "Avi", quest_id, "Ruchi", now=1010)
    assert request
    assert state["quest_boards_by_player"]["Avi"][0]["status"] == "pending_confirmation"

    state, result = apply_confirmation(state, request["id"], "Ruchi", True, now=1020)

    assert result["accepted"] is True
    assert state["quest_boards_by_player"]["Avi"][0]["status"] == "confirmed"
    assert state["scores"]["Avi"] > 0
    assert state["scores"].get("Ruchi", 0) == 0


def test_denied_confirmation_reopens_quest():
    state = create_initial_state(["Avi", "Ruchi"], {"quests_per_player": 3}, now=1000, seed="fixed")
    quest_id = state["quest_boards_by_player"]["Avi"][0]["quest_id"]
    state, request = create_confirmation_request(state, "Avi", quest_id, "Ruchi", now=1010)

    state, result = apply_confirmation(state, request["id"], "Ruchi", False, now=1020)

    assert result["accepted"] is False
    assert state["quest_boards_by_player"]["Avi"][0]["status"] == "open"
    assert len(state["denied_confirmations"]) == 1


def test_late_join_gets_board_during_active_phase():
    state = create_initial_state(["Avi"], {"quests_per_player": 3, "allow_late_join": True}, now=1000, seed="fixed")

    state = add_player(state, "Ruchi", now=1030)

    assert "Ruchi" in state["quest_boards_by_player"]
    assert len(state["quest_boards_by_player"]["Ruchi"]) == 3


def test_public_and_private_sync_separate_private_board():
    state = create_initial_state(["Avi", "Ruchi"], {"quests_per_player": 3}, now=1000, seed="fixed")
    players = [{"nickname": "Avi", "avatar": "🐯"}, {"nickname": "Ruchi", "avatar": "🎱"}]

    public = public_sync(state, players)
    private = private_sync(state, "Avi", players)

    assert public["players"][0]["nickname"] == "Avi"
    assert "my_board" not in public
    assert len(private["my_board"]) == 3


def test_final_reveal_and_complete_phases():
    state = create_initial_state(["Avi", "Ruchi"], {"quests_per_player": 3}, now=1000, seed="fixed")

    state = start_final_call(state, now=1100)
    assert state["phase"] == PHASE_FINAL_CALL

    state = reveal(state, now=1160)
    assert state["phase"] == PHASE_REVEAL

    state = complete(state, now=1200)
    assert state["phase"] == PHASE_PODIUM
    assert state["completed_at"] == 1200


def test_honor_mode_confirms_without_pending_request():
    state = create_initial_state(["Avi", "Ruchi"], {"quests_per_player": 3, "confirmation_mode": "honor"}, now=1000, seed="fixed")
    quest_id = state["quest_boards_by_player"]["Avi"][0]["quest_id"]

    state, request = create_confirmation_request(state, "Avi", quest_id, "Ruchi", now=1010)

    assert request is None
    assert state["quest_boards_by_player"]["Avi"][0]["status"] == "confirmed"
    assert state["phase"] == PHASE_ACTIVE


def test_generated_party_quests_are_normalized_for_review():
    request = PartyQuestsGenerateRequest(
        prompt="family birthday",
        theme="birthday",
        num_quests=5,
        quests_per_player=3,
    )
    result = _normalize_party_quests_generated({
        "game_title": "Birthday Quest Block",
        "quests": [
            {"display": "Find someone who can recommend a party song.", "points": 100},
            {"display": "Ask someone for a tiny toast idea.", "points": 100},
            {"display": "Meet someone who knows the guest of honor well.", "points": 150},
            {"display": "Find someone wearing a bright color.", "points": 100},
            {"display": "Ask someone about a favorite dessert.", "points": 100},
        ],
    }, request)

    assert result["game_title"] == "Birthday Quest Block"
    assert result["theme"] == "birthday"
    assert result["quests_per_player"] == 3
    assert [quest["id"] for quest in result["quests"]] == ["quest_1", "quest_2", "quest_3", "quest_4", "quest_5"]
    assert result["quests"][2]["points"] == 150
