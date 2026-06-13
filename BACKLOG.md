# LocalPlay Backlog

## Done

- **Find Someone Who MVP.** Implemented standalone `find_someone` social bingo with default prompt deck, per-player generated cards, tap-confirm and honor modes, line/corners/blackout claims, host/spectator aggregate sync, late-join card assignment, and one-player start support for future check-in auto-start flows. Revelry check-in exposure remains a host-app setting/bridge follow-up.

## Platform / Persistence

- **Deprecate SQLite runtime fallback.** Production and gamma now run on Supabase, but the codebase still keeps SQLite as the default local/dev adapter and as a documented rollback path. Plan a follow-up to narrow SQLite to explicit local tests only, remove deployed rollback assumptions after the Supabase cutover window, make deploy/runtime fail clearly if a deployed environment is accidentally configured with `DB_BACKEND=sqlite`, and move remaining SQLite-specific schema/admin behavior behind test-only fixtures or a clearly named legacy adapter.
