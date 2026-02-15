"""Centralized configuration — all env vars in one place."""
import os
import logging
from dotenv import load_dotenv

load_dotenv()

# --- Ollama / LLM ---
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:14b-instruct")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))
LLM_MAX_RETRIES = 3

# --- Cloud AI Providers ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
DEFAULT_PROVIDER = os.getenv("DEFAULT_PROVIDER", "ollama")

# --- Stable Diffusion ---
SD_API_URL = os.getenv("SD_API_URL", "http://localhost:8765")

# --- Server ---
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "")

# --- Game ---
MAX_NICKNAME_LENGTH = 20
ROOM_TTL_SECONDS = int(os.getenv("ROOM_TTL_SECONDS", "1800"))
MAX_ROOM_CODE_ATTEMPTS = 10
DEFAULT_TIME_LIMIT = 15
DEFAULT_NUM_QUESTIONS = 10
MIN_QUESTIONS = 3
MAX_QUESTIONS = 20
VALID_DIFFICULTIES = ("easy", "medium", "hard")

# --- Streak bonus ---
STREAK_THRESHOLDS = {3: 1.5, 5: 2.0}  # streak_count -> multiplier

# --- Bonus rounds ---
BONUS_ROUND_FRACTION = 0.3  # ~30% of questions will be bonus rounds (2x points)

# --- Logging ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE = os.getenv("LOG_FILE", "")  # empty = stdout only


def setup_logging():
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if LOG_FILE:
        handlers.append(logging.FileHandler(LOG_FILE))
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )
