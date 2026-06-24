"""Pure Photo Clue game mechanics.

Photo Clue is intentionally small and server-authoritative: prompts are assigned
up front, each active clue giver submits one image asset, and everyone else
guesses the target phrase.
"""
from __future__ import annotations

import re
import time
import unicodedata
from typing import Any, Optional


PHASE_WAITING_FOR_PHOTO = "PHOTO_WAITING_FOR_PHOTO"
PHASE_GUESSING = "PHOTO_GUESSING"
PHASE_REVEAL = "PHOTO_REVEAL"
PHASE_PODIUM = "PODIUM"

DEFAULT_PROMPTS = [
    {"id": "prompt_1", "answer": "birthday cake", "aliases": ["cake"], "category": "party"},
    {"id": "prompt_2", "answer": "dancing shoes", "aliases": ["shoes"], "category": "party"},
    {"id": "prompt_3", "answer": "secret smile", "aliases": ["smile"], "category": "party"},
    {"id": "prompt_4", "answer": "cold drink", "aliases": ["drink"], "category": "party"},
    {"id": "prompt_5", "answer": "party lights", "aliases": ["lights"], "category": "party"},
]


def _clean_text(value: Any, max_chars: int = 160) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(value or ""))
    text = re.sub(r"<\s*/?\s*(script|style|iframe)[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def normalize_guess(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^(a|an|the)\s+", "", text)
    return text


def _clamp_int(raw: dict, key: str, default: int, low: int, high: int) -> int:
    try:
        value = int(raw.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


def _sanitize_prompt(raw: dict, index: int) -> Optional[dict]:
    answer = _clean_text(raw.get("answer") or raw.get("prompt") or raw.get("text"), 80)
    if len(answer) < 2:
        return None
    aliases = []
    answer_key = normalize_guess(answer)
    for alias in raw.get("aliases") or []:
        clean = _clean_text(alias, 80)
        if clean and normalize_guess(clean) != answer_key and clean not in aliases:
            aliases.append(clean)
    return {
        "id": _clean_text(raw.get("id") or f"prompt_{index}", 40) or f"prompt_{index}",
        "answer": answer,
        "aliases": aliases[:8],
        "category": _clean_text(raw.get("category") or "party", 40) or "party",
        "photo_tip": _clean_text(raw.get("photo_tip") or "Take a clue photo. Do not include text or the answer.", 140),
    }


def validate_config(raw: dict | None) -> dict:
    raw = raw or {}
    source = raw.get("prompts") if isinstance(raw.get("prompts"), list) else DEFAULT_PROMPTS
    prompts = []
    seen = set()
    for index, item in enumerate(source, start=1):
        if not isinstance(item, dict):
            continue
        prompt = _sanitize_prompt(item, index)
        if not prompt:
            continue
        key = normalize_guess(prompt["answer"])
        if key in seen:
            continue
        seen.add(key)
        prompts.append(prompt)
        if len(prompts) >= 50:
            break
    if len(prompts) < 3:
        prompts = [_sanitize_prompt(item, index) for index, item in enumerate(DEFAULT_PROMPTS, start=1)]
        prompts = [item for item in prompts if item]
    round_count = _clamp_int(raw, "round_count", min(5, len(prompts)), 3, 25)
    return {
        "game_title": _clean_text(raw.get("game_title") or "Photo Clue", 120) or "Photo Clue",
        "theme": _clean_text(raw.get("theme") or "", 80),
        "round_count": min(round_count, len(prompts)),
        "photo_time_seconds": _clamp_int(raw, "photo_time_seconds", 90, 30, 300),
        "guess_time_seconds": _clamp_int(raw, "guess_time_seconds", 45, 10, 120),
        "correct_guess_points": _clamp_int(raw, "correct_guess_points", 100, 10, 1000),
        "clue_giver_points": _clamp_int(raw, "clue_giver_points", 50, 0, 500),
        "allow_late_join": bool(raw.get("allow_late_join", True)),
        "prompts": prompts[:round_count],
    }


def create_initial_state(player_ids: list[str], config: dict, now: float | None = None) -> dict:
    players = [str(player_id) for player_id in player_ids if str(player_id)]
    if len(players) < 2:
        raise ValueError("Photo Clue requires at least 2 players")
    setup = validate_config(config)
    started_at = now or time.time()
    assignments = []
    for index, prompt in enumerate(setup["prompts"]):
        assignments.append({
            "round_index": index,
            "clue_giver_id": players[index % len(players)],
            "prompt": prompt,
            "image_asset_id": "",
            "image_url": "",
            "guesses": {},
            "correct_guessers": [],
            "submitted_at": None,
        })
    return {
        "phase": PHASE_WAITING_FOR_PHOTO,
        "config": setup,
        "players": players,
        "current_round_index": 0,
        "assignments": assignments,
        "scores": {player_id: 0 for player_id in players},
        "deadline": started_at + setup["photo_time_seconds"],
        "completed_at": None,
    }


def current_assignment(state: dict) -> dict:
    assignments = state.get("assignments") or []
    index = int(state.get("current_round_index", 0))
    if index < 0 or index >= len(assignments):
        raise ValueError("No active Photo Clue round")
    return assignments[index]


def private_prompt_for_player(state: dict, player_id: str) -> list[dict]:
    return [
        {"round_index": item["round_index"], "prompt": item["prompt"]}
        for item in state.get("assignments", [])
        if item.get("clue_giver_id") == player_id
    ]


def submit_photo(state: dict, player_id: str, asset_id: str, image_url: str = "", now: float | None = None) -> dict:
    if state.get("phase") != PHASE_WAITING_FOR_PHOTO:
        raise ValueError("This round is not waiting for a photo")
    assignment = current_assignment(state)
    if player_id != assignment.get("clue_giver_id"):
        raise ValueError("Only the clue giver can submit this photo")
    clean_asset_id = _clean_text(asset_id, 120)
    if not clean_asset_id:
        raise ValueError("image asset is required")
    next_state = _copy_state(state)
    current = current_assignment(next_state)
    current["image_asset_id"] = clean_asset_id
    current["image_url"] = _clean_text(image_url, 300)
    current["submitted_at"] = now or time.time()
    next_state["phase"] = PHASE_GUESSING
    next_state["deadline"] = (now or time.time()) + int(next_state["config"]["guess_time_seconds"])
    return next_state


def _accepted_answers(prompt: dict) -> set[str]:
    values = [prompt.get("answer"), *list(prompt.get("aliases") or [])]
    return {normalized for value in values if (normalized := normalize_guess(value))}


def is_correct_guess(guess: Any, prompt: dict) -> bool:
    normalized = normalize_guess(guess)
    return len(normalized) >= 2 and normalized in _accepted_answers(prompt)


def submit_guess(state: dict, player_id: str, guess: str, now: float | None = None) -> tuple[dict, bool]:
    if state.get("phase") != PHASE_GUESSING:
        raise ValueError("This round is not accepting guesses")
    assignment = current_assignment(state)
    if player_id == assignment.get("clue_giver_id"):
        raise ValueError("The clue giver cannot guess their own clue")
    if player_id not in state.get("players", []):
        raise ValueError("Unknown player")
    clean_guess = _clean_text(guess, 120)
    if not clean_guess:
        raise ValueError("Guess is required")
    correct = is_correct_guess(clean_guess, assignment.get("prompt") or {})
    next_state = _copy_state(state)
    current = current_assignment(next_state)
    current["guesses"][player_id] = {"guess": clean_guess, "correct": correct, "at": now or time.time()}
    if correct and player_id not in current["correct_guessers"]:
        current["correct_guessers"].append(player_id)
        scores = dict(next_state.get("scores") or {})
        scores[player_id] = int(scores.get(player_id, 0)) + int(next_state["config"]["correct_guess_points"])
        clue_giver = current["clue_giver_id"]
        scores[clue_giver] = int(scores.get(clue_giver, 0)) + int(next_state["config"]["clue_giver_points"])
        next_state["scores"] = scores
    return next_state, correct


def reveal_round(state: dict) -> dict:
    if state.get("phase") not in {PHASE_WAITING_FOR_PHOTO, PHASE_GUESSING, PHASE_REVEAL}:
        raise ValueError("No round to reveal")
    return {**_copy_state(state), "phase": PHASE_REVEAL, "deadline": None}


def next_round(state: dict, now: float | None = None) -> dict:
    if state.get("phase") != PHASE_REVEAL:
        raise ValueError("Reveal the current round before continuing")
    next_state = _copy_state(state)
    next_index = int(next_state.get("current_round_index", 0)) + 1
    if next_index >= len(next_state.get("assignments") or []):
        next_state["phase"] = PHASE_PODIUM
        next_state["completed_at"] = now or time.time()
        next_state["deadline"] = None
        return next_state
    next_state["current_round_index"] = next_index
    next_state["phase"] = PHASE_WAITING_FOR_PHOTO
    next_state["deadline"] = (now or time.time()) + int(next_state["config"]["photo_time_seconds"])
    return next_state


def public_state(state: dict) -> dict:
    assignment = current_assignment(state) if state.get("phase") != PHASE_PODIUM else None
    prompt = assignment.get("prompt") if assignment and state.get("phase") == PHASE_REVEAL else None
    return {
        "phase": state.get("phase"),
        "config": {k: v for k, v in (state.get("config") or {}).items() if k != "prompts"},
        "players": list(state.get("players") or []),
        "current_round_index": int(state.get("current_round_index", 0)),
        "round_count": len(state.get("assignments") or []),
        "clue_giver_id": assignment.get("clue_giver_id") if assignment else "",
        "image_asset_id": assignment.get("image_asset_id") if assignment else "",
        "image_url": assignment.get("image_url") if assignment else "",
        "answer": prompt.get("answer") if prompt else "",
        "category": prompt.get("category") if prompt else "",
        "correct_guessers": list(assignment.get("correct_guessers") or []) if assignment else [],
        "guess_count": len(assignment.get("guesses") or {}) if assignment else 0,
        "scores": dict(state.get("scores") or {}),
        "deadline": state.get("deadline"),
        "completed_at": state.get("completed_at"),
    }


def _copy_state(state: dict) -> dict:
    copied = dict(state)
    copied["config"] = dict(state.get("config") or {})
    copied["players"] = list(state.get("players") or [])
    copied["scores"] = dict(state.get("scores") or {})
    assignments = []
    for item in state.get("assignments") or []:
        assignments.append({
            **item,
            "prompt": dict(item.get("prompt") or {}),
            "guesses": {player_id: dict(guess) for player_id, guess in (item.get("guesses") or {}).items()},
            "correct_guessers": list(item.get("correct_guessers") or []),
        })
    copied["assignments"] = assignments
    return copied
