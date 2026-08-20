# SPEC-ROOM-LIFECYCLE-RELIABILITY

Status: **Implemented baseline, active hardening track** (updated 2026-08-20).

Owner: LocalPlay / Revelry Games.

Purpose: make party-scale room creation, lobby waiting, reconnect, reset, cleanup, and live QA boringly reliable across every game. This spec owns the cross-game behavior; individual game specs should reference it instead of redefining room/socket policy.

## 1. Product Contract

Rooms are party infrastructure, not a single-game throwaway detail.

- A QR/link that guests scanned should remain useful across a short sequence of games when the host uses in-place replay/next-game actions.
- Guests who are sitting on a completed game's final-results screen should be moved into the next lobby by `ROOM_RESET` without rescanning.
- A host who waits while announcing or explaining should not lose the whole lobby just because phones slept or networks wobbled.
- The lobby must make connected versus preserved/offline seats understandable. Start gates count connected players only.
- Every organizer lobby must show the actual game title, an obvious **Back to games** action, Rules, and Start state feedback. The hamburger Home entry is secondary, not the only escape hatch.
- Host-app launches, including Revelry, must keep raw LocalPlay economy/account/share chrome hidden and use the host app's party-aware guest join URL when one is provided.

## 2. Runtime Requirements

### Lobby Seats

- In `LOBBY`, transient player disconnects preserve a seat for `LOBBY_RECONNECT_GRACE_SECONDS` (default 90 minutes).
- `player_count` is the number of connected/start-ready player sockets.
- `players` includes connected and preserved/offline seats so hosts know who may need to reopen their phone.
- `START_GAME` prunes stale seats before checking the game minimum and then force-prunes any remaining offline seats before materializing gameplay state.
- The host may explicitly remove offline seats before the grace expires. This is lobby-only and must broadcast the updated roster.

### Room Reset

- `RESET_ROOM` may reuse a completed room when the target game type is resettable.
- Reset preserves `room_code`, organizer socket, player sockets, and join URLs.
- Reset clears prior runtime/game state and broadcasts `ROOM_RESET` to organizer, players, and spectators.
- Players on previous podium/final-results screens must render the new lobby and be counted as connected if their socket is live.
- `RESET_ROOM` must not run from active gameplay or from a non-organizer client.

### Cleanup And Capacity

- `MAX_ROOMS` is a hard process-local safety limit. Room creation must fail closed with a clear 429 when the cap is reached.
- Host cancellation must immediately remove the room from the process map and snapshot store so capacity is recovered without waiting for TTL cleanup.
- Cleanup probes in live smoke tests must prove rooms are gone by reconnecting to the same room code and seeing `Room not found`.
- Harnesses must cancel every room they create; leaked test rooms are a production risk because they consume the same room cap as real parties.

### Host-App Behavior

- Host-app lobbies use the same shared lobby component as standalone lobbies.
- In host-app mode, QR/copy/share uses the validated host-app `guest_join_url`; raw `/join/{room_code}` links stay hidden unless no host app is involved.
- Returning to games from a host-app lobby returns to the LocalPlay party hub for that host app, after the same interruption warning used by standalone.

## 3. Test Matrix

Required gates:

- Backend socket scenarios:
  - organizer disconnect/reclaim
  - late join during running games where allowed
  - ignored reset outside podium
  - podium-to-next-game `ROOM_RESET` moves existing players into next lobby
  - podium-to-default/config-driven game `ROOM_RESET` keeps live players startable without a new content id
  - room-code uniqueness
  - `MAX_ROOMS` fails closed and host cancellation recovers capacity
- Frontend unit tests:
  - lobby title uses selected game name
  - missing game title does not show the old generic "Game Lobby" fallback
  - connected/offline seat display and explicit offline cleanup control
  - host-app lobby hides raw share URL and uses host-app join affordance
- Local Playwright:
  - `npm run test:e2e:all-games` creates, gates, starts, and tears down every catalog game.
- Gamma Playwright:
  - `npm run test:e2e:gamma` for desktop/mobile catalog/media smoke.
  - `npm run test:e2e:all-games:gamma` for deployed all-game coverage at modest parallelism.
  - `PREPROD_LIVE=1 PLAYWRIGHT_BASE_URL=https://gamesapi-gamma.revelryapp.me npm run test:e2e:preprod-live` for action-level gameplay.
- Load smoke:
  - `scripts/load-room-smoke.py` creates disposable rooms, opens organizer/player WebSockets, holds briefly, cancels, and verifies cleanup by probing the room codes.
  - With `--reconnect-check`, the harness closes and reopens one lobby player per room using the issued session token and requires a `RECONNECTED` lobby sync before cleanup.

Gamma all-games is not the concurrency test. It intentionally runs with lower parallelism than local so failures stay attributable to deployed behavior. Concurrency is owned by the load smoke.

## 4. Operational Runbook

Before production deploys that touch room creation, WebSockets, lobby reconnect, reset, room cleanup, or shared organizer/player/spectator surfaces:

1. Run backend tests excluding the known legacy E2E file.
2. Run focused socket scenarios.
3. Run frontend vitest and `npx tsc -b`.
4. Run local all-games Playwright.
5. Run local load smoke.
6. Deploy to gamma.
7. Run gamma smoke, gamma load smoke, gamma all-games, and pre-prod live regression.
8. Promote only after failures are either fixed or explicitly classified as a harness/deploy-environment issue with evidence.

Prod load smoke requires explicit approval and must use modest room/player counts because it creates live disposable lobbies.

## 5. Open Hardening

- Add a Revelry-aware mobile sleep/lobby-lull/reopen Playwright scenario.
- Add runtime metrics for room create latency, socket join latency, reset delivery, cancellation cleanup time, and reconnect success/failure.
- Add a bounded soak test that keeps rooms open across the lobby grace window using fake timers locally and a short-duration config in gamma.
- Expand reset coverage to one Bingo/Housie-family game.
