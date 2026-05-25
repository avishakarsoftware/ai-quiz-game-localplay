# LocalPlay Bingo / Housie Game Spec

## Overview

Add a reusable **Bingo-family engine** to LocalPlay, with **Housie** as the first full game.

Housie, also known as Tambola, is a caller-led number game. Each player receives a ticket with 3 rows, usually arranged into number columns covering 1 through 90. Exactly 15 cells are filled. Numbers are called one by one by the host/caller, either manually or with auto-caller mode. Players mark matching numbers on their tickets and claim prizes such as Quick 5, Corners, Top Row, Middle Row, Bottom Row, and Full House.

This spec deliberately treats Housie as the first ruleset on top of a broader Bingo engine. Later games such as Baby Bingo, Wedding Bingo, Emoji Bingo, Photo Bingo, and Word Bingo should reuse the same card/deck/draw/claim model with different card cell content, layouts, prize patterns, and theme packs.

```text
Engine family: bingo
First game type: housie
Future game types/rulesets: baby_bingo, word_bingo, emoji_bingo, photo_bingo
Backend engine: bingo_engine.py / housie_engine.py
Frontend display name: Housie
```

## Current Implementation Status

Standalone Housie is implemented as the first Bingo-family runtime:

- `backend/bingo_engine.py` provides reusable deck/item helpers for future numeric, word, emoji, and image Bingo variants.
- `backend/housie_engine.py` generates classic 3x9 / 15-number Housie tickets, creates the 1-90 call deck, and validates Quick 5, Four Corners, Top/Middle/Bottom Row, and Full House claims.
- `backend/socket_manager.py` has a dedicated `BINGO_CALLING` runtime path. Housie does not overload quiz `QUESTION` rounds.
- Standalone catalog shows Housie. `GET /catalog?host_app=revelry` does not expose Housie yet because the host-app setup/result contract is not enabled.
- Organizer can create a Housie setup, create a room, start with at least two players, call/undo numbers, view the called board, and end the game.
- Players receive server-generated tickets, mark cells locally, submit prize claims, and see accepted claims.
- Spectator/TV receives current called numbers, latest number, and winners through `SPECTATOR_SYNC` / `BINGO_*` messages.

Known v1 limitations:

- Auto-caller mode is present in setup data but needs a complete host pause/resume/control UI.
- Creator-facing play modes need to be explicit: Beginner keeps assisted marking/called-number hints, while Pro hides called-number assistance on player tickets and requires fully manual marking.
- Claim validation must enforce the Housie/Tambola "last number" rule for all prize patterns: the claim is valid only when the latest called number is part of the claimed pattern and the pattern was not already complete before that call.
- Latest-call and winner announcement animations need a full UX pass across organizer, player, and spectator screens.
- Housie setup is in-memory like generated quiz/drawing content; durable saved Bingo templates are future work.
- Host-app/Revelry mode remains disabled until party-scoped setup, callbacks, result summaries, and e2e tests are added.

## Goals

- Add a generic Bingo-family runtime that can support numbers, words, emojis, and images.
- Ship Housie as the first implementation using classic 1-90 tickets.
- Generate valid Housie tickets with 15 filled cells and configurable number-column layout.
- Support creator-selected Beginner and Pro modes.
- Support manual calling and auto-caller pause/resume.
- Stream the latest call and call history to organizer, player, and spectator screens.
- Let players mark cells on their own ticket.
- Let players claim configured prizes.
- Validate claims server-side against the ticket, called history, prize pattern, and latest-called-number rule.
- Announce accepted claims to all surfaces with winner name and prize label.
- Show a confetti animation on all organizer, player, and spectator screens when a prize is awarded.
- Keep the spectator/TV screen useful: latest number, called board/history, live claims, winners, and player count.
- Make the engine extensible enough for Baby Bingo and other event Bingo variants without rewriting the room lifecycle.
- Support standalone LocalPlay first; expose to Revelry only after standalone UX and safe result summaries are polished.

## Constraints

- Minimum players: 2. Housie is a group game; a single player can technically mark and claim but the experience is meaningless.
- Enforce the minimum when the host starts calling, not when the room is created or when a player joins. This keeps setup and TV testing possible while still preventing a one-person live game.
- Maximum players: same as `MAX_PLAYERS_PER_ROOM` (100 by default at the time of this spec). Each player receives one ticket in v1; multi-ticket support is a future option.

## Non-Goals

- No gambling, real-money prizes, betting, or cash-out mechanics.
- No randomized paid ticket sales.
- No player-submitted images in v1.
- No automatic optical/voice recognition of calls.
- No multi-room tournaments in v1.
- No real-time persistence beyond the current LocalPlay room model in v1.
- No Revelry/host-app launch until the catalog, setup, runtime, and result summary contracts are implemented and tested.

## Product Model

### Bingo Family

A Bingo-family game has:

- A `deck`: the set of possible called items.
- A `card_layout`: the shape and fill rules for each player's board.
- A `ticket/card`: the generated player-specific board.
- A `draw_state`: called items in order.
- A `pattern_set`: prizes/claims the room supports.
- A `claim_state`: submitted, accepted, rejected, and already-awarded claims.
- A `caller_mode`: manual or auto.

The engine should not assume all cells are numbers. Housie uses numeric cells. Baby Bingo may use words, phrases, emojis, or images.

### Housie Ruleset

Housie v1 uses:

- `game_type = "housie"`
- `engine_family = "bingo"`
- Ticket layout: classic 3 rows x 9 numeric columns.
- Filled cells per ticket: 15.
- Empty cells per ticket: 15.
- Numbers: 1 through 90 inclusive.
- Each number appears at most once per ticket.
- Numbers on a ticket are arranged by configured number buckets. The classic Housie/Tambola buckets are:
  - Column 0: 1-9
  - Column 1: 10-19
  - Column 2: 20-29
  - Column 3: 30-39
  - Column 4: 40-49
  - Column 5: 50-59
  - Column 6: 60-69
  - Column 7: 70-79
  - Column 8: 80-90
- Product decision: use 9 numeric columns for Housie. Earlier product notes mentioned 10 columns, but the "last column covers both 80s and 90" rule maps to the classic 9-column Housie/Tambola ticket. Keep `column_ranges` configurable in the engine so non-Housie Bingo variants can use different layouts later, but Housie v1 should be 3x9.
- Numbers increase top-to-bottom within each column.
- Numbers are called from a shuffled 1-90 deck without replacement.

### Creator Play Modes

Housie setup must offer a creator-facing mode selector:

```json
{
  "play_mode": "beginner" | "pro"
}
```

Mode controls player assistance only. It must not change the deck, ticket shape, prize definitions, server-side claim validation, result summaries, or house rules.

`beginner` mode:

- Default mode.
- Preserves the existing player-ticket assistance behavior.
- Player ticket cells may visually indicate called-but-unmarked numbers.
- Player ticket cells may optionally auto-highlight markable cells after each call.
- Claim buttons may show friendly eligibility hints, such as "Need 1 more for Quick 5."
- The player still manually taps/marks cells unless an explicit separate `auto_mark` feature is added later.

`pro` mode:

- For traditional Housie/Tambola play.
- The player ticket must not reveal which numbers have already been called.
- Filled cells should only show neutral unmarked styling until the player manually marks them.
- The player may still see the latest number in the shared call area, because that is equivalent to hearing the caller.
- The player may see a compact recent-call feed outside the ticket only if the host enables a separate room setting. Default Pro behavior should not show full called history on the player screen.
- Claim buttons should remain available but should not expose eligibility hints that reveal hidden called-number state.
- Server validation remains authoritative and may reject claims that the player marked incorrectly.

Organizer and spectator screens are not constrained by Pro ticket assistance rules. They may show the called board/history because they act as caller/TV surfaces.

Recommended setup copy:

- Beginner: "Helpful ticket mode. Called numbers are shown on each player ticket."
- Pro: "Classic mode. Players mark tickets themselves; called numbers are not highlighted on tickets."

## Ticket Generation

### Housie Ticket Shape

```ts
type HousieTicket = {
  ticket_id: string;
  player_id: string;
  layout: {
    rows: 3;
    columns: 9;
    column_ranges: Array<[number, number]>;
  };
  cells: Array<Array<HousieCell | null>>;
};

type HousieCell = {
  kind: "number";
  value: number;
  display: string;
  column: number;
  row: number;
  marked: boolean;
};
```

### Generation Constraints

Each ticket must satisfy:

- 3 rows.
- 9 numeric columns.
- 15 filled cells total.
- Exactly 5 filled cells per row.
- No more than 3 filled cells in any column.
- A column may have 0 filled cells.
- No duplicate numbers.
- Filled numbers belong to their column range.
- Filled numbers in a column are sorted ascending from top to bottom.

Recommended algorithm:

1. Start with a 3-row matrix using the configured number-column count.
2. Allocate exactly 5 filled positions per row.
3. Ensure the resulting column counts are each between 0 and 3.
4. Prefer a balanced spread so tickets are legible; avoid placing all cells into a small set of columns.
5. For each column with `n` filled positions:
   - sample `n` unique numbers from that column's range.
   - sort ascending.
   - assign sorted values to filled row positions from top to bottom.
6. Validate the final ticket. If invalid, retry with a bounded attempt count.

Implementation must include deterministic unit tests with seeded randomness.

### Ticket Uniqueness

For v1, tickets should be unique within a room by a stable hash of their filled cells. If the generator produces a duplicate, retry. This is not a cryptographic guarantee; it is enough for a local party room.

## Caller / Draw Flow

### Manual Caller

The host sees:

- Current/latest called item.
- Next number button.
- In manual mode, the primary `Call next` button must be placed above the prize panel so calling remains the host's first visible action.
- Undo last call. Disabled when any accepted claim was validated against the last called number. The server checks whether removing the last call would invalidate any accepted claim; if so, undo is blocked and the organizer sees a disabled state with a tooltip or label explaining why.
- Full called board/history.
- Claim queue.
- Prize status.
- Auto-caller toggle.

### Auto Caller

Auto-caller mode should:

- Call the next item every configured interval, default 8 seconds.
- Let the host configure the timer before start and adjust it while paused, clamped to the supported interval range.
- Let host pause/resume.
- Let host switch between manual and auto while the game is active.
- When `auto_pause_on_claim` is true, pause auto-caller while a claim is pending validation. Resume automatically after the claim is accepted or rejected, unless the accepted claim closes a terminal prize.
- When `auto_pause_on_claim` is false, auto-caller continues calling while claims are processed.
- Stop automatically when all numbers are called or a configured terminal prize is awarded.
- Announce upcoming call visually with a short countdown on organizer/spectator and, if space allows, on player screens.
- Never skip claim validation; players can still claim while auto-caller is running.
- Never call more than one number at a time. The server-side auto task must await each broadcast/claim-lock step before sleeping for the next interval.
- Clamp interval to a safe range, recommended 3-30 seconds.

Auto-caller settings:

```json
{
  "caller_mode": "manual" | "auto",
  "auto_interval_seconds": 8,
  "auto_pause_on_claim": true
}
```

Auto-caller state should be visible in sync payloads:

```json
{
  "caller_mode": "auto",
  "auto_status": "running" | "paused" | "stopped",
  "auto_interval_seconds": 8,
  "auto_pause_on_claim": true,
  "next_auto_call_at": "2026-05-25T20:15:30Z"
}
```

If the organizer disconnects during auto mode, the backend should pause the auto-caller during the organizer reconnect grace period rather than continuing unattended.

## Prize / Claim Patterns

Housie v1 should support these prize patterns:

| Pattern | Meaning |
|---|---|
| `quick_5` | First player to mark any 5 called numbers on their ticket |
| `four_corners` | First and last filled cells in the top row, and first and last filled cells in the bottom row, are all marked. These are the outermost filled cells, not literal grid positions, since Housie rows have only 5 of 9 columns filled. |
| `top_row` | All filled cells in row 0 are marked |
| `middle_row` | All filled cells in row 1 are marked |
| `bottom_row` | All filled cells in row 2 are marked |
| `full_house` | All 15 filled cells are marked |

Prize configuration should be room-level:

```json
{
  "patterns": [
    { "id": "quick_5", "label": "Quick 5", "max_winners": 1 },
    { "id": "four_corners", "label": "Corners", "max_winners": 1 },
    { "id": "top_row", "label": "Top Row", "max_winners": 1 },
    { "id": "middle_row", "label": "Middle Row", "max_winners": 1 },
    { "id": "bottom_row", "label": "Bottom Row", "max_winners": 1 },
    { "id": "full_house", "label": "Full House", "max_winners": 1, "terminal": true }
  ]
}
```

A `terminal` prize ends the game when its `max_winners` count is reached. If `max_winners` is 1, the game ends on the first Full House claim. If `max_winners` is greater than 1, claims are accepted until the count is reached, then the game ends.

If all 90 numbers are called before any terminal prize is awarded, the game should auto-complete. The result summary records the state at that point with any prizes awarded so far.

If simultaneous claims occur for the same pattern after the same call, the room should support tie behavior:

- v1 default: first valid claim received by the server wins.
- Future option: all valid claims after the same call share the prize.

This should be explicitly visible in host settings later. For v1, keep it simple and deterministic.

## Claim Validation

Players submit a claim with:

```json
{
  "type": "BINGO_CLAIM",
  "pattern_id": "quick_5"
}
```

The server resolves the player and their ticket from the WebSocket connection. Clients do not supply `ticket_id` in the claim message.

Server validation:

1. Player has a ticket in the active room.
2. Pattern is enabled in the room.
3. Pattern has not already reached `max_winners`.
4. The pattern's required cells are all present on the ticket and have all been called. For row patterns and full house, the required cells are deterministic from the ticket layout. For `quick_5`, the server checks that at least 5 of the player's filled ticket numbers appear in the called history; the player does not choose which 5.
5. For `four_corners`, the server identifies the outermost filled cells in the top and bottom rows and checks that all four have been called.
6. The latest called number must be part of the winning evidence for the pattern.
7. The pattern must not have been complete for that player before the latest called number.

Do not trust client-side marked state. Client marks are local convenience. The server validates from ticket contents and called history.

### Last-Called-Number Rule

All Housie prize claims use the traditional last-called-number rule in both Beginner and Pro modes. A claim is valid only if the latest called number caused that specific pattern to become complete.

This prevents stale claims. Example: if a player's Top Row became complete when 42 was called, but the player waits until after 73 is called to claim Top Row, the server rejects the claim with `stale_claim` because the match did not occur on the last number.

Pattern-specific validation:

- `quick_5`: accepted only when the latest called number is on the player's ticket, is among the called numbers, and the player had exactly 4 called ticket numbers before the latest call and at least 5 after it.
- `four_corners`: accepted only when the latest called number is one of that ticket's four corner cells, all four corner cells are called after the latest call, and at least one corner cell was uncalled before the latest call.
- `top_row`, `middle_row`, `bottom_row`: accepted only when the latest called number is in the claimed row, the row is complete after the latest call, and the row was incomplete before the latest call.
- `full_house`: accepted only when the latest called number is on the ticket, all 15 filled cells are called after the latest call, and the ticket was incomplete before the latest call.

Implementation detail:

```python
called_before_latest = called_numbers - {latest_number}
```

The validator should check the pattern against both `called_before_latest` and `called_numbers`. A valid claim is one where the pattern is false before the latest call and true after the latest call, and the latest number contributes to the claimed pattern.

Claim rejection reasons should include:

| Reason | Meaning |
|---|---|
| `unknown_pattern` | Pattern id is not enabled or not recognized. |
| `already_awarded` | Pattern has reached `max_winners`. |
| `not_complete` | Pattern is not complete after the latest call. |
| `stale_claim` | Pattern was already complete before the latest call. |
| `latest_number_not_in_pattern` | Latest call did not contribute to this claimed pattern. |
| `no_calls_yet` | Player claimed before any number was called. |

Claim response events:

```json
{
  "type": "BINGO_CLAIM_ACCEPTED",
  "pattern_id": "quick_5",
  "pattern_label": "Quick 5",
  "player_id": "p1",
  "player_name": "Avi",
  "call_index": 23,
  "winning_number": 42,
  "announce": true
}
```

```json
{
  "type": "BINGO_CLAIM_REJECTED",
  "pattern_id": "quick_5",
  "reason": "stale_claim"
}
```

Accepted claims should be announced on organizer, player, and spectator screens.

## Room State

Add a Bingo/Housie branch to room runtime state.

```ts
type BingoRoomState = {
  game_type: "housie" | "baby_bingo" | "word_bingo" | "emoji_bingo" | "photo_bingo";
  engine_family: "bingo";
  phase: "lobby" | "calling" | "paused" | "complete";
  deck: BingoDeckItem[];
  called_items: BingoDeckItem[];
  latest_item: BingoDeckItem | null;
  tickets_by_player: Record<string, BingoTicket>;
  patterns: BingoPrizePattern[];
  winners: BingoWinner[];
  claim_log: BingoClaim[];
  play_mode: "beginner" | "pro";
  caller_mode: "manual" | "auto";
  auto_status: "running" | "paused" | "stopped";
  auto_interval_seconds: number;
  auto_pause_on_claim: boolean;
  next_auto_call_at?: string | null;
  claim_requires_latest_call: true;
};
```

`BingoDeckItem` must support multiple content types:

```ts
type BingoDeckItem =
  | { kind: "number"; value: number; display: string }
  | { kind: "word"; value: string; display: string }
  | { kind: "emoji"; value: string; display: string }
  | { kind: "image"; asset_id: string; public_url: string; alt_text: string; display: string };
```

For Housie v1, only `number` is needed.

## WebSocket Events

Organizer to server:

- `BINGO_START`
- `BINGO_CALL_NEXT`
- `BINGO_UNDO_LAST_CALL`
- `BINGO_SET_CALLER_MODE`
- `BINGO_SET_PLAY_MODE` only before start, or via setup save before room creation.
- `BINGO_PAUSE`
- `BINGO_RESUME`
- `BINGO_END_GAME`

Player to server:

- `BINGO_MARK_CELL` for local echo/state sync; server may ignore for validation.
- `BINGO_UNMARK_CELL`
- `BINGO_CLAIM`

Server to all:

- `BINGO_SYNC`
- `BINGO_CALL`
- `BINGO_AUTO_STATUS`
- `BINGO_CLAIM_ACCEPTED`
- `BINGO_CLAIM_REJECTED`
- `BINGO_PRIZE_CLOSED`
- `BINGO_WINNER_ANNOUNCEMENT`
- `BINGO_COMPLETE`

`SPECTATOR_SYNC` should include the current Bingo/Housie state when a spectator joins mid-game.

## Surfaces

### Organizer

The organizer UI should be caller-first:

- Large latest call.
- Manual `Call next` button.
- Auto-caller controls.
- Beginner/Pro mode shown as read-only once the game starts.
- Called board/history.
- Prize panel with open/awarded state.
- Claim queue/log.
- Player count.
- End game button.

Recommended host layout order:

1. Latest call / auto-caller status.
2. Primary call controls: `Call next`, pause/resume, timer.
3. Called board/history.
4. Prize panel.
5. Claim queue/log.

### Player

The player UI should be ticket-first:

- Player's own ticket.
- Latest call.
- Mark/unmark cells.
- Available claim buttons.
- Claim status feedback.
- Winners/prizes already awarded.

In Beginner mode, player cells should visibly distinguish:

- Empty cells.
- Uncalled filled cells.
- Called but unmarked cells.
- Marked cells.
- Cells involved in a winning claim.

In Pro mode, player ticket cells should visibly distinguish only:

- Empty cells.
- Unmarked filled cells.
- Player-marked cells.
- Cells involved in an accepted winning claim after the server announces the prize.

Pro mode must not style unmarked cells based on called history. The frontend may still keep called history in memory if needed for sync/reconnect, but ticket rendering must not use it to reveal assistance.

### Spectator / TV

The spectator screen should be readable from across a room:

- Very large latest call.
- Draw history or called-number board.
- Prize winners.
- Claim announcements.
- Confetti and winner name/prize announcement on accepted claims.
- Player count.
- QR/join link behavior should reuse existing host-app/standalone share policy.

For Housie, a 1-90 called board is better than a long list once enough calls have happened.

## Setup / Authoring

### Standalone Housie Setup

Standalone setup fields:

- Game title.
- Play mode: Beginner or Pro.
- Caller mode: manual or auto.
- Auto interval.
- Auto pause on claim.
- Enabled prize patterns.
- Tie behavior, future.
- Number of tickets per player, future.
- Ticket layout is classic 3x9 for Housie. Other Bingo-family games can use different layouts.

No AI is required for numeric Housie v1.

### Bingo Family Setup

Generic Bingo-family setup fields for future games:

- Board/card layout.
- Content source:
  - built-in template.
  - manual word/emoji list.
  - AI-generated list.
  - uploaded image set.
- Minimum deck size.
- Prize patterns.
- Theme/party type.
- Media safety settings.

### Baby Bingo

Baby Bingo should be a ruleset on the same engine:

- Game type: `baby_bingo`.
- Deck items: baby shower gifts, baby items, predictions, phrases, or emojis.
- Card layout: likely 5x5 or configurable.
- Center free square optional.
- AI prompt generation from party context should be supported before Revelry launch.
- Image cells can be supported later using the shared media layer from `SPEC-IMAGE-GAMES.md`.

## Persistence

v1 can keep live room state process-local like the current room runtime, but setup/content should be durable when saved.

Recommended durable objects:

- Bingo setup/template:
  - `content_id`
  - `game_type`
  - `engine_family`
  - `title`
  - `deck_config`
  - `layout_config`
  - `patterns`
  - `caller_settings`
  - ownership scope
- Game history summary:
  - called count.
  - winners by pattern.
  - player count.
  - duration.
  - safe title.

Do not persist raw per-player ticket state in feed/result summaries unless needed for recovery and explicitly safe.

For host-app mode, saved content should use the existing party-scoped saved content model where possible. If the current generic `generated_content` payload becomes too loose for Bingo, add typed schema validation before enabling host-app launch.

## Catalog Metadata

Standalone catalog entry:

```json
{
  "id": "housie",
  "game_type": "housie",
  "engine_family": "bingo",
  "title": "Housie",
  "description": "Caller-led number tickets with Quick 5, rows, corners, and full house.",
  "status": "planned",
  "launchable": false,
  "supports_manual_authoring": true,
  "supports_ai_generation": false,
  "requires_content": false,
  "can_create_content": true,
  "can_quick_start": true,
  "supported_media": ["none"],
  "content_schema": "bingo_setup_v1",
  "config_options": {
    "play_modes": ["beginner", "pro"],
    "caller_modes": ["manual", "auto"],
    "default_play_mode": "beginner",
    "default_caller_mode": "manual",
    "claim_requires_latest_call": true
  },
  "result_summary_schema": "bingo_result_v1"
}
```

Revelry/host-app catalog should keep `launchable = false` until:

- standalone Housie runtime is playable.
- organizer/player/spectator routes work.
- safe result summaries are implemented.
- host-app chrome and share policies are applied.
- party-scoped setup save/start is tested.
- callbacks include safe `game.session_created`, `game.started`, and `game.completed` summaries.

## Results

Safe result summary:

```json
{
  "game_type": "housie",
  "title": "Christmas Housie",
  "status": "complete",
  "called_count": 47,
  "player_count": 12,
  "play_mode": "pro",
  "caller_mode": "auto",
  "winners": [
    { "pattern_id": "quick_5", "label": "Quick 5", "player_name": "Avi", "winning_number": 42 },
    { "pattern_id": "top_row", "label": "Top Row", "player_name": "Maya" },
    { "pattern_id": "full_house", "label": "Full House", "player_name": "Sam" }
  ]
}
```

Do not include:

- per-player full tickets.
- hidden/uncalled deck order.
- participant secrets.
- private media paths.
- raw internal logs.

## Integration With Revelry / Host Apps

Housie should start in standalone LocalPlay. Later, when enabled for Revelry:

- The Revelry Games hub shows Housie from `GET /catalog?host_app=revelry`.
- Host/cohost can set up Housie or quick-start a default Housie room.
- Guests see join/watch only.
- Runtime hides sparks/wallet/paywall/account/library chrome in host-app mode.
- QR/share uses Revelry-owned join URLs when provided.
- Results callback posts safe winner/prize summaries.
- Party type can influence templates later, such as holiday Housie or baby shower Bingo.

## Future Payment Integration

Do not implement Housie-specific payments in the current Housie gameplay slice.

When LocalPlay later adds paid Housie/Bingo features, payments should stay outside the live draw/claim path. A player should never be blocked by a checkout prompt after joining an active room.

Allowed future paid surfaces:

- Standalone LocalPlay premium Housie templates or theme packs.
- Larger saved template library/retention.
- Premium host controls such as custom branding, advanced auto-caller voices, custom prize labels, or analytics.
- Event/Baby Bingo AI generation packs.
- Multi-session party pass or subscription entitlements.

Disallowed monetization surfaces:

- Real-money prizes, betting, cash-out, or wagering.
- Randomized paid ticket sales.
- Per-player paid ticket advantages.
- Paid claim priority or paid second chances.

Recommended payment architecture:

- Use existing LocalPlay entitlement/wallet capability checks before room creation or setup save, not during gameplay.
- For standalone web one-time purchases, use Stripe Checkout Sessions.
- For native iOS purchases, continue to respect the existing server-side rule that blocks Stripe checkout from iOS and use Apple IAP if native purchases are introduced.
- For Revelry-launched sessions, keep billing host-app-managed. LocalPlay should receive capabilities such as `premium_housie_templates`, `ai_bingo_generation`, or `party_games`, not raw payment provider state.
- Result summaries and callbacks must not include Stripe session ids, receipt payloads, prices, refund state, or other payment data.

## Implementation Details

This section is the build checklist. If it conflicts with higher-level product notes above, prefer this section for v1 implementation.

### Backend Files

Add or update:

- `backend/bingo_engine.py`
  - Pure, deterministic Bingo-family helpers.
  - No FastAPI, WebSocket, token, or database imports.
- `backend/housie_engine.py`
  - Housie-specific ticket generation, default pattern definitions, and claim validation.
  - May import shared types/helpers from `bingo_engine.py`.
  - Enforce the latest-called-number rule for every claim.
- `backend/socket_manager.py`
  - Add `housie` runtime branch to `Room`.
  - Add Housie state reset, sync, call, claim, auto-caller, completion, and history behavior.
- `backend/main.py`
  - Accept `game_type = "housie"` in room creation validation.
  - Add optional `housie_id` or generic `content_id` handling for saved/default Housie setup.
  - Add catalog metadata for standalone Housie as disabled/planned until runtime is implemented.
  - Add `/housie/default` or equivalent only if the frontend needs a setup preview endpoint; otherwise create content directly at room creation.
- `backend/config.py`
  - Add `MIN_HOUSIE_PLAYERS = 2`.
  - Reuse `MAX_PLAYERS_PER_ROOM`.
- `backend/tests/test_housie_engine.py`
  - Pure engine tests.
- `backend/tests/test_housie_ws.py` or existing WebSocket flow tests
  - Runtime/caller/claim/spectator tests.

Do not add Supabase schema in v1 unless durable saved Housie setups require a new typed table. Prefer the existing generated content model for initial saved setup payloads if it is sufficient.

### Frontend Files

Add or update:

- `frontend/src/types.ts`
  - Add `housie` to `GameType`.
  - Add shared Bingo/Housie types if used across surfaces.
- `frontend/src/gameModes.ts`
  - Add a Housie catalog config with `runtimeType: "housie"` after `runtimeType` supports it.
- `frontend/src/pages/OrganizerPage.tsx`
  - Add Housie setup entry point.
  - Add caller runtime branch once room is created.
- `frontend/src/pages/PlayerPage.tsx`
  - Add player ticket runtime branch.
- `frontend/src/pages/SpectatorPage.tsx`
  - Add Housie spectator/called-board branch.
- `frontend/src/components/organizer/HousieSetupScreen.tsx`
  - Standalone setup: title, Beginner/Pro mode, caller mode, interval, auto-pause-on-claim, prize toggles.
- `frontend/src/components/organizer/HousieCallerScreen.tsx`
  - Organizer/caller runtime controls, auto-caller status, and latest-call animation.
- `frontend/src/components/player/HousieTicket.tsx`
  - Player ticket grid and claim buttons. Rendering must respect Beginner vs Pro assistance rules.
- `frontend/src/components/spectator/HousieSpectatorScreen.tsx`
  - TV/spectator latest call, called board, winner announcements, and confetti.
- `frontend/src/components/housie/`
  - Optional shared visual pieces: ticket grid, called board, prize badge, latest call overlay, confetti layer.

Keep Housie UI components shared between standalone and future host-app mode. Host-app behavior should be props/context policy, not a forked UI.

### TypeScript Runtime Types

Add these types or close equivalents:

```ts
export type BingoItem =
  | { kind: "number"; value: number; display: string }
  | { kind: "word"; value: string; display: string }
  | { kind: "emoji"; value: string; display: string }
  | { kind: "image"; asset_id: string; public_url: string; alt_text: string; display: string };

export type BingoCell =
  | {
      kind: "number";
      value: number;
      display: string;
      row: number;
      column: number;
      marked: boolean;
    }
  | {
      kind: "word" | "emoji";
      value: string;
      display: string;
      row: number;
      column: number;
      marked: boolean;
    }
  | {
      kind: "image";
      asset_id: string;
      public_url: string;
      alt_text: string;
      display: string;
      row: number;
      column: number;
      marked: boolean;
    };

export interface HousieCell {
  kind: "number";
  value: number;
  display: string;
  row: number;
  column: number;
  marked: boolean;
}

export interface HousieTicket {
  ticket_id: string;
  player_id: string;
  layout: {
    rows: 3;
    columns: 9;
    column_ranges: Array<[number, number]>;
  };
  cells: Array<Array<HousieCell | null>>;
}

export interface BingoPattern {
  id: "quick_5" | "four_corners" | "top_row" | "middle_row" | "bottom_row" | "full_house" | string;
  label: string;
  max_winners: number;
  terminal?: boolean;
}

export interface BingoWinner {
  pattern_id: string;
  pattern_label: string;
  player_id: string;
  player_name: string;
  call_index: number;
  winning_number?: number;
}
```

### Engine Function Contracts

`housie_engine.py` should expose pure functions shaped like:

```python
def default_housie_patterns() -> list[dict]:
    ...

def build_housie_deck(rng: random.Random | None = None) -> list[dict]:
    """Return shuffled number items 1..90 without replacement."""

def generate_housie_ticket(
    player_id: str,
    rng: random.Random | None = None,
    existing_hashes: set[str] | None = None,
) -> dict:
    """Return one valid 3x9/15-cell ticket."""

def validate_housie_ticket(ticket: dict) -> tuple[bool, list[str]]:
    """Return validity plus machine-readable error codes."""

def ticket_hash(ticket: dict) -> str:
    """Stable hash of filled numeric values and positions."""

def required_cells_for_pattern(ticket: dict, pattern_id: str) -> list[dict] | None:
    """Return the fixed set of ticket cells required for a prize claim, or None
    for threshold patterns like quick_5 where any N called cells satisfy the claim."""

def validate_housie_claim(
    ticket: dict,
    pattern_id: str,
    called_numbers: set[int],
    latest_number: int | None,
    awarded_patterns: dict[str, list[dict]],
) -> tuple[bool, str]:
    """Return (accepted, reason). Reasons include accepted, unknown_pattern,
    already_awarded, not_complete, stale_claim, latest_number_not_in_pattern,
    and no_calls_yet."""
```

`bingo_engine.py` should contain generic helpers that future word/emoji/image Bingo can reuse:

```python
def normalize_bingo_item(raw: dict) -> dict: ...
def called_value_set(called_items: list[dict]) -> set[str | int]: ...
def count_markable_items(ticket: dict, called_values: set[str | int]) -> int: ...
```

### Ticket Generation Algorithm Details

Use a bounded retry algorithm so generation cannot loop forever:

```python
MAX_TICKET_GENERATION_ATTEMPTS = 200
```

Recommended position allocation:

1. Generate all row masks with exactly 5 filled cells across 9 columns.
2. Pick one mask for each of 3 rows.
3. Reject if any column has more than 3 cells.
4. Prefer masks where at least 7 of 9 columns are used; this keeps tickets visually balanced while still allowing empty columns.
5. Sample column numbers and sort top-to-bottom.
6. Validate and hash.
7. Retry on duplicate hash or invalid ticket.

Do not mutate global randomness in tests. Accept an injected `random.Random`.

### Socket Manager Integration

Extend `Room` with Housie fields. Keep names separate from quiz/WMLT/drawing fields so reset behavior is readable:

```python
self.bingo_deck: list[dict] = []
self.bingo_called_items: list[dict] = []
self.bingo_latest_item: Optional[dict] = None
self.bingo_tickets: dict[str, dict] = {}  # player_id -> ticket
self.bingo_patterns: list[dict] = []
self.bingo_winners: list[dict] = []
self.bingo_claim_log: list[dict] = []
self.bingo_play_mode: str = "beginner"
self.bingo_caller_mode: str = "manual"
self.bingo_auto_status: str = "stopped"
self.bingo_auto_interval_seconds: int = 8
self.bingo_auto_pause_on_claim: bool = True
self.bingo_auto_task: Optional[asyncio.Task] = None
self.bingo_next_auto_call_at: Optional[str] = None
self.bingo_pending_claims: set[str] = set()
```

Reset these fields in `reset_for_new_game()`.

`Room.total_rounds()` for Housie should return `len(self.bingo_deck)` or `90`, but organizer/player UX should not depend on quiz-style round indexes.

Room states:

- Use existing `LOBBY` before game start.
- Add Housie-specific states using the existing `state` string:
  - `BINGO_CALLING`
  - `BINGO_PAUSED`
  - `PODIUM` or `COMPLETE` depending on current completion conventions.

Avoid overloading `QUESTION` for Housie. It makes spectator/player branching confusing.

### WebSocket Payloads

#### Organizer Starts Housie

```json
{
  "type": "BINGO_START",
  "play_mode": "beginner",
  "caller_mode": "manual",
  "auto_interval_seconds": 8,
  "auto_pause_on_claim": true,
  "patterns": ["quick_5", "four_corners", "top_row", "middle_row", "bottom_row", "full_house"]
}
```

Server behavior:

- Reject if fewer than `MIN_HOUSIE_PLAYERS`.
- Generate one ticket for every connected player who does not already have one.
- Initialize shuffled deck if needed.
- Broadcast `BINGO_SYNC`.

#### Organizer Calls Next

```json
{ "type": "BINGO_CALL_NEXT" }
```

Server broadcasts:

```json
{
  "type": "BINGO_CALL",
  "item": { "kind": "number", "value": 42, "display": "42" },
  "call_index": 12,
  "called_count": 12,
  "remaining_count": 78,
  "animation": "latest_call"
}
```

#### Player Claim

```json
{
  "type": "BINGO_CLAIM",
  "pattern_id": "top_row"
}
```

Server infers `player_id` and ticket from the websocket connection. Do not accept a client-supplied `ticket_id`; reject malformed claim payloads that include ticket ownership fields.

### Reconnect Behavior

Player reconnect should restore:

- same nickname/session token behavior as existing games.
- existing ticket.
- local marked state if server chooses to sync marks.
- called history.
- claim/winner state.

If server does not persist marks, client can recompute markable cells from called history and its local selections. Server claim validation remains authoritative either way.

Organizer reconnect should tolerate normal mobile sleep/background behavior. A host phone lock must not close the room immediately. The backend uses `ORGANIZER_RECONNECT_GRACE_SECONDS` before deleting a room after organizer disconnect; the default should remain around 10 minutes for party play. Players should see a host-disconnected waiting state during this grace period, and the organizer should receive a full Housie sync on reconnect.

The player client should also attempt a wake reconnect on `pageshow`, `visibilitychange`, `focus`, or `online` when it has a saved room/session token. If the socket is still open, the client may send a lightweight ping message to refresh activity; if it is closed, it should rejoin using the saved session token.

### Ticket Visual Model

Housie tickets should look like traditional paper tickets:

- Render as an actual 3x9 table structure, not a loose list or flex layout.
- Use a warm cream ticket background.
- Show visible gridlines between all cells.
- Empty cells stay the same paper family as filled cells, but remain blank and non-interactive.
- Filled cells use dark ink.
- Beginner mode may show called-but-unmarked cells using a high-contrast hint style without hiding the ticket grid.
- Pro mode must not reveal called-but-unmarked cells on the ticket.
- Marked cells use a player-applied daub/strike style that remains legible.
- Winning cells may use a celebration ring/glow after the server accepts a claim.

### Latest Call And Winner Visuals

Latest call animation:

- On every `BINGO_CALL`, show the called number as a large center-stage number on organizer, player, and spectator screens.
- The number should enter quickly, hold briefly, then fade/scale away into the called board/history.
- Recommended timing: 150-250ms entrance, 900-1400ms hold, 400-700ms fade.
- Respect `prefers-reduced-motion`: replace movement with a brief opacity/highlight change.
- The animation must not block ticket marking or host controls.

Winner animation:

- On every `BINGO_CLAIM_ACCEPTED`, show confetti on organizer, player, and spectator screens.
- Announce: `{player_name} won {pattern_label}`.
- Include the winning number when available: `{player_name} won Quick 5 on 42`.
- The successful claimant's player screen should get the strongest treatment: full-screen confetti, a personal "You won {pattern_label}" banner, and highlighted winning cells.
- Other player screens should show a smaller shared announcement so they know who won without losing ticket context.
- Spectator/TV should use the largest announcement treatment.
- Player screens should show the announcement without covering the ticket for too long.
- Respect `prefers-reduced-motion`: use a static celebratory banner instead of falling confetti.
- Use one shared confetti/announcement component where possible so behavior stays consistent across surfaces.

Suggested component names:

- `LatestCallOverlay`
- `WinnerAnnouncement`
- `ConfettiBurst`

### History And Results

When a Housie room completes, write a `game_history` entry with:

- `game_type = "housie"`.
- `game_title`.
- `player_count`.
- `completed_at`.
- `total_questions = 0` or a future renamed/optional round count; do not pretend there were quiz questions.
- `leaderboard = []` unless later scoring is added.
- `metadata` or game-specific result payload with:
  - `called_count`.
  - `winners`.
  - `patterns`.
  - `play_mode`.
  - `caller_mode`.
  - `duration_seconds`.

If the current history schema cannot store game-specific metadata, v1 may store a safe summary in existing fields and add richer metadata in a later persistence migration. Document any compromise in `SPEC.md` before implementation.

### Play Again

Standalone Housie `Play Again` should reuse the current Housie setup/content id and issue `RESET_ROOM`, not reopen the setup form or create a new setup first. The room code and connected players remain, Housie call/ticket/winner state is cleared, and the host returns to the lobby. New tickets are generated when the host starts the next round.

`Choose Another Game` is a separate final-results action. Standalone hosts return to the main game picker and can create/select different content that resets the same room. Host-app/party-scoped hosts return to the party's LocalPlay/Revelry Games hub, where game selection remains party-scoped.

### Catalog And API Guardrails

Do not expose Housie in host-app catalog until the host-app contract is done. Standalone catalog can show Housie only when playable.

Required backend validation:

- `RoomCreateRequest.validate_game_type` accepts `housie` only after runtime is implemented.
- Unknown Bingo pattern ids are rejected.
- Auto interval is clamped, recommended 3-30 seconds.
- `play_mode` is either `beginner` or `pro`; unknown values fall back to `beginner` only during old-content migration, otherwise reject.
- Enabled pattern list must not be empty.
- Housie room creation never accepts arbitrary player tickets from clients.
- Claim validation always enforces `claim_requires_latest_call = true` for Housie.

### Styling And UX

Housie should feel like a real game, not a debug panel:

- Use large tactile number tiles.
- Called numbers should animate into history.
- The latest number should briefly become the dominant element on screen and then gracefully disappear.
- Accepted claims should trigger confetti plus a clear player-name/prize announcement on every surface.
- Player ticket should be thumb-friendly on mobile.
- Claims should be prominent but not easy to mis-tap; use confirmation for claim buttons if multiple patterns are available.
- Spectator latest call should be huge and high contrast.
- Use existing Velvet tokens and avoid nested cards.

### Accessibility

- Ticket cells need text labels such as `Column 4, row 2, number 37, marked`.
- Called-board cells need called/not-called labels.
- Do not rely only on color to show marked/called/winning states.
- Auto-caller controls must be keyboard reachable.
- Claim rejection should be announced in an ARIA live region.

### Test Matrix

Backend engine tests:

- `generate_housie_ticket` returns 3 rows and 9 columns.
- Every generated ticket has exactly 15 filled cells.
- Every row has exactly 5 filled cells.
- No column has more than 3 filled cells.
- Numbers are unique within a ticket.
- Numbers fall within their configured column range.
- Numbers sort ascending top-to-bottom in each column.
- Repeated seeded generation is deterministic.
- Duplicate ticket hashes cause retry.
- `quick_5` accepts any 5 called ticket numbers and rejects 4.
- `quick_5` rejects stale claims where 5 called ticket numbers were already present before the latest call.
- Every prize rejects when the latest number is not part of the claimed pattern.
- `four_corners` uses outermost filled top/bottom cells, not literal empty corner grid cells.
- `top_row`, `middle_row`, `bottom_row`, and `full_house` validate correctly.
- Claims reject unknown patterns, already-awarded patterns, uncalled numbers, wrong-player tickets, stale claims, and claims before any call.

Backend WebSocket tests:

- Organizer cannot start Housie calling with fewer than 2 players.
- Organizer can start once 2 players have joined.
- Players receive server-generated tickets.
- Spectator receives `SPECTATOR_SYNC` with Housie state after joining mid-game.
- `BINGO_CALL_NEXT` advances without repeating numbers.
- `BINGO_UNDO_LAST_CALL` works before dependent claims and is rejected after dependent claims.
- Beginner mode sync allows player ticket assistance.
- Pro mode sync/rendering does not reveal called-but-unmarked cells on player tickets.
- Accepted claim broadcasts to organizer, player, and spectator.
- Rejected claim only notifies the claiming player plus optional organizer log.
- Full House terminal claim completes the game and writes safe history.
- Auto-caller can start, pause, resume, switch back to manual, and stop on terminal completion.
- Auto-caller pauses when organizer disconnects.

Frontend unit tests:

- Housie ticket component renders empty and filled cells with accessible labels.
- Marking a called cell toggles marked state.
- Claim buttons show available patterns and disabled/awarded states.
- Organizer caller screen disables undo when server says undo is blocked.
- Spectator screen renders latest call, called board, and winner announcements.
- Latest-call overlay appears on `BINGO_CALL` and clears after the animation.
- Winner announcement and confetti appear on accepted claims.
- Reduced-motion mode suppresses movement-heavy call/confetti animations.

Playwright tests:

- Standalone host creates a Housie room.
- Two players join, receive different tickets, and see the lobby.
- Host starts calling and both players see latest call updates.
- Player claim flow shows accepted/rejected feedback.
- Late/stale claims are rejected after another number has been called.
- Pro mode requires manual ticket marking and does not highlight called-but-unmarked ticket cells.
- Auto-caller can run several calls, pause, resume, and stop after Full House.
- Spectator/TV view can connect before and after calls begin.
- Mobile viewport ticket remains usable without horizontal overflow.

### Recommended PR Order

1. Pure engine only: `bingo_engine.py`, `housie_engine.py`, and backend engine tests.
2. Backend room runtime: add `housie` type, WebSocket events, state sync, claim validation, and history summary.
3. Frontend standalone setup and organizer caller surface.
4. Frontend player ticket and spectator called-board surfaces.
5. E2E polish: Beginner/Pro modes, auto-caller, latest-call animation, confetti/winner announcements, reconnect, accessibility, mobile layout, and Playwright coverage.
6. Catalog enablement for standalone.
7. Host-app/Revelry enablement in a later slice after standalone gamma testing.

## Implementation Plan

### Phase 0: Spec And Engine Shape

- Add this spec. Done.
- Add `housie` to standalone catalog metadata while keeping it hidden from host-app catalog until runtime contracts are complete. Done.
- Write pure engine tests for Housie ticket generation and claim validation. Done.

### Phase 1: Standalone Housie Runtime

- Add backend engine functions:
  - generate Housie deck.
  - generate ticket.
  - validate ticket shape through tests.
  - call next item through room runtime.
  - validate claims.
- Add runtime state to socket manager. Done.
- Add organizer caller screen. Done.
- Add player ticket screen. Done.
- Add spectator called-board screen. Done.
- Add game history summary. Done.

### Phase 2: Polish

- Beginner/Pro setup modes.
- Auto-caller mode with pause/resume, interval clamp, and disconnect pause.
- Last-called-number claim validation for every pattern.
- Latest-call large-number animation.
- Confetti and named winner announcements on all surfaces.
- Claim queue animations and announcements.
- Better TV called-board layout.
- Player reconnect restores ticket.
- Accessibility pass for marked cells and color contrast.
- Durable standalone saved Housie templates.
- Voice/audio number calls and better caller announcements.

### Phase 3: Bingo Family Expansion

- Add generic word/emoji deck support.
- Add Baby Bingo setup templates.
- Add AI-generated word/prompt decks.
- Add image-cell support using IONOS media and `SPEC-IMAGE-GAMES.md`.

### Phase 4: Host-App / Revelry Enablement

- Add host-app catalog metadata.
- Add party-scoped setup/save/start path.
- Add safe result callbacks.
- Add e2e tests for host/cohost/guest hub roles.
- Gamma test through Revelry before enabling production.

## Acceptance Criteria

Housie v1 is launch-ready when:

- Generated tickets always satisfy the configured layout and 15-cell constraints.
- Numbers are valid, unique, sorted within columns, and within configured ranges.
- Host can call numbers manually.
- Auto-caller can pause/resume.
- Creator can choose Beginner or Pro mode before starting.
- Beginner mode preserves assisted ticket marking/called-number hints.
- Pro mode hides called-number assistance from the player ticket and relies on manual marking.
- Players can mark tickets.
- Invalid claims are rejected with clear feedback.
- Claims are accepted only when the prize match occurred on the latest called number.
- Valid claims are accepted and announced.
- Latest called number appears as a large transient visual on all active surfaces.
- Accepted prizes trigger confetti and announce the winner name and prize on all active surfaces.
- A pattern cannot be awarded more than configured `max_winners`.
- Spectator can join mid-game and see current state.
- Results summarize winners without leaking tickets or hidden deck state.
- Standalone UX works on desktop and mobile.
- Tests cover ticket generation, claim validation, socket flow, and spectator sync.

## Open Questions

- Should LocalPlay support a "free" or decorative cell in any future Bingo-family display, or should every visible cell always be part of the game board?
- Should ties after the same call share a prize or should first valid server claim win?
- Should players be allowed multiple tickets in v1?
- Should host be able to manually approve/reject claims, or should server validation be authoritative?
- Should the spectator screen reveal the full called board only, or also show near-claims to create drama?
- Should Baby Bingo use a 5x5 Bingo grid by default or reuse the Housie 3-row ticket shape?
