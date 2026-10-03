# Production rollout plan — October 2026 repository review

Production promotion is pending. The current request authorizes gamma deployment; this document
is the plan for a subsequent production rollout. The release and validation record lives in
[DEPLOY.md](DEPLOY.md).

## Release gates

- Backend unit/integration and separate legacy E2E suites pass, including real local
  Postgres/PostgREST ownership, atomic quiz-save, purchase-history merge, and concurrency checks.
- Frontend unit tests and the complete TypeScript/Vite build pass. Local all-games/replay
  browser checks, gamma smoke, room/reconnect load, and the live Revelry matrix pass.
- Revelry live checks cover prepared-content creation/edit/start, organizer/player/watch
  handoffs, reconnect, cancellation, and completed results mirrored into the seeded gamma party.
  The stricter party/capability checks must work with the current Revelry consumer.
- Compare the production host-app catalog policy with gamma. Preserve production flags and
  existing disabled games; review any intended policy change separately.
- Review gamma logs after the tests for new exceptions, callback failures, unexpected room
  closures, and leftover test rooms. Record the running image revision and immutable image ID.

## Preparation and migrations

1. Choose the reviewed release commit recorded in the gamma ledger. Fetch it in a clean checkout
   and confirm the gamma running image label matches. Do not promote unrelated later work.
2. Capture production's immutable container image ID, runtime configuration, current Supabase
   function definitions, and a backup of the IONOS frontend before replacement. On October 3 the
   production image was `sha256:7b328e823c246c5d75627d21c5e67cc2ea8536190f8d933f6c0ffa7960ac7e5e`
   (container created August 9). Recheck at rollout time.
3. Apply only these reviewed production fragments through the Supabase Management API to project
   `hosbtyylacluziugwjfd`, in order:
   - `sql/migrations/20261003T000000_wallet_merge_identity.sql`
   - `sql/migrations/20261003T010000_atomic_quiz_save.sql`
   Never run a whole-schema Supabase CLI operation. Both changes are idempotent function
   replacements/additions, compatible with the old backend, and do not rewrite saved content.
4. Verify the target merge lock, drained-purchase handling, atomic quiz-save function, and
   service-role-only execution grants. Adapt the gamma verification SQL to the production
   prefix; use only disposable QA IDs, clean all rows, and verify no residue.
5. Keep `PARTY_GRACE_HOURS=0` in production and `ADS_ENABLED=false`. Preserve payment credentials,
   audience lists, callback signing secret/URL, data volume, and catalog policy. Do not copy the
   gamma environment file into production.

## Promotion and verification

1. Confirm room snapshots are enabled and healthy. Pick a quiet period, confirm active-room
   state is being snapshotted, and preserve the existing volume. Prefer promoting the exact
   validated gamma image: on the VM tag its captured immutable image ID as
   `revelry-backend:latest`, then run `./scripts/deploy-gcp.sh --skip-build --with-frontend` from
   the selected release checkout. The image uses runtime configuration and a same-origin bundled
   SPA, so production keeps its own env and flags. The script preflights the replacement and
   restores the previous image if startup or health fails. Verify the revision label afterward.
   If a rebuild is required, use `./scripts/deploy-gcp.sh --with-frontend` and revalidate the new
   artifact: backend requirements are currently unpinned, so a later rebuild may resolve different
   dependency versions.
2. Build the public IONOS bundle from the same checkout with `cd frontend && npm run ionos:build`.
   Inspect the production API origin and auth/config values. Upload the build and `.htaccess` to
   `~/revelryapp/games/`, following DEPLOY.md, keeping a restorable previous bundle. Test both
   `https://games.revelryapp.me/` and the backend-served fallback.
3. Run `scripts/regression.py --target prod`, production desktop/mobile smoke, and a synthetic
   room start/reconnect/replay/close. Verify purchases reject invalid input without completing a
   charge, host-app rooms omit referral CTAs, and production grace remains off.
4. With an authorized production QA party, validate the real Revelry host/player/watch flow,
   saved quiz editing, completed-result callback, return navigation, and cancellation. Never use
   an unrelated customer's room or content for these checks.
5. Monitor backend error and callback logs, room restoration, balance changes, and checkout
   errors during the rollout window and again the next day. Record results in DEPLOY.md.

## Rollback and follow-up

If health, room continuity, payments, or the Revelry contract regresses, restore the captured
production image using the same env, port, restart policy, and volume, and restore the IONOS
bundle as needed. Prefer leaving the backward-compatible database fixes applied. Restore an old
function definition only if the new function itself is demonstrated to cause the regression.
Verify health, reconnect, and economy after recovery and record the failure before retrying.

Native binaries require their own rebuild, simulator/device checks, signing, and store release.
Gamma/backend/IONOS deployment does not update installed native assets. Review the production
Capacitor build from this release separately; no store submission is included in this rollout.
