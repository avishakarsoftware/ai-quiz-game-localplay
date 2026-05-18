# LocalPlay Platform Spec

This document describes the intended platform direction for LocalPlay. It is forward-looking. For the current implemented system, see `SPEC.md`.

## Vision

LocalPlay is an independent local multiplayer game platform for groups in the same physical or social context. It should work as a standalone app and also be launchable from other apps, especially Revelry.

The product should feel like a game console for parties:

- A host chooses a game.
- AI can generate game content.
- Players join instantly by room code, QR code, or host-app invite.
- The group plays together in real time.
- Results become shareable memories.

LocalPlay is not just "the games tab" of another product. It is the game engine, catalog, and realtime runtime. Other apps may distribute or launch LocalPlay games, but LocalPlay owns the gameplay experience.

## Product Boundary

### LocalPlay Owns

- Game catalog and game metadata.
- Game setup flows.
- AI game content generation.
- Live room/session runtime.
- WebSocket transport for gameplay.
- Player join/rejoin flows.
- Game-specific rules, scoring, timers, and results.
- Team mode where supported.
- Game history and shareable result summaries.
- Standalone LocalPlay host and player UX.

### Revelry Owns

Revelry is a party lifecycle app. It owns:

- User accounts and party identity.
- Party host/cohost/helper/guest roles.
- Guest list and RSVP data.
- Party timeline, planning, chat, media, and memories.
- A Games tab that can launch LocalPlay sessions.
- Displaying LocalPlay results inside party memories/history.

Revelry should not own LocalPlay game rules. It should not need to know how Pictionary, Chinese Whispers, Taboo, Quiz, or WMLT score a round.

### Integration Bridge Owns

The integration layer should be small and explicit:

- Authenticate a launch request from an external app.
- Attach external context such as `party_id`.
- Create or resume a LocalPlay game session.
- Return launch URLs and session ids.
- Let the external app retrieve or receive game results.

The bridge should not leak LocalPlay internals into Revelry.

## Design Principles

1. **Standalone First, Embeddable Second**
   - Every game should work when launched directly from LocalPlay.
   - The same game should also work when launched from Revelry with party context.

2. **Sessions Are Product Objects; Rooms Are Runtime Objects**
   - A session is something an external app can reference.
   - A room is the live transport/runtime for gameplay.

3. **Shared Lifecycle, Custom Game Rules**
   - Joining, reconnecting, timers, lobby, results, and host controls should be shared where possible.
   - Game rules should remain explicit and readable.
   - Avoid a heavy plugin framework until the repetition proves it is necessary.

4. **Catalog Metadata Is Data-Driven**
   - The app should be able to list, filter, and recommend games without importing game implementation details.

5. **Results Are Portable**
   - Every game should produce a normalized result summary that can be shown in LocalPlay, Revelry, or another future host app.

6. **Defer Distributed Systems Until Needed**
   - Single-server hosting is appropriate now.
   - Persistent sessions and history should come before multi-instance realtime scaling.
   - Shared room state should be introduced only when growth requires it.

## Core Concepts

### Game

A game is a playable format, such as:

- Quiz
- Who's Most Likely To
- Pictionary
- Chinese Whispers
- Word Association
- Taboo variants

A game has:

- Stable id.
- Display metadata.
- Setup schema.
- Optional AI generation engine.
- Runtime message handlers.
- Player UI.
- Organizer UI.
- Result renderer.

### Game Catalog

The catalog is the list of available games and their display/runtime metadata.

Example shape:

```json
{
  "id": "pictionary",
  "title": "Pictionary",
  "short_description": "Draw prompts while your friends guess.",
  "category": "creative",
  "min_players": 3,
  "max_players": 20,
  "supports_teams": true,
  "supports_ai_generation": true,
  "estimated_minutes": 20,
  "setup_kind": "prompt",
  "capabilities": ["drawing", "guessing", "teams", "timed_rounds"],
  "status": "planned"
}
```

Catalog status values:

- `live`
- `beta`
- `planned`
- `hidden`
- `disabled`

Catalog metadata should power:

- LocalPlay game selection.
- Revelry Games tab.
- Future recommendations by party type.
- Feature flags and rollout controls.

### Game Session

A game session is the durable product object representing one launched game experience.

It may be created by LocalPlay directly or by an external app.

Suggested fields:

```json
{
  "id": "session_uuid",
  "game_type": "pictionary",
  "source_app": "localplay",
  "external_context": null,
  "host_user_id": "optional",
  "host_display_name": "optional",
  "room_code": "ABC123",
  "status": "draft",
  "title": "Birthday Pictionary",
  "created_at": 0,
  "started_at": null,
  "completed_at": null,
  "expires_at": 0,
  "settings": {},
  "content_id": "optional",
  "result_summary": null
}
```

Session statuses:

- `draft`: setup exists but room is not live.
- `lobby`: room exists and players can join.
- `live`: game is in progress.
- `complete`: game ended and results are available.
- `expired`: abandoned or TTL-expired.
- `cancelled`: host cancelled before completion.

### Room

A room is the live runtime for a session.

It owns:

- WebSocket connections.
- Active players.
- Organizer connection.
- Spectators.
- Current game state.
- Timers.
- Per-round state.

Current code stores rooms in memory. That is acceptable for the current server deployment. Long-term, `Room` should remain the runtime object, while `GameSession` becomes the durable object.

### Player

A player is a participant inside a session/room.

Fields:

- Local nickname.
- Avatar.
- Optional team.
- Optional external user id.
- Session token for reconnect/nickname ownership.
- Score and game-specific state.

Player identity should not require a LocalPlay account. Fast anonymous join must remain core to the product.

### Host / Organizer

The organizer controls:

- Game setup.
- Room creation.
- Start game.
- Advance rounds.
- End game.
- Reset/play again.

When launched from Revelry, the organizer may be authenticated through a signed handoff token rather than a LocalPlay login.

### External Context

External context links a LocalPlay session to another app's domain object.

Example:

```json
{
  "source_app": "revelry",
  "party_id": "party_uuid",
  "party_title": "Ava's Birthday",
  "host_user_id": "revelry_user_uuid"
}
```

LocalPlay should store enough external context to return results and support debugging, but not enough to duplicate the external app's data model.

## Current-To-Platform Migration

Current system:

- `Room` is the main concept.
- Generated content is stored in memory by content id.
- `/room/create` creates a room directly from content.
- Quiz and WMLT are hardcoded through `game_type` branches.

Target system:

- `GameSession` is created first.
- A session may have generated content.
- A room is created/resumed for that session.
- External apps interact with sessions, not raw rooms.

Suggested migration path:

1. Keep existing `/quiz/*`, `/mlt/*`, and `/room/create` working.
2. Add a catalog endpoint.
3. Add a `GameSession` model/table.
4. Make room creation optionally create or attach to a session.
5. Add result persistence.
6. Add external launch APIs.
7. Gradually move generated content from memory to persistent storage.

Do not pause game development waiting for the perfect session abstraction. Add it in a way that wraps the current model.

## Game Architecture

### Per-Game Backend Shape

For each game:

- Generation engine if AI content is needed.
- Validation and sanitization.
- Namespaced REST endpoints.
- Runtime message handlers.
- Round start helper.
- Round end/scoring helper.
- Result summary builder.

Example backend files over time:

```text
backend/
  games/
    catalog.py
    quiz.py
    wmlt.py
    pictionary.py
    chinese_whispers.py
    taboo.py
    word_association.py
```

The current code keeps game logic in `socket_manager.py`. That is acceptable for the first few games, but the long-term direction should move game-specific helpers into game modules while keeping shared WebSocket infrastructure centralized.

### Per-Game Frontend Shape

For each game:

- Catalog entry.
- Organizer setup screen.
- Optional review/edit screen.
- Organizer live-round screen.
- Player live-round screen.
- Result screen or result renderer.

Possible directory shape:

```text
frontend/src/games/
  catalog.ts
  quiz/
    OrganizerSetup.tsx
    Review.tsx
    PlayerRound.tsx
    OrganizerRound.tsx
    Results.tsx
  wmlt/
  pictionary/
  chinese-whispers/
```

The current `OrganizerPage.tsx` and `PlayerPage.tsx` can continue as state-machine shells, but game-specific UI should gradually move into game folders.

### Shared Lifecycle

Shared states:

- Select game.
- Setup/generate.
- Review.
- Lobby.
- Intro.
- Round.
- Round results.
- Final results.

Shared host actions:

- Create session/room.
- Lock room.
- Start.
- Next round.
- End.
- Play again.

Shared player actions:

- Join.
- Reconnect.
- Submit game action.
- Wait.
- View result.

Game-specific player actions:

- Quiz: answer.
- WMLT: vote.
- Pictionary: draw or guess.
- Chinese Whispers: submit phrase or drawing.
- Taboo: give clues, guess, skip, mark taboo violation.
- Word Association: submit word, vote, match, or rank depending on variant.

### WebSocket Message Naming

Current messages reuse quiz language:

- `QUESTION`
- `QUESTION_OVER`
- `NEXT_QUESTION`
- `END_QUIZ`

Long-term, prefer neutral names:

- `ROUND_STARTED`
- `ROUND_ENDED`
- `NEXT_ROUND`
- `END_GAME`
- `PLAYER_ACTION`
- `ACTION_CONFIRMED`

Migration should be careful:

- Keep old messages for quiz/WMLT compatibility.
- New games can use neutral messages.
- Eventually aliases can normalize old names.

## AI Content Generation

LocalPlay's AI generation pattern should remain consistent:

1. System prompt defines the game writer/designer role.
2. User-provided theme/topic is wrapped in boundary markers.
3. Provider returns strict JSON.
4. JSON is parsed.
5. Shape is validated.
6. User-visible text is sanitized and length-capped.
7. Content is stored with ownership/session context.

AI should generate game content, not game rules.

Examples:

- Quiz: questions, options, answers, image prompts.
- WMLT: statements.
- Pictionary: drawable prompts, difficulty tiers, optional forbidden words.
- Chinese Whispers: seed phrases or image prompts.
- Taboo: target words, forbidden words, clue difficulty.
- Word Association: seed words, category packs, scoring prompts.

## Integration With Revelry

### Integration Goals

From Revelry, a party host should be able to:

- Open a Games tab.
- See available LocalPlay games.
- Launch a game for a party.
- Share/join through party context.
- Play in LocalPlay.
- Save results back to the party.

Guests should be able to:

- Join quickly without creating a LocalPlay account.
- Use existing Revelry context when available.
- Return to Revelry after the game if launched from Revelry.

### Integration Non-Goals

Revelry should not:

- Implement LocalPlay game rules.
- Store live round state.
- Proxy every WebSocket message.
- Depend on LocalPlay internal room structures.

LocalPlay should not:

- Duplicate Revelry's party planning model.
- Require Revelry for standalone play.
- Require every player to have a Revelry account.

### Launch Flow

Recommended future flow:

```text
Revelry host opens Games tab
  -> Revelry fetches LocalPlay catalog
  -> Host picks a game
  -> Revelry requests a signed handoff/launch
  -> LocalPlay validates handoff
  -> LocalPlay creates GameSession
  -> LocalPlay returns launch URL
  -> Host runs the game in LocalPlay
  -> LocalPlay stores results
  -> Revelry retrieves or receives summary
```

### Signed Handoff Token

Revelry can issue or request a signed token that LocalPlay validates.

Claims:

```json
{
  "iss": "revelry",
  "aud": "localplay",
  "sub": "revelry_user_id",
  "role": "host",
  "party_id": "party_uuid",
  "party_title": "Ava's Birthday",
  "display_name": "Avi",
  "exp": 0,
  "nonce": "random"
}
```

Security requirements:

- Short expiration.
- Audience check.
- Issuer check.
- Signature verification.
- Replay protection where practical.
- Scope token to one party and intended role.

### Integration APIs

Potential LocalPlay APIs:

```http
GET /catalog
```

Returns game catalog metadata.

```http
POST /sessions
```

Creates a LocalPlay session from LocalPlay itself or a trusted external source.

```http
POST /integrations/revelry/sessions
```

Creates a session using a Revelry handoff token.

```http
GET /sessions/{session_id}
```

Returns session status and basic metadata.

```http
GET /sessions/{session_id}/launch
```

Returns or redirects to organizer launch URL.

```http
GET /sessions/{session_id}/results
```

Returns normalized results if complete.

```http
POST /integrations/revelry/results-callback
```

Optional callback from LocalPlay to Revelry if pull-based result retrieval is not enough.

The first version should prefer pull-based results. Callbacks add retry/signature complexity.

## Results Model

Every game should produce a normalized result summary.

Example:

```json
{
  "session_id": "session_uuid",
  "game_type": "wmlt",
  "title": "Most Likely To: Birthday Edition",
  "status": "complete",
  "started_at": 0,
  "completed_at": 0,
  "duration_seconds": 900,
  "players": [
    {
      "nickname": "Ava",
      "avatar": "🎨",
      "score": 4200,
      "rank": 1
    }
  ],
  "winner": {
    "nickname": "Ava",
    "score": 4200
  },
  "leaderboard": [],
  "team_leaderboard": [],
  "highlights": [
    {
      "type": "superlative",
      "title": "Mind Reader",
      "player": "Maya",
      "detail": "Voted with the majority 6 times"
    }
  ],
  "shareable_summary": "Ava won Most Likely To with 4200 points."
}
```

Game-specific details can live under `details`:

```json
{
  "details": {
    "rounds": [],
    "drawings": [],
    "vote_history": []
  }
}
```

External apps should be able to render the summary without reading `details`.

## Token Economy For New Games

The spark economy applies uniformly to all games:

- **Generate content**: `COST_GENERATE` (1 spark) — charged after successful LLM generation.
- **Start a game**: `COST_ROOM` (10 sparks) — charged on `START_GAME` and `RESET_ROOM` WebSocket messages.
- **Room creation**: free.

Default rule: new games should use the shared cost model. That keeps pricing simple and predictable while the catalog is growing.

If a game has no AI generation step, such as a player-authored game, only the game-start cost applies. Future exceptions are possible for premium games, sponsored/free games, unusually expensive generation modes, or games that use additional paid media services, but exceptions should be deliberate product decisions rather than per-game drift.

## Game Backlog

### Word Association

Possible loops:

- Everyone submits the first word they think of given a seed word.
- Score for matching the majority (encourages common associations).
- Variant: score for uniqueness (encourages creative thinking).
- Variant: build a chain and vote on funniest/weirdest.

Needs:

- Seed word/category generation (AI).
- Simultaneous text submissions (all players submit at once, hidden until reveal).
- Reveal animation showing all submissions grouped.
- Scoring: majority match or uniqueness depending on mode.
- Timer per round.

Complexity: low-medium.

Recommended first new game because:
- Text-only submissions — no canvas/drawing/audio.
- Simultaneous play — similar to WMLT voting (all submit, then reveal).
- Exercises the "private submit → reveal → score" pattern that other games will reuse.
- AI generates seed words, keeping the generation pattern consistent.

### Chinese Whispers / Telephone

Core loop:

- Start with AI-generated seed phrase (or player-submitted).
- Players take turns: each sees only the previous player's output.
- Alternating rounds of text → text (telephone) or text → drawing → text (Gartic Phone style).
- Final chain is revealed step-by-step for laughs.

Variants (start with simplest):

1. **Text-only telephone** (MVP): Each player rephrases what they saw. Chain drift is the comedy.
2. **Text + Drawing**: Alternate between describing and drawing. Much funnier but requires canvas.

Needs:

- Sequential turn assignment (not simultaneous — this is different from Quiz/WMLT).
- Private per-player prompts (each player sees only the previous step).
- Submission timer per turn.
- Chain assembly and reveal sequence animation.
- For drawing variant: canvas component (shared with Pictionary).

Complexity: medium (text-only) to high (with drawing).

Very strong party fit. Text-only version is viable without a canvas and should ship first.

**Key architecture difference**: This is the first turn-based game. Quiz and WMLT are simultaneous (all players act in the same round window). Chinese Whispers requires a turn queue — the socket_manager needs to track whose turn it is and send prompts to one player at a time while others wait.

### Pictionary

Core loop:

- AI generates drawable prompts with difficulty tiers.
- One player draws while others guess in real time.
- Correct guess awards points to guesser (speed bonus) and drawer (per correct guesser).
- Rotate drawer each round.

Needs:

- Drawing canvas (HTML5 Canvas with touch support).
- Real-time stroke broadcast via WebSocket (draw events → all guessers + spectators).
- Guess input (text field, submitted as typed or on enter).
- Guess validation: exact match, close match (Levenshtein?), or LLM-judged similarity.
- Prompt only visible to drawer; hidden from guessers and spectators.
- Round ends when: all guess correctly, timer expires, or drawer skips.
- Drawing replay or final image capture for result memories.

Complexity: high.

Best after canvas is built for Chinese Whispers (drawing variant) or as a standalone effort.

**Stroke sync approach**: Broadcast draw events (start, move, end, color, width, clear) as compact WS messages. Guessers render locally. This is lower bandwidth than streaming images and allows replay. Typical message: `{type: "DRAW", points: [[x,y],...], color: "#fff", width: 3}`.

**Spectator mode**: Spectators see the canvas in real-time (same stroke feed) plus the guess stream. This makes it great for TV/Chromecast display.

### Taboo Variant

Core loop:

- AI generates word cards: target word + 5 forbidden words.
- One player (clue-giver) sees the card and gives verbal/typed clues.
- Their team guesses the target word.
- Other team or the app monitors for forbidden word violations.
- Timer per card; skip costs a point.

Needs:

- Word pack generation (AI generates batches of cards).
- Team support (already exists in room infrastructure).
- Clue-giver rotation within team.
- Timer per card (short, e.g. 30-60s per card, multiple cards per round).
- Skip/pass mechanic.
- Violation detection: manual (opponent presses buzzer) or automatic (check typed clues against forbidden list).
- Score by correct guesses minus skips.

Complexity: medium.

Good fit because current team mode already exists. Works best with 4+ players (2+ per team).

**Design decision**: Typed clues (checkable) vs verbal clues (honor system / opponent buzzer). Typed is more app-native and enables automatic violation detection. Verbal is more party-like. Could support both modes.

### Two Truths and a Lie

Core loop:

- Each player submits 3 statements: 2 true, 1 lie.
- Other players vote on which one is the lie.
- Score for fooling others (your lie was believed) and detecting lies (you found theirs).

Needs:

- Per-player private submission (3 text fields).
- Sequential reveal: one player's statements shown at a time, others vote.
- AI can generate example statements as prompts/inspiration, but the fun is player-authored content.
- Scoring: deception points + detection points.

Complexity: low.

Great "get to know you" game. Minimal AI involvement (optional inspiration prompts). Could be even simpler than Word Association as it needs no AI generation at all.

### Additional Game Ideas

Future games should be evaluated by:

- Does it work on phones?
- Does it need simultaneous or turn-based play?
- Does it require drawing/audio/camera?
- Can AI generate useful content?
- Can results become a memory?
- Does it work standalone and from Revelry?
- Does it reuse infrastructure already built for another game?

### Recommended Build Order

1. **Word Association** — simplest new submission game, simultaneous play, reuses WMLT-like flow.
2. **Two Truths and a Lie** — player-authored content, sequential reveal, no AI generation needed.
3. **Chinese Whispers (text-only)** — first turn-based game, exercises turn queue infrastructure.
4. **Taboo** — team-based, uses existing team infrastructure, medium complexity.
5. **Chinese Whispers (drawing)** — builds canvas component.
6. **Pictionary** — reuses canvas from Chinese Whispers, adds real-time stroke sync + guessing.

## Gamma Environment

LocalPlay should follow the same deployment pattern as VibePix and Revelry: the backend serves both the API and the frontend, enabling a self-contained gamma environment for testing.

### How It Works

**Production** (unchanged):
- Frontend: IONOS CDN at `games.revelryapp.me/quiz/` — static Vite build
- Backend: GCP VM at `gamesapi.revelryapp.me` — API + WebSockets only

**Gamma** (new):
- A second Docker container on the same GCP VM (or Cloud Run)
- Serves both frontend and API at the same origin, e.g. `gamma-gamesapi.revelryapp.me`
- No IONOS involvement — the backend serves the built frontend directly
- Uses test Stripe keys, separate DB path (or table prefix), etc.

### Backend Serves Frontend

FastAPI mounts the built frontend as static files with an SPA fallback:

```python
# After all API routes are registered:
app.mount("/", StaticFiles(directory="static", html=True), name="static")

# SPA fallback for client-side routes (e.g. /join, /spectator):
@app.exception_handler(404)
async def spa_fallback(request, exc):
    if not request.url.path.startswith("/api/") and not request.url.path.startswith("/ws/"):
        return FileResponse("static/index.html")
    raise exc
```

### Build Configuration

The Vite build uses a placeholder for the API URL:

- **Same-origin (gamma/backend-served)**: `VITE_API_URL` is empty string — API calls go to the same origin.
- **Cross-origin (IONOS production)**: `VITE_API_URL=https://gamesapi.revelryapp.me` — API calls go to the GCP backend.

The frontend config already handles this:

```ts
const API_URL = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:9100`;
```

For same-origin serving, `VITE_API_URL` should be empty and the fallback should use the current origin:

```ts
const API_URL = import.meta.env.VITE_API_URL || '';
const WS_URL = import.meta.env.VITE_API_URL
  ? import.meta.env.VITE_API_URL.replace(/^http/, 'ws')
  : `ws://${window.location.hostname}:${window.location.port}`;
```

### Gamma Deployment

```text
Production:
  games.revelryapp.me (IONOS) → static frontend
  gamesapi.revelryapp.me (GCP) → API + WebSockets

Gamma:
  gamma-gamesapi.revelryapp.me (GCP) → API + WebSockets + frontend (same origin)
```

Gamma uses:
- Separate nginx server block on the VM
- Separate Docker container (different port, e.g. 8001)
- Separate `.env` with test Stripe keys, gamma DB path
- Same Gemini API key (free tier is fine for testing)

### Workflow

1. Develop locally (`scripts/dev-local.sh`)
2. Deploy to gamma — build frontend, copy into Docker image, deploy gamma container
3. Test full stack on `gamma-gamesapi.revelryapp.me`
4. When satisfied, deploy frontend to IONOS + backend to production container

This aligns LocalPlay with VibePix and Revelry, and sets up the integration path — Revelry can point its Games tab at the gamma URL for integration testing.

## Infrastructure Roadmap

### Current Phase: Single Server

Use a single server for now.

Why:

- Current in-memory room model is simple and fast.
- WebSocket behavior is easiest to reason about.
- Game development matters more than distributed scaling right now.

### Phase 1: Persistent Product Objects

Add persistence for:

- Game sessions.
- Generated content.
- Completed results.
- External context.

This can use SQLite first if staying on a single server.

### Phase 2: Integration Readiness

Add:

- Catalog endpoint.
- Session APIs.
- Revelry handoff token validation.
- Results retrieval.
- Basic admin/debug views for sessions.

### Phase 3: Runtime Modularization

Move game-specific runtime logic out of the main socket manager into game modules.

Goal:

- Shared WebSocket/room infrastructure remains central.
- Per-game rule code becomes easier to read, test, and add.

### Phase 4: Multi-Instance Readiness

Only when needed:

- Externalize live room state.
- Add shared pub/sub.
- Make reconnect instance-independent.
- Rework cleanup to be distributed-safe.
- Consider Cloud Run or autoscaled infrastructure.

## Spectator Mode Per Game Type

Spectator/TV display needs vary by game:

- **Quiz**: Show question, timer, answer distribution, leaderboard. (Already built.)
- **WMLT**: Show statement, vote counts, round podium. (Already built.)
- **Word Association**: Show seed word, then reveal all submissions grouped. Great for TV.
- **Chinese Whispers**: Show the chain reveal sequence. The best spectator experience — watching the chain degrade is the fun.
- **Pictionary**: Show the drawing canvas in real-time + guess stream. Ideal for TV/Chromecast.
- **Taboo**: Public spectator view should show timer, score, team, and safe round state. Do not show target/forbidden words on a shared TV by default because the guessing team may see it. A private host/judge view can show the hidden card.
- **Two Truths and a Lie**: Show statements, vote distribution, reveal which was the lie.

All games should produce a spectator-friendly live view. The existing `SPECTATOR_SYNC` pattern (send current state on connect, then stream updates) works for all game types.

## Play Pattern Classification

Games fall into several runtime patterns that affect socket_manager architecture:

### Simultaneous (all players act in same window)
- Quiz (answer)
- WMLT (vote)
- Word Association (submit word)
- Two Truths and a Lie (vote on lie)

These share: timer, round start → collect submissions → reveal → score → next round.

### Sequential (players take private turns)
- Chinese Whispers (chain of turns)

These need: turn queue, active-player tracking, per-player private prompts, and waiting state for inactive players.

### Role-Based / Turn-Led (one player has a special role)

- Pictionary (one drawer, others guess simultaneously)
- Taboo (one clue-giver, team guesses)

These need: role assignment, private role prompts, simultaneous actions from other players, and role rotation. They are not fully sequential because non-active players still act during the turn.

The socket_manager currently mainly handles simultaneous games. Sequential and role-based games will need:
- `room.turn_order: list[str]` — player order for the current round.
- `room.active_player: str` — whose private turn or special role is active.
- `room.player_roles: dict[str, str]` — current role assignment where needed.
- `TURN_START` / `TURN_END` messages.
- `ROLE_ASSIGNED` messages for role-led games.
- `WAITING_FOR_TURN` state on the player frontend.

This is the main infrastructure investment needed before Chinese Whispers or Pictionary.

## Open Design Questions

- Should LocalPlay have its own user accounts, or only anonymous users plus external handoff identities?
  - **Recommendation**: Keep anonymous fast-join as the primary path. LocalPlay identity should stay optional and mainly support host history, purchases, cross-device recovery, and external handoff identity. Never require sign-in to play.
- Should generated content be reusable across sessions?
  - **Recommendation**: Yes. Content already persists independently of rooms (quiz_id / mlt_id). Multiple rooms can reference the same content. This should continue for new games.
- Should hosts be able to build custom game packs?
  - **Recommendation**: Defer. Import/export already exists for quiz. Custom packs (curated collections of content across game types) are a Phase 3+ feature.
- Should Revelry guests appear automatically in LocalPlay player lists, or should they still join explicitly?
  - **Recommendation**: Explicit join always. Pre-populating player lists breaks the "anyone can join with a code" model and adds complexity around absent players.
- Should LocalPlay results post automatically to Revelry memories, or should the host approve?
  - **Recommendation**: Host approves. Auto-posting creates noise and privacy concerns (someone might not want their Taboo failures in the party album).
- How much game content should be family-safe by default versus configurable by audience?
  - **Recommendation**: Default to family-safe. WMLT already has the vibe system (party/spicy/wholesome/work). Extend this pattern: each game's generation has a "vibe" or "audience" selector that adjusts the LLM prompt. Spicy/adult modes should be opt-in per session.
- Should LocalPlay monetize independently, share Revelry billing, or support both?
  - **Recommendation**: Independent for now (spark economy is already built). Future Revelry integration could grant sparks to Revelry Premium subscribers, but LocalPlay's economy should remain self-contained.
- How should native app deep links route between Revelry and LocalPlay?
  - **Recommendation**: Stable LocalPlay universal links. The exact path can change, but links should support app-open when installed and browser fallback when not. Existing `/quiz/join` style links are legacy-compatible examples, not the final platform shape.
- **New: How should we handle games that need a canvas/drawing?**
  - Build a shared `<DrawingCanvas>` component that handles touch/mouse input, undo, color picker, and exports strokes as compact events. Reuse across Chinese Whispers (drawing variant) and Pictionary. Don't build it until the first drawing game is in scope.

## Near-Term Recommended Work

1. ~~Add `SPEC-PLATFORM.md` as the forward-looking design document.~~ Done.
2. Keep `SPEC.md` as current-state truth.
3. **Set up gamma environment** — FastAPI serves built frontend, nginx server block for `gamma-gamesapi.revelryapp.me`, separate Docker container. Enables testing new games end-to-end before production.
4. Add game catalog metadata for Quiz, WMLT, and planned games. Keep it static/code-backed initially.
5. Add a `/catalog` endpoint so LocalPlay and future host apps can read the same game list.
6. **Add Word Association** — first new game. Exercises text-submission + reveal pattern with minimal new infrastructure.
7. **Add Two Truths and a Lie** — player-authored content, sequential reveal, and low/no-AI flow.
8. Add a lightweight `GameSession` persistence model once the third game exposes the repeated room/session needs clearly.
9. Persist completed results in the normalized result shape.
10. **Add Chinese Whispers (text-only)** — first true private-turn game, builds turn-queue infrastructure.
11. Add drawing games (Chinese Whispers drawing variant, then Pictionary) after the turn-queue and session/result model are solid.
