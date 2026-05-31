import pytest

from bingo_engine import (
    create_bingo_call_deck,
    default_bingo_game,
    generate_bingo_card,
    sanitize_bingo_deck,
    validate_bingo_claim,
)


def _deck(count=25):
    return [{"kind": "text", "display": f"Item {index}", "value": f"item {index}"} for index in range(count)]


def test_sanitize_bingo_deck_trims_and_dedupes():
    deck = sanitize_bingo_deck([*_deck(24), {"display": " Item 1 "}], free_center=True)
    assert len(deck) == 24
    assert deck[0]["display"] == "Item 0"


def test_sanitize_bingo_deck_rejects_too_few_items():
    with pytest.raises(ValueError):
        sanitize_bingo_deck(_deck(23), free_center=True)
    with pytest.raises(ValueError):
        sanitize_bingo_deck(_deck(24), free_center=False)


def test_sanitize_bingo_deck_accepts_app_controlled_image_items():
    raw = _deck(25)
    raw[0] = {
        "kind": "image",
        "display": "Cake",
        "value": "cake",
        "image_asset_id": "img_abc",
        "image_url": "/media/img_abc",
        "alt_text": "Cake",
    }
    deck = sanitize_bingo_deck(raw, free_center=True)
    assert deck[0]["kind"] == "image"
    assert deck[0]["image_url"] == "/media/img_abc"


def test_sanitize_bingo_deck_rejects_external_image_urls():
    raw = _deck(25)
    raw[0] = {"kind": "image", "display": "Bad", "value": "bad", "image_url": "https://example.com/bad.png"}
    deck = sanitize_bingo_deck(raw, free_center=True)
    assert all(item["kind"] != "image" for item in deck)


def test_generate_bingo_card_has_free_center_and_unique_cells():
    game = default_bingo_game()
    card = generate_bingo_card("c1", "p1", "Avi", game["deck"], seed=42)
    assert card["layout"] == "bingo_5x5_free"
    assert len(card["rows"]) == 5
    assert all(len(row) == 5 for row in card["rows"])
    assert card["rows"][2][2]["kind"] == "free"
    values = [cell["value"] for row in card["rows"] for cell in row if cell["kind"] != "free"]
    assert len(values) == 24
    assert len(set(values)) == 24


def test_bingo_claims_first_line_corners_and_blackout():
    deck = sanitize_bingo_deck(_deck(25), free_center=True)
    card = generate_bingo_card("c1", "p1", "Avi", deck, seed=1)
    top_line = [cell for cell in card["rows"][0]]
    called_top = [{"id": cell["id"], "value": cell["value"], "display": cell["display"]} for cell in top_line]
    assert validate_bingo_claim(card, called_top, "first_line")[0] is True

    corners = [card["rows"][0][0], card["rows"][0][4], card["rows"][4][0], card["rows"][4][4]]
    called_corners = [{"id": cell["id"], "value": cell["value"], "display": cell["display"]} for cell in corners]
    assert validate_bingo_claim(card, called_corners, "four_corners")[0] is True

    all_cells = [cell for row in card["rows"] for cell in row if cell["kind"] != "free"]
    called_all = [{"id": cell["id"], "value": cell["value"], "display": cell["display"]} for cell in all_cells]
    assert validate_bingo_claim(card, called_all, "blackout")[0] is True


def test_bingo_strict_claim_rejects_stale_claim():
    deck = sanitize_bingo_deck(_deck(25), free_center=True)
    card = generate_bingo_card("c1", "p1", "Avi", deck, seed=1)
    top_line = [cell for cell in card["rows"][0]]
    unrelated = card["rows"][1][0]
    called = [{"id": cell["id"], "value": cell["value"], "display": cell["display"]} for cell in [*top_line, unrelated]]
    accepted, reason, _ = validate_bingo_claim(card, called, "first_line", require_latest=True)
    assert accepted is False
    assert reason == "latest_item_not_in_pattern"


def test_bingo_call_deck_shuffles_items_once_each():
    deck = sanitize_bingo_deck(_deck(25), free_center=True)
    called = create_bingo_call_deck(deck, seed=4)
    assert sorted(item["value"] for item in called) == sorted(item["value"] for item in deck)
