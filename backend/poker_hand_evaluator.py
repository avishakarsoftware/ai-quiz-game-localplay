"""Texas Hold'em hand evaluation helpers.

This module is intentionally pure and independent of sockets/UI. It evaluates
the best 5-card hand from 5-7 standard LocalPlay card dictionaries.
"""
from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import Iterable


RANK_VALUE = {
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
    "10": 10,
    "J": 11,
    "Q": 12,
    "K": 13,
    "A": 14,
}

CATEGORY_NAMES = {
    8: "straight_flush",
    7: "four_of_a_kind",
    6: "full_house",
    5: "flush",
    4: "straight",
    3: "three_of_a_kind",
    2: "two_pair",
    1: "one_pair",
    0: "high_card",
}


def _rank_values(cards: Iterable[dict]) -> list[int]:
    values = []
    for card in cards:
        value = RANK_VALUE.get(str(card.get("rank")))
        if value:
            values.append(value)
    return values


def _straight_high(values: Iterable[int]) -> int:
    unique = sorted(set(values), reverse=True)
    if 14 in unique:
        unique.append(1)
    for window in range(len(unique) - 4):
        run = unique[window:window + 5]
        if run[0] - run[4] == 4 and len(set(run)) == 5:
            return 5 if run[0] == 5 else run[0]
    return 0


def evaluate_five(cards: list[dict]) -> tuple[int, tuple[int, ...]]:
    if len(cards) != 5:
        raise ValueError("evaluate_five requires exactly 5 cards")
    values = sorted(_rank_values(cards), reverse=True)
    if len(values) != 5:
        raise ValueError("Cards must use standard poker ranks")
    suits = [str(card.get("suit")) for card in cards]
    counts = Counter(values)
    groups = sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)
    flush = len(set(suits)) == 1
    straight = _straight_high(values)

    if flush and straight:
        return 8, (straight,)
    if groups[0][1] == 4:
        four = groups[0][0]
        kicker = max(value for value in values if value != four)
        return 7, (four, kicker)
    if groups[0][1] == 3 and groups[1][1] == 2:
        return 6, (groups[0][0], groups[1][0])
    if flush:
        return 5, tuple(values)
    if straight:
        return 4, (straight,)
    if groups[0][1] == 3:
        trips = groups[0][0]
        kickers = sorted((value for value in values if value != trips), reverse=True)
        return 3, (trips, *kickers)
    pairs = sorted((rank for rank, count in counts.items() if count == 2), reverse=True)
    if len(pairs) == 2:
        kicker = max(value for value in values if value not in pairs)
        return 2, (pairs[0], pairs[1], kicker)
    if len(pairs) == 1:
        pair = pairs[0]
        kickers = sorted((value for value in values if value != pair), reverse=True)
        return 1, (pair, *kickers)
    return 0, tuple(values)


def evaluate_best(cards: list[dict]) -> dict:
    if len(cards) < 5 or len(cards) > 7:
        raise ValueError("Poker evaluation requires 5 to 7 cards")
    best_rank: tuple[int, tuple[int, ...]] | None = None
    best_cards: list[dict] = []
    for combo in combinations(cards, 5):
        rank = evaluate_five(list(combo))
        if best_rank is None or rank > best_rank:
            best_rank = rank
            best_cards = [dict(card) for card in combo]
    assert best_rank is not None
    category, kickers = best_rank
    return {
        "category": CATEGORY_NAMES[category],
        "category_rank": category,
        "tiebreakers": list(kickers),
        "cards": best_cards,
        "rank_tuple": (category, *kickers),
    }


def compare_hands(left: list[dict], right: list[dict]) -> int:
    left_rank = tuple(evaluate_best(left)["rank_tuple"])
    right_rank = tuple(evaluate_best(right)["rank_tuple"])
    return (left_rank > right_rank) - (left_rank < right_rank)


def rank_players(player_cards: dict[str, list[dict]], board: list[dict]) -> list[dict]:
    ranked = []
    for player_id, hole_cards in player_cards.items():
        evaluation = evaluate_best(list(hole_cards) + list(board))
        ranked.append({"player_id": player_id, "evaluation": evaluation})
    ranked.sort(key=lambda item: tuple(item["evaluation"]["rank_tuple"]), reverse=True)
    place = 0
    previous = None
    for index, item in enumerate(ranked, start=1):
        current = tuple(item["evaluation"]["rank_tuple"])
        if current != previous:
            place = index
            previous = current
        item["place"] = place
    return ranked
