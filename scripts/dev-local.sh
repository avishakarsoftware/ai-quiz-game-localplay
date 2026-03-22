#!/bin/bash
# =============================================================================
# Local Development Environment
# =============================================================================
# Starts backend + frontend dev server for local testing.
# QR codes point to your LAN IP so other devices can join.
#
# Usage:
#   ./scripts/dev-local.sh          # start everything
#   ./scripts/dev-local.sh stop     # stop all servers
#   ./scripts/dev-local.sh ios      # build + launch iOS simulator too
#   ./scripts/dev-local.sh status   # check what's running
# =============================================================================

set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
PID_DIR="$ROOT/.dev-pids"

# Auto-detect LAN IP
LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "localhost")
BACKEND_PORT=8000
FRONTEND_PORT=5173

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

stop_servers() {
    echo -e "${YELLOW}Stopping servers...${NC}"
    if [ -f "$PID_DIR/backend.pid" ]; then
        kill "$(cat "$PID_DIR/backend.pid")" 2>/dev/null && echo "  Backend stopped" || echo "  Backend was not running"
        rm -f "$PID_DIR/backend.pid"
    fi
    if [ -f "$PID_DIR/frontend.pid" ]; then
        kill "$(cat "$PID_DIR/frontend.pid")" 2>/dev/null && echo "  Frontend stopped" || echo "  Frontend was not running"
        rm -f "$PID_DIR/frontend.pid"
    fi
    # Also kill by port in case PIDs are stale
    lsof -ti:$BACKEND_PORT 2>/dev/null | xargs kill 2>/dev/null || true
    lsof -ti:$FRONTEND_PORT 2>/dev/null | xargs kill 2>/dev/null || true
    echo -e "${GREEN}All servers stopped.${NC}"
}

check_status() {
    echo -e "${YELLOW}Server status:${NC}"
    if lsof -ti:$BACKEND_PORT >/dev/null 2>&1; then
        echo -e "  Backend:  ${GREEN}running${NC} on http://$LAN_IP:$BACKEND_PORT"
    else
        echo -e "  Backend:  ${RED}stopped${NC}"
    fi
    if lsof -ti:$FRONTEND_PORT >/dev/null 2>&1; then
        echo -e "  Frontend: ${GREEN}running${NC} on http://$LAN_IP:$FRONTEND_PORT"
    else
        echo -e "  Frontend: ${RED}stopped${NC}"
    fi
}

start_servers() {
    mkdir -p "$PID_DIR"

    # Stop any existing servers first
    lsof -ti:$BACKEND_PORT 2>/dev/null | xargs kill 2>/dev/null || true
    lsof -ti:$FRONTEND_PORT 2>/dev/null | xargs kill 2>/dev/null || true
    sleep 1

    echo -e "${YELLOW}Starting local dev environment...${NC}"
    echo -e "  LAN IP: ${GREEN}$LAN_IP${NC}"
    echo ""

    # --- Backend ---
    echo -e "${YELLOW}Starting backend on :$BACKEND_PORT ...${NC}"
    cd "$BACKEND_DIR"
    JWT_SECRET="local-test-secret-32bytes-long!!" \
    ADMIN_API_KEY="test-admin-key" \
    FREE_TIER_LIMIT=3 \
    DB_DIR="$BACKEND_DIR/data" \
    python -m uvicorn main:app --host 0.0.0.0 --port $BACKEND_PORT \
        > "$PID_DIR/backend.log" 2>&1 &
    echo $! > "$PID_DIR/backend.pid"

    # Wait for backend to be ready
    for i in {1..10}; do
        if curl -s "http://127.0.0.1:$BACKEND_PORT/health" >/dev/null 2>&1; then
            echo -e "  Backend: ${GREEN}ready${NC}"
            break
        fi
        sleep 1
    done

    # --- Frontend dev server ---
    echo -e "${YELLOW}Starting frontend on :$FRONTEND_PORT ...${NC}"
    cd "$FRONTEND_DIR"
    VITE_API_URL="http://$LAN_IP:$BACKEND_PORT" \
    npx vite --host 0.0.0.0 --port $FRONTEND_PORT \
        > "$PID_DIR/frontend.log" 2>&1 &
    echo $! > "$PID_DIR/frontend.pid"
    sleep 2
    echo -e "  Frontend: ${GREEN}ready${NC}"

    echo ""
    echo -e "${GREEN}=== Local Dev Environment Ready ===${NC}"
    echo ""
    echo -e "  Frontend:  http://$LAN_IP:$FRONTEND_PORT"
    echo -e "  Backend:   http://$LAN_IP:$BACKEND_PORT"
    echo -e "  Health:    http://$LAN_IP:$BACKEND_PORT/health"
    echo ""
    echo -e "  ${YELLOW}Admin commands:${NC}"
    echo -e "  Grant games:  curl -X POST 'http://$LAN_IP:$BACKEND_PORT/admin/grant?device_id=DEVICE_UUID' -H 'Authorization: Bearer test-admin-key'"
    echo -e "  Lookup:       curl 'http://$LAN_IP:$BACKEND_PORT/admin/lookup?device_id=DEVICE_UUID' -H 'Authorization: Bearer test-admin-key'"
    echo ""
    echo -e "  ${YELLOW}Logs:${NC}"
    echo -e "  tail -f $PID_DIR/backend.log"
    echo -e "  tail -f $PID_DIR/frontend.log"
    echo ""
    echo -e "  Stop with: ${GREEN}./scripts/dev-local.sh stop${NC}"
}

build_ios() {
    echo -e "${YELLOW}Building iOS app for simulator...${NC}"
    cd "$FRONTEND_DIR"

    # Build frontend with local URLs
    VITE_API_URL="http://$LAN_IP:$BACKEND_PORT" \
    VITE_WEB_URL="http://$LAN_IP:$FRONTEND_PORT/" \
    npx vite build 2>&1 | tail -2

    # Sync to Capacitor
    npx cap sync ios 2>&1 | tail -3

    # Find simulator
    SIM_ID=$(xcrun simctl list devices available | grep -i "iphone" | grep "Booted" | grep -oE '[A-F0-9-]{36}' | head -1)
    if [ -z "$SIM_ID" ]; then
        echo -e "${YELLOW}No booted simulator found. Boot one first via Xcode or:${NC}"
        echo "  xcrun simctl boot 'iPhone 16 Pro'"
        return 1
    fi

    # Clean build
    cd "$FRONTEND_DIR/ios/App"
    xcodebuild -project App.xcodeproj -scheme App \
        -destination "id=$SIM_ID" \
        -configuration Debug clean build 2>&1 | tail -2

    # Install and launch
    xcrun simctl terminate "$SIM_ID" me.revelryapp.quiz 2>/dev/null || true
    xcrun simctl uninstall "$SIM_ID" me.revelryapp.quiz 2>/dev/null || true
    APP_PATH=$(find ~/Library/Developer/Xcode/DerivedData/App-*/Build/Products/Debug-iphonesimulator/App.app -maxdepth 0 2>/dev/null | head -1)
    xcrun simctl install "$SIM_ID" "$APP_PATH"
    xcrun simctl launch "$SIM_ID" me.revelryapp.quiz

    echo ""
    echo -e "${GREEN}iOS app launched on simulator.${NC}"
    echo -e "QR codes will point to http://$LAN_IP:$FRONTEND_PORT"
}

build_android() {
    echo -e "${YELLOW}Building Android app for emulator...${NC}"
    cd "$FRONTEND_DIR"

    # Build frontend with local URLs
    VITE_API_URL="http://$LAN_IP:$BACKEND_PORT" \
    VITE_WEB_URL="http://$LAN_IP:$FRONTEND_PORT/" \
    npx vite build 2>&1 | tail -2

    # Sync to Capacitor
    npx cap sync android 2>&1 | tail -3

    # Build debug APK
    cd "$FRONTEND_DIR/android"
    ./gradlew assembleDebug 2>&1 | tail -3

    # Check for connected device/emulator
    ADB="$HOME/Library/Android/sdk/platform-tools/adb"
    DEVICE=$($ADB devices 2>/dev/null | grep -w "device" | head -1 | awk '{print $1}')
    if [ -z "$DEVICE" ]; then
        echo -e "${YELLOW}No connected device/emulator found.${NC}"
        echo "  Start one with: \$HOME/Library/Android/sdk/emulator/emulator -avd Pixel_8 &"
        echo "  APK is at: frontend/android/app/build/outputs/apk/debug/app-debug.apk"
        return 0
    fi

    # Install and launch
    $ADB install -r "$FRONTEND_DIR/android/app/build/outputs/apk/debug/app-debug.apk" 2>&1
    $ADB shell am force-stop me.revelryapp.quiz 2>/dev/null || true
    $ADB shell am start -n me.revelryapp.quiz/.MainActivity 2>&1

    echo ""
    echo -e "${GREEN}Android app launched on emulator/device.${NC}"
    echo -e "QR codes will point to http://$LAN_IP:$FRONTEND_PORT"
}

# --- Main ---
case "${1:-start}" in
    stop)
        stop_servers
        ;;
    status)
        check_status
        ;;
    ios)
        build_ios
        ;;
    android)
        build_android
        ;;
    start|"")
        start_servers
        ;;
    *)
        echo "Usage: $0 {start|stop|status|ios|android}"
        exit 1
        ;;
esac
