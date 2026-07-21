# SPEC-ACHIEVEMENTS — Achievements / badges

Status: **Implemented (v1: economy events), feature-gated for Supabase rollout** (2026-07-21)
Owner: Avi
Related: `SPEC-REFERRAL.md`, `SPEC-GIFTING.md` (award trigger sites), `SPEC-ANALYTICS.md`

---

## 0. Goal

Reward players with badges on milestones. Read-mostly, **no economy risk** (badges never mint sparks).
v1 awards from clean economy choke-points only — no game-completion hooks, because game completions are
persisted to an in-memory list (`main.game_history`), not per-wallet in the DB, so game-based badges are a
deliberate follow-up (they'd need a durable completion write across ~6 socket_manager sites first).

## 1. Badge catalog (v1)

Backend-authoritative in `config.ACHIEVEMENT_CATALOG` (id/emoji/name/description); `ACHIEVEMENT_IDS` is the
validation set. The `/achievements` endpoint returns the whole catalog with per-wallet `earned` flags, so the
frontend renders what it's told — no client-side badge list to keep in sync.

| id | emoji | trigger |
|---|---|---|
| `welcome` | 👋 | Awarded lazily on first `/achievements` view (list is never empty for a real wallet) |
| `first_referral` | 🔗 | Both parties on a successful `/referral/redeem` |
| `first_gift` | 🎁 | Sender on a successful (non-duplicate) `/tokens/gift` |

## 2. Data model

`achievements(wallet_id TEXT, badge_id TEXT, awarded_at BIGINT, PRIMARY KEY (wallet_id, badge_id))` +
`idx_achievements_wallet`. The composite PK makes awarding idempotent (SQLite `INSERT OR IGNORE`, Postgres
`ON CONFLICT DO NOTHING`). No new wallet columns.

## 3. Backend

- `db.award_achievement(wallet_id, badge_id) -> bool` — idempotent; returns True **only on first award** so
  callers can fire one-time analytics. Rejects ids not in `ACHIEVEMENT_IDS`.
- `db.list_achievements(wallet_id) -> {badge_id: awarded_at}`.
- `main._award_badge(wallet_id, badge_id)` — best-effort wrapper: gated by `_ACHIEVEMENTS_SUPPORTED`,
  wrapped in try/except so a badge write can **never** break the primary action; fires `achievement_earned`
  analytics on a first award.
- `GET /achievements` — gated (503 when unsupported); ensures wallet, awards `welcome`, returns
  `{badges: [{...catalog, earned, awarded_at}], earned_count}`.
- Hooks: `_award_badge(...)` in the `/referral/redeem` and `/tokens/gift` success paths.
- `/config/public` exposes `feature_flags.achievements_enabled = _ACHIEVEMENTS_SUPPORTED`.

## 4. Supabase parity

`achievements` table + RLS (service-role policy) + `award_achievement` RPC (`ON CONFLICT DO NOTHING`,
returns `{awarded}`) in the template → rendered `sql/games-schema.sql` + `sql/games-gamma-schema.sql`.
`supabase_db.award_achievement` (RPC) + `list_achievements` (service-role select); both added to
`db.py`'s `_SUPABASE_EXPORTS`. Migration `sql/migrations/20260721T020000_achievements{,_gamma}.sql`.
**Activate on gamma/prod:** apply the migration, set `ACHIEVEMENTS_ENABLED=true`, recreate the container.

## 5. Frontend

`AchievementsSection` in `SettingsDrawer`, gated on `feature_flags.achievements_enabled === true`. Fetches
`/achievements`, renders every badge (earned lit, locked dimmed + grayscaled as a "what's available" hint),
shows an earned/total count. Stays hidden on empty/failed fetch.

## 6. Testing
- `backend/tests/test_achievements.py` (9): idempotent award + first-grant flag; unknown-id rejected;
  awarded_at timestamps; multi-badge; catalog↔frozenset consistency + every id awardable; endpoint returns
  full catalog with earned flags + display metadata; lazy `welcome` on view; referral awards both parties;
  gift awards the sender.
- `frontend/.../AchievementsSection.test.tsx` (3): catalog render + earned count + earned/locked state;
  hidden on empty; hidden on fetch failure.

## 7. Follow-ups
- Game-based badges (first game, Nth game, big win, streak day N, first purchase) — needs durable per-wallet
  game-completion + purchase writes first (game_history is currently in-memory). `first_purchase` could hook
  the webhook credit path when that's wired.
- Award toast/notification on first earn (currently silent + analytics only).
