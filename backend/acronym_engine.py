"""Pure Acronym Game mechanics."""
from __future__ import annotations

import hashlib
import re
import time
from typing import Any, Optional


PHASE_SUBMITTING = "ACRONYM_SUBMITTING"
PHASE_VOTING = "ACRONYM_VOTING"
PHASE_REVEAL = "ACRONYM_REVEAL"
PHASE_PODIUM = "PODIUM"

DEFAULT_PROMPTS = [
    {"id": "acro_1", "acronym": "PARTY", "hint": "Make it festive.", "category": "party"},
    {"id": "acro_2", "acronym": "CAKE", "hint": "Make it delicious.", "category": "birthday"},
    {"id": "acro_3", "acronym": "DANCE", "hint": "Make it dramatic.", "category": "party"},
]


def _clean_text(value: Any, max_chars: int = 160) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(value or ""))
    text = re.sub(r"<\s*/?\s*(script|style|iframe)[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def normalize_acronym(value: Any) -> str:
    return re.sub(r"[^A-Z]", "", str(value or "").upper())


def expansion_words(value: Any) -> list[str]:
    text = _clean_text(value, 160)
    return [word for word in re.split(r"\s+", text) if word]


def expansion_matches(acronym: str, expansion: str) -> bool:
    letters = list(normalize_acronym(acronym))
    words = expansion_words(expansion)
    return len(words) == len(letters) and all(word[0].upper() == letter for word, letter in zip(words, letters))


def _entry_id(player_id: str, state: dict) -> str:
    # Voting is blind, and entry ids are exposed to all clients during the
    # voting phase. Include room/round state as a salt so ids cannot be derived
    # from the visible player list, while staying stable for submission edits.
    source = f"{state.get('started_at')}:{state.get('current_round_index', 0)}:{player_id}"
    return "entry_" + hashlib.sha1(source.encode("utf-8")).hexdigest()[:12]


def _clamp_int(raw: dict, key: str, default: int, low: int, high: int) -> int:
    try:
        value = int(raw.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


def _sanitize_prompt(raw: dict, index: int) -> Optional[dict]:
    acronym = normalize_acronym(raw.get("acronym") or raw.get("letters") or raw.get("prompt"))
    if len(acronym) < 2 or len(acronym) > 8:
        return None
    return {
        "id": _clean_text(raw.get("id") or f"acro_{index}", 40) or f"acro_{index}",
        "acronym": acronym,
        "hint": _clean_text(raw.get("hint") or "", 100),
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
        if prompt["acronym"] in seen:
            continue
        seen.add(prompt["acronym"])
        prompts.append(prompt)
        if len(prompts) >= 20:
            break
    if len(prompts) < 3:
        prompts = [_sanitize_prompt(item, index) for index, item in enumerate(DEFAULT_PROMPTS, start=1)]
        prompts = [item for item in prompts if item]
    round_count = _clamp_int(raw, "round_count", min(8, len(prompts)), 3, 20)
    return {
        "game_title": _clean_text(raw.get("game_title") or "Acronym Game", 120) or "Acronym Game",
        "theme": _clean_text(raw.get("theme") or "", 80),
        "round_count": min(round_count, len(prompts)),
        "allow_submission_changes": bool(raw.get("allow_submission_changes", True)),
        "prompts": prompts[:round_count],
    }


def create_initial_state(player_ids: list[str], config: dict | None = None, now: float | None = None) -> dict:
    players = [str(player_id) for player_id in player_ids if str(player_id)]
    setup = validate_config(config)
    return {
        "phase": PHASE_SUBMITTING,
        "config": setup,
        "players": players,
        "current_round_index": 0,
        "rounds": [
            {"round_index": index, "prompt": prompt, "submissions": {}, "votes": {}, "revealed_at": None}
            for index, prompt in enumerate(setup["prompts"])
        ],
        "scores": {player_id: 0 for player_id in players},
        "started_at": now or time.time(),
        "completed_at": None,
    }


def current_round(state: dict) -> dict:
    rounds = state.get("rounds") or []
    index = int(state.get("current_round_index", 0))
    if index < 0 or index >= len(rounds):
        raise ValueError("No active Acronym round")
    return rounds[index]


def submit_expansion(state: dict, player_id: str, expansion: str) -> dict:
    if state.get("phase") != PHASE_SUBMITTING:
        raise ValueError("This round is not accepting submissions")
    if player_id not in state.get("players", []):
        raise ValueError("Unknown player")
    clean = _clean_text(expansion, 160)
    prompt = current_round(state).get("prompt") or {}
    if not expansion_matches(prompt.get("acronym"), clean):
        raise ValueError("Expansion must match the acronym letters")
    existing = current_round(state).get("submissions", {}).get(player_id)
    if existing and not state.get("config", {}).get("allow_submission_changes", True):
        raise ValueError("Submission changes are disabled")
    next_state = _copy_state(state)
    entry_id = _entry_id(player_id, state)
    current_round(next_state)["submissions"][player_id] = {"entry_id": entry_id, "text": clean}
    return next_state


def start_voting(state: dict) -> dict:
    if state.get("phase") != PHASE_SUBMITTING:
        raise ValueError("This round is not ready for voting")
    if not current_round(state).get("submissions"):
        raise ValueError("At least one submission is required")
    next_state = _copy_state(state)
    next_state["phase"] = PHASE_VOTING
    return next_state


def submit_vote(state: dict, voter_id: str, entry_id: str) -> dict:
    if state.get("phase") != PHASE_VOTING:
        raise ValueError("This round is not accepting votes")
    if voter_id not in state.get("players", []):
        raise ValueError("Unknown player")
    round_state = current_round(state)
    submissions = round_state.get("submissions") or {}
    owners = {entry["entry_id"]: player_id for player_id, entry in submissions.items()}
    if entry_id not in owners:
        raise ValueError("Unknown entry")
    if owners[entry_id] == voter_id:
        raise ValueError("Players cannot vote for their own entry")
    next_state = _copy_state(state)
    current_round(next_state)["votes"][voter_id] = entry_id
    return next_state


def reveal_round(state: dict, now: float | None = None) -> dict:
    if state.get("phase") != PHASE_VOTING:
        raise ValueError("This round is not ready to reveal")
    next_state = _copy_state(state)
    round_state = current_round(next_state)
    votes = dict(round_state.get("votes") or {})
    submissions = dict(round_state.get("submissions") or {})
    vote_counts = {entry["entry_id"]: 0 for entry in submissions.values()}
    for entry_id in votes.values():
        if entry_id in vote_counts:
            vote_counts[entry_id] += 1
    scores = dict(next_state.get("scores") or {})
    for player_id, entry in submissions.items():
        scores[player_id] = int(scores.get(player_id, 0)) + vote_counts.get(entry["entry_id"], 0)
    next_state["scores"] = scores
    round_state["revealed_at"] = now or time.time()
    round_state["vote_counts"] = vote_counts
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


def standings(state: dict) -> list[dict]:
    players = list(state.get("players") or [])
    scores = dict(state.get("scores") or {})
    ordered = sorted(players, key=lambda player_id: (-int(scores.get(player_id, 0)), players.index(player_id)))
    return [{"player_id": player_id, "score": int(scores.get(player_id, 0)), "rank": index + 1} for index, player_id in enumerate(ordered)]


def public_state(state: dict, viewer_id: str | None = None) -> dict:
    state_copy = _copy_state(state)
    phase = state_copy.get("phase")
    round_state = current_round(state_copy) if phase != PHASE_PODIUM else None
    submissions = dict((round_state or {}).get("submissions") or {})
    votes = dict((round_state or {}).get("votes") or {})
    entries = [{"entry_id": entry["entry_id"], "text": entry["text"]} for entry in submissions.values()]
    payload = {
        "phase": phase,
        "game_title": state_copy.get("config", {}).get("game_title"),
        "current_round_index": state_copy.get("current_round_index"),
        "round_count": len(state_copy.get("rounds") or []),
        "prompt": (round_state or {}).get("prompt"),
        "submitted_count": len(submissions),
        "vote_count": len(votes),
        "scores": dict(state_copy.get("scores") or {}),
        "standings": standings(state_copy),
        "completed_at": state_copy.get("completed_at"),
    }
    if viewer_id and viewer_id in submissions:
        payload["your_entry_id"] = submissions[viewer_id]["entry_id"]
        payload["your_submission"] = submissions[viewer_id]["text"]
    if viewer_id and viewer_id in votes:
        payload["your_vote"] = votes[viewer_id]
    if phase == PHASE_VOTING:
        payload["entries"] = entries
    if phase == PHASE_REVEAL:
        payload["submissions"] = submissions
        payload["votes"] = votes
        payload["vote_counts"] = dict((round_state or {}).get("vote_counts") or {})
    return payload


def _copy_state(state: dict) -> dict:
    rounds = []
    for round_state in state.get("rounds") or []:
        rounds.append({
            **round_state,
            "prompt": dict(round_state.get("prompt") or {}),
            "submissions": {player_id: dict(entry) for player_id, entry in (round_state.get("submissions") or {}).items()},
            "votes": dict(round_state.get("votes") or {}),
            "vote_counts": dict(round_state.get("vote_counts") or {}),
        })
    return {
        **state,
        "config": {**dict(state.get("config") or {}), "prompts": [dict(prompt) for prompt in state.get("config", {}).get("prompts", [])]},
        "players": list(state.get("players") or []),
        "rounds": rounds,
        "scores": dict(state.get("scores") or {}),
    }
