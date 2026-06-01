# LocalPlay Common Ground Game Spec

## Overview

Add **Common Ground** as a team-based icebreaker where small groups discover things they all have in common, submit their best shared facts, and optionally vote on the most surprising or fun answers.

This is a social conversation game, not trivia. The app gives structure, timers, team assignment, submission, reveal, voting, and scoring. The actual fun happens in the room as people talk.

```text
GameType: common_ground
Runtime family: social_icebreaker
Backend engine: common_ground_engine.py
Frontend display name: Common Ground
```

## Implementation-Ready MVP Scope

Status: implementation-ready.

- Standalone LocalPlay first.
- Host chooses team size, number of rounds, timer, and optional theme.
- Server creates small teams from connected players.
- Each round gives all teams the same prompt category or open challenge.
- Teams discuss in person and submit shared facts that are true for every team member.
- Spectator/TV shows timer, teams, submission status, and reveal.
- Optional voting phase lets players vote for funniest, most surprising, or most specific shared fact.
- Final ranking uses submitted facts plus voting bonuses.

## Goals

- Create a fast, friendly icebreaker for people who may not know each other.
- Encourage team conversation without asking for sensitive personal disclosure.
- Work well for company offsites, classrooms, meetups, weddings, family parties, and new groups.
- Support both structured prompts and open "find 3 things in common" mode.
- Keep implementation simpler than games with hidden roles or image uploads.
- Make TV/spectator mode central to the reveal.

## Non-Goals

- No demographic targeting or protected-class prompts.
- No prompts that pressure private/sensitive disclosure.
- No automatic truth verification.
- No persistent public profiles.
- No remote chat in MVP; discussion happens in person.
- No real-money prizes or economy-linked rewards.

## Game Modes

### Classic Common Ground

Each team must submit N shared facts within the timer.

Example:

```text
Find 3 things everyone on your team has in common.
```

### Prompted Rounds

Each round narrows the category:

```text
Find something everyone on your team has eaten.
Find a place everyone on your team has visited.
Find something everyone on your team liked as a kid.
Find a song or artist everyone on your team knows.
```

### One Best Fact

Each team submits one strong shared fact per round. Then everyone votes.

This is recommended for MVP because it creates a cleaner spectator reveal and avoids too much typing.

## Prompt Safety Rules

Prompts must be light, voluntary, and inclusive.

Good prompts:

```text
something everyone has eaten
a place everyone has visited
a movie everyone has seen
a hobby everyone has tried
something everyone wanted to be as a kid
a food everyone likes
a song everyone recognizes
```

Avoid:

- Race, ethnicity, nationality, religion, caste, sexuality, gender identity, disability, age, family status, or other protected-class targeting.
- Income, immigration, medical, trauma, criminal history, politics, or sexual topics.
- Anything that singles out one person.
- Anything requiring documents, addresses, employer secrets, or private screens.

AI prompt generation must include:

```text
Generate only light, voluntary, inclusive icebreaker prompts. Avoid sensitive personal data and protected-class targeting.
```

## Setup

```json
{
  "game_type": "common_ground",
  "game_title": "Common Ground",
  "mode": "one_best_fact",
  "team_size": 3,
  "rounds": 5,
  "discussion_time_seconds": 90,
  "vote_time_seconds": 30,
  "facts_per_round": 1,
  "voting_enabled": true,
  "vote_category": "most_surprising",
  "theme": "work_safe"
}
```

Defaults:

- `mode`: `one_best_fact`.
- `team_size`: 3.
- `rounds`: 5.
- `discussion_time_seconds`: 90.
- `vote_time_seconds`: 30.
- `facts_per_round`: 1.
- `voting_enabled`: true.
- `vote_category`: `most_surprising`.
- `theme`: `work_safe`.

Validation:

- Minimum players: 4.
- Recommended players: 6-60.
- Team size: 2-6.
- Rounds: 1-10.
- Discussion time: 30-300 seconds.
- Vote time: 10-90 seconds.
- Facts per round: 1-5.

## Team Assignment

Server assigns teams when the game starts.

Rules:

- Try to create teams of `team_size`.
- Avoid teams of 1. If there is a remainder of 1, distribute players across existing teams.
- Keep teams stable for the full game in MVP.
- Future mode can reshuffle teams every round.

Example:

```json
{
  "teams": [
    {"id": "team_1", "name": "Team A", "player_ids": ["p1", "p2", "p3"]},
    {"id": "team_2", "name": "Team B", "player_ids": ["p4", "p5", "p6", "p7"]}
  ]
}
```

## Content Model

```ts
export interface CommonGroundPrompt {
  id: string;
  text: string;
  category?: 'open' | 'food' | 'travel' | 'childhood' | 'music' | 'hobbies' | 'work_safe';
}

export interface CommonGroundGame {
  game_title: string;
  mode: 'classic' | 'prompted' | 'one_best_fact';
  prompts: CommonGroundPrompt[];
  team_size: number;
  rounds: number;
  discussion_time_seconds: number;
  vote_time_seconds: number;
  facts_per_round: number;
  voting_enabled: boolean;
  vote_category: 'funniest' | 'most_surprising' | 'most_specific';
}
```

Live round:

```ts
export interface CommonGroundRound {
  round_number: number;
  prompt_id: string;
  phase: 'DISCUSSION' | 'SUBMISSION_REVIEW' | 'REVEAL' | 'VOTING' | 'ROUND_RESULT';
  submissions_by_team: Record<string, CommonGroundSubmission[]>;
  votes_by_player: Record<string, string>;
  started_at: number;
  deadline: number;
}

export interface CommonGroundSubmission {
  id: string;
  team_id: string;
  text: string;
  submitted_by: string;
  created_at: number;
}
```

## Runtime Flow

1. Host creates or selects a Common Ground game.
2. Players join the room.
3. Host starts the game.
4. Server assigns teams.
5. Round starts with a prompt and discussion timer.
6. Team members talk in person.
7. One member per team submits the team's shared fact(s).
8. When all teams submit or timer ends, server moves to reveal.
9. Spectator/TV reveals team submissions.
10. If voting is enabled, players vote on submissions from other teams.
11. Server scores the round.
12. Next round starts.
13. Final podium ranks teams.

## Submission Rules

- Any team member can submit or edit the team's answer while the discussion timer is active.
- Last edit before deadline wins.
- Submissions are team-visible while editing.
- Other teams do not see submissions until reveal.
- Empty submissions score zero for that round.
- Team members cannot vote for their own team's submission.

## WebSocket Events

Client to server:

```json
{ "type": "COMMON_SUBMIT_FACT", "text": "We have all lived near the ocean" }
{ "type": "COMMON_EDIT_FACT", "submission_id": "s1", "text": "We have all lived near water" }
{ "type": "COMMON_VOTE", "submission_id": "s2" }
{ "type": "COMMON_NEXT_ROUND" }
```

Server to clients:

```json
{ "type": "COMMON_SYNC", "state": {} }
{ "type": "COMMON_TEAMS_ASSIGNED", "teams": [] }
{ "type": "COMMON_ROUND_STARTED", "round": {} }
{ "type": "COMMON_TEAM_SUBMITTED", "team_id": "team_1" }
{ "type": "COMMON_REVEAL", "submissions": [] }
{ "type": "COMMON_ROUND_RESULT", "scores": [] }
```

Visibility:

- Team submissions are private to that team during discussion.
- Spectator sees submission progress only, not text, until reveal.
- Votes are private until the result.
- Final result can show vote totals, not individual votes.

## Scoring

Default scoring:

| Event | Points |
|---|---:|
| Valid submission | 100 |
| First team to submit | +50 |
| Each vote received | +100 |
| All team members vote | +25 team bonus |

If voting is disabled:

- Each valid submission earns 100.
- First team to submit earns +50.
- Optional host-selected winner is future work, not MVP.

Tie-breakers:

1. More votes received.
2. More rounds with valid submissions.
3. Earlier final submission timestamp.

## Spectator/TV UX

Spectator view should be lively and legible:

- Current prompt.
- Team list with avatars/names.
- Countdown timer.
- Submission status per team.
- Reveal cards for each team's shared fact.
- Vote category, e.g. "Vote: most surprising."
- Round winner and running leaderboard.

Avoid:

- Showing submission text before reveal.
- Showing individual vote choices.
- Overloading the screen with all players in very large rooms; collapse team rosters if needed.

## Player UX

Player view:

- Team name and teammates.
- Current prompt.
- Discussion timer.
- Team submission editor.
- Submit/edit button.
- Voting screen after reveal.
- Team score and leaderboard.

For large groups, only one editor should be active at a time:

- Simple MVP: every teammate can edit, last write wins.
- Later: team can choose a scribe.

## Organizer UX

Setup:

- Team size.
- Rounds.
- Timer.
- Prompt mode/theme.
- Voting on/off and vote category.
- Manual prompt editor or AI generate.

In-game:

- Start/next round.
- Extend timer.
- Skip to reveal.
- End game.

## Backend Implementation

Add:

```text
backend/common_ground_engine.py
backend/tests/test_common_ground_engine.py
```

Pure helpers:

```py
def validate_common_ground_setup(raw: dict) -> dict: ...

def assign_teams(player_ids: list[str], team_size: int, seed: str | None = None) -> list[dict]: ...

def start_round(state: dict, now: float) -> dict: ...

def submit_fact(state: dict, player_id: str, text: str, now: float) -> tuple[dict, dict]: ...

def submit_vote(state: dict, player_id: str, submission_id: str) -> tuple[dict, dict]: ...

def score_round(state: dict) -> dict: ...

def build_public_sync(state: dict) -> dict: ...

def build_player_sync(state: dict, player_id: str) -> dict: ...
```

## AI Generation

Prompt generation can reuse the existing AI pattern:

```json
{
  "prompt": "new hire offsite, work-safe, engineering team",
  "difficulty": "work_safe",
  "num_items": 10,
  "mode": "common_ground"
}
```

Output:

```json
{
  "game_title": "Common Ground",
  "prompts": [
    {"text": "Find a food everyone on your team likes.", "category": "food"}
  ]
}
```

Generated prompts must be host-reviewed before room start.

## Revelry / Host-App Fit

Common Ground is a strong Revelry fit because it is party/event native and safe for mixed groups.

Expose to host-app only after:

- Standalone runtime has E2E coverage.
- Result summary has team winners and aggregate stats only.
- Prompt generation safety is tested.
- No team submission text is sent back through callbacks unless explicitly allowed as safe summary text.

Safe result summary:

```json
{
  "game_type": "common_ground",
  "teams": 4,
  "rounds_played": 5,
  "winning_team": "team_2",
  "submission_count": 20
}
```

## Testing Plan

Backend tests:

- Setup validation clamps team size, rounds, timers, and facts per round.
- Team assignment avoids teams of 1 when possible.
- Team assignment is deterministic with seed.
- Only team members can edit their team's submission.
- Submissions are hidden from other teams before reveal.
- Players cannot vote for their own team.
- Duplicate votes update or reject according to chosen rule.
- Round scoring handles votes and bonuses.
- Public sync hides private submission text before reveal.

Frontend tests:

- Setup renders team/timer/voting controls.
- Player sees team and prompt.
- Team submission editor works.
- Reveal shows all submissions.
- Voting excludes own team.
- Spectator shows prompt, timer, submission status, and reveal.

Playwright:

- Mobile team submission flow.
- Desktop spectator reveal with 6+ teams.
- Voting layout with long submissions.
- Final podium for teams.

## Acceptance Criteria

- Host can create a Common Ground room with 4+ players.
- Server assigns teams without single-person teams where possible.
- Teams can submit shared facts.
- Other teams cannot see submission text before reveal.
- Optional voting works and excludes own team.
- Scores and final team podium are deterministic.
- Spectator view is useful throughout discussion, reveal, voting, and results.
- Prompt generation avoids sensitive personal disclosure.

## Future Work

- Reshuffle teams every round.
- Team scribe selection.
- Host moderation/edit before reveal.
- "No repeats" validation across teams.
- Similarity grouping for duplicate common-ground facts.
- Theme packs: new hires, weddings, classrooms, family reunion, baby shower.
- Hybrid/remote typed team chat.
