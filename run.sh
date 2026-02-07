#!/bin/bash
# Run script for AI Quiz Game

echo "🎮 Starting AI Quiz Game..."

# Start backend
echo "📦 Starting Backend on http://localhost:8000"
cd backend
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
cd ..

# Wait for backend
sleep 2

# Start frontend
echo "🎨 Starting Frontend on http://localhost:5173"
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "✅ Services started!"
echo "   Backend:   http://localhost:8000"
echo "   Frontend:  http://localhost:5173"
echo "   Organizer: http://localhost:5173/"
echo "   Players:   http://localhost:5173/join"
echo ""
echo "Press Ctrl+C to stop all services"

# Wait for interrupt
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" SIGINT SIGTERM
wait
