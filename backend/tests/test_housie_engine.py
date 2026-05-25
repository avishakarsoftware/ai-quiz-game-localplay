import pytest

from housie_engine import (
    HOUSIE_COLUMNS,
    HOUSIE_NUMBERS_PER_ROW,
    HOUSIE_NUMBERS_PER_TICKET,
    HOUSIE_ROWS,
    column_range,
    corner_numbers,
    create_call_deck,
    generate_ticket,
    ticket_numbers,
    validate_claim,
)


def test_column_ranges_are_classic_housie_deciles():
    assert column_range(0) == (1, 9)
    assert column_range(1) == (10, 19)
    assert column_range(7) == (70, 79)
    assert column_range(8) == (80, 90)
    with pytest.raises(ValueError):
        column_range(9)


def test_generate_ticket_has_3_by_9_layout_and_15_sorted_numbers():
    ticket = generate_ticket("t1", "p1", "Avi", seed=42)
    assert ticket["layout"] == "housie_3x9_15"
    assert len(ticket["rows"]) == HOUSIE_ROWS
    assert all(len(row) == HOUSIE_COLUMNS for row in ticket["rows"])
    numbers = ticket_numbers(ticket)
    assert len(numbers) == HOUSIE_NUMBERS_PER_TICKET
    assert len(set(numbers)) == HOUSIE_NUMBERS_PER_TICKET
    assert min(numbers) >= 1
    assert max(numbers) <= 90
    for row in ticket["rows"]:
        filled = [cell for cell in row if cell]
        assert len(filled) == HOUSIE_NUMBERS_PER_ROW
        assert [cell["value"] for cell in filled] == sorted(cell["value"] for cell in filled)


def test_ticket_columns_match_housie_ranges():
    ticket = generate_ticket("t1", "p1", "Avi", seed=99)
    for row in ticket["rows"]:
        for col, cell in enumerate(row):
            if not cell:
                continue
            low, high = column_range(col)
            assert low <= cell["value"] <= high


def test_claim_validation_quick_5_and_rows():
    ticket = generate_ticket("t1", "p1", "Avi", seed=7)
    numbers = ticket_numbers(ticket)
    called_4 = [{"kind": "number", "value": n, "display": str(n), "sort_value": n} for n in numbers[:4]]
    called_5 = [{"kind": "number", "value": n, "display": str(n), "sort_value": n} for n in numbers[:5]]
    assert validate_claim(ticket, called_4, "quick_5")[0] is False
    assert validate_claim(ticket, called_5, "quick_5")[0] is True

    top = [cell["value"] for cell in ticket["rows"][0] if cell]
    top_called = [{"kind": "number", "value": n, "display": str(n), "sort_value": n} for n in top]
    assert validate_claim(ticket, top_called, "top_row")[0] is True
    assert validate_claim(ticket, top_called[:-1], "top_row")[0] is False


def test_claim_validation_requires_latest_number_to_complete_pattern():
    ticket = generate_ticket("t1", "p1", "Avi", seed=7)
    numbers = ticket_numbers(ticket)
    called_6 = [{"kind": "number", "value": n, "display": str(n), "sort_value": n} for n in numbers[:6]]

    accepted, reason = validate_claim(ticket, called_6[:5], "quick_5")
    assert accepted is True
    assert reason == "accepted"

    accepted, reason = validate_claim(ticket, called_6, "quick_5")
    assert accepted is False
    assert reason == "stale_claim"

    top = [cell["value"] for cell in ticket["rows"][0] if cell]
    unrelated = next(number for number in numbers if number not in top)
    called = [{"kind": "number", "value": n, "display": str(n), "sort_value": n} for n in [*top, unrelated]]
    accepted, reason = validate_claim(ticket, called, "top_row")
    assert accepted is False
    assert reason == "latest_number_not_in_pattern"


def test_four_corners_use_outermost_filled_cells_not_grid_corners():
    ticket = generate_ticket("t1", "p1", "Avi", seed=123)
    corners = corner_numbers(ticket)
    assert len(corners) == 4
    called = [{"kind": "number", "value": n, "display": str(n), "sort_value": n} for n in corners]
    assert validate_claim(ticket, called, "four_corners")[0] is True


def test_call_deck_is_1_to_90_once_each():
    deck = create_call_deck(seed=11)
    values = sorted(item["value"] for item in deck)
    assert values == list(range(1, 91))
