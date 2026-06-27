# LocalPlay Two Truths and a Lie Game Spec

## Overview

Add **Two Truths and a Lie** as a player-authored icebreaker where each player writes three statements about themselves, marks one as the lie, and the room guesses which statement is false.

This is one of the most obvious LocalPlay social games: simple, low-AI, high conversation value, and excellent for groups that are getting to know each other.

```text
GameType: two_truths
Runtime family: social_icebreaker
Backend engine: two_truths_engine.py
Frontend display name: Two Truths and a Lie
```

## Implementation Status

Status: standalone MVP implemented locally.

Implemented:

- `backend/two_truths_engine.py` pure runtime engine.
- `/room/create` support for `game_type = two_truths`.
- Catalog card and standalone organizer quick-start flow.
- WebSocket runtime with `TT_SYNC`, `TT_SUBMIT_STATEMENTS`, `TT_VOTE`, `TT_START_REVEAL`, and `TT_NEXT_AUTHOR`.
- Organizer, player, and spectator screens using a shared `TwoTruthsGame` component.
- Backend engine/API tests, frontend unit suite, and production frontend build verification.

Not implemented in the first slice:

- AI inspiration.
- Auto-paced timers.
- Host moderation/editing of player statements.
- Revelry exposure.

## MVP Scope

- Standalone LocalPlay first.
- Every player submits exactly three statements:
  - two true
  - one lie
- Players privately mark which statement is the lie.
- Server validates completion before the reveal phase starts.
- Each round reveals one player's three statements.
- Everyone except the author votes on which statement is the lie.
- Reveal shows the lie, vote distribution, and who guessed correctly.
- Scoring rewards both:
  - guessing correctly
  - fooling others with your lie
- Final podium ranks individual players.
- AI is optional inspiration only, not required for MVP.

## Goals

- Create a classic, instantly understood icebreaker.
- Keep the authoring flow fast and mobile-friendly.
- Preserve privacy until reveal: players' statements stay hidden until their round.
- Make the TV reveal suspenseful and readable.
- Support host-paced and auto-paced modes.
- Avoid sensitive prompt pressure.

## Non-Goals

- No verification of whether statements are truly true or false.
- No AI-generated personal statements as a default.
- No public profile or permanent statement archive.
- No sensitive personal data prompts.
- No anonymous insult/roast mode.
- No real-money prizes or economy-linked rewards.

## Safety and Content Guidance

This game asks players to disclose personal facts, so the UX should nudge safe choices.

Setup/help copy:

```text
Keep it light. Share things you are comfortable telling this room.
```

Good statement examples:

```text
I once missed a flight because I was buying snacks.
I can solve a Rubik's Cube.
I have been on live TV.
I hate coriander.
I once met a famous actor at an airport.
```

Avoid nudging players toward:

- Medical history.
- Legal/criminal history.
- Immigration or visa status.
- Income or debt.
- Politics or religion.
- Sexual content.
- Family status.
- Trauma or embarrassing private disclosures.

AI inspiration must generate safe, generic idea prompts, not fabricated personal statements.

## Setup

```json
{
  "game_type": "two_truths",
  "game_title": "Two Truths and a Lie",
  "submission_time_seconds": 180,
  "vote_time_seconds": 30,
  "reveal_mode": "host_paced",
  "shuffle_statement_order": true,
  "allow_ai_inspiration": true
}
```

Defaults:

- `submission_time_seconds`: 180.
- `vote_time_seconds`: 30.
- `reveal_mode`: `host_paced`.
- `shuffle_statement_order`: true.
- `allow_ai_inspiration`: true.

Validation:

- Minimum players: 3.
- Recommended players: 4-30.
- Submission time: 60-600 seconds.
- Vote time: 10-90 seconds.
- Statement length: 3-180 chars. The UI should explain this minimum instead of silently disabling submit.

## Content Model

```ts
export interface TwoTruthsSubmission {
  player_id: string;
  statements: TwoTruthsStatement[];
  submitted_at: number;
  updated_at: number;
}

export interface TwoTruthsStatement {
  id: string;
  text: string;
  is_lie: boolean;
  display_order: number;
}

export interface TwoTruthsGameState {
  phase: 'TT_SUBMISSION' | 'TT_VOTING' | 'TT_RESULT' | 'PODIUM';
  current_author_id?: string;
  reveal_order: string[];
  submissions_by_player: Record<string, TwoTruthsSubmission>;
  votes_by_round: Record<string, Record<string, string>>;
  scores: Record<string, number>;
}
```

Public reveal payload must not include `is_lie` until result.

## Runtime Flow

1. Host creates the game.
2. Players join.
3. Host starts submission phase.
4. Each player writes three statements and marks the lie.
5. Server stores each submission privately.
6. When the host starts reveal, server creates reveal order from submitted players.
7. Round begins for author 1.
8. TV/player screens show the author's three shuffled statements.
9. Everyone except the author votes for the lie.
10. Host closes voting to reveal the result.
11. Result reveals the lie and vote distribution.
12. Scores update.
13. Host/auto advances to next author.
14. Final podium after every submitted author has been revealed.

## Submission Phase

Player requirements:

- Exactly three non-empty statements.
- Each statement must be at least 3 characters.
- Exactly one lie selected.
- Statements must be unique after normalization.
- Author can edit until reveal starts.
- Author cannot see other players' statements before reveal.

Server should allow late joiners during submission:

- If they submit before reveal starts, include them.
- New players are currently blocked once the room is locked and the game starts.

## Reveal and Voting

Eligible voters:

- All connected players except the current author.
- Late joiners may vote if they are in the room before the vote closes.

Voting rules:

- One vote per voter per author round.
- Voters can change vote until the timer ends.
- Author cannot vote on their own statements.
- Votes are hidden until result.

Statement order:

- If `shuffle_statement_order = true`, server shuffles each author's three statements before reveal.
- Store `display_order` so all clients see the same order.

## WebSocket Events

Client to server:

```json
{ "type": "TT_SUBMIT_STATEMENTS", "statements": [{"text": "...", "is_lie": false}] }
{ "type": "TT_VOTE", "statement_id": "stmt_2" }
{ "type": "TT_START_REVEAL" }
{ "type": "TT_NEXT_AUTHOR" }
```

Server to clients:

```json
{ "type": "TT_SYNC", "state": {} }
{ "type": "TT_SUBMISSION_STATUS", "submitted_count": 4, "total_players": 6 }
{ "type": "TT_REVEAL_AUTHOR", "author_id": "p1", "statements": [] }
{ "type": "TT_VOTE_ACCEPTED", "statement_id": "stmt_2" }
{ "type": "TT_ROUND_RESULT", "lie_statement_id": "stmt_2", "votes": {} }
{ "type": "TT_GAME_RESULT", "standings": [] }
```

Visibility:

- During submission, a player sees only their own submission.
- During reveal/voting, clients see current author's statement text but not `is_lie`.
- During result, clients see the lie and aggregate votes.
- Individual vote choices may be shown in result only if product decides it is fun; MVP should show aggregate counts plus "you were right/wrong" privately.

## Scoring

Default scoring:

| Event | Points |
|---|---:|
| Correctly identifies lie | 500 |
| Author fools a voter | 250 per fooled voter |
| Author fools everyone | +500 bonus |
| Everyone guesses author's lie | author gets 0 deception bonus |

Examples:

- If 5 people vote and 2 guess correctly, 3 were fooled.
- Author gets `3 * 250 = 750`.
- Correct voters each get `500`.

Tie-breakers (planned, not yet implemented):

1. More correct guesses.
2. More fooled-voter points.
3. Earlier completed submission.

> Current code: `final_standings` breaks ties by score then alphabetically by nickname (`correct_guesses` / `fooled_points` are reported per player but not yet used for ordering). The richer tie-breakers above are a follow-up.

## Spectator/TV UX

Submission phase:

- Show room title.
- Submitted count.
- Waiting players by avatar/name.
- Gentle guidance: "Write two true statements and one lie."

Voting phase:

- Author name/avatar.
- Three large statement cards labeled A/B/C.
- Timer.
- Vote count progress.

Result:

- Highlight the lie.
- Show vote distribution bars.
- Show who guessed correctly privately on player devices; TV can show count.
- Show score changes and leaderboard.

## Player UX

Submission:

- Three text fields.
- Lie selector using segmented buttons or radio chips.
- Save/ready button.
- Optional "Give me ideas" button for safe inspiration.

Voting:

- Three statement buttons.
- Selected state.
- Timer.
- Author sees waiting state, not voting buttons.

Result:

- "You got it" / "Fooled" feedback.
- Score delta.

## Organizer UX

Setup:

- Timer settings.
- Host-paced vs auto-paced.
- AI inspiration toggle.

Submission phase:

- Submitted roster.
- Start reveal button once minimum ready threshold is met.
- Optional extend timer.

Reveal phase:

- Next author.
- Skip missing author.
- End game.

## Backend Implementation

Added:

```text
backend/two_truths_engine.py
backend/tests/test_two_truths_engine.py
```

Pure helpers:

```py
def validate_config(raw: dict) -> dict: ...

def validate_submission(raw_statements: list[dict], max_chars: int = 180) -> list[dict]: ...

def create_initial_state(player_ids: list[str], config: dict, seed: int | None = None) -> dict: ...

def submit_statements(state: dict, player_id: str, raw_statements: list[dict], now: float | None = None) -> dict: ...

def start_reveal(state: dict) -> dict: ...

def next_author(state: dict) -> dict: ...

def reveal_payload(submission: dict | None, include_answer: bool = False) -> list[dict]: ...

def submit_vote(state: dict, voter_id: str, statement_id: str) -> dict: ...

def score_current_round(state: dict) -> dict: ...

def public_sync(state: dict, players: list[dict] | None = None) -> dict: ...

def private_sync(state: dict, player_id: str, players: list[dict] | None = None) -> dict: ...

def final_standings(state: dict) -> list[dict]: ...
```

## AI Inspiration

AI should not pretend to know facts about the player. It can suggest categories or templates:

```json
{
  "ideas": [
    "A strange travel mishap",
    "A food you secretly dislike",
    "A skill people would not expect",
    "A celebrity or public figure you once saw",
    "A childhood hobby"
  ]
}
```

Button copy:

```text
Give me ideas
```

Do not generate final statements by default, because the game is about real player-authored facts.

## Reconnects and Disconnects

- Reconnected player during submission receives their saved draft/submission.
- Reconnected voter receives current author round and their selected vote if any.
- If current author disconnects during their reveal round, continue; author is not required to act.
- If a voter disconnects, voting timer continues.
- If a player never submits, they are skipped as an author but may still vote.

## Revelry / Host-App Fit

This is a strong Revelry game because it is party-native and low-risk.

Host-app exposure requirements:

- Standalone runtime tested.
- Result callbacks include standings and aggregate counts only.
- Do not send player statement text back to Revelry by default.

Safe result summary:

```json
{
  "game_type": "two_truths",
  "authors_revealed": 6,
  "total_votes": 30,
  "top_players": [
    {"player_id": "p1", "place": 1, "score": 2500}
  ]
}
```

## Testing Plan

Backend tests:

- Config validation clamps timers/length.
- Submission requires exactly three statements.
- Submission requires exactly one lie.
- Duplicate normalized statements are rejected.
- Reveal payload hides `is_lie` before result.
- Author cannot vote on own statements.
- Voter can change vote before close.
- Scoring rewards correct guesses and fooled voters.
- Never-submitted players are skipped as authors.
- Reconnect payload restores own submission/vote.

Frontend tests:

- Submission form enforces three statements and one lie.
- Saved submission shows ready state.
- Reveal screen shows three statement cards.
- Author does not see voting buttons.
- Vote distribution renders on result.
- Podium shows final standings.

Playwright:

- Mobile submission form.
- Desktop TV reveal.
- Vote and result flow with 4 players.
- Long statements wrap cleanly.

## Acceptance Criteria

- Host can start with 3+ players.
- Players submit three statements and one lie.
- Other players vote on the lie.
- The lie is hidden until result.
- Scores are deterministic.
- Podium ranks players.
- Spectator view is clear and TV-friendly.
- No player statement text is sent to host-app callbacks by default.

## Future Work

- Anonymous author mode.
- Spicy/work-safe/family-safe presets.
- Host moderation before reveal.
- AI-assisted rewrite for clarity.
- Team mode.
- "Speed round" with one statement set per pair.
