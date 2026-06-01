# LocalPlay Bingo / Housie Game Spec

## Overview

Add a reusable **Bingo-family engine** to LocalPlay, with **Housie** as the first full game and configurable Bingo as the first generic Bingo ruleset.

Housie, also known as Tambola, is a caller-led number game. Each player receives a ticket with 3 rows, usually arranged into number columns covering 1 through 90. Exactly 15 cells are filled. Numbers are called one by one by the host/caller, either manually or with auto-caller mode. Players mark matching numbers on their tickets and claim prizes such as Quick 5, Corners, Top Row, Middle Row, Bottom Row, and Full House.

This spec deliberately treats Housie as the first ruleset on top of a broader Bingo engine. Bingo variants such as Baby Bingo, Wedding Bingo, Holiday Bingo, Emoji Bingo, Image Bingo, Photo Bingo, Word Bingo, and Find Someone Who should reuse the same card/layout/pattern model where practical, with different completion mechanics and theme packs.

```text
Engine family: bingo
First game type: housie
Implemented sibling ruleset: bingo
Next game types/rulesets: baby_bingo, word_bingo, emoji_bingo, image_bingo, photo_bingo, find_someone_who
Backend engine: bingo_engine.py / housie_engine.py / bingo_content_engine.py
Frontend display names: Housie, Bingo
```

## Current Implementation Status

Standalone Housie and configurable Bingo are implemented on the Bingo-family runtime:

- `backend/bingo_engine.py` provides reusable deck/item helpers for numeric, text, emoji, and image-capable Bingo deck items.
- `backend/bingo_content_engine.py` normalizes configurable Bingo setup payloads, validates deck size/item fields, sanitizes text/image metadata, and creates 5x5 cards with optional free center.
- `backend/housie_engine.py` generates classic 3x9 / 15-number Housie tickets, creates the 1-90 call deck, and validates Quick 5, Four Corners, Top/Middle/Bottom Row, and Full House claims.
- `backend/socket_manager.py` has a dedicated `BINGO_CALLING` runtime path. Housie/Bingo do not overload quiz `QUESTION` rounds.
- Standalone catalog shows Housie, Bingo, and Baby Bingo. `GET /catalog?host_app=revelry` exposes Housie on gamma after host-app policy allows it; generic Bingo/Baby Bingo remain standalone-only until their Revelry bridge contract is promoted.
- Organizer can create a Housie setup, create a room, start with at least two players, call/undo numbers, view the called board, and end the game.
- Organizer can choose Beginner/Pro mode, manual/auto caller mode, configurable auto interval, and auto-pause-on-claim behavior.
- Players receive server-generated tickets, mark cells locally, submit prize claims, and see accepted claims.
- Spectator/TV receives current called numbers, latest number, and winners through `SPECTATOR_SYNC` / `BINGO_*` messages.
- Housie claim validation enforces the Tambola last-number rule: the prize must first become true on the latest called number.
- Bingo setup supports template/manual/AI-text deck creation in standalone LocalPlay. The MVP supports text, emoji, number, and image-shaped deck items in the schema; image deck items require media-backed `asset_id`, `public_url`, `display`, and `alt_text` before they can be saved/started.
- Bingo AI generation is a host-reviewed setup helper: the host gives a theme/prompt, LocalPlay generates editable deck items, and the deck is not live until the host reviews and saves/starts.
- Housie is available in the Revelry gamma party hub as a party-scoped setup with default prizes: Quick 5, Four Corners, Top Row, Middle Row, Bottom Row, and Full House. Housie uses `generated_content` with `content_type = housie` in gamma Supabase.
- `ROOM_RESET`/play-again keeps the same room code but now uses the shared all-games socket cleanup rule: dead player sockets discovered during reset broadcasts, runtime syncs, or pre-start probes are removed and followed by an updated roster. This prevents stale lobby counts such as "2 players" when those players are actually still on an old completed-results screen or have disconnected.
- Housie/Bingo start gates prune dead player sockets before checking `MIN_HOUSIE_PLAYERS` / `MIN_BINGO_PLAYERS`, so stale roster entries cannot either block a valid start or allow a start with too few live players.

Known v1 limitations:

- Latest-call and winner announcement animations exist, but need a final visual polish pass across organizer, player, and spectator screens.
- Housie setup is still in-memory for standalone room creation; Revelry gamma Housie setup is persisted party-scoped through `generated_content`.
- Generic Bingo and Baby Bingo are implemented for standalone/gamma UX first. They are not exposed to Revelry yet.
- Word Bingo, Emoji Bingo, Image Bingo, Photo Bingo, and Find Someone Who remain future named rulesets on the same card/layout foundation.
- Image Bingo has schema and validation requirements, but the full media upload / AI image generation authoring path remains a later slice.

## Goals

- Add a generic Bingo-family runtime that can support numbers, words, emojis, and images.
- Ship Housie as the first implementation using classic 1-90 tickets.
- Ship configurable Bingo after Housie: classic 5x5 text Bingo first, then Baby/Event Bingo, Emoji Bingo, Image Bingo, and Photo Bingo.
- Let creators choose from ready-made templates, enter a prompt for AI-generated deck items, manually edit deck items, upload images, or ask AI to generate images for image Bingo.
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
- Make image-based Bingo reuse the shared media layer and image safety rules from `SPEC-IMAGE-GAMES.md`.
- Support standalone LocalPlay first; expose individual games to Revelry only after their catalog, setup, runtime, result-summary, and regression tests are bridge-ready.

## Constraints

- Minimum players: 2. Housie is a group game; a single player can technically mark and claim but the experience is meaningless.
- Enforce the minimum when the host starts calling, not when the room is created or when a player joins. This keeps setup and TV testing possible while still preventing a one-person live game.
- Maximum players: same as `MAX_PLAYERS_PER_ROOM` (100 by default at the time of this spec). Each player receives one ticket in v1; multi-ticket support is a future option.

## Non-Goals

- No gambling, real-money prizes, betting, or cash-out mechanics.
- No randomized paid ticket sales.
- No player-submitted images in Housie v1. Image Bingo may allow host-uploaded or AI-generated deck images in the Bingo expansion slice.
- No automatic optical/voice recognition of calls.
- No multi-room tournaments in v1.
- No real-time persistence beyond the current LocalPlay room model in v1.
- No Revelry/host-app launch for a Bingo-family ruleset until that ruleset's catalog, setup, runtime, and result summary contracts are implemented and tested. Housie satisfies this for gamma; generic Bingo does not yet.

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

### Configurable Bingo Rulesets

Generic Bingo should be a sibling ruleset to Housie, not a forked runtime. It should use the same WebSocket room lifecycle, claim model, auto-caller controls, latest-call animation, confetti, result summaries, and host-app policy.

Recommended game types:

| Game type | Display name | Content | Default layout | Primary creation modes |
|---|---|---|---|---|
| `bingo` | Bingo | Words, short phrases, or numbers | 5x5 with optional free center | template, manual, AI prompt |
| `baby_bingo` | Baby Bingo | Baby gifts, baby items, shower phrases, predictions | 5x5 with optional free center | template, AI prompt |
| `word_bingo` | Word Bingo | Words or short phrases from a creator prompt | 5x5 with optional free center | manual, AI prompt |
| `emoji_bingo` | Emoji Bingo | Emoji plus short labels for accessibility | 5x5 with optional free center | template, AI prompt |
| `image_bingo` | Image Bingo | Host-uploaded or AI-generated images with labels | 4x4 or 5x5 | upload, AI image generation |
| `photo_bingo` | Photo Bingo | Host-uploaded party/event photos or image prompts | 4x4 or 5x5 | upload, AI image generation |
| `find_someone_who` | Find Someone Who | Social prompts completed by matching real people in the room | 5x5 with optional free center | template, manual, AI prompt |

Product guidance:

- `housie` remains the classic 90-ball/Tambola experience with 3x9 tickets and latest-called-number claim validation.
- `bingo`, `baby_bingo`, `word_bingo`, `emoji_bingo`, `image_bingo`, and `photo_bingo` use a standard caller-led Bingo card model where the called item can be text, emoji, or an image.
- `find_someone_who` reuses Bingo-style card layout and claim patterns but is not caller-led; cells are marked by finding and optionally confirming real people who match prompts. Its implementation-ready spec is `SPEC-GAME-FIND-SOMEONE-WHO.md`.
- The default non-Housie card is 5x5 with a free center. Image-heavy games may default to 4x4 for readability on phones.
- The host should be able to choose a creation path:
  - **Ready-made**: built-in themed template.
  - **Write my own**: manual deck item editor.
  - **AI prompt**: prompt-based text/emoji deck generation.
  - **Upload images**: host uploads image deck items.
  - **AI images**: AI generates image deck items from a prompt.
- The generated deck is editable before saving or starting. AI output must never go straight into a live game without host review.
- Saved Bingo setups should be reusable like WMLT/Drawing setups and future host-app party games.

### Generic Bingo Card Shape

Generic Bingo card payload:

```ts
type BingoCard = {
  card_id: string;
  player_id: string;
  layout: {
    rows: 4 | 5;
    columns: 4 | 5;
    free_center: boolean;
  };
  cells: Array<Array<BingoCell | null>>;
};

type BingoCell =
  | { kind: "number"; item_id: string; value: number; display: string; row: number; column: number; marked: boolean }
  | { kind: "word"; item_id: string; value: string; display: string; row: number; column: number; marked: boolean }
  | { kind: "emoji"; item_id: string; value: string; display: string; label: string; row: number; column: number; marked: boolean }
  | { kind: "image"; item_id: string; asset_id: string; public_url: string; alt_text: string; display: string; row: number; column: number; marked: boolean }
  | { kind: "free"; value: "free"; display: "FREE"; row: number; column: number; marked: true };
```

Generic card generation:

- The setup deck must contain enough unique playable items for the card:
  - 5x5 with free center: at least 24 unique items.
  - 5x5 without free center: at least 25 unique items.
  - 4x4: at least 16 unique items.
- Each player receives a shuffled card sampled without replacement from the setup deck.
- Cards should be unique within a room by stable hash of cell item ids/values and positions.
- Free center, if enabled, is marked from the start and does not appear in the call deck.
- The call deck contains all setup items, shuffled without replacement. It may include more items than fit on any one player's card.

### Generic Bingo Prize Patterns

Generic Bingo should support these prize patterns:

| Pattern | Meaning |
|---|---|
| `first_line` | Any complete row, column, or diagonal |
| `two_lines` | Any two complete rows/columns/diagonals |
| `four_corners` | Four literal corner cells are marked |
| `postage_stamp` | Any 2x2 corner block is marked |
| `blackout` | Every non-free cell is marked |
| `custom_pattern` | Future named shape from template/config |

Unlike Housie, generic Bingo does not need the "latest number made the prize true" rule by default. It should have a room setting:

```json
{
  "claim_requires_latest_call": false
}
```

If a host chooses classic strict validation, generic Bingo may set `claim_requires_latest_call = true` and reuse the same before/after latest-call validation pattern.

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

- Game type/ruleset: `bingo`, `baby_bingo`, `word_bingo`, `emoji_bingo`, `image_bingo`, or `photo_bingo`.
- Game title.
- Board/card layout.
- Free center toggle.
- Content source:
  - built-in template.
  - manual word/emoji list.
  - AI-generated list.
  - AI-generated image set.
  - uploaded image set.
- Minimum deck size.
- Prize patterns.
- Caller mode and auto-caller settings.
- Claim rule: `claim_requires_latest_call`.
- Theme/party type.
- Media safety settings.

### Creator Setup Flow For Bingo Variants

The creator setup should be a single Bingo setup surface that adapts by selected content type.

Step 1: Choose Bingo type:

- Classic Bingo.
- Baby Bingo.
- Word/Phrase Bingo.
- Emoji Bingo.
- Image Bingo.
- Photo Bingo.

Step 2: Choose how to fill the board:

- **Use a template**: select from built-in safe templates.
- **Write my own**: edit deck items directly.
- **Use AI prompt**: enter a prompt/theme such as "Ava's baby shower gifts", "wedding reception moments", or "office holiday party inside jokes".
- **Upload images**: upload image items and labels.
- **Generate AI images**: enter a prompt/theme and choose image style/count.

Step 3: Review and edit:

- The host sees all generated/uploaded deck items before saving.
- Text/emoji items can be edited inline.
- Image items must show thumbnail, label, alt text, and delete/regenerate actions.
- The setup cannot be saved until it has the minimum unique playable items for the chosen layout.

Step 4: Save or start:

- **Save** creates a reusable `content_id`.
- **Save and start** creates or updates the setup, then opens the room/lobby.
- **Start without saving** may be allowed in standalone mode only if the setup is still materialized into a temporary `content_id` for room reset/history.

### AI Text / Emoji Deck Generation

Endpoint shape:

```http
POST /bingo/generate-items
```

Request:

```json
{
  "game_type": "baby_bingo",
  "prompt": "Ava's baby shower with forest animals theme",
  "item_kind": "word" | "emoji",
  "count": 40,
  "vibe": "family" | "party" | "work" | "spicy",
  "party_type": "baby_shower"
}
```

Response:

```json
{
  "items": [
    { "kind": "word", "value": "Diaper cake", "display": "Diaper cake" },
    { "kind": "emoji", "value": "🍼", "display": "🍼", "label": "Baby bottle" }
  ],
  "warnings": []
}
```

Rules:

- Generate at least the requested count when possible; require a minimum of 24 usable items for a 5x5 free-center card.
- Deduplicate case-insensitively and by normalized emoji label.
- Keep item text short enough to fit in card cells, recommended 1-4 words and max 32 visible characters.
- Return family-safe content by default. Spicy/adult content must be opt-in and unavailable in host-app contexts unless the host-app capabilities allow it.
- The endpoint should return structured items only, not raw provider output.

### AI Image Deck Generation

Endpoint shape:

```http
POST /bingo/generate-images
```

Request:

```json
{
  "game_type": "image_bingo",
  "prompt": "cute woodland baby shower objects",
  "count": 24,
  "style": "sticker" | "photo" | "illustration" | "icon",
  "aspect_ratio": "1:1",
  "labels_required": true
}
```

Response:

```json
{
  "items": [
    {
      "kind": "image",
      "asset_id": "media_abc123",
      "public_url": "/media/media_abc123",
      "display": "Fox plushie",
      "alt_text": "Cute fox plush toy in a woodland baby shower style"
    }
  ],
  "warnings": []
}
```

Rules:

- Use the shared media layer from `SPEC-IMAGE-GAMES.md`; do not store image bytes in the Bingo setup payload.
- Every image item must have `asset_id`, safe public URL, display label, and alt text.
- The image generator should produce square, card-friendly images by default.
- The host must review images before saving or starting.
- Failed or unsafe image generations should be returned as warnings and omitted from the item list.
- The setup editor should allow regenerating one image item, regenerating all, deleting an item, or replacing it with an upload.
- Host-uploaded images use the existing `/media/upload-url` flow and then become `kind = "image"` Bingo items.

### Baby Bingo

Baby Bingo should be a ruleset on the same engine:

- Game type: `baby_bingo`.
- Deck items: baby shower gifts, baby items, predictions, phrases, or emojis.
- Card layout: likely 5x5 or configurable.
- Center free square optional.
- AI prompt generation from party context should be supported before Revelry launch.
- Image cells should use the shared media layer from `SPEC-IMAGE-GAMES.md`.

## Persistence

v1 can keep live room state process-local like the current room runtime, but setup/content should be durable when saved.

Recommended durable objects:

- Bingo setup/template:
  - `content_id`
  - `game_type`
  - `engine_family`
  - `title`
  - `item_kind`: `number`, `word`, `emoji`, or `image`
  - `deck_config`
  - `deck_items`: normalized playable items, with stable `item_id` values
  - `layout_config`
  - `patterns`
  - `caller_settings`
  - `claim_requires_latest_call`
  - `generation_config`: source prompt, template id, provider metadata, and warnings
  - `media_asset_ids`: ids for uploaded or generated images
  - ownership scope
- Game history summary:
  - called count.
  - winners by pattern.
  - player count.
  - duration.
  - safe title.

Do not persist raw per-player ticket state in feed/result summaries unless needed for recovery and explicitly safe.

For host-app mode, saved content should use the existing party-scoped saved content model where possible. If the current generic `generated_content` payload becomes too loose for Bingo, add typed schema validation before enabling host-app launch.

Generic Bingo setup payload shape:

```json
{
  "content_id": "bingo_abc123",
  "game_type": "image_bingo",
  "engine_family": "bingo",
  "title": "Woodland Baby Shower Bingo",
  "item_kind": "image",
  "layout_config": {
    "rows": 5,
    "columns": 5,
    "free_center": true
  },
  "deck_items": [
    {
      "item_id": "item_fox_plushie",
      "kind": "image",
      "asset_id": "media_abc123",
      "public_url": "/media/media_abc123",
      "display": "Fox plushie",
      "alt_text": "Cute fox plush toy in woodland baby shower style"
    }
  ],
  "patterns": [
    { "id": "first_line", "label": "First Line", "max_winners": 1 },
    { "id": "blackout", "label": "Blackout", "max_winners": 1, "terminal": true }
  ],
  "caller_settings": {
    "caller_mode": "manual",
    "auto_interval_seconds": 8,
    "auto_pause_on_claim": true
  },
  "claim_requires_latest_call": false,
  "generation_config": {
    "source": "ai_images",
    "prompt": "cute woodland baby shower objects",
    "style": "sticker",
    "warnings": []
  },
  "media_asset_ids": ["media_abc123"],
  "ownership_scope": {
    "mode": "standalone",
    "owner_user_id": "user_123"
  }
}
```

Persistence rules:

- Do not persist a shuffled live call order in saved setup content. Shuffle the call deck when a room starts or resets.
- Do not persist raw generated image bytes in setup payloads. Store only media ids/URLs from the shared media layer.
- Store labels and alt text for image items because those are part of gameplay and accessibility.
- Normalize item ids once at save time. Player card hashes and claim validation should use stable item ids, not display text alone.
- Keep AI prompt/provider metadata in setup history for host review and debugging, but do not show provider internals to players.

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

Planned standalone catalog entries for Bingo-family expansion:

```json
[
  {
    "id": "bingo",
    "game_type": "bingo",
    "engine_family": "bingo",
    "title": "Bingo",
    "description": "Classic 5x5 Bingo with words, phrases, numbers, or templates.",
    "status": "planned",
    "launchable": false,
    "supports_manual_authoring": true,
    "supports_ai_generation": true,
    "requires_content": true,
    "can_create_content": true,
    "can_quick_start": false,
    "supported_media": ["none"],
    "content_schema": "bingo_setup_v2",
    "result_summary_schema": "bingo_result_v2"
  },
  {
    "id": "baby_bingo",
    "game_type": "baby_bingo",
    "engine_family": "bingo",
    "title": "Baby Bingo",
    "description": "Baby shower Bingo using gifts, predictions, phrases, emojis, or images.",
    "status": "planned",
    "launchable": false,
    "supports_manual_authoring": true,
    "supports_ai_generation": true,
    "requires_content": true,
    "can_create_content": true,
    "can_quick_start": true,
    "supported_media": ["none", "image"],
    "content_schema": "bingo_setup_v2",
    "result_summary_schema": "bingo_result_v2"
  },
  {
    "id": "word_bingo",
    "game_type": "word_bingo",
    "engine_family": "bingo",
    "title": "Word Bingo",
    "description": "Prompt-generated or creator-written word and phrase Bingo.",
    "status": "planned",
    "launchable": false,
    "supports_manual_authoring": true,
    "supports_ai_generation": true,
    "requires_content": true,
    "can_create_content": true,
    "can_quick_start": false,
    "supported_media": ["none"],
    "content_schema": "bingo_setup_v2",
    "result_summary_schema": "bingo_result_v2"
  },
  {
    "id": "emoji_bingo",
    "game_type": "emoji_bingo",
    "engine_family": "bingo",
    "title": "Emoji Bingo",
    "description": "Emoji Bingo with accessible labels and editable themed decks.",
    "status": "planned",
    "launchable": false,
    "supports_manual_authoring": true,
    "supports_ai_generation": true,
    "requires_content": true,
    "can_create_content": true,
    "can_quick_start": true,
    "supported_media": ["none"],
    "content_schema": "bingo_setup_v2",
    "result_summary_schema": "bingo_result_v2"
  },
  {
    "id": "image_bingo",
    "game_type": "image_bingo",
    "engine_family": "bingo",
    "title": "Image Bingo",
    "description": "Bingo with host-uploaded or AI-generated image cells.",
    "status": "planned",
    "launchable": false,
    "supports_manual_authoring": true,
    "supports_ai_generation": true,
    "requires_content": true,
    "can_create_content": true,
    "can_quick_start": false,
    "supported_media": ["image"],
    "content_schema": "bingo_setup_v2",
    "result_summary_schema": "bingo_result_v2"
  },
  {
    "id": "photo_bingo",
    "game_type": "photo_bingo",
    "engine_family": "bingo",
    "title": "Photo Bingo",
    "description": "Bingo built from uploaded event photos or generated image prompts.",
    "status": "planned",
    "launchable": false,
    "supports_manual_authoring": true,
    "supports_ai_generation": true,
    "requires_content": true,
    "can_create_content": true,
    "can_quick_start": false,
    "supported_media": ["image"],
    "content_schema": "bingo_setup_v2",
    "result_summary_schema": "bingo_result_v2"
  }
]
```

Revelry/host-app catalog should keep a Bingo-family ruleset `launchable = false` until:

- standalone Housie runtime is playable.
- organizer/player/spectator routes work.
- safe result summaries are implemented.
- host-app chrome and share policies are applied.
- party-scoped setup save/start is tested.
- callbacks include safe `game.session_created`, `game.started`, and `game.completed` summaries.

Housie has met this threshold for gamma and may be returned by `GET /catalog?host_app=revelry` with `status = "gamma"`. Generic Bingo and named variants such as Baby Bingo remain hidden from Revelry until their own bridge tests pass.

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

Housie is enabled for Revelry gamma through the party hub:

- The Revelry Games hub shows Housie from `GET /catalog?host_app=revelry`.
- Host/cohost can set up Housie with default prize patterns or quick-start a default Housie room.
- Guests see join/watch only.
- Runtime hides sparks/wallet/paywall/account/library chrome in host-app mode.
- QR/share uses Revelry-owned join URLs when provided.
- Results callback posts safe winner/prize summaries.
- Party type can influence templates later, such as holiday Housie or baby shower Bingo.
- Housie content saves through `POST /integrations/revelry/party-games/content` use:

```json
{
  "party_games_token": "...",
  "game_type": "housie",
  "title": "Housie",
  "status": "ready",
  "content_payload": {
    "game": {
      "game_title": "Housie",
      "pattern_ids": ["quick_5", "four_corners", "top_row", "middle_row", "bottom_row", "full_house"],
      "play_mode": "beginner",
      "caller_mode": "manual",
      "auto_interval_seconds": 8,
      "auto_pause_on_claim": true
    }
  }
}
```

- Saved Housie summaries treat `question_count` / `item_count` as prize-pattern count, not questions.
- Housie has `supports_ai_generation = false`; the Revelry hub hides AI prompt generation for it.
- Housie launch/start uses the same party-games start endpoint as other games with `game_type = "housie"` and optional `content_id`.
- The gamma Supabase table `games_gamma_generated_content` must allow `content_type = 'housie'`; production remains unchanged until promotion.
- Generic Bingo remains standalone-only in host-app policy. Do not expose `bingo` to Revelry until party-scoped setup save/start, result summaries, and E2E coverage are complete.

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
  - Generic card generation for 4x4/5x5 word, emoji, and image Bingo.
  - Generic pattern validation for lines, corners, postage stamp, blackout, and configured custom shapes.
- `backend/housie_engine.py`
  - Housie-specific ticket generation, default pattern definitions, and claim validation.
  - May import shared types/helpers from `bingo_engine.py`.
  - Enforce the latest-called-number rule for every claim.
- `backend/bingo_content_engine.py`
  - Normalize and validate Bingo setup payloads.
  - Validate deck item counts, uniqueness, labels, alt text, media ids, and layout constraints.
  - Build prompt requests for text/emoji deck generation and image deck generation.
  - Sanitize provider responses into `BingoItem` records.
  - Produce template decks for classic, baby, holiday, wedding, emoji, and office Bingo.
- `backend/socket_manager.py`
  - Add `housie` runtime branch to `Room`.
  - Add Housie state reset, sync, call, claim, auto-caller, completion, and history behavior.
  - Keep field names generic enough for later `bingo`/`image_bingo` runtime reuse.
  - Sync generic Bingo card state without leaking hidden call order.
- `backend/main.py`
  - Accept `game_type = "housie"` in room creation validation.
  - Add optional `housie_id` or generic `content_id` handling for saved/default Housie setup.
  - Add catalog metadata for standalone Housie as disabled/planned until runtime is implemented.
  - Add `/housie/default` or equivalent only if the frontend needs a setup preview endpoint; otherwise create content directly at room creation.
  - Add `/bingo/create`, `/bingo/{content_id}`, `/bingo/generate-items`, and `/bingo/generate-images` when implementing the Bingo-family expansion.
  - Extend `API_PREFIXES` in the backend static-serving fallback if `/bingo` is added as a new top-level route.
- `backend/config.py`
  - Add `MIN_HOUSIE_PLAYERS = 2`.
  - Reuse `MAX_PLAYERS_PER_ROOM`.
- `backend/tests/test_housie_engine.py`
  - Pure engine tests.
- `backend/tests/test_bingo_engine.py`
  - Generic card generation and pattern validation tests.
- `backend/tests/test_bingo_content_engine.py`
  - Setup validation, item normalization, template loading, prompt generation, and AI response sanitization tests.
- `backend/tests/test_bingo_api.py`
  - Create/update/get setup endpoints plus text/image generation endpoints with mocked providers.
- `backend/tests/test_housie_ws.py` or existing WebSocket flow tests
  - Runtime/caller/claim/spectator tests.

Do not add Supabase schema in v1 unless durable saved Housie setups require a new typed table. Prefer the existing generated content model for initial saved setup payloads if it is sufficient.

### Frontend Files

Add or update:

- `frontend/src/types.ts`
  - Add `housie` to `GameType`.
  - Add shared Bingo/Housie types if used across surfaces.
  - Add `BingoSetup`, `BingoDeckItem`, `BingoLayoutConfig`, `BingoGenerationConfig`, `BingoCard`, `BingoCell`, and `BingoPattern`.
- `frontend/src/gameModes.ts`
  - Add a Housie catalog config with `runtimeType: "housie"` after `runtimeType` supports it.
  - Add planned catalog configs for `bingo`, `baby_bingo`, `word_bingo`, `emoji_bingo`, `image_bingo`, and `photo_bingo` once their setup flow exists.
- `frontend/src/pages/OrganizerPage.tsx`
  - Add Housie setup entry point.
  - Add caller runtime branch once room is created.
- `frontend/src/pages/PlayerPage.tsx`
  - Add player ticket runtime branch.
- `frontend/src/pages/SpectatorPage.tsx`
  - Add Housie spectator/called-board branch.
- `frontend/src/components/organizer/HousieSetupScreen.tsx`
  - Standalone setup: title, Beginner/Pro mode, caller mode, interval, auto-pause-on-claim, prize toggles.
- `frontend/src/components/organizer/BingoSetupScreen.tsx`
  - Generic Bingo setup: ruleset/type picker, layout controls, free center toggle, creation mode picker, AI prompt form, save/start actions.
- `frontend/src/components/bingo/BingoDeckEditor.tsx`
  - Text/emoji item editor with add, delete, reorder, dedupe warnings, and minimum-count validation.
- `frontend/src/components/bingo/BingoImageDeckEditor.tsx`
  - Image thumbnail grid with label/alt editing, upload, regenerate one, regenerate all, delete, and safety warnings.
- `frontend/src/components/bingo/BingoCardGrid.tsx`
  - Shared 4x4/5x5 player card renderer for word, emoji, image, and free cells.
- `frontend/src/components/bingo/BingoCallerScreen.tsx`
  - Generic caller UI for non-Housie Bingo, sharing auto-caller controls, latest-call animation, and winner announcements.
- `frontend/src/components/bingo/BingoSpectatorScreen.tsx`
  - TV/spectator surface for generic Bingo call history, latest item, winners, and confetti.
- `frontend/src/components/organizer/HousieCallerScreen.tsx`
  - Organizer/caller runtime controls, auto-caller status, and latest-call animation.
- `frontend/src/components/player/HousieTicket.tsx`
  - Player ticket grid and claim buttons. Rendering must respect Beginner vs Pro assistance rules.
- `frontend/src/components/spectator/HousieSpectatorScreen.tsx`
  - TV/spectator latest call, called board, winner announcements, and confetti.
- `frontend/src/components/housie/`
  - Optional shared visual pieces: ticket grid, called board, prize badge, latest call overlay, confetti layer.

Keep Housie UI components shared between standalone and future host-app mode. Host-app behavior should be props/context policy, not a forked UI.

Image Bingo UI requirements:

- Image cells must use stable square aspect-ratio boxes so card layout does not shift while images load.
- Every image has a visible short label and an accessible alt label.
- Broken/missing image URLs render a neutral fallback tile with the text label.
- The setup editor must block save/start if any image item is missing an asset id, public URL, display label, or alt text.
- AI generation and upload states must be cancellable or safely retryable from the setup editor.

### TypeScript Runtime Types

Add these types or close equivalents:

```ts
export type BingoItem =
  | { kind: "number"; item_id: string; value: number; display: string }
  | { kind: "word"; item_id: string; value: string; display: string }
  | { kind: "emoji"; item_id: string; value: string; display: string; label: string }
  | { kind: "image"; item_id: string; asset_id: string; public_url: string; alt_text: string; display: string };

export type BingoCell =
  | {
      kind: "number";
      item_id: string;
      value: number;
      display: string;
      row: number;
      column: number;
      marked: boolean;
    }
  | {
      kind: "word" | "emoji";
      item_id: string;
      value: string;
      display: string;
      label?: string;
      row: number;
      column: number;
      marked: boolean;
    }
  | {
      kind: "image";
      item_id: string;
      asset_id: string;
      public_url: string;
      alt_text: string;
      display: string;
      row: number;
      column: number;
      marked: boolean;
    }
  | {
      kind: "free";
      value: "free";
      display: "FREE";
      row: number;
      column: number;
      marked: true;
    };

export interface BingoLayoutConfig {
  rows: 4 | 5;
  columns: 4 | 5;
  free_center: boolean;
}

export interface BingoGenerationConfig {
  source: "template" | "manual" | "ai_text" | "ai_emoji" | "upload" | "ai_images";
  template_id?: string;
  prompt?: string;
  style?: "sticker" | "photo" | "illustration" | "icon";
  warnings?: string[];
}

export interface BingoSetup {
  content_id: string;
  game_type: "bingo" | "baby_bingo" | "word_bingo" | "emoji_bingo" | "image_bingo" | "photo_bingo";
  engine_family: "bingo";
  title: string;
  item_kind: "number" | "word" | "emoji" | "image";
  layout_config: BingoLayoutConfig;
  deck_items: BingoItem[];
  patterns: BingoPattern[];
  caller_settings: {
    caller_mode: "manual" | "auto";
    auto_interval_seconds: number;
    auto_pause_on_claim: boolean;
  };
  claim_requires_latest_call: boolean;
  generation_config: BingoGenerationConfig;
}

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
def validate_bingo_setup(setup: dict) -> tuple[bool, list[str]]: ...
def generate_bingo_card(setup: dict, player_id: str, rng: random.Random | None = None) -> dict: ...
def validate_bingo_claim(card: dict, pattern_id: str, called_items: list[dict], latest_item: dict | None, awarded_patterns: dict[str, list[dict]], claim_requires_latest_call: bool = False) -> tuple[bool, str]: ...
def called_value_set(called_items: list[dict]) -> set[str | int]: ...
def count_markable_items(ticket: dict, called_values: set[str | int]) -> int: ...
```

### Bingo REST API Contracts

These endpoints are for standalone LocalPlay first. Host-app/Revelry can call them later through party-scoped wrappers once authorization, capabilities, and callbacks are complete.

#### Create Bingo Setup

```http
POST /bingo/create
```

Request:

```json
{
  "game_type": "image_bingo",
  "title": "Woodland Baby Shower Bingo",
  "layout_config": { "rows": 5, "columns": 5, "free_center": true },
  "deck_items": [],
  "patterns": ["first_line", "blackout"],
  "caller_settings": {
    "caller_mode": "manual",
    "auto_interval_seconds": 8,
    "auto_pause_on_claim": true
  },
  "claim_requires_latest_call": false,
  "generation_config": {
    "source": "ai_images",
    "prompt": "cute woodland baby shower objects"
  }
}
```

Response:

```json
{
  "content_id": "bingo_abc123",
  "setup": {}
}
```

Server behavior:

- Validate game type, item kind, layout, deck minimum, labels, image media references, patterns, and caller settings.
- Normalize item ids and text before storing.
- Reject unsupported host-app contexts unless the caller has a capability such as `party_games` and `ai_bingo_generation`.
- Return machine-readable validation errors so the editor can highlight individual deck items.

#### Update Bingo Setup

```http
PUT /bingo/{content_id}
```

Rules:

- Only the owner or host-app party scope may update the setup.
- Existing running rooms should not silently mutate. Changes apply to future rooms unless the room is still in setup/lobby and explicitly reloads the setup.
- Removing image items should not immediately delete media assets; media cleanup follows shared retention policy.

#### Fetch Bingo Setup

```http
GET /bingo/{content_id}
```

Response includes the normalized setup but never includes hidden live call order, player cards, or private provider payloads.

#### Generate Text Or Emoji Items

```http
POST /bingo/generate-items
```

Use the AI Text / Emoji Deck Generation contract above.

#### Generate Image Items

```http
POST /bingo/generate-images
```

Use the AI Image Deck Generation contract above. This endpoint may internally call the shared media upload/storage layer after generation and must return media-backed Bingo items only.

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

Expose only Bingo-family rulesets whose host-app contract is complete. Housie is gamma-enabled for Revelry; generic Bingo remains standalone-only. Standalone catalog can show Housie/Bingo when playable.

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

Generic Bingo engine/content tests:

- `validate_bingo_setup` accepts 5x5/free-center setups with 24 unique deck items.
- `validate_bingo_setup` rejects 5x5/no-free setups with fewer than 25 unique deck items.
- `validate_bingo_setup` rejects 4x4 setups with fewer than 16 unique deck items.
- `validate_bingo_setup` rejects duplicate normalized word/emoji items.
- `validate_bingo_setup` rejects image items missing `asset_id`, `public_url`, `display`, or `alt_text`.
- `generate_bingo_card` creates stable 4x4/5x5 layouts with correct free-center behavior.
- `generate_bingo_card` samples without replacement and keeps cards unique by hash within bounded retries.
- Generic `first_line`, `two_lines`, `four_corners`, `postage_stamp`, and `blackout` patterns validate correctly.
- Generic strict mode rejects claims where `claim_requires_latest_call = true` and the latest item did not complete the claimed pattern.
- Generic non-strict mode accepts complete claims even when the pattern became true on an earlier call.
- AI text generation sanitizes provider output, caps visible text length, dedupes, and returns warnings for unusable items.
- AI emoji generation requires accessible labels.
- AI image generation returns only media-backed image items and omits unsafe/failed generations with warnings.
- Template decks load with enough items for their default layout.

Backend API tests:

- `POST /bingo/create` stores a normalized word Bingo setup and returns a `content_id`.
- `POST /bingo/create` stores a normalized image Bingo setup with media references.
- `POST /bingo/create` rejects unsupported game types, malformed layouts, empty patterns, and insufficient deck size.
- `PUT /bingo/{content_id}` updates only owner-scoped setup content.
- `GET /bingo/{content_id}` returns safe setup payload without hidden live state.
- `POST /bingo/generate-items` uses mocked AI provider output and returns sanitized items.
- `POST /bingo/generate-images` uses mocked image generation/media storage and returns media-backed image items.
- Host-app calls without required capabilities are rejected before paid or AI-only features are used.

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
- Generic Bingo rooms generate one card per player from the saved setup.
- Generic Bingo call deck includes setup items without repeating calls.
- Generic image Bingo sync payload includes only public media URLs and labels, not private storage paths.
- Generic Bingo accepted claims broadcast winner, pattern, and latest item metadata to organizer, players, and spectator.

Frontend unit tests:

- Housie ticket component renders empty and filled cells with accessible labels.
- Marking a called cell toggles marked state.
- Claim buttons show available patterns and disabled/awarded states.
- Organizer caller screen disables undo when server says undo is blocked.
- Spectator screen renders latest call, called board, and winner announcements.
- Latest-call overlay appears on `BINGO_CALL` and clears after the animation.
- Winner announcement and confetti appear on accepted claims.
- Reduced-motion mode suppresses movement-heavy call/confetti animations.
- Generic Bingo setup type picker switches between classic, baby, word, emoji, image, and photo flows.
- Text/emoji deck editor blocks save below minimum item count and highlights duplicates.
- Image deck editor blocks save when thumbnail items lack label or alt text.
- Image cells keep square dimensions while loading and fall back cleanly on broken images.
- AI text/image generation loading, warning, retry, and review states render without layout shift.
- Generic Bingo card grid renders free center, text, emoji, and image cells with accessible labels.

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
- Standalone host creates a Word Bingo setup from manual items, starts a room, and players receive cards.
- Standalone host creates an Image Bingo setup from mocked media items, starts a room, and image cells render.
- AI prompt generation flow returns editable items before save/start.
- AI image generation flow returns editable thumbnails before save/start.
- Generic Bingo player can claim First Line and Blackout.
- Generic Bingo spectator sees image/word latest-call visuals and winner confetti.

### Recommended PR Order

1. Pure engine only: `bingo_engine.py`, `housie_engine.py`, and backend engine tests.
2. Backend room runtime: add `housie` type, WebSocket events, state sync, claim validation, and history summary.
3. Frontend standalone setup and organizer caller surface.
4. Frontend player ticket and spectator called-board surfaces.
5. E2E polish: Beginner/Pro modes, auto-caller, latest-call animation, confetti/winner announcements, reconnect, accessibility, mobile layout, and Playwright coverage.
6. Catalog enablement for standalone.
7. Generic Bingo setup/content engine: text, emoji, templates, card generation, and validation.
8. Generic Bingo standalone runtime: player cards, caller surface, spectator surface, and claims.
9. Image Bingo media slice: upload flow, image card rendering, media-backed setup persistence, and safety validation.
10. AI Bingo generation slice: text/emoji prompts first, then AI image generation with review/edit.
11. Housie host-app/Revelry gamma enablement. Done.
12. Generic Bingo host-app/Revelry enablement in a later slice after standalone gamma testing.

## Implementation Plan

### Phase 0: Spec And Engine Shape

- Add this spec. Done.
- Add `housie` to standalone catalog metadata. Done.
- Add `housie` to Revelry gamma host-app catalog after party-scoped setup/save/start and E2E coverage. Done.
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

Phase 3A: Generic text/emoji Bingo setup and engine:

- Add `bingo_content_engine.py` setup validation and item normalization.
- Add 4x4/5x5 generic card generation with optional free center.
- Add generic pattern validation for line, two lines, corners, postage stamp, and blackout.
- Add manual word/phrase and emoji deck editor.
- Add built-in templates for classic, baby, holiday, wedding, office, and emoji Bingo.
- Add standalone Bingo setup UI with template/manual/AI text generation and host-reviewed editable items. Done for the first configurable Bingo slice.
- Keep catalog entries planned/hidden until setup, runtime, and tests are complete.

Phase 3B: Generic Bingo standalone runtime:

- Reuse the Housie room state where possible through generic `bingo_*` fields.
- Add generic caller, player card, spectator, claim, latest-call, confetti, and result-summary handling.
- Add room creation by saved `content_id`.
- Add Playwright coverage for manual Word Bingo from setup through claim.

Phase 3C: Image Bingo upload support:

- Add media-backed `image` deck items.
- Add upload-based image deck editor with label and alt-text requirements.
- Add image card rendering, latest image call visuals, and spectator display.
- Add tests for missing media fields, broken image fallbacks, and safe result summaries.

Phase 3D: AI Bingo generation:

- Add `/bingo/generate-items` with provider-mocked tests and host review before save/start.
- Add `/bingo/generate-images` using the shared media layer from `SPEC-IMAGE-GAMES.md`.
- Add regenerate-one, regenerate-all, delete, replace-upload, warning, and retry UI.
- Gate AI generation through standalone entitlements or host-app capabilities before exposing externally.

Phase 3E: Saved content and catalog enablement:

- Persist Bingo setups with `bingo_setup_v2`. Standalone Bingo uses normalized saved setup payloads; host-app persistence remains gated.
- Add standalone catalog cards for Classic Bingo, Baby Bingo, Word Bingo, Emoji Bingo, Image Bingo, and Photo Bingo. Classic configurable Bingo is visible; named future variants remain planned/hidden.
- Add safe result summaries for generic Bingo.
- Only enable host-app/Revelry after party-scoped saved content and callbacks are tested.

### Phase 4: Host-App / Revelry Enablement

- Add host-app catalog metadata. Done for Housie gamma.
- Add party-scoped setup/save/start path. Done for Housie gamma.
- Add safe result callbacks. Done through the shared Revelry session/result callback path.
- Add e2e tests for host/cohost/guest hub roles. Done for the Revelry party hub Housie setup/start path, plus existing gamma Revelry flows.
- Gamma test through Revelry before enabling production. Done for Housie gamma; production remains disabled until explicitly promoted.

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

Bingo-family expansion is implementation-ready when:

- `bingo_setup_v2` payload validation is implemented and tested.
- Creator can choose Classic, Baby, Word/Phrase, Emoji, Image, or Photo Bingo.
- Creator can use a template, write deck items manually, generate text/emoji items from a prompt, upload images, or generate AI images where supported.
- AI-generated text, emoji, and image output is always reviewed and editable before save/start.
- Image Bingo setup stores only media ids/URLs, labels, and alt text, not image bytes.
- 4x4 and 5x5 generic Bingo cards generate deterministically in tests and uniquely per player in rooms.
- Free center behavior is consistent across generation, rendering, and claim validation.
- Generic prize claims work for line, two lines, corners, postage stamp, and blackout.
- Generic Bingo can optionally enforce latest-call claim validation, but defaults to non-strict claims.
- Latest-call and winner/confetti visuals work for word, emoji, and image calls.
- Results summarize winners and called counts without leaking card layouts, hidden call order, private media paths, or provider payloads.

## Open Questions

- Should LocalPlay support a "free" or decorative cell in any future Bingo-family display, or should every visible cell always be part of the game board?
- Should ties after the same call share a prize or should first valid server claim win?
- Should players be allowed multiple tickets in v1?
- Should host be able to manually approve/reject claims, or should server validation be authoritative?
- Should the spectator screen reveal the full called board only, or also show near-claims to create drama?
- Should Image Bingo default to 4x4 on mobile for readability, or should the creator choose 4x4 vs 5x5 every time?
- What is the default AI image generation count and per-session limit before premium entitlements are required?
- Should Photo Bingo mean host-supplied photos only, or should it also include live player-submitted scavenger-hunt photos in a separate future game?
- Should Baby Bingo support both text-only and image-cell templates in its first expansion slice, or should image Baby Bingo wait for the dedicated Image Bingo slice?
- Should generic Bingo allow the strict "last call made it true" rule as a visible host toggle, or keep it hidden in advanced settings?
