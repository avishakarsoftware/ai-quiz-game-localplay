# LocalPlay Mafia Game Spec

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
- Use AI to generate flavored narration for night events, role reveals, and game-end summaries.
- Keep the game playable at party scale: 6-15 players, 15-30 minute sessions.
- Support standalone LocalPlay first; expose to Revelry after standalone UX is polished.

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

**NIGHT**: The app walks through night actions in a fixed order:
1. Mafia members see a list of living Town players and vote on a target. If multiple Mafia members exist, majority rules; ties are broken by the first vote. Mafia members can see each other's identity.
2. Detective chooses a living player to investigate. The result (Mafia or Town) is shown privately.
3. Doctor chooses a living player to protect. The Doctor may protect themselves (v1 allows self-protection; the host can disable it in setup).

Each night action has a configurable timer (default 30 seconds). If a player with a night action doesn't act before the timer expires, a random valid choice is made (Mafia target) or no action is taken (Detective skips, Doctor skips).

Players without night actions see a "Night has fallen — wait for dawn" screen.

**DAY_DISCUSSION**: The organizer/TV screen announces what happened overnight:
- "The town wakes up. [Player] was found dead!" (if Mafia kill succeeded and Doctor did not protect)
- "The town wakes up. Everyone survived the night!" (if Doctor saved the target or Mafia couldn't agree)
- The killed player's role is revealed.

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

No AI generation is required for setup. AI is used only for runtime narration flavor text.

### AI Narration

After each night phase, the server generates a short narration paragraph describing the night's events in a dramatic, story-like tone. This appears on the organizer/TV screen during the Day Discussion phase.

Example: "A chill swept through the town as darkness fell. When the sun rose, the townsfolk found Maya's door wide open and her chair empty. Maya, the village baker, was no more. The town mourns — and suspects."

Narration requirements:
- Use player display names.
- Never reveal who did the killing or who investigated whom.
- Use the selected theme for tone (noir for Mafia, medieval horror for Werewolf).
- Keep it to 2-3 sentences.
- Fall back to a template if AI generation fails or is disabled: "[Player] was eliminated during the night. Their role was [Role]."

Narration is generated server-side using the existing LLM provider infrastructure. It is a cosmetic enhancement; gameplay works without it.

## Room State

```ts
type MafiaRoomState = {
  game_type: "mafia";
  engine_family: "mafia";
  phase: "lobby" | "role_reveal" | "night" | "day_discussion" | "day_vote" | "vote_result" | "game_over";
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

## WebSocket Events

### Organizer to Server

- `MAFIA_START` — Start the game. Server assigns roles, enters ROLE_REVEAL.
- `MAFIA_SKIP_TIMER` — Skip the current phase timer (move to next phase immediately).
- `MAFIA_EXTEND_TIMER` — Add 30 seconds to the current discussion timer.
- `MAFIA_END_GAME` — Force-end the game early.

### Player to Server

- `MAFIA_NIGHT_ACTION` — Submit a night action: `{ target: "player_nickname" }`. The server infers the action type from the player's role.
- `MAFIA_VOTE` — Submit a Day vote: `{ target: "player_nickname" }` or `{ target: "skip" }`.

### Server to All (Broadcast)

- `MAFIA_SYNC` — Full game state sync. Sent on phase transitions and reconnect. Contains public state only; private information (roles of living players, night action details) is stripped.
- `MAFIA_ROLE_ASSIGNED` — Sent privately to each player with their role. Not broadcast.
- `MAFIA_NIGHT_START` — Night phase begins. Includes which actions the receiving player can take (if any).
- `MAFIA_NIGHT_ACTION_ACK` — Private confirmation that a night action was received.
- `MAFIA_DAY_START` — Day discussion begins. Includes night result narration and who was killed (if anyone).
- `MAFIA_VOTE_START` — Voting begins. Includes list of living players eligible for votes.
- `MAFIA_VOTE_RESULT` — Vote tally, who was eliminated (if anyone), their role reveal.
- `MAFIA_ELIMINATION` — A player has been eliminated. Includes their role.
- `MAFIA_GAME_OVER` — Game is over. Includes winner, all roles revealed, game summary.

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
- **DAY_DISCUSSION**: AI-narrated summary of the night. "The town wakes up. [Player] was found dead! They were a [Role]." Or "Everyone survived." Discussion timer. Player count (alive vs. eliminated).
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
- AI narration generates or gracefully falls back.
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

## Implementation Plan

### Phase 0: Spec and Engine

- Add this spec.
- Add `mafia` to planned catalog metadata as `launchable: false`.
- Write pure engine functions and tests for role assignment, night resolution, vote tallying, and win condition checks.

### Phase 1: Standalone Runtime

- Add backend engine: role distribution, night resolution, vote counting, win conditions.
- Add runtime state to socket manager with MAFIA_* states.
- Add organizer moderator screen.
- Add player role/action screens for each phase.
- Add spectator narration screen.
- Add eliminated-player spectator transition.
- Add game history summary.

### Phase 2: Polish

- AI-generated night narration.
- Theme support (Werewolf cosmetic reskin).
- Animations for night/day transitions, eliminations, role reveals.
- Sound effects for dramatic moments.
- Better TV/spectator display with player grid visualization.
- Reconnect restores role, alive status, and current phase.
- Accessibility pass.

### Phase 3: Host-App / Revelry Enablement

- Add host-app catalog metadata.
- Add party-scoped setup/save/start path.
- Add safe result callbacks.
- Add e2e tests.
- Gamma test through Revelry before enabling production.

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

## Open Questions

- Should the Doctor be allowed to protect the same player two nights in a row?
- Should Mafia members be able to communicate during the night phase (in-app quick reactions), or should night coordination be silent and vote-based?
- Should there be an anonymous day discussion option (typed messages) for remote/hybrid parties, or is voice-only sufficient for v1?
- Should the game support a "last words" phase where an eliminated player can speak before being revealed?
- Should the Detective's investigation results persist on their screen across rounds, or only show the latest?
- How should the game handle a player disconnecting mid-game? Options: treat as skip (Villager), treat as eliminated, or pause until reconnect.
- Should AI narration be enabled by default or opt-in, given it adds LLM latency between phases?
- Should the Werewolf theme use different role names only, or also change the night/day narration style and visual theme?
