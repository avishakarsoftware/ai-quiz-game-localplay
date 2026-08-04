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

### Built: `scripts/regression.py` (2026-08-04)

```bash
make test-prod            # or: cd frontend && npm run test:prod
make test-prod-deep       # adds the catalog sweep + one real playthrough
.venv/bin/python scripts/regression.py --target gamma --deep --verbose
.venv/bin/python scripts/regression.py --target prod --deep --games impostor,quiz --no-play
```

Two deliberate deviations from the sketch above, both about not lying in the report:

- **`GAMES (deep)` sweeps all 38 entries but starts only one game.** `/room/create` is free — the
  `COST_ROOM` debit lands on `START_GAME` — so per game it asserts *room create → organizer lobby
  reachable → minimum-player gate refuses to start (before charging) → `CANCEL_GAME` and the room
  is verified gone*. Starting all 38 would burn ~380 sparks across ~14 minted wallets and hold 38
  rooms against the shared `MAX_ROOMS=50` cap; the gate already proves the engine was constructed
  and the room is live. `--play <id>` starts one game for real (default `quiz`: two `QA-*` players
  join, first `QUESTION` broadcast asserted, spark debit asserted) on its own fresh wallet.
- **WARN is a distinct verdict from FAIL.** Cert renewal windows, an expired promo still advertised
  in `/config/public`, and drift in files nothing currently links to are reported but do not fail
  the run, so "is prod healthy right now" stays a yes/no question.

## 4. Layer-by-layer requirements

**L1/L2 (backend + vitest)** — keep as is; fill gaps found by the coverage guard in §5.

**L3/L4 (Playwright)** — one canonical "play every game" spec, parameterised over the catalog
rather than hand-listing games, so a new game is covered the moment it ships. Per game, assert:
1. A room can be created for it.
2. Its first playable screen renders (not an error, not a blank).
3. Its minimum-player gate behaves.
4. Rules metadata resolves.

**BUILT (2026-08-04): `frontend/e2e/all-games.spec.ts`.** Two tests per catalog game —
`catalog · <id>` (rules payload well-formed, picker tile present, Rules modal renders the catalog's
own title) and `play · <id>` (room created, min-player gate refuses Start below the minimum, first
playable screen renders). The game list comes from `GET /catalog` via top-level await, so there is
no hardcoded catalog anywhere in the spec — the guard in §5 fails if one appears.

    npm run test:e2e:all-games         # L3, backend :9100 + vite :9200
    npm run test:e2e:all-games:gamma   # L4

Per-game exceptions (prepared content, settle timings, waivers) live in `frontend/e2e/game-coverage.json`,
which is an exception list, never a catalog. **Do not point this suite at prod** — it creates a room
per game; §2/§3 own the prod path.

Two things this suite had to learn the hard way, both worth knowing before touching it:
- **Rooms must be handed back.** `MAX_ROOMS` is 50 and `ROOM_TTL_SECONDS` is 1800, so a 38-game run
  leaves 38 rooms squatting and the next run reports 429 for two thirds of the catalog. There is no
  REST endpoint for it, so teardown speaks the organizer socket: `AUTH` then `CANCEL_GAME`.
- **Local runs need their own `DB_DIR`.** With a shared `backend/data/`, a concurrent `pytest` run
  reset wallets mid-suite and four games failed with "insufficient balance" on wallets that had been
  created seconds earlier with the full signup bonus. Same symptom as a real economy bug, entirely
  an artefact of the shared file.

**L5 (prod)** — §2 and §3.

**L6 (visual)** — Playwright screenshot diffing. Mask volatile regions (room codes, timers, spark
balances) or every run diffs. Snapshots live beside the spec. **Built — see §7 for the suite, what
it masks, and how to review and accept a diff.**

## 5. Guard: coverage cannot silently regress

A test that fails when a catalog game has **no** e2e coverage. This is what makes the suite
self-maintaining: adding a game without a test breaks the build rather than quietly shipping
untested. Allow an explicit, commented waiver list for genuinely untestable cases (e.g. anything
needing a real camera) — a waiver is a decision, an omission is an accident.

**BUILT (2026-08-04): `backend/tests/test_e2e_game_coverage.py`.** pytest, not vitest, because the
catalog is backend-authoritative: `game_catalog.py` is the source and `frontend/src/gameModes.ts` is
a mirror, so a vitest guard reading the mirror would be blind to exactly the drift that shipped the
occasion bingos broken. pytest imports `GAME_CATALOG` in-process and runs in the same commit that
adds a game.

Since the Playwright suite covers every game automatically, "no coverage" cannot mean "no test was
written" — it means **not drivable**. So the guard checks drivability preconditions per game and
requires a waiver for anything that fails one:

| Check | Catches |
|---|---|
| `game_type ∈ SUPPORTED_ROOM_GAME_TYPES` | variant ids that no room can be created for |
| rules payload has title/summary/sections/min-players | the `catalog · <id>` leg silently having nothing to assert |
| a `GameModeConfig` exists in `gameModes.ts` | the occasion-bingo failure: in the catalog, absent from the picker |
| `players.min ≤ max_players` (8) | a game the suite cannot field enough players for |
| `interaction ∈ {default, pass_and_play}` | a NEW interaction model the suite has never been taught |
| no catalog id appears as a literal in the spec | someone "fixing" a new game by hardcoding it |
| waivers are non-stale, reasoned, and carry `revisit_when` | permanent-by-accident waivers |

One waiver today: `photo_clue` play-through (real camera). Its catalog leg and room creation still run.

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
- **`test.use({ reducedMotion: 'reduce' })` does not reach the `page` fixture** on Playwright 1.60
  (verified: `matchMedia` still reports no-preference). `page.emulateMedia()` and
  `browser.newContext({ reducedMotion })` both work. This silently left the podium fireworks canvas
  running under the visual suite, sprinkling ~1,500 random pixels into a "stable" baseline.
- **Playwright's default screenshot `threshold` (0.2) is too loose to notice a theme change.**
  With it, moving the Velvet accent from `#FF2E7A` to `#FF3E6A` diffed *nothing* across 18
  baselines. The visual suite pins `threshold: 0.02`.
- **Tailwind *layout* utility classes are not compiled** (no `@tailwindcss/vite`/postcss plugin), in
  dev *and* in the shipped build: `flex`, `flex-col`, `min-h-dvh` etc. resolve to nothing, so layout
  comes from the hand-written CSS in `src/index.css`. Screenshots therefore look "wrong" in places
  (e.g. the question countdown sits under the Q-counter instead of beside it) — that is the app as it
  actually ships, and the baselines record it deliberately. Enabling the plugin diffs 8 of 10 tests;
  it was tried and reverted. The *colour* classes (`text-[--text-tertiary]` &c.) **are** live as of
  2026-08-04 via hand-written shims — see §8a.

## 7. L6 visual regression — running it, and reviewing a diff

**Suite**: `frontend/e2e/visual-regression.spec.ts` · baselines in
`frontend/e2e/visual-regression.spec.ts-snapshots/` · capture-time CSS in
`frontend/e2e/visual-stabilize.css` · runner `scripts/visual-regression.sh`.

```bash
cd frontend
npm run test:e2e:visual            # compare against committed baselines
npm run test:e2e:visual:update     # accept new baselines (only after reviewing the diff)
npm run test:e2e:visual -- --project chromium-desktop   # extra args pass through to playwright
```

The runner owns its own stack — a throwaway backend on **:9310** with a temp SQLite dir, and a vite
dev server on **:5199** — so it can neither touch your dev database nor collide with `make dev`
(9100/9200). **Never point this at gamma or prod**: they generate quiz text with an LLM, so no
question screen there can be a stable baseline.

9 surfaces × 2 viewports (`chromium-desktop` 1440×1000, `chromium-mobile` Pixel 5) = 18 baselines:
catalog, TV launcher (play-now + all-games), Get Sparks paywall, settings drawer, lobby with QR,
organizer question, player question, podium.

**What is masked, and why it is deliberately small.** A mask is a hole in coverage, so volatile
content is *pinned* wherever it can be and masked only when it genuinely cannot: room code, the
join URL that contains it, the join QR, countdown timers, the spark balance, podium scores (speed-
weighted), and Google's remotely-drawn sign-in button (its script is blocked, so a run needs no
third-party network). Everything else is made deterministic instead — sequential joins for a stable
roster, seeded `Math.random` for avatars, an answer plan whose *ranking* cannot depend on speed, and
`reducedMotion` so canvas effects never run. Masked boxes whose text width varies get their width
pinned by `visual-stabilize.css`, otherwise the diff just moves to the edge of the pink rectangle.

**Measured noise floor: 0 pixels.** Two consecutive runs are byte-identical on every surface, so the
suite runs with `maxDiffPixels: 250` and `threshold: 0.02`.

### Reviewing a failure

1. Read *which* surface failed. The test name tells you the screen and the project tells you the
   viewport.
2. Open the report and look at the three images side by side:
   ```bash
   cd frontend && npx playwright show-report
   ```
   Artifacts also land in `frontend/test-results-visual/<test>/` as
   `<name>-expected.png`, `-actual.png`, `-diff.png`.
3. Classify it — this is the only decision that matters:
   - **Intended change** (you edited the theme, a layout, or copy): accept it, see below.
   - **Regression**: fix the code. Do not update the baseline.
   - **Noise** (the same surface diffs on a re-run with no code change): the masking is wrong —
     find the volatile region and pin or mask it. Raising `maxDiffPixels` / `threshold` is how a
     visual suite becomes the thing everyone ignores; the env overrides
     (`VISUAL_MAX_DIFF_PIXELS=0`, `VISUAL_PIXEL_THRESHOLD=…`) exist to *measure* noise, not to hide
     it.
4. Confirm it is not flake before accepting anything: `npm run test:e2e:visual` twice in a row.
   A suite that passes once is not passing.

### Accepting a new baseline

```bash
cd frontend
npm run test:e2e:visual:update
npm run test:e2e:visual            # must now be green with no --update
git add e2e/visual-regression.spec.ts-snapshots
```

Commit the PNGs **in the same commit as the change that caused them**, and say in the message which
surfaces moved and why. A baseline update with no explanation is indistinguishable from a regression
someone rubber-stamped. Baselines are per-platform (`…-darwin.png`): regenerate on the same kind of
machine, and if a new OS/arch joins, add its baselines rather than loosening the tolerances.

## 8. Standing hazards the suites revealed (2026-08-04)

Ranked by what they'd cost if left alone.

### 8a. Tailwind utility classes are inert — colours repaired, layout utilities still dead

`tailwindcss@^4` is a devDependency and `src/index.css` starts with `@import "tailwindcss"`, but
Tailwind v4 needs **either** `@tailwindcss/vite` **or** `@tailwindcss/postcss` and **neither is
installed**. Verified against the shipped bundle: `.flex-col`, `.justify-between`, `.min-h-dvh`,
`.items-center` appear **zero** times in `dist/assets/*.css`.

Measured blast radius: **~1,452 utility occurrences across ~49 files, 77 distinct utilities**
(`flex` ×193, `text-center` ×76, `mb-4` ×66 …). The app's real styling is the hand-written CSS in
`index.css`, tuned to look right *without* them.

**"Just enable Tailwind" is the DANGEROUS option**, and this is measured, not theoretical: it was
tried on 2026-08-04 and reverted. Installing `@tailwindcss/vite` applied ~1,450 dormant declarations
at once and diffed **8 of 10 visual baselines**, including type sizes on nearly every screen. That is
a layout regression, not an improvement.

**Resolved instead (option C, 2026-08-04):** only the **colour** classes were revived, via 14
hand-written escaped rules at the end of `index.css`. Those **204 occurrences** across 15 classes
were the subset whose deadness was a genuine visual bug — every `text-[--text-tertiary]` (×115) and
`text-[--text-secondary]` (×51) painted full-strength body colour, so captions, hints and helper text
had **no hierarchy at all**. Reviving them changed **0.03% of pixels and zero layout**; 6 baselines
updated after review. Three of the classes turned out to reference variables that never existed
(`--accent-magenta`, `--panel-border`, `--warning`) — those call sites were **fixed**, not shimmed,
since shimming a typo just hides it.

The remaining ~1,450 layout/spacing utilities are still inert and still dead code, so **the rule for
new code is unchanged: do not add Tailwind utility classes.** Style with the hand-written CSS.

`src/__tests__/tailwindNotCompiled.test.ts` guards all of it (4 tests) and each assertion has been
mutation-tested to prove it actually fails:
- the plugin is still absent, and the dead-class count is not growing;
- every `[--var]` colour class used in `.tsx` has a matching shim rule;
- every shim rule's **body** resolves a **declared** variable (a shim named `--text-tertiary` whose
  body says `var(--text-tertiarry)` renders as the inherited colour while looking correct at the call
  site — this exact bug passed the first version of the test);
- no shim rule exists for a class nobody uses.

### 8b. `frontend/e2e/` is not typechecked

`tsconfig.app.json` has `include: ["src"]`, so nothing under `e2e/` is ever type-checked — and a
type error there is invisible to `npm run build`. One is currently live in `liveGameHarness.ts`
(`options.reloadOnly` against a type that no longer has it). Harmless at runtime, but the whole
Playwright layer has no type safety. Compounds the fact that bare `npx tsc --noEmit` checks nothing.

### 8c. The shared dev SQLite file makes local suites interfere

`backend/data/revelry.db` is shared by pytest, the local e2e suite, and `make dev`. Two agents
running suites concurrently produced *four* "insufficient balance" failures that looked exactly like
an economy bug and were pure cross-contamination, plus a genuine flake in
`test_e2e.py::TestTokenEconomyE2E::test_history_scoped_to_wallet`, which asserts an **absolute row
count** and so breaks whenever anything else writes. Give each suite its own `DB_DIR`; the visual
runner already does.

### 8d. `test_e2e.py` is flakier than documented

Three consecutive runs on unmodified master: 20 pass (10.9s) → 1 fail (29.4s) → 3 fail (57.4s),
runtime roughly doubling each time. 8c is one confirmed contributor. Do **not** bisect it one run
per step — that has already produced a confidently wrong conclusion once.
