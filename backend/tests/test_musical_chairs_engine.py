from musical_chairs_engine import choose_eliminated, intensity_for_round, rank_grabs, total_rounds, validate_config


def test_validate_config_clamps_and_sanitizes_values():
    config = validate_config({
        "game_title": "  Birthday Sprint  ",
        "gameplay_mode": "physical",
        "music_mode": "external",
        "music_style": "unknown",
        "music_track_id": " jazzy-lounge ",
        "min_music_seconds": 1,
        "max_music_seconds": 2,
        "grab_window_seconds": 99,
        "eliminations_per_round": 0,
        "auto_stop": False,
    })

    assert config["game_title"] == "Birthday Sprint"
    assert config["gameplay_mode"] == "physical"
    assert config["music_mode"] == "external"
    assert config["music_style"] == "upbeat"
    assert config["music_track_id"] == "jazzy-lounge"
    assert config["min_music_seconds"] == 5
    assert config["max_music_seconds"] == 6
    assert config["grab_window_seconds"] == 10
    assert config["eliminations_per_round"] == 1
    assert config["auto_stop"] is False


def test_validate_config_defaults_track_to_style():
    config = validate_config({
        "music_style": "tropical",
    })

    assert config["music_style"] == "tropical"
    assert config["music_track_id"] == "tropical-island"


def test_total_rounds_leaves_one_winner():
    assert total_rounds(0) == 0
    assert total_rounds(1) == 0
    assert total_rounds(5) == 4
    assert total_rounds(7, eliminations_per_round=2) == 3


def test_rank_grabs_sorts_by_reaction_and_puts_no_taps_last():
    ranked = rank_grabs(
        ["Avi", "Ruchi", "Nia"],
        {"Ruchi": 10.42, "Avi": 10.2},
        stop_time=10.0,
    )

    assert [item["nickname"] for item in ranked] == ["Avi", "Ruchi", "Nia"]
    assert [item["rank"] for item in ranked] == [1, 2, 3]
    assert ranked[0]["reaction_ms"] == 200
    assert ranked[-1]["reaction_ms"] is None


def test_choose_eliminated_removes_slowest_or_no_tap_players():
    eliminated = choose_eliminated(
        ["Avi", "Ruchi", "Nia", "Kabir"],
        {"Avi": 12.1, "Ruchi": 12.4, "Nia": 12.2},
        stop_time=12.0,
        eliminations_per_round=2,
    )

    assert eliminated == ["Ruchi", "Kabir"]


def test_intensity_ramp_increases_over_rounds():
    assert intensity_for_round(1, 5, enabled=True) < intensity_for_round(5, 5, enabled=True)
    assert intensity_for_round(5, 5, enabled=False) == 0.35
