# LocalPlay Acronym Game Spec

## Overview

Add **Acronym Game** as an anonymous submit-then-vote party game. The room gets a short acronym, players invent funny expansions, then everyone votes for a favorite.

```text
GameType: acronym
Runtime family: submit_vote_reveal
Backend engine: acronym_engine.py
Frontend display name: Acronym Game
```

## Implementation-Ready MVP Scope

Status: standalone playable MVP implemented on June 24, 2026. `backend/acronym_engine.py` owns acronym validation, expansion validation, anonymous voting payloads, vote capture, reveal, scoring, redaction, late join, podium transition, standings, and pure tests. LocalPlay now exposes the game in the standalone catalog with default content, room creation, WebSocket sync, organizer/player/spectator UI, rules metadata, reconnect handling, podium flow, and focused API/socket regression tests. Remaining follow-ups are setup/AI authoring UI and broader Playwright matrix coverage.

- Host starts from curated or AI-generated acronyms.
- Each player submits one expansion per round.
- Expansion words must match the acronym letters.
- Voting view shows anonymous entries.
- Players cannot vote for their own entry.
- Submitters score one point per vote.
- Host manually advances through submit, vote, reveal phases in MVP.

## Rules

1. An acronym appears, e.g. `PARTY`.
2. Players submit an expansion like `Pancakes Are Really Too Yummy`.
3. The host opens voting.
4. Players vote for the funniest or best expansion.
5. The reveal shows authors, votes, and scores.
6. Highest score after all acronyms wins.

## Setup

```json
{
  "game_type": "acronym",
  "game_title": "Acronym Game",
  "theme": "birthday",
  "round_count": 8,
  "letters_min": 3,
  "letters_max": 6,
  "allow_submission_changes": true
}
```

Validation:

- `round_count`: 3-20.
- Acronym: 2-8 letters, A-Z only.
- Expansion: one word per acronym letter, each word starts with the matching letter.
- Minimum players: 2, recommended 4+.

## Content Model

```ts
export interface AcronymPrompt {
  id: string;
  acronym: string;
  hint?: string;
  category?: string;
}

export interface AcronymGame {
  game_title: string;
  prompts: AcronymPrompt[];
  scoring_mode: 'votes';
}
```

## Redaction Rules

- During submission, public state includes submitted count only.
- During voting, entries are anonymous and shuffled by stable entry id.
- A player sees their own entry id to prevent self-vote confusion.
- During reveal, authors and vote totals become public.

## AI Prompt Guidance

Generate short pronounceable acronyms with party-safe hints. Avoid acronyms that form slurs, adult terms, political attacks, or protected-class references.

## Revelry Readiness

Acronym Game is LocalPlay bridge-ready as a Revelry quick-start/settings game:

- `host_app_supported = true`, `supported_host_apps = ["revelry"]`
- `can_quick_start = true`
- `can_create_content = false`
- `can_edit_content = false`
- `supports_ai_generation = false`

It remains policy-gated. Revelry should show/start it only when LocalPlay's host-app catalog policy exposes it and gamma multi-tab tests cover submit, anonymous voting, reveal, late join, and final results. Future embedded authoring can reuse the same style as Random Chit and Most Likely To.
