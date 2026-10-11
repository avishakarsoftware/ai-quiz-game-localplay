# Revelry–LocalPlay Contract Repair

Updated: October 10, 2026. Status: implemented and qualified locally; hosted and
native admission remains open. This is not deployment or database-apply authorization.

The audit began with LocalPlay's reconciled working tree on `3a6af36b` and Revelry
`main` on `e6371bce`. Revelry advanced to `a1f78702` through unrelated cover/prepared
UI commits during this work; those changes remain intact and are included in the
final frontend qualification. Both integration repairs remain local working-tree
changes. This document resolves
the caller/callee defects found by the cross-repository audit. The parent contracts
are `SPEC-REVELRY-INTEGRATION.md` and Revelry's `SPEC-LOCALPLAY-INTEGRATION.md`;
atomic admission remains governed by `SPEC-LOCALPLAY-CALLBACK-RECOVERY.md`.

## Permissions and party lifecycle

- Revelry derives outgoing LocalPlay capabilities from verified effective
  `games_manage` permission. Stored `helper` alone grants no game operations.
  A delegated Game Host receives author/manage/operate/moderate game capabilities,
  while ordinary members retain player/watch access. Apply this mapping to member
  hub requests as well as explicit start/authoring requests. Host/cohost fallback
  is allowed only for legacy internal callers that omit the verified permission.
- Check-in configuration, explicit start, and automatic open/create enforce the
  existing writable-party guard before mutation or provider calls. Ended and
  archived parties retain permitted reads/history, not new game starts.
- Verify real outbound capabilities against LocalPlay's actual authorization,
  including helper denial and delegated authoring success. Tests must call the
  check-in entry points, not merely the guard helper.

## Content ownership and authoring returns

- Every service content GET/DELETE includes the known party's
  `external_container_id` and `external_container_type=party`. Thread that party
  through authoring returns, prepared pointers, callback enrichment, legacy
  reconciliation, and cleanup. LocalPlay's owner-scoped validation stays intact.
- Structured postMessage content remains authoritative. Merge missing draft/setup
  correlation from its trusted return URL only when content identity agrees;
  never replace explicit correlation with another same-party tab's storage.
  Conflicting identities fail safely. Verify two simultaneous same-game drafts.

## Launch exchange and runtime recovery

- A launch JWT is a short-lived exchange credential. Once the bound runtime
  credential is persisted (organizer exchange or player join), remove it from the
  visible URL and retain the durable session identity.
- Persist runtime recovery context with exact session ID, room, party identity,
  host-app mode, and return/hub URLs. Restore only when those bindings match the
  requested session/party; never resume an unrelated saved room or reveal its
  organizer credential. Runtime socket authentication and closed-room responses
  remain authoritative. Expired links cannot extend cancelled/superseded rooms.
- Players preserve their own nickname/seat credential. Organizers reuse their
  own organizer credential. Expired-link errors retain a valid bound return path.
- LocalPlay resolve returns safe host/container fields from the durable session,
  including service-minted launches. No participant identity or extra authority
  is inferred from ignored request-body actor fields.
- Every embedded Revelry surface offers Open full screen. Reentry obtains fresh
  credentials through the corresponding authorized hub/authoring/session API;
  it must not replay an expired URL or repeat a destructive start intent.
- Installed-native/browser launch and return still need separate device evidence.

## Durable ordering shared by callbacks and polling

- Keep existing integer-second storage fields and TTL behavior unchanged. Add a
  nullable `integration_updated_at_us` ordering clock to LocalPlay-owned session,
  quiz-pack, and generated-content rows. Database insert/update triggers assign
  `max(database wall time in microseconds, previous clock + 1)` atomically and
  ignore or reject caller clock overrides. SQLite triggers use built-in SQL functions so
  existing binaries can continue writing after migration.
- A small environment-scoped content deletion tombstone stores only resource
  type, opaque ID, and deletion clock for physically removed content. It cannot
  hold owner identity, content, credentials, media bytes, or financial data.
- Return the clock together with the exact committed resource payload. Callback
  `occurred_at`, session polling `updated_at`, and prepared metadata `updated_at`
  use that same clock. Delivery time is not a resource revision. Two same-second
  edits remain ordered; a later cancelled/expired/superseded snapshot can recover
  a missed callback. Legacy rows without a clock retain explicit compatibility.
- Prepare separate targeted prod/gamma migrations and update generated bootstrap
  templates. Do not backfill historical rows or apply full bootstrap SQL remotely.
  Trigger scope, privileges, existing-code compatibility, owner isolation, delete
  ordering, and transaction rollback require disposable-database verification.
- Revelry atomic flags stay disabled. New schema alone does not qualify provider
  retry, inbox replay, actual PostgREST deadlines, gamma, or compatible rollback.

## Bounded workspace reconciliation

- Load existing prepared pointers once through stable party-scoped pagination;
  map current/previous content IDs and preserve setup IDs, ownership, used/locked
  state, authoring correlation, and deletion/version lineage.
- An unchanged library performs no mirror writes and no per-item database reads.
  Changed/new items use bounded writes, preserving concurrency guards and truthful
  errors. Enabled atomic mode retains party/row CAS and SQL tombstone arbitration;
  never bypass its writers with direct inserts or updates.
- Do not cache across requests or treat a stale provider snapshot as permission
  to overwrite a callback/host edit. Test pagination, unchanged large libraries,
  version transitions, deletion, insertion races, and concurrent updates.
- Earlier published maintenance patches are separate candidates. This integrated
  source must receive its own tests and representative-library gamma timing.

## Documentation and qualification

- Managed continuation creates a fresh durable session; managed `RESET_ROOM`
  rejects before mutation. Correct Revelry's old same-room spec and live harness.
- Guest seat identity binding and token refresh remain explicit future work;
  actor-body extras must not be described as binding current LocalPlay membership.
- Preserve dated deployment evidence and label new source/migrations as unapplied.
  Record local backend, frontend, contract, SQL, browser, and build results after
  implementation. No hosted/shared database or provider is a test fixture.
- Promotion requires current CI, paired exact-source gamma gameplay/authoring,
  library latency, callbacks/poll recovery, cached/native clients, coordinated
  schema/code admission, and state-preserving rollback under both release plans.

## Candidate admission and rollback order

1. Record the paired immutable source/artifact IDs, current deployed flags and
   the recovery artifacts. Review the clock migration for exactly one environment
   with its LocalPlay owner before any apply. Shared identity or other-app tables
   are outside its write scope. Historical migrations remain unchanged.
2. Apply only the approved targeted gamma migration, then verify columns,
   triggers, service-only RPC privileges, NULL historical clocks and isolation.
   Reset the new tombstone table's inherited service-role privileges before
   granting only SELECT, INSERT and UPDATE. The October 10 hosted catalog shows
   broader defaults; those shared defaults stay unchanged.
   New provider code requires the snapshot-returning `save_quiz_pack` and
   `delete_integration_content` RPCs; missing schema fails closed. Do not deploy
   it against the old RPC shape or apply full bootstrap SQL as an upgrade.
3. Deploy the paired gamma code with Revelry atomic flags still off. Complete
   authoring, permission, lifecycle, reload/fullscreen, large-library timing and
   callback/poll acceptance on that exact pair. Separately qualify actual
   PostgREST execution deadlines, immutable provider retry and receipt/replay
   before admitting Revelry's default-off atomic path.
4. Rehearse recovery with these additive columns/triggers/RPCs retained. Older
   payload writers remain schema-compatible, but an old producer's send-time
   callbacks and polls without the durable clock are **not** a qualified recovery
   pair for an enabled atomic consumer. Retain a clock-aware producer and an
   independently qualified guarded consumer recovery artifact. Use the existing
   release fence when reverting guarded writers; no blind flag disable, dropping
   clocks/lineage/receipts, or restoring a historical database snapshot.
5. Production requires its own explicit single-migration approval, owned-object
   verification, paired exact-artifact promotion, smoke and rollback record.
   Source qualification does not authorize any of these hosted mutations.

## Implementation evidence

All checks below passed on October 10. Overlapping suite counts are not additive.

| Check | Result / evidence boundary |
| --- | --- |
| LocalPlay broad backend | **1,765 passed, 120 skipped**, fresh temporary SQLite; local async/WebSocket listeners enabled. Opt-in SQL cases execute separately below. |
| Revelry focused backend | **225 passed**, eight modules including 34 workspace cases; fresh source copy, no repository `.env`/live conftest, dummy loopback Supabase and blocked socket connections. |
| Actual caller/callee contract | Ordinary helper start **403**; delegated Game Host authoring **200**; party-scoped metadata succeeds; ended/archived check-in starts **409**. Current Revelry methods call the actual LocalPlay app with temporary SQLite. |
| Real PostgreSQL/PostgREST | **142 passed**: 26 producer/consumer clock and upgrade cases, 110 raw/REST persistence cases, 6 account-deletion SQL cases. Both prefixes, actual pending Revelry transaction SQL, no backfill, legacy writes, grants, failure rollback, concurrent saves/delete/recreate and exact snapshots. Owned loopback containers removed afterward. |
| Frontend unit suites | LocalPlay **548 tests / 80 files**; Revelry **2,357 tests / 150 files**, bounded workers. Fixed an existing Revelry mock Response to provide real clone/body behavior. |
| Builds | Both production builds and TypeScript passed. Existing LocalPlay chunk/import warnings remain. |
| Local browser gameplay | **78 passed, 1 existing real-camera waiver skipped**, all-games plus podium on a disposable SQLite/snapshot stack; cleanup completed. |
| Gamma continuation harness | Updated managed reset rejection/fresh-session assertions; discovery passes. No hosted run is claimed. |
| Source hygiene | Both `git diff --check` pass; rendered schemas match template and migration bodies through automated checks. |

Workspace cases prove one prepared-row SELECT and zero writes for 86 unchanged
items in both modes; pagination over 425 rows; bounded 50-row compatibility inserts
and 24-operation atomic commits; observations restricted to changed rows; guarded
concurrent title/pointer/deletion failures; owned insertion-race adoption; preserved
locks, used times, pending/cleanup markers; monotonic cursors; old-first/new-first
versions and out-of-order duplicate items. The response always returns the final
accepted version while retaining first display position. Independent review found
and verified the correction of the compatibility response snapshot edge case.

LocalPlay's final broad log is
`/private/tmp/localplay-revelry-repair-final-20261010/backend-current.log`.
Revelry qualified-source hashes, command summary and actual contract results are
in `/private/tmp/revelry-bridge-qualified-we2ixb4e/`. Frontend/browser commands and
tool references are transcribed in
`/private/tmp/bridge-browser-contract-validation.7SbHQj/validation.md`.
These temporary logs supplement this saved ledger; they are not deployment receipts.

Current CI, actual hosted provider retries/deadlines and receipt replay, paired
gamma gameplay/authoring/library latency, installed-native/cached clients, approved
prefix-specific schema apply and compatible recovery artifacts remain open gates.
No hosted/shared database, IONOS service or deployed environment was modified.
