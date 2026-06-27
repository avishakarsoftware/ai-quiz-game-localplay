# Generic Prompt Party Games Spec

Status: Implemented in LocalPlay standalone and covered by a live gamma regression suite. Gamma redeploy pending this change set.
Last updated: 2026-06-24

## Purpose

LocalPlay has several party games that share the same mechanics: show a prompt, collect quick player input, reveal the room result, score lightly, and move to the next round. Instead of building each as a bespoke runtime, this spec defines the shared Generic Prompt Party engine and the first ten games implemented on it.

The design goal is breadth without fragility: small, reliable, party-safe games that can be added to the catalog quickly while still supporting reconnects, spectators, rules, and future authoring.

## Implemented Games

- `hot_takes`: agree/disagree voting on party-safe takes.
- `this_or_that`: binary preference voting.
- `caption_contest`: short caption submissions, then voting.
- `pitch_battle`: short ridiculous-product pitches, then voting.
- `roast_toast`: playful compliment/very gentle roast lines, then voting.
- `desert_island`: short survival/preference answers, then voting.
- `memory_lane`: short memory/story answers, then voting.
- `rapid_fire`: instant short answers, grouped by normalized matches.
- `one_word_vibes`: one-word answers, grouped by normalized matches.
- `emoji_story`: tiny stories from emoji chains, then voting.

## Runtime Modes

The engine supports three modes.

`choice_vote`:

- Each round has one prompt and two to four visible options.
- Players choose one option on their phones.
- The host reveals the split.
- If there is a single majority option, players on that option score one point.
- Ties do not score.

`text_vote`:

- Each round has one prompt.
- Players submit short text.
- The host opens voting when submissions are ready.
- Players vote on visible submissions; self-voting is rejected.
- Voting payloads redact `player_id` and expose only submission text plus a stable room/round-salted `entry_id`; clients receive `is_mine`/`your_entry_id` so they can disable self-votes without revealing authors.
- Each vote scores one point for the submission author.

`text_group`:

- Each round has one prompt.
- Players submit short text.
- The host reveals normalized answer groups.
- Players in the largest matching group score one point when the largest group has at least two players.
- Single-player oddball answers are still shown but do not score.

## Room Lifecycle

1. Host selects a Generic Prompt Party game in standalone LocalPlay.
2. Backend creates a room with `game_type` equal to the concrete game id.
3. The room stores validated `generic_prompt_config`.
4. Host starts the game with at least two connected players.
5. Backend creates `generic_prompt_state` with rounds, player ids, scores, and the first phase.
6. Organizer, players, and spectators receive `GENERIC_PROMPT_SYNC`.
7. Host advances through reveal/vote/next actions.
8. Final round advances to `PODIUM` and emits normal LocalPlay podium/history payloads.

Late joins are supported while the game is active. New players are added to the score map and receive the current public/private state for their view. Late joins do not receive retroactive score opportunities for already revealed rounds.

## WebSocket Protocol

Server sync:

- `GENERIC_PROMPT_SYNC`
  - `game_type`
  - `generic_prompt`
  - `player_count`
  - `players`
  - `leaderboard`

Generic prompt payload:

- `phase`: `GENERIC_CHOICE`, `GENERIC_SUBMITTING`, `GENERIC_VOTING`, `GENERIC_REVEAL`, or `PODIUM`.
- `game_type`
- `game_title`
- `mode`
- `current_round_index`
- `round_count`
- `prompt`
- `submitted_count`
- `entries`
- `scores`
- `standings`
- `result`
- viewer-private fields: `your_choice`, `your_submission`, `your_vote`, `your_entry_id`.
- host-private fields before reveal: `private_choices`, `private_votes`.

Player actions:

- `GENERIC_CHOICE` with `choice`.
- `GENERIC_SUBMIT` with `text`.
- `GENERIC_VOTE` with `entry_id`.

Host actions:

- `GENERIC_START_VOTING` for `text_vote` games.
- `GENERIC_REVEAL` for all modes.
- `GENERIC_NEXT_ROUND` after reveal.
- `END_QUIZ` ends the generic prompt game and moves to podium.

## Catalog And Rules

Each game is listed in `backend/generic_prompt_engine.py` and surfaced through `GAME_CATALOG`.

Current catalog posture:

- `launchable=true`
- `default_content_available=true`
- `supports_custom_content=true` at engine level
- `supports_ai_generation=false`
- `host_app_supported=false`
- `supported_host_apps=[]`
- no schema changes required

Rules are declared in both:

- `backend/game_rules.py`
- `frontend/src/gameRules.ts`

## Frontend Surfaces

Shared UI:

- `frontend/src/components/GenericPromptGame.tsx`
- Host and spectator views show non-interactive choice previews before reveal instead of disabled player buttons.
- Player text submissions remain visible after submit so players can edit/update before the host advances.
- Text-vote host controls guide the sequence: collect submissions, start voting, then reveal.
- Reveal/result cards use a mobile-first one-column layout and only expand to two columns on wider screens.

State machine integration:

- `OrganizerPage.tsx`: host controls and create-room wiring.
- `PlayerPage.tsx`: choice, submit, vote, reconnect, podium.
- `SpectatorPage.tsx`: public prompt/reveal/standings view.
- `gameModes.ts`: catalog cards.
- `GameSelectScreen.tsx`: categories and non-AI labeling.

## Validation And Safety

- All prompt and player-submitted text is stripped of control characters and HTML tags.
- Submissions are capped at 160 characters.
- Prompts are capped at 180 characters.
- Choice options are deduplicated and capped at four options.
- Config round count is clamped to 3-25.
- Text grouping normalizes punctuation, case, accents, and whitespace for matching.
- Self-voting is rejected server-side.
- Public sync redacts text submissions until voting/reveal unless the viewer is the author or host.

## Tests

Implemented tests:

- `backend/tests/test_generic_prompt_engine.py`
  - choice majority scoring
  - text vote flow and author scoring
  - grouped answer scoring
  - public redaction
  - late join and podium
  - self-vote rejection
  - game metadata validation
- `backend/tests/test_generic_prompt_socket.py`
  - organizer/player websocket flow through submit, voting, reveal, and podium

Live gamma Playwright coverage:

- `frontend/e2e/generic-prompt-gamma-live.spec.ts`
  - creates a real gamma room for every implemented Generic Prompt Party game.
  - joins two live player browser contexts.
  - starts the room, plays one round through reveal, validates host/player UI, and checks horizontal overflow.
  - covers all three mechanics: `choice_vote`, `text_vote`, and `text_group`.

Build coverage:

- Frontend TypeScript/Vite build must pass.

## Future Work

- Add AI/custom authoring for host-created prompt packs.
- Add Revelry host-app support only after a host-app bridge and policy pass.
- Add richer prompt packs per occasion: birthday, wedding, office, school, family, spicy, work-safe.
- Add Playwright multi-tab coverage for at least one `choice_vote`, one `text_vote`, and one `text_group` game.
- Consider anonymous submissions/voting as a per-game setting for Caption Contest, Pitch Battle, and Roast & Toast.
