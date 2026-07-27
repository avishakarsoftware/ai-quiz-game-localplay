# SPEC-GAME-STATS — durable game results + the hosting stats screen

Status: **Built 2026-07-27, not yet deployed.** Works on SQLite immediately. On Supabase the
`game_results` table must be applied first (`sql/migrations/20260727T000000_game_results{,_gamma}.sql`);
until then `/stats` reports `available: false` and the UI hides itself, so shipping the code ahead
of the migration is safe and needs no feature flag. Live status: DEPLOY.md's env-status ledger.

## 1. Why

`game_history` in `main.py` is an in-memory list capped at `MAX_GAME_HISTORY`. It dies with the
process and isn't shared across instances, so:

- "games played / won / favourite mode" was impossible to show — the data didn't survive a deploy.
- Game-completion **achievement badges** were blocked on the same gap (SPEC-ACHIEVEMENTS v1 shipped
  economy-event badges only, explicitly deferring game badges for this reason).

This spec adds the missing durable record and builds both features on it.

## 2. What a "stat" actually counts — read this before changing the copy

`room.wallet_id` is the **host's** wallet. Guests join from their own phones by room code and never
authenticate, so a finished game can only ever be attributed to the host.

Every number here is therefore **games hosted**, not games played. The UI says "hosted" and
"Your parties" deliberately. Do not relabel these as "played" — it would be wrong for every guest
and it would overstate the number for the host.

If per-guest stats are ever wanted, that needs guest identity, which is a much larger change
(accounts for guests, or device-scoped join history) — not a relabel.

## 3. Data model

`game_results`, one row per completed game (template: `sql/templates/games-schema.template.sql`):

| column | notes |
|---|---|
| `room_code` | **PRIMARY KEY** — see idempotency below |
| `wallet_id` | the host's wallet; indexed with `completed_at DESC` |
| `game_type`, `game_title` | raw id + display title at time of play |
| `player_count` | includes disconnected players (from `get_game_summary`) |
| `winner_nickname`, `top_score` | leaderboard position 0 |
| `completed_at` | unix seconds |

**Idempotency is load-bearing.** Several engines can re-enter `PODIUM` for one room — a
re-broadcast, a host reconnect, a room reset path. `room_code` as the PK plus `INSERT OR IGNORE`
(SQLite) / `ignore_duplicates` (PostgREST) means a replayed podium is a no-op. Without it every
number on the screen silently inflates, and badges re-fire.

## 4. The write path — one choke-point

Before this change, 18 separate engine podium paths each inlined the same four lines:

```python
from main import game_history
summary = self.get_game_summary(room)
game_history.append(summary)
if len(game_history) > config.MAX_GAME_HISTORY:
    del game_history[:len(game_history) - config.MAX_GAME_HISTORY]
```

All 18 now call `main.record_game_completion(summary)`, which does the in-memory ring **and** the
durable write. Adding a game means calling one function; there is no second place to remember.

`record_game_completion` guarantees:

- **Never breaks a podium.** The DB write is wrapped — a failure (pre-migration Supabase, transient
  outage) logs and degrades to in-memory only. Stats are a side effect of finishing a game, never a
  precondition for it. Same posture as share snapshots.
- **Skips walletless rooms.** Revelry-hosted sessions have no wallet to attribute to; they're
  recorded in memory and skipped for the durable write rather than writing junk rows.
- **Awards badges only on a genuinely new row**, using `record_game_result`'s return value.

## 5. API

`GET /stats` (wallet-scoped, 401 without a wallet):

```jsonc
{
  "available": true,           // false => couldn't read; UI hides the section
  "games_hosted": 12,
  "players_entertained": 47,
  "distinct_games_played": 4,
  "favorite_game_type": "would_you_rather",
  "favorite_game_title": "Would You Rather",   // resolved via GAME_CATALOG
  "last_played_at": 1700000000,
  "by_game_type": [{ "game_type": "...", "game_title": "...", "count": 6 }],
  "recent": [{ "room_code": "...", "game_title": "...", "winner_nickname": "...", ... }]
}
```

`favorite_game_title` exists so the UI never renders a raw id like `would_you_rather`. Unknown /
retired game types fall back to the raw id rather than disappearing.

**`/stats` never 500s.** A read failure returns zeroed stats with `available: false`. That's what
lets the code ship before the migration.

## 6. Supabase parity

Aggregation runs in Python over the wallet's rows (`supabase_db.get_wallet_stats`) rather than a
GROUP BY RPC: PostgREST has no clean grouping and one host's lifetime games is a small set. Capped
at `STATS_ROW_CAP = 1000` rows so a pathological wallet can't pull an unbounded result. Tie-breaking
matches SQLite's `ORDER BY n DESC, game_type ASC` so both backends return the same favourite.

Table-only — no RPC, so the migration is a plain `CREATE TABLE` + index + RLS policy.

## 7. Achievements unblocked (SPEC-ACHIEVEMENTS v2)

Four badges now awardable, thresholds in `config.py`:

| badge | condition |
|---|---|
| `first_game` 🎉 | first hosted game |
| `ten_games` 🎪 | `ACHIEVEMENT_GAMES_HOSTED` (10) hosted |
| `big_party` 🥳 | a game with `ACHIEVEMENT_BIG_PARTY_PLAYERS` (8) or more players |
| `explorer` 🧭 | `ACHIEVEMENT_DISTINCT_GAMES` (5) different game types |

Awarded from `_award_game_badges`, gated on `_ACHIEVEMENTS_SUPPORTED`, best-effort throughout.

## 8. Frontend

`StatsSection` in the settings drawer. **No feature flag** — it hides itself when
`available: false` or `games_hosted === 0`, because a wall of zeros is worse than no section.

## 9. Tests

Backend 15 (`backend/tests/test_game_stats.py`): aggregation, idempotent replay, empty wallet,
favourite tie-break, recency ordering, limit clamping, walletless rejection, per-wallet scoping,
endpoint aggregates/auth/degradation, and that a DB failure can't break a podium.
Frontend 7 (`StatsSection.test.tsx`): renders, says "hosted" not "played", never leaks a raw
game_type, and all three hidden states.

**Testing gotcha:** conftest's autouse `fund_test_wallet` pins `tokens.get_wallet_id` to
`TEST_DEVICE_ID` for every request, so endpoint tests must seed *that* wallet — an `X-Device-Id`
header is ignored. And because `room_code` is the PK, tests reusing a fixed room code must clear
that code, not just the wallet, or a leftover row from an earlier run makes the insert a silent
no-op.

## 10. Not built

- Guest-side stats (needs guest identity — see §2).
- Streaks ("hosted N days in a row") — needs a date-bucketed query; the data now supports it.
- A full history screen; `recent` is returned but only the aggregate tiles are rendered.
