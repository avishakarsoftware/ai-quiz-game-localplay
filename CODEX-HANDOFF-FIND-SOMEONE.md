# Codex Handoff — Find Someone Who

Date: 2026-06-12

## Current State

Implemented standalone LocalPlay MVP for `find_someone` / **Find Someone Who**.

> **Status update (stale handoff):** This document is historical. Find Someone Who is now committed (engine `backend/find_someone_engine.py`, component `frontend/src/components/FindSomeoneGame.tsx`) and `SPEC-GAME-FIND-SOMEONE-WHO.md` is the current source of truth. The "not committed / not deployed" notes below were only true at the 2026-06-12 handoff.

Not committed. _(at time of handoff — now committed)_
Not deployed.
Dev server was started for smoke testing and then stopped.

## Key Changes

- Added backend engine:
  - `backend/find_someone_engine.py`
- Added backend tests:
  - `backend/tests/test_find_someone_engine.py`
- Wired backend runtime:
  - `backend/config.py`
  - `backend/main.py`
  - `backend/socket_manager.py`
- Added frontend runtime UI:
  - `frontend/src/components/FindSomeoneGame.tsx`
- Wired frontend surfaces:
  - `frontend/src/gameModes.ts`
  - `frontend/src/types.ts`
  - `frontend/src/components/organizer/GameSelectScreen.tsx`
  - `frontend/src/pages/OrganizerPage.tsx`
  - `frontend/src/pages/PlayerPage.tsx`
  - `frontend/src/pages/SpectatorPage.tsx`
  - `frontend/src/pages/PartyHubPage.tsx`
- Updated docs/specs:
  - `SPEC-GAME-FIND-SOMEONE-WHO.md`
  - `SPEC.md`
  - `SPEC-REVELRY-INTEGRATION.md`
  - `BACKLOG.md`

## Implemented Behavior

- Safe default prompt deck.
- Per-player generated bingo-style cards.
- `tap_confirm` confirmation mode.
- `honor` confirmation mode supported in engine.
- Players mark a cell by choosing another player.
- Matched player can confirm or deny.
- Server validates first line, four corners, and blackout claims.
- Blackout is terminal and moves game to `PODIUM`.
- Starts with one player so it can support future check-in auto-start.
- Late joiners can enter active games and receive a fresh card.
- Reconnects include private Find Someone state.
- Host and spectator receive public aggregate sync only.

## Revelry Boundary

LocalPlay only was changed.

Find Someone Who remains `host_app_supported = false` for Revelry for now.

Revelry still needs a future host-owned setting:

- Set Find Someone Who as default check-in game.
- Auto-start when first guest checks in, default on.
- Reuse existing active LocalPlay session for later guests.
- Pass existing nickname/session token when available to prevent duplicates.

## Verification Done

Passed:

```bash
.venv/bin/pytest backend/tests/test_find_someone_engine.py
.venv/bin/python -m py_compile backend/find_someone_engine.py backend/main.py backend/socket_manager.py backend/config.py
cd frontend && npm run build
```

Build warnings were existing-style Vite chunk-size/dynamic-import warnings.

Browser smoke:

- Opened `http://127.0.0.1:5175/`.
- Confirmed game picker renders **Find Someone Who**.
- Click handler fires.
- Room creation did not complete locally because the browser had no signed-in wallet/sparks and showed `Room Error`.

## Known Follow-Ups

- Do a full end-to-end room test after restart with a valid local/gamma wallet/session.
- Commit when satisfied.
- Deploy to gamma only after commit and a real room-flow test.
- Later: add AI/custom prompt authoring if desired.

## Suggested Next Commands

```bash
git status --short
.venv/bin/pytest backend/tests/test_find_someone_engine.py
cd frontend && npm run build
```

