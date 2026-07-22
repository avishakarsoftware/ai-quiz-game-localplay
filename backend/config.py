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
ENVIRONMENT = os.getenv("LOCALPLAY_ENV", os.getenv("APP_ENV", "")).strip().lower()
if not ENVIRONMENT:
    if DB_BACKEND == "supabase" and TABLE_PREFIX == "games_gamma_":
        ENVIRONMENT = "gamma"
    elif DB_BACKEND == "supabase" and TABLE_PREFIX == "games_":
        ENVIRONMENT = "production"
    else:
        ENVIRONMENT = "local"
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
# How long a disconnected lobby seat is preserved before the periodic cleanup
# prunes it. 10 min covers real party pauses (phone sleep, in-app browser
# suspend) while staying <= ROOM_TTL_SECONDS. The cleanup loop applies this
# mid-lobby, not just at game start.
LOBBY_RECONNECT_GRACE_SECONDS = int(os.getenv("LOBBY_RECONNECT_GRACE_SECONDS", "600"))
# Room snapshot/restore (room_snapshot.py): live games survive deploys/restarts.
ROOM_SNAPSHOT_ENABLED = os.getenv("ROOM_SNAPSHOT_ENABLED", "true").lower() == "true"
ROOM_SNAPSHOT_INTERVAL_SECONDS = int(os.getenv("ROOM_SNAPSHOT_INTERVAL_SECONDS", "10"))
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
MIN_BINGO_PLAYERS = 2  # Custom Bingo minimum players
MIN_MUSICAL_CHAIRS_PLAYERS = 3  # Musical Chairs minimum players
MIN_BLUFF_PLAYERS = 3  # Bluff minimum players
MIN_TWO_TRUTHS_PLAYERS = 3  # Two Truths and a Lie minimum players
MIN_STORY_CHAIN_PLAYERS = 3  # Story Chain minimum players
MIN_COMMON_GROUND_PLAYERS = 4  # Common Ground minimum players
MIN_FIND_SOMEONE_PLAYERS = 1  # Find Someone Who can auto-start when the first checked-in guest joins
MIN_WHO_AM_I_PLAYERS = 2  # Who Am I minimum players
MIN_CHIT_PULL_PLAYERS = 3  # Chit Pull minimum players
MIN_MAFIA_PLAYERS = 6  # Mafia minimum players
MIN_PARTY_QUESTS_PLAYERS = 1  # Ambient party quests can start as soon as the first guest joins
MIN_SURVEY_SAYS_PLAYERS = 2  # Survey Says needs at least two teams to feel right
MIN_WOULD_YOU_RATHER_PLAYERS = 2  # Would You Rather minimum players
MIN_NEVER_HAVE_I_EVER_PLAYERS = 2  # Never Have I Ever minimum players
MIN_WORD_ASSOCIATION_PLAYERS = 2  # Word Association minimum players
MIN_ACRONYM_PLAYERS = 2  # Acronym Game minimum players
MIN_PHOTO_CLUE_PLAYERS = 2  # Photo Clue minimum players
MIN_POKER_PLAYERS = 2  # Party Poker minimum players
MC_MIN_MUSIC_SECONDS = 3
MC_MAX_MUSIC_SECONDS = 60
MC_MIN_GRAB_WINDOW = 2
MC_MAX_GRAB_WINDOW = 10
MAX_GAME_HISTORY = 1000
BINGO_ENABLED = os.getenv("ENABLE_BINGO", "true").lower() == "true"

# --- Streak bonus ---
STREAK_THRESHOLDS = {3: 1.5, 5: 2.0}  # streak_count -> multiplier

# --- Bonus rounds ---
BONUS_ROUND_FRACTION = 0.3  # ~30% of questions will be bonus rounds (2x points)

# --- Token Economy ---
SIGNUP_BONUS_TOKENS = int(os.getenv("SIGNUP_BONUS_TOKENS", "20"))
DAILY_BONUS_TOKENS = int(os.getenv("DAILY_BONUS_TOKENS", "10"))
MAX_TOKEN_BALANCE = int(os.getenv("MAX_TOKEN_BALANCE", "1000"))
# Login-streak daily bonus (SPEC-STREAK-BONUS): reward = min(BASE + (streak-1)*STEP, MAX).
# STREAK_BASE defaults to DAILY_BONUS_TOKENS so day-1 is unchanged; keep them equal to avoid confusion.
STREAK_BASE = int(os.getenv("STREAK_BASE", str(DAILY_BONUS_TOKENS)))
STREAK_STEP = int(os.getenv("STREAK_STEP", "5"))
STREAK_MAX = int(os.getenv("STREAK_MAX", "30"))
# Referral rewards (SPEC-REFERRAL): both parties get REFERRAL_REWARD on a successful redeem.
REFERRAL_REWARD = int(os.getenv("REFERRAL_REWARD", "20"))
MAX_REFERRALS_PER_DAY = int(os.getenv("MAX_REFERRALS_PER_DAY", "10"))
# Referrals run on SQLite automatically. On Supabase they require the referral RPCs from
# sql/games-schema.sql to be applied first — set REFERRALS_ENABLED=true AFTER applying them.
REFERRALS_ENABLED = os.getenv("REFERRALS_ENABLED", "false").lower() == "true"
# Spark gifting (SPEC-GIFTING): send sparks wallet→wallet, addressed by the recipient's referral
# code (their public "friend code"). Atomic debit-then-credit, idempotent on a client key.
GIFT_MIN_AMOUNT = int(os.getenv("GIFT_MIN_AMOUNT", "1"))
GIFT_MAX_AMOUNT = int(os.getenv("GIFT_MAX_AMOUNT", "100"))  # per-gift ceiling
MAX_GIFTS_PER_DAY = int(os.getenv("MAX_GIFTS_PER_DAY", "20"))  # per-sender count cap
MAX_GIFT_TOKENS_PER_DAY = int(os.getenv("MAX_GIFT_TOKENS_PER_DAY", "200"))  # per-sender total-sparks cap
# Like REFERRALS_ENABLED: works on SQLite automatically; on Supabase needs the gift_sparks RPC
# applied first, then GIFTING_ENABLED=true.
GIFTING_ENABLED = os.getenv("GIFTING_ENABLED", "false").lower() == "true"
# Achievements / badges (SPEC-ACHIEVEMENTS): idempotent per-wallet badges awarded on milestones.
# v1 covers economy events only (no game-completion hooks yet). Read-mostly, no economy risk.
# Same gate shape: SQLite always on; on Supabase needs the achievements table + RPC, then ACHIEVEMENTS_ENABLED=true.
ACHIEVEMENTS_ENABLED = os.getenv("ACHIEVEMENTS_ENABLED", "false").lower() == "true"
# The badge catalog is backend-authoritative: /achievements returns the whole catalog with earned flags,
# so the frontend renders labels/emoji it's told about (no client-side badge list to keep in sync).
ACHIEVEMENT_CATALOG = [
    {"id": "welcome", "emoji": "👋", "name": "Welcome to Revelry", "description": "Joined the party."},
    {"id": "first_referral", "emoji": "🔗", "name": "Connector", "description": "Completed a referral."},
    {"id": "first_gift", "emoji": "🎁", "name": "Generous", "description": "Sent your first spark gift."},
]
ACHIEVEMENT_IDS = frozenset(b["id"] for b in ACHIEVEMENT_CATALOG)
# Shareable result cards (SPEC-SHARE-CARD): in-memory result snapshots for OG unfurl links.
SHARE_TTL_SECONDS = int(os.getenv("SHARE_TTL_SECONDS", str(7 * 86400)))
MAX_SHARE_SNAPSHOTS = int(os.getenv("MAX_SHARE_SNAPSHOTS", "500"))
COST_GENERATE = int(os.getenv("COST_GENERATE", "1"))
COST_ROOM = int(os.getenv("COST_ROOM", "10"))
AD_REWARD_TOKENS = int(os.getenv("AD_REWARD_TOKENS", "5"))
MAX_ADS_PER_DAY = int(os.getenv("MAX_ADS_PER_DAY", "5"))
# The /tokens/ad-reward endpoint is a "trust the client" stub with NO ad verification —
# any caller with a device id can farm the daily cap of free sparks (rotate device ids on
# web). It stays OFF until SPEC-ADS server-side verification (SSV) is built. Default false =
# the endpoint 403s. Do NOT flip this true until a verified ad grant replaces the stub.
ADS_ENABLED = os.getenv("ADS_ENABLED", "false").lower() == "true"
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
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")  # DEPRECATED single-pack price; no longer used for checkout
CHECKOUT_RETURN_URL = os.getenv("CHECKOUT_RETURN_URL", "")  # explicit return URL for Stripe checkout

# --- In-App Purchase (RevenueCat) + unified spark tier ladder (SPEC-IAP) ---
# RevenueCat posts a bearer-authed webhook to /webhook/revenuecat. The client SDK keys are public and
# live in the native build (VITE_REVENUECAT_*), not here.
REVENUECAT_WEBHOOK_SECRET = os.getenv("REVENUECAT_WEBHOOK_SECRET", "")

# Single source of truth for spark amounts AND prices on every surface (web Stripe + iOS + Android).
# SKUs / RC ids / amounts / prices deliberately mirror VibePix (server.js PRODUCTS) so the economies can
# merge later. Web checkout builds Stripe `price_data` inline from `price_cents` (VibePix-style) — no
# pre-created Stripe Price objects, no per-tier price env vars. `sparks`/`price_cents` are authoritative;
# never trust client- or webhook-body-supplied amounts.
SPARK_PRODUCTS = {
    "spark_pack_50": {
        "sparks": 50,
        "price_cents": 199,
        "name": "50 Sparks",
        "rc_id": "rc_spark_pack_50",
        "ios": "me.revelryapp.quiz.sparks_50",
        "android": "me.revelryapp.quiz.sparks_50",
    },
    "spark_pack_200": {
        "sparks": 200,
        "price_cents": 499,
        "name": "200 Sparks",
        "rc_id": "rc_spark_pack_200",
        "ios": "me.revelryapp.quiz.sparks_200",
        "android": "me.revelryapp.quiz.sparks_200",
    },
    "spark_pack_500": {
        "sparks": 500,
        "price_cents": 999,
        "name": "500 Sparks",
        "rc_id": "rc_spark_pack_500",
        "ios": "me.revelryapp.quiz.sparks_500",
        "android": "me.revelryapp.quiz.sparks_500",
    },
}

# Reverse lookup: any store/rc product id → sku (built at import time).
SPARK_PRODUCT_BY_ANY_ID = {}
for _sku, _p in SPARK_PRODUCTS.items():
    for _key in ("rc_id", "ios", "android"):
        SPARK_PRODUCT_BY_ANY_ID[_p[_key]] = _sku

# Largest single pack — used to cap webhook-metadata-supplied grant amounts (anti-tamper).
MAX_SPARK_PACK = max(p["sparks"] for p in SPARK_PRODUCTS.values())
DEFAULT_SPARK_SKU = "spark_pack_50"
REMOTE_CONFIG_URL = os.getenv("REMOTE_CONFIG_URL", "")  # e.g. https://games.revelryapp.me/quiz/config.json

# --- Product analytics (PostHog) — see SPEC-ANALYTICS. Backend no-ops unless POSTHOG_API_KEY is set. ---
POSTHOG_API_KEY = os.getenv("POSTHOG_API_KEY", "").strip()  # project write key ("phc_…")
POSTHOG_HOST = os.getenv("POSTHOG_HOST", "https://us.i.posthog.com").strip()

# --- Auth (Phase 2) ---
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_IDS = [
    client_id.strip()
    for client_id in os.getenv("GOOGLE_CLIENT_IDS", GOOGLE_CLIENT_ID).split(",")
    if client_id.strip()
]
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


class RuntimeConfigError(RuntimeError):
    """A fatal environment misconfiguration caught at startup (fail-fast, not a runtime surprise)."""


# Environments that must never run on SQLite. ENVIRONMENT is derived at import time (see top of file);
# note that if DB_BACKEND is misconfigured to sqlite AND LOCALPLAY_ENV/APP_ENV is unset, ENVIRONMENT
# degrades to "local" — which is exactly why the guard below leans primarily on the Supabase-creds
# signal, not on ENVIRONMENT alone.
_DEPLOYED_ENVIRONMENTS = ("gamma", "production")


def validate_runtime_db_config() -> None:
    """Fail fast if a deployment is accidentally pointed at SQLite (or Supabase without credentials).

    SQLite in a deployed container is EPHEMERAL: the DB file lives in the container's writable layer
    and is destroyed on every rebuild unless a volume is mounted, so a gamma/prod container silently
    running on SQLite loses all wallet/purchase data on the next deploy. Supabase is mandatory there.

    The reliable "this is a real deployment" signal is the presence of Supabase credentials — nobody
    sets SUPABASE_URL/SUPABASE_SERVICE_KEY for genuine local SQLite dev. ENVIRONMENT is a secondary
    signal (only meaningful when LOCALPLAY_ENV/APP_ENV is set explicitly). Called at app startup, not
    at import, so the test suite and plain local dev (no Supabase vars) are never affected.
    """
    has_supabase_creds = bool(SUPABASE_URL or SUPABASE_SERVICE_KEY)
    is_named_deploy = ENVIRONMENT in _DEPLOYED_ENVIRONMENTS

    if DB_BACKEND != "supabase" and (has_supabase_creds or is_named_deploy):
        raise RuntimeConfigError(
            f"Refusing to start: DB_BACKEND={DB_BACKEND!r} but this looks like a deployed environment "
            f"(ENVIRONMENT={ENVIRONMENT!r}, SUPABASE_URL set={bool(SUPABASE_URL)}, "
            f"SUPABASE_SERVICE_KEY set={bool(SUPABASE_SERVICE_KEY)}). SQLite in a deployed container is "
            "ephemeral — its data is destroyed on the next container rebuild. Set DB_BACKEND=supabase "
            "(with SUPABASE_URL + SUPABASE_SERVICE_KEY), or, for genuine local SQLite dev, unset the "
            "SUPABASE_* vars and LOCALPLAY_ENV/APP_ENV."
        )

    if DB_BACKEND == "supabase" and not (SUPABASE_URL and SUPABASE_SERVICE_KEY):
        raise RuntimeConfigError(
            "Refusing to start: DB_BACKEND=supabase but SUPABASE_URL and/or SUPABASE_SERVICE_KEY is "
            "missing. The Supabase adapter cannot function without both."
        )
