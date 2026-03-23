#!/usr/bin/env bash
#
# Deploy backend to GCP VM (revelry-backend)
#
# Usage:
#   ./scripts/deploy-gcp.sh          # Build locally, push, deploy
#   ./scripts/deploy-gcp.sh --skip-build   # Deploy with existing image on VM
#
# What this script does:
#   1. Builds the Docker image locally
#   2. Copies it to the GCP VM
#   3. Backs up the SQLite database
#   4. Stops the old container
#   5. Starts the new container WITH volume mount (data persists)
#   6. Verifies the deploy
#
# Prerequisites:
#   - gcloud CLI authenticated
#   - SSH key configured for the VM
#

set -euo pipefail

# --- Config ---
VM_NAME="revelry-backend"
VM_ZONE="us-central1-a"
CONTAINER_NAME="games-backend"
IMAGE_NAME="revelry-backend"
REMOTE_DATA_DIR="/home/revelry-data"
REMOTE_BACKUP_DIR="/home/revelry-backups"
REMOTE_ENV_FILE="/home/.env"
BACKEND_DIR="$(cd "$(dirname "$0")/../backend" && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[deploy]${NC} $*"; }
warn()  { echo -e "${YELLOW}[deploy]${NC} $*"; }
error() { echo -e "${RED}[deploy]${NC} $*" >&2; }

ssh_cmd() {
    gcloud compute ssh "$VM_NAME" --zone "$VM_ZONE" --command "$1"
}

# --- Pre-flight checks ---
info "Checking gcloud auth..."
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null | head -1 | grep -q .; then
    error "Not authenticated with gcloud. Run: gcloud auth login"
    exit 1
fi

info "Checking VM is reachable..."
if ! ssh_cmd "echo ok" &>/dev/null; then
    error "Cannot SSH to $VM_NAME. Check firewall and SSH keys."
    exit 1
fi

# --- Step 1: Build Docker image (unless --skip-build) ---
if [[ "${1:-}" != "--skip-build" ]]; then
    info "Building Docker image from $BACKEND_DIR..."
    docker build -t "$IMAGE_NAME:latest" "$BACKEND_DIR"

    info "Saving image to tarball..."
    docker save "$IMAGE_NAME:latest" | gzip > /tmp/revelry-backend.tar.gz

    info "Copying image to VM ($(du -h /tmp/revelry-backend.tar.gz | cut -f1))..."
    gcloud compute scp /tmp/revelry-backend.tar.gz "$VM_NAME:/tmp/revelry-backend.tar.gz" --zone "$VM_ZONE"

    info "Loading image on VM..."
    ssh_cmd "gunzip -c /tmp/revelry-backend.tar.gz | docker load && rm /tmp/revelry-backend.tar.gz"
    rm /tmp/revelry-backend.tar.gz
else
    info "Skipping build (--skip-build)"
fi

# --- Step 2: Ensure data & backup directories exist ---
info "Ensuring data directories exist on VM..."
ssh_cmd "mkdir -p $REMOTE_DATA_DIR $REMOTE_BACKUP_DIR"

# --- Step 3: Migrate data out of container (first-time only) ---
info "Checking for existing data..."
NEEDS_MIGRATION=$(ssh_cmd "
    if [ ! -f $REMOTE_DATA_DIR/revelry.db ] && docker ps -a --format '{{.Names}}' | grep -q '^${CONTAINER_NAME}$'; then
        echo 'yes'
    else
        echo 'no'
    fi
")

if [[ "$NEEDS_MIGRATION" == "yes" ]]; then
    warn "First deploy with volume mount — migrating DB from container..."
    ssh_cmd "docker cp ${CONTAINER_NAME}:/app/backend/data/revelry.db $REMOTE_DATA_DIR/revelry.db 2>/dev/null || echo 'No DB in container, starting fresh'"
    info "Migration complete."
fi

# --- Step 4: Backup current database ---
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
info "Backing up database..."
BACKUP_RESULT=$(ssh_cmd "
    if [ -f $REMOTE_DATA_DIR/revelry.db ]; then
        cp $REMOTE_DATA_DIR/revelry.db $REMOTE_BACKUP_DIR/revelry_${TIMESTAMP}.db
        # Keep only last 10 backups
        ls -t $REMOTE_BACKUP_DIR/revelry_*.db 2>/dev/null | tail -n +11 | xargs rm -f 2>/dev/null
        WALLETS=\$(sqlite3 $REMOTE_DATA_DIR/revelry.db 'SELECT COUNT(*) FROM wallets' 2>/dev/null || echo '?')
        USERS=\$(sqlite3 $REMOTE_DATA_DIR/revelry.db 'SELECT COUNT(*) FROM users' 2>/dev/null || echo '?')
        BALANCE=\$(sqlite3 $REMOTE_DATA_DIR/revelry.db 'SELECT COALESCE(SUM(balance),0) FROM wallets' 2>/dev/null || echo '?')
        echo \"Backup saved: \${WALLETS} wallets, \${USERS} users, \${BALANCE} total sparks\"
    else
        echo 'No database to backup (fresh deploy)'
    fi
")
info "$BACKUP_RESULT"

# --- Step 5: Stop old container ---
info "Stopping old container..."
ssh_cmd "docker stop $CONTAINER_NAME 2>/dev/null; docker rm $CONTAINER_NAME 2>/dev/null; true"

# --- Step 6: Start new container with volume mount ---
info "Starting new container..."
ssh_cmd "docker run -d \
    --name $CONTAINER_NAME \
    --env-file $REMOTE_ENV_FILE \
    -p 8000:8000 \
    -v $REMOTE_DATA_DIR:/app/backend/data \
    --restart unless-stopped \
    $IMAGE_NAME:latest"

# --- Step 7: Verify ---
info "Waiting for container to start..."
sleep 3

HEALTH=$(ssh_cmd "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health 2>/dev/null || echo 'fail'")
if [[ "$HEALTH" == "200" ]]; then
    info "Health check passed!"
else
    error "Health check failed (HTTP $HEALTH). Check logs:"
    error "  gcloud compute ssh $VM_NAME --zone $VM_ZONE --command 'docker logs $CONTAINER_NAME --tail 20'"
    exit 1
fi

# Verify DB is accessible
DB_CHECK=$(ssh_cmd "
    WALLETS=\$(sqlite3 $REMOTE_DATA_DIR/revelry.db 'SELECT COUNT(*) FROM wallets' 2>/dev/null || echo '?')
    echo \"\${WALLETS} wallets in database\"
")
info "Post-deploy: $DB_CHECK"

echo ""
info "Deploy complete!"
info "  Container: $CONTAINER_NAME"
info "  Data:      $REMOTE_DATA_DIR/revelry.db"
info "  Backup:    $REMOTE_BACKUP_DIR/revelry_${TIMESTAMP}.db"
info "  Logs:      gcloud compute ssh $VM_NAME --zone $VM_ZONE --command 'docker logs $CONTAINER_NAME -f'"
