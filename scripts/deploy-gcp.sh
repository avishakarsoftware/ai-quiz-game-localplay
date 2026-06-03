#!/usr/bin/env bash
#
# Deploy backend to GCP VM (revelry-backend)
#
# Usage:
#   ./scripts/deploy-gcp.sh          # Build locally, push, deploy
#   ./scripts/deploy-gcp.sh --skip-build   # Deploy with existing image on VM
#   ./scripts/deploy-gcp.sh --with-frontend # Build frontend into backend image
#   ./scripts/deploy-gcp.sh --gamma --with-frontend # Deploy gamma container
#   ./scripts/deploy-gcp.sh --bootstrap-vm # Create /home/revelry-games layout, then deploy
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
REMOTE_BASE_DIR="/home/revelry-games"
CONTAINER_NAME="games-backend"
IMAGE_NAME="revelry-backend"
REMOTE_APP_DIR="$REMOTE_BASE_DIR/app"
REMOTE_DATA_DIR="$REMOTE_BASE_DIR/revelry-data"
REMOTE_BACKUP_DIR="$REMOTE_BASE_DIR/revelry-backups"
REMOTE_ENV_FILE="$REMOTE_APP_DIR/.env"
HOST_PORT="8000"
BACKEND_DIR="$(cd "$(dirname "$0")/../backend" && pwd)"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
INCLUDE_FRONTEND=false
SKIP_BUILD=false
ENVIRONMENT="prod"
BOOTSTRAP_VM=false
GOOGLE_WEB_CLIENT_ID="${GOOGLE_WEB_CLIENT_ID:-458966837298-9hjencou1ag2o17ln06iuuj86j5p8igj.apps.googleusercontent.com}"
APPLE_WEB_CLIENT_ID="${APPLE_WEB_CLIENT_ID:-me.revelryapp.quiz.web}"
APPLE_NATIVE_CLIENT_ID="${APPLE_NATIVE_CLIENT_ID:-me.revelryapp.quiz}"
SUPABASE_URL_DEFAULT="${SUPABASE_URL_DEFAULT:-https://hosbtyylacluziugwjfd.supabase.co}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[deploy]${NC} $*"; }
warn()  { echo -e "${YELLOW}[deploy]${NC} $*"; }
error() { echo -e "${RED}[deploy]${NC} $*" >&2; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-build)
            SKIP_BUILD=true
            shift
            ;;
        --with-frontend)
            INCLUDE_FRONTEND=true
            shift
            ;;
        --gamma)
            ENVIRONMENT="gamma"
            shift
            ;;
        --bootstrap-vm)
            BOOTSTRAP_VM=true
            shift
            ;;
        *)
            error "Unknown option: $1"
            echo "Usage: ./scripts/deploy-gcp.sh [--skip-build] [--with-frontend] [--gamma] [--bootstrap-vm]"
            exit 1
            ;;
    esac
done

if [[ "$ENVIRONMENT" == "gamma" ]]; then
    CONTAINER_NAME="games-backend-gamma"
    IMAGE_NAME="revelry-backend-gamma"
    REMOTE_DATA_DIR="$REMOTE_BASE_DIR/revelry-data-gamma"
    REMOTE_BACKUP_DIR="$REMOTE_BASE_DIR/revelry-backups-gamma"
    REMOTE_ENV_FILE="$REMOTE_APP_DIR/.env.gamma"
    HOST_PORT="8004"
    if [[ "$INCLUDE_FRONTEND" != "true" ]]; then
        warn "Gamma deploys are usually expected to use --with-frontend for same-origin testing."
    fi
fi

ssh_cmd() {
    gcloud compute ssh "$VM_NAME" --zone "$VM_ZONE" --command "$1"
}

validate_remote_db_config() {
    info "Checking remote database config..."
    local expected_prefix="games_"
    if [[ "$ENVIRONMENT" == "gamma" ]]; then
        expected_prefix="games_gamma_"
    fi
    ssh_cmd "
        set -e
        env_file='$REMOTE_ENV_FILE'
        get_env() {
            grep -E \"^\$1=\" \"\$env_file\" 2>/dev/null | tail -n 1 | cut -d= -f2- || true
        }
        db_backend=\$(get_env DB_BACKEND)
        table_prefix=\$(get_env TABLE_PREFIX)
        supabase_url=\$(get_env SUPABASE_URL)
        supabase_service_key=\$(get_env SUPABASE_SERVICE_KEY)

        [ -z \"\$db_backend\" ] && db_backend='sqlite'
        [ -z \"\$table_prefix\" ] && table_prefix='$expected_prefix'

        if [ \"\$table_prefix\" != '$expected_prefix' ]; then
            echo 'TABLE_PREFIX mismatch for $ENVIRONMENT: expected $expected_prefix, got '\"\$table_prefix\" >&2
            exit 1
        fi

        if [ \"\$db_backend\" = 'supabase' ]; then
            if [ -z \"\$supabase_url\" ]; then
                echo 'DB_BACKEND=supabase requires SUPABASE_URL in $REMOTE_ENV_FILE' >&2
                exit 1
            fi
            if [ -z \"\$supabase_service_key\" ]; then
                echo 'DB_BACKEND=supabase requires SUPABASE_SERVICE_KEY in $REMOTE_ENV_FILE' >&2
                exit 1
            fi
        elif [ \"\$db_backend\" != 'sqlite' ]; then
            echo 'Unsupported DB_BACKEND in $REMOTE_ENV_FILE: '\"\$db_backend\" >&2
            exit 1
        fi

        echo \"DB_BACKEND=\$db_backend TABLE_PREFIX=\$table_prefix\"
    "
}

bootstrap_vm_layout() {
    info "Bootstrapping $REMOTE_BASE_DIR on VM..."
    ssh_cmd "
        set -e
        REMOTE_USER=\$(whoami)
        sudo mkdir -p $REMOTE_APP_DIR $REMOTE_BASE_DIR/revelry-data $REMOTE_BASE_DIR/revelry-backups $REMOTE_BASE_DIR/revelry-data-gamma $REMOTE_BASE_DIR/revelry-backups-gamma

        if [ ! -f $REMOTE_APP_DIR/.env ]; then
            if [ -f /home/Avi/app/.env ]; then
                sudo cp /home/Avi/app/.env $REMOTE_APP_DIR/.env
            else
                echo 'Missing production env: $REMOTE_APP_DIR/.env' >&2
                echo 'Copy an env file there before deploying.' >&2
                exit 1
            fi
        fi

        if [ ! -f $REMOTE_APP_DIR/.env.gamma ]; then
            sudo cp $REMOTE_APP_DIR/.env $REMOTE_APP_DIR/.env.gamma
        fi

        for ENV_FILE in $REMOTE_APP_DIR/.env $REMOTE_APP_DIR/.env.gamma; do
            if ! sudo grep -q '^JWT_SECRET=.' \"\$ENV_FILE\"; then
                JWT_SECRET_VALUE=\$(openssl rand -hex 32)
                sudo sh -c \"grep -q '^JWT_SECRET=' '\$ENV_FILE' && sed -i 's#^JWT_SECRET=.*#JWT_SECRET='\$JWT_SECRET_VALUE'#' '\$ENV_FILE' || echo 'JWT_SECRET='\$JWT_SECRET_VALUE >> '\$ENV_FILE'\"
            fi
        done

        # Production runs behind nginx and can also serve the bundled SPA at gamesapi.revelryapp.me.
        sudo sh -c \"grep -q '^DB_BACKEND=' $REMOTE_APP_DIR/.env || echo 'DB_BACKEND=sqlite' >> $REMOTE_APP_DIR/.env\"
        sudo sh -c \"grep -q '^TABLE_PREFIX=' $REMOTE_APP_DIR/.env || echo 'TABLE_PREFIX=games_' >> $REMOTE_APP_DIR/.env\"
        sudo sh -c \"grep -q '^SUPABASE_URL=' $REMOTE_APP_DIR/.env || echo 'SUPABASE_URL=$SUPABASE_URL_DEFAULT' >> $REMOTE_APP_DIR/.env\"
        sudo sh -c \"grep -q '^TRUST_PROXY_HEADERS=' $REMOTE_APP_DIR/.env && sed -i 's#^TRUST_PROXY_HEADERS=.*#TRUST_PROXY_HEADERS=true#' $REMOTE_APP_DIR/.env || echo 'TRUST_PROXY_HEADERS=true' >> $REMOTE_APP_DIR/.env\"
        sudo sh -c \"grep -q '^DB_DIR=' $REMOTE_APP_DIR/.env && sed -i 's#^DB_DIR=.*#DB_DIR=/app/data#' $REMOTE_APP_DIR/.env || echo 'DB_DIR=/app/data' >> $REMOTE_APP_DIR/.env\"
        PROD_ORIGINS_CSV='https://games.revelryapp.me,https://gamesapi.revelryapp.me,capacitor://localhost,http://localhost,https://localhost,http://localhost:9200,http://127.0.0.1:9200'
        PROD_ORIGIN_LIST='https://games.revelryapp.me https://gamesapi.revelryapp.me capacitor://localhost http://localhost https://localhost http://localhost:9200 http://127.0.0.1:9200'
        sudo sh -c \"if ! grep -q '^ALLOWED_ORIGINS=' $REMOTE_APP_DIR/.env; then echo 'ALLOWED_ORIGINS='\$PROD_ORIGINS_CSV >> $REMOTE_APP_DIR/.env; elif grep -q '^ALLOWED_ORIGINS=$' $REMOTE_APP_DIR/.env; then sed -i 's#^ALLOWED_ORIGINS=$#ALLOWED_ORIGINS='\$PROD_ORIGINS_CSV'#' $REMOTE_APP_DIR/.env; fi\"
        for ORIGIN in \$PROD_ORIGIN_LIST; do
            sudo sh -c \"if ! grep '^ALLOWED_ORIGINS=' $REMOTE_APP_DIR/.env | grep -q '\$ORIGIN'; then sed -i '/^ALLOWED_ORIGINS=/s|$|,'\$ORIGIN'|' $REMOTE_APP_DIR/.env; fi\"
        done
        for KV in \
            'GEMINI_MODEL=gemini-2.5-flash-lite' \
            'GEMINI_PREMIUM_MODEL=gemini-2.5-flash-lite' \
            'IMAGE_GENERATION_PROVIDER=none' \
            'GEMINI_IMAGE_MODEL=gemini-2.5-flash-image' \
            'REMOTE_CONFIG_URL=https://games.revelryapp.me/quiz/config.json' \
            'REVELRY_CALLBACK_URL=https://api.revelryapp.me/api/games/localplay/callback' \
            'GOOGLE_CLIENT_ID=$GOOGLE_WEB_CLIENT_ID' \
            'APPLE_CLIENT_ID=$APPLE_WEB_CLIENT_ID' \
            'APPLE_CLIENT_IDS=$APPLE_WEB_CLIENT_ID,$APPLE_NATIVE_CLIENT_ID' \
        ; do
            KEY=\${KV%%=*}
            sudo sh -c \"grep -q '^'\$KEY'=' $REMOTE_APP_DIR/.env && sed -i 's#^'\$KEY'=.*#\$KV#' $REMOTE_APP_DIR/.env || echo '\$KV' >> $REMOTE_APP_DIR/.env\"
        done

        # Set gamma-specific env vars (upsert pattern: update if exists, append if not)
        sudo sh -c \"grep -q '^DB_BACKEND=' $REMOTE_APP_DIR/.env.gamma || echo 'DB_BACKEND=sqlite' >> $REMOTE_APP_DIR/.env.gamma\"
        sudo sh -c \"grep -q '^TABLE_PREFIX=' $REMOTE_APP_DIR/.env.gamma && sed -i 's#^TABLE_PREFIX=.*#TABLE_PREFIX=games_gamma_#' $REMOTE_APP_DIR/.env.gamma || echo 'TABLE_PREFIX=games_gamma_' >> $REMOTE_APP_DIR/.env.gamma\"
        sudo sh -c \"grep -q '^SUPABASE_URL=' $REMOTE_APP_DIR/.env.gamma || echo 'SUPABASE_URL=$SUPABASE_URL_DEFAULT' >> $REMOTE_APP_DIR/.env.gamma\"
        for KV in \
            'ALLOWED_ORIGINS=https://gamesapi-gamma.revelryapp.me,http://localhost:9200,http://127.0.0.1:9200' \
            'DB_DIR=/app/data' \
            'CHECKOUT_RETURN_URL=https://gamesapi-gamma.revelryapp.me/' \
            'TRUST_PROXY_HEADERS=true' \
            'GEMINI_MODEL=gemini-2.5-flash-lite' \
            'GEMINI_PREMIUM_MODEL=gemini-2.5-flash-lite' \
            'IMAGE_GENERATION_PROVIDER=none' \
            'GEMINI_IMAGE_MODEL=gemini-2.5-flash-image' \
            'REMOTE_CONFIG_URL=https://gamesapi-gamma.revelryapp.me/config.json' \
            'REVELRY_CALLBACK_URL=https://api-gamma.revelryapp.me/api/games/localplay/callback' \
            'ENABLE_BINGO=true' \
            'GOOGLE_CLIENT_ID=$GOOGLE_WEB_CLIENT_ID' \
            'APPLE_CLIENT_ID=$APPLE_WEB_CLIENT_ID' \
            'APPLE_CLIENT_IDS=$APPLE_WEB_CLIENT_ID,$APPLE_NATIVE_CLIENT_ID' \
        ; do
            KEY=\${KV%%=*}
            sudo sh -c \"grep -q '^'\$KEY'=' $REMOTE_APP_DIR/.env.gamma && sed -i 's#^'\$KEY'=.*#\$KV#' $REMOTE_APP_DIR/.env.gamma || echo '\$KV' >> $REMOTE_APP_DIR/.env.gamma\"
        done

        echo ''
        echo '*** IMPORTANT: Review Stripe keys in $REMOTE_APP_DIR/.env.gamma ***'
        echo 'Gamma should use test-mode Stripe keys (sk_test_..., whsec_...) to avoid charging real money.'
        echo ''

        sudo chmod 600 $REMOTE_APP_DIR/.env $REMOTE_APP_DIR/.env.gamma
        sudo chown -R \"\$REMOTE_USER:\$REMOTE_USER\" $REMOTE_BASE_DIR
    "
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

if [[ "$BOOTSTRAP_VM" == "true" ]]; then
    bootstrap_vm_layout
fi

info "Checking remote env file exists..."
if ! ssh_cmd "test -f $REMOTE_ENV_FILE" &>/dev/null; then
    error "Missing remote env file: $REMOTE_ENV_FILE"
    error "Run ./scripts/deploy-gcp.sh --bootstrap-vm first, or create the env file manually."
    exit 1
fi
validate_remote_db_config

if [[ "$BOOTSTRAP_VM" == "true" && "$SKIP_BUILD" == "true" && "$INCLUDE_FRONTEND" != "true" ]]; then
    info "Bootstrap complete; skipping deploy because --skip-build was provided without --with-frontend."
    exit 0
fi

build_context="$BACKEND_DIR"
cleanup_build_context() {
    if [[ "${TEMP_BUILD_CONTEXT:-}" != "" && -d "$TEMP_BUILD_CONTEXT" ]]; then
        rm -rf "$TEMP_BUILD_CONTEXT"
    fi
}
trap cleanup_build_context EXIT

# --- Step 1: Build Docker image (unless --skip-build) ---
if [[ "$SKIP_BUILD" != "true" ]]; then
    if [[ "$INCLUDE_FRONTEND" == "true" ]]; then
        info "Building frontend for backend-served deployment..."
        (
            cd "$FRONTEND_DIR"
            VITE_BASE_PATH=/ \
                VITE_API_URL= \
                VITE_ENABLE_BINGO="${VITE_ENABLE_BINGO:-true}" \
                VITE_CAST_APP_ID="${VITE_CAST_APP_ID:-1BC9ACD8}" \
                VITE_GOOGLE_CLIENT_ID="${VITE_GOOGLE_CLIENT_ID:-$GOOGLE_WEB_CLIENT_ID}" \
                VITE_APPLE_CLIENT_ID="${VITE_APPLE_CLIENT_ID:-$APPLE_WEB_CLIENT_ID}" \
                VITE_APPLE_REDIRECT_URI= \
                npx vite build
        )

        TEMP_BUILD_CONTEXT="$(mktemp -d)"
        info "Preparing temporary Docker context with frontend static assets..."
        rsync -a \
            --exclude 'venv' \
            --exclude 'data' \
            --exclude '__pycache__' \
            --exclude '*.pyc' \
            "$BACKEND_DIR/" "$TEMP_BUILD_CONTEXT/"
        rm -rf "$TEMP_BUILD_CONTEXT/static"
        mkdir -p "$TEMP_BUILD_CONTEXT/static"
        rsync -a "$FRONTEND_DIR/dist/" "$TEMP_BUILD_CONTEXT/static/"
        build_context="$TEMP_BUILD_CONTEXT"
    fi

    info "Building Docker image from $build_context..."
    docker build --platform linux/amd64 -t "$IMAGE_NAME:latest" "$build_context"

    info "Saving image to tarball..."
    IMAGE_TARBALL="/tmp/${IMAGE_NAME}.tar.gz"
    docker save "$IMAGE_NAME:latest" | gzip > "$IMAGE_TARBALL"

    info "Copying image to VM ($(du -h "$IMAGE_TARBALL" | cut -f1))..."
    gcloud compute scp "$IMAGE_TARBALL" "$VM_NAME:$IMAGE_TARBALL" --zone "$VM_ZONE"

    info "Loading image on VM..."
    ssh_cmd "gunzip -c $IMAGE_TARBALL | docker load && rm $IMAGE_TARBALL"
    rm "$IMAGE_TARBALL"
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
    ssh_cmd "docker cp ${CONTAINER_NAME}:/app/data/revelry.db $REMOTE_DATA_DIR/revelry.db 2>/dev/null || docker cp ${CONTAINER_NAME}:/app/backend/data/revelry.db $REMOTE_DATA_DIR/revelry.db 2>/dev/null || echo 'No DB in container, starting fresh'"
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
    -p 127.0.0.1:$HOST_PORT:8000 \
    -v $REMOTE_DATA_DIR:/app/data \
    --restart unless-stopped \
    $IMAGE_NAME:latest"

# --- Step 7: Verify ---
info "Waiting for container to start..."
HEALTH=$(ssh_cmd "
    for i in \$(seq 1 20); do
        CODE=\$(curl -s -o /dev/null -w '%{http_code}' http://localhost:$HOST_PORT/health 2>/dev/null || echo 'fail')
        if [ \"\$CODE\" = '200' ]; then
            echo 200
            exit 0
        fi
        sleep 1
    done
    echo \"\$CODE\"
")
if [[ "$HEALTH" == "200" ]]; then
    info "Health check passed!"
else
    error "Health check failed (HTTP $HEALTH). Check logs:"
    error "  gcloud compute ssh $VM_NAME --zone $VM_ZONE --command 'docker logs $CONTAINER_NAME --tail 20'"
    exit 1
fi

# Verify DB is accessible
DB_CHECK=$(ssh_cmd "
    DB_BACKEND=\$(grep -E '^DB_BACKEND=' $REMOTE_ENV_FILE 2>/dev/null | tail -n 1 | cut -d= -f2- || true)
    TABLE_PREFIX=\$(grep -E '^TABLE_PREFIX=' $REMOTE_ENV_FILE 2>/dev/null | tail -n 1 | cut -d= -f2- || true)
    if [ \"\$DB_BACKEND\" = 'supabase' ]; then
        echo \"Supabase backend active (TABLE_PREFIX=\$TABLE_PREFIX)\"
    else
        WALLETS=\$(sqlite3 $REMOTE_DATA_DIR/revelry.db 'SELECT COUNT(*) FROM wallets' 2>/dev/null || echo '?')
        echo \"\${WALLETS} wallets in SQLite database\"
    fi
")
info "Post-deploy: $DB_CHECK"

echo ""
info "Deploy complete!"
info "  Container: $CONTAINER_NAME"
info "  Port:      127.0.0.1:$HOST_PORT"
info "  Data:      $REMOTE_DATA_DIR/revelry.db"
info "  Backup:    $REMOTE_BACKUP_DIR/revelry_${TIMESTAMP}.db"
info "  Logs:      gcloud compute ssh $VM_NAME --zone $VM_ZONE --command 'docker logs $CONTAINER_NAME -f'"
