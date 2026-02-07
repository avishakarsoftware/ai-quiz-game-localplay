# 🎮 AI Quiz Game (LocalPlay)

A Kahoot-style multiplayer quiz game powered by local AI (Ollama). The organizer gives a prompt, AI generates questions, and players compete in real-time.

## Features

- 🤖 **AI-Generated Questions** via Ollama (local LLM)
- 📱 **Mobile-First PWA** for players
- ⚡ **Real-time WebSocket** gameplay
- 🏆 **Fastest-finger scoring** (more points for quicker answers)
- 📲 **QR Code + Room Code** for easy joining

## Quick Start

### Prerequisites
- **Ollama** running locally with a model (e.g., `ollama run llama3`)
- **Node.js** 18+
- **Python** 3.11+

### Setup

```bash
# Backend
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
```

### Run

```bash
# Terminal 1: Backend
cd backend && source venv/bin/activate
uvicorn main:app --port 8000 --reload

# Terminal 2: Frontend
cd frontend
npm run dev
```

### Access
- **Organizer**: http://localhost:5173/
- **Players**: http://localhost:5173/join (or scan QR code)

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI + WebSockets |
| Frontend | React + TypeScript + Vite |
| Styling | Tailwind CSS v4 |
| AI | Ollama (local LLM) |

## Project Structure

```
LocalPlay/
├── backend/
│   ├── main.py           # FastAPI app
│   ├── quiz_engine.py    # Ollama integration
│   ├── socket_manager.py # WebSocket game engine
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── OrganizerPage.tsx
│       │   └── PlayerPage.tsx
│       └── App.tsx
└── run.sh               # Convenience script
```

## License

MIT
