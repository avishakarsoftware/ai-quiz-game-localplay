"""Reusable mechanics for lightweight prompt party games.

These games share the same room shape: a prompt appears, players either pick
an option or submit a short answer, the host reveals/votes/advances, and a
podium ranks the room.
"""
from __future__ import annotations

import copy
import hashlib
import re
import time
import unicodedata
from typing import Any


PHASE_CHOICE = "GENERIC_CHOICE"
PHASE_SUBMITTING = "GENERIC_SUBMITTING"
PHASE_VOTING = "GENERIC_VOTING"
PHASE_REVEAL = "GENERIC_REVEAL"
PHASE_PODIUM = "PODIUM"

MODE_CHOICE = "choice_vote"
MODE_TEXT_VOTE = "text_vote"
MODE_TEXT_GROUP = "text_group"

GENERIC_PROMPT_GAME_TYPES = (
    "hot_takes",
    "this_or_that",
    "caption_contest",
    "pitch_battle",
    "roast_toast",
    "desert_island",
    "memory_lane",
    "rapid_fire",
    "one_word_vibes",
    "emoji_story",
)


GAME_LIBRARY: dict[str, dict[str, Any]] = {
    "hot_takes": {
        "title": "Hot Takes",
        "icon": "🔥",
        "mode": MODE_CHOICE,
        "description": "Agree or disagree with party-safe hot takes, then reveal the room split.",
        "rounds": [
            {"id": "hot_1", "prompt": "Pineapple belongs on pizza.", "options": ["Agree", "Disagree"]},
            {"id": "hot_2", "prompt": "A party is better with a planned game than pure chaos.", "options": ["Agree", "Disagree"]},
            {"id": "hot_3", "prompt": "Cake is better than ice cream.", "options": ["Agree", "Disagree"]},
            {"id": "hot_4", "prompt": "The playlist matters more than the food.", "options": ["Agree", "Disagree"]},
            {"id": "hot_5", "prompt": "Surprise parties are usually a good idea.", "options": ["Agree", "Disagree"]},
        ],
    },
    "this_or_that": {
        "title": "This or That",
        "icon": "↔️",
        "mode": MODE_CHOICE,
        "description": "Fast preference rounds where players pick a side and compare the split.",
        "rounds": [
            {"id": "tot_1", "prompt": "Pick your party power.", "options": ["DJ", "Snack boss"]},
            {"id": "tot_2", "prompt": "Weekend plan?", "options": ["Road trip", "Staycation"]},
            {"id": "tot_3", "prompt": "Birthday treat?", "options": ["Cake", "Donuts"]},
            {"id": "tot_4", "prompt": "Game night energy?", "options": ["Strategy", "Chaos"]},
            {"id": "tot_5", "prompt": "Vacation vibe?", "options": ["Beach", "Mountains"]},
        ],
    },
    "caption_contest": {
        "title": "Caption Contest",
        "icon": "💬",
        "mode": MODE_TEXT_VOTE,
        "description": "Write the funniest caption for a scene, then vote for the winner.",
        "rounds": [
            {"id": "cap_1", "prompt": "Caption this: the birthday cake is leaning but everyone is pretending it is fine."},
            {"id": "cap_2", "prompt": "Caption this: someone walks into the room holding way too many balloons."},
            {"id": "cap_3", "prompt": "Caption this: the group selfie has one mysterious extra hand."},
            {"id": "cap_4", "prompt": "Caption this: the DJ accidentally starts a lullaby."},
            {"id": "cap_5", "prompt": "Caption this: the snack table disappears in three minutes."},
        ],
    },
    "pitch_battle": {
        "title": "Pitch Battle",
        "icon": "📣",
        "mode": MODE_TEXT_VOTE,
        "description": "Invent a ridiculous product or idea and vote for the best pitch.",
        "rounds": [
            {"id": "pitch_1", "prompt": "Pitch a new app for people who are always late."},
            {"id": "pitch_2", "prompt": "Pitch the world's most unnecessary party gadget."},
            {"id": "pitch_3", "prompt": "Pitch a restaurant with a truly odd theme."},
            {"id": "pitch_4", "prompt": "Pitch a superhero whose power is mildly useful."},
            {"id": "pitch_5", "prompt": "Pitch a holiday that should exist."},
        ],
    },
    "roast_toast": {
        "title": "Roast & Toast",
        "icon": "🥂",
        "mode": MODE_TEXT_VOTE,
        "description": "Write playful compliments or gentle roasts and vote for the best line.",
        "rounds": [
            {"id": "rt_1", "prompt": "Write a toast for someone who always brings snacks."},
            {"id": "rt_2", "prompt": "Write a gentle roast for the friend who is always late."},
            {"id": "rt_3", "prompt": "Write a toast for the best dancer in the room."},
            {"id": "rt_4", "prompt": "Write a gentle roast for someone who overplans everything."},
            {"id": "rt_5", "prompt": "Write a toast for the person who keeps the group chat alive."},
        ],
    },
    "desert_island": {
        "title": "Desert Island",
        "icon": "🏝️",
        "mode": MODE_TEXT_VOTE,
        "description": "Answer survival-style prompts and vote for the room's favorite pick.",
        "rounds": [
            {"id": "island_1", "prompt": "You can bring one snack to a desert island. What is it?"},
            {"id": "island_2", "prompt": "You can bring one album. Which one?"},
            {"id": "island_3", "prompt": "You can bring one silly comfort item. What is it?"},
            {"id": "island_4", "prompt": "You can bring one celebrity teammate. Who?"},
            {"id": "island_5", "prompt": "You can bring one board game. Which one?"},
        ],
    },
    "memory_lane": {
        "title": "Memory Lane",
        "icon": "🕰️",
        "mode": MODE_TEXT_VOTE,
        "description": "Share short memories or mini stories and vote for the favorite.",
        "rounds": [
            {"id": "mem_1", "prompt": "Share a tiny memory about a birthday or celebration."},
            {"id": "mem_2", "prompt": "Share a moment when a plan went hilariously wrong."},
            {"id": "mem_3", "prompt": "Share a food memory that still makes you smile."},
            {"id": "mem_4", "prompt": "Share a memory of someone being unexpectedly kind."},
            {"id": "mem_5", "prompt": "Share a travel memory in one sentence."},
        ],
    },
    "rapid_fire": {
        "title": "Rapid Fire",
        "icon": "⚡",
        "mode": MODE_TEXT_GROUP,
        "description": "Answer instantly, then reveal matching groups and oddballs.",
        "rounds": [
            {"id": "rapid_1", "prompt": "First party food that comes to mind."},
            {"id": "rapid_2", "prompt": "First movie villain that comes to mind."},
            {"id": "rapid_3", "prompt": "First vacation city that comes to mind."},
            {"id": "rapid_4", "prompt": "First childhood game that comes to mind."},
            {"id": "rapid_5", "prompt": "First dance song that comes to mind."},
        ],
    },
    "one_word_vibes": {
        "title": "One Word Vibes",
        "icon": "🔮",
        "mode": MODE_TEXT_GROUP,
        "description": "Describe a prompt in one word and see who matched your vibe.",
        "rounds": [
            {"id": "vibe_1", "prompt": "Describe this party in one word."},
            {"id": "vibe_2", "prompt": "Describe Mondays in one word."},
            {"id": "vibe_3", "prompt": "Describe road trips in one word."},
            {"id": "vibe_4", "prompt": "Describe karaoke in one word."},
            {"id": "vibe_5", "prompt": "Describe surprise gifts in one word."},
        ],
    },
    "emoji_story": {
        "title": "Emoji Story",
        "icon": "😄",
        "mode": MODE_TEXT_VOTE,
        "description": "Turn an emoji chain into a tiny story and vote for the best one.",
        "rounds": [
            {"id": "emoji_1", "prompt": "Write a tiny story for: 🎂🕯️😱😂"},
            {"id": "emoji_2", "prompt": "Write a tiny story for: 🚗🌧️🍟🎶"},
            {"id": "emoji_3", "prompt": "Write a tiny story for: 🐶🎈🏃‍♂️🏆"},
            {"id": "emoji_4", "prompt": "Write a tiny story for: 👑🍕🕺✨"},
            {"id": "emoji_5", "prompt": "Write a tiny story for: 🧳✈️😴📸"},
        ],
    },
}


def _clean_text(value: Any, max_chars: int = 220) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(value or ""))
    text = re.sub(r"<\s*/?\s*(script|style|iframe)[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def _normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _entry_id(player_id: str, state: dict) -> str:
    """Stable, collision-free, anonymous entry id for a submission.

    Player ids are room nicknames, so deriving the entry id from the normalized
    nickname (the old behaviour) both collided for nicknames that normalize to
    the same string (e.g. ``Bob!`` and ``Bob?`` -> ``entry_bob``, corrupting the
    vote tally) and leaked the author during blind voting. Hashing the nickname
    alone is also precomputable because the player list is visible, so include
    room/round state as a per-game salt while keeping the id stable for edits
    inside the same round.
    """
    source = f"{state.get('started_at')}:{state.get('current_round_index', 0)}:{player_id}"
    digest = hashlib.sha1(source.encode("utf-8")).hexdigest()
    return f"entry_{digest[:12]}"


def _clamp_int(raw: dict, key: str, default: int, low: int, high: int) -> int:
    try:
        value = int(raw.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


def is_generic_prompt_game(game_type: str) -> bool:
    return game_type in GENERIC_PROMPT_GAME_TYPES


def _library(game_type: str) -> dict:
    if game_type not in GAME_LIBRARY:
        raise ValueError(f"Unsupported generic prompt game: {game_type}")
    return GAME_LIBRARY[game_type]


def _sanitize_round(raw: dict, index: int, mode: str, prefix: str) -> dict | None:
    prompt = _clean_text(raw.get("prompt") or raw.get("question"), 180)
    if len(prompt) < 4:
        return None
    item = {
        "id": _clean_text(raw.get("id") or f"{prefix}_{index}", 40) or f"{prefix}_{index}",
        "prompt": prompt,
        "hint": _clean_text(raw.get("hint") or "", 80),
    }
    if mode == MODE_CHOICE:
        options = []
        seen = set()
        for option in raw.get("options") or []:
            clean = _clean_text(option, 80)
            key = clean.lower()
            if clean and key not in seen:
                seen.add(key)
                options.append(clean)
            if len(options) >= 4:
                break
        if len(options) < 2:
            return None
        item["options"] = options
    return item


def validate_config(raw: dict | None, game_type: str) -> dict:
    raw = raw or {}
    meta = _library(game_type)
    mode = meta["mode"]
    source = raw.get("rounds") if isinstance(raw.get("rounds"), list) else meta["rounds"]
    rounds = []
    seen = set()
    for index, item in enumerate(source, start=1):
        if not isinstance(item, dict):
            continue
        round_item = _sanitize_round(item, index, mode, game_type)
        if not round_item:
            continue
        key = _normalize(round_item["prompt"])
        if key in seen:
            continue
        seen.add(key)
        rounds.append(round_item)
        if len(rounds) >= 25:
            break
    if len(rounds) < 3:
        rounds = [_sanitize_round(item, index, mode, game_type) for index, item in enumerate(meta["rounds"], start=1)]
        rounds = [item for item in rounds if item]
    default_rounds = min(5, len(rounds))
    round_count = _clamp_int(raw, "round_count", default_rounds, 3, 25)
    vote_changes = bool(raw.get("allow_vote_changes", True))
    return {
        "game_type": game_type,
        "game_title": _clean_text(raw.get("game_title") or meta["title"], 120) or meta["title"],
        "mode": mode,
        "round_count": min(round_count, len(rounds)),
        "allow_vote_changes": vote_changes,
        "rounds": rounds[:round_count],
    }


def create_initial_state(player_ids: list[str], game_type: str, config: dict | None = None, now: float | None = None) -> dict:
    setup = validate_config(config, game_type)
    players = [str(player_id) for player_id in player_ids if str(player_id)]
    first_phase = PHASE_CHOICE if setup["mode"] == MODE_CHOICE else PHASE_SUBMITTING
    return {
        "phase": first_phase,
        "game_type": game_type,
        "config": setup,
        "players": players,
        "current_round_index": 0,
        "rounds": [
            {
                "round_index": index,
                "prompt": round_item,
                "choices": {},
                "submissions": {},
                "votes": {},
                "result": None,
                "revealed_at": None,
            }
            for index, round_item in enumerate(setup["rounds"])
        ],
        "scores": {player_id: 0 for player_id in players},
        "started_at": now or time.time(),
        "completed_at": None,
    }


def current_round(state: dict) -> dict:
    rounds = state.get("rounds") or []
    index = int(state.get("current_round_index", 0))
    if index < 0 or index >= len(rounds):
        raise ValueError("No active round")
    return rounds[index]


def add_player(state: dict, player_id: str) -> dict:
    clean = str(player_id or "")
    if not clean:
        raise ValueError("player_id is required")
    next_state = _copy_state(state)
    if clean not in next_state.get("players", []):
        next_state.setdefault("players", []).append(clean)
        next_state.setdefault("scores", {})[clean] = 0
    return next_state


def submit_choice(state: dict, player_id: str, choice: str) -> dict:
    if state.get("phase") != PHASE_CHOICE:
        raise ValueError("This round is not accepting choices")
    if player_id not in state.get("players", []):
        raise ValueError("Unknown player")
    round_state = current_round(state)
    options = round_state.get("prompt", {}).get("options") or []
    clean = _clean_text(choice, 80)
    if clean not in options:
        raise ValueError("Choose one of the visible options")
    if round_state.get("choices", {}).get(player_id) and not state.get("config", {}).get("allow_vote_changes", True):
        raise ValueError("Choice changes are disabled")
    next_state = _copy_state(state)
    current_round(next_state)["choices"][player_id] = clean
    return next_state


def submit_text(state: dict, player_id: str, text: str) -> dict:
    if state.get("phase") != PHASE_SUBMITTING:
        raise ValueError("This round is not accepting submissions")
    if player_id not in state.get("players", []):
        raise ValueError("Unknown player")
    clean = _clean_text(text, 160)
    if len(clean) < 1:
        raise ValueError("Submission is required")
    next_state = _copy_state(state)
    current_round(next_state)["submissions"][player_id] = {
        "entry_id": _entry_id(player_id, state),
        "player_id": player_id,
        "text": clean,
        "normalized": _normalize(clean),
        "at": time.time(),
    }
    return next_state


def start_voting(state: dict) -> dict:
    if state.get("phase") != PHASE_SUBMITTING:
        raise ValueError("Submissions are not open")
    if state.get("config", {}).get("mode") != MODE_TEXT_VOTE:
        raise ValueError("This game does not have a voting phase")
    next_state = _copy_state(state)
    if not current_round(next_state).get("submissions"):
        raise ValueError("Need at least one submission before voting")
    next_state["phase"] = PHASE_VOTING
    return next_state


def submit_vote(state: dict, player_id: str, entry_id: str) -> dict:
    if state.get("phase") != PHASE_VOTING:
        raise ValueError("This round is not accepting votes")
    if player_id not in state.get("players", []):
        raise ValueError("Unknown player")
    round_state = current_round(state)
    entries = {entry.get("entry_id"): entry for entry in (round_state.get("submissions") or {}).values()}
    entry = entries.get(entry_id)
    if not entry:
        raise ValueError("Choose a visible entry")
    if entry.get("player_id") == player_id:
        raise ValueError("Vote for someone else's answer")
    if round_state.get("votes", {}).get(player_id) and not state.get("config", {}).get("allow_vote_changes", True):
        raise ValueError("Vote changes are disabled")
    next_state = _copy_state(state)
    current_round(next_state)["votes"][player_id] = entry_id
    return next_state


def reveal_round(state: dict, now: float | None = None) -> dict:
    if state.get("phase") not in {PHASE_CHOICE, PHASE_SUBMITTING, PHASE_VOTING}:
        raise ValueError("Round is not ready to reveal")
    next_state = _copy_state(state)
    mode = next_state.get("config", {}).get("mode")
    round_state = current_round(next_state)
    result: dict[str, Any]
    if mode == MODE_CHOICE:
        choices = dict(round_state.get("choices") or {})
        counts = {option: 0 for option in round_state.get("prompt", {}).get("options") or []}
        for choice in choices.values():
            counts[choice] = counts.get(choice, 0) + 1
        max_count = max(counts.values()) if counts else 0
        winners = [option for option, count in counts.items() if count == max_count and count > 0]
        if len(winners) == 1:
            scores = dict(next_state.get("scores") or {})
            for player_id, choice in choices.items():
                if choice == winners[0]:
                    scores[player_id] = int(scores.get(player_id, 0)) + 1
            next_state["scores"] = scores
        result = {"counts": counts, "winners": winners, "total": len(choices)}
    elif mode == MODE_TEXT_GROUP:
        submissions = dict(round_state.get("submissions") or {})
        groups: dict[str, dict[str, Any]] = {}
        for entry in submissions.values():
            key = entry.get("normalized") or _normalize(entry.get("text"))
            if not key:
                continue
            group = groups.setdefault(key, {"normalized": key, "display": entry.get("text"), "players": [], "count": 0})
            group["players"].append(entry.get("player_id"))
            group["count"] += 1
        max_count = max((group["count"] for group in groups.values()), default=0)
        scores = dict(next_state.get("scores") or {})
        for group in groups.values():
            if max_count > 1 and group["count"] == max_count:
                for player_id in group["players"]:
                    scores[player_id] = int(scores.get(player_id, 0)) + 1
        next_state["scores"] = scores
        result = {"groups": sorted(groups.values(), key=lambda row: (-row["count"], row["display"])), "total": len(submissions)}
    else:
        submissions = dict(round_state.get("submissions") or {})
        votes = dict(round_state.get("votes") or {})
        vote_counts = {entry["entry_id"]: 0 for entry in submissions.values()}
        for entry_id in votes.values():
            if entry_id in vote_counts:
                vote_counts[entry_id] += 1
        scores = dict(next_state.get("scores") or {})
        for entry in submissions.values():
            scores[entry["player_id"]] = int(scores.get(entry["player_id"], 0)) + vote_counts.get(entry["entry_id"], 0)
        next_state["scores"] = scores
        result = {"vote_counts": vote_counts, "total_votes": len(votes)}
    round_state["result"] = result
    round_state["revealed_at"] = now or time.time()
    next_state["phase"] = PHASE_REVEAL
    return next_state


def next_round(state: dict, now: float | None = None) -> dict:
    if state.get("phase") != PHASE_REVEAL:
        raise ValueError("Reveal the current round before continuing")
    next_state = _copy_state(state)
    next_index = int(next_state.get("current_round_index", 0)) + 1
    if next_index >= len(next_state.get("rounds") or []):
        next_state["phase"] = PHASE_PODIUM
        next_state["completed_at"] = now or time.time()
        return next_state
    next_state["current_round_index"] = next_index
    mode = next_state.get("config", {}).get("mode")
    next_state["phase"] = PHASE_CHOICE if mode == MODE_CHOICE else PHASE_SUBMITTING
    return next_state


def standings(state: dict) -> list[dict]:
    players = list(state.get("players") or [])
    scores = dict(state.get("scores") or {})
    ordered = sorted(players, key=lambda player_id: (-int(scores.get(player_id, 0)), players.index(player_id)))
    return [{"player_id": player_id, "score": int(scores.get(player_id, 0)), "rank": index + 1} for index, player_id in enumerate(ordered)]


def public_state(state: dict, viewer_id: str | None = None, host: bool = False) -> dict:
    phase = state.get("phase")
    round_state = current_round(state) if phase != PHASE_PODIUM else {}
    submissions = list((round_state.get("submissions") or {}).values())
    if phase in {PHASE_REVEAL, PHASE_PODIUM} or host:
        # Authorship is intentionally revealed at reveal/podium and to the host.
        entries = submissions
    elif phase == PHASE_VOTING:
        # Blind voting: expose the text and id to vote on, but never who wrote
        # each entry. ``is_mine`` lets a client disable voting for its own entry
        # without leaking other authors.
        entries = [
            {
                "entry_id": entry.get("entry_id"),
                "text": entry.get("text"),
                "is_mine": entry.get("player_id") == viewer_id,
            }
            for entry in submissions
        ]
    else:
        entries = []
    choices = dict(round_state.get("choices") or {})
    votes = dict(round_state.get("votes") or {})
    payload = {
        "phase": phase,
        "game_type": state.get("game_type"),
        "game_title": state.get("config", {}).get("game_title"),
        "mode": state.get("config", {}).get("mode"),
        "current_round_index": state.get("current_round_index"),
        "round_count": len(state.get("rounds") or []),
        "prompt": round_state.get("prompt"),
        "submitted_count": len(submissions) if state.get("config", {}).get("mode") != MODE_CHOICE else len(choices),
        "entries": entries,
        "scores": dict(state.get("scores") or {}),
        "standings": standings(state),
        "result": round_state.get("result") if phase in {PHASE_REVEAL, PHASE_PODIUM} else None,
        "completed_at": state.get("completed_at"),
    }
    if viewer_id:
        payload["your_choice"] = choices.get(viewer_id)
        payload["your_submission"] = (round_state.get("submissions") or {}).get(viewer_id, {}).get("text")
        payload["your_vote"] = votes.get(viewer_id)
        payload["your_entry_id"] = (round_state.get("submissions") or {}).get(viewer_id, {}).get("entry_id")
    if host and phase not in {PHASE_REVEAL, PHASE_PODIUM}:
        payload["private_choices"] = choices
        payload["private_votes"] = votes
    return payload


def catalog_entries(max_players: int) -> list[dict[str, Any]]:
    entries = []
    for game_type in GENERIC_PROMPT_GAME_TYPES:
        meta = GAME_LIBRARY[game_type]
        entries.append({
            "id": game_type,
            "game_type": game_type,
            "runtime_type": game_type,
            "engine_family": "generic_prompt_party",
            "title": meta["title"],
            "description": meta["description"],
            "status": "gamma",
            "launchable": True,
            "host_app_supported": False,
            "supported_host_apps": [],
            "supports_custom_content": True,
            "supports_images": False,
            "can_create_content": False,
            "can_edit_content": False,
            "can_quick_start": True,
            "supports_ai_generation": False,
            "creation_modes": ["quick_start", "settings"],
            "default_content_available": True,
            "embedded_authoring_supported": False,
            "content_schema": {"kind": "generic_prompt_party_v1", "mode": meta["mode"], "supported_media": []},
            "result_summary_schema": "generic_prompt_party_result_v1",
            "config_schema": {
                "players": {"min": 2, "recommended_min": 4, "max": max_players},
                "rounds": {"min": 3, "max": 25, "default": 5},
                "mode": meta["mode"],
            },
        })
    return entries


def _copy_state(state: dict) -> dict:
    return copy.deepcopy(state)
