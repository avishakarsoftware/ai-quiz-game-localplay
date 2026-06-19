# LocalPlay Backlog

## Done

- **Party Quests MVP.** Implemented `party_quests` as an ambient social game with curated host-selectable packs, editable quest list, duration/quest-count/confirmation/late-join settings, per-player quest boards, tap-confirm/honor completions, late joins, organizer/player/spectator sync, final reveal, result summary, LocalPlay setup UI, and static Revelry-compatible quick-start catalog metadata. Follow-ups: AI generation, pair-code confirmation, multi-tab Playwright, and host-app policy enablement/smoke.
- **Mafia standalone MVP.** Implemented local standalone `mafia` with secret roles, role reveal, Mafia/Detective/Doctor night actions, Night Reads for every living player, aggregate-safe day discussion fuel, public-safe sync, day votes, role reveal on elimination, Town/Mafia win conditions, socket tests, and frontend organizer/player/spectator surfaces. Gamma deploy and multi-device Playwright QA remain the next launch gate.
- **Find Someone Who MVP.** Implemented standalone `find_someone` social bingo with default prompt deck, per-player generated cards, tap-confirm and honor modes, line/corners/blackout claims, host/spectator aggregate sync, late-join card assignment, and one-player start support for future check-in auto-start flows. Revelry check-in exposure remains a host-app setting/bridge follow-up.

## Platform / Persistence

- **Rules surface for every game.** Spec complete in `SPEC-GAME-RULES.md`. Next implementation pass: add catalog-backed rules metadata for every launchable game, host picker rules modal, organizer/player lobby rules access, and Revelry catalog propagation tests.
- **Deprecate SQLite runtime fallback.** Production and gamma now run on Supabase, but the codebase still keeps SQLite as the default local/dev adapter and as a documented rollback path. Plan a follow-up to narrow SQLite to explicit local tests only, remove deployed rollback assumptions after the Supabase cutover window, make deploy/runtime fail clearly if a deployed environment is accidentally configured with `DB_BACKEND=sqlite`, and move remaining SQLite-specific schema/admin behavior behind test-only fixtures or a clearly named legacy adapter.
