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
npm run build
```

- `npm test` runs Vitest unit/component tests.
- `npm run test:e2e` runs Playwright browser UX smoke tests from `e2e/`.
- `npm run test:e2e:gamma` runs a desktop/mobile Playwright smoke against `https://gamesapi-gamma.revelryapp.me`.
- `npm run test:e2e:gamma:revelry` runs a gamma-only Revelry embedded party regression for Drawing re-entry and custom Quiz image upload; set `REVELRY_GAMMA_PARTY_GAMES_URL_FILE` to a short-lived gamma party games URL file first.
- `npm run build` type-checks and builds the production bundle.

## Media Components

Generated quiz images should render through `src/components/media/GameImage.tsx`
instead of direct `backgroundImage` styling. `GameImage` keeps stable image
dimensions, shows loading/error states, and uses `src/utils/media.ts` so media
URLs work from both backend-served SPA deployments and the IONOS-hosted
frontend.

## Playwright UX Tests

The Playwright suite starts the local Vite dev server automatically. Current coverage includes the DrawingGame organizer prompt screen and quiz-variant prompt screens on desktop and mobile, with assertions for aligned controls, no horizontal page overflow, no overlap with fixed menu/spark controls, variant generation `mode` payloads, and visual snapshots for DrawingGame.

The gamma smoke skips the local dev server and points Playwright at the deployed backend-served SPA:

```bash
npm run test:e2e:gamma
```

The Revelry gamma flow is stateful and desktop-only because it mutates one disposable gamma party:

```bash
REVELRY_GAMMA_PARTY_GAMES_URL_FILE=/path/to/gamma_party_games_url.txt npm run test:e2e:gamma:revelry
```

When a deliberate visual change alters a snapshot, refresh baselines with:

```bash
npm run test:e2e -- --update-snapshots
```
