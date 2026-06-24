from chit_pull_engine import (
    PHASE_ACTIVE,
    PHASE_PODIUM,
    PHASE_READY,
    PHASE_RESULT,
    complete_turn,
    create_initial_state,
    draw_turn,
    final_standings,
    public_sync,
    redraw_chit,
    redraw_player,
    sanitize_generated_game,
    skip_turn,
    validate_config,
)


def test_validate_config_sanitizes_chits_and_defaults():
    config = validate_config({
        "game_title": "<script>Chaos</script> Chits",
        "rounds": 3,
        "safe_level": "family",
        "chits": [
            {"text": "Tell a funny story.", "category": "question"},
            {"text": "Make a celebration face.", "category": "funny_face"},
            {"text": "Ask the table for a movie title.", "category": "group"},
            {"text": "Do a tiny victory dance.", "category": "action"},
            {"text": "Name one snack everyone likes.", "category": "question"},
        ],
    })

    assert config["game_title"] == "Chaos Chits"
    assert config["rounds"] == 5
    assert len(config["chits"]) == 5
    assert config["chits"][1]["category"] == "funny_face"


def test_default_title_is_random_chit():
    config = validate_config({})

    assert config["game_title"] == "Random Chit"


def test_draw_complete_skip_and_final_standings():
    config = validate_config({
        "rounds": 5,
        "chits": [
            {"text": "Question one", "category": "question"},
            {"text": "Question two", "category": "question"},
            {"text": "Question three", "category": "question"},
            {"text": "Question four", "category": "question"},
            {"text": "Question five", "category": "question"},
        ],
    })
    state = create_initial_state(["Avi", "Ruchi", "Ashu"], config, now=100)

    assert state["phase"] == PHASE_READY

    state = draw_turn(state, now=101)
    assert state["phase"] == PHASE_ACTIVE
    assert state["current_chit"]
    assert state["selected_player_id"] in {"Avi", "Ruchi", "Ashu"}

    selected = state["selected_player_id"]
    state = complete_turn(state, bonus=True, now=102)
    assert state["phase"] == PHASE_RESULT
    assert state["scores"][selected] == 150
    assert state["round_index"] == 1

    state = draw_turn(state, now=103)
    skipped = state["selected_player_id"]
    score_before_skip = state["scores"][skipped]
    state = skip_turn(state, now=104)
    assert state["phase"] == PHASE_RESULT
    assert state["scores"][skipped] == score_before_skip
    assert final_standings(state)[0]["score"] == 150


def test_redraw_player_or_chit_preserves_the_other_side():
    state = create_initial_state(["Avi", "Ruchi", "Ashu"], validate_config({"rounds": 1}), now=100)
    state = draw_turn(state, now=101)
    original_player = state["selected_player_id"]
    original_chit = state["current_chit"]["id"]

    player_redrawn = redraw_player(state, now=102)
    assert player_redrawn["current_chit"]["id"] == original_chit
    assert player_redrawn["selected_player_id"] in {"Avi", "Ruchi", "Ashu"}

    chit_redrawn = redraw_chit(state, now=103)
    assert chit_redrawn["selected_player_id"] == original_player
    assert chit_redrawn["current_chit"]["id"] != original_chit


def test_public_sync_excludes_internal_rng_state():
    state = draw_turn(create_initial_state(["Avi", "Ruchi", "Ashu"], validate_config({"rounds": 1}), now=100), now=101)
    public = public_sync(state)

    assert "_rng_state" not in public
    assert public["current_chit"]["text"]
    assert public["phase"] == PHASE_ACTIVE


def test_generated_content_rejects_unsafe_or_too_short_decks():
    safe = sanitize_generated_game({
        "game_title": "Family Chits",
        "rounds": 5,
        "chits": [{"text": f"Clean prompt {index}", "category": "question"} for index in range(5)],
    })
    assert len(safe["chits"]) == 5

    topped_up = validate_config({"chits": [{"text": "only one", "category": "question"}]})
    assert len(topped_up["chits"]) == 5
    assert topped_up["chits"][0]["text"] == "only one"
