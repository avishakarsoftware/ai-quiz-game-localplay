# SPEC-TESTING — the test architecture, and what is safe to run against production

Status: **Spec + framework build in progress (2026-07-28).** Owner: Avi.
Goal: Avi can run one command against **prod** at any time and get a trustworthy regression report.

## 0. What already exists (this is not greenfield)

- **Backend**: 1269 pytest tests. Engines, endpoints, socket flows, Supabase parity.
- **Frontend**: 375 vitest tests.
- **Playwright**: 29 specs in `frontend/e2e/`, incl. a live harness (`liveGameHarness.ts`),
  gamma-live game specs, `preprod-live-regression`, store screenshots, legal pages.
- **Remote smoke**: `scripts/smoke-remote.py` — already prod-safe, but narrow (one quiz + an
  idempotency check).

Measured coverage gap (2026-07-28): **32 of 38 catalog games are referenced in some e2e spec.**
The 6 with none are the newest: `baby_bingo`, `wedding_bingo`, `holiday_bingo`, `road_trip_bingo`,
`odd_question`, `impostor`.

So the work is **consolidation and gap-filling**, not invention.

## 1. The layers

| Layer | Runs where | Speed | Owns |
|---|---|---|---|
| **L1 unit** | local, CI | ms | Engine rules, pure functions, component behaviour |
| **L2 integration** | local, CI | s | HTTP endpoints, socket flows, DB parity |
| **L3 e2e (local)** | local dev server | ~min | Real browser, real WebSocket, one process |
| **L4 live (gamma)** | deployed gamma | ~min | The same flows against real infra + Postgres |
| **L5 prod regression** | deployed prod | ~min | **Read-mostly**. Is prod healthy and correct *right now* |
| **L6 visual** | local or gamma | ~min | Screenshot diffs; catches layout/theme regressions |

**Rule: a failure must be attributable.** If L5 fails but L4 passes, the fault is prod
configuration or data, not code. Keep the suites structurally identical so that inference holds.

## 2. The production-safety contract — read this before writing any L5 test

Prod is a live storefront in 177 countries. These rules are **not negotiable**, and a test that
breaks one is a defect regardless of what it verifies.

**Allowed on prod**
- `GET` on public endpoints (`/health`, `/catalog`, `/config/public`, legal pages).
- Creating a **fresh synthetic wallet** per run via a random UUID device id.
- Creating rooms and playing games **as that synthetic wallet only**.
- Unauthenticated probes of protected endpoints to assert they *reject* (401/403/400).

**Forbidden on prod**
- Any real purchase. Never drive Stripe checkout to completion, never call an IAP flow.
  Payment verification is limited to asserting the rails *reject* bad input
  (`/webhook/stripe` → 400, `/webhook/revenuecat` → 401).
- Touching any wallet, room, or user not created by this run.
- `DELETE /account` on anything but a wallet the run just created.
- Admin endpoints, config mutation, migrations.
- Leaving a room running. Every created room must be ended or abandoned to its TTL.

**Budget awareness.** Rooms cost `COST_ROOM` (10) sparks and a fresh wallet gets
`SIGNUP_BONUS_TOKENS` (20–30). So **a synthetic wallet funds ~2–3 rooms**. An L5 suite that
creates a room per game would run dry and report false failures. Either mint a fresh device id per
game or assert the spark-exhaustion path deliberately — never accidentally.

**Traceability.** Every synthetic actor must be identifiable so real analytics and support can
distinguish it: nicknames prefixed `QA-`, device ids logged in the report. If a synthetic room is
ever seen by a real user, we must be able to explain it.

## 3. The prod regression report

One command, human-readable output, non-zero exit on failure:

```bash
npm run test:prod            # read-mostly, safe any time
npm run test:prod -- --deep  # also plays games as a synthetic wallet
```

Report shape — grouped, with an explicit verdict per line so a glance is enough:

```
REVELRY GAMES · PROD REGRESSION · 2026-07-28 01:42 UTC
target: https://gamesapi.revelryapp.me   commit: b0c1fc03

INFRA            5/5   health 200 · SPA served · legal pages · CDN · TLS
CATALOG         38/38  all games present, rules resolvable
ECONOMY          6/6   wallet create · signup bonus · room debit · idempotent retry
PAYMENT RAILS    2/2   stripe 400 (keys live) · revenuecat 401 (secret set)
SECURITY         4/4   ad-reward 403 · admin 401 · organizer token required · CORS
GAMES (deep)    38/38  every catalog game reached its first playable screen
FLAGS            4/4   gifting=false achievements=false referral=true ads=false

VERDICT: PASS (59 checks, 0 failed, 41s)
```

**The `GAMES (deep)` line is the valuable one.** "Every game reaches its first playable screen"
is the single assertion that would have caught the occasion-bingo breakage, the `odd_one_out`
collision, and the Impostor room-create rejection — all three shipped tonight and all three were
invisible to unit tests.

## 4. Layer-by-layer requirements

**L1/L2 (backend + vitest)** — keep as is; fill gaps found by the coverage guard in §5.

**L3/L4 (Playwright)** — one canonical "play every game" spec, parameterised over the catalog
rather than hand-listing games, so a new game is covered the moment it ships. Per game, assert:
1. A room can be created for it.
2. Its first playable screen renders (not an error, not a blank).
3. Its minimum-player gate behaves.
4. Rules metadata resolves.

**L5 (prod)** — §2 and §3.

**L6 (visual)** — Playwright screenshots at the four store viewports. Mask volatile regions (room
codes, timers, spark balances) or every run diffs. Snapshots live beside the spec.

## 5. Guard: coverage cannot silently regress

A test that fails when a catalog game has **no** e2e coverage. This is what makes the suite
self-maintaining: adding a game without a test breaks the build rather than quietly shipping
untested. Allow an explicit, commented waiver list for genuinely untestable cases (e.g. anything
needing a real camera) — a waiver is a decision, an omission is an accident.

## 6. Known constraints, honestly

- **`test_e2e.py::TestExportImportE2E::test_generate_export_import_play` is a pre-existing flake.**
  Don't bisect a flaky test one run per step; that produced a confidently wrong answer once already.
- **TestClient websockets need `socket_manager.allowed_origins = []`** and the route is
  `/ws/{code}/{client_id}?organizer=true` + an `AUTH` message.
- **`receive_json()` blocks forever** on a missing broadcast — always use
  `tests/ws_test_utils.recv_until`.
- **`npx tsc --noEmit` checks NOTHING** — the root tsconfig is `files: []` + references. Use
  `npm run build` or `tsc -p tsconfig.app.json`. This hid two real errors for a whole session.
- **Gamma has no Stripe keys**, so `/webhook/stripe` is 503 there and 400 on prod. An L4/L5 shared
  assertion must account for that difference.
- **Photo games can't be fully automated** (real camera). Waiver, documented.
