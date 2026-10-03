# Production rollout plan — October 2026 repository review

Production promotion is pending. The current request authorizes gamma deployment; this document
is the plan for a subsequent production rollout. The release and validation record lives in
[DEPLOY.md](DEPLOY.md).

## Release gates

- Backend unit/integration and separate legacy E2E suites pass, including real local
  Postgres/PostgREST ownership, atomic quiz-save, purchase-history merge, and concurrency checks.
- Frontend unit tests and the complete TypeScript/Vite build pass. Local all-games/replay
  browser checks, gamma smoke, room/reconnect load, and the live Revelry matrix pass.
- All five required CI jobs pass for the selected source commit. The visual screenshot step
  remains advisory until reviewed Linux baselines are committed; record that limitation.
- Revelry live checks cover prepared-content creation/edit/start, organizer/player/watch
  handoffs, reconnect, cancellation, and completed results mirrored into the seeded gamma party.
  The stricter party/capability checks must work with the current Revelry consumer.
- Resolve the external Revelry consumer's workspace scaling issue before production promotion.
  With at least 86 prepared-content rows, verify workspace latency fits the production client's
  request deadline and unchanged refreshes avoid per-item database reads/writes. The gamma
  harness's bounded 30-second workspace request is a diagnostic allowance, not evidence that
  this performance gate is satisfied; other Revelry harness API requests remain bounded at 12 seconds.
- The Revelry matrix starts every game advertised as launchable, including Odd Question.
  Managed podium continuation returns to the authenticated hub and starts a new session id;
  standalone replay preserves the room/roster and clears previous answers/results.
- Compare the production host-app catalog policy with gamma. Preserve production flags and
  existing disabled games; review any intended policy change separately.
- Review gamma logs after the tests for new exceptions, callback failures, unexpected room
  closures, and leftover test rooms. Record the running image revision and immutable image ID.

October 3 diagnostics measured the seeded Revelry gamma workspace at 16.22 seconds with 86
prepared-content rows, while LocalPlay's corresponding resolve completed in 0.69 seconds.
The adjacent Revelry consumer synchronously selects and updates each prepared item during
workspace normalization, implying roughly 172 sequential database round trips for this fixture.
Completed-quiz callbacks and mirrored results worked in the gamma flow; large-library workspace
latency remains unresolved. The final gamma validation record belongs in DEPLOY.md.

The follow-up belongs in the Revelry consumer repository: fetch the party's existing prepared
setups once, map current/previous content versions, skip unchanged rows, and batch necessary
writes while preserving setup IDs, party ownership, locked/used status, and version mapping.
Verify those contracts alongside the 86-row-or-larger latency check. Keep pre-existing QA content;
future harness cleanup should track and remove only content/session IDs created by that test run.
This LocalPlay review does not change the external repository or remove historical fixtures.

## Preparation and migrations

1. Choose the reviewed release commit recorded in the gamma ledger. Fetch it in a clean checkout
   and confirm the gamma running image label matches. Record that exact source revision and
   immutable image ID; later documentation or test-only changes need not change the runtime revision.
   Do not promote unrelated later work.
2. Capture production's immutable container image ID, runtime configuration, current Supabase
   function definitions, and a backup of the IONOS frontend before replacement. On October 3 the
   production image was `sha256:7b328e823c246c5d75627d21c5e67cc2ea8536190f8d933f6c0ffa7960ac7e5e`
   (image created August 9). Recheck at rollout time.
3. Apply only these reviewed production fragments through the Supabase Management API to project
   `hosbtyylacluziugwjfd`, in order:
   - `sql/migrations/20261003T000000_wallet_merge_identity.sql`
   - `sql/migrations/20261003T010000_atomic_quiz_save.sql`
   Never run a whole-schema Supabase CLI operation. Both changes are idempotent function
   replacements/additions, compatible with the old backend, and do not rewrite saved content.
4. Run `sql/verification/20261003_persistence_review.sql`, which targets only `games_` and verifies
   the merge lock, drained/legacy/fresh purchase handling, atomic quiz-save ownership and rollback,
   and service-role-only execution grants. It creates and removes disposable QA rows in one
   transaction. Verify no QA residue and confirm the `games_gamma_` definitions are unchanged.
5. Keep `PARTY_GRACE_HOURS=0` in production and `ADS_ENABLED=false`. Preserve payment credentials,
   auth audience lists, callback signing secret/URL, data volume, and catalog policy. Confirm
   `DB_BACKEND=supabase`, `TABLE_PREFIX=games_`, production `PUBLIC_BASE_URL`, and the production
   callback endpoint. Keep `REVELRY_CALLBACK_SECRET` empty unless a deliberate rotation is planned;
   normal callbacks use `REVELRY_INTEGRATION_SECRET`. Do not copy the gamma environment file into
   production. The deploy script upserts Google/Apple audience settings from local variables or
   defaults, so explicitly pass the reviewed existing `GOOGLE_WEB_CLIENT_ID`,
   `GOOGLE_IOS_CLIENT_ID`, `GOOGLE_ALLOWED_CLIENT_IDS`, `APPLE_WEB_CLIENT_ID`,
   `APPLE_NATIVE_CLIENT_ID`, and `APPLE_ALLOWED_CLIENT_IDS` when preserving custom production values.

## Promotion and verification

1. Confirm room snapshots are enabled and healthy. Pick a quiet period, confirm active-room
   state is being snapshotted, and copy the snapshots before the swap while preserving the existing
   volume. Snapshots contain room credentials; keep the backup private on the VM. Prefer promoting
   the exact validated gamma image: on the VM tag its captured immutable image ID as
   `revelry-backend:latest`, then run `./scripts/deploy-gcp.sh --skip-build --with-frontend` from
   the selected release checkout. The image uses runtime configuration and a same-origin bundled
   SPA, so production keeps its own env and flags.
   Confirm the image's baked Google/Apple web client IDs and Cast app ID match production, and
   that its frontend uses the same-origin API/config paths rather than gamma URLs. Rebuild and
   revalidate if those build-time values differ from the production requirements.
   The script preflights the replacement and restores the previous image if startup or health fails.
   This shallow health gate does not verify database RPCs or callbacks; complete the functional
   checks below before declaring the
   rollout successful. Verify the revision label afterward.
   If a rebuild is required, use `./scripts/deploy-gcp.sh --with-frontend` and revalidate the new
   artifact: backend requirements are currently unpinned, so a later rebuild may resolve different
   dependency versions.
2. Build the public IONOS bundle from the same checkout with `cd frontend && npm run ionos:build`.
   Inspect the production API origin and auth/config values. Compare `dist/config.json` with the
   live production file and preserve live overrides unless a reviewed configuration change is
   intended. Upload assets additively and the build/`.htaccess` to `~/revelryapp/games/`, following
   DEPLOY.md, keeping a restorable previous bundle and its config. Keep old hashed assets through
   the rollback window. Test both `https://games.revelryapp.me/` and the backend-served fallback,
   and record each deployed entry-bundle hash.
3. Run `scripts/regression.py --target prod`, production desktop/mobile smoke, and a synthetic
   room start/reconnect/replay/close. Verify purchases reject invalid input without completing a
   charge, host-app rooms omit referral CTAs, and production grace remains off.
4. With an authorized production QA party, validate the real Revelry host/player/watch flow,
   two edits to the same unused saved quiz (both reflected in the Revelry mirror), completed-result
   callback, return navigation, fresh-session podium continuation, and cancellation. Verify public
   results omit private role/answer/credential fields. Never use an unrelated customer's room or
   content for these checks. Repeat app/universal-link return navigation on an actual native client;
   browser-only gamma checks do not establish native return behavior.
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
