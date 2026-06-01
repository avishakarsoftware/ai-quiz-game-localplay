"""Pure Bluff/Cheat card game logic."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from card_engine import (
    RANKS,
    build_decks,
    deal_round_robin,
    recommended_deck_count,
    redact_hands,
    remove_cards,
    shuffle_cards,
    sort_hand,
)


PHASE_TURN = "BLUFF_TURN"
PHASE_CHALLENGE = "BLUFF_CHALLENGE"
PHASE_REVEAL = "BLUFF_REVEAL"
PHASE_PODIUM = "PODIUM"


@dataclass(frozen=True)
class BluffConfig:
    game_title: str = "Bluff"
    deck_count: int = 1
    allow_pass: bool = True
    challenge_window_seconds: int = 12
    turn_time_seconds: int = 30
    target_cards_per_player: int = 8

    def to_dict(self) -> dict:
        return {
            "game_title": self.game_title,
            "deck_count": self.deck_count,
            "allow_pass": self.allow_pass,
            "challenge_window_seconds": self.challenge_window_seconds,
            "turn_time_seconds": self.turn_time_seconds,
            "target_cards_per_player": self.target_cards_per_player,
        }


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def validate_config(raw: Optional[dict], player_count: int = 0) -> dict:
    raw = raw or {}
    title = str(raw.get("game_title") or raw.get("title") or "Bluff").strip()[:120] or "Bluff"

    try:
        target_cards = int(raw.get("target_cards_per_player", 8))
    except (TypeError, ValueError):
        target_cards = 8
    target_cards = _clamp(target_cards, 4, 20)

    recommended = recommended_deck_count(max(1, player_count), target_cards)
    try:
        deck_count = int(raw.get("deck_count", recommended))
    except (TypeError, ValueError):
        deck_count = recommended
    deck_count = _clamp(deck_count, 1, 4)

    try:
        challenge_window = int(raw.get("challenge_window_seconds", 12))
    except (TypeError, ValueError):
        challenge_window = 12
    challenge_window = _clamp(challenge_window, 5, 60)

    try:
        turn_time = int(raw.get("turn_time_seconds", 30))
    except (TypeError, ValueError):
        turn_time = 30
    turn_time = _clamp(turn_time, 10, 120)

    return BluffConfig(
        game_title=title,
        deck_count=deck_count,
        allow_pass=bool(raw.get("allow_pass", True)),
        challenge_window_seconds=challenge_window,
        turn_time_seconds=turn_time,
        target_cards_per_player=target_cards,
    ).to_dict()


def _validate_players(player_ids: list[str]) -> list[str]:
    players = [str(player_id).strip() for player_id in player_ids if str(player_id).strip()]
    if len(players) < 3:
        raise ValueError("Bluff requires at least 3 players")
    if len(set(players)) != len(players):
        raise ValueError("Player ids must be unique")
    if len(players) > 20:
        raise ValueError("Bluff supports up to 20 players in v1")
    return players


def next_rank(rank: str | None) -> str:
    if rank not in RANKS:
        return RANKS[0]
    return RANKS[(RANKS.index(rank) + 1) % len(RANKS)]


def create_initial_state(player_ids: list[str], config: Optional[dict] = None, seed: str | int | None = None) -> dict:
    players = _validate_players(player_ids)
    validated = validate_config(config, player_count=len(players))
    deck = shuffle_cards(build_decks(validated["deck_count"]), seed=seed)
    hands = deal_round_robin(players, deck, deal_all=True)
    return {
        "phase": PHASE_TURN,
        "players": players,
        "config": validated,
        "hands": {player_id: sort_hand(hand) for player_id, hand in hands.items()},
        "pile": [],
        "last_claim": None,
        "required_rank": RANKS[0],
        "rank_index": 0,
        "turn_index": 0,
        "active_player_id": players[0],
        "winners": [],
        "revealed_cards": [],
        "challenge_deadline": None,
    }


def _copy_state(state: dict) -> dict:
    copied = dict(state)
    copied["players"] = list(state.get("players", []))
    copied["config"] = dict(state.get("config", {}))
    copied["hands"] = {player_id: [dict(card) for card in hand] for player_id, hand in state.get("hands", {}).items()}
    copied["pile"] = [dict(card) for card in state.get("pile", [])]
    copied["last_claim"] = dict(state["last_claim"]) if state.get("last_claim") else None
    copied["winners"] = [dict(winner) for winner in state.get("winners", [])]
    copied["revealed_cards"] = [dict(card) for card in state.get("revealed_cards", [])]
    return copied


def _remaining_players(state: dict) -> list[str]:
    winners = {winner["player_id"] for winner in state.get("winners", [])}
    return [player_id for player_id in state.get("players", []) if player_id not in winners]


def _advance_turn(state: dict) -> None:
    remaining = _remaining_players(state)
    if len(remaining) <= 1:
        if remaining:
            _record_winner(state, remaining[0])
        state["phase"] = PHASE_PODIUM
        state["active_player_id"] = None
        return

    players = state["players"]
    current_index = int(state.get("turn_index", 0))
    for offset in range(1, len(players) + 1):
        next_index = (current_index + offset) % len(players)
        candidate = players[next_index]
        if candidate in remaining:
            state["turn_index"] = next_index
            state["active_player_id"] = candidate
            return


def _advance_rank(state: dict) -> None:
    current = str(state.get("required_rank") or RANKS[0])
    next_value = next_rank(current)
    state["required_rank"] = next_value
    state["rank_index"] = RANKS.index(next_value)


def _record_winner(state: dict, player_id: str) -> None:
    if any(winner["player_id"] == player_id for winner in state.get("winners", [])):
        return
    state.setdefault("winners", []).append({
        "player_id": player_id,
        "place": len(state.get("winners", [])) + 1,
    })


def play_cards(state: dict, player_id: str, card_ids: list[str], now: float = 0) -> dict:
    if state.get("phase") != PHASE_TURN:
        raise ValueError("Cards can only be played during a turn")
    if player_id != state.get("active_player_id"):
        raise ValueError("Only the active player can play")
    if not card_ids:
        raise ValueError("Play at least one card or pass")

    next_state = _copy_state(state)
    hand = next_state["hands"].get(player_id, [])
    remaining, played = remove_cards(hand, card_ids)
    next_state["hands"][player_id] = sort_hand(remaining)
    claim = {
        "actor_id": player_id,
        "claimed_rank": next_state["required_rank"],
        "claimed_count": len(played),
        "card_ids": [card["id"] for card in played],
        "created_at": now,
    }
    next_state["last_claim"] = claim
    next_state["pile"].extend(played)
    next_state["revealed_cards"] = []
    next_state["challenge_deadline"] = now + next_state["config"]["challenge_window_seconds"]
    next_state["phase"] = PHASE_CHALLENGE
    return next_state


def pass_turn(state: dict, player_id: str) -> dict:
    if state.get("phase") != PHASE_TURN:
        raise ValueError("Pass is only allowed during a turn")
    if player_id != state.get("active_player_id"):
        raise ValueError("Only the active player can pass")
    if not state.get("config", {}).get("allow_pass", True):
        raise ValueError("Passing is disabled")

    next_state = _copy_state(state)
    _advance_turn(next_state)
    return next_state


def resolve_unchallenged(state: dict) -> dict:
    if state.get("phase") != PHASE_CHALLENGE or not state.get("last_claim"):
        raise ValueError("No challenge window to resolve")

    next_state = _copy_state(state)
    actor_id = next_state["last_claim"]["actor_id"]
    if not next_state["hands"].get(actor_id):
        _record_winner(next_state, actor_id)
    _advance_rank(next_state)
    next_state["last_claim"] = None
    next_state["challenge_deadline"] = None
    next_state["phase"] = PHASE_TURN
    _advance_turn(next_state)
    return next_state


def challenge_claim(state: dict, challenger_id: str) -> dict:
    if state.get("phase") != PHASE_CHALLENGE or not state.get("last_claim"):
        raise ValueError("There is no active claim to challenge")
    claim = state["last_claim"]
    actor_id = claim["actor_id"]
    if challenger_id == actor_id:
        raise ValueError("Actor cannot challenge their own claim")
    if challenger_id not in _remaining_players(state):
        raise ValueError("Only active players can challenge")

    next_state = _copy_state(state)
    played_ids = set(claim.get("card_ids", []))
    revealed = [dict(card) for card in next_state["pile"] if card.get("id") in played_ids]
    truthful = bool(revealed) and all(card.get("rank") == claim["claimed_rank"] for card in revealed)
    loser_id = challenger_id if truthful else actor_id

    next_state["hands"][loser_id] = sort_hand(next_state["hands"].get(loser_id, []) + next_state["pile"])
    next_state["pile"] = []
    next_state["revealed_cards"] = revealed
    next_state["last_claim"] = {
        **claim,
        "challenger_id": challenger_id,
        "truthful": truthful,
        "loser_id": loser_id,
    }
    next_state["challenge_deadline"] = None
    next_state["phase"] = PHASE_REVEAL
    return next_state


def continue_after_reveal(state: dict) -> dict:
    if state.get("phase") != PHASE_REVEAL:
        raise ValueError("Can only continue after a reveal")
    next_state = _copy_state(state)
    claim = next_state.get("last_claim") or {}
    actor_id = claim.get("actor_id")
    if claim.get("truthful") and actor_id and not next_state["hands"].get(actor_id):
        _record_winner(next_state, actor_id)
    _advance_rank(next_state)
    next_state["last_claim"] = None
    next_state["revealed_cards"] = []
    next_state["phase"] = PHASE_TURN
    _advance_turn(next_state)
    return next_state


def public_sync(state: dict) -> dict:
    return {
        "phase": state.get("phase"),
        "players": list(state.get("players", [])),
        "active_player_id": state.get("active_player_id"),
        "required_rank": state.get("required_rank"),
        "pile_count": len(state.get("pile", [])),
        "hands": redact_hands(state.get("hands", {}), viewer_id=None),
        "last_claim": dict(state["last_claim"]) if state.get("last_claim") else None,
        "revealed_cards": [dict(card) for card in state.get("revealed_cards", [])],
        "challenge_deadline": state.get("challenge_deadline"),
        "winners": [dict(winner) for winner in state.get("winners", [])],
    }


def private_sync(state: dict, viewer_id: str) -> dict:
    sync = public_sync(state)
    sync["hands"] = redact_hands(state.get("hands", {}), viewer_id=viewer_id)
    return sync
