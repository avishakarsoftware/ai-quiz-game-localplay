# LocalPlay Backlog

## Done

- **Mafia standalone MVP.** Implemented local standalone `mafia` with secret roles, role reveal, Mafia/Detective/Doctor night actions, Night Reads for every living player, aggregate-safe day discussion fuel, public-safe sync, day votes, role reveal on elimination, Town/Mafia win conditions, socket tests, and frontend organizer/player/spectator surfaces. Gamma deploy and multi-device Playwright QA remain the next launch gate.
- **Find Someone Who MVP.** Implemented standalone `find_someone` social bingo with default prompt deck, per-player generated cards, tap-confirm and honor modes, line/corners/blackout claims, host/spectator aggregate sync, late-join card assignment, and one-player start support for future check-in auto-start flows. Revelry check-in exposure remains a host-app setting/bridge follow-up.

## Platform / Persistence

- **Rules surface for every game.** Add a concise, structured rules section to each catalog game. Hosts should be able to open/read rules from the game picker before selecting a game. Players should be able to open/read the same game rules from the join/lobby screen before the host starts. Rules should be short, mobile-friendly, and game-specific: objective, player count, round flow, scoring/winning, important privacy/role notes, and any physical-world setup needed. Back the UI with catalog metadata or a shared rules registry so standalone, Revelry hub, player lobby, and future spectator/help surfaces stay consistent.
- **Deprecate SQLite runtime fallback.** Production and gamma now run on Supabase, but the codebase still keeps SQLite as the default local/dev adapter and as a documented rollback path. Plan a follow-up to narrow SQLite to explicit local tests only, remove deployed rollback assumptions after the Supabase cutover window, make deploy/runtime fail clearly if a deployed environment is accidentally configured with `DB_BACKEND=sqlite`, and move remaining SQLite-specific schema/admin behavior behind test-only fixtures or a clearly named legacy adapter.
