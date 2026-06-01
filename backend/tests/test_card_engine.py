import pytest

from card_engine import (
    RANKS,
    build_decks,
    build_standard_deck,
    deal_round_robin,
    recommended_deck_count,
    redact_hands,
    remove_cards,
    shuffle_cards,
)


def test_standard_deck_has_unique_ids_and_all_cards():
    deck = build_standard_deck()

    assert len(deck) == 52
    assert len({card["id"] for card in deck}) == 52
    assert {card["rank"] for card in deck} == set(RANKS)
    assert deck[0]["id"] == "0:clubs:A"


def test_multi_deck_ids_include_deck_index():
    deck = build_decks(2)

    assert len(deck) == 104
    assert len({card["id"] for card in deck}) == 104
    assert {"0:hearts:Q", "1:hearts:Q"}.issubset({card["id"] for card in deck})


def test_shuffle_is_deterministic_with_seed():
    deck = build_decks(1)

    first = shuffle_cards(deck, seed="room-1")
    second = shuffle_cards(deck, seed="room-1")
    third = shuffle_cards(deck, seed="room-2")

    assert [card["id"] for card in first] == [card["id"] for card in second]
    assert [card["id"] for card in first] != [card["id"] for card in third]


def test_deal_round_robin_distributes_all_cards():
    deck = build_standard_deck()
    hands = deal_round_robin(["a", "b", "c", "d"], deck)

    assert sum(len(hand) for hand in hands.values()) == 52
    assert [len(hands[player]) for player in ["a", "b", "c", "d"]] == [13, 13, 13, 13]


def test_remove_cards_preserves_requested_order_and_rejects_missing():
    hand = build_standard_deck()[:5]
    remaining, removed = remove_cards(hand, [hand[2]["id"], hand[0]["id"]])

    assert [card["id"] for card in removed] == [hand[2]["id"], hand[0]["id"]]
    assert len(remaining) == 3

    with pytest.raises(ValueError, match="Cards not in hand"):
        remove_cards(hand, ["missing"])


def test_redact_hands_only_reveals_viewer_hand():
    hands = deal_round_robin(["a", "b"], build_standard_deck()[:4])

    public = redact_hands(hands)
    private = redact_hands(hands, viewer_id="a")

    assert "cards" not in public["a"]
    assert "cards" in private["a"]
    assert "cards" not in private["b"]
    assert private["a"]["count"] == 2


def test_recommended_deck_count_scales_for_big_groups():
    assert recommended_deck_count(4) == 1
    assert recommended_deck_count(12) == 2
    assert recommended_deck_count(30) == 4
