import random
import re
import time
from typing import Any

from engine_common import clamp_int as _clamp_int, make_clean_text
_clean_text = make_clean_text(max_chars=180)

PHASE_READY = "CHIT_READY"
PHASE_ACTIVE = "CHIT_ACTIVE"
PHASE_RESULT = "CHIT_RESULT"
PHASE_PODIUM = "PODIUM"

VALID_CATEGORIES = {"question", "action", "funny_face", "mini_challenge", "group"}
VALID_SAFE_LEVELS = {"kids", "family", "work_safe", "spicy"}

DEFAULT_CHITS = [
    {"id": "chit_1", "text": "Make the face you make when someone says there is cake.", "category": "funny_face", "safe_level": "family"},
    {"id": "chit_2", "text": "Tell the room your most useless talent.", "category": "question", "safe_level": "family"},
    {"id": "chit_3", "text": "Do your best slow-motion celebration.", "category": "action", "safe_level": "family"},
    {"id": "chit_4", "text": "Ask someone nearby for a two-word movie review.", "category": "group", "safe_level": "family"},
    {"id": "chit_5", "text": "Say one food you could eat every week.", "category": "question", "safe_level": "family"},
    {"id": "chit_6", "text": "Make your most dramatic villain face.", "category": "funny_face", "safe_level": "family"},
    {"id": "chit_7", "text": "Invent a silly award for someone in the room.", "category": "group", "safe_level": "family"},
    {"id": "chit_8", "text": "Give the party a five-second news headline.", "category": "mini_challenge", "safe_level": "family"},
    {"id": "chit_9", "text": "Do a tiny victory dance from your chair.", "category": "action", "safe_level": "family"},
    {"id": "chit_10", "text": "Name a fictional character you would invite here.", "category": "question", "safe_level": "family"},
]

UNSAFE_PATTERNS = [
    r"\b(drink|shot|alcohol|beer|wine|liquor)\b",
    r"\b(kiss|touch|grope|strip|naked|sexual|sex)\b",
    r"\b(address|password|salary|bank|medical|diagnosis|trauma)\b",
    r"\b(race|religion|caste|disabled|disability|immigration)\b",
]


def _normalize(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _is_unsafe(text: str) -> bool:
    lower = text.lower()
    return any(re.search(pattern, lower) for pattern in UNSAFE_PATTERNS)


def sanitize_chit_deck(raw_chits: list[dict] | None, minimum: int = 5) -> list[dict]:
    chits: list[dict] = []
    seen: set[str] = set()
    source = raw_chits if isinstance(raw_chits, list) else []
    for index, item in enumerate(source, start=1):
        if not isinstance(item, dict):
            continue
        text = _clean_text(item.get("text"), 180)
        key = _normalize(text)
        if len(text) < 3 or key in seen or _is_unsafe(text):
            continue
        category = _normalize(item.get("category")).replace(" ", "_")
        if category not in VALID_CATEGORIES:
            category = "question"
        safe_level = _normalize(item.get("safe_level")).replace(" ", "_")
        if safe_level not in VALID_SAFE_LEVELS:
            safe_level = "family"
        seen.add(key)
        chits.append({
            "id": _clean_text(item.get("id") or f"chit_{index}", 40) or f"chit_{index}",
            "text": text,
            "category": category,
            "safe_level": safe_level,
        })
        if len(chits) >= 200:
            break
    if len(chits) < minimum:
        for item in DEFAULT_CHITS:
            key = _normalize(item["text"])
            if key not in seen:
                seen.add(key)
                chits.append(dict(item))
            if len(chits) >= minimum:
                break
    return chits


def validate_config(raw: dict | None) -> dict:
    raw = raw or {}
    chits = sanitize_chit_deck(raw.get("chits"), minimum=5)
    rounds = _clamp_int(raw, "rounds", min(20, len(chits)), 5, 100)
    safe_level = _normalize(raw.get("safe_level") or "family").replace(" ", "_")
    if safe_level not in VALID_SAFE_LEVELS:
        safe_level = "family"
    return {
        "game_title": _clean_text(raw.get("game_title") or "Random Chit", 120) or "Random Chit",
        "selection_mode": "random_player",
        "rounds": min(rounds, len(chits) if not bool(raw.get("allow_chit_repeats", False)) else rounds),
        "turn_time_seconds": _clamp_int(raw, "turn_time_seconds", 30, 10, 120),
        "allow_player_repeats": bool(raw.get("allow_player_repeats", True)),
        "allow_chit_repeats": bool(raw.get("allow_chit_repeats", False)),
        "skip_limit_per_player": _clamp_int(raw, "skip_limit_per_player", 2, 0, 10),
        "scoring_enabled": bool(raw.get("scoring_enabled", True)),
        "completion_points": _clamp_int(raw, "completion_points", 100, 0, 1000),
        "bonus_points": _clamp_int(raw, "bonus_points", 50, 0, 500),
        "safe_level": safe_level,
        "chits": chits,
    }


def create_initial_state(player_ids: list[str], config: dict, now: float | None = None, seed: str | int | None = None) -> dict:
    setup = validate_config(config)
    players = [str(player_id) for player_id in player_ids if str(player_id)]
    rng = random.Random(seed)
    return {
        "phase": PHASE_READY,
        "config": setup,
        "players": players,
        "round_index": 0,
        "selected_player_id": "",
        "current_chit": None,
        "used_chit_ids": [],
        "player_turn_counts": {player_id: 0 for player_id in players},
        "skips_by_player": {player_id: 0 for player_id in players},
        "scores": {player_id: 0 for player_id in players},
        "turn_results": [],
        "deadline": None,
        "_rng_state": rng.getstate(),
        "created_at": now or time.time(),
        "completed_at": None,
    }


def _rng(state: dict) -> random.Random:
    rng = random.Random()
    if state.get("_rng_state") is not None:
        rng.setstate(state["_rng_state"])
    return rng


def _save_rng(state: dict, rng: random.Random) -> dict:
    next_state = dict(state)
    next_state["_rng_state"] = rng.getstate()
    return next_state


def _available_players(state: dict) -> list[str]:
    players = [player_id for player_id in state.get("players", []) if player_id]
    if state.get("config", {}).get("allow_player_repeats", True):
        return players
    counts = state.get("player_turn_counts", {})
    min_turns = min((int(counts.get(player_id, 0)) for player_id in players), default=0)
    return [player_id for player_id in players if int(counts.get(player_id, 0)) == min_turns]


def _available_chits(state: dict) -> list[dict]:
    chits = list(state.get("config", {}).get("chits", []))
    if state.get("config", {}).get("allow_chit_repeats", False):
        return chits
    used = set(state.get("used_chit_ids", []))
    return [chit for chit in chits if chit.get("id") not in used]


def _draw(state: dict, redraw_player_only: bool = False, redraw_chit_only: bool = False, now: float | None = None) -> dict:
    if state.get("phase") == PHASE_PODIUM:
        raise ValueError("The game is over")
    if int(state.get("round_index", 0)) >= int(state.get("config", {}).get("rounds", 0)):
        return {**state, "phase": PHASE_PODIUM, "completed_at": now or time.time(), "deadline": None}

    rng = _rng(state)
    next_state = dict(state)
    if not redraw_chit_only:
        players = _available_players(state)
        if not players:
            raise ValueError("No players are available")
        if redraw_player_only and len(players) > 1:
            current_player = str(state.get("selected_player_id") or "")
            players = [player_id for player_id in players if player_id != current_player] or players
        next_state["selected_player_id"] = rng.choice(players)
    if not redraw_player_only:
        chits = _available_chits(state)
        if not chits:
            return {**next_state, "phase": PHASE_PODIUM, "completed_at": now or time.time(), "deadline": None}
        if redraw_chit_only and len(chits) > 1:
            current_chit_id = (state.get("current_chit") or {}).get("id")
            chits = [chit for chit in chits if chit.get("id") != current_chit_id] or chits
        next_state["current_chit"] = rng.choice(chits)
    next_state["phase"] = PHASE_ACTIVE
    next_state["deadline"] = (now or time.time()) + int(state.get("config", {}).get("turn_time_seconds", 30))
    return _save_rng(next_state, rng)


def draw_turn(state: dict, now: float | None = None) -> dict:
    return _draw(state, now=now)


def redraw_player(state: dict, now: float | None = None) -> dict:
    return _draw(state, redraw_player_only=True, now=now)


def redraw_chit(state: dict, now: float | None = None) -> dict:
    return _draw(state, redraw_chit_only=True, now=now)


def _resolve_turn(state: dict, outcome: str, bonus: bool = False, now: float | None = None) -> dict:
    if state.get("phase") != PHASE_ACTIVE:
        raise ValueError("No active chit to resolve")
    player_id = str(state.get("selected_player_id") or "")
    chit = state.get("current_chit") or {}
    if not player_id or not chit.get("id"):
        raise ValueError("No active chit to resolve")
    config = state.get("config", {})
    points = 0
    if outcome == "completed" and bool(config.get("scoring_enabled", True)):
        points = int(config.get("completion_points", 100)) + (int(config.get("bonus_points", 50)) if bonus else 0)
    scores = dict(state.get("scores", {}))
    scores[player_id] = int(scores.get(player_id, 0)) + points
    turn_counts = dict(state.get("player_turn_counts", {}))
    turn_counts[player_id] = int(turn_counts.get(player_id, 0)) + 1
    skips = dict(state.get("skips_by_player", {}))
    if outcome == "skipped":
        skips[player_id] = int(skips.get(player_id, 0)) + 1
    used = list(state.get("used_chit_ids", []))
    if chit.get("id") not in used:
        used.append(chit.get("id"))
    round_number = int(state.get("round_index", 0)) + 1
    result = {
        "round_number": round_number,
        "player_id": player_id,
        "chit_id": chit.get("id"),
        "chit_text": chit.get("text"),
        "category": chit.get("category", "question"),
        "outcome": outcome,
        "bonus": bool(bonus),
        "points_awarded": points,
        "completed_at": now or time.time(),
    }
    next_state = {
        **state,
        "phase": PHASE_RESULT,
        "scores": scores,
        "player_turn_counts": turn_counts,
        "skips_by_player": skips,
        "used_chit_ids": used,
        "turn_results": list(state.get("turn_results", [])) + [result],
        "round_index": round_number,
        "deadline": None,
    }
    if round_number >= int(config.get("rounds", 0)):
        next_state["phase"] = PHASE_PODIUM
        next_state["completed_at"] = now or time.time()
    return next_state


def complete_turn(state: dict, bonus: bool = False, now: float | None = None) -> dict:
    return _resolve_turn(state, "completed", bonus=bonus, now=now)


def skip_turn(state: dict, now: float | None = None) -> dict:
    return _resolve_turn(state, "skipped", bonus=False, now=now)


def public_sync(state: dict, players: list[dict[str, str]] | None = None) -> dict:
    config_payload = {key: value for key, value in state.get("config", {}).items() if key != "chits"}
    config_payload["chit_count"] = len(state.get("config", {}).get("chits", []))
    return {
        "phase": state.get("phase", PHASE_READY),
        "config": config_payload,
        "players": players or [{"nickname": player_id, "avatar": ""} for player_id in state.get("players", [])],
        "round_number": min(int(state.get("round_index", 0)) + 1, int(state.get("config", {}).get("rounds", 0))),
        "total_rounds": int(state.get("config", {}).get("rounds", 0)),
        "selected_player_id": state.get("selected_player_id", ""),
        "current_chit": state.get("current_chit"),
        "used_chit_ids": list(state.get("used_chit_ids", [])),
        "player_turn_counts": dict(state.get("player_turn_counts", {})),
        "skips_by_player": dict(state.get("skips_by_player", {})),
        "scores": dict(state.get("scores", {})),
        "turn_results": list(state.get("turn_results", []))[-10:],
        "deadline": state.get("deadline"),
    }


def final_standings(state: dict) -> list[dict[str, Any]]:
    scores = state.get("scores", {})
    turn_counts = state.get("player_turn_counts", {})
    skips = state.get("skips_by_player", {})
    return [
        {
            "nickname": player_id,
            "score": int(scores.get(player_id, 0)),
            "turns": int(turn_counts.get(player_id, 0)),
            "skips": int(skips.get(player_id, 0)),
        }
        for player_id in sorted(
            state.get("players", []),
            key=lambda player_id: (
                -int(scores.get(player_id, 0)),
                -int(turn_counts.get(player_id, 0)),
                int(skips.get(player_id, 0)),
                str(player_id).lower(),
            ),
        )
    ]


def sanitize_generated_game(raw: dict, fallback_title: str = "Random Chit") -> dict:
    if not isinstance(raw, dict):
        raw = {}
    return validate_config({
        "game_title": raw.get("game_title") or fallback_title,
        "safe_level": raw.get("safe_level") or "family",
        "rounds": raw.get("rounds") or len(raw.get("chits") or []),
        "chits": raw.get("chits") or [],
    })


def validate_generated_game(raw: dict) -> bool:
    try:
        game = sanitize_generated_game(raw)
    except Exception:
        return False
    return len(game.get("chits", [])) >= 5
