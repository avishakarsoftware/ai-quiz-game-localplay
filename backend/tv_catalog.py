"""Derived TV-primary capability metadata for catalog entries.

The native TV app uses the same game catalog as web and Revelry, but the TV
surface needs one more answer: can this game be started from a TV, and what
kind of phone companion is needed?  Keep that answer derived from runtime
properties wherever possible so new games do not require updating a hidden
manual list in the frontend.
"""

COMPANION_NONE = "none"
COMPANION_SHARED_PHONE = "shared_phone"
COMPANION_PER_PLAYER_PHONE = "per_player_phone"
COMPANION_PHONE_HOST = "phone_host"

TV_COMPANION_MODES = {
    COMPANION_NONE,
    COMPANION_SHARED_PHONE,
    COMPANION_PER_PLAYER_PHONE,
    COMPANION_PHONE_HOST,
}

BUCKET_TV_REMOTE = "tv_remote"
BUCKET_SHARED_PHONE = "shared_phone"
BUCKET_PER_PLAYER_PHONE = "per_player_phone"
BUCKET_PHONE_HOST = "phone_host"

# Games where a TV cannot reasonably be the primary host because the core host
# action depends on a phone-native capability such as camera/media capture.
PHONE_HOST_GAME_IDS = frozenset({"photo_clue"})

# Runtime families that can be facilitated from a TV with no per-player private
# screens in their TV adaptation.  Existing web rooms may still use phones for
# scoring; this marks the native-TV launcher as allowed to offer a TV-primary
# no-companion or room-led mode.
TV_REMOTE_ONLY_RUNTIMES = frozenset({
    "housie",
    "bingo",
    "musical_chairs",
    "two_truths",
    "story_chain",
    "survey_says",
    "would_you_rather",
    "never_have_i_ever",
    "word_association",
    "hot_takes",
    "this_or_that",
    "rapid_fire",
    "one_word_vibes",
    "memory_lane",
})


def _entry_id(entry: dict) -> str:
    return str(entry.get("id") or entry.get("game_type") or "")


def _runtime(entry: dict) -> str:
    return str(entry.get("runtime_type") or entry.get("game_type") or _entry_id(entry))


def _minimum_players(entry: dict) -> int:
    players = (entry.get("config_schema") or {}).get("players") or {}
    try:
        return max(1, int(players.get("min") or 1))
    except (TypeError, ValueError):
        return 1


def derive_tv_capability(entry: dict) -> dict:
    """Return the TV capability contract for one catalog entry."""
    game_id = _entry_id(entry)
    runtime = _runtime(entry)
    min_players = _minimum_players(entry)
    custom_text = bool(entry.get("supports_ai_generation") or entry.get("supports_custom_content"))

    if game_id in PHONE_HOST_GAME_IDS or runtime in PHONE_HOST_GAME_IDS:
        return {
            "hostable": False,
            "bucket": BUCKET_PHONE_HOST,
            "companion_mode": COMPANION_PHONE_HOST,
            "min_companion_devices": 0,
            "private_screen": False,
            "text_input_for_customization": custom_text,
            "requirement_label": "Start on phone",
            "reason_chip": "Start from a phone",
            "tv_play_note": "The host needs a phone-native capability such as camera or media capture.",
        }

    if entry.get("interaction") == "pass_and_play":
        return {
            "hostable": True,
            "bucket": BUCKET_SHARED_PHONE,
            "companion_mode": COMPANION_SHARED_PHONE,
            "min_companion_devices": 1,
            "private_screen": True,
            "text_input_for_customization": custom_text,
            "requirement_label": "TV + 1 shared phone",
            "reason_chip": "Needs 1 shared phone",
            "tv_play_note": "One phone is passed around for private screens while the TV anchors the room.",
        }

    if runtime in TV_REMOTE_ONLY_RUNTIMES:
        return {
            "hostable": True,
            "bucket": BUCKET_TV_REMOTE,
            "companion_mode": COMPANION_NONE,
            "min_companion_devices": 0,
            "private_screen": False,
            "text_input_for_customization": custom_text,
            "requirement_label": "TV only",
            "reason_chip": "TV ready",
            "tv_play_note": "The TV can facilitate this with remote control and room-led scoring or discussion.",
        }

    reason = f"Needs {min_players} phones" if min_players > 1 else "Needs phones to join"
    return {
        "hostable": True,
        "bucket": BUCKET_PER_PLAYER_PHONE,
        "companion_mode": COMPANION_PER_PLAYER_PHONE,
        "min_companion_devices": min_players,
        "private_screen": False,
        "text_input_for_customization": custom_text,
        "requirement_label": "TV + player phones",
        "reason_chip": reason,
        "tv_play_note": "Players need phones for private input, cards, votes, photos, guesses, or scoring.",
    }


def attach_tv_capabilities(catalog: list[dict]) -> list[dict]:
    """Attach derived TV capability metadata in place and return the catalog."""
    for entry in catalog:
        entry["tv_capability"] = derive_tv_capability(entry)
    return catalog


def tv_availability(entry: dict, connected_devices: int = 0) -> dict:
    """Evaluate whether a catalog entry can be played from TV right now."""
    capability = entry.get("tv_capability") or derive_tv_capability(entry)
    if not capability.get("hostable"):
        return {
            "hostable": False,
            "playable": False,
            "reasons": [capability.get("companion_mode") or COMPANION_PHONE_HOST],
            "reason_chip": capability.get("reason_chip") or "Start from a phone",
        }
    required = int(capability.get("min_companion_devices") or 0)
    if connected_devices < required:
        return {
            "hostable": True,
            "playable": False,
            "reasons": [capability.get("companion_mode") or COMPANION_PER_PLAYER_PHONE],
            "reason_chip": capability.get("reason_chip") or "Needs phones",
        }
    return {
        "hostable": True,
        "playable": True,
        "reasons": [],
        "reason_chip": capability.get("reason_chip") or "TV ready",
    }


def tv_playable_now(catalog: list[dict], connected_devices: int = 0) -> list[dict]:
    return [entry for entry in catalog if tv_availability(entry, connected_devices).get("playable")]
