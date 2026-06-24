# LocalPlay Mafia Game Spec

Status: **implemented standalone MVP locally; Revelry quick-start eligible; gamma multi-device Playwright QA pending**

Last updated: June 24, 2026

The current implementation is a deterministic, in-memory standalone runtime that
works without AI narration or durable party/host-app authoring. It includes Night Reads so every living player has a private night
prompt, reducing the risk that special roles are exposed by phone behavior. AI
narration and richer setup UI remain follow-up polish once the standalone UX has
passed multi-device QA.

June 24, 2026 host-app update:

- LocalPlay now declares `mafia` as `host_app_supported = true` for Revelry.
- Revelry sees Mafia as quick-start/settings only: `can_quick_start = true`, `can_create_content = false`, and `supports_ai_generation = false`.
- The generic Revelry saved-content/AI authoring endpoints do not apply to Mafia.
- Multi-device gamma QA remains required before broad production rollout because private role prompts, Night Reads, and day voting need real-device validation.

June 23, 2026 polish update:

- Player Night UI now explicitly shows whether the private role action is submitted and whether the quiet Night Read is submitted.
- Role reveal reminds players to keep roles private and sets up the "everyone checks their phone at night" behavior.
- Frontend component tests cover Night action/Night Read task visibility and submission callbacks.
- Backend engine/socket tests continue to cover Night Reads, private role boundaries, Mafia target voting, day vote, and podium flow.

## Overview

Add a **social deduction game** to LocalPlay where players are secretly assigned roles — some are Mafia, the rest are Town. The game alternates between Night phases (Mafia secretly picks a target; special Town roles act privately) and Day phases (everyone discusses in person, then votes on a phone to eliminate a suspect). The game ends when all Mafia are eliminated or Mafia reaches parity with Town.

The phone replaces the physical moderator. Each player's screen shows only their own role and private information. The organizer/TV screen narrates public events ("Last night, someone was attacked...") without revealing who did what. Discussion happens out loud in the room — the app handles role assignment, night actions, vote counting, and narration.

```text
Engine family: mafia
First game type: mafia
Future rulesets: werewolf (themed reskin), spy_hunt (simplified, no night kills)
Backend engine: mafia_engine.py
Frontend display name: Mafia
```

## Goals

- Let a party host run Mafia without needing a dedicated human moderator.
- Assign secret roles to each player's phone.
- Run structured Night and Day phases with timed actions and votes.
- Validate night actions and vote tallies server-side so no one can cheat.
- Narrate public results on the organizer/TV screen without revealing private information.
- Support eliminated players as spectators who can still watch but cannot act or vote.
- Use template narration in v1, with an engine hook for later AI-generated flavor text.
- Keep the game playable at party scale: 6-15 players, 15-30 minute sessions.
- Support standalone LocalPlay first and Revelry quick-start after host-app policy/QA allows it.

## Constraints

- Minimum players: 6. Below this, Mafia is not fun — too few suspects, games end in 1-2 rounds.
- Maximum players: 15. Above this, Day discussion becomes unwieldy at a party. The room cap allows more, but the role distribution table stops at 15.
- Enforce the minimum when the host starts the game, not at room creation.
- One game per room. Mafia does not support mid-game join. Late arrivals become spectators.

## Non-Goals

- No text chat or in-app messaging. Discussion happens out loud in the room.
- No voice or video integration.
- No custom role creation in v1.
- No player-submitted accusations or evidence files.
- No real-time persistence beyond the current in-memory room model in v1.
- No Revelry/host-app launch until standalone is polished and result summaries are safe.

## Product Model

### Roles

Mafia v1 uses four role types:

| Role | Team | Night Action | Count |
|---|---|---|---|
| Villager | Town | None — sleeps at night | Fills remaining slots |
| Detective | Town | Investigates one player: learns if they are Mafia or Town | 1 |
| Doctor | Town | Protects one player from being killed that night | 1 |
| Mafia | Mafia | Votes with other Mafia members to kill one player | See distribution table |

Future roles (v2+): Jester (wins if voted out), Vigilante (Town member who can kill at night), Godfather (appears innocent to Detective), Lovers, Mayor (vote counts double).

### Role Distribution

| Players | Mafia | Detective | Doctor | Villagers |
|---|---|---|---|---|
| 6 | 1 | 1 | 1 | 3 |
| 7 | 2 | 1 | 1 | 3 |
| 8 | 2 | 1 | 1 | 4 |
| 9 | 2 | 1 | 1 | 5 |
| 10 | 3 | 1 | 1 | 5 |
| 11 | 3 | 1 | 1 | 6 |
| 12 | 3 | 1 | 1 | 7 |
| 13 | 4 | 1 | 1 | 7 |
| 14 | 4 | 1 | 1 | 8 |
| 15 | 4 | 1 | 1 | 9 |

The host can optionally disable Doctor or Detective in setup for a simpler game. When Doctor is disabled, one extra Villager fills the slot. Same for Detective.

### Game Phases

```text
LOBBY → ROLE_REVEAL → NIGHT → DAY_DISCUSSION → DAY_VOTE → VOTE_RESULT → [NIGHT...] → GAME_OVER
```

**LOBBY**: Players join. Host configures settings and starts.

**ROLE_REVEAL**: Each player's phone shows their secret role with a brief description. The organizer/TV screen shows a dramatic "Roles have been assigned..." message. This phase lasts a configurable duration (default 10 seconds) so players can read their role.

**NIGHT**: The app walks through night actions in a fixed order, but every living player receives a private night prompt so action roles are not socially exposed by being the only people interacting with their phones:
1. Mafia members see a list of living Town players and vote on a target. If multiple Mafia members exist, majority rules; ties are broken by the first vote. Mafia members can see each other's identity.
2. Detective chooses a living player to investigate. The result (Mafia or Town) is shown privately.
3. Doctor chooses a living player to protect. The Doctor may protect themselves (v1 allows self-protection; the host can disable it in setup).
4. Villagers, and optionally special roles after submitting their real action, answer a lightweight **Night Read** prompt such as "Who do you suspect is Mafia?", "Who feels definitely Town?", or "Who is playing the best game so far?"

Each night action has a configurable timer (default 30 seconds). If a player with a night action doesn't act before the timer expires, a random valid choice is made (Mafia target) or no action is taken (Detective skips, Doctor skips).

Players without night actions should never see a passive "wait for dawn" screen as their primary night UI. They receive a social-read prompt that requires the same kind of quiet phone interaction as action roles. This preserves the in-person stealth of Mafia: everyone checks their phone, everyone appears to be thinking, and no one can infer role ownership merely from who is tapping.

Night Reads are conversation fuel only. They do not affect kills, investigations, protection, votes, scoring, or win conditions.

**DAY_DISCUSSION**: The organizer/TV screen announces what happened overnight:
- "The town wakes up. [Player] was found dead!" (if Mafia kill succeeded and Doctor did not protect)
- "The town wakes up. Everyone survived the night!" (if Doctor saved the target or Mafia couldn't agree)
- The killed player's role is revealed.
- Optional anonymized Night Read aggregates are revealed before discussion, for example "Most suspected: Avi", "Most trusted: Ruchi", or "The town is split between Avi and Karan."

Players discuss in person. The app shows a countdown timer (default 90 seconds for discussion). The organizer can extend or shorten the timer.

**DAY_VOTE**: Each living player votes to eliminate one other living player, or votes to skip (no elimination). Votes are cast on phones. The vote is secret until all votes are in or the timer expires (default 30 seconds).

**VOTE_RESULT**: Votes are tallied and revealed. The player with the most votes is eliminated. Ties result in no elimination (v1 default). The eliminated player's role is revealed. The eliminated player becomes a spectator.

Then the game checks win conditions:
- If all Mafia are eliminated → Town wins.
- If Mafia count >= Town count → Mafia wins.
- Otherwise → next NIGHT phase.

**GAME_OVER**: All roles are revealed. The organizer/TV shows the winning team, all player roles, and a summary of key events.

### Win Conditions

- **Town wins**: All Mafia members are eliminated (voted out during Day or, in future versions, killed by Vigilante at Night).
- **Mafia wins**: The number of living Mafia members equals or exceeds the number of living Town members. At this point, Mafia can block any vote and cannot be outvoted.

### Eliminated Players

Eliminated players:
- See their own role and the public game state.
- Cannot vote, use night actions, or participate in Day votes.
- Can watch the game on their phone as spectators.
- Their role is publicly revealed when they are eliminated.
- They should not communicate game information to living players. The app cannot enforce this in-person, but a "Stay quiet — you're a ghost!" reminder is shown.

## Setup / Authoring

### Standalone Setup

The host configures:

- **Game title**: Optional, default "Mafia".
- **Theme**: Classic Mafia, Werewolf (cosmetic reskin — werewolves/villagers/seer/healer), or None. Affects narration copy and role names. Does not change mechanics.
- **Include Detective**: Toggle, default on.
- **Include Doctor**: Toggle, default on.
- **Doctor self-protection**: Toggle, default on. When off, the Doctor cannot choose themselves.
- **Night timer**: 15-60 seconds, default 30.
- **Discussion timer**: 30-180 seconds, default 90.
- **Vote timer**: 15-60 seconds, default 30.
- **Role reveal duration**: 5-20 seconds, default 10.
- **Tie vote behavior**: No elimination (default) or revote once then no elimination.

No AI generation is required for setup. Runtime narration uses safe templates in v1.

### Narration

After each night phase, the server creates a short narration paragraph describing the night's public result. This appears on the organizer/TV screen during the Day Discussion phase.

Example: "A chill swept through the town as darkness fell. When the sun rose, the townsfolk found Maya's door wide open and her chair empty. Maya, the village baker, was no more. The town mourns — and suspects."

Template narration requirements:
- Use player display names.
- Never reveal who did the killing or who investigated whom.
- Use the selected theme for tone (noir for Mafia, medieval horror for Werewolf).
- Keep it to 2-3 sentences.
- If a player died: `The town wakes up to grim news: [Player] was eliminated during the night. They were a [Role].`
- If the kill was saved: `The town wakes up shaken, but everyone survived the night. Someone was protected in the darkness.`
- If no target was available: `The town wakes up uneasy, but everyone survived the night. The night passed without a clear target.`

AI narration is a v2 cosmetic enhancement. Do not call an LLM from the v1 game loop.

### Night Reads

Night Reads are required v1 UX polish because app-moderated Mafia otherwise risks exposing special roles: Mafia, Detective, and Doctor would be the only people visibly doing something during Night. The goal is to make every living player appear equally engaged while generating useful, safe day-discussion prompts.

Night Read prompt pool:

```text
Who do you most suspect is Mafia right now?
Who feels definitely Town right now?
Who is playing the best social game so far?
Who changed their behavior this round?
Who should the town listen to during the next discussion?
```

Night Read rules:

- Every living player receives one prompt during Night.
- Villagers must answer a Night Read before their night turn is considered complete.
- Mafia, Detective, and Doctor may answer a Night Read after submitting their real action, or receive the read prompt alongside the real action if the UI can present both without confusion.
- Ghosts may optionally answer a ghost-only read prompt for fun, but ghost reads are excluded from public aggregates in v1.
- Answers are player selections from the living roster, not free text.
- The server stores reads by round, prompt id, respondent id, and selected player id.
- Individual Night Read answers are never shown publicly and are never sent to other players.
- Public reveal is aggregate-only and only when at least 3 living players submitted comparable reads.
- Aggregates must be soft and non-accusatory: "Most suspected" / "Most trusted" / "Best social game" rather than "Mafia is definitely..."
- Detective investigation results must never be blended into Night Read aggregates.
- Night Reads do not determine or modify the Mafia kill, Doctor save, Detective result, Day vote, score, or win condition.

Suggested v1 implementation:

```ts
type NightReadPrompt =
  | "suspect_mafia"
  | "trusted_town"
  | "best_social_game"
  | "changed_behavior"
  | "discussion_leader";

type NightReadAnswer = {
  round: number;
  prompt_id: NightReadPrompt;
  respondent_id: string;
  selected_player_id: string;
};
```

Public sync should include only aggregate cards:

```json
{
  "night_read_highlights": [
    {
      "prompt_id": "suspect_mafia",
      "label": "Most suspected",
      "player_id": "Avi",
      "count": 3
    }
  ]
}
```

## Implementation Decisions

These decisions close the v1 open questions:

- Doctor may protect the same player on consecutive nights.
- Doctor self-protection defaults on and is configurable.
- Mafia coordination is vote-based only; no in-app chat or quick reactions.
- Day discussion is in-person only; no typed accusations.
- No last-words phase in v1.
- Detective investigation results persist privately for that Detective across reconnects and later phases.
- Disconnected living players remain alive. Their timed actions become defaults on phase expiry: Mafia random target, Detective skip, Doctor skip, Day vote skip.
- Template narration is enabled by default. AI narration is disabled in v1.
- Werewolf is cosmetic only: role labels and narration copy may change, but state uses canonical role ids.

## Room State

```ts
type MafiaRoomState = {
  game_type: "mafia";
  engine_family: "mafia";
  phase: "LOBBY" | "MAFIA_ROLE_REVEAL" | "MAFIA_NIGHT" | "MAFIA_DAY_DISCUSSION" | "MAFIA_DAY_VOTE" | "MAFIA_VOTE_RESULT" | "PODIUM";
  round: number;
  theme: "classic" | "werewolf" | "none";
  settings: MafiaSettings;
  players: MafiaPlayer[];
  eliminated: MafiaPlayer[];
  night_log: NightResult[];
  vote_log: VoteResult[];
  winner: "town" | "mafia" | null;
};

type MafiaPlayer = {
  client_id: string;
  nickname: string;
  avatar: string;
  role: MafiaRole;
  alive: boolean;
  protected_tonight: boolean;
};

type MafiaRole = "villager" | "detective" | "doctor" | "mafia";

type NightResult = {
  round: number;
  mafia_target: string | null;
  doctor_target: string | null;
  detective_target: string | null;
  detective_result: "mafia" | "town" | null;
  killed: string | null;
  saved: boolean;
  narration: string;
};

type VoteResult = {
  round: number;
  votes: Record<string, string>;
  eliminated: string | null;
  eliminated_role: MafiaRole | null;
  tied: boolean;
};

type MafiaSettings = {
  include_detective: boolean;
  include_doctor: boolean;
  doctor_self_protect: boolean;
  night_timer_seconds: number;
  discussion_timer_seconds: number;
  vote_timer_seconds: number;
  role_reveal_seconds: number;
  tie_behavior: "no_elimination" | "revote_once";
};
```

### Canonical Phase Constants

Backend room state should use these exact string constants so frontend routing
can branch predictably:

```py
PHASE_ROLE_REVEAL = "MAFIA_ROLE_REVEAL"
PHASE_NIGHT = "MAFIA_NIGHT"
PHASE_DAY_DISCUSSION = "MAFIA_DAY_DISCUSSION"
PHASE_DAY_VOTE = "MAFIA_DAY_VOTE"
PHASE_VOTE_RESULT = "MAFIA_VOTE_RESULT"
PHASE_PODIUM = "PODIUM"
```

The engine may expose lowercase semantic phases internally only if every public
sync maps them to these constants. Prefer using the public constants throughout
to match existing game runtimes.

### Engine API

Create `backend/mafia_engine.py` with pure functions. Functions must not touch
WebSockets, room objects, global random state, databases, or LLM providers.

```py
def validate_config(raw: dict | None) -> dict
def role_distribution(player_count: int, include_detective: bool = True, include_doctor: bool = True) -> dict
def create_initial_state(player_ids: list[str], config: dict, seed: int | str | None = None, now: float | None = None) -> dict
def advance_after_role_reveal(state: dict, now: float | None = None) -> dict
def submit_night_action(state: dict, actor_id: str, target_id: str) -> dict
def resolve_night(state: dict, now: float | None = None) -> dict
def start_day_vote(state: dict, now: float | None = None) -> dict
def submit_vote(state: dict, voter_id: str, target_id: str) -> dict
def resolve_vote(state: dict, now: float | None = None) -> dict
def advance_after_vote_result(state: dict, now: float | None = None) -> dict
def force_complete(state: dict, winner: str | None = None, now: float | None = None) -> dict
def public_sync(state: dict, players: list[dict] | None = None) -> dict
def private_sync(state: dict, player_id: str, players: list[dict] | None = None) -> dict
def result_summary(state: dict, players: list[dict] | None = None) -> dict
```

Required engine behavior:

- `validate_config` clamps timers and validates enums:
  - `theme`: `classic | werewolf | none`, default `classic`
  - `night_timer_seconds`: 15-60, default 30
  - `discussion_timer_seconds`: 30-180, default 90
  - `vote_timer_seconds`: 15-60, default 30
  - `role_reveal_seconds`: 5-20, default 10
  - `tie_behavior`: v1 accepts `no_elimination`; `revote_once` may be accepted but treated as `no_elimination` until implemented.
- `create_initial_state` rejects fewer than 6 or more than 15 players with `ValueError`.
- Role assignment is deterministic for a supplied seed.
- `players` in state are keyed by stable player id/nickname strings used elsewhere in the room.
- Late join is not supported after the host starts; socket manager keeps the room locked.
- Public sync never includes living player roles, detective results, Mafia member list, doctor target, or unresolved vote choices.
- Private sync includes only the requesting player's role, action eligibility, submitted action/vote, investigation history if they are Detective, and Mafia teammate names if they are Mafia.

### Phase Advancement

| Current phase | Advance trigger | Engine function | Next phase |
|---|---|---|---|
| `MAFIA_ROLE_REVEAL` | Timer expires or organizer skips | `advance_after_role_reveal` | `MAFIA_NIGHT` |
| `MAFIA_NIGHT` | All required actions submitted, timer expires, or organizer skips | `resolve_night` | `MAFIA_DAY_DISCUSSION` or `PODIUM` |
| `MAFIA_DAY_DISCUSSION` | Timer expires or organizer skips | `start_day_vote` | `MAFIA_DAY_VOTE` |
| `MAFIA_DAY_VOTE` | All living votes submitted, timer expires, or organizer skips | `resolve_vote` | `MAFIA_VOTE_RESULT` or `PODIUM` |
| `MAFIA_VOTE_RESULT` | Organizer continues or short timer expires | `advance_after_vote_result` | `MAFIA_NIGHT` or `PODIUM` |

If implementation prefers a single generic helper, use:

```py
def advance_phase(state: dict, now: float | None = None, reason: str = "manual") -> dict
```

but keep the specific functions above for tests and readability.

Timer automation belongs in `backend/socket_manager.py`, not the engine. Socket
manager should create/cancel one Mafia timer task per room, following the same
cleanup pattern as existing room timers.

## WebSocket Events

### Organizer to Server

- `START_GAME` — Existing room start event. For `game_type = "mafia"`, server assigns roles and enters `MAFIA_ROLE_REVEAL`.
- `MAFIA_SKIP_TIMER` — Skip the current phase timer and advance immediately.
- `MAFIA_EXTEND_TIMER` — Add 30 seconds to the current discussion timer. Valid only during `MAFIA_DAY_DISCUSSION`.
- `END_QUIZ` — Existing force-end event. For `game_type = "mafia"`, reveal roles and complete the game.

### Player to Server

- `MAFIA_NIGHT_ACTION` — Submit a night action. Payload: `{ "target": "player_nickname" }`. The server infers the action type from the player's role.
- `MAFIA_VOTE` — Submit a Day vote. Payload: `{ "target": "player_nickname" }` or `{ "target": "skip" }`.

### Server to All (Broadcast)

- `MAFIA_SYNC` — Game state sync. Sent on phase transitions, reconnect, and accepted actions. For connected players this is personalized with private fields. For organizer and spectators this contains public state only.
- `MAFIA_ROLE_ASSIGNED` — Sent privately to each player with their role. Not broadcast.
- `MAFIA_NIGHT_START` — Night phase begins. Includes which actions the receiving player can take (if any).
- `MAFIA_NIGHT_ACTION_ACK` — Private confirmation that a night action was received.
- `MAFIA_DAY_START` — Day discussion begins. Includes night result narration and who was killed (if anyone).
- `MAFIA_VOTE_START` — Voting begins. Includes list of living players eligible for votes.
- `MAFIA_VOTE_RESULT` — Vote tally, who was eliminated (if anyone), their role reveal.
- `MAFIA_ELIMINATION` — A player has been eliminated. Includes their role.
- `MAFIA_GAME_OVER` — Game is over. Includes winner, all roles revealed, game summary.

### Required Socket Payload Shapes

`MAFIA_SYNC`:

```json
{
  "type": "MAFIA_SYNC",
  "game_type": "mafia",
  "mafia": {
    "phase": "MAFIA_NIGHT",
    "round": 1,
    "config": { "game_title": "Mafia", "theme": "classic" },
    "players": [
      { "nickname": "Avi", "avatar": "🕵️", "alive": true, "role": null },
      { "nickname": "Maya", "avatar": "🌙", "alive": false, "role": "villager", "eliminated_round": 1 }
    ],
    "alive_count": 5,
    "eliminated_count": 1,
    "deadline": 1780000000.0,
    "vote_progress": { "submitted": 0, "eligible": 5 },
    "last_night": null,
    "last_vote": null,
    "winner": null,
    "my_role": "detective",
    "my_action": { "kind": "investigate", "eligible_targets": ["Maya", "Sam"], "submitted_target": "" },
    "my_investigations": []
  },
  "player_count": 6,
  "players": [],
  "leaderboard": []
}
```

Public recipient rules:

- Organizer and spectator receive `role: null` for living players.
- Eliminated player roles are public after elimination.
- Game-over sync includes all roles.
- Organizer and spectator never receive `my_role`, `my_action`, `my_investigations`, or Mafia teammate fields.

Private player fields:

- `my_role`: canonical role id for that player.
- `my_action`: one of:
  - `{ "kind": "mafia_kill", "eligible_targets": [...], "submitted_target": "...", "mafia_teammates": [...] }`
  - `{ "kind": "investigate", "eligible_targets": [...], "submitted_target": "..." }`
  - `{ "kind": "protect", "eligible_targets": [...], "submitted_target": "..." }`
  - `{ "kind": "none", "eligible_targets": [] }`
- `my_vote`: submitted Day vote target or empty string.
- `my_investigations`: Detective-only list of `{ "round": 1, "target": "Sam", "result": "town" }`.
- `ghost`: true when the player is eliminated.

Action acknowledgements:

```json
{ "type": "MAFIA_NIGHT_ACTION_ACK", "target": "Sam" }
{ "type": "MAFIA_VOTE_ACK", "target": "skip" }
```

Errors:

```json
{ "type": "ERROR", "message": "Only living players can vote" }
```

Use existing `ERROR` handling; no Mafia-specific error modal type is required.

### Privacy Rules for Broadcasts

The server must never broadcast:
- Which player is Mafia, Detective, or Doctor (until they are eliminated or the game ends).
- Who the Mafia targeted at night (only the result: killed or saved).
- Who the Detective investigated (only the Detective sees their own result).
- Who the Doctor protected (only the Doctor knows).
- Individual vote choices before all votes are cast (votes are revealed together in VOTE_RESULT).

Each player receives a personalized `MAFIA_SYNC` that includes their own role and night action history, but not other players' roles.

## Surfaces

### Organizer / TV

The organizer screen acts as the game moderator and public display:

- **ROLE_REVEAL**: "Roles have been assigned. Check your phone." Dramatic theme art. Timer countdown.
- **NIGHT**: "Night has fallen. Close your eyes..." Ambient night visual. Timer for night actions. No private information shown.
- **DAY_DISCUSSION**: Template-narrated summary of the night. "The town wakes up. [Player] was found dead! They were a [Role]." Or "Everyone survived." Discussion timer. Player count (alive vs. eliminated).
- **DAY_VOTE**: "Time to vote. Who do you suspect?" Timer. Vote progress indicator (X of Y voted, no names).
- **VOTE_RESULT**: Vote tally visualization. Eliminated player and role reveal. Or "No one was eliminated — the vote was tied."
- **GAME_OVER**: Full role reveal grid. Winning team announcement. Key moments summary.

The organizer has moderator controls: skip timer, extend discussion, end game.

### Player

Each player's phone shows their private role and phase-appropriate actions:

- **ROLE_REVEAL**: "You are the Detective. Each night, you can investigate one player." Role-specific description and icon.
- **NIGHT (Mafia)**: List of living Town players. Tap to target. See other Mafia members' names. If multiple Mafia, see who they targeted. Timer.
- **NIGHT (Detective)**: List of living players (except self). Tap to investigate. Timer.
- **NIGHT (Doctor)**: List of living players (including self if allowed). Tap to protect. Timer.
- **NIGHT (Villager/no action)**: "Night has fallen. Wait for dawn." Ambient screen.
- **DAY_DISCUSSION**: Night result. Discussion timer. "Discuss with the group — who do you suspect?"
- **DAY_VOTE**: List of living players. Tap to vote. "Skip" option. Timer.
- **VOTE_RESULT**: Tally. Eliminated player reveal.
- **Eliminated**: "You have been eliminated. You were the [Role]. Watch quietly." Spectator view of public game state.
- **GAME_OVER**: Full role reveal. Win/lose indicator.

### Spectator / TV

The spectator screen shows the public narrative:
- Large text for narration and announcements.
- Player grid showing alive/eliminated status (no roles until elimination or game end).
- Night/day cycle visual.
- Vote progress and results.
- QR/join link behavior follows existing host-app/standalone share policy.
- Eliminated player roles shown as they are revealed.

## Persistence

v1 keeps game state in-memory like the current room model.

Durable objects for history:

- Game summary:
  - `game_type = "mafia"`
  - `player_count`
  - `winner` (town or mafia)
  - `rounds_played`
  - `theme`
  - `completed_at`
  - `duration_seconds`
- Safe result summary (for feed/recap):
  - Winner team
  - MVP or key moment (e.g., "The Doctor saved the Detective on Night 3!")
  - Player list with roles (revealed at game end)
  - Round count

Do not include:
- Per-round night action details in public summaries.
- Detective investigation results.
- Individual vote breakdowns beyond what was publicly revealed.
- Private narration prompts.

## Catalog Metadata

```json
{
  "id": "mafia",
  "game_type": "mafia",
  "engine_family": "mafia",
  "title": "Mafia",
  "description": "Secret roles, night kills, and daytime accusations. Find the Mafia before they outnumber you.",
  "status": "planned",
  "launchable": false,
  "min_players": 6,
  "max_players": 15,
  "estimated_minutes": 20,
  "supports_manual_authoring": false,
  "supports_ai_generation": false,
  "requires_content": false,
  "can_create_content": false,
  "can_quick_start": true,
  "supported_media": ["none"],
  "content_schema": "mafia_setup_v1",
  "result_summary_schema": "mafia_result_v1"
}
```

Keep `launchable = false` until:
- Standalone runtime is playable end-to-end.
- Night actions, voting, elimination, and win conditions all work.
- Template narration works without revealing private actions.
- Spectator/TV shows the public narrative.
- Eliminated players transition to spectator correctly.
- Safe result summaries are implemented.

## Results

Safe result summary:

```json
{
  "game_type": "mafia",
  "title": "Friday Night Mafia",
  "status": "complete",
  "theme": "classic",
  "winner": "town",
  "rounds_played": 5,
  "player_count": 10,
  "duration_seconds": 1200,
  "players": [
    { "nickname": "Avi", "role": "detective", "survived": true },
    { "nickname": "Maya", "role": "mafia", "survived": false, "eliminated_round": 3 },
    { "nickname": "Sam", "role": "doctor", "survived": true }
  ],
  "highlights": [
    "The Doctor saved the Detective on Night 2!",
    "Maya almost convinced everyone to vote out Avi, but the town held firm."
  ]
}
```

Do not include:
- Per-night action targets.
- Detective investigation details.
- Individual vote choices.
- AI narration prompts.
- Internal game logs.

## Key Architecture Considerations

### Eliminated Player Spectator Mode

This is the first LocalPlay game where players are eliminated mid-game but stay in the room. The room model needs:

- An `alive` flag per player (not just connected/disconnected).
- Eliminated players remain in `room.players` with `alive = false`.
- The WebSocket connection stays open for eliminated players. They receive public broadcasts but cannot send game actions.
- Player reconnect for an eliminated player restores spectator state, not active state.
- The player count display should show "7 alive / 10 total" not just "10 players."

### Private Messages

Mafia requires sending different information to different players within the same room. The existing `_send_to_client` method handles this. Key privacy boundaries:

- Role assignment: private to each player.
- Night actions: private to the acting player.
- Detective results: private to the Detective.
- Mafia member list: private to Mafia members only.
- Vote choices: private until the vote phase ends, then revealed to all.

The server must never include private information in broadcast messages. Each `MAFIA_SYNC` should be personalized per recipient.

### Night Phase Sequencing

Night actions resolve in a fixed order: Mafia → Detective → Doctor. This means:

- The Doctor's protection applies to the current night, not retroactively.
- If the Doctor protects the Mafia's target, the kill is prevented.
- The Detective's investigation result is accurate at the time of investigation (a player investigated as "Town" is Town even if they get killed that same night).

All night actions are collected before any are resolved. The server waits for all actions (or timer expiry) before resolving the night.

### Timer Management

Each phase has a configurable timer. When the timer expires:

- **Night actions**: Mafia random-targets a living Town player. Detective and Doctor skip (no action).
- **Discussion**: Automatically transitions to Day Vote.
- **Vote**: Uncast votes are counted as "skip." Tally proceeds with votes received.
- **Role reveal**: Automatically transitions to first Night.

The organizer can skip any timer (advance to next phase) or extend discussion time.

### Socket Manager Integration Points

Update `backend/socket_manager.py` in the same style as Bluff, Two Truths, Common
Ground, Who Am I, and Random Chit (`chit_pull`):

- Import Mafia engine functions at the top of the file.
- Add `room.mafia_config`, `room.mafia_state`, and `room.mafia_timer_task`.
- Reset Mafia state in `Room.reset_for_new_game`.
- Include Mafia in:
  - `Room.total_rounds`
  - `Room.current_round_data`
  - spectator initial `SPECTATOR_SYNC`
  - organizer reconnect sync
  - `START_GAME` min-player and launch branch
  - `NEXT_QUESTION` ignore list
  - `END_QUIZ`
  - `RESET_ROOM` allowed `game_type` and default content resolution
- Add helper methods:
  - `_start_mafia_game(room)`
  - `_broadcast_mafia_sync(room)`
  - `_send_mafia_private_sync(room, client_id)`
  - `_schedule_mafia_timer(room)`
  - `_cancel_mafia_timer(room)`
  - `_advance_mafia_phase(room, reason="manual")`
  - `_mafia_submit_night_action(room, client_id, target)`
  - `_mafia_submit_vote(room, client_id, target)`
  - `_mafia_complete_game(room, winner=None)`

Broadcast behavior:

- Use personalized syncs for player connections: send `private_sync` to each
  connected player client separately.
- Send `public_sync` to organizer and spectators.
- Do not use `room.broadcast` for raw Mafia state unless the payload is public.

Late join behavior:

- Once Mafia starts, `room.locked = True`.
- If a new player route reaches a locked Mafia room, preserve existing locked-room behavior and do not add them to `room.players`.
- Spectator routes remain allowed.

Timer behavior:

- On every Mafia phase transition, cancel the previous Mafia timer and schedule
  a new one if the phase has a deadline.
- If all required night actions or all living Day votes are submitted before
  deadline, advance immediately and cancel the timer.
- On disconnect, do not eliminate the player. Timer expiry applies defaults.
- On room close, reset, organizer disconnect cleanup, or game completion, cancel
  `room.mafia_timer_task`.

### Frontend Integration Points

Add lightweight standalone screens before polish:

- `frontend/src/components/MafiaGame.tsx`
  - Accepts `state`, `viewerName`, `controls`, and callbacks.
  - Renders organizer/spectator public state and player private actions from the same component.
  - Must not render living-player roles unless they are the current viewer's role.
- `frontend/src/types.ts`
  - Add `mafia` to `GameType`.
  - Add `MafiaState`, `MafiaRole`, and `MafiaPlayer` interfaces.
- `frontend/src/gameModes.ts`
  - Add Mafia with `runtimeType: "mafia"`, title `Mafia`, and description from catalog metadata.
- `frontend/src/pages/OrganizerPage.tsx`
  - Add `MAFIA` organizer state and render `MafiaGame controls="host"`.
  - Create quick-start room with `game_type = "mafia"` and default config.
  - Handle `MAFIA_SYNC`, `MAFIA_GAME_OVER`, and `PODIUM`.
- `frontend/src/pages/PlayerPage.tsx`
  - Store Mafia state from `MAFIA_SYNC`.
  - Send `MAFIA_NIGHT_ACTION` and `MAFIA_VOTE`.
  - Render `MafiaGame controls="player"`.
- `frontend/src/pages/SpectatorPage.tsx`
  - Store Mafia public state from `SPECTATOR_SYNC` or `MAFIA_SYNC`.
  - Render `MafiaGame controls="spectator"`.
- `frontend/src/components/organizer/GameSelectScreen.tsx`
  - Show Mafia as launchable only when backend catalog marks it launchable.

The first UI does not need custom animations, sound, AI narration, or advanced
theme art. It must be readable on phones and TV, show clear phase labels,
private actions, vote/action acknowledgements, and role reveal/game-over grids.

### Main API / Catalog Integration

Update `backend/main.py`:

- Import `validate_config as validate_mafia_config`.
- Add `mafia_config: dict = {}` to the room creation request model.
- Allow `game_type = "mafia"` in validators.
- Add catalog metadata exactly as listed in this spec.
- Default quick-start content:

```py
validate_mafia_config({"game_title": title or "Mafia"})
```

- For `POST /rooms`, when `game_type == "mafia"`, use `request.mafia_config`
  or validated defaults.

Keep `launchable = false` in host-app/Revelry catalogs until the acceptance
criteria pass. Standalone catalog launch can be enabled only after the runtime
and tests in this spec land.

## Implementation Plan

### Phase 1: Engine

- Add `backend/mafia_engine.py`.
- Add `backend/tests/test_mafia_engine.py`.
- Implement config validation, role distribution, seeded role assignment, night actions, night resolution, voting, win checks, public/private sync, and safe result summary.
- Keep all functions pure and deterministic when a seed is supplied.

Required engine tests:

- 6-15 player role distribution matches the table.
- Optional Detective/Doctor toggles backfill Villagers.
- Seeded assignment is stable.
- Mafia cannot target Mafia; Detective cannot target self; Doctor self-target respects config.
- Night kill succeeds when Doctor does not protect the target.
- Doctor save prevents the kill.
- Detective result is private and persists in private sync.
- Vote majority eliminates and reveals role.
- Vote tie causes no elimination.
- Uncast votes count as skip on timeout resolution.
- Town wins when all Mafia are eliminated.
- Mafia wins at parity.
- Public sync hides living roles and all private night details.
- Private sync includes only the viewer's own role/action info.
- Result summary excludes night targets, detective details, and individual vote choices.

### Phase 2: Socket Runtime

- Add Mafia state and timer handling to `backend/socket_manager.py`.
- Add Mafia config/catalog handling to `backend/main.py`.
- Add socket tests in `backend/tests/test_mafia_socket.py` or extend existing websocket tests.

Required socket tests:

- `START_GAME` rejects fewer than 6 players and accepts 6.
- `START_GAME` locks the room and sends each player a private role.
- Organizer and spectator sync do not expose living roles.
- Mafia player receives teammate list; non-Mafia players do not.
- Night actions can be submitted only by living eligible roles.
- All required night actions advance to Day Discussion.
- `MAFIA_SKIP_TIMER` advances current phase.
- `MAFIA_EXTEND_TIMER` only extends Day Discussion.
- Eliminated players remain connected, receive syncs, and cannot vote or act.
- Reconnect restores private role/alive state.
- `END_QUIZ` reveals all roles and records safe history.

### Phase 3: Frontend Standalone

- Add `MafiaGame` component and TypeScript types.
- Add Mafia to game mode config and standalone room creation.
- Wire organizer, player, and spectator pages to `MAFIA_SYNC`.
- Add focused component tests under `frontend/src/components/__tests__/MafiaGame.test.tsx`.

Required frontend tests:

- Player role reveal shows only the viewer's role.
- Organizer/spectator do not show living roles.
- Mafia night action shows only living Town targets and teammate names.
- Detective and Doctor action lists respect eligibility rules.
- Eliminated player sees ghost/spectator state and disabled actions.
- Vote screen includes living suspects and skip.
- Game-over screen reveals all roles.

### Phase 4: E2E and Launch Gate

- Add a Playwright smoke test that starts a 6-player Mafia room, performs a night kill, completes a Day vote, and reaches either next Night or Game Over.
- Run backend engine/socket tests and frontend tests.
- Enable standalone launch only after the above pass.

Do not enable Revelry/host-app launch in this phase.

### Phase 5: Polish and Host-App Follow-Up

- AI-generated narration with strict fallback and no private prompt leakage.
- Werewolf cosmetic labels and visual theme.
- Better TV layout, motion, sound, and accessibility pass.
- Party-scoped setup/save/start and safe callbacks.
- Revelry gamma matrix fixture before production exposure.

## Acceptance Criteria

Mafia v1 is launch-ready when:

- Roles are correctly distributed per the player count table.
- Each player sees only their own role on their phone.
- Mafia members can see each other and coordinate a night target.
- Detective receives a correct investigation result privately.
- Doctor can protect a player (including self if enabled).
- A successful Doctor save prevents the kill and is narrated.
- Day discussion has a visible, extendable timer.
- Day vote collects votes from all living players or times out.
- Vote ties result in no elimination (default behavior).
- Eliminated players transition to spectator mode and cannot act.
- Win conditions are checked after each elimination.
- Game Over reveals all roles.
- The organizer/TV screen never shows private role information for living players.
- Result summary includes winner, roles, and highlights without leaking night action details.
- Standalone UX works on desktop and mobile.
- Tests cover role assignment, night resolution, vote tallying, win conditions, privacy boundaries, and spectator transitions.

## Deferred Questions

These are explicitly out of scope for standalone v1 and should not block implementation:

- Should v2 add in-app Mafia quick reactions or typed remote discussion?
- Should v2 add a last-words phase before role reveal?
- Should AI narration be opt-in or default after the template runtime is stable?
- Should Werewolf eventually have unique visuals and sound in addition to cosmetic role labels?
