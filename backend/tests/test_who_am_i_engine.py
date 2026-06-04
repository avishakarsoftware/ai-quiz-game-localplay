import pytest

from who_am_i_engine import (
    PHASE_PODIUM,
    PHASE_REVEAL,
    PHASE_ROUND,
    create_initial_state,
    final_standings,
    is_correct_guess,
    next_clue,
    next_round,
    private_sync,
    public_sync,
    reveal_answer,
    submit_guess,
    validate_config,
)


def test_validate_config_defaults_and_hides_answer_from_clues():
    config = validate_config({
        "game_title": "<script>Bad</script>Who Am I?",
        "round_count": 4,
        "clues_per_round": 4,
        "points_by_clue": [500, 700, 250, 100],
    })

    assert config["game_title"] == "BadWho Am I?"
    assert len(config["rounds"]) == 4
    assert config["points_by_clue"] == [500, 500, 250, 100]
    for round_item in config["rounds"]:
        answer = round_item["answer"].lower()
        assert all(answer not in clue.lower() for clue in round_item["clues"])


def test_guess_matching_accepts_aliases_and_small_typos():
    round_item = {
        "answer": "Taylor Swift",
        "aliases": ["Taylor"],
    }

    assert is_correct_guess("the taylor swift", round_item)
    assert is_correct_guess("Taylro Swift", round_item)
    assert is_correct_guess("Taylor", round_item)
    assert not is_correct_guess("Beyonce", round_item)


def test_public_sync_hides_answer_until_reveal_and_private_sync_shows_guesses():
    state = create_initial_state(["Avi", "Ruchi"], {"round_count": 3}, now=100)
    public = public_sync(state)

    assert public["phase"] == PHASE_ROUND
    assert "answer" not in public
    assert public["clues"][0]["revealed"] is True
    assert public["clues"][1]["revealed"] is False

    state, result = submit_guess(state, "Avi", "wrong answer", now=101)
    private = private_sync(state, "Avi")

    assert result["correct"] is False
    assert private["my_guesses"][0]["guess"] == "wrong answer"
    assert private["my_correct"] is False

    state = reveal_answer(state)
    assert public_sync(state)["answer"]


def test_correct_guess_scores_once_and_limits_extra_guesses_per_clue():
    config = {
        "rounds": [
            {
                "answer": "Mona Lisa",
                "aliases": ["La Gioconda"],
                "category": "Art",
                "clues": ["I am a famous painting.", "I live in the Louvre.", "Leonardo painted me."],
            },
            {
                "answer": "Mount Everest",
                "category": "Place",
                "clues": ["I am very tall.", "Climbers visit me.", "I sit in the Himalayas."],
            },
            {
                "answer": "Serena Williams",
                "category": "Sport",
                "clues": ["I won many majors.", "I play tennis.", "Venus is my sister."],
            },
        ],
        "clues_per_round": 3,
        "points_by_clue": [300, 200, 100],
        "max_guesses_per_player_per_clue": 1,
    }
    state = create_initial_state(["Avi", "Ruchi"], config, now=100)

    state, result = submit_guess(state, "Avi", "Mona Lisa", now=101)
    assert result["correct"] is True
    assert result["points"] == 300
    assert state["scores"]["Avi"] == 300

    state, result = submit_guess(state, "Avi", "La Gioconda", now=102)
    assert result["correct"] is True
    assert result["points"] == 0

    state, _ = submit_guess(state, "Ruchi", "Picasso", now=103)
    with pytest.raises(ValueError, match="next clue"):
        submit_guess(state, "Ruchi", "Van Gogh", now=104)


def test_clue_reveal_round_advance_and_podium():
    state = create_initial_state(["Avi", "Ruchi"], {"round_count": 3, "clues_per_round": 3}, now=100)

    state = next_clue(state, now=101)
    assert state["current_clue_index"] == 1
    state = next_clue(state, now=102)
    assert state["current_clue_index"] == 2
    state = next_clue(state, now=103)
    assert state["phase"] == PHASE_REVEAL

    state = next_round(state, now=104)
    assert state["phase"] == PHASE_ROUND
    assert state["current_round_index"] == 1

    state = reveal_answer(state)
    state = next_round(state, now=105)
    state = reveal_answer(state)
    state = next_round(state, now=106)

    assert state["phase"] == PHASE_PODIUM
    assert final_standings(state)
