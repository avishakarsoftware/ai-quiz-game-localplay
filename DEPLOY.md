# Revelry Quiz — Production Deployment Guide

## Architecture Overview

```
Users → revelryapp.me (IONOS CDN) → static frontend
     → api.revelryapp.me (GCP VM)  → FastAPI backend + WebSockets
```

- **Frontend**: Static React/Vite build hosted on IONOS shared hosting
- **Backend**: FastAPI in Docker on a GCP Compute Engine e2-micro VM
- **Reverse proxy**: Nginx on the VM handles HTTPS termination + WebSocket upgrade
- **SSL**: Let's Encrypt via Certbot (auto-renewing)

## Production URLs

| Component | URL |
|-----------|-----|
| Frontend  | https://revelryapp.me/standalone/quiz/ |
| Backend API | https://api.revelryapp.me |
| Spectator/TV | https://revelryapp.me/standalone/quiz/spectator |
| Player join  | https://revelryapp.me/standalone/quiz/join |
| Cast App ID  | `1BC9ACD8` |

## Credentials & Access

| Service | Access |
|---------|--------|
| IONOS SSH | `ssh u69414981@home420463025.1and1-data.host` (key: `~/.ssh/id_ed25519`) |
| GCP SSH | `gcloud compute ssh revelry-backend --project=revelryapp --zone=us-central1-a` |
| GCP VM IP | `136.115.33.75` |
| GCP Project | `revelryapp` |
| GCP Zone | `us-central1-a` |
| GCP Instance | `revelry-backend` |

---

## Frontend Deployment

### Prerequisites
- Node.js installed locally
- SSH key configured for IONOS

### Step 1: Build the frontend

```bash
cd frontend

# Production build with subpath and backend URL
VITE_BASE_PATH=/standalone/quiz/ VITE_API_URL=https://api.revelryapp.me npm run build
```

This produces `frontend/dist/` with all static assets.

### Step 2: Clean old assets on IONOS

```bash
ssh u69414981@home420463025.1and1-data.host "rm -rf ~/revelryapp/standalone/quiz/assets"
```

Old JS/CSS bundles have hashed filenames that accumulate. Always clean before deploying.

### Step 3: Upload to IONOS

```bash
scp -r frontend/dist/* u69414981@home420463025.1and1-data.host:~/revelryapp/standalone/quiz/
```

### Step 4: Verify

Open https://revelryapp.me/standalone/quiz/ in a browser. Check the browser console for errors.

### SPA Routing

An `.htaccess` file at `~/revelryapp/standalone/quiz/.htaccess` handles client-side routing:

```apache
RewriteEngine On
RewriteBase /standalone/quiz/
RewriteCond %{REQUEST_FILENAME} !-f
RewriteCond %{REQUEST_FILENAME} !-d
RewriteRule . /standalone/quiz/index.html [L]
```

This file is already deployed. Only re-upload it if the base path changes.

---

## Backend Deployment

### Prerequisites
- `gcloud` CLI installed and authenticated (`gcloud auth login`)
- Docker installed on the VM (already done)

### Step 1: Copy backend files to the VM

```bash
cd backend

# Copy all Python files, requirements, Dockerfile, and .env
gcloud compute scp *.py requirements.txt Dockerfile \
  revelry-backend:~/app/ \
  --project=revelryapp --zone=us-central1-a
```

If `.env` needs updating:
```bash
gcloud compute scp .env \
  revelry-backend:~/app/.env \
  --project=revelryapp --zone=us-central1-a
```

### Step 2: SSH into the VM

```bash
gcloud compute ssh revelry-backend --project=revelryapp --zone=us-central1-a
```

### Step 3: Rebuild and restart the Docker container

```bash
cd ~/app

# Stop and remove old container
sudo docker stop revelry-backend
sudo docker rm revelry-backend

# Rebuild image
sudo docker build -t revelry-backend .

# Start new container
sudo docker run -d \
  --name revelry-backend \
  --restart=unless-stopped \
  --env-file .env \
  -p 127.0.0.1:8000:8000 \
  revelry-backend
```

### Step 4: Verify

```bash
# Check container is running
sudo docker ps

# Check logs
sudo docker logs revelry-backend --tail 20

# Test API locally on VM
curl http://localhost:8000/providers
```

Then test from your browser: https://api.revelryapp.me/providers

### Zero-downtime shortcut (restart only, no rebuild)

If you only changed `.env` values (no code changes):
```bash
sudo docker restart revelry-backend
```

---

## Nginx Configuration

Nginx runs on the VM as a reverse proxy. Config is at `/etc/nginx/sites-available/default`.

Key sections:
- Listens on 443 (HTTPS) with Let's Encrypt certs
- Proxies all requests to `http://127.0.0.1:8000`
- WebSocket upgrade headers for `/ws/` paths
- HTTP (port 80) redirects to HTTPS

### View current config
```bash
sudo cat /etc/nginx/sites-available/default
```

### After editing Nginx config
```bash
sudo nginx -t              # test config syntax
sudo systemctl reload nginx  # apply changes
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

The production `.env` on the VM should have at minimum:

```env
# AI Providers — at least one must be configured
GEMINI_API_KEY=<your-key>
GEMINI_MODEL=gemini-2.0-flash
DEFAULT_PROVIDER=gemini

# Server
HOST=0.0.0.0
PORT=8000
ALLOWED_ORIGINS=https://revelryapp.me,https://www.revelryapp.me

# Game
ROOM_TTL_SECONDS=1800
LOG_LEVEL=INFO
```

Ollama and Stable Diffusion are NOT available on the production VM (no GPU).

---

## Quick Reference Commands

### Full redeploy (both frontend and backend)

```bash
# From project root:

# 1. Build frontend
cd frontend
VITE_BASE_PATH=/standalone/quiz/ VITE_API_URL=https://api.revelryapp.me npm run build

# 2. Deploy frontend
ssh u69414981@home420463025.1and1-data.host "rm -rf ~/revelryapp/standalone/quiz/assets"
scp -r dist/* u69414981@home420463025.1and1-data.host:~/revelryapp/standalone/quiz/

# 3. Deploy backend
cd ../backend
gcloud compute scp *.py requirements.txt Dockerfile \
  revelry-backend:~/app/ \
  --project=revelryapp --zone=us-central1-a

# 4. Rebuild on VM
gcloud compute ssh revelry-backend --project=revelryapp --zone=us-central1-a -- \
  'cd ~/app && sudo docker stop revelry-backend && sudo docker rm revelry-backend && sudo docker build -t revelry-backend . && sudo docker run -d --name revelry-backend --restart=unless-stopped --env-file .env -p 127.0.0.1:8000:8000 revelry-backend'
```

### View backend logs
```bash
gcloud compute ssh revelry-backend --project=revelryapp --zone=us-central1-a -- \
  'sudo docker logs revelry-backend --tail 50 -f'
```

### Check if backend is healthy
```bash
curl -s https://api.revelryapp.me/providers | python3 -m json.tool
```

### Check IONOS disk usage
```bash
ssh u69414981@home420463025.1and1-data.host "du -sh ~/revelryapp/standalone/quiz/"
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
| Docker won't start | `sudo docker logs revelry-backend` for error details |
| SSL cert expired | `sudo certbot renew && sudo systemctl reload nginx` |
| Old JS bundles cached | Clear `assets/` dir before deploying, hard-refresh browser |
| API suddenly unreachable | Home IP probably changed — update firewall rules (see section above) |
| VM stopped unexpectedly | Billing cap may have triggered — re-link billing (see billing cap section) |
