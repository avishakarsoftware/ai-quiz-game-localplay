# LocalPlay Story Chain Game Spec

## Overview

Add **Story Chain** as a sequential creative party game where players collaboratively build a story one sentence at a time. Each player adds a sentence to the chain, then the TV reveals the increasingly strange story with dramatic pacing.

This is adjacent to Chinese Whispers / Telephone, but it is not about distortion or guessing. It is about collaborative escalation: every player contributes a sentence and the final story is the payoff.

```text
GameType: story_chain
Runtime family: creative_sequential
Backend engine: story_chain_engine.py
Frontend display name: Story Chain
```

## Implementation-Ready MVP Scope

Status: standalone MVP implemented locally.

Implemented:

- Standalone catalog card and quick-start room creation.
- One chain per room.
- Default starter prompt, `funny` tone, `last_sentence_only` visibility, 45 second turn window, and 180 character sentence limit.
- `full_context` and `last_sentence_only` backend support.
- Server-assigned turn order.
- Private active-player context over WebSocket.
- Public host/spectator/player sync that hides unrevealed sentences while writing.
- Player sentence submission, host skip/placeholder, host-paced reveal, podium, and light scoring.
- Backend engine, API, and websocket integration tests.

Not implemented yet:

- Dedicated setup screen for starter/tone/timer/visibility choices.
- AI starter prompt generation.
- Multiple chains.
- Voting awards.
- Automatic timeout task.
- Revelry/host-app exposure.

- Standalone LocalPlay first.
- Host quick-starts a default setup in the current MVP. A setup screen for starting prompt, tone, sentence timer, and visibility mode remains future work.
- Server assigns a turn order.
- Active player receives the story context they are allowed to see.
- Active player writes one sentence.
- Server appends the sentence and advances to the next player.
- Inactive players see waiting/progress state, not the hidden story if visibility mode says it is hidden.
- Spectator/TV shows progress while writing and then reveals the final story after the chain is complete.
- Optional voting can pick funniest, weirdest, most dramatic, or best twist when multiple chains are played in a future slice.

## Goals

- Create a low-friction creative game that works for mixed groups.
- Make the TV reveal delightful and central.
- Build reusable private-turn queue infrastructure for other sequential games.
- Support multiple visibility modes for different flavors of chaos.
- Keep content safe and party-friendly.
- Work without AI, while allowing AI to suggest starting prompts.

## Non-Goals

- No AI writing player sentences in MVP.
- No public publishing/gallery in MVP.
- No image or drawing chain in MVP.
- No live chat.
- No permanent profiles.
- No sensitive/personal prompts.
- No moderation beyond basic length/safety validation in MVP.

## Game Modes

### Full Context

Each player sees the entire story so far and adds one sentence.

Best for:

- Younger groups.
- Clearer, more coherent stories.
- First implementation.

### Last Sentence Only

Each player sees only the previous sentence and adds the next one.

Best for:

- More surprising twists.
- Telephone-like chaos.
- Stronger final reveal.

### Hidden Chain

Each player sees only the starter prompt and maybe a genre/tone, not previous sentences.

Best for:

- Maximum nonsense.
- Later phase, because it may produce less satisfying stories without guardrails.

MVP recommendation: ship `full_context` and `last_sentence_only`. Defer `hidden_chain`.

## Setup

```json
{
  "game_type": "story_chain",
  "game_title": "Story Chain",
  "starter_prompt": "A birthday cake started glowing at midnight.",
  "tone": "funny",
  "visibility_mode": "last_sentence_only",
  "chains": 1,
  "turn_time_seconds": 45,
  "sentence_max_chars": 180,
  "sentences_per_player": 1,
  "voting_enabled": false,
  "vote_category": "funniest"
}
```

Defaults:

- `tone`: `funny`.
- `visibility_mode`: `last_sentence_only`.
- `chains`: 1.
- `turn_time_seconds`: 45.
- `sentence_max_chars`: 180.
- `sentences_per_player`: 1.
- `voting_enabled`: false.
- `vote_category`: `funniest`.

Validation:

- Minimum players: 3.
- Recommended players: 4-20.
- `chains`: 1-5.
- `turn_time_seconds`: 20-120.
- `sentence_max_chars`: 60-280.
- `sentences_per_player`: 1-3.
- Starter prompt max: 180 chars.

## Prompt Safety Rules

Starter prompts should be imaginative but safe.

Good prompts:

```text
The office coffee machine started giving life advice.
A suitcase at the airport began singing.
The family dog discovered a secret tunnel.
At the wedding, the bouquet floated into the sky.
The birthday cake started glowing at midnight.
```

Avoid:

- Sexual, hateful, graphic, humiliating, or targeted prompts.
- Prompts that name private people unless the host writes them knowingly for their private group.
- Prompts about protected classes or sensitive personal facts.
- Prompts that ask players to disclose private information.

AI prompt generation must include:

```text
Generate whimsical, family-friendly story starters for a party game. Avoid sensitive personal data, protected-class targeting, and explicit or hateful content.
```

## Content Model

```ts
export interface StoryChainGame {
  game_title: string;
  starter_prompt: string;
  tone: 'funny' | 'spooky' | 'wholesome' | 'dramatic' | 'chaotic' | 'custom';
  visibility_mode: 'full_context' | 'last_sentence_only' | 'hidden_chain';
  chains: number;
  turn_time_seconds: number;
  sentence_max_chars: number;
  sentences_per_player: number;
  voting_enabled: boolean;
  vote_category?: 'funniest' | 'weirdest' | 'best_twist' | 'most_dramatic';
}

export interface StoryChainState {
  phase: 'STORY_WAITING' | 'STORY_TURN' | 'STORY_REVEAL' | 'STORY_VOTING' | 'PODIUM';
  chain_id: string;
  turn_order: string[];
  active_player_id?: string;
  current_turn_index: number;
  starter_prompt: string;
  sentences: StorySentence[];
  votes_by_player: Record<string, string>;
  deadline?: number;
}

export interface StorySentence {
  id: string;
  player_id: string;
  text: string;
  position: number;
  created_at: number;
}
```

## Runtime Flow

1. Host creates or selects a Story Chain setup.
2. Players join.
3. Host starts the game.
4. Server shuffles/assigns turn order.
5. Server starts chain 1 with the starter prompt.
6. Active player receives private turn payload.
7. Active player writes one sentence.
8. Server validates and appends the sentence.
9. Server advances to next player.
10. When all turns are complete, server enters reveal.
11. Spectator/TV reveals starter prompt and sentences one by one.
12. If voting is enabled and multiple chains exist, players vote.
13. Server shows result/podium.

## Private Turn Payload

The active player receives only what the visibility mode permits:

```json
{
  "type": "STORY_TURN_PRIVATE",
  "chain_id": "chain_1",
  "starter_prompt": "The office coffee machine started giving life advice.",
  "visible_context": [
    "It told Priya to stop replying-all."
  ],
  "sentence_max_chars": 180,
  "deadline": 1234567890
}
```

Visibility:

- `full_context`: starter prompt plus all previous sentences.
- `last_sentence_only`: starter prompt plus only the previous sentence.
- `hidden_chain`: starter prompt only.

Inactive players receive:

- active player name/avatar.
- turn number.
- total turns.
- timer.
- no hidden sentence text unless the visibility mode and product choice intentionally make the story public while writing.

## WebSocket Events

Client to server:

```json
{ "type": "STORY_SUBMIT_SENTENCE", "text": "Then it demanded a promotion." }
{ "type": "STORY_SKIP_TURN" }
{ "type": "STORY_NEXT_REVEAL_STEP" }
{ "type": "STORY_VOTE", "chain_id": "chain_2" }
```

Server to clients:

```json
{ "type": "STORY_SYNC", "state": {} }
{ "type": "STORY_TURN_STARTED", "active_player_id": "p2", "turn_index": 3 }
{ "type": "STORY_TURN_PRIVATE", "visible_context": [] }
{ "type": "STORY_SENTENCE_ACCEPTED", "player_id": "p2" }
{ "type": "STORY_REVEAL_STEP", "sentence": {} }
{ "type": "STORY_RESULT", "scores": [] }
```

## Submission Rules

- Active player only.
- One sentence per turn.
- Sentence must be non-empty.
- Sentence max is configurable.
- Strip leading/trailing whitespace.
- Collapse repeated whitespace.
- Reject or sanitize obvious markup/script content.
- If time expires:
  - MVP: auto-submit a safe placeholder such as "Then something unexpected happened."
  - Alternative: skip turn and mark as skipped.

Recommended MVP timeout: safe placeholder, because it keeps the reveal flowing.

## Scoring

Story Chain can be mostly non-scored in MVP, but LocalPlay usually expects a result.

MVP scoring:

- Every submitted sentence: 100 points.
- On-time submission: +25.
- If voting is enabled:
  - winning chain contributors: +200.
  - each vote received by a chain: +50 split among contributors.

Non-scored mode:

- Show a completion podium based on random/fun awards:
  - Best Twist
  - Chaos Agent
  - Plot Saver

Recommendation: MVP uses light scoring but emphasizes the story reveal over competition.

## Spectator/TV UX

During writing:

- Starter prompt.
- Turn progress.
- Active player.
- Timer.
- "Writing..." animation.
- No hidden sentence text unless mode is public.

Reveal:

- Show title/starter prompt.
- Reveal each sentence one at a time.
- Show contributor avatar/name after or before each sentence depending on mode.
- Use dramatic pacing and a progress rail.
- Final full story view.

Voting:

- Show vote category and chain cards.
- Reveal vote totals.
- Show final contributors.

## Player UX

Active player:

- Prompt/context panel.
- Sentence input.
- Character counter.
- Submit button.
- Timer.

Waiting player:

- Active writer.
- Turn order.
- Progress.
- Optional "your turn soon" alert.

Reveal player:

- Read along with TV.
- Vote if enabled.

## Organizer UX

Setup:

- Starter prompt input.
- Dice/AI starter suggestions.
- Tone selector.
- Visibility mode selector.
- Turn timer.
- Chains count.
- Voting toggle.

In-game:

- Start.
- Pause.
- Skip active turn.
- Extend timer.
- Start reveal.
- Next reveal step / auto-reveal toggle.
- End game.

## Backend Implementation

Add:

```text
backend/story_chain_engine.py
backend/tests/test_story_chain_engine.py
```

Pure helpers:

```py
def validate_story_chain_setup(raw: dict) -> dict: ...

def create_turn_order(player_ids: list[str], seed: str | None = None) -> list[str]: ...

def start_chain(setup: dict, player_ids: list[str], now: float, seed: str | None = None) -> dict: ...

def build_private_turn_payload(state: dict, player_id: str) -> dict: ...

def submit_sentence(state: dict, player_id: str, text: str, now: float) -> tuple[dict, dict]: ...

def timeout_turn(state: dict, now: float) -> tuple[dict, dict]: ...

def build_public_sync(state: dict) -> dict: ...

def build_reveal_payload(state: dict, reveal_index: int) -> dict: ...
```

## Reconnects and Disconnects

- Reconnected active player receives current private turn payload if their turn is still active.
- Reconnected waiting players receive public progress only.
- If active player disconnects, timer continues.
- Host can pause or skip.
- Timeout placeholder keeps game moving.
- If a player leaves before their turn and cannot return, their turn can be skipped or placeholder-filled.

## AI Generation

AI is optional and only for starter prompts.

Endpoint shape can mirror other generation endpoints:

```json
{
  "prompt": "birthday party, goofy, family friendly",
  "difficulty": "party",
  "num_items": 10,
  "mode": "story_chain_starters"
}
```

Output:

```json
{
  "starters": [
    "The birthday cake started glowing at midnight."
  ]
}
```

Host must review/select starter before starting.

## Revelry / Host-App Fit

Story Chain is a good Revelry game after standalone turn-queue infrastructure is reliable.

Host-app exposure requirements:

- Safe result summary only.
- Do not send full player-written story text back to Revelry callbacks by default.
- Include title, contributor count, chain count, and optional safe excerpt only if explicitly approved.

Safe result summary:

```json
{
  "game_type": "story_chain",
  "chains_completed": 1,
  "sentences": 8,
  "players": 8
}
```

## Testing Plan

Backend tests:

- Setup validation clamps timers/chars/chains.
- Turn order deterministic by seed.
- Private payload respects `full_context`.
- Private payload respects `last_sentence_only`.
- Public sync hides unrevealed sentences.
- Only active player can submit.
- Timeout adds placeholder or skips according to config.
- Reveal payload returns sentences in order.
- Reconnect payload for active player includes private context.

Frontend tests:

- Setup renders starter/tone/visibility controls.
- Active player sentence form shows context and timer.
- Waiting player does not see hidden story.
- Reveal screen steps through sentences.
- Spectator reveal handles long sentences.

Playwright:

- Mobile active-turn writing flow.
- Desktop spectator reveal pacing.
- Reconnect during active turn.
- Long story final view scrolls cleanly.

## Acceptance Criteria

- Host can start a Story Chain game with 3+ players.
- Server assigns a turn order.
- Each active player can submit exactly one sentence per turn.
- Visibility mode controls how much context the active player sees.
- Inactive players and spectator do not see hidden sentences before reveal.
- TV reveal shows the full chain in order.
- Reconnects preserve active turn/private context.
- Existing games remain unaffected.

## Future Work

- Multiple simultaneous chains for large groups.
- Drawing/image sentence variants.
- Anonymous contributor reveal.
- AI-generated title after story completion.
- Group voting awards.
- Export/share story with explicit host consent.
- Team Story Chain.
