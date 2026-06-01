# LocalPlay Quiz Variant Games Spec

## Purpose

Add five polished party-friendly games that reuse LocalPlay's proven quiz runtime:

- **Rebus Rush**
- **Emoji Charades**
- **Fact or Fiction**
- **Timeline Twist**
- **Odd One Out**

These are distinct host-facing game modes, but the first implementation should deliberately share the existing quiz room lifecycle, player answer UI, spectator display, scoring, power-ups, spark charging, and review flow. This lets us ship more game variety without multiplying WebSocket state machines too early.

## Shared Implementation Model

Each game is a `quiz_variant`:

- Frontend shows a dedicated game card and tailored setup screen.
- Backend receives a `mode` on `/quiz/generate`.
- `quiz_engine.py` adds mode-specific system instructions.
- The generated content still has the existing `Quiz` shape:
  - `quiz_title`
  - `questions[]`
  - `text`
  - `options`
  - `answer_index`
  - optional `image_prompt`
- Room creation still uses `game_type="quiz"` and `quiz_id`.
- Player and spectator screens stay compatible.

This is Phase 0 for these games. If a variant later needs custom scoring or typed input, it can graduate into a full backend game type.

## Shared Requirements

- All modes must work from IONOS `/quiz/` and backend-served SPA.
- All modes must support local dev and gamma.
- Manual prompt text is treated only as topic/context, never instructions.
- Mode instructions must live in backend system prompts, not in the unsafe user prompt.
- Review/edit should work the same as regular quiz.
- Generated games should charge the same generation spark cost as quiz.
- Starting rooms should charge the same room spark cost as quiz.
- Existing import/export remains regular quiz JSON.

## Game 1: Rebus Rush

### Concept

Players decode emoji/symbol rebus clues into words, phrases, movies, songs, places, or concepts.

Example:

```text
🌊 + 🐴
Options: Seahorse, Water Polo, Beach Ride, Ocean Pony
```

### Generation Rules

- Question text should be the rebus clue first, with minimal explanatory text.
- Use emoji and simple symbols where possible.
- The correct answer should be a phrase or title that the rebus represents.
- Wrong answers should be plausible misreads.
- Avoid clues that require obscure private knowledge.
- Prefer 4-option multiple choice.
- True/false questions are allowed only if the model cannot make enough multiple-choice clues, but should be rare.

### UX

- Game card icon: `🧩`
- Host subtitle: "Decode emoji and symbol clues before the room catches on."
- Prompt placeholder: "Theme, category, or vibe: movies, travel, 90s hits..."
- Generate button: "Generate Rebus"

## Game 2: Emoji Charades

### Concept

Players guess the movie, song, celebrity, place, idiom, event, or phrase from an emoji-only clue.

Example:

```text
🧊🚢💔
Options: Titanic, Frozen, The Perfect Storm, Ice Age
```

### Generation Rules

- Question text should be mostly emoji.
- Include a short category label only when it helps fairness, e.g. "Movie: 🧊🚢💔".
- Correct answer should be recognizable to a broad audience unless the host topic narrows it.
- Wrong answers should share theme/genre/era.
- Prefer 4-option multiple choice.

### UX

- Game card icon: `🎭`
- Host subtitle: "Guess movies, songs, sayings, and places from emoji clues."
- Prompt placeholder: "Movies, pop songs, vacation spots, office inside jokes..."
- Generate button: "Generate Emoji Rounds"

## Game 3: Fact or Fiction

### Concept

Fast true/false rounds where players decide whether surprising statements are real or made up.

Example:

```text
Bananas are berries, but strawberries are not.
Options: True, False
```

### Generation Rules

- Every question must use exactly `["True", "False"]`.
- Keep statements crisp and verifiable.
- Mix true and false answers.
- Avoid ambiguous wording.
- Avoid harmful medical/legal/financial claims unless they are basic, non-actionable trivia.
- Explanations are not currently rendered but can be included in metadata later.

### UX

- Game card icon: `🕵️`
- Host subtitle: "Spot which surprising claims are real."
- Prompt placeholder: "Science myths, history, sports records, office lore..."
- Generate button: "Generate Questions"

## Game 4: Timeline Twist

### Concept

Players answer chronology questions: what came first, what happened last, which year matches, or which item is out of order.

Example:

```text
Which happened first?
Options: First iPhone announced, YouTube launched, Instagram launched, TikTok launched
```

### Generation Rules

- Question text should clearly ask about order/time.
- Use historical, pop culture, tech, sports, or topic-specific chronology.
- Wrong answers should be plausible and near enough to be interesting.
- Avoid exact-year questions unless the year is famous or all options are years.
- Prefer 4-option multiple choice.

### UX

- Game card icon: `⏳`
- Host subtitle: "Put events, releases, and moments in the right order."
- Prompt placeholder: "Tech milestones, movie releases, family history..."
- Generate button: "Generate Timeline"

## Game 5: Odd One Out

### Concept

Players identify which option does not belong with the others.

Example:

```text
Which one is the odd one out?
Options: Mercury, Venus, Mars, Pluto
Correct: Pluto
```

### Generation Rules

- The grouping rule must be fair and inferable.
- Three options should clearly share a category/property.
- One option should break that rule.
- Question text can include the rule when needed for fairness, but better rounds let players infer it.
- Wrong answers should not be trivially unrelated.
- Prefer 4-option multiple choice.

### UX

- Game card icon: `🔍`
- Host subtitle: "Find the item that breaks the pattern."
- Prompt placeholder: "Animals, food, superheroes, world capitals..."
- Generate button: "Generate Patterns"

## Backend Design

Add a safe mode enum:

```py
VALID_QUIZ_MODES = (
    "classic",
    "rebus",
    "emoji_charades",
    "fact_fiction",
    "timeline",
    "odd_one_out",
)
```

`QuizRequest` accepts:

```json
{
  "prompt": "90s movies",
  "difficulty": "medium",
  "num_questions": 10,
  "provider": "gemini",
  "mode": "emoji_charades"
}
```

`quiz_engine.generate_quiz(...)` accepts `mode` and passes it to provider functions.

System prompt construction:

- Keep the existing injection boundary for user topic.
- Add mode instructions inside the trusted system prompt.
- For `fact_fiction`, require true/false options.
- For other modes, prefer 4-option multiple choice.

Validation:

- Existing quiz validation remains the baseline.
- Add optional mode-aware validation:
  - `fact_fiction`: all options are exactly `True`, `False`.
  - others: at least most questions have 4 options.
- After provider output is validated and sanitized, backend shuffles each 4-option multiple-choice question and rewrites `answer_index` to the new correct option position. This is required because LLMs frequently put the correct answer first, especially for Rebus Rush and Emoji Charades. Two-option questions are not shuffled; `fact_fiction` keeps `["True", "False"]` order for clarity.

Mode-aware validation can be warning-only in V1 so generation does not fail too aggressively.

## Frontend Design

Add quiz variant metadata:

```ts
export type QuizVariantGameType =
  | 'rebus'
  | 'emoji_charades'
  | 'fact_fiction'
  | 'timeline'
  | 'odd_one_out';
```

`GameSelectScreen` shows all five cards.

Organizer flow:

1. Selecting a variant opens `QuizVariantPromptScreen`.
2. `QuizVariantPromptScreen` uses variant-specific title, icon, description, placeholder, and button copy.
3. Quiz variants reuse the same curated topic library as AI Quiz. Opening a quiz or quiz-variant prompt prepopulates the textarea with one random topic, and the dice button replaces it with another topic.
4. Generate calls `/quiz/generate` with `mode`.
5. Review screen is the existing `ReviewScreen`.
6. Room create maps every quiz variant to backend `game_type="quiz"`.

Player/spectator:

- No required changes in V1.
- The generated question text carries the game-specific clue.

## Testing Plan

Backend tests:

- `/quiz/generate` accepts each valid mode.
- Invalid mode is rejected.
- Fact or Fiction prompt construction includes true/false constraints.
- Classic mode remains default when omitted.

Frontend tests:

- Game select renders all five variant cards.
- Selecting a variant opens the tailored prompt screen.
- Generate sends the correct `mode`.
- Room creation maps quiz variants to backend `game_type="quiz"`.

Playwright:

- Rebus Rush prompt screen desktop/mobile layout:
  - no horizontal overflow
  - fixed menu/sparks controls do not overlap Back
  - controls remain aligned
- Fact or Fiction generate smoke with stubbed backend verifies request body includes `mode="fact_fiction"`.

## Acceptance Criteria

- Five new game cards are visible and selectable.
- Each game has a differentiated host setup screen.
- Each game calls `/quiz/generate` with a safe backend mode.
- Generated content lands in the existing review screen.
- Starting a room works because variants map to the quiz runtime.
- Existing quiz, WMLT, and DrawingGame flows still work.
- Backend and frontend tests pass.
- Playwright covers at least one variant prompt screen.

## Future Work

- Persist selected variant metadata into game history.
- Show variant-specific labels in lobby/podium.
- Add variant-specific review affordances.
- Add typed-answer Rebus/Emoji modes.
- Add closest-year Timeline scoring.
- Add explanations after each Fact or Fiction answer.
- Add image-enhanced Odd One Out once media uploads are persistent.
