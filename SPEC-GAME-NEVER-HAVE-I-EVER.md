# LocalPlay Never Have I Ever Game Spec

## Overview

Add **Never Have I Ever** as a light binary-vote party game where players privately answer whether they have done a prompt, then the room sees the group split.

```text
GameType: never_have_i_ever
Runtime family: social_vote
Backend engine: never_have_i_ever_engine.py
Frontend display name: Never Have I Ever
```

## Implementation-Ready MVP Scope

Status: backend engine foundation implemented on June 24, 2026. `backend/never_have_i_ever_engine.py` owns prompt validation, player answer capture, reveal splits, optional minority scoring, redaction, late join, podium transition, and pure tests. Remaining MVP work is catalog exposure, setup/AI UI, socket events, player answer UI, spectator reveal UI, rules metadata, and Playwright coverage.

- Host starts from curated or AI-generated prompts.
- Players answer `have` or `never`.
- Players may change their answer until reveal when allowed.
- Spectator sees submitted count before reveal, not individual answers.
- Reveal shows counts and percentages.
- Scoring is optional. MVP supports `none` and `minority` modes.
- Host manually advances rounds in MVP.

## Rules

1. A prompt appears, e.g. "Never have I ever sung karaoke in public."
2. Each player answers `I have` or `Never`.
3. The host reveals the room split.
4. If minority scoring is on, players in the smaller group get one point.
5. Ties award no points.
6. Continue until prompts are exhausted.

## Setup

```json
{
  "game_type": "never_have_i_ever",
  "game_title": "Never Have I Ever",
  "theme": "birthday party",
  "round_count": 10,
  "safe_level": "family",
  "scoring_mode": "none",
  "show_live_counts": false,
  "allow_answer_changes": true
}
```

Validation:

- `round_count`: 3-25.
- `safe_level`: `family`, `work`, `party`, or `spicy`.
- Prompt text: 8-140 characters.
- Minimum players: 1, recommended 4+.

## Content Model

```ts
export interface NeverHaveIEverPrompt {
  id: string;
  statement: string;
  category?: string;
}

export interface NeverHaveIEverGame {
  game_title: string;
  safe_level: 'family' | 'work' | 'party' | 'spicy';
  scoring_mode: 'none' | 'minority';
  prompts: NeverHaveIEverPrompt[];
}
```

## Redaction Rules

- Before reveal, public state includes submitted count only.
- A player can see their own answer.
- After reveal, public state includes answer counts and individual answers.

## AI Prompt Guidance

Generate prompts that are playful, broadly answerable, and safe for the selected level. Avoid protected-class targeting, humiliation, sexual coercion, illegal activity, medical/private data, or prompts that pressure players to reveal sensitive information.

## Revelry Readiness

Do not enable in Revelry catalog until the runtime socket/UI slice is complete and gamma has multi-tab tests for host, player, spectator, late join, and reveal.
