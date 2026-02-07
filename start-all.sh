#!/bin/bash
# Start all LocalPlay servers
# Usage: ./start-all.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

echo "🚀 Starting LocalPlay servers..."
echo ""

# 1. Start Stable Diffusion Image Server
echo "🖼️  Starting Image Generation Server (port 8765)..."
cd "$SCRIPT_DIR/../image-gen-server"
source venv/bin/activate
nohup python server.py > "$LOG_DIR/image-gen.log" 2>&1 &
echo $! > "$LOG_DIR/image-gen.pid"
echo "   PID: $(cat $LOG_DIR/image-gen.pid)"

# 2. Start Backend API
echo "⚙️  Starting Backend API (port 8000)..."
cd "$SCRIPT_DIR/backend"
source venv/bin/activate
nohup uvicorn main:app --host 0.0.0.0 --port 8000 --reload > "$LOG_DIR/backend.log" 2>&1 &
echo $! > "$LOG_DIR/backend.pid"
echo "   PID: $(cat $LOG_DIR/backend.pid)"

# 3. Start Frontend Dev Server
echo "🌐 Starting Frontend (port 5173)..."
cd "$SCRIPT_DIR/frontend"
nohup npm run dev -- --host 0.0.0.0 > "$LOG_DIR/frontend.log" 2>&1 &
echo $! > "$LOG_DIR/frontend.pid"
echo "   PID: $(cat $LOG_DIR/frontend.pid)"

echo ""
echo "✅ All servers starting!"
echo ""
echo "📍 URLs:"
echo "   Frontend:  http://localhost:5173"
echo "   Backend:   http://localhost:8000"
echo "   Image Gen: http://localhost:8765"
echo ""
echo "📁 Logs: $LOG_DIR"
echo "🛑 Stop: ./stop-all.sh"
