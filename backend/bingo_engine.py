"""Generic Bingo/Housie primitives.

The runtime uses these helpers for Housie v1, but the types are intentionally
plain dictionaries so future Bingo variants can use words, images, or emoji.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import random
from typing import Iterable, Literal, Optional


BingoItemKind = Literal["number", "text", "emoji", "image"]
BINGO_SIZE = 5
BINGO_MAX_DECK_ITEMS = 120
BINGO_MAX_DISPLAY_LENGTH = 40
BINGO_APP_MEDIA_RE = re.compile(r"^https://media\.revelryapp\.me/apps/localplay/", re.IGNORECASE)

DEFAULT_BINGO_PATTERNS = [
    {"id": "first_line", "label": "First Line", "description": "Any complete row, column, or diagonal"},
    {"id": "four_corners", "label": "Four Corners", "description": "All four corner cells"},
    {"id": "blackout", "label": "Blackout", "description": "Every non-free cell", "terminal": True},
]

BINGO_PATTERN_ORDER = [pattern["id"] for pattern in DEFAULT_BINGO_PATTERNS]


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


def _sanitize_display(value: object, max_length: int = BINGO_MAX_DISPLAY_LENGTH) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(value or "")).strip()
    text = re.sub(r"\s+", " ", text)
    return text[:max_length].strip()


def is_app_controlled_image_url(url: str) -> bool:
    return url.startswith("/media/") or url.startswith("/quiz/") or BINGO_APP_MEDIA_RE.match(url) is not None


def sanitize_bingo_deck(items: Iterable[dict] | None, *, free_center: bool = True) -> list[dict]:
    """Normalize a custom Bingo deck and enforce MVP size limits."""
    sanitized: list[dict] = []
    seen: set[str] = set()
    for index, raw in enumerate(items or []):
        if not isinstance(raw, dict):
            raw = {"display": raw}
        kind = str(raw.get("kind") or "text").strip().lower()
        if kind not in ("text", "emoji", "image"):
            kind = "text"
        display = _sanitize_display(raw.get("display") or raw.get("label") or raw.get("value"))
        if not display:
            continue
        value = _sanitize_display(raw.get("value") or display).lower()
        image_url = _sanitize_display(raw.get("image_url") or raw.get("public_url"), 1000)
        image_asset_id = _sanitize_display(raw.get("image_asset_id") or raw.get("asset_id"), 128)
        alt_text = _sanitize_display(raw.get("alt_text") or raw.get("image_alt") or display, 300)
        if kind == "image":
            if not image_asset_id and not image_url:
                continue
            if image_url and not is_app_controlled_image_url(image_url):
                continue
        key = f"{kind}:{image_asset_id or image_url or value}"
        if key in seen:
            continue
        seen.add(key)
        item = {
            "id": _sanitize_display(raw.get("id") or f"item_{len(sanitized) + 1}", 80) or f"item_{len(sanitized) + 1}",
            "kind": kind,
            "value": value,
            "display": display,
            "sort_value": index + 1,
        }
        if kind == "image":
            item["image_asset_id"] = image_asset_id
            item["image_url"] = image_url or f"/media/{image_asset_id}"
            item["alt_text"] = alt_text
        sanitized.append(item)
        if len(sanitized) >= BINGO_MAX_DECK_ITEMS:
            break

    minimum = 24 if free_center else 25
    if len(sanitized) < minimum:
        raise ValueError(f"Bingo deck needs at least {minimum} unique items")
    return sanitized


def sanitize_bingo_patterns(pattern_ids: Iterable[str] | None = None) -> list[dict]:
    requested = [str(pid).strip() for pid in (pattern_ids or BINGO_PATTERN_ORDER)]
    allowed = {pattern["id"]: pattern for pattern in DEFAULT_BINGO_PATTERNS}
    selected = [dict(allowed[pid]) for pid in requested if pid in allowed]
    return selected or [dict(pattern) for pattern in DEFAULT_BINGO_PATTERNS]


def generate_bingo_card(
    card_id: str,
    player_id: str,
    player_name: str,
    deck_items: Iterable[dict],
    *,
    free_center: bool = True,
    free_center_label: str = "FREE",
    seed: Optional[int] = None,
) -> dict:
    rng = random.Random(seed)
    needed = 24 if free_center else 25
    deck = [dict(item) for item in deck_items]
    if len(deck) < needed:
        raise ValueError(f"Bingo deck needs at least {needed} unique items")
    selected = rng.sample(deck, needed)
    rows: list[list[dict]] = []
    index = 0
    for row in range(BINGO_SIZE):
        cells: list[dict] = []
        for col in range(BINGO_SIZE):
            if free_center and row == 2 and col == 2:
                cells.append({
                    "kind": "free",
                    "value": "free",
                    "display": _sanitize_display(free_center_label, 16) or "FREE",
                    "row": row,
                    "col": col,
                })
                continue
            item = dict(selected[index])
            index += 1
            item["row"] = row
            item["col"] = col
            cells.append(item)
        rows.append(cells)
    return {
        "id": card_id,
        "player_id": player_id,
        "player_name": player_name,
        "layout": "bingo_5x5_free" if free_center else "bingo_5x5",
        "rows": rows,
    }


def create_bingo_call_deck(items: Iterable[dict], seed: Optional[int] = None) -> list[dict]:
    return shuffled_deck(items, seed=seed)


def _playable_cells(card: dict) -> list[dict]:
    cells: list[dict] = []
    for row in card.get("rows", []):
        for cell in row:
            if isinstance(cell, dict) and cell.get("kind") != "free":
                cells.append(cell)
    return cells


def _cell_called(cell: dict, called: set[str]) -> bool:
    return str(cell.get("value")) in called or str(cell.get("id")) in called


def _line_cells(card: dict) -> list[list[dict]]:
    rows = card.get("rows", [])
    lines: list[list[dict]] = []
    for row in rows:
        lines.append([cell for cell in row if isinstance(cell, dict) and cell.get("kind") != "free"])
    for col in range(BINGO_SIZE):
        lines.append([
            rows[row][col]
            for row in range(BINGO_SIZE)
            if row < len(rows) and col < len(rows[row]) and isinstance(rows[row][col], dict) and rows[row][col].get("kind") != "free"
        ])
    lines.append([
        rows[index][index]
        for index in range(BINGO_SIZE)
        if index < len(rows) and index < len(rows[index]) and isinstance(rows[index][index], dict) and rows[index][index].get("kind") != "free"
    ])
    lines.append([
        rows[index][BINGO_SIZE - 1 - index]
        for index in range(BINGO_SIZE)
        if index < len(rows) and BINGO_SIZE - 1 - index < len(rows[index]) and isinstance(rows[index][BINGO_SIZE - 1 - index], dict) and rows[index][BINGO_SIZE - 1 - index].get("kind") != "free"
    ])
    return lines


def _winning_cells(card: dict, pattern_id: str, called: set[str]) -> list[dict]:
    if pattern_id == "first_line":
        for line in _line_cells(card):
            if line and all(_cell_called(cell, called) for cell in line):
                return line
        return []
    if pattern_id == "four_corners":
        rows = card.get("rows", [])
        corners = []
        for row, col in ((0, 0), (0, 4), (4, 0), (4, 4)):
            try:
                cell = rows[row][col]
            except (IndexError, TypeError):
                return []
            if not isinstance(cell, dict) or cell.get("kind") == "free":
                return []
            corners.append(cell)
        return corners if all(_cell_called(cell, called) for cell in corners) else []
    if pattern_id == "blackout":
        cells = _playable_cells(card)
        return cells if cells and all(_cell_called(cell, called) for cell in cells) else []
    return []


def validate_bingo_claim(
    card: dict,
    called_items: Iterable[dict],
    pattern_id: str,
    *,
    require_latest: bool = False,
) -> tuple[bool, str, list[str]]:
    called_list = list(called_items)
    called = called_values(called_list) | {str(item.get("id")) for item in called_list if isinstance(item, dict) and item.get("id")}
    winning = _winning_cells(card, pattern_id, called)
    if not winning:
        return False, "not_complete", []
    winning_values = [str(cell.get("value")) for cell in winning]
    if not require_latest:
        return True, "accepted", winning_values
    latest = called_list[-1] if called_list else None
    latest_keys = {str(latest.get("value")), str(latest.get("id"))} if isinstance(latest, dict) else set()
    if not latest_keys.intersection({str(cell.get("value")) for cell in winning} | {str(cell.get("id")) for cell in winning}):
        return False, "latest_item_not_in_pattern", []
    called_before = called_values(called_list[:-1]) | {str(item.get("id")) for item in called_list[:-1] if isinstance(item, dict) and item.get("id")}
    if _winning_cells(card, pattern_id, called_before):
        return False, "stale_claim", []
    return True, "accepted", winning_values


def default_bingo_game(title: str = "Bingo") -> dict:
    starter = [
        "Dance floor", "Group photo", "Someone laughs", "Snack table", "Party playlist",
        "Inside joke", "A toast", "Late arrival", "New friend", "Dessert",
        "Someone sings", "Sparkly outfit", "Favorite song", "Big hug", "Phone photo",
        "Someone cheers", "Cake", "Gift bag", "Funny story", "Matching colors",
        "Table games", "A surprise", "Best dressed", "Last call", "Confetti",
    ]
    deck = sanitize_bingo_deck([{"kind": "text", "display": item} for item in starter], free_center=True)
    return {
        "game_title": title or "Bingo",
        "ruleset": "custom",
        "layout": "bingo_5x5_free",
        "free_center": True,
        "free_center_label": "FREE",
        "deck": deck,
        "patterns": [dict(pattern) for pattern in DEFAULT_BINGO_PATTERNS],
        "caller_mode": "manual",
        "claim_requires_latest_call": False,
    }
