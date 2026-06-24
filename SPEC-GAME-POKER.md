# LocalPlay Party Poker Tournament Spec

## Overview

Add **Party Poker** as a non-monetary, tournament-style card game built on the shared LocalPlay card engine.

This is poker as a social party game, not gambling. Players receive a fixed starting stack of play chips. There are no buy-ins, no cash value, no cash-out, no rewards, and no connection to sparks or LocalPlay/Revelry economics. Chips exist only as game state inside the room.

```text
Runtime family: cards
GameType: poker
First variant: texas_holdem_tournament
Backend engine: card_engine.py / poker_engine.py / poker_hand_evaluator.py
Frontend display name: Party Poker
```

## Implementation-Ready MVP Scope

Status: first playable standalone MVP implemented on June 24, 2026. The shared card engine dependency exists through the Bluff MVP, and `backend/poker_hand_evaluator.py` evaluates best 5-card Hold'em hands from 5-7 cards, handles wheel straights, tie-breaking, player ranking, and pure tests. `backend/poker_engine.py` now ships a quick no-money Hold'em tournament slice: equal play-chip stacks, fixed antes, two private hole cards, five table cards, Stay/Fold decisions, showdown, elimination, podium, private card redaction, room/socket events, organizer/player/spectator UI, and focused API/socket regression tests. Full betting rounds, blinds, raises, all-ins, side pots, and richer dealer controls remain Phase 2.

Revelry bridge status: LocalPlay now marks Party Poker as a host-app-capable quick-start/settings game for Revelry. It is `can_quick_start=true`, `can_create_content=false`, `can_edit_content=false`, `supports_ai_generation=false`, and `supports_custom_content=false`. Actual Revelry visibility remains host-app policy gated and should ship only after gamma embedded QA covers start, join, spectator, reconnect, showdown, completion, and result polling. Revelry must preserve the no-money framing and must not attach sparks, rewards, buy-ins, cash-out language, or economic value to poker outcomes.

- Variant: Texas Hold'em tournament. The shipped first slice is quick Hold'em with antes plus Stay/Fold decisions; full betting is Phase 2.
- One table only in MVP.
- 2-10 players.
- Spectators can watch the table.
- Everyone starts with equal play chips.
- Players are eliminated when their stack reaches zero.
- The final surviving player is the winner.
- Runner up, third place, and full rankings are based on elimination order.
- Private hole cards are visible only to the owning player until showdown/reveal.
- No real-money terms in UX: use `play chips`, `stack`, `pot`, and `table`; avoid `buy-in`, `cash`, `wager`, `payout`, or `prize`.
- Room lifecycle should reuse the normal LocalPlay lobby, QR/join flow, spectator view, reconnect model, and podium flow.

## Goals

- Add a polished spectator-friendly poker experience for parties.
- Keep all card dealing and chip accounting authoritative on the server.
- Support standard Hold'em actions: check, call, raise, fold, all-in.
- Support side pots correctly enough for all-in scenarios.
- Redact hidden information from spectators and other players.
- Produce a clear winner, runner up, third place, and full final standings.
- Keep the first version table-local and process-local, matching current LocalPlay deployment assumptions.

## Non-Goals

- No real money, entry fee, buy-in, cash-out, crypto, gift cards, or spark conversion.
- No platform economy rewards.
- No casino branding or gambling-adjacent monetization.
- No multi-table tournament in MVP.
- No Omaha, Seven Card Stud, draw poker, or wild-card variants in MVP.
- No bot players in MVP.
- No public matchmaking.
- No persistent poker bankroll.
- No hand-history analytics beyond normal game history summary.

## Compliance and Product Framing

Party Poker must stay clearly separated from gambling:

- Every player starts with the same fixed play-chip stack.
- Chips cannot be purchased.
- Chips cannot be redeemed.
- Chips cannot be transferred outside the room.
- Game outcome does not award sparks, wallet credit, money, coupons, or prizes.
- The game is framed as a private-room party game.
- If Revelry launches the game later, Revelry also must not attach economic rewards to poker outcomes.

UI copy examples:

```text
Everyone gets the same play-chip stack. No money, no buy-ins, no cash-out.
```

```text
Play chips are only for this table.
```

## Setup

Default setup:

```json
{
  "game_type": "poker",
  "variant": "texas_holdem_tournament",
  "game_title": "Party Poker",
  "starting_stack": 1000,
  "small_blind": 10,
  "big_blind": 20,
  "blind_increase_hands": 8,
  "action_time_seconds": 25,
  "showdown_reveal": "eligible_hands",
  "spectator_delay_seconds": 0
}
```

Validation:

- `starting_stack`: 200-10000, default 1000.
- `small_blind`: 1-500, default 10.
- `big_blind`: must be at least `small_blind * 2`, default 20.
- `blind_increase_hands`: 0-50. `0` disables increases.
- `action_time_seconds`: 10-60, default 25.
- `showdown_reveal`: `eligible_hands` in MVP.
- Minimum players: 2.
- Maximum players: 10.

## Table Model

Persistent room-level state:

```json
{
  "phase": "POKER_WAITING",
  "variant": "texas_holdem_tournament",
  "players": ["p1", "p2", "p3"],
  "seats": {
    "p1": {"seat": 0, "stack": 1000, "status": "active"},
    "p2": {"seat": 1, "stack": 1000, "status": "active"},
    "p3": {"seat": 2, "stack": 1000, "status": "active"}
  },
  "dealer_seat": 0,
  "small_blind": 10,
  "big_blind": 20,
  "hand_number": 0,
  "eliminations": [],
  "standings": []
}
```

## Host Controller and Player Seating

Party Poker should use the shared card-game host model:

- The server is the dealer and owns all hidden state.
- The organizer controls setup, start, pause, and end-game actions.
- The organizer is not automatically seated.
- If the host wants to play, they join the room as a normal player from a phone or separate tab.
- The organizer control view never receives hole cards, undealt deck order, or any private player-only payload.
- A host who is also a player receives their hole cards only on their player connection.
- Spectator/TV remains public-state only.

This lets the host play without introducing a trusted human dealer or leaking private hands to the control screen.

Hand-level state:

```json
{
  "hand_id": "room:42",
  "phase": "PREFLOP",
  "deck": [],
  "hole_cards": {
    "p1": [],
    "p2": []
  },
  "community_cards": [],
  "pot": 0,
  "side_pots": [],
  "current_bet": 20,
  "min_raise": 20,
  "contributions": {
    "p1": 10,
    "p2": 20
  },
  "acted_this_street": [],
  "active_player_id": "p3",
  "last_aggressor_id": "p2",
  "action_deadline": 1234567890
}
```

Seat statuses:

- `active`: can play future hands.
- `in_hand`: currently live in this hand.
- `folded`: folded this hand.
- `all_in`: all chips committed; still eligible for pots.
- `eliminated`: stack is zero after a completed hand.
- `disconnected`: temporarily absent but not eliminated.

## Game Phases

Room phases:

- `POKER_WAITING`: lobby/table setup.
- `POKER_HAND_START`: blinds/deal are being prepared.
- `POKER_BETTING`: current betting street is active.
- `POKER_SHOWDOWN`: eligible hands are revealed and evaluated.
- `POKER_HAND_RESULT`: pot winners and eliminations are shown.
- `PODIUM`: tournament finished.

Betting streets:

- `PREFLOP`
- `FLOP`
- `TURN`
- `RIVER`

## Hand Flow

1. Host starts the game with 2-10 connected players.
2. Server assigns seats and equal starting stacks.
3. Server chooses dealer button. For two players, dealer is small blind.
4. Server posts blinds from player stacks.
5. Server shuffles one standard 52-card deck.
6. Server deals two private hole cards to each active player.
7. Preflop betting starts with the player after the big blind.
8. When betting is closed, server deals flop: three community cards.
9. Flop betting starts with the first live player left of dealer.
10. Server deals turn, then turn betting.
11. Server deals river, then river betting.
12. If only one player remains unfolded, that player wins all claimable pots immediately.
13. Otherwise, showdown reveals eligible hands.
14. Server evaluates best five-card poker hands from each player's hole cards plus community cards.
15. Server awards main/side pots.
16. Players with zero stack are eliminated and recorded in standings.
17. Dealer button advances to the next non-eliminated player.
18. Blinds increase after configured number of hands if enabled.
19. Next hand starts until one player remains.
20. Final podium shows winner, runner up, third place, and full ranking.

## Player Actions

Client to server:

```json
{ "type": "POKER_CHECK" }
{ "type": "POKER_CALL" }
{ "type": "POKER_FOLD" }
{ "type": "POKER_RAISE", "amount": 60 }
{ "type": "POKER_ALL_IN" }
```

Action validation:

- Only `active_player_id` can act.
- `CHECK` only when the player has matched `current_bet`.
- `CALL` only when there is an amount to call.
- `RAISE.amount` is total contribution for the street, not just the increment.
- Raise must be at least `current_bet + min_raise` unless the player is all-in with fewer chips.
- `ALL_IN` commits the player's remaining stack.
- A player with zero chips cannot act.
- Folded and all-in players cannot act again in the current hand.

Timeout behavior:

- If check is legal, timeout checks.
- Otherwise timeout folds.
- If a disconnected player is all-in, they remain eligible for pots.
- If a disconnected player returns, they receive the current private sync and can act when their turn arrives.

## Betting Closure

A betting street closes when:

- Every live, non-all-in player has acted.
- Every live, non-all-in player has matched the current bet.

If all remaining live players are all-in, the server should deal remaining streets automatically and proceed to showdown.

## Side Pots

The engine must support side pots in MVP because all-in actions are common and avoiding them makes poker feel broken.

Side-pot rules:

- Track total hand contribution per player.
- Sort distinct contribution levels.
- For each level, create a pot from eligible players' incremental contributions.
- A player is eligible for a pot only if they contributed at least that pot level and did not fold.
- Folded players' chips remain in pots but folded players are not eligible to win.
- Award each pot independently to the best eligible hand.
- Split pots evenly; leave odd chip remainders using deterministic seat order from left of dealer.

## Hand Evaluation

Add `poker_hand_evaluator.py` with a deterministic evaluator:

```py
def evaluate_holdem_hand(hole_cards: list[dict], community_cards: list[dict]) -> dict: ...

def compare_hand_values(a: dict, b: dict) -> int: ...

def rank_showdown(players: dict[str, list[dict]], community_cards: list[dict]) -> list[dict]: ...
```

Hand ranks, high to low:

1. Royal flush
2. Straight flush
3. Four of a kind
4. Full house
5. Flush
6. Straight
7. Three of a kind
8. Two pair
9. One pair
10. High card

The evaluator should return enough detail for UI:

```json
{
  "category": "two_pair",
  "label": "Two pair, Queens and Tens",
  "rank_value": [2, 12, 10, 8],
  "best_cards": []
}
```

Implementation note:

- It is acceptable to evaluate every 5-card combination from the 7 available cards in MVP. There are only 21 combinations per player.
- Keep the evaluator pure and thoroughly tested before wiring the WebSocket runtime.

## Hidden Information and Sync

Private player sync includes:

- Own hole cards.
- Own stack and available actions.
- Amount to call.
- Minimum legal raise.
- Action deadline.

Public/spectator sync includes:

- Seats and player display info.
- Stack counts.
- Dealer/small blind/big blind markers.
- Pot and side pots.
- Community cards.
- Current actor.
- Folded/all-in/eliminated statuses.
- Last public action.
- Showdown cards only after reveal.

Never expose:

- Other players' hole cards before showdown.
- Undealt deck order.
- Burned cards if the engine models them.

## Spectator UX

Spectator view is a first-class reason to build this.

Spectator should show:

- Table ring with seats.
- Player names/avatars.
- Stack sizes.
- Dealer/blind markers.
- Pot size.
- Community cards.
- Current action highlight.
- Folded/all-in/eliminated badges.
- Showdown reveal.
- Elimination banner.
- Tournament standings.

Spectator should not show:

- Private hole cards before showdown.
- Available action buttons.
- Any play-chip wording that implies money value.

## Organizer UX

Setup:

- Starting stack.
- Blind size.
- Blind increase cadence.
- Action timer.
- Start room.

In-game controls:

- Pause/resume timer.
- Skip disconnected player using timeout rules.
- End tournament.

Host should not be able to manually edit chip stacks during a live hand in MVP.

## Player UX

Player surface:

- Own hole cards.
- Community cards.
- Pot.
- Stack.
- Amount to call.
- Available action buttons only.
- Raise slider/stepper bounded by legal min/max.
- Clear all-in confirmation if all-in is not the only legal action.
- Eliminated players become spectators on their phone.

Button copy:

- `Check`
- `Call {amount}`
- `Fold`
- `Raise to {amount}`
- `All in`

## Winner and Podium

Elimination ranking:

- When one or more players hit zero after a hand, record elimination positions.
- If multiple players are eliminated in the same hand, order them by stack before the hand, then by best showdown hand if both reached showdown, then by seat order from left of dealer.
- The last remaining player is first place.
- The last eliminated player before the winner is runner up.
- Podium should show:
  - Winner
  - Runner up
  - Third place
  - Full standings list

Game history summary:

```json
{
  "game_type": "poker",
  "variant": "texas_holdem_tournament",
  "hands_played": 18,
  "starting_stack": 1000,
  "final_standings": [
    {"player_id": "p4", "place": 1, "label": "Winner"},
    {"player_id": "p2", "place": 2, "label": "Runner up"}
  ]
}
```

## Reconnects, Disconnects, and Leaving

- Reconnected players receive their own hole cards if still in the hand.
- If a player disconnects during their turn, timer continues.
- Timeout checks when legal, otherwise folds.
- If a player disconnects while all-in, they remain in the hand.
- If a player leaves permanently, host can remove them only between hands.
- Removing a player between hands eliminates them at their current standing position.
- Spectators can reconnect without affecting table state.

## Backend Integration

Add:

```text
backend/poker_engine.py
backend/poker_hand_evaluator.py
backend/tests/test_poker_engine.py
backend/tests/test_poker_hand_evaluator.py
```

Use shared card engine from `SPEC-GAME-CARD-ENGINE.md`.

`Room` additions:

- `game_type = "poker"`
- `poker_config`
- `poker_state`

Room creation:

- Accept `game_type = "poker"` with optional setup config.
- No content generation required.
- No sparks for AI generation.
- Use normal room creation/start pricing only if the product applies a generic room cost.

## WebSocket Events

Server to clients:

```json
{ "type": "POKER_SYNC", "state": {} }
{ "type": "POKER_HAND_STARTED", "hand_number": 1 }
{ "type": "POKER_ACTION", "player_id": "p1", "action": "raise", "amount": 60 }
{ "type": "POKER_STREET", "street": "FLOP", "community_cards": [] }
{ "type": "POKER_SHOWDOWN", "revealed_hands": {} }
{ "type": "POKER_HAND_RESULT", "pots": [], "eliminations": [] }
{ "type": "POKER_TOURNAMENT_COMPLETE", "standings": [] }
```

Clients to server:

```json
{ "type": "POKER_CHECK" }
{ "type": "POKER_CALL" }
{ "type": "POKER_FOLD" }
{ "type": "POKER_RAISE", "amount": 60 }
{ "type": "POKER_ALL_IN" }
```

## Testing Plan

Card/evaluator tests:

- Every hand category ranks correctly.
- Kickers break ties correctly.
- Wheel straight `A-2-3-4-5` works.
- Flush/straight flush comparison works.
- Best 5 out of 7 is selected.
- Split pots detect exact ties.

Poker engine tests:

- Game starts with equal stacks and assigned seats.
- Dealer/blind positions are correct for 2 players and 3+ players.
- Blinds post from stacks.
- Legal actions are computed correctly.
- Invalid out-of-turn actions are rejected.
- Check/call/raise/fold/all-in transition state correctly.
- Betting street closes only when all live players have matched/acted.
- All-in fast-forwards remaining streets.
- Side pots are created and awarded correctly.
- Eliminations produce stable ranking.
- Winner/runner up/third place podium is generated.
- Sync redacts other players' hole cards.
- Reconnect restores private hand only for the reconnecting player.

Frontend tests:

- Setup renders legal controls.
- Player only sees own hole cards.
- Spectator sees table state but no private cards.
- Action buttons match legal actions.
- Raise control respects min/max.
- Eliminated player view switches to spectator mode.
- Podium shows winner, runner up, and third place.

Playwright:

- Mobile player action layout has no overlap.
- Desktop spectator table is readable with 10 players.
- Showdown reveal fits long names and split pots.
- Tournament completion renders full standings.
- Quick MVP tests cover fixed-ante Stay/Fold decisions, private hole-card redaction, showdown, next hand, elimination, and podium.

## Acceptance Criteria

- Party Poker appears as a standalone game after the quick no-money runtime is wired and tested.
- A 2-10 player table can start with equal play chips.
- Players can complete repeated quick Hold'em hands with fixed antes and Stay/Fold decisions.
- Side pots, raises, all-ins, and full betting rounds are Phase 2 acceptance criteria, not part of the first playable standalone slice.
- Hidden cards are never leaked to spectators/other players.
- Eliminated players are ranked.
- Final podium shows winner, runner up, third place, and full standings.
- No UI or API implies real money, buy-ins, cash-out, or economic value.
- Existing LocalPlay games continue to pass tests.

## Future Work

- Multi-table tournaments for 11+ players.
- Table balancing and final table merge.
- Optional faster blind structures.
- Host-selected short deck or simplified party rules.
- Omaha after Hold'em is stable.
- Replay/highlight summary.
- Revelry party hub policy enablement after embedded gamma QA and compliance copy review.
