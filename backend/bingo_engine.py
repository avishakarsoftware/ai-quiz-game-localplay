"""Generic Bingo/Housie primitives.

The runtime uses these helpers for Housie v1, but the types are intentionally
plain dictionaries so future Bingo variants can use words, images, or emoji.
"""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Iterable, Literal, Optional


BingoItemKind = Literal["number", "text", "emoji", "image"]


@dataclass(frozen=True)
class BingoItem:
    kind: BingoItemKind
    value: str | int
    display: str
    sort_value: int

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "value": self.value,
            "display": self.display,
            "sort_value": self.sort_value,
        }


def numeric_deck(start: int = 1, end: int = 90) -> list[dict]:
    """Return a numeric Bingo deck as serializable items."""
    return [
        BingoItem(kind="number", value=n, display=str(n), sort_value=n).to_dict()
        for n in range(start, end + 1)
    ]


def shuffled_deck(items: Iterable[dict], seed: Optional[int] = None) -> list[dict]:
    deck = [dict(item) for item in items]
    rng = random.Random(seed)
    rng.shuffle(deck)
    return deck


def called_values(called_items: Iterable[dict]) -> set[str]:
    return {str(item.get("value")) for item in called_items if "value" in item}


def item_value(item: dict | None) -> str:
    if not isinstance(item, dict):
        return ""
    return str(item.get("value", ""))
