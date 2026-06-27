import pytest

from bluff_engine import (
    PHASE_CHALLENGE,
    PHASE_PODIUM,
    PHASE_REVEAL,
    PHASE_TURN,
    challenge_claim,
    continue_after_reveal,
    create_initial_state,
    pass_turn,
    play_cards,
    private_sync,
    public_sync,
    resolve_unchallenged,
    validate_config,
)


def test_validate_config_defaults_to_recommended_deck_count():
    config = validate_config({"game_title": "  Family Bluff  ", "deck_count": "bad"}, player_count=12)

    assert config["game_title"] == "Family Bluff"
    assert config["deck_count"] == 2
    assert config["challenge_window_seconds"] == 12


def test_create_initial_state_deals_and_redacts_public_sync():
    state = create_initial_state(["avi", "ruchi", "nia"], seed="bluff")
    sync = public_sync(state)

    assert state["phase"] == PHASE_TURN
    assert state["active_player_id"] == "avi"
    assert sum(len(hand) for hand in state["hands"].values()) == 52
    assert sync["pile_count"] == 0
    assert "rank_counts_in_pile" not in sync
    assert "cards" not in sync["hands"]["avi"]

    private = private_sync(state, "avi")
    assert "cards" in private["hands"]["avi"]
    assert "cards" not in private["hands"]["ruchi"]


def test_create_initial_state_rejects_duplicate_or_too_few_players():
    with pytest.raises(ValueError, match="at least 3"):
        create_initial_state(["a", "b"])

    with pytest.raises(ValueError, match="unique"):
        create_initial_state(["a", "a", "b"])


def test_active_player_can_play_and_non_active_cannot():
    state = create_initial_state(["avi", "ruchi", "nia"], seed="bluff")
    card = state["hands"]["avi"][0]

    with pytest.raises(ValueError, match="Only the active player"):
        play_cards(state, "ruchi", [card["id"]])

    next_state = play_cards(state, "avi", [card["id"]], now=10)

    assert next_state["phase"] == PHASE_CHALLENGE
    assert next_state["last_claim"]["actor_id"] == "avi"
    assert next_state["last_claim"]["claimed_rank"] == "A"
    assert next_state["challenge_deadline"] == 22
    assert len(next_state["pile"]) == 1
    assert card["id"] not in {c["id"] for c in next_state["hands"]["avi"]}


def test_public_sync_hides_played_card_ids_during_challenge():
    # Card ids encode rank/suit, so exposing the played card ids during the
    # challenge window would reveal whether a claim is a bluff to everyone.
    state = create_initial_state(["avi", "ruchi", "nia"], seed="bluff")
    card = state["hands"]["avi"][0]
    state = play_cards(state, "avi", [card["id"]], now=10)

    assert state["phase"] == PHASE_CHALLENGE
    # Internal state still carries the real card ids for resolution.
    assert state["last_claim"]["card_ids"] == [card["id"]]

    sync = public_sync(state)
    assert "card_ids" not in sync["last_claim"]
    # But the public-facing claim metadata is preserved.
    assert sync["last_claim"]["actor_id"] == "avi"
    assert sync["last_claim"]["claimed_rank"] == "A"
    assert sync["last_claim"]["claimed_count"] == 1

    # Other players' private views must not leak the card ids either.
    assert "card_ids" not in private_sync(state, "ruchi")["last_claim"]
    assert "card_ids" not in private_sync(state, "avi")["last_claim"]


def test_pass_turn_advances_to_next_player_when_enabled():
    state = create_initial_state(["avi", "ruchi", "nia"], seed="bluff")

    next_state = pass_turn(state, "avi")

    assert next_state["phase"] == PHASE_TURN
    assert next_state["active_player_id"] == "ruchi"
    assert next_state["required_rank"] == "A"


def test_pass_turn_rejects_when_disabled():
    state = create_initial_state(["avi", "ruchi", "nia"], config={"allow_pass": False}, seed="bluff")

    with pytest.raises(ValueError, match="disabled"):
        pass_turn(state, "avi")


def test_unchallenged_claim_advances_rank_and_turn():
    state = create_initial_state(["avi", "ruchi", "nia"], seed="bluff")
    claim_state = play_cards(state, "avi", [state["hands"]["avi"][0]["id"]], now=5)

    next_state = resolve_unchallenged(claim_state)

    assert next_state["phase"] == PHASE_TURN
    assert next_state["required_rank"] == "2"
    assert next_state["active_player_id"] == "ruchi"
    assert next_state["pile"]
    assert next_state["last_claim"] is None


def test_truthful_challenge_makes_challenger_pick_up_pile():
    state = create_initial_state(["avi", "ruchi", "nia"], seed="bluff")
    ace = next(card for card in state["hands"]["avi"] if card["rank"] == "A")
    claim_state = play_cards(state, "avi", [ace["id"]], now=5)

    reveal_state = challenge_claim(claim_state, "ruchi")

    assert reveal_state["phase"] == PHASE_REVEAL
    assert reveal_state["last_claim"]["truthful"] is True
    assert reveal_state["last_claim"]["loser_id"] == "ruchi"
    assert len(reveal_state["pile"]) == 0
    assert ace["id"] in {card["id"] for card in reveal_state["hands"]["ruchi"]}


def test_false_challenge_makes_actor_pick_up_pile():
    state = create_initial_state(["avi", "ruchi", "nia"], seed="bluff")
    non_ace = next(card for card in state["hands"]["avi"] if card["rank"] != "A")
    claim_state = play_cards(state, "avi", [non_ace["id"]], now=5)

    reveal_state = challenge_claim(claim_state, "ruchi")

    assert reveal_state["last_claim"]["truthful"] is False
    assert reveal_state["last_claim"]["loser_id"] == "avi"
    assert non_ace["id"] in {card["id"] for card in reveal_state["hands"]["avi"]}


def test_actor_cannot_challenge_own_claim():
    state = create_initial_state(["avi", "ruchi", "nia"], seed="bluff")
    claim_state = play_cards(state, "avi", [state["hands"]["avi"][0]["id"]], now=5)

    with pytest.raises(ValueError, match="own claim"):
        challenge_claim(claim_state, "avi")


def test_truthful_challenge_can_record_winner_after_reveal():
    state = create_initial_state(["avi", "ruchi", "nia"], seed="bluff")
    state["hands"]["avi"] = [{"id": "0:clubs:A", "deck_index": 0, "suit": "clubs", "rank": "A", "label": "A of clubs"}]
    claim_state = play_cards(state, "avi", ["0:clubs:A"], now=5)
    reveal_state = challenge_claim(claim_state, "ruchi")

    next_state = continue_after_reveal(reveal_state)

    assert next_state["winners"][0] == {"player_id": "avi", "place": 1}
    assert next_state["phase"] == PHASE_TURN
    assert next_state["active_player_id"] in {"ruchi", "nia"}


def test_unchallenged_last_remaining_player_completes_podium():
    state = create_initial_state(["avi", "ruchi", "nia"], seed="bluff")
    state["winners"] = [{"player_id": "ruchi", "place": 1}]
    state["turn_index"] = 0
    state["active_player_id"] = "avi"
    state["hands"]["avi"] = [{"id": "0:clubs:A", "deck_index": 0, "suit": "clubs", "rank": "A", "label": "A of clubs"}]
    claim_state = play_cards(state, "avi", ["0:clubs:A"], now=5)

    next_state = resolve_unchallenged(claim_state)

    assert next_state["phase"] == PHASE_PODIUM
    assert next_state["winners"] == [
        {"player_id": "ruchi", "place": 1},
        {"player_id": "avi", "place": 2},
        {"player_id": "nia", "place": 3},
    ]
