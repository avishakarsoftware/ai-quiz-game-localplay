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

Revelry should not own LocalPlay game rules. It should not need to know how DrawingGame, Chinese Whispers, Taboo, Quiz, or WMLT score a round.

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

7. **Database Isolation In Shared Infrastructure**
   - The Supabase migration should reuse the shared VibePix Supabase project, but LocalPlay objects must be namespaced.
   - Production database objects use the `games_` prefix.
   - Gamma database objects use the `games_gamma_` prefix.
   - SQLite remains the default runtime backend until gamma has proven the Supabase path.

## Core Concepts

### Game

A game is a playable format, such as:

- Quiz
- Who's Most Likely To
- DrawingGame
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
  "id": "drawing",
  "title": "Drawing Game",
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
  "game_type": "drawing",
  "source_app": "localplay",
  "external_context": null,
  "host_user_id": "optional",
  "host_display_name": "optional",
  "room_code": "ABC123",
  "status": "draft",
  "title": "Birthday Drawing Game",
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
    drawing.py
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
  drawing/
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
- DrawingGame: draw or guess.
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
- DrawingGame: drawable prompts, difficulty tiers, optional aliases.
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
- For drawing variant: canvas component (shared with DrawingGame).

Complexity: medium (text-only) to high (with drawing).

Very strong party fit. Text-only version is viable without a canvas and should ship first.

**Key architecture difference**: This is the first turn-based game. Quiz and WMLT are simultaneous (all players act in the same round window). Chinese Whispers requires a turn queue — the socket_manager needs to track whose turn it is and send prompts to one player at a time while others wait.

### DrawingGame

Detailed implementation spec: `SPEC-GAME-DRAWING.md`.

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

### Hot Takes / Would You Rather

Core loop:

- AI generates divisive opinion pairs ("pineapple on pizza: yes or no", "teleport or fly?").
- Everyone votes, live vote bars fill up on TV, then reveal the split.
- Optional: host picks a side to defend, group debates, then re-votes.

Needs:

- AI generates pairs/statements with two clear sides.
- Binary vote (reuses WMLT voting flow almost entirely).
- TV shows live vote bars filling up — visually engaging.

Complexity: low.

Nearly identical to WMLT in flow — submit vote, reveal results. The content shape is different (opinion pair vs "most likely to" statement) but the round lifecycle is the same.

### Never Have I Ever

Core loop:

- AI generates "Never have I ever…" statements (or players submit their own).
- Everyone taps "I have" or "I haven't" — reveal who did what.
- Scoring: minority group gets points (rare experiences = interesting).

Needs:

- Statement generation (AI) or player-submitted statements.
- Binary vote ("I have" / "I haven't") — simpler than WMLT multi-player voting.
- Reveal: show who's in each group, highlight the minority.
- Optional: anonymous mode where only counts are shown, not names.

Complexity: low.

Great for baby showers ("Never have I ever changed a diaper at 3am"), weddings, team building. Works with any group size.

**Event customization**: The vibe/theme system (like WMLT's party/spicy/wholesome/work) maps directly — "baby shower", "wedding", "office team building" vibes would produce appropriate statements.

### Acronym Game

Core loop:

- AI generates a random 3-5 letter acronym (e.g. "B.R.T.").
- Everyone invents what it stands for ("Big Red Tomato", "Babies Rule Tuesday").
- Anonymous reveal, group votes on funniest.

Needs:

- AI generates acronyms (trivial generation — could even be random letters).
- Text submission (simultaneous, hidden until reveal).
- Anonymous reveal with voting.
- Scoring: votes received.

Complexity: low-medium.

Exercises the "submit → anonymous reveal → vote on best" pattern that Caption This and other creative games will reuse.

### Caption This

Core loop:

- AI generates an image (using existing Stable Diffusion engine or a prompt-based image), or host uploads a photo.
- Everyone writes a caption.
- Anonymous reveal, vote on best.

Needs:

- Image display (already supported via quiz question images).
- Text submission (simultaneous, hidden until reveal).
- Anonymous reveal with voting.
- Optional: host photo upload endpoint.

Complexity: low-medium.

Could reuse the existing Stable Diffusion image engine for generated images. If host-uploaded photos are supported, this becomes a platform for custom party games.

### Scattergories

Core loop:

- AI generates a letter and a list of categories (e.g. letter "B" — animal, food, movie, city, celebrity).
- Everyone simultaneously submits one answer per category that starts with the given letter.
- Timer (60-90s for all categories).
- Reveal: answers shown per category. Duplicate answers cancel out — only unique valid answers score.
- Multiple rounds with different letters.

Needs:

- AI generates category lists (themed by vibe: party, kids, adults, work).
- Random letter selection (weighted to avoid X, Q, Z unless hard mode).
- Multi-field simultaneous submission (one text input per category, 5-8 categories per round).
- Duplicate detection across players (case-insensitive, trimmed).
- Scoring: 1 point per unique valid answer, 0 for duplicates, bonus for creative answers (optional group vote).
- TV shows the grid of all answers per category with duplicates crossed out.

Complexity: low-medium.

Strong party fit — everyone knows the format. The "unique answers only" mechanic creates natural tension and laughs when multiple people write the same thing. AI category generation keeps it fresh.

**Variant**: "Speed Scattergories" — one category at a time, shorter timer, first unique answer wins the round. Simpler to build, faster pace.

### Spy / Odd One Out

Core loop:

- Everyone gets the same location/word except one spy.
- Players take turns asking questions to find the spy.
- Spy tries to figure out the location from the questions.
- At the end: everyone votes on who the spy is, spy guesses the location.

Needs:

- Private per-player state (existing WS supports this — spy gets different content).
- AI generates location + related questions/hints.
- Question round (sequential or timed discussion).
- Voting round (who is the spy?).
- Spy's counter-guess.
- Scoring: spy wins if not caught or guesses correctly, villagers win if they catch the spy.

Complexity: medium.

Enormous replay value. Hidden roles + social deduction without the full complexity of Mafia.

### Charades (AI-Prompted)

Core loop:

- AI generates charades prompts on the actor's phone (only they see it).
- Actor performs, everyone else guesses via text input.
- Timer on TV, correct guessers + actor both score.
- Rotate actor each round.

Needs:

- Prompt generation (same as drawing prompts but optimized for acting).
- Private prompt display (actor only).
- Text guess input with forgiving matching (same as drawing game).
- Timer + guess acceptance flow (very similar to drawing game without the canvas).

Complexity: medium.

Essentially the drawing game minus the canvas. Could share the guess matching, scoring, and rotation infrastructure.

### Mafia / Werewolf (Simplified)

Core loop:

- AI assigns roles: mafia (1-2), detective, doctor, villagers.
- Night phase: mafia picks a target (phone tap), detective investigates, doctor protects.
- Day phase: discussion, then everyone votes to eliminate.
- Eliminated players become spectators.
- Game ends when all mafia are eliminated or mafia equals/outnumbers villagers.

Needs:

- Private role assignment per player.
- Night phase: sequential private actions (mafia target, detective investigate, doctor protect).
- Day phase: timed discussion + voting.
- Elimination tracking.
- TV shows the public narrative ("Last night, someone was attacked…") without revealing roles.
- Role reveal at game end.

Complexity: medium-high.

Strong demand — everyone knows Mafia. The phone-as-role-card eliminates the need for a physical moderator. AI can narrate the night events on TV.

**Key architecture need**: This is the first game where eliminated players exist as spectators mid-game. The room model needs a "dead players" concept.

### Eye Spy (Photo-Based)

Core loop:

- Host takes a photo of the room → uploads to the game.
- AI vision (Gemini multimodal) generates questions about the photo ("find something red", "count the chairs", "what brand is the laptop?").
- Players answer on their phones.
- Scoring: speed + correctness.

Needs:

- Photo upload endpoint (host camera → server).
- AI vision API call (Gemini 2.5 Flash supports image input).
- Question generation from image analysis.
- Quiz-style answer rounds.

Complexity: high.

Novel and room-contextual — every game is unique to the physical space. Strong "wow" factor. Could also work with pre-loaded images for remote play.

### Photo Scavenger Hunt

Core loop:

- AI generates a list of things to find/photograph ("something older than you", "the weirdest thing in this room", "a hidden snack").
- Players take photos with their phone camera, submit them.
- Group votes on best photo per prompt.
- Scoring: votes received + completion bonus.

Needs:

- Camera access on player phones.
- Photo upload + display.
- Voting round per prompt.
- Timer per hunt item.

Complexity: high.

Gets people moving around. Works great at parties, team events, weddings. The AI generation makes every hunt unique.

### Musical Chairs (Digital Judge)

Core loop:

- Phone plays music, random stop.
- Last person to tap "I'M SITTING" after the music stops is eliminated.
- Repeat until one player remains.

Needs:

- Audio playback (server-controlled music start/stop via WS).
- Fast tap input ("buzzer" button).
- Elimination tracking.
- TV shows countdown + eliminated players.

Complexity: low.

Very simple technically — just audio control + tap timing. But relies on the physical game happening alongside.

### Predictions (Event-Specific)

Core loop:

- Host creates prediction prompts ("What will the baby's first word be?", "How much will the baby weigh?", "What time will the bride cry?").
- Everyone submits predictions.
- Revealed later (or voted on for funniest/most likely).

Needs:

- Host-authored prompts (or AI-generated based on event type).
- Text submission per prompt.
- Reveal/voting round.
- Optional: results can be checked weeks/months later.

Complexity: low.

Perfect for baby showers, weddings, New Year's parties. Could store predictions in Supabase for later reveal.

### Rebus Puzzles

Core loop:

- AI generates rebus puzzles: combinations of images, symbols, or emoji that represent a word or phrase.
- Each round shows a rebus on the TV/phone (e.g. 🌊 + 🐴 = "seahorse", 🔥 + 🪰 = "firefly").
- Players type their guess. First correct answer scores highest (time-based).
- Rounds are fast (15-30s each), many rounds per game.

Needs:

- AI generates rebus puzzles with answer + visual components. Each puzzle is a sequence of emoji or simple image descriptions that combine to form a word/phrase.
- Display: show the emoji/images large on TV, smaller on phone.
- Text guess input with forgiving matching (same as drawing game).
- Scoring: time-based, similar to quiz.
- Optional: difficulty tiers (easy = 2 emoji, hard = 4+ emoji with wordplay).

Complexity: low-medium.

Very visual and fun. Works great on TV. AI generation is the main challenge — the LLM needs to produce emoji sequences that actually make sense as rebus clues. Could also use AI-generated images (via Stable Diffusion or Gemini image generation) for richer visual puzzles.

**Variant**: "Emoji Charades" — show only emoji, guess the movie/song/phrase. Even simpler than full rebus since it's just emoji selection, no image generation needed.

### Baby Shower / Wedding / Event Game Packs

These aren't separate game types — they're **themed content packs** for existing game mechanics:

- **How Well Do You Know the Parents/Couple?** — Custom quiz (already supported via quiz import). Need a friendlier "create your own questions" flow.
- **Baby Name Battle** — AI generates unusual baby names, group votes (Hot Takes variant).
- **Price is Right (Baby/Wedding Edition)** — Show products, guess the price. Needs numeric input (quiz variant with closest-wins scoring).
- **Predictions** — See above.

The event-specific value comes from themed AI prompts, not new game mechanics. The vibe/theme selector should support event types: "baby shower", "wedding", "birthday", "team building", "holiday party".

### Additional Game Evaluation Criteria

Future games should be evaluated by:

- Does it work on phones?
- Does it need simultaneous or turn-based play?
- Does it require drawing/audio/camera?
- Can AI generate useful content?
- Can results become a memory?
- Does it work standalone and from Revelry?
- Does it reuse infrastructure already built for another game?
- Can it work for event-specific contexts (baby showers, weddings, team building)?

### Recommended Build Order

Phase A — Low complexity, reuse existing flows:

1. **Two Truths and a Lie** — player-authored content, sequential reveal, no AI needed.
2. **Hot Takes / Would You Rather** — reuses WMLT voting flow almost entirely.
3. **Never Have I Ever** — binary vote, AI-generated statements, works for any event type.
4. **Word Association** — simultaneous text submit, majority matching.

Phase B — Medium complexity, new patterns:

5. **Rebus Puzzles** — emoji/image display + text guess. Visual, fast rounds, great on TV.
6. **Acronym Game** — introduces "submit → anonymous reveal → vote" pattern.
7. **Scattergories** — multi-field text submit, duplicate elimination scoring. Universally known format.
8. **Charades** — prompt display + guess matching, like drawing without canvas.
9. **Spy / Odd One Out** — hidden roles, social deduction.
10. **Chinese Whispers (text-only)** — first turn-based game, turn queue infrastructure.
11. **Taboo** — team-based, clue-giver rotation.

Phase C — High complexity, new capabilities:

12. **DrawingGame** — canvas + real-time stroke sync + guessing. Full spec in `SPEC-GAME-DRAWING.md`.
13. **Chinese Whispers (drawing)** — reuses canvas from DrawingGame.
14. **Mafia** — hidden roles, night/day phases, elimination.
15. **Eye Spy** — photo upload + AI vision.
16. **Photo Scavenger Hunt** — camera access + photo upload + voting.
17. **Musical Chairs** — audio playback + buzzer timing.

## Deployment Model

LocalPlay should follow the VibePix deployment pattern: the backend can serve the built frontend, but IONOS remains the user-facing production host for the public web app.

This is an implementation requirement, not just a hosting preference. The same frontend build must be usable in two modes:

- **IONOS-hosted mode**: IONOS serves the static Vite build. The frontend calls the backend API/WebSockets cross-origin.
- **Backend-served mode**: FastAPI serves the static Vite build from the same origin as API/WebSockets.

Backend-served mode is required for gamma/staging, production smoke tests, and future Cloud Run compatibility. It is not a replacement for IONOS production hosting unless a later decision explicitly changes the public URL strategy.

### Environment Shape

**Production user-facing path**:
- Frontend: IONOS CDN/shared hosting at `games.revelryapp.me/quiz/`
- Backend: GCP VM at `gamesapi.revelryapp.me`
- API mode: cross-origin from IONOS frontend to backend API/WebSockets
- Build mode: `VITE_BASE_PATH=/quiz/`, `VITE_API_URL=https://gamesapi.revelryapp.me`

**Gamma/staging path**:
- Frontend + backend: one FastAPI container origin, e.g. `gamesapi-gamma.revelryapp.me`
- Deployment target: a second Docker container on the same GCP VM initially
- API mode: same-origin API and WebSockets
- Config: test Stripe keys, separate DB path or table prefix, separate env file
- Build mode: no API base, root base path unless gamma is intentionally mounted under a subpath

**Optional backend-hosted production preview**:
- The production backend may also serve the built frontend at `gamesapi.revelryapp.me` for smoke testing before IONOS rollout.
- This should not be treated as the canonical customer URL unless a later deployment decision explicitly changes it.
- Build mode: no API base, root base path

### Required Code Changes

Implementation should be small and reversible. It should not change the room model, WebSocket protocol, game rules, or IONOS production URL.

1. **Backend static serving**
   - Add `FileResponse` and `Path` usage in `backend/main.py`.
   - Add a config/env value for the frontend build directory, defaulting to `/app/static` inside Docker and optionally `backend/static` for local packaged testing.
   - Serve the frontend only if the directory exists and contains `index.html`.
   - Register the SPA catch-all after API and WebSocket routes.
   - Preserve `/health` and all API endpoints exactly as API responses.
   - Change the current `GET /` API route so it returns the frontend `index.html` when a frontend build exists, and only returns the API status JSON when no frontend build exists.

2. **SPA fallback**
   - Return `index.html` for unknown browser routes such as `/join`, `/spectator`, and future platform routes.
   - Do not swallow API mistakes. Unknown API paths should still return 404 JSON, not the app shell.
   - Because the current backend uses top-level routes rather than only `/api/*`, the fallback must exclude known API prefixes.

3. **Frontend API base**
   - Update `frontend/src/config.ts` so deployed same-origin builds use `API_URL=''`.
   - Keep local dev ergonomic by making `scripts/dev-local.sh` pass `VITE_API_URL=http://<LAN_IP>:9100`, as it already does.
   - WebSocket same-origin fallback must derive `ws` or `wss` from `window.location.protocol`.

4. **Docker image**
   - Build the frontend before building the backend image.
   - Copy `frontend/dist/` into the backend image at `/app/static/`.
   - Keep backend data mounted separately at `/app/data` or an equivalent persistent path.

5. **Deployment scripts/docs**
   - Add a gamma deployment flow that builds the frontend in backend-served mode, builds the backend image with static files included, and runs a second container.
   - Keep the existing IONOS static deployment flow for production users.

### FastAPI Static Serving Contract

The final implementation can vary, but it must satisfy this contract:

```python
from pathlib import Path
from fastapi.responses import FileResponse

FRONTEND_DIST_DIR = Path(os.getenv("FRONTEND_DIST_DIR", "/app/static"))

API_PREFIXES = (
    "/admin",
    "/auth",
    "/checkout",
    "/entitlements",
    "/health",
    "/history",
    "/mlt",
    "/providers",
    "/purchases",
    "/quiz",
    "/room",
    "/sd",
    "/system",
    "/tokens",
    "/webhook",
    "/ws",
)

@app.get("/")
async def root():
    if (FRONTEND_DIST_DIR / "index.html").is_file():
        return FileResponse(FRONTEND_DIST_DIR / "index.html")
    return {"message": "AI Quiz Game API is running"}


# After API routes and websocket routes are registered.
@app.get("/{full_path:path}", include_in_schema=False)
async def frontend_spa(full_path: str, request: Request):
    path = request.url.path
    if any(path == prefix or path.startswith(prefix + "/") for prefix in API_PREFIXES):
        raise HTTPException(status_code=404, detail="Not found")
    if not (FRONTEND_DIST_DIR / "index.html").is_file():
        raise HTTPException(status_code=404, detail="Not found")

    frontend_root = FRONTEND_DIST_DIR.resolve()
    candidate = (frontend_root / full_path).resolve()
    try:
        candidate.relative_to(frontend_root)
    except ValueError:
        return FileResponse(FRONTEND_DIST_DIR / "index.html")
    if candidate.is_file():
        return FileResponse(candidate)
    if full_path == "assets" or full_path.startswith("assets/"):
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(FRONTEND_DIST_DIR / "index.html")
```

Notes:

- The `resolve()` + `relative_to()` check on static file candidates prevents path traversal (e.g. `../../etc/passwd`).
- Missing `/assets/*` files should return JSON 404 instead of `index.html`, so stale hashed bundles fail clearly.
- `API_PREFIXES` must be updated whenever a new top-level API namespace is added.
- If routes later move under `/api`, the fallback can become simpler, but that is not required for this deployment step.
- The catch-all route must be registered after API routes.
- If no frontend build is present, the backend should continue to run API-only. This keeps local backend tests simple.

### Frontend API Base Configuration

The frontend must support both same-origin and cross-origin API bases:

- **Same-origin backend-served build**: no API base is injected. REST calls use `''`, and WebSockets use the current page origin.
- **IONOS production build**: inject `VITE_API_URL=https://gamesapi.revelryapp.me`.
- **Local dev**: use explicit local ports from the dev scripts, currently backend `9100` and frontend `9200`.

`frontend/src/config.ts` should be implemented like this:

```ts
const explicitApiUrl = import.meta.env.VITE_API_URL;
const API_URL = explicitApiUrl || '';
const WS_URL = explicitApiUrl
  ? explicitApiUrl.replace(/^http/, 'ws')
  : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`;
const API_HOST = explicitApiUrl ? new URL(explicitApiUrl).hostname : window.location.hostname;

export { API_URL, WS_URL, API_HOST };
```

Local dev remains explicit because `scripts/dev-local.sh` sets `VITE_API_URL="http://$LAN_IP:$BACKEND_PORT"`.

### Build Commands

Use separate build commands for each serving mode.

**IONOS production frontend build**:

```bash
cd frontend
VITE_BASE_PATH=/quiz/ \
VITE_API_URL=https://gamesapi.revelryapp.me \
VITE_CAST_APP_ID=1BC9ACD8 \
npx vite build
```

Deploy `frontend/dist/*` to `~/revelryapp/games/quiz/` on IONOS as described in `DEPLOY.md`.

**Backend-served gamma/preview build**:

```bash
cd frontend
VITE_BASE_PATH=/ \
VITE_API_URL= \
VITE_CAST_APP_ID=1BC9ACD8 \
npx vite build
```

Then copy or package `frontend/dist/` into the backend image as `/app/static/`.

### Docker Image Shape

The backend image should contain both the FastAPI app and, when available, the built frontend:

```text
/app/
  main.py
  config.py
  ...
  static/
    index.html
    assets/
      *.js
      *.css
```

Recommended Dockerfile direction:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./
COPY static ./static

ENV FRONTEND_DIST_DIR=/app/static

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

The current implementation keeps `backend/Dockerfile` as the build file. For backend-served deploys, `scripts/deploy-gcp.sh --with-frontend` builds the frontend and creates a temporary Docker context where `frontend/dist` is copied into `static/` before `docker build`.

### Deployment Topology

```text
Production user-facing:
  games.revelryapp.me/quiz/ (IONOS) → static frontend
                                    → gamesapi.revelryapp.me (GCP) API + WebSockets

Gamma:
  gamesapi-gamma.revelryapp.me (GCP) → FastAPI + WebSockets + frontend (same origin)

Production backend preview:
  gamesapi.revelryapp.me (GCP) → FastAPI + WebSockets + frontend (same origin, optional)
```

Gamma uses:
- Separate nginx server block on the VM
- Separate Docker container on `127.0.0.1:8004`
- Separate `.env` with test Stripe keys, gamma DB path
- Same Gemini API key (free tier is fine for testing)
- Canonical VM home under `/home/revelry-games`

### Nginx Requirements

Each backend-served environment needs WebSocket upgrade headers and normal HTTP proxying.

Production API/preview:

```nginx
server {
    server_name gamesapi.revelryapp.me;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

Gamma should use the same shape but proxy to the gamma container port, e.g. `127.0.0.1:8004`.

### Gamma Runtime

Gamma should run as a separate container, not as a mode inside the production container.

Suggested VM container layout:

```text
games-backend        -> 127.0.0.1:8000 -> gamesapi.revelryapp.me
games-backend-gamma  -> 127.0.0.1:8004 -> gamesapi-gamma.revelryapp.me
```

Gamma env requirements:

- `ALLOWED_ORIGINS=https://gamesapi-gamma.revelryapp.me,http://localhost:9200,http://127.0.0.1:9200`
- `JWT_SECRET=<strong random secret>`
- `CHECKOUT_RETURN_URL=https://gamesapi-gamma.revelryapp.me/`
- `TRUST_PROXY_HEADERS=true`
- `GEMINI_MODEL=gemini-2.5-flash-lite`
- `GEMINI_PREMIUM_MODEL=gemini-2.5-flash-lite`
- `REMOTE_CONFIG_URL=https://gamesapi-gamma.revelryapp.me/config.json`
- `GOOGLE_CLIENT_ID=458966837298-9hjencou1ag2o17ln06iuuj86j5p8igj.apps.googleusercontent.com`
- `APPLE_CLIENT_ID=me.revelryapp.quiz.web`
- `APPLE_CLIENT_IDS=me.revelryapp.quiz.web,me.revelryapp.quiz`
- test Stripe keys and webhook secret
- distinct mounted data directory; current gamma should set `DB_DIR=/app/data` and mount `/home/revelry-games/revelry-data-gamma:/app/data`
- same Gemini key unless a separate quota is desired
- lower rate limits are acceptable for testing

Production env should include both user-facing and backend-preview origins:

- `ALLOWED_ORIGINS=https://games.revelryapp.me,https://gamesapi.revelryapp.me,capacitor://localhost,http://localhost,https://localhost,http://localhost:9200,http://127.0.0.1:9200`
- `JWT_SECRET=<strong random secret>`
- `TRUST_PROXY_HEADERS=true`
- `GEMINI_MODEL=gemini-2.5-flash-lite`
- `GEMINI_PREMIUM_MODEL=gemini-2.5-flash-lite`
- `REMOTE_CONFIG_URL=https://games.revelryapp.me/quiz/config.json`
- `GOOGLE_CLIENT_ID=458966837298-9hjencou1ag2o17ln06iuuj86j5p8igj.apps.googleusercontent.com`
- `APPLE_CLIENT_ID=me.revelryapp.quiz.web`
- `APPLE_CLIENT_IDS=me.revelryapp.quiz.web,me.revelryapp.quiz`
- keep any existing `revelryapp.me` origins that are still needed for compatibility
- CORS origins are scheme + host + optional port only; do not include `/quiz/`.
- Deployed env vars and remote `config.json` override code defaults; free and premium model settings should both stay on `gemini-2.5-flash-lite`.

OAuth provider consoles must also trust every SPA origin:

- Google OAuth Web Client authorized JavaScript origins: `https://games.revelryapp.me`, `https://gamesapi.revelryapp.me`, `https://gamesapi-gamma.revelryapp.me`, `http://localhost:5173`, `http://localhost:9200`, `http://127.0.0.1:9200`
- Google redirect URI compatibility entries, if used: the same web roots plus the Firebase handler `https://revelryapp.firebaseapp.com/__/auth/handler`
- Apple Sign in with Apple Service ID `me.revelryapp.quiz.web` domains: `games.revelryapp.me`, `gamesapi.revelryapp.me`, `gamesapi-gamma.revelryapp.me`
- Apple return URLs: `https://games.revelryapp.me`, `https://gamesapi.revelryapp.me`, `https://gamesapi-gamma.revelryapp.me`

Backend-served builds leave `VITE_APPLE_REDIRECT_URI` blank so the Apple JS SDK uses the current origin. IONOS `/quiz/` builds may keep `VITE_APPLE_REDIRECT_URI=https://games.revelryapp.me`.

`JWT_SECRET` is required after provider token verification. Without it, Google/Apple can succeed but `/auth/signin` still fails because the backend cannot create the app session token.

### Workflow

1. Develop locally (`scripts/dev-local.sh`)
2. Deploy to gamma by building the frontend into the Docker image and starting the gamma container
3. Test full stack on `gamesapi-gamma.revelryapp.me`
4. Deploy the backend to the production container and test the optional backend-hosted production preview
5. When satisfied, deploy the static frontend build to IONOS for real users

Users on IONOS are not affected until the IONOS static deploy happens. This mirrors VibePix: Cloud Run or server-served pages are useful staging surfaces, while IONOS is the public web delivery path.

### Acceptance Checks

Before calling the implementation done:

- `curl -s https://gamesapi-gamma.revelryapp.me/health` returns backend health JSON.
- `curl -s https://gamesapi-gamma.revelryapp.me/ | head` returns HTML.
- `curl -sI https://gamesapi-gamma.revelryapp.me/assets/<built-asset>` returns `200`.
- Browser refresh works on `/join`, `/spectator`, and organizer routes.
- WebSocket join works from the backend-served gamma page.
- Unknown API paths such as `/quiz/not-real/export` return JSON 404, not `index.html`.
- IONOS production still loads from `https://games.revelryapp.me/quiz/`.
- IONOS production still calls `https://gamesapi.revelryapp.me` for API/WebSockets.
- Existing backend tests pass with no frontend build present.
- The deployed production container can still run API-only if `/app/static/index.html` is missing.

### Implementation Status

Done in repo:

- `frontend/src/config.ts` supports explicit API URLs and same-origin backend-served builds.
- `backend/main.py` conditionally serves the SPA and keeps API routes protected.
- `backend/Dockerfile` includes `/app/static`.
- `scripts/deploy-gcp.sh` supports `--with-frontend` and `--gamma --with-frontend`.
- `scripts/deploy-gcp.sh` supports `--bootstrap-vm` for `/home/revelry-games` and builds VM images for `linux/amd64`.
- `DEPLOY.md` documents the operational flow.
- Backend tests cover the SPA serving edge cases.

Deployed outside the repo:

1. DNS and SSL exist for `gamesapi.revelryapp.me` and `gamesapi-gamma.revelryapp.me`.
2. Nginx routes production to `127.0.0.1:8000` and gamma to `127.0.0.1:8004`.
3. `/home/revelry-games` is the canonical LocalPlay VM home.
4. `games-backend` and `games-backend-gamma` are deployed with bundled SPA assets.
5. Production and gamma `/health`, root SPA HTML, client-route fallback, assets, and `/providers` API JSON have been smoke-tested.

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
- **DrawingGame**: Show the drawing canvas in real-time + guess stream. Ideal for TV/Chromecast.
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

- DrawingGame (one drawer, others guess simultaneously)
- Taboo (one clue-giver, team guesses)

These need: role assignment, private role prompts, simultaneous actions from other players, and role rotation. They are not fully sequential because non-active players still act during the turn.

The socket_manager currently mainly handles simultaneous games. Sequential and role-based games will need:
- `room.turn_order: list[str]` — player order for the current round.
- `room.active_player: str` — whose private turn or special role is active.
- `room.player_roles: dict[str, str]` — current role assignment where needed.
- `TURN_START` / `TURN_END` messages.
- `ROLE_ASSIGNED` messages for role-led games.
- `WAITING_FOR_TURN` state on the player frontend.

This is the main infrastructure investment needed before Chinese Whispers or DrawingGame.

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
  - Build a shared `<DrawingCanvas>` component that handles touch/mouse input, undo, color picker, and exports strokes as compact events. Reuse across Chinese Whispers (drawing variant) and DrawingGame. Don't build it until the first drawing game is in scope. See `SPEC-GAME-DRAWING.md`.

## Near-Term Recommended Work

1. ~~Add `SPEC-PLATFORM.md` as the forward-looking design document.~~ Done.
2. Keep `SPEC.md` as current-state truth.
3. ~~Set up dual-serving deployment in repo.~~ Done. Remaining work is VM/nginx/DNS gamma rollout.
4. **Migrate from SQLite to Supabase** — VibePix already uses Supabase; shared infra across projects simplifies Revelry integration, enables gamma/prod isolation via table prefixes (like VibePix's `vp_` / `vp_gamma_`), and removes the single-server data durability risk. Schema is small (wallets, users, transactions, game history). Do this soon after the gamma environment is live.
5. Add game catalog metadata for Quiz, WMLT, and planned games. Keep it static/code-backed initially.
6. Add a `/catalog` endpoint so LocalPlay and future host apps can read the same game list.
7. **Add Word Association** — first new game. Exercises text-submission + reveal pattern with minimal new infrastructure.
8. **Add Two Truths and a Lie** — player-authored content, sequential reveal, and low/no-AI flow.
9. Add a lightweight `GameSession` persistence model once the third game exposes the repeated room/session needs clearly.
10. Persist completed results in the normalized result shape.
11. **Add Chinese Whispers (text-only)** — first true private-turn game, builds turn-queue infrastructure.
12. Add drawing games (Chinese Whispers drawing variant, then DrawingGame) after the turn-queue and session/result model are solid.
