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
- **Party Quests MVP + LocalPlay staged check-in flow.** Implemented `party_quests` as an ambient social game with curated and AI-generated editable quest decks, party-scoped saved content, deterministic Host/Player/TV preview, duration/quest-count/confirmation/late-join settings, exact saved-version room materialization, first-real-player check-in auto-start, per-player boards, tap-confirm/honor completions, late joins, organizer/player/spectator sync, final reveal, idempotent host cancellation, safe callbacks, and local backend/frontend regression coverage. Gamma now has the content-type migration and four non-breaking authoring capabilities enabled; strict prepared-content check-in remains gated until Revelry gamma is deployed and the pointer/arming flow passes. Direct service-minted Party Quests authoring links now dispatch to the Party Quests editor instead of the quiz-only page and support type-safe create/edit resolution. Production remains quick-start-only. This staged flow **resolves two operational gaps hit in the field (2026-07-09):** (1) *check-in auto-start bypassing host setup* → now strict `requires_prepared_content_for_checkin` plus the setup UI + Host/Player/TV preview, so a check-in game must be configured first (gamma flip applied 2026-07-09); (2) *no host stop control* → now `POST /integrations/revelry/party-games/cancel` (`_cancel_revelry_session`, idempotent, one callback) with a "Cancel game" button in `PartyHubPage` and `LobbyScreen`. **Both are live on gamma only.** Residual: **production still has neither** until the prod rollout (see DEPLOY.md "Party Quests staged-authoring gamma rollout" → step 4), so a prod host today cannot self-cancel a stray check-in session — one had to be cancelled at the DB level on 2026-07-09 (`lp_b83ca5c0…`, "Rafting and Camping"). Follow-ups: pair-code confirmation, the multi-tab live Playwright rollout matrix, and the production rollout (DDL → deploy → authoring caps → strict flip).
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

- **Game-history / stats screen + game-completion badges (SPEC-GAME-STATS).** `game_history` was an
  in-memory ring, so lifetime stats were impossible and game-completion achievements stayed blocked.
  Adds a durable `game_results` table (room_code PK ⇒ a replayed podium can't double-count), collapses
  the 18 duplicated engine podium blocks into one `record_game_completion` choke-point, `GET /stats`
  (never 500s — reports `available:false` pre-migration so the code ships safely ahead of the table),
  Supabase parity via table-only + Python aggregation, `StatsSection` in the drawer (self-hiding, no
  flag), and 4 new badges (`first_game`/`ten_games`/`big_party`/`explorer`). Copy says **hosted**, not
  played: guests never authenticate, so the host's wallet is the only attributable identity. Tests:
  backend 15, frontend 7. **Not yet deployed / table not yet applied on Supabase.**

- **Odd One Out: socket + frontend wiring (SPEC-GAME-ODD-ONE-OUT §9).** Engine done and tested (30
  tests, commit `93feb599`); catalog entry deliberately `launchable: False` / `status: planned` so a
  game that can't start is never offered. Remaining: the ~48 socket_manager touchpoints listed in the
  spec, plus organizer/player screens. Do it test-first — assert over the wire that a non-odd
  player's payload never contains the minority prompt, since per-viewer prompt scoping is what's most
  likely to break in translation.
- **Derive socket_manager's game-type sets from the catalog.** Adding a game means editing ~12
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

## Platform / Persistence

- **LLM model bump: hold 2.5-flash-lite → move early Oct 2026.** Stay on `gemini-2.5-flash-lite` (the current default for free + premium, `GEMINI_MODEL` / `GEMINI_PREMIUM_MODEL` in `backend/config.py`, plus the checked-in `.env` and gamma/prod VM `.env`) **through September 2026**, then migrate to the newer flash-lite (e.g. `gemini-3.x-flash-lite`) at the **beginning of October 2026**. Scope when the time comes: bump the two config defaults + `GEMINI_IMAGE_MODEL` if the image model also moves, update `backend/.env`, `model_comparison.py`, and the `test_remote_config.py` fixtures; verify generation quality/latency/cost on gamma first; then set `GEMINI_MODEL` on the gamma/prod VM `.env` and recreate the containers. No code migration — it's env-driven.
- **Party-scale lobby continuity follow-ups.** ~~Add explicit host cleanup/remove controls for offline seats~~
  **DONE 2026-07-27** — offline seats are held for `LOBBY_RECONNECT_GRACE_SECONDS` (10 min) so a slept phone
  keeps its place, but the host had no way to reclaim them early and some games gate their minimum-player
  check on the roster. Added organizer-only `REMOVE_OFFLINE_PLAYERS` (force-prune all) and `REMOVE_PLAYER`
  (one seat, by nickname), both LOBBY-only, broadcasting `PLAYERS_REMOVED`; `Room.remove_offline_lobby_player`
  **refuses to remove a connected player** — this is seat cleanup, not a kick tool, which is a separate
  feature with a different abuse surface. Inline "Remove them all" control next to the reconnecting count.
  Tests: backend 6, frontend 3. Still open: a Revelry-aware mobile sleep/lobby lull/reopen gamma Playwright scenario, and reconnect timing/status telemetry so long party pauses can be monitored before broad production reliance.
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
- **Share card: dynamic per-result OG image.** v1 uses a static branded image; a rendered SVG→PNG per-result
  card would unfurl richer. (Persisting share snapshots to DB — **done** 2026-07-21, see Done section.)
- ~~**Remote config: admin write endpoint.**~~ **DONE 2026-07-27** — the fetched config lives on IONOS and
  can't be written from the backend, so this shipped as a persisted **override layer** (`app_settings` table)
  deep-merged over the fetched config, with `GET/PUT/DELETE /admin/config` behind `ADMIN_API_KEY`. Overrides
  also drive `_get_ai_models()`, so the Oct 2026 model bump becomes an API call instead of a frontend deploy.
  Tests: backend 13. **Migration `20260727T010000_app_settings{,_gamma}.sql` not yet applied.**
- **Analytics: turn on.** Needs a PostHog project + `POSTHOG_API_KEY` (backend) / `VITE_POSTHOG_KEY` (build);
  code is wired and no-ops until set.
