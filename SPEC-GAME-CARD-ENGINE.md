# LocalPlay Card Game Engine Spec

## Overview

Add a reusable card-game engine to LocalPlay for large-room, host-led party card games.

The first target game is **Bluff** (also known as Cheat or I Doubt It), because it works well with bigger groups, supports multiple decks, has simple rules, and creates strong social moments without requiring every player to know a complicated trick-taking system.

```text
Runtime family: cards
First game type: bluff
Backend engine: card_engine.py / bluff_engine.py
Frontend display name: Bluff
```

This spec is implementation-ready, but it is not yet implemented. It should be built as a pure engine first, then wired into room creation and WebSocket runtime after tests cover the rules.

## Goals

- Create shared card primitives for future card games.
- Support big groups by allowing multiple standard decks in one room.
- Make Bluff the first concrete game on top of the engine.
- Keep all hidden information authoritative on the server.
- Support organizer, player, and spectator surfaces.
- Keep the protocol explicit enough to support reconnects, host-app embedding, and future Cloud Run/state externalization.
- Avoid real-money gambling mechanics and casino framing.

## Non-Goals

- No betting, wagering, chips, or casino UX.
- No computer opponents in v1.
- No trick-taking engine in the first slice.
- No random matchmaking.
- No persistent ranked ladder.
- No physical card scanning.
- No Revelry launch until standalone cards are tested.

## Recommended Game Roadmap

Best first games for big groups:

- **Bluff**: 4-12+ players, multiple decks, high social energy, simple hidden-card rules.
- **Spoons**: 4-10 players, phone can manage rounds and elimination, but the physical spoon grab makes it less fully digital.
- **Donkey / Old Maid variants**: 4-12 players, simple passing mechanics, good casual party fit.
- **President / Scum**: 5-10 players, popular social hierarchy, but rule variations need careful setup options.
- **Party Poker**: 2-10 players per table with fixed play chips, strong spectator appeal, but should come after Bluff because betting rounds, side pots, and hand evaluation add complexity.
- **Memory Match Relay**: team-friendly, scalable, uses card primitives without poker/trick-taking complexity.

Good later or smaller-table games:

- **Black Queen / Hearts**: excellent card game, but usually best at 4 players and less ideal for a big-room launch.
- **Rummy**: familiar, but slower and more rules-heavy.
- **Judgment / Oh Hell**: fun, but best at smaller tables and needs bidding/trick-taking support.
- **Spades / Court Piece / Rang**: strong team games, but usually fixed around 4 players.

## Engine Architecture

Split the implementation into shared primitives and game-specific rules:

```text
backend/card_engine.py
backend/bluff_engine.py
backend/tests/test_card_engine.py
backend/tests/test_bluff_engine.py
```

`card_engine.py` owns reusable deck operations:

- Card identifiers.
- Standard deck generation.
- Multi-deck generation.
- Deterministic shuffling for tests.
- Round-robin dealing.
- Hand serialization.
- Hidden-hand redaction.
- Basic move validation helpers.

`bluff_engine.py` owns Bluff-specific state and rules:

- Setup validation.
- Turn order.
- Required rank progression.
- Card-play submission.
- Claim/challenge resolution.
- Penalty pickup.
- Player elimination/win detection.
- Public sync payloads.

## Host Controller vs Player Seat

Card games need the host to be able to play without giving the host unfair access to hidden state. Treat the host role as a **room controller**, not automatically as a player.

Concepts:

- `organizer`: setup/control identity. Can create the room, start the game, pause/skip/end when allowed, and open spectator/TV.
- `player`: seated game participant with a private hand.
- `spectator`: watch-only participant with redacted public state.
- `system dealer`: server-owned authority that shuffles, deals, advances turns, resolves timers, and validates moves.

Rules:

- The organizer may also join as a player, but only through a normal player session/device/tab.
- The organizer's player session receives only that player's private hand, exactly like every other player.
- The organizer control session never receives hidden cards or deck order.
- The server is the dealer. There is no human dealer who can see the deck or all hands.
- Spectator/TV surfaces use public sync only.
- If the host is playing, they should ideally keep organizer controls on a TV/laptop and their player hand on their phone.

Implementation shape:

```json
{
  "room_code": "ABCD12",
  "organizer_token": "control-token",
  "system_dealer_id": "system",
  "seats": {
    "player-device-id": {"player_id": "p1", "nickname": "Avi", "role": "player"}
  }
}
```

This model avoids a special "host hand" path and keeps all private information scoped to player connections.

## Shared Card Model

Use text ranks and suits instead of Unicode card symbols in backend state.

```py
RANKS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
SUITS = ("clubs", "diamonds", "hearts", "spades")
```

Card payload:

```json
{
  "id": "0:hearts:Q",
  "deck_index": 0,
  "suit": "hearts",
  "rank": "Q",
  "label": "Q of hearts"
}
```

Rules:

- `id` must be stable and unique inside a room, including across multiple decks.
- `deck_index` differentiates duplicates when two or more decks are used.
- Player clients receive their own hand with full card payloads.
- Other players' hands are redacted to counts only.
- Spectator/TV never sees hidden hands unless a game-specific reveal requires it.

## Shared Engine API

Pure functions should be small and deterministic:

```py
def build_standard_deck(deck_index: int = 0) -> list[dict]: ...

def build_decks(deck_count: int) -> list[dict]: ...

def shuffle_cards(cards: list[dict], seed: str | int | None = None) -> list[dict]: ...

def deal_round_robin(
    player_ids: list[str],
    cards: list[dict],
    cards_per_player: int | None = None,
    deal_all: bool = True,
) -> dict[str, list[dict]]: ...

def remove_cards(hand: list[dict], card_ids: list[str]) -> tuple[list[dict], list[dict]]: ...

def count_by_rank(cards: list[dict]) -> dict[str, int]: ...

def redact_hands(hands: dict[str, list[dict]], viewer_id: str | None) -> dict: ...

def recommended_deck_count(player_count: int, target_cards_per_player: int = 8) -> int: ...
```

`recommended_deck_count` should keep starting hands playable:

```text
deck_count = ceil((player_count * target_cards_per_player) / 52)
```

Clamp to at least 1 deck and at most 4 decks for v1.

## Bluff Game Rules

Bluff is a shedding game. Players try to get rid of all cards by playing face-down cards and claiming they match the required rank. Other players may challenge the claim. If the claim was false, the actor picks up the pile. If the claim was true, the challenger picks up the pile.

### Setup

```json
{
  "game_type": "bluff",
  "game_title": "Bluff",
  "deck_count": 2,
  "rank_order": "ascending",
  "allow_pass": true,
  "challenge_window_seconds": 12,
  "turn_time_seconds": 30,
  "target_cards_per_player": 8
}
```

Defaults:

- `deck_count`: recommended from player count.
- `rank_order`: `ascending`, starting at `A`.
- `allow_pass`: true.
- `challenge_window_seconds`: 12.
- `turn_time_seconds`: 30.
- Minimum players: 3.
- Recommended players: 4-12.
- Hard max v1: 20 players with 4 decks.

### Round Flow

1. Host creates a Bluff room.
2. Players join the lobby.
3. Host starts the game.
4. Server builds and shuffles one or more decks.
5. Server deals cards round-robin.
6. Server picks a starting player.
7. The required rank starts at `A`.
8. The active player either plays one or more cards face-down with a claim or passes if enabled.
9. Other players get a challenge window.
10. If nobody challenges, cards stay in the face-down pile and turn advances to the next rank.
11. If a player challenges, the played cards are revealed.
12. If every played card matches the claimed rank, the challenger takes the full pile.
13. If any played card does not match the claimed rank, the actor takes the full pile.
14. A player with zero cards after a claim is provisional until the challenge window closes.
15. First player to empty their hand after the challenge window wins.
16. Continue for podium positions or end immediately after first winner in MVP.

### Rank Progression

Default rank sequence:

```text
A, 2, 3, 4, 5, 6, 7, 8, 9, 10, J, Q, K, A...
```

Rules:

- The server owns the required rank.
- The active player cannot choose a different rank in v1.
- Passing advances to the next player but not the next rank, unless future setup says otherwise.
- A successful unchallenged play advances the rank.
- A resolved challenge advances the rank after penalty pickup.

### Hidden Information

The server stores:

- All hands.
- Current pile.
- Last played card ids.
- Actor for the current claim.
- Claimed rank and claimed count.
- Challenge window deadline.

Public sync includes:

- Player hand counts.
- Current required rank.
- Current actor.
- Pile card count.
- Last claim summary.
- Challenge window remaining.
- Recent revealed cards only while resolving a challenge.

Private player sync includes:

- The player's own hand.
- Which card ids they have selected locally if the server stores selection state. Client-local selection is preferred.

## Bluff State Model

```json
{
  "phase": "BLUFF_TURN",
  "players": ["p1", "p2", "p3"],
  "active_player_id": "p1",
  "required_rank": "A",
  "hands": {
    "p1": [],
    "p2": [],
    "p3": []
  },
  "pile": [],
  "last_claim": null,
  "challenge_deadline": null,
  "rank_index": 0,
  "turn_index": 0,
  "winners": []
}
```

Phases:

- `BLUFF_LOBBY`: room exists, players joining.
- `BLUFF_TURN`: active player must play or pass.
- `BLUFF_CHALLENGE`: claim is waiting for challenge.
- `BLUFF_REVEAL`: challenge result is shown.
- `BLUFF_ROUND_END`: optional interstitial after a winner.
- `PODIUM`: final results.

## WebSocket Events

Client to server:

```json
{ "type": "BLUFF_PLAY_CARDS", "card_ids": ["0:hearts:Q"], "claimed_count": 1 }
{ "type": "BLUFF_PASS" }
{ "type": "BLUFF_CHALLENGE" }
{ "type": "BLUFF_CONTINUE" }
```

Server to client:

```json
{ "type": "BLUFF_SYNC", "state": {} }
{ "type": "BLUFF_CLAIM", "actor_id": "p1", "claimed_rank": "A", "claimed_count": 2 }
{ "type": "BLUFF_REVEAL", "truthful": false, "loser_id": "p1", "revealed_cards": [] }
{ "type": "BLUFF_WINNER", "player_id": "p3" }
```

Validation:

- Only the active player can play/pass.
- Only non-actor connected players can challenge.
- Played card ids must exist in the actor's hand.
- `claimed_count` must equal the number of submitted card ids.
- A player cannot challenge after the deadline.
- A player cannot play zero cards unless using `BLUFF_PASS`.

## Reconnects, Disconnects, and Leaving

- Reconnected players receive their current hand and the public room state.
- If the active player disconnects, keep their turn alive for `turn_time_seconds`.
- If they do not reconnect, auto-pass when passing is enabled.
- If passing is disabled, host may skip the player.
- Disconnected players remain in hand state until removed by host or room cleanup.
- Leaving during a challenge window does not cancel the claim.
- If a player with cards is removed, their cards go to the pile only if the host confirms; otherwise the game can continue with them marked inactive.

## Frontend UX

Organizer:

- Setup screen for title, deck count, challenge window, turn timer, and pass rule.
- Lobby uses normal room code/QR flow.
- Game control view shows current actor, required rank, pile count, and challenge state.
- Host can skip inactive players and end game.

Player:

- Hand view sorted by rank and suit.
- Large current-rank display.
- Card selection with clear selected count.
- Play button copy: `Play as {rank}`.
- Pass button when enabled.
- Challenge button during another player's challenge window.
- Reveal screen clearly shows whether the claim was true.

Spectator/TV:

- Big current rank.
- Turn order ring.
- Player hand counts.
- Pile size.
- Challenge countdown.
- Reveal animation after challenges.

## Testing Plan

Pure engine tests:

- Multi-deck card ids are unique.
- Shuffle is deterministic with seed.
- Round-robin deal preserves card counts.
- Hand redaction shows only viewer hand details.
- Recommended deck count scales with player count.

Bluff engine tests:

- Start game deals cards to every player.
- Active player can play valid cards.
- Non-active player cannot play.
- Actor cannot challenge their own claim.
- Truthful claim makes challenger pick up the pile.
- False claim makes actor pick up the pile.
- Winner is only declared after challenge window closes.
- Reconnect sync redacts other players' hands.
- Disconnect during turn auto-passes only when passing is enabled.

Frontend tests:

- Bluff setup screen renders and creates a room request.
- Player hand selection updates selected count.
- Challenge button appears only during `BLUFF_CHALLENGE` for eligible players.
- Spectator shows hand counts without hidden card details.

Playwright:

- Desktop/mobile setup layout has no overlapping controls.
- Player hand is usable on small phones.
- Challenge reveal fits long player names.
- Reconnect flow restores hand and phase.

## Acceptance Criteria

- `card_engine.py` exposes deterministic deck/deal/redaction helpers with tests.
- `bluff_engine.py` exposes pure state transition functions with tests.
- Starting a Bluff room with 3+ players deals cards and enters `BLUFF_TURN`.
- All hidden hands are redacted correctly in public/spectator sync.
- Challenge resolution is authoritative and deterministic.
- A player can win by emptying their hand after the challenge window.
- Existing quiz, WMLT, drawing, bingo/housie, and musical chairs flows still pass tests.

## Future Work

- Add President/Scum on top of shared card primitives.
- Add Spoons with physical-object and phone-tap variants.
- Add Donkey/Old Maid style passing games.
- Add team/table modes for very large parties.
- Add trick-taking primitives later for Black Queen/Hearts, Spades, Court Piece, and Judgment.
- Add host-app/Revelry catalog exposure after standalone Bluff is stable.
