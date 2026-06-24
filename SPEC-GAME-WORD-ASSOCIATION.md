# LocalPlay Word Association Game Spec

## Overview

Add **Word Association** as a fast simultaneous text game. A seed word appears, everyone submits the first related word that comes to mind, and the reveal groups matching answers.

```text
GameType: word_association
Runtime family: text_submit_reveal
Backend engine: word_association_engine.py
Frontend display name: Word Association
```

## Implementation-Ready MVP Scope

Status: standalone playable MVP implemented on June 24, 2026. `backend/word_association_engine.py` owns seed validation, submission capture, normalization/grouping, majority scoring, redaction, late join, podium transition, standings, and pure tests. LocalPlay now exposes the game in the standalone catalog with default content, room creation, WebSocket sync, organizer/player/spectator UI, rules metadata, reconnect handling, podium flow, and focused API/socket regression tests. Remaining follow-ups are setup/AI authoring UI and broader Playwright matrix coverage.

- Host starts from curated or AI-generated seed words.
- Players submit one association per round.
- Players may edit before reveal when allowed.
- Reveal groups normalized matches while preserving display text.
- Majority group scores one point; tied majority groups all score unless every answer is unique.
- Host manually advances rounds in MVP.

## Rules

1. A seed appears, e.g. `Birthday`.
2. Players type the first related word or short phrase they think of.
3. The host reveals submissions grouped by match.
4. Players in the biggest matching group score.
5. If every answer is unique, nobody scores.
6. Highest score after all seeds wins.

## Setup

```json
{
  "game_type": "word_association",
  "game_title": "Word Association",
  "theme": "party",
  "round_count": 10,
  "scoring_mode": "majority",
  "allow_submission_changes": true
}
```

Validation:

- `round_count`: 3-25.
- Seed text: 1-60 characters.
- Submission text: 1-80 characters.
- Minimum players: 1, recommended 4+.

## Content Model

```ts
export interface WordAssociationSeed {
  id: string;
  seed: string;
  category?: string;
}

export interface WordAssociationGame {
  game_title: string;
  scoring_mode: 'none' | 'majority';
  seeds: WordAssociationSeed[];
}
```

## Redaction Rules

- Before reveal, public state includes submitted count only.
- A player can see their own submission.
- After reveal, public state includes grouped answers and player ids.

## AI Prompt Guidance

Generate seed words that are concrete, party-safe, culturally broad, and likely to produce fun clusters. Avoid names of private attendees unless explicitly supplied by the host.

## Revelry Readiness

Word Association is LocalPlay bridge-ready as a Revelry quick-start/settings game:

- `host_app_supported = true`, `supported_host_apps = ["revelry"]`
- `can_quick_start = true`
- `can_create_content = false`
- `can_edit_content = false`
- `supports_ai_generation = false`

It remains policy-gated. Revelry should show/start it only when LocalPlay's host-app catalog policy exposes it and gamma multi-tab tests cover submission, reveal grouping, late join, and final results.
