# Revelry Games / LocalPlay — Production Deployment Guide

## Architecture Overview

```
Users → games.revelryapp.me (IONOS CDN) → static frontend
     → gamesapi.revelryapp.me (GCP VM)  → FastAPI backend + WebSockets + optional frontend
     → gamesapi-gamma.revelryapp.me (GCP VM) → FastAPI backend + WebSockets + frontend
```

- **Frontend**: Static React/Vite build hosted on IONOS shared hosting
- **Backend**: FastAPI in Docker on a GCP Compute Engine e2-micro VM
- **Current persistence**: Production and gamma use the shared Supabase project (`games_*` / `games_gamma_*`); SQLite files remain on the VM only as local-dev defaults and rollback backups
- **Backend-served SPA**: The FastAPI container can serve the built Vite frontend from `/app/static`
- **Reverse proxy**: Nginx on the VM handles HTTPS termination + WebSocket upgrade
- **SSL**: Let's Encrypt via Certbot (auto-renewing)

The public production game is expected to run at `https://games.revelryapp.me/` from IONOS. The backend-served SPA gives us a same-origin deployment path for gamma, previews, and emergency/prod fallback at the API domains.

## Production URLs

| Component | URL |
|-----------|-----|
| Frontend  | https://games.revelryapp.me/ |
| Backend API + SPA fallback | https://gamesapi.revelryapp.me |
| Gamma full stack | https://gamesapi-gamma.revelryapp.me |
| Spectator/TV | https://games.revelryapp.me/spectator |
| Player join  | https://games.revelryapp.me/join |
| Cast App ID  | `1BC9ACD8` |

## Current VM State

As of the SPA rollout, the VM has both LocalPlay containers deployed:

| Environment | Domain | Container | Image | VM bind | Data dir |
|-------------|--------|-----------|-------|---------|----------|
| Production | `gamesapi.revelryapp.me` | `games-backend` | `revelry-backend:latest` | `127.0.0.1:8000` | `/home/revelry-games/revelry-data` |
| Gamma | `gamesapi-gamma.revelryapp.me` | `games-backend-gamma` | `revelry-backend-gamma:latest` | `127.0.0.1:8004` | `/home/revelry-games/revelry-data-gamma` |

The older backup containers `revelry-platform` and `revelry-gamma` may exist on the VM. They are not managed by `scripts/deploy-gcp.sh`; the LocalPlay deploy script only stops/removes `games-backend` and `games-backend-gamma`.

Useful state checks:

```bash
gcloud compute ssh revelry-backend --project=revelryapp --zone=us-central1-a --command \
  'docker ps -a --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"'

curl -sS -i https://gamesapi.revelryapp.me/health
curl -sS -i https://gamesapi-gamma.revelryapp.me/health
```

### Recent gamma deploy — June 24, 2026 (Generic Prompt Party engine)

Deployed commit `44d38ad` via `./scripts/deploy-gcp.sh --gamma --with-frontend` to `games-backend-gamma` (prod `games-backend` untouched). Ships the shared Generic Prompt Party runtime plus ten standalone games: `hot_takes`, `this_or_that`, `caption_contest`, `pitch_battle`, `roast_toast`, `desert_island`, `memory_lane`, `rapid_fire`, `one_word_vibes`, and `emoji_story`. Verified live after deploy: `/health` returned healthy, `/catalog` contains all ten game ids with `content_schema.kind=generic_prompt_party_v1`, and `npm run test:e2e:gamma` passed on desktop and mobile. No Supabase schema migration is required. Revelry/host-app exposure remains disabled because these entries are standalone-only until a bridge/policy pass is completed.

### Recent gamma deploy — June 12, 2026 (Revelry integration hardening)

Deployed via `./scripts/deploy-gcp.sh --gamma --with-frontend` to `games-backend-gamma` (prod `games-backend` untouched). Ships the June 12 integration hardening in `SPEC-REVELRY-INTEGRATION.md`: session-create/party-games-link `game_type` validators accept all Revelry host-app start types, handoff JWTs require `iss=revelry`+`aud=localplay`+`typ=localplay_launch`, and return-url default-port normalization. Verified live: `POST https://gamesapi-gamma.revelryapp.me/integrations/revelry/sessions` with `game_type=drawing` passes validation (→ 401 without credentials) and `game_type=bogus` → 422 listing all five types. Not yet redeployed to prod — run `./scripts/deploy-gcp.sh --with-frontend` after a reviewed prod cutover.

### Recent gamma deploy — June 24, 2026 (expanded Revelry quick-start catalog)

Deployed commit `e00a3ef` via `./scripts/deploy-gcp.sh --gamma --with-frontend` to `games-backend-gamma` (prod `games-backend` untouched). Ships LocalPlay bridge support for Revelry quick-start/settings launches of `would_you_rather`, `never_have_i_ever`, `word_association`, `acronym`, `photo_clue`, and `poker`, plus updated specs and Revelry preprod matrix expectations. Verified live after deploy: `/health` returned healthy, `/catalog?host_app=revelry` returned the expanded game set, and an unauthenticated `POST /integrations/revelry/sessions` with `game_type=photo_clue` returned `401 Missing integration credential` rather than a validator rejection.

### Recent gamma deploy — June 24, 2026 (Survey Says standalone MVP)

Deployed commit `119ff65` via `./scripts/deploy-gcp.sh --gamma --with-frontend` to `games-backend-gamma` (prod `games-backend` untouched). Ships standalone `survey_says` with default curated rounds, automatic two-team assignment, player guesses, host answer-board adjudication, strikes, steal flow, late joins, spectator sync, rules metadata, and podium. Verified live after deploy: `/health` returned healthy, `/catalog` includes `survey_says`, and `npm run test:e2e:gamma` passed against `https://gamesapi-gamma.revelryapp.me` on desktop and mobile.

Follow-up verification on June 24:

- `npm run test:e2e:gamma` passed against `https://gamesapi-gamma.revelryapp.me` on desktop and mobile.
- `python3 scripts/smoke-remote.py --base-url https://gamesapi-gamma.revelryapp.me --skip-generate` passed.
- `PREPROD_REVELRY=1 REVELRY_GAMMA_PARTY_GAMES_URL_FILE=../gamma_party_games_url.txt npm run test:e2e:preprod-revelry` passed after adding the Random Chit saved-content fixture to the matrix.

Production is intentionally not updated by this gamma deploy. As of the same check, `https://gamesapi.revelryapp.me/catalog?host_app=revelry` exposed only `quiz`, `wmlt`, `drawing`, and `musical_chairs`, and `POST /integrations/revelry/sessions` with `game_type=photo_clue` returned a validator `422`. A prod rollout therefore requires deploying current `master` to production before enabling policy rows for the new game types.

Production rollout notes for the six new quick-start/settings candidates:

- No Supabase schema migration is required for `would_you_rather`, `never_have_i_ever`, `word_association`, `acronym`, `photo_clue`, or `poker` because the Revelry bridge starts them without saved `generated_content`.
- Add production `host_app_catalog_flags` rows only after prod deploy and smoke. Use `status=live`, `enabled=true`, and leave `can_create_content=false` as advertised by the static catalog.
- Photo Clue policy may expose `supports_images=true`, but Revelry should not mirror raw uploaded photos unless LocalPlay returns an explicit safe share payload.
- Party Poker must stay no-money/no-rewards: no buy-ins, cash-out, sparks, prizes, or economy-linked copy.
- Random Chit can be enabled in production as quick-start-only before the prod DDL by overriding `can_create_content=false`, `can_edit_content=false`, and `supports_ai_generation=false`. Do not enable Random Chit saved-content/AI authoring in prod until the `generated_content.content_type` CHECK migration is applied.

### Pending LocalPlay DB/content migration — June 24, 2026

Random Chit host-app authoring adds `chit_pull` as a saved `generated_content.content_type`. The local SQLite initializer/migration and rendered Supabase SQL expand the CHECK constraint to `('quiz', 'mlt', 'drawing', 'housie', 'chit_pull')`. Gamma Supabase DDL was applied on June 24, 2026 and verified with `games_gamma_generated_content_content_type_check`. Production SQL is updated in-repo but not applied; do not enable Random Chit `can_create_content` / `supports_ai_generation` production policy rows until the production DDL is explicitly applied.

Would You Rather, Never Have I Ever, Word Association, Acronym Game, Photo Clue, and Party Poker are Revelry quick-start/settings candidates only. They do not save `generated_content` rows through the host-app bridge and do not require a schema migration before host-app catalog policy enablement. Keep them policy-gated until embedded gamma QA covers start, join, spectator, reconnect, completion, and result polling. Photo Clue should not mirror raw uploaded photos into Revelry unless LocalPlay returns an explicit safe share payload. Party Poker must remain no-money/no-rewards.

## IONOS Directory Structure

```
~/revelryapp/
  site/          → revelryapp.me (marketing website)
  app/           → app.revelryapp.me (platform frontend, future)
  games/         → games.revelryapp.me (public LocalPlay game surface)
    quiz/        → legacy LocalPlay static build, kept only for old links/PWAs
  media/         → media.revelryapp.me
    apps/
      localplay/ → LocalPlay uploaded/generated game images
        music/   → hosted Musical Chairs loop files
```

## Credentials & Access

| Service | Access |
|---------|--------|
| IONOS SSH | `ssh u69414981@home420463025.1and1-data.host` (key: `~/.ssh/id_ed25519`) |
| GCP SSH | `gcloud compute ssh revelry-backend --project=revelryapp --zone=us-central1-a` |
| GCP VM IP | `136.115.33.75` |
| GCP Project | `revelryapp` |
| GCP Zone | `us-central1-a` |
| GCP Instance | `revelry-backend` |
| Supabase Project | `hosbtyylacluziugwjfd` (`LearningCompanion`, shared with VibePix) |

---

## From-Scratch Setup

Use this section when rebuilding the VM setup or adding LocalPlay to a fresh host. These steps assume the GCP VM exists and you can SSH into it with `gcloud compute ssh`.

### 1. DNS

In IONOS DNS for `revelryapp.me`, create or verify:

| Host | Type | Value |
|------|------|-------|
| `gamesapi` | `A` | `136.115.33.75` |
| `gamesapi-gamma` | `A` | `136.115.33.75` |

Verify from local:

```bash
nslookup gamesapi.revelryapp.me
nslookup gamesapi-gamma.revelryapp.me
```

### 2. Install VM packages

On a fresh Debian/Ubuntu VM:

```bash
gcloud compute ssh revelry-backend --project=revelryapp --zone=us-central1-a

sudo apt-get update
sudo apt-get install -y docker.io nginx certbot python3-certbot-nginx sqlite3
sudo systemctl enable --now docker
sudo systemctl enable --now nginx
sudo usermod -aG docker "$USER"
exit
```

Open a new SSH session after adding the user to the `docker` group.

### 3. Bootstrap the LocalPlay VM home

The canonical LocalPlay home on the VM is `/home/revelry-games`.

```bash
./scripts/deploy-gcp.sh --bootstrap-vm --skip-build
```

This creates:

```text
/home/revelry-games/
  app/
    .env
    .env.gamma
  revelry-data/
  revelry-backups/
  revelry-data-gamma/
  revelry-backups-gamma/
```

If `/home/revelry-games/app/.env` does not exist, the bootstrap script copies `/home/Avi/app/.env` when available. Otherwise create `/home/revelry-games/app/.env` manually before deploying.

The gamma env is copied from production and then adjusted by bootstrap:

```env
ALLOWED_ORIGINS=https://gamesapi-gamma.revelryapp.me,http://localhost:9200,http://127.0.0.1:9200
DB_DIR=/app/data
JWT_SECRET=<generated by bootstrap if missing>
DB_BACKEND=supabase
TABLE_PREFIX=games_gamma_
SUPABASE_URL=https://hosbtyylacluziugwjfd.supabase.co
SUPABASE_SERVICE_KEY=<service-role-key>
CHECKOUT_RETURN_URL=https://gamesapi-gamma.revelryapp.me/
TRUST_PROXY_HEADERS=true
GEMINI_MODEL=gemini-2.5-flash-lite
GEMINI_PREMIUM_MODEL=gemini-2.5-flash-lite
REMOTE_CONFIG_URL=https://gamesapi-gamma.revelryapp.me/config.json
GOOGLE_CLIENT_ID=458966837298-9hjencou1ag2o17ln06iuuj86j5p8igj.apps.googleusercontent.com
APPLE_CLIENT_ID=me.revelryapp.quiz.web
APPLE_CLIENT_IDS=me.revelryapp.quiz.web,me.revelryapp.quiz
PUBLIC_BASE_URL=https://gamesapi-gamma.revelryapp.me
REVELRY_INTEGRATION_SECRET=<strong gamma shared secret matching Revelry gamma>
REVELRY_LAUNCH_TOKEN_TTL_SECONDS=600
REVELRY_AUTHORING_TOKEN_TTL_SECONDS=3600
REVELRY_PARTY_HUB_RETURN_TOKEN_TTL_SECONDS=14400
REVELRY_SESSION_LOBBY_TTL_SECONDS=14400
REVELRY_SESSION_IDLE_TTL_SECONDS=7200
REVELRY_CALLBACK_URL=https://api-gamma.revelryapp.me/api/games/localplay/callback
# Keep unset unless doing a deliberate callback-secret rotation/compatibility window.
REVELRY_CALLBACK_SECRET=
```

**Important:** The bootstrap copies production Stripe keys into gamma. You must manually replace them with test-mode keys (`sk_test_...`, `whsec_...`) in `/home/revelry-games/app/.env.gamma` before testing checkout, or you will charge real money.

Production `.env` should also include `gamesapi.revelryapp.me` in `ALLOWED_ORIGINS` for backend-served SPA access:

```env
ALLOWED_ORIGINS=https://games.revelryapp.me,https://gamesapi.revelryapp.me,capacitor://localhost,http://localhost,https://localhost,http://localhost:9200,http://127.0.0.1:9200
TRUST_PROXY_HEADERS=true
JWT_SECRET=<generated by bootstrap if missing>
DB_BACKEND=supabase
TABLE_PREFIX=games_
SUPABASE_URL=https://hosbtyylacluziugwjfd.supabase.co
SUPABASE_SERVICE_KEY=<service-role-key>
GOOGLE_CLIENT_ID=458966837298-9hjencou1ag2o17ln06iuuj86j5p8igj.apps.googleusercontent.com
APPLE_CLIENT_ID=me.revelryapp.quiz.web
APPLE_CLIENT_IDS=me.revelryapp.quiz.web,me.revelryapp.quiz
PUBLIC_BASE_URL=https://gamesapi.revelryapp.me
REVELRY_INTEGRATION_SECRET=<strong prod shared secret matching Revelry prod>
REVELRY_LAUNCH_TOKEN_TTL_SECONDS=600
REVELRY_AUTHORING_TOKEN_TTL_SECONDS=3600
REVELRY_PARTY_HUB_RETURN_TOKEN_TTL_SECONDS=14400
REVELRY_SESSION_LOBBY_TTL_SECONDS=14400
REVELRY_SESSION_IDLE_TTL_SECONDS=7200
REVELRY_CALLBACK_URL=https://api.revelryapp.me/api/games/localplay/callback
# Keep unset unless doing a deliberate callback-secret rotation/compatibility window.
REVELRY_CALLBACK_SECRET=
```

Origins are scheme + host + optional port only; do not include `/quiz/` or other paths. Installed PWAs still use the web origin they were installed from, while Capacitor/native shells and local development need their own localhost-style origins.

`JWT_SECRET` is required for successful Google/Apple sign-in. Google or Apple may return a valid ID token, but the backend cannot finish login unless it can mint the app's own session JWT.

### 3a. Configure Google and Apple web sign-in origins

Google and Apple must trust every browser origin that can host the SPA. This includes the IONOS customer URL and the backend-served prod/gamma URLs. Otherwise the browser sign-in popup can fail before the backend receives a token.

Google Cloud Console: <https://console.cloud.google.com/apis/credentials>

Open the Web OAuth client whose client ID matches `VITE_GOOGLE_CLIENT_ID`, then add these **Authorized JavaScript origins**:

```text
https://games.revelryapp.me
https://gamesapi.revelryapp.me
https://gamesapi-gamma.revelryapp.me
http://localhost:5173
http://localhost:9200
http://127.0.0.1:9200
```

The current Google Identity Services popup flow primarily needs JavaScript origins, not redirect URIs. If redirect URIs are configured on the same client, keep the Firebase handler and add the same web roots for compatibility:

```text
https://revelryapp.firebaseapp.com/__/auth/handler
https://games.revelryapp.me
https://gamesapi.revelryapp.me
https://gamesapi-gamma.revelryapp.me
http://localhost:5173
http://localhost:9200
http://127.0.0.1:9200
```

Do not include `/quiz/` in Google OAuth origins or redirect roots.

Apple Developer: <https://developer.apple.com/account/resources/identifiers/list>

Open the web Sign in with Apple Service ID `me.revelryapp.quiz.web`, enable Sign in with Apple, and configure these domains:

```text
games.revelryapp.me
gamesapi.revelryapp.me
gamesapi-gamma.revelryapp.me
```

Configure these return URLs:

```text
https://games.revelryapp.me
https://gamesapi.revelryapp.me
https://gamesapi-gamma.revelryapp.me
```

Backend-served builds intentionally set `VITE_APPLE_REDIRECT_URI` to blank, so Apple JS falls back to `window.location.origin`. The IONOS build can keep `VITE_APPLE_REDIRECT_URI=https://games.revelryapp.me`.

### 3b. Verify sign-in state

Browser sign-in is not Firebase Auth. The app uses Google Identity Services and Apple Sign-In directly, sends the provider ID token to `/auth/signin`, and the backend creates a LocalPlay session JWT.

Expected successful login state:

- The menu shows **Signed in**.
- The account/email prefix is visible.
- The **Sign Out** button is visible.
- The browser has a LocalPlay session token for the current origin.

Verified browser sign-in coverage:

| Origin | Google | Apple |
|--------|--------|-------|
| `https://gamesapi-gamma.revelryapp.me` | Verified | Verified |
| `https://games.revelryapp.me/` | Configured; expected to work with the same web client | Verified |

The LocalPlay session is separate from the main Revelry app. It may share Google Cloud/Firebase project infrastructure, but it does not share the main Revelry app's login cookie or session.

Common sign-in failures:

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Google `origin_mismatch` before the app receives a token | Missing OAuth JavaScript origin | Add the exact SPA origin in Google Cloud Console |
| Account chooser appears, then app says invalid/expired token | Backend cannot complete LocalPlay session creation | Verify `JWT_SECRET`, `GOOGLE_CLIENT_ID`, and container runtime env |
| Apple popup fails or returns invalid token | Apple Service ID domains/return URLs or audience mismatch | Verify Apple Developer Service ID and `APPLE_CLIENT_IDS` |
| Login works on `games.revelryapp.me` but not `gamesapi-gamma.revelryapp.me` | Provider console only trusts the IONOS origin | Add backend-served prod/gamma origins |
| Signed-in user has 0 sparks | New user wallet or wallet merge did not transfer guest balance | Check wallet merge logs and `/tokens/balance` under the signed-in session |

Runtime checks:

```bash
gcloud compute ssh revelry-backend --project=revelryapp --zone=us-central1-a --command \
  'for c in games-backend games-backend-gamma; do echo "== $c =="; docker exec "$c" sh -lc '"'"'printf "JWT_SECRET=%s\n" "${JWT_SECRET:+set}"; printf "GOOGLE_CLIENT_ID=%s\n" "${GOOGLE_CLIENT_ID:+set}"; printf "APPLE_CLIENT_ID=%s\n" "${APPLE_CLIENT_ID:+set}"; printf "APPLE_CLIENT_IDS=%s\n" "${APPLE_CLIENT_IDS:+set}"'"'"'; done'
```

### 4. Install nginx routes

Production should proxy to `127.0.0.1:8000`; gamma should proxy to `127.0.0.1:8004`.

Create `/etc/nginx/sites-available/revelry-gamesapi`:

```nginx
server {
    server_name gamesapi.revelryapp.me;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }

    listen 80;
}
```

Create `/etc/nginx/sites-available/revelry-gamesapi-gamma`:

```nginx
server {
    server_name gamesapi-gamma.revelryapp.me;

    location / {
        proxy_pass http://127.0.0.1:8004;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }

    listen 80;
}
```

Enable, test, reload, and issue certs:

```bash
sudo ln -sf /etc/nginx/sites-available/revelry-gamesapi /etc/nginx/sites-enabled/revelry-gamesapi
sudo ln -sf /etc/nginx/sites-available/revelry-gamesapi-gamma /etc/nginx/sites-enabled/revelry-gamesapi-gamma
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d gamesapi.revelryapp.me
sudo certbot --nginx -d gamesapi-gamma.revelryapp.me
sudo nginx -t
sudo systemctl reload nginx
```

### 5. Deploy both backend containers with bundled SPA

From the repo root:

```bash
./scripts/deploy-gcp.sh --with-frontend
./scripts/deploy-gcp.sh --gamma --with-frontend
```

The script builds the Docker images locally with `--platform linux/amd64`, uploads them to the VM, backs up SQLite, restarts only the target LocalPlay container, and checks `/health`.

### 6. Verify from outside the VM

```bash
curl -sS -i https://gamesapi.revelryapp.me/health
curl -sS -i https://gamesapi-gamma.revelryapp.me/health
curl -sS -D - -o /dev/null https://gamesapi.revelryapp.me/
curl -sS -D - -o /dev/null https://gamesapi-gamma.revelryapp.me/join/testroom
curl -sS -i https://gamesapi.revelryapp.me/providers
curl -sS -i https://gamesapi-gamma.revelryapp.me/providers
```

Expected:

- `/health` returns JSON `200`
- `/` and client routes like `/join/testroom` return `text/html`
- API routes like `/providers` return JSON, not `index.html`

### 7. Optional: deploy public IONOS frontend

The IONOS frontend remains the canonical public game surface:

```bash
cd frontend
VITE_BASE_PATH=/ VITE_API_URL=https://gamesapi.revelryapp.me VITE_WEB_URL=https://games.revelryapp.me/ VITE_CAST_APP_ID=1BC9ACD8 npx vite build
ssh u69414981@home420463025.1and1-data.host "mkdir -p ~/revelryapp/games"
scp -r dist/* u69414981@home420463025.1and1-data.host:~/revelryapp/games/
rsync -avz dist/.htaccess u69414981@home420463025.1and1-data.host:~/revelryapp/games/.htaccess
```

### 7a. Optional: deploy Musical Chairs hosted music

Built-in Musical Chairs streams short loop files from IONOS media storage so the web/native app bundle stays small. The canonical public base is:

```text
https://media.revelryapp.me/apps/localplay/music/
~/revelryapp/media/apps/localplay/music/
```

Generate the current 20 MVP loops locally:

```bash
node scripts/generate-musical-chairs-loops.mjs /private/tmp/localplay-musical-chairs-audio
```

Upload:

```bash
ssh u69414981@home420463025.1and1-data.host "mkdir -p ~/revelryapp/media/apps/localplay/music"
rsync -avz /private/tmp/localplay-musical-chairs-audio/ u69414981@home420463025.1and1-data.host:~/revelryapp/media/apps/localplay/music/
```

Verify one file:

```bash
curl -sSI https://media.revelryapp.me/apps/localplay/music/upbeat-confetti.wav
```

The frontend manifest lives in `frontend/src/audio/musicalChairsTracks.ts`. Set `VITE_MUSICAL_CHAIRS_MUSIC_BASE_URL` only if the media base changes; otherwise it defaults to the IONOS URL above.

---

## Frontend Deployment

### Prerequisites
- Node.js installed locally
- SSH key configured for IONOS

### Step 1: Build the frontend

```bash
cd frontend

# Production build with root path and backend URL
VITE_BASE_PATH=/ VITE_API_URL=https://gamesapi.revelryapp.me VITE_WEB_URL=https://games.revelryapp.me/ VITE_CAST_APP_ID=1BC9ACD8 npx vite build
```

This produces `frontend/dist/` with all static assets.

### Step 2: Prepare the IONOS target directory

```bash
ssh u69414981@home420463025.1and1-data.host "mkdir -p ~/revelryapp/games"
```

Old JS/CSS bundles have hashed filenames that accumulate. Clean `~/revelryapp/games/assets` before deploying when you want to remove stale root bundles; keep `~/revelryapp/games/quiz` unless intentionally removing the legacy path.

### Step 3: Upload to IONOS

```bash
scp -r frontend/dist/* u69414981@home420463025.1and1-data.host:~/revelryapp/games/
rsync -avz frontend/dist/.htaccess u69414981@home420463025.1and1-data.host:~/revelryapp/games/.htaccess
```

### Step 4: Verify

Open https://games.revelryapp.me/ in a browser. Check the browser console for errors.

### SPA Routing

An `.htaccess` file at `~/revelryapp/games/.htaccess` handles client-side routing:

```apache
RewriteEngine On
RewriteBase /
RewriteCond %{REQUEST_FILENAME} !-f
RewriteCond %{REQUEST_FILENAME} !-d
RewriteRule ^ index.html [L]
```

The legacy `/quiz/` directory can remain for old links/PWAs, but new production builds should be uploaded at the root.

---

## Backend Deployment

### Prerequisites
- `gcloud` CLI installed and authenticated (`gcloud auth login`)
- Docker installed locally
- Docker installed on the VM
- Node.js installed locally when using `--with-frontend`
- `/home/revelry-games/app/.env` exists on the VM

### Preferred script deploy

The deployment script builds locally, copies the image to the VM, backs up SQLite, restarts the container, and verifies `/health`.
Images are built with `--platform linux/amd64` because the GCP VM is AMD64 even when the local build machine is Apple Silicon.

```bash
# One-time VM layout bootstrap
./scripts/deploy-gcp.sh --bootstrap-vm --skip-build

# Production API + backend-served SPA fallback
./scripts/deploy-gcp.sh --with-frontend

# Gamma full-stack same-origin environment
./scripts/deploy-gcp.sh --gamma --with-frontend

# Backend-only production deploy
./scripts/deploy-gcp.sh
```

Script container layout:

| Environment | Container | VM bind | Env file | Data dir |
|-------------|-----------|---------|----------|----------|
| Production | `games-backend` | `127.0.0.1:8000` | `/home/revelry-games/app/.env` | `/home/revelry-games/revelry-data` |
| Gamma | `games-backend-gamma` | `127.0.0.1:8004` | `/home/revelry-games/app/.env.gamma` | `/home/revelry-games/revelry-data-gamma` |

`--with-frontend` builds `frontend/dist` with same-origin API settings and packages it into the backend image at `/app/static`. If `/app/static/index.html` is absent, the backend still runs API-only.

`--bootstrap-vm` creates the canonical LocalPlay VM home at `/home/revelry-games`, migrates `/home/Avi/app/.env` into `/home/revelry-games/app/.env` if needed, creates `.env.gamma`, and creates prod/gamma data and backup directories.

Port notes:
- Production `gamesapi.revelryapp.me` uses `127.0.0.1:8000`.
- `127.0.0.1:8001` is already reserved by the existing `/pp/` proxy in `revelry-gamesapi`.
- `127.0.0.1:8003` is already used by the older `api-gamma.revelryapp.me` config.
- LocalPlay gamma therefore uses `127.0.0.1:8004`.

### Backend-served SPA behavior

When deployed with `--with-frontend`, the container includes the Vite build under `/app/static`.

Expected behavior:

- `GET /` returns `index.html`
- client routes like `/join/testroom` return `index.html`
- static files like `/assets/index-*.js` return the real asset
- missing assets under `/assets/*` return JSON `404`
- API routes stay API routes and never fall through to the SPA

Protected API prefixes include `/system`, `/providers`, `/quiz`, `/quiz-packs`, `/room`, `/ws`, `/mlt`, `/drawing`, `/history`, `/auth`, `/checkout`, `/webhook`, `/tokens`, `/entitlements`, `/purchases`, `/admin`, `/health`, `/sd`, `/catalog`, `/integrations`, `/media`, and `/config.json`.

The frontend service worker must mirror this rule for same-origin backend-served builds. It should not cache or fulfill API requests for `gamesapi.revelryapp.me`, `gamesapi-gamma.revelryapp.me`, local backend port `8000`, or any protected API prefix; those requests must always reach the backend. Service-worker updates should wait and surface the in-app **New version ready** prompt; do not restore automatic `skipWaiting()` unless the app also avoids mid-game reloads. Embedded Revelry/host-app iframe routes skip service-worker registration, and standalone registration must resolve `sw.js` from the app root rather than the current route path.

The fallback route resolves candidate files under `/app/static` and rejects paths outside that directory to avoid directory traversal.

### Verify

```bash
curl -sS -i https://gamesapi.revelryapp.me/health
curl -sS -i https://gamesapi-gamma.revelryapp.me/health
curl -sS -D - -o /dev/null https://gamesapi.revelryapp.me/
curl -sS -D - -o /dev/null https://gamesapi-gamma.revelryapp.me/
curl -sS -i https://gamesapi.revelryapp.me/providers
```

Check containers on the VM:

```bash
gcloud compute ssh revelry-backend --project=revelryapp --zone=us-central1-a --command \
  'docker ps -a --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"'
```

---

## Nginx Configuration

Nginx runs on the VM as a reverse proxy. Each subdomain has its own config file:

- `/etc/nginx/sites-available/revelry-gamesapi` — `gamesapi.revelryapp.me` (LocalPlay backend)
- `/etc/nginx/sites-available/revelry-gamesapi-gamma` — `gamesapi-gamma.revelryapp.me` (gamma backend + frontend)
- `/etc/nginx/sites-available/revelry-api` — `api.revelryapp.me` (legacy, kept for backward compat)

Key sections:
- Listens on 443 (HTTPS) with Let's Encrypt certs
- Proxies production requests to `http://127.0.0.1:8000`
- Proxies gamma requests to `http://127.0.0.1:8004`
- WebSocket upgrade headers for `/ws/` paths
- HTTP (port 80) redirects to HTTPS

Gamma should proxy to `http://127.0.0.1:8004`; production should proxy to `http://127.0.0.1:8000`.

### View current config
```bash
sudo cat /etc/nginx/sites-available/revelry-gamesapi
```

### After editing Nginx config
```bash
sudo nginx -t              # test config syntax
sudo systemctl reload nginx  # apply changes
```

### Gamma nginx setup

Create `/etc/nginx/sites-available/revelry-gamesapi-gamma`:

```nginx
server {
    server_name gamesapi-gamma.revelryapp.me;

    location / {
        proxy_pass http://127.0.0.1:8004;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }

    listen 80;
}
```

Enable and issue cert:

```bash
sudo ln -sf /etc/nginx/sites-available/revelry-gamesapi-gamma /etc/nginx/sites-enabled/revelry-gamesapi-gamma
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d gamesapi-gamma.revelryapp.me
sudo nginx -t
sudo systemctl reload nginx
```

### Gamma env setup

The canonical LocalPlay VM home is `/home/revelry-games`. Bootstrap it once:

```bash
./scripts/deploy-gcp.sh --bootstrap-vm --skip-build
```

This creates:

```text
/home/revelry-games/
  app/
    .env
    .env.gamma
  revelry-data/
  revelry-backups/
  revelry-data-gamma/
  revelry-backups-gamma/
```

If doing it manually instead, production env lives at `/home/revelry-games/app/.env`, and gamma should live beside it:

```bash
sudo cp /home/revelry-games/app/.env /home/revelry-games/app/.env.gamma
sudo mkdir -p /home/revelry-games/revelry-data-gamma /home/revelry-games/revelry-backups-gamma
```

Then edit `/home/revelry-games/app/.env.gamma`:

```env
ALLOWED_ORIGINS=https://gamesapi-gamma.revelryapp.me
DB_DIR=/app/data
```

Use test Stripe keys in gamma before testing checkout. If checkout is not being tested, live Stripe keys should still be avoided in gamma.

Deploy gamma:

```bash
./scripts/deploy-gcp.sh --gamma --with-frontend
```

Verify:

```bash
curl -s https://gamesapi-gamma.revelryapp.me/health
curl -s https://gamesapi-gamma.revelryapp.me/ | head -3
curl -sI https://gamesapi-gamma.revelryapp.me/assets/DO_REPLACE_WITH_BUILT_ASSET
```

---

## SSL Certificate

Managed by Certbot. Auto-renews via systemd timer.

### Check cert status
```bash
sudo certbot certificates
```

### Force renewal (if needed)
```bash
sudo certbot renew --force-renewal
sudo systemctl reload nginx
```

---

## Backend .env (Production)

The production `.env` lives at `/home/revelry-games/app/.env` on the VM and should have at minimum:

```env
# AI Providers — at least one must be configured
GEMINI_API_KEY=<your-key>
GEMINI_MODEL=gemini-2.5-flash-lite
GEMINI_PREMIUM_MODEL=gemini-2.5-flash-lite
DEFAULT_PROVIDER=gemini
REMOTE_CONFIG_URL=https://games.revelryapp.me/config.json

# Server
HOST=0.0.0.0
PORT=8000
ALLOWED_ORIGINS=https://revelryapp.me,https://www.revelryapp.me,https://games.revelryapp.me,https://gamesapi.revelryapp.me,capacitor://localhost,http://localhost,https://localhost,http://localhost:9200,http://127.0.0.1:9200
DB_DIR=/app/data
TRUST_PROXY_HEADERS=true

# Persistence
DB_BACKEND=supabase
TABLE_PREFIX=games_
SUPABASE_URL=https://hosbtyylacluziugwjfd.supabase.co
SUPABASE_SERVICE_KEY=<service-role-key>

# Game
ROOM_TTL_SECONDS=1800
ORGANIZER_RECONNECT_GRACE_SECONDS=600
LOG_LEVEL=INFO
```

Include `https://gamesapi.revelryapp.me` in production `ALLOWED_ORIGINS` when using the backend-served SPA fallback, and keep PWA/native/local development origins that the app can actually launch from:

```env
ALLOWED_ORIGINS=https://revelryapp.me,https://www.revelryapp.me,https://games.revelryapp.me,https://gamesapi.revelryapp.me,capacitor://localhost,http://localhost,https://localhost,http://localhost:9200,http://127.0.0.1:9200
```

Gamma env lives at `/home/revelry-games/app/.env.gamma`. Keep it separate from production because it has its own database volume and should use safe/test third-party credentials:

```env
ALLOWED_ORIGINS=https://gamesapi-gamma.revelryapp.me,http://localhost:9200,http://127.0.0.1:9200
DB_BACKEND=supabase
TABLE_PREFIX=games_gamma_
SUPABASE_URL=https://hosbtyylacluziugwjfd.supabase.co
SUPABASE_SERVICE_KEY=<service-role-key>
DB_DIR=/app/data
CHECKOUT_RETURN_URL=https://gamesapi-gamma.revelryapp.me/
TRUST_PROXY_HEADERS=true
GEMINI_MODEL=gemini-2.5-flash-lite
GEMINI_PREMIUM_MODEL=gemini-2.5-flash-lite
REMOTE_CONFIG_URL=https://gamesapi-gamma.revelryapp.me/config.json
ROOM_TTL_SECONDS=1800
ORGANIZER_RECONNECT_GRACE_SECONDS=600
```

AI model gotcha: `backend/config.py` defaults to `gemini-2.5-flash-lite`, but deployed env vars and remote `config.json` override code defaults. If generation fails with Gemini `404 Not Found`, check `GEMINI_MODEL`, `GEMINI_PREMIUM_MODEL`, `REMOTE_CONFIG_URL`, and `ai_models` in `frontend/public/config.json`. Free and premium generation should both use `gemini-2.5-flash-lite`.

Mobile room lifecycle gotcha: keep `ORGANIZER_RECONNECT_GRACE_SECONDS` comfortably longer than a normal phone lock/background interruption. The default is 600 seconds. Do not lower this to a few seconds; otherwise the organizer's phone sleeping can close the whole room before the host or players can reconnect.

Ollama and Stable Diffusion are NOT available on the production VM (no GPU).

---

## Supabase Connection Reference

### Project

| Field | Value |
|---|---|
| Project ref | `hosbtyylacluziugwjfd` |
| Project name | LearningCompanion (shared with VibePix) |
| Region | us-west-2 |
| REST URL | `https://hosbtyylacluziugwjfd.supabase.co` |
| Dashboard | `https://supabase.com/dashboard/project/hosbtyylacluziugwjfd` |

### How LocalPlay connects at runtime

The backend uses raw HTTP via `httpx` to the Supabase PostgREST API. No Supabase client SDK.

Implementation: `backend/supabase_db.py` → `SupabaseClient` class.

```
Every request:
  apikey: <SUPABASE_SERVICE_KEY>
  Authorization: Bearer <SUPABASE_SERVICE_KEY>
  Content-Type: application/json

CRUD via PostgREST:
  GET    {SUPABASE_URL}/rest/v1/{prefix}{table}?{filters}     # select
  POST   {SUPABASE_URL}/rest/v1/{prefix}{table}                # insert/upsert
  PATCH  {SUPABASE_URL}/rest/v1/{prefix}{table}?{filters}      # update
  DELETE {SUPABASE_URL}/rest/v1/{prefix}{table}?{filters}      # delete

Atomic operations via Postgres RPCs:
  POST   {SUPABASE_URL}/rest/v1/rpc/{prefix}{function}         # e.g. games_debit_tokens
```

PostgREST filter syntax: `eq.`, `is.null`, `not.is.null`, `in.()`, `gte.`, `lt.`, `lte.`, `ilike.`

### Backend env vars

```env
DB_BACKEND=supabase
TABLE_PREFIX=games_              # or games_gamma_ for gamma
SUPABASE_URL=https://hosbtyylacluziugwjfd.supabase.co
SUPABASE_SERVICE_KEY=<service-role-key>
SUPABASE_ANON_KEY=<anon-key>     # optional, not used at runtime
SUPABASE_TIMEOUT_SECONDS=10
```

### Table prefix isolation

| Environment | Table prefix | Example table | Example RPC |
|---|---|---|---|
| Production | `games_` | `games_wallets` | `games_debit_tokens` |
| Gamma | `games_gamma_` | `games_gamma_wallets` | `games_gamma_debit_tokens` |
| VibePix prod | `vp_` | `vp_photos` | — |
| VibePix gamma | `vp_gamma_` | `vp_gamma_photos` | — |

All apps share one Supabase project. Prefixes prevent collisions.

### LocalPlay tables (per prefix)

```
{prefix}users
{prefix}wallets
{prefix}token_transactions
{prefix}entitlements
{prefix}device_usage
{prefix}request_log
{prefix}pending_tokens
{prefix}webhook_events
{prefix}generated_content
{prefix}quiz_packs
{prefix}quiz_questions
{prefix}media_assets
{prefix}game_sessions
{prefix}localplay_callback_events
{prefix}game_history
{prefix}rejections
```

`{prefix}generated_content.content_type` must allow the game setup types enabled in that environment. Production currently requires `quiz`, `mlt`, and `drawing`. Gamma additionally allows `housie` for the Housie party-hub setup/save/start path. The schema template includes a constraint refresh for existing Supabase tables; apply the rendered environment-specific SQL before deploying a build that saves a new setup type from the Revelry Games hub.

### LocalPlay RPCs (per prefix)

```
{prefix}ensure_wallet
{prefix}debit_tokens
{prefix}credit_tokens
{prefix}credit_purchase
{prefix}merge_wallet
{prefix}grant_daily_bonus
{prefix}grant_ad_reward
{prefix}claim_device_usage
{prefix}claim_user_usage
{prefix}mark_webhook_processed
{prefix}admin_stats
```

### Code architecture

```
backend/db.py              # Facade — all call sites import from here
backend/supabase_db.py     # Supabase implementation (PostgREST via httpx)

db.py selects backend at import:
  if config.DB_BACKEND == "supabase":
      import supabase_db
      # overlay every function in _SUPABASE_EXPORTS via globals()
  else:
      # use SQLite (local dev default)

Call sites (main.py, tokens.py, auth.py) always: import db
They never import supabase_db directly.
```

### SQL schema files

```
sql/templates/games-schema.template.sql   # Source template (__PREFIX__ placeholder)
sql/games-schema.sql                      # Rendered prod (games_)
sql/games-gamma-schema.sql                # Rendered gamma (games_gamma_)
scripts/render-supabase-sql.py            # Regenerates both from template
```

Render after editing the template:

```bash
.venv/bin/python scripts/render-supabase-sql.py --prefix games_ --output sql/games-schema.sql
.venv/bin/python scripts/render-supabase-sql.py --prefix games_gamma_ --output sql/games-gamma-schema.sql
```

### Applying schema changes to Supabase

This is always a manual human step — never automated by deploy scripts or CI.

```bash
# Get auth token from macOS Keychain (same pattern as VibePix)
TOKEN=$(security find-generic-password -s "Supabase CLI" -w | sed 's/^go-keyring-base64://' | base64 -d)

# Apply gamma schema
body=$(jq -n --rawfile q sql/games-gamma-schema.sql '{query: $q}')
curl -sS -X POST "https://api.supabase.com/v1/projects/hosbtyylacluziugwjfd/database/query" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$body"

# Apply prod schema
body=$(jq -n --rawfile q sql/games-schema.sql '{query: $q}')
curl -sS -X POST "https://api.supabase.com/v1/projects/hosbtyylacluziugwjfd/database/query" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$body"
```

HTTP 201 with `[]` means success. Any error returns a JSON object with details.

If an IDE agent cannot read the Keychain item, use an explicit Supabase personal access token in that same shell:

```bash
export SUPABASE_ACCESS_TOKEN="sbp_..."
TOKEN="${SUPABASE_ACCESS_TOKEN}"
supabase projects list
```

The expected project is `hosbtyylacluziugwjfd`. This fixes the restart/session case where `security find-generic-password -s "Supabase CLI" -w` returns "item could not be found" for one agent even though another local agent can read it. The app runtime service-role key is not enough for schema DDL; it only covers PostgREST/RPC runtime access.

### Verifying applied objects

List all LocalPlay tables:

```bash
QUERY="SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE 'games_%' ORDER BY tablename;"
body=$(jq -n --arg q "$QUERY" '{query: $q}')
curl -sS -X POST "https://api.supabase.com/v1/projects/hosbtyylacluziugwjfd/database/query" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$body"
```

List all LocalPlay RPCs:

```bash
QUERY="SELECT proname FROM pg_proc WHERE proname LIKE 'games_%' ORDER BY proname;"
body=$(jq -n --arg q "$QUERY" '{query: $q}')
curl -sS -X POST "https://api.supabase.com/v1/projects/hosbtyylacluziugwjfd/database/query" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$body"
```

Test PostgREST access to a table (uses the service-role key from backend .env):

```bash
curl -sS "https://hosbtyylacluziugwjfd.supabase.co/rest/v1/games_gamma_wallets?select=id&limit=1" \
  -H "apikey: <service-role-key>" \
  -H "Authorization: Bearer <service-role-key>"
```

### Ad-hoc queries via Management API

Run any SQL (read or write) through the Management API:

```bash
TOKEN=$(security find-generic-password -s "Supabase CLI" -w | sed 's/^go-keyring-base64://' | base64 -d)

QUERY="SELECT COUNT(*) as cnt FROM games_wallets;"
body=$(jq -n --arg q "$QUERY" '{query: $q}')
curl -sS -X POST "https://api.supabase.com/v1/projects/hosbtyylacluziugwjfd/database/query" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$body"
```

### When adding new tables or RPCs

1. Edit `sql/templates/games-schema.template.sql` using `__PREFIX__` for all names
2. Run `scripts/render-supabase-sql.py` to regenerate both prod and gamma SQL
3. Add corresponding functions in `backend/supabase_db.py`
4. Add function names to `_SUPABASE_EXPORTS` list in `backend/db.py`
5. Commit the SQL + Python changes
6. **Human manually** applies the SQL to Supabase (gamma first, then prod after testing)

---

## Database Migration Status

Production and gamma currently use Supabase:

| Environment | Active backend | Active data |
|-------------|----------------|-------------|
| Production | `DB_BACKEND=supabase` | Supabase `games_*` tables |
| Gamma | `DB_BACKEND=supabase` | Supabase `games_gamma_*` tables |

Supabase migration planning and SQL scaffolding live in `SPEC-SUPABASE-MIGRATION.md` and `sql/`.

As of 2026-05-19, the LocalPlay Supabase schema has been applied to the shared VibePix/LearningCompanion Supabase project:

- Project ref: `hosbtyylacluziugwjfd`.
- Production tables/RPCs: `games_*`.
- Gamma tables/RPCs: `games_gamma_*`.
- Gamma runtime was switched and smoke-tested against Supabase on 2026-05-19.
- Production SQLite was exported into `games_*` and production was switched to Supabase on 2026-05-19 PDT.
- Production cutover source counts matched Supabase target counts: `2` users, `7` wallets, `17` token transactions, `158` total sparks.
- Production smoke after cutover verified `/health`, `/providers`, `/config.json`, live quiz generation, Supabase wallet/request-log writes, and retry idempotency. Current runtime behavior preflight-checks generation balance and records `spend_generate` only when generated content is accepted into a playable room or reset.

The Supabase project is shared with VibePix, so LocalPlay tables and RPCs must always use explicit prefixes:

| Environment | Prefix |
|-------------|--------|
| Production | `games_` |
| Gamma | `games_gamma_` |

Render SQL locally only:

```bash
.venv/bin/python scripts/render-supabase-sql.py --prefix games_ --output sql/games-schema.sql
.venv/bin/python scripts/render-supabase-sql.py --prefix games_gamma_ --output sql/games-gamma-schema.sql
```

Apply SQL using the same Management API pattern as VibePix:

```bash
TOKEN=$(security find-generic-password -s "Supabase CLI" -w | sed 's/^go-keyring-base64://' | base64 -d)

body=$(jq -n --rawfile q sql/games-gamma-schema.sql '{query: $q}')
curl -sS -X POST "https://api.supabase.com/v1/projects/hosbtyylacluziugwjfd/database/query" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$body"

body=$(jq -n --rawfile q sql/games-schema.sql '{query: $q}')
curl -sS -X POST "https://api.supabase.com/v1/projects/hosbtyylacluziugwjfd/database/query" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$body"
```

Verify applied objects:

```bash
QUERY="SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE 'games_%' ORDER BY tablename;"
body=$(jq -n --arg q "$QUERY" '{query: $q}')
curl -sS -X POST "https://api.supabase.com/v1/projects/hosbtyylacluziugwjfd/database/query" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$body"
```

Migrate a stopped SQLite snapshot into a prefixed Supabase target:

```bash
.venv/bin/python scripts/migrate-sqlite-to-supabase.py \
  --sqlite /private/tmp/localplay-prod-cutover/revelry.db \
  --prefix games_ \
  --supabase-url https://hosbtyylacluziugwjfd.supabase.co \
  --service-key-file /private/tmp/localplay-prod-cutover/supabase-service-key.txt \
  --dry-run

.venv/bin/python scripts/migrate-sqlite-to-supabase.py \
  --sqlite /private/tmp/localplay-prod-cutover/revelry.db \
  --prefix games_ \
  --supabase-url https://hosbtyylacluziugwjfd.supabase.co \
  --service-key-file /private/tmp/localplay-prod-cutover/supabase-service-key.txt \
  --clear-target
```

Production cutover checklist, retained for future rebuilds or rollback/retry work:

- `/home/revelry-games/app/.env` has `SUPABASE_SERVICE_KEY` set.
- Gamma has soaked with `DB_BACKEND=supabase`.
- Production SQLite has been exported/reconciled into `games_*`.
- A fresh production SQLite backup exists.
- Production `.env` sets `DB_BACKEND=supabase` and `TABLE_PREFIX=games_`.

The deploy script validates the prefix before deploy:

- Production must use `TABLE_PREFIX=games_`.
- Gamma must use `TABLE_PREFIX=games_gamma_`.
- `DB_BACKEND=supabase` requires both `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`.

Prod or gamma can be rolled back to SQLite during the initial rollout window by restoring the intended `.env` file to `DB_BACKEND=sqlite` and redeploying the matching target:

```bash
# Production rollback
./scripts/deploy-gcp.sh --with-frontend

# Gamma rollback
./scripts/deploy-gcp.sh --gamma --with-frontend
```

Rollback caveat: writes accepted by Supabase after cutover must be replayed manually into SQLite if you need a fully current rollback database.

---

## Revelry Integration

LocalPlay exposes integration endpoints that let the Revelry app launch games, create rooms, and retrieve results without knowing game internals.

### Env vars

Both LocalPlay and Revelry need a shared secret:

| Service | Env var | Value |
|---|---|---|
| LocalPlay backend | `REVELRY_INTEGRATION_SECRET` | shared HMAC secret (hex, 64 chars) |
| LocalPlay backend | `PUBLIC_BASE_URL` | `https://gamesapi-gamma.revelryapp.me` (gamma) or `https://gamesapi.revelryapp.me` (prod) |
| LocalPlay backend | `REVELRY_AUTHORING_TOKEN_TTL_SECONDS` | authoring token lifetime; default `3600` |
| LocalPlay backend | `REVELRY_PARTY_HUB_RETURN_TOKEN_TTL_SECONDS` | party hub return-token lifetime after a LocalPlay-owned start; default `14400` |
| LocalPlay backend | `REVELRY_CALLBACK_URL` | Revelry callback endpoint for content/session/result sync: `https://api-gamma.revelryapp.me/api/games/localplay/callback` in gamma, `https://api.revelryapp.me/api/games/localplay/callback` in prod |
| LocalPlay backend | `REVELRY_CALLBACK_SECRET` | temporary rotation-only alias; normal callback signing uses `REVELRY_INTEGRATION_SECRET` |
| Revelry backend | `LOCALPLAY_INTEGRATION_SECRET` | same value as `REVELRY_INTEGRATION_SECRET` |

Generate a new secret: `openssl rand -hex 32`

### Setting env vars on the VM

```bash
# Gamma
gcloud compute ssh revelry-backend --zone us-central1-a --command "
  sudo sh -c \"grep -q '^REVELRY_INTEGRATION_SECRET=' /home/revelry-games/app/.env.gamma && \
    sed -i 's#^REVELRY_INTEGRATION_SECRET=.*#REVELRY_INTEGRATION_SECRET=<secret>#' /home/revelry-games/app/.env.gamma || \
    echo 'REVELRY_INTEGRATION_SECRET=<secret>' >> /home/revelry-games/app/.env.gamma\"
  sudo sh -c \"grep -q '^PUBLIC_BASE_URL=' /home/revelry-games/app/.env.gamma && \
    sed -i 's#^PUBLIC_BASE_URL=.*#PUBLIC_BASE_URL=https://gamesapi-gamma.revelryapp.me#' /home/revelry-games/app/.env.gamma || \
    echo 'PUBLIC_BASE_URL=https://gamesapi-gamma.revelryapp.me' >> /home/revelry-games/app/.env.gamma\"
"

# Production (when ready)
# Same pattern with /home/revelry-games/app/.env and PUBLIC_BASE_URL=https://gamesapi.revelryapp.me
```

After setting env vars, redeploy: `./scripts/deploy-gcp.sh --gamma --with-frontend`

### Supabase table

The `game_sessions` table must exist in Supabase before the integration works:

```bash
# Apply gamma schema (includes games_gamma_game_sessions)
TOKEN=$(security find-generic-password -s "Supabase CLI" -w | sed 's/^go-keyring-base64://' | base64 -d)
body=$(jq -n --rawfile q sql/games-gamma-schema.sql '{query: $q}')
curl -sS -X POST "https://api.supabase.com/v1/projects/hosbtyylacluziugwjfd/database/query" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$body"
```

### Integration endpoints

All integration endpoints require `Authorization: Bearer <REVELRY_INTEGRATION_SECRET>`.

LocalPlay callbacks to Revelry are signed with `REVELRY_INTEGRATION_SECRET` using HMAC-SHA256 over `${timestamp}.${raw_body}` and include `X-LocalPlay-Timestamp`, `X-LocalPlay-Event-Id`, and `X-LocalPlay-Signature: sha256=...`. Keep `REVELRY_CALLBACK_SECRET` unset unless doing a deliberate rotation/compatibility window; it must not silently diverge from the integration secret in normal gamma/prod.
If both `REVELRY_INTEGRATION_SECRET` and `REVELRY_CALLBACK_SECRET` are set to different values, LocalPlay logs a startup warning and continues to use `REVELRY_INTEGRATION_SECRET` as canonical.
Revelry-created sessions are LocalPlay `host_app_managed` billing sessions: LocalPlay does not grant signup-bonus sparks to the integration wallet and does not debit sparks when the host starts the game. Customer-facing billing/entitlement policy is owned by Revelry for this launch path. LocalPlay should receive normalized party capabilities from Revelry and enforce them; it should not need Revelry prices, provider receipt data, or transaction amounts in gamma/prod runtime requests.

| Endpoint | Method | Purpose |
|---|---|---|
| `/catalog?host_app=revelry` | GET | List available games with metadata |
| `/integrations/revelry/party-games-link` | POST | Mint a party hub URL and optional LocalPlay-owned start-intent URL |
| `/integrations/revelry/games?party_games_token=...` | GET | Open the party-scoped LocalPlay hub; may include `start_content_id` for Start shortcuts |
| `/integrations/revelry/sessions` | POST | Create a game session for a Revelry party |
| `/integrations/revelry/sessions/{id}/launch-token` | POST | Generate a signed JWT launch URL |
| `/integrations/revelry/sessions/{id}` | GET | Check session status |
| `/integrations/revelry/launch-token/resolve` | GET | Resolve a launch token to a room code (used by frontend) |

### Smoke test

```bash
# 1. Catalog
curl -s "https://gamesapi-gamma.revelryapp.me/catalog?host_app=revelry" | python3 -m json.tool | head -10

# 2. Create session
SECRET="<REVELRY_INTEGRATION_SECRET from gamma .env>"
curl -sS -X POST "https://gamesapi-gamma.revelryapp.me/integrations/revelry/sessions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${SECRET}" \
  -d '{
    "game_type": "quiz",
    "external_context": {
      "host_app": "revelry",
      "external_container_type": "party",
      "external_container_id": "test-party-123",
      "external_container_title": "Test Party"
    },
    "actor": { "display_name": "Avi", "role": "host" }
  }'

# 3. Generate launch token (use session_id from step 2)
curl -sS -X POST "https://gamesapi-gamma.revelryapp.me/integrations/revelry/sessions/<session_id>/launch-token" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${SECRET}" \
  -d '{"scope": "player", "route": "join", "embed": true}'

# 4. Open the returned launch_url in a browser
```

### Gamma readiness status

- Deployed the bridge, party hub, custom quiz authoring, host-app chrome cleanup, and callback retry slice to gamma from commit `cbc218f` on 2026-05-23 with `./scripts/deploy-gcp.sh --gamma --with-frontend`.
- Supabase gamma schema includes `games_gamma_game_sessions`, `games_gamma_quiz_packs`, `games_gamma_quiz_questions`, and `games_gamma_media_assets`.
- Gamma env includes `REVELRY_INTEGRATION_SECRET`, `PUBLIC_BASE_URL=https://gamesapi-gamma.revelryapp.me`, and `REVELRY_CALLBACK_URL=https://api-gamma.revelryapp.me/api/games/localplay/callback`; `REVELRY_CALLBACK_SECRET` should stay unset unless doing a deliberate rotation/compatibility window.
- Smoke-tested after deploy: `/health`, `/config.json`, `/catalog?host_app=revelry`, session creation, launch token generation, status polling, tokenless player launch redirect, party hub link/resolve, party workspace, LocalPlay-hosted authoring, saved quiz start, organizer/player WebSocket play-through, completion, results polling, and no signup-bonus sparks for the Revelry integration wallet.
- Deployed host-app lobby QR rendering from Revelry-provided `guest_join_url`, including the nested `external_context.guest_join_url` / `display.guest_join_url` launch-token shape used by Revelry.
- Callback behavior in gamma build: HMAC over `${timestamp}.${raw_body}` with `REVELRY_INTEGRATION_SECRET`, ISO UTC `occurred_at`, `content.deleted` support, and short bounded retry for Revelry `429` / transient `5xx`. Polling remains the recovery path if callbacks are disabled or miss delivery.
- Deployed host-app completed-game action returns to the Revelry Games surface instead of the standalone LocalPlay setup loop; spectator aliases `/spectate`, `/spectate/{room_code}`, `/tv`, and `/tv/{room_code}` connect through the shared spectator page and show clear websocket error states.
- Deployed broader host-app egress hardening so organizer/player/spectator terminal error states return to Revelry Games instead of exposing standalone LocalPlay picker/join recovery.
- Deployed standalone player/spectator URL room-code normalization before websocket connection so typed TV URLs like `/tv/abcd12` connect to room `ABCD12`.
- Deployed the Revelry start-intent hardening slice to gamma from commit `f6798ee` on 2026-05-24 with `./scripts/deploy-gcp.sh --gamma --with-frontend`. This includes encoded `start_url` query construction, `game_type` validation on party-games links, and in-hub active-game replacement confirmation before closing the old room.
- Deployed the generic Revelry setup/save/start slice to gamma from commit `2b3e345` on 2026-05-24 with `./scripts/deploy-gcp.sh --gamma --with-frontend`. This includes WMLT/Drawing setup forms, stable party-scoped saved content ids before start for those configurable games, generic party-hub content save/load/delete APIs, and catalog updates (`can_create_content = true`, `can_quick_start = false`) for WMLT/Drawing.
- Deployed the Revelry party-content scoping and callback hardening slice to gamma from commit `13f609e` on 2026-05-24 with `./scripts/deploy-gcp.sh --gamma --with-frontend`. This includes standalone custom-quiz draft isolation from Revelry party drafts, safe callback actor metadata for hub-started games, parsed-origin return/guest URL validation, `content.updated` with `previous_content_id` when used content versions, and startup warnings if `REVELRY_CALLBACK_SECRET` diverges from canonical `REVELRY_INTEGRATION_SECRET`.
- Applied the rendered gamma Supabase schema on 2026-05-24; `games_gamma_generated_content_content_type_check` now allows `quiz`, `mlt`, and `drawing`.
- Post-deploy gamma smoke on 2026-05-24 passed for `/health`, `/media/status`, `/config.json`, SPA root, anonymous auth rejection, invalid sign-in rejection, iOS checkout guard, and `GET /catalog?host_app=revelry`. The remote smoke was run with generation skipped; catalog returned launchable `quiz`, `wmlt`, and `drawing`, with Drawing Game default `time_limit = 30`.
- Deployed the active Revelry game re-entry and Supabase catalog-policy store fixes to gamma from commits `02cd0e0` and `5775eca` on 2026-05-25 with `./scripts/deploy-gcp.sh --gamma --with-frontend`. This fixes party-hub **Host game** / **Join to play** / **Join to watch** re-entry by minting fresh launch tokens from the party hub token, returns flat safe content metadata for Revelry compatibility, and routes host-app catalog policy reads through the active Supabase adapter.
- Revelry party hub active-session recovery: LocalPlay must reconcile persisted `games_gamma_game_sessions` rows with the current runtime room map after any gamma deploy/restart. If a session remains `lobby` / `active` / `paused` but its room no longer exists, LocalPlay marks it `expired` with `closed_reason = runtime_unavailable`, rejects new organizer/player launch tokens for it, hides it from the hub's active game card, and allows the host to start a fresh game without replacement confirmation.
- Applied the rendered gamma Supabase schema again on 2026-05-25; `games_gamma_host_app_catalog_flags` now exists. Seeded Revelry gamma catalog policy rows for `quiz`, `wmlt`, and `drawing` with `enabled = true` and `status = gamma`. `GET /catalog?host_app=revelry` now returns those rows with `status: "gamma"` instead of relying on the non-production permissive fallback.
- Post-deploy gamma smoke on 2026-05-25 passed for `/health`, `/providers`, `/media/status`, `/config.json`, SPA root, anonymous auth rejection, invalid sign-in rejection, iOS checkout guard, and `GET /catalog?host_app=revelry`; generation/idempotency checks were intentionally skipped.
- On 2026-05-25, gamma media upload testing found `403 bad_signature` from the IONOS LocalPlay upload handler because `games-backend-gamma` had a `MEDIA_UPLOAD_SECRET` that did not match `~/revelryapp/media/apps/localplay/.upload_secret`. Updated `/home/revelry-games/app/.env.gamma` to match the IONOS secret, redeployed gamma with `./scripts/deploy-gcp.sh --gamma --with-frontend`, and verified a signed PNG upload returned `200`.
- On 2026-05-25, deployed the Revelry authoring editor remount fix to gamma so saving a new party-scoped quiz no longer clears the custom quiz editor after `currentContentId` is assigned.
- Post-fix gamma Playwright passed on 2026-05-25: `npm run test:e2e:gamma` returned `2 passed`; `REVELRY_GAMMA_PARTY_GAMES_URL_FILE=... npm run test:e2e:gamma:revelry` returned `2 passed`, covering Drawing save/start/re-entry plus custom Quiz image upload/save/payload verification.
- Deployed gamma-only extended party-games token TTL support on 2026-05-25 with `./scripts/deploy-gcp.sh --gamma --with-frontend`. The Revelry gamma mint script can now write a 30-day disposable-party URL to `gamma_party_games_url.txt`; production rejects custom party-games token TTLs. Verified the minted token expiry was 30 days, then reran Playwright: `REVELRY_GAMMA_PARTY_GAMES_URL_FILE=... npm run test:e2e:gamma:revelry` returned `2 passed`, and `npm run test:e2e:gamma` returned `2 passed`.
- On 2026-05-26, added gamma callback URL management to the deploy bootstrap, set `/home/revelry-games/app/.env.gamma` to call `https://api-gamma.revelryapp.me/api/games/localplay/callback`, and redeployed gamma with `./scripts/deploy-gcp.sh --gamma --with-frontend`.
- On 2026-05-26, `REVELRY_GAMMA_PARTY_GAMES_URL_FILE=... npm run test:e2e:gamma:revelry` returned `3 passed`, now covering Drawing save/start/re-entry, a complete Revelry-started Quiz through LocalPlay WebSockets to podium, Revelry callback/session mirror, Revelry session-results polling with final player score, workspace cleanup after completion, and custom Quiz image upload/save/payload verification. `npm run test:e2e:gamma` returned `2 passed`.
- On 2026-06-01, applied the gamma-only Housie schema update: `games_gamma_generated_content_content_type_check` now allows `quiz`, `mlt`, `drawing`, and `housie`. Production `games_generated_content_content_type_check` remains unchanged until Housie is promoted.
- On 2026-06-24, applied the gamma Random Chit authoring schema update: `games_gamma_generated_content_content_type_check` now allows `quiz`, `mlt`, `drawing`, `housie`, and `chit_pull`. Production SQL is updated in the repo but the production constraint was not applied in this gamma pass.
- On 2026-06-01, deployed Housie Revelry gamma enablement. Live gamma catalog returns `housie` for `host_app=revelry` with `status: "gamma"`, `can_create_content: true`, `can_quick_start: true`, and `supports_ai_generation: false`; gamma Housie content save returned `question_count/item_count = 6`.
- On 2026-06-01, deployed the stale lobby roster fix. When `ROOM_RESET` or another lobby broadcast discovers dead player sockets, LocalPlay removes them and emits an updated roster so the organizer player count matches server-side minimum-player checks.
- On 2026-06-01, broadened the socket lifecycle fix across game families. Per-player runtime syncs and drawing broadcasts now publish corrected rosters after removing dead player sockets; min-player-gated starts prune dead sockets before checking player counts; superseded Revelry sessions close their old runtime rooms and cannot later be marked complete by stale callbacks. Housie saved setups are included in the Revelry party workspace `prepared_content` list.
- Basic Revelry gamma end-to-end testing has worked for catalog, session creation, organizer/player/spectator launch, Drawing setup/start/re-entry, custom Quiz image upload/save, completion, result polling, callback delivery, and workspace active-session cleanup. Before production promotion, still repeat from Revelry gamma for native app/universal-link return flows and any production-only host-app chrome checks.
- Full spec: `SPEC-REVELRY-INTEGRATION.md`

### Production readiness status

- Deployed the current LocalPlay bridge/backend-served SPA to production on 2026-06-02 with `./scripts/deploy-gcp.sh --with-frontend`, promoting the gamma-tested Revelry catalog picker, Musical Chairs quick-start bridge, hosted music loops, and recent UX/gameplay fixes.
- Production env includes `REVELRY_INTEGRATION_SECRET`, `PUBLIC_BASE_URL=https://gamesapi.revelryapp.me`, `REVELRY_CALLBACK_URL=https://api.revelryapp.me/api/games/localplay/callback`, and `REVELRY_CALLBACK_SECRET=`. Keep `REVELRY_CALLBACK_SECRET` empty unless doing a deliberate rotation/compatibility window.
- Production env keeps AI image generation disabled with `IMAGE_GENERATION_PROVIDER=none`.
- Production media uploads are enabled through IONOS with `MEDIA_PUBLIC_BASE_URL=https://media.revelryapp.me/apps/localplay`, `MEDIA_UPLOAD_URL=https://media.revelryapp.me/apps/localplay/upload.php`, `MEDIA_PATH_PREFIX=prod`, and a `MEDIA_UPLOAD_SECRET` matching `~/revelryapp/media/apps/localplay/.upload_secret`.
- Applied the targeted production Supabase parity migration on 2026-05-25: `games_quiz_packs`, `games_quiz_questions`, `games_media_assets`, `games_game_sessions`, and the refreshed `games_generated_content_content_type_check` allowing `quiz`, `mlt`, and `drawing`.
- Post-migration consistency check scoped to LocalPlay tables/RPCs (`games_` vs `games_gamma_`) returned no diffs across tables, columns/defaults, constraints, indexes, RLS, policies, and RPC signatures as of 2026-05-25. The shared Supabase project also contains unrelated `pp_*` tables; those are not LocalPlay/Revelry bridge migrations and should not be modified by LocalPlay deploy work.
- Applied the rendered production Supabase schema on 2026-06-02 to create `games_host_app_catalog_flags`, then seeded production Revelry policy rows with `status = "live"` for `quiz`, `wmlt`, `drawing`, and quick-start-only `musical_chairs`. Housie remains unpromoted in production until the production generated-content constraint is explicitly expanded to include `housie` and a prod Housie save/start smoke passes.
- Standalone production LocalPlay enables the implemented standalone game catalog, including Bingo and Baby Bingo. `ENABLE_BINGO=false` and `VITE_ENABLE_BINGO=false` are kill switches only; do not use them as the default prod posture. Revelry exposure remains controlled separately through static host-app support plus `games_host_app_catalog_flags`.
- Production smoke passed on 2026-06-02 for `/health`, `GET /catalog?host_app=revelry` returning live games, `/media/status`, and the backend-served frontend Playwright smoke on desktop/mobile.
- `/media/status` should report `upload_available=true`, `generation_available=false`, and `storage_backend=ionos` in production. This is the intended state for custom quiz photo uploads with AI image generation disabled.
- Added the same shared secret to GCP Secret Manager secret `revelry-prod-localplay-integration-secret` on 2026-05-25; version `1` is enabled. Do not print or copy this value into docs.
- Remaining production validation should smoke a real Revelry prod party Games tab, LocalPlay launch, and callback/result handling with the production `LOCALPLAY_INTEGRATION_SECRET`.

### Enabling Revelry games

Revelry game availability is controlled by LocalPlay's host-app catalog policy. Revelry should render the catalog returned by LocalPlay instead of hardcoding enabled games.

Important distinction:

- A game that does not exist in LocalPlay yet still needs one LocalPlay implementation release: static catalog metadata, runtime/setup/content contracts, host-app-safe routes, callbacks/results, and tests.
- A game that is already implemented and bridge-ready should be exposed, hidden, allowlisted, or killed through host-app catalog policy, without a Revelry release and ideally without another LocalPlay deploy.
- Remote policy cannot turn on capabilities that the static LocalPlay catalog does not support. The static catalog is the safety ceiling; policy is the rollout/control layer.

Policy rows live in the prefixed Supabase table `{TABLE_PREFIX}host_app_catalog_flags`, for example `games_gamma_host_app_catalog_flags` in gamma and `games_host_app_catalog_flags` in production. Production fails closed when policy is missing, so seed production rows before expecting games to appear in `GET /catalog?host_app=revelry`.

Use the admin API when `ADMIN_API_KEY` is configured. Do not paste real keys into docs, shell history, or git:

```bash
# List current gamma Revelry flags.
curl -sS -H "Authorization: Bearer ${ADMIN_API_KEY}" \
  "https://gamesapi-gamma.revelryapp.me/admin/host-app-catalog-flags?environment=gamma&host_app=revelry"

# Enable an already bridge-ready game for gamma.
curl -sS -X POST \
  -H "Authorization: Bearer ${ADMIN_API_KEY}" \
  -H "Content-Type: application/json" \
  https://gamesapi-gamma.revelryapp.me/admin/host-app-catalog-flags \
  -d '{
    "environment": "gamma",
    "host_app": "revelry",
    "game_id": "drawing",
    "enabled": true,
    "status": "gamma",
    "capability_overrides": {
      "can_create_content": true,
      "can_edit_content": true,
      "can_quick_start": false,
      "supports_ai_generation": true,
      "supports_images": false,
      "payments_enabled": false,
      "embedded_authoring_supported": true
    },
    "notes": "Gamma rollout",
    "updated_by": "deploy-operator"
  }'

# Kill-switch a game after the 30-60 second policy cache expires.
curl -sS -X POST \
  -H "Authorization: Bearer ${ADMIN_API_KEY}" \
  -H "Content-Type: application/json" \
  https://gamesapi-gamma.revelryapp.me/admin/host-app-catalog-flags \
  -d '{
    "environment": "gamma",
    "host_app": "revelry",
    "game_id": "drawing",
    "enabled": false,
    "status": "disabled",
    "notes": "Disabled by operator",
    "updated_by": "deploy-operator"
  }'
```

After changing policy:

1. Verify `GET /catalog?host_app=revelry` shows or hides the expected game after the policy cache expires.
2. Run `npm run test:e2e:gamma` for deployed gamma frontend health.
3. For a game exposed to Revelry gamma, run the repeatable `Revelry gamma embedded E2E` below with a fresh party games URL.
4. Promote to production only after the game is implemented, bridge-ready, gamma-tested, and seeded in the production policy table with `status = "live"`.

---

## Media Uploads (IONOS)

LocalPlay image files should be stored on IONOS, not Supabase Storage and not the GCP VM filesystem. Supabase remains the metadata store for media asset rows and quiz-pack question references.

This should follow the Revelry media-upload pattern:

1. Frontend calls the LocalPlay backend for a signed upload target, e.g. `POST /media/upload-url`.
2. Backend validates wallet/content ownership and generates:
   - `asset_id`
   - relative IONOS path
   - short expiry
   - HMAC token using `MEDIA_UPLOAD_SECRET`
3. Frontend uploads `multipart/form-data` directly to the IONOS PHP handler.
4. PHP validates CORS, expiry, HMAC, path prefix, extension, MIME type, and upload status.
5. PHP writes the image under the LocalPlay media directory.
6. Frontend calls a finalize endpoint, e.g. `POST /media/{asset_id}/finalize`, so backend metadata becomes `ready`.
7. Runtime quiz questions use `image_asset_id`, `image_url`, and `image_alt`; `image_url` may be `/media/{asset_id}` or a direct `media.revelryapp.me` URL.

IONOS is not a product-facing authoring concept. Quiz authors should see upload, preview, replace, remove, and alt text controls only; IONOS paths, CDN URLs, `/media` paths, asset ids, and storage backend names are internal metadata/debugging details.

The owner/context path segment must be sanitized before signing. Host-app wallets can contain unsafe characters, for example `revelry:party:{party_id}`; signed paths should use a path-safe segment such as `revelry_party_{party_id}`. Raw `:` characters are rejected by the IONOS PHP handler as `invalid_path`.

Recommended public URL and server layout:

```text
Public base URL:
https://media.revelryapp.me/apps/localplay/

IONOS server:
~/revelryapp/media/apps/localplay/
  upload.php
  delete.php
  .htaccess
  .upload_secret
  prod/
    uploads/{wallet_prefix}/YYYY/MM/DD/{asset_id}.webp
    generated/{asset_id}.webp
    thumbs/{asset_id}.webp
  gamma/
    uploads/{wallet_prefix}/YYYY/MM/DD/{asset_id}.webp
    generated/{asset_id}.webp
    thumbs/{asset_id}.webp
```

Repo source:

```text
ionos/media/upload.php
ionos/media/delete.php   # future
ionos/media/.htaccess    # future
```

Deploy PHP handlers only from repo source:

```bash
scp ionos/media/upload.php u69414981@home420463025.1and1-data.host:~/revelryapp/media/apps/localplay/upload.php
```

The IONOS secret file must match backend env:

```text
IONOS:   ~/revelryapp/media/apps/localplay/.upload_secret
Backend: MEDIA_UPLOAD_SECRET
```

Required backend env for uploads:

```env
MEDIA_PUBLIC_BASE_URL=https://media.revelryapp.me/apps/localplay
MEDIA_UPLOAD_URL=https://media.revelryapp.me/apps/localplay/upload.php
MEDIA_UPLOAD_SECRET=<same value as .upload_secret>
MEDIA_PATH_PREFIX=gamma   # gamma; use prod in production
MEDIA_ALLOWED_MIME_TYPES=image/png,image/jpeg,image/webp
MEDIA_UPLOAD_TOKEN_TTL_SECONDS=900
```

CORS:

- `upload.php` should allow `POST, OPTIONS` from:
  - `https://games.revelryapp.me`
  - `https://gamesapi.revelryapp.me`
  - `https://gamesapi-gamma.revelryapp.me`
  - local dev origins such as `http://localhost:9200` and `http://127.0.0.1:9200`
  - Capacitor origins if native upload is enabled
- `.htaccess` should allow reads for image files across web/PWA/native surfaces. Like Revelry, this can be `Access-Control-Allow-Origin: *` because the files are public CDN-style bearer URLs protected by unguessable UUID paths, not auth cookies.

Path validation:

- PHP handlers must reject `..`, absolute paths, and unknown prefixes.
- LocalPlay paths should start with `prod/` or `gamma/`.
- Backend-generated paths must use sanitized owner/context segments.
- Backend-generated paths should use UUID-like asset names, never user-provided filenames.
- Delete should be best-effort: signed `delete.php` removes the IONOS file, while backend metadata is soft-deleted.

Operational notes:

- Deploying or editing live IONOS PHP files should be treated as a production operation.
- Check disk usage before enabling broad uploads:

```bash
ssh u69414981@home420463025.1and1-data.host "du -sh ~/revelryapp/media/apps/localplay/"
```

---

## Quick Reference Commands

### Full LocalPlay redeploy

```bash
# From project root:

# Production backend + bundled SPA fallback
./scripts/deploy-gcp.sh --with-frontend

# Gamma backend + bundled SPA
./scripts/deploy-gcp.sh --gamma --with-frontend

# Public IONOS frontend
cd frontend
VITE_BASE_PATH=/ VITE_API_URL=https://gamesapi.revelryapp.me VITE_WEB_URL=https://games.revelryapp.me/ VITE_CAST_APP_ID=1BC9ACD8 npx vite build
ssh u69414981@home420463025.1and1-data.host "mkdir -p ~/revelryapp/games"
scp -r dist/* u69414981@home420463025.1and1-data.host:~/revelryapp/games/
rsync -avz dist/.htaccess u69414981@home420463025.1and1-data.host:~/revelryapp/games/.htaccess
```

### Public IONOS frontend only

```bash
cd frontend
VITE_BASE_PATH=/ VITE_API_URL=https://gamesapi.revelryapp.me VITE_WEB_URL=https://games.revelryapp.me/ VITE_CAST_APP_ID=1BC9ACD8 npx vite build
ssh u69414981@home420463025.1and1-data.host "mkdir -p ~/revelryapp/games"
scp -r dist/* u69414981@home420463025.1and1-data.host:~/revelryapp/games/
rsync -avz dist/.htaccess u69414981@home420463025.1and1-data.host:~/revelryapp/games/.htaccess
```

### Backend containers only

```bash
# Production
./scripts/deploy-gcp.sh --with-frontend

# Gamma
./scripts/deploy-gcp.sh --gamma --with-frontend
```

### View backend logs
```bash
gcloud compute ssh revelry-backend --project=revelryapp --zone=us-central1-a --command \
  'docker logs games-backend --tail 50 -f'

gcloud compute ssh revelry-backend --project=revelryapp --zone=us-central1-a --command \
  'docker logs games-backend-gamma --tail 50 -f'
```

### Check if backends are healthy

```bash
curl -sS -i https://gamesapi.revelryapp.me/health
curl -sS -i https://gamesapi-gamma.revelryapp.me/health
```

### Test runbook

Use this section as the repeatable deploy/regression checklist. Pick the narrowest test that matches the change, then run the broader smoke before promoting or after touching deploy/env/media/auth paths.

#### Local backend tests

Run focused backend tests while developing integration or storage changes:

```bash
.venv/bin/python -m pytest backend/tests/test_revelry_integration.py
.venv/bin/python -m pytest backend/tests/test_host_app_catalog_policy.py backend/tests/test_revelry_integration.py
```

Run the broader backend suite when touching shared API/session/storage behavior:

```bash
make test
```

#### Local frontend tests

Run unit/component tests while developing frontend behavior:

```bash
cd frontend
npm test -- --run src/__tests__/hostAppMode.test.tsx
npm run build
```

Run local Playwright against the Vite dev server before deploying frontend-heavy changes, especially game-screen, theme, authoring, or layout changes:

```bash
make test-frontend-e2e
```

This runs Playwright against local Vite. The current coverage includes the DrawingGame organizer prompt screen and quiz-variant prompt screens on desktop and mobile, verifies segmented controls stay aligned, checks there is no horizontal page overflow, catches overlap with fixed menu/spark controls, and verifies variant generation sends the expected `mode`.

If an intentional visual change updates snapshots, refresh them from `frontend/`:

```bash
npm run test:e2e -- --update-snapshots
```

#### Remote backend smoke

Run these after prod/gamma deploys and after auth/provider/DNS/backend env changes:

```bash
# Production: health, provider/config, SPA root, auth guards, iOS checkout guard,
# live generation, idempotent retry, and token balance no-double-charge check.
make test-remote-prod

# Gamma equivalent.
make test-remote-gamma

# Lower-impact variant when you do not want to spend a live LLM call:
.venv/bin/python scripts/smoke-remote.py --base-url https://gamesapi.revelryapp.me --skip-generate
```

#### Gamma Playwright smoke

Run this after deploying gamma frontend/backend changes:

```bash
cd frontend
npm run test:e2e:gamma
```

This points Playwright at `https://gamesapi-gamma.revelryapp.me`, verifies the standalone catalog renders on desktop and mobile, checks `/media/status`, and fails on browser console/page errors.

#### Pre-prod live game regression

Run this before major production deployments that touch room creation, WebSockets, game runtime logic, or shared player/host/spectator surfaces:

```bash
cd frontend
PREPROD_LIVE=1 PLAYWRIGHT_BASE_URL=https://gamesapi-gamma.revelryapp.me npm run test:e2e:preprod-live
```

This is intentionally heavier than the gamma smoke: it creates disposable deterministic content and rooms, opens multiple real browser player contexts, starts each covered game family, performs one meaningful action or turn handoff, and checks host/player UI state. Run it with one worker and treat failures as production-blocking until triaged. Current coverage includes Quiz runtime, Most Likely To, Housie, Bingo/Baby Bingo, Musical Chairs, Bluff, Two Truths and a Lie, Story Chain, Common Ground, Who Am I, and Chit Pull. Drawing is a tracked skipped case until `/drawing/import` exists; do not make this pre-prod suite depend on live AI generation.

For a representative mobile screenshot audit of live states, run:

```bash
cd frontend
PREPROD_UX_AUDIT=1 PLAYWRIGHT_BASE_URL=https://gamesapi-gamma.revelryapp.me npm run test:e2e:preprod-ux
```

Screenshots default to `/private/tmp/localplay-preprod-ux-audit`; override with `PREPROD_UX_AUDIT_DIR` when saving artifacts for review.

#### Revelry gamma embedded E2E

This is the repeatable gamma-only test for the LocalPlay/Revelry embedded party hub. It is intentionally desktop-only and stateful because it mutates one disposable gamma party.

1. Mint a fresh gamma `party_games_url` for the disposable Revelry gamma party. The token must have host capabilities: `manage_games`, `author_content`, and `operate_game`. The current repeatable path uses the Revelry repo script and the gamma LocalPlay/Revelry integration secret:

```bash
export LOCALPLAY_GAMMA_INTEGRATION_SECRET="$(gcloud secrets versions access latest --project revelryapp --secret revelry-gamma-localplay-integration-secret)"
.venv/bin/python /Users/Avi/Desktop/dev/antigravity/revelryapp/scripts/mint-localplay-gamma-url.py \
  --ttl-days 0.05 \
  --output ./gamma_party_games_url.txt >/dev/null
```

The script is gamma-only and writes the full URL to `gamma_party_games_url.txt`, which must stay ignored. Do not print the URL or token in chat, logs, or committed files. Mint fresh before each run; a short TTL such as `0.05` days, about 72 minutes, is enough for normal E2E. LocalPlay honors the script's `ttl_seconds` request outside production only, capped at 30 days; production rejects custom party-games token TTLs. Use a longer gamma-only TTL, up to 30 days, only while actively debugging across sessions.

2. Verify only the shape/expiry, not the token:

```bash
.venv/bin/python -c "import base64,json,datetime,urllib.parse,pathlib,time; url=pathlib.Path('gamma_party_games_url.txt').read_text().strip(); print('has_gamma_url=', url.startswith('https://gamesapi-gamma.revelryapp.me/integrations/revelry/games?party_games_token=')); tok=urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get('party_games_token',[''])[0]; payload=tok.split('.')[1]; payload += '='*((4-len(payload)%4)%4); data=json.loads(base64.urlsafe_b64decode(payload)); exp=data.get('exp'); print('exp=', datetime.datetime.fromtimestamp(exp, datetime.timezone.utc).isoformat() if exp else data.get('expires_at')); print('valid_now=', bool(exp and exp > time.time()))"
```

3. Run:

```bash
cd frontend
REVELRY_GAMMA_PARTY_GAMES_URL_FILE=../gamma_party_games_url.txt npm run test:e2e:gamma:revelry
```

For a larger pre-production Revelry check, run the host-app matrix after the standard gamma flow:

```bash
cd frontend
PREPROD_REVELRY=1 REVELRY_GAMMA_PARTY_GAMES_URL_FILE=../gamma_party_games_url.txt npm run test:e2e:preprod-revelry
```

The matrix verifies the embedded Revelry Games hub catalog/search UI, then starts every launchable game returned by the live Revelry catalog. It covers deterministic party-scoped content saves for Quiz, Most Likely To, Drawing, Housie, and Random Chit, and quick-start launch for all catalog games that expose `can_quick_start=true` without `can_create_content`. It also mints organizer/player/spectator launch tokens for each session. If a newly exposed Revelry game requires saved content but is missing from the matrix fixture set, the test fails and the harness must be updated before rollout.

The test verifies:

- LocalPlay embedded party hub resolves the Revelry party token.
- Drawing setup saves through the live workspace API.
- Drawing start/replacement creates or replaces the active room.
- Organizer/player/spectator launch-token minting works.
- Re-entering the hub shows the active game.
- **Host game** opens with a fresh organizer token, avoiding stale-token failures.
- Custom Quiz authoring opens from the hub.
- Custom Quiz question image upload works through signed IONOS media upload.
- Saved quiz payload contains the media-backed image URL and alt text.
- A small quiz can be started from the Revelry party workspace, driven through LocalPlay WebSockets to podium, and mirrored back to Revelry as a completed session.
- Revelry's sessions and session-results endpoints return the final player score/feed-card summary, and the workspace no longer reports the completed LocalPlay room as active.

If the test shows `Invalid or expired party games token`, mint a fresh gamma URL and rerun. If image upload fails with `403 bad_signature`, verify `games-backend-gamma` `MEDIA_UPLOAD_SECRET` matches `~/revelryapp/media/apps/localplay/.upload_secret` on IONOS, then redeploy gamma. If completion succeeds in LocalPlay but Revelry never shows a completed session, verify gamma has `REVELRY_CALLBACK_URL=https://api-gamma.revelryapp.me/api/games/localplay/callback` and redeploy gamma.

Do not run this against production. For production, create a separate explicitly approved smoke plan using a disposable prod party.

#### Manual auth/payment checks

Manual provider sign-in smoke is still required for the browser popup flows:

- Google: open the SPA, sign in, verify the menu shows **Signed in**, account/email prefix, and **Sign Out**.
- Apple: same as Google; verify Apple returns to the same host.
- IONOS production frontend: repeat on `https://games.revelryapp.me/`.
- Backend-served prod/gamma: repeat on `https://gamesapi.revelryapp.me` and `https://gamesapi-gamma.revelryapp.me` when those origins have changed.

Stripe smoke should stay manual/test-mode unless explicitly doing a paid production checkout:

- Gamma checkout must use Stripe test keys.
- Production checkout should only be tested with an intentional real purchase/refund workflow.

Manual curl spot checks:

```bash
curl -s https://gamesapi.revelryapp.me/health
curl -s https://gamesapi-gamma.revelryapp.me/health
curl -s https://gamesapi.revelryapp.me/providers | python3 -m json.tool
curl -s https://gamesapi-gamma.revelryapp.me/providers | python3 -m json.tool
curl -s https://gamesapi.revelryapp.me/media/status | python3 -m json.tool
curl -s https://gamesapi-gamma.revelryapp.me/media/status | python3 -m json.tool
```

`/media/status` is the Phase 0 image-platform smoke check. It should return
JSON, not `index.html`; that confirms `/media` is still protected from the
backend-served SPA fallback.

### Check IONOS disk usage
```bash
ssh u69414981@home420463025.1and1-data.host "du -sh ~/revelryapp/games/"
```

---

## GCP Firewall (Access Restriction)

The backend is locked down so only your home IP can reach it. Anyone else gets a connection timeout.

**Current rules**: `allow-http` and `allow-https` are restricted to your home IPv4.
**SSH is unaffected** — `gcloud compute ssh` always works regardless of these rules.

### Check current rules
```bash
gcloud compute firewall-rules list --project=revelryapp \
  --format="table(name,allowed,sourceRanges)" \
  --filter="name:(allow-http OR allow-https)"
```

### Update after IP change

If the game stops working, your ISP probably changed your IP.

```bash
# Get your new IP
curl -s https://ifconfig.me

# Update both rules (replace NEW_IP with your actual IP)
gcloud compute firewall-rules update allow-http --project=revelryapp --source-ranges="NEW_IP/32"
gcloud compute firewall-rules update allow-https --project=revelryapp --source-ranges="NEW_IP/32"
```

### Open to everyone (remove restriction)
```bash
gcloud compute firewall-rules update allow-http --project=revelryapp --source-ranges="0.0.0.0/0"
gcloud compute firewall-rules update allow-https --project=revelryapp --source-ranges="0.0.0.0/0"
```

---

## GCP Billing Cap ($10/month hard limit)

A Cloud Function automatically **disables billing** if monthly costs reach $10.

**How it works:**
1. GCP Budget "Revelry monthly cap" sends alerts to Pub/Sub topic `billing-alerts`
2. Cloud Function `stop-billing` listens on that topic
3. When cost hits 100% of $10, the function unlinks the billing account from the project
4. All paid resources (VM, network) stop — no more charges

**What happens if it triggers:** The VM shuts down and the backend goes offline. The frontend on IONOS is unaffected (separate hosting). To restore, re-link billing in the GCP Console.

### Check current budget status
```bash
gcloud billing budgets describe \
  "billingAccounts/012366-DC2219-426FD9/budgets/3971e00b-3ca2-4b99-a702-68ad9383d1c0" \
  --format="yaml(displayName,amount,thresholdRules)"
```

### Check Cloud Function logs
```bash
gcloud functions logs read stop-billing --project=revelryapp --region=us-central1 --limit=20
```

### Re-enable billing after it triggers
1. Go to https://console.cloud.google.com/billing/projects?project=revelryapp
2. Click "Link a billing account" next to the revelryapp project
3. Select "Default Billing Amount"
4. Restart the VM: `gcloud compute instances start revelry-backend --project=revelryapp --zone=us-central1-a`

### Note on free tier
The e2-micro VM + 30GB disk in us-central1 is covered by GCP's Always Free tier, so normal usage should cost $0/month. This cap is a safety net for unexpected charges.

---

## Troubleshooting

| Problem | Check |
|---------|-------|
| Frontend 404 on refresh | `.htaccess` missing or wrong `RewriteBase` |
| WebSocket fails to connect | Nginx config missing `Upgrade`/`Connection` headers |
| CORS errors | `ALLOWED_ORIGINS` in backend `.env` doesn't include frontend domain |
| Docker won't start | `docker logs games-backend --tail 80` or `docker logs games-backend-gamma --tail 80` |
| SSL cert expired | `sudo certbot renew && sudo systemctl reload nginx` |
| Old JS bundles cached | Clear `assets/` dir before deploying, hard-refresh browser |
| API suddenly unreachable | Home IP probably changed — update firewall rules (see section above) |
| VM stopped unexpectedly | Billing cap may have triggered — re-link billing (see billing cap section) |
| `gamesapi.revelryapp.me` returns 502 | Check `games-backend` is running and bound to `127.0.0.1:8000` |
| `gamesapi-gamma.revelryapp.me` returns 502 | Check `games-backend-gamma` is running and bound to `127.0.0.1:8004` |
| Container logs show `exec format error` | Rebuild through `scripts/deploy-gcp.sh`; images must be `linux/amd64` for the VM |
| SPA route returns API JSON unexpectedly | Confirm the path is not under a protected API prefix |
| Generation fails with Gemini `404 Not Found` | Check VM `GEMINI_MODEL`, `GEMINI_PREMIUM_MODEL`, `REMOTE_CONFIG_URL`, and `frontend/public/config.json`; all model settings should be `gemini-2.5-flash-lite` |
