# LocalPlay Find Someone Who Game Spec

## Overview

Add **Find Someone Who** as a social icebreaker game where each player gets a Bingo-style grid of people-finding prompts and marks squares by finding someone in the room who matches the prompt.

This is adjacent to Bingo, but it is not caller-led. The "called item" is replaced by real social discovery: players talk to each other, find matches, and optionally collect confirmation from the matched person.

```text
GameType: find_someone_who
Runtime family: social_bingo
Backend engine: find_someone_engine.py, reusing bingo_content_engine.py/card helpers where practical
Frontend display name: Find Someone Who
```

## Implementation-Ready MVP Scope

Status: implementation-ready after generic Bingo card rendering and player-mark state are stable.

- Standalone LocalPlay first.
- Host creates, edits, or AI-generates a list of people-finding prompts.
- Server generates a Bingo-style card for each player.
- Players move around physically and talk to people.
- To mark a cell, a player selects the prompt and chooses the person they found.
- MVP confirmation mode can be host-configured:
  - `honor`: no confirmation; trust players.
  - `tap_confirm`: selected person receives a prompt and taps confirm/deny.
- Players claim patterns such as line, corners, blackout.
- Server validates claims against the player's marked cells and confirmation rules.
- Spectator/TV shows safe aggregate progress, winners, and fun prompt highlights, not private personal details unless revealed by game rules.

## Goals

- Create a low-friction icebreaker for parties, weddings, offsites, classrooms, and meetups.
- Reuse Bingo-family layout/pattern concepts without requiring a caller.
- Encourage people to talk to people they do not already know.
- Support ready-made templates and AI-generated prompt sets.
- Keep personal/demographic targeting safe and compliant.
- Work without sign-in and without requiring persistent identity.

## Non-Goals

- No demographic targeting based on protected classes.
- No prompts that ask players to disclose sensitive personal information.
- No public permanent profile or directory.
- No location tracking.
- No facial recognition or photo verification.
- No automatic truth verification in MVP.
- No real-money prizes, paid cards, or randomized paid advantages.

## Prompt Safety Rules

Prompts should be light, voluntary, and conversation-friendly.

Good prompts:

```text
has visited three countries
can play a musical instrument
has the same birth month as you
likes spicy food
has a pet
has run a 5K
knows how to cook a signature dish
has lived in more than one city
```

Avoid:

- Race, ethnicity, nationality, religion, caste, sexuality, gender identity, disability, age targeting, or family status.
- Income, visa, immigration, medical, trauma, criminal history, or political affiliation.
- Anything that pressures someone to reveal private/sensitive information.
- Anything humiliating, sexual, or unsafe.
- Negative prompts like "has never..." when they can shame people.

Prompt generation must include a safety instruction that says:

```text
Generate only light, voluntary, conversation-friendly prompts. Avoid sensitive personal data and protected-class targeting.
```

## Game Setup

```json
{
  "game_type": "find_someone_who",
  "game_title": "Find Someone Who",
  "layout": "bingo_5x5_free",
  "prompt_count": 40,
  "confirmation_mode": "tap_confirm",
  "claim_patterns": ["first_line", "four_corners", "blackout"],
  "round_time_seconds": 600,
  "allow_same_person_multiple_cells": false,
  "allow_self_match": false
}
```

Defaults:

- `layout`: `bingo_5x5_free`.
- `prompt_count`: 40.
- `confirmation_mode`: `tap_confirm`.
- `claim_patterns`: first line, four corners, blackout.
- `round_time_seconds`: 600.
- `allow_same_person_multiple_cells`: false.
- `allow_self_match`: false.

Validation:

- Minimum players: 3.
- Recommended players: 6-60.
- `prompt_count` must be enough for the selected layout:
  - 5x5 free center: at least 24.
  - 5x5 no free center: at least 25.
  - 4x4: at least 16.
- Max prompt count: 120.

## Content Model

```ts
export interface FindSomeonePrompt {
  id: string;
  display: string;
  category?: 'travel' | 'hobby' | 'food' | 'work_safe' | 'family_friendly' | 'custom';
}

export interface FindSomeoneGame {
  game_title: string;
  prompts: FindSomeonePrompt[];
  layout: 'bingo_5x5_free' | 'bingo_5x5' | 'bingo_4x4';
  confirmation_mode: 'honor' | 'tap_confirm';
  claim_patterns: string[];
  round_time_seconds: number;
  allow_same_person_multiple_cells: boolean;
  allow_self_match: boolean;
}
```

Generated player card:

```ts
export interface FindSomeoneCard {
  card_id: string;
  player_id: string;
  cells: FindSomeoneCell[][];
}

export interface FindSomeoneCell {
  prompt_id: string;
  display: string;
  row: number;
  column: number;
  marked: boolean;
  matched_player_id?: string;
  matched_player_name?: string;
  confirmation_status?: 'pending' | 'confirmed' | 'denied';
}
```

## Runtime Model

Room state:

```json
{
  "phase": "FIND_ACTIVE",
  "cards_by_player": {},
  "pending_confirmations": {},
  "accepted_claims": [],
  "claim_log": [],
  "started_at": 1234567890,
  "ends_at": 1234568490
}
```

Phases:

- `FIND_LOBBY`
- `FIND_ACTIVE`
- `FIND_REVIEW_CLAIM`
- `FIND_RESULTS`
- `PODIUM`

## Marking a Cell

Player flow:

1. Player taps an unmarked prompt cell.
2. Player chooses the person they found from the current roster.
3. If `allow_self_match = false`, the player cannot choose themselves.
4. If `allow_same_person_multiple_cells = false`, the same matched player cannot satisfy multiple cells on one player's card.
5. If `confirmation_mode = honor`, the cell marks immediately.
6. If `confirmation_mode = tap_confirm`, the selected person receives a confirmation request.
7. Selected person taps confirm or deny.
8. Confirm marks the original player's cell. Deny leaves it unmarked.

Client to server:

```json
{ "type": "FIND_MARK_CELL", "prompt_id": "p12", "matched_player_id": "player_2" }
{ "type": "FIND_CONFIRM_MATCH", "request_id": "req_1", "accepted": true }
{ "type": "FIND_CLAIM_PATTERN", "pattern_id": "first_line" }
```

Server to clients:

```json
{ "type": "FIND_SYNC", "state": {} }
{ "type": "FIND_CONFIRMATION_REQUEST", "request": {} }
{ "type": "FIND_CELL_CONFIRMED", "player_id": "player_1", "prompt_id": "p12" }
{ "type": "FIND_CLAIM_ACCEPTED", "winner": {} }
{ "type": "FIND_CLAIM_REJECTED", "reason": "not_complete" }
```

## Claim Validation

Supported MVP patterns:

- `first_line`: row, column, or diagonal.
- `four_corners`.
- `blackout`.

Rules:

- Claimed cells must be marked.
- In `tap_confirm` mode, claimed cells must be confirmed, not pending.
- Free center counts as marked.
- A player cannot claim the same pattern more than once.
- By default, a matched person can appear only once on a given player's card.

## Scoring and Winners

MVP can use prize-style claims rather than point scoring:

- First accepted `first_line` wins that prize.
- First accepted `four_corners` wins that prize.
- First accepted `blackout` wins final/top prize.
- Podium can rank by:
  1. Blackout winner.
  2. Most accepted prize claims.
  3. Most confirmed cells.
  4. Earliest last accepted claim timestamp.

If no blackout happens before time expires, rank by accepted claims and confirmed cells.

## Spectator/TV UX

Spectator should motivate the room without exposing unnecessary personal data:

- Timer.
- Number of active players.
- Prize winners.
- Leaderboard by confirmed cell count.
- Prompt highlights such as "Most matched prompt" without listing everyone.
- Recent confirmations in safe form, for example "A match was confirmed for likes spicy food."

Avoid:

- Showing every player's full card by default.
- Showing denied confirmations publicly.
- Showing sensitive/custom prompts that were flagged as private.

## Player UX

Player surface:

- Bingo-style card.
- Tap cell to pick matched person.
- Pending/confirmed/denied states.
- Incoming confirmation requests.
- Claim buttons when a pattern looks complete.
- Clear "Go talk to people" empty/waiting copy.

Incoming confirmation request:

```text
Avi says you match: "can play a musical instrument"
Confirm?
```

Buttons:

- `Confirm`
- `Not me`

## Organizer UX

Setup:

- Choose template or AI generate from event theme.
- Edit prompt list.
- Choose confirmation mode.
- Choose layout and patterns.
- Start room.

In-game:

- Timer.
- Winners/claims.
- End game.
- Optional: approve/reject disputed claim in a later phase.

## Backend Implementation

Add:

```text
backend/find_someone_engine.py
backend/tests/test_find_someone_engine.py
```

Pure helpers:

```py
def validate_find_someone_setup(raw: dict) -> dict: ...

def generate_find_someone_card(setup: dict, player_id: str, seed: str | None = None) -> dict: ...

def create_confirmation_request(card: dict, prompt_id: str, player_id: str, matched_player_id: str) -> dict: ...

def apply_confirmation(card: dict, request: dict, accepted: bool) -> dict: ...

def validate_claim(card: dict, pattern_id: str, setup: dict) -> tuple[bool, str, list[dict]]: ...

def summarize_progress(cards_by_player: dict) -> dict: ...
```

Reuse where practical:

- Bingo card layout helpers.
- Bingo pattern validation shape.
- Existing player roster and socket sync.
- Existing confetti/podium components.

## AI Generation

Endpoint can mirror Bingo text generation:

```json
{
  "prompt": "company offsite for engineers",
  "difficulty": "work_safe",
  "num_items": 40,
  "mode": "find_someone_who"
}
```

Output:

```json
{
  "game_title": "Find Someone Who",
  "prompts": [
    {"display": "has worked on a side project this year", "category": "work_safe"}
  ]
}
```

Validation must reject unsafe/sensitive prompts even if generated.

## Revelry / Host-App Fit

This game is a strong Revelry fit because it is event/party-native.

Expose to host-app only after:

- Standalone runtime is tested.
- Result summary includes winners and aggregate participation only.
- Safe prompt generation and editing are covered.
- No sensitive prompt categories are returned through callbacks.

Result summary should include:

```json
{
  "game_type": "find_someone_who",
  "winner_count": 3,
  "confirmed_match_count": 84,
  "top_players": [
    {"player_id": "p1", "place": 1, "claims": 2}
  ]
}
```

Do not include every prompt/person match in host-app callbacks.

## Testing Plan

Backend tests:

- Setup validation clamps layout, timers, prompt count, and confirmation mode.
- Card generation is deterministic by seed and unique enough across players.
- Self-match is rejected when disabled.
- Duplicate matched person is rejected when disabled.
- Tap-confirm requests can be accepted/denied only by the matched person.
- Confirmed cells count for claims; pending cells do not.
- First line, four corners, and blackout validate correctly.
- Result summary excludes per-cell personal match detail.

Frontend tests:

- Player card renders stable 4x4/5x5 layout.
- Mark-cell flow opens roster picker.
- Incoming confirmation request renders and responds.
- Claim button appears only when eligible.
- Spectator shows aggregate progress, not full private cards.

Playwright:

- Mobile player card can scroll/tap without layout shifts.
- 20+ player roster picker remains usable.
- Confirmation request is readable on small phones.
- Spectator leaderboard fits long names.

## Acceptance Criteria

- Host can create a Find Someone Who game with safe prompts.
- Players receive Bingo-style cards.
- Players can mark cells by selecting another player.
- Optional tap confirmation works.
- Claims validate server-side.
- Spectator shows aggregate progress and winners.
- Podium ranks by blackout/claims/confirmed cells.
- No sensitive personal detail is exposed in result summaries.
- Existing Bingo/Housie runtime remains unaffected.

## Future Work

- Team mode.
- QR-to-confirm so players can scan another player's phone after talking.
- Host dispute resolution.
- Event-specific templates: weddings, baby showers, college orientation, company offsites.
- Optional "meet everyone" mode where each person can match only one square per other player.
- Printable fallback boards for low-connectivity events.
