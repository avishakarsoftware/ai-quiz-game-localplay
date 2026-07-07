# NIGHT-BUILD-JOURNAL

Autonomous overnight build (2026-07-07). User asleep; I proceed making + logging reasonable
decisions, implementing, testing, committing to master (no branching, no deploy).

---

## SUMMARY (filled in at the end)

_(pending — see per-feature sections below until this is populated)_

---

## Orientation findings (before writing any code)

Discovered a lot of the requested surface **already exists** — recalibrated scope from "build from
scratch" to "extend/complete" for #1 and #5:

- **#1 Analytics** — Frontend PostHog is **already built**: `posthog-js@^1.352.0` dep,
  `frontend/src/utils/analytics.ts` (`initAnalytics`/`track`/`identify`, key-gated no-op), `initAnalytics()`
  called at boot (`main.tsx:7`), and ~23 `track()` events already fire app-wide. **Gaps:** (a) `identify()`
  is never called (sessions aren't tied to a wallet); (b) `VITE_POSTHOG_KEY/HOST` **not baked** into
  `cap-build.mjs`/`ionos-build.mjs`; (c) **no backend analytics at all** — server-authoritative events
  (IAP credit via webhook, referral, ad reward) aren't captured. So #1 = backend capture module (net-new) +
  `identify()` wiring + build-script baking + a few missing economy events.
- **#5 Remote config** — Frontend is **already built**: `useRemoteConfig` fetches static
  `public/config.json` with cache/TTL/kill-switches/pricing/promo/feature_flags/announcements
  (`types/remoteConfig.ts`, `RemoteConfigContext`, MaintenanceOverlay/AnnouncementBanner). **Gaps:** no
  **backend** `/config/public` endpoint (frontend reads a static file), and the schema lacks an
  `enabled_game_types` list + tunable spark costs. So #5 = backend endpoint (net-new) + schema extension +
  frontend game-catalog gating (additive — keep the static-file flow working).
- **#2 streak / #3 referral / #4 share card** — net-new.

## Feature 1 — Analytics (PostHog) ✅

**Decisions:**
- Backend `analytics.py`: dependency-free (`httpx`), `capture()`/`capture_bg()`, **no-op unless
  `POSTHOG_API_KEY` set**. `capture_bg` holds strong task refs to dodge the asyncio fire-and-forget GC bug.
- `distinct_id = wallet_id` (user_id else device_id) so backend + frontend events unify on one person.
- Server events emitted: `web_purchase_credited` (Stripe), `iap_purchase_credited` + `iap_refund`
  (RevenueCat webhook), `spark_earned{source:ad}` (ad reward). Referral/daily-bonus events added in their
  own features.
- Frontend: wired `identify()` in `AuthContext` (sign-in, restored session, and **anonymous device wallet**
  so the anon distinct_id matches the backend wallet_id). Baked `VITE_POSTHOG_KEY/HOST` into
  `cap-build.mjs` + `ionos-build.mjs` (absent ⇒ disabled).
- Did NOT touch `utils/platform.ts` (analytics keeps its own getPlatform, per instruction).

**Files:** `backend/analytics.py` (new), `backend/config.py` (+POSTHOG_*), `backend/main.py` (import +
4 capture sites), `backend/tests/test_analytics.py` (new, 5 tests), `frontend/src/context/AuthContext.tsx`
(identify), `frontend/scripts/{cap-build,ionos-build}.mjs`, `frontend/src/utils/__tests__/analytics.test.ts`.

**Tests:** backend 5/5 pass; frontend 2/2 pass; `tsc` clean.

**Deviation:** dropped a brittle `initAnalytics` no-op assertion — the test env has a `VITE_POSTHOG_KEY`
set, so init legitimately runs there. Kept the load-bearing pre-init no-op assertions.

**Needs user:** a PostHog project + `POSTHOG_API_KEY` (backend) and `VITE_POSTHOG_KEY` (build env) to turn on.

---

## Feature 2 — Login-streak daily bonus ✅

**Decisions:**
- Reward = `min(STREAK_BASE + (streak-1)*STREAK_STEP, STREAK_MAX)` = 10/15/20/25/30… (env-tunable).
  `STREAK_BASE` defaults to `DAILY_BONUS_TOKENS` so **day-1 is unchanged** — existing tests keep passing.
- Added `wallets.bonus_streak` via the idempotent add-column migration. New `_utc_yesterday_str()` +
  `_streak_reward()` helpers. `check_and_grant_daily_bonus` now returns a **4-tuple**
  `(granted, balance, streak, reward)`; streak continues if last claim == yesterday, else resets to 1.
- Balance-at-cap still advances the streak (login counts even when wallet is full) — logged when clipped.
- `/tokens/balance` payload gains `bonus_streak` + `streak_next_reward`; emits `spark_earned{source:daily_bonus,streak}`.
- Frontend: streak chip ("🔥 Day N streak") under the spark badge when streak ≥ 2.

**Supabase deviation (logged):** the deployed `grant_daily_bonus` RPC still grants a FLAT bonus. I did
**not** change its call signature (would break prod against the old RPC and can't be tested here). The
wrapper now returns the 4-tuple with safe fallbacks (streak=1 on grant) and a comment documenting the SQL
RPC update needed to activate full streak on Supabase. **SQLite (local/dev/tests) has full streak.**

**Files:** `backend/config.py` (STREAK_*), `backend/db.py` (migration + helpers + logic),
`backend/supabase_db.py` (4-tuple wrapper + note), `backend/tokens.py` (payload), `backend/main.py`
(event), `backend/tests/test_streak_bonus.py` (new, 6 tests), `backend/tests/test_tokens.py` (updated 4
unpackers), `frontend/src/hooks/useTokenBalance.ts` (+fields), `frontend/src/components/SettingsDrawer.tsx` (chip).

**Tests:** streak 6/6 + tokens all pass (73 total in that batch); IAP suite unchanged (19 pass; 3
pre-existing stripe-module failures unrelated); frontend tsc clean.

---

## Feature 3 — Referral rewards ✅

**Decisions:**
- `wallets.referral_code` (6-char, unambiguous alphabet, **unique partial index**) + `referred_by`
  (one-time gate), added via idempotent migrations.
- `get_or_create_referral_code` (lazy, retry-on-collision), `count_referrals_today`, `redeem_referral`
  (single `BEGIN IMMEDIATE` txn). Both parties credited via a new `_credit_in_txn` helper (caps at
  MAX_TOKEN_BALANCE, always writes a txn row so idempotency + daily-cap counts hold). Idempotent on
  `reference_id = referral:{referrer}:{referee}`.
- Guards → status codes: `invalid_code`→404, `self_referral`→400, `already_redeemed`→409,
  `cap_reached`→429 (cap does NOT set `referred_by`, so the referee can retry another code).
  `REFERRAL_REWARD=20`, `MAX_REFERRALS_PER_DAY=10` (env-tunable).
- Endpoints `GET /referral/code` + `POST /referral/redeem` (rate-limited); emit `spark_earned{referral}` +
  `referral_redeemed` for both roles.
- Frontend: self-contained `ReferralSection` (code + Share via navigator.share/clipboard + redeem input,
  prefilled from a `?ref=CODE` launch link) rendered in `SettingsDrawer`.

**Files:** `backend/config.py`, `backend/db.py` (migrations + 4 fns + helper), `backend/main.py`
(2 endpoints + model), `backend/tests/test_referral.py` (new, 8 tests),
`frontend/src/components/ReferralSection.tsx` (new), `frontend/src/components/SettingsDrawer.tsx`.

**Tests:** referral 8/8; combined feature batch 19/19; tsc clean.

**IMPORTANT Supabase safety (handled):** db.py dispatches listed functions to `supabase_db` in prod
(`globals()[_name] = getattr(_supabase_db, _name)`, db.py:1932). My referral fns are NOT in that list, so in
supabase mode `db.redeem_referral` would run SQLite logic against a **phantom local DB** (and the columns
don't exist in Postgres). Fix: the referral **endpoints are gated to `DB_BACKEND != "supabase"`** — prod
returns a clean 503 and the frontend hides the section. Full Supabase parity is a follow-up: add
`bonus_streak`/`referral_code`/`referred_by` columns + `games_redeem_referral`/`games_referral_code` RPCs to
`sql/games-schema.sql`, add the fn names to db.py's override list, and drop the endpoint gate.

---

## Feature 4 — Shareable result cards ✅

**Decisions:**
- `backend/share.py`: in-memory snapshot store (token → {game_type, winner, top_score, player_count}) with
  TTL + max-count eviction (mirrors the quiz store). `POST /share/game` mints a token; `GET /share/game/{token}`
  returns an OG-unfurl HTML page (dynamic title/description with winner+score). Unknown/expired token → a
  generic branded page (still 200, so stale links look fine).
- **v1 = dynamic OG text + static image** (`{PUBLIC_BASE_URL}/og-image.png`, which already exists in
  `frontend/public/`). Per-result dynamic image generation is deferred (logged).
- Input sanitized on store (tag-strip + control-char removal, length clamp) and HTML-escaped once on render.
- **Bug I caught + fixed:** initial `render_html` double-escaped the winner (escaped the field, then escaped
  the whole title again) → `&amp;lt;`. Now escapes once at the render boundary. Test proves tag payloads are
  stripped and bare `<` is escaped.
- Frontend: `PodiumScreen` gains an optional `onShareResults`; OrganizerPage passes a handler
  (`utils/shareResult.ts`) that POSTs the summary and opens the OS share sheet (clipboard fallback). Hidden
  in `hostAppMode`.

**Files:** `backend/config.py` (SHARE_*), `backend/share.py` (new), `backend/main.py` (import + 2 routes +
model), `backend/tests/test_share_card.py` (new, 7 tests), `frontend/src/utils/shareResult.ts` (new),
`frontend/src/components/organizer/PodiumScreen.tsx`, `frontend/src/pages/OrganizerPage.tsx`.

**Tests:** share 7/7; tsc clean. In-memory store is per-process (fine for v1 best-effort links).

---

DB facts (backbone for #2/#3): `wallets` table columns = id, balance, lifetime_purchased,
last_daily_bonus_date, ads_watched_today, ads_watched_date, created_at. Migration pattern =
`try: ALTER TABLE ... ADD COLUMN / except duplicate-column`. `credit_purchase` shows the idempotency
pattern (reference_id dedup inside a `BEGIN IMMEDIATE` txn). `check_and_grant_daily_bonus` is currently
**flat** (no streak). `_utc_date_str()` exists. `credit_tokens` is NOT idempotent on its own — must add a
dedup check for referral.

Decision — **specs reflect reality**: each spec's Status header states what already exists vs. what this
work adds, so the docs don't imply green-field where it isn't.

---
