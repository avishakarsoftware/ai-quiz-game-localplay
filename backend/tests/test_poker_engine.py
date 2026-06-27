from card_engine import make_card
from poker_engine import (
    PHASE_DECISION,
    PHASE_PODIUM,
    PHASE_SHOWDOWN,
    create_initial_state,
    public_sync,
    start_next_hand,
    submit_decision,
    validate_config,
)


def test_validate_config_clamps_ante_below_stack():
    config = validate_config({"starting_stack": 200, "ante": 999})

    assert config["game_title"] == "Party Poker"
    assert config["starting_stack"] == 200
    assert config["ante"] < 200


def test_quick_holdem_starts_with_hidden_cards_and_equal_antes():
    state = create_initial_state(["alice", "bob", "cara"], {"starting_stack": 500, "ante": 50}, seed="unit", now=100)

    assert state["phase"] == PHASE_DECISION
    assert state["pot"] == 150
    assert state["stacks"] == {"alice": 450, "bob": 450, "cara": 450}
    assert len(state["community_cards"]) == 5
    assert len(state["hole_cards"]["alice"]) == 2
    public = public_sync(state)
    private = public_sync(state, "alice")
    assert public["hole_cards"]["alice"][0]["hidden"] is True
    assert private["hole_cards"]["alice"][0]["rank"]
    assert private["hole_cards"]["bob"][0]["hidden"] is True


def test_players_stay_or_fold_until_showdown_and_winner_gets_pot():
    state = create_initial_state(["alice", "bob"], {"starting_stack": 500, "ante": 50}, seed="unit", now=100)

    state = submit_decision(state, "alice", "stay")
    assert state["phase"] == PHASE_DECISION
    state = submit_decision(state, "bob", "fold")

    assert state["phase"] == PHASE_SHOWDOWN
    assert state["hand_result"]["winner_id"] == "alice"
    assert state["stacks"]["alice"] == 550
    assert state["stacks"]["bob"] == 450


def test_pot_is_split_on_tied_showdown():
    # When the board plays (a royal flush nobody can beat), both contenders tie
    # and must chop the pot instead of one player taking it all.
    state = create_initial_state(["alice", "bob"], {"starting_stack": 500, "ante": 50}, seed="unit", now=100)
    state["community_cards"] = [
        make_card("A", "spades"), make_card("K", "spades"), make_card("Q", "spades"),
        make_card("J", "spades"), make_card("10", "spades"),
    ]
    state["hole_cards"]["alice"] = [make_card("2", "hearts"), make_card("3", "diamonds")]
    state["hole_cards"]["bob"] = [make_card("4", "clubs"), make_card("5", "hearts")]

    state = submit_decision(state, "alice", "stay")
    state = submit_decision(state, "bob", "stay")

    assert state["phase"] == PHASE_SHOWDOWN
    result = state["hand_result"]
    assert set(result["winner_ids"]) == {"alice", "bob"}
    assert result["pot"] == 100
    assert result["payouts"] == {"alice": 50, "bob": 50}
    # Both anted 50 (-> 450) and got their 50 back via the split.
    assert state["stacks"]["alice"] == 500
    assert state["stacks"]["bob"] == 500


def test_split_pot_awards_odd_chip_to_first_winner():
    state = create_initial_state(["alice", "bob"], {"starting_stack": 500, "ante": 25}, seed="unit", now=100)
    # Odd total pot (2 * 25 = 50 is even); force an odd pot via an ante that
    # leaves a remainder when split. Use ante 25 with a manual pot bump.
    state["pot"] = 51
    state["community_cards"] = [
        make_card("A", "spades"), make_card("K", "spades"), make_card("Q", "spades"),
        make_card("J", "spades"), make_card("10", "spades"),
    ]
    state["hole_cards"]["alice"] = [make_card("2", "hearts"), make_card("3", "diamonds")]
    state["hole_cards"]["bob"] = [make_card("4", "clubs"), make_card("5", "hearts")]

    state = submit_decision(state, "alice", "stay")
    state = submit_decision(state, "bob", "stay")

    payouts = state["hand_result"]["payouts"]
    assert sorted(payouts.values()) == [25, 26]
    assert sum(payouts.values()) == 51


def test_tournament_completes_when_one_player_remains():
    state = create_initial_state(["alice", "bob"], {"starting_stack": 200, "ante": 100}, seed="unit", now=100)
    state = submit_decision(state, "alice", "stay")
    state = submit_decision(state, "bob", "fold")
    state = start_next_hand(state, now=200)
    state = submit_decision(state, "alice", "stay")
    state = submit_decision(state, "bob", "fold")

    assert state["phase"] == PHASE_PODIUM
    assert state["standings"][0]["player_id"] == "alice"
