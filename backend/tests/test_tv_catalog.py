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
            "bucket",
            "companion_mode",
            "min_companion_devices",
            "private_screen",
            "text_input_for_customization",
            "requirement_label",
            "reason_chip",
            "tv_play_note",
        }
        assert isinstance(capability["hostable"], bool)
        assert isinstance(capability["min_companion_devices"], int)
        assert capability["bucket"]
        assert capability["requirement_label"]
        assert capability["reason_chip"]
        assert capability["tv_play_note"]


def test_tv_only_games_are_playable_without_companion_devices():
    for game_id in ["housie", "bingo", "baby_bingo", "musical_chairs", "story_chain"]:
        capability = game(game_id)["tv_capability"]
        assert capability["hostable"] is True
        assert capability["bucket"] == "tv_remote"
        assert capability["requirement_label"] == "TV only"
        assert capability["companion_mode"] == COMPANION_NONE
        assert capability["min_companion_devices"] == 0
        assert tv_availability(game(game_id), connected_devices=0)["playable"] is True


def test_pass_and_play_games_need_one_shared_phone():
    capability = game("impostor")["tv_capability"]
    assert capability["hostable"] is True
    assert capability["bucket"] == "shared_phone"
    assert capability["requirement_label"] == "TV + 1 shared phone"
    assert capability["companion_mode"] == COMPANION_SHARED_PHONE
    assert capability["min_companion_devices"] == 1
    assert capability["private_screen"] is True
    assert tv_availability(game("impostor"), connected_devices=0)["playable"] is False
    assert tv_availability(game("impostor"), connected_devices=1)["playable"] is True


def test_phone_host_games_are_not_tv_hostable():
    capability = game("photo_clue")["tv_capability"]
    assert capability["hostable"] is False
    assert capability["bucket"] == "phone_host"
    assert capability["requirement_label"] == "Start on phone"
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
    assert capability["bucket"] == "per_player_phone"
    assert capability["requirement_label"] == "TV + player phones"
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


class TestTvOnlyClassificationCannotDrift:
    """The TV-only list is a hand-maintained product judgement, which makes it the most likely
    place for a wrong answer. These tests pin the two failure modes that actually bite a user.
    """

    def test_no_typos_in_the_tv_only_list(self):
        """A runtime name that doesn't exist silently demotes its game to per_player_phone —
        the game just quietly stops being TV-playable and nobody notices."""
        from game_catalog import GAME_CATALOG
        from tv_catalog import TV_REMOTE_ONLY_RUNTIMES
        runtimes = {str(g.get("runtime_type") or g.get("game_type")) for g in GAME_CATALOG}
        unknown = sorted(TV_REMOTE_ONLY_RUNTIMES - runtimes)
        assert unknown == [], f"TV_REMOTE_ONLY_RUNTIMES names runtimes not in the catalog: {unknown}"

    def test_a_game_needing_typed_input_is_never_marked_tv_only(self):
        """The real bug this caught (2026-07-28): memory_lane, rapid_fire and one_word_vibes are
        generic_prompt games in text_vote/text_group mode — every player TYPES an answer — yet they
        were listed as "TV only / TV ready". A host with no phones would pick the tile and hit a
        dead end. Eligibility is now gated on the engine's own mode, so the list cannot override it.
        """
        from generic_prompt_engine import GAME_LIBRARY
        from tv_catalog import GENERIC_PROMPT_TV_SAFE_MODES, _is_tv_remote_eligible
        for runtime, spec in GAME_LIBRARY.items():
            mode = str(spec.get("mode") or "")
            if mode not in GENERIC_PROMPT_TV_SAFE_MODES:
                assert not _is_tv_remote_eligible(runtime), (
                    f"{runtime} needs typed input (mode={mode}) but is treated as TV-only"
                )

    def test_choice_vote_games_stay_tv_eligible(self):
        """The counterpart: a show-of-hands game must NOT be demoted by the mode gate."""
        from tv_catalog import _is_tv_remote_eligible
        for runtime in ("hot_takes", "this_or_that"):
            assert _is_tv_remote_eligible(runtime), f"{runtime} is choice_vote and should be TV-only"

    def test_every_tv_only_game_ships_content_that_needs_no_typing(self):
        """A TV-only game with no default content would strand a phoneless host at a setup screen
        asking for a topic."""
        from game_catalog import GAME_CATALOG
        for entry in GAME_CATALOG:
            if entry["tv_capability"]["bucket"] != "tv_remote":
                continue
            assert entry.get("default_content_available"), (
                f"{entry['id']} is TV-only but ships no default content"
            )

