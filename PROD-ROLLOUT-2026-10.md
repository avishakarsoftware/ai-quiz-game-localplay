# October 2026 release candidate promotion plan

Saved 2026-10-03; publication record updated 2026-10-04. **Status: LocalPlay maintenance candidate qualified in gamma; both scoped Revelry maintenance branches published. Separate Revelry deployment approval and live qualification remain pending. Production has not yet been changed.**
This runbook covers qualification and later promotion of LocalPlay's reviewed backend, bundled
SPA, two persistence migrations, public IONOS web bundle, and Revelry integration. The human release owner authorized review, necessary fixes, commit/push and deployment through
production, with rollback readiness and protection of the shared databases. The two
reviewed LocalPlay RPC fragments are in scope. After automatic approval review initially rejected
publication to the separate Revelry repository, Avi explicitly replied "great. commit and push"
to the approval request. Both reviewed maintenance branches are now published and their remote
commit identities verified; that follow-up authorizes publication, with consumer image deployment
still pending. Preserve
existing production feature policy; no customer charges, native store submission or unrelated
Revelry work is included. Actual environment state remains in [DEPLOY.md](DEPLOY.md).

## 1. Candidate identity and scope

| Item | Proposed candidate / recorded evidence |
|---|---|
| Runtime source | `dfcb266e5b6a93bad344d7e0c7c0975363844c42`, ownership-404 maintenance layer on qualified `0bf94209` base |
| Validated gamma Docker image ID | `sha256:e318edd8cd2b812370b665b42ada8afdf4cbfdc600ff510d700501277ae6b275`; parent `sha256:394e8061a2923cb295bc02566a4884facdcadfcefc4fb17a287cb3be90e57051` retained |
| Source CI | [37178586787](https://github.com/avishakarsoftware/ai-quiz-game-localplay/actions/runs/37178586787), all five required jobs passed for `dfcb266e` |
| Gamma | `https://gamesapi-gamma.revelryapp.me/`; `games-backend-gamma`, loopback port `8004`, Supabase `games_gamma_` |
| Production backend | `https://gamesapi.revelryapp.me/`; `games-backend`, loopback port `8000`, Supabase `games_` |
| Production web | `https://games.revelryapp.me/`; IONOS `~/revelryapp/games/` |
| Shared VM | Project `revelryapp`, VM `revelry-backend`, zone `us-central1-a` |
| Shared Supabase project | `hosbtyylacluziugwjfd`; contains both environments and unrelated applications |
| Last observed production image | `sha256:7b328e823c246c5d75627d21c5e67cc2ea8536190f8d933f6c0ffa7960ac7e5e`, created August 9; re-capture at rollout |
| Production source provenance | Unlabeled mixed artifact: live `main.py` matches `1179b530`; `socket_manager.py` matches `40b8dd09`. Recover by captured image, not inferred source |
| Documentation revision | Later docs/test-only commits, including `a555fed5`, do not change deployed runtime; record final plan/evidence commit separately |
| IONOS artifact | Built from `0bf94209`, production OAuth/analytics inputs and original live config preserved; SHA-256 `cb53d7d7f1a67e2b67dd0c9e4c21c88d8e62ce67e020c6a67bc55cdfd96c846b`; 16 mixed-browser / four deployed-schema checks passed with intercepted writes/sockets; actual production acceptance pending |
| Revelry backend/client pair | Published maintenance commits `ada6f6e9` on gamma `06df3136` and `f4497edb` on production `e8b97eca`; original frontend/dependencies/config retained; deployment and staged/live qualification pending |

The Docker value is an immutable local **image ID**, not a registry manifest digest or pullable
registry reference. Confirm it exists on the VM; retain/export it and the previous production image.
A missing artifact or incompatible build input requires a newly built and qualified candidate.

Scope includes party/content/capability boundaries, atomic quiz ownership/saving, wallet purchase
history conservation, replay charging, timer/socket closure, reconnect/result recovery, managed
continuation, native guest URLs and Odd Question launch. Production keeps its existing catalog
and flags; promotion does not automatically enable gamma games, gifting, achievements, analytics,
ads or party grace. Native binaries are separate artifacts; compatibility with installed clients
still needs evidence for affected paths.

## 2. Owners, evidence and decision

Release owner: Avi; implementation, QA, deploy and rollback operator: Codex, with independent
agent reviews. Authorization is the latest direct production-rollout request. Record who
accepted each gate, who executes deployment, and who is available to execute rollback.

| Role | Responsibility |
|---|---|
| Release owner | Freeze candidate, resolve gates/exceptions, present go/no-go evidence and obtain rollout authorization |
| LocalPlay maintainer | Runtime, persistence, auth/economy, image/frontend compatibility and restoration |
| Revelry maintainer | External workspace fix, consumer deployment, callback/session contracts and recovery pair |
| QA owner | Gamma qualification, canonical production web/device smoke, run-owned fixtures and cleanup |
| Deploy operator | Private backups, targeted SQL, image swap, IONOS publication, logs and recovery |
| Product/payment owner | Enabled-path scope, camera/native exceptions, approved financial QA and reconciliation |

Keep a durable release evidence directory containing a manifest, CI links, timestamped reports,
sanitized logs, config/policy diffs, SQL hashes/results, image inspection, frontend hashes, owned
QA IDs and signed decision. Copy useful temporary reports into durable storage; `/tmp` and a
green `/health` alone are insufficient. Secrets, env files, launch URLs/tokens, room snapshots
and function backups belong in private operator storage, never Git or a public web directory.

The manifest must record runtime source/image, plan/evidence commit, IONOS artifact/hash/build
inputs, production config/policy comparison, SQL hashes, Revelry backend/client revisions and
effective deadlines, previous artifacts, gate owners/status, exceptions, authorization, window,
rollback location and observation result. Runtime/dependency/build/contract-config changes
invalidate affected evidence. Docs-only changes require document checks, not runtime redeployment.

## 3. Gate register

These statuses describe October 3 evidence; recheck drift before the window. **Every gate must
pass at its assigned stage; unknown or failed prerequisites block that stage.** Exceptions need
scope, evidence, owner, expiry and follow-up. Integrity/ownership/callback failures and the
unresolved workspace defect cannot be waived by increasing a harness timeout.

Stages: G1–G5, G7–G8, G9's candidate/provider/device qualification or accepted scope decisions,
and G10's rollout authorization are required before production writes. G6's backup/hash preparation
is also required then; its authorized live SQL/verification runs during the window and must pass
before runtime swap. Production-only G9 checks, section 10 acceptance/bake and next-day review
must pass before declaring promotion complete. The authorization record lists these scheduled
production checks as pending, with abort/recovery actions; it does not mark them passed in advance.

| Gate | Current evidence | Remaining exit criterion |
|---|---|---|
| G1 — Local and CI | Prior base: 1,655 backend + 20 legacy E2E, 516 frontend. New `dfcb266e`: 1,617 isolated unit/API passes, 73 local DB skips, 40 focused passes and all five exact-source CI jobs green, including Postgres/PostgREST and browser suites | Confirm frozen source/CI unchanged; counts overlap and must not be summed |
| G2 — Gameplay | 78 gamma all-games/replay passes on `25301590`, one Photo Clue camera waiver; current narrow delta adds ownership-specific HTTP 404, with 40 focused passes, full unit/API and exact-source CI | Maintainer accepts the unchanged-gameplay delta based on focused/full/exact-source CI and gamma API/recovery; repeat integration after consumer remediation |
| G3 — Final artifact | Current image: 64 API checks, live owner/save/refusal checks and actual image-swap recovery passed. Prior qualified base: eight rooms/32 sockets/reconnect/full cleanup | New candidate: 64 fresh API checks, live owner create/two edits/stranger POST/GET/DELETE 404 + unchanged data + cleanup, and image-swap lobby/answered-quiz recovery passed; repeat after consumer remediation |
| G4 — Real Revelry | Three embedded workflows + four launch/staging/reconnect matrix tests; mirrored completion, fresh Odd Question continuation, image save | Repeat with fixed consumer pair; player/watch browser and deployed-client return evidence beyond token minting |
| G5 — Workspace scale | Previous defect: 16.22s for 86 items. Reviewed fix passes 2,904 gamma / 2,700 prod baseline tests; unchanged 86-item fixture makes one read, zero writes | External fix and large-library deadline/identity/idempotency checks in section 4 pass |
| G6 — Persistence | Fresh full/focused backups and isolated restores passed; exact two fragments + verification passed offline, with all 465 table contents unchanged; live production SQL pending | Backups; authorized targeted production fragments; verification, ACL, schema-cache and API checks before swap |
| G7 — Artifacts/config | Exact gamma identity/CI rechecked; frozen IONOS bundle preserves production OAuth, analytics and original config | Frozen bundle/30 hashes and 16 mixed-browser/four schema checks passed; production candidate CORS and canonical publication checks remain |
| G8 — Recovery | Immutable old image/env/volume and IONOS backups captured, backend rollback check passed, both DB restores passed; current gamma owned-lobby/answered-quiz restart drill passed, zero extra debit and cleanup verified | Actual old-to-new gamma recovery passed; refreshed rollback check and private candidate export passed. Production-only smoke/observation still pending |
| G9 — Enabled-path gaps | Camera automated waiver; gamma Stripe unset; native return/real paid checkout not established | Manual enabled-path evidence or explicit scope exclusion; invalid-input guards do not prove successful payment/refund |
| G10 — Decision | Human rollout authorization recorded; production checks still pending | Named owners, gates/exceptions, QA scope/budgets, baseline/thresholds, window and recovery signed |

Visual screenshots remain advisory until reviewed Linux baselines exist; required functional CI
remains blocking. If an untested path stays disabled in production, record the exclusion and
verify unchanged policy. Do not silently waive a path already advertised to production users.

## 4. Remediate Revelry, then requalify gamma

The fix belongs in the adjacent Revelry consumer repository. Normalization synchronously selects
and updates each item even unchanged; roughly 172 sequential DB round trips for the measured
86-item fixture is an inference from that code. LocalPlay resolve already uses bounded reads.
Deleting historical QA content or lowering the list limit would conceal the defect.

1. Fetch party setups once, map current/previous content versions, skip unchanged rows, and batch
   needed writes. Preserve setup IDs, ownership, used/locked/completed state, result pointers and
   version mappings. Unchanged refresh must not write rows or churn `updated_at`.
2. Verify cold/warm refresh, create plus two edits to unused content, used-content versioning,
   concurrent refresh and completion-callback races. Compare IDs/state/feed/results; no duplicate
   or cross-party setup and no stale active session after cancellation.
3. Deploy the fix to Revelry gamma under that repository's workflow. Record consumer backend,
   client, LocalPlay runtime/image and effective timeout/proxy config as a tested pair.
4. Retain the historical large fixture; test at least 86 ready items and the expected maximum
   production library size agreed by owners, plus a small control and isolated second party.
   Record payload size, query counts, cold/warm latency, p50/p95/max and errors. Proposed sample:
   at least three cold and twenty unchanged warm refreshes.
5. Capture the effective shortest deadline **per request leg**: deployed client/proxy deadline
   for Revelry workspace, and Revelry's separate upstream LocalPlay deadline. Source defaults are
   30s for client reads and 10s for the upstream workspace call; overrides may differ. Require
   zero timeouts and p95 at most 80% of each applicable deadline. This proposed release headroom
   criterion needs actual seconds recorded before sign-off; do not relax deadlines to hide DB work.
   The harness's bounded 30s diagnostic allowance is neither an SLA nor remediation.
6. Repeat embedded and launch/staging/reconnect suites. Every advertised launchable gamma game
   starts, including Odd Question; verify all three launch scopes and representative real
   organizer/player/watch screens. Complete a quiz, mirror results, return to the authenticated
   hub and create new LocalPlay **and** Revelry session IDs while old completion/feed/results stay
   intact. Standalone replay retains room/roster, clears old answers and charges only on successful
   start. Include media/alt text and two saved-quiz edits reflected in Revelry.
7. Review logs, callback acceptance/idempotence/privacy and owned session/room/content cleanup.
   Remove only positively identified run-created artifacts via supported APIs; retain historical
   fixtures. Record synthetic wallet/ledger retention rather than broad SQL cleanup. Keep handoff
   URLs/tokens out of stored reports.

A contract-compatible consumer fix may qualify the same LocalPlay image. A changed boundary
requires a new LocalPlay candidate. Revelry's owner must supply its production rollout/rollback
procedure. Prefer its backward-compatible fix first, verify production, then promote LocalPlay;
a coordinated contract change needs an agreed order and tested recovery pair. LocalPlay rollback
does not roll back Revelry, and old/new combinations must not be assumed compatible.

## 5. Freeze artifacts before the window

1. Use a clean checkout at the runtime revision. Verify gamma image ID, OCI revision label,
   `linux/amd64`, bundled `/app/static` and baked frontend values. Freeze concurrent build/tag/
   deploy/policy operations while preparing the manifest. `:latest` is not release identity.
2. The ownership-404 follow-up is qualified as a backend-only layer on the validated base,
   copying main.py, db.py, supabase_db.py and persistence_errors.py with exact committed-source
   labels. Dependencies and SPA are preserved; all five exact-source CI jobs, gamma HTTP and
   actual image-swap recovery passed. Section 8 uses the verified new immutable image. A further
   runtime change requires repeat qualification and a new identity.
   Its SPA uses same-origin API and `/config/public`; compare
   baked Google/Apple web clients, Cast/build flags and URLs with production. No gamma origin may
   be baked in. If incompatible, build/requalify a new image in gamma. Backend requirements and
   Docker base tags are unpinned: even the same-source rebuild may resolve different dependencies.
3. Build the **separate IONOS artifact** at selected source: `npm ci`, then `npm run ionos:build`
   in `frontend/`. Explicitly supply reviewed production `VITE_GOOGLE_CLIENT_ID` and
   `VITE_APPLE_CLIENT_ID`; a clean checkout can otherwise bake empty clients while passing the API
   guard. Review Cast, Bingo and analytics inputs. The wrapper forces production API/config/web
   URLs and Apple redirect. Never upload the same-origin gamma image SPA to IONOS.
4. Inspect routes/assets/auth/service-worker bypass. Compare generated `config.json` with live
   production remote config and DB overrides; preserve live settings unless separately reviewed.
   Hash/archive the final artifact after approved config preservation; publish those exact bytes.
   Qualify mixed-version overlap in an isolated environment: current IONOS/open tabs/installed
   clients against the candidate backend, and the candidate IONOS bundle against the captured
   previous backend. Promotion and recovery can leave these combinations briefly live. If an
   incompatible pairing exists, resolve it or agree a coordinated maintenance/recovery sequence
   before authorization; do not rely on single-component rollback to restore compatibility.
5. Designate the production QA party, synthetic actors/device IDs, run naming and allowed start/
   LLM/payment budgets. Prepare run-ID manifest and cleanup checklist. Broad gamma matrices and
   load tests must not target production.

Read-only identity check for the future operator:

```bash
gcloud compute ssh revelry-backend --project=revelryapp --zone=us-central1-a --command='docker inspect games-backend-gamma --format "{{.Image}}"; docker image inspect sha256:e318edd8cd2b812370b665b42ada8afdf4cbfdc600ff510d700501277ae6b275 --format "{{.Id}} {{.Architecture}} {{index .Config.Labels \"org.opencontainers.image.revision\"}}"'
```

## 6. Recovery package and pre-window baseline

The human has authorized this rollout. Qualification and rollback preparation remain prerequisites
to executing production changes; do not treat authorization as evidence of successful checks.
Before any production write:

- Re-capture production image/container settings, health, canonical IONOS entry hash, callback,
  public config, enabled games and policy. Abort unexplained drift.
- Privately back up `/home/revelry-games/app/.env`, container inspection, current mounted volume
  `/home/revelry-games/revelry-data`, snapshots and both image artifacts. Use restrictive
  permissions; snapshots contain room credentials. Confirm enabled/writable snapshots and recent
  timestamps. Default periodic interval is 10s, with a final save on graceful shutdown.
- Save production and gamma RPC definitions/existence/ownership/ACLs. Confirm Supabase backup/
  recovery availability and recovery point. The deploy script's SQLite copy is **not** a Supabase
  backup. An isolated LocalPlay regression must not trigger whole shared-project restoration.
- Back up IONOS stable files (`index.html`, config, service worker/manifest, `.htaccess`, legal/
  static files) plus referenced assets outside the public docroot. Verify restoration is possible;
  retain old hashed assets on the site through the rollback window.
- Record 15 minutes of baseline health, errors/5xx/callback failures, workspace latency, resources,
  room count and checkout/webhook outcomes. Assign probe/log cadence and monitoring sources;
  existing metrics are incomplete, so include logs and explicit QA observations.
- Prefer a quiet window with no customer rooms. Private admin-bearer `/admin/stats` gives counts,
  not a safe customer-room identity list. Coordinate Revelry and pause new launches only through
  an authorized/reviewed mechanism if necessary. Current singleton/process-local rooms cannot
  support percentage canaries or rolling deployment.

Restart is a brief socket interruption with recovery, not zero downtime. Qualify current gamma
restart with owned lobby/answered-quiz/score state, completion and managed reconnect; review
old-image snapshot compatibility in isolation. Production's old image has mixed source provenance; the captured immutable artifact is the rollback authority.
Quiz countdown restarts while scoring keeps original start time; Housie needs host resume and
Musical Chairs/Mafia timed substates may need host recovery. If customer rooms cannot drain,
disclose/accept these edges with the release owner. Avoid swapping during game-start/payment
operations; reconcile unknown outcomes against durable ledger/idempotency/session state before
retry. Record a maximum accepted outage and recovery-time budget based on the gamma restart/
rollback drill before authorization; assign incident escalation if that budget is exceeded.
Keep deploy and rollback operators available throughout the window.

## 7. Production persistence prerequisite

After authorization/backups, apply only these production fragments through the Management API
`/v1/projects/hosbtyylacluziugwjfd/database/query`, in order, with a private access token. Never
print credentials, run whole-schema operations, `supabase db push`, `db reset`, `db diff --linked`,
or substitute gamma files on the shared project.

| File | SHA-256 |
|---|---|
| `sql/migrations/20261003T000000_wallet_merge_identity.sql` | `0e9a0aafba42d6bf55476c6dd9003be0ba7f1d8910d1ec2ea00d7dcc14f10566` |
| `sql/migrations/20261003T010000_atomic_quiz_save.sql` | `3a43cd2f4e661f1449cba2e588a28497354f419f58b7bd6f7621ba9b7c349c95` |
| `sql/verification/20261003_persistence_review.sql` | `3fdbf7e5f0cb931879f5573eacc5e4fe42a6a79b1350cc09c380ab31adc65801` |

1. Compare hashes and `games_` scope; capture existing merge/save function definitions/existence,
   ownership and execution ACLs, plus gamma comparison definitions.
2. Apply wallet merge, then atomic quiz save. They are idempotent function replacements/additions
   compatible with old backend, without a saved-content rewrite. New adapter requires quiz RPC;
   do not swap runtime if either step fails. Partial success may stay applied with old runtime;
   record state and retry only the failed step after diagnosis.
3. Run the existing production verification SQL: one DO transaction, uniquely named synthetic
   rows, cleanup before success and statement rollback on failure. Verify lock, drained/legacy/
   fresh entitlement conservation, same-second ledger order, owner refusal and failed-save
   rollback. Inspect both RPC signatures and service-role-only grants explicitly.
4. Confirm no verification residue, expected definitions, unchanged `games_gamma_`/unrelated
   objects and PostgREST cache visibility. Perform bounded supported API/RPC save/read/two-edits/
   owner-refusal on designated QA identities using deployed credentials. Never point disposable
   local parity suites at hosted production.
5. Save results/update ledger before swap. `/health` and printed DB env do not prove DB or RPC
   readiness. A failed migration gate leaves the previous runtime serving production.

## 8. Backend promotion

Preserve production env/volume. Confirm Supabase `games_`, production public/site/checkout/config
origins, media path `prod`, CORS/proxy settings, callback
`https://api.revelryapp.me/api/games/localplay/callback`, signing/JWT/session/payment keys and
catalog rows. Keep `PARTY_GRACE_HOURS=0`, `ADS_ENABLED=false` and current gifting/achievement/
analytics policy. Do not copy gamma env, fixtures or flags. Normal callbacks use
`REVELRY_INTEGRATION_SECRET`; keep `REVELRY_CALLBACK_SECRET` empty unless deliberately rotated.
Credential rotation is outside this candidate.

Even `--skip-build` unconditionally upserts auth audiences **before preflight**. Export reviewed
existing production values for `GOOGLE_WEB_CLIENT_ID`, `GOOGLE_IOS_CLIENT_ID`,
`GOOGLE_ALLOWED_CLIENT_IDS`, `APPLE_WEB_CLIENT_ID`, `APPLE_NATIVE_CLIENT_ID`,
`APPLE_ALLOWED_CLIENT_IDS`; defaults are not proof of live settings. Compare resulting env diff
and restore the private original if a failed deploy changed it. Do not use `--bootstrap-vm`.

Confirm the commands below still match the verified ownership-corrected image before execution.
The identity is updated to `dfcb266e`; do not deploy the superseded base as the final RC.
Only in the authorized window, from the selected release checkout with those variables exported:

```bash
gcloud compute ssh revelry-backend --project=revelryapp --zone=us-central1-a --command='docker image inspect sha256:e318edd8cd2b812370b665b42ada8afdf4cbfdc600ff510d700501277ae6b275 >/dev/null && docker tag sha256:e318edd8cd2b812370b665b42ada8afdf4cbfdc600ff510d700501277ae6b275 revelry-backend:latest'
CLOUDSDK_CORE_PROJECT=revelryapp ./scripts/deploy-gcp.sh --skip-build --with-frontend
```

`--skip-build` builds neither image nor SPA; `--with-frontend` does not add assets to an existing
image. Pin `CLOUDSDK_CORE_PROJECT` because the script omits `--project`. Production preflight is
port 8070, no volume, snapshots off; it receives production credentials, can contact services
on startup and has no resource caps, so watch the shared VM. The script captures the old image,
swaps containers and tries twenty one-second health probes. Failed start/health automatically
restores the old image on the current env/volume; it does not revert env, SQL, IONOS or Revelry.

Immediately verify image/revision, mount/port/env diff, public health, real DB/RPC, callback and
restore logs. Stop before public frontend publication if a required check fails. No rebuild during
the window; a changed artifact returns to qualification.

## 9. Publish the frozen IONOS artifact

Operator host: `u69414981@home420463025.1and1-data.host`; destination `~/revelryapp/games/`.
Use the frozen IONOS artifact, not a fresh build or unordered `scp dist/*`.

1. Upload new hashed assets first and verify hashes/existence. Keep old assets and entry point;
   do not clear `assets/` or run a deleting sync.
2. Stage reviewed stable config, `.htaccess`, service worker/manifest and static files. Verify
   routing/API bypass/live-config preservation and compatibility with both entry points. Stable
   overwrites are not a multi-file atomic deployment; backups and overlap compatibility matter.
3. Upload `index.html` under a unique temporary filename and publish last using same-filesystem
   `mv`. Verify public entry hash and every referenced asset; save publication/file-hash records.
4. Test canonical root, `/join`, `/spectator`, `/privacy`, `/support` and authenticated host-app
   entry on desktop/mobile, plus backend SPA fallback. No missing chunks, HTML-as-JSON, CORS,
   auth, callback or media failures.
5. Test fresh profile and existing open page/PWA: old chunks still load, APIs bypass service
   worker, refresh/update works between rounds without forced active-player reload. Installed
   native assets do not change here.

## 10. Production acceptance and observation

Use only authorized QA scope, one owned party/room at a time. Do not run broad gamma catalog/
browser/load suites or an unbudgeted LLM call. Plain API regression is read-mostly but writes a
synthetic wallet/referral; record device ID. Its frontend base includes legacy `/quiz/`, so verify
canonical root/routes and shipped hash separately; green regression alone does not prove publication.

```bash
backend/venv/bin/python scripts/regression.py --target prod
```

Prepare interpreter/dependencies before the window. `--deep` spends playthrough sparks and
generates unless disabled; it is not the default acceptance command. Additional room/load/LLM/
financial checks require recorded budgets; `smoke-remote.py` also generates unless `--skip-generate`.

| Area | Acceptance evidence |
|---|---|
| Config/security | Production origins/prefix/policy unchanged; anonymous/admin/party/scope misuse refused; invalid payment/ad inputs rejected |
| Standalone | Desktop/mobile join, meaningful round, answered-state reconnect, podium, replay lobby/start and cancel; debit once per successful start, zero on reset/failed minimum-player gate |
| Persistence/economy | Owned quiz create/read/two edits and stranger refusal; no mixed/partial save; synthetic entitlement/idempotency checks without customer writes |
| Real Revelry | QA party create/edit/media/start; host/player/watch screens, late join/reconnect/cancel; completion mirror; authenticated return and fresh IDs with old results intact |
| Workspace | Fixed production consumer/client pair and config; small/representative large-library timing/identity meets section 4 |
| Auth/payments | Real Google/Apple canonical sign-in; separate authorized test-mode/sandbox and approved production purchase/credit/refund evidence as required. Invalid-input rejection does not prove success; never charge a customer's card as QA |
| Device gaps | Actual native/universal-link return and installed-client compatibility where used; camera and TV/Cast enabled paths manually checked or explicitly excluded |
| Cleanup/logs | All owned rooms/sessions closed; artifacts reconciled by run IDs; no new socket-close, callback, ownership, restoration or payment errors |

Proposed observation: immediate checks for 15 minutes, operator-attended 60-minute bake, then
next-day review before closure. Confirm durations in the decision. Minimum bake cadence is
health every 30s/log review every five minutes, covering LocalPlay, Revelry and the shared VM.

| Signal | Proposed stop/rollback threshold |
|---|---|
| Integrity/privacy/economy | Any confirmed cross-owner access, private exposure, duplicate debit/credit, lost accepted save or completed-result corruption: stop and roll back affected component immediately |
| Availability | Two consecutive failed health probes, restart/OOM or critical restore failure: stop/rollback without waiting for bake |
| Contract | Reproducible callback rejection/missing mirror, old-result mutation or reused managed session ID: rollback responsible service/pair |
| HTTP/resources | New 5xx over 1% for five minutes with at least 100 requests, or three consecutive synthetic critical-flow failures at low volume; CPU over 85% for five minutes/growing memory pressure: pause, investigate and rollback if attributed to candidate |
| Workspace | Any QA timeout or p95 above agreed 80%-deadline target: stop promotion; during bake reproduce/compare baseline and rollback responsible consumer if confirmed |

These are proposed release criteria, not claims that monitoring already enforces them. Record
baseline, denominators and tools before go. Attribute existing unrelated errors; integrity failures
never wait for statistical thresholds. Retain recovery artifacts/old assets through next-day review
and longer if the owners' policy requires.

## 11. Rollback and reconciliation

Deploy operator executes recovery; release owner records abort and coordinates Revelry. Capture
sanitized timing/logs/IDs if doing so does not delay recovery. Stop QA edits/starts and retries of
unknown financial outcomes. Identify whether runtime, frontend, env, RPC or consumer caused failure.

1. Preflight failure leaves old image running but may change audience env; compare/restore it.
   Automatic image rollback is still a failed release; verify env, database and critical flows.
2. Post-health runtime regression: use the captured **current production image**, not gamma's
   rollback or a mutable tag. Gracefully stop, then restart old image with current volume/port/
   restart policy. Restore backed-up env only for unintended window changes, preserving separate
   approved live changes. Example on VM, after verifying captured settings match this topology:

   ```bash
   set -eu
   : "${RC_PREVIOUS_IMAGE:?Set the immutable image ID from the release backup}"
   docker image inspect "$RC_PREVIOUS_IMAGE" >/dev/null
   # If needed, restore the reviewed private prod.env backup first, with mode 600.
   docker stop -t 30 games-backend
   docker rm games-backend
   docker run -d --name games-backend --env-file /home/revelry-games/app/.env \
     -p 127.0.0.1:8000:8000 -v /home/revelry-games/revelry-data:/app/data \
     --restart unless-stopped "$RC_PREVIOUS_IMAGE"
   ```

3. Restore previous IONOS stable files/config and publish old `index.html` last; retain both asset
   sets. A web-only regression does not require restarting a healthy backend. Verify hashes/routes.
4. Leave compatible SQL hardening applied by default. Only a demonstrated RPC regression justifies
   restoring its captured definition/ownership/ACLs through targeted Management API SQL, then
   verification/cache reload. Do not rewind wallets, purchase/webhook idempotency, current rooms
   or the shared DB: accepted writes would be lost. Data recovery needs scoped reconciliation.
5. Revelry owner restores its captured consumer/config and tested recovery pair as needed, then
   verifies workspace IDs, completion callbacks and return flow.
6. Recheck health/auth/DB, seats/answers/scores/reconnect, callback mirror, both web surfaces and
   payment idempotency, including timed-state recovery. If old image cannot read current snapshots,
   preserve files and use the qualified incident path; do not blindly restore pre-window volume.
7. Record failed artifact, cause, actual recovery, pending reconciliation and next decision in
   DEPLOY.md. A repaired/rebuilt candidate returns to qualification; no blind repeated swaps or
   incident-time build. Failed recovery is an incident, not successful promotion.

## 12. Completion record and follow-up

Record exact production source/image, IONOS hash, Revelry backend/client pair, SQL/verification,
preserved config/policy, acceptance/device/payment results or signed exclusions, owned cleanup,
observation, previous recovery artifacts, authorization and next-day review in DEPLOY.md. Update
the ledger in the same commit as deployment/migration/policy records; commit/push sanitized
evidence. Plan existence must not change spec headers to claim production is live.

Native release requires separate build numbers, device/simulator checks, signing, store approval
and binary recovery strategy; backend/IONOS promotion does not update installed assets. Reviewed
Linux visual baselines, longer soak/OS sleep recovery and richer runtime metrics remain separate
follow-ups and cannot substitute for the required functional/integration gates.

## References

- [System baseline](SPEC.md), [deployment ledger](DEPLOY.md), [Revelry contract](SPEC-REVELRY-INTEGRATION.md).
- [Testing/RC evidence](SPEC-TESTING.md), [Supabase contract](SPEC-SUPABASE-MIGRATION.md),
  [room lifecycle](SPEC-ROOM-LIFECYCLE-RELIABILITY.md).
- [Deploy script](scripts/deploy-gcp.sh), [IONOS build guard](frontend/scripts/ionos-build.mjs),
  [API regression](scripts/regression.py), [room snapshots](backend/room_snapshot.py).
