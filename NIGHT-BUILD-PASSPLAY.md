# NIGHT BUILD — Pass-and-Play platform + Impostor

**This file is the resume contract.** An autonomous run may stop at any point (token exhaustion,
process exit). A resumed session should read THIS FILE FIRST, find the first unchecked box, and
continue from there. Keep it updated as you go — an accurate ledger is worth more than extra code.

- **Started:** 2026-07-28 (session cae10bec)
- **Authorised by Avi:** build + commit to master + deploy to gamma freely. **Prod and native are
  OFF LIMITS** this run. No `supabase db push` ever (shared project — use the Management API).
- **Spec:** `SPEC-PASS-AND-PLAY.md` (written, no code yet)
- **Goal:** the five shared primitives + the real Impostor, tested, on gamma by morning.

## Resume procedure

1. `git log --oneline -5` and `git status` — see what landed.
2. Read the checklist below; first unchecked box is the next task.
3. Run the suites before continuing: `cd backend && python -m pytest tests/ -q --ignore=tests/test_e2e.py`
   and `cd frontend && npx vitest run`. Fix any red before adding new work.
4. Update this file's checkboxes + "Session log" as you complete things, and commit it with the work.

## Why this feature (don't lose the thread)

Every existing game assumes one phone per player. That structurally excludes real party guests:
kids, grandparents, dead batteries, phones-away dinners. Teens already play this way — one phone
circulating IS the native mode of Impostor. "One phone — no downloads for guests" is also the
answer to the biggest party-app objection, and it's store-listing material.

It is **cheaper** than a normal game: no per-player sockets, no reconnect/seat grace, no
per-viewer payload scoping. Privacy is physical, enforced by a deliberate reveal gate.

## Architecture decisions (locked — don't relitigate mid-run)

- **Single client.** The host's device drives everything. No player WebSockets. The existing
  organizer socket is enough (host screen / TV mirroring can come later).
- **Seats are not connections.** A seat is `{id, name, emoji}` typed at setup. Never reuse the
  `players` dict keyed by client_id — that's the per-device model and it will fight you.
- **Privacy is a UI gate, not a payload filter.** The engine may hand the client all roles; the
  `PrivacyGate` component is what prevents shoulder-surfing. Do NOT build per-seat payload scoping
  — there's one viewer.
- **`interaction: "pass_and_play"`** on catalog entries so the picker can badge them.
- **Reuse `record_game_completion`** for stats — host-wallet attribution is exactly right here.

## Checklist

### Phase 1 — backend engine + catalog
- [x] `backend/pass_play_common.py` — seat roster validation/sanitisation, turn-order engine
      (rotation, skip, insert), shared phase constants. Mirror `engine_common.py` conventions.
- [x] `backend/impostor_engine.py` — word-pair decks, role assignment (1 impostor, N knowers),
      spoken-clue round tracking, vote tally, strict-majority catch, impostor-guess comeback rule.
      Curated packs first; AI generation later.
- [x] Catalog entry for `impostor` with `interaction: "pass_and_play"`, `MIN_IMPOSTOR_PLAYERS = 3`.
- [x] Rules metadata (`game_rules.py`) so the rules modal works.
- [x] Backend tests: engine unit tests + a socket/flow test. (66 green)

### Phase 2 — frontend primitives
- [x] `SeatRosterSetup` — host types names, add/remove, emoji pick, min/max enforcement.
- [x] `PassScreen` — full-screen "Pass to **Maya** 🥭", nothing sensitive rendered.
- [x] `PrivacyGate` — tap-and-hold to reveal → content → "Got it, hide & pass".
- [x] `GroupScreenFrame` — face-up phases (vote, reveal, timer) styled for table viewing.
- [x] Frontend tests for each primitive (19 green), esp. that `PrivacyGate` renders nothing before reveal.

### Phase 3 — Impostor UI on the primitives
- [x] Organizer/host flow: setup → role reveal loop → clue rounds → vote → reveal → podium.
- [x] Picker tile + `passAndPlay` flag + local rules + collision guards.
- [x] Frontend tests (356 total green).

### Phase 4 — ship + verify
- [x] Full suites green: backend 1258, frontend 356, tsc + build clean.
- [x] Deployed to gamma 2026-07-28.
- [x] Live-verified: full round over a real WebSocket, **22/22 checks** (script in scratchpad).
- [x] Updated SPEC-PASS-AND-PLAY status + DEPLOY.md ledger + BACKLOG.

### Opportunistic (only if blocked or waiting)
- [x] First-run gaps noticed while in the picker/lobby surfaces. **Found and fixed one real gap:**
      `passAndPlay` was set on the catalog config but rendered NOWHERE a browsing user could see —
      it only drove the lobby swap. Among 38 games nothing signalled which one a phoneless guest
      could join, despite this spec calling that badge a selling point. Added a "1 phone" badge to
      the picker tile + a guard test so it can't silently regress to an internal-only flag.
      **Noted, not fixed (needs a product decision):** 38 games is a lot for a first-run user and
      there's no grouping by "how many phones do you need" — now a meaningful axis with both modes
      shipping. That's a picker IA question for Avi, not a cheap fix.

## Known traps (learned the hard way this session — do not rediscover)

- **Game-id collisions are real.** `odd_one_out` collided with a quiz variant; "Impostor" collided
  culturally. `impostor` is now free and correct for THIS game. Guard tests live in
  `frontend/src/__tests__/gameIdCollision.test.ts` — extend them.
- **`GameType` unions dedupe silently** in TypeScript, so tsc will NOT catch a duplicate id.
- **Adding a game means touching several hardcoded lists.** Grep for an existing pass-adjacent id
  across `backend/` and `frontend/src/` before assuming the catalog entry is enough. The occasion
  bingos shipped broken because three lists still said `['bingo','baby_bingo']`. Prefer deriving
  from a property over adding to a list.
- **Room state-attr maps:** a new game type usually needs entries in the per-game state/config
  attribute maps in `socket_manager.py`. Missing ones fail at runtime, not import.
- **`Room(...)` signature** is `Room(room_code, game_data: dict, ..., game_type=...)` — not kwargs
  like `wallet_id=`.
- **conftest pins `tokens.get_wallet_id`** to `TEST_DEVICE_ID` for every request; endpoint tests
  must seed that wallet, and an `X-Device-Id` header is ignored.
- **Device ids must be UUIDs** (`tokens.get_device_id` rejects anything else → resolves to no wallet).
- **The backend serves the SPA as a catch-all**, so a missing route returns `200 text/html`. Always
  check content-type when verifying a new endpoint, never just the status code.
- **Never write a waiter loop whose own command line contains its search pattern** —
  `pgrep -f "foo"` matches the waiter itself and it never exits. Bracket a char: `"fo[o]"`.
- **`test_e2e.py::TestExportImportE2E::test_generate_export_import_play` IS FLAKY.** It fails
  intermittently in a full-suite run with `Timed out ... waiting for QUESTION after no messages`.
  It is **pre-existing** — it reproduced before any pass-and-play code existed. **Do not bisect a
  flaky test with one run per step**: doing that produced a confident wrong conclusion tonight
  (blamed the WS rate-limiter change, which for a quiz room computes a byte-identical limit). Any
  suspected culprit must be re-run 3x before you believe it.
- **`TestClient` websockets need `socket_manager.allowed_origins = []`** in a fixture, because
  `backend/.env` sets ALLOWED_ORIGINS and TestClient sends no Origin header.
- **The WS route is `/ws/{room_code}/{client_id}`** and the organizer connects with
  `?organizer=true` then sends `{"type":"AUTH","token":...}`. Build rooms directly via
  `socket_manager.create_room(...)` in socket tests, as the other suites do.
- **`tests/ws_test_utils.py`** now holds a bounded `recv_until` — use it. A raw `receive_json()`
  blocks forever on a missing broadcast and hangs the whole run instead of failing one test.

## Session log

- **2026-07-28 ~01:30 (cron resume)** — Verified: all four phases complete, tree clean, nothing
  unpushed, backend 1258 + frontend 357 + tsc + build clean, gamma healthy (38 games, impostor
  present, ad-reward still 403, RC secret intact) and the served bundle confirmed to carry the
  Impostor UI strings. Closed the last opportunistic box with a real find — see above.
  **Loop stopped: no work left that doesn't need Avi's input.**

- **2026-07-28 ~01:20** — **ALL FOUR PHASES DONE. Impostor is live on gamma and verified.**
  Walked a complete round over a real WebSocket against live gamma: 22/22 checks, including the
  two invariants that only a live run can prove — a room starting with ZERO connected players, and
  roles arriving during the gated reveal phase but NOT once the phone is face-up. Comeback rule
  fired for real (word "Pillow", impostor caught). No migration, no feature flag: seats and game
  state are in-memory per room.
  **Remaining for a future session:** AI-generated word packs, the pass-mode retrofit for
  chit_pull/nhie/wmlt/two_truths, and the rest of the slate (Paranoia, Hot Seat, Truth or Dare,
  Forehead Guess, Wavelength-ish). None of it blocks anything.

- **2026-07-28 ~01:10** — Phase 3 mostly done: `ImpostorGame.tsx`, types, picker tile with a
  `passAndPlay` flag, local rules, extended collision guards. Backend 1258 / frontend 356 / tsc
  clean. **Design fix worth remembering:** two of my own rules contradicted each other — "privacy
  is a UI gate not a payload filter" vs "withhold the secret until the round resolves" — which
  made the role reveal unimplementable. Resolved by scoping disclosure **by phase**: `roles` ships
  only during IMP_REVEAL_ROLES (the phase with a gate mounted), empty in every face-up phase.
  Pinned by `TestPhaseScopedDisclosure`.
  Then wired into `OrganizerPage`: IMPOSTOR_SYNC handler, seven senders, the game render, and
  **seat setup REPLACING the lobby** for pass-and-play — a QR code would be actively misleading
  when the players have no devices. Reachable end to end. Frontend build clean.

- **2026-07-28 ~01:05** — Phase 2 COMPLETE. Four primitives in
  `frontend/src/components/passplay/` + 19 tests + Velvet CSS. tsc clean.
  The security-relevant design: `PrivacyGate` does NOT render `children` at all while shielded
  (not `display:none` — a hidden secret is still in the DOM, the a11y tree, and one devtools
  glance away), reveal needs a press-and-HOLD because a *tap* is what a phone being handed over
  receives by accident, and it re-shields both on done AND on seat change so a pass mid-reveal
  can't leak the previous player's role. Tests assert absence from the document, not invisibility.
  Note: fake-timer advances and pointerDown must be wrapped in `act()` or React warns.
  Next: Phase 3 — Impostor UI on these primitives.

- **2026-07-28 ~00:55** — Phase 1 COMPLETE (66 tests). Three real bugs the over-the-wire test
  caught: (1) `/room/create` rejected `impostor` via a hardcoded 23-type tuple → replaced with
  `SUPPORTED_ROOM_GAME_TYPES` **derived from the catalog** (verified set-identical + impostor);
  (2) the WS rate limit throttles pass-and-play, because the whole table's input arrives on the
  host's ONE socket — a 3-seat round is ~14 messages against a 10/sec cap, so the vote came back
  `ERROR: Too many messages` → added `PASS_PLAY_RATE_LIMIT_PER_SEC = 30` mirroring the DRAW_OP
  precedent; (3) a start gate on `connected_player_count()` would make the game permanently
  unstartable → gated on SEATS, pinned by `test_starts_with_zero_connected_players`.
  Also extracted `tests/ws_test_utils.py` (bounded websocket receive) out of test_e2e.
  Podium substitutes seat count for `player_count`, else stats record every party as 0 players.

- **2026-07-28 ~23:45** — Phase 1 engines DONE: `pass_play_common.py` (seat roster, turn engine,
  strict-majority vote) + `impostor_engine.py` (word packs, roles, clues, vote, comeback rule).
  53 tests green (20 + 33). Design notes worth keeping: turn order stores explicit seat ids, NOT
  an index — with an index, removing the current seat silently skips a player. Conviction needs a
  STRICT majority so a split table acquits. `public_state` withholds the secret until the round
  resolves, because the clue phase is face-up on a table. Next: catalog + rules + socket wiring.
- **2026-07-28 ~23:20** — Ledger created. Gamma is deployed and verified with everything through
  `d769b509` + the bingo-family fix (37 games, `odd_question`, stats, share images). Starting Phase 1.
