# SPEC-STREAK-BONUS — Daily login-streak bonus

Status: **Proposed — not started** (2026-07-07)
Owner: Avi
Related: `SPEC.md` (spark economy), `backend/db.py` (`check_and_grant_daily_bonus`), `backend/tokens.py`

---

## 0. What exists today

`check_and_grant_daily_bonus(wallet_id)` grants a **flat** `DAILY_BONUS_TOKENS` (10) once per UTC day
(idempotent on `wallets.last_daily_bonus_date`). There is **no streak** — a player who logs in daily gets
the same 10 as one who logs in monthly. (Note: `config.STREAK_THRESHOLDS` is an *in-game answer-streak*
points multiplier — unrelated to this login streak.)

## 1. Goal

Reward consecutive daily logins with an escalating bonus, to lift day-over-day retention. Miss a day → the
streak resets. Purely additive to the existing daily-bonus mechanic; same once-per-UTC-day idempotency.

## 2. Reward curve (env-tunable)

`reward = min(STREAK_BASE + (streak - 1) * STREAK_STEP, STREAK_MAX)`, then capped at `MAX_TOKEN_BALANCE`.

| Var | Default | Meaning |
|---|---|---|
| `STREAK_BASE` | 10 | day-1 bonus (== current `DAILY_BONUS_TOKENS`, so day 1 is unchanged) |
| `STREAK_STEP` | 5 | added per consecutive day |
| `STREAK_MAX` | 30 | ceiling (day 5+) |

Day 1→10, 2→15, 3→20, 4→25, 5+→30. `DAILY_BONUS_TOKENS` stays as the day-1 value; `STREAK_BASE` defaults to
it. (If they diverge, `STREAK_BASE` wins for streak math; keep them equal to avoid confusion.)

## 3. Data model

Add `wallets.bonus_streak INTEGER NOT NULL DEFAULT 0` via the try/except `ALTER TABLE ADD COLUMN` migration
pattern (both SQLite `db.py` and a Supabase migration + `supabase_db` parity).

## 4. Logic — extend `check_and_grant_daily_bonus`

Inside the existing `BEGIN IMMEDIATE` txn, after the "already claimed today" check:
- `today = _utc_date_str()`, `yesterday = _utc_yesterday_str()` (new helper).
- If `last_daily_bonus_date == yesterday` → `streak = bonus_streak + 1`, else `streak = 1` (missed a day, or
  first ever, or a gap).
- `reward = min(STREAK_BASE + (streak-1)*STREAK_STEP, STREAK_MAX)`.
- Credit `reward` (cap at `MAX_TOKEN_BALANCE`), set `last_daily_bonus_date = today`, `bonus_streak = streak`,
  reset the ad counter (as today), write a `daily_bonus` transaction with `metadata={"streak":streak}`.
- Return `(granted, new_balance, streak, reward)` — extend the return tuple (update all callers).

## 5. Surfacing

- `tokens.get_token_status` / `GET /tokens/balance` payload gains `bonus_streak` and (when just granted)
  keeps `bonus_amount` = the streak-scaled reward. Add `streak_next_reward` (what tomorrow pays) for UI.
- **Frontend:** show the streak in the balance UI / `SettingsDrawer` (e.g. "🔥 Day 3 — +20 sparks",
  "Day 4 tomorrow = +25"). Fire `spark_earned{source:'daily_bonus', streak}` (per SPEC-ANALYTICS).

## 6. Edge cases

- **Timezone:** UTC day boundary, consistent with the existing bonus — documented; not localized (v1).
- **Cap collision:** if `MAX_TOKEN_BALANCE` clips the reward, `actual_bonus` may be < computed reward — the
  streak still increments (login counts even if wallet is full). Log actual vs computed.
- **Backfill:** existing wallets have `bonus_streak=0`; first grant post-migration computes from
  `last_daily_bonus_date` (yesterday ⇒ streak 1, since stored streak is 0 → 0+1=1; acceptable — no
  retroactive streak). Documented.

## 7. Testing (`backend/tests/test_streak_bonus.py`)
- Day 1 grants BASE; consecutive day (`last=yesterday`) increments and scales; gap (`last=2 days ago`)
  resets to 1; same-day re-call is idempotent (no double grant); reward clamps at STREAK_MAX; cap at
  MAX_TOKEN_BALANCE doesn't crash and still advances streak. Use monkeypatched dates (inject today/yesterday).

## 8. Files touched
- `backend/config.py` (STREAK_BASE/STEP/MAX), `backend/db.py` (migration + logic + `_utc_yesterday_str`),
  `backend/supabase_db.py` (+ SQL migration), `backend/tokens.py` (return fields), `backend/main.py`
  (balance payload), `backend/tests/test_streak_bonus.py` (new).
- Frontend: balance hook + `SettingsDrawer` streak display.
