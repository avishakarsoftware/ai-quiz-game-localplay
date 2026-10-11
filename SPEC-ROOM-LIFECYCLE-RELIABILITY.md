# SPEC-ROOM-LIFECYCLE-RELIABILITY

Status: **Implemented baseline, active hardening track** (source reconciled 2026-10-10; live status not rechecked).

Owner: LocalPlay / Revelry Games.

Purpose: make party-scale room creation, lobby waiting, reconnect, reset, cleanup, and live QA boringly reliable across every game. This spec owns the cross-game behavior; individual game specs should reference it instead of redefining room/socket policy.

## 1. Product Contract

Rooms are party infrastructure, not a single-game throwaway detail.

- Standalone QR/room links remain useful across in-place replay/next-game actions. Revelry-managed continuation uses the party-aware join URL and a fresh durable session from its hub.
- Standalone guests on final results move into the next lobby by `ROOM_RESET` without rescanning. Managed clients return to the party hub; roster reuse across a fresh managed session remains future work.
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

### Active-Game Reconnect

- Both player seat-reclaim paths (offline seat and replacement socket) restore the current view.
- A quiz reconnect during `QUESTION` reports `has_answered` without exposing the answer. An
  already-submitted answer returns to the waiting view rather than offering another answer.
- `LEADERBOARD` reconnect includes current individual/team standings, `has_answered`, and the
  revealed quiz answer/index. `PODIUM` reconnect includes standings and WMLT superlatives.
- Question timers may end their own round without cancelling themselves before the results
  broadcast finishes.

### Room Reset

- Standalone `RESET_ROOM` may reuse a completed room when the target game type is resettable. Managed host-app rooms return through the authenticated party games hub to create a fresh registered session; direct managed `RESET_ROOM` fails before mutation so host-app catalog rules and prior results remain consistent.
- Reset preserves `room_code`, organizer socket, player sockets, and join URLs.
- Reset clears prior runtime/game state and broadcasts `ROOM_RESET` to organizer, players, and spectators.
- Reset stages a lobby for free. Only `START_GAME`, after its connected-player gates pass, charges a room fee or consumes a party-grace use. Accepting pending generated content into the reset still charges generation once, independently of the later room fee.
- Switching to a default game clears the previous content id; Odd Question supports this continuation just like other default social games.
- Standalone **Play Again** uses that in-place path for default/config-driven games as well as saved-content games. Recovered timer settings, Musical Chairs and Party Quests replay configuration come from organizer sync rather than fresh UI defaults, including `ROOM_CREATED` for an empty lobby.
- Players on previous podium/final-results screens must render the new lobby and be counted as connected if their socket is live.
- `RESET_ROOM` must not run from active gameplay or from a non-organizer client.
- Clients clear every prior game payload, including generic prompts, photo clues, card hands, and Bingo tickets/marks, before entering the reset lobby. A new `GAME_STARTING` received before its runtime sync must show a waiting state rather than the previous game's content.

### Snapshot recovery

- `ROOM_SNAPSHOT_ENABLED` defaults to true and the interval defaults to ten seconds; graceful shutdown saves once more. `ROOM_SNAPSHOT_DIR` defaults under `DB_DIR/room_snapshots`.
- Snapshot directories/files use owner-only permissions (0700/0600), since they contain organizer/player credentials and private game payloads. Protect copied backups equally.
- Atomic per-room writes preserve the last complete snapshot. Malformed JSON or metadata in one file is logged and skipped without stopping healthy rooms; retain unreadable files for diagnosis.
- Restore uses the longer lobby TTL only when preserved seats exist. Empty lobbies and active rooms use the base room TTL. Runtime/session TTLs are distinct: advertised four-hour session expiry does not keep an abandoned process room alive for four hours.
- Live sockets/tasks/locks are recreated. Lobby seats restore offline; active seats preserve score/streak/answered state for token reclaim. Quiz countdown restarts while scoring retains its original start timestamp; Housie auto-call restores stopped. Musical Chairs/Mafia timed tasks still require host recovery.
- Snapshot recovery protects a single writable mounted volume. It does not provide multiple-instance routing/fanout, durable participant tables or native device qualification.

Regression anchor: `backend/tests/test_room_snapshot.py`; deployed restart evidence remains a separate release gate.

### Client Reconnect And Recovery

- An authenticated organizer receives authoritative `time_limit`, `game_type`, and full game content in `ROOM_CREATED`, including recovery of an empty lobby; unauthenticated sockets cannot receive organizer configuration.
- Each mounted organizer/player/spectator/TV surface owns one current socket. Frames and close callbacks from superseded sockets are ignored; replacing a socket cancels its scheduled retry.
- Organizer actions send only through the current open socket, and lobby/pass-and-play Start stays disabled while connecting or reconnecting. Setup edits retain only the latest same-room Impostor roster and send it after the organizer's `AUTH` frame; gameplay actions are not replayed after reconnect.
- A player waking while a retry is pending reconnects once, without a second timer opening another socket and taking over their own nickname.
- Saved organizer/player recovery works under the application's React StrictMode effect setup/cleanup cycle. A saved player token is attached only to its matching room and nickname; opening a different room link does not silently join using the old room credential.
- `KICKED` is terminal until the player deliberately joins again. Focus/online events must not cause the displaced tab to steal its nickname back from the active tab.
- A terminal room/auth error or `ROOM_CLOSED` cancels retries and closes the socket. Spectator answer-reveal timers must not overwrite that terminal screen or a newly joined room.
- Quiz-runtime player `RECONNECTED` restores final/round leaderboards, team standings and the correct answer after round closure. `has_answered` restores a waiting state for an already submitted question so the client does not offer a second answer. A restored round displays neutral completion feedback when per-answer correctness is unavailable.
- Shared game-image loading/error state is scoped to the image URL, so a failed image in one round cannot prevent the next round's image from loading.
- Guest/TV links use the public web URL in native builds and preserve the deployed browser base path. Native WebView origins such as `capacitor://localhost` are never exposed as guest join links.
- Spark balance refreshes accept only the latest request. An older anonymous/account response must not overwrite the balance after a sign-in or sign-out wallet change.

### Cleanup And Capacity

- `MAX_ROOMS` is a hard process-local safety limit. Room creation must fail closed with a clear 429 when the cap is reached.
- Closing a room stops all room-owned timers and auto-advance tasks, including drawing pauses and organizer grace. A grace cleanup may finish its own close/status recording without self-cancellation. Closed socket maps and organizer references are cleared.
- Server-initiated room/socket closure exits the receive loop normally through connection cleanup. Host cancellation and rejected joins must not log errors from receiving again after a server close; unexpected handler failures must still be logged.
- Host cancellation must immediately remove the room from the process map and snapshot store so capacity is recovered without waiting for TTL cleanup.
- Cleanup probes in live smoke tests must prove rooms are gone by reconnecting to the same room code and seeing `Room not found`.
- Harnesses must cancel every room they create; leaked test rooms are a production risk because they consume the same room cap as real parties.
- Track rooms immediately after HTTP creation and sockets immediately after connection, before auth/join/reconnect acknowledgements. Partial opens must use the same cancellation and cleanup probe as successful opens, and cleanup failures must be reported even when the original smoke already failed.

### Host-App Behavior

- Host-app lobbies use the same shared lobby component as standalone lobbies.
- Host-app player podiums suppress LocalPlay referral/spark offers. Managed rooms must return `{available: false}` from the invite endpoint even when they have an internal wallet identity.
- Standalone next-game suggestions use connected players and deployed catalog minimum/maximum counts, so an offline seat or a group above a game's limit cannot produce an unstartable suggestion.
- In host-app mode, QR/copy/share uses the validated host-app `guest_join_url`; raw `/join/{room_code}` links stay hidden unless no host app is involved.
- Returning to games from a host-app lobby returns to the LocalPlay party hub for that host app, after the same interruption warning used by standalone.

## 3. Test Matrix

Required gates:

- Backend socket scenarios:
  - organizer disconnect/reclaim
  - player reconnect from question, leaderboard, and podium on both seat-reclaim paths
  - closure cancels every room-owned task and timer-driven round completion publishes results
  - host cancellation closes real ASGI organizer/player/spectator sockets without error logs or remaining room tasks; rejected joins also end normally, while unexpected handler failures retain error reporting
  - late join during running games where allowed
  - ignored reset outside podium
  - podium-to-next-game `ROOM_RESET` moves existing players into next lobby
  - podium-to-default/config-driven game `ROOM_RESET` keeps live players startable without a new content id
  - podium-to-Bingo-family saved content `ROOM_RESET` keeps live players startable and emits `BINGO_SYNC`
  - replay charges one room fee or grace use per actual start, stages a lobby with zero room budget, and settles pending generation independently
  - default Odd Question continuation clears prior content and keeps live guests startable
  - room-code uniqueness
  - `MAX_ROOMS` fails closed and host cancellation recovers capacity
- Frontend unit tests:
  - lobby title uses selected game name
  - missing game title does not show the old generic "Game Lobby" fallback
  - connected/offline seat display and explicit offline cleanup control
  - host-app lobby hides raw share URL and uses host-app join affordance
  - organizer/player saved-room recovery under StrictMode
  - player wake/retry reconciliation, scoped saved credentials, and kicked-tab suppression
  - player quiz round/podium restoration and already-answered recovery
  - reset clears stale runtime payload before the next sync
  - spectator terminal reveal-timer cancellation and leave/join/reconnect across rooms
  - TV terminal errors, pending/replaced room creation, and authoritative connected-device counts
  - image recovery between rounds, public native/base-path links, and wallet response ordering
- Local Playwright:
  - `npm run test:e2e:all-games` creates, gates, starts, and tears down every catalog game.
  - `frontend/e2e/podium-continuation.spec.ts` drives quiz podium suggestions into Odd Question and Would You Rather, checks that the reset sends no stale quiz content, and starts the same guests in the same room.
- Gamma Playwright:
  - `npm run test:e2e:gamma` for desktop/mobile catalog/media smoke.
  - `npm run test:e2e:all-games:gamma` for deployed all-game coverage at modest parallelism.
  - `PREPROD_LIVE=1 PLAYWRIGHT_BASE_URL=https://gamesapi-gamma.revelryapp.me npm run test:e2e:preprod-live` for action-level gameplay.
- Load smoke:
  - `scripts/load-room-smoke.py` creates disposable rooms, opens organizer/player WebSockets, holds briefly, cancels, and verifies cleanup by probing the room codes.
  - With `--reconnect-check`, the harness closes and reopens one lobby player per room using the issued session token and requires a `RECONNECTED` lobby sync before cleanup.
  - `backend/tests/test_load_room_smoke.py` injects failures in creation, organizer connect/auth, player join, reconnect, and cancellation; every known created room and connected socket must reach cleanup and any failed cleanup probe must remain visible.
- Revelry pre-prod live:
  - `frontend/e2e/revelry-preprod-live.spec.ts` includes a host-app lobby-lull regression where a Revelry quick-started room accepts a player, preserves their seat across a socket drop, reconnects with the issued session token, and remains startable by the organizer.

Gamma all-games is not the concurrency test. It intentionally runs with lower parallelism than local so failures stay attributable to deployed behavior. Concurrency is owned by the load smoke.

## 4. Operational Runbook

Before production deploys that touch room creation, WebSockets, lobby reconnect, reset, room cleanup, or shared organizer/player/spectator surfaces:

1. Run isolated SQLite backend tests (set `DB_BACKEND=sqlite` and a private `DB_DIR`) excluding the known legacy E2E file; run that file serially as its own CI/local step.
2. Run focused socket scenarios.
3. Run frontend vitest and `npx tsc -b`.
4. Run local all-games Playwright.
5. Run local load smoke.
6. Deploy to gamma.
7. Run gamma smoke, gamma load smoke, gamma all-games, and Revelry pre-prod live regression.
8. Promote only after failures are fixed or classified with evidence and the candidate gates in [PROD-ROLLOUT-2026-10.md](PROD-ROLLOUT-2026-10.md) pass. An increased harness timeout does not waive the external Revelry workspace gate.

Prod load smoke requires explicit approval and must use modest room/player counts because it creates live disposable lobbies.

### Release swap and recovery contract

- Bind qualification to the selected source/image, config and consumer version pair. A live all-games run on an earlier candidate plus focused final-delta evidence needs a recorded scope/rerun rationale; docs-only later commits do not change the runtime candidate.
- Before a swap, verify snapshots are enabled, recent and writable; privately back up the current volume and credentials-bearing snapshots. Defaults save every ten seconds and on graceful shutdown. Prefer no customer rooms; the current single-process architecture does not support a rolling or percentage-canary release.
- Qualify the current candidate's actual restart/reconnect using owned QA rooms, including an answered quiz, score/seat preservation and managed session continuity. Reclaimed sockets recover state, while quiz question countdown restarts with its original scoring timestamp. Housie caller resumes through the host; Musical Chairs/Mafia timed substates may require host recovery. Record these edges if an active-room window is accepted.
- Verify previous-image snapshot compatibility before accepting rollback readiness. Gracefully stop and restore the captured immutable image with the current env/volume; do not blindly replace current snapshots or durable ledger state with a pre-window copy. Reconcile unknown in-flight start/financial outcomes before retries.
- Production acceptance is bounded to designated QA parties/rooms and recorded budgets. Verify closure and consumer active-session cleanup by owned IDs, and retain historical content. Image health alone does not prove callback, reconnect, billing or cancellation recovery.

## 5. Open Hardening

- Add a mobile OS sleep/reopen Playwright-or-device scenario on top of the existing Revelry pre-prod live lobby-lull socket regression.
- Add runtime metrics for room create latency, socket join latency, reset delivery, cancellation cleanup time, and reconnect success/failure.
- Add a bounded soak test that keeps rooms open across the lobby grace window using fake timers locally and a short-duration config in gamma.
