"""Party Poker quick Hold'em tournament mechanics.

This MVP keeps poker party-safe and fast: every active player posts the same
play-chip ante, receives two private cards, sees a five-card board, then chooses
Stay or Fold. The best remaining Hold'em hand wins the pot.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from card_engine import build_standard_deck, shuffle_cards
from poker_hand_evaluator import rank_players


PHASE_DECISION = "POKER_DECISION"
PHASE_SHOWDOWN = "POKER_SHOWDOWN"
PHASE_PODIUM = "PODIUM"


def _clamp_int(raw: dict, key: str, default: int, low: int, high: int) -> int:
    try:
        value = int(raw.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


def validate_config(raw: Optional[dict]) -> dict:
    raw = raw or {}
    title = str(raw.get("game_title") or raw.get("title") or "Party Poker").strip()[:120] or "Party Poker"
    starting_stack = _clamp_int(raw, "starting_stack", 1000, 200, 10000)
    ante = _clamp_int(raw, "ante", raw.get("big_blind", 20), 5, 500)
    if ante >= starting_stack:
        ante = max(5, starting_stack // 20)
    return {
        "game_title": title,
        "variant": "quick_holdem_tournament",
        "starting_stack": starting_stack,
        "ante": ante,
        "decision_time_seconds": _clamp_int(raw, "decision_time_seconds", 25, 10, 90),
    }


def _players(player_ids: list[str]) -> list[str]:
    cleaned = [str(player_id).strip() for player_id in player_ids if str(player_id).strip()]
    if len(cleaned) < 2:
        raise ValueError("Party Poker requires at least 2 players")
    if len(cleaned) > 10:
        raise ValueError("Party Poker supports up to 10 players")
    if len(set(cleaned)) != len(cleaned):
        raise ValueError("Player ids must be unique")
    return cleaned


def create_initial_state(player_ids: list[str], config: Optional[dict] = None, seed: str | int | None = None, now: float | None = None) -> dict:
    players = _players(player_ids)
    setup = validate_config(config)
    state = {
        "phase": PHASE_DECISION,
        "config": setup,
        "players": players,
        "stacks": {player_id: setup["starting_stack"] for player_id in players},
        "statuses": {player_id: "active" for player_id in players},
        "dealer_index": 0,
        "hand_number": 0,
        "hole_cards": {},
        "community_cards": [],
        "pot": 0,
        "decisions": {},
        "hand_result": None,
        "eliminations": [],
        "standings": [],
        "deadline": None,
        "seed": seed,
    }
    return start_next_hand(state, now=now)


def _copy_state(state: dict) -> dict:
    copied = dict(state)
    copied["config"] = dict(state.get("config") or {})
    copied["players"] = list(state.get("players") or [])
    copied["stacks"] = dict(state.get("stacks") or {})
    copied["statuses"] = dict(state.get("statuses") or {})
    copied["hole_cards"] = {player_id: [dict(card) for card in cards] for player_id, cards in (state.get("hole_cards") or {}).items()}
    copied["community_cards"] = [dict(card) for card in state.get("community_cards") or []]
    copied["decisions"] = dict(state.get("decisions") or {})
    copied["hand_result"] = dict(state["hand_result"]) if state.get("hand_result") else None
    copied["eliminations"] = [dict(item) for item in state.get("eliminations") or []]
    copied["standings"] = [dict(item) for item in state.get("standings") or []]
    return copied


def active_players(state: dict) -> list[str]:
    return [player_id for player_id in state.get("players", []) if int(state.get("stacks", {}).get(player_id, 0)) > 0 and state.get("statuses", {}).get(player_id) != "eliminated"]


def start_next_hand(state: dict, now: float | None = None) -> dict:
    next_state = _copy_state(state)
    live = active_players(next_state)
    if len(live) <= 1:
        return _complete_tournament(next_state, live[0] if live else "")

    next_state["phase"] = PHASE_DECISION
    next_state["hand_number"] = int(next_state.get("hand_number", 0)) + 1
    next_state["hand_result"] = None
    next_state["decisions"] = {player_id: "pending" for player_id in live}
    next_state["statuses"] = {player_id: ("in_hand" if player_id in live else "eliminated") for player_id in next_state["players"]}
    next_state["pot"] = 0
    ante = int(next_state["config"]["ante"])
    for player_id in live:
        contribution = min(ante, int(next_state["stacks"].get(player_id, 0)))
        next_state["stacks"][player_id] = int(next_state["stacks"].get(player_id, 0)) - contribution
        next_state["pot"] += contribution

    seed = f"{next_state.get('seed') or ''}:{next_state['hand_number']}:{int(now or time.time())}"
    deck = shuffle_cards(build_standard_deck(), seed=seed)
    next_state["hole_cards"] = {player_id: [deck.pop(), deck.pop()] for player_id in live}
    next_state["community_cards"] = [deck.pop() for _ in range(5)]
    next_state["deadline"] = (now or time.time()) + int(next_state["config"]["decision_time_seconds"])
    return next_state


def submit_decision(state: dict, player_id: str, decision: str) -> dict:
    if state.get("phase") != PHASE_DECISION:
        raise ValueError("Poker decisions are closed for this hand")
    if player_id not in state.get("decisions", {}):
        raise ValueError("You are not in this poker hand")
    normalized = str(decision or "").strip().lower()
    if normalized not in {"stay", "fold"}:
        raise ValueError("Choose stay or fold")
    next_state = _copy_state(state)
    next_state["decisions"][player_id] = normalized
    next_state["statuses"][player_id] = "folded" if normalized == "fold" else "staying"
    pending = [value for value in next_state["decisions"].values() if value == "pending"]
    if not pending:
        next_state = reveal_hand(next_state)
    elif len([p for p, value in next_state["decisions"].items() if value != "fold"]) <= 1:
        next_state = reveal_hand(next_state)
    return next_state


def reveal_hand(state: dict) -> dict:
    if state.get("phase") not in {PHASE_DECISION, PHASE_SHOWDOWN}:
        raise ValueError("No poker hand to reveal")
    next_state = _copy_state(state)
    contenders = [player_id for player_id, decision in next_state.get("decisions", {}).items() if decision != "fold"]
    if not contenders:
        contenders = list(next_state.get("decisions", {}).keys())[:1]
    if len(contenders) == 1:
        winner_id = contenders[0]
        ranked = [{"player_id": winner_id, "place": 1, "evaluation": None}]
    else:
        ranked = rank_players({player_id: next_state["hole_cards"][player_id] for player_id in contenders}, next_state["community_cards"])
        winner_id = ranked[0]["player_id"]
    pot = int(next_state.get("pot", 0))
    # Split the pot among all players tied for the best hand (place == 1). Odd
    # chips go to the earliest-ranked winners. Awarding the whole pot to a single
    # player on a tie silently destroyed chips that the tied players had anted.
    winner_ids = [row["player_id"] for row in ranked if int(row.get("place", 1)) == 1] or [winner_id]
    base_share = pot // len(winner_ids)
    remainder = pot - base_share * len(winner_ids)
    payouts: dict[str, int] = {}
    for index, pid in enumerate(winner_ids):
        award = base_share + (1 if index < remainder else 0)
        next_state["stacks"][pid] = int(next_state["stacks"].get(pid, 0)) + award
        payouts[pid] = award
    next_state["phase"] = PHASE_SHOWDOWN
    next_state["deadline"] = None
    next_state["hand_result"] = {
        "winner_id": winner_id,
        "winner_ids": winner_ids,
        "payouts": payouts,
        "pot": pot,
        "ranked": ranked,
        "decisions": dict(next_state.get("decisions") or {}),
    }
    _record_eliminations(next_state)
    if len(active_players(next_state)) <= 1:
        winner = active_players(next_state)[0] if active_players(next_state) else winner_id
        return _complete_tournament(next_state, winner)
    return next_state


def _record_eliminations(state: dict) -> None:
    eliminated = {item["player_id"] for item in state.get("eliminations", [])}
    remaining_count = len([p for p in state.get("players", []) if p not in eliminated])
    for player_id in state.get("players", []):
        if player_id in eliminated:
            continue
        if int(state.get("stacks", {}).get(player_id, 0)) <= 0:
            state["statuses"][player_id] = "eliminated"
            state.setdefault("eliminations", []).append({
                "player_id": player_id,
                "place": max(2, remaining_count),
                "hand_number": state.get("hand_number", 0),
            })
            remaining_count -= 1


def _complete_tournament(state: dict, winner_id: str) -> dict:
    next_state = _copy_state(state)
    next_state["phase"] = PHASE_PODIUM
    next_state["deadline"] = None
    existing = {item["player_id"]: item for item in next_state.get("eliminations", [])}
    standings = []
    if winner_id:
        standings.append({"player_id": winner_id, "place": 1, "stack": int(next_state.get("stacks", {}).get(winner_id, 0))})
    for item in sorted(existing.values(), key=lambda row: int(row.get("place", 999))):
        standings.append({**item, "stack": int(next_state.get("stacks", {}).get(item["player_id"], 0))})
    seen = {row["player_id"] for row in standings}
    for player_id in next_state.get("players", []):
        if player_id not in seen:
            standings.append({"player_id": player_id, "place": len(standings) + 1, "stack": int(next_state.get("stacks", {}).get(player_id, 0))})
    next_state["standings"] = standings
    return next_state


def _redact_card(card: dict) -> dict:
    return {"id": card.get("id", "hidden"), "hidden": True}


def public_sync(state: dict, viewer_id: str | None = None) -> dict:
    reveal = state.get("phase") in {PHASE_SHOWDOWN, PHASE_PODIUM}
    hole_cards = {}
    for player_id, cards in (state.get("hole_cards") or {}).items():
        if reveal or (viewer_id and player_id == viewer_id):
            hole_cards[player_id] = [dict(card) for card in cards]
        else:
            hole_cards[player_id] = [_redact_card(card) for card in cards]
    return {
        "phase": state.get("phase"),
        "config": dict(state.get("config") or {}),
        "players": list(state.get("players") or []),
        "stacks": dict(state.get("stacks") or {}),
        "statuses": dict(state.get("statuses") or {}),
        "hand_number": int(state.get("hand_number", 0)),
        "dealer_index": int(state.get("dealer_index", 0)),
        "community_cards": [dict(card) for card in state.get("community_cards") or []],
        "hole_cards": hole_cards,
        "pot": int(state.get("pot", 0)),
        "decisions": dict(state.get("decisions") or {}),
        "hand_result": dict(state["hand_result"]) if state.get("hand_result") else None,
        "standings": [dict(item) for item in state.get("standings") or []],
        "deadline": state.get("deadline"),
        "your_decision": (state.get("decisions") or {}).get(viewer_id) if viewer_id else None,
    }
