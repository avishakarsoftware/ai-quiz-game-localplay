from card_engine import make_card
from poker_hand_evaluator import compare_hands, evaluate_best, rank_players


def c(rank: str, suit: str) -> dict:
    return make_card(rank, suit)


def test_evaluates_best_straight_flush_from_seven_cards():
    cards = [
        c("9", "hearts"),
        c("10", "hearts"),
        c("J", "hearts"),
        c("Q", "hearts"),
        c("K", "hearts"),
        c("2", "clubs"),
        c("A", "spades"),
    ]

    result = evaluate_best(cards)

    assert result["category"] == "straight_flush"
    assert result["tiebreakers"] == [13]


def test_evaluates_wheel_straight():
    cards = [
        c("A", "clubs"),
        c("2", "diamonds"),
        c("3", "spades"),
        c("4", "hearts"),
        c("5", "clubs"),
        c("K", "diamonds"),
        c("9", "spades"),
    ]

    result = evaluate_best(cards)

    assert result["category"] == "straight"
    assert result["tiebreakers"] == [5]


def test_full_house_beats_flush():
    full_house = [c("A", "clubs"), c("A", "diamonds"), c("A", "spades"), c("K", "clubs"), c("K", "hearts")]
    flush = [c("2", "hearts"), c("5", "hearts"), c("8", "hearts"), c("J", "hearts"), c("Q", "hearts")]

    assert compare_hands(full_house, flush) == 1


def test_rank_players_keeps_ties_on_same_place():
    board = [c("A", "clubs"), c("K", "diamonds"), c("Q", "spades"), c("J", "hearts"), c("2", "diamonds")]
    player_cards = {
        "alice": [c("10", "clubs"), c("3", "hearts")],
        "bob": [c("10", "spades"), c("3", "diamonds")],
        "cara": [c("9", "clubs"), c("4", "spades")],
    }

    ranked = rank_players(player_cards, board)

    assert [item["player_id"] for item in ranked[:2]] == ["alice", "bob"]
    assert ranked[0]["place"] == 1
    assert ranked[1]["place"] == 1
    assert ranked[2]["place"] == 3
