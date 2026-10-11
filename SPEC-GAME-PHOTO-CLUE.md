# LocalPlay Photo Clue Game Spec

## Current repository contract (reviewed 2026-10-10)

Rooms accept `photo_clue_config`; the implemented phases are `PHOTO_WAITING_FOR_PHOTO`, `PHOTO_GUESSING`, `PHOTO_REVEAL`, and `PODIUM`. Prompts are assigned in roster order up front. All state, including the viewer's upcoming prompts and current guess, uses `PHOTO_CLUE_SYNC.photo_clue`; there are no separate photo-ready/private-prompts/result events. The clue-giver uploads through the shared media endpoints, then sends `PHOTO_CLUE_UPLOAD_READY`; the host uses `PHOTO_CLUE_REVEAL` to reveal/skip and `PHOTO_CLUE_NEXT_ROUND` to advance. The active prompt is private until reveal. Scoring is fixed per correct guess, with no first-guesser/time bonus. Deadlines are recorded but expiry/automatic reveal/progressive hints are roadmap.

Attachment uses a short-lived server-signed capability returned by authenticated `/media/upload-url` for `purpose=photo_clue_submission`. `PHOTO_CLUE_UPLOAD_READY` carries its `attachment_token` alongside `asset_id`. The token binds the asset, authenticated owner, purpose, and expiry; the socket resolves the owner's ready DB record and attaches its canonical `public_url`, ignoring any caller-supplied URL. The active clue-giver and round phase are checked independently. This closes the former client-URL bypass without trusting a WebSocket-supplied wallet identity.

`finalize` still marks owner-scoped metadata ready without independently fetching/decoding remote bytes. The IONOS upload handler verifies signed size and detected MIME, but dimensions and EXIF stripping remain follow-ups. CDN URLs have no room authorization or automatic retention cleanup in this repository; possession of a URL permits reading the file. Ownership checks on attachment therefore do not establish private/expiring CDN reads. The stronger media verification and retention requirements remain in `SPEC-IMAGE-GAMES.md`.

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

Status: standalone playable MVP implemented on June 24, 2026. The shared media upload/finalize platform exists, and `backend/photo_clue_engine.py` owns prompt validation, up-front prompt assignment, private clue-giver queues, photo submission state, guess normalization, scoring, reveal, podium transition, public-state redaction, and pure engine tests. LocalPlay now exposes Photo Clue in the standalone catalog with default prompts, room creation, WebSocket events, player upload/guessing UI, organizer reveal/next controls, spectator reveal UI, reconnect handling, podium flow, and focused API/socket regression tests. July 6, 2026 polish/bridge-hardening pass is implementation-ready. Remaining follow-ups are AI/manual authoring UI, moderation/review, richer media retention controls, and broader Playwright matrix coverage.

Revelry bridge status: LocalPlay now marks Photo Clue as a host-app-capable quick-start/settings game for Revelry. It is `can_quick_start=true`, `can_create_content=false`, `can_edit_content=false`, `supports_ai_generation=false`, and `supports_images=true`. Actual Revelry visibility remains host-app policy gated and should ship only after gamma embedded QA covers upload/finalize, guessing, spectator reveal, reconnect, completion, and result polling. Revelry should not mirror raw submitted photos unless LocalPlay later returns an explicit safe share payload.

- Host quick-starts curated prompts or supplies a custom prompt list through the room API. Dedicated AI/manual authoring UI remains roadmap.
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

## July 6, 2026 Polish Roadmap (not the current API contract)

Photo Clue is playable, but should not be broadly exposed to Revelry production until the image-specific UX and privacy edges are tightened.

### Scope

Host setup polish:

- Add a setup/review screen for prompt packs before room creation.
- Support curated packs: Party Objects, Birthday, Wedding, Travel, Food, Office-safe.
- Add AI prompt generation behind host review, using the existing AI provider selection/prompt shuffle pattern.
- Add manual edit/add/remove/reorder for prompts.
- Show clear copy that players should submit photos of objects/scenes, not private documents or people without consent.

Player upload polish:

- Show the active clue-giver, round number, and remaining photo time.
- Provide clear upload states: selecting, uploading, processing, retry, submitted.
- If camera/upload is unavailable, show a graceful fallback and let host skip the round.
- Prevent multiple final submissions for a round unless host resets the photo.
- Preserve upload state across reconnect after `asset_id` is finalized.

Guessing/reveal polish:

- Show answer blanks before reveal, similar to Drawing Game: word count and letter count.
- Reveal first-letter hints after 50% of guessing time, first letter of each word after 75%, and first/last letters after 90% if no one has guessed.
- Spectator/TV should show submitted photo, timer, clue-giver, correct guess count, and reveal in a large, legible layout.
- Organizer should have Skip Round and Reveal Now controls.

Privacy/safety:

- Result summaries and Revelry callbacks must not include raw photo URLs by default.
- If a future share/recap includes photos, it must use an explicit `safe_share_media` payload generated by LocalPlay after host approval.
- Uploaded files remain under the shared media retention policy; no public gallery in this pass.
- Do not run face recognition, identity detection, or biometric analysis.

### Backend/API Work

- Add or complete `POST /photo-clue/generate` for AI prompt packs with sanitizer validation.
- Ensure `PHOTO_CLUE_PHOTO_SUBMITTED` stores only `asset_id` and canonical `photo_url` from finalized media metadata.
- Add `PHOTO_CLUE_SKIP_ROUND` and `PHOTO_CLUE_REVEAL_NOW` organizer events.
- Add hint state derived server-side from elapsed guessing time so reconnecting clients agree.
- Add safe `result_summary` that includes title, rounds, winner/top players, and aggregate counts only.

### Tests

Backend:

- AI-generated prompts sanitize unsafe/private-photo requests.
- Upload cannot be submitted by non-clue-giver.
- A round cannot accept a second photo after finalized submission.
- Skip/reveal transitions are idempotent.
- Result summary excludes raw photo URLs.

Frontend:

- Player sees upload retry and submitted states.
- Guessing screen shows blanks and progressive hints.
- Spectator reveal is legible with a large submitted image.
- Organizer Skip Round and Reveal Now controls work.

Playwright:

- Host creates Photo Clue from curated prompts.
- Clue-giver uploads a small test image through the real media flow in gamma.
- Guesser submits correct/incorrect guesses.
- Spectator sees photo/reveal without console errors.
- Reconnect after upload restores the submitted state.

Acceptance:

- A 3+ player room can complete at least two Photo Clue rounds on gamma with real media upload/finalize.
- No raw uploaded photo is sent to Revelry result callbacks.
- Host can recover from a failed upload or absent clue-giver.

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
12. Guessers submit text guesses while the host keeps the guessing phase open; automatic expiry/all-solved reveal is not implemented.
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
  "type": "PHOTO_CLUE_SYNC",
  "photo_clue": {"private_prompts": [
    {"round_index": 0, "prompt": {"id": "prompt_7", "answer": "secret snack", "aliases": ["hidden snack", "sneaky snack"]}}
  ]}
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
  "round_count": 5,
  "photo_time_seconds": 90,
  "guess_time_seconds": 45,
  "correct_guess_points": 100,
  "clue_giver_points": 50,
  "allow_late_join": true
}
```

Defaults:

- `round_count`: 5, capped by available prompts.
- `photo_time_seconds`: 90.
- `guess_time_seconds`: 45.
- `correct_guess_points`: 100.
- `clue_giver_points`: 50 per correct guesser.
- `allow_late_join`: true. Camera/feed controls are not engine config fields.

Validation:

- `round_count`: 3-25, capped by available prompts.
- `photo_time_seconds`: 30-300.
- `guess_time_seconds`: 10-120.
- Minimum players: 2.
- Recommended players: 4-12.

## Original Data-Model Design (historical; current phases are `PHOTO_*`)

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

## Original Backend Design Sketch (historical helper names)

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
{ "type": "PHOTO_CLUE_UPLOAD_READY", "asset_id": "asset_uuid", "attachment_token": "server_signed_capability" }
{ "type": "PHOTO_CLUE_GUESS", "guess": "secret snack" }
{ "type": "PHOTO_CLUE_REVEAL" }
{ "type": "PHOTO_CLUE_NEXT_ROUND" }
```

Server to clients:

```json
{ "type": "PHOTO_CLUE_SYNC", "game_type": "photo_clue", "photo_clue": {} }
{ "type": "PODIUM", "game_type": "photo_clue", "leaderboard": [] }
```

Visibility:

- At game start and reconnect, each player receives only their own `private_prompts` list inside `PHOTO_CLUE_SYNC.photo_clue`.
- The current clue-giver receives `secret_prompt` again in round sync for convenience, but it must match their pre-assigned prompt.
- Guessers and spectator do not receive `secret_prompt` until result.
- Photo asset URL becomes public to the room only after finalize succeeds.
- Incorrect guesses are private to the submitting player; there is no public incorrect-guess feed setting.

## Media Upload Flow

1. Clue-giver taps camera/upload.
2. Authenticated frontend requests `POST /media/upload-url` with purpose `photo_clue_submission` and retains the returned `asset_id` and `attachment_token`.
3. Browser uploads directly to IONOS using the signed URL.
4. Frontend calls `POST /media/{asset_id}/finalize`.
5. Frontend sends `PHOTO_CLUE_UPLOAD_READY` with `asset_id` and `attachment_token`.
6. Backend verifies the capability's signature, expiry, asset binding, and Photo Clue purpose, then resolves ready media metadata under its bound owner. It also validates the active clue-giver and waiting-for-photo phase.
7. Backend attaches the record's canonical CDN `public_url` to the round and broadcasts `PHOTO_CLUE_SYNC`; caller-supplied `photo_url` or `image_url` is ignored.

Constraints:

- MIME: JPEG, PNG, WebP.
- Size: use shared media limits; backend and IONOS handler currently cap uploads at 2 MiB.
- Strip EXIF metadata when normalization is available.
- Block pending/failed/deleted assets.
- Do not accept arbitrary external URLs.
- Use the canonical app-controlled CDN URL from the persisted asset record in game state. `/media/{asset_id}` currently serves generated in-memory images only.
- A ready record is not independent proof that a remote file was uploaded successfully; remote byte verification remains a finalize requirement.
- Attachment capabilities use HS256 with `MEDIA_UPLOAD_SECRET`, issuer `localplay.media`, audience `photo_clue`, scope `photo_clue_submission`, and lifetime `MEDIA_UPLOAD_TOKEN_TTL_SECONDS`. Required claims include the exact asset, owner, issued-at time, and expiry.

## Scoring

Default scoring:

| Event | Points |
|---|---:|
| Each correct guesser (once per round) | 100 by default |
| Clue-giver bonus per correct guesser | 50 by default |

Both values are configurable (`correct_guess_points`: 10-1000; `clue_giver_points`: 0-500). First-guesser/time-scaled scoring and an all-solved bonus are roadmap.

Rules:

- Clue-giver gets no points if nobody guesses correctly.
- Guessers can score once per round.
- Clue-giver cannot guess their own prompt.
- If clue-giver skips/fails to submit a photo, no clue-giver points for that round.

## Reconnects, Disconnects, and Skips

- Reconnected players receive their private prompt assignment list again.
- Reconnected clue-giver sees the active secret prompt if the round is still active.
- Reconnected guesser sees the submitted photo and whether they already guessed correctly.
- If the clue-giver disconnects before submitting, the round waits for reconnect or host reveal; stored deadline expiry does not automatically skip.
- Host can skip the round if photo submission is blocked.
- If a guesser disconnects, they can rejoin and continue guessing while the host keeps the guessing phase open.
- Submitted photos remain attached to the round even if the clue-giver disconnects.

## Frontend UX and Follow-Ups (prompt authoring/camera controls are roadmap)

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
- Missing, expired, wrong-purpose, tampered, and asset-mismatched attachment capabilities are rejected; only the bound owner's ready media record is eligible.
- Guess normalization accepts aliases.
- Clue-giver cannot guess.
- Scoring matches the configured fixed guesser and per-correct-guesser clue-giver points.
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
