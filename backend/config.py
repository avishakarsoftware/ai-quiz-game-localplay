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
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
DEFAULT_PROVIDER = os.getenv("DEFAULT_PROVIDER", "gemini")

# --- Image Generation ---
IMAGE_GENERATION_PROVIDER = os.getenv("IMAGE_GENERATION_PROVIDER", "stable_diffusion").strip().lower()
SD_API_URL = os.getenv("SD_API_URL", "http://localhost:8765")

# --- Server ---
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "9100"))
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "")
FRONTEND_DIST_DIR = os.getenv("FRONTEND_DIST_DIR", "/app/static")

# --- Database ---
# Default remains SQLite so Supabase migration scaffolding is inert until an
# environment explicitly opts in with DB_BACKEND=supabase.
DB_BACKEND = os.getenv("DB_BACKEND", "sqlite").strip().lower()
TABLE_PREFIX = os.getenv("TABLE_PREFIX", "games_").strip()
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "").strip()
SUPABASE_TIMEOUT_SECONDS = float(os.getenv("SUPABASE_TIMEOUT_SECONDS", "10"))

# --- Rate Limiting ---
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_REQUESTS = 5  # max quiz generations per window per IP
DAILY_QUIZ_LIMIT = int(os.getenv("DAILY_QUIZ_LIMIT", "100"))  # max quiz generations per day (0 = unlimited)
MAX_LLM_CALLS_PER_HOUR = int(os.getenv("MAX_LLM_CALLS_PER_HOUR", "500"))  # global cap across all users (0 = unlimited)
TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "false").lower() == "true"  # trust X-Forwarded-For

# --- WebSocket Security ---
WS_RATE_LIMIT_PER_SEC = 10  # max messages per second per client
DRAW_OP_RATE_LIMIT_PER_SEC = 30  # drawing strokes need a separate higher cap
MAX_DRAW_OP_MESSAGE_SIZE = 2048  # bytes
MAX_DRAW_OPS_PER_SYNC = 500
MAX_WS_MESSAGE_SIZE = 4096  # bytes
MAX_AVATAR_LENGTH = 10  # emoji avatars only
MAX_TEAM_NAME_LENGTH = 30

# --- Storage Limits ---
MAX_ROOMS = 50
MAX_QUIZZES = 100
MAX_IMAGE_SIZE_BYTES = 2 * 1024 * 1024  # 2MB per image
QUIZ_TTL_SECONDS = 3600  # 1 hour

# --- IONOS media uploads ---
MEDIA_UPLOAD_URL = os.getenv("MEDIA_UPLOAD_URL", "").strip()
MEDIA_PUBLIC_BASE_URL = os.getenv("MEDIA_PUBLIC_BASE_URL", "").strip().rstrip("/")
MEDIA_UPLOAD_SECRET = os.getenv("MEDIA_UPLOAD_SECRET", "").strip()
MEDIA_PATH_PREFIX = os.getenv("MEDIA_PATH_PREFIX", "local").strip().strip("/")
MEDIA_UPLOAD_TOKEN_TTL_SECONDS = int(os.getenv("MEDIA_UPLOAD_TOKEN_TTL_SECONDS", "900"))
MEDIA_ALLOWED_MIME_TYPES = tuple(
    item.strip()
    for item in os.getenv("MEDIA_ALLOWED_MIME_TYPES", "image/png,image/jpeg,image/webp").split(",")
    if item.strip()
)

# --- Game ---
MAX_PROMPT_LENGTH = 140
MAX_NICKNAME_LENGTH = 20
ROOM_TTL_SECONDS = int(os.getenv("ROOM_TTL_SECONDS", "1800"))
ORGANIZER_RECONNECT_GRACE_SECONDS = int(os.getenv("ORGANIZER_RECONNECT_GRACE_SECONDS", "600"))
MAX_ROOM_CODE_ATTEMPTS = 10
DEFAULT_TIME_LIMIT = 15
DEFAULT_NUM_QUESTIONS = 10
MIN_QUESTIONS = 3
MAX_QUESTIONS = 20
VALID_DIFFICULTIES = ("easy", "medium", "hard")

# --- Player / history limits ---
MAX_PLAYERS_PER_ROOM = 100
MIN_WMLT_PLAYERS = 2  # WMLT minimum players
MIN_DRAWING_PLAYERS = 2  # DrawingGame minimum players
MIN_HOUSIE_PLAYERS = 2  # Housie minimum players
MAX_GAME_HISTORY = 1000

# --- Streak bonus ---
STREAK_THRESHOLDS = {3: 1.5, 5: 2.0}  # streak_count -> multiplier

# --- Bonus rounds ---
BONUS_ROUND_FRACTION = 0.3  # ~30% of questions will be bonus rounds (2x points)

# --- Token Economy ---
SIGNUP_BONUS_TOKENS = int(os.getenv("SIGNUP_BONUS_TOKENS", "20"))
DAILY_BONUS_TOKENS = int(os.getenv("DAILY_BONUS_TOKENS", "10"))
MAX_TOKEN_BALANCE = int(os.getenv("MAX_TOKEN_BALANCE", "1000"))
COST_GENERATE = int(os.getenv("COST_GENERATE", "1"))
COST_ROOM = int(os.getenv("COST_ROOM", "10"))
AD_REWARD_TOKENS = int(os.getenv("AD_REWARD_TOKENS", "5"))
MAX_ADS_PER_DAY = int(os.getenv("MAX_ADS_PER_DAY", "5"))
TOKEN_PACK_AMOUNT = int(os.getenv("TOKEN_PACK_AMOUNT", "110"))
PROMO_ID = os.getenv("PROMO_ID", "")  # e.g. "launch_2026" — must match config.json promo.id
PROMO_TOKEN_AMOUNT = int(os.getenv("PROMO_TOKEN_AMOUNT", "0"))  # tokens to credit when promo is active

# --- Legacy (kept for db.py migration compatibility, not actively used) ---
PREMIUM_DURATION_HOURS = int(os.getenv("PREMIUM_DURATION_HOURS", "720"))  # 30 days
FREE_TIER_LIMIT = int(os.getenv("FREE_TIER_LIMIT", "3"))

# --- Premium / Payments ---
JWT_SECRET = os.getenv("JWT_SECRET", "")
GEMINI_PREMIUM_MODEL = os.getenv("GEMINI_PREMIUM_MODEL", "gemini-2.5-flash-lite")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")
CHECKOUT_RETURN_URL = os.getenv("CHECKOUT_RETURN_URL", "")  # explicit return URL for Stripe checkout
REMOTE_CONFIG_URL = os.getenv("REMOTE_CONFIG_URL", "")  # e.g. https://games.revelryapp.me/quiz/config.json

# --- Auth (Phase 2) ---
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
APPLE_CLIENT_ID = os.getenv("APPLE_CLIENT_ID", "")  # e.g. "me.revelryapp.quiz"
APPLE_CLIENT_IDS = [
    client_id.strip()
    for client_id in os.getenv("APPLE_CLIENT_IDS", APPLE_CLIENT_ID).split(",")
    if client_id.strip()
]
SESSION_JWT_EXPIRY_DAYS = int(os.getenv("SESSION_JWT_EXPIRY_DAYS", "30"))

# --- Host app integrations ---
REVELRY_INTEGRATION_SECRET = os.getenv("REVELRY_INTEGRATION_SECRET", "").strip()
REVELRY_LAUNCH_TOKEN_TTL_SECONDS = int(os.getenv("REVELRY_LAUNCH_TOKEN_TTL_SECONDS", "600"))
REVELRY_AUTHORING_TOKEN_TTL_SECONDS = int(os.getenv("REVELRY_AUTHORING_TOKEN_TTL_SECONDS", "3600"))
REVELRY_PARTY_HUB_RETURN_TOKEN_TTL_SECONDS = int(os.getenv("REVELRY_PARTY_HUB_RETURN_TOKEN_TTL_SECONDS", str(4 * 3600)))
REVELRY_SESSION_LOBBY_TTL_SECONDS = int(os.getenv("REVELRY_SESSION_LOBBY_TTL_SECONDS", str(4 * 3600)))
REVELRY_SESSION_IDLE_TTL_SECONDS = int(os.getenv("REVELRY_SESSION_IDLE_TTL_SECONDS", str(2 * 3600)))
REVELRY_CALLBACK_URL = os.getenv("REVELRY_CALLBACK_URL", "").strip()
REVELRY_CALLBACK_SECRET = os.getenv("REVELRY_CALLBACK_SECRET", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")

if REVELRY_INTEGRATION_SECRET and REVELRY_CALLBACK_SECRET and REVELRY_INTEGRATION_SECRET != REVELRY_CALLBACK_SECRET:
    logging.getLogger(__name__).warning(
        "REVELRY_CALLBACK_SECRET differs from REVELRY_INTEGRATION_SECRET; "
        "REVELRY_INTEGRATION_SECRET is canonical and the callback secret should only be used during planned rotation."
    )

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
