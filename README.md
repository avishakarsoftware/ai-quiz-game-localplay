# AI Quiz Game (LocalPlay)

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

This starts both backend (port 9100) and frontend (port 9200) with hot-reload.

Or run them separately:

```bash
# Terminal 1: Backend
make dev-backend

# Terminal 2: Frontend
make dev-frontend
```

### Access
- **Organizer**: http://localhost:9200/
- **Players**: http://localhost:9200/join (or scan QR code)
- **Spectator**: http://localhost:9200/spectator?room=ROOMCODE

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

## Sign-In And Sessions

LocalPlay uses Google Identity Services and Apple Sign-In directly, not Firebase Auth, for the browser sign-in flow:

```text
Browser provider sign-in -> provider ID token -> LocalPlay backend verifies token -> LocalPlay session JWT
```

The signed-in state is LocalPlay-specific. It is not shared with the main Revelry app session, even though the Google Cloud project/client family may be shared. When sign-in works, the menu shows **Signed in**, the account/email prefix, and a **Sign Out** button.

Required deployed auth settings:

- `GOOGLE_CLIENT_ID` must match `VITE_GOOGLE_CLIENT_ID`.
- `APPLE_CLIENT_ID` should be the web Service ID, currently `me.revelryapp.quiz.web`.
- `APPLE_CLIENT_IDS` should include web and future native audiences, currently `me.revelryapp.quiz.web,me.revelryapp.quiz`.
- `JWT_SECRET` must be set or provider sign-in can succeed but LocalPlay session creation will fail.

## Deployment Notes

Public production still uses IONOS for the web frontend:

- `https://games.revelryapp.me/quiz/` serves the static Vite build.
- `https://gamesapi.revelryapp.me` serves API and WebSockets.

The backend can also serve the built SPA from `/app/static` for gamma and backend preview:

```bash
# Backend preview with bundled frontend
./scripts/deploy-gcp.sh --with-frontend

# Gamma same-origin app/API/WebSockets
./scripts/deploy-gcp.sh --gamma --with-frontend
```

## Persistence

The active runtime still uses SQLite by default. Production stores data at `/home/revelry-games/revelry-data/revelry.db`. Gamma is currently deployed with `DB_BACKEND=supabase` and stores durable data in the shared Supabase project's `games_gamma_*` tables.

Supabase migration planning is documented in [SPEC-SUPABASE-MIGRATION.md](SPEC-SUPABASE-MIGRATION.md). The generated SQL has been applied to the shared VibePix Supabase project. Prefixes are mandatory because the database is shared: `games_` for production and `games_gamma_` for gamma.

Gamma convention: `https://gamesapi-gamma.revelryapp.me`.

Backend-served prod/gamma SPA origins must also be registered in Google Cloud OAuth and Apple Developer for browser sign-in. See [DEPLOY.md](DEPLOY.md) for the exact origins and redirect roots.

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
