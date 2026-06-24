"""Pure Word Association game mechanics."""
from __future__ import annotations

import re
import time
import unicodedata
from collections import defaultdict
from typing import Any, Optional


PHASE_SUBMITTING = "WORD_ASSOC_SUBMITTING"
PHASE_REVEAL = "WORD_ASSOC_REVEAL"
PHASE_PODIUM = "PODIUM"

DEFAULT_SEEDS = [
    {"id": "word_1", "seed": "Birthday", "category": "party"},
    {"id": "word_2", "seed": "Music", "category": "party"},
    {"id": "word_3", "seed": "Vacation", "category": "classic"},
]


def _clean_text(value: Any, max_chars: int = 160) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(value or ""))
    text = re.sub(r"<\s*/?\s*(script|style|iframe)[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def normalize_submission(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _clamp_int(raw: dict, key: str, default: int, low: int, high: int) -> int:
    try:
        value = int(raw.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


def _sanitize_seed(raw: dict, index: int) -> Optional[dict]:
    seed = _clean_text(raw.get("seed") or raw.get("prompt") or raw.get("word"), 60)
    if not seed:
        return None
    return {
        "id": _clean_text(raw.get("id") or f"word_{index}", 40) or f"word_{index}",
        "seed": seed,
        "category": _clean_text(raw.get("category") or "party", 40) or "party",
    }


def validate_config(raw: dict | None) -> dict:
    raw = raw or {}
    source = raw.get("seeds") if isinstance(raw.get("seeds"), list) else DEFAULT_SEEDS
    seeds = []
    seen = set()
    for index, item in enumerate(source, start=1):
        if not isinstance(item, dict):
            continue
        seed = _sanitize_seed(item, index)
        if not seed:
            continue
        key = normalize_submission(seed["seed"])
        if key in seen:
            continue
        seen.add(key)
        seeds.append(seed)
        if len(seeds) >= 25:
            break
    if len(seeds) < 3:
        seeds = [_sanitize_seed(item, index) for index, item in enumerate(DEFAULT_SEEDS, start=1)]
        seeds = [item for item in seeds if item]
    round_count = _clamp_int(raw, "round_count", min(10, len(seeds)), 3, 25)
    scoring_mode = str(raw.get("scoring_mode") or "majority").lower()
    if scoring_mode not in {"none", "majority"}:
        scoring_mode = "majority"
    return {
        "game_title": _clean_text(raw.get("game_title") or "Word Association", 120) or "Word Association",
        "theme": _clean_text(raw.get("theme") or "", 80),
        "round_count": min(round_count, len(seeds)),
        "scoring_mode": scoring_mode,
        "allow_submission_changes": bool(raw.get("allow_submission_changes", True)),
        "seeds": seeds[:round_count],
    }


def create_initial_state(player_ids: list[str], config: dict | None = None, now: float | None = None) -> dict:
    players = [str(player_id) for player_id in player_ids if str(player_id)]
    setup = validate_config(config)
    return {
        "phase": PHASE_SUBMITTING,
        "config": setup,
        "players": players,
        "current_round_index": 0,
        "rounds": [{"round_index": index, "seed": seed, "submissions": {}, "groups": [], "revealed_at": None} for index, seed in enumerate(setup["seeds"])],
        "scores": {player_id: 0 for player_id in players},
        "started_at": now or time.time(),
        "completed_at": None,
    }


def current_round(state: dict) -> dict:
    rounds = state.get("rounds") or []
    index = int(state.get("current_round_index", 0))
    if index < 0 or index >= len(rounds):
        raise ValueError("No active Word Association round")
    return rounds[index]


def submit_word(state: dict, player_id: str, word: str) -> dict:
    if state.get("phase") != PHASE_SUBMITTING:
        raise ValueError("This round is not accepting submissions")
    if player_id not in state.get("players", []):
        raise ValueError("Unknown player")
    clean = _clean_text(word, 80)
    normalized = normalize_submission(clean)
    if not normalized:
        raise ValueError("Submission is required")
    existing = current_round(state).get("submissions", {}).get(player_id)
    if existing and not state.get("config", {}).get("allow_submission_changes", True):
        raise ValueError("Submission changes are disabled")
    next_state = _copy_state(state)
    current_round(next_state)["submissions"][player_id] = {"text": clean, "normalized": normalized}
    return next_state


def reveal_round(state: dict, now: float | None = None) -> dict:
    if state.get("phase") != PHASE_SUBMITTING:
        raise ValueError("This round is not ready to reveal")
    next_state = _copy_state(state)
    round_state = current_round(next_state)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for player_id, submission in (round_state.get("submissions") or {}).items():
        grouped[submission["normalized"]].append({"player_id": player_id, "text": submission["text"]})
    groups = []
    for normalized, entries in grouped.items():
        display = sorted((entry["text"] for entry in entries), key=lambda value: (-len(value), value.lower()))[0]
        groups.append({"normalized": normalized, "display": display, "players": entries, "count": len(entries)})
    groups.sort(key=lambda item: (-item["count"], item["display"].lower()))
    round_state["groups"] = groups
    round_state["revealed_at"] = now or time.time()
    if next_state["config"]["scoring_mode"] == "majority" and groups:
        max_count = groups[0]["count"]
        if max_count > 1:
            winners = {entry["player_id"] for group in groups if group["count"] == max_count for entry in group["players"]}
            scores = dict(next_state.get("scores") or {})
            for player_id in winners:
                scores[player_id] = int(scores.get(player_id, 0)) + 1
            next_state["scores"] = scores
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
    next_state["phase"] = PHASE_SUBMITTING
    return next_state


def add_player(state: dict, player_id: str) -> dict:
    player_id = str(player_id or "")
    if not player_id:
        raise ValueError("player_id is required")
    next_state = _copy_state(state)
    if player_id not in next_state["players"]:
        next_state["players"].append(player_id)
        next_state["scores"][player_id] = 0
    return next_state


def public_state(state: dict, viewer_id: str | None = None) -> dict:
    state_copy = _copy_state(state)
    phase = state_copy.get("phase")
    round_state = current_round(state_copy) if phase != PHASE_PODIUM else None
    submissions = dict((round_state or {}).get("submissions") or {})
    payload = {
        "phase": phase,
        "game_title": state_copy.get("config", {}).get("game_title"),
        "current_round_index": state_copy.get("current_round_index"),
        "round_count": len(state_copy.get("rounds") or []),
        "seed": (round_state or {}).get("seed"),
        "submitted_count": len(submissions),
        "scores": dict(state_copy.get("scores") or {}),
        "completed_at": state_copy.get("completed_at"),
    }
    if viewer_id and viewer_id in submissions:
        payload["your_submission"] = submissions[viewer_id]["text"]
    if phase == PHASE_REVEAL:
        payload["groups"] = list((round_state or {}).get("groups") or [])
        payload["submissions"] = submissions
    return payload


def _copy_state(state: dict) -> dict:
    rounds = []
    for round_state in state.get("rounds") or []:
        rounds.append({
            **round_state,
            "seed": dict(round_state.get("seed") or {}),
            "submissions": {player_id: dict(submission) for player_id, submission in (round_state.get("submissions") or {}).items()},
            "groups": [
                {**group, "players": [dict(entry) for entry in group.get("players", [])]}
                for group in (round_state.get("groups") or [])
            ],
        })
    return {
        **state,
        "config": {**dict(state.get("config") or {}), "seeds": [dict(seed) for seed in state.get("config", {}).get("seeds", [])]},
        "players": list(state.get("players") or []),
        "rounds": rounds,
        "scores": dict(state.get("scores") or {}),
    }
