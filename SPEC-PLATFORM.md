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

## Game Backlog

### Pictionary

Core loop:

- AI generates drawable prompts.
- One player draws while others guess.
- Guesses stream in real time.
- Correct guess awards points to guesser and drawer.
- Rotate drawer each round.

Needs:

- Drawing canvas.
- Stroke sync or host/player canvas broadcast.
- Guess validation.
- Prompt hiding from guessers.
- Drawing replay or final image capture for memories.

Complexity: high.

Best after at least one simpler text-submission game.

### Chinese Whispers / Telephone

Core loop:

- Start with seed phrase.
- Players alternate between writing and drawing.
- Each player only sees the previous step.
- Final chain is revealed for laughs.

Needs:

- Turn assignment.
- Private per-player prompts.
- Drawing and text submission.
- Reveal sequence.
- Strong session state model.

Complexity: medium-high.

Very strong party fit.

### Taboo Variant

Core loop:

- One player gives clues.
- Team guesses target word.
- Forbidden words cannot be used.
- Opposing team or app can mark violations.

Needs:

- Word pack generation.
- Team support.
- Timer.
- Skip/pass.
- Violation handling.
- Score by correct guesses.

Complexity: medium.

Good fit because current team mode already exists.

### Word Association

Possible loops:

- Everyone submits the first word they think of.
- Score for matching the majority.
- Or score for uniqueness.
- Or build a chain and vote on funniest/weirdest.

Needs:

- Seed word generation.
- Text submissions.
- Reveal/vote/scoring.

Complexity: low-medium.

Recommended first new game because it exercises non-quiz submissions without drawing complexity.

### Additional Game Ideas

Future games should be evaluated by:

- Does it work on phones?
- Does it need simultaneous or turn-based play?
- Does it require drawing/audio/camera?
- Can AI generate useful content?
- Can results become a memory?
- Does it work standalone and from Revelry?

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

## Open Design Questions

- Should LocalPlay have its own user accounts, or only anonymous users plus external handoff identities?
- Should generated content be reusable across sessions?
- Should hosts be able to build custom game packs?
- Should Revelry guests appear automatically in LocalPlay player lists, or should they still join explicitly?
- Should LocalPlay results post automatically to Revelry memories, or should the host approve?
- How much game content should be family-safe by default versus configurable by audience?
- Should LocalPlay monetize independently, share Revelry billing, or support both?
- How should native app deep links route between Revelry and LocalPlay?

## Near-Term Recommended Work

1. Add `SPEC-PLATFORM.md` as the forward-looking design document.
2. Keep `SPEC.md` as current-state truth.
3. Add game catalog metadata for existing Quiz and WMLT.
4. Add a `/catalog` endpoint.
5. Add a lightweight `GameSession` persistence model.
6. Persist completed results.
7. Add Word Association as the first new game.
8. Add Pictionary or Chinese Whispers after the session/result model feels solid.
