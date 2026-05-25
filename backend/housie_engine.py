"""Classic 90-ball Housie ticket and claim engine."""

from __future__ import annotations

import random
from typing import Iterable, Optional

from bingo_engine import called_values, numeric_deck, shuffled_deck


HOUSIE_COLUMNS = 9
HOUSIE_ROWS = 3
HOUSIE_NUMBERS_PER_TICKET = 15
HOUSIE_NUMBERS_PER_ROW = 5

DEFAULT_HOUSIE_PATTERNS = [
    {"id": "quick_5", "label": "Quick 5", "description": "Any five numbers on your ticket"},
    {"id": "four_corners", "label": "Four Corners", "description": "The leftmost and rightmost filled cells in the top and bottom rows"},
    {"id": "top_row", "label": "Top Row", "description": "All numbers in the top row"},
    {"id": "middle_row", "label": "Middle Row", "description": "All numbers in the middle row"},
    {"id": "bottom_row", "label": "Bottom Row", "description": "All numbers in the bottom row"},
    {"id": "full_house", "label": "Full House", "description": "Every number on your ticket", "terminal": True},
]

PATTERN_ORDER = [pattern["id"] for pattern in DEFAULT_HOUSIE_PATTERNS]


def column_range(column: int) -> tuple[int, int]:
    """Return inclusive (low, high) for a Housie column.

    Classic Housie/Tambola buckets:
      Col 0: 1-9, Col 1: 10-19, Col 2: 20-29, ... Col 7: 70-79, Col 8: 80-90
    """
    if column < 0 or column >= HOUSIE_COLUMNS:
        raise ValueError("column must be 0-8")
    if column == 0:
        return 1, 9
    if column == HOUSIE_COLUMNS - 1:
        return 80, 90
    return column * 10, (column + 1) * 10 - 1


def sanitize_patterns(pattern_ids: Iterable[str] | None = None) -> list[str]:
    allowed = set(PATTERN_ORDER)
    selected = [pid for pid in (pattern_ids or PATTERN_ORDER) if pid in allowed]
    return selected or PATTERN_ORDER[:]


def _choose_column_counts(rng: random.Random) -> list[int]:
    """Choose 15 cells across 9 columns with 1-3 numbers in each column."""
    counts = [1] * HOUSIE_COLUMNS
    remaining = HOUSIE_NUMBERS_PER_TICKET - HOUSIE_COLUMNS
    columns = list(range(HOUSIE_COLUMNS))
    while remaining:
        col = rng.choice(columns)
        if counts[col] < HOUSIE_ROWS:
            counts[col] += 1
            remaining -= 1
        if counts[col] >= HOUSIE_ROWS and col in columns:
            columns.remove(col)
    return counts


def _fits_row_counts(assignments: list[list[int]]) -> bool:
    row_counts = [0, 0, 0]
    for rows in assignments:
        for row in rows:
            row_counts[row] += 1
    return row_counts == [HOUSIE_NUMBERS_PER_ROW] * HOUSIE_ROWS


def _choose_row_assignments(column_counts: list[int], rng: random.Random) -> list[list[int]]:
    row_options = {
        1: [[0], [1], [2]],
        2: [[0, 1], [0, 2], [1, 2]],
        3: [[0, 1, 2]],
    }
    for _ in range(400):
        assignments = [rng.choice(row_options[count])[:] for count in column_counts]
        if _fits_row_counts(assignments):
            return assignments
    # Deterministic fallback: greedily place cells in rows with remaining room.
    remaining = [HOUSIE_NUMBERS_PER_ROW] * HOUSIE_ROWS
    assignments = []
    for count in column_counts:
        rows = sorted(range(HOUSIE_ROWS), key=lambda row: remaining[row], reverse=True)[:count]
        for row in rows:
            remaining[row] -= 1
        assignments.append(sorted(rows))
    if not _fits_row_counts(assignments):
        raise RuntimeError("could not generate a valid Housie ticket layout")
    return assignments


def generate_ticket(ticket_id: str, player_id: str, player_name: str, seed: Optional[int] = None) -> dict:
    """Generate a classic 3x9 Housie ticket with 15 numbers."""
    rng = random.Random(seed)
    column_counts = _choose_column_counts(rng)
    row_assignments = _choose_row_assignments(column_counts, rng)
    grid: list[list[dict | None]] = [[None for _ in range(HOUSIE_COLUMNS)] for _ in range(HOUSIE_ROWS)]

    for col, count in enumerate(column_counts):
        low, high = column_range(col)
        numbers = sorted(rng.sample(range(low, high + 1), count))
        rows = row_assignments[col]
        for row, number in zip(rows, numbers):
            grid[row][col] = {
                "kind": "number",
                "value": number,
                "display": str(number),
                "sort_value": number,
                "row": row,
                "col": col,
            }

    return {
        "id": ticket_id,
        "player_id": player_id,
        "player_name": player_name,
        "layout": "housie_3x9_15",
        "rows": grid,
    }


def ticket_numbers(ticket: dict) -> list[int]:
    numbers: list[int] = []
    for row in ticket.get("rows", []):
        for cell in row:
            if isinstance(cell, dict) and cell.get("kind") == "number":
                numbers.append(int(cell["value"]))
    return sorted(numbers)


def ticket_called_count(ticket: dict, called_items: Iterable[dict]) -> int:
    called = called_values(called_items)
    return sum(1 for number in ticket_numbers(ticket) if str(number) in called)


def row_numbers(ticket: dict, row_index: int) -> list[int]:
    row = ticket.get("rows", [])[row_index]
    return [int(cell["value"]) for cell in row if isinstance(cell, dict)]


def corner_numbers(ticket: dict) -> list[int]:
    corners: list[int] = []
    rows = ticket.get("rows", [])
    for row_index in (0, HOUSIE_ROWS - 1):
        filled = [cell for cell in rows[row_index] if isinstance(cell, dict)]
        if not filled:
            continue
        corners.append(int(filled[0]["value"]))
        if filled[-1]["value"] != filled[0]["value"]:
            corners.append(int(filled[-1]["value"]))
    return corners


def validate_claim(
    ticket: dict,
    called_items: Iterable[dict],
    pattern_id: str,
    *,
    require_latest: bool = True,
) -> tuple[bool, str]:
    called_list = list(called_items)
    called = called_values(called_list)
    latest_item = called_list[-1] if called_list else None
    latest_value = str(latest_item.get("value")) if isinstance(latest_item, dict) and "value" in latest_item else ""
    called_before_latest = called_values(called_list[:-1])

    def all_called(numbers: Iterable[int], values: set[str]) -> bool:
        return all(str(number) in values for number in numbers)

    def latest_contributed(numbers: Iterable[int]) -> bool:
        return bool(latest_value) and latest_value in {str(number) for number in numbers}

    def apply_latest_rule(numbers: Iterable[int], was_complete_before: bool, is_complete_now: bool) -> tuple[bool, str]:
        number_list = list(numbers)
        if not is_complete_now:
            return False, "not_complete"
        if not require_latest:
            return True, "accepted"
        if not latest_value:
            return False, "no_calls_yet"
        if not latest_contributed(number_list):
            return False, "latest_number_not_in_pattern"
        if was_complete_before:
            return False, "stale_claim"
        return True, "accepted"

    if pattern_id == "quick_5":
        numbers = ticket_numbers(ticket)
        count = sum(1 for number in numbers if str(number) in called)
        before_count = sum(1 for number in numbers if str(number) in called_before_latest)
        return apply_latest_rule(numbers, before_count >= 5, count >= 5)
    if pattern_id == "four_corners":
        numbers = corner_numbers(ticket)
        return apply_latest_rule(
            numbers,
            len(numbers) == 4 and all_called(numbers, called_before_latest),
            len(numbers) == 4 and all_called(numbers, called),
        )
    if pattern_id == "top_row":
        numbers = row_numbers(ticket, 0)
        return apply_latest_rule(
            numbers,
            len(numbers) == HOUSIE_NUMBERS_PER_ROW and all_called(numbers, called_before_latest),
            len(numbers) == HOUSIE_NUMBERS_PER_ROW and all_called(numbers, called),
        )
    if pattern_id == "middle_row":
        numbers = row_numbers(ticket, 1)
        return apply_latest_rule(
            numbers,
            len(numbers) == HOUSIE_NUMBERS_PER_ROW and all_called(numbers, called_before_latest),
            len(numbers) == HOUSIE_NUMBERS_PER_ROW and all_called(numbers, called),
        )
    if pattern_id == "bottom_row":
        numbers = row_numbers(ticket, 2)
        return apply_latest_rule(
            numbers,
            len(numbers) == HOUSIE_NUMBERS_PER_ROW and all_called(numbers, called_before_latest),
            len(numbers) == HOUSIE_NUMBERS_PER_ROW and all_called(numbers, called),
        )
    if pattern_id == "full_house":
        numbers = ticket_numbers(ticket)
        return apply_latest_rule(
            numbers,
            len(numbers) == HOUSIE_NUMBERS_PER_TICKET and all_called(numbers, called_before_latest),
            len(numbers) == HOUSIE_NUMBERS_PER_TICKET and all_called(numbers, called),
        )
    return False, "unknown_pattern"


def create_call_deck(seed: Optional[int] = None) -> list[dict]:
    return shuffled_deck(numeric_deck(1, 90), seed=seed)


def default_housie_game(title: str = "Housie") -> dict:
    return {
        "game_title": title or "Housie",
        "layout": "housie_3x9_15",
        "deck": numeric_deck(1, 90),
        "patterns": DEFAULT_HOUSIE_PATTERNS[:],
        "play_mode": "beginner",
        "caller_mode": "manual",
        "auto_interval_seconds": 8,
        "auto_pause_on_claim": True,
    }
