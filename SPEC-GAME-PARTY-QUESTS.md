# LocalPlay Party Quests Game Spec

## Overview

Add **Party Quests** as an ambient, long-running social game that runs in the background during a party. Players receive lightweight social tasks, complete them while mingling, collect confirmation from other players, and later gather for a reveal of winners, funniest completions, and party stats.

Unlike round-based games, Party Quests is designed to be played over 30-180 minutes without requiring everyone to stare at their phones. The app creates prompts, tracks confirmations, prevents obvious duplicate farming, and produces a final podium.

```text
GameType: party_quests
Runtime family: ambient_social
Backend engine: party_quests_engine.py
Frontend display name: Party Quests
```

Example tasks:

```text
Talk to someone whose name starts with R.
Find someone born in July.
Find someone who plays a musical instrument.
Meet someone who shares one of your hobbies.
Find someone who has visited a city you want to visit.
```

## Current Implementation Status

Status: LocalPlay MVP implemented on June 18, 2026.

- Standalone LocalPlay host setup is implemented.
- Host can choose a curated pack: Mingling, Birthday, Wedding, Work-safe, or Family.
- Host can edit the quest text list before room creation.
- Host can choose duration, quests per player, confirmation mode, and late-join support.
- Revelry/host-app catalog support is implemented as quick-start/default-content capable (`host_app_supported=true`, `can_quick_start=true`).
- Embedded Revelry custom authoring is deferred; LocalPlay exposes a safe quick-start path first.
- AI quest generation is deferred; the backend config and safety rules are ready for it.
- Every player receives a personal quest board/list.
- Quests are completed by selecting another player and requesting confirmation.
- Confirmation modes:
  - `tap_confirm`: selected player receives a confirm/deny prompt.
  - `honor`: no confirmation, for very casual parties.
  - `pair_code`: schema-reserved only; not exposed in the MVP UI.
- Late join is allowed by default during `QUESTS_ACTIVE`; new players receive fresh quest boards with the remaining timer.
- Re-scans/rejoins should preserve a player when the same browser/device player token is present. Nickname alone is not enough to merge identity.
- Players can continue normal party activity while quests run.
- Spectator/TV can show ambient progress or stay quiet until reveal.
- Host ends the game manually or after a timer.
- Final reveal shows winner, runner up, top connectors, quest highlights, and aggregate stats.

## Goals

- Create a game people keep playing throughout a party.
- Encourage guests to talk to more people.
- Keep phone interaction brief and intermittent.
- Support safe, inclusive social discovery prompts.
- Provide a satisfying final reveal/podium.
- Reuse confirmation ideas from Find Someone Who while supporting longer-running scoring.

## Non-Goals

- No location tracking.
- No Bluetooth/proximity tracking in MVP.
- No face recognition.
- No demographic targeting based on protected classes.
- No sensitive personal data prompts.
- No public profile/directory.
- No real-money prizes or economy-linked rewards.
- No constant notification spam.

## Quest Safety Rules

Quests must be light, voluntary, and conversation-friendly.

Good quests:

```text
Talk to someone whose name starts with R.
Find someone born in the same month as you.
Find someone who likes the same snack as you.
Find someone who has watched the same show as you recently.
Meet someone who has lived in another city.
Find someone who shares one of your hobbies.
Talk to someone who knows a good restaurant nearby.
Find someone wearing the same color as you.
```

Avoid:

- Protected-class targeting: race, ethnicity, nationality, religion, caste, sexuality, gender identity, disability, age, family status.
- Sensitive areas: income, health, trauma, immigration, politics, criminal history, relationship status.
- Prompts that pressure disclosure.
- Humiliating, sexual, or unsafe tasks.
- Tasks requiring photos of people without consent.

Important nuance:

- "Name starts with R" and "born in July" are generally low-risk icebreaker prompts when optional and not used for discriminatory targeting.
- Age-related prompts should avoid exact age, "youngest/oldest," or age-band targeting.
- Birthday month is acceptable as a casual prompt; full birth date/year should be avoided.

AI generation instruction:

```text
Generate only light, voluntary, inclusive party mingling tasks. Avoid sensitive personal data, protected-class targeting, exact ages, full birth dates, politics, medical/legal/financial topics, and anything humiliating or sexual.
```

## Setup

```json
{
  "game_type": "party_quests",
  "game_title": "Party Quests",
  "quest_count": 20,
  "quests_per_player": 8,
  "duration_minutes": 90,
  "confirmation_mode": "tap_confirm",
  "allow_repeat_partner": false,
  "max_completions_per_partner": 2,
  "reveal_mode": "host_paced",
  "theme": "party"
}
```

Defaults:

- `quest_count`: 20.
- `quests_per_player`: 8.
- `duration_minutes`: 90.
- `confirmation_mode`: `tap_confirm`.
- `allow_repeat_partner`: false.
- `max_completions_per_partner`: 2.
- `reveal_mode`: `host_paced`.
- `theme`: `party`.
- `allow_late_join`: true.
- `auto_start_on_first_checkin`: schema-supported for future check-in/default-game host-app flows; false for normal standalone rooms until the host presses Start.

Validation:

- Technical minimum players: 1, so check-in/default-game host-app flows can start when the first guest joins.
- Recommended players: 4+; best at 8-100.
- Quest count: 5-120.
- Quests per player: 3-25.
- Duration: 10-240 minutes.
- Confirmation mode: `tap_confirm`, `pair_code`, or `honor`.
- Late join: boolean.

## Quest Model

```ts
export interface PartyQuest {
  id: string;
  display: string;
  category: 'name' | 'birthday_month' | 'hobby' | 'food' | 'travel' | 'shared_interest' | 'custom';
  points: number;
  requires_partner: boolean;
}

export interface PlayerQuest {
  quest_id: string;
  display: string;
  points: number;
  status: 'open' | 'pending_confirmation' | 'confirmed' | 'denied';
  confirmed_by_player_id?: string;
  confirmed_by_name?: string;
  completed_at?: number;
}

export interface PartyQuestGame {
  game_title: string;
  quests: PartyQuest[];
  quests_per_player: number;
  duration_minutes: number;
  confirmation_mode: 'tap_confirm' | 'pair_code' | 'honor';
  allow_repeat_partner: boolean;
  max_completions_per_partner: number;
  allow_late_join: boolean;
  auto_start_on_first_checkin?: boolean;
}
```

## Runtime Model

Room state:

```json
{
  "phase": "QUESTS_ACTIVE",
  "started_at": 1234567890,
  "ends_at": 1234573290,
  "quest_boards_by_player": {},
  "pending_confirmations": {},
  "completed_confirmations": [],
  "scores": {},
  "reveal_started": false
}
```

Phases:

- `QUESTS_LOBBY`
- `QUESTS_ACTIVE`
- `QUESTS_FINAL_CALL`
- `QUESTS_REVEAL`
- `PODIUM`

## Quest Assignment

At game start:

- Server freezes the active player roster for board generation.
- Server shuffles quests and assigns `quests_per_player` to each player.
- Players may receive overlapping quests; this is fine because they need to find their own matches.
- Avoid giving every player the exact same board unless host chooses "shared board" mode later.
- If quest count is smaller than needed, reuse quests but shuffle order.

Assignment should be deterministic by room seed for tests.

Late-join assignment:

- If `allow_late_join` is true and the game is active, a new player receives a board immediately.
- The new board is generated from the same quest pool and seed plus the player id so reconnects are stable.
- Late joiners can score normally, but final standings should show their join time if needed to explain shorter play time.
- If a player rejoins from the same device/session token, restore their existing board and pending confirmations instead of assigning a second board.
- If a different person tries to join with an already active nickname and no matching token, reject with "That name is already in use."

## Completion Flow: Tap Confirm

1. Player taps a quest.
2. Player selects the person they spoke with from the roster.
3. Server validates duplicate/partner limits.
4. Selected person receives a confirmation request:

```text
Avi says they completed:
"Talk to someone whose name starts with R"
with you. Confirm?
```

5. Selected person taps confirm/deny.
6. Confirm awards points and marks quest complete.
7. Deny returns quest to open or marks it denied with retry allowed.

Client to server:

```json
{ "type": "QUESTS_REQUEST_CONFIRMATION", "quest_id": "q1", "partner_player_id": "p2" }
{ "type": "QUESTS_CONFIRM", "request_id": "req1", "accepted": true }
```

Server to clients:

```json
{ "type": "QUESTS_SYNC", "game_type": "party_quests", "party_quests": {} }
```
```

## Completion Flow: Pair Code / QR

Pair-code mode reduces notification dependence and works well for crowded parties.

Flow:

1. Every player has a rotating short code and/or QR on their profile screen.
2. Requester talks to a person and asks for their code.
3. Requester enters/scans the code while completing the quest.
4. Server validates code owner and expiry.
5. Quest completes immediately.

Rules:

- Code expires every 60-180 seconds.
- Code must identify a live player.
- Cannot use own code if self-match is disabled.
- Pair-code completions still count toward partner duplicate limits.

## Scoring

Default:

- Standard quest: 100 points.
- Hard/specific quest: 150 points.
- First 3 completions bonus: +50 each.
- Unique partner bonus: +25 per distinct confirmed partner.
- Complete entire board: +300.

Anti-farming:

- By default, the same partner can confirm at most 2 completions for the same player.
- Host can loosen/tighten this.
- Denied confirmations do not score.
- Pending confirmations do not score until accepted.

Final rankings:

1. Total points.
2. Number of completed quests.
3. Number of unique confirmed partners.
4. Earliest final completion timestamp.

Awards:

- Winner.
- Runner up.
- Social Butterfly: most unique partners.
- Speed Starter: first to complete a quest.
- Completionist: completed all assigned quests.

## Spectator/TV UX

Ambient mode during party:

- Optional low-noise display.
- Timer.
- Total completions.
- Leaderboard top 5.
- Fun safe stats:
  - "23 conversations confirmed"
  - "Most completed quest: shared a hobby"
  - "12 unique partner pairs"

Final reveal:

- Countdown/final call.
- Winner podium.
- Runner up.
- Award cards.
- Quest highlights.
- Aggregate network map in future, but no detailed personal graph in MVP.

Avoid:

- Showing denied confirmations.
- Showing every person-to-person match.
- Showing sensitive custom quest text if host marked it private.

## Player UX

Player screen:

- Quest list/board.
- Progress count.
- Score.
- Tap quest to complete.
- Roster picker.
- Incoming confirmation requests.
- Pair code / QR profile if enabled.
- Final reveal view.

Low interruption:

- Incoming confirmations should be simple and quick.
- Avoid forcing the player back into the app constantly.
- Optional browser notifications can be future work; MVP can rely on in-app pending badge.

## Organizer UX

Setup:

- Choose template/theme.
- AI generate quests.
- Manual edit.
- Choose confirmation mode.
- Choose duration.
- Start room.

In-game:

- Timer.
- Total progress.
- End/reveal now.
- Extend duration.
- Final call mode.

No manual score editing in MVP.

## Backend Implementation

Implemented files:

```text
backend/party_quests_engine.py
backend/tests/test_party_quests_engine.py
```

Pure helpers:

```py
def validate_config(raw: dict) -> dict: ...

def assign_quests(player_ids: list[str], quests: list[dict], quests_per_player: int, seed: str | None = None) -> dict: ...

def create_initial_state(config: dict, players: list[dict], *, now: float | None = None, seed: str | None = None) -> dict: ...

def add_player(state: dict, player: dict, *, now: float | None = None) -> tuple[dict, dict]: ...

def create_confirmation_request(state: dict, player_id: str, quest_id: str, partner_player_id: str, now: float) -> tuple[dict, dict]: ...

def apply_confirmation(state: dict, request_id: str, confirmer_id: str, accepted: bool, now: float) -> tuple[dict, dict]: ...

def start_final_call(state: dict, *, now: float | None = None) -> tuple[dict, dict]: ...

def reveal(state: dict, *, now: float | None = None) -> tuple[dict, dict]: ...

def complete(state: dict, *, now: float | None = None) -> tuple[dict, dict]: ...

def calculate_scores(state: dict) -> dict: ...

def public_sync(state: dict) -> dict: ...

def private_sync(state: dict, player_id: str) -> dict: ...

def result_summary(state: dict) -> dict: ...
```

Implemented:

1. Pure engine with setup validation, deterministic assignment, tap-confirm requests, scoring, and public/private sync.
2. Room creation/catalog wiring for `game_type = "party_quests"` with default template content.
3. WebSocket runtime for `QUESTS_REQUEST_CONFIRMATION`, `QUESTS_CONFIRM`, final call, reveal, and game end.
4. Player UI: quest board, roster picker, incoming confirmation cards, score/progress.
5. Organizer/spectator UI: ambient progress, final call, reveal, and end controls.
6. Backend tests for config, confirmation, denial, late join, private/public sync, and reveal phases.

Deferred:

1. Multi-tab Playwright happy path with host + two players.
2. Revelry gamma policy enablement and embedded party-hub smoke once product approves exposure.
3. AI generation and prompt sanitizer UI.
4. Pair-code/QR mode if tap confirmation proves too interruptive.

MVP can ship with only `tap_confirm` and `honor` if pair-code QR scanning would delay the first playable version. Keep the setup schema compatible with `pair_code` so it can be enabled later without reshaping saved content.

## WebSocket Events

Client to server:

```json
{ "type": "QUESTS_REQUEST_CONFIRMATION", "quest_id": "q1", "partner_player_id": "p2" }
{ "type": "QUESTS_CONFIRM", "request_id": "req1", "accepted": true }
{ "type": "QUESTS_FINAL_CALL" }
{ "type": "QUESTS_REVEAL" }
{ "type": "END_QUIZ" }
```

Server to clients:

```json
{ "type": "QUESTS_SYNC", "game_type": "party_quests", "party_quests": {} }
{ "type": "PODIUM", "game_type": "party_quests", "party_quests": {} }
```

Visibility:

- Player sees their own quest board and incoming requests.
- Public/spectator sees aggregate progress and leaderboard.
- Other players do not see a player's full quest board by default.
- Confirmation request recipient sees only the specific quest being confirmed.

## AI Generation

Request:

```json
{
  "prompt": "wedding reception, mixed ages, family-friendly",
  "difficulty": "family",
  "num_items": 30,
  "mode": "party_quests"
}
```

Output:

```json
{
  "game_title": "Party Quests",
  "quests": [
    {"display": "Find someone who knows the couple from college.", "category": "shared_interest", "points": 100}
  ]
}
```

Host must review/edit generated quests before starting.

## Reconnects and Long-Running Behavior

- Reconnected players receive their quest board, score, pending outgoing confirmations, and incoming requests.
- If a player disconnects, they remain on the roster unless host removes them or room ends.
- Pending confirmations can expire after a configurable period, default 10 minutes.
- A player who joins late can receive a board if host allows late join; default allow during active phase.
- If host's organizer connection drops, game continues until timer end; another host control path is future work.

## Revelry / Host-App Fit

Party Quests is a strong Revelry fit because it can run for the whole event.

Check-in/default-game contract:

- Revelry or another host app may let the host pick Party Quests as the party's default check-in game.
- If `auto_start_on_first_checkin` is enabled, the first guest check-in should create/start the LocalPlay room automatically and show the join QR/link on the party surface.
- Later guests should join the same active room and receive a board immediately.
- LocalPlay should not create duplicate rooms for the same party/default game while one `QUESTS_ACTIVE` session exists.
- If the host manually ends and reveals the game, later joins should not restart it unless the host explicitly starts a new round/session.
- Safe callbacks/results should include aggregate stats and winners only, not a per-person social graph.

Expose only after:

- Standalone runtime is reliable for long sessions.
- Result summary is safe and aggregate.
- No per-person match graph is sent to host-app callbacks.
- Confirmation UX is tested on mobile webviews.

Safe result summary:

```json
{
  "game_type": "party_quests",
  "duration_minutes": 90,
  "completed_quests": 84,
  "unique_confirmed_pairs": 38,
  "top_players": [
    {"player_id": "p1", "place": 1, "score": 1200}
  ]
}
```

## Testing Plan

Backend tests:

- Setup validation clamps quest count, duration, and confirmation mode.
- Quest assignment is deterministic by seed.
- Player cannot confirm their own quest unless self-match is explicitly enabled.
- Duplicate partner limits are enforced.
- Only selected partner can accept/deny tap-confirm request.
- Pair codes expire and map to the correct player.
- Pending confirmations do not score.
- Confirmed completions score correctly.
- Public sync excludes full personal quest boards and denied confirmations.
- Final standings tie-breakers are deterministic.

Frontend tests:

- Quest board/list renders on mobile.
- Roster picker submits confirmation request.
- Incoming confirmation request accepts/denies.
- Pair-code entry works when enabled.
- Spectator aggregate view does not show private boards.
- Final reveal shows podium and awards.

Playwright:

- Mobile completion flow.
- Incoming confirmation flow on second player.
- Long quest labels wrap cleanly.
- Final reveal with 20+ players.
- June 23, 2026 local QA: focused engine tests still pass for config, confirmation, denial, late join, public/private sync, honor mode, and reveal/complete phases. Added frontend component tests for player confirmation requests, incoming confirm actions, and host Final Call / Reveal Scores / End Game controls. Added WebSocket regression coverage for start, request/confirm, active late join, final call, and reveal. Gamma multi-tab Revelry smoke remains the launch gate before broad production exposure.

## Acceptance Criteria

- Host can start Party Quests with 4+ players.
- Players receive quest boards.
- Players can complete quests through tap confirmation or pair code.
- Scores update only after confirmation.
- Partner duplicate limits prevent trivial farming.
- Game can run until host ends it or timer expires.
- Final reveal shows winners and aggregate party stats.
- Public/spectator sync avoids exposing private per-person match details.

## Future Work

- Push notifications for confirmation requests.
- QR scan flow instead of manual pair code.
- Team quests.
- Sponsored/event-branded quest packs.
- Host moderation for custom quests.
- Optional photo-proof quests with consent.
- Ambient TV animations during the party.
- Multi-host/cohost controls for long events.
