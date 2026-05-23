# Revelry Quiz — Production Deployment Guide

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

The public production game is still expected to run at `https://games.revelryapp.me/quiz/` from IONOS. The backend-served SPA gives us a same-origin deployment path for gamma, previews, and emergency/prod fallback at the API domains.

## Production URLs

| Component | URL |
|-----------|-----|
| Frontend  | https://games.revelryapp.me/quiz/ |
| Backend API + SPA fallback | https://gamesapi.revelryapp.me |
| Gamma full stack | https://gamesapi-gamma.revelryapp.me |
| Spectator/TV | https://games.revelryapp.me/quiz/spectator |
| Player join  | https://games.revelryapp.me/quiz/join |
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

## IONOS Directory Structure

```
~/revelryapp/
  site/          → revelryapp.me (marketing website)
  app/           → app.revelryapp.me (platform frontend, future)
  games/         → games.revelryapp.me
    quiz/        → games.revelryapp.me/quiz (quiz game)
  media/         → media.revelryapp.me
    apps/
      localplay/ → LocalPlay uploaded/generated game images
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
REVELRY_SESSION_LOBBY_TTL_SECONDS=14400
REVELRY_SESSION_IDLE_TTL_SECONDS=7200
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
REVELRY_SESSION_LOBBY_TTL_SECONDS=14400
REVELRY_SESSION_IDLE_TTL_SECONDS=7200
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
| `https://games.revelryapp.me/quiz/` | Configured; expected to work with the same web client | Verified |

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
VITE_BASE_PATH=/quiz/ VITE_API_URL=https://gamesapi.revelryapp.me VITE_CAST_APP_ID=1BC9ACD8 npx vite build
ssh u69414981@home420463025.1and1-data.host "rm -rf ~/revelryapp/games/quiz/assets"
scp -r dist/* u69414981@home420463025.1and1-data.host:~/revelryapp/games/quiz/
```

---

## Frontend Deployment

### Prerequisites
- Node.js installed locally
- SSH key configured for IONOS

### Step 1: Build the frontend

```bash
cd frontend

# Production build with subpath and backend URL
VITE_BASE_PATH=/quiz/ VITE_API_URL=https://gamesapi.revelryapp.me VITE_CAST_APP_ID=1BC9ACD8 npx vite build
```

This produces `frontend/dist/` with all static assets.

### Step 2: Clean old assets on IONOS

```bash
ssh u69414981@home420463025.1and1-data.host "rm -rf ~/revelryapp/games/quiz/assets"
```

Old JS/CSS bundles have hashed filenames that accumulate. Always clean before deploying.

### Step 3: Upload to IONOS

```bash
scp -r frontend/dist/* u69414981@home420463025.1and1-data.host:~/revelryapp/games/quiz/
```

### Step 4: Verify

Open https://games.revelryapp.me/quiz/ in a browser. Check the browser console for errors.

### SPA Routing

An `.htaccess` file at `~/revelryapp/games/quiz/.htaccess` handles client-side routing:

```apache
RewriteEngine On
RewriteBase /quiz/
RewriteCond %{REQUEST_FILENAME} !-f
RewriteCond %{REQUEST_FILENAME} !-d
RewriteRule . /quiz/index.html [L]
```

This file is already deployed. Only re-upload it if the base path changes.

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

Protected API prefixes include `/system`, `/providers`, `/quiz`, `/room`, `/ws`, `/mlt`, `/history`, `/auth`, `/checkout`, `/webhook`, `/tokens`, `/entitlements`, `/purchases`, `/admin`, `/health`, and `/sd`.

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

- `/etc/nginx/sites-available/revelry-gamesapi` — `gamesapi.revelryapp.me` (quiz game backend)
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
REMOTE_CONFIG_URL=https://games.revelryapp.me/quiz/config.json

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
```

AI model gotcha: `backend/config.py` defaults to `gemini-2.5-flash-lite`, but deployed env vars and remote `config.json` override code defaults. If generation fails with Gemini `404 Not Found`, check `GEMINI_MODEL`, `GEMINI_PREMIUM_MODEL`, `REMOTE_CONFIG_URL`, and `ai_models` in `frontend/public/config.json`. Free and premium generation should both use `gemini-2.5-flash-lite`.

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
{prefix}game_history
{prefix}rejections
```

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
- Production smoke after cutover verified `/health`, `/providers`, `/config.json`, live quiz generation, Supabase wallet/request-log writes, and retry idempotency with one `spend_generate` transaction.

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
VITE_BASE_PATH=/quiz/ VITE_API_URL=https://gamesapi.revelryapp.me VITE_CAST_APP_ID=1BC9ACD8 npx vite build
ssh u69414981@home420463025.1and1-data.host "rm -rf ~/revelryapp/games/quiz/assets"
scp -r dist/* u69414981@home420463025.1and1-data.host:~/revelryapp/games/quiz/
```

### Public IONOS frontend only

```bash
cd frontend
VITE_BASE_PATH=/quiz/ VITE_API_URL=https://gamesapi.revelryapp.me VITE_CAST_APP_ID=1BC9ACD8 npx vite build
ssh u69414981@home420463025.1and1-data.host "rm -rf ~/revelryapp/games/quiz/assets"
scp -r dist/* u69414981@home420463025.1and1-data.host:~/revelryapp/games/quiz/
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

### Remote smoke tests

Run these after prod/gamma deploys and after auth/provider/DNS changes:

```bash
# Production: health, provider/config, SPA root, auth guards, iOS checkout guard,
# live generation, idempotent retry, and token balance no-double-charge check.
make test-remote-prod

# Gamma equivalent.
make test-remote-gamma

# Lower-impact variant when you do not want to spend a live LLM call:
.venv/bin/python scripts/smoke-remote.py --base-url https://gamesapi.revelryapp.me --skip-generate
```

Manual provider sign-in smoke is still required for the browser popup flows:

- Google: open the SPA, sign in, verify the menu shows **Signed in**, account/email prefix, and **Sign Out**.
- Apple: same as Google; verify Apple returns to the same host.
- IONOS production frontend: repeat on `https://games.revelryapp.me/quiz/`.
- Backend-served prod/gamma: repeat on `https://gamesapi.revelryapp.me` and `https://gamesapi-gamma.revelryapp.me` when those origins have changed.

Stripe smoke should stay manual/test-mode unless explicitly doing a paid production checkout:

- Gamma checkout must use Stripe test keys.
- Production checkout should only be tested with an intentional real purchase/refund workflow.

### Frontend UX smoke tests

Run the local browser UX suite before deploying frontend-heavy changes, especially game-screen or theme changes:

```bash
make test-frontend-e2e
```

This runs Playwright against the local Vite dev server. The current coverage includes the DrawingGame organizer prompt screen and quiz-variant prompt screens on desktop and mobile, verifies segmented controls stay aligned, checks there is no horizontal page overflow, catches overlap with the fixed hamburger/spark controls, and verifies variant generation sends the expected `mode`. If an intentional visual change updates the page shape, refresh the snapshots from `frontend/`:

```bash
npm run test:e2e -- --update-snapshots
```

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
ssh u69414981@home420463025.1and1-data.host "du -sh ~/revelryapp/games/quiz/"
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
