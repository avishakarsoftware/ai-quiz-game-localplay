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

DB facts (backbone for #2/#3): `wallets` table columns = id, balance, lifetime_purchased,
last_daily_bonus_date, ads_watched_today, ads_watched_date, created_at. Migration pattern =
`try: ALTER TABLE ... ADD COLUMN / except duplicate-column`. `credit_purchase` shows the idempotency
pattern (reference_id dedup inside a `BEGIN IMMEDIATE` txn). `check_and_grant_daily_bonus` is currently
**flat** (no streak). `_utc_date_str()` exists. `credit_tokens` is NOT idempotent on its own — must add a
dedup check for referral.

Decision — **specs reflect reality**: each spec's Status header states what already exists vs. what this
work adds, so the docs don't imply green-field where it isn't.

---
