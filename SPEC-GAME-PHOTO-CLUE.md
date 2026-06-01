# LocalPlay Photo Clue Game Spec

## Overview

Add **Photo Clue** as an image-native party game where a player receives a secret word or phrase, submits a photo as the clue, and the rest of the room guesses the word from that photo.

This is not an image quiz and not Bingo. It is closer to DrawingGame, but the clue is a submitted photo instead of a canvas drawing.

```text
GameType: photo_clue
Runtime family: image_games
Backend engine: photo_clue_engine.py
Frontend display name: Photo Clue
```

Working title alternatives:

- Photo Clue
- Snap Guess
- Pic Prompt
- Guess the Snap

## Implementation-Ready MVP Scope

Status: implementation-ready after the player-photo upload slice of the shared image platform exists.

- Host creates or AI-generates a list of words/phrases.
- At game start, the server pre-assigns prompts to players for all planned rounds.
- Each player receives their own private prompt queue up front, before round 1 starts.
- Each round has one clue-giver whose already-delivered private prompt becomes active.
- The clue-giver takes or uploads one photo as a clue.
- Guessers see the submitted photo and type guesses.
- Server normalizes guesses against the target phrase and aliases.
- Correct guessers score.
- The clue-giver scores when at least one guesser gets it.
- Spectator/TV shows the photo, timer, correct guess count, and reveal.
- Player-submitted photos use the shared `/media/upload-url` and `/media/{asset_id}/finalize` flow.
- Photos are private party content by default and are not publicly browsable through an index.

## Goals

- Create a fun phone-native image game that uses the real party environment.
- Reuse DrawingGame's guessing/scoring model where possible.
- Exercise the shared media upload layer with player-submitted photos.
- Keep prompt visibility safe: players can see only their own assigned future prompts; other players and spectators see a prompt only after its round reveal.
- Make the spectator/TV view visually strong.
- Support reconnects and upload retries without breaking the round.
- Avoid mid-game prompt delivery dependencies by sending each player's private prompt queue at the beginning.

## Non-Goals

- No public gallery in MVP.
- No permanent social sharing in MVP.
- No AI judging in MVP.
- No AI image generation in MVP.
- No requirement for Gemini vision in MVP.
- No player photo submissions outside a live room.
- No saving submitted photos beyond the configured media retention period.
- No face recognition, identity detection, or biometric analysis.

## Game Rules

### Participants

- Host: creates prompt set and starts the game.
- Clue-giver: uses one of their pre-assigned private prompts and submits a photo clue.
- Guessers: everyone except the clue-giver.
- Spectator: TV/large screen view.

### Round Flow

1. Host creates or selects a Photo Clue prompt set.
2. Players join the room.
3. Host starts the game.
4. Server freezes the player list for prompt assignment.
5. Server selects the clue-giver order for all planned rounds.
6. Server assigns one prompt per planned clue-giver turn.
7. Each player receives their own private prompt queue immediately.
8. Round 1 starts using the first clue-giver's first assigned prompt.
9. Clue-giver takes/uploads a photo clue.
10. Server validates/finalizes the photo asset.
11. Guessers and spectator see the photo.
12. Guessers submit text guesses until the timer ends or all guessers are correct.
13. Server accepts correct guesses using normalized matching.
14. Round ends with a reveal of the target phrase and photo.
15. Scores update.
16. Next round rotates to the next pre-assigned clue-giver/prompt.
17. Final podium uses total points.

### Prompt Assignment

The game should not depend on delivering a new prompt in the middle of play. At start:

- Server creates a deterministic clue-giver schedule for all rounds.
- Server assigns prompts to that schedule.
- Server sends every player only their own future prompt assignments.
- Players may see upcoming prompts assigned to them, but not prompts assigned to other players.
- Spectator and other players see only round numbers, clue-giver names, and post-reveal prompts.
- If there are more rounds than players, players may receive multiple private prompts.
- If there are more prompts than rounds, unused prompts stay server-only and are not sent.

Private prompt assignment payload:

```json
{
  "type": "PHOTO_CLUE_PRIVATE_PROMPTS",
  "assignments": [
    {"round_number": 1, "prompt_id": 7, "text": "secret snack", "aliases": ["hidden snack", "sneaky snack"]}
  ]
}
```

## Prompt Rules

Prompts must be photographable or representable with a photo clue.

Good prompts:

```text
morning chaos
something suspicious
birthday energy
too fancy
secret snack
teamwork
almost famous
```

Avoid:

- Private or humiliating targets.
- Prompts that require photographing a specific person.
- Adult or hateful content.
- Prompts that require unsafe behavior.
- Prompts that require showing personal documents, payment cards, addresses, or private screens.

Prompt constraints:

- 1-5 words recommended.
- 80 characters maximum.
- Include 2-5 aliases where AI/manual setup can provide them.
- Prefer flexible phrases over exact trivia answers.

## Setup

```json
{
  "game_type": "photo_clue",
  "game_title": "Photo Clue",
  "rounds": 10,
  "photo_time_seconds": 60,
  "guess_time_seconds": 45,
  "allow_camera": true,
  "allow_gallery_upload": true,
  "show_incorrect_guess_feed": false
}
```

Defaults:

- `rounds`: 10.
- `photo_time_seconds`: 60.
- `guess_time_seconds`: 45.
- `allow_camera`: true.
- `allow_gallery_upload`: true.
- `show_incorrect_guess_feed`: false.

Validation:

- `rounds`: 1-50.
- `photo_time_seconds`: 20-180.
- `guess_time_seconds`: 15-120.
- Minimum players: 3.
- Recommended players: 4-12.

## Content Model

```ts
export interface PhotoCluePrompt {
  id: number;
  text: string;
  aliases?: string[];
}

export interface PhotoClueGame {
  game_title: string;
  prompts: PhotoCluePrompt[];
  assignments?: PhotoCluePromptAssignment[];
  photo_time_seconds: number;
  guess_time_seconds: number;
}

export interface PhotoCluePromptAssignment {
  round_number: number;
  clue_giver_id: string;
  prompt_id: number;
}
```

Live round:

```ts
export interface PhotoClueRound {
  round_number: number;
  clue_giver_id: string;
  prompt_id: number;
  phase: 'PHOTO_SUBMISSION' | 'PHOTO_REVEAL' | 'GUESSING' | 'ROUND_RESULT';
  photo_asset_id?: string;
  photo_url?: string;
  correct_guessers: string[];
  started_at: number;
  deadline: number;
}
```

## Backend Engine

Add:

```text
backend/photo_clue_engine.py
backend/tests/test_photo_clue_engine.py
```

Engine helpers:

```py
def validate_photo_clue_game(raw: dict) -> dict: ...

def choose_clue_giver(players: list[dict], round_number: int, prior_givers: list[str]) -> str: ...

def assign_prompts(players: list[dict], prompts: list[dict], rounds: int, seed: str | None = None) -> dict: ...

def private_prompt_sync(assignments: dict, viewer_id: str) -> dict: ...

def start_round(state: dict, now: float) -> dict: ...

def attach_photo(state: dict, player_id: str, asset_id: str, now: float) -> dict: ...

def normalize_guess(value: str) -> str: ...

def submit_guess(state: dict, player_id: str, guess: str, now: float) -> tuple[dict, dict]: ...

def score_round(state: dict) -> dict: ...
```

Reuse DrawingGame guess matching:

- lowercase
- trim whitespace
- strip punctuation
- collapse repeated spaces
- remove leading articles
- basic singular/plural normalization
- match target text or aliases

## WebSocket Events

Client to server:

```json
{ "type": "PHOTO_CLUE_UPLOAD_READY", "asset_id": "asset_uuid" }
{ "type": "PHOTO_CLUE_GUESS", "guess": "secret snack" }
{ "type": "PHOTO_CLUE_SKIP_PHOTO" }
{ "type": "PHOTO_CLUE_NEXT_ROUND" }
```

Server to clients:

```json
{ "type": "PHOTO_CLUE_SYNC", "state": {} }
{ "type": "PHOTO_CLUE_PHOTO_READY", "photo_url": "/media/asset_uuid" }
{ "type": "PHOTO_CLUE_GUESS_ACCEPTED", "player_id": "p2" }
{ "type": "PHOTO_CLUE_ROUND_RESULT", "prompt": "secret snack", "correct_guessers": [] }
{ "type": "PHOTO_CLUE_PRIVATE_PROMPTS", "assignments": [] }
```

Visibility:

- At game start, each player receives only their own `PHOTO_CLUE_PRIVATE_PROMPTS` assignment list.
- The current clue-giver receives `secret_prompt` again in round sync for convenience, but it must match their pre-assigned prompt.
- Guessers and spectator do not receive `secret_prompt` until result.
- Photo asset URL becomes public to the room only after finalize succeeds.
- Incorrect guesses should be local-only in MVP unless `show_incorrect_guess_feed` is explicitly enabled.

## Media Upload Flow

1. Clue-giver taps camera/upload.
2. Frontend requests `POST /media/upload-url` with purpose `photo_clue_submission`.
3. Browser uploads directly to IONOS using the signed URL.
4. Frontend calls `POST /media/{asset_id}/finalize`.
5. Frontend sends `PHOTO_CLUE_UPLOAD_READY`.
6. Backend verifies asset ownership, status, purpose, size, and MIME type.
7. Backend attaches the photo to the round and broadcasts `PHOTO_CLUE_PHOTO_READY`.

Constraints:

- MIME: JPEG, PNG, WebP.
- Size: use shared media limits; recommend 8 MB max.
- Strip EXIF metadata when normalization is available.
- Block pending/failed/deleted assets.
- Do not accept arbitrary external URLs.
- Use only app-controlled `/media/{asset_id}` URLs in game state.

## Scoring

Default scoring:

| Event | Points |
|---|---:|
| First correct guesser | 1000 |
| Later correct guessers | time-scaled 300-900 |
| Clue-giver bonus per correct guesser | 150 |
| All guessers correct | +400 clue-giver bonus |

Time scaling:

```text
guesser_points = 300 + round(600 * (time_remaining / guess_time_seconds))
```

Rules:

- Clue-giver gets no points if nobody guesses correctly.
- Guessers can score once per round.
- Clue-giver cannot guess their own prompt.
- If clue-giver skips/fails to submit a photo, no clue-giver points for that round.

## Reconnects, Disconnects, and Skips

- Reconnected players receive their private prompt assignment list again.
- Reconnected clue-giver sees the active secret prompt if the round is still active.
- Reconnected guesser sees the submitted photo and whether they already guessed correctly.
- If clue-giver disconnects before submitting photo, round waits until `photo_time_seconds` expires.
- Host can skip the round if photo submission is blocked.
- If a guesser disconnects, they can rejoin and continue guessing while the timer is active.
- Submitted photos remain attached to the round even if the clue-giver disconnects.

## Frontend UX

Organizer:

- Prompt setup screen: AI generate, manual edit, template prompts.
- Room lobby.
- In-game controls: start/next round, skip photo, end game.

Clue-giver:

- Private upcoming prompt list.
- Big active secret prompt for the current round.
- Camera/upload action.
- Upload progress.
- Replace photo before submitting if time remains.
- Waiting state while others guess.

Guessers:

- Photo display with stable aspect ratio.
- Guess input.
- Correct feedback when accepted.
- Waiting/reveal states.

Spectator:

- Large photo.
- Timer.
- Correct guess count.
- Clue-giver avatar/name.
- Reveal with target phrase.
- Leaderboard between rounds.

## Safety and Privacy

- Photos are party-private by default.
- No directory listing or gallery browsing.
- Avoid showing raw upload filenames.
- EXIF stripping should be prioritized before broad release.
- Add clear in-game copy: "Only submit photos you are comfortable showing to this room."
- Consider a host remove-photo control after MVP.
- Do not run face recognition or identity inference.

## Testing Plan

Backend tests:

- Prompt validation clamps timers and round count.
- Clue-giver rotation and prompt assignment are deterministic and fair.
- Private prompt assignment sync sends only the viewer's own prompts.
- Secret prompt is redacted from guesser/spectator sync.
- Only clue-giver can attach a photo.
- Pending/failed/wrong-owner media assets are rejected.
- Guess normalization accepts aliases.
- Clue-giver cannot guess.
- Scoring matches first/later/time-scaled rules.
- Reconnect sync preserves correct visibility.

Frontend tests:

- Player sees their own upcoming prompt list.
- Clue-giver sees active prompt and upload controls.
- Guessers do not see prompt before reveal.
- Photo display uses `GameImage` and stable dimensions.
- Guess input submits and shows accepted state.
- Spectator reveal shows photo and answer.

Playwright:

- Mobile clue-giver upload flow layout.
- Mobile guesser photo/guess layout.
- Desktop spectator photo view with long prompt reveal.
- Reconnect during guessing.

## Acceptance Criteria

- A host can create a Photo Clue game with 3+ players.
- Each round assigns one clue-giver and hides the prompt from everyone else.
- Clue-giver can upload/finalize a photo asset.
- Guessers can guess from the photo.
- Correct guesses and clue-giver bonuses score correctly.
- Spectator view shows photo, timer, reveal, and leaderboard.
- No hidden prompt or private media fields leak before reveal.
- Existing quiz, drawing, bingo/housie, musical chairs, and card specs remain unaffected.

## Future Work

- Gemini vision-assisted safety checks.
- AI-generated aliases after a prompt is written.
- Voting mode for subjective photo prompts.
- Team mode.
- Photo scavenger hunt variant where everyone submits a photo for the same prompt and the room votes.
- Host moderation controls for removing a submitted photo.
- Optional post-game album export if explicit room consent exists.
