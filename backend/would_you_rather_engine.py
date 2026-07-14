"""Pure Would You Rather game mechanics."""
from __future__ import annotations

import re
import time
from typing import Any, Optional

from engine_common import clamp_int as _clamp_int, make_clean_text
_clean_text = make_clean_text(max_chars=160)

PHASE_VOTING = "WYR_VOTING"
PHASE_REVEAL = "WYR_REVEAL"
PHASE_PODIUM = "PODIUM"

CHOICE_A = "A"
CHOICE_B = "B"
VALID_CHOICES = {CHOICE_A, CHOICE_B}

DEFAULT_PROMPTS = [
    {
        "id": "wyr_1",
        "question": "Would you rather have unlimited party snacks or unlimited party music?",
        "option_a": "Unlimited snacks",
        "option_b": "Unlimited music",
        "category": "party",
    },
    {
        "id": "wyr_2",
        "question": "Would you rather teleport anywhere or fly anywhere?",
        "option_a": "Teleport",
        "option_b": "Fly",
        "category": "classic",
    },
    {
        "id": "wyr_3",
        "question": "Would you rather only speak in movie quotes or only communicate with emojis?",
        "option_a": "Movie quotes",
        "option_b": "Emojis",
        "category": "silly",
    },
]


def _sanitize_prompt(raw: dict, index: int) -> Optional[dict]:
    question = _clean_text(raw.get("question") or raw.get("prompt"), 120)
    option_a = _clean_text(raw.get("option_a") or raw.get("a"), 80)
    option_b = _clean_text(raw.get("option_b") or raw.get("b"), 80)
    if len(question) < 4 or not option_a or not option_b:
        return None
    if option_a.lower() == option_b.lower():
        return None
    return {
        "id": _clean_text(raw.get("id") or f"wyr_{index}", 40) or f"wyr_{index}",
        "question": question,
        "option_a": option_a,
        "option_b": option_b,
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
        key = (prompt["question"].lower(), prompt["option_a"].lower(), prompt["option_b"].lower())
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
    scoring_mode = str(raw.get("scoring_mode") or "majority").lower()
    if scoring_mode not in {"none", "majority"}:
        scoring_mode = "majority"
    return {
        "game_title": _clean_text(raw.get("game_title") or "Would You Rather", 120) or "Would You Rather",
        "theme": _clean_text(raw.get("theme") or "", 80),
        "round_count": min(round_count, len(prompts)),
        "scoring_mode": scoring_mode,
        "show_live_counts": bool(raw.get("show_live_counts", False)),
        "allow_vote_changes": bool(raw.get("allow_vote_changes", True)),
        "prompts": prompts[:round_count],
    }


def create_initial_state(player_ids: list[str], config: dict | None = None, now: float | None = None) -> dict:
    players = [str(player_id) for player_id in player_ids if str(player_id)]
    setup = validate_config(config)
    return {
        "phase": PHASE_VOTING,
        "config": setup,
        "players": players,
        "current_round_index": 0,
        "rounds": [
            {
                "round_index": index,
                "prompt": prompt,
                "votes": {},
                "revealed_at": None,
                "result": None,
            }
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
        raise ValueError("No active Would You Rather round")
    return rounds[index]


def submit_vote(state: dict, player_id: str, choice: str) -> dict:
    if state.get("phase") != PHASE_VOTING:
        raise ValueError("This round is not accepting votes")
    if player_id not in state.get("players", []):
        raise ValueError("Unknown player")
    normalized_choice = str(choice or "").strip().upper()
    if normalized_choice not in VALID_CHOICES:
        raise ValueError("Vote must be A or B")
    round_state = current_round(state)
    existing = round_state.get("votes", {}).get(player_id)
    if existing and not state.get("config", {}).get("allow_vote_changes", True):
        raise ValueError("Vote changes are disabled")
    next_state = _copy_state(state)
    current_round(next_state)["votes"][player_id] = normalized_choice
    return next_state


def reveal_round(state: dict, now: float | None = None) -> dict:
    if state.get("phase") != PHASE_VOTING:
        raise ValueError("This round is not ready to reveal")
    next_state = _copy_state(state)
    round_state = current_round(next_state)
    votes = dict(round_state.get("votes") or {})
    count_a = sum(1 for value in votes.values() if value == CHOICE_A)
    count_b = sum(1 for value in votes.values() if value == CHOICE_B)
    total = count_a + count_b
    majority = None
    if count_a > count_b:
        majority = CHOICE_A
    elif count_b > count_a:
        majority = CHOICE_B
    result = {
        "count_a": count_a,
        "count_b": count_b,
        "total_votes": total,
        "percent_a": round((count_a / total) * 100) if total else 0,
        "percent_b": round((count_b / total) * 100) if total else 0,
        "majority": majority,
        "tie": count_a == count_b,
    }
    round_state["result"] = result
    round_state["revealed_at"] = now or time.time()
    if majority and next_state["config"]["scoring_mode"] == "majority":
        scores = dict(next_state.get("scores") or {})
        for voter_id, vote in votes.items():
            if vote == majority:
                scores[voter_id] = int(scores.get(voter_id, 0)) + 1
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
    next_state["phase"] = PHASE_VOTING
    return next_state


def add_player(state: dict, player_id: str) -> dict:
    player_id = str(player_id or "")
    if not player_id:
        raise ValueError("player_id is required")
    next_state = _copy_state(state)
    if player_id not in next_state.get("players", []):
        next_state.setdefault("players", []).append(player_id)
        next_state.setdefault("scores", {})[player_id] = 0
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
    votes = dict((round_state or {}).get("votes") or {})
    show_live_counts = bool(state_copy.get("config", {}).get("show_live_counts"))
    result = (round_state or {}).get("result") if phase in {PHASE_REVEAL, PHASE_PODIUM} else None
    payload = {
        "phase": phase,
        "game_title": state_copy.get("config", {}).get("game_title"),
        "current_round_index": state_copy.get("current_round_index"),
        "round_count": len(state_copy.get("rounds") or []),
        "prompt": (round_state or {}).get("prompt"),
        "submitted_votes": len(votes),
        "scores": dict(state_copy.get("scores") or {}),
        "standings": standings(state_copy),
        "completed_at": state_copy.get("completed_at"),
    }
    if viewer_id and viewer_id in votes:
        payload["your_vote"] = votes[viewer_id]
    if phase == PHASE_REVEAL:
        payload["result"] = result
        payload["votes"] = votes
    elif show_live_counts:
        payload["live_counts"] = {
            "count_a": sum(1 for value in votes.values() if value == CHOICE_A),
            "count_b": sum(1 for value in votes.values() if value == CHOICE_B),
        }
    return payload


def _copy_state(state: dict) -> dict:
    rounds = []
    for round_state in state.get("rounds") or []:
        rounds.append({
            **round_state,
            "prompt": dict(round_state.get("prompt") or {}),
            "votes": dict(round_state.get("votes") or {}),
            "result": dict(round_state.get("result") or {}) if round_state.get("result") else None,
        })
    return {
        **state,
        "config": {
            **dict(state.get("config") or {}),
            "prompts": [dict(prompt) for prompt in state.get("config", {}).get("prompts", [])],
        },
        "players": list(state.get("players") or []),
        "rounds": rounds,
        "scores": dict(state.get("scores") or {}),
    }
