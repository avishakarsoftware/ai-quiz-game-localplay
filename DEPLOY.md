# Revelry Games / LocalPlay — Production Deployment Guide

## Architecture Overview

```
Users → games.revelryapp.me (IONOS CDN) → static frontend
     → gamesapi.revelryapp.me (GCP VM)  → FastAPI backend + WebSockets + optional frontend
     → gamesapi-gamma.revelryapp.me (GCP VM) → FastAPI backend + WebSockets + frontend
```

- **Frontend**: Static React/Vite build hosted on IONOS shared hosting
- **Backend**: FastAPI in Docker on a GCP Compute Engine e2-micro VM
- **Current persistence**: Production and gamma use the shared Supabase project (`games_*` / `games_gamma_*`); SQLite files remain on the VM only as local-dev defaults and rollback backups
- **Backend-served SPA**: The FastAPI container can serve the built Vite frontend from `/app/static`
- **Reverse proxy**: Nginx on the VM handles HTTPS termination + WebSocket upgrade
- **SSL**: Let's Encrypt via Certbot (auto-renewing)

The public production game is expected to run at `https://games.revelryapp.me/` from IONOS. The backend-served SPA gives us a same-origin deployment path for gamma, previews, and emergency/prod fallback at the API domains.

## Production URLs

| Component | URL |
|-----------|-----|
| Frontend  | https://games.revelryapp.me/ |
| Backend API + SPA fallback | https://gamesapi.revelryapp.me |
| Gamma full stack | https://gamesapi-gamma.revelryapp.me |
| Spectator/TV | https://games.revelryapp.me/spectator |
| Player join  | https://games.revelryapp.me/join |
| Cast App ID  | `1BC9ACD8` |

## Current VM State

As of the SPA rollout, the VM has both LocalPlay containers deployed:

| Environment | Domain | Container | Image | VM bind | Data dir |
|-------------|--------|-----------|-------|---------|----------|
| Production | `gamesapi.revelryapp.me` | `games-backend` | `revelry-backend:latest` | `127.0.0.1:8000` | `/home/revelry-games/revelry-data` |
| Gamma | `gamesapi-gamma.revelryapp.me` | `games-backend-gamma` | `revelry-backend-gamma:latest` | `127.0.0.1:8004` | `/home/revelry-games/revelry-data-gamma` |

The older backup containers `revelry-platform` and `revelry-gamma` may exist on the VM. They are not managed by `scripts/deploy-gcp.sh`; the LocalPlay deploy script only stops/removes `games-backend` and `games-backend-gamma`.

## Environment status ledger — the single source of truth for "what is live where"

**Update this table in the same commit as any deploy, DB migration, or policy flip.** Specs must
link here instead of restating environment status (stale spec headers were a recurring bug).

| Capability / feature | Gamma | Prod | Notes |
|---|---|---|---|
| Deployed code (backend+SPA) | `f4d89f5a` (2026-07-19) | `f4d89f5a` (2026-07-19) | Account-deletion deploy. `DELETE /account` live on both (present in openapi.json). IONOS public frontend updated 2026-07-19 to `index-C84KNWsC.js` (deletion UI verified live; `config.json` byte-identical, no clobber) — all three web surfaces now carry the account-deletion build. Post-deploy verified: prod stripe→400, rc→401, health→200; synthetic deletion cycle green on BOTH envs (see below). |
| Account deletion (migration + endpoint) | ✅ live + verified | ✅ live + verified | 2026-07-19: `sql/migrations/20260718T000000_account_deletion.sql` applied via Management API (gamma first, then prod): `*_deleted_accounts` denylist + `*_delete_account` RPC created, `*_token_transactions_wallet_id_fkey` **CASCADE dropped** (constraint names pre-verified against pg_constraint on both prefixes). Synthetic account cycle on each env: user+wallet(240)+ledger row → RPC delete → user/wallet gone, **ledger retained**, denylisted, re-delete `already_deleted`; live resurrection probe (`/tokens/balance` with the deleted id) returned 200/balance:0 and created **no wallet, no signup bonus**. All test rows cleaned (0 residue). |
| Login-streak bonus (SQL RPC) | ✅ live | ✅ live | applied 2026-07-08, targeted migration |
| Check-in games policy (`party_quests`, `find_someone`) | ✅ enabled | ✅ enabled | policy rows 2026-07-08; prod Party Quests upgraded from quick-start-only on 2026-07-14 |
| Party Quests staged flow (authoring caps + strict `requires_prepared_content_for_checkin`) | ✅ flipped 2026-07-09 | ✅ flipped 2026-07-14 | production DDL/policy enabled after gamma strict harness passed |
| `generated_content.content_type` CHECK | quiz/mlt/drawing/housie/chit_pull/party_quests | quiz/mlt/drawing/housie/chit_pull/party_quests | prod verified with disposable `party_quests` insert/delete on 2026-07-14 |
| Referrals (`REFERRALS_ENABLED` + referral RPCs) | ✅ live | ✅ live | Activated 2026-07-21 (commit `acd284b9`): referral RPCs applied to both prefixes + `REFERRALS_ENABLED=true` + containers recreated; synthetic RPC guards + live end-to-end HTTP flow verified. Also fixed the Supabase `new_balance` response key. Works on SQLite locally without the flag. |
| Spark gifting (`GIFTING_ENABLED` + `gift_sparks` RPC) | ❌ off | ❌ off | Built on master 2026-07-21 (commit `49ad0782`), gated OFF. Migrations `sql/migrations/20260721T010000_gifting{,_gamma}.sql` and follow-up `20260721T040000_gifting_idempotency_replay{,_gamma}.sql` authored but NOT applied; `GIFTING_ENABLED` unset. Works on SQLite locally. To activate: apply migrations → set `GIFTING_ENABLED=true` → recreate container. |
| Achievements v1 (`ACHIEVEMENTS_ENABLED` + `award_achievement` RPC) | ❌ off | ❌ off | Built on master 2026-07-21 (commit `c80598a5`), gated OFF. Migration `sql/migrations/20260721T020000_achievements{,_gamma}.sql` authored but NOT applied; `ACHIEVEMENTS_ENABLED` unset. Works on SQLite locally. To activate: apply migration → set `ACHIEVEMENTS_ENABLED=true` → recreate container. |
| Share-card DB persistence (`share_snapshots` table) | ❌ not applied | ❌ not applied | Built on master 2026-07-21 (commit `1a301f90`). Migration `sql/migrations/20260721T030000_share_snapshots{,_gamma}.sql` authored but NOT applied. No flag — `share.py` is best-effort and degrades to in-memory until the table exists, so applying it is a transparent no-downtime upgrade. |
| Native IAP (`REVENUECAT_WEBHOOK_SECRET`) | ✅ configured | ✅ live + verified (both sides) | RevenueCat prod webhook "Revelry Games Prod" (`gamesapi.revelryapp.me/webhook/revenuecat`, Bearer, Both env, all apps/events, HMAC off) created + Active 2026-07-14. **Test event `E1662E2D-1609-4EBF-8A70-241FCCDA68B5` (env=SANDBOX, product=`test_product`) confirmed 200 on BOTH sides** — RevenueCat dashboard shows Response 200, and prod logs show the same event id authenticated + processed (webhook_events dedup + `games_mark_webhook_processed`). **Store rollout (2026-07-16):** iOS **v3.1.1 (6) archived + uploaded to App Store Connect** (review submission with the 3 IAPs attached still pending); Android release AAB **built** (v3.1.1/versionCode 6, prod-baked, signed) but **not yet uploaded** to the Production track. Real customer purchases still gated on store approval/promotion. |
| Web Stripe | test keys (local `backend/.env`) | ✅ live keys configured (real-card test pending) | 2026-07-15: prod `.env` set with `sk_live_` `STRIPE_SECRET_KEY` + `whsec_` `STRIPE_WEBHOOK_SECRET` + `CHECKOUT_RETURN_URL=https://games.revelryapp.me/`; container recreated. Verified: `/webhook/stripe`→400 (configured), `/checkout/create`→live `cs_live_` session on `checkout.stripe.com`. Live secrets backed up in `backupenv/quiz/local/localplay-prod-payment.env`. Remaining: one real-card end-to-end purchase to confirm credit + refund clawback. |
| Cross-app Playwright testids | ✅ | ✅ (incl. IONOS) | 8 testids, 2026-07-09 |
| Room snapshot/restore (`ROOM_SNAPSHOT_ENABLED`) | ✅ live + restart/reconnect-verified | ✅ deployed + smoke-verified | gamma live-verified 2026-07-14: room `V0QSIN` + player seat survived a real container restart and WebSocket reconnect; prod restart drill pending |
| Paywall price accuracy (`ErrorModal` CTA) | ✅ fixed + live | ✅ fixed + live (all 3 web surfaces) | Deployed 2026-07-17. The CTA no longer interpolates a pack size/price; verified on gamma, prod, and IONOS that the old `Sparks — {price}` template is **absent** and the literal `"Get Sparks"` is present in each served bundle. `token_pack_price`/`token_pack_amount:110` remain in the bundle as **inert config data** (nothing renders them) — retiring that dead single-pack config is tracked separately. **Native still needs the rebuilt binary**: v3.1.2(7) is prepped, the uploaded v3.1.1(6) is stale. |
| **Google Play submission** | n/a | ✅ **IN REVIEW since 2026-07-20** | All 12 changes submitted (~4:45 AM PT): production release **8 (3.1.2)** (AD_ID-free), full listing, IARC rating (Teen US / PEGI 18 EU / R18+ AU / Korea pending GRAC), Data safety, declarations. **Managed publishing OFF → auto-live in 176 countries on approval.** Gotcha that cost an hour: the ad-ID "No" declaration is validated against EVERY active track — the July 6 internal-testing release (v5, AD_ID-bearing) kept the check red until superseded with bundle 8. After approval: license-tester purchase smoke. |
| Store listing assets (screenshots + copy) | n/a | ✅ refreshed `67af2407` | 7 screens × 4 store targets captured from prod at exact required px (`marketing/{app-store,play-store}/`), regenerable via `frontend/e2e/store-screenshots.spec.ts`; `store-listing.md` rewritten for **Revelry Games** + all 33 games. Not yet uploaded to either console. |
| Store-required legal pages (`/privacy`, `/support`) | ✅ live | ✅ live (all 3 surfaces) | Deployed 2026-07-18 (`72d03165`). Privacy policy rewritten to match reality (accounts + purchases + all processors); new support page for Apple's required Support URL. Extensionless paths now resolve on the backend SPA too (MultiViews-style), not just IONOS. Guarded by `e2e/legal-pages.spec.ts` (asserts rendered content, not status — the old `/support` returned **200** while rendering 11 chars) and `backend/tests/test_frontend_static.py`. Store console values: `https://games.revelryapp.me/privacy` + `/support`. |
| Analytics (PostHog keys) | ❌ unset | ❌ unset | code no-ops until keys set |
| Ads (`ADS_ENABLED` / `ads_enabled`) | ❌ | ❌ | Rewarded-AdMob SSV (SPEC-ADS) still unbuilt (no ad SDK). The legacy trust-the-client `/tokens/ad-reward` stub was farmable; as of 2026-07-21 (commit `672b7fb0`) it is gated behind `ADS_ENABLED` (default false → 403) in code — **built on master, NOT yet deployed**, so prod still runs the old farmable endpoint until the next backend deploy. Do NOT set `ADS_ENABLED=true` until SSV replaces the stub. |

### Recent gamma + prod + IONOS deploy — July 17, 2026 (paywall price fix + `--build-on-vm`)

Deployed `6144ebd0` (fix `67af2407`) to **all three web surfaces**. The out-of-sparks CTA was
advertising `Get 110 Sparks — $0.99` — a pack that cannot be bought — from the retired single-pack
config; the real ladder is 50/200/500 and native prices are store-localized by RevenueCat. This was
the highest-intent purchase path, and the web rail is the one already taking real money.

**Deploy path — `--build-on-vm` is now a real flag.** Docker Desktop was off again (pihole /
homeassistant run there; deliberately not restarted). Rather than hand-roll production deploy
commands a second time, the fallback documented on 07-16 was implemented as
`./scripts/deploy-gcp.sh --with-frontend --build-on-vm`: it tars the build context, ships it, and
runs `docker build` on the VM, then follows the script's normal backup/stop/run/health path. Also
faster than the local path (native x86, datacenter link, a few MB of context instead of a large
image tarball). Gamma first, verified, then prod.

**Verification.** Grepping for `"110 Sparks"` would have been a false negative — that string never
existed in the bundle, since the old code was a template with interpolated values. The real test is
that the old `Sparks — ` template is **absent** and the literal `"Get Sparks"` is **present**:
confirmed on gamma (`index-D2aAVhRM.js`), prod (same), and IONOS (`index-6V9hgGrE.js`). `config.json`
was byte-identical to live before upload, so no feature-flag clobber; uploaded additively (no
`--delete`). Post-deploy: prod `/webhook/stripe`→400, `/webhook/revenuecat`→401, both `/health`→200,
IONOS→200, `/catalog`→33 games, and `e2e/payment-ux.spec.ts` 5/5 green against live prod. DB backed
up on both (`revelry_20260717_230323.db` gamma, `revelry_20260717_230508.db` prod).

**Native v3.1.2 / build 7 prepped** (iOS `MARKETING_VERSION` 3.1.2 / `CURRENT_PROJECT_VERSION` 7;
Android `versionName` 3.1.2 / `versionCode` 7). `cap:sync:prod` baked both bundles — verified the
main chunk (not a small vendor chunk) carries the fix, `gamesapi.revelryapp.me`, the RevenueCat
publishable keys, and appName "Revelry Games". iOS handed to Xcode for Archive → Distribute.
**Android AAB not rebuilt** — the release keystore password was not available in
`backupenv/quiz/local/`, the keychain, or the environment; it must be supplied to run
`KEYSTORE_PASSWORD=… KEY_PASSWORD=… ./gradlew bundleRelease`.

### Recent gamma/prod deploy — July 14, 2026 (Party Quests strict staging harness + launch metadata)

Deployed commit `684d8354` to gamma/prod with `./scripts/deploy-gcp.sh --gamma --with-frontend` and `./scripts/deploy-gcp.sh --with-frontend`. Ships a LocalPlay-side Revelry launch fix and QA hardening:

- `/integrations/revelry/launch-token/resolve` now returns `game_type`, `content_id`, and `game_title` so LocalPlay organizer/player surfaces can initialize the correct non-quiz game before the first WebSocket sync. This fixed a user-visible Party Quests issue where a prepared `party_quests` session opened as **AI Quiz Lobby** even though the room/session were correctly typed.
- `_format_session` now maps saved `game_id` to public `content_id`, so Revelry and the LocalPlay harness can see the prepared-content pointer on session responses.
- The Revelry pre-prod matrix now has deterministic Party Quests saved-content fixtures.
- Added `e2e/revelry-party-quests-staging.spec.ts` and included it in `npm run test:e2e:preprod-revelry`.

Gamma backup: `revelry-backups-gamma/revelry_20260714_192522.db`; health passed. Production backup: `revelry-backups/revelry_20260714_192656.db`; health passed. Verified locally: targeted backend Revelry/catalog tests (`17 passed`), host-app/Party Quests frontend unit tests (`14 passed`), frontend production build. Verified live on gamma after redeploy: focused Party Quests staging Playwright plus full embedded Revelry pre-prod suite (`3 passed`): setup-required 409, saved preview Host/Player/TV, prepared Party Quests start, correct **Party Quests Lobby**, first-player auto-start, late join board assignment, cancellation/ROOM_CLOSED, workspace clearing, sorted/searchable catalog, and every launchable Revelry game resolving organizer/player/watch launch routes. Verified prod DDL/policy: Supabase migration `20260715021000_allow_party_quests_generated_content` applied to production, disposable `content_type='party_quests'` insert/delete passed, and the production `party_quests` host-app policy row now returns `status=live`, `can_create_content=true`, `can_edit_content=true`, `supports_ai_generation=true`, `embedded_authoring_supported=true`, and `requires_prepared_content_for_checkin=true` for the running `production` environment. Standard remote smokes passed after deploy for both `https://gamesapi-gamma.revelryapp.me` and `https://gamesapi.revelryapp.me`.

### Recent gamma + prod deploy — July 14, 2026 (allowlist cleanup + snapshot promotion)

Promoted commit `7a163171` to gamma and prod with the normal backend-served SPA path. Ships the July 14 refactor/snapshot train plus a Revelry start allowlist cleanup: `party_quests` is no longer duplicated in `REVELRY_PARTY_GAME_START_TYPES`, and a catalog-policy test now prevents duplicate start-type entries from creeping back in. No schema migration, policy flip, or IONOS upload was performed in this pass.

- **Gamma:** `./scripts/deploy-gcp.sh --gamma --with-frontend` -> `games-backend-gamma` (Supabase `games_gamma_`). DB backed up to `revelry-backups-gamma/revelry_20260714_175818.db`; health passed.
- **Gamma live restart drill:** created room `V0QSIN`, joined a player, confirmed the snapshot file existed on the mounted gamma data volume, restarted `games-backend-gamma`, saw logs restore `V0QSIN`, and reconnected the same player session successfully (`RECONNECTED_OK`).
- **Prod backend + fallback SPA:** `./scripts/deploy-gcp.sh --with-frontend` -> `games-backend` (Supabase `games_`). DB backed up to `revelry-backups/revelry_20260714_180650.db`; health passed.
- **Verified:** focused backend tests for catalog policy, room snapshot, and engine_common passed (`41 passed`); `backend/tests/test_websocket_async.py` passed (`6 passed`) outside the sandbox; broader backend suite reached `958 passed, 1 skipped` before the sandbox blocked localhost socket binding for that same WebSocket file. Remote smoke passed for gamma and prod (`make test-remote-gamma`, `make test-remote-prod`). Playwright catalog smoke passed for gamma and prod backend-served SPA (`2 passed` each).

### Recent gamma + prod + IONOS deploy — July 16, 2026 (payment UX + native v3.1.1)

Deployed commit `8ca4d57a` to **all three web surfaces**: gamma + prod backend-served SPA (VM-build path — Docker Desktop was off; built the image on the VM and swapped both containers) and the IONOS public frontend (`npm run ionos:build` + additive scp; `config.json` was identical so no clobber). Ships the payment-UX improvements (cost context + purchase terms in Get Sparks). **Zero backend `.py` changes** since the prior prod image (`91b93f40`) — effectively a frontend refresh; the prod Stripe/RevenueCat env set 2026-07-15 was preserved. Verified live: gamma+prod serve `index-BfmpLaIh.js`, IONOS serves `index-CPlKcEqO.js` (all match their local builds containing `spark-cost-context`); prod `/webhook/stripe` → 400, `/webhook/revenuecat` → 401, `/checkout/create` → live `cs_live` Checkout Session. DB backed up on both.

**Native builds (v3.1.1 / versionCode 6, build 6):** `npm run cap:sync:prod` baked the prod bundle (API=`gamesapi.revelryapp.me` + RC/OAuth keys, appName "Revelry Games") into both projects. **Android AAB built + signed** (`app-release.aab`, 8.6 MB, v2 upload keystore) — ready to upload to the Play Production track. **iOS: prepped, handed to Xcode** — the keychain has only an Apple *Development* cert (no Distribution cert) and no ASC upload creds, so the App Store archive must be done in Xcode (Archive → Distribute → App Store Connect, which creates the distribution cert via the signed-in Apple ID).

### Recent gamma deploy — July 14, 2026 (refactor train + room snapshot/restore)

Deployed commit `d04e7f0c` to gamma. Ships: engine_common extraction (one strict sanitization policy — 4 engines were below the documented tag-stripping baseline), GAME_CATALOG extracted from main.py, CI hardening (vitest in CI, e2e un-quarantined, pytest-timeout, Postgres parity suite — 8/8 green vs postgres:16), and **room snapshot/restore** (`ROOM_SNAPSHOT_ENABLED=true` default; snapshots at `/app/data/room_snapshots` on the mounted volume).

**Deploy-path note:** the local `docker build` was blocked this pass (Docker Desktop VM couldn't reach Docker Hub and `python:3.12-slim` was no longer cached; host network fine — did NOT restart Docker Desktop because pihole/homeassistant run there). Fallback used and worth keeping: build the frontend locally, rsync the backend+static context to the VM, `docker build` **on the VM** (native x86 + datacenter network), then the script's normal stop/run/health steps. Consider adding `--build-on-vm` to deploy-gcp.sh.

Verified live: health, 16-game revelry catalog with `party_quests` strict flag intact, SPA serving. **Restart drill on live gamma:** created room `P93RR8`, player joined via WSS, snapshot appeared on the volume within one 10s tick, `docker restart games-backend-gamma`, logs showed `Restored 1 room(s) from snapshots: P93RR8`, and the same session token got `RECONNECTED` with the seat intact. Local: backend 1031 passed, frontend 291 + tsc clean. Prod not deployed.

### Recent gamma + prod deploy — July 13, 2026 (authoring-return docs/code promotion)

Promoted repo HEAD `6b6fffb5` to gamma and prod with the normal backend-served SPA path. No schema migration, IONOS upload, or Party Quests production capability/policy flip was performed in this pass.

- **Gamma:** `./scripts/deploy-gcp.sh --gamma --with-frontend` -> `games-backend-gamma` (Supabase `games_gamma_`). DB backed up to `revelry-backups-gamma/revelry_20260713_224748.db`; health passed.
- **Prod backend + fallback SPA:** `./scripts/deploy-gcp.sh --with-frontend` -> `games-backend` (Supabase `games_`). DB backed up to `revelry-backups/revelry_20260713_224934.db`; health passed.
- **Verified:** `cd frontend && npm run test:e2e:gamma` passed on desktop+mobile (`2 passed`); `make test-remote-gamma` passed; `make test-remote-prod` passed. The remote smoke covered `/health`, Gemini provider/config, `/media/status`, SPA root, anonymous auth rejection, invalid token rejection, iOS checkout guard, first generation, idempotency, and token balance no-double-charge before room start.
- **Policy note:** production remains on the existing conservative host-app policy. Party Quests staged/check-in production enablement still requires the explicit prod DDL/policy rollout described in `SPEC-REVELRY-INTEGRATION.md`; this deploy only promotes the backward-compatible code/docs state.

### Recent PROD deploy — June 29, 2026 (unified back nav + lobby review peek + grace prune + mint helper)

Promoted runtime commit `435ed15` to gamma and prod. No schema migration required.

- **Gamma:** `./scripts/deploy-gcp.sh --gamma --with-frontend` → `games-backend-gamma` (Supabase `games_gamma_`). DB backed up to `revelry-backups-gamma/revelry_20260629_002655.db`; health passed.
- **Prod backend + fallback SPA:** `./scripts/deploy-gcp.sh --with-frontend` → `games-backend` (Supabase `games_`). DB backed up to `revelry-backups/revelry_20260629_003210.db`; health passed.
- **Public frontend (IONOS `games.revelryapp.me`):** `VITE_BASE_PATH=/ VITE_API_URL=https://gamesapi.revelryapp.me VITE_WEB_URL=https://games.revelryapp.me/ VITE_CAST_APP_ID=1BC9ACD8 npx vite build`, then additive `scp -r dist/*` + `rsync dist/.htaccess` (no `--delete`). Live index serves bundle `index-BHeZoS-L.js` (matches local build); deployed bundle confirmed to contain `Review questions`, `read-only preview`, `restarts the room`, `screen-back-button`.
- Ships: (#1) shared top-left `ScreenBackButton` across every organizer setup/prompt/review/editor screen; (#2) quiz lobby read-only **Review questions** peek that keeps the room (Edit-from-peek restarts it); (#3) `LOBBY_RECONNECT_GRACE_SECONDS` lowered to 600s (10 min) plus a periodic lobby-prune in `_cleanup_expired_rooms`; (#4) `scripts/mint-gamma-revelry-url.sh` mints the seeded-party gamma token so the Revelry e2e matrix (incl. mirror-results-back) runs green.
- **Verified on gamma:** smoke (desktop+mobile) 2/2; lobby-navigation 5/5 (16-game Back sweep, Back-to-games, read-only review peek, Edit-setup); Revelry gamma matrix 3/3 (Drawing save/start/re-enter, quiz mirror-results-back, custom-quiz image upload). Visual review of #1 back pill on prompt/editor/review screens, #2 lobby Review button + peek modal, and mobile no-overlap. Pre-deploy locally: backend 868 + 46 ws, frontend 258, typecheck clean.
- **Verified on prod:** `gamesapi.revelryapp.me` health ok; `games.revelryapp.me` catalog 200 + AI Quiz prompt renders the `‹ Back` control (live Playwright + screenshot).

### Recent PROD deploy — June 28, 2026 (post-podium room reuse roster fix)

Promoted runtime commit `3f029c8` to gamma and prod. No schema migration required.

- **Gamma:** `./scripts/deploy-gcp.sh --gamma --with-frontend` → `games-backend-gamma` (Supabase `games_gamma_`); health passed.
- **Prod backend + fallback SPA:** `./scripts/deploy-gcp.sh --with-frontend` → `games-backend` (Supabase `games_`). DB backed up to `revelry-backups/revelry_20260628_224734.db`; health passed.
- **Public frontend (IONOS `games.revelryapp.me`):** `VITE_BASE_PATH=/ VITE_API_URL=https://gamesapi.revelryapp.me VITE_WEB_URL=https://games.revelryapp.me/ VITE_CAST_APP_ID=1BC9ACD8 npx vite build`, then additive `scp -r dist/*` + `rsync dist/.htaccess` (no `--delete`). Live index serves bundle `index-BwaAlYKl.js`.
- Ships: post-podium room reuse no longer shows a stale roster — `RESET_ROOM` is gated to genuinely finished rooms, `ROOM_CREATED` clears the roster on a fresh room, and config-driven games (Musical Chairs, Party Quests) can reset in place via `runtime_config`. Adds `utils/roomReuse` + unit test for reset eligibility.
- **Verified:** backend 867 + 46 ws; frontend 258; gamma smoke (desktop+mobile), lobby-nav sweep (5), preprod-live (12 gameplay-to-podium), Revelry Drawing + custom-quiz chooser flows; prod smoke on `gamesapi.revelryapp.me` and `games.revelryapp.me` (desktop+mobile).

### Recent PROD deploy — June 28, 2026 (Revelry quiz authoring stale-state fix)

Promoted runtime commit `e285c92` to gamma and prod. No schema migration required.

- **Gamma:** `./scripts/deploy-gcp.sh --gamma --with-frontend` → `games-backend-gamma` (Supabase `games_gamma_`). DB backed up to `revelry-backups-gamma/revelry_20260628_190704.db`; health passed.
- **Prod backend + fallback SPA:** `./scripts/deploy-gcp.sh --with-frontend` → `games-backend` (Supabase `games_`). DB backed up to `revelry-backups/revelry_20260628_190839.db`; health passed.
- **Public frontend (IONOS `games.revelryapp.me`):** rebuilt with `VITE_API_URL=https://gamesapi.revelryapp.me` and uploaded additively with `scp -r dist/*` plus `rsync dist/.htaccess`. Live index serves bundle `index-DrC122EO.js`.
- Ships: embedded Revelry quiz authoring no longer carries an AI-generated quiz into the Custom quiz path after returning to the AI/custom chooser.
- **Verified:** `npm test -- RevelryAuthoringPage --run` passed; `npm run build` passed; `npm run test:e2e:gamma` passed on desktop+mobile against gamma; `PLAYWRIGHT_BASE_URL=https://gamesapi.revelryapp.me npm exec playwright test e2e/gamma-smoke.spec.ts` passed on desktop+mobile; `PLAYWRIGHT_BASE_URL=https://games.revelryapp.me npm exec playwright test e2e/gamma-smoke.spec.ts` passed on desktop+mobile.

### Recent PROD deploy — June 28, 2026 (lobby continuity + answer reveal + lobby nav)

Promoted the gamma-validated RC (runtime commit `b3b9542`; repo HEAD `f794e07` adds only test-only commits) to **prod**. No schema migration required.

- **Backend + fallback SPA:** `./scripts/deploy-gcp.sh --with-frontend` → `games-backend` (Supabase prod `games_`). DB backed up to `revelry-backups/revelry_20260628_170032.db`; health passed; gamma untouched.
- **Public frontend (IONOS `games.revelryapp.me`):** `VITE_BASE_PATH=/ VITE_API_URL=https://gamesapi.revelryapp.me VITE_WEB_URL=https://games.revelryapp.me/ VITE_CAST_APP_ID=1BC9ACD8 npx vite build`, then additive `scp -r dist/*` + `rsync .htaccess` (no `--delete`, no asset cleanup). Live index serves bundle `index-CRH0ltSK.js` (matches local build).
- Ships: quiz answer-reveal on all surfaces, consistent lobby Back/Edit nav + mobile overlap fix, lobby continuity (offline seat preservation / reconnect, `connected_player_count`), Party Quests AI setup, and the Revelry callback event-loop hardening.
- **Verified after promotion:** `scripts/smoke-remote.py --base-url https://gamesapi.revelryapp.me` passed (health, providers, generation, idempotency, token no-double-charge); `PLAYWRIGHT_BASE_URL=https://games.revelryapp.me npm exec playwright test e2e/gamma-smoke.spec.ts` passed desktop+mobile. Pre-promotion gamma RC suites (smoke, lobby-nav, generic 10, preprod-live 12, broader live 4, Revelry preprod matrix 2, UX audit) all green.

### Recent gamma deploy — July 9, 2026 (authoring-return contract hardening)

Deployed commit `22095a0c` to gamma with `./scripts/deploy-gcp.sh --gamma --with-frontend` (prod untouched). Frontend-only: the embedded authoring save-return `postMessage` now mirrors the saved pointer as `content:{localplay_content_id, game_type, status}` (backward compatible — the values stay on `return_url` too), so Revelry can reconcile in place without a full `window.location` reload (the reload was dropping the Revelry session and signing the host out on save). Backend unchanged from the prior gamma deploy. Verified: health green; live gamma entry bundle `index-BRBGQ48j.js` matches the local build. The auth fix still requires Revelry to stop full-reloading on that message.

### Recent gamma + prod deploy — July 9, 2026 (cross-app Playwright data-testids)

Deployed commit `76f5a0b5`/`024db054` to **gamma then prod** — `./scripts/deploy-gcp.sh --gamma --with-frontend` then `./scripts/deploy-gcp.sh --with-frontend`. Frontend-only change: stable `data-testid`s on the embedded organizer/player/spectator surfaces for Revelry's cross-app Playwright (`organizer-room-code`, `organizer-player-count`, `organizer-start-game`, `organizer-end-game`, `player-nickname-input`, `player-join-button`, `player-in-game`, `spectator-root` — see `SPEC-REVELRY-INTEGRATION.md` testid contract). **Zero backend `.py` changes** since the prior deploy (`git diff bae6e769 HEAD -- 'backend/**/*.py'` empty), so both were effectively frontend-only refreshes of the backend-served SPA. Verified live on both: health passed, and the live entry bundle hash (`index-BGnl2Ki9.js`) matches the locally-built dist that contains all 8 testids (prod + gamma serve this build). Prod DB backed up to `revelry-backups/revelry_20260709_010309.db`; prod `/catalog?host_app=revelry` still lists the check-in games (6). Revelry confirmed 2/2 green binding all 8 testids on gamma (then re-verified against prod).

Also refreshed the **standalone IONOS public frontend** (`games.revelryapp.me`, docroot `~/revelryapp/games/`) so all three prod surfaces carry the testids and sit on the same commit. Built via `npm run ionos:build` (points at `gamesapi.revelryapp.me`, guard passed), uploaded additively per §7 (`scp -r dist/*` + `rsync dist/.htaccess`, no `--delete`). `dist/config.json` was byte-identical to the live prod `config.json`, so the overwrite was a no-op (no feature-flag clobber). Verified live: `games.revelryapp.me/` → 200, entry bundle `index-fIPW26v_.js` matches the local build and contains all 8 testids. (This IONOS bundle differs from the backend-served SPA hash because it bakes an explicit `VITE_API_URL`.) The legacy `~/revelryapp/games/quiz/` path was left untouched.

### Recent gamma deploy — June 28, 2026 (Revelry callback event-loop hardening)

Deployed runtime commit `1170215` to gamma with `./scripts/deploy-gcp.sh --gamma --with-frontend`. No schema migration was required. The deploy includes LocalPlay-side Revelry session/callback timing instrumentation and moves runtime WebSocket lifecycle callbacks (`game.started`, `game.completed`, cancellation/expiration) through a worker thread so synchronous HTTP retry/backoff cannot block the asyncio event loop for other rooms and players.

Post-deploy verification:

- `https://gamesapi-gamma.revelryapp.me/health` returned `{"status":"healthy"}`.
- `https://gamesapi-gamma.revelryapp.me/catalog?host_app=revelry` returned the host-app game catalog.

### Recent gamma deploy — June 27, 2026 (Drawing pre-prod coverage)

Deployed runtime commit `4c1ef1e` to gamma with `./scripts/deploy-gcp.sh --gamma --with-frontend`. No schema migration was required. The deploy adds deterministic `/drawing/import` seeding for pre-prod QA, fixes Drawing room start so it enters round one from `START_GAME`, and hardens organizer WebSocket close handling during first-frame auth.

Post-deploy verification:

- `cd frontend && npm run test:e2e:gamma` passed: `2 passed`.
- `cd frontend && PREPROD_LIVE=1 PLAYWRIGHT_BASE_URL=https://gamesapi-gamma.revelryapp.me npm run test:e2e:preprod-live` passed: `12 passed`, including deterministic Drawing gameplay.

Useful state checks:

```bash
gcloud compute ssh revelry-backend --project=revelryapp --zone=us-central1-a --command \
  'docker ps -a --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"'

curl -sS -i https://gamesapi.revelryapp.me/health
curl -sS -i https://gamesapi-gamma.revelryapp.me/health
```

### Gamma QA sprint — June 25, 2026

Deployed commit `2cc7597` to gamma with `./scripts/deploy-gcp.sh --gamma --with-frontend`, after making backend e2e quiz generation deterministic so the default backend suite no longer depends on transient live AI provider availability. No schema migration was required.

Post-deploy verification:

- `.venv/bin/pytest backend/tests` passed: `918 passed`.
- `cd frontend && npm test -- --run` passed: `226 passed`.
- `cd frontend && npm run build` passed.
- `cd frontend && npm run test:e2e:gamma` passed on desktop and mobile, including standalone `Most Popular` and `Cards` filter coverage.
- `cd frontend && PREPROD_LIVE=1 PLAYWRIGHT_BASE_URL=https://gamesapi-gamma.revelryapp.me npm run test:e2e:preprod-live` passed at the time with 11 live gameplay tests. Current pre-prod coverage now also includes deterministic Drawing seeding through `/drawing/import`.
- `cd frontend && npm run test:e2e:gamma:generic` passed for the 10 Generic Prompt Party games.
- `cd frontend && PLAYWRIGHT_BASE_URL=https://gamesapi-gamma.revelryapp.me PREPROD_LIVE=1 TWO_TRUTHS_LIVE=1 npx playwright test e2e/gamma-smoke.spec.ts e2e/bingo-gamma-live.spec.ts e2e/bluff-gamma-live.spec.ts e2e/two-truths-live.spec.ts e2e/standalone-turns-gamma-live.spec.ts e2e/foundation-games-live.spec.ts --project chromium-desktop --workers=1` passed: 11 broader live standalone flows.
- `cd frontend && PREPROD_UX_AUDIT=1 PLAYWRIGHT_BASE_URL=https://gamesapi-gamma.revelryapp.me npm run test:e2e:preprod-ux` passed and produced representative mobile screenshots for catalog, Bluff host, and Chit Pull host states.
- With a freshly minted short-lived gamma party-games URL, `cd frontend && PREPROD_REVELRY=1 REVELRY_GAMMA_PARTY_GAMES_URL_FILE=../gamma_party_games_url.txt npm run test:e2e:preprod-revelry` passed: sorted/searchable embedded catalog plus host/player/watch launch-token routes for every launchable Revelry game. The harness now explicitly checks the embedded `Most Popular` and `Cards` filters.

The Revelry preprod harness requires a fresh gamma party-games URL. Expired `gamma_party_games_url.txt` tokens fail with `401 Invalid or expired party games token`; mint a new token using the Revelry repo helper documented below, and never print or commit the token.

### Recent gamma deploy — June 24, 2026 (Generic Prompt Party engine)

Deployed commit `44d38ad` via `./scripts/deploy-gcp.sh --gamma --with-frontend` to `games-backend-gamma` (prod `games-backend` untouched). Ships the shared Generic Prompt Party runtime plus ten standalone games: `hot_takes`, `this_or_that`, `caption_contest`, `pitch_battle`, `roast_toast`, `desert_island`, `memory_lane`, `rapid_fire`, `one_word_vibes`, and `emoji_story`. Verified live after deploy: `/health` returned healthy, `/catalog` contains all ten game ids with `content_schema.kind=generic_prompt_party_v1`, and `npm run test:e2e:gamma` passed on desktop and mobile. No Supabase schema migration is required. Revelry/host-app exposure remains disabled because these entries are standalone-only until a bridge/policy pass is completed.

### Recent gamma deploy — June 12, 2026 (Revelry integration hardening)

Deployed via `./scripts/deploy-gcp.sh --gamma --with-frontend` to `games-backend-gamma` (prod `games-backend` untouched). Ships the June 12 integration hardening in `SPEC-REVELRY-INTEGRATION.md`: session-create/party-games-link `game_type` validators accept all Revelry host-app start types, handoff JWTs require `iss=revelry`+`aud=localplay`+`typ=localplay_launch`, and return-url default-port normalization. Verified live: `POST https://gamesapi-gamma.revelryapp.me/integrations/revelry/sessions` with `game_type=drawing` passes validation (→ 401 without credentials) and `game_type=bogus` → 422 listing all five types. Not yet redeployed to prod — run `./scripts/deploy-gcp.sh --with-frontend` after a reviewed prod cutover.

### Recent gamma deploy — June 24, 2026 (expanded Revelry quick-start catalog)

Deployed commit `e00a3ef` via `./scripts/deploy-gcp.sh --gamma --with-frontend` to `games-backend-gamma` (prod `games-backend` untouched). Ships LocalPlay bridge support for Revelry quick-start/settings launches of `would_you_rather`, `never_have_i_ever`, `word_association`, `acronym`, `photo_clue`, and `poker`, plus updated specs and Revelry preprod matrix expectations. Verified live after deploy: `/health` returned healthy, `/catalog?host_app=revelry` returned the expanded game set, and an unauthenticated `POST /integrations/revelry/sessions` with `game_type=photo_clue` returned `401 Missing integration credential` rather than a validator rejection.

### Recent gamma deploy — June 24, 2026 (Survey Says standalone MVP)

Deployed commit `119ff65` via `./scripts/deploy-gcp.sh --gamma --with-frontend` to `games-backend-gamma` (prod `games-backend` untouched). Ships standalone `survey_says` with default curated rounds, automatic two-team assignment, player guesses, host answer-board adjudication, strikes, steal flow, late joins, spectator sync, rules metadata, and podium. Verified live after deploy: `/health` returned healthy, `/catalog` includes `survey_says`, and `npm run test:e2e:gamma` passed against `https://gamesapi-gamma.revelryapp.me` on desktop and mobile.

Follow-up verification on June 24:

- `npm run test:e2e:gamma` passed against `https://gamesapi-gamma.revelryapp.me` on desktop and mobile.
- `python3 scripts/smoke-remote.py --base-url https://gamesapi-gamma.revelryapp.me --skip-generate` passed.
- `PREPROD_REVELRY=1 REVELRY_GAMMA_PARTY_GAMES_URL_FILE=../gamma_party_games_url.txt npm run test:e2e:preprod-revelry` passed after adding the Random Chit saved-content fixture to the matrix.

Production is intentionally not updated by this gamma deploy. As of the same check, `https://gamesapi.revelryapp.me/catalog?host_app=revelry` exposed only `quiz`, `wmlt`, `drawing`, and `musical_chairs`, and `POST /integrations/revelry/sessions` with `game_type=photo_clue` returned a validator `422`. A prod rollout therefore requires deploying current `master` to production before enabling policy rows for the new game types.

Production rollout notes for the six new quick-start/settings candidates:

- No Supabase schema migration is required for `would_you_rather`, `never_have_i_ever`, `word_association`, `acronym`, `photo_clue`, or `poker` because the Revelry bridge starts them without saved `generated_content`.
- Add production `host_app_catalog_flags` rows only after prod deploy and smoke. Use `status=live`, `enabled=true`, and leave `can_create_content=false` as advertised by the static catalog.
- Photo Clue policy may expose `supports_images=true`, but Revelry should not mirror raw uploaded photos unless LocalPlay returns an explicit safe share payload.
- Party Poker must stay no-money/no-rewards: no buy-ins, cash-out, sparks, prizes, or economy-linked copy.
- Random Chit can be enabled in production as quick-start-only before the prod DDL by overriding `can_create_content=false`, `can_edit_content=false`, and `supports_ai_generation=false`. Do not enable Random Chit saved-content/AI authoring in prod until the `generated_content.content_type` CHECK migration is applied.

### Pending LocalPlay DB/content migration — June 24, 2026

Random Chit host-app authoring adds `chit_pull` as a saved `generated_content.content_type`. The local SQLite initializer/migration and rendered Supabase SQL expand the CHECK constraint to `('quiz', 'mlt', 'drawing', 'housie', 'chit_pull')`. Gamma Supabase DDL was applied on June 24, 2026 and verified with `games_gamma_generated_content_content_type_check`. Production SQL is updated in-repo but not applied; do not enable Random Chit `can_create_content` / `supports_ai_generation` production policy rows until the production DDL is explicitly applied.

Would You Rather, Never Have I Ever, Word Association, Acronym Game, Photo Clue, and Party Poker are Revelry quick-start/settings candidates only. They do not save `generated_content` rows through the host-app bridge and do not require a schema migration before host-app catalog policy enablement. Keep them policy-gated until embedded gamma QA covers start, join, spectator, reconnect, completion, and result polling. Photo Clue should not mirror raw uploaded photos into Revelry unless LocalPlay returns an explicit safe share payload. Party Poker must remain no-money/no-rewards.

### Party Quests staged-authoring gamma rollout — July 9, 2026

The LocalPlay implementation supports party-scoped saved/AI Party Quests, deterministic Host/Player/TV preview, exact saved-content materialization, first-player check-in auto-start, and idempotent host cancellation.

Gamma rollout status:

- Applied the targeted `games_gamma_generated_content_content_type_check` migration so `party_quests` is accepted. A uniquely identified row was inserted, read, and deleted successfully; no smoke content remains.
- Deployed backend and backend-served frontend commits `33c4ea48` and `a9d2e5fb` to `games-backend-gamma`; the standard container health check passed.
- Enabled explicit gamma policy overrides for `can_create_content`, `can_edit_content`, `supports_ai_generation`, and `embedded_authoring_supported` while retaining `can_quick_start=true`.
- Intentionally left `requires_prepared_content_for_checkin=false` until the matching Revelry gamma implementation is deployed. Existing check-in quick-start remains backward compatible during this interval.
- Verified the live catalog, desktop setup/edit/save flow, Host/Player/TV sample preview, and a 390x844 mobile preview with no horizontal overflow. The temporary saved setup was deleted after the test.
- `npm run test:e2e:gamma` passed on desktop and mobile (`2 passed`). The full pre-deploy suites were `1003` backend tests and `285` frontend tests, with the final focused additions also passing.
- Docker Desktop's registry bridge stalled while resolving `python:3.12-slim`; the same official image was pulled and the exact prepared context was built on the deployment VM, after which the normal `--skip-build` backup/restart/health path completed. This was a local build-path issue, not a gamma service failure.
- Revelry's staged-flow harness then exposed a direct-link routing gap: `POST /integrations/revelry/content/authoring-link` accepted `game_type=party_quests` but `/revelry/author` still rendered the quiz chooser. Commit `c545e2d4` now dispatches the resolved authoring token by game type, loads/type-checks generic Party Quests content for edit, and returns the Party Quests setup UI; it is deployed to gamma. A live service-minted authoring URL showed one **Party Quests** heading, no **Create a quiz** heading, editable starter quests, AI generation, and no 390px horizontal overflow. Post-deploy `npm run test:e2e:gamma` passed desktop/mobile (`2 passed`); pre-deploy suites were backend `1005`, frontend `289`, and a clean production build.

Production remains unchanged: the production generated-content constraint and production Party Quests capability row have not been promoted.

Remaining cross-app rollout sequence:

1. Deploy Revelry's matching gamma implementation so it can persist the ready party-scoped `localplay_content_id`, arm the game, and send that id on first check-in.
2. Run the cross-app configure, save-pointer, return, arm, first-check-in auto-start, late-join, cancel, and callback-reconciliation tests while strict enforcement remains off.
3. ~~Set gamma `requires_prepared_content_for_checkin=true`~~ **DONE 2026-07-09.** After Revelry confirmed gamma ready (setup opens, save returns a party-scoped `localplay_content_id`, preview opens Host/Player/TV, no duplicate cards), flipped the gamma `party_quests` policy row via a surgical jsonb merge (`capability_overrides || '{"requires_prepared_content_for_checkin": true}'`) — only that key changed; the four authoring overrides (`can_create_content`, `can_edit_content`, `supports_ai_generation`, `embedded_authoring_supported`) preserved. Pre-flip: LocalPlay tests green (backend `test_revelry_integration`/`test_party_quests_socket`/`test_host_app_catalog_policy` = 59; frontend authoring/preview/hostAppMode/LobbyScreen/PartyQuestsGame = 35). Verified live: gamma `/catalog?host_app=revelry` now returns `party_quests` with `requires_prepared_content_for_checkin=true` (60s cache); **prod unchanged** (`None`). Revelry runs the strict cross-app acceptance flow next.
4. Repeat the database migration, policy rollout, tests, and strict-enforcement gate explicitly for production; do not infer production readiness from the gamma migration.

The capability evaluator treats those five new Party Quests capabilities as explicit policy opt-ins. Existing July 8 quick-start rows with empty/older overrides stayed quick-start-only after the code deploy; deploying code alone did not enable saved authoring or strict check-in. On 2026-07-14, production Party Quests was explicitly opted in through the production policy row after the production `generated_content` constraint was expanded and smoke-verified.

## IONOS Directory Structure

```
~/revelryapp/
  site/          → revelryapp.me (marketing website)
  app/           → app.revelryapp.me (platform frontend, future)
  games/         → games.revelryapp.me (public LocalPlay game surface)
    quiz/        → legacy LocalPlay static build, kept only for old links/PWAs
  media/         → media.revelryapp.me
    apps/
      localplay/ → LocalPlay uploaded/generated game images
        music/   → hosted Musical Chairs loop files
```

## Credentials & Access

| Service | Access |
|---------|--------|
| IONOS SSH | `ssh u69414981@home420463025.1and1-data.host` (key: `~/.ssh/id_ed25519`) |
| GCP SSH | `gcloud compute ssh revelry-backend --project=revelryapp --zone=us-central1-a` |
| GCP VM IP | `136.115.33.75` |
| GCP Project | `revelryapp` |
| GCP Zone | `us-central1-a` |
| GCP Instance | `revelry-backend` |
| Supabase Project | `hosbtyylacluziugwjfd` (`LearningCompanion`, shared with VibePix) |

---

## From-Scratch Setup

Use this section when rebuilding the VM setup or adding LocalPlay to a fresh host. These steps assume the GCP VM exists and you can SSH into it with `gcloud compute ssh`.

### 1. DNS

In IONOS DNS for `revelryapp.me`, create or verify:

| Host | Type | Value |
|------|------|-------|
| `gamesapi` | `A` | `136.115.33.75` |
| `gamesapi-gamma` | `A` | `136.115.33.75` |

Verify from local:

```bash
nslookup gamesapi.revelryapp.me
nslookup gamesapi-gamma.revelryapp.me
```

### 2. Install VM packages

On a fresh Debian/Ubuntu VM:

```bash
gcloud compute ssh revelry-backend --project=revelryapp --zone=us-central1-a

sudo apt-get update
sudo apt-get install -y docker.io nginx certbot python3-certbot-nginx sqlite3
sudo systemctl enable --now docker
sudo systemctl enable --now nginx
sudo usermod -aG docker "$USER"
exit
```

Open a new SSH session after adding the user to the `docker` group.

### 3. Bootstrap the LocalPlay VM home

The canonical LocalPlay home on the VM is `/home/revelry-games`.

```bash
./scripts/deploy-gcp.sh --bootstrap-vm --skip-build
```

This creates:

```text
/home/revelry-games/
  app/
    .env
    .env.gamma
  revelry-data/
  revelry-backups/
  revelry-data-gamma/
  revelry-backups-gamma/
```

If `/home/revelry-games/app/.env` does not exist, the bootstrap script copies `/home/Avi/app/.env` when available. Otherwise create `/home/revelry-games/app/.env` manually before deploying.

The gamma env is copied from production and then adjusted by bootstrap:

```env
ALLOWED_ORIGINS=https://gamesapi-gamma.revelryapp.me,http://localhost:9200,http://127.0.0.1:9200
DB_DIR=/app/data
JWT_SECRET=<generated by bootstrap if missing>
DB_BACKEND=supabase
TABLE_PREFIX=games_gamma_
SUPABASE_URL=https://hosbtyylacluziugwjfd.supabase.co
SUPABASE_SERVICE_KEY=<service-role-key>
CHECKOUT_RETURN_URL=https://gamesapi-gamma.revelryapp.me/
TRUST_PROXY_HEADERS=true
GEMINI_MODEL=gemini-2.5-flash-lite
GEMINI_PREMIUM_MODEL=gemini-2.5-flash-lite
REMOTE_CONFIG_URL=https://gamesapi-gamma.revelryapp.me/config.json
GOOGLE_CLIENT_ID=458966837298-9hjencou1ag2o17ln06iuuj86j5p8igj.apps.googleusercontent.com
GOOGLE_CLIENT_IDS=458966837298-9hjencou1ag2o17ln06iuuj86j5p8igj.apps.googleusercontent.com,458966837298-ncc86ha91tct2lo9ah16g8v9ibp4ckki.apps.googleusercontent.com
APPLE_CLIENT_ID=me.revelryapp.quiz.web
APPLE_CLIENT_IDS=me.revelryapp.quiz.web,me.revelryapp.quiz
PUBLIC_BASE_URL=https://gamesapi-gamma.revelryapp.me
REVELRY_INTEGRATION_SECRET=<strong gamma shared secret matching Revelry gamma>
REVELRY_LAUNCH_TOKEN_TTL_SECONDS=600
REVELRY_AUTHORING_TOKEN_TTL_SECONDS=3600
REVELRY_PARTY_HUB_RETURN_TOKEN_TTL_SECONDS=14400
REVELRY_SESSION_LOBBY_TTL_SECONDS=14400
REVELRY_SESSION_IDLE_TTL_SECONDS=7200
REVELRY_CALLBACK_URL=https://api-gamma.revelryapp.me/api/games/localplay/callback
# Keep unset unless doing a deliberate callback-secret rotation/compatibility window.
REVELRY_CALLBACK_SECRET=
```

**Important:** The bootstrap copies production Stripe keys into gamma. You must manually replace them with test-mode keys (`sk_test_...`, `whsec_...`) in `/home/revelry-games/app/.env.gamma` before testing checkout, or you will charge real money.

Production `.env` should also include `gamesapi.revelryapp.me` in `ALLOWED_ORIGINS` for backend-served SPA access:

```env
ALLOWED_ORIGINS=https://games.revelryapp.me,https://gamesapi.revelryapp.me,capacitor://localhost,http://localhost,https://localhost,http://localhost:9200,http://127.0.0.1:9200
TRUST_PROXY_HEADERS=true
JWT_SECRET=<generated by bootstrap if missing>
DB_BACKEND=supabase
TABLE_PREFIX=games_
SUPABASE_URL=https://hosbtyylacluziugwjfd.supabase.co
SUPABASE_SERVICE_KEY=<service-role-key>
GOOGLE_CLIENT_ID=458966837298-9hjencou1ag2o17ln06iuuj86j5p8igj.apps.googleusercontent.com
GOOGLE_CLIENT_IDS=458966837298-9hjencou1ag2o17ln06iuuj86j5p8igj.apps.googleusercontent.com,458966837298-ncc86ha91tct2lo9ah16g8v9ibp4ckki.apps.googleusercontent.com
APPLE_CLIENT_ID=me.revelryapp.quiz.web
APPLE_CLIENT_IDS=me.revelryapp.quiz.web,me.revelryapp.quiz
PUBLIC_BASE_URL=https://gamesapi.revelryapp.me
REVELRY_INTEGRATION_SECRET=<strong prod shared secret matching Revelry prod>
REVELRY_LAUNCH_TOKEN_TTL_SECONDS=600
REVELRY_AUTHORING_TOKEN_TTL_SECONDS=3600
REVELRY_PARTY_HUB_RETURN_TOKEN_TTL_SECONDS=14400
REVELRY_SESSION_LOBBY_TTL_SECONDS=14400
REVELRY_SESSION_IDLE_TTL_SECONDS=7200
REVELRY_CALLBACK_URL=https://api.revelryapp.me/api/games/localplay/callback
# Keep unset unless doing a deliberate callback-secret rotation/compatibility window.
REVELRY_CALLBACK_SECRET=
```

Origins are scheme + host + optional port only; do not include `/quiz/` or other paths. Installed PWAs still use the web origin they were installed from, while Capacitor/native shells and local development need their own localhost-style origins.

`JWT_SECRET` is required for successful Google/Apple sign-in. Google or Apple may return a valid ID token, but the backend cannot finish login unless it can mint the app's own session JWT.

### 3a. Configure Google and Apple web sign-in origins

Google and Apple must trust every browser origin that can host the SPA. This includes the IONOS customer URL and the backend-served prod/gamma URLs. Otherwise the browser sign-in popup can fail before the backend receives a token.

Google Cloud Console: <https://console.cloud.google.com/apis/credentials>

Open the Web OAuth client whose client ID matches `VITE_GOOGLE_CLIENT_ID`, then add these **Authorized JavaScript origins**:

```text
https://games.revelryapp.me
https://gamesapi.revelryapp.me
https://gamesapi-gamma.revelryapp.me
http://localhost:5173
http://localhost:9200
http://127.0.0.1:9200
```

The current Google Identity Services popup flow primarily needs JavaScript origins, not redirect URIs. If redirect URIs are configured on the same client, keep the Firebase handler and add the same web roots for compatibility:

```text
https://revelryapp.firebaseapp.com/__/auth/handler
https://games.revelryapp.me
https://gamesapi.revelryapp.me
https://gamesapi-gamma.revelryapp.me
http://localhost:5173
http://localhost:9200
http://127.0.0.1:9200
```

Do not include `/quiz/` in Google OAuth origins or redirect roots.

Apple Developer: <https://developer.apple.com/account/resources/identifiers/list>

Open the web Sign in with Apple Service ID `me.revelryapp.quiz.web`, enable Sign in with Apple, and configure these domains:

```text
games.revelryapp.me
gamesapi.revelryapp.me
gamesapi-gamma.revelryapp.me
```

Configure these return URLs:

```text
https://games.revelryapp.me
https://gamesapi.revelryapp.me
https://gamesapi-gamma.revelryapp.me
```

Backend-served builds intentionally set `VITE_APPLE_REDIRECT_URI` to blank, so Apple JS falls back to `window.location.origin`. The IONOS build can keep `VITE_APPLE_REDIRECT_URI=https://games.revelryapp.me`.

### 3b. Verify sign-in state

Browser sign-in is not Firebase Auth. The app uses Google Identity Services and Apple Sign-In directly, sends the provider ID token to `/auth/signin`, and the backend creates a LocalPlay session JWT.

Expected successful login state:

- The menu shows **Signed in**.
- The account/email prefix is visible.
- The **Sign Out** button is visible.
- The browser has a LocalPlay session token for the current origin.

Startup session revalidation uses `/auth/me`. `401/403` clears the LocalPlay session, but network timeouts and
temporary server failures are treated as transient so a slow phone network does not silently sign users out.

Verified browser sign-in coverage:

| Origin | Google | Apple |
|--------|--------|-------|
| `https://gamesapi-gamma.revelryapp.me` | Verified | Verified |
| `https://games.revelryapp.me/` | Configured; expected to work with the same web client | Verified |

The LocalPlay session is separate from the main Revelry app. It may share Google Cloud/Firebase project infrastructure, but it does not share the main Revelry app's login cookie or session.

Common sign-in failures:

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Google `origin_mismatch` before the app receives a token | Missing OAuth JavaScript origin | Add the exact SPA origin in Google Cloud Console |
| Account chooser appears, then app says invalid/expired token | Backend cannot complete LocalPlay session creation or token `aud` is not allowed | Verify `JWT_SECRET`, `GOOGLE_CLIENT_IDS`, `APPLE_CLIENT_IDS`, and container runtime env |
| Apple popup fails or returns invalid token | Apple Service ID domains/return URLs or audience mismatch | Verify Apple Developer Service ID and `APPLE_CLIENT_IDS` |
| Login works on `games.revelryapp.me` but not `gamesapi-gamma.revelryapp.me` | Provider console only trusts the IONOS origin | Add backend-served prod/gamma origins |
| User appears signed out after app launch on a weak network | `/auth/me` revalidation was slow or unavailable | Keep the cached session; retry on better network and inspect `/auth/me` logs before clearing local storage |
| Signed-in user has 0 sparks | New user wallet or wallet merge did not transfer guest balance | Check wallet merge logs and `/tokens/balance` under the signed-in session |

Runtime checks:

```bash
gcloud compute ssh revelry-backend --project=revelryapp --zone=us-central1-a --command \
  'for c in games-backend games-backend-gamma; do echo "== $c =="; docker exec "$c" sh -lc '"'"'printf "JWT_SECRET=%s\n" "${JWT_SECRET:+set}"; printf "GOOGLE_CLIENT_ID=%s\n" "${GOOGLE_CLIENT_ID:+set}"; printf "GOOGLE_CLIENT_IDS=%s\n" "${GOOGLE_CLIENT_IDS:+set}"; printf "APPLE_CLIENT_ID=%s\n" "${APPLE_CLIENT_ID:+set}"; printf "APPLE_CLIENT_IDS=%s\n" "${APPLE_CLIENT_IDS:+set}"'"'"'; done'
```

### 3c. Native In-App Purchase (RevenueCat) — pending console setup

Native IAP sells the unified spark ladder (50/200/500). The backend (`POST /webhook/revenuecat`) and the
web/frontend are implemented; the native plugin install + console setup remain. Full plan: **`SPEC-IAP.md`**
(§7 console setup, §8 env, §9 testing).

The native client plugin is installed (`@revenuecat/purchases-capacitor@^12.3.2`, Capacitor 8 / SPM — no
CocoaPods). Build + sync a native target with the codified scripts (mirrors VibePix's `cap:gamma`/`cap:prod`):

```bash
cd frontend
npm run cap:sync:gamma   # vite build (gamma API + baked RC keys) → npx cap sync
npx cap open ios         # Xcode → signing team → Run on a REAL device (sandbox IAP needs a device)
# prod build: npm run cap:sync:prod
```

`scripts/cap-build.mjs` injects per-env `VITE_API_URL`/`VITE_WEB_URL` plus the publishable
`VITE_REVENUECAT_IOS_KEY`/`_ANDROID_KEY` (same RevenueCat project for gamma + prod). Gamma's
`ALLOWED_ORIGINS` includes `capacitor://localhost,http://localhost,https://localhost` so the native
WebView can call the API.

Backend env (GCP `.env`/`.env.gamma`, distinct per env, never printed/committed):

| Var | Notes |
|-----|-------|
| `REVENUECAT_WEBHOOK_SECRET` | Bearer secret for `POST /webhook/revenuecat` |
| `STRIPE_SECRET_KEY` | enables web checkout (test on gamma, live on prod) |
| `STRIPE_WEBHOOK_SECRET` | from the per-env Stripe webhook endpoint |

Web Stripe uses inline `price_data` from the catalog — **no Stripe Product/Price objects or per-tier price
env vars**. The only Stripe console step is registering one webhook endpoint per env
(`https://gamesapi-gamma.revelryapp.me/webhook/stripe`, `https://gamesapi.revelryapp.me/webhook/stripe`,
events `checkout.session.completed`, `charge.refunded`, `charge.dispute.created`).

Native build env (Vite, native builds only — publishable keys, safe to bake in):

```
VITE_REVENUECAT_IOS_KEY=appl_xxx
VITE_REVENUECAT_ANDROID_KEY=goog_xxx
```

RevenueCat webhook URLs to register (Authorization: `Bearer <REVENUECAT_WEBHOOK_SECRET>`):
- Gamma: `https://gamesapi-gamma.revelryapp.me/webhook/revenuecat`
- Prod: `https://gamesapi.revelryapp.me/webhook/revenuecat`

Console steps (full detail in `SPEC-IAP.md §7`): RevenueCat app for `me.revelryapp.quiz` (Apple In-App Purchase
.p8 + reuse the `revenuecat-play@revelryapp.iam` service account; enable `androidpublisher.googleapis.com`),
products `rc_spark_pack_50/200/500` → store products `me.revelryapp.quiz.sparks_50/200/500`; create the matching
consumable IAPs in App Store Connect + Play Console. (Web Stripe needs no products — inline `price_data`.)

**Android product-creation gotcha:** Play won't let you create one-time products until an uploaded build
declares the `com.android.vending.BILLING` permission (the Play Billing lib RevenueCat pulls in adds it
automatically). So the Android order is **build a signed AAB → upload to internal testing → then create the
3 products** (the inverse of iOS). (versionCode must exceed the track's; currently 5.)

**Android status (DONE 2026-07-06):** products created, published, and mapped in RevenueCat. What was done
(kept here as the runbook for future builds / re-signing):

- **Signing / upload key:** the original `revelry-quiz-upload.keystore` password was lost and is
  unrecoverable. A **new upload keystore** was generated — `~/keystores/revelry-quiz-upload-v2.keystore`
  (alias `revelry-quiz`; password in `~/Desktop/dev/antigravity/backupenv/quiz/local/keystore.properties` (dev-root backupenv, NOT the repo-local `backupenv/`)); `app/build.gradle` defaults
  to it. Since the app uses **Play App Signing**, this only needed an **upload-key reset** (Play Console →
  Test and release → Setup → App signing → Request upload key reset → upload
  `~/keystores/revelry-quiz-upload-v2.pem`) — no impact to app identity or other apps. **Approved.**
- **Build/upload (repeat for future releases):**
  ```bash
  cd frontend && npm run cap:sync:gamma
  cd android
  KEYSTORE_PASSWORD='<see ~/Desktop/dev/antigravity/backupenv/quiz/local/keystore.properties>' \
  KEY_PASSWORD='<same>' ./gradlew bundleRelease   # → app/build/outputs/bundle/release/app-release.aab
  ```
  AAB **v5 (3.1.0)** uploaded to **internal testing** (bump `versionCode` for each new upload).
- **Play products:** 3 one-time products `me.revelryapp.quiz.sparks_50/200/500` created + **Active**
  ($1.99/$4.99/$9.99), then imported into RevenueCat and mapped into the `default` offering (each package
  serves both the App Store and Play products).
- **Play credential in RevenueCat:** the `revenuecat-play@revelryapp.iam` service account needed the full
  Play permission set to validate — see `backupenv/quiz/local/iap-setup.md` for the exact working set
  (financial + Manage orders **and** Manage store presence + Manage policy were required for green).
- **Remaining:** license-tester device install + a real purchase to confirm the live webhook credits sparks.

### 3d. Native sign-in (`@capgo/capacitor-social-login`)

LocalPlay does **not** use Firebase (unlike revelryapp). Web sign-in = Google Identity Services + Apple JS;
native sign-in = `@capgo/capacitor-social-login` → ID token → backend verifies (`auth.py`). The code is wired
(`utils/socialAuth.ts` `SocialLogin.initialize()`, called before `login()`; iOS Google reversed-client-id URL
scheme in `Info.plist`; iOS Apple Sign In entitlement in `App/App.entitlements`; `cap-build.mjs` bakes the public client ids). Remaining one-time console setup:

| Platform | Step |
|---|---|
| iOS | Sign in with Apple entitlement is tracked in `frontend/ios/App/App/App.entitlements` and wired through `CODE_SIGN_ENTITLEMENTS`; Google iOS client + URL scheme already configured. |
| Android | Create a **GCP OAuth client** (project `revelryapp`, type Android): package `me.revelryapp.quiz` + the **Play App Signing** SHA-1 (Play Console → Test and release → Setup → App integrity). Also add the **upload** key SHA-1 for direct/sideload installs: `keytool -list -v -keystore ~/keystores/revelry-quiz-upload.keystore -alias revelry-quiz | grep SHA`. The **Play App Signing** SHA-1 is the one Play-installed builds use — register that as the primary. serverClientId = the web Google client (already baked); creating the Android OAuth client needs no code change. |

Backend verifies Google ID tokens against `GOOGLE_CLIENT_IDS` and Apple via JWKS (`APPLE_CLIENT_IDS`). Prod/gamma must include both Google web+iOS clients, and both Apple Service ID+native bundle id, so browser, Android, and iOS tokens are accepted.

### 4. Install nginx routes

Production should proxy to `127.0.0.1:8000`; gamma should proxy to `127.0.0.1:8004`.

Create `/etc/nginx/sites-available/revelry-gamesapi`:

```nginx
server {
    server_name gamesapi.revelryapp.me;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }

    listen 80;
}
```

Create `/etc/nginx/sites-available/revelry-gamesapi-gamma`:

```nginx
server {
    server_name gamesapi-gamma.revelryapp.me;

    location / {
        proxy_pass http://127.0.0.1:8004;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }

    listen 80;
}
```

Enable, test, reload, and issue certs:

```bash
sudo ln -sf /etc/nginx/sites-available/revelry-gamesapi /etc/nginx/sites-enabled/revelry-gamesapi
sudo ln -sf /etc/nginx/sites-available/revelry-gamesapi-gamma /etc/nginx/sites-enabled/revelry-gamesapi-gamma
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d gamesapi.revelryapp.me
sudo certbot --nginx -d gamesapi-gamma.revelryapp.me
sudo nginx -t
sudo systemctl reload nginx
```

### 5. Deploy both backend containers with bundled SPA

From the repo root:

```bash
./scripts/deploy-gcp.sh --with-frontend
./scripts/deploy-gcp.sh --gamma --with-frontend
```

The script builds the Docker images locally with `--platform linux/amd64`, uploads them to the VM, backs up SQLite, restarts only the target LocalPlay container, and checks `/health`.

### 6. Verify from outside the VM

```bash
curl -sS -i https://gamesapi.revelryapp.me/health
curl -sS -i https://gamesapi-gamma.revelryapp.me/health
curl -sS -D - -o /dev/null https://gamesapi.revelryapp.me/
curl -sS -D - -o /dev/null https://gamesapi-gamma.revelryapp.me/join/testroom
curl -sS -i https://gamesapi.revelryapp.me/providers
curl -sS -i https://gamesapi-gamma.revelryapp.me/providers
```

Expected:

- `/health` returns JSON `200`
- `/` and client routes like `/join/testroom` return `text/html`
- API routes like `/providers` return JSON, not `index.html`

### 7. Optional: deploy public IONOS frontend

The IONOS frontend remains the canonical public game surface:

```bash
cd frontend
VITE_BASE_PATH=/ VITE_API_URL=https://gamesapi.revelryapp.me VITE_WEB_URL=https://games.revelryapp.me/ VITE_CAST_APP_ID=1BC9ACD8 npx vite build
ssh u69414981@home420463025.1and1-data.host "mkdir -p ~/revelryapp/games"
scp -r dist/* u69414981@home420463025.1and1-data.host:~/revelryapp/games/
rsync -avz dist/.htaccess u69414981@home420463025.1and1-data.host:~/revelryapp/games/.htaccess
```

### 7a. Optional: deploy Musical Chairs hosted music

Built-in Musical Chairs streams short loop files from IONOS media storage so the web/native app bundle stays small. The canonical public base is:

```text
https://media.revelryapp.me/apps/localplay/music/
~/revelryapp/media/apps/localplay/music/
```

Generate the current 20 MVP loops locally:

```bash
node scripts/generate-musical-chairs-loops.mjs /private/tmp/localplay-musical-chairs-audio
```

Upload:

```bash
ssh u69414981@home420463025.1and1-data.host "mkdir -p ~/revelryapp/media/apps/localplay/music"
rsync -avz /private/tmp/localplay-musical-chairs-audio/ u69414981@home420463025.1and1-data.host:~/revelryapp/media/apps/localplay/music/
```

Verify one file:

```bash
curl -sSI https://media.revelryapp.me/apps/localplay/music/upbeat-confetti.wav
```

The frontend manifest lives in `frontend/src/audio/musicalChairsTracks.ts`. Set `VITE_MUSICAL_CHAIRS_MUSIC_BASE_URL` only if the media base changes; otherwise it defaults to the IONOS URL above.

---

## Frontend build contexts (three distinct var sets — do not conflate)

The frontend ships in three contexts with **slightly different `VITE_*` vars**. `API_URL = VITE_API_URL || ''`,
so an *empty* `VITE_API_URL` means **same-origin** — uploading a same-origin bundle to IONOS would route
`/quiz`,`/room`,`/tokens`,`/checkout` to IONOS static hosting and break the public site (this exact mistake
bit revelryapp). Each context has a codified build script so the vars can't drift:

| Context | Command | `VITE_API_URL` | base | `VITE_APPLE_REDIRECT_URI` | RevenueCat keys |
|---|---|---|---|---|---|
| **IONOS web** (`games.revelryapp.me`) | `npm run ionos:build` | `https://gamesapi.revelryapp.me` | `/` | `https://games.revelryapp.me` | — |
| **Backend-served** (gamma/prod container) | `./scripts/deploy-gcp.sh [--gamma] --with-frontend` | *empty (same-origin)* | `/` | blank | — |
| **Native gamma** | `npm run cap:sync:gamma` | `https://gamesapi-gamma.revelryapp.me` | `/` | blank | yes |
| **Native prod** | `npm run cap:sync:prod` | `https://gamesapi.revelryapp.me` | `/` | blank | yes |

`scripts/ionos-build.mjs` **hard-fails** unless the built bundle actually references `gamesapi.revelryapp.me`,
so a same-origin bundle can't be shipped to IONOS by accident. `scripts/cap-build.mjs` bakes the publishable
RevenueCat keys (same project for gamma+prod) into native builds.

## Frontend Deployment

### Prerequisites
- Node.js installed locally
- SSH key configured for IONOS

### Step 1: Build the frontend

```bash
cd frontend
npm run ionos:build   # builds + verifies the bundle points at gamesapi.revelryapp.me
```

This produces `frontend/dist/` with all static assets, verified safe to upload to IONOS.

### Step 2: Prepare the IONOS target directory

```bash
ssh u69414981@home420463025.1and1-data.host "mkdir -p ~/revelryapp/games"
```

Old JS/CSS bundles have hashed filenames that accumulate. Clean `~/revelryapp/games/assets` before deploying when you want to remove stale root bundles; keep `~/revelryapp/games/quiz` unless intentionally removing the legacy path.

### Step 3: Upload to IONOS

```bash
scp -r frontend/dist/* u69414981@home420463025.1and1-data.host:~/revelryapp/games/
rsync -avz frontend/dist/.htaccess u69414981@home420463025.1and1-data.host:~/revelryapp/games/.htaccess
```

### Step 4: Verify

Open https://games.revelryapp.me/ in a browser. Check the browser console for errors.

### SPA Routing

An `.htaccess` file at `~/revelryapp/games/.htaccess` handles client-side routing:

```apache
RewriteEngine On
RewriteBase /
RewriteCond %{REQUEST_FILENAME} !-f
RewriteCond %{REQUEST_FILENAME} !-d
RewriteRule ^ index.html [L]
```

The legacy `/quiz/` directory can remain for old links/PWAs, but new production builds should be uploaded at the root.

---

## Backend Deployment

### Prerequisites
- `gcloud` CLI installed and authenticated (`gcloud auth login`)
- Docker installed locally
- Docker installed on the VM
- Node.js installed locally when using `--with-frontend`
- `/home/revelry-games/app/.env` exists on the VM

### Preferred script deploy

The deployment script builds locally, copies the image to the VM, backs up SQLite, restarts the container, and verifies `/health`.
Images are built with `--platform linux/amd64` because the GCP VM is AMD64 even when the local build machine is Apple Silicon.

```bash
# One-time VM layout bootstrap
./scripts/deploy-gcp.sh --bootstrap-vm --skip-build

# Production API + backend-served SPA fallback
./scripts/deploy-gcp.sh --with-frontend

# Gamma full-stack same-origin environment
./scripts/deploy-gcp.sh --gamma --with-frontend

# Backend-only production deploy
./scripts/deploy-gcp.sh
```

Script container layout:

| Environment | Container | VM bind | Env file | Data dir |
|-------------|-----------|---------|----------|----------|
| Production | `games-backend` | `127.0.0.1:8000` | `/home/revelry-games/app/.env` | `/home/revelry-games/revelry-data` |
| Gamma | `games-backend-gamma` | `127.0.0.1:8004` | `/home/revelry-games/app/.env.gamma` | `/home/revelry-games/revelry-data-gamma` |

`--with-frontend` builds `frontend/dist` with same-origin API settings and packages it into the backend image at `/app/static`. If `/app/static/index.html` is absent, the backend still runs API-only.

`--bootstrap-vm` creates the canonical LocalPlay VM home at `/home/revelry-games`, migrates `/home/Avi/app/.env` into `/home/revelry-games/app/.env` if needed, creates `.env.gamma`, and creates prod/gamma data and backup directories.

Port notes:
- Production `gamesapi.revelryapp.me` uses `127.0.0.1:8000`.
- `127.0.0.1:8001` is already reserved by the existing `/pp/` proxy in `revelry-gamesapi`.
- `127.0.0.1:8003` is already used by the older `api-gamma.revelryapp.me` config.
- LocalPlay gamma therefore uses `127.0.0.1:8004`.

### Backend-served SPA behavior

When deployed with `--with-frontend`, the container includes the Vite build under `/app/static`.

Expected behavior:

- `GET /` returns `index.html`
- client routes like `/join/testroom` return `index.html`
- static files like `/assets/index-*.js` return the real asset
- missing assets under `/assets/*` return JSON `404`
- API routes stay API routes and never fall through to the SPA

Protected API prefixes include `/system`, `/providers`, `/quiz`, `/quiz-packs`, `/room`, `/ws`, `/mlt`, `/drawing`, `/history`, `/auth`, `/checkout`, `/webhook`, `/tokens`, `/entitlements`, `/purchases`, `/admin`, `/health`, `/sd`, `/catalog`, `/integrations`, `/media`, and `/config.json`.

The frontend service worker must mirror this rule for same-origin backend-served builds. It should not cache or fulfill API requests for `gamesapi.revelryapp.me`, `gamesapi-gamma.revelryapp.me`, local backend port `8000`, or any protected API prefix; those requests must always reach the backend. Service-worker updates should wait and surface the in-app **New version ready** prompt; do not restore automatic `skipWaiting()` unless the app also avoids mid-game reloads. Embedded Revelry/host-app iframe routes skip service-worker registration, and standalone registration must resolve `sw.js` from the app root rather than the current route path.

The fallback route resolves candidate files under `/app/static` and rejects paths outside that directory to avoid directory traversal.

### Verify

```bash
curl -sS -i https://gamesapi.revelryapp.me/health
curl -sS -i https://gamesapi-gamma.revelryapp.me/health
curl -sS -D - -o /dev/null https://gamesapi.revelryapp.me/
curl -sS -D - -o /dev/null https://gamesapi-gamma.revelryapp.me/
curl -sS -i https://gamesapi.revelryapp.me/providers
```

Check containers on the VM:

```bash
gcloud compute ssh revelry-backend --project=revelryapp --zone=us-central1-a --command \
  'docker ps -a --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"'
```

---

## Nginx Configuration

Nginx runs on the VM as a reverse proxy. Each subdomain has its own config file:

- `/etc/nginx/sites-available/revelry-gamesapi` — `gamesapi.revelryapp.me` (LocalPlay backend)
- `/etc/nginx/sites-available/revelry-gamesapi-gamma` — `gamesapi-gamma.revelryapp.me` (gamma backend + frontend)
- `/etc/nginx/sites-available/revelry-api` — `api.revelryapp.me` (legacy, kept for backward compat)

Key sections:
- Listens on 443 (HTTPS) with Let's Encrypt certs
- Proxies production requests to `http://127.0.0.1:8000`
- Proxies gamma requests to `http://127.0.0.1:8004`
- WebSocket upgrade headers for `/ws/` paths
- HTTP (port 80) redirects to HTTPS

Gamma should proxy to `http://127.0.0.1:8004`; production should proxy to `http://127.0.0.1:8000`.

### View current config
```bash
sudo cat /etc/nginx/sites-available/revelry-gamesapi
```

### After editing Nginx config
```bash
sudo nginx -t              # test config syntax
sudo systemctl reload nginx  # apply changes
```

### Gamma nginx setup

Create `/etc/nginx/sites-available/revelry-gamesapi-gamma`:

```nginx
server {
    server_name gamesapi-gamma.revelryapp.me;

    location / {
        proxy_pass http://127.0.0.1:8004;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }

    listen 80;
}
```

Enable and issue cert:

```bash
sudo ln -sf /etc/nginx/sites-available/revelry-gamesapi-gamma /etc/nginx/sites-enabled/revelry-gamesapi-gamma
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d gamesapi-gamma.revelryapp.me
sudo nginx -t
sudo systemctl reload nginx
```

### Gamma env setup

The canonical LocalPlay VM home is `/home/revelry-games`. Bootstrap it once:

```bash
./scripts/deploy-gcp.sh --bootstrap-vm --skip-build
```

This creates:

```text
/home/revelry-games/
  app/
    .env
    .env.gamma
  revelry-data/
  revelry-backups/
  revelry-data-gamma/
  revelry-backups-gamma/
```

If doing it manually instead, production env lives at `/home/revelry-games/app/.env`, and gamma should live beside it:

```bash
sudo cp /home/revelry-games/app/.env /home/revelry-games/app/.env.gamma
sudo mkdir -p /home/revelry-games/revelry-data-gamma /home/revelry-games/revelry-backups-gamma
```

Then edit `/home/revelry-games/app/.env.gamma`:

```env
ALLOWED_ORIGINS=https://gamesapi-gamma.revelryapp.me
DB_DIR=/app/data
```

Use test Stripe keys in gamma before testing checkout. If checkout is not being tested, live Stripe keys should still be avoided in gamma.

Deploy gamma:

```bash
./scripts/deploy-gcp.sh --gamma --with-frontend
```

Verify:

```bash
curl -s https://gamesapi-gamma.revelryapp.me/health
curl -s https://gamesapi-gamma.revelryapp.me/ | head -3
curl -sI https://gamesapi-gamma.revelryapp.me/assets/DO_REPLACE_WITH_BUILT_ASSET
```

---

## SSL Certificate

Managed by Certbot. Auto-renews via systemd timer.

### Check cert status
```bash
sudo certbot certificates
```

### Force renewal (if needed)
```bash
sudo certbot renew --force-renewal
sudo systemctl reload nginx
```

---

## Backend .env (Production)

The production `.env` lives at `/home/revelry-games/app/.env` on the VM and should have at minimum:

```env
# AI Providers — at least one must be configured
GEMINI_API_KEY=<your-key>
GEMINI_MODEL=gemini-2.5-flash-lite
GEMINI_PREMIUM_MODEL=gemini-2.5-flash-lite
DEFAULT_PROVIDER=gemini
REMOTE_CONFIG_URL=https://games.revelryapp.me/config.json

# Server
HOST=0.0.0.0
PORT=8000
ALLOWED_ORIGINS=https://revelryapp.me,https://www.revelryapp.me,https://games.revelryapp.me,https://gamesapi.revelryapp.me,capacitor://localhost,http://localhost,https://localhost,http://localhost:9200,http://127.0.0.1:9200
DB_DIR=/app/data
TRUST_PROXY_HEADERS=true

# Persistence
DB_BACKEND=supabase
TABLE_PREFIX=games_
SUPABASE_URL=https://hosbtyylacluziugwjfd.supabase.co
SUPABASE_SERVICE_KEY=<service-role-key>

# Game
ROOM_TTL_SECONDS=1800
ORGANIZER_RECONNECT_GRACE_SECONDS=600
LOG_LEVEL=INFO
```

Include `https://gamesapi.revelryapp.me` in production `ALLOWED_ORIGINS` when using the backend-served SPA fallback, and keep PWA/native/local development origins that the app can actually launch from:

```env
ALLOWED_ORIGINS=https://revelryapp.me,https://www.revelryapp.me,https://games.revelryapp.me,https://gamesapi.revelryapp.me,capacitor://localhost,http://localhost,https://localhost,http://localhost:9200,http://127.0.0.1:9200
```

Gamma env lives at `/home/revelry-games/app/.env.gamma`. Keep it separate from production because it has its own database volume and should use safe/test third-party credentials:

```env
ALLOWED_ORIGINS=https://gamesapi-gamma.revelryapp.me,http://localhost:9200,http://127.0.0.1:9200
DB_BACKEND=supabase
TABLE_PREFIX=games_gamma_
SUPABASE_URL=https://hosbtyylacluziugwjfd.supabase.co
SUPABASE_SERVICE_KEY=<service-role-key>
DB_DIR=/app/data
CHECKOUT_RETURN_URL=https://gamesapi-gamma.revelryapp.me/
TRUST_PROXY_HEADERS=true
GEMINI_MODEL=gemini-2.5-flash-lite
GEMINI_PREMIUM_MODEL=gemini-2.5-flash-lite
REMOTE_CONFIG_URL=https://gamesapi-gamma.revelryapp.me/config.json
ROOM_TTL_SECONDS=1800
ORGANIZER_RECONNECT_GRACE_SECONDS=600
```

AI model gotcha: `backend/config.py` defaults to `gemini-2.5-flash-lite`, but deployed env vars and remote `config.json` override code defaults. If generation fails with Gemini `404 Not Found`, check `GEMINI_MODEL`, `GEMINI_PREMIUM_MODEL`, `REMOTE_CONFIG_URL`, and `ai_models` in `frontend/public/config.json`. Free and premium generation should both use `gemini-2.5-flash-lite`.

Mobile room lifecycle gotcha: keep `ORGANIZER_RECONNECT_GRACE_SECONDS` comfortably longer than a normal phone lock/background interruption. The default is 600 seconds. Do not lower this to a few seconds; otherwise the organizer's phone sleeping can close the whole room before the host or players can reconnect.

Ollama and Stable Diffusion are NOT available on the production VM (no GPU).

---

## Supabase Connection Reference

### Project

| Field | Value |
|---|---|
| Project ref | `hosbtyylacluziugwjfd` |
| Project name | LearningCompanion (shared with VibePix) |
| Region | us-west-2 |
| REST URL | `https://hosbtyylacluziugwjfd.supabase.co` |
| Dashboard | `https://supabase.com/dashboard/project/hosbtyylacluziugwjfd` |

### How LocalPlay connects at runtime

The backend uses raw HTTP via `httpx` to the Supabase PostgREST API. No Supabase client SDK.

Implementation: `backend/supabase_db.py` → `SupabaseClient` class.

```
Every request:
  apikey: <SUPABASE_SERVICE_KEY>
  Authorization: Bearer <SUPABASE_SERVICE_KEY>
  Content-Type: application/json

CRUD via PostgREST:
  GET    {SUPABASE_URL}/rest/v1/{prefix}{table}?{filters}     # select
  POST   {SUPABASE_URL}/rest/v1/{prefix}{table}                # insert/upsert
  PATCH  {SUPABASE_URL}/rest/v1/{prefix}{table}?{filters}      # update
  DELETE {SUPABASE_URL}/rest/v1/{prefix}{table}?{filters}      # delete

Atomic operations via Postgres RPCs:
  POST   {SUPABASE_URL}/rest/v1/rpc/{prefix}{function}         # e.g. games_debit_tokens
```

PostgREST filter syntax: `eq.`, `is.null`, `not.is.null`, `in.()`, `gte.`, `lt.`, `lte.`, `ilike.`

### Backend env vars

```env
DB_BACKEND=supabase
TABLE_PREFIX=games_              # or games_gamma_ for gamma
SUPABASE_URL=https://hosbtyylacluziugwjfd.supabase.co
SUPABASE_SERVICE_KEY=<service-role-key>
SUPABASE_ANON_KEY=<anon-key>     # optional, not used at runtime
SUPABASE_TIMEOUT_SECONDS=10
LOBBY_RECONNECT_GRACE_SECONDS=5400
```

`LOBBY_RECONNECT_GRACE_SECONDS` preserves disconnected lobby seats for mobile party continuity. The default is 5400 seconds (90 minutes). Connected-player counts and start gates still count only live sockets; preserved offline seats are pruned before the game materializes.

### Table prefix isolation

| Environment | Table prefix | Example table | Example RPC |
|---|---|---|---|
| Production | `games_` | `games_wallets` | `games_debit_tokens` |
| Gamma | `games_gamma_` | `games_gamma_wallets` | `games_gamma_debit_tokens` |
| VibePix prod | `vp_` | `vp_photos` | — |
| VibePix gamma | `vp_gamma_` | `vp_gamma_photos` | — |

All apps share one Supabase project. Prefixes prevent collisions.

### LocalPlay tables (per prefix)

```
{prefix}users
{prefix}wallets
{prefix}token_transactions
{prefix}entitlements
{prefix}device_usage
{prefix}request_log
{prefix}pending_tokens
{prefix}webhook_events
{prefix}generated_content
{prefix}quiz_packs
{prefix}quiz_questions
{prefix}media_assets
{prefix}game_sessions
{prefix}localplay_callback_events
{prefix}game_history
{prefix}rejections
```

`{prefix}generated_content.content_type` must allow the game setup types enabled in that environment. Production currently requires `quiz`, `mlt`, and `drawing`. Gamma additionally allows `housie` for the Housie party-hub setup/save/start path. The schema template includes a constraint refresh for existing Supabase tables; apply the rendered environment-specific SQL before deploying a build that saves a new setup type from the Revelry Games hub.

### LocalPlay RPCs (per prefix)

```
{prefix}ensure_wallet
{prefix}debit_tokens
{prefix}credit_tokens
{prefix}credit_purchase
{prefix}merge_wallet
{prefix}grant_daily_bonus
{prefix}grant_ad_reward
{prefix}claim_device_usage
{prefix}claim_user_usage
{prefix}mark_webhook_processed
{prefix}admin_stats
```

### Code architecture

```
backend/db.py              # Facade — all call sites import from here
backend/supabase_db.py     # Supabase implementation (PostgREST via httpx)

db.py selects backend at import:
  if config.DB_BACKEND == "supabase":
      import supabase_db
      # overlay every function in _SUPABASE_EXPORTS via globals()
  else:
      # use SQLite (local dev default)

Call sites (main.py, tokens.py, auth.py) always: import db
They never import supabase_db directly.
```

### SQL schema files

```
sql/templates/games-schema.template.sql   # Source template (__PREFIX__ placeholder)
sql/games-schema.sql                      # Rendered prod (games_)
sql/games-gamma-schema.sql                # Rendered gamma (games_gamma_)
scripts/render-supabase-sql.py            # Regenerates both from template
```

Render after editing the template:

```bash
.venv/bin/python scripts/render-supabase-sql.py --prefix games_ --output sql/games-schema.sql
.venv/bin/python scripts/render-supabase-sql.py --prefix games_gamma_ --output sql/games-gamma-schema.sql
```

### Applying schema changes to Supabase

This is always a manual human step — never automated by deploy scripts or CI.

```bash
# Get auth token from macOS Keychain (same pattern as VibePix)
TOKEN=$(security find-generic-password -s "Supabase CLI" -w | sed 's/^go-keyring-base64://' | base64 -d)

# Apply gamma schema
body=$(jq -n --rawfile q sql/games-gamma-schema.sql '{query: $q}')
curl -sS -X POST "https://api.supabase.com/v1/projects/hosbtyylacluziugwjfd/database/query" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$body"

# Apply prod schema
body=$(jq -n --rawfile q sql/games-schema.sql '{query: $q}')
curl -sS -X POST "https://api.supabase.com/v1/projects/hosbtyylacluziugwjfd/database/query" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$body"
```

HTTP 201 with `[]` means success. Any error returns a JSON object with details.

If an IDE agent cannot read the Keychain item, use an explicit Supabase personal access token in that same shell:

```bash
export SUPABASE_ACCESS_TOKEN="sbp_..."
TOKEN="${SUPABASE_ACCESS_TOKEN}"
supabase projects list
```

The expected project is `hosbtyylacluziugwjfd`. This fixes the restart/session case where `security find-generic-password -s "Supabase CLI" -w` returns "item could not be found" for one agent even though another local agent can read it. The app runtime service-role key is not enough for schema DDL; it only covers PostgREST/RPC runtime access.

### Verifying applied objects

List all LocalPlay tables:

```bash
QUERY="SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE 'games_%' ORDER BY tablename;"
body=$(jq -n --arg q "$QUERY" '{query: $q}')
curl -sS -X POST "https://api.supabase.com/v1/projects/hosbtyylacluziugwjfd/database/query" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$body"
```

List all LocalPlay RPCs:

```bash
QUERY="SELECT proname FROM pg_proc WHERE proname LIKE 'games_%' ORDER BY proname;"
body=$(jq -n --arg q "$QUERY" '{query: $q}')
curl -sS -X POST "https://api.supabase.com/v1/projects/hosbtyylacluziugwjfd/database/query" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$body"
```

Test PostgREST access to a table (uses the service-role key from backend .env):

```bash
curl -sS "https://hosbtyylacluziugwjfd.supabase.co/rest/v1/games_gamma_wallets?select=id&limit=1" \
  -H "apikey: <service-role-key>" \
  -H "Authorization: Bearer <service-role-key>"
```

### Ad-hoc queries via Management API

Run any SQL (read or write) through the Management API:

```bash
TOKEN=$(security find-generic-password -s "Supabase CLI" -w | sed 's/^go-keyring-base64://' | base64 -d)

QUERY="SELECT COUNT(*) as cnt FROM games_wallets;"
body=$(jq -n --arg q "$QUERY" '{query: $q}')
curl -sS -X POST "https://api.supabase.com/v1/projects/hosbtyylacluziugwjfd/database/query" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$body"
```

### When adding new tables or RPCs

1. Edit `sql/templates/games-schema.template.sql` using `__PREFIX__` for all names
2. Run `scripts/render-supabase-sql.py` to regenerate both prod and gamma SQL
3. Add corresponding functions in `backend/supabase_db.py`
4. Add function names to `_SUPABASE_EXPORTS` list in `backend/db.py`
5. Commit the SQL + Python changes
6. **Human manually** applies the SQL to Supabase (gamma first, then prod after testing)

---

## Database Migration Status

Production and gamma currently use Supabase:

| Environment | Active backend | Active data |
|-------------|----------------|-------------|
| Production | `DB_BACKEND=supabase` | Supabase `games_*` tables |
| Gamma | `DB_BACKEND=supabase` | Supabase `games_gamma_*` tables |

Supabase migration planning and SQL scaffolding live in `SPEC-SUPABASE-MIGRATION.md` and `sql/`.

As of 2026-05-19, the LocalPlay Supabase schema has been applied to the shared VibePix/LearningCompanion Supabase project:

- Project ref: `hosbtyylacluziugwjfd`.
- Production tables/RPCs: `games_*`.
- Gamma tables/RPCs: `games_gamma_*`.
- Gamma runtime was switched and smoke-tested against Supabase on 2026-05-19.
- Production SQLite was exported into `games_*` and production was switched to Supabase on 2026-05-19 PDT.
- Production cutover source counts matched Supabase target counts: `2` users, `7` wallets, `17` token transactions, `158` total sparks.
- Production smoke after cutover verified `/health`, `/providers`, `/config.json`, live quiz generation, Supabase wallet/request-log writes, and retry idempotency. Current runtime behavior preflight-checks generation balance and records `spend_generate` only when generated content is accepted into a playable room or reset.

The Supabase project is shared with VibePix, so LocalPlay tables and RPCs must always use explicit prefixes:

| Environment | Prefix |
|-------------|--------|
| Production | `games_` |
| Gamma | `games_gamma_` |

Render SQL locally only:

```bash
.venv/bin/python scripts/render-supabase-sql.py --prefix games_ --output sql/games-schema.sql
.venv/bin/python scripts/render-supabase-sql.py --prefix games_gamma_ --output sql/games-gamma-schema.sql
```

Apply SQL using the same Management API pattern as VibePix:

```bash
TOKEN=$(security find-generic-password -s "Supabase CLI" -w | sed 's/^go-keyring-base64://' | base64 -d)

body=$(jq -n --rawfile q sql/games-gamma-schema.sql '{query: $q}')
curl -sS -X POST "https://api.supabase.com/v1/projects/hosbtyylacluziugwjfd/database/query" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$body"

body=$(jq -n --rawfile q sql/games-schema.sql '{query: $q}')
curl -sS -X POST "https://api.supabase.com/v1/projects/hosbtyylacluziugwjfd/database/query" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$body"
```

Verify applied objects:

```bash
QUERY="SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE 'games_%' ORDER BY tablename;"
body=$(jq -n --arg q "$QUERY" '{query: $q}')
curl -sS -X POST "https://api.supabase.com/v1/projects/hosbtyylacluziugwjfd/database/query" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$body"
```

Migrate a stopped SQLite snapshot into a prefixed Supabase target:

```bash
.venv/bin/python scripts/migrate-sqlite-to-supabase.py \
  --sqlite /private/tmp/localplay-prod-cutover/revelry.db \
  --prefix games_ \
  --supabase-url https://hosbtyylacluziugwjfd.supabase.co \
  --service-key-file /private/tmp/localplay-prod-cutover/supabase-service-key.txt \
  --dry-run

.venv/bin/python scripts/migrate-sqlite-to-supabase.py \
  --sqlite /private/tmp/localplay-prod-cutover/revelry.db \
  --prefix games_ \
  --supabase-url https://hosbtyylacluziugwjfd.supabase.co \
  --service-key-file /private/tmp/localplay-prod-cutover/supabase-service-key.txt \
  --clear-target
```

Production cutover checklist, retained for future rebuilds or rollback/retry work:

- `/home/revelry-games/app/.env` has `SUPABASE_SERVICE_KEY` set.
- Gamma has soaked with `DB_BACKEND=supabase`.
- Production SQLite has been exported/reconciled into `games_*`.
- A fresh production SQLite backup exists.
- Production `.env` sets `DB_BACKEND=supabase` and `TABLE_PREFIX=games_`.

The deploy script validates the prefix before deploy:

- Production must use `TABLE_PREFIX=games_`.
- Gamma must use `TABLE_PREFIX=games_gamma_`.
- `DB_BACKEND=supabase` requires both `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`.

Prod or gamma can be rolled back to SQLite during the initial rollout window by restoring the intended `.env` file to `DB_BACKEND=sqlite` and redeploying the matching target:

```bash
# Production rollback
./scripts/deploy-gcp.sh --with-frontend

# Gamma rollback
./scripts/deploy-gcp.sh --gamma --with-frontend
```

Rollback caveat: writes accepted by Supabase after cutover must be replayed manually into SQLite if you need a fully current rollback database.

---

## Revelry Integration

LocalPlay exposes integration endpoints that let the Revelry app launch games, create rooms, and retrieve results without knowing game internals.

### Env vars

Both LocalPlay and Revelry need a shared secret:

| Service | Env var | Value |
|---|---|---|
| LocalPlay backend | `REVELRY_INTEGRATION_SECRET` | shared HMAC secret (hex, 64 chars) |
| LocalPlay backend | `PUBLIC_BASE_URL` | `https://gamesapi-gamma.revelryapp.me` (gamma) or `https://gamesapi.revelryapp.me` (prod) |
| LocalPlay backend | `REVELRY_AUTHORING_TOKEN_TTL_SECONDS` | authoring token lifetime; default `3600` |
| LocalPlay backend | `REVELRY_PARTY_HUB_RETURN_TOKEN_TTL_SECONDS` | party hub return-token lifetime after a LocalPlay-owned start; default `14400` |
| LocalPlay backend | `REVELRY_CALLBACK_URL` | Revelry callback endpoint for content/session/result sync: `https://api-gamma.revelryapp.me/api/games/localplay/callback` in gamma, `https://api.revelryapp.me/api/games/localplay/callback` in prod |
| LocalPlay backend | `REVELRY_CALLBACK_SECRET` | temporary rotation-only alias; normal callback signing uses `REVELRY_INTEGRATION_SECRET` |
| Revelry backend | `LOCALPLAY_INTEGRATION_SECRET` | same value as `REVELRY_INTEGRATION_SECRET` |

Generate a new secret: `openssl rand -hex 32`

### Setting env vars on the VM

```bash
# Gamma
gcloud compute ssh revelry-backend --zone us-central1-a --command "
  sudo sh -c \"grep -q '^REVELRY_INTEGRATION_SECRET=' /home/revelry-games/app/.env.gamma && \
    sed -i 's#^REVELRY_INTEGRATION_SECRET=.*#REVELRY_INTEGRATION_SECRET=<secret>#' /home/revelry-games/app/.env.gamma || \
    echo 'REVELRY_INTEGRATION_SECRET=<secret>' >> /home/revelry-games/app/.env.gamma\"
  sudo sh -c \"grep -q '^PUBLIC_BASE_URL=' /home/revelry-games/app/.env.gamma && \
    sed -i 's#^PUBLIC_BASE_URL=.*#PUBLIC_BASE_URL=https://gamesapi-gamma.revelryapp.me#' /home/revelry-games/app/.env.gamma || \
    echo 'PUBLIC_BASE_URL=https://gamesapi-gamma.revelryapp.me' >> /home/revelry-games/app/.env.gamma\"
"

# Production (when ready)
# Same pattern with /home/revelry-games/app/.env and PUBLIC_BASE_URL=https://gamesapi.revelryapp.me
```

After setting env vars, redeploy: `./scripts/deploy-gcp.sh --gamma --with-frontend`

### Supabase table

The `game_sessions` table must exist in Supabase before the integration works:

```bash
# Apply gamma schema (includes games_gamma_game_sessions)
TOKEN=$(security find-generic-password -s "Supabase CLI" -w | sed 's/^go-keyring-base64://' | base64 -d)
body=$(jq -n --rawfile q sql/games-gamma-schema.sql '{query: $q}')
curl -sS -X POST "https://api.supabase.com/v1/projects/hosbtyylacluziugwjfd/database/query" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$body"
```

### Integration endpoints

All integration endpoints require `Authorization: Bearer <REVELRY_INTEGRATION_SECRET>`.

LocalPlay callbacks to Revelry are signed with `REVELRY_INTEGRATION_SECRET` using HMAC-SHA256 over `${timestamp}.${raw_body}` and include `X-LocalPlay-Timestamp`, `X-LocalPlay-Event-Id`, and `X-LocalPlay-Signature: sha256=...`. Keep `REVELRY_CALLBACK_SECRET` unset unless doing a deliberate rotation/compatibility window; it must not silently diverge from the integration secret in normal gamma/prod.
If both `REVELRY_INTEGRATION_SECRET` and `REVELRY_CALLBACK_SECRET` are set to different values, LocalPlay logs a startup warning and continues to use `REVELRY_INTEGRATION_SECRET` as canonical.
Revelry-created sessions are LocalPlay `host_app_managed` billing sessions: LocalPlay does not grant signup-bonus sparks to the integration wallet and does not debit sparks when the host starts the game. Customer-facing billing/entitlement policy is owned by Revelry for this launch path. LocalPlay should receive normalized party capabilities from Revelry and enforce them; it should not need Revelry prices, provider receipt data, or transaction amounts in gamma/prod runtime requests.

| Endpoint | Method | Purpose |
|---|---|---|
| `/catalog?host_app=revelry` | GET | List available games with metadata |
| `/integrations/revelry/party-games-link` | POST | Mint a party hub URL and optional LocalPlay-owned start-intent URL |
| `/integrations/revelry/games?party_games_token=...` | GET | Open the party-scoped LocalPlay hub; may include `start_content_id` for Start shortcuts |
| `/integrations/revelry/sessions` | POST | Create a game session for a Revelry party |
| `/integrations/revelry/sessions/{id}/launch-token` | POST | Generate a signed JWT launch URL |
| `/integrations/revelry/sessions/{id}` | GET | Check session status |
| `/integrations/revelry/launch-token/resolve` | GET | Resolve a launch token to a room code (used by frontend) |

### Smoke test

```bash
# 1. Catalog
curl -s "https://gamesapi-gamma.revelryapp.me/catalog?host_app=revelry" | python3 -m json.tool | head -10

# 2. Create session
SECRET="<REVELRY_INTEGRATION_SECRET from gamma .env>"
curl -sS -X POST "https://gamesapi-gamma.revelryapp.me/integrations/revelry/sessions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${SECRET}" \
  -d '{
    "game_type": "quiz",
    "external_context": {
      "host_app": "revelry",
      "external_container_type": "party",
      "external_container_id": "test-party-123",
      "external_container_title": "Test Party"
    },
    "actor": { "display_name": "Avi", "role": "host" }
  }'

# 3. Generate launch token (use session_id from step 2)
curl -sS -X POST "https://gamesapi-gamma.revelryapp.me/integrations/revelry/sessions/<session_id>/launch-token" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${SECRET}" \
  -d '{"scope": "player", "route": "join", "embed": true}'

# 4. Open the returned launch_url in a browser
```

### Gamma readiness status

- Deployed the bridge, party hub, custom quiz authoring, host-app chrome cleanup, and callback retry slice to gamma from commit `cbc218f` on 2026-05-23 with `./scripts/deploy-gcp.sh --gamma --with-frontend`.
- Supabase gamma schema includes `games_gamma_game_sessions`, `games_gamma_quiz_packs`, `games_gamma_quiz_questions`, and `games_gamma_media_assets`.
- Gamma env includes `REVELRY_INTEGRATION_SECRET`, `PUBLIC_BASE_URL=https://gamesapi-gamma.revelryapp.me`, and `REVELRY_CALLBACK_URL=https://api-gamma.revelryapp.me/api/games/localplay/callback`; `REVELRY_CALLBACK_SECRET` should stay unset unless doing a deliberate rotation/compatibility window.
- Smoke-tested after deploy: `/health`, `/config.json`, `/catalog?host_app=revelry`, session creation, launch token generation, status polling, tokenless player launch redirect, party hub link/resolve, party workspace, LocalPlay-hosted authoring, saved quiz start, organizer/player WebSocket play-through, completion, results polling, and no signup-bonus sparks for the Revelry integration wallet.
- Deployed host-app lobby QR rendering from Revelry-provided `guest_join_url`, including the nested `external_context.guest_join_url` / `display.guest_join_url` launch-token shape used by Revelry.
- Callback behavior in gamma build: HMAC over `${timestamp}.${raw_body}` with `REVELRY_INTEGRATION_SECRET`, ISO UTC `occurred_at`, `content.deleted` support, and short bounded retry for Revelry `429` / transient `5xx`. Polling remains the recovery path if callbacks are disabled or miss delivery.
- Deployed host-app completed-game action returns to the Revelry Games surface instead of the standalone LocalPlay setup loop; spectator aliases `/spectate`, `/spectate/{room_code}`, `/tv`, and `/tv/{room_code}` connect through the shared spectator page and show clear websocket error states.
- Deployed broader host-app egress hardening so organizer/player/spectator terminal error states return to Revelry Games instead of exposing standalone LocalPlay picker/join recovery.
- Deployed standalone player/spectator URL room-code normalization before websocket connection so typed TV URLs like `/tv/abcd12` connect to room `ABCD12`.
- Deployed the Revelry start-intent hardening slice to gamma from commit `f6798ee` on 2026-05-24 with `./scripts/deploy-gcp.sh --gamma --with-frontend`. This includes encoded `start_url` query construction, `game_type` validation on party-games links, and in-hub active-game replacement confirmation before closing the old room.
- Deployed the generic Revelry setup/save/start slice to gamma from commit `2b3e345` on 2026-05-24 with `./scripts/deploy-gcp.sh --gamma --with-frontend`. This includes WMLT/Drawing setup forms, stable party-scoped saved content ids before start for those configurable games, generic party-hub content save/load/delete APIs, and catalog updates (`can_create_content = true`, `can_quick_start = false`) for WMLT/Drawing.
- Deployed the Revelry party-content scoping and callback hardening slice to gamma from commit `13f609e` on 2026-05-24 with `./scripts/deploy-gcp.sh --gamma --with-frontend`. This includes standalone custom-quiz draft isolation from Revelry party drafts, safe callback actor metadata for hub-started games, parsed-origin return/guest URL validation, `content.updated` with `previous_content_id` when used content versions, and startup warnings if `REVELRY_CALLBACK_SECRET` diverges from canonical `REVELRY_INTEGRATION_SECRET`.
- Applied the rendered gamma Supabase schema on 2026-05-24; `games_gamma_generated_content_content_type_check` now allows `quiz`, `mlt`, and `drawing`.
- Post-deploy gamma smoke on 2026-05-24 passed for `/health`, `/media/status`, `/config.json`, SPA root, anonymous auth rejection, invalid sign-in rejection, iOS checkout guard, and `GET /catalog?host_app=revelry`. The remote smoke was run with generation skipped; catalog returned launchable `quiz`, `wmlt`, and `drawing`, with Drawing Game default `time_limit = 30`.
- Deployed the active Revelry game re-entry and Supabase catalog-policy store fixes to gamma from commits `02cd0e0` and `5775eca` on 2026-05-25 with `./scripts/deploy-gcp.sh --gamma --with-frontend`. This fixes party-hub **Host game** / **Join to play** / **Join to watch** re-entry by minting fresh launch tokens from the party hub token, returns flat safe content metadata for Revelry compatibility, and routes host-app catalog policy reads through the active Supabase adapter.
- Revelry party hub active-session recovery: LocalPlay must reconcile persisted `games_gamma_game_sessions` rows with the current runtime room map after any gamma deploy/restart. If a session remains `lobby` / `active` / `paused` but its room no longer exists, LocalPlay marks it `expired` with `closed_reason = runtime_unavailable`, rejects new organizer/player launch tokens for it, hides it from the hub's active game card, and allows the host to start a fresh game without replacement confirmation.
- Applied the rendered gamma Supabase schema again on 2026-05-25; `games_gamma_host_app_catalog_flags` now exists. Seeded Revelry gamma catalog policy rows for `quiz`, `wmlt`, and `drawing` with `enabled = true` and `status = gamma`. `GET /catalog?host_app=revelry` now returns those rows with `status: "gamma"` instead of relying on the non-production permissive fallback.
- Post-deploy gamma smoke on 2026-05-25 passed for `/health`, `/providers`, `/media/status`, `/config.json`, SPA root, anonymous auth rejection, invalid sign-in rejection, iOS checkout guard, and `GET /catalog?host_app=revelry`; generation/idempotency checks were intentionally skipped.
- On 2026-05-25, gamma media upload testing found `403 bad_signature` from the IONOS LocalPlay upload handler because `games-backend-gamma` had a `MEDIA_UPLOAD_SECRET` that did not match the IONOS upload secret. Updated `/home/revelry-games/app/.env.gamma` to match the IONOS secret, redeployed gamma with `./scripts/deploy-gcp.sh --gamma --with-frontend`, and verified a signed PNG upload returned `200`.
- On 2026-05-25, deployed the Revelry authoring editor remount fix to gamma so saving a new party-scoped quiz no longer clears the custom quiz editor after `currentContentId` is assigned.
- Post-fix gamma Playwright passed on 2026-05-25: `npm run test:e2e:gamma` returned `2 passed`; `REVELRY_GAMMA_PARTY_GAMES_URL_FILE=... npm run test:e2e:gamma:revelry` returned `2 passed`, covering Drawing save/start/re-entry plus custom Quiz image upload/save/payload verification.
- Deployed gamma-only extended party-games token TTL support on 2026-05-25 with `./scripts/deploy-gcp.sh --gamma --with-frontend`. The Revelry gamma mint script can now write a 30-day disposable-party URL to `gamma_party_games_url.txt`; production rejects custom party-games token TTLs. Verified the minted token expiry was 30 days, then reran Playwright: `REVELRY_GAMMA_PARTY_GAMES_URL_FILE=... npm run test:e2e:gamma:revelry` returned `2 passed`, and `npm run test:e2e:gamma` returned `2 passed`.
- On 2026-05-26, added gamma callback URL management to the deploy bootstrap, set `/home/revelry-games/app/.env.gamma` to call `https://api-gamma.revelryapp.me/api/games/localplay/callback`, and redeployed gamma with `./scripts/deploy-gcp.sh --gamma --with-frontend`.
- On 2026-05-26, `REVELRY_GAMMA_PARTY_GAMES_URL_FILE=... npm run test:e2e:gamma:revelry` returned `3 passed`, now covering Drawing save/start/re-entry, a complete Revelry-started Quiz through LocalPlay WebSockets to podium, Revelry callback/session mirror, Revelry session-results polling with final player score, workspace cleanup after completion, and custom Quiz image upload/save/payload verification. `npm run test:e2e:gamma` returned `2 passed`.
- On 2026-06-01, applied the gamma-only Housie schema update: `games_gamma_generated_content_content_type_check` now allows `quiz`, `mlt`, `drawing`, and `housie`. Production `games_generated_content_content_type_check` remains unchanged until Housie is promoted.
- On 2026-06-24, applied the gamma Random Chit authoring schema update: `games_gamma_generated_content_content_type_check` now allows `quiz`, `mlt`, `drawing`, `housie`, and `chit_pull`. Production SQL is updated in the repo but the production constraint was not applied in this gamma pass.
- On 2026-07-08, applied the **login-streak bonus** activation (SPEC-STREAK-BONUS) to **gamma then prod** via a targeted migration (Management API, project `hosbtyylacluziugwjfd`). Prod (`games_`): `ALTER TABLE games_wallets ADD COLUMN IF NOT EXISTS bonus_streak` + `CREATE OR REPLACE FUNCTION games_grant_daily_bonus`. Gamma (`games_gamma_`): `ALTER TABLE games_gamma_wallets ADD COLUMN IF NOT EXISTS bonus_streak` + `CREATE OR REPLACE FUNCTION games_gamma_grant_daily_bonus`. Streak-aware, **signature unchanged** `(TEXT,TEXT,INTEGER,INTEGER)` → no code redeploy. Deliberately scoped to only those two objects — the `content_type` CHECK and referral RPCs (gates #2–#4) were **not** touched. Verified on both prefixes with a throwaway wallet: day-1 `streak=1/reward=10`, same-day `granted=false`, consecutive-day `streak=2/reward=15`; temp wallets deleted (`leftover=0`). STREAK_STEP=5/STREAK_MAX=30 are constants mirrored in the RPC — re-render + re-apply if the config env defaults change.
- On 2026-07-08, **enabled the check-in games** (`party_quests`, `find_someone`) for `host_app=revelry` in **gamma then prod** by upserting rows into `games_gamma_host_app_catalog_flags` (gamma) and `games_host_app_catalog_flags` (prod) — unique on `(environment,host_app,game_id)`: gamma `status=gamma`/`capability_overrides={}`, prod `status=live` with explicit quick-start-only overrides (`can_quick_start=true`, everything else false, matching `musical_chairs`). Reason: Revelry's check-in default selector offers these (static-catalog metadata, policy-independent), but the launch gate is policy-gated, so without these rows a prod check-in launch returned 422. Verified: real policy code yields `launchable=True, authorable=False`; live `/catalog?host_app=revelry` on **prod** (6 games) and **gamma** (16) both list them `launchable=true`. Policy cache TTL is 60s, so running backends picked the rows up within a minute (no redeploy).
- On 2026-07-14, upgraded **production Party Quests** from quick-start-only to the configured staging/check-in flow. Applied Supabase migration `20260715021000_allow_party_quests_generated_content` to production only, expanding `games_generated_content_content_type_check` to `quiz`, `mlt`, `drawing`, `housie`, `chit_pull`, and `party_quests`; verified with a disposable `party_quests` insert/delete. Then upserted the `party_quests` `games_host_app_catalog_flags` row for the running `production` environment (and left the older `prod` compatibility row harmlessly strict too) to `status=live` with `can_quick_start=true`, `can_create_content=true`, `can_edit_content=true`, `supports_ai_generation=true`, `embedded_authoring_supported=true`, and `requires_prepared_content_for_checkin=true`.
- On 2026-06-01, deployed Housie Revelry gamma enablement. Live gamma catalog returns `housie` for `host_app=revelry` with `status: "gamma"`, `can_create_content: true`, `can_quick_start: true`, and `supports_ai_generation: false`; gamma Housie content save returned `question_count/item_count = 6`.
- On 2026-06-01, deployed the stale lobby roster fix. When `ROOM_RESET` or another lobby broadcast discovers dead player sockets, LocalPlay removes them and emits an updated roster so the organizer player count matches server-side minimum-player checks.
- On 2026-06-01, broadened the socket lifecycle fix across game families. Per-player runtime syncs and drawing broadcasts now publish corrected rosters after removing dead player sockets; min-player-gated starts prune dead sockets before checking player counts; superseded Revelry sessions close their old runtime rooms and cannot later be marked complete by stale callbacks. Housie saved setups are included in the Revelry party workspace `prepared_content` list.
- Basic Revelry gamma end-to-end testing has worked for catalog, session creation, organizer/player/spectator launch, Drawing setup/start/re-entry, custom Quiz image upload/save, completion, result polling, callback delivery, and workspace active-session cleanup. Before production promotion, still repeat from Revelry gamma for native app/universal-link return flows and any production-only host-app chrome checks.
- Full spec: `SPEC-REVELRY-INTEGRATION.md`

### Production readiness status

- Deployed the current LocalPlay bridge/backend-served SPA to production on 2026-06-02 with `./scripts/deploy-gcp.sh --with-frontend`, promoting the gamma-tested Revelry catalog picker, Musical Chairs quick-start bridge, hosted music loops, and recent UX/gameplay fixes.
- Production env includes `REVELRY_INTEGRATION_SECRET`, `PUBLIC_BASE_URL=https://gamesapi.revelryapp.me`, `REVELRY_CALLBACK_URL=https://api.revelryapp.me/api/games/localplay/callback`, and `REVELRY_CALLBACK_SECRET=`. Keep `REVELRY_CALLBACK_SECRET` empty unless doing a deliberate rotation/compatibility window.
- Production env keeps AI image generation disabled with `IMAGE_GENERATION_PROVIDER=none`.
- Production media uploads are enabled through IONOS with `MEDIA_PUBLIC_BASE_URL=https://media.revelryapp.me/apps/localplay`, `MEDIA_UPLOAD_URL=https://media.revelryapp.me/apps/localplay/upload.php`, `MEDIA_PATH_PREFIX=prod`, and a `MEDIA_UPLOAD_SECRET` matching the string returned by `~/revelryapp/media/apps/localplay/upload-secret.php`.
- Applied the targeted production Supabase parity migration on 2026-05-25: `games_quiz_packs`, `games_quiz_questions`, `games_media_assets`, `games_game_sessions`, and the refreshed `games_generated_content_content_type_check` allowing `quiz`, `mlt`, and `drawing`.
- Post-migration consistency check scoped to LocalPlay tables/RPCs (`games_` vs `games_gamma_`) returned no diffs across tables, columns/defaults, constraints, indexes, RLS, policies, and RPC signatures as of 2026-05-25. The shared Supabase project also contains unrelated `pp_*` tables; those are not LocalPlay/Revelry bridge migrations and should not be modified by LocalPlay deploy work.
- Applied the rendered production Supabase schema on 2026-06-02 to create `games_host_app_catalog_flags`, then seeded production Revelry policy rows with `status = "live"` for `quiz`, `wmlt`, `drawing`, and quick-start-only `musical_chairs`. The production generated-content constraint now includes `housie`, `chit_pull`, and `party_quests` after the July 14 Party Quests migration; Housie/Random Chit production authoring exposure is still controlled separately by host-app catalog policy and should only be flipped after their own prod save/start smokes.
- Standalone production LocalPlay enables the implemented standalone game catalog, including Bingo and Baby Bingo. `ENABLE_BINGO=false` and `VITE_ENABLE_BINGO=false` are kill switches only; do not use them as the default prod posture. Revelry exposure remains controlled separately through static host-app support plus `games_host_app_catalog_flags`.
- Production smoke passed on 2026-06-02 for `/health`, `GET /catalog?host_app=revelry` returning live games, `/media/status`, and the backend-served frontend Playwright smoke on desktop/mobile.
- `/media/status` should report `upload_available=true`, `generation_available=false`, and `storage_backend=ionos` in production. This is the intended state for custom quiz photo uploads with AI image generation disabled.
- Added the same shared secret to GCP Secret Manager secret `revelry-prod-localplay-integration-secret` on 2026-05-25; version `1` is enabled. Do not print or copy this value into docs.
- Remaining production validation should smoke a real Revelry prod party Games tab, LocalPlay launch, and callback/result handling with the production `LOCALPLAY_INTEGRATION_SECRET`.

### Enabling Revelry games

Revelry game availability is controlled by LocalPlay's host-app catalog policy. Revelry should render the catalog returned by LocalPlay instead of hardcoding enabled games.

Important distinction:

- A game that does not exist in LocalPlay yet still needs one LocalPlay implementation release: static catalog metadata, runtime/setup/content contracts, host-app-safe routes, callbacks/results, and tests.
- A game that is already implemented and bridge-ready should be exposed, hidden, allowlisted, or killed through host-app catalog policy, without a Revelry release and ideally without another LocalPlay deploy.
- Remote policy cannot turn on capabilities that the static LocalPlay catalog does not support. The static catalog is the safety ceiling; policy is the rollout/control layer.

Policy rows live in the prefixed Supabase table `{TABLE_PREFIX}host_app_catalog_flags`, for example `games_gamma_host_app_catalog_flags` in gamma and `games_host_app_catalog_flags` in production. Production fails closed when policy is missing, so seed production rows before expecting games to appear in `GET /catalog?host_app=revelry`.

Use the admin API when `ADMIN_API_KEY` is configured. Do not paste real keys into docs, shell history, or git:

```bash
# List current gamma Revelry flags.
curl -sS -H "Authorization: Bearer ${ADMIN_API_KEY}" \
  "https://gamesapi-gamma.revelryapp.me/admin/host-app-catalog-flags?environment=gamma&host_app=revelry"

# Enable an already bridge-ready game for gamma.
curl -sS -X POST \
  -H "Authorization: Bearer ${ADMIN_API_KEY}" \
  -H "Content-Type: application/json" \
  https://gamesapi-gamma.revelryapp.me/admin/host-app-catalog-flags \
  -d '{
    "environment": "gamma",
    "host_app": "revelry",
    "game_id": "drawing",
    "enabled": true,
    "status": "gamma",
    "capability_overrides": {
      "can_create_content": true,
      "can_edit_content": true,
      "can_quick_start": false,
      "supports_ai_generation": true,
      "supports_images": false,
      "payments_enabled": false,
      "embedded_authoring_supported": true
    },
    "notes": "Gamma rollout",
    "updated_by": "deploy-operator"
  }'

# Kill-switch a game after the 30-60 second policy cache expires.
curl -sS -X POST \
  -H "Authorization: Bearer ${ADMIN_API_KEY}" \
  -H "Content-Type: application/json" \
  https://gamesapi-gamma.revelryapp.me/admin/host-app-catalog-flags \
  -d '{
    "environment": "gamma",
    "host_app": "revelry",
    "game_id": "drawing",
    "enabled": false,
    "status": "disabled",
    "notes": "Disabled by operator",
    "updated_by": "deploy-operator"
  }'
```

After changing policy:

1. Verify `GET /catalog?host_app=revelry` shows or hides the expected game after the policy cache expires.
2. Run `npm run test:e2e:gamma` for deployed gamma frontend health.
3. For a game exposed to Revelry gamma, run the repeatable `Revelry gamma embedded E2E` below with a fresh party games URL.
4. Promote to production only after the game is implemented, bridge-ready, gamma-tested, and seeded in the production policy table with `status = "live"`.

---

## Media Uploads (IONOS)

LocalPlay image files should be stored on IONOS, not Supabase Storage and not the GCP VM filesystem. Supabase remains the metadata store for media asset rows and quiz-pack question references.

This should follow the Revelry media-upload pattern:

1. Frontend calls the LocalPlay backend for a signed upload target, e.g. `POST /media/upload-url`.
2. Backend validates wallet/content ownership and generates:
   - `asset_id`
   - relative IONOS path
   - short expiry
   - HMAC token using `MEDIA_UPLOAD_SECRET`
3. Frontend uploads `multipart/form-data` directly to the IONOS PHP handler.
4. PHP validates CORS, expiry, HMAC, path prefix, extension, MIME type, and upload status.
5. PHP writes the image under the LocalPlay media directory.
6. Frontend calls a finalize endpoint, e.g. `POST /media/{asset_id}/finalize`, so backend metadata becomes `ready`.
7. Runtime quiz questions use `image_asset_id`, `image_url`, and `image_alt`; `image_url` may be `/media/{asset_id}` or a direct `media.revelryapp.me` URL.

IONOS is not a product-facing authoring concept. Quiz authors should see upload, preview, replace, remove, and alt text controls only; IONOS paths, CDN URLs, `/media` paths, asset ids, and storage backend names are internal metadata/debugging details.

The owner/context path segment must be sanitized before signing. Host-app wallets can contain unsafe characters, for example `revelry:party:{party_id}`; signed paths should use a path-safe segment such as `revelry_party_{party_id}`. Raw `:` characters are rejected by the IONOS PHP handler as `invalid_path`.

Recommended public URL and server layout:

```text
Public base URL:
https://media.revelryapp.me/apps/localplay/

IONOS server:
~/revelryapp/media/apps/localplay/
  upload.php
  upload-secret.php
  delete.php
  .htaccess
  prod/
    uploads/{wallet_prefix}/YYYY/MM/DD/{asset_id}.webp
    generated/{asset_id}.webp
    thumbs/{asset_id}.webp
  gamma/
    uploads/{wallet_prefix}/YYYY/MM/DD/{asset_id}.webp
    generated/{asset_id}.webp
    thumbs/{asset_id}.webp
```

Repo source:

```text
ionos/media/upload.php
ionos/media/upload-secret.example.php
ionos/media/uploads.htaccess
ionos/media/delete.php   # future
ionos/media/.htaccess    # future
```

Deploy PHP handlers only from repo source:

```bash
scp ionos/media/upload.php u69414981@home420463025.1and1-data.host:~/revelryapp/media/apps/localplay/upload.php
ssh u69414981@home420463025.1and1-data.host "mkdir -p ~/revelryapp/media/apps/localplay/gamma/uploads ~/revelryapp/media/apps/localplay/prod/uploads"
scp ionos/media/uploads.htaccess u69414981@home420463025.1and1-data.host:~/revelryapp/media/apps/localplay/gamma/uploads/.htaccess
scp ionos/media/uploads.htaccess u69414981@home420463025.1and1-data.host:~/revelryapp/media/apps/localplay/prod/uploads/.htaccess
```

Create `upload-secret.php` from `ionos/media/upload-secret.example.php`, replace the placeholder with
the real `MEDIA_UPLOAD_SECRET`, and deploy that edited file. Do not deploy the example file as-is.

The IONOS secret file must match backend env:

```text
IONOS:   ~/revelryapp/media/apps/localplay/upload-secret.php
Backend: MEDIA_UPLOAD_SECRET
```

`upload-secret.php` should return the secret string and must not echo it. A legacy `.upload_secret`
file is still accepted by `upload.php` only as a migration fallback, but it should not be used for
new deploys because some shared-host docroots serve dotfiles publicly. After updating the secret,
verify the response body is empty or denied:

```bash
curl -sS https://media.revelryapp.me/apps/localplay/upload-secret.php
curl -sS https://media.revelryapp.me/apps/localplay/.upload_secret
```

Neither command should print `MEDIA_UPLOAD_SECRET`.

Required backend env for uploads:

```env
MEDIA_PUBLIC_BASE_URL=https://media.revelryapp.me/apps/localplay
MEDIA_UPLOAD_URL=https://media.revelryapp.me/apps/localplay/upload.php
MEDIA_UPLOAD_SECRET=<same value returned by upload-secret.php>
MEDIA_PATH_PREFIX=gamma   # gamma; use prod in production
MEDIA_ALLOWED_MIME_TYPES=image/png,image/jpeg,image/webp
MEDIA_UPLOAD_TOKEN_TTL_SECONDS=900
```

CORS:

- `upload.php` should allow `POST, OPTIONS` from:
  - `https://games.revelryapp.me`
  - `https://gamesapi.revelryapp.me`
  - `https://gamesapi-gamma.revelryapp.me`
  - local dev origins such as `http://localhost:9200` and `http://127.0.0.1:9200`
  - Capacitor origins if native upload is enabled
- `.htaccess` should allow reads for image files across web/PWA/native surfaces. Like Revelry, this can be `Access-Control-Allow-Origin: *` because the files are public CDN-style bearer URLs protected by unguessable UUID paths, not auth cookies.

Path validation:

- PHP handlers must reject `..`, absolute paths, and unknown prefixes.
- LocalPlay paths should start with `prod/` or `gamma/`.
- Backend-generated paths must use sanitized owner/context segments.
- Backend-generated paths should use UUID-like asset names, never user-provided filenames.
- Backend and PHP handlers must reject executable/config/web extensions even when MIME type appears image-like, including double-extension names such as `image.php.jpg`.
- Put `ionos/media/uploads.htaccess` under each uploaded-content directory (`gamma/uploads/` and `prod/uploads/`) to disable PHP/script execution without disabling `upload.php`.
- Delete should be best-effort: signed `delete.php` removes the IONOS file, while backend metadata is soft-deleted.

Operational notes:

- Deploying or editing live IONOS PHP files should be treated as a production operation.
- Check disk usage before enabling broad uploads:

```bash
ssh u69414981@home420463025.1and1-data.host "du -sh ~/revelryapp/media/apps/localplay/"
```

---

## Quick Reference Commands

### Full LocalPlay redeploy

```bash
# From project root:

# Production backend + bundled SPA fallback
./scripts/deploy-gcp.sh --with-frontend

# Gamma backend + bundled SPA
./scripts/deploy-gcp.sh --gamma --with-frontend

# Public IONOS frontend
cd frontend
VITE_BASE_PATH=/ VITE_API_URL=https://gamesapi.revelryapp.me VITE_WEB_URL=https://games.revelryapp.me/ VITE_CAST_APP_ID=1BC9ACD8 npx vite build
ssh u69414981@home420463025.1and1-data.host "mkdir -p ~/revelryapp/games"
scp -r dist/* u69414981@home420463025.1and1-data.host:~/revelryapp/games/
rsync -avz dist/.htaccess u69414981@home420463025.1and1-data.host:~/revelryapp/games/.htaccess
```

### Public IONOS frontend only

```bash
cd frontend
VITE_BASE_PATH=/ VITE_API_URL=https://gamesapi.revelryapp.me VITE_WEB_URL=https://games.revelryapp.me/ VITE_CAST_APP_ID=1BC9ACD8 npx vite build
ssh u69414981@home420463025.1and1-data.host "mkdir -p ~/revelryapp/games"
scp -r dist/* u69414981@home420463025.1and1-data.host:~/revelryapp/games/
rsync -avz dist/.htaccess u69414981@home420463025.1and1-data.host:~/revelryapp/games/.htaccess
```

### Backend containers only

```bash
# Production
./scripts/deploy-gcp.sh --with-frontend

# Gamma
./scripts/deploy-gcp.sh --gamma --with-frontend
```

### View backend logs
```bash
gcloud compute ssh revelry-backend --project=revelryapp --zone=us-central1-a --command \
  'docker logs games-backend --tail 50 -f'

gcloud compute ssh revelry-backend --project=revelryapp --zone=us-central1-a --command \
  'docker logs games-backend-gamma --tail 50 -f'
```

### Check if backends are healthy

```bash
curl -sS -i https://gamesapi.revelryapp.me/health
curl -sS -i https://gamesapi-gamma.revelryapp.me/health
```

### Test runbook

Use this section as the repeatable deploy/regression checklist. Pick the narrowest test that matches the change, then run the broader smoke before promoting or after touching deploy/env/media/auth paths.

#### Local backend tests

Run focused backend tests while developing integration or storage changes:

```bash
.venv/bin/python -m pytest backend/tests/test_revelry_integration.py
.venv/bin/python -m pytest backend/tests/test_host_app_catalog_policy.py backend/tests/test_revelry_integration.py
```

Run the broader backend suite when touching shared API/session/storage behavior:

```bash
make test
```

#### Local frontend tests

Run unit/component tests while developing frontend behavior:

```bash
cd frontend
npm test -- --run src/__tests__/hostAppMode.test.tsx
npm run build
```

Run local Playwright against the Vite dev server before deploying frontend-heavy changes, especially game-screen, theme, authoring, or layout changes:

```bash
make test-frontend-e2e
```

This runs Playwright against local Vite. The current coverage includes the DrawingGame organizer prompt screen and quiz-variant prompt screens on desktop and mobile, verifies segmented controls stay aligned, checks there is no horizontal page overflow, catches overlap with fixed menu/spark controls, and verifies variant generation sends the expected `mode`.

If an intentional visual change updates snapshots, refresh them from `frontend/`:

```bash
npm run test:e2e -- --update-snapshots
```

#### Remote backend smoke

Run these after prod/gamma deploys and after auth/provider/DNS/backend env changes:

```bash
# Production: health, provider/config, SPA root, auth guards, iOS checkout guard,
# live generation, idempotent retry, and token balance no-double-charge check.
make test-remote-prod

# Gamma equivalent.
make test-remote-gamma

# Lower-impact variant when you do not want to spend a live LLM call:
.venv/bin/python scripts/smoke-remote.py --base-url https://gamesapi.revelryapp.me --skip-generate
```

#### Gamma Playwright smoke

Run this after deploying gamma frontend/backend changes:

```bash
cd frontend
npm run test:e2e:gamma
```

This points Playwright at `https://gamesapi-gamma.revelryapp.me`, verifies the standalone catalog renders on desktop and mobile, checks `/media/status`, and fails on browser console/page errors.

#### Pre-prod live game regression

Run this before major production deployments that touch room creation, WebSockets, game runtime logic, or shared player/host/spectator surfaces:

```bash
cd frontend
PREPROD_LIVE=1 PLAYWRIGHT_BASE_URL=https://gamesapi-gamma.revelryapp.me npm run test:e2e:preprod-live
```

This is intentionally heavier than the gamma smoke: it creates disposable deterministic content and rooms, opens multiple real browser player contexts, starts each covered game family, performs one meaningful action or turn handoff, and checks host/player UI state. Run it with one worker and treat failures as production-blocking until triaged. Current coverage includes Quiz runtime, Most Likely To, Housie, Bingo/Baby Bingo, Musical Chairs, Bluff, Two Truths and a Lie, Story Chain, Common Ground, Who Am I, Chit Pull, and Drawing. The suite must seed deterministic content and must not depend on live AI generation.

For local split-origin QA, run the backend on a free port and pass both `VITE_API_URL` and `LIVE_API_BASE_URL` to the Playwright command. This avoids assuming port `8000` is available when other local projects are running.

For a representative mobile screenshot audit of live states, run:

```bash
cd frontend
PREPROD_UX_AUDIT=1 PLAYWRIGHT_BASE_URL=https://gamesapi-gamma.revelryapp.me npm run test:e2e:preprod-ux
```

Screenshots default to `/private/tmp/localplay-preprod-ux-audit`; override with `PREPROD_UX_AUDIT_DIR` when saving artifacts for review.

#### Revelry gamma embedded E2E

This is the repeatable gamma-only test for the LocalPlay/Revelry embedded party hub. It is intentionally desktop-only and stateful because it mutates one disposable gamma party.

1. Mint a fresh gamma `party_games_url` for the disposable Revelry gamma party. The token must have host capabilities: `manage_games`, `author_content`, and `operate_game`.

   **Preferred (LocalPlay-side helper, no local gcloud-secrets setup):** `scripts/mint-gamma-revelry-url.sh` pulls `REVELRY_INTEGRATION_SECRET` from the running gamma container over SSH (the secret never leaves the VM; only the URL is written locally) and mints against the real seeded party `bc87a6df-9f2e-4ac3-acbf-b89dc82f127e` ("Gamma Full Flow Test Party") so the mirror-results-back test resolves on Revelry:

```bash
./scripts/mint-gamma-revelry-url.sh                 # writes ./gamma_party_games_url.txt, 1h TTL
./scripts/mint-gamma-revelry-url.sh 3600 /tmp/x.txt # custom ttl_seconds + output path
```

   **Alternative (Revelry repo script + Secret Manager):**

```bash
export LOCALPLAY_GAMMA_INTEGRATION_SECRET="$(gcloud secrets versions access latest --project revelryapp --secret revelry-gamma-localplay-integration-secret)"
.venv/bin/python /Users/Avi/Desktop/dev/antigravity/revelryapp/scripts/mint-localplay-gamma-url.py \
  --ttl-days 0.05 \
  --output ./gamma_party_games_url.txt >/dev/null
```

Both scripts are gamma-only and write the full URL to `gamma_party_games_url.txt`, which must stay ignored. Do not print the URL or token in chat, logs, or committed files. Mint fresh before each run; a short TTL such as `0.05` days, about 72 minutes, is enough for normal E2E. LocalPlay honors the script's `ttl_seconds` request outside production only, capped at 30 days; production rejects custom party-games token TTLs. Use a longer gamma-only TTL, up to 30 days, only while actively debugging across sessions.

2. Verify only the shape/expiry, not the token:

```bash
.venv/bin/python -c "import base64,json,datetime,urllib.parse,pathlib,time; url=pathlib.Path('gamma_party_games_url.txt').read_text().strip(); print('has_gamma_url=', url.startswith('https://gamesapi-gamma.revelryapp.me/integrations/revelry/games?party_games_token=')); tok=urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get('party_games_token',[''])[0]; payload=tok.split('.')[1]; payload += '='*((4-len(payload)%4)%4); data=json.loads(base64.urlsafe_b64decode(payload)); exp=data.get('exp'); print('exp=', datetime.datetime.fromtimestamp(exp, datetime.timezone.utc).isoformat() if exp else data.get('expires_at')); print('valid_now=', bool(exp and exp > time.time()))"
```

3. Run:

```bash
cd frontend
REVELRY_GAMMA_PARTY_GAMES_URL_FILE=../gamma_party_games_url.txt npm run test:e2e:gamma:revelry
```

For a larger pre-production Revelry check, run the host-app matrix after the standard gamma flow:

```bash
cd frontend
PREPROD_REVELRY=1 REVELRY_GAMMA_PARTY_GAMES_URL_FILE=../gamma_party_games_url.txt npm run test:e2e:preprod-revelry
```

The matrix verifies the embedded Revelry Games hub catalog/search UI, then starts every launchable game returned by the live Revelry catalog. It covers deterministic party-scoped content saves for Quiz, Most Likely To, Drawing, Housie, Random Chit, and Party Quests, and quick-start launch for all catalog games that expose `can_quick_start=true` without `can_create_content`. It also mints organizer/player/spectator launch tokens for each session. If a newly exposed Revelry game requires saved content but is missing from the matrix fixture set, the test fails and the harness must be updated before rollout. The Party Quests staging spec additionally exercises the strict setup-required/check-in lifecycle: saved preview, prepared session start, first-player auto-start, late join, and cancellation.

The test verifies:

- LocalPlay embedded party hub resolves the Revelry party token.
- Drawing setup saves through the live workspace API.
- Drawing start/replacement creates or replaces the active room.
- Organizer/player/spectator launch-token minting works.
- Re-entering the hub shows the active game.
- **Host game** opens with a fresh organizer token, avoiding stale-token failures.
- Custom Quiz authoring opens from the hub.
- Custom Quiz question image upload works through signed IONOS media upload.
- Saved quiz payload contains the media-backed image URL and alt text.
- A small quiz can be started from the Revelry party workspace, driven through LocalPlay WebSockets to podium, and mirrored back to Revelry as a completed session.
- Revelry's sessions and session-results endpoints return the final player score/feed-card summary, and the workspace no longer reports the completed LocalPlay room as active.

If the test shows `Invalid or expired party games token`, mint a fresh gamma URL and rerun. If image upload fails with `403 bad_signature`, verify `games-backend-gamma` `MEDIA_UPLOAD_SECRET` matches the string returned by `~/revelryapp/media/apps/localplay/upload-secret.php` on IONOS, then redeploy gamma. If completion succeeds in LocalPlay but Revelry never shows a completed session, verify gamma has `REVELRY_CALLBACK_URL=https://api-gamma.revelryapp.me/api/games/localplay/callback` and redeploy gamma.

If a Revelry-hosted Start or replay feels slow, check LocalPlay logs before changing the callback contract:

```bash
gcloud compute ssh revelry-backend --zone us-central1-a --command \
  "docker logs games-backend-gamma --since 2h | grep -E 'revelry_party_game_start_timing|revelry_sessions_create_timing|revelry_session_create_timing|revelry_superseded_room_close_timing|revelry_callback_timing|integration_callback_timing'"
```

For same-content replay, prefer the organizer's in-place `RESET_ROOM` / Play Again path when the room socket is still alive. That avoids session replacement, signed callbacks, and a full organizer reload. If timing logs show genuine new-session starts are blocked by inline callbacks, the safe follow-up is a durable callback outbox with retries and Revelry idempotency, not fire-and-forget callback delivery.

Runtime game callbacks from WebSocket paths are awaited through a worker thread so synchronous HTTP retries and backoff do not block the event loop. If a callback is slow, the relevant game flow may still wait for its own lifecycle callback, but other rooms, joins, answers, timers, and socket traffic should keep moving.

Do not run this against production. For production, create a separate explicitly approved smoke plan using a disposable prod party.

#### Manual auth/payment checks

Manual provider sign-in smoke is still required for the browser popup flows:

- Google: open the SPA, sign in, verify the menu shows **Signed in**, account/email prefix, and **Sign Out**.
- Apple: same as Google; verify Apple returns to the same host.
- IONOS production frontend: repeat on `https://games.revelryapp.me/`.
- Backend-served prod/gamma: repeat on `https://gamesapi.revelryapp.me` and `https://gamesapi-gamma.revelryapp.me` when those origins have changed.

Stripe smoke should stay manual/test-mode unless explicitly doing a paid production checkout:

- Gamma checkout must use Stripe test keys.
- Production checkout should only be tested with an intentional real purchase/refund workflow.

Manual curl spot checks:

```bash
curl -s https://gamesapi.revelryapp.me/health
curl -s https://gamesapi-gamma.revelryapp.me/health
curl -s https://gamesapi.revelryapp.me/providers | python3 -m json.tool
curl -s https://gamesapi-gamma.revelryapp.me/providers | python3 -m json.tool
curl -s https://gamesapi.revelryapp.me/media/status | python3 -m json.tool
curl -s https://gamesapi-gamma.revelryapp.me/media/status | python3 -m json.tool
```

`/media/status` is the Phase 0 image-platform smoke check. It should return
JSON, not `index.html`; that confirms `/media` is still protected from the
backend-served SPA fallback.

### Check IONOS disk usage
```bash
ssh u69414981@home420463025.1and1-data.host "du -sh ~/revelryapp/games/"
```

---

## GCP Firewall (Access Restriction)

The backend is locked down so only your home IP can reach it. Anyone else gets a connection timeout.

**Current rules**: `allow-http` and `allow-https` are restricted to your home IPv4.
**SSH is unaffected** — `gcloud compute ssh` always works regardless of these rules.

### Check current rules
```bash
gcloud compute firewall-rules list --project=revelryapp \
  --format="table(name,allowed,sourceRanges)" \
  --filter="name:(allow-http OR allow-https)"
```

### Update after IP change

If the game stops working, your ISP probably changed your IP.

```bash
# Get your new IP
curl -s https://ifconfig.me

# Update both rules (replace NEW_IP with your actual IP)
gcloud compute firewall-rules update allow-http --project=revelryapp --source-ranges="NEW_IP/32"
gcloud compute firewall-rules update allow-https --project=revelryapp --source-ranges="NEW_IP/32"
```

### Open to everyone (remove restriction)
```bash
gcloud compute firewall-rules update allow-http --project=revelryapp --source-ranges="0.0.0.0/0"
gcloud compute firewall-rules update allow-https --project=revelryapp --source-ranges="0.0.0.0/0"
```

---

## GCP Billing Cap ($10/month hard limit)

A Cloud Function automatically **disables billing** if monthly costs reach $10.

**How it works:**
1. GCP Budget "Revelry monthly cap" sends alerts to Pub/Sub topic `billing-alerts`
2. Cloud Function `stop-billing` listens on that topic
3. When cost hits 100% of $10, the function unlinks the billing account from the project
4. All paid resources (VM, network) stop — no more charges

**What happens if it triggers:** The VM shuts down and the backend goes offline. The frontend on IONOS is unaffected (separate hosting). To restore, re-link billing in the GCP Console.

### Check current budget status
```bash
gcloud billing budgets describe \
  "billingAccounts/012366-DC2219-426FD9/budgets/3971e00b-3ca2-4b99-a702-68ad9383d1c0" \
  --format="yaml(displayName,amount,thresholdRules)"
```

### Check Cloud Function logs
```bash
gcloud functions logs read stop-billing --project=revelryapp --region=us-central1 --limit=20
```

### Re-enable billing after it triggers
1. Go to https://console.cloud.google.com/billing/projects?project=revelryapp
2. Click "Link a billing account" next to the revelryapp project
3. Select "Default Billing Amount"
4. Restart the VM: `gcloud compute instances start revelry-backend --project=revelryapp --zone=us-central1-a`

### Note on free tier
The e2-micro VM + 30GB disk in us-central1 is covered by GCP's Always Free tier, so normal usage should cost $0/month. This cap is a safety net for unexpected charges.

---

## Troubleshooting

| Problem | Check |
|---------|-------|
| Frontend 404 on refresh | `.htaccess` missing or wrong `RewriteBase` |
| WebSocket fails to connect | Nginx config missing `Upgrade`/`Connection` headers |
| CORS errors | `ALLOWED_ORIGINS` in backend `.env` doesn't include frontend domain |
| Docker won't start | `docker logs games-backend --tail 80` or `docker logs games-backend-gamma --tail 80` |
| SSL cert expired | `sudo certbot renew && sudo systemctl reload nginx` |
| Old JS bundles cached | Clear `assets/` dir before deploying, hard-refresh browser |
| API suddenly unreachable | Home IP probably changed — update firewall rules (see section above) |
| VM stopped unexpectedly | Billing cap may have triggered — re-link billing (see billing cap section) |
| `gamesapi.revelryapp.me` returns 502 | Check `games-backend` is running and bound to `127.0.0.1:8000` |
| `gamesapi-gamma.revelryapp.me` returns 502 | Check `games-backend-gamma` is running and bound to `127.0.0.1:8004` |
| Container logs show `exec format error` | Rebuild through `scripts/deploy-gcp.sh`; images must be `linux/amd64` for the VM |
| SPA route returns API JSON unexpectedly | Confirm the path is not under a protected API prefix |
| Generation fails with Gemini `404 Not Found` | Check VM `GEMINI_MODEL`, `GEMINI_PREMIUM_MODEL`, `REMOTE_CONFIG_URL`, and `frontend/public/config.json`; all model settings should be `gemini-2.5-flash-lite` |
