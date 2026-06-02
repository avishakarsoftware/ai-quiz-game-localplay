# LocalPlay DrawingGame Spec

## Overview

Add a drawing-and-guessing game to LocalPlay under the product-neutral name **DrawingGame**.

This is a Pictionary-style party game, but do not use `pictionary` as a code identifier, route, public product name, database enum, or API value. Use:

```text
GameType: drawing
Backend engine: drawing_engine.py
Frontend display name: Drawing Game
```

The goal is to support a host-led local multiplayer drawing game where one player draws a prompt, other players guess in real time, and the spectator/TV screen shows the drawing surface, timer, accepted guesses, and round results.

This spec should be implemented after the current LocalPlay platform work is stable enough for additional game types. It must preserve the existing quiz and WMLT flows.

## Goals

- Add `drawing` as a first-class `GameType`.
- Generate or select drawing prompts using the existing spark/generation model.
- In Revelry/host-app party hub mode, allow the host to AI-generate drawing prompts from party context, edit them in the generic setup form, then save or save-and-start the party-scoped setup without exposing standalone sparks/wallet UI.
- Support organizer, player, and spectator surfaces.
- Let one player draw per round and all non-drawing players guess.
- Score both the drawer and the correct guessers.
- Keep live drawing state process-local for the initial VM deployment.
- Avoid adding Supabase live-room requirements in the first version.
- Make future Cloud Run/state externalization possible by keeping event contracts explicit.

## Non-Goals

- No image generation for drawings in v1.
- No persistent gallery in v1.
- No multiplayer collaborative drawing in v1.
- No public sharing of player drawings in v1.
- No AI judging in v1.
- No autoscaled Cloud Run support in v1.
- No trademarked naming in code or docs.

## Current Architecture Fit

Current game support is centered on:

- `GameType = 'quiz' | 'wmlt'` in `frontend/src/types.ts`.
- Backend room runtime in `backend/socket_manager.py`.
- Game-specific generation in `quiz_engine.py` and `mlt_engine.py`.
- Host/player/spectator branching in:
  - `frontend/src/pages/OrganizerPage.tsx`
  - `frontend/src/pages/PlayerPage.tsx`
  - `frontend/src/pages/SpectatorPage.tsx`
  - `frontend/src/components/organizer/*`

DrawingGame should follow the existing pattern first, then carve out abstractions only where the code gets materially cleaner.

Key integration points that need updating:

- `RoomCreateRequest.validate_game_type` in `main.py` currently rejects anything other than `"quiz"` or `"wmlt"`. Add `"drawing"`.
- `frontend/src/types.ts` `GameType` union: add `'drawing'`.
- Room creation must accept a `drawing_id` field alongside existing `quiz_id` and `mlt_id`, then branch in `create_room()` the same way it currently branches for `mlt_id`.
- Content storage in `main.py` needs `drawing_games: Dict[str, dict]` and `drawing_timestamps: Dict[str, float]`, matching the `quizzes`/`quiz_timestamps` and `mlt_scenarios`/`mlt_timestamps` pattern.
- `content_owners` must be set for generated drawing content and checked during room creation, so anonymous/user ownership remains consistent with quiz and WMLT.
- Eviction in `_evict_old_content()` must include drawing content, skip drawing IDs used by active rooms, and remove stale `content_owners` entries.
- The backend-served SPA `API_PREFIXES` list must include `/drawing`, otherwise `/drawing/...` API routes can be swallowed by the SPA fallback.
- Admin/system stats should include drawing content counts once drawing content is kept in memory.

## Game Rules

### Participants

- Host: creates the game, starts rounds, sees controls.
- Drawer: one player selected for the current round.
- Guessers: all connected players except the drawer.
- Spectator: TV/large screen display.

### Round Flow

1. Host creates or selects a DrawingGame prompt set.
2. Players join the room as usual.
3. Host starts the game.
4. Server selects the drawer for round 1.
5. Drawer receives the secret prompt.
6. Guessers see a guessing input and the live drawing canvas.
7. Guessers and spectators see a progressive letter clue, not the full prompt.
8. Spectator sees the live drawing canvas, timer, drawer name, recent guesses, correct guessers, and non-secret round metadata.
9. Drawer draws until time expires or all guessers answer.
10. Correct guesses are accepted in real time.
11. Round ends.
12. Server scores drawer and guessers.
13. Leaderboard/result screen shows the prompt, correct guessers, and score changes.
14. In auto mode, the server waits 5 seconds and starts the next round. In manual mode, the host presses Next Round.
15. Next round selects another drawer.
16. Final podium works like other games.

### Round Advance Mode

The host chooses a round advance mode during Drawing Game review:

- `auto` is the default.
- `manual` is available when the host wants to pause between rounds.
- Auto mode uses `drawing_auto_advance = true` and `drawing_inter_round_seconds = 5` in room creation.
- Manual mode uses `drawing_auto_advance = false`.
- During the 5-second inter-round pause, the server broadcasts `DRAWING_NEXT_ROUND_PENDING`.
- If the host manually advances during the pause, the pending auto-advance task is cancelled to avoid double-starting a round.

### Progressive Clues

Guessers and spectators must never receive the full prompt text until the round ends. Instead they receive `drawing_clue`.

Clue format:

- Each unrevealed alphanumeric character is shown as `_`.
- Letters inside a word are separated by a single space.
- Words are separated visually, for example `cat` -> `_ _ _` and `cold cat` -> `_ _ _ _   _ _ _`.
- Punctuation can remain visible because it does not reveal the answer materially.

Reveal schedule:

| Elapsed timer | Example for `cold cat` |
|---:|---|
| 0-49% | `_ _ _ _   _ _ _` |
| 50-74% | `c _ _ _   _ _ _` |
| 75-89% | `c _ _ _   c _ _` |
| 90%+ | `c _ _ d   c _ t` |

The server computes clues from authoritative timer state and includes the updated `drawing_clue` in `TIMER` payloads so reconnecting clients and spectators stay synchronized.

### Drawer Rotation

Default v1 behavior:

- Every player should draw at least once before any player draws twice.
- Drawer order should be deterministic per room once shuffled by the server.
- Reconnecting players keep their drawer slot.
- Disconnected drawers:
  - If the drawer disconnects before drawing starts, skip to the next drawer.
  - If the drawer disconnects mid-round, pause for up to 15 seconds.
  - If they do not reconnect, end the round with no drawer bonus and continue.

### Prompt Rules

Prompts should be drawable and family-friendly by default.

Prompt examples:

```text
astronaut
haunted house
roller coaster
banana peel
volcano
robot chef
```

Prompt constraints:

- 1 to 5 words.
- No proper nouns by default unless user asks for a theme that needs them.
- Avoid abstract trivia-like concepts that are hard to draw.
- Avoid adult, hateful, violent, or private-person prompts.
- Avoid prompts that require text to solve.

### Guess Rules

- Guesses are free-text.
- Matching should be forgiving:
  - case-insensitive
  - trim whitespace
  - strip punctuation and token-boundary articles ("a", "an", "the")
  - simple singular/plural normalization on both guess and prompt: apply `ies` -> `y` first, then trailing `es`/`s`
  - support generated aliases where available
  - do NOT use fuzzy/Levenshtein matching in v1 — false positives are worse than near-misses. Aliases cover common alternate phrasings
- The drawer cannot guess.
- Each guesser can score once per round.
- Incorrect guesses may be shown as a rolling feed on player/TV surfaces, but do not need to persist.

### Scoring

Default scoring:

| Event | Points |
|---|---:|
| First correct guesser | 1000 |
| Later correct guessers | time-scaled 300-900 |
| Drawer bonus per correct guesser | 200 |
| All guessers correct | +500 drawer bonus |

Time scaling:

```text
guesser_points = 300 + round(600 * (time_remaining / time_limit))
```

Rules:

- Drawer gets no points if nobody guesses correctly.
- Correct guessers get points immediately or at round end; v1 can apply at round end to reduce state churn.
- Tie handling should reuse existing podium behavior.

## Content Model

### TypeScript

Extend:

```ts
export type GameType = 'quiz' | 'wmlt' | 'drawing';
```

Add:

```ts
export interface DrawingPrompt {
  id: number;
  text: string;
  aliases?: string[];
  difficulty?: 'easy' | 'medium' | 'hard';
}

export interface DrawingGame {
  game_title: string;
  prompts: DrawingPrompt[];
  auto_advance?: boolean;
  inter_round_seconds?: number;
}
```

### Backend Runtime Shape

Add a DrawingGame content object:

```py
{
    "game_title": "Drawing Game",
    "prompts": [
        {
            "id": 1,
            "text": "robot chef",
            "aliases": ["robot cook", "cooking robot"],
            "difficulty": "medium",
        }
    ]
}
```

Room runtime additions:

```py
room.game_type = "drawing"
room.quiz = drawing_game  # keep existing generic field temporarily
room.drawer_order = ["Avi", "Sam", "Maya"]
room.current_drawer = "Avi"
room.correct_guessers = set()
room.guess_log = []
room.drawing_ops = []
```

Longer-term cleanup:

- Rename `Room.quiz` to `Room.content` once more game types exist.
- Rename `current_question_index` to `current_round_index`.
- Keep compatibility wrappers if the refactor is not done in the same PR.

## Prompt Generation

### Endpoint

Preferred v1 endpoint:

```http
POST /drawing/generate
```

Request:

```json
{
  "prompt": "things at a beach party",
  "difficulty": "medium",
  "num_prompts": 10,
  "provider": "gemini"
}
```

Response:

```json
{
  "game_title": "Beach Party Drawing Game",
  "prompts": [
    {
      "id": 1,
      "text": "sandcastle",
      "aliases": ["sand castle"],
      "difficulty": "easy"
    }
  ]
}
```

Economy:

- Reuse `COST_GENERATE`.
- Reuse generation idempotency behavior.
- Store content in memory for v1 like quiz/WMLT.
- Supabase persistence for generated DrawingGame content belongs to the future content-persistence phase.

### Engine

Add:

```text
backend/drawing_engine.py
```

Responsibilities:

- Build provider prompt.
- Parse provider JSON.
- Validate prompt count and shape.
- Normalize aliases.
- Reject unsuitable prompts.
- Provide local fallback prompts if the configured provider fails.

Generation model:

- Use the same configured Gemini 2.5 Flash Lite model as quiz/WMLT.
- Do not introduce a drawing-specific premium model in v1.

### Provider Prompt Requirements

The provider should return strict JSON:

```json
{
  "game_title": "string",
  "prompts": [
    {
      "text": "string",
      "aliases": ["string"],
      "difficulty": "easy|medium|hard"
    }
  ]
}
```

Instruction notes:

- Prompts must be visually drawable.
- Keep each prompt short.
- Avoid text-dependent answers.
- Include 2-5 aliases for common alternate guesses.
- Match the requested theme.
- Avoid copyrighted character names unless the user's prompt explicitly asks for that universe.

## WebSocket Protocol

Reuse the existing room WebSocket:

```text
/ws/{room_code}/{client_id}
```

### Existing Messages Reused

- `JOIN`
- `JOINED_ROOM`
- `PLAYER_JOINED`
- `PLAYER_LEFT`
- `GAME_STARTING`
- `TIMER`
- `LEADERBOARD`
- `PODIUM`
- `ROOM_RESET`
- `ERROR`

### New Messages

#### Server -> Clients: QUESTION

Sent at the start of each round.

Drawer receives:

```json
{
  "type": "QUESTION",
  "game_type": "drawing",
  "question_number": 1,
  "total_questions": 10,
  "time_limit": 60,
  "drawer": "Avi",
  "is_drawer": true,
  "drawing_clue": "_ _ _ _ _   _ _ _ _",
  "drawing_prompt": {
    "id": 1,
    "text": "robot chef",
    "aliases": ["robot cook"],
    "difficulty": "medium"
  }
}
```

Guessers receive:

```json
{
  "type": "QUESTION",
  "game_type": "drawing",
  "question_number": 1,
  "total_questions": 10,
  "time_limit": 60,
  "drawer": "Avi",
  "is_drawer": false,
  "drawing_clue": "_ _ _ _ _   _ _ _ _",
  "drawing_prompt": {
    "id": 1,
    "difficulty": "medium"
  }
}
```

Spectators receive:

```json
{
  "type": "QUESTION",
  "game_type": "drawing",
  "question_number": 1,
  "total_questions": 10,
  "time_limit": 60,
  "drawer": "Avi",
  "drawing_clue": "_ _ _ _ _   _ _ _ _",
  "drawing_prompt": {
    "id": 1,
    "difficulty": "medium"
  }
}
```

Do not send the prompt text or aliases to guessers or spectators until the round ends.

Timer updates include the current clue:

```json
{
  "type": "TIMER",
  "remaining": 22,
  "drawer": "Avi",
  "drawing_clue": "r _ _ _ _   _ _ _ _"
}
```

#### Drawer -> Server: DRAW_OP

Sent by the drawer as compact vector operations.

```json
{
  "type": "DRAW_OP",
  "op": {
    "kind": "stroke",
    "id": "stroke-uuid",
    "points": [[0.12, 0.44], [0.13, 0.45]],
    "color": "#111111",
    "width": 6
  }
}
```

Coordinates are normalized 0-1 canvas coordinates so spectator/player canvases can scale independently.

Supported v1 operations:

```text
stroke
clear
undo
```

Future operations:

```text
fill
shape
eraser stroke
```

#### Server -> Clients: DRAW_OP

Broadcast to all non-drawer clients and spectators.

```json
{
  "type": "DRAW_OP",
  "from": "Avi",
  "op": {
    "kind": "stroke",
    "id": "stroke-uuid",
    "points": [[0.12, 0.44], [0.13, 0.45]],
    "color": "#111111",
    "width": 6
  }
}
```

Server validation:

- Only current drawer may send draw ops.
- Drop ops after the round is over.
- Limit operation size.
- Rate limit draw ops per connection.

#### Guesser -> Server: GUESS

```json
{
  "type": "GUESS",
  "guess": "robot cook"
}
```

Server response to guesser:

```json
{
  "type": "GUESS_RESULT",
  "correct": true,
  "guess": "robot cook",
  "points": 780
}
```

Broadcast for public feed:

```json
{
  "type": "GUESS_ACCEPTED",
  "nickname": "Sam",
  "rank": 1
}
```

Incorrect guess public feed, optional:

```json
{
  "type": "GUESS_SUBMITTED",
  "nickname": "Sam",
  "guess": "chef hat"
}
```

For v1, show incorrect guesses only if it feels fun and non-spammy. Add a per-player cooldown if public feed is enabled.

#### Server -> Clients: DRAWING_ROUND_OVER

Legacy name for this spec; the implementation uses `QUESTION_OVER`.

```json
{
  "type": "QUESTION_OVER",
  "game_type": "drawing",
  "round_number": 1,
  "total_rounds": 10,
  "prompt": "robot chef",
  "drawer": "Avi",
  "correct_guessers": [
    {
      "nickname": "Sam",
      "points": 780,
      "rank": 1
    }
  ],
  "drawer_points": 700,
  "leaderboard": []
}
```

#### Server -> Clients: DRAWING_NEXT_ROUND_PENDING

Sent once per second during auto mode's inter-round pause.

```json
{
  "type": "DRAWING_NEXT_ROUND_PENDING",
  "remaining": 5,
  "is_final": false,
  "next_label": "Next round"
}
```

## Canvas Transport

### Why Vector Ops

Use vector drawing operations instead of streaming bitmap frames.

Benefits:

- Small WebSocket payloads.
- Scales cleanly between phones and TV.
- Easy undo/clear.
- Can replay state for reconnecting players.
- Lower server bandwidth.

### Operation Limits

Recommended defaults:

```text
Max points per DRAW_OP: 80
Max ops per second per drawer: 30
Max stored ops per round: 2500
Max stroke width: 32
Max color palette: fixed server-approved colors
Initial drawing color: black (#111111)
Default round timer: 30 seconds
Max DRAW_OP message size: 2048 bytes
```

If the drawer sends too many points:

- Server may simplify or drop the op.
- Client should batch points every 30-50ms.
- Client should quantize coordinates before sending, either as small integers in canvas-normalized space or rounded decimals, so 80-point strokes reliably fit under the DRAW_OP envelope limit.

**Important**: The current global WebSocket rate limit is `WS_RATE_LIMIT_PER_SEC = 10` messages/second (in `config.py`). Drawing requires ~30 ops/second for smooth strokes. The rate limiter must be relaxed for DRAW_OP messages specifically, or the drawer's game type must bypass the global limit with a separate drawing-specific rate counter. Do not raise the global limit — only exempt `DRAW_OP` from it while enforcing the drawing-specific 30 ops/sec cap.

The current receive loop in `backend/socket_manager.py` applies the global rate limit before parsing the JSON message type. Drawing implementation must reorder that loop carefully:

1. Enforce `MAX_WS_MESSAGE_SIZE`.
2. Parse JSON once.
3. Read `msg["type"]`.
4. For `DRAW_OP`, enforce the 2048-byte DRAW_OP envelope limit and a separate `DRAW_OP` counter, for example `draw_op_timestamps`, capped at 30/sec.
5. For every other message type, keep the existing global `msg_timestamps` behavior.

Similarly, `MAX_WS_MESSAGE_SIZE = 4096` bytes is sufficient for DRAW_OP, but validate that the entire DRAW_OP envelope stays under 2048 bytes to leave headroom for other messages and avoid unusually large stroke batches.

### Reconnect

When a player/spectator reconnects during a drawing round, server sends:

```json
{
  "type": "DRAWING_SYNC",
  "state": "DRAWING",
  "round_number": 1,
  "total_rounds": 10,
  "time_remaining": 38,
  "drawer": "Avi",
  "is_drawer": false,
  "drawing_ops": [],
  "correct_guessers": []
}
```

Only the current drawer receives the prompt in sync.

## Frontend UX

### Game Select

Add a card:

```text
Drawing Game
Draw the prompt while everyone guesses.
```

Use `gameType: 'drawing'`.

### Organizer Flow

New screens/components:

```text
frontend/src/components/organizer/DrawingPromptScreen.tsx
frontend/src/components/organizer/DrawingReviewScreen.tsx
```

Organizer prompt screen:

- Theme/topic textarea.
- Difficulty control.
- Number of prompts/rounds.
- Time per round.
- Generate button.

Organizer review screen:

- List prompts.
- Edit prompt text.
- Edit aliases, optional behind a disclosure.
- Delete prompts, minimum 3.
- Time per round.
- Create Room.

Room/lobby:

- Reuse `LobbyScreen`.
- Show "Drawing Game" title and round count.

In-game organizer:

- Show current drawer.
- Show round number and timer.
- Show correct guess count.
- Controls:
  - End Round
  - Next Round
  - End Game

### Player Flow

Player states:

```ts
type PlayerState =
  | existing states
  | 'DRAWING'
  | 'GUESSING'
  | 'DRAWING_RESULT';
```

Drawer screen:

- Secret prompt card.
- Full-width canvas.
- Tool row:
  - color swatches
  - black selected as the initial color
  - brush size
  - undo
  - clear
- Timer.
- Correct guess count.

Guesser screen:

- Read-only canvas.
- Guess input pinned near bottom.
- Submit button.
- Guess feedback.
- Correct guessers strip.

Round result:

- Reveal prompt.
- Show drawer.
- Show correct guessers.
- Show points.
- Show leaderboard chart.

### Spectator/TV Flow

Spectator drawing round:

- Large drawing canvas, 16:9 safe.
- Drawer name.
- Timer.
- Correct guess count.
- Optional guess feed on side.
- Never show prompt during active round.

Round result:

- Reveal prompt in large type.
- Show correct guessers.
- Show drawer bonus.
- Show leaderboard.

Podium:

- Reuse existing podium.

### Drawing Canvas Component

Create:

```text
frontend/src/components/drawing/DrawingCanvas.tsx
frontend/src/components/drawing/drawingOps.ts
```

`DrawingCanvas` props:

```ts
type DrawingCanvasProps = {
  mode: 'draw' | 'view';
  ops: DrawingOp[];
  onOp?: (op: DrawingOp) => void;
  color?: string;
  width?: number;
  disabled?: boolean;
};
```

Implementation notes:

- Use `<canvas>`, not SVG, for rendering.
- Use Pointer Events for mouse/touch/stylus.
- Normalize pointer coordinates to 0-1.
- Re-render from ops when size changes.
- Batch pointer move points.
- Support high-DPI rendering using `devicePixelRatio`.
- Avoid page scroll while drawing on touch devices.
- Maintain mobile safe areas.

## Backend Implementation Plan

### Phase 1: Types And Catalog

- Add `drawing` to frontend `GameType`.
- Add Drawing Game card.
- Add backend game metadata if catalog exists.
- Add placeholder disabled state only if backend is not ready.

### Phase 2: Prompt Generation

- Add `backend/drawing_engine.py`.
- Add `POST /drawing/generate`.
- Reuse spark cost and idempotency.
- Add unit tests for prompt validation and alias matching.

### Phase 3: Room Runtime

- Extend room data shape for drawing:
  - drawer order
  - current drawer
  - drawing ops
  - guess log
  - correct guessers
- Add server-side guess matching.
- Add draw-op validation and broadcast.
- Add reconnect sync.

### Phase 4: Organizer UI

- Add prompt and review screens.
- Add room creation support.
- Add in-game host controls.

### Phase 5: Player UI

- Add drawer canvas.
- Add guesser canvas and guess input.
- Add round result screen.

### Phase 6: Spectator UI

- Add TV canvas.
- Add result reveal.
- Add guess/correct feed.

### Phase 7: Tests And Smoke

Backend tests:

- Generate drawing prompts.
- Reject malformed generated prompt data.
- Normalize guesses.
- Match aliases.
- Only drawer can submit draw ops.
- Drawer cannot guess.
- Correct guess idempotency.
- Scoring.
- Reconnect sync hides prompt from guessers.

Frontend tests:

- Game select card appears.
- Drawer sees prompt and canvas tools.
- Guesser does not see prompt.
- Spectator does not see prompt.
- Draw ops render in view mode.
- Correct guess result appears.
- Round result reveals prompt.

Smoke test:

1. Generate DrawingGame.
2. Create room.
3. Join with two players.
4. Start game.
5. Verify drawer sees prompt.
6. Verify guesser/spectator do not see prompt.
7. Draw one stroke.
8. Verify guesser/spectator receive stroke.
9. Submit correct alias.
10. Verify points and round result.
11. Finish game and podium.

## Data Persistence

V1:

- Generated DrawingGame content remains in process memory.
- Live drawing ops remain in process memory.
- Completed game history remains current behavior.

Supabase future:

- Store generated DrawingGame content in `games_generated_content` once content persistence is implemented.
- Store completed summaries in `games_game_history`.
- Do not store raw drawing ops by default.

Optional future gallery:

- Store final canvas image only if a product feature needs it.
- Require explicit consent/copy if drawings are shared.
- Apply retention limits.

## Moderation And Safety

Prompt generation:

- Keep family-friendly by default.
- Reject hateful, sexual, graphic, or private-person prompts.
- Avoid prompts that encourage drawing slurs or explicit content.

Player drawings:

- V1 does not need AI moderation of live drawings.
- Host should be able to kick players using existing room controls if available.
- Add future backlog for report/moderation if public sharing is introduced.

Guess feed:

- Incorrect guess feed can become a harassment surface.
- For v1, either:
  - show only correct guesses publicly, or
  - show incorrect guesses only locally to the guesser.

Recommended v1: only broadcast `GUESS_ACCEPTED`.

## Performance

Client:

- Throttle pointer move batching.
- Use `requestAnimationFrame` for canvas rendering.
- Cap canvas CSS size for phones.
- Render high DPI but clamp backing resolution on low-end devices.

Server:

- Validate and drop oversized ops.
- Keep per-room ops bounded.
- Clear ops after round result unless needed for short replay.
- Avoid writing ops to Supabase in v1.

Network:

- Prefer compact numeric arrays over verbose point objects.
- Avoid sending prompt to unauthorized clients.

## Accessibility

- Drawer canvas must have accessible label text.
- Guesser input should be focusable and submit on Enter.
- Timer should be visible text, not only a ring.
- Color swatches must have text labels/tooltips.
- Do not rely only on color for correct guess status.
- Support reduced motion.

## Open Questions

- Should all players draw once, or should round count be host-configurable independent of player count?
- Should drawer get points only if someone guesses correctly?
- Should incorrect guesses be visible to everyone, or only the guesser?
- Should prompt aliases be visible/editable in the review screen by default?
- Should teams affect drawer rotation/scoring?
- Should a drawing replay be shown after each round?

Recommended defaults:

- Host chooses round count, default equals player count when known, otherwise 8.
- Drawer only scores when at least one guesser is correct.
- Broadcast only correct guesses in v1.
- Hide aliases behind "Advanced".
- Ignore teams for v1 scoring.
- No replay in v1.

## Acceptance Criteria

- `drawing` appears in game select and can be generated.
- Backend exposes drawing content routes under `/drawing/...`, and those routes are protected from the SPA fallback by `API_PREFIXES`.
- Host can review generated prompts and create a room.
- Room can start with at least 2 players (add `MIN_DRAWING_PLAYERS = 2` in `config.py`, matching the WMLT pattern).
- Drawer receives prompt; guessers and spectators do not.
- Drawer strokes appear on guesser and spectator canvases.
- Correct guesses are accepted by normalized prompt or alias.
- Round result reveals prompt and points.
- Final podium works.
- Existing quiz and WMLT tests still pass.
- DrawingGame has backend unit tests for generation, matching, draw-op authorization, and scoring.
- DrawingGame has frontend tests for drawer/guesser/spectator prompt visibility.
- DrawingGame organizer prompt UX has Playwright coverage on desktop and mobile for aligned controls, no horizontal overflow, no overlap with fixed menu/spark controls, and visual snapshots.

## Backlog After V1

- Persist generated DrawingGame content in Supabase.
- Persist final game result summaries.
- Add standalone saved custom prompt packs/library, equivalent to My Quizzes, so hosts can create, revisit, edit, and start custom DrawingGame sets outside a party context.
- Add host-uploaded prompts.
- Add drawing replay.
- Add optional final image export.
- Add team mode.
- Add more drawing tools.
- Add moderation/reporting if drawings become shareable.
- Add external state store if LocalPlay moves to autoscaled Cloud Run.
