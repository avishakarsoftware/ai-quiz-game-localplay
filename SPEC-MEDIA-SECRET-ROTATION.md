# SPEC — Media Upload Secret Rotation (LocalPlay)

Status: **Runbook (not yet executed).** Safe path for rotating LocalPlay's shared media **upload signing secret**
(`MEDIA_UPLOAD_SECRET`) across the prod backend, gamma backend, and the IONOS validator. Adapted from
revelryapp's battle-tested `MEDIA-SECRET-ROTATION-PLAN.md`, changed for LocalPlay's infra (GCP **VM Docker +
`.env` files**, not Cloud Run + Secret Manager).

Run only in an agreed low-traffic window with explicit operator approval for every secret step and every
live IONOS write. **This document describes the operation; it is not itself permission to execute it.**

Related: `SPEC-IMAGE-GAMES.md` (media layer), `DEPLOY.md` (media handler deploy), repo handler source
`ionos/media/upload.php`, `ionos/media/upload-secret.example.php`, `ionos/media/uploads.htaccess`.

---

## October 10, 2026 — Source-verified runbook corrections

This review read source only: no secret, live handler, deployed container, media URL or remote database was
inspected, and no rotation occurred. The original status records the planned operation; consult
`DEPLOY.md` for separately authorized outcomes before using it.

Current source: `backend/main.py` signs `path\nexpires\nmime_type\nbytes`; `backend/config.py`
and `ionos/media/upload.php` strip the configured string. Upload signing is `POST /media/upload-url`,
then multipart POST to its returned IONOS target, then `POST /media/{asset_id}/finalize` with the
same owner/authoring credential. MIME/byte validation is 2 MiB PNG/JPEG/WebP; the PHP handler
also sniffs the uploaded type. `/media/status` reports capability, not secret agreement.

Photo Clue also uses `MEDIA_UPLOAD_SECRET` for its backend-only HS256 attachment capability
(`backend/photo_clue_media.py`). Authenticated `purpose=photo_clue_submission` requests receive
an owner/asset-bound `attachment_token`, valid for `MEDIA_UPLOAD_TOKEN_TTL_SECONDS` (default
900 seconds). Rotating the backend value immediately invalidates outstanding capabilities
signed with the old value, even when their upload and finalize already succeeded. A fresh
upload request and submission recover the flow; the current API does not reissue a capability
for an existing asset. IONOS does not validate this capability.

Current deployment source recreates containers with `--env-file` and the volume mounted at
`/app/data`, capturing an immutable previous image and attempting rollback on health failure.
Supabase holds the deployed ledger; the local volume still holds room snapshots and legacy SQLite.
Use `--skip-build` after verifying the selected existing image equals the approved running runtime,
so a secret rotation does not silently deploy unrelated source changes. The script's health rollback
uses the newly edited env file, so image rollback alone does not restore an old secret.

The handler currently accepts a single secret string and legacy dotfile fallback. Dual-secret grace,
physical signed deletion and scheduled orphan cleanup are future work. Account deletion removes
owned media metadata but cannot revoke a public CDN URL or delete IONOS bytes today.

## Key Guarantee

**Existing uploaded media reads do NOT break during rotation.** The secret signs new uploads
(`_sign_media_upload` → `hmac_sha256(payload, MEDIA_UPLOAD_SECRET)`; IONOS `upload.php`
recomputes the same HMAC and `403`s on mismatch) and Photo Clue attachment capabilities.
Existing media are plain static `GET`s from
`media.revelryapp.me/apps/localplay/…` and never touch the secret. We still verify reads before/after because
media is user-visible.

## Revelry integration impact — none to the integration itself

`MEDIA_UPLOAD_SECRET` and the Revelry integration secrets (`REVELRY_INTEGRATION_SECRET` /
`REVELRY_CALLBACK_SECRET`) are **separate secrets with no cross-use**. Rotating the media
secret does **not** touch party-games links, launch tokens, resolve, lifecycle callbacks, or mirror-results —
launching and playing Revelry-embedded games keeps working throughout the rotation.

The overlap is media uploads and Photo Clue attachment: if a Revelry-launched authoring surface uploads media (custom-quiz images), it uses the same `MEDIA_UPLOAD_SECRET` path, so during the Option-A cutover blip a *new* upload from
**any** surface — web, native, or Revelry-embedded — may briefly `403` until both containers + IONOS converge
(retry / fresh signed URL recovers it). Existing media (including images already attached to Revelry games)
read fine throughout. Photo Clue capabilities minted before a backend restart also need a fresh
upload and submission after rotation. Measure the acceptable upload and attachment interruption
budget before selecting the window.

## Why it must be coordinated (3 places, one value)

`media.revelryapp.me/apps/localplay/` is a **single IONOS host** whose one validator
(`~/revelryapp/media/apps/localplay/upload-secret.php`, `trim()`ed) checks **both** prod (`prod/…`) and gamma
(`gamma/…`) uploads. Both backends sign with their own env value:

| Environment | Container (GCP VM `revelry-backend`, zone us-central1-a) | Secret source |
|---|---|---|
| Prod | `games-backend` (:8000) | `MEDIA_UPLOAD_SECRET` in `/home/revelry-games/app/.env` |
| Gamma | `games-backend-gamma` (:8004) | `MEDIA_UPLOAD_SECRET` in `/home/revelry-games/app/.env.gamma` |

An upload succeeds only when **backend signing secret == IONOS validating secret**. So all **three** must be
rotated together (prod `.env`, gamma `.env.gamma`, IONOS `upload-secret.php`), and **both containers must be
restarted** to re-read their env. Rotating only one breaks uploads for at least one environment.

## LocalPlay-specific differences from the revelry runbook (read first)

1. **No Secret Manager → no version history.** With Cloud Run, revelry could roll back to an old secret
   *version*. Here the secret is a plain string in `.env`/`.env.gamma`. **Rollback is only possible if you
   captured the OLD value first.** Phase 0 backs it up to the private store (`backupenv/quiz/local/`); do not
   skip it.
2. **Both sides already `trim()`/`.strip()`** (`config.py` strips; `upload.php read_upload_secret()` trims)
   → LocalPlay is **immune to revelry's trailing-newline `403` bug**. Still generate a clean 64-hex value.
3. **Container restart, not Cloud Run roll.** `docker restart` does **not** re-read `--env-file`; you must
   `docker rm` + `docker run --env-file …`. **The run MUST include the DB volume mount**
   `-v /home/revelry-games/revelry-data:/app/data` or room snapshots and deliberate SQLite recovery lose their durable volume. Use
   `./scripts/deploy-gcp.sh` (it backs up the DB and rm+runs with the correct mount) rather than a hand-rolled
   `docker run`.
4. **Uploads and attachment proofs.** `delete.php` is future/not deployed, so there is no signed-delete
   path to rotate (unlike revelry). Phase 4 also covers the backend Photo Clue proof. If delete ships
   later, extend verification to cover it.
5. **Shared host, separate app subtree.** `apps/localplay/` is independent of revelry's `apps/revelry/` —
   rotating LocalPlay's secret does not touch revelry/VibePix.

## Hard Rules

- Never print, paste, echo, screenshot, commit, or chat the secret value. Compare by **hash only**.
- Generate the new value **outside the repo** with `umask 077`.
- **Back up the OLD value before mutating** (no Secret Manager fallback here) and keep the new value in
  `backupenv/quiz/local/` (chmod 600), like the keystore creds.
- Never `git add` a secret; the repo only holds `upload-secret.example.php` (placeholder).
- Restart containers via the deploy script so the **DB volume mount** is preserved.
- Stop if any hash comparison, live-handler check, or verification probe is ambiguous.

## Operator Decision

| Option | When | Behavior |
|---|---|---|
| **A. Quick coordinated cutover** (default) | brief upload/attachment interruption acceptable | No handler change. New uploads may `403` until both containers + IONOS converge. In-flight signed URLs and Photo Clue proofs (TTL `MEDIA_UPLOAD_TOKEN_TTL_SECONDS`, default 900s) require a fresh upload request and submission after backend rotation. **Existing reads stay up.** |
| B. Dual-secret grace window | near-zero interruption required | Proposed PHP acceptance of `[old,new]` protects upload HMACs. Preserving Photo Clue proofs also requires backend verification against old/new keys for the bounded TTL window; neither dual-key path exists today. Qualify both changes before selecting this option. |
| C. Defer | explicit risk acceptance | Leaves any forged-upload risk open; record the reason. |

Operational default: **Option A** only after the owner accepts the observed upload interruption budget. This source review did not measure current traffic or establish an exposure incident.

---

## Phase 0 — Read-only preflight (no mutations)

All `backupenv/quiz/local/` paths below name the access-controlled private operator store,
resolved outside every source checkout; they are not repository directories. Keep generated
validator files owner-only and use unique temporary names.

1. Repo clean: `git status --short && git rev-parse HEAD`.
2. Source media tests green (find the media test files; e.g. `pytest tests/ -k "media or ionos" -q`).
3. Verify live IONOS `upload.php` matches repo source by hash; confirm `.htaccess` hardening present.
4. **Secret-exposure probe** — never stream a response body to the terminal/chat.
   An authorized operator should fetch each of `upload-secret.php` and `.upload_secret` into an
   owner-only temporary file, inspect status/byte count privately, and report only a verdict.
   Accept `403`/`404`, or a successful empty PHP response. Stop on any unexpected successful
   nonempty body; do not print it or attach it as evidence. Capture errors without echoing bytes.
5. **Hash-agreement check** (prod == gamma == IONOS), values never printed:
   use an authorized private routine to read the two running container values and the PHP-returned
   validator value, strip whitespace consistently, reject empty values, and hash each with SHA-256.
   Require every remote read to exit successfully before comparing three nonempty digest results;
   a failed command or an empty value must never hash into an apparent agreement. Print only
   `AGREE` / `DIVERGE`, keeping values and digests in the access-controlled operator worksheet.
   Do not substitute a public HTTP download for the IONOS private read.
6. **Capture rollback anchors (CRITICAL — no version history):**
   - the **OLD secret value** → write to `backupenv/quiz/local/media-secret.OLD` (chmod 600), never printed;
   - one existing prod media URL + one gamma media URL for read probes;
   - current immutable image ID/OCI revision for each container; a mutable `latest` tag is not a rollback anchor.
7. Confirm existing reads: `curl -sS -i "$KNOWN_PROD_MEDIA_URL"` and gamma → expect `200` + media content-type.

## Phase 1 — Prepare the new secret (outside repo)

```bash
umask 077
NEWFILE="$(mktemp /tmp/lp-media-secret.XXXXXX)"
openssl rand -hex 32 | tr -d '\n' > "$NEWFILE"      # clean 64 hex chars, no newline
test "$(wc -c < "$NEWFILE")" -eq 64
```
Store a copy at `backupenv/quiz/local/media-secret.NEW` (chmod 600). Never print `$NEWFILE`.
(LocalPlay strips on both ends so a stray newline wouldn't break it — but keep it clean anyway.)

## Phase 2 — Stage the value on the VM `.env` files (no effect until restart)

Editing `.env`/`.env.gamma` does **not** change the running containers until they're restarted, so this is safe
to do first. Upsert `MEDIA_UPLOAD_SECRET` in both, over SSH, without printing the value (pipe `$NEWFILE`):

```bash
# for each of: /home/revelry-games/app/.env  and  /home/revelry-games/app/.env.gamma
#   grep -q '^MEDIA_UPLOAD_SECRET=' && sed -i 's#^MEDIA_UPLOAD_SECRET=.*#MEDIA_UPLOAD_SECRET=<new>#' || echo append
```
Do NOT restart yet. Do NOT remove the old value from your backup.

## Phase 3A — Option A cutover (restart both + update IONOS)

1. **Restart both containers so they re-read the new env** — via the deploy script (preserves the DB volume
   mount + backs up SQLite first). Confirm the running secret hash changed to the new value afterward:
   ```bash
   ./scripts/deploy-gcp.sh --gamma --skip-build # verified approved gamma image, rereads .env.gamma
   ./scripts/deploy-gcp.sh --skip-build         # verified approved prod image, rereads .env
   ```
   (`--skip-build` exists in current source; verify the selected existing image and confirm it still does
   `docker rm`+`run --env-file` with the volume mount before relying on it.)
2. **Build the IONOS validator from `$NEWFILE`** without printing it, then deploy:
   ```bash
   umask 077
   VALIDATOR_FILE="$(mktemp /tmp/lp-upload-validator.XXXXXX)"
   python3 - "$NEWFILE" "$VALIDATOR_FILE" <<'PY'
   import json, pathlib, sys
   s = pathlib.Path(sys.argv[1]).read_text().strip()
   pathlib.Path(sys.argv[2]).write_text("<?php\nreturn " + json.dumps(s) + ";\n")
   PY
   scp "$VALIDATOR_FILE" u69414981@home420463025.1and1-data.host:~/revelryapp/media/apps/localplay/upload-secret.php
   rm -f "$VALIDATOR_FILE"
   ```
3. Continue immediately to Phase 4.

## Phase 3B — Option B dual-secret grace (only with approved `ionos/` change)
Update `ionos/media/upload.php` `read_upload_secret()` to accept a string **or** array from `upload-secret.php`
and pass if the request HMAC matches **any** entry; add source tests (old-only, old+new, new-only-rejects-old);
deploy dual `[old,new]` → restart both backends onto new → deploy new-only → Phase 4 (incl. old-signature reject).
For uninterrupted Photo Clue submissions, also implement and test bounded old/new backend proof
verification before the rollout. PHP dual acceptance alone does not preserve those capabilities.

## Phase 4 — Verification (all must pass; else roll back)

1. **Prod new upload works** — sign through `POST /media/upload-url` with an owned synthetic wallet or authorized authoring token, upload a tiny PNG to the returned target, finalize through `POST /media/{asset_id}/finalize`, then read its CDN URL (`200`). Record the owned asset ID/path; physical cleanup is not currently automated.
2. **Gamma new upload works** — same against gamma (`test:e2e:gamma:revelry` custom-quiz image path exercises
   this end-to-end).
3. **Existing reads still `200`** — `curl -i "$KNOWN_PROD_MEDIA_URL"` and gamma.
4. **Old signature now fails** — sign an upload with the OLD value (from `backupenv/quiz/local/media-secret.OLD`,
   in a shell var, never printed) → expect `403 bad_signature`.
5. **Hardening probes still reject** — `.php`/`.phtml`/`.svg`/`.html`/`.js`, extension↔MIME mismatch, traversal,
   dotfile, oversized (per `ionos/media/uploads.htaccess`).
6. **Post-rotation hash agreement** — prod == gamma == IONOS (Phase 0 private routine; record hashes privately, not in chat).
7. **Photo Clue attachment works** — in an owned synthetic room in each environment, upload/finalize
   with `purpose=photo_clue_submission`, submit the returned fresh proof as the active clue-giver,
   and assert the canonical photo appears. Assert an old-key proof is rejected after the cutover
   (or after the approved bounded grace window), while the existing CDN URL still reads. End and
   clean up only the owned room; record asset IDs because physical media deletion remains unavailable.

## Rollback (prepare before Phase 3)

Triggers: prod or gamma upload fails after cutover; existing reads fail; hashes disagree; old signatures still
pass after cutover; hardening probe unexpectedly succeeds; secret-exposure probe leaks.

Steps (rollback = restore the OLD value everywhere — this is why Phase 0 backup is mandatory):
1. Restore IONOS validator from `backupenv/quiz/local/media-secret.OLD` (rebuild `upload-secret.php`, scp it back).
2. Restore `MEDIA_UPLOAD_SECRET=<old>` in `/home/revelry-games/app/.env` and `.env.gamma`.
3. Restart both containers via the deploy script (volume mount preserved).
4. Re-verify: prod upload, gamma upload, fresh Photo Clue attachment, existing read, hash agreement
   (all on the old value). Proofs minted with the new value are invalid after rollback; clients
   need a fresh upload request and submission.

Existing media reads do not depend on the signing secret. A read failure still requires independent routing/handler diagnosis before accepting the cutover.

## Cleanup (after a stable observation window)

1. Remove only the private temporary files created by this operation (`"$NEWFILE"`, `"$VALIDATOR_FILE"`).
2. Once stable, you may delete `backupenv/quiz/local/media-secret.OLD` — but keep it through the observation
   window (it is the only rollback path; there's no Secret Manager version to fall back to).
3. Update docs: `DEPLOY.md` (rotation date + verification summary), this file (status/outcome),
   `backupenv/quiz/local/iap-setup.md` or a media note (record hashes/date, **not** values).

## Operator Worksheet

| Item | Value |
|---|---|
| Operator / window | |
| Decision A / B / C | |
| Preflight source tests passed | |
| Secret-exposure probe passed | |
| OLD value backed up (backupenv) | |
| Prod/gamma/IONOS pre-rotation hashes agree | |
| New value generated (64 hex characters / 32 random bytes, no newline) | |
| Prod `.env` updated / gamma `.env.gamma` updated | |
| Prod container restarted / gamma container restarted | |
| IONOS validator updated | |
| Prod new upload / gamma new upload verified | |
| Existing prod read / gamma read still 200 | |
| Old signature rejected (403) | |
| Fresh Photo Clue proof accepted / old-key proof rejected in prod and gamma | |
| Hardening probes passed | |
| Post-rotation hashes agree | |
| Rollback needed? | |
| OLD backup deleted date | |
