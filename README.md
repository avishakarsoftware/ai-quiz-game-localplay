# 🎮 AI Quiz Game (LocalPlay)

A multiplayer quiz game powered by local AI (Ollama). The organizer gives a prompt, AI generates questions, and players compete in real-time.

## Features

- 🤖 **AI-Generated Questions** via Ollama (local LLM) or cloud providers (Gemini, Anthropic)
- 📱 **Mobile-First PWA** for players
- ⚡ **Real-time WebSocket** gameplay
- 🏆 **Fastest-finger scoring** (more points for quicker answers)
- 🔥 **Streak bonuses** (1.5x at 3 correct, 2x at 5 correct)
- 🎯 **Bonus rounds** (~30% of questions award 2x points)
- 💪 **Power-ups** (Double Points, 50/50)
- 👥 **Team mode** with averaged team scores
- 📲 **QR Code + Room Code** for easy joining
- 🏅 **Animated podium** with fireworks and team standings
- 📺 **Spectator mode** for big-screen display

## Quick Start

### Prerequisites
- **Python** 3.11+
- **Node.js** 18+
- **Ollama** running locally with a model (default: `qwen2.5:14b-instruct`)

### Install

```bash
make install
```

Or manually:

```bash
cd backend && python3 -m venv venv && venv/bin/pip install -r requirements.txt
cd frontend && npm install
```

### Configure

Copy the example env file and edit as needed:

```bash
cp .env.example backend/.env
```

Key settings in `backend/.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_URL` | `http://localhost:11434/api/generate` | Ollama API endpoint |
| `OLLAMA_MODEL` | `qwen2.5:14b-instruct` | Model for quiz generation |
| `DEFAULT_PROVIDER` | `ollama` | AI provider (`ollama`, `gemini`, `anthropic`) |
| `GEMINI_API_KEY` | | Google Gemini API key (if using Gemini) |
| `ANTHROPIC_API_KEY` | | Anthropic API key (if using Claude) |

### Run

```bash
make dev
```

This starts both backend (port 8000) and frontend (port 5173) with hot-reload.

Or run them separately:

```bash
# Terminal 1: Backend
make dev-backend

# Terminal 2: Frontend
make dev-frontend
```

### Access
- **Organizer**: http://localhost:5173/
- **Players**: http://localhost:5173/join (or scan QR code)
- **Spectator**: http://localhost:5173/spectate?room=ROOMCODE

## Testing

### Unit + Integration Tests (no external dependencies)

```bash
make test
```

Runs all backend tests except E2E (~150 tests, ~8 seconds). Covers:
- API endpoint validation
- Game logic (scoring, streaks, bonus rounds, team leaderboard)
- WebSocket integration (full game flows, power-ups, reconnection)

### E2E Tests (requires Ollama running)

```bash
make test-e2e
```

Runs end-to-end tests with live quiz generation via Ollama. Tests the full flow: generate quiz → create room → play game → podium.

### All Tests

```bash
make test-all
```

### Frontend Type Check

```bash
make lint
```

## Makefile Commands

| Command | Description |
|---------|-------------|
| `make install` | Install all dependencies (Python venv + npm) |
| `make dev` | Start backend + frontend with hot-reload |
| `make dev-backend` | Start only the backend server |
| `make dev-frontend` | Start only the frontend dev server |
| `make test` | Run unit + integration tests |
| `make test-e2e` | Run E2E tests (requires Ollama) |
| `make test-all` | Run all tests |
| `make build` | Build frontend for production |
| `make lint` | TypeScript type checking |
| `make clean` | Remove build artifacts and `__pycache__` |

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI + WebSockets |
| Frontend | React + TypeScript + Vite |
| Styling | Tailwind CSS v4 |
| AI | Ollama / Gemini / Anthropic |

## Project Structure

```
LocalPlay/
├── backend/
│   ├── main.py           # FastAPI app + REST endpoints
│   ├── quiz_engine.py    # LLM integration (Ollama/Gemini/Anthropic)
│   ├── socket_manager.py # WebSocket game engine
│   ├── config.py         # Centralized configuration
│   ├── image_engine.py   # Stable Diffusion integration
│   └── tests/
│       ├── test_api.py                  # API endpoint tests
│       ├── test_game_logic.py           # Unit tests
│       ├── test_websocket_integration.py # WebSocket integration tests
│       └── test_e2e.py                  # E2E tests (live Ollama)
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── OrganizerPage.tsx  # Game host view
│       │   ├── PlayerPage.tsx     # Player view
│       │   └── SpectatorPage.tsx  # Big-screen spectator view
│       └── components/
│           ├── BonusSplash.tsx     # 2x bonus round animation
│           └── organizer/         # Organizer sub-screens
└── Makefile
```

## License

MIT
