import random
import re
import time
from typing import Any


PHASE_ACTIVE = "FIND_ACTIVE"
PHASE_PODIUM = "PODIUM"

DEFAULT_PROMPTS = [
    {"id": "prompt_1", "display": "has visited three countries", "category": "travel"},
    {"id": "prompt_2", "display": "can play a musical instrument", "category": "hobby"},
    {"id": "prompt_3", "display": "likes spicy food", "category": "food"},
    {"id": "prompt_4", "display": "has a pet", "category": "life"},
    {"id": "prompt_5", "display": "has run a 5K", "category": "activity"},
    {"id": "prompt_6", "display": "knows how to cook a signature dish", "category": "food"},
    {"id": "prompt_7", "display": "has lived in more than one city", "category": "travel"},
    {"id": "prompt_8", "display": "shares your birth month", "category": "fun"},
    {"id": "prompt_9", "display": "has been camping", "category": "travel"},
    {"id": "prompt_10", "display": "can say hello in three languages", "category": "skill"},
    {"id": "prompt_11", "display": "has met someone famous", "category": "story"},
    {"id": "prompt_12", "display": "prefers tea over coffee", "category": "food"},
    {"id": "prompt_13", "display": "has won a board game recently", "category": "game"},
    {"id": "prompt_14", "display": "can do a magic trick", "category": "skill"},
    {"id": "prompt_15", "display": "has taken a train trip", "category": "travel"},
    {"id": "prompt_16", "display": "has a favorite karaoke song", "category": "music"},
    {"id": "prompt_17", "display": "has tried gardening", "category": "hobby"},
    {"id": "prompt_18", "display": "has made a handmade gift", "category": "creative"},
    {"id": "prompt_19", "display": "has a favorite dessert recipe", "category": "food"},
    {"id": "prompt_20", "display": "has watched a sunrise this year", "category": "story"},
    {"id": "prompt_21", "display": "can name five constellations", "category": "skill"},
    {"id": "prompt_22", "display": "has played a team sport", "category": "activity"},
    {"id": "prompt_23", "display": "has a favorite local restaurant", "category": "food"},
    {"id": "prompt_24", "display": "has learned a new skill this year", "category": "skill"},
    {"id": "prompt_25", "display": "has a funny travel story", "category": "story"},
    {"id": "prompt_26", "display": "has baked something from scratch", "category": "food"},
    {"id": "prompt_27", "display": "has been to a live concert", "category": "music"},
    {"id": "prompt_28", "display": "has solved an escape room", "category": "game"},
    {"id": "prompt_29", "display": "has tried painting or sketching", "category": "creative"},
    {"id": "prompt_30", "display": "has a go-to dance move", "category": "fun"},
]

DEFAULT_PATTERNS = [
    {"id": "first_line", "label": "First Line"},
    {"id": "four_corners", "label": "Four Corners"},
    {"id": "blackout", "label": "Blackout", "terminal": True},
]


def _clean_text(value: Any, max_chars: int = 140) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(value or ""))
    text = re.sub(r"<\s*/?\s*(script|style|iframe)[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def _clamp_int(raw: dict, key: str, default: int, low: int, high: int) -> int:
    try:
        value = int(raw.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


def validate_config(raw: dict | None) -> dict:
    raw = raw or {}
    layout = str(raw.get("layout") or "bingo_5x5_free").strip().lower()
    if layout not in {"bingo_5x5_free", "bingo_5x5", "bingo_4x4"}:
        layout = "bingo_5x5_free"
    confirmation_mode = str(raw.get("confirmation_mode") or "tap_confirm").strip().lower()
    if confirmation_mode not in {"honor", "tap_confirm"}:
        confirmation_mode = "tap_confirm"
    needed = 16 if layout == "bingo_4x4" else 24 if layout == "bingo_5x5_free" else 25

    prompts = []
    raw_prompts = raw.get("prompts") or raw.get("items") or DEFAULT_PROMPTS
    for index, prompt in enumerate(raw_prompts, start=1):
        if isinstance(prompt, str):
            display = _clean_text(prompt)
            category = "custom"
        else:
            display = _clean_text((prompt or {}).get("display") or (prompt or {}).get("text"))
            category = _clean_text((prompt or {}).get("category") or "custom", 40) or "custom"
        if display:
            prompts.append({"id": f"prompt_{index}", "display": display, "category": category})
    if len(prompts) < needed:
        for prompt in DEFAULT_PROMPTS:
            if len(prompts) >= needed:
                break
            if prompt["display"].lower() not in {item["display"].lower() for item in prompts}:
                prompts.append({**prompt, "id": f"prompt_{len(prompts) + 1}"})
    prompts = prompts[:120]

    patterns = []
    raw_patterns = raw.get("claim_patterns") or [item["id"] for item in DEFAULT_PATTERNS]
    for raw_pattern in raw_patterns:
        pattern_id = raw_pattern.get("id") if isinstance(raw_pattern, dict) else raw_pattern
        pattern_id = str(pattern_id or "").strip().lower()
        known = next((item for item in DEFAULT_PATTERNS if item["id"] == pattern_id), None)
        if known and known["id"] not in {item["id"] for item in patterns}:
            patterns.append(dict(known))
    if not patterns:
        patterns = [dict(DEFAULT_PATTERNS[0])]
    checkin_join_policy = str(raw.get("checkin_join_policy") or "resume_or_join").strip().lower()
    if checkin_join_policy not in {"resume_or_join", "host_started_only"}:
        checkin_join_policy = "resume_or_join"

    return {
        "game_title": _clean_text(raw.get("game_title") or "Find Someone Who", 120) or "Find Someone Who",
        "layout": layout,
        "prompts": prompts,
        "confirmation_mode": confirmation_mode,
        "claim_patterns": patterns,
        "round_time_seconds": _clamp_int(raw, "round_time_seconds", 900, 120, 7200),
        "allow_same_person_multiple_cells": bool(raw.get("allow_same_person_multiple_cells", False)),
        "allow_self_match": bool(raw.get("allow_self_match", False)),
        "free_center_label": _clean_text(raw.get("free_center_label") or "FREE", 30) or "FREE",
        "default_for_checkin": bool(raw.get("default_for_checkin", False)),
        "auto_start_on_first_checkin": bool(raw.get("auto_start_on_first_checkin", True)),
        "checkin_join_policy": checkin_join_policy,
    }


def _layout_size(layout: str) -> int:
    return 4 if layout == "bingo_4x4" else 5


def _free_center(layout: str) -> bool:
    return layout == "bingo_5x5_free"


def generate_card(player_id: str, config: dict, seed: str | int | None = None) -> list[list[dict]]:
    setup = validate_config(config)
    size = _layout_size(setup["layout"])
    free = _free_center(setup["layout"])
    needed = size * size - (1 if free else 0)
    rng = random.Random(f"{seed}:{player_id}")
    prompts = list(setup["prompts"])
    rng.shuffle(prompts)
    chosen = prompts[:needed]
    cells = []
    index = 0
    for row in range(size):
        row_cells = []
        for col in range(size):
            if free and row == size // 2 and col == size // 2:
                row_cells.append({
                    "prompt_id": "free",
                    "display": setup["free_center_label"],
                    "row": row,
                    "column": col,
                    "marked": True,
                    "confirmation_status": "confirmed",
                    "free": True,
                })
            else:
                prompt = chosen[index]
                index += 1
                row_cells.append({
                    "prompt_id": prompt["id"],
                    "display": prompt["display"],
                    "row": row,
                    "column": col,
                    "marked": False,
                    "matched_player_id": "",
                    "matched_player_name": "",
                    "confirmation_status": "unmarked",
                    "free": False,
                })
        cells.append(row_cells)
    return cells


def create_initial_state(player_ids: list[str], config: dict, now: float | None = None, seed: str | int | None = None) -> dict:
    setup = validate_config(config)
    started_at = now or time.time()
    state = {
        "phase": PHASE_ACTIVE,
        "config": setup,
        "cards_by_player": {},
        "pending_confirmations": {},
        "accepted_claims": [],
        "claim_log": [],
        "started_at": started_at,
        "deadline": started_at + int(setup["round_time_seconds"]),
        "completed_at": None,
    }
    for player_id in player_ids:
        state = add_player(state, player_id, seed=seed)
    return state


def add_player(state: dict, player_id: str, seed: str | int | None = None) -> dict:
    player_id = str(player_id or "").strip()
    if not player_id or player_id in state.get("cards_by_player", {}):
        return state
    cards = dict(state.get("cards_by_player", {}))
    cards[player_id] = {
        "card_id": f"find_{player_id}",
        "player_id": player_id,
        "cells": generate_card(player_id, state.get("config", {}), seed=seed or state.get("started_at")),
    }
    return {**state, "cards_by_player": cards}


def _find_cell(card: dict, prompt_id: str) -> dict | None:
    for row in card.get("cells", []):
        for cell in row:
            if cell.get("prompt_id") == prompt_id:
                return cell
    return None


def mark_cell(state: dict, player_id: str, prompt_id: str, matched_player_id: str, now: float | None = None) -> tuple[dict, dict | None]:
    if state.get("phase") != PHASE_ACTIVE:
        raise ValueError("This game is not accepting matches now")
    player_id = str(player_id or "").strip()
    matched_player_id = str(matched_player_id or "").strip()
    if not player_id or player_id not in state.get("cards_by_player", {}):
        raise ValueError("You are not in this game")
    if not matched_player_id or matched_player_id not in state.get("cards_by_player", {}):
        raise ValueError("Choose someone currently in the game")
    setup = state.get("config", {})
    if not setup.get("allow_self_match") and matched_player_id == player_id:
        raise ValueError("Choose someone else for this square")
    card = copy_card(state["cards_by_player"][player_id])
    cell = _find_cell(card, str(prompt_id or ""))
    if not cell or cell.get("free"):
        raise ValueError("That square cannot be marked")
    if not setup.get("allow_same_person_multiple_cells"):
        for row in card.get("cells", []):
            for existing in row:
                if existing.get("prompt_id") != cell.get("prompt_id") and existing.get("matched_player_id") == matched_player_id:
                    raise ValueError("Use each person only once on your card")
    timestamp = now or time.time()
    pending = dict(state.get("pending_confirmations", {}))
    request = None
    if setup.get("confirmation_mode") == "honor":
        cell.update({
            "marked": True,
            "matched_player_id": matched_player_id,
            "matched_player_name": matched_player_id,
            "confirmation_status": "confirmed",
            "confirmed_at": timestamp,
        })
    else:
        request_id = f"confirm_{int(timestamp * 1000)}_{len(pending) + 1}"
        cell.update({
            "marked": False,
            "matched_player_id": matched_player_id,
            "matched_player_name": matched_player_id,
            "confirmation_status": "pending",
            "request_id": request_id,
        })
        request = {
            "id": request_id,
            "requester_id": player_id,
            "matched_player_id": matched_player_id,
            "prompt_id": cell["prompt_id"],
            "display": cell["display"],
            "created_at": timestamp,
        }
        pending[request_id] = request
    cards = dict(state["cards_by_player"])
    cards[player_id] = card
    return {**state, "cards_by_player": cards, "pending_confirmations": pending}, request


def confirm_match(state: dict, player_id: str, request_id: str, accepted: bool, now: float | None = None) -> dict:
    pending = dict(state.get("pending_confirmations", {}))
    request = pending.get(str(request_id or ""))
    if not request:
        raise ValueError("That confirmation is no longer pending")
    if request.get("matched_player_id") != player_id:
        raise ValueError("That confirmation is for another player")
    requester = request["requester_id"]
    card = copy_card(state.get("cards_by_player", {}).get(requester, {}))
    cell = _find_cell(card, request["prompt_id"])
    if not cell:
        raise ValueError("That square no longer exists")
    timestamp = now or time.time()
    if accepted:
        cell.update({
            "marked": True,
            "confirmation_status": "confirmed",
            "confirmed_at": timestamp,
        })
    else:
        cell.update({
            "marked": False,
            "matched_player_id": "",
            "matched_player_name": "",
            "confirmation_status": "denied",
            "request_id": "",
        })
    pending.pop(request["id"], None)
    cards = dict(state.get("cards_by_player", {}))
    cards[requester] = card
    return {**state, "cards_by_player": cards, "pending_confirmations": pending}


def copy_card(card: dict) -> dict:
    return {
        "card_id": card.get("card_id", ""),
        "player_id": card.get("player_id", ""),
        "cells": [[dict(cell) for cell in row] for row in card.get("cells", [])],
    }


def _marked_grid(card: dict) -> list[list[bool]]:
    return [[bool(cell.get("marked") or cell.get("free")) for cell in row] for row in card.get("cells", [])]


def _line_complete(grid: list[list[bool]]) -> bool:
    if not grid:
        return False
    size = len(grid)
    if any(all(row) for row in grid):
        return True
    if any(all(grid[row][col] for row in range(size)) for col in range(size)):
        return True
    return all(grid[i][i] for i in range(size)) or all(grid[i][size - 1 - i] for i in range(size))


def _corners_complete(grid: list[list[bool]]) -> bool:
    if not grid:
        return False
    last = len(grid) - 1
    return grid[0][0] and grid[0][last] and grid[last][0] and grid[last][last]


def _blackout_complete(grid: list[list[bool]]) -> bool:
    return bool(grid) and all(all(row) for row in grid)


def claim_pattern(state: dict, player_id: str, pattern_id: str, now: float | None = None) -> tuple[dict, dict]:
    player_id = str(player_id or "").strip()
    pattern_id = str(pattern_id or "").strip()
    if player_id not in state.get("cards_by_player", {}):
        raise ValueError("You are not in this game")
    if any(claim.get("player_id") == player_id and claim.get("pattern_id") == pattern_id for claim in state.get("accepted_claims", [])):
        raise ValueError("You already claimed that prize")
    known = {pattern["id"]: pattern for pattern in state.get("config", {}).get("claim_patterns", DEFAULT_PATTERNS)}
    if pattern_id not in known:
        raise ValueError("That prize is not available")
    grid = _marked_grid(state["cards_by_player"][player_id])
    complete = (
        _line_complete(grid) if pattern_id == "first_line"
        else _corners_complete(grid) if pattern_id == "four_corners"
        else _blackout_complete(grid) if pattern_id == "blackout"
        else False
    )
    if not complete:
        raise ValueError("That pattern is not complete yet")
    timestamp = now or time.time()
    claim = {
        "id": f"claim_{len(state.get('accepted_claims', [])) + 1}",
        "player_id": player_id,
        "pattern_id": pattern_id,
        "pattern_label": known[pattern_id].get("label", pattern_id),
        "accepted_at": timestamp,
    }
    claims = list(state.get("accepted_claims", [])) + [claim]
    log = list(state.get("claim_log", [])) + [{**claim, "accepted": True}]
    next_state = {**state, "accepted_claims": claims, "claim_log": log}
    if known[pattern_id].get("terminal"):
        next_state = {**next_state, "phase": PHASE_PODIUM, "completed_at": timestamp}
    return next_state, claim


def confirmed_count(card: dict) -> int:
    return sum(1 for row in card.get("cells", []) for cell in row if cell.get("marked") and not cell.get("free"))


def final_standings(state: dict) -> list[dict]:
    claims = state.get("accepted_claims", [])
    claim_counts: dict[str, int] = {}
    last_claim: dict[str, float] = {}
    for claim in claims:
        player_id = claim.get("player_id", "")
        claim_counts[player_id] = claim_counts.get(player_id, 0) + 1
        last_claim[player_id] = max(last_claim.get(player_id, 0), float(claim.get("accepted_at") or 0))
    rows = []
    for player_id, card in state.get("cards_by_player", {}).items():
        rows.append({
            "player_id": player_id,
            "score": claim_counts.get(player_id, 0) * 1000 + confirmed_count(card) * 25,
            "claims": claim_counts.get(player_id, 0),
            "confirmed_cells": confirmed_count(card),
            "last_claim_at": last_claim.get(player_id, 0),
        })
    rows.sort(key=lambda item: (-item["score"], item["last_claim_at"], item["player_id"]))
    return [{**item, "rank": index + 1} for index, item in enumerate(rows)]


def public_sync(state: dict, players: list[dict] | None = None) -> dict:
    players = players or []
    return {
        "phase": state.get("phase", PHASE_ACTIVE),
        "config": {
            "game_title": state.get("config", {}).get("game_title", "Find Someone Who"),
            "layout": state.get("config", {}).get("layout", "bingo_5x5_free"),
            "confirmation_mode": state.get("config", {}).get("confirmation_mode", "tap_confirm"),
            "claim_patterns": state.get("config", {}).get("claim_patterns", DEFAULT_PATTERNS),
            "round_time_seconds": state.get("config", {}).get("round_time_seconds", 900),
        },
        "players": players,
        "player_count": len(state.get("cards_by_player", {})),
        "deadline": state.get("deadline"),
        "accepted_claims": state.get("accepted_claims", []),
        "claim_log": state.get("claim_log", [])[-10:],
        "leaderboard": final_standings(state),
    }


def private_sync(state: dict, player_id: str, players: list[dict] | None = None) -> dict:
    sync = public_sync(state, players=players)
    card = state.get("cards_by_player", {}).get(player_id)
    sync["my_card"] = copy_card(card) if card else None
    sync["my_pending_confirmations"] = [
        dict(request)
        for request in state.get("pending_confirmations", {}).values()
        if request.get("matched_player_id") == player_id
    ]
    sync["my_claimed_patterns"] = [
        claim.get("pattern_id")
        for claim in state.get("accepted_claims", [])
        if claim.get("player_id") == player_id
    ]
    return sync
