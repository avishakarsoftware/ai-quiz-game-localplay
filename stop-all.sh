#!/bin/bash
# Stop all LocalPlay servers
# Usage: ./stop-all.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"

echo "🛑 Stopping LocalPlay servers..."
echo ""

# Kill by PID files
for service in image-gen backend frontend; do
    PID_FILE="$LOG_DIR/$service.pid"
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo "   Stopping $service (PID: $PID)..."
            kill "$PID" 2>/dev/null
            rm "$PID_FILE"
        else
            echo "   $service not running (stale PID file)"
            rm "$PID_FILE"
        fi
    fi
done

# Also kill any remaining processes on our ports
echo ""
echo "🔍 Cleaning up remaining processes on ports..."

for port in 5173 8000 8765; do
    PID=$(lsof -ti :$port 2>/dev/null)
    if [ -n "$PID" ]; then
        echo "   Killing process on port $port (PID: $PID)"
        kill $PID 2>/dev/null
    fi
done

echo ""
echo "✅ All servers stopped!"
