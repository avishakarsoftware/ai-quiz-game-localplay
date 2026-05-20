# LocalPlay Frontend

React + TypeScript + Vite frontend for the LocalPlay host, player, and spectator surfaces.

## Commands

```bash
npm install
npm run dev
npm test
npm run test:e2e
npm run build
```

- `npm test` runs Vitest unit/component tests.
- `npm run test:e2e` runs Playwright browser UX smoke tests from `e2e/`.
- `npm run build` type-checks and builds the production bundle.

## Playwright UX Tests

The Playwright suite starts the local Vite dev server automatically. Current coverage includes the DrawingGame organizer prompt screen on desktop and mobile, with assertions for aligned controls, no horizontal page overflow, no overlap with fixed menu/spark controls, and visual snapshots.

When a deliberate visual change alters a snapshot, refresh baselines with:

```bash
npm run test:e2e -- --update-snapshots
```
