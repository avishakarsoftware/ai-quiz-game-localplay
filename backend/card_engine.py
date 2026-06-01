"""Reusable playing-card helpers for LocalPlay card games."""
from __future__ import annotations

import random
from math import ceil
from typing import Iterable, Optional


RANKS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
SUITS = ("clubs", "diamonds", "hearts", "spades")
SUIT_LABELS = {
    "clubs": "clubs",
    "diamonds": "diamonds",
    "hearts": "hearts",
    "spades": "spades",
}


def card_id(deck_index: int, suit: str, rank: str) -> str:
    return f"{deck_index}:{suit}:{rank}"


def make_card(rank: str, suit: str, deck_index: int = 0) -> dict:
    if rank not in RANKS:
        raise ValueError(f"Unknown card rank: {rank}")
    if suit not in SUITS:
        raise ValueError(f"Unknown card suit: {suit}")
    return {
        "id": card_id(deck_index, suit, rank),
        "deck_index": deck_index,
        "suit": suit,
        "rank": rank,
        "label": f"{rank} of {SUIT_LABELS[suit]}",
    }


def build_standard_deck(deck_index: int = 0) -> list[dict]:
    return [make_card(rank, suit, deck_index) for suit in SUITS for rank in RANKS]


def build_decks(deck_count: int) -> list[dict]:
    count = max(1, min(4, int(deck_count or 1)))
    cards: list[dict] = []
    for deck_index in range(count):
        cards.extend(build_standard_deck(deck_index))
    return cards


def shuffle_cards(cards: Iterable[dict], seed: str | int | None = None) -> list[dict]:
    shuffled = [dict(card) for card in cards]
    rng = random.Random(seed)
    rng.shuffle(shuffled)
    return shuffled


def deal_round_robin(
    player_ids: list[str],
    cards: list[dict],
    cards_per_player: Optional[int] = None,
    deal_all: bool = True,
) -> dict[str, list[dict]]:
    players = [str(player_id) for player_id in player_ids if str(player_id)]
    if not players:
        raise ValueError("At least one player is required")

    hands = {player_id: [] for player_id in players}
    max_cards = len(cards) if deal_all or cards_per_player is None else min(len(cards), cards_per_player * len(players))
    for index, card in enumerate(cards[:max_cards]):
        hands[players[index % len(players)]].append(dict(card))
    return hands


def remove_cards(hand: list[dict], card_ids: list[str]) -> tuple[list[dict], list[dict]]:
    requested = list(card_ids)
    requested_set = set(requested)
    if len(requested_set) != len(requested):
        raise ValueError("Duplicate card ids are not allowed")

    found = [dict(card) for card in hand if card.get("id") in requested_set]
    if len(found) != len(requested):
        missing = sorted(requested_set - {str(card.get("id")) for card in found})
        raise ValueError(f"Cards not in hand: {', '.join(missing)}")

    remaining = [dict(card) for card in hand if card.get("id") not in requested_set]
    order = {card_id_value: index for index, card_id_value in enumerate(requested)}
    found.sort(key=lambda card: order[str(card["id"])])
    return remaining, found


def count_by_rank(cards: Iterable[dict]) -> dict[str, int]:
    counts = {rank: 0 for rank in RANKS}
    for card in cards:
        rank = str(card.get("rank", ""))
        if rank in counts:
            counts[rank] += 1
    return {rank: count for rank, count in counts.items() if count}


def sort_hand(cards: Iterable[dict]) -> list[dict]:
    rank_order = {rank: index for index, rank in enumerate(RANKS)}
    suit_order = {suit: index for index, suit in enumerate(SUITS)}
    return sorted(
        [dict(card) for card in cards],
        key=lambda card: (
            rank_order.get(str(card.get("rank")), 99),
            suit_order.get(str(card.get("suit")), 99),
            int(card.get("deck_index", 0)),
        ),
    )


def redact_hands(hands: dict[str, list[dict]], viewer_id: str | None = None) -> dict:
    redacted = {}
    for player_id, hand in hands.items():
        if viewer_id is not None and player_id == viewer_id:
            redacted[player_id] = {
                "count": len(hand),
                "cards": sort_hand(hand),
            }
        else:
            redacted[player_id] = {
                "count": len(hand),
            }
    return redacted


def recommended_deck_count(player_count: int, target_cards_per_player: int = 8) -> int:
    players = max(1, int(player_count or 1))
    target = max(1, int(target_cards_per_player or 8))
    return max(1, min(4, ceil((players * target) / 52)))
