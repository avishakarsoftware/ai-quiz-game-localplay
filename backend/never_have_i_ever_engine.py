"""Pure Never Have I Ever game mechanics."""
from __future__ import annotations

import re
import time
from typing import Any, Optional


PHASE_ANSWERING = "NHIE_ANSWERING"
PHASE_REVEAL = "NHIE_REVEAL"
PHASE_PODIUM = "PODIUM"

ANSWER_HAVE = "have"
ANSWER_NEVER = "never"
VALID_ANSWERS = {ANSWER_HAVE, ANSWER_NEVER}
VALID_SAFE_LEVELS = {"family", "work", "party", "spicy"}

DEFAULT_PROMPTS = [
    {"id": "nhie_1", "statement": "Never have I ever sung karaoke in public.", "category": "classic"},
    {"id": "nhie_2", "statement": "Never have I ever forgotten why I walked into a room.", "category": "classic"},
    {"id": "nhie_3", "statement": "Never have I ever laughed at the worst possible moment.", "category": "party"},
]


def _clean_text(value: Any, max_chars: int = 160) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(value or ""))
    text = re.sub(r"<\s*/?\s*(script|style|iframe)[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def _clamp_int(raw: dict, key: str, default: int, low: int, high: int) -> int:
    try:
        value = int(raw.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


def _sanitize_prompt(raw: dict, index: int) -> Optional[dict]:
    statement = _clean_text(raw.get("statement") or raw.get("prompt") or raw.get("text"), 140)
    if len(statement) < 8:
        return None
    return {
        "id": _clean_text(raw.get("id") or f"nhie_{index}", 40) or f"nhie_{index}",
        "statement": statement,
        "category": _clean_text(raw.get("category") or "party", 40) or "party",
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
        key = prompt["statement"].lower()
        if key in seen:
            continue
        seen.add(key)
        prompts.append(prompt)
        if len(prompts) >= 25:
            break
    if len(prompts) < 3:
        prompts = [_sanitize_prompt(item, index) for index, item in enumerate(DEFAULT_PROMPTS, start=1)]
        prompts = [item for item in prompts if item]
    round_count = _clamp_int(raw, "round_count", min(10, len(prompts)), 3, 25)
    safe_level = str(raw.get("safe_level") or "party").lower()
    if safe_level not in VALID_SAFE_LEVELS:
        safe_level = "party"
    scoring_mode = str(raw.get("scoring_mode") or "none").lower()
    if scoring_mode not in {"none", "minority"}:
        scoring_mode = "none"
    return {
        "game_title": _clean_text(raw.get("game_title") or "Never Have I Ever", 120) or "Never Have I Ever",
        "theme": _clean_text(raw.get("theme") or "", 80),
        "safe_level": safe_level,
        "round_count": min(round_count, len(prompts)),
        "scoring_mode": scoring_mode,
        "show_live_counts": bool(raw.get("show_live_counts", False)),
        "allow_answer_changes": bool(raw.get("allow_answer_changes", True)),
        "prompts": prompts[:round_count],
    }


def create_initial_state(player_ids: list[str], config: dict | None = None, now: float | None = None) -> dict:
    players = [str(player_id) for player_id in player_ids if str(player_id)]
    setup = validate_config(config)
    return {
        "phase": PHASE_ANSWERING,
        "config": setup,
        "players": players,
        "current_round_index": 0,
        "rounds": [{"round_index": index, "prompt": prompt, "answers": {}, "result": None, "revealed_at": None} for index, prompt in enumerate(setup["prompts"])],
        "scores": {player_id: 0 for player_id in players},
        "started_at": now or time.time(),
        "completed_at": None,
    }


def current_round(state: dict) -> dict:
    rounds = state.get("rounds") or []
    index = int(state.get("current_round_index", 0))
    if index < 0 or index >= len(rounds):
        raise ValueError("No active Never Have I Ever round")
    return rounds[index]


def submit_answer(state: dict, player_id: str, answer: str) -> dict:
    if state.get("phase") != PHASE_ANSWERING:
        raise ValueError("This round is not accepting answers")
    if player_id not in state.get("players", []):
        raise ValueError("Unknown player")
    normalized = str(answer or "").strip().lower()
    if normalized not in VALID_ANSWERS:
        raise ValueError("Answer must be have or never")
    existing = current_round(state).get("answers", {}).get(player_id)
    if existing and not state.get("config", {}).get("allow_answer_changes", True):
        raise ValueError("Answer changes are disabled")
    next_state = _copy_state(state)
    current_round(next_state)["answers"][player_id] = normalized
    return next_state


def reveal_round(state: dict, now: float | None = None) -> dict:
    if state.get("phase") != PHASE_ANSWERING:
        raise ValueError("This round is not ready to reveal")
    next_state = _copy_state(state)
    round_state = current_round(next_state)
    answers = dict(round_state.get("answers") or {})
    have_count = sum(1 for value in answers.values() if value == ANSWER_HAVE)
    never_count = sum(1 for value in answers.values() if value == ANSWER_NEVER)
    total = have_count + never_count
    minority = None
    if 0 < have_count < never_count:
        minority = ANSWER_HAVE
    elif 0 < never_count < have_count:
        minority = ANSWER_NEVER
    result = {
        "have_count": have_count,
        "never_count": never_count,
        "total_answers": total,
        "have_percent": round((have_count / total) * 100) if total else 0,
        "never_percent": round((never_count / total) * 100) if total else 0,
        "minority": minority,
        "tie": have_count == never_count,
    }
    round_state["result"] = result
    round_state["revealed_at"] = now or time.time()
    if minority and next_state["config"]["scoring_mode"] == "minority":
        scores = dict(next_state.get("scores") or {})
        for player_id, value in answers.items():
            if value == minority:
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
    next_state["phase"] = PHASE_ANSWERING
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


def standings(state: dict) -> list[dict]:
    players = list(state.get("players") or [])
    scores = dict(state.get("scores") or {})
    ordered = sorted(players, key=lambda player_id: (-int(scores.get(player_id, 0)), players.index(player_id)))
    return [{"player_id": player_id, "score": int(scores.get(player_id, 0)), "rank": index + 1} for index, player_id in enumerate(ordered)]


def public_state(state: dict, viewer_id: str | None = None) -> dict:
    state_copy = _copy_state(state)
    phase = state_copy.get("phase")
    round_state = current_round(state_copy) if phase != PHASE_PODIUM else None
    answers = dict((round_state or {}).get("answers") or {})
    payload = {
        "phase": phase,
        "game_title": state_copy.get("config", {}).get("game_title"),
        "current_round_index": state_copy.get("current_round_index"),
        "round_count": len(state_copy.get("rounds") or []),
        "prompt": (round_state or {}).get("prompt"),
        "submitted_answers": len(answers),
        "scores": dict(state_copy.get("scores") or {}),
        "standings": standings(state_copy),
        "completed_at": state_copy.get("completed_at"),
    }
    if viewer_id and viewer_id in answers:
        payload["your_answer"] = answers[viewer_id]
    if phase == PHASE_REVEAL:
        payload["result"] = (round_state or {}).get("result")
        payload["answers"] = answers
    elif state_copy.get("config", {}).get("show_live_counts"):
        payload["live_counts"] = {
            "have_count": sum(1 for value in answers.values() if value == ANSWER_HAVE),
            "never_count": sum(1 for value in answers.values() if value == ANSWER_NEVER),
        }
    return payload


def _copy_state(state: dict) -> dict:
    rounds = []
    for round_state in state.get("rounds") or []:
        rounds.append({
            **round_state,
            "prompt": dict(round_state.get("prompt") or {}),
            "answers": dict(round_state.get("answers") or {}),
            "result": dict(round_state.get("result") or {}) if round_state.get("result") else None,
        })
    return {
        **state,
        "config": {**dict(state.get("config") or {}), "prompts": [dict(prompt) for prompt in state.get("config", {}).get("prompts", [])]},
        "players": list(state.get("players") or []),
        "rounds": rounds,
        "scores": dict(state.get("scores") or {}),
    }
