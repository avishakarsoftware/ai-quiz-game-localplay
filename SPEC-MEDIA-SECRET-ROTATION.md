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

## Key Guarantee

**Existing uploaded media does NOT break during rotation.** The secret is used *only* to mint and validate
**new** signed uploads (`_sign_media_upload` → `hmac_sha256(payload, MEDIA_UPLOAD_SECRET)`; IONOS `upload.php`
recomputes the same HMAC and `403`s on mismatch). Existing media are plain static `GET`s from
`media.revelryapp.me/apps/localplay/…` and never touch the secret. We still verify reads before/after because
media is user-visible.

## Revelry integration impact — none to the integration itself

`MEDIA_UPLOAD_SECRET` and the Revelry integration secrets (`REVELRY_INTEGRATION_SECRET` /
`REVELRY_CALLBACK_SECRET`, config.py:220/227) are **separate secrets with no cross-use**. Rotating the media
secret does **not** touch party-games links, launch tokens, resolve, lifecycle callbacks, or mirror-results —
launching and playing Revelry-embedded games keeps working throughout the rotation.

The **only** overlap is new media *uploads*: if a Revelry-launched game uploads media (custom-quiz images,
drawing), it uses the same `MEDIA_UPLOAD_SECRET` path, so during the Option-A cutover blip a *new* upload from
**any** surface — web, native, or Revelry-embedded — may briefly `403` until both containers + IONOS converge
(retry / fresh signed URL recovers it). Existing media (including images already attached to Revelry games)
read fine throughout. A low-traffic window makes this negligible.

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
2. **Both sides already `trim()`/`.strip()`** (`config.py:75` strips; `upload.php read_upload_secret()` trims)
   → LocalPlay is **immune to revelry's trailing-newline `403` bug**. Still generate a clean 64-hex value.
3. **Container restart, not Cloud Run roll.** `docker restart` does **not** re-read `--env-file`; you must
   `docker rm` + `docker run --env-file …`. **The run MUST include the DB volume mount**
   `-v /home/revelry-data…:/app/backend/data` or SQLite is wiped ([deploy_volume_mount] landmine). Use
   `./scripts/deploy-gcp.sh` (it backs up the DB and rm+runs with the correct mount) rather than a hand-rolled
   `docker run`.
4. **Upload-only.** `delete.php` is future/not deployed, so there is no signed-delete path to rotate (unlike
   revelry). If delete ships later, extend Phase 4 to cover it.
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
| **A. Quick coordinated cutover** (default) | brief upload blip acceptable | No handler change. New uploads may `403` for the seconds/minutes it takes both containers + IONOS to converge; in-flight signed URLs (TTL `MEDIA_UPLOAD_TOKEN_TTL_SECONDS`, 900s) may fail until the client requests a fresh one. **Existing reads stay up.** |
| B. Dual-secret grace window | near-zero upload interruption required | Change `upload.php` to accept `upload-secret.php` returning `old` **or** an array `[old,new]`; deploy dual → roll backends → deploy new-only. More work; needs approved `ionos/` handler change + source tests. |
| C. Defer | explicit risk acceptance | Leaves any forged-upload risk open; record the reason. |

Recommended default: **Option A** in a low-traffic window. LocalPlay media traffic is low, so the blip is minor.

---

## Phase 0 — Read-only preflight (no mutations)

1. Repo clean: `git status --short && git rev-parse HEAD`.
2. Source media tests green (find the media test files; e.g. `pytest tests/ -k "media or ionos" -q`).
3. Verify live IONOS `upload.php` matches repo source by hash; confirm `.htaccess` hardening present.
4. **Secret-exposure probe** — must NOT leak bytes:
   ```bash
   curl -sS -i https://media.revelryapp.me/apps/localplay/upload-secret.php
   curl -sS -i https://media.revelryapp.me/apps/localplay/.upload_secret
   ```
   Accept only `403`/`404`/empty. If secret-like bytes appear, stop.
5. **Hash-agreement check** (prod == gamma == IONOS), values never printed:
   ```bash
   PROD=$(gcloud compute ssh revelry-backend --zone us-central1-a --command \
     "docker exec games-backend printenv MEDIA_UPLOAD_SECRET" 2>/dev/null | tr -d '\n' | shasum -a256 | cut -d' ' -f1)
   GAMMA=$(gcloud compute ssh revelry-backend --zone us-central1-a --command \
     "docker exec games-backend-gamma printenv MEDIA_UPLOAD_SECRET" 2>/dev/null | tr -d '\n' | shasum -a256 | cut -d' ' -f1)
   IONOS=$(ssh u69414981@home420463025.1and1-data.host \
     "php -r 'echo hash(\"sha256\", trim(require \"\$HOME/revelryapp/media/apps/localplay/upload-secret.php\"));'")
   test "$PROD" = "$GAMMA" && test "$PROD" = "$IONOS" && echo AGREE || echo DIVERGE
   ```
   If DIVERGE, reconcile before rotating.
6. **Capture rollback anchors (CRITICAL — no version history):**
   - the **OLD secret value** → write to `backupenv/quiz/local/media-secret.OLD` (chmod 600), never printed;
   - one existing prod media URL + one gamma media URL for read probes;
   - current container image tag (`revelry-backend:latest`).
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
   ./scripts/deploy-gcp.sh --gamma            # gamma: games-backend-gamma picks up .env.gamma
   ./scripts/deploy-gcp.sh                     # prod:  games-backend picks up .env
   ```
   (If a `--skip-build` fast path is available it may be used to avoid an image rebuild — verify it still does
   `docker rm`+`run --env-file` with the volume mount before relying on it.)
2. **Build the IONOS validator from `$NEWFILE`** without printing it, then deploy:
   ```bash
   python3 - "$NEWFILE" /tmp/upload-secret.php <<'PY'
   import json, pathlib, sys
   s = pathlib.Path(sys.argv[1]).read_text().strip()
   pathlib.Path(sys.argv[2]).write_text("<?php\nreturn " + json.dumps(s) + ";\n")
   PY
   scp /tmp/upload-secret.php u69414981@home420463025.1and1-data.host:~/revelryapp/media/apps/localplay/upload-secret.php
   rm -P /tmp/upload-secret.php
   ```
3. Continue immediately to Phase 4.

## Phase 3B — Option B dual-secret grace (only with approved `ionos/` change)
Update `ionos/media/upload.php` `read_upload_secret()` to accept a string **or** array from `upload-secret.php`
and pass if the request HMAC matches **any** entry; add source tests (old-only, old+new, new-only-rejects-old);
deploy dual `[old,new]` → restart both backends onto new → deploy new-only → Phase 4 (incl. old-signature reject).

## Phase 4 — Verification (all must pass; else roll back)

1. **Prod new upload works** — call `/media/upload-url` (or the real endpoint) against prod, upload a tiny PNG,
   read the CDN URL (`200`).
2. **Gamma new upload works** — same against gamma (`test:e2e:gamma:revelry` custom-quiz image path exercises
   this end-to-end).
3. **Existing reads still `200`** — `curl -i "$KNOWN_PROD_MEDIA_URL"` and gamma.
4. **Old signature now fails** — sign an upload with the OLD value (from `backupenv/quiz/local/media-secret.OLD`,
   in a shell var, never printed) → expect `403 bad_signature`.
5. **Hardening probes still reject** — `.php`/`.phtml`/`.svg`/`.html`/`.js`, extension↔MIME mismatch, traversal,
   dotfile, oversized (per `ionos/media/uploads.htaccess`).
6. **Post-rotation hash agreement** — prod == gamma == IONOS (Phase 0 command; record hashes privately, not in chat).

## Rollback (prepare before Phase 3)

Triggers: prod or gamma upload fails after cutover; existing reads fail; hashes disagree; old signatures still
pass after cutover; hardening probe unexpectedly succeeds; secret-exposure probe leaks.

Steps (rollback = restore the OLD value everywhere — this is why Phase 0 backup is mandatory):
1. Restore IONOS validator from `backupenv/quiz/local/media-secret.OLD` (rebuild `upload-secret.php`, scp it back).
2. Restore `MEDIA_UPLOAD_SECRET=<old>` in `/home/revelry-games/app/.env` and `.env.gamma`.
3. Restart both containers via the deploy script (volume mount preserved).
4. Re-verify: prod upload, gamma upload, existing read, hash agreement (all on the old value).

Existing media **reads** never require rollback (static GETs).

## Cleanup (after a stable observation window)

1. `rm -P "$NEWFILE"` and any `/tmp/upload-secret.php`.
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
| New value generated (64 bytes, no newline) | |
| Prod `.env` updated / gamma `.env.gamma` updated | |
| Prod container restarted / gamma container restarted | |
| IONOS validator updated | |
| Prod new upload / gamma new upload verified | |
| Existing prod read / gamma read still 200 | |
| Old signature rejected (403) | |
| Hardening probes passed | |
| Post-rotation hashes agree | |
| Rollback needed? | |
| OLD backup deleted date | |
