# LocalPlay Backlog

## Platform / Persistence

- **Deprecate SQLite runtime fallback.** Production and gamma now run on Supabase, but the codebase still keeps SQLite as the default local/dev adapter and as a documented rollback path. Plan a follow-up to narrow SQLite to explicit local tests only, remove deployed rollback assumptions after the Supabase cutover window, make deploy/runtime fail clearly if a deployed environment is accidentally configured with `DB_BACKEND=sqlite`, and move remaining SQLite-specific schema/admin behavior behind test-only fixtures or a clearly named legacy adapter.
