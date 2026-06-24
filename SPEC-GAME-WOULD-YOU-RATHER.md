# LocalPlay Would You Rather Game Spec

## Overview

Add **Would You Rather** as a fast binary-vote party game where players choose between two playful options, the TV reveals the split, and the room debates the result.

```text
GameType: would_you_rather
Runtime family: social_vote
Backend engine: would_you_rather_engine.py
Frontend display name: Would You Rather
```

This is intentionally close to Most Likely To and Fact or Fiction in pacing, but the voting shape is binary and opinion-based rather than person-targeted or truth-based.

## Implementation-Ready MVP Scope

Status: backend engine foundation implemented on June 24, 2026. `backend/would_you_rather_engine.py` owns prompt validation, round state, binary vote capture, reveal, split calculation, optional majority scoring, public-state redaction, and pure tests. Remaining MVP work is catalog exposure, AI/manual setup UI, room/socket events, player voting UI, spectator reveal UI, and Playwright end-to-end coverage.

- Host starts with curated prompts or AI-generated prompts from a theme.
- Each prompt has exactly two options.
- Every connected player can vote once per round.
- Players can change their vote until reveal.
- TV/spectator view shows the prompt and options during voting, then the final split on reveal.
- Optional scoring gives one point to players who picked the majority option.
- Host can advance rounds manually in MVP.
- Late joiners can vote on the current unrevealed round.

## Goals

- Add a low-friction party game that works with very small or large groups.
- Reuse LocalPlay's room/lobby/spectator model.
- Keep prompts safe and non-personal by default.
- Make it fun for Revelry parties where people may join mid-event.
- Provide a strong AI prompt target for weddings, birthdays, baby showers, team events, and family gatherings.

## Non-Goals

- No anonymous confession mechanics.
- No free-text player submissions in MVP.
- No personal targeting or demographic targeting.
- No elimination.
- No persistent profile preferences.
- No real rewards or sparks tied to choices.

## Game Rules

1. Host chooses or generates a prompt set.
2. Players join the lobby.
3. Host starts the game.
4. The current prompt appears with two options.
5. Players vote for option A or option B on their phones.
6. Spectator view may show vote count progress, but not individual votes before reveal.
7. Host reveals the round.
8. TV shows the final split, majority option, and optionally funny copy for ties.
9. If scoring is enabled, players on the majority side gain one point.
10. Host advances to the next prompt.
11. Final podium ranks by majority picks, with ties allowed.

## Setup

```json
{
  "game_type": "would_you_rather",
  "game_title": "Would You Rather",
  "theme": "birthday party",
  "round_count": 10,
  "scoring_mode": "majority",
  "show_live_counts": false,
  "allow_vote_changes": true
}
```

Defaults:

- `round_count`: 10.
- `scoring_mode`: `majority`.
- `show_live_counts`: false.
- `allow_vote_changes`: true.

Validation:

- `round_count`: 3-25.
- Prompt text: 4-120 characters.
- Option text: 1-80 characters.
- Minimum players: 1 for party-mode usability, recommended 3+.

## Prompt Model

```ts
export interface WouldYouRatherPrompt {
  id: string;
  question: string;
  option_a: string;
  option_b: string;
  category?: string;
}

export interface WouldYouRatherGame {
  game_title: string;
  theme?: string;
  prompts: WouldYouRatherPrompt[];
  round_count: number;
  scoring_mode: 'none' | 'majority';
  show_live_counts: boolean;
  allow_vote_changes: boolean;
}
```

Good prompts:

```text
Would you rather have unlimited snacks or unlimited party music?
Would you rather travel by teleporting or flying?
Would you rather only speak in movie quotes or only communicate with emojis?
```

Avoid:

- Protected-class or demographic comparisons.
- Sexual, humiliating, cruel, or exclusionary choices.
- Prompts that reveal private information.
- Choices that imply unsafe behavior.

## Backend Events

Client to server:

```json
{ "type": "WYR_VOTE", "choice": "A" }
{ "type": "WYR_REVEAL" }
{ "type": "WYR_NEXT_ROUND" }
```

Server to clients:

```json
{ "type": "ROOM_STATE", "state": { "would_you_rather": { "...": "..." } } }
{ "type": "WYR_VOTE_ACK", "round_index": 0, "choice": "A" }
{ "type": "GAME_OVER", "results": [] }
```

## Redaction Rules

- Before reveal, public state includes each player's own vote only on that player's private payload.
- Before reveal, spectator state includes total submitted count, not individual votes.
- If `show_live_counts` is false, spectator state hides option counts until reveal.
- After reveal, public state includes counts, percentages, and the majority option.

## Scoring

MVP scoring mode:

- `none`: no points, just results.
- `majority`: each player who picked the majority option gets 1 point.
- Ties award no points.

Final standings sort by score desc, then stable join order.

## Revelry Integration

Would You Rather is a future Revelry quick-start candidate, but should not be enabled until:

- Runtime socket events exist.
- Player and spectator UI are implemented.
- Rules metadata is present in the LocalPlay catalog.
- Gamma multi-tab smoke verifies host, player, spectator, late join, and final result.

## Test Plan

Unit tests:

- Config validation sanitizes prompts and options.
- Voting records one vote per player and supports change before reveal.
- Reveal computes counts, percentages, majority, and scores.
- Tie reveal awards no majority score.
- Next round resets votes and advances.
- Public state hides individual votes before reveal.

Integration tests after UI/socket implementation:

- Host creates AI/manual prompt set.
- Two players vote and reveal.
- Late join can vote before reveal.
- Spectator sees no private vote details before reveal.
- Final podium is stable.

## Open Follow-Ups

- Decide whether the first UI slice should reuse Most Likely To components.
- Add AI generator prompt once the game is catalog-exposed.
- Consider a debate/re-vote mode after MVP.
