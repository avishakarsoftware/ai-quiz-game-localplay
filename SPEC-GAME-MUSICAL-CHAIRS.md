# LocalPlay Musical Chairs Game Spec

## Overview

Add a digital **Musical Chairs** game to LocalPlay. The classic party game translates to a phone-based elimination game: music plays with rising tension, stops at a random moment, and players race to tap their screen to "grab a chair." The slowest player each round is eliminated until one winner remains.

This is not a quiz variant. Musical Chairs is a separate runtime family like Drawing and Housie, with its own round model, elimination mechanic, and audio layer.

```text
GameType: musical_chairs
Backend engine: musical_chairs_engine.py
Frontend display name: Musical Chairs
```

## Implementation-Ready MVP Scope

Status: implementation-ready for standalone LocalPlay first.

The current MVP ships two gameplay modes plus a hosted-audio built-in music player:

- `musical_chairs` is a first-class standalone game type and appears in the standalone catalog.
- Room creation is setup-only. It does not use AI generation and does not require content authoring.
- Revelry/host-app launch is explicitly deferred; host-app catalog responses should keep this game hidden until the bridge contract is added and tested.
- Minimum start requirement is 3 connected players.
- `physical` gameplay mode is the default: LocalPlay starts the round, stops at a random time, players scramble for real chairs, and the host chooses who is out.
- `digital` gameplay mode keeps the phone-tap race: LocalPlay opens a grab window after the stop signal and eliminates the slowest/no-tap player automatically.
- The backend owns all authoritative round state:
  - `MC_BETWEEN_ROUNDS`: host can start the next round.
  - `MC_MUSIC`: music/visual rhythm is active; taps are ignored.
  - `MC_GRAB`: digital mode stop signal has fired; players can tap once.
  - `MC_PHYSICAL_ELIMINATION`: physical mode stop signal has fired; host chooses who is out.
  - `MC_REVEAL`: slowest/no-tap player is eliminated.
  - `PODIUM`: winner is crowned.
- Organizer controls: start round, stop music manually, end game.
- Built-in mode streams a selected short loop from IONOS media storage, starts it from the host's Start Round tap, and stops it when the server stop cue arrives.
- External mode lets the host use their own playlist and manually stop the round.
- In physical mode, player devices show instructions and do not offer a tap target; in digital mode, player devices show a large grab button only during `MC_GRAB`.
- Spectator/TV shows the visualizer, active players, chairs remaining, and reveal state.
- Scoring is survival order: the final active player wins, then eliminated players are ranked by reverse elimination order.

MVP acceptance criteria:

- A standalone host can choose Musical Chairs, pick physical or phone-tap mode, configure basic timing/music options, create a room, and start with 3+ players.
- Players can join, reconnect into the current state, tap during the grab phase, and see eliminated/surviving state.
- In digital mode, the server ranks taps by server receipt time and eliminates the slowest/no-tap player while keeping at least one player alive.
- In physical mode, the server waits for the host to select the eliminated player after the stop signal.
- Organizer, player, and spectator receive `MC_SYNC`/round event updates.
- The game reaches the normal podium flow without touching quiz/WMLT/drawing/bingo paths.

## Goals

- Add `musical_chairs` as a first-class `GameType`.
- Provide built-in hosted music loops and randomized stop timing without increasing the web/native app bundle size.
- Support an external music mode where the host plays their own music and the app handles timing/game logic only.
- Elimination-based rounds: N players, N-1 chairs, last to tap is out.
- Support organizer, player, and spectator surfaces.
- Spectator/TV should be the musical centerpiece: show the music visualizer, countdown drama, elimination reveals, and final winner.
- Keep the implementation simple and process-local for the current VM deployment.

## Non-Goals

- No Spotify, Apple Music, or YouTube integration in v1.
- No bundled audio files in v1; built-in tracks live on IONOS media storage and are streamed by URL.
- No AI-generated music in v1.
- No team mode in v1.
- No custom music upload in v1.
- No Revelry/host-app launch until standalone is tested.
- No autoscaled Cloud Run support in v1.

## Music Source Strategy

Music is the core of Musical Chairs. The MVP uses a two-mode approach.

### Mode 1: Built-In Music (Default)

Use short hosted loop files selected from the Musical Chairs setup screen. This is the default because:

- Zero licensing cost or legal risk.
- Zero app bundle growth: files are not packaged into the Vite build or native shell.
- Runs on all modern browsers including iOS Safari after a host tap.
- The track list can be updated independently of app deployments.
- Style categories remain simple for hosts: upbeat, jazzy, suspense, retro, tropical.

Implementation approach:

- Track manifest lives in `frontend/src/audio/musicalChairsTracks.ts`.
- Files live at `https://media.revelryapp.me/apps/localplay/music/{track_id}.wav`.
- The organizer/host page owns playback via an HTML audio element. Player phones do NOT play music.
- The selected `music_track_id` is stored in the room config and included in `MC_SYNC` so reconnecting hosts keep the same selection.
- The selected `music_track_id` is the starting track for the game. Each new round rotates to the next loop in the selected style so the music does not repeat the exact same loop every round.
- Music starts from the same user gesture as Start Round to satisfy mobile autoplay policies.
- Music stops immediately when the server transitions out of `MC_MUSIC` or when the host presses Stop Music.
- A visual rhythm/stop cue remains required because audio alone is not accessible.

Current MVP track set:

- Upbeat: Confetti Pop, Bounce Around, Neon Hop, Sprinkles.
- Jazzy: Lounge Shuffle, Tiny Swing, Walking Bass, Piano Wink.
- Suspense: Tiptoe Tension, Clock Chase, Pulse Runner, Sting Loop.
- Retro: Arcade Glow, Wave Runner, Pixel Steps, Cassette Dash.
- Tropical: Island Steps, Sun Parade, Breeze Bounce, Mango Walk.

Fallback if hosted audio cannot play: the organizer sees the visual-only pulsing animation and can continue in practice as external music mode.

### Mode 2: External Music (Host's Own Music)

The host plays music from any external source (Bluetooth speaker, Spotify on another device, vinyl, live guitar — whatever). The app provides:

- A large "STOP MUSIC" button for the organizer.
- Optional auto-stop: the app picks a random stop time within a configured window and alerts the organizer to stop their music.
- The app handles all game logic: elimination, scoring, drama reveals.

This mode is valuable because:

- Hosts can use their party playlist.
- Works in noisy venues where phone speakers are inadequate.
- Familiar to anyone who has played traditional musical chairs.

Setup option:

```json
{
  "gameplay_mode": "physical" | "digital",
  "music_mode": "builtin" | "external",
  "music_style": "upbeat" | "jazzy" | "suspenseful" | "retro" | "tropical",
  "music_track_id": "upbeat-confetti",
  "auto_stop": true
}
```

When `music_mode` is `external`, the server still controls round timing and randomized stop windows, but music playback is the host's responsibility.

### Why Not Bundled Audio Files

Bundled clips were considered and rejected for v1:

- Licensing: royalty-free music libraries have varying terms; some restrict commercial use, redistribution, or require attribution in ways that conflict with app store distribution.
- Storage: even short loops add up across styles. IONOS media hosting keeps the app bundle small.
- Staleness: a fixed set of clips gets repetitive. Procedural generation can vary every round.
- Offline: bundled files in the service worker cache would bloat the PWA install.

Bundled high-quality audio loops remain a future option only if offline Musical Chairs becomes important.

### Why Not Streaming Services

Spotify, Apple Music, YouTube, etc. were rejected for v1:

- OAuth/auth complexity per provider.
- Playback restrictions (Spotify Web Playback SDK requires Premium).
- Regional availability.
- Licensing gray areas for synchronized game mechanics.
- Network dependency for a local-party game.

A future "connect your Spotify" feature could replace the built-in audio, but it should be additive, not required.

## Game Rules

### Participants

- Host: creates the game, controls music/rounds, sees elimination controls.
- Players: race to tap when music stops. Eliminated players become spectators.
- Spectator: TV/large screen shows the music visualizer, active players, and elimination drama.

### Round Flow

1. Host starts the round. Music begins playing (built-in or external).
2. Players see a "waiting" screen with a pulsing visual. They know music is playing but cannot predict when it stops.
3. After a random interval within the configured window, the server sends the STOP signal.
4. Built-in mode: music fades out on the organizer/spectator. External mode: organizer gets a "STOP NOW" alert.
5. Players see a "GRAB A CHAIR!" button appear on their screen. They tap as fast as possible.
6. Server collects tap timestamps. The slowest player (or players, if multiple chairs are removed) is eliminated.
7. Elimination reveal: dramatic pause, then the eliminated player is announced on all surfaces.
8. Eliminated players become spectators for the rest of the game. They can still watch on their phone.
9. Next round begins with one fewer chair.
10. Final round: 2 players, 1 chair. Winner is crowned.

### Timing

Music play duration per round should be randomized within a window:

```json
{
  "min_music_seconds": 60,
  "max_music_seconds": 300,
  "grab_window_seconds": 5
}
```

- `min_music_seconds` / `max_music_seconds`: the server picks a random stop time within this range each round.
- Setup shows this window in minutes. The product default is 1 minute minimum and 5 minutes maximum.
- Backend validation accepts a minimum as low as 5 seconds for tests/debugging, but the product default is minutes-oriented for real physical play.
- `grab_window_seconds`: how long players have to tap after the stop signal. After this window closes, any player who hasn't tapped is automatically eliminated.
- As rounds progress and fewer players remain, the grab window should tighten slightly (e.g., -0.5s per elimination, floor of 2s) to increase tension.

### Elimination Rules

- Default: 1 player eliminated per round (classic musical chairs).
- Optional speed mode: eliminate the bottom N players per round for faster games with large groups. Configurable in setup.
- Ties at the elimination boundary: if two players tap at the exact same server-received millisecond, both survive that round and an extra player is eliminated next round. This is generous by design — punishing ties feels unfair.
- If a player disconnects during an active round, they are automatically eliminated unless they reconnect within the grab window.

### Tap Validation

- The server records the timestamp when each player's GRAB message arrives.
- Players are ranked by arrival order, not client-reported timestamps. Client clocks are untrusted.
- Only one GRAB per player per round is accepted. Subsequent taps are ignored.
- GRAB messages received before the STOP signal are rejected (no pre-tapping).
- GRAB messages received after the grab window closes are treated as non-taps (eliminated).

## Content Model

Musical Chairs does not require LLM-generated content. The "content" is the game configuration:

```json
{
  "game_title": "Musical Chairs",
  "music_mode": "builtin",
  "music_style": "upbeat",
  "music_track_id": "upbeat-confetti",
  "min_music_seconds": 60,
  "max_music_seconds": 300,
  "grab_window_seconds": 5,
  "eliminations_per_round": 1,
  "auto_stop": true,
  "intensity_ramp": true
}
```

### TypeScript

Extend:

```ts
export type GameType = 'quiz' | 'wmlt' | 'drawing' | 'housie' | 'musical_chairs';
```

Add:

```ts
export interface MusicalChairsConfig {
  game_title: string;
  music_mode: 'builtin' | 'external';
  music_style: 'upbeat' | 'jazzy' | 'suspenseful' | 'retro' | 'tropical';
  music_track_id?: string;
  min_music_seconds: number;
  max_music_seconds: number;
  grab_window_seconds: number;
  eliminations_per_round: number;
  auto_stop: boolean;
  intensity_ramp: boolean;
}

export interface MusicalChairsRoundResult {
  round_number: number;
  total_rounds: number;
  eliminated_players: string[];
  tap_order: Array<{ nickname: string; rank: number; reaction_ms: number }>;
  remaining_players: string[];
  grab_window_seconds: number;
}
```

### Backend Runtime Shape

```python
room.game_type = "musical_chairs"
room.quiz = musical_chairs_config  # reuse generic content field
room.mc_music_mode = "builtin"
room.mc_music_style = "upbeat"
room.mc_music_track_id = "upbeat-confetti"
room.mc_active_players: list[str] = []      # players still in the game
room.mc_eliminated_players: list[str] = []  # elimination order
room.mc_round_number: int = 0
room.mc_round_active: bool = False
room.mc_stop_time: Optional[float] = None   # when server decided to stop
room.mc_grab_deadline: Optional[float] = None
room.mc_grabs: dict[str, float] = {}        # player_id -> server timestamp
room.mc_music_task: Optional[asyncio.Task] = None  # auto-stop timer
room.mc_grab_window_seconds: float = 5.0
room.mc_eliminations_per_round: int = 1
room.mc_intensity_ramp: bool = True
room.mc_auto_stop: bool = True
room.mc_min_music_seconds: int = 5
room.mc_max_music_seconds: int = 20
```

## REST API

Musical Chairs does not need a generation endpoint since there is no LLM content. Room creation accepts the config directly.

### Room Creation

`POST /room/create` with:

```json
{
  "game_type": "musical_chairs",
  "time_limit": 5,
  "musical_chairs_config": {
    "music_mode": "builtin",
    "music_style": "upbeat",
    "music_track_id": "upbeat-confetti",
    "min_music_seconds": 60,
    "max_music_seconds": 300,
    "grab_window_seconds": 5,
    "eliminations_per_round": 1,
    "auto_stop": true,
    "intensity_ramp": true
  }
}
```

The backend validates config bounds and stores it. No content id is needed since the config is embedded in the room.

Validation:

- `min_music_seconds` clamped to 5-600.
- `max_music_seconds` clamped to `min_music_seconds`+1 to 900.
- `grab_window_seconds` clamped to 2-10.
- `eliminations_per_round` clamped to 1 to `floor(active_players / 2)`.
- `music_style` must be a known style.
- `music_track_id` is optional and sanitized; if missing, the backend chooses the default track for the selected style.
- `music_mode` must be `builtin` or `external`.

### Spark Economy

Musical Chairs does not require content generation, so `COST_GENERATE` does not apply.

`COST_ROOM` still applies when the game starts, same as other game types.

If LLM features are added later (AI-generated round themes, commentary, etc.), generation costs would be added at that point.

## WebSocket Protocol

### Organizer Messages To Server

- `START_GAME`
  - Validates minimum player count (`MIN_MC_PLAYERS = 3`).
  - Initializes `mc_active_players` from connected players.
  - Charges `COST_ROOM`.
  - Broadcasts `GAME_STARTING`.

- `MC_START_ROUND`
  - Begins music on clients (built-in mode) or signals the host to start music (external mode).
  - Server picks a random stop time.
  - If `auto_stop` is true, server schedules the stop. If false, host must manually trigger stop.

- `MC_STOP_MUSIC`
  - Manual stop trigger (external mode or manual override in built-in mode).
  - Only valid during an active round before auto-stop fires.

- `MC_NEXT_ROUND`
  - After elimination reveal, starts the next round.

- `END_QUIZ`
  - Ends the game early. Broadcasts `PODIUM`.

### Player Messages To Server

- `JOIN`
  - Standard join flow.

- `MC_GRAB`
  - Sent when the player taps the grab button after music stops.
  - Server records arrival timestamp.
  - Rejected if: round not active, music hasn't stopped, player already grabbed, player is eliminated.

### Server Messages To Clients

- `MC_ROUND_START`
  - Signals a new round is beginning.

```json
{
  "type": "MC_ROUND_START",
  "round_number": 3,
  "total_rounds": 7,
  "active_players": ["Avi", "Sam", "Maya", "Jo", "Lee"],
  "chairs": 4,
  "music_mode": "builtin",
  "music_style": "suspenseful",
  "intensity": 0.6,
  "grab_window_seconds": 4.5
}
```

- `MC_MUSIC_STOP`
  - Music has stopped. Players must grab.

```json
{
  "type": "MC_MUSIC_STOP",
  "grab_deadline_ms": 4500
}
```

- `MC_GRAB_CONFIRMED`
  - Sent to the grabbing player.

```json
{
  "type": "MC_GRAB_CONFIRMED",
  "rank": 2,
  "reaction_ms": 342
}
```

- `MC_GRAB_COUNT`
  - Broadcast to organizer and spectators as grabs come in.

```json
{
  "type": "MC_GRAB_COUNT",
  "grabbed": 4,
  "total": 5
}
```

- `MC_ROUND_OVER`
  - Elimination reveal.

```json
{
  "type": "MC_ROUND_OVER",
  "round_number": 3,
  "tap_order": [
    { "nickname": "Sam", "rank": 1, "reaction_ms": 187 },
    { "nickname": "Maya", "rank": 2, "reaction_ms": 342 },
    { "nickname": "Avi", "rank": 3, "reaction_ms": 510 },
    { "nickname": "Jo", "rank": 4, "reaction_ms": 823 }
  ],
  "eliminated": ["Lee"],
  "remaining_players": ["Sam", "Maya", "Avi", "Jo"],
  "is_final": false
}
```

- `MC_ELIMINATED`
  - Sent to the eliminated player specifically.

```json
{
  "type": "MC_ELIMINATED",
  "round_number": 3,
  "final_rank": 5,
  "reaction_ms": null,
  "reason": "slowest_tap"
}
```

Reasons: `slowest_tap`, `no_tap`, `disconnected`.

- `MC_WINNER`
  - Final round winner announcement.

```json
{
  "type": "MC_WINNER",
  "winner": "Sam",
  "total_rounds": 7
}
```

- `PODIUM`
  - Reuse existing podium with elimination-order ranking.

```json
{
  "type": "PODIUM",
  "game_type": "musical_chairs",
  "leaderboard": [
    { "nickname": "Sam", "rank": 1, "survived_rounds": 7 },
    { "nickname": "Maya", "rank": 2, "survived_rounds": 6 },
    { "nickname": "Avi", "rank": 3, "survived_rounds": 5 }
  ]
}
```

### Spectator Sync

`SPECTATOR_SYNC` should include Musical Chairs state when a spectator joins mid-game:

```json
{
  "type": "SPECTATOR_SYNC",
  "game_type": "musical_chairs",
  "round_number": 3,
  "active_players": ["Avi", "Sam", "Maya", "Jo"],
  "eliminated_players": ["Lee", "Chris", "Pat"],
  "phase": "music_playing",
  "music_mode": "builtin",
  "music_style": "suspenseful",
  "intensity": 0.6
}
```

## Frontend UX

### Setup Screen

`frontend/src/components/organizer/MusicalChairsSetupScreen.tsx`

Fields:

- Game title (default: "Musical Chairs").
- Music mode: Built-in / External.
- Music style picker (built-in mode only): visual cards for each style with a short preview.
- Music duration range slider (min/max seconds).
- Grab window slider.
- Eliminations per round (1 for classic, more for speed mode).
- Intensity ramp toggle.

No generation needed — "Create Room" goes directly to room creation.

This means Musical Chairs skips the LOADING and REVIEW organizer states. Setup -> Room.

### Organizer In-Game

`frontend/src/components/organizer/MusicalChairsGameScreen.tsx`

- Large "Start Round" / "Stop Music" button (context-dependent).
- Active player count and list.
- Current round / total rounds.
- Grab progress: "3/5 players grabbed."
- Elimination reveal with dramatic pause.
- "Next Round" button after reveal.
- "End Game" button.
- Music visualizer (built-in mode).

### Player In-Game

Active player states:

- `MC_WAITING`: Music is playing. Screen shows a pulsing visual sync'd to the beat. Text: "Listen to the music..." or "Get ready..."
- `MC_GRAB`: Music stopped. Large tap target appears. "GRAB A CHAIR!" — full screen, impossible to miss.
- `MC_GRABBED`: Player has tapped. Shows their reaction time and rank so far.
- `MC_SAFE`: Round over, player survived. Shows elimination reveal.
- `MC_OUT`: Player was eliminated. Shows their final rank and a "Watch the rest!" message. Transitions to spectator-like view.

Eliminated player states:

- `MC_SPECTATING`: Can see the game progress, active players, and round results. Cannot tap.

### Spectator / TV

The spectator screen is the most important surface for Musical Chairs. It should feel like a game show.

- **During music**: Large animated visualizer with player avatars arranged in a circle (virtual chairs). Pulsing to the beat. Player count. Round number.
- **Music stops**: Flash "GRAB!" across the screen. Show chairs disappearing animation.
- **Grab phase**: Live grab counter. Player avatars light up as they grab.
- **Elimination reveal**: Dramatic pause (2-3 seconds). Then the eliminated player's name/avatar is shown with an "OUT!" animation. Remaining players shown.
- **Final round**: Special "FINAL SHOWDOWN" treatment. Two players, one chair. Huge reaction time reveal.
- **Winner**: Confetti, winner name, crown animation.

### Drawing Canvas / Visualizer Component

`frontend/src/components/musical-chairs/MusicVisualizer.tsx`

A visual component that responds to Musical Chairs phase/intensity:

- Circular player/chair visualizer with pulse energy.
- Syncs to the current phase and rough intensity.
- Intensity parameter controls visual energy.
- Does not require audio analysis in the hosted-track MVP.

`frontend/src/components/musical-chairs/GrabButton.tsx`

- Full-screen tap target.
- Appears only after `MC_MUSIC_STOP`.
- Shows reaction time after tap.
- Disabled after first tap.
- Accessible: large, high contrast, screen reader label.

## Hosted Audio Implementation

### Architecture

```text
frontend/src/audio/
  musicalChairsTracks.ts — hosted IONOS track manifest

scripts/
  generate-musical-chairs-loops.mjs — local generator for the 20 MVP loop files

IONOS:
  ~/revelryapp/media/apps/localplay/music/
  https://media.revelryapp.me/apps/localplay/music/
```

### Music Player Contract

```ts
type MusicalChairsTrack = {
  id: string;
  title: string;
  style: MusicalChairsMusicStyle;
  bpm: number;
  url: string;
};
```

Playback rules:

- Use one looping `HTMLAudioElement` on the organizer host screen.
- Start playback only inside or immediately after the Start Round user gesture.
- Stop playback on `MC_STOP_MUSIC`, `MC_PHYSICAL_ELIMINATION`, `MC_GRAB`, `MC_REVEAL`, `PODIUM`, unmount, or track change.
- If `audio.play()` is blocked, keep the game usable and show copy telling the host to tap Start Round again.
- Do not preload all tracks; only preload the selected track.

### Browser Audio Considerations

- Browser audio must start from a user gesture. The organizer "Start Round" tap satisfies this requirement.
- If playback is blocked or interrupted by backgrounding, the game continues with visual cues and the next Start Round tap retries audio.
- Silent/mute switch behavior varies by device and browser. Keep visible rhythm/stop cues as the source of truth.
- Player phones stay silent; the host/organizer device or TV supplies the room audio.

### iOS Safari Considerations

- `AudioContext` must be created and resumed on a user gesture.
- The organizer "Start Round" tap satisfies this requirement.
- If the context is suspended (backgrounding), resume on the next user interaction.
- Test with silent mode (mute switch) on iOS — Web Audio still plays through the media channel, but users may need to unmute.

## Scoring and Leaderboard

Musical Chairs uses elimination order rather than point accumulation:

- Last player standing wins (rank 1).
- Second-to-last eliminated is rank 2, etc.
- First eliminated is last place.

For the podium, map elimination order to ranks. The leaderboard shows:

```json
[
  { "nickname": "Sam", "rank": 1, "survived_rounds": 7, "avg_reaction_ms": 245 },
  { "nickname": "Maya", "rank": 2, "survived_rounds": 6, "avg_reaction_ms": 312 },
  { "nickname": "Avi", "rank": 3, "survived_rounds": 5, "avg_reaction_ms": 478 }
]
```

Optional fun stats for the podium:

- Fastest single reaction time.
- Most consistent (lowest reaction time variance).
- "By a hair" — closest near-elimination survival.

## Room State

Musical Chairs uses distinct phases, not the quiz `QUESTION`/`LEADERBOARD` cycle:

- `LOBBY` — standard.
- `MC_MUSIC` — music is playing, waiting for stop.
- `MC_GRAB` — music stopped, players racing to tap.
- `MC_REVEAL` — elimination reveal.
- `MC_BETWEEN_ROUNDS` — organizer can start next round.
- `PODIUM` — game complete.

## Constraints

- Minimum players: 3. Musical chairs with 2 players is just a single round.
- Maximum players: same as `MAX_PLAYERS_PER_ROOM`.
- Musical Chairs has exactly `N-1` rounds for `N` starting players (or fewer if multiple eliminations per round).

## Backend Implementation

### Files

Add or update:

- `backend/musical_chairs_engine.py`
  - Pure game logic: round state, elimination, grab ranking, config validation.
  - No FastAPI, WebSocket, or database imports.
- `backend/socket_manager.py`
  - Add `musical_chairs` runtime branch to `Room`.
  - Add MC state fields, round lifecycle, grab collection, elimination logic.
  - Handle auto-stop timer as an `asyncio.Task`.
- `backend/main.py`
  - Accept `game_type = "musical_chairs"` in room creation.
  - Validate `musical_chairs_config`.
  - Add catalog metadata.
- `backend/config.py`
  - Add `MIN_MC_PLAYERS = 3`.
  - Add `MC_MIN_MUSIC_SECONDS = 3`, `MC_MAX_MUSIC_SECONDS = 60`.
  - Add `MC_MIN_GRAB_WINDOW = 2`, `MC_MAX_GRAB_WINDOW = 10`.
- `backend/tests/test_musical_chairs_engine.py`
  - Pure engine tests.
- `backend/tests/test_musical_chairs_ws.py`
  - WebSocket flow tests.

### Frontend Files

Add or update:

- `frontend/src/types.ts` — add `musical_chairs` to `GameType`, add MC types.
- `frontend/src/gameModes.ts` — add Musical Chairs catalog entry.
- `frontend/src/audio/musicEngine.ts` — Web Audio engine.
- `frontend/src/audio/proceduralStyles.ts` — style registry.
- `frontend/src/audio/styles/*.ts` — individual style generators.
- `frontend/src/components/organizer/MusicalChairsSetupScreen.tsx` — setup form.
- `frontend/src/components/organizer/MusicalChairsGameScreen.tsx` — in-game host controls.
- `frontend/src/components/player/MusicalChairsPlayer.tsx` — player round UI.
- `frontend/src/components/spectator/MusicalChairsSpectator.tsx` — TV surface.
- `frontend/src/components/musical-chairs/MusicVisualizer.tsx` — audio visualizer.
- `frontend/src/components/musical-chairs/GrabButton.tsx` — tap target.
- `frontend/src/components/musical-chairs/EliminationReveal.tsx` — dramatic reveal.
- `frontend/src/components/musical-chairs/PlayerCircle.tsx` — visual player arrangement.
- `frontend/src/pages/OrganizerPage.tsx` — add MC setup + game branches.
- `frontend/src/pages/PlayerPage.tsx` — add MC player branches.
- `frontend/src/pages/SpectatorPage.tsx` — add MC spectator branch.

## Reconnect Behavior

- Player reconnect during `MC_MUSIC`: rejoin as active, will see next stop.
- Player reconnect during `MC_GRAB`: if within grab window, can still tap. If window passed, treated as no-tap.
- Player reconnect during `MC_REVEAL` or `MC_BETWEEN_ROUNDS`: receive current state.
- Eliminated player reconnect: placed in spectator view.
- Organizer reconnect: full MC state sync, music task pauses during grace period.

## History and Results

When a Musical Chairs room completes, write a `game_history` entry with:

- `game_type = "musical_chairs"`.
- `game_title`.
- `player_count`.
- `completed_at`.
- `total_questions = total_rounds` (reuse field, rename later).
- `leaderboard` — elimination-order ranking.
- Metadata:
  - `music_mode`.
  - `music_style`.
  - `rounds_played`.
  - `elimination_order`.
  - `fastest_reaction_ms`.
  - `duration_seconds`.

## Play Again

Standalone Musical Chairs `Play Again` sends `RESET_ROOM`. Room code and connected players remain. All MC state is cleared. All previously eliminated players are restored to active for the next game.

`Choose Another Game` returns to game select (standalone) or party hub (host-app).

## Catalog Metadata

```json
{
  "id": "musical_chairs",
  "game_type": "musical_chairs",
  "title": "Musical Chairs",
  "description": "Music plays, then stops. Race to grab a chair. Last one standing wins.",
  "status": "planned",
  "launchable": false,
  "supports_manual_authoring": false,
  "supports_ai_generation": false,
  "requires_content": false,
  "can_create_content": false,
  "can_quick_start": true,
  "supported_media": ["none"],
  "config_options": {
    "music_modes": ["builtin", "external"],
    "music_styles": ["upbeat", "jazzy", "suspenseful", "retro", "tropical"],
    "default_music_mode": "builtin",
    "default_music_style": "upbeat"
  }
}
```

## Moderation and Safety

- No user-generated text content beyond nicknames (already sanitized).
- No drawings or uploads.
- Music is procedurally generated or externally sourced — no moderation needed.
- Elimination messaging should be lighthearted, not harsh. Use "You're out!" not "You lost."

## Accessibility

- Grab button must be large, high contrast, and screen-reader announced.
- Elimination results must not rely only on color or animation.
- Music stop must have a visual signal (not just audio) for hearing-impaired players.
- `prefers-reduced-motion`: replace visualizer animations with static state changes.
- Provide a visible countdown/flash on music stop, not just the audio fade.

## Test Matrix

### Backend Engine Tests

- Config validation rejects out-of-range values.
- Round elimination correctly identifies slowest player(s).
- Multiple eliminations per round works correctly.
- Tied timestamps (same ms) result in both surviving.
- Players who don't tap are eliminated.
- Disconnected players during grab phase are eliminated.
- Grab before stop signal is rejected.
- Grab after deadline is rejected.
- Double grab from same player is ignored.
- Round count equals `ceil((N-1) / eliminations_per_round)` for N players.
- Intensity ramp calculates correctly across rounds.

### Backend WebSocket Tests

- Cannot start with fewer than 3 players.
- `MC_ROUND_START` is broadcast with correct player/chair count.
- Auto-stop fires within configured window.
- `MC_GRAB` is accepted and ranked by server timestamp.
- `MC_ROUND_OVER` includes correct elimination.
- Eliminated player receives `MC_ELIMINATED`.
- Final round produces `MC_WINNER` and `PODIUM`.
- Spectator receives `SPECTATOR_SYNC` with MC state.
- Organizer reconnect restores MC state.
- Player reconnect during grab phase can still tap.
- External music mode: organizer can manually stop.

### Frontend Tests

- Setup screen shows music mode and style options.
- Grab button only appears after `MC_MUSIC_STOP`.
- Grab button disabled after first tap.
- Eliminated player sees spectator view.
- Spectator shows active player count and visualizer.
- Music visualizer responds to analyser data (or gracefully degrades).
- `prefers-reduced-motion` suppresses visualizer animations.

### Playwright Tests

- Host creates a Musical Chairs room.
- Three players join.
- Host starts game, round begins.
- Players see grab button after stop.
- Elimination reveal shows correct player.
- Game completes with winner podium.
- External music mode shows manual stop button.

## Implementation Plan

### Phase 0: Spec

- Add this spec. Done.

### Phase 1: Backend Engine and Room Runtime

- Add `musical_chairs_engine.py` with config validation, round logic, grab ranking, elimination.
- Add MC state fields and runtime branch to `socket_manager.py`.
- Accept `musical_chairs` in room creation.
- Add config constants.
- Add backend tests.

### Phase 2: Frontend Setup and Game Screens

- Add MC to `GameType` and `gameModes.ts`.
- Add setup screen.
- Add organizer in-game screen.
- Add player round UI with grab button.
- Add spectator surface.

### Phase 3: Web Audio Music Engine

- Future phase: implement `musicEngine.ts` with AudioContext lifecycle.
- Implement at least 2 procedural styles (upbeat, suspenseful).
- Add music visualizer component.
- Wire music start/stop to WebSocket events.
- Test on iOS Safari.

### Phase 4: Polish

- Add remaining 3 music styles.
- Elimination reveal animations.
- Spectator player circle / chair visuals.
- Intensity ramp across rounds.
- External music mode UX.
- Reaction time stats on podium.
- Accessibility pass.
- Mobile layout pass.

### Phase 5: Catalog Enablement

- Enable in standalone catalog after testing.
- Keep disabled in host-app catalog until Revelry integration is tested.

## Future: AI Camera Elimination Mode

A future variant could use the device camera and on-device vision AI to detect who is physically sitting vs. standing when the music stops, bringing the game closer to real musical chairs.

Concept:

- The host device (or a dedicated camera device) captures a video feed of the room.
- When the music stops, the system takes a snapshot or short clip.
- An on-device vision model (e.g., MiniCPM-o, or a cloud vision API) analyzes the frame to detect players and their positions (standing vs. seated).
- The AI determines who is "out" — the player(s) not seated.
- Players could hold up their phones showing their avatar/color to help the AI identify them.

This would require:

- Camera access permission and a well-lit room.
- Player identification (colored badges, phone screens, or manual host confirmation).
- A fast vision model that can process a frame in under 2-3 seconds.
- A confidence threshold with host override — the AI suggests who is out, but the host confirms.
- Privacy considerations: frames should be processed ephemerally and never stored or transmitted off-device.

This is explicitly out of scope for v1 but is a compelling differentiator for a future version. It could also work as a hybrid mode: AI suggests, host confirms, app tracks elimination and scoring.

Relevant infrastructure:

- MiniCPM-o runs locally on Apple Silicon and could be called from the organizer device.
- Cloud vision APIs (Gemini multimodal, Claude vision) could analyze frames for hosted games.
- The existing `SPEC-IMAGE-GAMES.md` media layer patterns may be partially reusable for camera frame handling.

## Open Questions

- Should eliminated players be able to vote on a "crowd favorite" or participate in mini-games between rounds?
- Should there be a "sudden death" variant where grab window shrinks to near-zero in final rounds?
- Should reaction times be shown to all players during reveal, or only to the player themselves?
- Should the host be able to pause between rounds indefinitely, or should there be an auto-advance option?
- Should Music style auto-rotate between rounds, or stay consistent?
- Should there be a practice/warm-up round that doesn't eliminate anyone?
- For very large groups (20+), should the default `eliminations_per_round` auto-increase?

## Acceptance Criteria

Musical Chairs v1 is launch-ready when:

- `musical_chairs` appears in game select and can create a room without content generation.
- Room starts with 3+ players.
- Built-in MVP mode provides visual rhythm and server-randomized stop timing; procedural Web Audio is a future phase.
- Music stops at a random time within the configured window.
- Players see and can tap the grab button after music stops.
- Server ranks grabs by arrival time and eliminates the slowest.
- Eliminated players are announced with a reveal on all surfaces.
- Eliminated players transition to spectator view.
- Final round crowns a winner with podium.
- External music mode provides manual stop control.
- Spectator/TV surface shows visualizer, player state, and elimination drama.
- Reconnect works for active and eliminated players.
- Existing quiz, WMLT, Drawing, and Housie tests still pass.
- Backend has unit tests for engine logic and WebSocket flows.
- Frontend has tests for grab button behavior and state transitions.
