# LocalPlay Who Am I Game Spec

## Overview

Add **Who Am I?** as a clue-ladder guessing game. Each round has one hidden answer, the host/TV reveals clues one at a time, and players submit free-text guesses from their phones. Earlier correct guesses score more, so the game rewards both knowledge and nerve.

This is adjacent to quiz variants, but it should be a standalone runtime because it needs progressive clues, free-text guesses, clue timing, answer normalization, and optional clue-by-clue host pacing.

```text
GameType: who_am_i
Runtime family: clue_guessing
Backend engine: who_am_i_engine.py
Frontend display name: Who Am I?
Catalog category: Quiz/Trivia
AI marker: yes
```

## Implementation Status

Status: implemented MVP in standalone LocalPlay.

Implemented in this repo with:

- `backend/who_am_i_engine.py` clue ladder mechanics, guess normalization, scoring, and public/private sync helpers.
- `/who-am-i/generate`, `/who-am-i/import`, and `/who-am-i/{id}` update routes.
- Room creation support through `game_type="who_am_i"` and `who_am_i_id` / `who_am_i_config`.
- WebSocket runtime messages for clue advancement, answer reveal, round advancement, guesses, and sync.
- Organizer AI prompt, quick start, manual/review editing, and live host controls.
- Player free-text guess flow and spectator clue/answer display.
- Backend tests for matching, scoring, clue advancement, and podium flow.

Current exposure is standalone LocalPlay first. Revelry catalog exposure should follow the host-app allowlist/policy rollout after gamma smoke.

## MVP Scope

- Standalone LocalPlay first.
- Minimum 2 players, recommended 3-30.
- Host can AI-generate rounds from a theme.
- Host can manually create and edit rounds before room creation.
- Each round has:
  - one answer
  - optional answer aliases
  - 3-6 ordered clues
  - optional category/theme label
- Runtime reveals clues one by one.
- Players submit free-text guesses until they are correct or the round ends.
- Server normalizes guesses and matches against answer/aliases.
- Earlier clue guesses score more.
- Spectator/TV shows clue ladder, correct guessers, and final reveal.
- Host can advance clues manually; optional auto clue reveal is allowed but manual is the default.
- Final podium ranks players by score.

## Goals

- Add a highly understandable party trivia game with a different feel from multiple-choice quiz.
- Make AI generation useful and easy: "Bollywood stars", "animal kingdom", "birthday person's friends", "90s cartoons".
- Keep the runtime simple enough to reuse for future clue games.
- Let groups play around shared interests without requiring exact spelling.
- Avoid answer ambiguity through aliases and validation.

## Non-Goals

- No voice recognition in MVP.
- No AI judging guesses during live gameplay in MVP.
- No player-created clues during runtime in MVP.
- No hidden-role or impersonation mechanics in MVP.
- No Revelry exposure until standalone runtime, gamma smoke, and host-app catalog policy are tested.
- No sensitive personal data generation for real private people unless the host writes/edits the content knowingly.

## Game Modes

### Classic Clue Ladder

Default MVP mode.

1. Round answer is hidden.
2. Clue 1 is revealed.
3. Players guess.
4. Host reveals next clue or auto timer reveals it.
5. Round ends when host reveals answer, all active players have guessed correctly, or max clues are exhausted.

### Team Guess

Future mode. Teams submit one guess per clue.

### Who In This Room?

Future mode. Answers are party guest names. This must be host-authored or host-approved because AI should not invent personal facts about private people.

### Reverse Clues

Future mode. Players see an answer and write clues; other players guess.

## Setup

```json
{
  "game_type": "who_am_i",
  "game_title": "Who Am I?",
  "theme": "Bollywood actors",
  "round_count": 10,
  "clues_per_round": 5,
  "guess_time_seconds": 25,
  "clue_reveal_mode": "manual",
  "allow_multiple_guesses_per_clue": true,
  "max_guesses_per_player_per_clue": 3,
  "case_sensitive": false,
  "fuzzy_match_enabled": true,
  "points_by_clue": [500, 400, 300, 200, 100],
  "rounds": [
    {
      "id": "round_1",
      "answer": "Shah Rukh Khan",
      "aliases": ["SRK", "King Khan"],
      "category": "Actor",
      "clues": [
        "I was born in New Delhi.",
        "I became famous on Indian television before films.",
        "I am closely associated with romantic films.",
        "I co-own a cricket team.",
        "Fans often call me King Khan."
      ],
      "difficulty": "medium"
    }
  ]
}
```

Defaults:

- `game_title`: `Who Am I?`.
- `round_count`: 10.
- `clues_per_round`: 5.
- `guess_time_seconds`: 25.
- `clue_reveal_mode`: `manual`.
- `allow_multiple_guesses_per_clue`: true.
- `max_guesses_per_player_per_clue`: 3.
- `case_sensitive`: false.
- `fuzzy_match_enabled`: true.
- `points_by_clue`: `[500, 400, 300, 200, 100]`.

Validation:

- Minimum players: 2.
- Recommended players: 3-30.
- Rounds: 3-25.
- Clues per round: 3-6.
- Clue text: 8-180 chars.
- Answer text: 2-80 chars.
- Aliases: 0-8, each 1-80 chars.
- Guess time: 10-90 seconds.
- `points_by_clue.length` must be at least `clues_per_round`.
- Points must descend or stay flat; no later clue should be worth more than an earlier clue.

## AI Generation in MVP

AI generation is part of the MVP.

Host flow:

1. Host chooses **Who Am I?**.
2. Host enters a theme/topic.
3. Host chooses difficulty and round count.
4. Host taps **Generate Rounds**.
5. Backend charges sparks using existing generation flow.
6. AI returns structured clue rounds.
7. Backend validates, normalizes, and rejects ambiguous rounds.
8. Host reviews, edits, deletes, and adds rounds before creating the room.

### AI Request

```json
{
  "prompt": "Indian movie stars and cricket icons",
  "difficulty": "medium",
  "round_count": 10,
  "clues_per_round": 5,
  "provider": "gemini"
}
```

### AI Output

```json
{
  "game_title": "Indian Icons: Who Am I?",
  "rounds": [
    {
      "answer": "Sachin Tendulkar",
      "aliases": ["Sachin", "The Little Master"],
      "category": "Cricketer",
      "clues": [
        "I made my international debut as a teenager.",
        "I am associated with the number 10 jersey.",
        "I scored 100 international centuries.",
        "I played for India for more than two decades.",
        "I am often called the Little Master."
      ],
      "difficulty": "medium"
    }
  ]
}
```

### AI Prompt Contract

The generation prompt must include:

```text
Generate a party game called Who Am I. Each round has exactly one answer and an ordered ladder of clues from broad to specific. The answer must be guessable from the clues and not ambiguous. Include common aliases when useful. Avoid private personal data, protected-class targeting, explicit content, hateful content, medical/legal/financial advice, and clues that require sensitive personal information. Return strict JSON only.
```

Mode-specific rules:

- Clue 1 should be broad but fair.
- Last clue should make the answer reasonably obvious to the target audience.
- Do not make multiple rounds with the same answer.
- Do not use "I am a person/place/thing" as a clue unless it helps the theme.
- Do not include the answer text inside any clue.
- Avoid clues that could fit many equally plausible answers.
- For private-party themes like "our friends", require host-provided names/facts; AI may help format clues but must not invent facts.

## Guess Matching

MVP matching is deterministic and server-side.

Normalize both guesses and accepted answers:

- trim whitespace
- lowercase
- remove repeated spaces
- strip punctuation and emojis
- remove common leading articles: `a`, `an`, `the`
- normalize unicode accents where practical

Accepted when:

- normalized guess equals normalized answer or alias
- fuzzy match is enabled and edit distance is within a conservative threshold
- token initials match a configured alias, e.g. `srk` for `Shah Rukh Khan`, only when alias is present or generated safely

Do not accept:

- empty guesses
- guesses shorter than 2 chars, unless matching an explicit alias
- substring-only guesses for long answers unless the substring is an alias

Examples:

| Answer | Alias | Guess | Result |
|---|---|---|---|
| Shah Rukh Khan | SRK | `srk` | correct |
| Shah Rukh Khan | King Khan | `shahrukh khan` | correct |
| Sachin Tendulkar | Sachin | `sachin` | correct |
| The Beatles | Beatles | `beatles` | correct |
| Taylor Swift | none | `taylor` | wrong unless alias added |

## Content Model

```ts
export interface WhoAmIGame {
  game_title: string;
  theme?: string;
  round_count: number;
  clues_per_round: number;
  guess_time_seconds: number;
  clue_reveal_mode: 'manual' | 'auto';
  allow_multiple_guesses_per_clue: boolean;
  max_guesses_per_player_per_clue: number;
  fuzzy_match_enabled: boolean;
  points_by_clue: number[];
  rounds: WhoAmIRound[];
}

export interface WhoAmIRound {
  id: string;
  answer: string;
  aliases: string[];
  category?: string;
  clues: string[];
  difficulty?: 'easy' | 'medium' | 'hard';
}

export interface WhoAmIState {
  phase: 'WHOAMI_WAITING' | 'WHOAMI_ROUND' | 'WHOAMI_REVEAL' | 'PODIUM';
  current_round_index: number;
  current_clue_index: number;
  revealed_clues: string[];
  correct_by_player: Record<string, WhoAmICorrectGuess>;
  guesses_by_player: Record<string, WhoAmIGuess[]>;
  scores: Record<string, number>;
  deadline?: number;
  round_revealed: boolean;
}

export interface WhoAmIGuess {
  player_id: string;
  guess: string;
  clue_index: number;
  correct: boolean;
  created_at: number;
}

export interface WhoAmICorrectGuess {
  player_id: string;
  clue_index: number;
  points: number;
  guess: string;
  created_at: number;
}
```

Public state must never include the current round answer until reveal. Player private state may include the player's own guesses and whether they are already correct.

## Runtime Flow

1. Host creates or selects a Who Am I setup.
2. Players join.
3. Host starts the game.
4. Server enters `WHOAMI_ROUND`.
5. Server reveals clue 1.
6. Players submit guesses.
7. Server validates guesses and sends private result to each guesser.
8. Correct guessers are locked for the current round and score points based on clue index.
9. Host reveals next clue or auto timer reveals it.
10. Round ends when:
    - host taps reveal answer,
    - all active players guessed correctly,
    - or final clue timer expires.
11. Spectator/TV reveals answer, aliases, correct guessers, and clue-by-clue score.
12. Host advances to next round.
13. After all rounds, server enters `PODIUM`.

## WebSocket Events

Client to server:

```json
{ "type": "WHOAMI_SUBMIT_GUESS", "guess": "SRK" }
{ "type": "WHOAMI_NEXT_CLUE" }
{ "type": "WHOAMI_REVEAL_ANSWER" }
{ "type": "WHOAMI_NEXT_ROUND" }
{ "type": "WHOAMI_SET_AUTO_REVEAL", "enabled": true }
```

Server to clients:

```json
{
  "type": "WHOAMI_STATE",
  "state": {
    "phase": "WHOAMI_ROUND",
    "current_round_index": 0,
    "current_clue_index": 1,
    "revealed_clues": ["I was born in New Delhi.", "I became famous on Indian television before films."],
    "correct_count": 2,
    "scores": { "Avi": 500, "Ruchi": 400 }
  }
}
```

Private guess response:

```json
{
  "type": "WHOAMI_GUESS_RESULT",
  "correct": true,
  "points": 400,
  "message": "Correct! You got it after clue 2."
}
```

Reveal payload:

```json
{
  "type": "WHOAMI_ANSWER_REVEALED",
  "answer": "Shah Rukh Khan",
  "aliases": ["SRK", "King Khan"],
  "correct_guessers": [
    { "nickname": "Avi", "clue_index": 1, "points": 400 }
  ]
}
```

## Backend Implementation

Add `backend/who_am_i_engine.py` with pure helpers:

- `sanitize_who_am_i_game(raw: dict) -> dict`
- `validate_who_am_i_game(game: dict) -> tuple[bool, list[str]]`
- `normalize_guess(value: str) -> str`
- `is_correct_guess(guess: str, round: dict, fuzzy: bool = True) -> bool`
- `public_state(state: dict) -> dict`
- `private_player_state(state: dict, player_id: str) -> dict`
- `score_for_clue(points_by_clue: list[int], clue_index: int) -> int`

Backend integration:

- Add `who_am_i` to `GameType` validators.
- Add catalog metadata in `backend/main.py`.
- Add `/who-am-i/generate` or extend a generic generation route with `game_type="who_am_i"`.
- Store generated content using existing `generated_content` if schema allows generic content types; otherwise add gamma schema first and defer prod schema until promotion.
- Add room creation support.
- Add WebSocket branch in `socket_manager.py` for:
  - start
  - submit guess
  - next clue
  - reveal answer
  - next round
  - reconnect state
  - spectator state

State should stay in memory for MVP, matching current standalone room runtime style.

## Frontend Implementation

Catalog:

- Add `who_am_i` to `frontend/src/types.ts`.
- Add game card in `frontend/src/gameModes.ts`.
- Category: `Quiz/Trivia`.
- Icon: `❓` or `🪪`.
- Title: `Who Am I? ✨`.
- Subtitle: `Reveal clues while everyone races to guess the answer.`

Organizer screens:

- `WhoAmIPromptScreen.tsx`
  - theme textarea
  - difficulty
  - rounds: 5 / 10 / 15 / 20
  - clues per round: 3 / 4 / 5 / 6
  - provider selector when available
  - buttons: Generate Rounds, Create Your Own
- `WhoAmIReviewScreen.tsx`
  - list rounds
  - edit answer, aliases, category, clues
  - add/delete/reorder clues
  - validation badges
- Runtime in `OrganizerPage.tsx`
  - clue ladder
  - correct count
  - next clue / reveal answer / next round controls
  - current scoreboard

Player screen:

- Shows revealed clues.
- Guess input with submit button.
- Shows private result: incorrect, correct, already solved, out of guesses for this clue.
- Locks guess input after correct guess until next round.
- Shows current score and rank.

Spectator screen:

- Large title/category.
- Clues revealed one by one.
- Correct guessers appear without exposing the answer until reveal.
- Answer reveal moment.
- Between-round leaderboard.

## UX Copy

Game card:

```text
Who Am I? ✨
Reveal clues while everyone races to guess the answer.
```

Prompt placeholder:

```text
Bollywood stars, animal kingdom, 90s cartoons, world cities...
```

Generate button:

```text
Generate Rounds
```

Player guess placeholder:

```text
Type your guess
```

Incorrect message:

```text
Not quite. Try again after another clue.
```

Correct message:

```text
Correct! You got it after clue {n}.
```

## Edge Cases

- Player joins mid-game:
  - They can start guessing from the current clue.
  - They do not receive points for previous rounds.
- Player reconnects:
  - Restore private guesses, solved state, and score.
- All players solve early:
  - Server may auto-enter reveal state; host still controls next round.
- No one solves:
  - Reveal answer after final clue or host reveal.
- Duplicate answers:
  - Reject at setup validation.
- Ambiguous AI content:
  - Reject or flag during generation validation.
- Host refresh:
  - Organizer reconnect should restore clue index, round state, and controls.

## Safety

- AI-generated rounds must avoid sensitive private facts.
- User-provided themes are context only, not instructions.
- For "people in this room" themes, require manual authoring or host-provided source facts.
- Avoid protected-class targeting and mean-spirited clues.
- Avoid medical, legal, financial, sexual, hateful, or graphic content.
- Do not reveal hidden answer in public state or browser logs before round reveal.

## Tests

Backend unit tests:

- setup sanitization clamps counts and clue lengths.
- duplicate answers rejected.
- clue containing answer rejected.
- guess normalization handles case, punctuation, and articles.
- aliases match.
- fuzzy typo match works conservatively.
- scoring by clue index.
- public state hides answers before reveal.
- private state includes only own guesses.

WebSocket tests:

- host starts game and first clue appears.
- player incorrect guess receives private incorrect response.
- player correct guess scores once and locks further guesses.
- host next clue increments clue index.
- reveal includes answer.
- next round resets per-round guesses.
- reconnect restores player solved state.
- spectator never receives answer before reveal.

Frontend tests:

- catalog card appears under Quiz/Trivia and search.
- prompt screen disables generation with empty prompt.
- review screen edits aliases/clues.
- player guess submit sends websocket event.
- correct result locks input.
- organizer next clue/reveal buttons render correctly.
- spectator answer is hidden until reveal.

Playwright:

- local smoke: generate/manual setup -> room -> player guesses -> reveal -> podium.
- gamma smoke before promotion.
- mobile viewport: player guess input/button fits and no controls overlap.

## Rollout

1. Implement standalone local runtime.
2. Add backend/frontend tests.
3. Deploy to gamma.
4. Run gamma Playwright on desktop and mobile.
5. Do not expose in Revelry until catalog policy, session creation, callbacks, and host-app chrome are tested.
6. Production standalone exposure is safe after gamma smoke if no schema changes are required.
7. If schema changes are required, apply gamma first; production schema only after promotion approval.

## Future Enhancements

- Team mode.
- Host-uploaded answer list.
- Party guest/person mode with host approval.
- Clue packs by occasion.
- AI explanation after reveal.
- AI-assisted alias suggestions.
- Voice input for guesses.
- Spectator "hot/cold" animation based on number of correct guesses.
- Host setting for wrong-guess cooldown.
