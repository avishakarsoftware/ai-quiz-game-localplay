# LocalPlay Backlog

## Done

- **Share-card snapshots persisted to DB (SPEC-SHARE-CARD).** Share/OG-unfurl links were in-memory only —
  they died on process restart and didn't work multi-instance. Added a `share_snapshots` table +
  `db.save/get_share_snapshot` (+ Supabase parity via insert/select wrappers + `20260721T030000_share_snapshots{,_gamma}.sql`
  migration); `share.py` now write-throughs to the DB with the in-memory dict as a hot-path cache. DB access
  is best-effort — a failure (e.g. Supabase pre-migration) degrades to memory-only and never 500s a share, so
  applying the migration is a transparent no-flag upgrade. Tests: backend 11 (4 new: survives cache loss,
  TTL after cache loss, create/read degrade on DB failure). **Deployed 2026-07-26; table applied on both
  Supabase prefixes.** No flag — see DEPLOY.md.
- **Achievements / badges v1 (SPEC-ACHIEVEMENTS).** Idempotent per-wallet badges (`achievements` table,
  composite PK) awarded from clean economy choke-points — `welcome` (lazy on first view), `first_referral`
  (both parties), `first_gift` (sender). `GET /achievements` returns the backend-authoritative catalog with
  earned flags; `_award_badge` is best-effort (gated + try/except, never breaks the primary action). Supabase
  parity via `award_achievement` RPC + table/RLS (template + rendered + `20260721T020000_achievements{,_gamma}.sql`),
  gated on `ACHIEVEMENTS_ENABLED`; `achievements_enabled` flag on `/config/public`. Frontend `AchievementsSection`
  in the settings drawer. Tests: backend 9, frontend 3. Game-completion + purchase badges deferred (game_history
  is in-memory, not per-wallet). **Deployed 2026-07-26; migration applied to both Supabase prefixes.
  Live + smoke-verified on gamma (`ACHIEVEMENTS_ENABLED=true`); prod schema ready, flag still OFF.**
- **Spark gifting (SPEC-GIFTING).** Send N sparks wallet→wallet, addressed by the recipient's referral
  ("friend") code. One atomic debit-then-credit; idempotent on a client key; self-gift blocked;
  `invalid_amount`/`insufficient`/`recipient_full` (conserves sparks at the cap)/`daily_cap` guards; per-sender
  daily count + token caps. `POST /tokens/gift` (rate-limited, gated by `_GIFTING_SUPPORTED`); `gifting_enabled`
  flag on `/config/public`. Supabase parity via `gift_sparks` RPC (template + rendered + `20260721T010000_gifting{,_gamma}.sql`
  migration plus `20260721T040000_gifting_idempotency_replay{,_gamma}.sql` follow-up) + `supabase_db` wrapper + override-list entry, gated on `GIFTING_ENABLED`. Frontend `GiftSection`
  in the settings drawer with per-attempt idempotency key (reused on retry, rotated on success). Emits
  `spark_sent`/`spark_received`. Tests: backend 14 (db + endpoint + Supabase wrapper), frontend 4. **Deployed
  2026-07-26; both migrations applied to both Supabase prefixes (in timestamp order — the `…040000` replay
  follow-up supersedes the `…010000` function body). Live + smoke-verified on gamma (`GIFTING_ENABLED=true`);
  prod schema ready, flag still OFF.**
- **Legacy sync E2E WebSocket timeout hardening.** Hardened `backend/tests/test_e2e.py` so sync `TestClient` websocket receives have a real wall-clock timeout, timeout errors include the message types already seen, room-created handshakes are explicit, and `START_GAME` drains `GAME_STARTING` for organizer/player/spectator sockets before tests advance to `NEXT_QUESTION`. This keeps the legacy export/import and reset flows from hanging indefinitely when lifecycle messages such as `PING` or `GAME_STARTING` arrive before `QUESTION`.
- **Generic Prompt Party engine plus 10 standalone games.** Implemented shared `generic_prompt_party` mechanics and catalog entries for Hot Takes, This or That, Caption Contest, Pitch Battle, Roast & Toast, Desert Island, Memory Lane, Rapid Fire, One Word Vibes, and Emoji Story. The shared runtime supports choice voting, text submissions with voting, grouped text reveals, late joins, reconnect/spectator sync, rules metadata, podium/history summaries, frontend organizer/player/spectator UI, engine unit tests, and websocket flow coverage. Follow-ups: AI/custom authoring, richer occasion packs, multi-tab Playwright matrix, and a separate Revelry host-app bridge/policy pass.
- **Party Quests MVP + LocalPlay staged check-in flow.** Implemented `party_quests` as an ambient social game with curated and AI-generated editable quest decks, party-scoped saved content, deterministic Host/Player/TV preview, duration/quest-count/confirmation/late-join settings, exact saved-version room materialization, first-real-player check-in auto-start, per-player boards, tap-confirm/honor completions, late joins, organizer/player/spectator sync, final reveal, idempotent host cancellation, safe callbacks, and local backend/frontend regression coverage. Direct service-minted Party Quests authoring links dispatch to the Party Quests editor instead of the quiz-only page and support type-safe create/edit resolution. This staged flow **resolves two operational gaps hit in the field (2026-07-09):** (1) *check-in auto-start bypassing host setup* → now strict `requires_prepared_content_for_checkin` plus the setup UI + Host/Player/TV preview, so a check-in game must be configured first; (2) *no host stop control* → now `POST /integrations/revelry/party-games/cancel` (`_cancel_revelry_session`, idempotent, one callback) with a "Cancel game" button in `PartyHubPage` and `LobbyScreen`. Gamma flipped 2026-07-09; production DDL/policy flipped 2026-07-14 (see DEPLOY.md ledger). Follow-ups: pair-code confirmation and the multi-tab live Playwright rollout matrix.
- **Survey Says standalone MVP.** Implemented `survey_says` as a team survey-answer game with default curated rounds, automatic two-team assignment, player free-text guesses, host answer-board adjudication, strikes, steal flow, late joins, spectator sync, rules metadata, podium, and focused backend tests. Follow-ups: AI/manual authoring, buzzer/faceoff mode, host-app policy enablement, and embedded gamma QA.
- **Mafia standalone MVP.** Implemented local standalone `mafia` with secret roles, role reveal, Mafia/Detective/Doctor night actions, Night Reads for every living player, aggregate-safe day discussion fuel, public-safe sync, day votes, role reveal on elimination, Town/Mafia win conditions, socket tests, frontend organizer/player/spectator surfaces, and Night task status polish. LocalPlay now exposes it as a Revelry quick-start/settings catalog candidate; host-app policy, gamma deploy, and multi-device Playwright QA remain the next launch gate.
- **Random Chit MVP.** Implemented as stable game type `chit_pull` with AI/manual deck setup, safe prompt sanitization, random player/chit turns, host complete/bonus/skip/redraw controls, scoring, podium, user-facing Random Chit naming, and backend/frontend regression tests. LocalPlay now supports Revelry quick-start plus saved-content/AI authoring for `chit_pull`; rollout requires the `generated_content.content_type` migration and host-app policy enablement.
- **Find Someone Who MVP.** Implemented standalone `find_someone` social bingo with default prompt deck, per-player generated cards, tap-confirm and honor modes, line/corners/blackout claims, host/spectator aggregate sync, late-join card assignment, and one-player start support for future check-in auto-start flows. Host-app policy **enabled for `host_app=revelry` in gamma + prod on 2026-07-08** (quick-start only; see DEPLOY.md migration log), so it works as a Revelry check-in game. Revelry still owns the party check-in default and auto-start setting; follow-up: embedded gamma check-in auto-start smoke.
- **Bluff bridge readiness.** Shared card engine and Bluff MVP are implemented locally. LocalPlay now exposes Bluff as a Revelry quick-start/settings catalog candidate. Gamma visual QA and policy rollout remain before broad production enablement.
- **Photo Clue standalone MVP.** Implemented `photo_clue` with up-front private prompt assignment, player photo upload/finalize, guessing, scoring, organizer reveal/next controls, spectator reveal, reconnect-safe sync, podium, rules metadata, catalog exposure, and focused API/socket/frontend build coverage. LocalPlay now exposes it as a Revelry quick-start/settings catalog candidate with `supports_images=true`; rollout needs host-app policy, embedded gamma QA, and safe media-summary discipline. Follow-ups: AI/manual authoring UI, moderation, richer retention controls, and broad Playwright matrix coverage.
- **Party Poker quick standalone MVP.** Implemented `poker` as a no-money quick Hold'em table with equal play chips, fixed antes, private hole-card redaction, Stay/Fold decisions, showdown, elimination, podium, organizer/player/spectator UI, and focused API/socket/frontend build coverage. LocalPlay now exposes it as a Revelry quick-start/settings catalog candidate; rollout needs host-app policy, embedded gamma QA, and no-money compliance copy. Follow-ups: full betting rounds, blinds, raises, all-ins, side pots, and dealer controls.
- **Would You Rather standalone MVP.** Implemented catalog/room/socket/runtime UI for binary voting, vote changes, reveal splits, majority scoring, late join, reconnect, podium, rules metadata, and focused API/socket tests. LocalPlay now exposes it as a Revelry quick-start/settings catalog candidate. Follow-ups: AI/manual authoring UI, host-app policy/embedded QA, and broad Playwright matrix coverage.
- **Never Have I Ever standalone MVP.** Implemented catalog/room/socket/runtime UI for have/never answers, reveal splits, optional minority scoring, late join, reconnect, podium, rules metadata, and focused API/socket tests. LocalPlay now exposes it as a Revelry quick-start/settings catalog candidate. Follow-ups: AI/manual authoring UI, host-app policy/embedded QA, and broad Playwright matrix coverage.
- **Word Association standalone MVP.** Implemented catalog/room/socket/runtime UI for seed prompts, text submissions, grouped reveal, majority scoring, late join, reconnect, podium, rules metadata, and focused API/socket tests. LocalPlay now exposes it as a Revelry quick-start/settings catalog candidate. Follow-ups: AI/manual authoring UI, host-app policy/embedded QA, and broad Playwright matrix coverage.
- **Acronym Game standalone MVP.** Implemented catalog/room/socket/runtime UI for acronym expansion submission, anonymous voting, reveal, vote scoring, late join, reconnect, podium, rules metadata, and focused API/socket tests. LocalPlay now exposes it as a Revelry quick-start/settings catalog candidate. Follow-ups: AI/manual authoring UI, host-app policy/embedded QA, and broad Playwright matrix coverage.
- **Party-scale lobby continuity base.** Implemented soft lobby disconnects so transient player WebSocket closes preserve seats as `offline` for a configurable grace window, lobby/start counts use connected players only, offline seats are visible to the host, same-token lobby reconnect reclaims the nickname, offline seats are pruned before a game starts, and player sessions are saved across session/local browser storage. Follow-ups: explicit host remove/cleanup action, gamma soak test simulating mobile sleep/lobby lull/reopen from Revelry, and reconnect telemetry dashboards.
- **Room/socket lifecycle QA guardrails.** Added bounded socket coverage for podium-to-next-game `ROOM_RESET`: players who remain on the final-results screen are pushed back to the same room's lobby and counted for the next start, so QR/Revelry join links stay stable across games. Added `MAX_ROOMS` capacity-recovery coverage proving room creation fails closed at cap and host cancellation immediately frees a slot. Added `scripts/load-room-smoke.py`, a repeatable local/gamma/prod-approved harness that creates disposable lobbies, connects organizers plus `QA-*` players over real WebSockets with browser-like `Origin`, holds briefly, and cancels all rooms without starting games or spending sparks.

- **Game-history / stats screen + game-completion badges (SPEC-GAME-STATS).** `game_history` was an
  in-memory ring, so lifetime stats were impossible and game-completion achievements stayed blocked.
  Adds a durable `game_results` table (room_code PK ⇒ a replayed podium can't double-count), collapses
  the 18 duplicated engine podium blocks into one `record_game_completion` choke-point, `GET /stats`
  (never 500s — reports `available:false` pre-migration so the code ships safely ahead of the table),
  Supabase parity via table-only + Python aggregation, `StatsSection` in the drawer (self-hiding, no
  flag), and 4 new badges (`first_game`/`ten_games`/`big_party`/`explorer`). Copy says **hosted**, not
  played: guests never authenticate, so the host's wallet is the only attributable identity. Tests:
  backend 15, frontend 7. **Not yet deployed / table not yet applied on Supabase.**

- **Odd Question (né Odd One Out, briefly Impostor — see SPEC-GAME-ODD-QUESTION's naming history;
  `impostor` is deliberately kept FREE for the real teen pass-the-phone game): frontend screens DONE,
  picker tile DONE.** Original note: (renamed 2026-07-28 to fix the quiz-variant id collision; see
  SPEC-GAME-IMPOSTOR header): frontend screens DONE, picker tile DONE.** Backend wiring DONE 2026-07-27 —
  it joined the existing **simple-social family**, whose `_broadcast_simple_social_sync` already sends a
  separate payload per connection, which is exactly the per-viewer prompt scoping this game needs. So the
  feared ~48 bespoke touchpoints were the wrong read. Verified over the wire (2 socket tests) including
  that a non-odd player never receives the minority prompt. Now `launchable: True` — 37 games, all
  launchable. Remaining: organizer/player UI, modelled on the four sibling simple-social games.
- ~~[old] Odd One Out: socket wiring.~~ Engine done and tested (30
  tests, commit `93feb599`); catalog entry deliberately `launchable: False` / `status: planned` so a
  game that can't start is never offered. Remaining: the ~48 socket_manager touchpoints listed in the
  spec, plus organizer/player screens. Do it test-first — assert over the wire that a non-odd
  player's payload never contains the minority prompt, since per-viewer prompt scoping is what's most
  likely to break in translation.
- ~~**Derive socket_manager's game-type sets from the catalog.**~~ **DONE 2026-07-27** — see below.
- **[done] Derive socket_manager's game-type sets from the catalog.** Adding a game means editing ~12
  hardcoded game-type tuples in socket_manager with *different* semantics (podium/summary path, valid
  `new_game_type` on reset, "simple round" reconnect/sync shape, …). Nothing forces you to find them
  all, so a miss is a silent runtime gap discovered only by playing the game. The catalog already
  records each game's `runtime_type`; deriving these sets from it — one per distinct purpose, not one
  merged set — would make new games correct by construction. Surfaced while adding game #34.

- **Occasion Bingo decks: Wedding / Holiday / Road Trip.** DONE 2026-07-27. Content-only games that
  reuse `runtimeType: 'bingo'`, so they needed **zero socket wiring** — catalog entry + rules + a 25-item
  deck each. Also collapsed the per-deck mapper into one `bingoDeckFrom(prefix, items)` builder plus an
  `OCCASION_BINGO` table, so the organizer branch didn't grow a copy per occasion (it was about to be a
  4th near-identical function). Catalog: 37 games, 36 launchable. Tests: frontend 3 (assert all four
  occasion decks stay on the shared bingo runtime, and that no game id is duplicated).

- **Flaky e2e tests when run alongside other socket suites.** *Investigated at length 2026-07-27 —
  still NOT fixed, but now well characterised. Read this before attempting it again.*

  **The one reliable lever is pytest output capture**, not load or ordering:

  | Command | Result |
  |---|---|
  | `pytest tests/test_ws_flow.py tests/test_e2e.py` | **1 failed × 3/3 runs** |
  | same + `-s` (capture off) | **56 passed × 3/3 runs** |

  Perfectly deterministic on that flag. Failure is always `TimeoutError: waiting for QUESTION after
  **no messages**` — nothing arrives at all.

  **Companion-file bisect** (3 runs each, capture on), i.e. which file paired with `test_e2e.py`:

  | Companion | Failures |
  |---|---|
  | `test_ws_flow` | 3/3 |
  | `test_mafia_socket` | 2/3 |
  | `test_socket_unit` | 1/3 |
  | `test_odd_one_out_socket` (since renamed `test_impostor_socket`) | 1/3 |
  | `test_websocket_integration` | 0/3 |
  | `test_generic_prompt_socket` | 0/3 |

  Note `test_ws_flow` + a **single** e2e test passes — it needs the companion *and* the earlier e2e
  tests, so something accumulates within the session.

  **Three theories tested and DISPROVEN — do not redo these:**
  1. *Load/timing.* Raising the receive timeout 8s → 45s changed nothing but how long a failing run
     takes (passing 14s, failing ~60s — the difference IS the timeout). Constant is back at 15s.
  2. *Global LLM budget leak.* `main._llm_call_timestamps` is never cleared by any fixture, so it
     looked ideal. Measured: it reaches **3** against a cap of **500**. Not it.
  3. *Orphaned reader thread eating the message.* `receive_json_with_timeout` spawns a thread per
     receive and, on timeout, leaves it blocked in `ws.receive_json()` — a plausible message thief.
     Replacing it with one long-lived reader per socket made things **much worse** (9 failed vs a
     20-passed baseline), so the per-receive thread is not the cause. Reverted.

  **Where to look next:** capture being decisive points at fd-level capture interacting with
  TestClient's anyio portal — each test file has its own module-level `TestClient(app)`, so a session
  holds several portals while `socket_manager` is a single module-level singleton. Most promising
  concrete step: give the socket suites **one shared TestClient fixture** (removing the multiple
  portals) or run `test_e2e.py` in its own pytest process (`-p xdist --dist loadfile`, or a separate
  CI step). Try `--capture=tee-sys` too — if that also passes, it narrows it to fd-level capture.

  **UPDATE 2026-08-18 — the deterministic repro no longer fires locally, but CI still flakes.**
  On today's tree `pytest tests/test_ws_flow.py tests/test_e2e.py` (capture ON) passes, measured
  **12 consecutive runs across three variants**: as-is, without the new `ws.close()` timeout cleanup,
  and with `spawn()`'s strong reference removed. So neither of those is what changed it, and I could
  not attribute the improvement — stated plainly rather than claimed. One suggestive signal: runtime
  dropped from the documented ~14s passing to **5.4s**, which points at the per-test SQLite isolation
  added the same week (the shared dev DB had grown to ~7.9 MB, and timing was always the trigger).

  **It is NOT fixed.** CI failed once today (run 32108611618, `backend-test`) on
  `TestTokenEconomyE2E::test_history_scoped_to_wallet`, same signature: "waiting for QUESTION after
  no messages", 15s stall. The instrumented dump again showed **two `asyncio-portal-*` threads**
  coexisting — now observed twice (2026-08-09 local, 2026-08-18 CI), which is the strongest standing
  clue and matches the "multiple TestClient portals" hypothesis below.

  Two things done rather than theorised:
  1. A timed-out receive now **closes the socket before raising**, so the parked reader thread exits
     and its portal is released. Theory 3 below (orphaned reader as message *thief*) stays disproven —
     this is about not *accumulating* portals after a failure, and it measurably changed nothing on
     its own (3/3 pass either way), so it is hygiene, not a fix.
  2. `test_history_scoped_to_wallet` no longer asserts `len(games) == 1`; it asserts the room_code
     is visible to the host wallet and invisible to the other — the property it is named for, and
     immune to anything else writing history.

  Still-untried next steps, in order: `--capture=tee-sys` (narrows fd-level vs sys-level capture),
  one shared `TestClient` fixture across socket suites, or running `test_e2e.py` in its own process.

  **Confirmed pre-existing** — reproduced with the working tree stashed at `0b86c619`. Practical
  impact: a socket-suite run is not a trustworthy regression signal, and CI may fail spuriously.
  `test_ws_flow`/`test_websocket_integration`/`test_socket_unit`/`test_mafia_socket`/`test_generic_prompt_socket`
  fails non-deterministically — three consecutive runs on a clean tree gave 1 failed, 2 failed, then 0
  failed, with a *different* test failing each time (`TestExportImportE2E::test_generate_export_import_play`,
  `TestGameResetE2E::test_reset_room_with_new_quiz`). Each passes alone and `test_e2e.py` alone is 20/20, so
  it is cross-file shared state (module-level `socket_manager.rooms` / `game_history` / TestClient portals),
  not a product bug. **Confirmed pre-existing** — reproduced with the working tree stashed at `0b86c619`.
  Worth fixing because it makes any socket-suite run untrustworthy as a regression signal.

- **Pass-and-play platform + Impostor flagship (SPEC-PASS-AND-PLAY).** ✅ **BUILT + LIVE ON GAMMA
  2026-07-28** (full round verified over a real WebSocket, 22/22). Five primitives + Impostor +
  catalog/rules/socket wiring + OrganizerPage. Prod not deployed. Remaining: AI word packs, pass-mode
  retrofits, and the rest of the slate. Original note: One shared phone circulates so
  phoneless guests can play — a new interaction model, not a game: five shared UX primitives (seat
  roster without devices, pass screen, privacy gate, turn engine, group-screen frame), then Impostor
  (the real teen secret-word game) as the first title on top. Cheaper than it looks: no player
  sockets, no reconnect, no per-viewer scoping — privacy is physical. Not started.

- **TV app as a DISTRIBUTION channel, TV-primary (SPEC-TV-APP).** **MVP slice built locally
  2026-07-28:** backend derives `tv_capability` for every catalog game, `/catalog` exposes it, helper tests
  pin `tv_availability`, and `/tv` is now a D-pad-friendly TV launcher while `/tv/:code` remains the legacy
  spectator receiver. Install on the TV *instead of* a phone: one install per household, room code on a 55"
  screen, and TV stores are far less crowded than mobile — which matters because installs, not features, are
  the bottleneck. Still open: (a) TV-origin room creation with `{room_code, tv_token}`, (b) claim-host
  handshake for the first phone to scan, (c) live connected-device sync to un-grey tiles for real rooms,
  (d) TV-safe in-game polish/overscan pass, (e) Fire TV/Android TV packaging. **TV-store billing is dodged
  entirely** because `tokens.get_wallet_id` already resolves to `user_id` when signed in — the host buys on
  their phone and the TV spends the same wallet. Scope: Fire TV + Google TV only; Tizen/webOS/tvOS/Roku are
  separate businesses. **Rank this against other install-getting work, not against other features.**

## Platform / Persistence

- **LLM model bump: hold 2.5-flash-lite → move early Oct 2026.** Stay on `gemini-2.5-flash-lite` (the current default for free + premium, `GEMINI_MODEL` / `GEMINI_PREMIUM_MODEL` in `backend/config.py`, plus the checked-in `.env` and gamma/prod VM `.env`) **through September 2026**, then migrate to the newer flash-lite (e.g. `gemini-3.x-flash-lite`) at the **beginning of October 2026**. Scope when the time comes: bump the two config defaults + `GEMINI_IMAGE_MODEL` if the image model also moves, update `backend/.env`, `model_comparison.py`, and the `test_remote_config.py` fixtures; verify generation quality/latency/cost on gamma first; then set `GEMINI_MODEL` on the gamma/prod VM `.env` and recreate the containers. No code migration — it's env-driven.
- **Party-scale lobby continuity follow-ups.** ~~Add explicit host cleanup/remove controls for offline seats~~
  **DONE 2026-07-27** — offline seats are held for `LOBBY_RECONNECT_GRACE_SECONDS` (90 min by default) so a slept phone
  keeps its place, but the host had no way to reclaim them early and some games gate their minimum-player
  check on the roster. Added organizer-only `REMOVE_OFFLINE_PLAYERS` (force-prune all) and `REMOVE_PLAYER`
  (one seat, by nickname), both LOBBY-only, broadcasting `PLAYERS_REMOVED`; `Room.remove_offline_lobby_player`
  **refuses to remove a connected player** — this is seat cleanup, not a kick tool, which is a separate
  feature with a different abuse surface. Inline "Remove them all" control next to the reconnecting count.
  LOBBY room expiry and room snapshot restore now also use the lobby grace, so an idle pre-start lobby is not removed by the generic 30-minute room TTL before guests have a chance to reconnect. Tests: backend 9, frontend 3. Still open: a Revelry-aware mobile sleep/lobby lull/reopen gamma Playwright scenario, and reconnect timing/status telemetry so long party pauses can be monitored before broad production reliance.
- **Rules surface for every game.** Phase 1 underway in `SPEC-GAME-RULES.md`: catalog-backed rules metadata, host picker rules modal, organizer/player lobby access, embedded Party Hub rules affordance, and backend/frontend regression tests. Follow-ups: room-config-aware rule overrides and post-start help access from the menu.
- **Deprecate SQLite runtime fallback.** Production and gamma now run on Supabase, but the codebase still keeps SQLite as the default local/dev adapter and as a documented rollback path. **Done (2026-07-21): fail-loud guards.** `config.validate_runtime_db_config()` runs at app startup and refuses to boot a deployed environment on SQLite (signal: Supabase creds present, or `ENVIRONMENT` names gamma/prod/production, while `DB_BACKEND != supabase`) — SQLite in a container is ephemeral, so this closes the silent-data-loss footgun; it also rejects `DB_BACKEND=supabase` with missing creds. `scripts/deploy-gcp.sh` refuses to deploy gamma/prod on SQLite unless `ALLOW_SQLITE_DEPLOY=true` (the deliberate-rollback escape hatch). Guard covered by `backend/tests/test_runtime_db_guard.py`. **Still open:** narrow SQLite to explicit local tests only, drop the deployed rollback assumption entirely now the cutover window is closed, and move remaining SQLite-specific schema/admin behaviour behind test-only fixtures or a clearly named legacy adapter.

## Growth / Monetization

Candidate next features, all wallet/DB-centric so they're fully unit-testable against SQLite (like the
2026-07-07 streak + referral build) and reuse the same idempotency + Supabase-override-list + template-RPC
patterns. Each should ship as: spec → backend + pytest → frontend + vitest → commit, plus a ready-to-apply
Supabase RPC via `sql/templates/games-schema.template.sql` and the `REFERRALS_ENABLED`-style activation gate.

- ~~**Game-history / stats screen.**~~ DONE 2026-07-27 — see SPEC-GAME-STATS (shipped as *games hosted*;
  streaks still open). Original note: Per-wallet "games played / won / favorite mode / current streak"
  summary. A `game_history` write on game completion + a `/stats` read endpoint + a simple stats UI.
  (Note: some history already exists server-side — audit `game_history`/`MAX_GAME_HISTORY` before building.)

## Growth — deferred follow-ups (from the 2026-07-07 overnight build)

- **Ad-supported sparks (SPEC-ADS).** Rewarded AdMob video → server-verified (SSV) spark grant. Needs an
  AdMob account + a device; not autonomously testable. `ads_enabled` flag already ships `false`.
- ~~**Share card: dynamic per-result OG image.**~~ **DONE 2026-07-27** — `GET /share/game/{token}/image.png`
  renders a 1200x630 card naming the winner (Pillow primitives, not SVG: cairosvg isn't installed and
  Pillow already ships). Uses Pillow's bundled scalable face so it works in the font-less slim container —
  pinned by a test that clears the system-font candidates. Never 500s (crawlers fetch once and don't
  retry): any failure 302s to the static brand image. Tests: backend 19. See SPEC-SHARE-CARD.
- ~~**Remote config: admin write endpoint.**~~ **DONE 2026-07-27** — the fetched config lives on IONOS and
  can't be written from the backend, so this shipped as a persisted **override layer** (`app_settings` table)
  deep-merged over the fetched config, with `GET/PUT/DELETE /admin/config` behind `ADMIN_API_KEY`. Overrides
  also drive `_get_ai_models()`, so the Oct 2026 model bump becomes an API call instead of a frontend deploy.
  Tests: backend 13. **Migration `20260727T010000_app_settings{,_gamma}.sql` not yet applied.**
- **Analytics: turn on.** Needs a PostHog project + `POSTHOG_API_KEY` (backend) / `VITE_POSTHOG_KEY` (build);
  code is wired and no-ops until set.
