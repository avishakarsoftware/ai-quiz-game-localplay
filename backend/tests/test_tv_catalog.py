from game_catalog import GAME_CATALOG
from tv_catalog import (
    COMPANION_NONE,
    COMPANION_PER_PLAYER_PHONE,
    COMPANION_PHONE_HOST,
    COMPANION_SHARED_PHONE,
    tv_availability,
    tv_playable_now,
)


def game(game_id: str) -> dict:
    return next(entry for entry in GAME_CATALOG if entry["id"] == game_id)


def test_every_launchable_game_exposes_tv_capability_metadata():
    for entry in GAME_CATALOG:
        if not entry.get("launchable"):
            continue
        capability = entry.get("tv_capability")
        assert capability, f"{entry['id']} missing tv_capability"
        assert set(capability) == {
            "hostable",
            "companion_mode",
            "min_companion_devices",
            "private_screen",
            "text_input_for_customization",
            "reason_chip",
        }
        assert isinstance(capability["hostable"], bool)
        assert isinstance(capability["min_companion_devices"], int)
        assert capability["reason_chip"]


def test_tv_only_games_are_playable_without_companion_devices():
    for game_id in ["housie", "bingo", "baby_bingo", "musical_chairs", "story_chain"]:
        capability = game(game_id)["tv_capability"]
        assert capability["hostable"] is True
        assert capability["companion_mode"] == COMPANION_NONE
        assert capability["min_companion_devices"] == 0
        assert tv_availability(game(game_id), connected_devices=0)["playable"] is True


def test_pass_and_play_games_need_one_shared_phone():
    capability = game("impostor")["tv_capability"]
    assert capability["hostable"] is True
    assert capability["companion_mode"] == COMPANION_SHARED_PHONE
    assert capability["min_companion_devices"] == 1
    assert capability["private_screen"] is True
    assert tv_availability(game("impostor"), connected_devices=0)["playable"] is False
    assert tv_availability(game("impostor"), connected_devices=1)["playable"] is True


def test_phone_host_games_are_not_tv_hostable():
    capability = game("photo_clue")["tv_capability"]
    assert capability["hostable"] is False
    assert capability["companion_mode"] == COMPANION_PHONE_HOST
    assert tv_availability(game("photo_clue"), connected_devices=10) == {
        "hostable": False,
        "playable": False,
        "reasons": [COMPANION_PHONE_HOST],
        "reason_chip": "Start from a phone",
    }


def test_per_player_games_use_catalog_player_minimums():
    capability = game("drawing")["tv_capability"]
    assert capability["hostable"] is True
    assert capability["companion_mode"] == COMPANION_PER_PLAYER_PHONE
    assert capability["min_companion_devices"] == game("drawing")["config_schema"]["players"]["min"]
    assert tv_availability(game("drawing"), connected_devices=capability["min_companion_devices"] - 1)["playable"] is False
    assert tv_availability(game("drawing"), connected_devices=capability["min_companion_devices"])["playable"] is True


def test_playable_now_filters_by_companion_count():
    playable_zero = {entry["id"] for entry in tv_playable_now(GAME_CATALOG, connected_devices=0)}
    playable_one = {entry["id"] for entry in tv_playable_now(GAME_CATALOG, connected_devices=1)}
    assert "housie" in playable_zero
    assert "impostor" not in playable_zero
    assert "impostor" in playable_one
    assert "photo_clue" not in playable_one
