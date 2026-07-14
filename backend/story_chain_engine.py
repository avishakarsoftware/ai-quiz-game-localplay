import random
import re
import time
from typing import Any

from engine_common import clamp_int as _clamp_int, make_clean_text
_clean_text = make_clean_text(max_chars=180)

PHASE_TURN = "STORY_TURN"
PHASE_REVEAL = "STORY_REVEAL"
PHASE_PODIUM = "PODIUM"

PLACEHOLDER_SENTENCE = "Then something unexpected happened."
POINTS_SENTENCE = 100
POINTS_ON_TIME = 25


def validate_config(raw: dict | None) -> dict:
    raw = raw or {}
    tone = str(raw.get("tone") or "funny").strip().lower()
    if tone not in {"funny", "spooky", "wholesome", "dramatic", "chaotic", "custom"}:
        tone = "funny"
    visibility_mode = str(raw.get("visibility_mode") or "last_sentence_only").strip().lower()
    if visibility_mode not in {"full_context", "last_sentence_only"}:
        visibility_mode = "last_sentence_only"

    prompt = _clean_text(raw.get("starter_prompt") or "The birthday cake started glowing at midnight.", 180)
    if len(prompt) < 8:
        prompt = "The birthday cake started glowing at midnight."

    return {
        "game_title": _clean_text(raw.get("game_title") or "Story Chain", 120) or "Story Chain",
        "starter_prompt": prompt,
        "tone": tone,
        "visibility_mode": visibility_mode,
        "chains": _clamp_int(raw, "chains", 1, 1, 1),
        "turn_time_seconds": _clamp_int(raw, "turn_time_seconds", 45, 20, 120),
        "sentence_max_chars": _clamp_int(raw, "sentence_max_chars", 180, 60, 280),
        "sentences_per_player": _clamp_int(raw, "sentences_per_player", 1, 1, 1),
        "voting_enabled": False,
        "vote_category": "funniest",
    }


def create_turn_order(player_ids: list[str], seed: str | int | None = None) -> list[str]:
    order = [str(player_id) for player_id in player_ids if str(player_id)]
    random.Random(seed).shuffle(order)
    return order


def create_initial_state(player_ids: list[str], config: dict, now: float | None = None, seed: str | int | None = None) -> dict:
    setup = validate_config(config)
    started_at = now or time.time()
    order = create_turn_order(player_ids, seed=seed)
    active = order[0] if order else ""
    return {
        "phase": PHASE_TURN,
        "config": setup,
        "chain_id": "chain_1",
        "turn_order": order,
        "active_player_id": active,
        "current_turn_index": 0,
        "starter_prompt": setup["starter_prompt"],
        "sentences": [],
        "scores": {player_id: 0 for player_id in order},
        "deadline": started_at + setup["turn_time_seconds"] if active else None,
        "reveal_index": -1,
        "completed_at": None,
    }


def _visible_context(state: dict) -> list[str]:
    sentences = state.get("sentences", [])
    if state.get("config", {}).get("visibility_mode") == "full_context":
        return [item.get("text", "") for item in sentences]
    if sentences:
        return [sentences[-1].get("text", "")]
    return []


def private_sync(state: dict, player_id: str, players: list[dict[str, str]] | None = None) -> dict:
    sync = public_sync(state, players)
    is_active = player_id == state.get("active_player_id") and state.get("phase") == PHASE_TURN
    sync["is_active"] = is_active
    sync["visible_context"] = _visible_context(state) if is_active else []
    return sync


def public_sync(state: dict, players: list[dict[str, str]] | None = None) -> dict:
    phase = state.get("phase", PHASE_TURN)
    reveal_index = int(state.get("reveal_index", -1))
    sentences = list(state.get("sentences", []))
    reveal_sentences = sentences if phase == PHASE_PODIUM else sentences[:max(0, reveal_index + 1)] if phase == PHASE_REVEAL else []
    return {
        "phase": phase,
        "config": state.get("config", {}),
        "players": players or [{"nickname": player_id, "avatar": ""} for player_id in state.get("turn_order", [])],
        "chain_id": state.get("chain_id", "chain_1"),
        "turn_order": list(state.get("turn_order", [])),
        "active_player_id": state.get("active_player_id", ""),
        "current_turn_index": int(state.get("current_turn_index", 0)),
        "total_turns": len(state.get("turn_order", [])),
        "starter_prompt": state.get("starter_prompt", ""),
        "sentences_count": len(sentences),
        "sentences": reveal_sentences,
        "deadline": state.get("deadline"),
        "reveal_index": reveal_index,
        "scores": dict(state.get("scores", {})),
    }


def validate_sentence(text: Any, max_chars: int) -> str:
    sentence = _clean_text(text, max_chars)
    if not sentence:
        raise ValueError("Write a sentence before submitting")
    if len(sentence) < 8:
        raise ValueError("Sentence needs a little more story")
    if sentence.count(" ") < 2:
        raise ValueError("Write a full sentence")
    return sentence


def submit_sentence(state: dict, player_id: str, text: Any, now: float | None = None, timed_out: bool = False) -> dict:
    if state.get("phase") != PHASE_TURN:
        raise ValueError("Story is not accepting sentences")
    if player_id != state.get("active_player_id"):
        raise ValueError("It is not your turn")

    setup = state.get("config", {})
    submitted_at = now or time.time()
    sentence = PLACEHOLDER_SENTENCE if timed_out else validate_sentence(text, int(setup.get("sentence_max_chars", 180)))
    turn_index = int(state.get("current_turn_index", 0))
    order = list(state.get("turn_order", []))
    deadline = state.get("deadline")
    on_time = bool(timed_out) or deadline is None or submitted_at <= float(deadline)

    sentences = list(state.get("sentences", []))
    sentences.append({
        "id": f"sentence_{len(sentences) + 1}",
        "player_id": player_id,
        "text": sentence,
        "position": len(sentences),
        "created_at": submitted_at,
        "timed_out": bool(timed_out),
    })

    scores = dict(state.get("scores", {}))
    scores[player_id] = int(scores.get(player_id, 0)) + POINTS_SENTENCE + (POINTS_ON_TIME if on_time else 0)

    next_index = turn_index + 1
    next_state = {**state, "sentences": sentences, "scores": scores}
    if next_index >= len(order):
        return {
            **next_state,
            "phase": PHASE_REVEAL,
            "active_player_id": "",
            "current_turn_index": len(order),
            "deadline": None,
            "reveal_index": -1,
            "completed_at": submitted_at,
        }

    return {
        **next_state,
        "current_turn_index": next_index,
        "active_player_id": order[next_index],
        "deadline": submitted_at + int(setup.get("turn_time_seconds", 45)),
    }


def timeout_turn(state: dict, now: float | None = None) -> dict:
    active = state.get("active_player_id")
    if not active:
        raise ValueError("No active player")
    return submit_sentence(state, active, PLACEHOLDER_SENTENCE, now=now, timed_out=True)


def next_reveal_step(state: dict) -> dict:
    if state.get("phase") != PHASE_REVEAL:
        raise ValueError("Story is not in reveal")
    next_index = int(state.get("reveal_index", -1)) + 1
    if next_index >= len(state.get("sentences", [])):
        return {**state, "phase": PHASE_PODIUM, "reveal_index": len(state.get("sentences", [])) - 1}
    return {**state, "reveal_index": next_index}


def final_standings(state: dict) -> list[dict[str, Any]]:
    scores = state.get("scores", {})
    return [
        {"nickname": player_id, "score": score, "sentences": len([s for s in state.get("sentences", []) if s.get("player_id") == player_id])}
        for player_id, score in sorted(scores.items(), key=lambda item: (-item[1], item[0].lower()))
    ]
