from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
from pydantic import BaseModel, Field, field_validator
from typing import Any, List, Optional, Dict
from collections import defaultdict
import os
import re
import time
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode, urlparse
import uvicorn
import uuid
import string
import secrets
import base64
import hmac
import hashlib
import logging
import socket as socketlib
import json
import asyncio
import jwt
import httpx

import config
config.setup_logging()

from quiz_engine import quiz_engine, _sanitize_quiz, _validate_quiz, VALID_QUIZ_MODES, DailyLimitExceeded, AIQuotaExceeded
from mlt_engine import mlt_engine, _sanitize_mlt, _validate_mlt
from drawing_engine import drawing_engine, _sanitize_drawing_game, _validate_drawing_game
from housie_engine import DEFAULT_HOUSIE_PATTERNS, default_housie_game, sanitize_patterns
from socket_manager import socket_manager
from image_engine import image_engine
from media_store import media_store
import tokens
import db
import auth
import remote_config
from host_app_catalog_policy import clear_policy_cache, effective_catalog, is_game_allowed

logger = logging.getLogger(__name__)

FRONTEND_DIST_DIR = Path(config.FRONTEND_DIST_DIR)
API_PREFIXES = (
    "/admin",
    "/auth",
    "/checkout",
    "/drawing",
    "/entitlements",
    "/health",
    "/history",
    "/housie",
    "/integrations",
    "/media",
    "/mlt",
    "/providers",
    "/purchases",
    "/quiz",
    "/quiz-packs",
    "/room",
    "/sessions",
    "/sd",
    "/system",
    "/tokens",
    "/webhook",
    "/ws",
)


def _frontend_index_path() -> Path:
    return FRONTEND_DIST_DIR / "index.html"


def _has_frontend_build() -> bool:
    return _frontend_index_path().is_file()


def _is_api_path(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix + "/") for prefix in API_PREFIXES)


def _frontend_file_response(full_path: str):
    if not _has_frontend_build():
        raise HTTPException(status_code=404, detail="Not found")

    frontend_root = FRONTEND_DIST_DIR.resolve()
    candidate = (frontend_root / full_path).resolve()
    try:
        candidate.relative_to(frontend_root)
    except ValueError:
        return FileResponse(_frontend_index_path())

    if candidate.is_file():
        return FileResponse(candidate)
    if full_path == "assets" or full_path.startswith("assets/"):
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(_frontend_index_path())


def _check_secret_strength():
    """Warn on weak or missing secrets at startup."""
    warnings = []
    if config.JWT_SECRET and len(config.JWT_SECRET) < 32:
        warnings.append("JWT_SECRET is too short (< 32 chars) — sessions may be forgeable")
    if config.STRIPE_WEBHOOK_SECRET and not config.STRIPE_WEBHOOK_SECRET.startswith("whsec_"):
        warnings.append("STRIPE_WEBHOOK_SECRET doesn't look like a Stripe webhook secret")
    if ADMIN_API_KEY and len(ADMIN_API_KEY) < 16:
        warnings.append("ADMIN_API_KEY is too short (< 16 chars) — easily guessable")
    for w in warnings:
        logger.warning("SECRET CHECK: %s", w)
    return warnings


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting LocalPlay backend")
    _check_secret_strength()
    db.init_db()
    await remote_config.init()
    socket_manager.start_cleanup_loop()
    yield
    logger.info("Shutting down LocalPlay backend")
    socket_manager.stop_cleanup_loop()


app = FastAPI(title="AI Quiz Game Backend", lifespan=lifespan)


def get_local_ip():
    try:
        s = socketlib.socket(socketlib.AF_INET, socketlib.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            return ip
        finally:
            s.close()
    except Exception:
        return "127.0.0.1"


@app.get("/system/info")
async def get_system_info(req: Request):
    """Internal IP info — always requires admin key."""
    if not ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Admin API key not configured")
    _check_admin(req)
    return {"ip": get_local_ip()}


# In-memory rate limiter
_rate_limit_store: Dict[str, list] = defaultdict(list)

# Global LLM call budget — protects API bill regardless of IP count
_llm_call_timestamps: list = []

# Stripe webhook event dedup — prevents double-processing on retries
# Webhook event dedup moved to db.webhook_events table


def _get_client_ip(req: Request) -> str:
    """Get real client IP, accounting for reverse proxy headers.

    Only trusts X-Forwarded-For / X-Real-IP when TRUST_PROXY_HEADERS is enabled,
    preventing attackers from spoofing their IP to bypass rate limits.
    """
    if config.TRUST_PROXY_HEADERS:
        forwarded = req.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = req.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()
    return req.client.host if req.client else "unknown"


def _check_rate_limit(client_ip: str) -> bool:
    """Return True if the request is allowed, False if rate-limited."""
    now = time.time()
    window = config.RATE_LIMIT_WINDOW
    # Prune old entries
    _rate_limit_store[client_ip] = [
        t for t in _rate_limit_store[client_ip] if now - t < window
    ]
    if len(_rate_limit_store[client_ip]) >= config.RATE_LIMIT_MAX_REQUESTS:
        return False
    _rate_limit_store[client_ip].append(now)
    return True


def _check_llm_budget() -> bool:
    """Return True if global LLM call budget allows another call. 0 = unlimited."""
    if config.MAX_LLM_CALLS_PER_HOUR <= 0:
        return True
    now = time.time()
    cutoff = now - 3600
    _llm_call_timestamps[:] = [t for t in _llm_call_timestamps if t > cutoff]
    if len(_llm_call_timestamps) >= config.MAX_LLM_CALLS_PER_HOUR:
        logger.warning("LLM budget exhausted: %d/%d calls in the last hour", len(_llm_call_timestamps), config.MAX_LLM_CALLS_PER_HOUR)
        return False
    _llm_call_timestamps.append(now)
    return True


# In-memory storage with timestamps for cleanup
quizzes: Dict[str, dict] = {}  # quiz_id -> quiz_data
quiz_timestamps: Dict[str, float] = {}  # quiz_id -> creation time
quiz_images: Dict[str, Dict[int, str]] = {}  # quiz_id -> {question_id: base64_image}
quiz_image_assets: Dict[str, Dict[int, str]] = {}  # quiz_id -> {question_id: media asset id}

# MLT (Most Likely To) storage
mlt_scenarios: Dict[str, dict] = {}  # scenario_id -> {game_title, statements}
mlt_timestamps: Dict[str, float] = {}  # scenario_id -> creation time

# DrawingGame storage
drawing_games: Dict[str, dict] = {}  # drawing_id -> {game_title, prompts}
drawing_timestamps: Dict[str, float] = {}  # drawing_id -> creation time

# Housie storage
housie_games: Dict[str, dict] = {}  # housie_id -> {game_title, patterns, caller settings}
housie_timestamps: Dict[str, float] = {}  # housie_id -> creation time

# Content ownership: content_id -> wallet_id of creator
content_owners: Dict[str, str] = {}
pending_generation_charges: Dict[str, str] = {}  # content_id -> wallet_id to charge when first room is created


def _check_content_owner(content_id: str, wallet_id: str):
    """Raise 403 if wallet_id doesn't own this content."""
    owner = content_owners.get(content_id)
    if owner and owner != wallet_id:
        raise HTTPException(status_code=403, detail="You don't have permission to modify this content")


def _evict_old_content():
    """Evict oldest generated content if storage limit exceeded, and expire stale items."""
    # Content IDs currently in use by active rooms — never evict these
    active_content_ids = {room.content_id for room in socket_manager.rooms.values() if room.content_id}
    now = time.time()

    # Evict quizzes
    expired = [qid for qid, ts in quiz_timestamps.items()
               if now - ts > config.QUIZ_TTL_SECONDS and qid not in active_content_ids]
    for qid in expired:
        quizzes.pop(qid, None)
        quiz_timestamps.pop(qid, None)
        quiz_images.pop(qid, None)
        quiz_image_assets.pop(qid, None)
        content_owners.pop(qid, None)
        pending_generation_charges.pop(qid, None)
    # Evict oldest non-active quizzes until under limit
    if len(quizzes) >= config.MAX_QUIZZES:
        for qid in sorted(quiz_timestamps, key=quiz_timestamps.get):
            if len(quizzes) < config.MAX_QUIZZES:
                break
            if qid not in active_content_ids:
                quizzes.pop(qid, None)
                quiz_timestamps.pop(qid, None)
                quiz_images.pop(qid, None)
                quiz_image_assets.pop(qid, None)
                content_owners.pop(qid, None)
                pending_generation_charges.pop(qid, None)

    # Evict MLT scenarios
    expired_mlt = [sid for sid, ts in mlt_timestamps.items()
                   if now - ts > config.QUIZ_TTL_SECONDS and sid not in active_content_ids]
    for sid in expired_mlt:
        mlt_scenarios.pop(sid, None)
        mlt_timestamps.pop(sid, None)
        content_owners.pop(sid, None)
        pending_generation_charges.pop(sid, None)
    if len(mlt_scenarios) >= config.MAX_QUIZZES:
        for sid in sorted(mlt_timestamps, key=mlt_timestamps.get):
            if len(mlt_scenarios) < config.MAX_QUIZZES:
                break
            if sid not in active_content_ids:
                mlt_scenarios.pop(sid, None)
                mlt_timestamps.pop(sid, None)
                content_owners.pop(sid, None)
                pending_generation_charges.pop(sid, None)

    # Evict DrawingGame prompt sets
    expired_drawing = [did for did, ts in drawing_timestamps.items()
                       if now - ts > config.QUIZ_TTL_SECONDS and did not in active_content_ids]
    for did in expired_drawing:
        drawing_games.pop(did, None)
        drawing_timestamps.pop(did, None)
        content_owners.pop(did, None)
        pending_generation_charges.pop(did, None)
    if len(drawing_games) >= config.MAX_QUIZZES:
        for did in sorted(drawing_timestamps, key=drawing_timestamps.get):
            if len(drawing_games) < config.MAX_QUIZZES:
                break
            if did not in active_content_ids:
                drawing_games.pop(did, None)
                drawing_timestamps.pop(did, None)
                content_owners.pop(did, None)
                pending_generation_charges.pop(did, None)

    # Evict Housie games
    expired_housie = [hid for hid, ts in housie_timestamps.items()
                      if now - ts > config.QUIZ_TTL_SECONDS and hid not in active_content_ids]
    for hid in expired_housie:
        housie_games.pop(hid, None)
        housie_timestamps.pop(hid, None)
        content_owners.pop(hid, None)
        pending_generation_charges.pop(hid, None)
    if len(housie_games) >= config.MAX_QUIZZES:
        for hid in sorted(housie_timestamps, key=housie_timestamps.get):
            if len(housie_games) < config.MAX_QUIZZES:
                break
            if hid not in active_content_ids:
                housie_games.pop(hid, None)
                housie_timestamps.pop(hid, None)
                content_owners.pop(hid, None)
                pending_generation_charges.pop(hid, None)

def generate_room_code() -> str:
    """Generate a unique 6-character room code, checking for collisions."""
    for _ in range(config.MAX_ROOM_CODE_ATTEMPTS):
        code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
        if code not in socket_manager.rooms:
            return code
    raise RuntimeError("Failed to generate unique room code")


class QuizRequest(BaseModel):
    prompt: str
    difficulty: str = "medium"
    num_questions: int = config.DEFAULT_NUM_QUESTIONS
    provider: str = ""
    mode: str = "classic"

    @field_validator('prompt')
    @classmethod
    def validate_prompt(cls, v: str) -> str:
        # Strip null bytes and control characters (keep newlines, tabs)
        v = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', v)
        # Strip HTML tags to prevent XSS
        v = re.sub(r'<[^>]+>', '', v)
        v = v.strip()
        if not v or len(v) > config.MAX_PROMPT_LENGTH:
            raise ValueError(f'Prompt must be 1-{config.MAX_PROMPT_LENGTH} characters')
        # Block prompt injection patterns (case-insensitive)
        injection_patterns = [
            r'ignore\s+(all\s+)?previous\s+instructions',
            r'ignore\s+(all\s+)?above',
            r'disregard\s+(all\s+)?previous',
            r'you\s+are\s+now\s+(?:a|an|in)',
            r'new\s+instructions?\s*:',
            r'system\s*:\s*',
            r'<\s*/?script',
            r'javascript\s*:',
        ]
        lower_v = v.lower()
        for pattern in injection_patterns:
            if re.search(pattern, lower_v):
                raise ValueError('Prompt contains disallowed content')
        return v

    @field_validator('difficulty')
    @classmethod
    def validate_difficulty(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in config.VALID_DIFFICULTIES:
            raise ValueError(f'Difficulty must be one of: {", ".join(config.VALID_DIFFICULTIES)}')
        return v

    @field_validator('num_questions')
    @classmethod
    def validate_num_questions(cls, v: int) -> int:
        if v < config.MIN_QUESTIONS or v > config.MAX_QUESTIONS:
            raise ValueError(f'Number of questions must be {config.MIN_QUESTIONS}-{config.MAX_QUESTIONS}')
        return v

    @field_validator('mode')
    @classmethod
    def validate_mode(cls, v: str) -> str:
        v = (v or "classic").lower().strip()
        if v not in VALID_QUIZ_MODES:
            raise ValueError(f'Mode must be one of: {", ".join(VALID_QUIZ_MODES)}')
        return v


class RoomCreateRequest(BaseModel):
    quiz_id: str = ""      # For quiz game
    mlt_id: str = ""       # For MLT game
    drawing_id: str = ""   # For DrawingGame
    housie_id: str = ""    # For Housie
    game_type: str = "quiz"
    time_limit: Optional[int] = None

    @field_validator('time_limit')
    @classmethod
    def validate_time_limit(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return v
        if v < 5 or v > 60:
            raise ValueError('Time limit must be between 5 and 60 seconds')
        return v

    @field_validator('game_type')
    @classmethod
    def validate_game_type(cls, v: str) -> str:
        if v not in ("quiz", "wmlt", "drawing", "housie"):
            raise ValueError('game_type must be "quiz", "wmlt", "drawing", or "housie"')
        return v


GAME_CATALOG = [
    {
        "id": "quiz",
        "game_type": "quiz",
        "runtime_type": "quiz",
        "title": "AI Quiz",
        "description": "A fast trivia room with multiple-choice questions.",
        "launchable": True,
        "host_app_supported": True,
        "supported_host_apps": ["revelry"],
        "supports_ai_generation": True,
        "supports_custom_content": True,
        "supports_images": True,
        "can_create_content": True,
        "can_edit_content": True,
        "can_quick_start": True,
        "creation_modes": ["manual", "ai"],
        "default_content_available": True,
        "embedded_authoring_supported": True,
        "content_schema": {
            "kind": "quiz",
            "question_count": {"min": 1, "max": 50},
            "supported_media": ["image"],
        },
    },
    {
        "id": "wmlt",
        "game_type": "wmlt",
        "runtime_type": "wmlt",
        "title": "Most Likely To",
        "description": "Vote on who best matches each prompt.",
        "launchable": True,
        "host_app_supported": True,
        "supported_host_apps": ["revelry"],
        "supports_custom_content": True,
        "supports_images": False,
        "can_create_content": True,
        "can_edit_content": True,
        "can_quick_start": False,
        "supports_ai_generation": True,
        "creation_modes": ["template", "manual", "ai"],
        "default_content_available": True,
        "embedded_authoring_supported": False,
        "content_schema": {
            "kind": "prompt_list",
            "prompt_count": {"min": 1, "max": 50},
            "supported_media": [],
        },
    },
    {
        "id": "drawing",
        "game_type": "drawing",
        "runtime_type": "drawing",
        "title": "Drawing Game",
        "description": "Draw secret prompts while everyone guesses.",
        "launchable": True,
        "host_app_supported": True,
        "supported_host_apps": ["revelry"],
        "supports_custom_content": True,
        "supports_images": False,
        "can_create_content": True,
        "can_edit_content": True,
        "can_quick_start": False,
        "supports_ai_generation": True,
        "creation_modes": ["template", "manual", "ai"],
        "default_content_available": True,
        "embedded_authoring_supported": False,
        "content_schema": {
            "kind": "prompt_list",
            "prompt_count": {"min": 1, "max": 50},
            "supported_media": [],
        },
        "config_schema": {
            "time_limit": {"min": 5, "max": 60, "default": 30},
        },
    },
    {
        "id": "housie",
        "game_type": "housie",
        "runtime_type": "housie",
        "title": "Housie",
        "description": "Classic 90-ball number calling with tickets and prize claims.",
        "launchable": True,
        "host_app_supported": False,
        "supported_host_apps": [],
        "supports_custom_content": True,
        "supports_images": False,
        "can_create_content": True,
        "can_edit_content": True,
        "can_quick_start": True,
        "supports_ai_generation": False,
        "creation_modes": ["manual", "template"],
        "default_content_available": True,
        "embedded_authoring_supported": False,
        "content_schema": {
            "kind": "housie_setup",
            "ticket_layout": "housie_3x9_15",
            "number_range": {"min": 1, "max": 90},
            "patterns": [pattern["id"] for pattern in DEFAULT_HOUSIE_PATTERNS],
            "play_modes": ["beginner", "pro"],
            "caller_modes": ["manual", "auto"],
            "claim_requires_latest_call": True,
            "supported_media": [],
        },
    },
]


def _default_time_limit_for_game(game_type: str) -> int:
    return 30 if game_type == "drawing" else config.DEFAULT_TIME_LIMIT


def _sanitize_housie_game(game: dict) -> dict:
    title = str(game.get("game_title") or game.get("title") or "Housie").strip()[:120] or "Housie"
    pattern_ids = sanitize_patterns(game.get("pattern_ids") or [p.get("id") for p in game.get("patterns", []) if isinstance(p, dict)])
    pattern_map = {p["id"]: p for p in DEFAULT_HOUSIE_PATTERNS}
    patterns = [dict(pattern_map[pid]) for pid in pattern_ids if pid in pattern_map]
    caller_mode = str(game.get("caller_mode") or "manual").strip().lower()
    if caller_mode not in ("manual", "auto"):
        caller_mode = "manual"
    play_mode = str(game.get("play_mode") or "beginner").strip().lower()
    if play_mode not in ("beginner", "pro"):
        play_mode = "beginner"
    try:
        auto_interval = int(game.get("auto_interval_seconds") or 8)
    except (TypeError, ValueError):
        auto_interval = 8
    return {
        "game_title": title,
        "layout": "housie_3x9_15",
        "deck": game.get("deck") if isinstance(game.get("deck"), list) else default_housie_game(title)["deck"],
        "patterns": patterns,
        "play_mode": play_mode,
        "caller_mode": caller_mode,
        "auto_interval_seconds": max(3, min(30, auto_interval)),
        "auto_pause_on_claim": bool(game.get("auto_pause_on_claim", True)),
        "claim_requires_latest_call": True,
    }


def _now_ts() -> int:
    return int(time.time())


def _iso(ts: Optional[int]) -> Optional[str]:
    if not ts:
        return None
    if isinstance(ts, str):
        return ts
    return datetime.fromtimestamp(int(ts), timezone.utc).isoformat().replace("+00:00", "Z")


def _public_base_url(req: Request) -> str:
    configured = config.PUBLIC_BASE_URL
    if configured:
        return configured
    return str(req.base_url).rstrip("/")


def _default_game_content(game_type: str, title: str) -> tuple[str, dict]:
    if game_type == "housie":
        return str(uuid.uuid4()), default_housie_game(title or "Housie")
    if game_type == "wmlt":
        return str(uuid.uuid4()), {
            "game_title": title or "Most Likely To",
            "statements": [
                {"id": 1, "text": "Most likely to start the dance floor"},
                {"id": 2, "text": "Most likely to remember every tiny detail"},
                {"id": 3, "text": "Most likely to make everyone laugh"},
            ],
        }
    if game_type == "drawing":
        return str(uuid.uuid4()), {
            "game_title": title or "Drawing Game",
            "prompts": [
                {"id": 1, "text": "birthday cake", "aliases": ["cake"]},
                {"id": 2, "text": "dance party", "aliases": ["party"]},
                {"id": 3, "text": "confetti", "aliases": []},
            ],
        }
    return str(uuid.uuid4()), {
        "quiz_title": title or "Party Quiz",
        "questions": [
            {"id": 1, "text": "What is the best kind of party snack?", "options": ["Chips", "Napkins", "Ice cubes", "Plates"], "answer_index": 0, "image_prompt": ""},
            {"id": 2, "text": "How many points is a correct answer worth by default?", "options": ["1", "10", "100", "1000"], "answer_index": 2, "image_prompt": ""},
            {"id": 3, "text": "What should players do first?", "options": ["Join the room", "Close the tab", "Mute everyone", "Hide the QR code"], "answer_index": 0, "image_prompt": ""},
        ],
    }


def _resolve_runtime_content(game_type: str, content_id: str = "", title: str = "") -> tuple[str, dict]:
    if game_type == "wmlt":
        if content_id:
            if content_id not in mlt_scenarios:
                raise HTTPException(status_code=404, detail="MLT scenario not found")
            return content_id, mlt_scenarios[content_id]
        return _default_game_content(game_type, title)
    if game_type == "drawing":
        if content_id:
            if content_id not in drawing_games:
                raise HTTPException(status_code=404, detail="Drawing game not found")
            return content_id, drawing_games[content_id]
        return _default_game_content(game_type, title)
    if game_type == "housie":
        if content_id:
            if content_id not in housie_games:
                raise HTTPException(status_code=404, detail="Housie game not found")
            return content_id, housie_games[content_id]
        return _default_game_content(game_type, title)
    if content_id:
        if content_id not in quizzes:
            raise HTTPException(status_code=404, detail="Quiz not found")
        return content_id, quizzes[content_id]
    return _default_game_content("quiz", title)


def _resolve_revelry_runtime_content(
    context: Any,
    game_type: str,
    content_id: str = "",
    title: str = "",
) -> tuple[str, dict]:
    wallet_id = _revelry_party_wallet_id(context.external_container_id)
    if game_type == "quiz" and content_id and content_id not in quizzes:
        pack = db.get_quiz_pack(wallet_id, content_id)
        if not pack:
            raise HTTPException(status_code=404, detail="Quiz content not found for this party")
        quiz_data = _sanitize_quiz(_pack_to_quiz(pack))
        if not _validate_quiz(quiz_data, attempt=0):
            raise HTTPException(status_code=422, detail="Invalid quiz content")
        quizzes[content_id] = quiz_data
        quiz_timestamps[content_id] = time.time()
        content_owners[content_id] = wallet_id
        return content_id, quiz_data
    if game_type in ("wmlt", "drawing", "housie") and content_id:
        if game_type == "wmlt" and content_id in mlt_scenarios:
            return content_id, mlt_scenarios[content_id]
        if game_type == "drawing" and content_id in drawing_games:
            return content_id, drawing_games[content_id]
        if game_type == "housie" and content_id in housie_games:
            return content_id, housie_games[content_id]
        content = db.get_game_content(wallet_id, content_id)
        if not content or content.get("game_type") != game_type:
            raise HTTPException(status_code=404, detail="Game content not found for this party")
        payload = _game_content_payload(content)
        game_data = payload.get("game") if isinstance(payload.get("game"), dict) else payload
        if not isinstance(game_data, dict):
            raise HTTPException(status_code=422, detail="Invalid game content")
        if game_type == "wmlt":
            game_data = _sanitize_mlt(game_data)
            if not _validate_mlt(game_data, attempt=0):
                raise HTTPException(status_code=422, detail="Invalid Most Likely To content")
            mlt_scenarios[content_id] = game_data
            mlt_timestamps[content_id] = time.time()
        elif game_type == "drawing":
            game_data = _sanitize_drawing_game(game_data)
            if not _validate_drawing_game(game_data, attempt=0):
                raise HTTPException(status_code=422, detail="Invalid drawing game content")
            if payload.get("time_limit"):
                game_data["time_limit"] = int(payload["time_limit"])
            drawing_games[content_id] = game_data
            drawing_timestamps[content_id] = time.time()
        else:
            game_data = _sanitize_housie_game(game_data)
            housie_games[content_id] = game_data
            housie_timestamps[content_id] = time.time()
        content_owners[content_id] = wallet_id
        return content_id, game_data
    return _resolve_runtime_content(game_type, content_id, title)


def _create_runtime_room(
    game_type: str,
    content_id: str,
    game_data: dict,
    wallet_id: str,
    time_limit: int,
    billing_mode: str = "localplay_sparks",
) -> tuple[str, str]:
    if game_type == "wmlt" and not game_data.get("statements"):
        raise HTTPException(status_code=422, detail="Game has no statements")
    if game_type == "drawing" and not game_data.get("prompts"):
        raise HTTPException(status_code=422, detail="Drawing game has no prompts")
    if game_type == "housie" and not game_data.get("patterns"):
        raise HTTPException(status_code=422, detail="Housie game has no prize patterns")
    if game_type == "quiz" and not game_data.get("questions"):
        raise HTTPException(status_code=422, detail="Quiz has no questions")
    if len(socket_manager.rooms) >= config.MAX_ROOMS:
        raise HTTPException(status_code=429, detail="Too many active rooms. Please try again later.")

    room_code = generate_room_code()
    organizer_token = secrets.token_urlsafe(32)

    import copy
    game_data = copy.deepcopy(game_data)
    if game_type == "quiz" and content_id in quiz_images:
        for question in game_data["questions"]:
            asset_id = quiz_image_assets.get(content_id, {}).get(question["id"])
            if asset_id:
                asset = media_store.get_asset(asset_id)
                if asset:
                    question["image_asset_id"] = asset.id
                    question["image_url"] = asset.url
                    question["image_alt"] = asset.alt_text
                    continue
            if question["id"] in quiz_images[content_id]:
                question["image_url"] = f"/quiz/{content_id}/image/{question['id']}"

    room = socket_manager.create_room(
        room_code,
        game_data,
        time_limit,
        organizer_token=organizer_token,
        content_id=content_id,
        game_type=game_type,
        billing_mode=billing_mode,
    )
    room.wallet_id = wallet_id
    logger.info("Room created: %s (type=%s)", room_code, game_type)
    return room_code, organizer_token


def _settle_pending_generation_charge(content_id: str, wallet_id: str, room_code: str = ""):
    """Charge generated AI content only after it becomes playable."""
    pending_wallet_id = pending_generation_charges.get(content_id)
    if not pending_wallet_id:
        return
    if pending_wallet_id != wallet_id:
        raise HTTPException(status_code=403, detail="You don't have permission to use this generated content")
    spent, _ = tokens.spend_generate(wallet_id)
    if not spent:
        if room_code:
            socket_manager.rooms.pop(room_code, None)
        raise HTTPException(status_code=402, detail=f"You need {config.COST_GENERATE} token to use generated content. Buy tokens or watch an ad!")
    pending_generation_charges.pop(content_id, None)


class ImageGenerateRequest(BaseModel):
    quiz_id: str
    question_id: Optional[int] = None  # If None, generate for all questions


def _quiz_authoring_wallet_id(req: Request) -> str:
    has_authoring_credential = bool(
        (req.headers.get("authorization") or "").strip().lower().startswith("bearer ")
        or (req.query_params.get("authoring_token") or "").strip()
    )
    claims = _authoring_claims_from_request(req) if has_authoring_credential else None
    if not claims:
        return tokens.get_wallet_id(req)
    if claims.get("game_type") != "quiz":
        raise HTTPException(status_code=422, detail="game_type does not match authoring token")
    launch_context = claims["launch_context"]
    actor = _actor_from_launch_context(launch_context)
    if not _author_can_author(actor):
        raise HTTPException(status_code=403, detail="Missing capability to author content")
    context = _external_context_from_launch_context(launch_context)
    if context.host_app != "revelry":
        raise HTTPException(status_code=422, detail="Unsupported host_app")
    return _revelry_party_wallet_id(context.external_container_id)


def _store_quiz_image_asset(quiz_id: str, question: dict, image_b64: str, wallet_id: str):
    """Store a generated quiz image in the shared media layer and legacy map."""
    qid = int(question["id"])
    quiz_images.setdefault(quiz_id, {})[qid] = image_b64
    asset = media_store.create_generated_image(
        image_b64,
        owner_wallet_id=wallet_id,
        provider="stable_diffusion",
        prompt=question.get("image_prompt") or question.get("text") or "",
        alt_text=question.get("text") or question.get("image_prompt") or "Generated quiz image",
        ttl_seconds=config.QUIZ_TTL_SECONDS,
    )
    quiz_image_assets.setdefault(quiz_id, {})[qid] = asset.id
    question["image_asset_id"] = asset.id
    question["image_url"] = asset.url
    question["image_alt"] = asset.alt_text
    return asset


@app.get("/providers")
async def get_providers():
    return {"providers": await quiz_engine.get_available_providers()}


@app.post("/quiz/generate")
async def generate_quiz(request: QuizRequest, req: Request):
    client_ip = _get_client_ip(req)
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait before generating another quiz.")
    device_id = tokens.get_device_id(req)
    if not device_id:
        raise HTTPException(status_code=400, detail="X-Device-Id header is required")
    idem_key = tokens.get_idempotency_key(req)

    # Idempotency: return cached result if this request was already processed.
    # If the generated content aged out of process memory, do not regenerate and
    # charge again for the same idempotency key.
    if idem_key:
        cached_id = db.check_idempotency(idem_key, device_id)
        if cached_id:
            if cached_id in quizzes:
                return {"quiz_id": cached_id, "quiz": _strip_answers(quizzes[cached_id])}
            raise HTTPException(
                status_code=409,
                detail="Request was already processed, but the generated quiz is no longer available. Please start a new request.",
            )

    # Resolve wallet and check token balance
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=400, detail="X-Device-Id header is required")
    tokens.ensure_wallet(wallet_id)
    if not tokens.can_generate(wallet_id):
        raise HTTPException(status_code=402, detail=f"You need {config.COST_GENERATE} token to generate. Buy tokens or watch an ad!")

    if not _check_llm_budget():
        raise HTTPException(status_code=503, detail="Server is busy. Please try again later.")

    await remote_config.get_config()  # refresh if stale
    provider = request.provider or remote_config.get_provider()
    model_override = remote_config.get_paid_model() if tokens.use_premium_model(wallet_id) else remote_config.get_free_model()
    try:
        quiz_data = await quiz_engine.generate_quiz(
            request.prompt,
            request.difficulty,
            request.num_questions,
            provider,
            model_override=model_override,
            mode=request.mode,
        )
    except DailyLimitExceeded:
        raise HTTPException(status_code=429, detail="Daily quiz limit reached. Please try again tomorrow!")
    except AIQuotaExceeded:
        raise HTTPException(status_code=503, detail="Free tier limit reached. Upgrade for unlimited games.")
    if not quiz_data:
        raise HTTPException(status_code=500, detail="Failed to generate quiz")

    _evict_old_content()
    quiz_id = str(uuid.uuid4())
    quizzes[quiz_id] = quiz_data
    quiz_timestamps[quiz_id] = time.time()
    content_owners[quiz_id] = wallet_id
    pending_generation_charges[quiz_id] = wallet_id
    if idem_key:
        db.record_idempotency(idem_key, device_id, quiz_id)
    logger.info("Quiz created: %s ('%s') owner=%s", quiz_id, quiz_data.get("quiz_title", "Untitled"), wallet_id[:8])
    return {"quiz_id": quiz_id, "quiz": _strip_answers(quiz_data)}


def _strip_answers(quiz_data: dict) -> dict:
    """Return a copy of quiz data with answer_index removed from questions."""
    stripped = {**quiz_data}
    stripped["questions"] = [
        {k: v for k, v in q.items() if k != "answer_index"}
        for q in quiz_data.get("questions", [])
    ]
    return stripped


def _pack_to_quiz(pack: dict) -> dict:
    return {
        "quiz_title": pack.get("title", "Custom Quiz"),
        "questions": [
            {
                "id": index + 1,
                "text": q.get("text", ""),
                "options": q.get("options", []),
                "answer_index": q.get("answer_index", 0),
                "image_prompt": "",
                **({"image_asset_id": q["image_asset_id"]} if q.get("image_asset_id") else {}),
                **({"image_url": q["image_url"]} if q.get("image_url") else {}),
                **({"image_alt": q["image_alt"]} if q.get("image_alt") else {}),
            }
            for index, q in enumerate(pack.get("questions", []))
        ],
    }


@app.get("/quiz/{quiz_id}")
async def get_quiz(quiz_id: str):
    if quiz_id not in quizzes:
        raise HTTPException(status_code=404, detail="Quiz not found")
    return _strip_answers(quizzes[quiz_id])


class QuizPackSaveRequest(BaseModel):
    pack_id: Optional[str] = None
    quiz: dict

    @field_validator('quiz')
    @classmethod
    def validate_quiz(cls, v: dict) -> dict:
        QuizImportRequest.validate_quiz(v)
        return v


@app.get("/quiz-packs")
async def list_custom_quiz_packs(req: Request):
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {"packs": db.list_quiz_packs(wallet_id)}


@app.post("/quiz-packs")
async def save_custom_quiz_pack(request: QuizPackSaveRequest, req: Request):
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    quiz_data = _sanitize_quiz(request.quiz)
    if not _validate_quiz(quiz_data, attempt=0):
        raise HTTPException(status_code=422, detail="Invalid quiz data")
    pack = db.save_quiz_pack(wallet_id, quiz_data.get("quiz_title", "Custom Quiz"), quiz_data["questions"], request.pack_id)
    return {"pack": pack}


@app.get("/quiz-packs/{pack_id}")
async def get_custom_quiz_pack(pack_id: str, req: Request):
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    pack = db.get_quiz_pack(wallet_id, pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="Quiz pack not found")
    return {"pack": pack, "quiz": _pack_to_quiz(pack)}


@app.delete("/quiz-packs/{pack_id}")
async def delete_custom_quiz_pack(pack_id: str, req: Request):
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not db.delete_quiz_pack(wallet_id, pack_id):
        raise HTTPException(status_code=404, detail="Quiz pack not found")
    return {"status": "deleted"}


@app.post("/quiz-packs/{pack_id}/materialize")
async def materialize_custom_quiz_pack(pack_id: str, req: Request):
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    pack = db.get_quiz_pack(wallet_id, pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="Quiz pack not found")
    quiz_data = _sanitize_quiz(_pack_to_quiz(pack))
    if not _validate_quiz(quiz_data, attempt=0):
        raise HTTPException(status_code=422, detail="Invalid quiz pack")
    _evict_old_content()
    quiz_id = str(uuid.uuid4())
    quizzes[quiz_id] = quiz_data
    quiz_timestamps[quiz_id] = time.time()
    content_owners[quiz_id] = wallet_id
    return {"quiz_id": quiz_id, "quiz": _strip_answers(quiz_data)}


class QuizUpdateRequest(BaseModel):
    quiz_title: str
    questions: list

    @field_validator('questions')
    @classmethod
    def validate_questions(cls, v: list) -> list:
        if len(v) == 0:
            raise ValueError('Quiz must have at least 1 question')
        for q in v:
            if not isinstance(q, dict):
                raise ValueError('Each question must be an object')
            if not all(k in q for k in ('id', 'text', 'options', 'answer_index')):
                raise ValueError('Question missing required fields')
            opts = q['options']
            if not isinstance(opts, list) or len(opts) not in (2, 4):
                raise ValueError('Question must have 2 or 4 options')
            if not all(isinstance(opt, str) for opt in opts):
                raise ValueError('Each option must be a string')
            if not isinstance(q['answer_index'], int) or not (0 <= q['answer_index'] < len(opts)):
                raise ValueError('Invalid answer_index')
        return v


@app.put("/quiz/{quiz_id}")
async def update_quiz(quiz_id: str, request: QuizUpdateRequest, req: Request):
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    if quiz_id not in quizzes:
        raise HTTPException(status_code=404, detail="Quiz not found")
    _check_content_owner(quiz_id, wallet_id)
    quiz_data = {"quiz_title": request.quiz_title, "questions": request.questions}
    quiz_data = _sanitize_quiz(quiz_data)
    quizzes[quiz_id] = quiz_data
    logger.info("Quiz updated: %s ('%s'), %d questions", quiz_id, quiz_data["quiz_title"], len(quiz_data["questions"]))
    return {"quiz_id": quiz_id, "quiz": _strip_answers(quizzes[quiz_id])}


@app.delete("/quiz/{quiz_id}/question/{question_id}")
async def delete_question(quiz_id: str, question_id: int, req: Request):
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    if quiz_id not in quizzes:
        raise HTTPException(status_code=404, detail="Quiz not found")
    _check_content_owner(quiz_id, wallet_id)
    quiz = quizzes[quiz_id]
    remaining = [q for q in quiz["questions"] if q["id"] != question_id]
    if len(remaining) == len(quiz["questions"]):
        raise HTTPException(status_code=404, detail="Question not found")
    if len(remaining) == 0:
        raise HTTPException(status_code=400, detail="Cannot delete the last question")
    quiz["questions"] = remaining
    logger.info("Question %d deleted from quiz %s", question_id, quiz_id)
    return {"quiz_id": quiz_id, "quiz": _strip_answers(quiz)}


@app.post("/quiz/generate-images")
async def generate_quiz_images(request: ImageGenerateRequest, req: Request):
    """Generate images for quiz questions using the shared media layer."""
    wallet_id = _quiz_authoring_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    client_ip = _get_client_ip(req)
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait.")
    if request.quiz_id not in quizzes:
        raise HTTPException(status_code=404, detail="Quiz not found")
    _check_content_owner(request.quiz_id, wallet_id)

    if not await image_engine.is_available():
        raise HTTPException(status_code=503, detail="Stable Diffusion not available. Start the SD WebUI server.")

    quiz = quizzes[request.quiz_id]

    if request.question_id is not None:
        question = next((q for q in quiz["questions"] if q["id"] == request.question_id), None)
        if not question:
            raise HTTPException(status_code=404, detail="Question not found")

        image = await image_engine.generate_image(question.get("image_prompt", question["text"]))
        if image:
            asset = _store_quiz_image_asset(request.quiz_id, question, image, wallet_id)
            return {"status": "success", "question_id": request.question_id, "asset": asset.to_dict()}
        raise HTTPException(status_code=500, detail="Image generation failed")
    else:
        generated_count = 0
        assets = []
        for question in quiz["questions"]:
            prompt = question.get("image_prompt") or question.get("text")
            if not prompt:
                continue
            image = await image_engine.generate_image(prompt)
            if image:
                asset = _store_quiz_image_asset(request.quiz_id, question, image, wallet_id)
                asset_payload = asset.to_dict()
                asset_payload["question_id"] = question["id"]
                assets.append(asset_payload)
                generated_count += 1
        return {"status": "success", "generated_count": generated_count, "assets": assets}


@app.get("/quiz/{quiz_id}/image/{question_id}")
async def get_question_image(quiz_id: str, question_id: int):
    """Legacy quiz image route. New code should prefer /media/{asset_id}."""
    asset_id = quiz_image_assets.get(quiz_id, {}).get(question_id)
    if asset_id:
        asset = media_store.get_asset(asset_id)
        image_bytes = media_store.get_image_bytes(asset_id)
        if asset and image_bytes:
            return Response(content=image_bytes, media_type=asset.mime_type)

    if quiz_id not in quiz_images or question_id not in quiz_images[quiz_id]:
        raise HTTPException(status_code=404, detail="Image not found")

    image_data = quiz_images[quiz_id][question_id]
    try:
        image_bytes = base64.b64decode(image_data)
    except Exception:
        raise HTTPException(status_code=500, detail="Corrupt image data")
    return Response(content=image_bytes, media_type="image/png")


@app.get("/media/status")
async def media_status():
    """Report shared media platform capabilities."""
    generation_available = await image_engine.is_available()
    upload_available = bool(config.MEDIA_UPLOAD_URL and config.MEDIA_PUBLIC_BASE_URL and config.MEDIA_UPLOAD_SECRET)
    providers = [
        {
            "id": "gemini_image",
            "name": f"Gemini Image ({config.GEMINI_IMAGE_MODEL})",
            "available": generation_available and config.IMAGE_GENERATION_PROVIDER == "gemini",
        },
        {
            "id": "stable_diffusion",
            "name": "Stable Diffusion",
            "available": generation_available and config.IMAGE_GENERATION_PROVIDER == "stable_diffusion",
        },
    ]
    return {
        "upload_available": upload_available,
        "generation_available": generation_available,
        "providers": providers,
        "max_upload_bytes": config.MAX_IMAGE_SIZE_BYTES,
        "allowed_mime_types": list(config.MEDIA_ALLOWED_MIME_TYPES),
        "storage_backend": "ionos" if upload_available else "memory",
    }


class MediaUploadUrlRequest(BaseModel):
    filename: str
    mime_type: str
    bytes: int
    purpose: str = "custom_quiz_question"


class MediaFinalizeRequest(BaseModel):
    bytes: int = 0
    alt_text: str = ""


def _sign_media_upload(path: str, expires: int, mime_type: str, bytes_size: int) -> str:
    payload = f"{path}\n{expires}\n{mime_type}\n{bytes_size}".encode()
    return hmac.new(config.MEDIA_UPLOAD_SECRET.encode(), payload, hashlib.sha256).hexdigest()


def _media_owner_path_segment(wallet_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", wallet_id).strip("_")
    return (safe or "owner")[:48]


def _media_wallet_id(req: Request) -> str:
    claims = _authoring_claims_from_request(req)
    if claims:
        launch_context = claims["launch_context"]
        return _revelry_party_wallet_id(launch_context["external_container_id"])
    wallet_id = tokens.get_wallet_id(req)
    if wallet_id:
        return wallet_id
    return ""


@app.post("/media/upload-url")
async def create_media_upload_url(request: MediaUploadUrlRequest, req: Request):
    wallet_id = _media_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not (config.MEDIA_UPLOAD_URL and config.MEDIA_PUBLIC_BASE_URL and config.MEDIA_UPLOAD_SECRET):
        raise HTTPException(status_code=503, detail="Media uploads are not configured")
    if request.mime_type not in config.MEDIA_ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported image type")
    if request.bytes <= 0 or request.bytes > config.MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(status_code=422, detail="Image is too large")

    ext_by_mime = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
    ext = ext_by_mime.get(request.mime_type)
    if not ext:
        raise HTTPException(status_code=422, detail="Unsupported image type")
    asset_id = f"img_{uuid.uuid4().hex}"
    date_part = time.strftime("%Y/%m/%d", time.gmtime())
    storage_path = f"{config.MEDIA_PATH_PREFIX}/uploads/{_media_owner_path_segment(wallet_id)}/{date_part}/{asset_id}.{ext}"
    public_url = f"{config.MEDIA_PUBLIC_BASE_URL}/{storage_path}"
    expires = int(time.time()) + config.MEDIA_UPLOAD_TOKEN_TTL_SECONDS
    token = _sign_media_upload(storage_path, expires, request.mime_type, request.bytes)
    asset = db.create_media_asset(asset_id, wallet_id, storage_path, public_url, request.mime_type, request.bytes)
    return {
        "asset": asset,
        "upload": {
            "url": config.MEDIA_UPLOAD_URL,
            "fields": {
                "path": storage_path,
                "expires": str(expires),
                "mime_type": request.mime_type,
                "bytes": str(request.bytes),
                "token": token,
            },
        },
    }


@app.post("/media/{asset_id}/finalize")
async def finalize_media_upload(asset_id: str, request: MediaFinalizeRequest, req: Request):
    wallet_id = _media_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    asset = db.finalize_media_asset(wallet_id, asset_id, request.bytes, request.alt_text)
    if not asset:
        raise HTTPException(status_code=404, detail="Media asset not found")
    return {"asset": asset}


@app.get("/media/{asset_id}")
async def get_media_asset(asset_id: str):
    """Serve a generated image asset from the shared media namespace."""
    asset = media_store.get_asset(asset_id)
    image_bytes = media_store.get_image_bytes(asset_id)
    if not asset or image_bytes is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return Response(
        content=image_bytes,
        media_type=asset.mime_type,
        headers={"Cache-Control": "private, max-age=300"},
    )


@app.get("/catalog")
async def get_catalog(
    host_app: str = "",
    external_container_id: str = "",
    external_user_id: str = "",
    include_planned: bool = False,
):
    """Return launchable LocalPlay catalog metadata for first-party and host apps."""
    games = effective_catalog(
        GAME_CATALOG,
        host_app=host_app,
        external_container_id=external_container_id,
        external_user_id=external_user_id,
        include_planned=include_planned,
    )
    return {
        "host_app": host_app or None,
        "games": games,
    }


class RevelryActor(BaseModel):
    external_user_id: str = ""
    external_guest_id: Optional[str] = None
    display_name: str = ""
    avatar_url: str = ""
    role: str = "host"
    capabilities: list[str] = Field(default_factory=list)


class RevelryExternalContext(BaseModel):
    host_app: str = "revelry"
    external_container_type: str = "party"
    external_container_id: str
    external_container_title: str = ""
    party_type: str = ""
    brand_key: str = "revelry"
    host_user_id: str = ""
    return_url: str = ""
    guest_join_url: str = ""
    cover_image_url: str = ""
    accent_color: str = ""


class RevelrySessionCreateRequest(BaseModel):
    handoff_token: str = ""
    game_type: str = "quiz"
    settings: dict[str, Any] = Field(default_factory=dict)
    replace_session_id: Optional[str] = None
    replacement_confirmed: bool = False
    external_context: RevelryExternalContext
    actor: RevelryActor = Field(default_factory=RevelryActor)

    @field_validator("game_type")
    @classmethod
    def validate_game_type(cls, value: str) -> str:
        if value != "quiz":
            raise ValueError('Only "quiz" uses the dedicated authoring route')
        return value


class RevelryLaunchTokenRequest(BaseModel):
    scope: str = "player"
    route: str = "join"
    embed: bool = True
    return_url: str = ""
    guest_join_url: str = ""
    external_context: Optional[RevelryExternalContext] = None
    display: dict[str, Any] = Field(default_factory=dict)

    @field_validator("scope")
    @classmethod
    def validate_scope(cls, value: str) -> str:
        if value not in ("organizer", "player", "spectator"):
            raise ValueError("scope must be organizer, player, or spectator")
        return value


class RevelryPartyGamesLinkRequest(BaseModel):
    external_context: RevelryExternalContext
    actor: RevelryActor = Field(default_factory=RevelryActor)
    return_url: str = ""
    guest_join_url: str = ""
    preferred_display: str = "fullscreen"
    intent: str = "hub"
    content_id: str = ""
    game_type: str = "quiz"
    time_limit: Optional[int] = None
    ttl_seconds: Optional[int] = None
    display: dict[str, Any] = Field(default_factory=dict)

    @field_validator("intent")
    @classmethod
    def validate_intent(cls, value: str) -> str:
        if value not in ("hub", "start"):
            raise ValueError("intent must be hub or start")
        return value

    @field_validator("game_type")
    @classmethod
    def validate_game_type(cls, value: str) -> str:
        if value != "quiz":
            raise ValueError('Only "quiz" uses the dedicated authoring route')
        return value

    @field_validator("ttl_seconds")
    @classmethod
    def validate_ttl_seconds(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value <= 0:
            raise ValueError("ttl_seconds must be greater than 0")
        return value


class RevelryContentAuthoringLinkRequest(BaseModel):
    external_context: RevelryExternalContext
    actor: RevelryActor = Field(default_factory=RevelryActor)
    game_type: str = "quiz"
    mode: str = "create"
    content_id: Optional[str] = None
    return_url: str = ""
    prepared_setup_id: str = ""
    display: dict[str, Any] = Field(default_factory=dict)

    @field_validator("game_type")
    @classmethod
    def validate_game_type(cls, value: str) -> str:
        if value not in ("quiz", "wmlt", "drawing"):
            raise ValueError('game_type must be "quiz", "wmlt", or "drawing"')
        return value

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        if value not in ("create", "edit", "duplicate"):
            raise ValueError("mode must be create, edit, or duplicate")
        return value


class RevelryPartyGamesAuthoringLinkRequest(BaseModel):
    party_games_token: str
    game_type: str = "quiz"
    mode: str = "create"
    content_id: Optional[str] = None

    @field_validator("game_type")
    @classmethod
    def validate_game_type(cls, value: str) -> str:
        if value not in ("quiz", "wmlt", "drawing"):
            raise ValueError('game_type must be "quiz", "wmlt", or "drawing"')
        return value


class RevelryPartyGamesContentDeleteRequest(BaseModel):
    party_games_token: str


class RevelryPartyGamesContentSaveRequest(BaseModel):
    party_games_token: str
    game_type: str = "quiz"
    title: str = "Saved Game"
    content_id: Optional[str] = None
    content_payload: dict[str, Any] = Field(default_factory=dict)
    status: str = "ready"

    @field_validator("game_type")
    @classmethod
    def validate_game_type(cls, value: str) -> str:
        if value not in ("quiz", "wmlt", "drawing"):
            raise ValueError('game_type must be "quiz", "wmlt", or "drawing"')
        return value


class RevelryPartyGamesPromptGenerateRequest(BaseModel):
    party_games_token: str
    game_type: str
    prompt: str = ""
    difficulty: str = "medium"
    num_prompts: int = 10
    provider: str = ""

    @field_validator("game_type")
    @classmethod
    def validate_game_type(cls, value: str) -> str:
        if value not in ("quiz", "wmlt", "drawing"):
            raise ValueError('game_type must be "quiz", "wmlt", or "drawing"')
        return value

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        value = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', value)
        value = re.sub(r'<[^>]+>', '', value).strip()
        if len(value) > config.MAX_PROMPT_LENGTH:
            raise ValueError(f'Prompt must be at most {config.MAX_PROMPT_LENGTH} characters')
        return value

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty(cls, value: str) -> str:
        value = value.lower().strip()
        if value not in VALID_MLT_VIBES and value not in config.VALID_DIFFICULTIES:
            raise ValueError('Invalid difficulty or vibe')
        return value

    @field_validator("num_prompts")
    @classmethod
    def validate_num_prompts(cls, value: int) -> int:
        if value < 1 or value > 50:
            raise ValueError('Number of prompts must be 1-50')
        return value


class RevelryContentSaveRequest(BaseModel):
    external_context: Optional[RevelryExternalContext] = None
    actor: Optional[RevelryActor] = None
    game_type: str = "quiz"
    title: str = "Custom Quiz"
    content_id: Optional[str] = None
    content_payload: dict[str, Any] = Field(default_factory=dict)
    status: str = "ready"

    @field_validator("game_type")
    @classmethod
    def validate_game_type(cls, value: str) -> str:
        if value not in ("quiz", "wmlt", "drawing"):
            raise ValueError('game_type must be "quiz", "wmlt", or "drawing"')
        return value


class RevelryPartyGameStartRequest(BaseModel):
    party_games_token: str
    content_id: str = ""
    game_type: str = "quiz"
    time_limit: Optional[int] = None
    replacement_confirmed: bool = False
    replace_session_id: Optional[str] = None

    @field_validator("time_limit")
    @classmethod
    def validate_time_limit(cls, value: Optional[int]) -> Optional[int]:
        if value is None:
            return value
        if value < 5 or value > 60:
            raise ValueError("time_limit must be between 5 and 60 seconds")
        return value

    @field_validator("game_type")
    @classmethod
    def validate_game_type(cls, value: str) -> str:
        if value not in ("quiz", "wmlt", "drawing"):
            raise ValueError('game_type must be "quiz", "wmlt", or "drawing"')
        return value


class RevelryPartyGameLaunchRequest(BaseModel):
    party_games_token: str
    session_id: str
    scope: str = "player"
    route: str = "join"
    embed: bool = True

    @field_validator("scope")
    @classmethod
    def validate_scope(cls, value: str) -> str:
        if value not in ("organizer", "player", "spectator"):
            raise ValueError("scope must be organizer, player, or spectator")
        return value


def _require_revelry_auth(req: Request, handoff_token: str = "") -> dict:
    secret = config.REVELRY_INTEGRATION_SECRET
    if not secret:
        raise HTTPException(status_code=503, detail="Revelry integration is not configured")
    bearer = (req.headers.get("authorization") or "").strip()
    token = ""
    if bearer.lower().startswith("bearer "):
        token = bearer[7:].strip()
    token = handoff_token or token
    if not token:
        raise HTTPException(status_code=401, detail="Missing integration credential")
    if hmac.compare_digest(token, secret):
        return {"type": "service", "iss": "local"}
    try:
        claims = jwt.decode(token, secret, algorithms=["HS256"], options={"require": ["exp"]})
        if claims.get("iss") not in ("revelry", "localplay"):
            raise HTTPException(status_code=401, detail="Invalid integration issuer")
        return claims
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired integration credential")


def _session_launch_routes(base_url: str, session_id: str) -> dict:
    return {
        "organizer": {
            "url": f"{base_url}/sessions/{session_id}/organizer?embed=1",
            "path": f"/sessions/{session_id}/organizer",
            "scope": "organizer",
        },
        "player": {
            "url": f"{base_url}/sessions/{session_id}/join",
            "path": f"/sessions/{session_id}/join",
            "scope": "player",
        },
        "spectator": {
            "url": f"{base_url}/sessions/{session_id}/spectate",
            "path": f"/sessions/{session_id}/spectate",
            "scope": "spectator",
        },
    }


def _session_feed_card(title: str, actor_name: str) -> dict:
    return {
        "title": title,
        "body": f"{actor_name or 'The host'} started a LocalPlay game.",
        "action_label": "Join game",
        "thumbnail_url": "",
    }


def _revelry_party_wallet_id(external_container_id: str) -> str:
    return f"revelry:party:{external_container_id}"


def _revelry_display(context: RevelryExternalContext, display: Optional[dict[str, Any]] = None) -> dict:
    display = display or {}
    label = display.get("container_label") or context.external_container_title or "Revelry party"
    guest_join_url = display.get("guest_join_url") or context.guest_join_url
    guest_join_url = _validate_revelry_return_url(guest_join_url) if guest_join_url else ""
    return {
        "show_localplay_nav": False,
        "show_account_menu": False,
        "show_wallet": False,
        "show_paywalls": False,
        "show_library": False,
        "show_return_action": True,
        "container_label": label,
        "container_image_url": display.get("container_image_url") or context.cover_image_url,
        "accent_color": display.get("accent_color") or context.accent_color,
        "link_label": display.get("link_label") or f"Open {label} Games Hub on Revelry Games",
        "return_label": display.get("return_label") or "Back to Revelry",
        "guest_join_url": guest_join_url,
        "guest_join_label": display.get("guest_join_label") or "Scan to join from Revelry",
    }


def _revelry_launch_context(
    context: RevelryExternalContext,
    actor: RevelryActor,
    surface: str,
    return_url: str = "",
    display: Optional[dict[str, Any]] = None,
) -> dict:
    allowed_games = [game["id"] for game in _host_app_catalog(context, actor) if game.get("launchable")]
    return {
        "mode": "host_app",
        "host_app": context.host_app,
        "brand_key": context.brand_key,
        "external_container_type": context.external_container_type,
        "external_container_id": context.external_container_id,
        "external_container_title": context.external_container_title,
        "party_type": context.party_type,
        "external_user_id": actor.external_user_id,
        "external_guest_id": actor.external_guest_id,
        "display_name": actor.display_name,
        "avatar_url": actor.avatar_url,
        "role": actor.role,
        "capabilities": actor.capabilities,
        "return_url": return_url or context.return_url,
        "guest_join_url": context.guest_join_url,
        "billing_mode": "host_app_managed",
        "allowed_game_ids": allowed_games,
        "surface": surface,
        "display": _revelry_display(context, display),
    }


def _host_app_catalog(context: RevelryExternalContext, actor: Optional[RevelryActor] = None, include_planned: bool = False) -> list[dict]:
    return effective_catalog(
        GAME_CATALOG,
        host_app=context.host_app,
        external_container_id=context.external_container_id,
        external_user_id=(actor.external_user_id if actor else context.host_user_id),
        include_planned=include_planned,
    )


def _require_host_app_game_allowed(
    context: RevelryExternalContext,
    game_type: str,
    actor: Optional[RevelryActor] = None,
    required_capability: str = "",
) -> None:
    if context.host_app != "revelry":
        raise HTTPException(status_code=422, detail="Unsupported host_app")
    if not is_game_allowed(
        GAME_CATALOG,
        game_type,
        host_app=context.host_app,
        external_container_id=context.external_container_id,
        external_user_id=(actor.external_user_id if actor else context.host_user_id),
        required_capability=required_capability,
    ):
        raise HTTPException(status_code=422, detail="Game is not enabled for this Revelry party")


def _create_party_games_token(
    context: RevelryExternalContext,
    actor: RevelryActor,
    return_url: str = "",
    display: Optional[dict[str, Any]] = None,
    ttl_seconds: Optional[int] = None,
) -> tuple[str, int, dict]:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=ttl_seconds or config.REVELRY_LAUNCH_TOKEN_TTL_SECONDS)
    launch_context = _revelry_launch_context(context, actor, "party_hub", return_url, display)
    payload = {
        "type": "revelry_party_games",
        "iss": "localplay",
        "launch_context": launch_context,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": uuid.uuid4().hex,
    }
    token = jwt.encode(payload, config.REVELRY_INTEGRATION_SECRET, algorithm="HS256")
    return token, int(exp.timestamp()), launch_context


def _party_games_token_ttl_seconds(requested_ttl_seconds: Optional[int]) -> Optional[int]:
    if requested_ttl_seconds is None:
        return None
    if config.ENVIRONMENT == "production":
        raise HTTPException(status_code=422, detail="Custom party games token TTL is not available in production")
    max_ttl_seconds = 30 * 24 * 60 * 60
    return min(requested_ttl_seconds, max_ttl_seconds)


def _resolve_party_games_token(token: str) -> dict:
    if not config.REVELRY_INTEGRATION_SECRET:
        raise HTTPException(status_code=503, detail="Revelry integration is not configured")
    try:
        claims = jwt.decode(token, config.REVELRY_INTEGRATION_SECRET, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired party games token")
    if claims.get("type") != "revelry_party_games":
        raise HTTPException(status_code=401, detail="Invalid party games token")
    launch_context = claims.get("launch_context") or {}
    if launch_context.get("host_app") != "revelry" or not launch_context.get("external_container_id"):
        raise HTTPException(status_code=401, detail="Invalid party games context")
    return launch_context


def _create_authoring_token(
    context: RevelryExternalContext,
    actor: RevelryActor,
    game_type: str,
    mode: str,
    content_id: str = "",
    return_url: str = "",
    prepared_setup_id: str = "",
    display: Optional[dict[str, Any]] = None,
) -> tuple[str, int, dict]:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=config.REVELRY_AUTHORING_TOKEN_TTL_SECONDS)
    launch_context = _revelry_launch_context(context, actor, "content_authoring", return_url, display)
    payload = {
        "type": "revelry_authoring",
        "iss": "localplay",
        "launch_context": launch_context,
        "game_type": game_type,
        "mode": mode,
        "content_id": content_id or "",
        "prepared_setup_id": prepared_setup_id or "",
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": uuid.uuid4().hex,
    }
    token = jwt.encode(payload, config.REVELRY_INTEGRATION_SECRET, algorithm="HS256")
    return token, int(exp.timestamp()), launch_context


def _resolve_authoring_token(token: str) -> dict:
    if not config.REVELRY_INTEGRATION_SECRET:
        raise HTTPException(status_code=503, detail="Revelry integration is not configured")
    try:
        claims = jwt.decode(token, config.REVELRY_INTEGRATION_SECRET, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired authoring token")
    if claims.get("type") != "revelry_authoring":
        raise HTTPException(status_code=401, detail="Invalid authoring token")
    launch_context = claims.get("launch_context") or {}
    if launch_context.get("host_app") != "revelry" or not launch_context.get("external_container_id"):
        raise HTTPException(status_code=401, detail="Invalid authoring context")
    return claims


def _authoring_claims_from_request(req: Request) -> Optional[dict]:
    bearer = (req.headers.get("authorization") or "").strip()
    token = bearer[7:].strip() if bearer.lower().startswith("bearer ") else ""
    if not token:
        token = (req.query_params.get("authoring_token") or "").strip()
    if not token:
        return None
    return _resolve_authoring_token(token)


def _require_authoring_or_service(req: Request, request_context: Optional[RevelryExternalContext] = None) -> tuple[RevelryExternalContext, RevelryActor, Optional[dict]]:
    claims = _authoring_claims_from_request(req)
    if claims:
        launch_context = claims["launch_context"]
        return _external_context_from_launch_context(launch_context), _actor_from_launch_context(launch_context), claims
    _require_revelry_auth(req)
    if not request_context:
        raise HTTPException(status_code=422, detail="external_context is required for service calls")
    return request_context, RevelryActor(), None


def _author_can_author(actor: RevelryActor) -> bool:
    capabilities = set(actor.capabilities or [])
    return "author_content" in capabilities or "manage_games" in capabilities


def _author_can_operate(actor: RevelryActor) -> bool:
    capabilities = set(actor.capabilities or [])
    return "operate_game" in capabilities or "manage_games" in capabilities


def _validate_revelry_return_url(return_url: str) -> str:
    if not return_url:
        return ""
    parsed = urlparse(return_url)
    if parsed.scheme in ("revelry", "revelryapp"):
        if parsed.netloc and parsed.netloc not in ("party", "games", "open"):
            raise HTTPException(status_code=422, detail="return_url is not allowed")
        return return_url
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(status_code=422, detail="Invalid return_url")
    allowed = set()
    for origin in config.ALLOWED_ORIGINS.split(","):
        origin = origin.strip()
        if not origin:
            continue
        allowed_url = urlparse(origin)
        if allowed_url.scheme in ("http", "https") and allowed_url.netloc:
            allowed.add((allowed_url.scheme, allowed_url.hostname, allowed_url.port))
    allowed.update({
        ("https", "app.revelryapp.me", None),
        ("https", "api.revelryapp.me", None),
        ("https", "api-gamma.revelryapp.me", None),
        ("http", "localhost", 5173),
        ("http", "127.0.0.1", 5173),
    })
    if (parsed.scheme, parsed.hostname, parsed.port) not in allowed:
        raise HTTPException(status_code=422, detail="return_url is not allowed")
    return return_url


def _safe_actor_payload(actor: Optional[Any] = None, session: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
    actor_data: dict[str, Any] = {}
    if actor:
        actor_data = {
            "external_user_id": getattr(actor, "external_user_id", "") or "",
            "external_guest_id": getattr(actor, "external_guest_id", None),
            "display_name": getattr(actor, "display_name", "") or "",
            "role": getattr(actor, "role", "") or "",
        }
    if session:
        actor_data = {
            "external_user_id": actor_data.get("external_user_id") or session.get("external_host_user_id") or "",
            "external_guest_id": actor_data.get("external_guest_id"),
            "display_name": actor_data.get("display_name") or session.get("external_host_display_name") or "",
            "role": actor_data.get("role") or "host",
        }
    actor_data = {key: value for key, value in actor_data.items() if value}
    return actor_data or None


def _authoring_url(req: Request, token: str) -> str:
    return f"{_public_base_url(req)}/revelry/author?authoring_token={token}"


def _callback_event_type(event_type: str) -> str:
    return {
        "session.created": "game.session_created",
        "session.started": "game.started",
        "session.completed": "game.completed",
        "session.cancelled": "game.cancelled",
        "session.expired": "game.expired",
        "session.superseded": "game.superseded",
    }.get(event_type, event_type)


def _callback_signing_secret() -> str:
    return config.REVELRY_INTEGRATION_SECRET or config.REVELRY_CALLBACK_SECRET


def _callback_retry_delay(response: Optional[httpx.Response], attempt: int) -> float:
    if response is not None:
        retry_after = response.headers.get("Retry-After", "")
        try:
            return max(0.0, min(float(retry_after), 5.0))
        except ValueError:
            pass
    return min(0.25 * (2 ** attempt), 2.0)


def _safe_result_summary(result: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not isinstance(result, dict):
        return None
    if isinstance(result.get("top_results"), list):
        top_results = result["top_results"][:5]
        winner = result.get("winner") if isinstance(result.get("winner"), dict) else (top_results[0] if top_results else None)
        return {
            "title": result.get("title") or result.get("game_title") or "LocalPlay results",
            "game_type": result.get("game_type"),
            "total_rounds": result.get("total_rounds") or result.get("total_questions"),
            "player_count": result.get("player_count"),
            "top_results": top_results,
            "players": top_results,
            "leaderboard": top_results,
            "winner": winner,
            "completed_at": result.get("completed_at"),
        }
    leaderboard = result.get("leaderboard") if isinstance(result.get("leaderboard"), list) else []
    top_results = []
    for row in leaderboard[:5]:
        if not isinstance(row, dict):
            continue
        top_results.append({
            "nickname": row.get("nickname"),
            "avatar": row.get("avatar"),
            "score": row.get("score"),
        })
    winner = top_results[0] if top_results else None
    return {
        "title": result.get("title") or result.get("game_title") or "LocalPlay results",
        "game_type": result.get("game_type"),
        "total_rounds": result.get("total_questions") or result.get("total_rounds"),
        "player_count": result.get("player_count"),
        "top_results": top_results,
        "players": top_results,
        "leaderboard": top_results,
        "winner": winner,
        "completed_at": result.get("completed_at"),
    }


async def _send_revelry_callback(event_type: str, payload: dict[str, Any]) -> None:
    if not config.REVELRY_CALLBACK_URL:
        return
    event_type = _callback_event_type(event_type)
    session = payload.get("session") if isinstance(payload.get("session"), dict) else {}
    result_summary = _safe_result_summary(payload.get("result_summary") or payload.get("result"))
    session_id = payload.get("session_id") or session.get("session_id") or session.get("id")
    content_id = payload.get("content_id") or payload.get("localplay_content_id")
    actor_payload = payload.get("actor") if isinstance(payload.get("actor"), dict) else _safe_actor_payload(session=session)
    body = {
        "event_id": f"lp_evt_{uuid.uuid4().hex}",
        "event_type": event_type,
        "occurred_at": _iso(_now_ts()),
        "host_app": payload.get("host_app") or session.get("host_app") or "revelry",
        "external_container_type": payload.get("external_container_type") or session.get("external_container_type") or "party",
        "external_container_id": payload.get("external_container_id") or session.get("external_container_id"),
        "session_id": session_id,
        "content_id": content_id,
        "previous_content_id": payload.get("previous_content_id") or payload.get("versioned_from_content_id"),
        "idempotency_key": f"{event_type}:{session_id or content_id or uuid.uuid4().hex}:v1",
        "payload": {
            "status": payload.get("status") or session.get("status"),
            "session": session or None,
            "actor": actor_payload,
            "result_summary": result_summary,
            "content": payload.get("content"),
            "previous_content_id": payload.get("previous_content_id") or payload.get("versioned_from_content_id"),
            "feed_card": payload.get("feed_card") or session.get("feed_card"),
            "closed_reason": payload.get("closed_reason") or session.get("closed_reason"),
            "closed_message": payload.get("closed_message") or session.get("closed_message"),
            "superseded_by_session_id": payload.get("superseded_by_session_id") or session.get("superseded_by_session_id"),
        },
    }
    body["payload"] = {k: v for k, v in body["payload"].items() if v is not None}
    body = {k: v for k, v in body.items() if v is not None}
    raw = json.dumps(body, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    signature = ""
    signing_secret = _callback_signing_secret()
    if signing_secret:
        signature = hmac.new(
            signing_secret.encode(),
            f"{timestamp}.".encode() + raw,
            hashlib.sha256,
        ).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-LocalPlay-Event-Id": body["event_id"],
        "X-LocalPlay-Timestamp": timestamp,
    }
    if signature:
        headers["X-LocalPlay-Signature"] = f"sha256={signature}"
    async with httpx.AsyncClient(timeout=5.0) as client:
        for attempt in range(3):
            try:
                response = await client.post(config.REVELRY_CALLBACK_URL, content=raw, headers=headers)
                response.raise_for_status()
                return
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status not in (429, 500, 502, 503, 504) or attempt == 2:
                    logger.warning("Revelry callback failed for %s: %s", event_type, exc)
                    return
                await asyncio.sleep(_callback_retry_delay(exc.response, attempt))
            except httpx.HTTPError as exc:
                if attempt == 2:
                    logger.warning("Revelry callback failed for %s: %s", event_type, exc)
                    return
                await asyncio.sleep(_callback_retry_delay(None, attempt))


def _quiz_pack_summary(pack: dict) -> dict:
    thumbnail_url = ""
    for question in pack.get("questions") or []:
        if question.get("image_url"):
            thumbnail_url = question["image_url"]
            break
    return {
        "localplay_content_id": pack["id"],
        "game_type": "quiz",
        "title": pack.get("title") or "Custom Quiz",
        "status": pack.get("status") or "ready",
        "thumbnail_url": thumbnail_url,
        "question_count": pack.get("question_count") or len(pack.get("questions") or []),
        "created_by": "",
        "updated_at": _iso(pack.get("updated_at")),
        "last_used_at": None,
        "action_requirements": {
            "start": ["operate_game"],
            "edit": ["author_content"],
            "delete": ["manage_games"],
        },
    }


def _game_content_payload(content: dict) -> dict:
    payload = content.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {}
    return payload if isinstance(payload, dict) else {}


def _count_game_items(game_type: str, payload: dict) -> int:
    game = payload.get("game") if isinstance(payload.get("game"), dict) else payload
    if game_type == "wmlt":
        return len(game.get("statements") or [])
    if game_type == "drawing":
        return len(game.get("prompts") or [])
    if game_type == "quiz":
        return len(game.get("questions") or [])
    return 0


def _game_content_summary(content: dict) -> dict:
    payload = _game_content_payload(content)
    game_type = content.get("game_type") or "wmlt"
    count = _count_game_items(game_type, payload)
    return {
        "localplay_content_id": content["id"],
        "game_type": game_type,
        "title": content.get("title") or ("Drawing Game" if game_type == "drawing" else "Most Likely To"),
        "status": content.get("status") or "ready",
        "thumbnail_url": "",
        "question_count": count,
        "item_count": count,
        "time_limit": payload.get("time_limit"),
        "created_by": "",
        "updated_at": _iso(content.get("updated_at")),
        "last_used_at": None,
        "action_requirements": {
            "start": ["operate_game"],
            "edit": ["author_content"],
            "delete": ["manage_games"],
        },
    }


def _prepared_content_summary(content: dict) -> dict:
    if content.get("game_type") == "quiz" or "questions" in content:
        return _quiz_pack_summary(content)
    return _game_content_summary(content)


def _workspace_payload(context: RevelryExternalContext, actor: Optional[RevelryActor] = None) -> dict:
    wallet_id = _revelry_party_wallet_id(context.external_container_id)
    packs = db.list_quiz_packs(wallet_id)
    saved_games = db.list_game_content(wallet_id, ["wmlt", "drawing"])
    prepared = [_quiz_pack_summary(pack) for pack in packs] + [_game_content_summary(game) for game in saved_games]
    prepared.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    active = db.get_active_game_session(context.host_app, context.external_container_id)
    return {
        "external_context": {
            "host_app": context.host_app,
            "external_container_type": context.external_container_type,
            "external_container_id": context.external_container_id,
            "external_container_title": context.external_container_title,
        },
        "catalog": _host_app_catalog(context, actor),
        "prepared_content": prepared,
        "active_session": _format_session(active) if active else None,
        "recent_results": [],
    }


def _actor_from_launch_context(launch_context: dict) -> RevelryActor:
    return RevelryActor(
        external_user_id=launch_context.get("external_user_id", ""),
        external_guest_id=launch_context.get("external_guest_id"),
        display_name=launch_context.get("display_name", "") or launch_context.get("display", {}).get("container_label", "") or launch_context.get("external_container_title", ""),
        avatar_url=launch_context.get("avatar_url", ""),
        role=launch_context.get("role", "host"),
        capabilities=launch_context.get("capabilities") or [],
    )


def _external_context_from_launch_context(launch_context: dict) -> RevelryExternalContext:
    return RevelryExternalContext(
        host_app=launch_context.get("host_app", "revelry"),
        external_container_type=launch_context.get("external_container_type", "party"),
        external_container_id=launch_context["external_container_id"],
        external_container_title=launch_context.get("external_container_title", ""),
        party_type=launch_context.get("party_type", ""),
        brand_key=launch_context.get("brand_key", "revelry"),
        return_url=launch_context.get("return_url", ""),
        guest_join_url=launch_context.get("guest_join_url", "") or launch_context.get("display", {}).get("guest_join_url", ""),
    )


def _format_session(session: dict) -> dict:
    room = socket_manager.rooms.get(session.get("room_code", ""))
    status = session.get("status", "lobby")
    joinable = bool(session.get("joinable", True))
    last_activity_at = session.get("last_activity_at")
    if room and status not in ("complete", "expired", "cancelled", "superseded"):
        last_activity_at = int(room.last_activity)
        if room.state == "LOBBY":
            status = "lobby"
        elif room.state == "PODIUM":
            status = "complete"
            joinable = False
        else:
            status = "active"
    elif status in ("lobby", "active", "paused") and session.get("expires_at", 0) <= _now_ts():
        status = "expired"
        joinable = False
    return {
        "session_id": session["id"],
        "room_code": session["room_code"],
        "status": status,
        "joinable": joinable,
        "closed_reason": session.get("closed_reason"),
        "closed_message": session.get("closed_message"),
        "superseded_by_session_id": session.get("superseded_by_session_id"),
        "feed_card": session.get("feed_card") or {},
        "launch_routes": session.get("launch_routes") or {},
        "created_at": _iso(session.get("created_at")),
        "started_at": _iso(session.get("started_at")),
        "completed_at": _iso(session.get("completed_at")),
        "expires_at": _iso(session.get("expires_at")),
        "last_activity_at": _iso(last_activity_at),
    }


def _create_launch_token(
    session_id: str,
    scope: str,
    route: str,
    return_url: str = "",
    launch_context: Optional[dict[str, Any]] = None,
) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=config.REVELRY_LAUNCH_TOKEN_TTL_SECONDS)
    payload = {
        "type": "revelry_launch",
        "iss": "localplay",
        "session_id": session_id,
        "scope": scope,
        "route": route,
        "return_url": return_url,
        "launch_context": launch_context or {},
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, config.REVELRY_INTEGRATION_SECRET, algorithm="HS256"), int(exp.timestamp())


def _resolve_launch_token(token: str, expected_session_id: str = "", expected_scope: str = "") -> dict:
    if not config.REVELRY_INTEGRATION_SECRET:
        raise HTTPException(status_code=503, detail="Revelry integration is not configured")
    try:
        claims = jwt.decode(token, config.REVELRY_INTEGRATION_SECRET, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired launch token")
    if claims.get("type") != "revelry_launch":
        raise HTTPException(status_code=401, detail="Invalid launch token")
    if expected_session_id and claims.get("session_id") != expected_session_id:
        raise HTTPException(status_code=401, detail="Launch token session mismatch")
    if expected_scope and claims.get("scope") != expected_scope:
        raise HTTPException(status_code=403, detail="Launch token scope mismatch")
    return claims


def _create_revelry_session_from_context(
    context: RevelryExternalContext,
    actor: RevelryActor,
    game_type: str,
    settings: dict[str, Any],
    req: Request,
    replacement_confirmed: bool = False,
    replace_session_id: Optional[str] = None,
) -> dict:
    if context.host_app != "revelry":
        raise HTTPException(status_code=422, detail="Unsupported host_app")
    _require_host_app_game_allowed(context, game_type, actor)

    active = db.get_active_game_session(context.host_app, context.external_container_id)
    if active and not replacement_confirmed:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "active_session_exists",
                "session_id": active["id"],
                "game_type": active.get("game_type"),
                "game_title": active.get("game_title"),
                "message": "An active LocalPlay session already exists for this party.",
            },
        )
    if replacement_confirmed and active:
        if not replace_session_id or replace_session_id != active["id"]:
            raise HTTPException(status_code=409, detail="replace_session_id must match the active LocalPlay session")

    title = context.external_container_title or next((g["title"] for g in GAME_CATALOG if g["game_type"] == game_type), "LocalPlay Game")
    content_id, game_data = _resolve_revelry_runtime_content(context, game_type, str(settings.get("content_id") or ""), title)
    time_limit = int(settings.get("time_limit") or game_data.get("time_limit") or _default_time_limit_for_game(game_type))
    time_limit = max(5, min(60, time_limit))
    wallet_id = f"revelry:{context.host_user_id or actor.external_user_id or context.external_container_id}"
    db.get_or_create_wallet(wallet_id, signup_bonus=False)
    room_code, organizer_token = _create_runtime_room(
        game_type,
        content_id,
        game_data,
        wallet_id,
        time_limit,
        billing_mode="host_app_managed",
    )

    now = _now_ts()
    session_id = f"lp_{uuid.uuid4().hex}"
    base_url = _public_base_url(req)
    game_title = game_data.get("quiz_title") or game_data.get("game_title") or title
    session = db.create_game_session({
        "id": session_id,
        "host_app": context.host_app,
        "external_container_id": context.external_container_id,
        "external_container_type": context.external_container_type,
        "external_container_title": context.external_container_title,
        "external_host_user_id": context.host_user_id,
        "external_host_display_name": actor.display_name,
        "game_type": game_type,
        "game_id": content_id,
        "game_title": game_title,
        "room_code": room_code,
        "organizer_token": organizer_token,
        "status": "lobby",
        "joinable": True,
        "launch_routes": _session_launch_routes(base_url, session_id),
        "feed_card": _session_feed_card(game_title, actor.display_name),
        "created_at": now,
        "expires_at": now + config.REVELRY_SESSION_LOBBY_TTL_SECONDS,
        "last_activity_at": now,
        "updated_at": now,
    })
    if active:
        superseded = db.update_game_session(active["id"], {
            "status": "superseded",
            "joinable": False,
            "closed_reason": "superseded",
            "closed_message": "The host started a newer game.",
            "superseded_by_session_id": session_id,
        })
        session["_superseded_session"] = superseded or db.get_game_session(active["id"]) or active
    return session


@app.post("/integrations/revelry/party-games-link")
async def create_revelry_party_games_link(request: RevelryPartyGamesLinkRequest, req: Request):
    _require_revelry_auth(req)
    context = request.external_context
    if context.host_app != "revelry":
        raise HTTPException(status_code=422, detail="Unsupported host_app")
    display = dict(request.display or {})
    if request.guest_join_url and not display.get("guest_join_url"):
        display["guest_join_url"] = request.guest_join_url
    token, expires, launch_context = _create_party_games_token(
        context,
        request.actor,
        _validate_revelry_return_url(request.return_url or context.return_url),
        display,
        ttl_seconds=_party_games_token_ttl_seconds(request.ttl_seconds),
    )
    base_url = _public_base_url(req)
    party_games_url = f"{base_url}/integrations/revelry/games?{urlencode({'party_games_token': token})}"
    start_url = ""
    if request.intent == "start" or request.content_id:
        if not request.content_id:
            raise HTTPException(status_code=422, detail="content_id is required for start intent")
        _require_host_app_game_allowed(context, request.game_type, request.actor)
        start_params: dict[str, Any] = {
            "party_games_token": token,
            "start_content_id": request.content_id,
            "game_type": request.game_type,
        }
        if request.time_limit is not None:
            start_params["time_limit"] = request.time_limit
        start_url = f"{base_url}/integrations/revelry/games?{urlencode(start_params)}"
    return {
        "party_games_url": party_games_url,
        "start_url": start_url,
        "party_games_token_expires_at": _iso(expires),
        "return_url": launch_context.get("return_url", ""),
        "display": launch_context.get("display", {}),
    }


@app.post("/integrations/revelry/content/authoring-link")
async def create_revelry_content_authoring_link(request: RevelryContentAuthoringLinkRequest, req: Request):
    _require_revelry_auth(req)
    if request.external_context.host_app != "revelry":
        raise HTTPException(status_code=422, detail="Unsupported host_app")
    if not _author_can_author(request.actor):
        raise HTTPException(status_code=403, detail="Missing capability to author content")
    required_capability = "can_edit_content" if request.mode in ("edit", "duplicate") else "can_create_content"
    _require_host_app_game_allowed(request.external_context, request.game_type, request.actor, required_capability)
    if request.mode in ("edit", "duplicate") and not request.content_id:
        raise HTTPException(status_code=422, detail="content_id is required for edit or duplicate")
    if request.content_id:
        wallet_id = _revelry_party_wallet_id(request.external_context.external_container_id)
        if not db.get_quiz_pack(wallet_id, request.content_id):
            raise HTTPException(status_code=404, detail="Content not found")
    token, expires, launch_context = _create_authoring_token(
        request.external_context,
        request.actor,
        request.game_type,
        request.mode,
        request.content_id or "",
        _validate_revelry_return_url(request.return_url or request.external_context.return_url),
        request.prepared_setup_id,
        request.display,
    )
    return {
        "authoring_url": _authoring_url(req, token),
        "authoring_token_expires_at": _iso(expires),
        "localplay_content_id": request.content_id,
        "launch_context": launch_context,
    }


@app.post("/integrations/revelry/party-games/authoring-link")
async def create_revelry_party_games_authoring_link(request: RevelryPartyGamesAuthoringLinkRequest, req: Request):
    launch_context = _resolve_party_games_token(request.party_games_token)
    actor = _actor_from_launch_context(launch_context)
    if not _author_can_author(actor):
        raise HTTPException(status_code=403, detail="Missing capability to author content")
    context = _external_context_from_launch_context(launch_context)
    required_capability = "can_edit_content" if request.mode in ("edit", "duplicate") else "can_create_content"
    _require_host_app_game_allowed(context, request.game_type, actor, required_capability)
    if request.mode in ("edit", "duplicate") and not request.content_id:
        raise HTTPException(status_code=422, detail="content_id is required for edit or duplicate")
    if request.content_id:
        wallet_id = _revelry_party_wallet_id(context.external_container_id)
        if not db.get_quiz_pack(wallet_id, request.content_id):
            raise HTTPException(status_code=404, detail="Content not found")
    token, expires, next_context = _create_authoring_token(
        context,
        actor,
        request.game_type,
        request.mode,
        request.content_id or "",
        f"{_public_base_url(req)}/revelry/games?party_games_token={request.party_games_token}",
        "",
        launch_context.get("display") or {},
    )
    return {
        "authoring_url": _authoring_url(req, token),
        "authoring_token_expires_at": _iso(expires),
        "localplay_content_id": request.content_id,
        "launch_context": next_context,
    }


@app.get("/integrations/revelry/content/authoring-token/resolve")
async def resolve_revelry_authoring_token(authoring_token: str):
    claims = _resolve_authoring_token(authoring_token)
    context = _external_context_from_launch_context(claims["launch_context"])
    content = None
    content_id = claims.get("content_id") or ""
    if content_id:
        pack = db.get_quiz_pack(_revelry_party_wallet_id(context.external_container_id), content_id)
        if not pack:
            raise HTTPException(status_code=404, detail="Content not found")
        content = {"metadata": _quiz_pack_summary(pack), "quiz": _pack_to_quiz(pack)}
    return {
        "launch_context": claims["launch_context"],
        "game_type": claims.get("game_type", "quiz"),
        "mode": claims.get("mode", "create"),
        "localplay_content_id": content_id or None,
        "prepared_setup_id": claims.get("prepared_setup_id") or "",
        "content": content,
    }


def _content_quiz_from_payload(request: RevelryContentSaveRequest) -> dict:
    payload = request.content_payload or {}
    quiz_data = payload.get("quiz") if isinstance(payload.get("quiz"), dict) else payload
    if not isinstance(quiz_data, dict):
        raise HTTPException(status_code=422, detail="Invalid content payload")
    if "quiz_title" not in quiz_data and request.title:
        quiz_data = {**quiz_data, "quiz_title": request.title}
    quiz_data = _sanitize_quiz(quiz_data)
    if not _validate_quiz(quiz_data, attempt=0):
        raise HTTPException(status_code=422, detail="Invalid quiz content")
    return quiz_data


def _content_game_from_payload(game_type: str, title: str, payload: dict[str, Any]) -> dict:
    raw = payload or {}
    game_data = raw.get("game") if isinstance(raw.get("game"), dict) else raw
    if not isinstance(game_data, dict):
        raise HTTPException(status_code=422, detail="Invalid content payload")
    if game_type == "wmlt":
        if "game_title" not in game_data and title:
            game_data = {**game_data, "game_title": title}
        game_data = _sanitize_mlt(game_data)
        if not _validate_mlt(game_data, attempt=0):
            raise HTTPException(status_code=422, detail="Invalid Most Likely To content")
        return {"game": game_data}
    if game_type == "drawing":
        if "game_title" not in game_data and title:
            game_data = {**game_data, "game_title": title}
        game_data = _sanitize_drawing_game(game_data)
        if not _validate_drawing_game(game_data, attempt=0):
            raise HTTPException(status_code=422, detail="Invalid drawing game content")
        time_limit = raw.get("time_limit") or game_data.get("time_limit") or 30
        try:
            time_limit = int(time_limit)
        except (TypeError, ValueError):
            time_limit = 30
        return {"game": game_data, "time_limit": max(5, min(60, time_limit))}
    raise HTTPException(status_code=422, detail="Unsupported game_type")


def _content_response(context: RevelryExternalContext, content: dict) -> dict:
    summary = _prepared_content_summary(content)
    return {
        **summary,
        "content": summary,
        "localplay_content_id": content["id"],
        "workspace": _workspace_payload(context),
    }


async def _generate_party_prompt_content(context: RevelryExternalContext, request: RevelryPartyGamesPromptGenerateRequest) -> dict:
    title_context = context.external_container_title or "this party"
    prompt = request.prompt.strip() or f"{title_context} {request.game_type} prompts"
    await remote_config.get_config()
    provider = request.provider or remote_config.get_provider()
    model_override = remote_config.get_free_model()
    try:
        if request.game_type == "quiz":
            difficulty = request.difficulty if request.difficulty in config.VALID_DIFFICULTIES else "medium"
            quiz_data = await quiz_engine.generate_quiz(
                prompt,
                difficulty,
                max(config.MIN_QUESTIONS, min(config.MAX_QUESTIONS, request.num_prompts)),
                provider,
                model_override=model_override,
                mode="classic",
            )
            if not quiz_data:
                raise HTTPException(status_code=500, detail="Failed to generate quiz")
            quiz_data = _sanitize_quiz(quiz_data)
            if not _validate_quiz(quiz_data, attempt=0):
                raise HTTPException(status_code=500, detail="Failed to generate quiz")
            return {"quiz": quiz_data}
        if request.game_type == "wmlt":
            vibe = request.difficulty if request.difficulty in VALID_MLT_VIBES else "party"
            game_data = await mlt_engine.generate_statements(
                prompt,
                vibe,
                max(3, min(25, request.num_prompts)),
                provider,
                model_override=model_override,
            )
            if not game_data:
                raise HTTPException(status_code=500, detail="Failed to generate prompts")
            game_data = _sanitize_mlt(game_data)
            if not _validate_mlt(game_data, attempt=0):
                raise HTTPException(status_code=500, detail="Failed to generate prompts")
            return {"game": game_data}
        difficulty = request.difficulty if request.difficulty in config.VALID_DIFFICULTIES else "medium"
        game_data = await drawing_engine.generate_prompts(
            prompt,
            difficulty,
            max(config.MIN_QUESTIONS, min(config.MAX_QUESTIONS, request.num_prompts)),
            provider,
            model_override=model_override,
        )
        if not game_data:
            raise HTTPException(status_code=500, detail="Failed to generate prompts")
        game_data = _sanitize_drawing_game(game_data)
        if not _validate_drawing_game(game_data, attempt=0):
            raise HTTPException(status_code=500, detail="Failed to generate prompts")
        return {"game": game_data}
    except DailyLimitExceeded:
        raise HTTPException(status_code=429, detail="Daily generation limit reached. Please try again tomorrow!")
    except AIQuotaExceeded:
        raise HTTPException(status_code=503, detail="Generation is temporarily unavailable. Please try again later.")


def _content_save_id_for_request(context: RevelryExternalContext, request: RevelryContentSaveRequest) -> tuple[Optional[str], Optional[str]]:
    if not request.content_id:
        return None, None
    if db.game_content_has_sessions(context.host_app, context.external_container_id, request.content_id):
        return None, request.content_id
    return request.content_id, None


def _save_revelry_content(context: RevelryExternalContext, request: RevelryContentSaveRequest) -> tuple[dict, str, Optional[str]]:
    wallet_id = _revelry_party_wallet_id(context.external_container_id)
    save_content_id, previous_content_id = _content_save_id_for_request(context, request)
    if request.game_type == "quiz":
        quiz_data = _content_quiz_from_payload(request)
        content = db.save_quiz_pack(wallet_id, quiz_data.get("quiz_title", request.title or "Custom Quiz"), quiz_data["questions"], save_content_id)
    else:
        payload = _content_game_from_payload(request.game_type, request.title, request.content_payload)
        content = db.save_game_content(wallet_id, request.game_type, request.title or payload["game"].get("game_title", "Saved Game"), payload, save_content_id)
    event_type = "content.updated" if request.content_id else "content.created"
    return content, event_type, previous_content_id


@app.post("/integrations/revelry/content")
async def create_revelry_content(request: RevelryContentSaveRequest, req: Request):
    context, actor, claims = _require_authoring_or_service(req, request.external_context)
    if context.host_app != "revelry":
        raise HTTPException(status_code=422, detail="Unsupported host_app")
    if claims:
        actor = _actor_from_launch_context(claims["launch_context"])
        if claims.get("game_type") != request.game_type:
            raise HTTPException(status_code=422, detail="game_type does not match authoring token")
        token_content_id = claims.get("content_id") or ""
        if token_content_id and request.content_id and request.content_id != token_content_id:
            raise HTTPException(status_code=403, detail="content_id does not match authoring token")
        if token_content_id and not request.content_id:
            request.content_id = token_content_id
    elif request.actor:
        actor = request.actor
    if not _author_can_author(actor):
        raise HTTPException(status_code=403, detail="Missing capability to author content")
    _require_host_app_game_allowed(context, request.game_type, actor, "can_create_content")
    content, event_type, previous_content_id = _save_revelry_content(context, request)
    await _send_revelry_callback(event_type, {
        "host_app": context.host_app,
        "external_container_type": context.external_container_type,
        "external_container_id": context.external_container_id,
        "content_id": content["id"],
        "localplay_content_id": content["id"],
        "previous_content_id": previous_content_id,
        "versioned_from_content_id": previous_content_id,
        "content": _prepared_content_summary(content),
    })
    response = _content_response(context, content)
    if previous_content_id:
        response["previous_content_id"] = previous_content_id
        response["versioned_from_content_id"] = previous_content_id
        response["status"] = "version_created"
    return response


@app.get("/integrations/revelry/content/{content_id}")
async def get_revelry_content(
    content_id: str,
    req: Request,
    include_payload: bool = False,
    external_container_id: str = "",
    external_container_type: str = "party",
):
    request_context = RevelryExternalContext(
        external_container_id=external_container_id,
        external_container_type=external_container_type,
    ) if external_container_id else None
    context, _actor, claims = _require_authoring_or_service(req, request_context)
    if claims and claims.get("content_id") and claims.get("content_id") != content_id:
        raise HTTPException(status_code=403, detail="content_id does not match authoring token")
    pack = db.get_quiz_pack(_revelry_party_wallet_id(context.external_container_id), content_id)
    wallet_id = _revelry_party_wallet_id(context.external_container_id)
    content = pack or db.get_game_content(wallet_id, content_id)
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    response = {"content": _prepared_content_summary(content), "localplay_content_id": content["id"]}
    if include_payload:
        if pack:
            response["quiz"] = _pack_to_quiz(pack)
        else:
            response["content_payload"] = _game_content_payload(content)
    return response


@app.put("/integrations/revelry/content/{content_id}")
async def update_revelry_content(content_id: str, request: RevelryContentSaveRequest, req: Request):
    request.content_id = content_id
    return await create_revelry_content(request, req)


@app.delete("/integrations/revelry/content/{content_id}")
async def delete_revelry_content(
    content_id: str,
    req: Request,
    external_container_id: str = "",
    external_container_type: str = "party",
):
    request_context = RevelryExternalContext(
        external_container_id=external_container_id,
        external_container_type=external_container_type,
    ) if external_container_id else None
    context, actor, claims = _require_authoring_or_service(req, request_context)
    if claims and claims.get("content_id") and claims.get("content_id") != content_id:
        raise HTTPException(status_code=403, detail="content_id does not match authoring token")
    if claims:
        actor = _actor_from_launch_context(claims["launch_context"])
    if not _author_can_author(actor):
        raise HTTPException(status_code=403, detail="Missing capability to delete content")
    wallet_id = _revelry_party_wallet_id(context.external_container_id)
    pack = db.get_quiz_pack(wallet_id, content_id)
    content = pack or db.get_game_content(wallet_id, content_id)
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    deleted = db.delete_quiz_pack(wallet_id, content_id) if pack else db.delete_game_content(wallet_id, content_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Content not found")
    await _send_revelry_callback("content.deleted", {
        "host_app": context.host_app,
        "external_container_type": context.external_container_type,
        "external_container_id": context.external_container_id,
        "content_id": content_id,
        "localplay_content_id": content_id,
        "status": "deleted_by_host",
        "content": {**_prepared_content_summary(content), "status": "deleted_by_host"},
    })
    return {"status": "deleted_by_host", "localplay_content_id": content_id, "workspace": _workspace_payload(context)}


@app.get("/integrations/revelry/party-games/resolve")
async def resolve_revelry_party_games(party_games_token: str):
    launch_context = _resolve_party_games_token(party_games_token)
    context = RevelryExternalContext(
        host_app=launch_context.get("host_app", "revelry"),
        external_container_type=launch_context.get("external_container_type", "party"),
        external_container_id=launch_context["external_container_id"],
        external_container_title=launch_context.get("external_container_title", ""),
        party_type=launch_context.get("party_type", ""),
        brand_key=launch_context.get("brand_key", "revelry"),
        return_url=launch_context.get("return_url", ""),
    )
    actor = _actor_from_launch_context(launch_context)
    return {
        "launch_context": launch_context,
        "workspace": _workspace_payload(context, actor),
    }


@app.get("/integrations/revelry/games")
async def open_revelry_party_games(
    party_games_token: str = "",
    start_content_id: str = "",
    game_type: str = "",
    time_limit: Optional[int] = None,
):
    if not party_games_token:
        raise HTTPException(status_code=401, detail="party_games_token is required")
    _resolve_party_games_token(party_games_token)
    redirect_params: dict[str, Any] = {"party_games_token": party_games_token}
    if start_content_id:
        redirect_params["start_content_id"] = start_content_id
    if game_type:
        redirect_params["game_type"] = game_type
    if time_limit is not None:
        redirect_params["time_limit"] = time_limit
    redirect = f"/revelry/games?{urlencode(redirect_params)}"
    return RedirectResponse(redirect, status_code=302)


@app.get("/integrations/revelry/party-workspace")
async def get_revelry_party_workspace(
    req: Request,
    external_container_id: str,
    external_container_type: str = "party",
    external_container_title: str = "",
    host_user_id: str = "",
    external_user_id: str = "",
    role: str = "host",
):
    _require_revelry_auth(req)
    context = RevelryExternalContext(
        external_container_id=external_container_id,
        external_container_type=external_container_type,
        external_container_title=external_container_title,
        host_user_id=host_user_id,
    )
    actor = RevelryActor(external_user_id=external_user_id, role=role) if external_user_id else None
    return _workspace_payload(context, actor)


@app.post("/integrations/revelry/party-games/start")
async def start_revelry_party_game(request: RevelryPartyGameStartRequest, req: Request):
    launch_context = _resolve_party_games_token(request.party_games_token)
    capabilities = set(launch_context.get("capabilities") or [])
    if "operate_game" not in capabilities and "manage_games" not in capabilities:
        raise HTTPException(status_code=403, detail="Missing capability to start games")
    context = _external_context_from_launch_context(launch_context)
    actor = _actor_from_launch_context(launch_context)
    session = _create_revelry_session_from_context(
        context,
        actor,
        request.game_type,
        {"content_id": request.content_id, "time_limit": request.time_limit},
        req,
        replacement_confirmed=request.replacement_confirmed,
        replace_session_id=request.replace_session_id,
    )
    superseded = session.pop("_superseded_session", None)
    if superseded:
        await _send_revelry_callback("session.superseded", {
            "host_app": context.host_app,
            "external_container_type": context.external_container_type,
            "external_container_id": context.external_container_id,
            "session": _format_session(superseded),
        })
    return_token, _return_expires, return_context = _create_party_games_token(
        context,
        actor,
        launch_context.get("return_url", ""),
        launch_context.get("display") or {},
        ttl_seconds=config.REVELRY_PARTY_HUB_RETURN_TOKEN_TTL_SECONDS,
    )
    token, expires = _create_launch_token(
        session["id"],
        "organizer",
        "organizer",
        launch_context.get("return_url", ""),
        {
            **launch_context,
            "party_hub_url": f"{_public_base_url(req)}/revelry/games?party_games_token={return_token}",
            "party_hub_token_expires_at": _iso(_return_expires),
            "display": return_context.get("display") or launch_context.get("display") or {},
        },
    )
    base_url = _public_base_url(req)
    await _send_revelry_callback("session.created", {
        "host_app": context.host_app,
        "external_container_type": context.external_container_type,
        "external_container_id": context.external_container_id,
        "session": _format_session(session),
        "actor": _safe_actor_payload(actor),
    })
    return {
        "session": _format_session(session),
        "launch_url": f"{base_url}/organizer?session_id={session['id']}&launch_token={token}&embed=1",
        "launch_token_expires_at": _iso(expires),
    }


@app.post("/integrations/revelry/party-games/launch-token")
async def create_revelry_party_game_launch_token(request: RevelryPartyGameLaunchRequest, req: Request):
    launch_context = _resolve_party_games_token(request.party_games_token)
    route_by_scope = {"organizer": "organizer", "player": "join", "spectator": "spectate"}
    if request.route != route_by_scope[request.scope]:
        raise HTTPException(status_code=422, detail="route must match scope")
    capabilities = set(launch_context.get("capabilities") or [])
    if request.scope == "organizer" and "operate_game" not in capabilities and "manage_games" not in capabilities:
        raise HTTPException(status_code=403, detail="Missing capability to host games")

    context = _external_context_from_launch_context(launch_context)
    session = db.get_game_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.get("host_app") != context.host_app or session.get("external_container_id") != context.external_container_id:
        raise HTTPException(status_code=403, detail="Session does not belong to this Revelry party")
    formatted = _format_session(session)
    if not formatted["joinable"] and request.scope != "spectator":
        raise HTTPException(status_code=409, detail="Session is not joinable")

    token, expires = _create_launch_token(
        session["id"],
        request.scope,
        request.route,
        launch_context.get("return_url", ""),
        launch_context,
    )
    base_url = _public_base_url(req)
    query = f"session_id={session['id']}&launch_token={token}"
    if request.embed:
        query += "&embed=1"
    path = "organizer" if request.scope == "organizer" else "join" if request.scope == "player" else "spectator"
    return {
        "launch_url": f"{base_url}/{path}?{query}",
        "launch_token_expires_at": _iso(expires),
    }


@app.post("/integrations/revelry/party-games/content")
async def save_revelry_party_game_content(request: RevelryPartyGamesContentSaveRequest):
    launch_context = _resolve_party_games_token(request.party_games_token)
    actor = _actor_from_launch_context(launch_context)
    if not _author_can_author(actor):
        raise HTTPException(status_code=403, detail="Missing capability to author content")
    context = _external_context_from_launch_context(launch_context)
    _require_host_app_game_allowed(context, request.game_type, actor, "can_create_content")
    save_request = RevelryContentSaveRequest(
        external_context=context,
        actor=actor,
        game_type=request.game_type,
        title=request.title,
        content_id=request.content_id,
        content_payload=request.content_payload,
        status=request.status,
    )
    content, event_type, previous_content_id = _save_revelry_content(context, save_request)
    await _send_revelry_callback(event_type, {
        "host_app": context.host_app,
        "external_container_type": context.external_container_type,
        "external_container_id": context.external_container_id,
        "content_id": content["id"],
        "localplay_content_id": content["id"],
        "previous_content_id": previous_content_id,
        "versioned_from_content_id": previous_content_id,
        "content": _prepared_content_summary(content),
    })
    response = _content_response(context, content)
    if previous_content_id:
        response["previous_content_id"] = previous_content_id
        response["versioned_from_content_id"] = previous_content_id
        response["status"] = "version_created"
    return response


@app.post("/integrations/revelry/party-games/prompts/generate")
async def generate_revelry_party_game_prompts(request: RevelryPartyGamesPromptGenerateRequest):
    try:
        launch_context = _resolve_party_games_token(request.party_games_token)
        token_game_type = ""
    except HTTPException:
        claims = _resolve_authoring_token(request.party_games_token)
        launch_context = claims["launch_context"]
        token_game_type = claims.get("game_type") or ""
    if token_game_type and token_game_type != request.game_type:
        raise HTTPException(status_code=422, detail="game_type does not match authoring token")
    actor = _actor_from_launch_context(launch_context)
    if not _author_can_author(actor):
        raise HTTPException(status_code=403, detail="Missing capability to author content")
    context = _external_context_from_launch_context(launch_context)
    _require_host_app_game_allowed(context, request.game_type, actor, "supports_ai_generation")
    payload = await _generate_party_prompt_content(context, request)
    return {
        "game_type": request.game_type,
        "content_payload": payload,
    }


@app.get("/integrations/revelry/party-games/content/{content_id}")
async def get_revelry_party_game_content(content_id: str, party_games_token: str, include_payload: bool = False):
    launch_context = _resolve_party_games_token(party_games_token)
    actor = _actor_from_launch_context(launch_context)
    if not _author_can_author(actor):
        raise HTTPException(status_code=403, detail="Missing capability to author content")
    context = _external_context_from_launch_context(launch_context)
    wallet_id = _revelry_party_wallet_id(context.external_container_id)
    pack = db.get_quiz_pack(wallet_id, content_id)
    content = pack or db.get_game_content(wallet_id, content_id)
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    response = {"content": _prepared_content_summary(content), "localplay_content_id": content["id"]}
    if include_payload:
        if pack:
            response["quiz"] = _pack_to_quiz(pack)
        else:
            response["content_payload"] = _game_content_payload(content)
    return response


@app.delete("/integrations/revelry/party-games/content/{content_id}")
async def delete_revelry_party_game_content(content_id: str, request: RevelryPartyGamesContentDeleteRequest):
    launch_context = _resolve_party_games_token(request.party_games_token)
    actor = _actor_from_launch_context(launch_context)
    if "manage_games" not in set(actor.capabilities or []):
        raise HTTPException(status_code=403, detail="Missing capability to delete content")
    context = _external_context_from_launch_context(launch_context)
    wallet_id = _revelry_party_wallet_id(context.external_container_id)
    pack = db.get_quiz_pack(wallet_id, content_id)
    content = pack or db.get_game_content(wallet_id, content_id)
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    deleted = db.delete_quiz_pack(wallet_id, content_id) if pack else db.delete_game_content(wallet_id, content_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Content not found")
    await _send_revelry_callback("content.deleted", {
        "host_app": context.host_app,
        "external_container_type": context.external_container_type,
        "external_container_id": context.external_container_id,
        "content_id": content_id,
        "localplay_content_id": content_id,
        "status": "deleted_by_host",
        "content": {**_prepared_content_summary(content), "status": "deleted_by_host"},
    })
    return {"status": "deleted_by_host", "localplay_content_id": content_id, "workspace": _workspace_payload(context)}


@app.post("/integrations/revelry/sessions")
async def create_revelry_session(request: RevelrySessionCreateRequest, req: Request):
    _require_revelry_auth(req, request.handoff_token)
    context = request.external_context
    session = _create_revelry_session_from_context(
        context,
        request.actor,
        request.game_type,
        request.settings,
        req,
        replacement_confirmed=request.replacement_confirmed,
        replace_session_id=request.replace_session_id,
    )
    superseded = session.pop("_superseded_session", None)
    if superseded:
        await _send_revelry_callback("session.superseded", {
            "host_app": context.host_app,
            "external_container_type": context.external_container_type,
            "external_container_id": context.external_container_id,
            "session": _format_session(superseded),
        })
    await _send_revelry_callback("session.created", {
        "host_app": context.host_app,
        "external_container_type": context.external_container_type,
        "external_container_id": context.external_container_id,
        "session": _format_session(session),
        "actor": _safe_actor_payload(request.actor),
    })
    return _format_session(session)


@app.post("/integrations/revelry/sessions/{session_id}/launch-token")
async def create_revelry_launch_token(session_id: str, request: RevelryLaunchTokenRequest, req: Request):
    _require_revelry_auth(req)
    route_by_scope = {"organizer": "organizer", "player": "join", "spectator": "spectate"}
    if request.route != route_by_scope[request.scope]:
        raise HTTPException(status_code=422, detail="route must match scope")
    session = db.get_game_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    formatted = _format_session(session)
    if not formatted["joinable"] and request.scope != "spectator":
        raise HTTPException(status_code=409, detail="Session is not joinable")
    guest_join_url = request.guest_join_url or request.display.get("guest_join_url")
    if not guest_join_url and request.external_context:
        guest_join_url = request.external_context.guest_join_url
    guest_join_label = request.display.get("guest_join_label") or "Scan to join from Revelry"
    launch_context: dict[str, Any] = {}
    if guest_join_url:
        launch_context = {
            "mode": "host_app",
            "host_app": request.external_context.host_app if request.external_context else "revelry",
            "surface": request.scope,
            "display": {
                "guest_join_url": _validate_revelry_return_url(guest_join_url),
                "guest_join_label": guest_join_label,
            },
        }
    token, expires = _create_launch_token(session_id, request.scope, request.route, request.return_url, launch_context)
    base_url = _public_base_url(req)
    query = f"session_id={session_id}&launch_token={token}"
    if request.embed:
        query += "&embed=1"
    path = "organizer" if request.scope == "organizer" else "join" if request.scope == "player" else "spectator"
    return {
        "launch_url": f"{base_url}/{path}?{query}",
        "launch_token_expires_at": _iso(expires),
    }


@app.get("/integrations/revelry/launch-token/resolve")
async def resolve_revelry_launch_token(launch_token: str, scope: str = ""):
    claims = _resolve_launch_token(launch_token, expected_scope=scope or "")
    session = db.get_game_session(claims["session_id"])
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    formatted = _format_session(session)
    if not formatted["joinable"] and claims.get("scope") != "spectator":
        raise HTTPException(status_code=409, detail="Session is not joinable")
    payload = {
        "session_id": session["id"],
        "room_code": session["room_code"],
        "scope": claims.get("scope"),
        "return_url": claims.get("return_url", ""),
        "launch_context": claims.get("launch_context") or {},
    }
    if claims.get("scope") == "organizer":
        payload["organizer_token"] = session.get("organizer_token", "")
    return payload


@app.get("/integrations/revelry/sessions/{session_id}")
async def get_revelry_session_status(session_id: str, req: Request):
    _require_revelry_auth(req)
    session = db.get_game_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return _format_session(session)


@app.get("/integrations/revelry/sessions/{session_id}/results")
async def get_revelry_session_results(session_id: str, req: Request):
    _require_revelry_auth(req)
    session = db.get_game_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    result = session.get("result_summary")
    if not result:
        for game in reversed(game_history):
            if game.get("room_code") == session.get("room_code"):
                result = _safe_result_summary(game)
                break
    else:
        result = _safe_result_summary(result)
    return {
        "session_id": session_id,
        "status": _format_session(session)["status"],
        "result": result,
        "result_summary": result,
        "feed_card": {
            "title": f"{session.get('game_title') or 'LocalPlay'} results",
            "body": "Final results are ready.",
            "thumbnail_url": "",
        } if result else None,
    }


@app.get("/sessions/{session_id}/{route}")
async def launch_session_route(session_id: str, route: str, launch_token: str = "", embed: int = 0):
    if route not in ("organizer", "join", "spectate"):
        raise HTTPException(status_code=404, detail="Launch route not found")
    session = db.get_game_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    scope_by_route = {"organizer": "organizer", "join": "player", "spectate": "spectator"}
    if launch_token:
        _resolve_launch_token(launch_token, expected_session_id=session_id, expected_scope=scope_by_route[route])
    elif route == "organizer":
        raise HTTPException(status_code=401, detail="Organizer launch token required")

    if route == "organizer":
        path = f"/organizer?session_id={session_id}&launch_token={launch_token}"
    elif route == "spectate":
        path = f"/spectator?room={session['room_code']}"
    else:
        path = f"/join?room={session['room_code']}"
    if embed:
        path += "&embed=1"
    return RedirectResponse(path, status_code=302)


@app.get("/sd/status")
async def sd_status():
    """Legacy image-generation availability endpoint."""
    return {
        "available": await image_engine.is_available(),
        "provider": config.IMAGE_GENERATION_PROVIDER,
        "model": config.GEMINI_IMAGE_MODEL if config.IMAGE_GENERATION_PROVIDER == "gemini" else "stable_diffusion",
    }


@app.post("/room/create")
async def create_room(request: RoomCreateRequest, req: Request):
    content_id = (
        request.quiz_id if request.game_type == "quiz"
        else request.mlt_id if request.game_type == "wmlt"
        else request.drawing_id if request.game_type == "drawing"
        else request.housie_id
    )
    content_id, game_data = _resolve_runtime_content(request.game_type, content_id)
    time_limit = request.time_limit if request.time_limit is not None else _default_time_limit_for_game(request.game_type)
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=400, detail="Device ID required")
    tokens.ensure_wallet(wallet_id)
    _check_content_owner(content_id, wallet_id)
    if pending_generation_charges.get(content_id) == wallet_id and not tokens.can_generate(wallet_id):
        raise HTTPException(status_code=402, detail=f"You need {config.COST_GENERATE} token to use generated content. Buy tokens or watch an ad!")
    room_code, organizer_token = _create_runtime_room(request.game_type, content_id, game_data, wallet_id, time_limit)
    _settle_pending_generation_charge(content_id, wallet_id, room_code)
    return {"room_code": room_code, "organizer_token": organizer_token}


@app.websocket("/ws/{room_code}/{client_id}")
async def websocket_endpoint(websocket: WebSocket, room_code: str, client_id: str,
                             organizer: bool = False, spectator: bool = False):
    await socket_manager.connect(websocket, room_code, client_id,
                                 is_organizer=organizer, is_spectator=spectator)


# --- Export / Import ---

@app.get("/quiz/{quiz_id}/export")
async def export_quiz(quiz_id: str, req: Request):
    """Export a quiz as JSON for sharing/reuse. Answers stripped."""
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    if quiz_id not in quizzes:
        raise HTTPException(status_code=404, detail="Quiz not found")
    _check_content_owner(quiz_id, wallet_id)
    return {"quiz": quizzes[quiz_id]}


class QuizImportRequest(BaseModel):
    quiz: dict

    @field_validator('quiz')
    @classmethod
    def validate_quiz(cls, v: dict) -> dict:
        if "quiz_title" not in v or "questions" not in v:
            raise ValueError("Quiz must have quiz_title and questions")
        if not isinstance(v["questions"], list) or len(v["questions"]) == 0:
            raise ValueError("Quiz must have at least 1 question")
        for q in v["questions"]:
            if not all(k in q for k in ("id", "text", "options", "answer_index")):
                raise ValueError("Question missing required fields")
            if not isinstance(q["options"], list) or len(q["options"]) not in (2, 4):
                raise ValueError("Question must have 2 or 4 options")
            if not all(isinstance(opt, str) for opt in q["options"]):
                raise ValueError("Each option must be a string")
            if not isinstance(q["answer_index"], int) or not (0 <= q["answer_index"] < len(q["options"])):
                raise ValueError("Invalid answer_index")
        return v


@app.post("/quiz/import")
async def import_quiz(request: QuizImportRequest, req: Request):
    """Import a previously exported quiz."""
    wallet_id = _quiz_authoring_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    _evict_old_content()
    quiz_id = str(uuid.uuid4())
    quiz_data = _sanitize_quiz(request.quiz)
    if not _validate_quiz(quiz_data, attempt=0):
        raise HTTPException(status_code=422, detail="Invalid quiz data: check questions, options, and answer_index values")
    quizzes[quiz_id] = quiz_data
    quiz_timestamps[quiz_id] = time.time()
    content_owners[quiz_id] = wallet_id
    logger.info("Quiz imported: %s ('%s') owner=%s", quiz_id, quiz_data.get("quiz_title", "Untitled"), wallet_id[:8])
    return {"quiz_id": quiz_id, "quiz": _strip_answers(quizzes[quiz_id])}


# --- MLT (Most Likely To) Endpoints ---

VALID_MLT_VIBES = ("party", "spicy", "wholesome", "work", "custom")


class MLTRequest(BaseModel):
    prompt: str
    difficulty: str = "party"  # accepts vibe name or legacy difficulty
    num_rounds: int = 10
    provider: str = ""

    @field_validator('prompt')
    @classmethod
    def validate_prompt(cls, v: str) -> str:
        v = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', v)
        v = re.sub(r'<[^>]+>', '', v)
        v = v.strip()
        if not v or len(v) > config.MAX_PROMPT_LENGTH:
            raise ValueError(f'Prompt must be 1-{config.MAX_PROMPT_LENGTH} characters')
        lower_v = v.lower()
        injection_patterns = [
            r'ignore\s+(all\s+)?previous\s+instructions',
            r'ignore\s+(all\s+)?above',
            r'disregard\s+(all\s+)?previous',
            r'you\s+are\s+now\s+(?:a|an|in)',
            r'new\s+instructions?\s*:',
            r'system\s*:\s*',
            r'<\s*/?script',
            r'javascript\s*:',
        ]
        for pattern in injection_patterns:
            if re.search(pattern, lower_v):
                raise ValueError('Prompt contains disallowed content')
        return v

    @field_validator('difficulty')
    @classmethod
    def validate_difficulty(cls, v: str) -> str:
        v = v.lower().strip()
        # Accept both vibe names and legacy difficulty values
        if v not in VALID_MLT_VIBES and v not in config.VALID_DIFFICULTIES:
            raise ValueError(f'Vibe must be one of: {", ".join(VALID_MLT_VIBES)}')
        return v

    @field_validator('num_rounds')
    @classmethod
    def validate_num_rounds(cls, v: int) -> int:
        if v < 3 or v > 25:
            raise ValueError('Number of rounds must be 3-25')
        return v


@app.post("/mlt/generate")
async def generate_mlt(request: MLTRequest, req: Request):
    client_ip = _get_client_ip(req)
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait before generating.")
    device_id = tokens.get_device_id(req)
    if not device_id:
        raise HTTPException(status_code=400, detail="X-Device-Id header is required")
    idem_key = tokens.get_idempotency_key(req)

    # Idempotency: return cached result if this request was already processed.
    # If the generated content aged out of process memory, do not regenerate and
    # charge again for the same idempotency key.
    if idem_key:
        cached_id = db.check_idempotency(idem_key, device_id)
        if cached_id:
            if cached_id in mlt_scenarios:
                return {"scenario_id": cached_id, "game": mlt_scenarios[cached_id]}
            raise HTTPException(
                status_code=409,
                detail="Request was already processed, but the generated game is no longer available. Please start a new request.",
            )

    # Resolve wallet and check token balance
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=400, detail="X-Device-Id header is required")
    tokens.ensure_wallet(wallet_id)
    if not tokens.can_generate(wallet_id):
        raise HTTPException(status_code=402, detail=f"You need {config.COST_GENERATE} token to generate. Buy tokens or watch an ad!")

    if not _check_llm_budget():
        raise HTTPException(status_code=503, detail="Server is busy. Please try again later.")

    await remote_config.get_config()  # refresh if stale
    provider = request.provider or remote_config.get_provider()
    model_override = remote_config.get_paid_model() if tokens.use_premium_model(wallet_id) else remote_config.get_free_model()
    try:
        mlt_data = await mlt_engine.generate_statements(request.prompt, request.difficulty, request.num_rounds, provider, model_override=model_override)
    except DailyLimitExceeded:
        raise HTTPException(status_code=429, detail="Daily generation limit reached. Please try again tomorrow!")
    except AIQuotaExceeded:
        raise HTTPException(status_code=503, detail="Free tier limit reached. Upgrade for unlimited games.")
    if not mlt_data:
        raise HTTPException(status_code=500, detail="Failed to generate statements")

    _evict_old_content()
    scenario_id = str(uuid.uuid4())
    mlt_scenarios[scenario_id] = mlt_data
    mlt_timestamps[scenario_id] = time.time()
    content_owners[scenario_id] = wallet_id
    pending_generation_charges[scenario_id] = wallet_id
    if idem_key:
        db.record_idempotency(idem_key, device_id, scenario_id)
    logger.info("MLT created: %s ('%s') owner=%s", scenario_id, mlt_data.get("game_title", "Untitled"), wallet_id[:8])
    return {"scenario_id": scenario_id, "game": mlt_data}


@app.get("/mlt/{scenario_id}")
async def get_mlt(scenario_id: str):
    if scenario_id not in mlt_scenarios:
        raise HTTPException(status_code=404, detail="MLT scenario not found")
    return mlt_scenarios[scenario_id]


class MLTUpdateRequest(BaseModel):
    game_title: str
    statements: list

    @field_validator('statements')
    @classmethod
    def validate_statements(cls, v: list) -> list:
        if len(v) == 0:
            raise ValueError('Must have at least 1 statement')
        for s in v:
            if not isinstance(s, dict) or "id" not in s or "text" not in s:
                raise ValueError('Each statement must have id and text')
            if not isinstance(s["text"], str) or not s["text"].strip():
                raise ValueError('Statement text must be a non-empty string')
        return v


@app.put("/mlt/{scenario_id}")
async def update_mlt(scenario_id: str, request: MLTUpdateRequest, req: Request):
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    if scenario_id not in mlt_scenarios:
        raise HTTPException(status_code=404, detail="MLT scenario not found")
    _check_content_owner(scenario_id, wallet_id)
    mlt_data = {"game_title": request.game_title, "statements": request.statements}
    mlt_data = _sanitize_mlt(mlt_data)
    mlt_scenarios[scenario_id] = mlt_data
    logger.info("MLT updated: %s ('%s'), %d statements", scenario_id, mlt_data["game_title"], len(mlt_data["statements"]))
    return {"scenario_id": scenario_id, "game": mlt_scenarios[scenario_id]}


@app.delete("/mlt/{scenario_id}/statement/{statement_id}")
async def delete_mlt_statement(scenario_id: str, statement_id: int, req: Request):
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    if scenario_id not in mlt_scenarios:
        raise HTTPException(status_code=404, detail="MLT scenario not found")
    _check_content_owner(scenario_id, wallet_id)
    game = mlt_scenarios[scenario_id]
    remaining = [s for s in game["statements"] if s["id"] != statement_id]
    if len(remaining) == len(game["statements"]):
        raise HTTPException(status_code=404, detail="Statement not found")
    if len(remaining) == 0:
        raise HTTPException(status_code=400, detail="Cannot delete the last statement")
    game["statements"] = remaining
    return {"scenario_id": scenario_id, "game": game}


@app.get("/mlt/{scenario_id}/export")
async def export_mlt(scenario_id: str, req: Request):
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    if scenario_id not in mlt_scenarios:
        raise HTTPException(status_code=404, detail="MLT scenario not found")
    _check_content_owner(scenario_id, wallet_id)
    return {"game": mlt_scenarios[scenario_id]}


class MLTImportRequest(BaseModel):
    game: dict

    @field_validator('game')
    @classmethod
    def validate_game(cls, v: dict) -> dict:
        if "game_title" not in v or "statements" not in v:
            raise ValueError("Game must have game_title and statements")
        if not isinstance(v["statements"], list) or len(v["statements"]) == 0:
            raise ValueError("Game must have at least 1 statement")
        for s in v["statements"]:
            if not isinstance(s, dict) or "id" not in s or "text" not in s:
                raise ValueError("Statement missing required fields")
            if not isinstance(s["text"], str):
                raise ValueError("Statement text must be a string")
        return v


@app.post("/mlt/import")
async def import_mlt(request: MLTImportRequest, req: Request):
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    _evict_old_content()
    scenario_id = str(uuid.uuid4())
    mlt_data = _sanitize_mlt(request.game)
    if not _validate_mlt(mlt_data, attempt=0):
        raise HTTPException(status_code=422, detail="Invalid MLT data: check statements have id and text fields")
    mlt_scenarios[scenario_id] = mlt_data
    mlt_timestamps[scenario_id] = time.time()
    content_owners[scenario_id] = wallet_id
    logger.info("MLT imported: %s ('%s') owner=%s", scenario_id, mlt_data.get("game_title", "Untitled"), wallet_id[:8])
    return {"scenario_id": scenario_id, "game": mlt_scenarios[scenario_id]}


# --- DrawingGame Endpoints ---


class DrawingRequest(BaseModel):
    prompt: str
    difficulty: str = "medium"
    num_prompts: int = config.DEFAULT_NUM_QUESTIONS
    provider: str = ""

    @field_validator('prompt')
    @classmethod
    def validate_prompt(cls, v: str) -> str:
        v = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', v)
        v = re.sub(r'<[^>]+>', '', v).strip()
        if not v or len(v) > config.MAX_PROMPT_LENGTH:
            raise ValueError(f'Prompt must be 1-{config.MAX_PROMPT_LENGTH} characters')
        lower_v = v.lower()
        injection_patterns = [
            r'ignore\s+(all\s+)?previous\s+instructions',
            r'ignore\s+(all\s+)?above',
            r'disregard\s+(all\s+)?previous',
            r'you\s+are\s+now\s+(?:a|an|in)',
            r'new\s+instructions?\s*:',
            r'system\s*:\s*',
            r'<\s*/?script',
            r'javascript\s*:',
        ]
        for pattern in injection_patterns:
            if re.search(pattern, lower_v):
                raise ValueError('Prompt contains disallowed content')
        return v

    @field_validator('difficulty')
    @classmethod
    def validate_difficulty(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in config.VALID_DIFFICULTIES:
            raise ValueError(f'Difficulty must be one of: {", ".join(config.VALID_DIFFICULTIES)}')
        return v

    @field_validator('num_prompts')
    @classmethod
    def validate_num_prompts(cls, v: int) -> int:
        if v < config.MIN_QUESTIONS or v > config.MAX_QUESTIONS:
            raise ValueError(f'Number of prompts must be {config.MIN_QUESTIONS}-{config.MAX_QUESTIONS}')
        return v


@app.post("/drawing/generate")
async def generate_drawing(request: DrawingRequest, req: Request):
    client_ip = _get_client_ip(req)
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait before generating.")
    device_id = tokens.get_device_id(req)
    if not device_id:
        raise HTTPException(status_code=400, detail="X-Device-Id header is required")
    idem_key = tokens.get_idempotency_key(req)

    if idem_key:
        cached_id = db.check_idempotency(idem_key, device_id)
        if cached_id:
            if cached_id in drawing_games:
                return {"drawing_id": cached_id, "game": drawing_games[cached_id]}
            raise HTTPException(
                status_code=409,
                detail="Request was already processed, but the generated drawing game is no longer available. Please start a new request.",
            )

    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=400, detail="X-Device-Id header is required")
    tokens.ensure_wallet(wallet_id)
    if not tokens.can_generate(wallet_id):
        raise HTTPException(status_code=402, detail=f"You need {config.COST_GENERATE} token to generate. Buy tokens or watch an ad!")

    if not _check_llm_budget():
        raise HTTPException(status_code=503, detail="Server is busy. Please try again later.")

    await remote_config.get_config()
    provider = request.provider or remote_config.get_provider()
    model_override = remote_config.get_paid_model() if tokens.use_premium_model(wallet_id) else remote_config.get_free_model()
    try:
        drawing_data = await drawing_engine.generate_prompts(
            request.prompt,
            request.difficulty,
            request.num_prompts,
            provider,
            model_override=model_override,
        )
    except DailyLimitExceeded:
        raise HTTPException(status_code=429, detail="Daily generation limit reached. Please try again tomorrow!")
    except AIQuotaExceeded:
        raise HTTPException(status_code=503, detail="Free tier limit reached. Upgrade for unlimited games.")
    if not drawing_data:
        raise HTTPException(status_code=500, detail="Failed to generate drawing prompts")

    _evict_old_content()
    drawing_id = str(uuid.uuid4())
    drawing_games[drawing_id] = drawing_data
    drawing_timestamps[drawing_id] = time.time()
    content_owners[drawing_id] = wallet_id
    pending_generation_charges[drawing_id] = wallet_id
    if idem_key:
        db.record_idempotency(idem_key, device_id, drawing_id)
    logger.info("DrawingGame created: %s ('%s') owner=%s", drawing_id, drawing_data.get("game_title", "Untitled"), wallet_id[:8])
    return {"drawing_id": drawing_id, "game": drawing_data}


@app.get("/drawing/{drawing_id}")
async def get_drawing(drawing_id: str):
    if drawing_id not in drawing_games:
        raise HTTPException(status_code=404, detail="Drawing game not found")
    return drawing_games[drawing_id]


class DrawingUpdateRequest(BaseModel):
    game_title: str
    prompts: list

    @field_validator('prompts')
    @classmethod
    def validate_prompts(cls, v: list) -> list:
        if len(v) == 0:
            raise ValueError('Must have at least 1 prompt')
        for p in v:
            if not isinstance(p, dict) or "id" not in p or "text" not in p:
                raise ValueError('Each prompt must have id and text')
            if not isinstance(p["text"], str) or not p["text"].strip():
                raise ValueError('Prompt text must be a non-empty string')
            aliases = p.get("aliases", [])
            if aliases is not None and (not isinstance(aliases, list) or not all(isinstance(a, str) for a in aliases)):
                raise ValueError('Aliases must be a list of strings')
        return v


@app.put("/drawing/{drawing_id}")
async def update_drawing(drawing_id: str, request: DrawingUpdateRequest, req: Request):
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    if drawing_id not in drawing_games:
        raise HTTPException(status_code=404, detail="Drawing game not found")
    _check_content_owner(drawing_id, wallet_id)
    drawing_data = _sanitize_drawing_game({"game_title": request.game_title, "prompts": request.prompts})
    drawing_games[drawing_id] = drawing_data
    logger.info("DrawingGame updated: %s ('%s'), %d prompts", drawing_id, drawing_data["game_title"], len(drawing_data["prompts"]))
    return {"drawing_id": drawing_id, "game": drawing_games[drawing_id]}


@app.delete("/drawing/{drawing_id}/prompt/{prompt_id}")
async def delete_drawing_prompt(drawing_id: str, prompt_id: int, req: Request):
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    if drawing_id not in drawing_games:
        raise HTTPException(status_code=404, detail="Drawing game not found")
    _check_content_owner(drawing_id, wallet_id)
    game = drawing_games[drawing_id]
    remaining = [p for p in game["prompts"] if p["id"] != prompt_id]
    if len(remaining) == len(game["prompts"]):
        raise HTTPException(status_code=404, detail="Prompt not found")
    if len(remaining) == 0:
        raise HTTPException(status_code=400, detail="Cannot delete the last prompt")
    game["prompts"] = remaining
    return {"drawing_id": drawing_id, "game": game}


# --- Housie Endpoints ---


class HousieCreateRequest(BaseModel):
    game_title: str = "Housie"
    pattern_ids: List[str] = Field(default_factory=lambda: [pattern["id"] for pattern in DEFAULT_HOUSIE_PATTERNS])
    play_mode: str = "beginner"
    caller_mode: str = "manual"
    auto_interval_seconds: int = 8
    auto_pause_on_claim: bool = True

    @field_validator("game_title")
    @classmethod
    def validate_game_title(cls, value: str) -> str:
        value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value or "").strip()
        if not value or len(value) > 120:
            raise ValueError("Game title must be 1-120 characters")
        return value

    @field_validator("caller_mode")
    @classmethod
    def validate_caller_mode(cls, value: str) -> str:
        value = (value or "manual").lower().strip()
        if value not in ("manual", "auto"):
            raise ValueError('caller_mode must be "manual" or "auto"')
        return value

    @field_validator("play_mode")
    @classmethod
    def validate_play_mode(cls, value: str) -> str:
        value = (value or "beginner").lower().strip()
        if value not in ("beginner", "pro"):
            raise ValueError('play_mode must be "beginner" or "pro"')
        return value

    @field_validator("auto_interval_seconds")
    @classmethod
    def validate_auto_interval(cls, value: int) -> int:
        if value < 3 or value > 30:
            raise ValueError("auto_interval_seconds must be 3-30")
        return value


@app.post("/housie/create")
async def create_housie(request: HousieCreateRequest, req: Request):
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=400, detail="X-Device-Id header is required")
    tokens.ensure_wallet(wallet_id)
    _evict_old_content()
    game_data = _sanitize_housie_game({
        "game_title": request.game_title,
        "pattern_ids": request.pattern_ids,
        "play_mode": request.play_mode,
        "caller_mode": request.caller_mode,
        "auto_interval_seconds": request.auto_interval_seconds,
        "auto_pause_on_claim": request.auto_pause_on_claim,
    })
    housie_id = str(uuid.uuid4())
    housie_games[housie_id] = game_data
    housie_timestamps[housie_id] = time.time()
    content_owners[housie_id] = wallet_id
    logger.info("Housie created: %s ('%s') owner=%s", housie_id, game_data["game_title"], wallet_id[:8])
    return {"housie_id": housie_id, "game": game_data}


@app.get("/housie/{housie_id}")
async def get_housie(housie_id: str):
    if housie_id not in housie_games:
        raise HTTPException(status_code=404, detail="Housie game not found")
    return housie_games[housie_id]


@app.put("/housie/{housie_id}")
async def update_housie(housie_id: str, request: HousieCreateRequest, req: Request):
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    if housie_id not in housie_games:
        raise HTTPException(status_code=404, detail="Housie game not found")
    _check_content_owner(housie_id, wallet_id)
    game_data = _sanitize_housie_game({
        "game_title": request.game_title,
        "pattern_ids": request.pattern_ids,
        "play_mode": request.play_mode,
        "caller_mode": request.caller_mode,
        "auto_interval_seconds": request.auto_interval_seconds,
        "auto_pause_on_claim": request.auto_pause_on_claim,
    })
    housie_games[housie_id] = game_data
    return {"housie_id": housie_id, "game": game_data}


# --- Game History ---

game_history: List[dict] = []


@app.get("/history")
async def get_game_history(req: Request):
    """Get history of completed games scoped to the requesting wallet."""
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    my_games = [g for g in game_history if g.get("wallet_id") == wallet_id]
    return {"games": my_games}


@app.get("/history/{room_code}")
async def get_game_detail(room_code: str, req: Request):
    """Get detailed results of a specific game. Must be the organizer."""
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    game = next((g for g in game_history if g["room_code"] == room_code), None)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.get("wallet_id") != wallet_id:
        raise HTTPException(status_code=403, detail="Not your game")
    return game


# Configure CORS
if config.ALLOWED_ORIGINS.strip():
    origins = [o.strip() for o in config.ALLOWED_ORIGINS.split(",")]
else:
    local_ip = get_local_ip()
    origins = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:9200",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:9200",
        f"http://{local_ip}:5173",
        f"http://{local_ip}:5174",
        f"http://{local_ip}:9200",
        # Capacitor native app origins
        "capacitor://localhost",  # iOS
        "http://localhost",       # Android
        "https://localhost",      # Android (androidScheme: https)
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-Device-Id", "X-Platform", "X-App-Version", "X-Build", "X-Idempotency-Key", "Idempotency-Key", "X-Session-Token"],
)

# Share allowed origins with WebSocket manager for origin validation
socket_manager.allowed_origins = origins


# --- Auth (Phase 2) ---

class SignInRequest(BaseModel):
    provider: str
    id_token: str
    device_id: str

    @field_validator('provider')
    @classmethod
    def validate_provider(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in ("google", "apple"):
            raise ValueError('Provider must be "google" or "apple"')
        return v

    @field_validator('id_token')
    @classmethod
    def validate_id_token(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError('id_token is required')
        if len(v) > 10000:
            raise ValueError('id_token is too long')
        return v

    @field_validator('device_id')
    @classmethod
    def validate_device_id(cls, v: str) -> str:
        v = v.strip()
        if not tokens._UUID_RE.match(v):
            raise ValueError('device_id must be a valid UUID')
        return v


@app.post("/auth/signin")
async def auth_signin(request: SignInRequest, req: Request):
    # Bind body device_id to caller's device context (X-Device-Id header)
    header_device_id = tokens.get_device_id(req)
    if header_device_id and header_device_id != request.device_id:
        raise HTTPException(status_code=400, detail="device_id does not match X-Device-Id header")
    result = auth.signin(request.provider, request.id_token, request.device_id)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid or expired ID token")
    # Migrate game history from device wallet to user wallet
    user_id = result["user"]["id"]
    for game in game_history:
        if game.get("wallet_id") == request.device_id:
            game["wallet_id"] = user_id
    return result


@app.get("/auth/me")
async def auth_me(req: Request):
    session = auth.get_session_from_request(req)
    if not session:
        raise HTTPException(status_code=401, detail="Not signed in")
    user = db.get_user(session["user_id"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    token_status = tokens.get_token_status(user["id"])

    return {
        "user": {
            "id": user["id"],
            "provider": user["provider"],
            "email": user.get("email"),
        },
        "tokens": token_status,
    }


# --- Premium / Checkout ---

class CheckoutRequest(BaseModel):
    device_id: str
    promo_id: str = ""

    @field_validator('device_id')
    @classmethod
    def validate_device_id(cls, v: str) -> str:
        v = v.strip()
        if not tokens._UUID_RE.match(v):
            raise ValueError('device_id must be a valid UUID')
        return v

    @field_validator('promo_id')
    @classmethod
    def validate_promo_id(cls, v: str) -> str:
        v = v.strip()
        if v and (len(v) > 50 or not re.match(r'^[a-zA-Z0-9_-]+$', v)):
            return ""  # Silently discard invalid promo IDs
        return v


@app.post("/checkout/create")
async def create_checkout(request: CheckoutRequest, req: Request):
    # Enforce iOS IAP-only rule: block Stripe on native iOS
    platform = tokens.get_platform(req)
    if platform == "ios":
        raise HTTPException(status_code=403, detail="Use in-app purchase on iOS")

    # Verify body device_id matches header device_id
    header_device_id = tokens.get_device_id(req)
    if header_device_id and header_device_id != request.device_id:
        raise HTTPException(status_code=400, detail="Device ID mismatch")

    if not config.STRIPE_SECRET_KEY or not config.STRIPE_PRICE_ID:
        raise HTTPException(status_code=503, detail="Payments not configured")
    import stripe
    stripe.api_key = config.STRIPE_SECRET_KEY

    # Resolve wallet for this user/device
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=400, detail="Device ID required")
    tokens.ensure_wallet(wallet_id)

    # Determine token amount (promo or standard)
    promo_id = request.promo_id.strip()
    if promo_id and promo_id == config.PROMO_ID and config.PROMO_TOKEN_AMOUNT > 0:
        token_amount = config.PROMO_TOKEN_AMOUNT
    else:
        token_amount = config.TOKEN_PACK_AMOUNT
        promo_id = ""  # Clear invalid promo

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price": config.STRIPE_PRICE_ID, "quantity": 1}],
            metadata={
                "device_id": request.device_id,
                "wallet_id": wallet_id,
                "token_amount": str(token_amount),
                "promo_id": promo_id,
            },
            success_url=f"{config.CHECKOUT_RETURN_URL or origins[0]}?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{config.CHECKOUT_RETURN_URL or origins[0]}?checkout=cancel",
        )
        return {"checkout_url": session.url, "session_id": session.id}
    except Exception as e:
        logger.error("Stripe checkout error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create checkout session")


@app.post("/webhook/stripe")
async def stripe_webhook(req: Request):
    if not config.STRIPE_SECRET_KEY or not config.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Payments not configured")
    import stripe
    stripe.api_key = config.STRIPE_SECRET_KEY
    payload = await req.body()
    sig = req.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, config.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.SignatureVerificationError) as e:
        logger.warning("Stripe webhook signature failed: %s", e)
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Deduplicate webhook events (DB-backed, survives restarts)
    event_id = event.get("id", "")
    if event_id and db.is_webhook_event_processed(event_id):
        logger.info("Skipping duplicate webhook event: %s", event_id)
        return {"status": "ok", "detail": "already processed"}

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        stripe_session_id = session.get("id", "")
        metadata = session.get("metadata", {})
        device_id = metadata.get("device_id", "")
        wallet_id = metadata.get("wallet_id", "")

        if not wallet_id:
            # Fallback: use device_id as wallet_id (backward compat)
            wallet_id = device_id

        if not wallet_id:
            logger.error("No wallet_id in webhook metadata for session %s", stripe_session_id[:8])
            return {"status": "error", "detail": "No wallet_id in metadata"}

        # Read token amount from metadata (set at checkout creation), fallback to config
        # Cap to max allowed amount to prevent metadata tampering
        import json
        max_allowed = max(config.TOKEN_PACK_AMOUNT, config.PROMO_TOKEN_AMOUNT) if config.PROMO_TOKEN_AMOUNT > 0 else config.TOKEN_PACK_AMOUNT
        try:
            raw_token_amount = int(metadata.get("token_amount") or config.TOKEN_PACK_AMOUNT)
        except (ValueError, TypeError):
            raw_token_amount = config.TOKEN_PACK_AMOUNT
        token_amount = min(raw_token_amount, max_allowed) if raw_token_amount > 0 else config.TOKEN_PACK_AMOUNT
        if raw_token_amount > max_allowed:
            logger.warning("Refund token_amount capped: requested %d, allowed %d (session %s)", raw_token_amount, max_allowed, stripe_session_id[:8])
        promo_id = metadata.get("promo_id", "")
        txn_metadata = json.dumps({"promo_id": promo_id}) if promo_id else ""

        # Credit tokens to wallet (idempotent — credit_purchase checks for duplicate reference_id atomically)
        _, new_balance = db.credit_purchase(wallet_id, token_amount, stripe_session_id, metadata=txn_metadata)
        logger.info("Credited %d tokens to wallet %s (session %s, promo=%s, balance=%d)",
                    token_amount, wallet_id[:8], stripe_session_id[:8], promo_id or "none", new_balance)

        # Store pickup notification for frontend polling
        if device_id:
            notification = json.dumps({"tokens_added": token_amount, "new_balance": db.get_wallet_balance(wallet_id)})
            db.store_pending_token(device_id, notification)

    elif event["type"] in ("charge.refunded", "charge.dispute.created"):
        # Debit tokens back on refund/chargeback
        charge = event["data"]["object"]
        payment_intent_id = charge.get("payment_intent", "")
        if payment_intent_id:
            try:
                sessions = stripe.checkout.Session.list(payment_intent=payment_intent_id, limit=1)
                if sessions.data:
                    stripe_session_id = sessions.data[0].id
                    refund_metadata = sessions.data[0].metadata
                    wallet_id = refund_metadata.get("wallet_id", "")
                    try:
                        tokens_purchased = int(refund_metadata.get("token_amount") or config.TOKEN_PACK_AMOUNT)
                    except (ValueError, TypeError):
                        tokens_purchased = config.TOKEN_PACK_AMOUNT
                    token_cap = max(config.TOKEN_PACK_AMOUNT, config.PROMO_TOKEN_AMOUNT) if config.PROMO_TOKEN_AMOUNT > 0 else config.TOKEN_PACK_AMOUNT
                    tokens_purchased = min(tokens_purchased, token_cap) if tokens_purchased > 0 else config.TOKEN_PACK_AMOUNT

                    # Prorate tokens for partial refunds based on cumulative refund/charge ratio
                    charge_amount = charge.get("amount", 0)  # cents
                    refunded_amount = charge.get("amount_refunded", charge_amount)  # cents (cumulative)
                    if charge_amount > 0 and refunded_amount < charge_amount:
                        # Partial refund — prorate tokens proportionally, round up
                        total_owed = max(1, -(-tokens_purchased * refunded_amount // charge_amount))
                    else:
                        # Full refund or dispute
                        total_owed = tokens_purchased

                    # Subtract tokens already debited for prior refunds on this session
                    already_debited = db.get_refund_debits_for_session(stripe_session_id)
                    refund_tokens = max(0, total_owed - already_debited)

                    if wallet_id and refund_tokens > 0:
                        success, _ = db.debit_tokens(wallet_id, refund_tokens, "refund", stripe_session_id)
                        if not success:
                            logger.warning("Failed to debit tokens for refund: wallet=%s session=%s amount=%d",
                                           wallet_id, stripe_session_id, refund_tokens)
                        else:
                            logger.info("Debited %d tokens from wallet %s (refund %d/%d cents, prior=%d, session %s)",
                                        refund_tokens, wallet_id[:8], refunded_amount, charge_amount, already_debited, stripe_session_id[:8])
                    elif wallet_id and refund_tokens == 0:
                        logger.info("Refund already fully debited for session %s (owed=%d, debited=%d)",
                                    stripe_session_id[:8], total_owed, already_debited)
            except Exception as e:
                logger.error("Failed to process refund: %s", e)
                raise  # Let Stripe retry — don't mark event as processed

    # Mark event as processed AFTER business logic succeeds
    if event_id:
        db.mark_webhook_event_processed(event_id)

    return {"status": "ok"}


@app.get("/checkout/token")
async def get_checkout_token(req: Request):
    """Poll for checkout completion — returns token credit notification."""
    device_id = tokens.get_device_id(req)
    if not device_id:
        raise HTTPException(status_code=400, detail="X-Device-Id header is required")
    notification = db.pop_pending_token(device_id)
    if not notification:
        raise HTTPException(status_code=404, detail="Token not ready")
    # notification is JSON string: {"tokens_added": 110, "new_balance": X}
    import json
    try:
        return json.loads(notification)
    except (json.JSONDecodeError, TypeError):
        return {"tokens_added": config.TOKEN_PACK_AMOUNT}


@app.get("/tokens/balance")
async def token_balance(req: Request):
    """Get current token balance. Auto-grants daily bonus if new UTC day."""
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        device_id = tokens.get_device_id(req)
        if not device_id:
            return {"balance": 0, "has_purchased": False, "daily_bonus_available": False,
                    "daily_bonus_granted": False, "bonus_amount": 0,
                    "cost_generate": config.COST_GENERATE, "cost_room": config.COST_ROOM,
                    "ads_remaining_today": config.MAX_ADS_PER_DAY}
        wallet_id = device_id
    return tokens.get_token_status(wallet_id)


# Keep old endpoint as alias for backward compatibility during rollout
@app.get("/entitlements/current")
async def entitlement_status_compat(req: Request):
    """Legacy endpoint — redirects to token balance."""
    return await token_balance(req)


@app.post("/tokens/ad-reward")
async def ad_reward(req: Request):
    """Grant tokens for watching an ad. V1: trust client + daily cap + rate limit."""
    client_ip = _get_client_ip(req)
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait.")
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=400, detail="X-Device-Id header is required")
    tokens.ensure_wallet(wallet_id)
    granted, new_balance, ads_remaining = db.check_and_grant_ad_reward(wallet_id)
    if not granted:
        raise HTTPException(status_code=429, detail="Daily ad limit reached. Come back tomorrow!")
    return {"granted": True, "tokens_added": config.AD_REWARD_TOKENS,
            "new_balance": new_balance, "ads_remaining_today": ads_remaining}


@app.post("/purchases/restore")
async def restore_purchases(req: Request):
    """Restore IAP purchases — credits tokens if not already credited."""
    device_id = tokens.get_device_id(req)
    if not device_id:
        raise HTTPException(status_code=400, detail="X-Device-Id header is required")

    session = auth.get_session_from_request(req)
    user_id = session["user_id"] if session else None

    ent = db.find_restorable_entitlement(device_id, user_id=user_id)
    if not ent:
        return {"restored": False}

    if ent["status"] != "active":
        return {"restored": False, "reason": "expired"}

    # Credit remaining games as tokens (if not already migrated)
    wallet_id = user_id or device_id
    tokens_to_credit = ent["games_remaining"] * config.COST_ROOM
    if tokens_to_credit > 0:
        db.credit_tokens(wallet_id, tokens_to_credit, "restore", reference_id=ent["id"])
    new_balance = db.get_wallet_balance(wallet_id)
    return {"restored": True, "tokens_added": tokens_to_credit, "new_balance": new_balance}


# --- Admin Endpoints ---

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")


def _check_admin(req: Request):
    """Verify admin API key from Authorization header (constant-time compare)."""
    if not ADMIN_API_KEY:
        raise HTTPException(status_code=503, detail="Admin API not configured")
    auth_header = req.headers.get("Authorization", "")
    expected = f"Bearer {ADMIN_API_KEY}"
    if not hmac.compare_digest(auth_header.encode(), expected.encode()):
        raise HTTPException(status_code=403, detail="Forbidden")


@app.get("/admin/lookup")
async def admin_lookup(req: Request, device_id: str = "", wallet_id: str = "", user_id: str = "", email: str = ""):
    _check_admin(req)
    if wallet_id:
        result = db.admin_lookup_wallet(wallet_id)
        if not result:
            raise HTTPException(status_code=404, detail="Wallet not found")
        return result
    if device_id:
        # Look up wallet by device_id + legacy entitlement data
        wallet = db.admin_lookup_wallet(device_id)
        legacy = db.lookup_by_device(device_id)
        return {"wallet": wallet, "legacy": legacy}
    if user_id:
        wallet = db.admin_lookup_wallet(user_id)
        legacy = db.lookup_by_user(user_id)
        return {"wallet": wallet, "legacy": legacy}
    if email:
        users = db.lookup_user_by_email(email)
        if not users:
            raise HTTPException(status_code=404, detail="No users found")
        return {"results": users}
    raise HTTPException(status_code=400, detail="Provide wallet_id, device_id, user_id, or email")


@app.post("/admin/grant")
async def admin_grant(req: Request, wallet_id: str = "", device_id: str = "", user_id: str = "", amount: int = 110):
    _check_admin(req)
    target = wallet_id or user_id or device_id
    if not target:
        raise HTTPException(status_code=400, detail="Provide wallet_id, device_id, or user_id")
    if amount <= 0 or amount > config.MAX_TOKEN_BALANCE:
        raise HTTPException(status_code=400, detail=f"Amount must be between 1 and {config.MAX_TOKEN_BALANCE}")
    new_balance = db.admin_grant_tokens(target, amount)
    return {"status": "granted", "wallet_id": target, "tokens_granted": amount, "new_balance": new_balance}


@app.get("/admin/stats")
async def admin_stats(req: Request):
    """Live server stats: LLM usage, rooms, wallets, revenue."""
    _check_admin(req)
    now = time.time()
    cutoff = now - 3600

    # LLM budget
    active_llm_calls = len([t for t in _llm_call_timestamps if t > cutoff])

    # Active rooms
    active_rooms = len(socket_manager.rooms)
    total_connections = sum(len(r.connections) for r in socket_manager.rooms.values())

    # Content in memory
    total_quizzes = len(quizzes)
    total_mlt = len(mlt_scenarios)
    total_drawing = len(drawing_games)
    total_housie = len(housie_games)

    # Database stats
    db_stats = db.get_admin_stats()

    # Rate limit pressure
    active_ips = len(_rate_limit_store)

    return {
        "llm": {
            "calls_last_hour": active_llm_calls,
            "budget_per_hour": config.MAX_LLM_CALLS_PER_HOUR,
            "budget_remaining": max(0, config.MAX_LLM_CALLS_PER_HOUR - active_llm_calls),
            "utilization_pct": round(active_llm_calls / config.MAX_LLM_CALLS_PER_HOUR * 100, 1) if config.MAX_LLM_CALLS_PER_HOUR > 0 else 0,
        },
        "rooms": {
            "active": active_rooms,
            "total_connections": total_connections,
        },
        "content": {
            "quizzes_in_memory": total_quizzes,
            "mlt_in_memory": total_mlt,
            "drawing_in_memory": total_drawing,
            "housie_in_memory": total_housie,
        },
        "economy": {
            "total_wallets": db_stats["wallet_count"],
            "total_sparks_in_circulation": db_stats["total_sparks"],
            "paying_users": db_stats["paying_users"],
            "total_purchases": db_stats["purchase_count"],
            "total_merges": db_stats["merge_count"],
        },
        "users": {
            "signed_in_accounts": db_stats["users_count"],
        },
        "rate_limiting": {
            "tracked_ips": active_ips,
        },
    }


class HostAppCatalogFlagRequest(BaseModel):
    environment: str = Field(default_factory=lambda: config.ENVIRONMENT)
    host_app: str = "revelry"
    game_id: str
    enabled: bool = False
    status: str = "disabled"
    allowlist_party_ids: list[str] = Field(default_factory=list)
    allowlist_external_user_ids: list[str] = Field(default_factory=list)
    rollout_percentage: Optional[int] = None
    capability_overrides: dict[str, bool] = Field(default_factory=dict)
    notes: str = ""
    updated_by: str = ""

    @field_validator("environment", "host_app", "game_id", "status")
    @classmethod
    def _required_text(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("value is required")
        return value

    @field_validator("status")
    @classmethod
    def _valid_status(cls, value: str) -> str:
        if value not in {"live", "gamma", "planned", "disabled"}:
            raise ValueError("invalid status")
        return value

    @field_validator("rollout_percentage")
    @classmethod
    def _valid_rollout(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and not 0 <= value <= 100:
            raise ValueError("rollout_percentage must be between 0 and 100")
        return value


@app.get("/admin/host-app-catalog-flags")
async def admin_list_host_app_catalog_flags(req: Request, environment: str = "", host_app: str = "revelry"):
    _check_admin(req)
    env = (environment or config.ENVIRONMENT).strip()
    return {"flags": db.list_host_app_catalog_flags(env, host_app)}


@app.post("/admin/host-app-catalog-flags")
async def admin_upsert_host_app_catalog_flag(req: Request, request: HostAppCatalogFlagRequest):
    _check_admin(req)
    flag = db.upsert_host_app_catalog_flag(
        request.environment,
        request.host_app,
        request.game_id,
        request.model_dump(exclude={"environment", "host_app", "game_id"}),
    )
    clear_policy_cache()
    return {"flag": flag}


@app.get("/")
async def root():
    if _has_frontend_build():
        return FileResponse(_frontend_index_path())
    return {"message": "AI Quiz Game API is running"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/{full_path:path}", include_in_schema=False)
async def frontend_spa(full_path: str, request: Request):
    if _is_api_path(request.url.path):
        raise HTTPException(status_code=404, detail="Not found")
    return _frontend_file_response(full_path)


if __name__ == "__main__":
    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=True)
