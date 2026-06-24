# LocalPlay Random Chit Game Spec

## Overview

Add **Random Chit** as a light party prompt game where the app randomly picks a player, reveals a random chit, and asks that player to answer a question, do a tiny action, make a funny face, perform a mini challenge, or involve the group.

The host can write their own chits or generate a reviewed chit deck with AI. This should feel like a digital bowl of folded paper chits, but with LocalPlay room sync, player selection, spectator reveal, scoring, and replay controls.

```text
GameType: chit_pull
Runtime family: social_icebreaker
Backend engine: chit_pull_engine.py
Frontend display name: Random Chit
Legacy/internal name: Chit Pull
```

## Implementation Status

Status: implemented MVP in standalone LocalPlay. The stable API/game type remains `chit_pull`; user-facing catalog/setup/runtime labels now use **Random Chit**.

On June 24, 2026, LocalPlay made Random Chit eligible for Revelry host-app catalog exposure and host-app authoring: `host_app_supported = true`, `supported_host_apps = ["revelry"]`, `can_quick_start = true`, `can_create_content = true`, `can_edit_content = true`, and `supports_ai_generation = true`. LocalPlay now supports `chit_pull` in the Revelry party-games save/start/generate contract, stores it in `generated_content`, and shares the same sanitizer/generation helper with standalone `/chit-pull/generate`.

Implemented in this repo with:

- `backend/chit_pull_engine.py` pure mechanics and validation helpers.
- `/chit-pull/generate`, `/chit-pull/import`, and `/chit-pull/{id}` update routes.
- Room creation support through `game_type="chit_pull"` and `chit_pull_id` / `chit_pull_config`.
- WebSocket runtime messages: `CHIT_SYNC`, `CHIT_NEXT`, `CHIT_COMPLETE`, `CHIT_SKIP`, `CHIT_REDRAW_PLAYER`, and `CHIT_REDRAW_CHIT`.
- Organizer prompt/review/live screens, plus player and spectator live views.
- Backend and frontend tests for engine behavior, Random Chit default naming, and live component rendering.

Current host-app exposure can include quick-start, manual saved-content authoring, and AI deck generation once Revelry catalog policy enables it in gamma/prod. This is still driven by LocalPlay's catalog response and policy rows; no Revelry repo changes are included here.

## MVP Scope

- Standalone LocalPlay first.
- Minimum 3 players.
- Host can create chits manually.
- Host can AI-generate chits from a theme in MVP.
- Host reviews and edits generated chits before room creation.
- Runtime randomly chooses one active player and one unused chit per turn.
- Spectator/TV reveals the selected player and chit with a playful reveal moment.
- Host marks the turn as completed, skipped, or redraws.
- Optional scoring is included in MVP:
  - completed = points
  - skipped = no points
  - host bonus = optional extra points
- Final podium ranks players.

## Goals

- Create a flexible social game that works for birthdays, weddings, offsites, family parties, classrooms, and casual hangouts.
- Let the host tailor the vibe quickly.
- Make AI useful without making it mandatory.
- Keep prompts safe, short, and easy to perform in person.
- Support lots of replayability with different themes and custom decks.
- Keep the runtime simpler than card games or hidden-role games.

## Non-Goals

- No forced sensitive disclosure.
- No anonymous insults or roast mode in MVP.
- No judging with AI.
- No real-money or economy-linked rewards.
- No photo/video capture in MVP.
- Revelry exposure is controlled by host-app catalog policy; LocalPlay now supports the saved-content and AI generation contract for `chit_pull`.

## Game Modes

### Classic Pull

Each turn:

1. App randomly selects one player.
2. App randomly selects one chit.
3. Player does the thing or answers.
4. Host marks done / skip / redraw.

### Team Pull

Future mode. App picks a team, not just one player.

### Hot Seat

Future mode. App keeps one selected player for multiple chits.

## Chit Categories

MVP categories:

| Category | Description | Example |
|---|---|---|
| `question` | answer something light | "What is your most useless talent?" |
| `action` | do a small action | "High-five someone wearing your favorite color." |
| `funny_face` | make an expression | "Make the face you make when the Wi-Fi dies." |
| `mini_challenge` | short performable challenge | "Say the alphabet backwards as far as you can in 10 seconds." |
| `group` | involve the room | "Find two people who agree on the best dessert." |

Optional future categories:

- `truth`
- `compliment`
- `memory`
- `dance`
- `wedding`
- `kids`
- `work_safe`
- `spicy`

## Safety and Content Rules

Chits should be light, voluntary, and inclusive.

Good chits:

```text
Name a food you could eat every week.
Make your most dramatic movie-villain face.
Ask someone nearby for a two-word movie review.
Do your best slow-motion celebration.
Tell the room your least useful superpower.
```

Avoid:

- Race, ethnicity, nationality, religion, caste, sexuality, gender identity, disability, age, family status, or protected-class targeting.
- Medical, legal, immigration, financial, trauma, criminal history, sexual, or deeply private prompts.
- Prompts that pressure someone to touch, reveal, drink, spend money, or leave the venue.
- Mean-spirited, humiliating, or targeted personal insults.
- Anything requiring photos, documents, private screens, addresses, or employer secrets.

Player-facing skip should always be available in MVP. The game should normalize skipping: "Skip is allowed. Keep it fun."

## Setup

```json
{
  "game_type": "chit_pull",
  "game_title": "Random Chit",
  "selection_mode": "random_player",
  "rounds": 20,
  "turn_time_seconds": 30,
  "allow_player_repeats": true,
  "allow_chit_repeats": false,
  "skip_limit_per_player": 2,
  "scoring_enabled": true,
  "completion_points": 100,
  "bonus_points": 50,
  "chits": [
    {
      "id": "chit_1",
      "text": "Make the face you make when your food arrives.",
      "category": "funny_face",
      "safe_level": "work_safe"
    }
  ]
}
```

Defaults:

- `selection_mode`: `random_player`.
- `rounds`: 20.
- `turn_time_seconds`: 30.
- `allow_player_repeats`: true.
- `allow_chit_repeats`: false.
- `skip_limit_per_player`: 2.
- `scoring_enabled`: true.
- `completion_points`: 100.
- `bonus_points`: 50.
- `safe_level`: `work_safe`.

Validation:

- Minimum players: 3.
- Recommended players: 4-50.
- Rounds: 5-100.
- Chits: 5-200.
- Chit text: 3-180 chars.
- Turn time: 10-120 seconds.
- Skip limit: 0-10.
- Categories must be known or normalized to `question`.

## AI Generation in MVP

AI generation is part of the MVP.

Host flow:

1. Host chooses Random Chit.
2. Host enters a theme/vibe, e.g. "birthday party, cousins, silly but clean."
3. Host chooses count: 10, 20, 30, or 50 chits.
4. Host chooses safety level: `kids`, `work_safe`, `family`, or `spicy`.
5. Host taps **Generate Chits**.
6. Backend charges sparks using existing generation quota/payment flow.
7. AI returns structured chits.
8. Backend validates and sanitizes chits.
9. Host reviews, edits, deletes, and adds chits before creating the room.

### AI Request

```json
{
  "prompt": "birthday party, silly but clean",
  "difficulty": "medium",
  "num_chits": 20,
  "safe_level": "family",
  "categories": ["question", "action", "funny_face", "mini_challenge", "group"],
  "provider": "gemini"
}
```

### AI Output

```json
{
  "game_title": "Birthday Random Chit",
  "chits": [
    {
      "id": 1,
      "text": "Make the face you make when someone says there is cake.",
      "category": "funny_face",
      "safe_level": "family"
    }
  ]
}
```

### AI Prompt Contract

Generation prompt must include:

```text
Generate short, performable party chits for a live group game.
Every chit must be safe, voluntary, inclusive, and easy to do in person.
Avoid protected-class targeting, private/sensitive disclosure, humiliation, touching, drinking, spending money, or leaving the venue.
Return JSON only.
```

Mode-specific instructions:

- `kids`: no romance, adult topics, alcohol, embarrassment, or body jokes.
- `family`: broadly clean, low embarrassment, friendly for mixed ages.
- `work_safe`: suitable for coworkers; avoid personal, political, romantic, medical, financial, or sensitive prompts.
- `spicy`: playful and cheeky, but still no coercion, protected-class targeting, explicit sexual content, or humiliation.

Backend validation must reject or replace chits that:

- are too long or empty
- duplicate another chit after normalization
- include disallowed safety terms
- target a protected class
- require physical contact, drinking, payment, private disclosure, or leaving the venue

Generated chits must be host-reviewed before room creation. No AI-generated chit deck should start automatically without review.

## Content Model

```ts
export interface ChitPullChit {
  id: string;
  text: string;
  category: 'question' | 'action' | 'funny_face' | 'mini_challenge' | 'group';
  safe_level?: 'kids' | 'family' | 'work_safe' | 'spicy';
}

export interface ChitPullGame {
  game_title: string;
  selection_mode: 'random_player';
  rounds: number;
  turn_time_seconds: number;
  allow_player_repeats: boolean;
  allow_chit_repeats: boolean;
  skip_limit_per_player: number;
  scoring_enabled: boolean;
  completion_points: number;
  bonus_points: number;
  chits: ChitPullChit[];
}
```

Runtime state:

```ts
export interface ChitPullState {
  phase: 'CHIT_READY' | 'CHIT_REVEAL' | 'CHIT_ACTIVE' | 'CHIT_RESULT' | 'PODIUM';
  round_number: number;
  total_rounds: number;
  selected_player_id: string;
  current_chit?: ChitPullChit;
  deadline?: number;
  used_chit_ids: string[];
  player_turn_counts: Record<string, number>;
  skips_by_player: Record<string, number>;
  scores: Record<string, number>;
  turn_results: ChitPullTurnResult[];
}

export interface ChitPullTurnResult {
  round_number: number;
  player_id: string;
  chit_id: string;
  outcome: 'completed' | 'skipped' | 'redrawn';
  points_awarded: number;
  completed_at: number;
}
```

## Runtime Flow

1. Host creates or AI-generates a chit deck.
2. Host reviews/edits chits.
3. Host creates a room.
4. Players join.
5. Host starts game.
6. Server chooses player and chit.
7. Spectator/TV animates reveal.
8. Selected player sees the chit and action controls.
9. Host marks:
   - completed
   - skipped
   - redraw chit
   - redraw player
10. Server updates score/result log.
11. Next turn starts.
12. Final podium after configured rounds or no chits remain.

## Selection Rules

Player selection:

- Random among active players.
- If `allow_player_repeats = false`, prefer players with the fewest turns.
- Do not select disconnected players.
- If the selected player disconnects before resolution, host can redraw player.

Chit selection:

- Random among available chits.
- If `allow_chit_repeats = false`, remove used chits from the pool.
- If all chits are used before all rounds finish, either end early or reshuffle used chits based on config.
- Redrawn chits are not counted as used unless host confirms completion/skip.

## Scoring

Default scoring:

| Outcome | Points |
|---|---:|
| Completed | 100 |
| Skipped | 0 |
| Host bonus | +50 |

Rules:

- Host bonus is optional and should be one tap.
- If scoring is disabled, show turn count / participation instead of score.
- Skips are tracked for pacing but should not shame players.

## WebSocket Events

Client to server:

```json
{ "type": "CHIT_NEXT" }
{ "type": "CHIT_COMPLETE", "bonus": false }
{ "type": "CHIT_SKIP" }
{ "type": "CHIT_REDRAW_PLAYER" }
{ "type": "CHIT_REDRAW_CHIT" }
```

Server to clients:

```json
{
  "type": "CHIT_SYNC",
  "game_type": "chit_pull",
  "chit_pull": {
    "phase": "CHIT_ACTIVE",
    "round_number": 3,
    "selected_player_id": "Avi",
    "current_chit": {
      "id": "chit_7",
      "text": "Make your best shocked face.",
      "category": "funny_face"
    },
    "scores": {}
  }
}
```

Visibility:

- Everyone can see the selected player and active chit after reveal.
- If future hidden-player modes are added, they must use private sync payloads.
- Host controls are organizer-only.

## Frontend UX

### Organizer Setup

- Game card in Creative category.
- Prompt screen with:
  - theme/vibe textarea
  - safety level segmented control
  - number of chits
  - provider selector when available
  - **Generate Chits**
  - **Create Your Own**
- Review screen:
  - editable chit list
  - category dropdown per chit
  - add/delete
  - regenerate
  - create room

### Player View

- If selected: large "You're up" moment, chit text, skip reminder.
- If not selected: show selected player, chit, and score/turn standings.
- Avoid tiny text: chit text should be readable on mobile.

### Spectator/TV View

- Big selected player reveal.
- Large chit card.
- Category icon.
- Running round count.
- Score/participation sidebar.
- Result moment after completed/skipped.

## Backend Implementation

Add:

```text
backend/chit_pull_engine.py
backend/tests/test_chit_pull_engine.py
```

Pure helpers:

```py
def validate_config(raw: dict | None) -> dict: ...
def sanitize_chit_deck(raw_chits: list[dict]) -> list[dict]: ...
def create_initial_state(player_ids: list[str], config: dict, now: float | None = None, seed: str | int | None = None) -> dict: ...
def draw_turn(state: dict, now: float | None = None) -> dict: ...
def complete_turn(state: dict, bonus: bool = False, now: float | None = None) -> dict: ...
def skip_turn(state: dict, now: float | None = None) -> dict: ...
def redraw_player(state: dict, now: float | None = None) -> dict: ...
def redraw_chit(state: dict, now: float | None = None) -> dict: ...
def public_sync(state: dict, players: list[dict[str, str]] | None = None) -> dict: ...
def final_standings(state: dict) -> list[dict]: ...
```

AI engine:

```text
backend/chit_pull_generation.py
```

or use a single `chit_pull_engine.py` if generation remains small.

REST endpoints:

```text
POST /chit-pull/generate
POST /chit-pull/import
PUT /chit-pull/{id}
```

`/room/create` support:

```json
{
  "game_type": "chit_pull",
  "chit_pull_id": "content-id"
}
```

For quick start, backend can create a safe default deck if no content id is supplied.

## Testing Plan

Backend:

- Config validation clamps rounds, timers, skip limits, and scoring values.
- Chit sanitization rejects empty, duplicate, unsafe, and too-long chits.
- AI validator accepts valid structured output and rejects unsafe shapes.
- Draw turn selects active players only.
- Draw turn respects no-repeat chit config.
- Complete/skip records result and advances.
- Scoring applies completion and bonus points.
- Final standings sort by score, completions, and fewer skips.
- Public sync contains selected player, chit, scores, and turn history.

Frontend:

- Setup can generate chits with a theme.
- Review can edit/add/delete chits.
- Create room disabled until enough valid chits exist.
- Active selected-player state renders clearly.
- Host complete/skip/redraw buttons call expected websocket handlers.
- Mobile layout keeps chit text readable and buttons separated.

Playwright:

- Standalone AI generation and review flow.
- Manual chit deck creation.
- 3-player live room through multiple turns.
- Redraw player/chit controls.
- Final podium.
- Gamma smoke once deployed.

## Acceptance Criteria

- Host can AI-generate, review, edit, and start a Random Chit deck.
- Host can manually create a deck without AI.
- Game starts with 3+ players.
- Server randomly chooses player and chit.
- Host can complete, skip, redraw player, or redraw chit.
- Scores update deterministically.
- Final podium appears.
- Chit safety validation prevents obviously unsafe AI or manual content from entering generated decks.
- Spec and docs clearly state that AI-generated chits require host review.

## Revelry / Host-App Fit

Random Chit is a strong Revelry fit because it is party-native, highly customizable, and easy to theme for an event.

Defer Revelry exposure until:

- Standalone AI/manual authoring is tested.
- Result summary callback does not include raw sensitive chit text by default.
- Host-app catalog policy is seeded in gamma.
- Embedded flow hides standalone sparks/account UI unless allowed.

Safe result summary:

```json
{
  "game_type": "chit_pull",
  "rounds_played": 20,
  "completed_count": 17,
  "skipped_count": 3,
  "winner": "Avi"
}
```

Do not send raw chit text to Revelry callbacks by default.

## Future Work

- Theme packs: weddings, birthdays, office, kids, family, baby shower.
- Team mode.
- Hot Seat mode.
- QR tap confirmation for group tasks.
- Optional anonymous host-submitted chits.
- "Spicy but safe" reviewed pack.
- Photo/video capture after a completed chit.
- Player-submitted chits before game start.
- AI rewrite/safety repair for manual chits.
