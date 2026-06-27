# LocalPlay Frontend

React + TypeScript + Vite frontend for the LocalPlay host, player, and spectator surfaces.

## Commands

```bash
npm install
npm run dev
npm test
npm run test:e2e
npm run test:e2e:gamma
npm run test:e2e:gamma:revelry
npm run test:e2e:preprod-live
npm run test:e2e:preprod-revelry
npm run test:e2e:preprod-ux
npm run build
```

- `npm test` runs Vitest unit/component tests.
- `npm run test:e2e` runs Playwright browser UX smoke tests from `e2e/`.
- `npm run test:e2e:gamma` runs a desktop/mobile Playwright smoke against `https://gamesapi-gamma.revelryapp.me`.
- `npm run test:e2e:gamma:revelry` runs a gamma-only Revelry embedded party regression for Drawing re-entry and custom Quiz image upload; set `REVELRY_GAMMA_PARTY_GAMES_URL_FILE` to a short-lived gamma party games URL file first.
- `npm run test:e2e:preprod-live` runs the opt-in heavy live game regression suite. Set `PREPROD_LIVE=1` and `PLAYWRIGHT_BASE_URL` first.
- `npm run test:e2e:preprod-revelry` runs the opt-in Revelry party hub matrix. Set `PREPROD_REVELRY=1` and `REVELRY_GAMMA_PARTY_GAMES_URL_FILE` first.
- `npm run test:e2e:preprod-ux` runs the opt-in live screenshot UX audit. Set `PREPROD_UX_AUDIT=1` and `PLAYWRIGHT_BASE_URL` first.
- `npm run build` type-checks and builds the production bundle.

## Media Components

Generated quiz images should render through `src/components/media/GameImage.tsx`
instead of direct `backgroundImage` styling. `GameImage` keeps stable image
dimensions, shows loading/error states, and uses `src/utils/media.ts` so media
URLs work from both backend-served SPA deployments and the IONOS-hosted
frontend.

## Playwright UX Tests

The Playwright suite starts the local Vite dev server automatically unless `PLAYWRIGHT_BASE_URL` points at gamma/prod. Current coverage includes the DrawingGame organizer prompt screen, quiz-variant prompt screens, and a prompt UX audit across AI-backed setup screens on desktop and mobile, with assertions for visible random-topic dice controls, aligned controls, no horizontal page overflow, no overlap with fixed menu/spark controls, variant generation `mode` payloads, and visual snapshots for DrawingGame.

The gamma smoke skips the local dev server and points Playwright at the deployed backend-served SPA:

```bash
npm run test:e2e:gamma
```

The Revelry gamma flow is stateful and desktop-only because it mutates one disposable gamma party:

```bash
REVELRY_GAMMA_PARTY_GAMES_URL_FILE=/path/to/gamma_party_games_url.txt npm run test:e2e:gamma:revelry
```

For big production pushes, run the fuller Revelry party hub matrix against the same disposable gamma party:

```bash
PREPROD_REVELRY=1 REVELRY_GAMMA_PARTY_GAMES_URL_FILE=/path/to/gamma_party_games_url.txt npm run test:e2e:preprod-revelry
```

This matrix loads the embedded Revelry Games hub, verifies the searchable/sorted catalog UI and category filters, then starts every launchable game returned by the live Revelry catalog. It saves deterministic party-scoped content for Quiz, Most Likely To, Drawing, Housie, and Random Chit, quick-starts quick-start-only games, and verifies organizer/player/spectator launch tokens for each active session. If a newly exposed Revelry game lacks a harness fixture, the test fails so bridge coverage is updated with the rollout.

The pre-production live regression is the heavier browser-driven safety net for big production pushes. It creates disposable rooms/content through the live API, joins real player tabs, starts the game, and verifies one meaningful action or handoff for the deterministic game runtimes. Run it with one worker against gamma unless intentionally validating prod:

```bash
PREPROD_LIVE=1 PLAYWRIGHT_BASE_URL=https://gamesapi-gamma.revelryapp.me npm run test:e2e:preprod-live
```

Coverage currently includes Quiz runtime, Most Likely To, Housie, Bingo/Baby Bingo, Musical Chairs, Bluff, Two Truths and a Lie, Story Chain, Common Ground, Who Am I, and Chit Pull. Quiz variants share the Quiz runtime and remain covered by prompt/setup audits plus the Quiz live scenario. Drawing is tracked in the suite but skipped until the backend exposes a deterministic `/drawing/import` endpoint; using AI generation here would make the pre-prod suite flaky and token-dependent.

For a lighter visual pass over representative live mobile states, run:

```bash
PREPROD_UX_AUDIT=1 PLAYWRIGHT_BASE_URL=https://gamesapi-gamma.revelryapp.me npm run test:e2e:preprod-ux
```

By default screenshots are written to `/private/tmp/localplay-preprod-ux-audit`; override with `PREPROD_UX_AUDIT_DIR`.

When a deliberate visual change alters a snapshot, refresh baselines with:

```bash
npm run test:e2e -- --update-snapshots
```
