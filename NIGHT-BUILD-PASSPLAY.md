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
- [ ] `SeatRosterSetup` — host types names, add/remove, emoji pick, min/max enforcement.
- [ ] `PassScreen` — full-screen "Pass to **Maya** 🥭", nothing sensitive rendered.
- [ ] `PrivacyGate` — tap-and-hold to reveal → content → "Got it, hide & pass".
- [ ] `GroupScreenFrame` — face-up phases (vote, reveal, timer) styled for table viewing.
- [ ] Frontend tests for each primitive, esp. that `PrivacyGate` renders nothing before reveal.

### Phase 3 — Impostor UI on the primitives
- [ ] Organizer/host flow: setup → role reveal loop → clue rounds → vote → reveal → podium.
- [ ] Picker tile + the "One phone" badge on pass-and-play games.
- [ ] Frontend tests for the full flow.

### Phase 4 — ship + verify
- [ ] Full suites green (backend + frontend + tsc).
- [ ] Deploy gamma (`./scripts/deploy-gcp.sh --gamma --with-frontend --build-on-vm`).
- [ ] Live-verify on gamma: create an impostor room, walk a full round.
- [ ] Update `SPEC-PASS-AND-PLAY.md` status, `DEPLOY.md` ledger, `BACKLOG.md`.

### Opportunistic (only if blocked or waiting)
- [ ] First-run gaps noticed while in the picker/lobby surfaces — note them here, fix the cheap ones.

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
