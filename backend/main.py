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

from quiz_engine import quiz_engine, _extract_gemini_text, _sanitize_quiz, _validate_quiz, VALID_QUIZ_MODES, DailyLimitExceeded, AIQuotaExceeded
from mlt_engine import mlt_engine, _sanitize_mlt, _validate_mlt
from drawing_engine import drawing_engine, _sanitize_drawing_game, _validate_drawing_game
from housie_engine import DEFAULT_HOUSIE_PATTERNS, default_housie_game, sanitize_patterns
from bingo_engine import DEFAULT_BINGO_PATTERNS, bingo_engine, default_bingo_game, sanitize_bingo_deck, sanitize_bingo_patterns
from musical_chairs_engine import validate_config as validate_musical_chairs_config
from bluff_engine import validate_config as validate_bluff_config
from two_truths_engine import validate_config as validate_two_truths_config
from story_chain_engine import validate_config as validate_story_chain_config
from common_ground_engine import validate_config as validate_common_ground_config
from find_someone_engine import validate_config as validate_find_someone_config
from who_am_i_engine import sanitize_generated_game as sanitize_who_am_i_game, validate_config as validate_who_am_i_config, validate_generated_game as validate_who_am_i_game
from chit_pull_engine import VALID_SAFE_LEVELS as VALID_CHIT_PULL_SAFE_LEVELS, sanitize_generated_game as sanitize_chit_pull_game, validate_config as validate_chit_pull_config, validate_generated_game as validate_chit_pull_game
from mafia_engine import validate_config as validate_mafia_config
from party_quests_engine import validate_config as validate_party_quests_config
from survey_says_engine import validate_config as validate_survey_says_config
from generic_prompt_engine import GENERIC_PROMPT_GAME_TYPES, catalog_entries as generic_prompt_catalog_entries, validate_config as validate_generic_prompt_config
from would_you_rather_engine import validate_config as validate_would_you_rather_config
from never_have_i_ever_engine import validate_config as validate_never_have_i_ever_config
from word_association_engine import validate_config as validate_word_association_config
from acronym_engine import validate_config as validate_acronym_config
from photo_clue_engine import validate_config as validate_photo_clue_config
from poker_engine import validate_config as validate_poker_config
from impostor_engine import validate_config as validate_impostor_config
from socket_manager import socket_manager
from image_engine import image_engine
from media_store import media_store
import tokens
import db
import auth
import analytics
import share
import share_image
import remote_config
from game_rules import attach_rules
from host_app_catalog_policy import clear_policy_cache, effective_catalog, is_game_allowed

logger = logging.getLogger(__name__)


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)

FRONTEND_DIST_DIR = Path(config.FRONTEND_DIST_DIR)
API_PREFIXES = (
    "/admin",
    "/auth",
    "/bingo",
    "/checkout",
    "/chit-pull",
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
    "/who-am-i",
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

    # Extensionless static pages, mirroring Apache MultiViews on the IONOS frontend so that
    # /privacy and /support resolve identically on every surface. Without this the backend-served
    # SPA answers those paths with index.html -- a 200 that renders an empty shell, which is
    # exactly how a broken store Support URL can look healthy. Store review hits these URLs.
    if full_path and "." not in Path(full_path).name:
        html_candidate = (frontend_root / f"{full_path}.html").resolve()
        try:
            html_candidate.relative_to(frontend_root)
        except ValueError:
            return FileResponse(_frontend_index_path())
        if html_candidate.is_file():
            return FileResponse(html_candidate)

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


def _check_payment_config():
    """Log operational notices about payment/IAP configuration (not secret-strength).

    These are expected-to-be-empty pre-launch, so they're informational rather than security warnings."""
    notices = []
    if not config.REVENUECAT_WEBHOOK_SECRET:
        notices.append("REVENUECAT_WEBHOOK_SECRET unset — native IAP fulfillment is disabled")
    if not config.STRIPE_SECRET_KEY:
        notices.append("STRIPE_SECRET_KEY unset — web checkout is disabled (will 503)")
    for n in notices:
        logger.info("PAYMENT CONFIG: %s", n)
    return notices


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting LocalPlay backend")
    # Fail fast BEFORE touching the DB: a deployed container accidentally on SQLite loses all data on
    # the next rebuild. Raises RuntimeConfigError (→ startup crash) on that misconfig. No-op for local
    # dev / tests, which set no Supabase vars. See config.validate_runtime_db_config.
    config.validate_runtime_db_config()
    _check_secret_strength()
    _check_payment_config()
    db.init_db()
    await remote_config.init()
    restored_rooms = socket_manager.restore_rooms()
    if restored_rooms:
        logger.info("Room snapshots restored %d live room(s) across restart", restored_rooms)
    socket_manager.start_cleanup_loop()
    socket_manager.start_snapshot_loop()
    yield
    logger.info("Shutting down LocalPlay backend")
    socket_manager.stop_cleanup_loop()
    socket_manager.stop_snapshot_loop()  # takes a final snapshot for the incoming process


app = FastAPI(title="AI Quiz Game Backend", lifespan=lifespan)
from game_catalog import (
    GAME_CATALOG,
    REVELRY_PARTY_GAME_TYPES,
    REVELRY_PARTY_GAME_TYPES_ERROR,
    REVELRY_PARTY_GAME_START_TYPES,
    REVELRY_PARTY_GAME_START_TYPES_ERROR,
)

# Every game_type a room may be created with, DERIVED from the catalog rather than hand-listed.
# This was a 23-item literal tuple, which is the same shape of bug that shipped the occasion
# bingos broken: a new game landed in the catalog, three hardcoded lists elsewhere didn't know
# about it, and the failure only showed up at runtime. Verified equivalent to the old tuple at the
# time of the swap (identical set, plus `impostor`).
SUPPORTED_ROOM_GAME_TYPES = frozenset(
    {g["game_type"] for g in GAME_CATALOG} | set(GENERIC_PROMPT_GAME_TYPES)
)



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

# Custom Bingo storage
bingo_games: Dict[str, dict] = {}  # bingo_id -> {game_title, deck, patterns, settings}
bingo_timestamps: Dict[str, float] = {}  # bingo_id -> creation time

# Who Am I storage
who_am_i_games: Dict[str, dict] = {}  # who_am_i_id -> {game_title, rounds, settings}
who_am_i_timestamps: Dict[str, float] = {}

# Chit Pull storage
chit_pull_games: Dict[str, dict] = {}  # chit_pull_id -> {game_title, chits, settings}
chit_pull_timestamps: Dict[str, float] = {}

# Party Quests generated setup cache
party_quests_generations: Dict[str, dict] = {}
party_quests_timestamps: Dict[str, float] = {}

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

    # Evict custom Bingo games
    expired_bingo = [bid for bid, ts in bingo_timestamps.items()
                     if now - ts > config.QUIZ_TTL_SECONDS and bid not in active_content_ids]
    for bid in expired_bingo:
        bingo_games.pop(bid, None)
        bingo_timestamps.pop(bid, None)
        content_owners.pop(bid, None)
        pending_generation_charges.pop(bid, None)
    if len(bingo_games) >= config.MAX_QUIZZES:
        for bid in sorted(bingo_timestamps, key=bingo_timestamps.get):
            if len(bingo_games) < config.MAX_QUIZZES:
                break
            if bid not in active_content_ids:
                bingo_games.pop(bid, None)
                bingo_timestamps.pop(bid, None)
                content_owners.pop(bid, None)
                pending_generation_charges.pop(bid, None)

    # Evict Who Am I clue packs
    expired_who = [wid for wid, ts in who_am_i_timestamps.items()
                   if now - ts > config.QUIZ_TTL_SECONDS and wid not in active_content_ids]
    for wid in expired_who:
        who_am_i_games.pop(wid, None)
        who_am_i_timestamps.pop(wid, None)
        content_owners.pop(wid, None)
        pending_generation_charges.pop(wid, None)
    if len(who_am_i_games) >= config.MAX_QUIZZES:
        for wid in sorted(who_am_i_timestamps, key=who_am_i_timestamps.get):
            if len(who_am_i_games) < config.MAX_QUIZZES:
                break
            if wid not in active_content_ids:
                who_am_i_games.pop(wid, None)
                who_am_i_timestamps.pop(wid, None)
                content_owners.pop(wid, None)
                pending_generation_charges.pop(wid, None)

    # Evict Chit Pull decks
    expired_chit = [cid for cid, ts in chit_pull_timestamps.items()
                    if now - ts > config.QUIZ_TTL_SECONDS and cid not in active_content_ids]
    for cid in expired_chit:
        chit_pull_games.pop(cid, None)
        chit_pull_timestamps.pop(cid, None)
        content_owners.pop(cid, None)
        pending_generation_charges.pop(cid, None)
    if len(chit_pull_games) >= config.MAX_QUIZZES:
        for cid in sorted(chit_pull_timestamps, key=chit_pull_timestamps.get):
            if len(chit_pull_games) < config.MAX_QUIZZES:
                break
            if cid not in active_content_ids:
                chit_pull_games.pop(cid, None)
                chit_pull_timestamps.pop(cid, None)
                content_owners.pop(cid, None)
                pending_generation_charges.pop(cid, None)

    # Evict generated Party Quests drafts used for idempotent retries.
    expired_quests = [pid for pid, ts in party_quests_timestamps.items()
                      if now - ts > config.QUIZ_TTL_SECONDS]
    for pid in expired_quests:
        party_quests_generations.pop(pid, None)
        party_quests_timestamps.pop(pid, None)
    if len(party_quests_generations) >= config.MAX_QUIZZES:
        for pid in sorted(party_quests_timestamps, key=party_quests_timestamps.get):
            if len(party_quests_generations) < config.MAX_QUIZZES:
                break
            party_quests_generations.pop(pid, None)
            party_quests_timestamps.pop(pid, None)

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
    drawing_auto_advance: bool = True
    drawing_inter_round_seconds: int = 5
    housie_id: str = ""    # For Housie
    bingo_id: str = ""     # For custom Bingo
    musical_chairs_config: dict = {}
    bluff_config: dict = {}
    two_truths_config: dict = {}
    story_chain_config: dict = {}
    common_ground_config: dict = {}
    find_someone_config: dict = {}
    who_am_i_config: dict = {}
    who_am_i_id: str = ""
    chit_pull_config: dict = {}
    chit_pull_id: str = ""
    mafia_config: dict = {}
    party_quests_config: dict = {}
    survey_says_config: dict = {}
    generic_prompt_config: dict = {}
    would_you_rather_config: dict = {}
    never_have_i_ever_config: dict = {}
    word_association_config: dict = {}
    acronym_config: dict = {}
    photo_clue_config: dict = {}
    poker_config: dict = {}
    # Pass-and-play: carries seat_names/seat_emojis typed by the host (SPEC-PASS-AND-PLAY).
    impostor_config: dict = {}
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

    @field_validator('drawing_inter_round_seconds')
    @classmethod
    def validate_drawing_inter_round_seconds(cls, v: int) -> int:
        if v < 0 or v > 30:
            raise ValueError('Drawing inter-round pause must be between 0 and 30 seconds')
        return v

    @field_validator('game_type')
    @classmethod
    def validate_game_type(cls, v: str) -> str:
        if v not in SUPPORTED_ROOM_GAME_TYPES:
            raise ValueError('game_type must be a supported LocalPlay game type')
        return v




def _default_time_limit_for_game(game_type: str) -> int:
    if game_type == "drawing":
        return 30
    if game_type == "musical_chairs":
        return 5
    if game_type == "bluff":
        return 30
    if game_type == "poker":
        return 30
    if game_type == "two_truths":
        return 30
    if game_type == "story_chain":
        return 45
    if game_type == "common_ground":
        return 30
    if game_type == "find_someone":
        return 30
    if game_type == "who_am_i":
        return 25
    if game_type == "chit_pull":
        return 30
    if game_type == "mafia":
        return 30
    if game_type == "party_quests":
        return 30
    if game_type == "survey_says":
        return 30
    if game_type in GENERIC_PROMPT_GAME_TYPES:
        return 30
    if game_type in ("would_you_rather", "never_have_i_ever", "word_association", "acronym", "photo_clue", "odd_question"):
        return 30
    return config.DEFAULT_TIME_LIMIT


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


def _sanitize_bingo_game(game: dict) -> dict:
    title = str(game.get("game_title") or game.get("title") or "Bingo").strip()[:120] or "Bingo"
    free_center = bool(game.get("free_center", True))
    free_center_label = str(game.get("free_center_label") or "FREE").strip()[:16] or "FREE"
    deck = sanitize_bingo_deck(game.get("deck") or [], free_center=free_center)
    pattern_ids = game.get("pattern_ids") or [p.get("id") for p in game.get("patterns", []) if isinstance(p, dict)]
    patterns = sanitize_bingo_patterns(pattern_ids)
    caller_mode = str(game.get("caller_mode") or "manual").strip().lower()
    if caller_mode not in ("manual", "auto"):
        caller_mode = "manual"
    try:
        auto_interval = int(game.get("auto_interval_seconds") or 8)
    except (TypeError, ValueError):
        auto_interval = 8
    return {
        "game_title": title,
        "ruleset": str(game.get("ruleset") or "custom").strip()[:60] or "custom",
        "layout": "bingo_5x5_free" if free_center else "bingo_5x5",
        "free_center": free_center,
        "free_center_label": free_center_label,
        "deck": deck,
        "patterns": patterns,
        "caller_mode": caller_mode,
        "auto_interval_seconds": max(3, min(30, auto_interval)),
        "auto_pause_on_claim": bool(game.get("auto_pause_on_claim", True)),
        "claim_requires_latest_call": bool(game.get("claim_requires_latest_call", False)),
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
    if game_type == "musical_chairs":
        return str(uuid.uuid4()), validate_musical_chairs_config({"game_title": title or "Musical Chairs"})
    if game_type == "bluff":
        return str(uuid.uuid4()), validate_bluff_config({"game_title": title or "Bluff"})
    if game_type == "two_truths":
        return str(uuid.uuid4()), validate_two_truths_config({"game_title": title or "Two Truths and a Lie"})
    if game_type == "story_chain":
        return str(uuid.uuid4()), validate_story_chain_config({"game_title": title or "Story Chain"})
    if game_type == "common_ground":
        return str(uuid.uuid4()), validate_common_ground_config({"game_title": title or "Common Ground"})
    if game_type == "find_someone":
        return str(uuid.uuid4()), validate_find_someone_config({"game_title": title or "Find Someone Who"})
    if game_type == "who_am_i":
        return str(uuid.uuid4()), validate_who_am_i_config({"game_title": title or "Who Am I?"})
    if game_type == "chit_pull":
        return str(uuid.uuid4()), validate_chit_pull_config({"game_title": title or "Random Chit"})
    if game_type == "mafia":
        return str(uuid.uuid4()), validate_mafia_config({"game_title": title or "Mafia"})
    if game_type == "party_quests":
        return str(uuid.uuid4()), validate_party_quests_config({"game_title": title or "Party Quests"})
    if game_type == "survey_says":
        return str(uuid.uuid4()), validate_survey_says_config({"game_title": title or "Survey Says"})
    if game_type in GENERIC_PROMPT_GAME_TYPES:
        return str(uuid.uuid4()), validate_generic_prompt_config({"game_title": title or ""}, game_type)
    if game_type == "would_you_rather":
        return str(uuid.uuid4()), validate_would_you_rather_config({"game_title": title or "Would You Rather"})
    if game_type == "never_have_i_ever":
        return str(uuid.uuid4()), validate_never_have_i_ever_config({"game_title": title or "Never Have I Ever"})
    if game_type == "word_association":
        return str(uuid.uuid4()), validate_word_association_config({"game_title": title or "Word Association"})
    if game_type == "acronym":
        return str(uuid.uuid4()), validate_acronym_config({"game_title": title or "Acronym Game"})
    if game_type == "photo_clue":
        return str(uuid.uuid4()), validate_photo_clue_config({"game_title": title or "Photo Clue"})
    if game_type == "poker":
        return str(uuid.uuid4()), validate_poker_config({"game_title": title or "Party Poker"})
    if game_type == "impostor":
        return str(uuid.uuid4()), validate_impostor_config({"game_title": title or "Impostor"})
    if game_type == "bingo":
        return str(uuid.uuid4()), default_bingo_game(title or "Bingo")
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
    if game_type == "musical_chairs":
        return _default_game_content(game_type, title)
    if game_type == "bluff":
        return _default_game_content(game_type, title)
    if game_type == "poker":
        return _default_game_content(game_type, title)
    if game_type == "two_truths":
        return _default_game_content(game_type, title)
    if game_type == "story_chain":
        return _default_game_content(game_type, title)
    if game_type == "common_ground":
        return _default_game_content(game_type, title)
    if game_type == "find_someone":
        return _default_game_content(game_type, title)
    if game_type == "who_am_i":
        if content_id:
            if content_id not in who_am_i_games:
                raise HTTPException(status_code=404, detail="Who Am I? game not found")
            return content_id, who_am_i_games[content_id]
        return _default_game_content(game_type, title)
    if game_type == "chit_pull":
        if content_id:
            if content_id not in chit_pull_games:
                raise HTTPException(status_code=404, detail="Random Chit game not found")
            return content_id, chit_pull_games[content_id]
        return _default_game_content(game_type, title)
    if game_type == "mafia":
        return _default_game_content(game_type, title)
    if game_type == "party_quests":
        return _default_game_content(game_type, title)
    if game_type == "survey_says":
        return _default_game_content(game_type, title)
    if game_type in GENERIC_PROMPT_GAME_TYPES:
        return _default_game_content(game_type, title)
    if game_type in ("would_you_rather", "never_have_i_ever", "word_association", "acronym", "photo_clue", "odd_question"):
        return _default_game_content(game_type, title)
    if game_type == "bingo":
        if not config.BINGO_ENABLED:
            raise HTTPException(status_code=404, detail="Bingo is not available")
        if content_id:
            if content_id not in bingo_games:
                raise HTTPException(status_code=404, detail="Bingo game not found")
            return content_id, bingo_games[content_id]
        return _default_game_content(game_type, title)
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
    if game_type in ("wmlt", "drawing", "housie", "bingo", "chit_pull", "party_quests") and content_id:
        if game_type == "wmlt" and content_id in mlt_scenarios:
            return content_id, mlt_scenarios[content_id]
        if game_type == "drawing" and content_id in drawing_games:
            return content_id, drawing_games[content_id]
        if game_type == "housie" and content_id in housie_games:
            return content_id, housie_games[content_id]
        if game_type == "bingo" and content_id in bingo_games:
            return content_id, bingo_games[content_id]
        if game_type == "chit_pull" and content_id in chit_pull_games:
            return content_id, chit_pull_games[content_id]
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
        elif game_type == "housie":
            game_data = _sanitize_housie_game(game_data)
            housie_games[content_id] = game_data
            housie_timestamps[content_id] = time.time()
        elif game_type == "bingo":
            game_data = _sanitize_bingo_game(game_data)
            bingo_games[content_id] = game_data
            bingo_timestamps[content_id] = time.time()
        elif game_type == "party_quests":
            game_data = validate_party_quests_config(game_data)
            if len(game_data.get("quests") or []) < 3:
                raise HTTPException(status_code=422, detail="Invalid Party Quests content")
        else:
            game_data = sanitize_chit_pull_game(game_data)
            if not validate_chit_pull_game(game_data):
                raise HTTPException(status_code=422, detail="Invalid Random Chit content")
            chit_pull_games[content_id] = game_data
            chit_pull_timestamps[content_id] = time.time()
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
    if game_type == "bingo":
        if not config.BINGO_ENABLED:
            raise HTTPException(status_code=404, detail="Bingo is not available")
        if not game_data.get("deck"):
            raise HTTPException(status_code=422, detail="Bingo game has no deck items")
        if not game_data.get("patterns"):
            raise HTTPException(status_code=422, detail="Bingo game has no prize patterns")
    if game_type == "quiz" and not game_data.get("questions"):
        raise HTTPException(status_code=422, detail="Quiz has no questions")
    if game_type == "who_am_i" and len(game_data.get("rounds", [])) < 3:
        raise HTTPException(status_code=422, detail="Who Am I? needs at least 3 clue rounds")
    if game_type == "chit_pull" and len(game_data.get("chits", [])) < 5:
        raise HTTPException(status_code=422, detail="Random Chit needs at least 5 chits")
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
                return {"quiz_id": cached_id, "quiz": quizzes[cached_id]}
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
    return {"quiz_id": quiz_id, "quiz": quiz_data}


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
    return {"quiz_id": quiz_id, "quiz": quiz_data}


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
    return {"quiz_id": quiz_id, "quiz": quiz_data}


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
    return {"quiz_id": quiz_id, "quiz": quiz}


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


_DANGEROUS_MEDIA_EXTENSIONS = {
    ".asa",
    ".asax",
    ".ascx",
    ".ashx",
    ".asp",
    ".aspx",
    ".bat",
    ".cgi",
    ".cmd",
    ".config",
    ".exe",
    ".htaccess",
    ".html",
    ".js",
    ".jsp",
    ".jspx",
    ".php",
    ".php3",
    ".php4",
    ".php5",
    ".php7",
    ".phtml",
    ".phar",
    ".pl",
    ".py",
    ".shtml",
    ".sh",
    ".svg",
}


def _sign_media_upload(path: str, expires: int, mime_type: str, bytes_size: int) -> str:
    payload = f"{path}\n{expires}\n{mime_type}\n{bytes_size}".encode()
    return hmac.new(config.MEDIA_UPLOAD_SECRET.encode(), payload, hashlib.sha256).hexdigest()


def _has_dangerous_media_extension(filename: str) -> bool:
    suffixes = Path(filename or "").suffixes
    return any(suffix.lower() in _DANGEROUS_MEDIA_EXTENSIONS for suffix in suffixes)


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
    if _has_dangerous_media_extension(request.filename):
        raise HTTPException(status_code=415, detail="Executable media filenames are not allowed")
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
        if value not in REVELRY_PARTY_GAME_START_TYPES:
            raise ValueError(REVELRY_PARTY_GAME_START_TYPES_ERROR)
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
        if value not in REVELRY_PARTY_GAME_START_TYPES:
            raise ValueError(REVELRY_PARTY_GAME_START_TYPES_ERROR)
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
        if value not in REVELRY_PARTY_GAME_TYPES:
            raise ValueError(REVELRY_PARTY_GAME_TYPES_ERROR)
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
        if value not in REVELRY_PARTY_GAME_TYPES:
            raise ValueError(REVELRY_PARTY_GAME_TYPES_ERROR)
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
        if value not in REVELRY_PARTY_GAME_TYPES:
            raise ValueError(REVELRY_PARTY_GAME_TYPES_ERROR)
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
        if value not in REVELRY_PARTY_GAME_TYPES:
            raise ValueError(REVELRY_PARTY_GAME_TYPES_ERROR)
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
        if value not in REVELRY_PARTY_GAME_TYPES:
            raise ValueError(REVELRY_PARTY_GAME_TYPES_ERROR)
        return value


class RevelryPartyGameStartRequest(BaseModel):
    party_games_token: str
    content_id: str = ""
    game_type: str = "quiz"
    time_limit: Optional[int] = None
    settings: dict[str, Any] = Field(default_factory=dict)
    open_or_create: bool = False
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
        if value not in REVELRY_PARTY_GAME_START_TYPES:
            raise ValueError(REVELRY_PARTY_GAME_START_TYPES_ERROR)
        return value


class RevelryPartyGameCancelRequest(BaseModel):
    party_games_token: str
    session_id: str
    reason: str = "host_cancelled"

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        if value != "host_cancelled":
            raise ValueError("reason must be host_cancelled")
        return value


class RevelrySessionCancelRequest(BaseModel):
    external_context: RevelryExternalContext
    actor: RevelryActor = Field(default_factory=RevelryActor)
    reason: str = "host_cancelled"

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        if value != "host_cancelled":
            raise ValueError("reason must be host_cancelled")
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
    # Handoff tokens are minted by Revelry for a specific party launch. They must
    # be addressed to LocalPlay (aud), issued by Revelry (iss), and carry the
    # launch credential type; accepting another signed token as a partner
    # credential would cross the trust boundary.
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience="localplay",
            options={"require": ["exp", "aud"]},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired integration credential")
    if claims.get("iss") != "revelry":
        raise HTTPException(status_code=401, detail="Invalid integration issuer")
    if claims.get("typ") != "localplay_launch":
        raise HTTPException(status_code=401, detail="Invalid integration token type")
    return claims


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


def _host_app_catalog_game(context: RevelryExternalContext, game_type: str, actor: Optional[RevelryActor] = None) -> Optional[dict]:
    return next(
        (
            game for game in _host_app_catalog(context, actor)
            if game_type in {game.get("id"), game.get("game_type")}
        ),
        None,
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

    # Normalize origins so an explicit default port (https://host:443) compares
    # equal to the same host with the port omitted. Without this, a Revelry URL
    # that happens to carry :443/:80 would be rejected even though it is allowed.
    def _origin_key(scheme: Optional[str], hostname: Optional[str], port: Optional[int]) -> tuple:
        effective_port = port if port is not None else {"http": 80, "https": 443}.get(scheme or "")
        return (scheme, (hostname or "").lower(), effective_port)

    allowed = set()
    for origin in config.ALLOWED_ORIGINS.split(","):
        origin = origin.strip()
        if not origin:
            continue
        allowed_url = urlparse(origin)
        if allowed_url.scheme in ("http", "https") and allowed_url.netloc:
            allowed.add(_origin_key(allowed_url.scheme, allowed_url.hostname, allowed_url.port))
    allowed.update({
        _origin_key("https", "app.revelryapp.me", None),
        _origin_key("https", "api.revelryapp.me", None),
        _origin_key("https", "api-gamma.revelryapp.me", None),
        _origin_key("http", "localhost", 5173),
        _origin_key("http", "127.0.0.1", 5173),
    })
    if _origin_key(parsed.scheme, parsed.hostname, parsed.port) not in allowed:
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
    callback_started = time.perf_counter()
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
            attempt_started = time.perf_counter()
            try:
                response = await client.post(config.REVELRY_CALLBACK_URL, content=raw, headers=headers)
                response.raise_for_status()
                logger.info(
                    "revelry_callback_timing event_type=%s session_id=%s content_id=%s status=%s attempt=%s attempt_ms=%s total_ms=%s",
                    event_type,
                    session_id or "",
                    content_id or "",
                    getattr(response, "status_code", "unknown"),
                    attempt + 1,
                    _elapsed_ms(attempt_started),
                    _elapsed_ms(callback_started),
                )
                return
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status not in (429, 500, 502, 503, 504) or attempt == 2:
                    logger.warning(
                        "Revelry callback failed for %s after %sms attempt=%s status=%s: %s",
                        event_type,
                        _elapsed_ms(callback_started),
                        attempt + 1,
                        status,
                        exc,
                    )
                    return
                await asyncio.sleep(_callback_retry_delay(exc.response, attempt))
            except httpx.HTTPError as exc:
                if attempt == 2:
                    logger.warning(
                        "Revelry callback failed for %s after %sms attempt=%s: %s",
                        event_type,
                        _elapsed_ms(callback_started),
                        attempt + 1,
                        exc,
                    )
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
    if game_type == "housie":
        return len(game.get("patterns") or [])
    if game_type == "chit_pull":
        return len(game.get("chits") or [])
    if game_type == "party_quests":
        return len(game.get("quests") or [])
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
        "title": content.get("title") or ("Drawing Game" if game_type == "drawing" else "Housie" if game_type == "housie" else "Random Chit" if game_type == "chit_pull" else "Party Quests" if game_type == "party_quests" else "Most Likely To"),
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
    saved_games = db.list_game_content(wallet_id, ["wmlt", "drawing", "housie", "chit_pull", "party_quests"])
    prepared = [_quiz_pack_summary(pack) for pack in packs] + [_game_content_summary(game) for game in saved_games]
    prepared.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    active = db.get_active_game_session(context.host_app, context.external_container_id)
    active = _sync_session_runtime_availability(active)
    if active and active.get("status") not in ("lobby", "active", "paused"):
        active = None
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
        "game_type": session.get("game_type"),
        "content_id": session.get("content_id") or session.get("game_id"),
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


def _sync_session_runtime_availability(session: Optional[dict]) -> Optional[dict]:
    if not session:
        return None
    status = session.get("status", "lobby")
    if status not in ("lobby", "active", "paused"):
        return session
    if session.get("room_code", "") in socket_manager.rooms:
        return session
    now = _now_ts()
    if session.get("expires_at", 0) <= now:
        closed_reason = "expired"
        closed_message = "This game session expired."
    else:
        closed_reason = "runtime_unavailable"
        closed_message = "This game room is no longer available. Start a new game from the party hub."
    return db.update_game_session(session["id"], {
        "status": "expired",
        "joinable": False,
        "closed_reason": closed_reason,
        "closed_message": closed_message,
        "last_activity_at": now,
    }) or {**session, "status": "expired", "joinable": False, "closed_reason": closed_reason, "closed_message": closed_message}


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

    started = time.perf_counter()
    active_lookup_started = time.perf_counter()
    active = db.get_active_game_session(context.host_app, context.external_container_id)
    active = _sync_session_runtime_availability(active)
    active_lookup_ms = _elapsed_ms(active_lookup_started)
    if active and active.get("status") not in ("lobby", "active", "paused"):
        active = None
    requested_content_id = str(settings.get("content_id") or "")
    same_content = (
        bool(requested_content_id)
        and active is not None
        and active.get("game_id") == requested_content_id
        and active.get("game_type") == game_type
    )
    checkin_config_keys = {
        "find_someone": "find_someone_config",
        "party_quests": "party_quests_config",
    }
    checkin_game_config_key = checkin_config_keys.get(game_type, "")
    checkin_game_settings = (
        settings.get(checkin_game_config_key)
        if checkin_game_config_key and isinstance(settings.get(checkin_game_config_key), dict)
        else {}
    )
    open_or_create = bool(
        settings.get("open_or_create")
        or settings.get("reuse_active_session")
        or settings.get("default_for_checkin")
        or checkin_game_settings.get("default_for_checkin")
    )
    same_checkin_default = bool(
        open_or_create
        and game_type in checkin_config_keys
        and active
        and active.get("game_type") == game_type
    )
    catalog_game = _host_app_catalog_game(context, game_type, actor)
    if (
        game_type == "party_quests"
        and open_or_create
        and (checkin_game_settings.get("default_for_checkin") or settings.get("default_for_checkin"))
        and catalog_game
        and catalog_game.get("requires_prepared_content_for_checkin")
        and not requested_content_id
        and not same_checkin_default
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "party_quests_setup_required",
                "game_type": game_type,
                "action_required": "host_configure_party_quests",
                "message": "Set up Party Quests before enabling it for check-in.",
            },
        )
    if active and (same_content or same_checkin_default) and open_or_create:
        existing = dict(active)
        existing["_existing_session"] = True
        return existing
    if active and not replacement_confirmed:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "active_session_exists",
                "session_id": active["id"],
                "active_session_id": active["id"],
                "game_type": active.get("game_type"),
                "game_title": active.get("game_title"),
                "active_content_id": active.get("game_id") or "",
                "requested_content_id": requested_content_id,
                "active_status": active.get("status"),
                "active_joinable": bool(active.get("joinable", False)),
                "active_room_code": active.get("room_code") or "",
                "same_content": same_content,
                "action_required": "continue_existing" if same_content else "continue_or_replace",
                "replace_session_id": active["id"],
                "message": "An active LocalPlay session already exists for this party.",
            },
        )
    if replacement_confirmed and active:
        if not replace_session_id or replace_session_id != active["id"]:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "replace_session_mismatch",
                    "session_id": active["id"],
                    "active_session_id": active["id"],
                    "active_content_id": active.get("game_id") or "",
                    "active_status": active.get("status"),
                    "action_required": "retry_with_active_replace_session_id",
                    "replace_session_id": active["id"],
                    "message": "replace_session_id must match the active LocalPlay session",
                },
            )
    if open_or_create and game_type in checkin_config_keys and not active and not replacement_confirmed:
        latest = db.get_latest_game_session(context.host_app, context.external_container_id, game_type)
        latest = _sync_session_runtime_availability(latest) or latest
        if latest and latest.get("status") not in ("lobby", "active", "paused"):
            title_for_message = latest.get("game_title") or next((g["title"] for g in GAME_CATALOG if g["game_type"] == game_type), "LocalPlay Game")
            raise HTTPException(
                status_code=409,
                detail={
                    "code": f"{game_type}_session_finished",
                    "session_id": latest["id"],
                    "active_session_id": latest["id"],
                    "game_type": latest.get("game_type") or game_type,
                    "game_title": title_for_message,
                    "active_content_id": latest.get("game_id") or "",
                    "active_status": latest.get("status"),
                    "active_joinable": bool(latest.get("joinable", False)),
                    "active_room_code": latest.get("room_code") or "",
                    "action_required": "host_start_new_session",
                    "message": f"The {title_for_message} session for this party has already ended. Start a new session from the Games hub.",
                },
            )

    title = context.external_container_title or next((g["title"] for g in GAME_CATALOG if g["game_type"] == game_type), "LocalPlay Game")
    content_started = time.perf_counter()
    content_id, game_data = _resolve_revelry_runtime_content(context, game_type, str(settings.get("content_id") or ""), title)
    if game_type == "find_someone" and isinstance(settings.get("find_someone_config"), dict):
        game_data = validate_find_someone_config({
            **game_data,
            **settings["find_someone_config"],
            "game_title": settings["find_someone_config"].get("game_title") or game_data.get("game_title") or title,
        })
    if game_type == "party_quests" and isinstance(settings.get("party_quests_config"), dict):
        game_data = validate_party_quests_config({
            **game_data,
            **settings["party_quests_config"],
            "game_title": settings["party_quests_config"].get("game_title") or game_data.get("game_title") or title,
        })
    content_ms = _elapsed_ms(content_started)
    time_limit = int(settings.get("time_limit") or game_data.get("time_limit") or _default_time_limit_for_game(game_type))
    time_limit = max(5, min(60, time_limit))
    wallet_id = f"revelry:{context.host_user_id or actor.external_user_id or context.external_container_id}"
    wallet_started = time.perf_counter()
    db.get_or_create_wallet(wallet_id, signup_bonus=False)
    wallet_ms = _elapsed_ms(wallet_started)
    room_started = time.perf_counter()
    room_code, organizer_token = _create_runtime_room(
        game_type,
        content_id,
        game_data,
        wallet_id,
        time_limit,
        billing_mode="host_app_managed",
    )
    room_ms = _elapsed_ms(room_started)

    now = _now_ts()
    session_id = f"lp_{uuid.uuid4().hex}"
    base_url = _public_base_url(req)
    game_title = game_data.get("quiz_title") or game_data.get("game_title") or title
    session_db_started = time.perf_counter()
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
    session_db_ms = _elapsed_ms(session_db_started)
    supersede_db_ms = 0
    if active:
        supersede_db_started = time.perf_counter()
        superseded = db.update_game_session(active["id"], {
            "status": "superseded",
            "joinable": False,
            "closed_reason": "superseded",
            "closed_message": "The host started a newer game.",
            "superseded_by_session_id": session_id,
        })
        supersede_db_ms = _elapsed_ms(supersede_db_started)
        session["_superseded_session"] = superseded or db.get_game_session(active["id"]) or active
    logger.info(
        "revelry_session_create_timing session_id=%s external_container_id=%s game_type=%s content_id=%s active_session_id=%s total_ms=%s active_lookup_ms=%s content_ms=%s wallet_ms=%s room_ms=%s session_db_ms=%s supersede_db_ms=%s",
        session_id,
        context.external_container_id,
        game_type,
        content_id,
        active.get("id", "") if active else "",
        _elapsed_ms(started),
        active_lookup_ms,
        content_ms,
        wallet_ms,
        room_ms,
        session_db_ms,
        supersede_db_ms,
    )
    return session


async def _close_superseded_runtime_session(superseded: Optional[dict]) -> None:
    if not superseded:
        return
    room_code = superseded.get("room_code") or ""
    if not room_code:
        return
    started = time.perf_counter()
    await socket_manager.close_room(
        room_code,
        reason="superseded",
        message="The host started a newer game.",
    )
    logger.info(
        "revelry_superseded_room_close_timing session_id=%s room_code=%s total_ms=%s",
        superseded.get("id", ""),
        room_code,
        _elapsed_ms(started),
    )


async def _cancel_revelry_session(
    session: dict,
    *,
    context: RevelryExternalContext,
    actor: RevelryActor,
) -> tuple[dict, bool]:
    if "manage_games" not in set(actor.capabilities or []):
        raise HTTPException(status_code=403, detail="Missing capability to cancel games")
    if session.get("host_app") != context.host_app or session.get("external_container_id") != context.external_container_id:
        raise HTTPException(status_code=404, detail="Session not found")
    status = str(session.get("status") or "")
    if status == "cancelled":
        return session, True
    if status not in {"lobby", "active", "paused"}:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "session_not_cancellable",
                "session_id": session.get("id"),
                "status": status,
                "action_required": "refresh_party_workspace",
                "message": "This game session has already ended.",
            },
        )

    message = "The host ended this Party Quests session." if session.get("game_type") == "party_quests" else "The host ended this game session."
    now = _now_ts()
    updated = db.update_game_session(session["id"], {
        "status": "cancelled",
        "joinable": False,
        "closed_reason": "host_cancelled",
        "closed_message": message,
        "last_activity_at": now,
        "updated_at": now,
    }) or session
    if session.get("room_code"):
        await socket_manager.close_room(
            session["room_code"],
            reason="host_cancelled",
            message=message,
        )
    await _send_revelry_callback("session.cancelled", {
        "host_app": context.host_app,
        "external_container_type": context.external_container_type,
        "external_container_id": context.external_container_id,
        "session": _format_session(updated),
        "actor": _safe_actor_payload(actor),
        "closed_reason": "host_cancelled",
        "closed_message": message,
    })
    return updated, False


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
        pack = db.get_quiz_pack(wallet_id, request.content_id)
        game_content = db.get_game_content(wallet_id, request.content_id)
        content_game_type = "quiz" if pack else (game_content or {}).get("game_type", "")
        if not pack and not game_content:
            raise HTTPException(status_code=404, detail="Content not found")
        if content_game_type != request.game_type:
            raise HTTPException(status_code=422, detail="content_id does not match game_type")
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
        pack = db.get_quiz_pack(wallet_id, request.content_id)
        game_content = db.get_game_content(wallet_id, request.content_id)
        content_game_type = "quiz" if pack else (game_content or {}).get("game_type", "")
        if not pack and not game_content:
            raise HTTPException(status_code=404, detail="Content not found")
        if content_game_type != request.game_type:
            raise HTTPException(status_code=422, detail="content_id does not match game_type")
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
        wallet_id = _revelry_party_wallet_id(context.external_container_id)
        pack = db.get_quiz_pack(wallet_id, content_id)
        game_content = db.get_game_content(wallet_id, content_id)
        if not pack and not game_content:
            raise HTTPException(status_code=404, detail="Content not found")
        token_game_type = claims.get("game_type", "quiz")
        content_game_type = "quiz" if pack else (game_content or {}).get("game_type", "")
        if content_game_type != token_game_type:
            raise HTTPException(status_code=422, detail="content_id does not match game_type")
        content = (
            {"metadata": _quiz_pack_summary(pack), "quiz": _pack_to_quiz(pack)}
            if pack
            else {
                "metadata": _prepared_content_summary(game_content),
                "content_payload": _game_content_payload(game_content),
            }
        )
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
    if game_type == "housie":
        if "game_title" not in game_data and title:
            game_data = {**game_data, "game_title": title}
        game_data = _sanitize_housie_game(game_data)
        return {"game": game_data}
    if game_type == "chit_pull":
        if "game_title" not in game_data and title:
            game_data = {**game_data, "game_title": title}
        game_data = sanitize_chit_pull_game(game_data)
        if not validate_chit_pull_game(game_data):
            raise HTTPException(status_code=422, detail="Invalid Random Chit content")
        return {"game": game_data}
    if game_type == "party_quests":
        raw_quests = game_data.get("quests")
        if not isinstance(raw_quests, list):
            raise HTTPException(status_code=422, detail="Party Quests needs at least 3 quests")
        supplied = set()
        for item in raw_quests:
            value = (item.get("display") or item.get("text")) if isinstance(item, dict) else item
            text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(value or ""))
            text = re.sub(r"<\s*/?\s*(script|style|iframe)[^>]*>", "", text, flags=re.IGNORECASE)
            text = re.sub(r"<[^>]+>", "", text)
            text = re.sub(r"\s+", " ", text).strip()[:180].casefold()
            if text:
                supplied.add(text)
        if len(supplied) < 3:
            raise HTTPException(status_code=422, detail="Party Quests needs at least 3 unique quests")
        cleaned = validate_party_quests_config({**game_data, "game_title": game_data.get("game_title") or title})
        if len(cleaned.get("quests") or []) < 3:
            raise HTTPException(status_code=422, detail="Party Quests needs at least 3 unique quests")
        return {"game": cleaned}
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
        if request.game_type == "chit_pull":
            game_data = await generate_chit_pull_content(
                prompt,
                max(5, min(50, request.num_prompts)),
                provider,
                safe_level=request.difficulty if request.difficulty in VALID_CHIT_PULL_SAFE_LEVELS else "family",
                model_override=model_override,
            )
            if not game_data:
                raise HTTPException(status_code=500, detail="Failed to generate chits")
            game_data = sanitize_chit_pull_game(game_data)
            if not validate_chit_pull_game(game_data):
                raise HTTPException(status_code=500, detail="Failed to generate chits")
            return {"game": game_data}
        if request.game_type == "party_quests":
            theme = {
                "party": "mingling",
                "wholesome": "family",
                "work": "work_safe",
                "spicy": "party",
            }.get(request.difficulty, request.difficulty if request.difficulty in {"easy", "medium", "hard"} else "mingling")
            game_data = await generate_party_quests_content(
                PartyQuestsGenerateRequest(
                    prompt=prompt,
                    theme=theme,
                    num_quests=max(5, min(40, request.num_prompts)),
                    quests_per_player=max(3, min(8, request.num_prompts)),
                    duration_minutes=90,
                    confirmation_mode="tap_confirm",
                ),
                provider,
                model_override=model_override,
            )
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
    endpoint_started = time.perf_counter()
    launch_context = _resolve_party_games_token(request.party_games_token)
    capabilities = set(launch_context.get("capabilities") or [])
    if "operate_game" not in capabilities and "manage_games" not in capabilities:
        raise HTTPException(status_code=403, detail="Missing capability to start games")
    context = _external_context_from_launch_context(launch_context)
    actor = _actor_from_launch_context(launch_context)
    create_started = time.perf_counter()
    session = _create_revelry_session_from_context(
        context,
        actor,
        request.game_type,
        {
            **request.settings,
            "content_id": request.content_id or request.settings.get("content_id", ""),
            "time_limit": request.time_limit if request.time_limit is not None else request.settings.get("time_limit"),
            "open_or_create": request.open_or_create or request.settings.get("open_or_create", False),
        },
        req,
        replacement_confirmed=request.replacement_confirmed,
        replace_session_id=request.replace_session_id,
    )
    create_ms = _elapsed_ms(create_started)
    opened_existing = bool(session.pop("_existing_session", False))
    superseded = session.pop("_superseded_session", None)
    close_started = time.perf_counter()
    if not opened_existing:
        await _close_superseded_runtime_session(superseded)
    close_ms = _elapsed_ms(close_started)
    superseded_callback_ms = 0
    if superseded and not opened_existing:
        callback_started = time.perf_counter()
        await _send_revelry_callback("session.superseded", {
            "host_app": context.host_app,
            "external_container_type": context.external_container_type,
            "external_container_id": context.external_container_id,
            "session": _format_session(superseded),
        })
        superseded_callback_ms = _elapsed_ms(callback_started)
    token_started = time.perf_counter()
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
    token_ms = _elapsed_ms(token_started)
    created_callback_ms = 0
    if not opened_existing:
        created_callback_started = time.perf_counter()
        await _send_revelry_callback("session.created", {
            "host_app": context.host_app,
            "external_container_type": context.external_container_type,
            "external_container_id": context.external_container_id,
            "session": _format_session(session),
            "actor": _safe_actor_payload(actor),
        })
        created_callback_ms = _elapsed_ms(created_callback_started)
    logger.info(
        "revelry_party_game_start_timing session_id=%s external_container_id=%s game_type=%s content_id=%s superseded_session_id=%s total_ms=%s create_ms=%s close_ms=%s superseded_callback_ms=%s token_ms=%s created_callback_ms=%s",
        session["id"],
        context.external_container_id,
        request.game_type,
        request.content_id,
        superseded.get("id", "") if superseded else "",
        _elapsed_ms(endpoint_started),
        create_ms,
        close_ms,
        superseded_callback_ms,
        token_ms,
        created_callback_ms,
    )
    return {
        "session": _format_session(session),
        "launch_url": f"{base_url}/organizer?session_id={session['id']}&launch_token={token}&embed=1",
        "launch_token_expires_at": _iso(expires),
        "opened_existing": opened_existing,
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
    session = _sync_session_runtime_availability(session) or session
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


@app.post("/integrations/revelry/party-games/cancel")
async def cancel_revelry_party_game(request: RevelryPartyGameCancelRequest):
    launch_context = _resolve_party_games_token(request.party_games_token)
    context = _external_context_from_launch_context(launch_context)
    actor = _actor_from_launch_context(launch_context)
    session = db.get_game_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    updated, already_terminal = await _cancel_revelry_session(session, context=context, actor=actor)
    return {
        "session": _format_session(updated),
        "workspace": _workspace_payload(context, actor),
        "already_terminal": already_terminal,
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
    endpoint_started = time.perf_counter()
    _require_revelry_auth(req, request.handoff_token)
    context = request.external_context
    create_started = time.perf_counter()
    session = _create_revelry_session_from_context(
        context,
        request.actor,
        request.game_type,
        request.settings,
        req,
        replacement_confirmed=request.replacement_confirmed,
        replace_session_id=request.replace_session_id,
    )
    create_ms = _elapsed_ms(create_started)
    opened_existing = bool(session.pop("_existing_session", False))
    superseded = session.pop("_superseded_session", None)
    close_started = time.perf_counter()
    if not opened_existing:
        await _close_superseded_runtime_session(superseded)
    close_ms = _elapsed_ms(close_started)
    superseded_callback_ms = 0
    if superseded and not opened_existing:
        callback_started = time.perf_counter()
        await _send_revelry_callback("session.superseded", {
            "host_app": context.host_app,
            "external_container_type": context.external_container_type,
            "external_container_id": context.external_container_id,
            "session": _format_session(superseded),
        })
        superseded_callback_ms = _elapsed_ms(callback_started)
    created_callback_ms = 0
    if not opened_existing:
        created_callback_started = time.perf_counter()
        await _send_revelry_callback("session.created", {
            "host_app": context.host_app,
            "external_container_type": context.external_container_type,
            "external_container_id": context.external_container_id,
            "session": _format_session(session),
            "actor": _safe_actor_payload(request.actor),
        })
        created_callback_ms = _elapsed_ms(created_callback_started)
    logger.info(
        "revelry_sessions_create_timing session_id=%s external_container_id=%s game_type=%s content_id=%s superseded_session_id=%s total_ms=%s create_ms=%s close_ms=%s superseded_callback_ms=%s created_callback_ms=%s",
        session["id"],
        context.external_container_id,
        request.game_type,
        request.settings.get("content_id") or "",
        superseded.get("id", "") if superseded else "",
        _elapsed_ms(endpoint_started),
        create_ms,
        close_ms,
        superseded_callback_ms,
        created_callback_ms,
    )
    response = _format_session(session)
    response["opened_existing"] = opened_existing
    return response


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


@app.post("/integrations/revelry/sessions/{session_id}/cancel")
async def cancel_revelry_session(session_id: str, request: RevelrySessionCancelRequest, req: Request):
    _require_revelry_auth(req)
    session = db.get_game_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    updated, already_terminal = await _cancel_revelry_session(
        session,
        context=request.external_context,
        actor=request.actor,
    )
    return {
        "session": _format_session(updated),
        "workspace": _workspace_payload(request.external_context, request.actor),
        "already_terminal": already_terminal,
    }


@app.get("/integrations/revelry/launch-token/resolve")
async def resolve_revelry_launch_token(launch_token: str, scope: str = ""):
    claims = _resolve_launch_token(launch_token, expected_scope=scope or "")
    session = db.get_game_session(claims["session_id"])
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session = _sync_session_runtime_availability(session) or session
    formatted = _format_session(session)
    if not formatted["joinable"] and claims.get("scope") != "spectator":
        raise HTTPException(status_code=409, detail="Session is not joinable")
    payload = {
        "session_id": session["id"],
        "room_code": session["room_code"],
        "game_type": formatted.get("game_type"),
        "content_id": formatted.get("content_id"),
        "game_title": session.get("game_title") or (session.get("feed_card") or {}).get("title") or "",
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
    session = _sync_session_runtime_availability(session) or session
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
        else request.housie_id if request.game_type == "housie"
        else request.bingo_id if request.game_type == "bingo"
        else request.who_am_i_id if request.game_type == "who_am_i"
        else request.chit_pull_id if request.game_type == "chit_pull"
        else ""
    )
    if request.game_type == "musical_chairs":
        content_id = str(uuid.uuid4())
        game_data = validate_musical_chairs_config(request.musical_chairs_config)
    elif request.game_type == "bluff":
        content_id = str(uuid.uuid4())
        game_data = validate_bluff_config(request.bluff_config)
    elif request.game_type == "two_truths":
        content_id = str(uuid.uuid4())
        game_data = validate_two_truths_config(request.two_truths_config)
    elif request.game_type == "story_chain":
        content_id = str(uuid.uuid4())
        game_data = validate_story_chain_config(request.story_chain_config)
    elif request.game_type == "common_ground":
        content_id = str(uuid.uuid4())
        game_data = validate_common_ground_config(request.common_ground_config)
    elif request.game_type == "find_someone":
        content_id = str(uuid.uuid4())
        game_data = validate_find_someone_config(request.find_someone_config)
    elif request.game_type == "who_am_i":
        if content_id:
            content_id, game_data = _resolve_runtime_content("who_am_i", content_id)
        else:
            content_id = str(uuid.uuid4())
            game_data = validate_who_am_i_config(request.who_am_i_config)
    elif request.game_type == "chit_pull":
        if content_id:
            content_id, game_data = _resolve_runtime_content("chit_pull", content_id)
        else:
            content_id = str(uuid.uuid4())
            game_data = validate_chit_pull_config(request.chit_pull_config)
    elif request.game_type == "mafia":
        content_id = str(uuid.uuid4())
        game_data = validate_mafia_config(request.mafia_config)
    elif request.game_type == "party_quests":
        content_id = str(uuid.uuid4())
        game_data = validate_party_quests_config(request.party_quests_config)
    elif request.game_type == "survey_says":
        content_id = str(uuid.uuid4())
        game_data = validate_survey_says_config(request.survey_says_config)
    elif request.game_type in GENERIC_PROMPT_GAME_TYPES:
        content_id = str(uuid.uuid4())
        game_data = validate_generic_prompt_config(request.generic_prompt_config, request.game_type)
    elif request.game_type == "would_you_rather":
        content_id = str(uuid.uuid4())
        game_data = validate_would_you_rather_config(request.would_you_rather_config)
    elif request.game_type == "never_have_i_ever":
        content_id = str(uuid.uuid4())
        game_data = validate_never_have_i_ever_config(request.never_have_i_ever_config)
    elif request.game_type == "word_association":
        content_id = str(uuid.uuid4())
        game_data = validate_word_association_config(request.word_association_config)
    elif request.game_type == "acronym":
        content_id = str(uuid.uuid4())
        game_data = validate_acronym_config(request.acronym_config)
    elif request.game_type == "photo_clue":
        content_id = str(uuid.uuid4())
        game_data = validate_photo_clue_config(request.photo_clue_config)
    elif request.game_type == "poker":
        content_id = str(uuid.uuid4())
        game_data = validate_poker_config(request.poker_config)
    elif request.game_type == "impostor":
        content_id = str(uuid.uuid4())
        # validate_config keeps the game settings; seat names are passed through untouched so the
        # Room constructor can build seats from them.
        game_data = {
            **validate_impostor_config(request.impostor_config),
            "seat_names": (request.impostor_config or {}).get("seat_names") or [],
            "seat_emojis": (request.impostor_config or {}).get("seat_emojis") or [],
        }
    else:
        content_id, game_data = _resolve_runtime_content(request.game_type, content_id)
    if request.game_type == "drawing":
        game_data = dict(game_data)
        game_data["auto_advance"] = bool(request.drawing_auto_advance)
        game_data["inter_round_seconds"] = int(request.drawing_inter_round_seconds)
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
    return {"quiz_id": quiz_id, "quiz": quiz_data}


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


@app.post("/drawing/import")
async def import_drawing(request: DrawingUpdateRequest, req: Request):
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    drawing_data = _sanitize_drawing_game({"game_title": request.game_title, "prompts": request.prompts})
    if not _validate_drawing_game(drawing_data, attempt=0):
        raise HTTPException(status_code=422, detail="Drawing game needs at least 1 valid prompt with 1-5 drawable words")
    _evict_old_content()
    drawing_id = str(uuid.uuid4())
    drawing_games[drawing_id] = drawing_data
    drawing_timestamps[drawing_id] = time.time()
    content_owners[drawing_id] = wallet_id
    logger.info("DrawingGame imported: %s ('%s') owner=%s", drawing_id, drawing_data.get("game_title", "Untitled"), wallet_id[:8])
    return {"drawing_id": drawing_id, "game": drawing_data}


@app.put("/drawing/{drawing_id}")
async def update_drawing(drawing_id: str, request: DrawingUpdateRequest, req: Request):
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    if drawing_id not in drawing_games:
        raise HTTPException(status_code=404, detail="Drawing game not found")
    _check_content_owner(drawing_id, wallet_id)
    drawing_data = _sanitize_drawing_game({"game_title": request.game_title, "prompts": request.prompts})
    if not _validate_drawing_game(drawing_data, attempt=0):
        raise HTTPException(status_code=422, detail="Drawing game needs at least 1 valid prompt with 1-5 drawable words")
    drawing_games[drawing_id] = drawing_data
    logger.info("DrawingGame updated: %s ('%s'), %d prompts", drawing_id, drawing_data["game_title"], len(drawing_data["prompts"]))
    return {"drawing_id": drawing_id, "game": drawing_games[drawing_id]}


# --- Who Am I / Chit Pull authoring endpoints ---

PROMPT_INJECTION_PATTERNS = [
    r'ignore\s+(all\s+)?previous\s+instructions',
    r'ignore\s+(all\s+)?above',
    r'disregard\s+(all\s+)?previous',
    r'you\s+are\s+now\s+(?:a|an|in)',
    r'new\s+instructions?\s*:',
    r'system\s*:\s*',
    r'<\s*/?script',
    r'javascript\s*:',
]


def _sanitize_authoring_prompt(value: str) -> str:
    value = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', value or '')
    value = re.sub(r'<[^>]+>', '', value).strip()
    if not value or len(value) > config.MAX_PROMPT_LENGTH:
        raise ValueError(f'Prompt must be 1-{config.MAX_PROMPT_LENGTH} characters')
    lower_value = value.lower()
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, lower_value):
            raise ValueError('Prompt contains disallowed content')
    return value


async def _generate_json_content(provider: str, model_override: str, prompt_text: str) -> Optional[dict]:
    provider = (provider or "gemini").strip().lower()
    if provider == "ollama":
        payload = {
            "model": model_override or config.OLLAMA_MODEL,
            "prompt": prompt_text,
            "stream": False,
            "format": "json",
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(config.OLLAMA_URL, json=payload, timeout=config.OLLAMA_TIMEOUT)
            response.raise_for_status()
        result = response.json()
        return json.loads(result.get("response") or "{}")
    if provider == "claude":
        if not config.ANTHROPIC_API_KEY:
            return None
        headers = {
            "x-api-key": config.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": model_override or config.ANTHROPIC_MODEL,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt_text}],
        }
        async with httpx.AsyncClient() as client:
            response = await client.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers, timeout=60)
            response.raise_for_status()
        result = response.json()
        text = result.get("content", [{}])[0].get("text", "")
        if text.strip().startswith("```"):
            text = text.strip().split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(re.search(r"\{.*\}", text, re.DOTALL).group(0) if re.search(r"\{.*\}", text, re.DOTALL) else text)
    if not config.GEMINI_API_KEY:
        return None
    model = model_override or config.GEMINI_MODEL
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {"x-goog-api-key": config.GEMINI_API_KEY}
    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {"temperature": 0.85, "responseMimeType": "application/json"},
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
    text = _extract_gemini_text(response.json()) or "{}"
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return json.loads(match.group(0) if match else text)


class WhoAmIGenerateRequest(BaseModel):
    prompt: str
    difficulty: str = "medium"
    num_rounds: int = 10
    clues_per_round: int = 5
    provider: str = ""

    @field_validator('prompt')
    @classmethod
    def validate_prompt(cls, v: str) -> str:
        return _sanitize_authoring_prompt(v)

    @field_validator('difficulty')
    @classmethod
    def validate_difficulty(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in config.VALID_DIFFICULTIES:
            raise ValueError(f'Difficulty must be one of: {", ".join(config.VALID_DIFFICULTIES)}')
        return v

    @field_validator('num_rounds')
    @classmethod
    def validate_num_rounds(cls, v: int) -> int:
        if v < 3 or v > 25:
            raise ValueError('Number of rounds must be 3-25')
        return v

    @field_validator('clues_per_round')
    @classmethod
    def validate_clues_per_round(cls, v: int) -> int:
        if v < 3 or v > 6:
            raise ValueError('Clues per round must be 3-6')
        return v


@app.post("/who-am-i/generate")
async def generate_who_am_i(request: WhoAmIGenerateRequest, req: Request):
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
            if cached_id in who_am_i_games:
                return {"who_am_i_id": cached_id, "game": who_am_i_games[cached_id]}
            raise HTTPException(status_code=409, detail="Request was already processed, but the generated game is no longer available. Please start a new request.")
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=400, detail="X-Device-Id header is required")
    tokens.ensure_wallet(wallet_id)
    if not tokens.can_generate(wallet_id):
        raise HTTPException(status_code=402, detail=f"You need {config.COST_GENERATE} token to generate.")
    if not _check_llm_budget():
        raise HTTPException(status_code=503, detail="Server is busy. Please try again later.")
    await remote_config.get_config()
    provider = request.provider or remote_config.get_provider()
    model_override = remote_config.get_paid_model() if tokens.use_premium_model(wallet_id) else remote_config.get_free_model()
    prompt_text = f"""
You are writing a live party game called Who Am I.
Generate {request.num_rounds} clue-ladder rounds about the user theme below.
Difficulty: {request.difficulty}. Clues per round: {request.clues_per_round}.

Rules:
- Each round has an answer, 1-5 aliases, category, difficulty, and exactly {request.clues_per_round} clues.
- Clues must go from broad to specific.
- Never include the answer text inside any clue.
- Use famous people, fictional characters, landmarks, objects, places, animals, or concepts that a group can reasonably guess.
- Avoid private individuals, sensitive personal facts, protected-class targeting, explicit sexual content, tragedy, medical/legal/financial advice, and humiliating content.
- Return JSON only with this structure:
{{
  "game_title": "string",
  "theme": "string",
  "round_count": {request.num_rounds},
  "clues_per_round": {request.clues_per_round},
  "rounds": [
    {{"id": "round_1", "answer": "string", "aliases": ["string"], "category": "string", "difficulty": "{request.difficulty}", "clues": ["string"]}}
  ]
}}

--- BEGIN USER THEME ---
{request.prompt}
--- END USER THEME ---
"""
    try:
        raw = await _generate_json_content(provider, model_override, prompt_text)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (403, 429):
            raise HTTPException(status_code=503, detail="Free tier limit reached. Upgrade for unlimited games.")
        raise HTTPException(status_code=500, detail="Failed to generate Who Am I")
    except Exception:
        logger.exception("Who Am I generation failed")
        raise HTTPException(status_code=500, detail="Failed to generate Who Am I")
    game_data = sanitize_who_am_i_game({**(raw or {}), "clues_per_round": request.clues_per_round, "round_count": request.num_rounds, "theme": request.prompt})
    if not validate_who_am_i_game(game_data):
        raise HTTPException(status_code=500, detail="Generated clue pack was not playable")
    _evict_old_content()
    who_am_i_id = str(uuid.uuid4())
    who_am_i_games[who_am_i_id] = game_data
    who_am_i_timestamps[who_am_i_id] = time.time()
    content_owners[who_am_i_id] = wallet_id
    pending_generation_charges[who_am_i_id] = wallet_id
    if idem_key:
        db.record_idempotency(idem_key, device_id, who_am_i_id)
    return {"who_am_i_id": who_am_i_id, "game": game_data}


class WhoAmIUpdateRequest(BaseModel):
    game_title: str
    rounds: list
    clues_per_round: int = 5
    round_count: int = 10
    theme: str = ""


@app.post("/who-am-i/import")
async def import_who_am_i(request: WhoAmIUpdateRequest, req: Request):
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    game_data = sanitize_who_am_i_game(request.model_dump())
    if not validate_who_am_i_game(game_data):
        raise HTTPException(status_code=422, detail="Who Am I? needs at least 3 valid rounds")
    _evict_old_content()
    who_am_i_id = str(uuid.uuid4())
    who_am_i_games[who_am_i_id] = game_data
    who_am_i_timestamps[who_am_i_id] = time.time()
    content_owners[who_am_i_id] = wallet_id
    return {"who_am_i_id": who_am_i_id, "game": game_data}


@app.put("/who-am-i/{who_am_i_id}")
async def update_who_am_i(who_am_i_id: str, request: WhoAmIUpdateRequest, req: Request):
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    if who_am_i_id not in who_am_i_games:
        raise HTTPException(status_code=404, detail="Who Am I? game not found")
    _check_content_owner(who_am_i_id, wallet_id)
    game_data = sanitize_who_am_i_game(request.model_dump())
    if not validate_who_am_i_game(game_data):
        raise HTTPException(status_code=422, detail="Who Am I? needs at least 3 valid rounds")
    who_am_i_games[who_am_i_id] = game_data
    return {"who_am_i_id": who_am_i_id, "game": game_data}


class ChitPullGenerateRequest(BaseModel):
    prompt: str
    difficulty: str = "medium"
    num_chits: int = 20
    safe_level: str = "family"
    provider: str = ""

    @field_validator('prompt')
    @classmethod
    def validate_prompt(cls, v: str) -> str:
        return _sanitize_authoring_prompt(v)

    @field_validator('difficulty')
    @classmethod
    def validate_difficulty(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in config.VALID_DIFFICULTIES:
            raise ValueError(f'Difficulty must be one of: {", ".join(config.VALID_DIFFICULTIES)}')
        return v

    @field_validator('num_chits')
    @classmethod
    def validate_num_chits(cls, v: int) -> int:
        if v < 5 or v > 100:
            raise ValueError('Number of chits must be 5-100')
        return v

    @field_validator('safe_level')
    @classmethod
    def validate_safe_level(cls, v: str) -> str:
        v = v.lower().strip().replace(" ", "_")
        if v not in ("kids", "family", "work_safe", "spicy"):
            raise ValueError('Safe level must be kids, family, work_safe, or spicy')
        return v


async def generate_chit_pull_content(
    prompt: str,
    num_chits: int,
    provider: str,
    *,
    difficulty: str = "medium",
    safe_level: str = "family",
    model_override: str = "",
) -> dict:
    safe_level = safe_level.lower().strip().replace(" ", "_")
    if safe_level not in VALID_CHIT_PULL_SAFE_LEVELS:
        safe_level = "family"
    difficulty = difficulty.lower().strip()
    if difficulty not in config.VALID_DIFFICULTIES:
        difficulty = "medium"
    num_chits = max(5, min(100, int(num_chits or 20)))
    prompt_text = f"""
Generate {num_chits} short, performable party chits for a live group game.
Theme/vibe: bounded user theme below.
Difficulty: {difficulty}. Safety level: {safe_level}.

Rules:
- Every chit must be safe, voluntary, inclusive, and easy to do in person.
- Mix categories: question, action, funny_face, mini_challenge, group.
- Keep each chit under 120 characters.
- Avoid protected-class targeting, private/sensitive disclosure, humiliation, touching, drinking, spending money, leaving the venue, explicit sexual content, or medical/legal/financial topics.
- For kids/family/work_safe, keep everything clean and broadly comfortable.
- For spicy, be playful and cheeky but not explicit, coercive, or humiliating.
- Return JSON only:
{{
  "game_title": "string",
  "safe_level": "{safe_level}",
  "rounds": {min(num_chits, 20)},
  "chits": [
    {{"id": "chit_1", "text": "string", "category": "question", "safe_level": "{safe_level}"}}
  ]
}}

--- BEGIN USER THEME ---
{prompt}
--- END USER THEME ---
"""
    raw = await _generate_json_content(provider, model_override, prompt_text)
    game_data = sanitize_chit_pull_game({**(raw or {}), "safe_level": safe_level, "rounds": min(num_chits, 20)})
    if not validate_chit_pull_game(game_data):
        raise ValueError("Generated chit deck was not playable")
    return game_data


@app.post("/chit-pull/generate")
async def generate_chit_pull(request: ChitPullGenerateRequest, req: Request):
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
            if cached_id in chit_pull_games:
                return {"chit_pull_id": cached_id, "game": chit_pull_games[cached_id]}
            raise HTTPException(status_code=409, detail="Request was already processed, but the generated game is no longer available. Please start a new request.")
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=400, detail="X-Device-Id header is required")
    tokens.ensure_wallet(wallet_id)
    if not tokens.can_generate(wallet_id):
        raise HTTPException(status_code=402, detail=f"You need {config.COST_GENERATE} token to generate.")
    if not _check_llm_budget():
        raise HTTPException(status_code=503, detail="Server is busy. Please try again later.")
    await remote_config.get_config()
    provider = request.provider or remote_config.get_provider()
    model_override = remote_config.get_paid_model() if tokens.use_premium_model(wallet_id) else remote_config.get_free_model()
    try:
        game_data = await generate_chit_pull_content(
            request.prompt,
            request.num_chits,
            provider,
            difficulty=request.difficulty,
            safe_level=request.safe_level,
            model_override=model_override,
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (403, 429):
            raise HTTPException(status_code=503, detail="Free tier limit reached. Upgrade for unlimited games.")
        raise HTTPException(status_code=500, detail="Failed to generate Random Chit")
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        logger.exception("Random Chit generation failed")
        raise HTTPException(status_code=500, detail="Failed to generate Random Chit")
    _evict_old_content()
    chit_pull_id = str(uuid.uuid4())
    chit_pull_games[chit_pull_id] = game_data
    chit_pull_timestamps[chit_pull_id] = time.time()
    content_owners[chit_pull_id] = wallet_id
    pending_generation_charges[chit_pull_id] = wallet_id
    if idem_key:
        db.record_idempotency(idem_key, device_id, chit_pull_id)
    return {"chit_pull_id": chit_pull_id, "game": game_data}


class ChitPullUpdateRequest(BaseModel):
    game_title: str
    rounds: int = 20
    turn_time_seconds: int = 30
    safe_level: str = "family"
    chits: list


@app.post("/chit-pull/import")
async def import_chit_pull(request: ChitPullUpdateRequest, req: Request):
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    game_data = sanitize_chit_pull_game(request.model_dump())
    if not validate_chit_pull_game(game_data):
        raise HTTPException(status_code=422, detail="Random Chit needs at least 5 valid chits")
    _evict_old_content()
    chit_pull_id = str(uuid.uuid4())
    chit_pull_games[chit_pull_id] = game_data
    chit_pull_timestamps[chit_pull_id] = time.time()
    content_owners[chit_pull_id] = wallet_id
    return {"chit_pull_id": chit_pull_id, "game": game_data}


@app.put("/chit-pull/{chit_pull_id}")
async def update_chit_pull(chit_pull_id: str, request: ChitPullUpdateRequest, req: Request):
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    if chit_pull_id not in chit_pull_games:
        raise HTTPException(status_code=404, detail="Random Chit game not found")
    _check_content_owner(chit_pull_id, wallet_id)
    game_data = sanitize_chit_pull_game(request.model_dump())
    if not validate_chit_pull_game(game_data):
        raise HTTPException(status_code=422, detail="Random Chit needs at least 5 valid chits")
    chit_pull_games[chit_pull_id] = game_data
    return {"chit_pull_id": chit_pull_id, "game": game_data}


class PartyQuestsGenerateRequest(BaseModel):
    prompt: str
    theme: str = "mingling"
    num_quests: int = 10
    quests_per_player: int = 8
    duration_minutes: int = 90
    confirmation_mode: str = "tap_confirm"
    provider: str = ""

    @field_validator('prompt')
    @classmethod
    def validate_prompt(cls, v: str) -> str:
        return _sanitize_authoring_prompt(v)

    @field_validator('theme')
    @classmethod
    def validate_theme(cls, v: str) -> str:
        value = re.sub(r"[^a-z0-9_\- ]", "", (v or "mingling").lower()).strip().replace(" ", "_")
        return value[:40] or "mingling"

    @field_validator('num_quests')
    @classmethod
    def validate_num_quests(cls, v: int) -> int:
        if v < 5 or v > 40:
            raise ValueError('Number of quests must be 5-40')
        return v

    @field_validator('quests_per_player')
    @classmethod
    def validate_quests_per_player(cls, v: int) -> int:
        if v < 3 or v > 25:
            raise ValueError('Quests per player must be 3-25')
        return v

    @field_validator('duration_minutes')
    @classmethod
    def validate_duration_minutes(cls, v: int) -> int:
        if v < 10 or v > 240:
            raise ValueError('Duration must be 10-240 minutes')
        return v

    @field_validator('confirmation_mode')
    @classmethod
    def validate_confirmation_mode(cls, v: str) -> str:
        value = (v or "tap_confirm").strip().lower()
        if value not in {"tap_confirm", "honor"}:
            raise ValueError('Confirmation mode must be tap_confirm or honor')
        return value


def _normalize_party_quests_generated(raw: dict, request: PartyQuestsGenerateRequest) -> dict:
    quests = raw.get("quests") if isinstance(raw, dict) else []
    normalized = []
    if isinstance(quests, list):
        for item in quests:
            if isinstance(item, str):
                display = item
                category = request.theme
                points = 100
            elif isinstance(item, dict):
                display = item.get("display") or item.get("text") or item.get("quest") or ""
                category = item.get("category") or request.theme
                points = item.get("points") or 100
            else:
                continue
            display = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(display or ""))
            display = re.sub(r"<[^>]+>", "", display)
            display = re.sub(r"\s+", " ", display).strip()[:180]
            if not display:
                continue
            try:
                point_value = int(points or 100)
            except (TypeError, ValueError):
                point_value = 100
            normalized.append({
                "display": display,
                "category": str(category or request.theme)[:40],
                "points": 150 if point_value > 100 else 100,
            })
    if len(normalized) < 5:
        raise ValueError("Generated Party Quests deck needs at least 5 playable quests")
    title = str((raw or {}).get("game_title") or "Party Quests").strip()[:120] or "Party Quests"
    return validate_party_quests_config({
        "game_title": title,
        "theme": request.theme,
        "duration_minutes": request.duration_minutes,
        "quests_per_player": min(request.quests_per_player, len(normalized)),
        "confirmation_mode": request.confirmation_mode,
        "allow_late_join": True,
        "auto_start_on_first_checkin": True,
        "quests": normalized[:request.num_quests],
    })


async def generate_party_quests_content(
    request: PartyQuestsGenerateRequest,
    provider: str,
    *,
    model_override: str = "",
) -> dict:
    prompt_text = f"""
Generate a Party Quests deck for an ambient live party game.
Theme/category: {request.theme}
Number of quests: {request.num_quests}
Quests per player: {request.quests_per_player}

Rules:
- Every quest must make guests mingle, talk, compare preferences, or collect a lightweight confirmation from another guest.
- Quests must be doable at a party without leaving the venue, buying anything, drinking, touching, recording strangers, or revealing private/sensitive information.
- Keep each quest under 120 characters.
- Avoid protected-class targeting, age/health/body/finance/legal questions, humiliating dares, explicit sexual content, profanity, and anything unsafe for a mixed group.
- Write varied quests. Do not repeat the same structure more than twice.
- Prefer concrete, friendly actions: "Find someone who...", "Ask someone...", "Meet someone...", "Take a group photo with...".
- Return JSON only:
{{
  "game_title": "string",
  "theme": "{request.theme}",
  "quests": [
    {{"display": "string", "category": "{request.theme}", "points": 100}}
  ]
}}

--- BEGIN HOST THEME ---
{request.prompt}
--- END HOST THEME ---
"""
    raw = await _generate_json_content(provider, model_override, prompt_text)
    return _normalize_party_quests_generated(raw or {}, request)


@app.post("/party-quests/generate")
async def generate_party_quests(request: PartyQuestsGenerateRequest, req: Request):
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
            if cached_id in party_quests_generations:
                return {"party_quests_id": cached_id, "game": party_quests_generations[cached_id]}
            raise HTTPException(status_code=409, detail="Request was already processed, but the generated quest deck is no longer available. Please start a new request.")
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=400, detail="X-Device-Id header is required")
    tokens.ensure_wallet(wallet_id)
    if not tokens.can_generate(wallet_id):
        raise HTTPException(status_code=402, detail=f"You need {config.COST_GENERATE} token to generate.")
    if not _check_llm_budget():
        raise HTTPException(status_code=503, detail="Server is busy. Please try again later.")
    await remote_config.get_config()
    provider = request.provider or remote_config.get_provider()
    model_override = remote_config.get_paid_model() if tokens.use_premium_model(wallet_id) else remote_config.get_free_model()
    try:
        game_data = await generate_party_quests_content(request, provider, model_override=model_override)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (403, 429):
            raise HTTPException(status_code=503, detail="Free tier limit reached. Upgrade for unlimited games.")
        raise HTTPException(status_code=500, detail="Failed to generate Party Quests")
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        logger.exception("Party Quests generation failed")
        raise HTTPException(status_code=500, detail="Failed to generate Party Quests")
    charged, _balance = tokens.spend_generate(wallet_id)
    if not charged:
        raise HTTPException(status_code=402, detail=f"You need {config.COST_GENERATE} token to generate.")
    _evict_old_content()
    party_quests_id = str(uuid.uuid4())
    party_quests_generations[party_quests_id] = game_data
    party_quests_timestamps[party_quests_id] = time.time()
    if idem_key:
        db.record_idempotency(idem_key, device_id, party_quests_id)
    return {"party_quests_id": party_quests_id, "game": game_data}


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


class BingoDeckItemRequest(BaseModel):
    id: str = ""
    kind: str = "text"
    value: str = ""
    display: str = ""
    image_asset_id: str = ""
    image_url: str = ""
    alt_text: str = ""


class BingoCreateRequest(BaseModel):
    game_title: str = "Bingo"
    deck: List[BingoDeckItemRequest]
    pattern_ids: List[str] = Field(default_factory=lambda: [pattern["id"] for pattern in DEFAULT_BINGO_PATTERNS])
    free_center: bool = True
    free_center_label: str = "FREE"
    caller_mode: str = "manual"
    claim_requires_latest_call: bool = False

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


class BingoGenerateRequest(BaseModel):
    prompt: str
    difficulty: str = "medium"
    num_items: int = 30
    provider: str = ""

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value or "")
        value = re.sub(r"<[^>]+>", "", value).strip()
        if not value or len(value) > config.MAX_PROMPT_LENGTH:
            raise ValueError(f"Prompt must be 1-{config.MAX_PROMPT_LENGTH} characters")
        lower_value = value.lower()
        injection_patterns = [
            r"ignore\s+(all\s+)?previous\s+instructions",
            r"ignore\s+(all\s+)?above",
            r"disregard\s+(all\s+)?previous",
            r"you\s+are\s+now\s+(?:a|an|in)",
            r"new\s+instructions?\s*:",
            r"system\s*:\s*",
            r"<\s*/?script",
            r"javascript\s*:",
        ]
        for pattern in injection_patterns:
            if re.search(pattern, lower_value):
                raise ValueError("Prompt contains disallowed content")
        return value

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty(cls, value: str) -> str:
        value = value.lower().strip()
        if value not in config.VALID_DIFFICULTIES:
            raise ValueError(f"Difficulty must be one of: {', '.join(config.VALID_DIFFICULTIES)}")
        return value

    @field_validator("num_items")
    @classmethod
    def validate_num_items(cls, value: int) -> int:
        if value < 24 or value > 60:
            raise ValueError("Number of Bingo items must be 24-60")
        return value


@app.post("/bingo/generate")
async def generate_bingo(request: BingoGenerateRequest, req: Request):
    if not config.BINGO_ENABLED:
        raise HTTPException(status_code=404, detail="Bingo is not available")
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
            if cached_id in bingo_games:
                return {"bingo_id": cached_id, "game": bingo_games[cached_id]}
            raise HTTPException(status_code=409, detail="Request was already processed, but the generated Bingo game is no longer available. Please start a new request.")

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
        game_data = await bingo_engine.generate_game(
            request.prompt,
            request.difficulty,
            request.num_items,
            provider,
            model_override=model_override,
        )
    except DailyLimitExceeded:
        raise HTTPException(status_code=429, detail="Daily generation limit reached. Please try again tomorrow!")
    except AIQuotaExceeded:
        raise HTTPException(status_code=503, detail="Free tier limit reached. Upgrade for unlimited games.")
    if not game_data:
        raise HTTPException(status_code=500, detail="Failed to generate Bingo")

    _evict_old_content()
    bingo_id = str(uuid.uuid4())
    bingo_games[bingo_id] = game_data
    bingo_timestamps[bingo_id] = time.time()
    content_owners[bingo_id] = wallet_id
    pending_generation_charges[bingo_id] = wallet_id
    if idem_key:
        db.record_idempotency(idem_key, device_id, bingo_id)
    return {"bingo_id": bingo_id, "game": game_data}


@app.post("/bingo/create")
async def create_bingo(request: BingoCreateRequest, req: Request):
    if not config.BINGO_ENABLED:
        raise HTTPException(status_code=404, detail="Bingo is not available")
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=400, detail="X-Device-Id header is required")
    tokens.ensure_wallet(wallet_id)
    _evict_old_content()
    try:
        game_data = _sanitize_bingo_game({
            "game_title": request.game_title,
            "deck": [item.model_dump() for item in request.deck],
            "pattern_ids": request.pattern_ids,
            "free_center": request.free_center,
            "free_center_label": request.free_center_label,
            "caller_mode": request.caller_mode,
            "claim_requires_latest_call": request.claim_requires_latest_call,
        })
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    bingo_id = str(uuid.uuid4())
    bingo_games[bingo_id] = game_data
    bingo_timestamps[bingo_id] = time.time()
    content_owners[bingo_id] = wallet_id
    logger.info("Bingo created: %s ('%s') owner=%s", bingo_id, game_data["game_title"], wallet_id[:8])
    return {"bingo_id": bingo_id, "game": game_data}


@app.get("/bingo/{bingo_id}")
async def get_bingo(bingo_id: str):
    if not config.BINGO_ENABLED:
        raise HTTPException(status_code=404, detail="Bingo is not available")
    if bingo_id not in bingo_games:
        raise HTTPException(status_code=404, detail="Bingo game not found")
    return bingo_games[bingo_id]


@app.put("/bingo/{bingo_id}")
async def update_bingo(bingo_id: str, request: BingoCreateRequest, req: Request):
    if not config.BINGO_ENABLED:
        raise HTTPException(status_code=404, detail="Bingo is not available")
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    if bingo_id not in bingo_games:
        raise HTTPException(status_code=404, detail="Bingo game not found")
    _check_content_owner(bingo_id, wallet_id)
    try:
        game_data = _sanitize_bingo_game({
            "game_title": request.game_title,
            "deck": [item.model_dump() for item in request.deck],
            "pattern_ids": request.pattern_ids,
            "free_center": request.free_center,
            "free_center_label": request.free_center_label,
            "caller_mode": request.caller_mode,
            "claim_requires_latest_call": request.claim_requires_latest_call,
        })
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    bingo_games[bingo_id] = game_data
    return {"bingo_id": bingo_id, "game": game_data}


# --- Game History ---

game_history: List[dict] = []


def _game_display_name(game_type: str) -> str:
    """Catalog title for a game_type, falling back to the raw id.

    Stats must never surface a bare id like "would_you_rather" to a player, but a game_type
    that has since been removed from the catalog should still render as *something*.
    """
    if not game_type:
        return ""
    return next((g["title"] for g in GAME_CATALOG if g["game_type"] == game_type), game_type)


def record_game_completion(summary: dict) -> None:
    """Record one finished game: in-memory ring + durable per-wallet row (SPEC-GAME-STATS).

    Every engine's podium path used to inline the same four lines (append, trim, done), which
    meant 18 copies and no durable record — `game_history` dies with the process, so lifetime
    stats were impossible. This is the single choke-point for both.

    The DB write is best-effort on purpose: stats must never be able to break a podium. A
    failure (pre-migration Supabase, transient outage) degrades to in-memory only, exactly how
    share snapshots behave, so applying the migration is a transparent no-flag upgrade.
    """
    game_history.append(summary)
    if len(game_history) > config.MAX_GAME_HISTORY:
        del game_history[:len(game_history) - config.MAX_GAME_HISTORY]
    wallet_id = summary.get("wallet_id") or ""
    if not wallet_id:
        return  # Revelry-hosted / walletless rooms have nobody to attribute the game to.
    try:
        leaderboard = summary.get("leaderboard") or []
        top = leaderboard[0] if leaderboard else {}
        player_count = int(summary.get("player_count") or 0)
        newly_recorded = db.record_game_result(
            room_code=summary.get("room_code") or "",
            wallet_id=wallet_id,
            game_type=summary.get("game_type") or "",
            game_title=summary.get("game_title") or "",
            player_count=player_count,
            winner_nickname=str(top.get("nickname") or ""),
            top_score=int(top.get("score") or 0),
            completed_at=int(summary.get("completed_at") or time.time()),
        )
        # Only award on a genuinely new row — a replayed podium must not re-trigger badges.
        if newly_recorded:
            _award_game_badges(wallet_id, player_count)
    except Exception:
        logger.warning("Could not persist game result for room %s", summary.get("room_code"), exc_info=True)


def _award_game_badges(wallet_id: str, player_count: int) -> None:
    """Game-completion badges (SPEC-ACHIEVEMENTS v2). Best-effort — `_award_badge` already
    swallows failures, and the stats read is wrapped so a badge check can't fail a podium."""
    if not _ACHIEVEMENTS_SUPPORTED:
        return
    _award_badge(wallet_id, "first_game")
    if player_count >= config.ACHIEVEMENT_BIG_PARTY_PLAYERS:
        _award_badge(wallet_id, "big_party")
    try:
        stats = db.get_wallet_stats(wallet_id)
    except Exception:
        return
    if stats.get("games_hosted", 0) >= config.ACHIEVEMENT_GAMES_HOSTED:
        _award_badge(wallet_id, "ten_games")
    if stats.get("distinct_games_played", 0) >= config.ACHIEVEMENT_DISTINCT_GAMES:
        _award_badge(wallet_id, "explorer")


@app.get("/history")
async def get_game_history(req: Request):
    """Get history of completed games scoped to the requesting wallet."""
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    my_games = [g for g in game_history if g.get("wallet_id") == wallet_id]
    return {"games": my_games}


@app.get("/stats")
async def get_stats(req: Request):
    """Lifetime hosting stats for the requesting wallet (SPEC-GAME-STATS).

    Never 500s: if the `game_results` table isn't applied yet (or the DB blips), this returns
    zeroed stats with `available: false` so the UI can hide the section instead of erroring.
    That makes shipping the code ahead of the migration safe.
    """
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        stats = db.get_wallet_stats(wallet_id)
        recent = db.get_recent_games(wallet_id, limit=10)
    except Exception:
        logger.warning("Stats unavailable for wallet %s", wallet_id[:8], exc_info=True)
        return {
            "available": False,
            "games_hosted": 0,
            "players_entertained": 0,
            "distinct_games_played": 0,
            "favorite_game_type": "",
            "favorite_game_title": "",
            "last_played_at": 0,
            "by_game_type": [],
            "recent": [],
        }
    # Resolve the catalog's display name so the UI never shows a raw id like "would_you_rather".
    fav_type = stats.get("favorite_game_type") or ""
    stats["favorite_game_title"] = _game_display_name(fav_type)
    for row in stats.get("by_game_type", []):
        row["game_title"] = _game_display_name(row.get("game_type") or "")
    stats["available"] = True
    stats["recent"] = recent
    return stats


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


class DeleteAccountRequest(BaseModel):
    confirm: str = ""


@app.delete("/account")
async def delete_account(request: DeleteAccountRequest, req: Request):
    """Permanently delete the signed-in user's account (SPEC-ACCOUNT-DELETION §4.1).

    Required by App Store Review Guideline 5.1.1(v): an app that supports account creation
    must let users delete the account from inside the app.
    """
    client_ip = _get_client_ip(req)
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests")

    session = auth.get_session_from_request(req)
    if not session:
        # Also covers a session for an already-deleted account: get_session_from_request
        # returns None for those, so a retry with a stale token reads as signed-out.
        raise HTTPException(status_code=401, detail="Not signed in")

    # Second gate: an explicit confirmation string, so a stray or malformed DELETE cannot
    # destroy an account by accident.
    if request.confirm != "DELETE":
        raise HTTPException(status_code=400, detail="Confirmation required")

    user_id = session["user_id"]
    # Capture BEFORE deleting: afterwards this id intentionally resolves to nothing. No email
    # or other PII in the payload — the point of the operation is to erase it.
    analytics.capture_bg(user_id, "account_deleted")

    deleted = db.delete_account(user_id)
    if not deleted:
        raise HTTPException(status_code=410, detail="Account already deleted")

    return {"deleted": True}


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
    sku: str = config.DEFAULT_SPARK_SKU  # which spark tier; default keeps older clients working
    promo_id: str = ""

    @field_validator('device_id')
    @classmethod
    def validate_device_id(cls, v: str) -> str:
        v = v.strip()
        if not tokens._UUID_RE.match(v):
            raise ValueError('device_id must be a valid UUID')
        return v

    @field_validator('sku')
    @classmethod
    def validate_sku(cls, v: str) -> str:
        v = (v or "").strip()
        # Unknown/blank sku falls back to the default tier rather than erroring an old client.
        return v if v in config.SPARK_PRODUCTS else config.DEFAULT_SPARK_SKU

    @field_validator('promo_id')
    @classmethod
    def validate_promo_id(cls, v: str) -> str:
        v = v.strip()
        if v and (len(v) > 50 or not re.match(r'^[a-zA-Z0-9_-]+$', v)):
            return ""  # Silently discard invalid promo IDs
        return v


@app.post("/checkout/create")
async def create_checkout(request: CheckoutRequest, req: Request):
    # Native platforms must use in-app purchase (Stripe for digital goods violates store policy).
    platform = tokens.get_platform(req)
    if platform in ("ios", "android"):
        raise HTTPException(status_code=403, detail="Use in-app purchase on native platforms")

    # Verify body device_id matches header device_id
    header_device_id = tokens.get_device_id(req)
    if header_device_id and header_device_id != request.device_id:
        raise HTTPException(status_code=400, detail="Device ID mismatch")

    if not config.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Payments not configured")
    import stripe
    stripe.api_key = config.STRIPE_SECRET_KEY

    # Resolve the price + spark amount from the catalog (single source of truth). The Stripe line item
    # is built inline via price_data (VibePix-style) — no pre-created Stripe Price objects required.
    sku = request.sku  # validated to a known sku (or default) above
    pack = config.SPARK_PRODUCTS[sku]
    spark_amount = pack["sparks"]

    # Resolve wallet for this user/device
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=400, detail="Device ID required")
    tokens.ensure_wallet(wallet_id)

    # Promo overrides the tier amount when active (legacy behavior, applies to the default tier).
    promo_id = request.promo_id.strip()
    if promo_id and promo_id == config.PROMO_ID and config.PROMO_TOKEN_AMOUNT > 0:
        token_amount = config.PROMO_TOKEN_AMOUNT
    else:
        token_amount = spark_amount
        promo_id = ""  # Clear invalid promo

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": pack["name"]},
                    "unit_amount": pack["price_cents"],
                },
                "quantity": 1,
            }],
            metadata={
                "device_id": request.device_id,
                "wallet_id": wallet_id,
                "token_amount": str(token_amount),
                "sku": sku,
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
        max_allowed = max(config.MAX_SPARK_PACK, config.PROMO_TOKEN_AMOUNT)
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
        analytics.capture_bg(wallet_id, "web_purchase_credited",
                             {"sparks": token_amount, "promo_id": promo_id or None})

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
                    token_cap = max(config.MAX_SPARK_PACK, config.PROMO_TOKEN_AMOUNT)
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


def _record_iap_entitlement(wallet_id: str, store: str, transaction_id: str) -> None:
    """Best-effort audit/restore marker for a native IAP. The authoritative spark credit lives in
    token_transactions (reference_id=iap:store:txn); this row just records the store transaction id.
    APP_STORE txns go in apple_transaction_id, PLAY_STORE in google_order_id. games=0 + a neutral
    status keep it out of the restorable-entitlement path. Swallows all errors — credit_purchase is the
    real idempotency gate, so a failure here must never fail the webhook after a successful grant."""
    if not (wallet_id and transaction_id):
        return
    try:
        apple_txn = transaction_id if store == "APP_STORE" else None
        google_txn = transaction_id if store == "PLAY_STORE" else None
        if not (apple_txn or google_txn):
            return  # unknown store → nothing to key the audit row on
        db.create_entitlement(
            uuid.uuid4().hex,
            device_id=wallet_id,
            apple_transaction_id=apple_txn,
            google_order_id=google_txn,
            games=0,
            status="iap_consumed",
        )
    except Exception as e:  # noqa: BLE001 — audit marker is best-effort
        logger.warning("IAP entitlement audit record failed (store=%s): %s", store, e)


@app.post("/webhook/revenuecat")
async def revenuecat_webhook(req: Request):
    """Fulfill native IAP purchases validated by RevenueCat. See SPEC-IAP §5.1.

    Idempotency is double-layered: webhook_events(event_id) skips exact replays, and
    credit_purchase(reference_id=iap:{store}:{txn}) prevents a second credit even when RevenueCat
    sends a new event id for the same transaction."""
    if not config.REVENUECAT_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="IAP not configured")
    auth = req.headers.get("authorization", "")
    if not hmac.compare_digest(auth, f"Bearer {config.REVENUECAT_WEBHOOK_SECRET}"):
        logger.warning("RevenueCat webhook auth failure from %s", _get_client_ip(req))
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        body = await req.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    event = body.get("event") if isinstance(body, dict) else None
    if not isinstance(event, dict):
        raise HTTPException(status_code=400, detail="Missing event")

    event_type = (event.get("type") or "").upper()
    wallet_id = (event.get("app_user_id") or "").strip()
    product_id = (event.get("product_id") or "").strip()
    store = (event.get("store") or "").upper()  # "APP_STORE" | "PLAY_STORE"
    txn_id = (event.get("transaction_id") or event.get("store_transaction_id") or "").strip()
    event_id = (event.get("id") or (f"rc_{store}_{txn_id}" if txn_id else "")).strip()
    if not event_id:
        raise HTTPException(status_code=400, detail="Missing event identifier")
    if not wallet_id:
        raise HTTPException(status_code=400, detail="Missing app_user_id")

    # Idempotency: skip already-processed events (survives restarts).
    if db.is_webhook_event_processed(event_id):
        logger.info("Skipping duplicate RevenueCat event: %s", event_id)
        return {"status": "ok", "detail": "already processed"}

    sku = config.SPARK_PRODUCT_BY_ANY_ID.get(product_id)
    reference_id = f"iap:{store or 'UNKNOWN'}:{txn_id}"

    if event_type in ("INITIAL_PURCHASE", "NON_RENEWING_PURCHASE"):
        if not sku:
            # Ack unknown products with 200 so RevenueCat stops retrying, but credit nothing.
            logger.warning("RevenueCat unknown product: %s", product_id)
            db.mark_webhook_event_processed(event_id)
            return {"status": "ok", "detail": "unknown product"}
        if not txn_id:
            raise HTTPException(status_code=400, detail="Missing transaction_id")
        sparks = config.SPARK_PRODUCTS[sku]["sparks"]

        # Idempotent on reference_id (DB error here propagates as 500 → RevenueCat retries).
        credited, new_balance = db.credit_purchase(
            wallet_id, sparks, reference_id,
            metadata=json.dumps({"source": "iap", "store": store, "product_id": product_id}),
        )
        logger.info("IAP credit %s sparks to wallet %s (store=%s, sku=%s, credited=%s, balance=%s)",
                    sparks, wallet_id[:8], store, sku, credited, new_balance)
        if credited:
            analytics.capture_bg(wallet_id, "iap_purchase_credited",
                                 {"store": store, "sku": sku, "sparks": sparks})
        _record_iap_entitlement(wallet_id, store, txn_id)

        if credited:
            try:
                db.store_pending_token(wallet_id, json.dumps(
                    {"tokens_added": sparks, "new_balance": new_balance}))
            except Exception as e:  # noqa: BLE001 — notification is best-effort; native polls balance
                logger.warning("IAP pending-token notify failed: %s", e)

    elif event_type in ("REFUND", "CANCELLATION"):
        # Clawback — mirror the Stripe charge.refunded path (debit_tokens, idempotent via already-debited).
        if sku and txn_id:
            already = db.get_refund_debits_for_session(reference_id)
            owed = config.SPARK_PRODUCTS[sku]["sparks"]
            refund_tokens = max(0, owed - already)
            if refund_tokens > 0:
                success, _ = db.debit_tokens(wallet_id, refund_tokens, "refund", reference_id)
                if not success:
                    logger.warning("IAP refund debit failed: wallet=%s ref=%s amount=%d",
                                   wallet_id[:8], reference_id, refund_tokens)
                else:
                    logger.info("IAP refund debited %d sparks from wallet %s (ref=%s)",
                                refund_tokens, wallet_id[:8], reference_id)
                    analytics.capture_bg(wallet_id, "iap_refund",
                                         {"store": store, "sku": sku, "sparks_clawed": refund_tokens})
    # else: TEST, TRANSFER, RENEWAL, EXPIRATION, BILLING_ISSUE, etc. → ack and ignore (no subscriptions in v1)

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
                    "bonus_streak": 0, "streak_next_reward": config.STREAK_BASE,
                    "cost_generate": config.COST_GENERATE, "cost_room": config.COST_ROOM,
                    "ads_remaining_today": config.MAX_ADS_PER_DAY}
        wallet_id = device_id
    status = tokens.get_token_status(wallet_id)
    if status.get("daily_bonus_granted"):
        analytics.capture_bg(wallet_id, "spark_earned",
                             {"source": "daily_bonus", "amount": status.get("bonus_amount", 0),
                              "streak": status.get("bonus_streak", 1)})
    return status


# Keep old endpoint as alias for backward compatibility during rollout
@app.get("/entitlements/current")
async def entitlement_status_compat(req: Request):
    """Legacy endpoint — redirects to token balance."""
    return await token_balance(req)


@app.post("/tokens/ad-reward")
async def ad_reward(req: Request):
    """Grant tokens for watching an ad.

    LOCKED by default: this is a trust-the-client stub with no ad verification, so it is
    farmable free sparks (SPEC-ADS §0). It returns 403 unless ADS_ENABLED is explicitly set —
    which must not happen until server-side ad verification (SSV) replaces this stub.
    """
    if not config.ADS_ENABLED:
        raise HTTPException(status_code=403, detail="Ad rewards are not available.")
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
    analytics.capture_bg(wallet_id, "spark_earned",
                         {"source": "ad", "amount": config.AD_REWARD_TOKENS})
    return {"granted": True, "tokens_added": config.AD_REWARD_TOKENS,
            "new_balance": new_balance, "ads_remaining_today": ads_remaining}


class ReferralRedeemRequest(BaseModel):
    code: str = ""


# Referrals run on SQLite automatically. On Supabase they need the referral RPCs (sql/games-schema.sql)
# applied first, then REFERRALS_ENABLED=true — until then the endpoints 503 and the UI hides the section.
_REFERRALS_SUPPORTED = config.DB_BACKEND != "supabase" or config.REFERRALS_ENABLED


@app.get("/referral/code")
async def referral_code(req: Request):
    """Return this wallet's referral code + a shareable link (SPEC-REFERRAL). Lazily generated."""
    if not _REFERRALS_SUPPORTED:
        raise HTTPException(status_code=503, detail="Referrals are not available yet.")
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=400, detail="X-Device-Id header is required")
    tokens.ensure_wallet(wallet_id)
    code = db.get_or_create_referral_code(wallet_id)
    share_url = f"{config.PUBLIC_BASE_URL}/?ref={code}" if config.PUBLIC_BASE_URL else f"/?ref={code}"
    return {"code": code, "share_url": share_url, "reward": config.REFERRAL_REWARD}


@app.post("/referral/redeem")
async def referral_redeem(body: ReferralRedeemRequest, req: Request):
    """Redeem a referral code — credits both parties once (SPEC-REFERRAL)."""
    if not _REFERRALS_SUPPORTED:
        raise HTTPException(status_code=503, detail="Referrals are not available yet.")
    client_ip = _get_client_ip(req)
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait.")
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=400, detail="X-Device-Id header is required")
    result = db.redeem_referral(wallet_id, body.code)
    status = result.get("status")
    if status == "ok":
        analytics.capture_bg(wallet_id, "spark_earned",
                             {"source": "referral", "amount": result.get("reward", 0)})
        analytics.capture_bg(wallet_id, "referral_redeemed", {"role": "referee"})
        _award_badge(wallet_id, "first_referral")
        if result.get("referrer_id"):
            analytics.capture_bg(result["referrer_id"], "referral_redeemed", {"role": "referrer"})
            _award_badge(result["referrer_id"], "first_referral")
        return {"redeemed": True, "reward": result.get("reward", 0),
                "new_balance": result.get("new_balance", 0)}
    _errmap = {
        "invalid_code": (404, "That referral code isn't valid."),
        "self_referral": (400, "You can't redeem your own referral code."),
        "already_redeemed": (409, "You've already redeemed a referral code."),
        "cap_reached": (429, "This code has hit its daily limit. Try again tomorrow."),
    }
    code_status, detail = _errmap.get(status, (400, "Could not redeem referral code."))
    raise HTTPException(status_code=code_status, detail=detail)


class GiftSparksRequest(BaseModel):
    code: str = ""
    amount: int = 0
    idempotency_key: str = ""


# Gifting runs on SQLite automatically. On Supabase it needs the gift_sparks RPC (sql/games-schema.sql)
# applied first, then GIFTING_ENABLED=true — until then the endpoint 503s and the UI hides the section.
_GIFTING_SUPPORTED = config.DB_BACKEND != "supabase" or config.GIFTING_ENABLED


@app.post("/tokens/gift")
async def gift_sparks(body: GiftSparksRequest, req: Request):
    """Send sparks to another player's wallet by their friend (referral) code (SPEC-GIFTING).
    Atomic debit-then-credit; idempotent on the client-supplied idempotency_key so a retry is safe."""
    if not _GIFTING_SUPPORTED:
        raise HTTPException(status_code=503, detail="Gifting is not available yet.")
    client_ip = _get_client_ip(req)
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait.")
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=400, detail="X-Device-Id header is required")
    tokens.ensure_wallet(wallet_id)
    result = db.gift_sparks(wallet_id, body.code, body.amount, body.idempotency_key)
    status = result.get("status")
    if status == "ok":
        if not result.get("duplicate"):
            analytics.capture_bg(wallet_id, "spark_sent",
                                 {"amount": result.get("amount", 0)})
            _award_badge(wallet_id, "first_gift")
            if result.get("recipient_id"):
                analytics.capture_bg(result["recipient_id"], "spark_received",
                                     {"amount": result.get("amount", 0)})
        return {"sent": True, "amount": result.get("amount", 0),
                "new_balance": result.get("new_balance", 0),
                "duplicate": bool(result.get("duplicate"))}
    _errmap = {
        "invalid_amount": (400, f"Gift amount must be between {config.GIFT_MIN_AMOUNT} and {config.GIFT_MAX_AMOUNT} sparks."),
        "invalid_code": (404, "That friend code isn't valid."),
        "self_gift": (400, "You can't gift sparks to yourself."),
        "insufficient": (402, "You don't have enough sparks for that gift."),
        "recipient_full": (409, "That player's spark balance is already full."),
        "daily_cap": (429, "You've hit today's gifting limit. Try again tomorrow."),
    }
    code_status, detail = _errmap.get(status, (400, "Could not send the gift."))
    raise HTTPException(status_code=code_status, detail=detail)


# Achievements run on SQLite automatically. On Supabase they need the achievements table + award RPC
# (sql/games-schema.sql) applied first, then ACHIEVEMENTS_ENABLED=true — until then the endpoint 503s.
_ACHIEVEMENTS_SUPPORTED = config.DB_BACKEND != "supabase" or config.ACHIEVEMENTS_ENABLED


def _award_badge(wallet_id: str, badge_id: str) -> None:
    """Best-effort badge award (SPEC-ACHIEVEMENTS). Idempotent, and NEVER allowed to break the
    primary action that triggered it — a badge is a side effect, not a precondition."""
    if not _ACHIEVEMENTS_SUPPORTED or not wallet_id:
        return
    try:
        if db.award_achievement(wallet_id, badge_id):
            analytics.capture_bg(wallet_id, "achievement_earned", {"badge": badge_id})
    except Exception:  # noqa: BLE001 — awarding must never surface to the caller
        logger.warning("award_achievement failed for %s/%s", wallet_id[:8], badge_id, exc_info=True)


@app.get("/achievements")
async def get_achievements(req: Request):
    """Return the full badge catalog with per-wallet earned flags (SPEC-ACHIEVEMENTS)."""
    if not _ACHIEVEMENTS_SUPPORTED:
        raise HTTPException(status_code=503, detail="Achievements are not available yet.")
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=400, detail="X-Device-Id header is required")
    tokens.ensure_wallet(wallet_id)
    # Everyone with a wallet earns "welcome" on first view, so the list is never empty.
    _award_badge(wallet_id, "welcome")
    earned = db.list_achievements(wallet_id)
    badges = [
        {**badge, "earned": badge["id"] in earned, "awarded_at": earned.get(badge["id"])}
        for badge in config.ACHIEVEMENT_CATALOG
    ]
    return {"badges": badges, "earned_count": len(earned)}


class ShareGameRequest(BaseModel):
    game_type: str = ""
    winner: str = ""
    top_score: int = 0
    player_count: int = 0


@app.post("/share/game")
async def create_share_card(body: ShareGameRequest, req: Request):
    """Mint a shareable result card token (SPEC-SHARE-CARD)."""
    client_ip = _get_client_ip(req)
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait.")
    token = share.create_snapshot(body.game_type, body.winner, body.top_score, body.player_count)
    base = config.PUBLIC_BASE_URL or ""
    share_url = f"{base}/share/game/{token}" if base else f"/share/game/{token}"
    return {"token": token, "share_url": share_url}


@app.get("/share/game/{token}")
async def get_share_card(token: str):
    """Render the OG-unfurl page for a result card. Unknown/expired token → generic branded page."""
    snap = share.get_snapshot(token)
    return Response(content=share.render_html(snap), media_type="text/html")


# Cache for a day: a snapshot is immutable once minted, and crawlers plus every recipient's chat
# client will each fetch this. immutable tells them not to revalidate.
_SHARE_IMAGE_CACHE_CONTROL = "public, max-age=86400, immutable"


@app.get("/share/game/{token}/image.png")
async def get_share_card_image(token: str):
    """Per-result OG image (SPEC-SHARE-CARD).

    NEVER raises. Crawlers fetch an OG image once, eagerly, and do not retry — a 500 here means the
    link unfurls bare forever. Any failure (unknown token, expired snapshot, a Pillow problem)
    redirects to the static branded image, so the preview degrades instead of breaking.
    """
    static_fallback = f"{config.PUBLIC_BASE_URL}/og-image.png" if config.PUBLIC_BASE_URL else "/og-image.png"
    try:
        snap = share.get_snapshot(token)
        if not snap:
            return RedirectResponse(static_fallback, status_code=302)
        png = share_image.render_card(
            winner=snap.get("winner") or "",
            top_score=snap.get("top_score") or 0,
            player_count=snap.get("player_count") or 0,
            # Reuse the catalog title so the card never shows a raw id like "would_you_rather".
            game_label=_game_display_name(snap.get("game_type") or "") or "party game",
        )
        return Response(
            content=png,
            media_type="image/png",
            headers={"Cache-Control": _SHARE_IMAGE_CACHE_CONTROL},
        )
    except Exception:  # noqa: BLE001 — see docstring; a broken image must not break the unfurl
        logger.warning("Share image render failed for token %s", token[:8], exc_info=True)
        return RedirectResponse(static_fallback, status_code=302)


@app.get("/config/public")
async def public_config():
    """Server-effective remote config (SPEC-REMOTE-CONFIG): the fetched config.json augmented with
    backend-authoritative economy + feature flags. Safe defaults; never 500. Read-only, unauthenticated."""
    try:
        base = await remote_config.get_config()
    except Exception:  # noqa: BLE001 — config read must never 500
        base = {}
    cfg = dict(base) if isinstance(base, dict) else {}
    # Backend is authoritative for spend costs (config.json can't override real spending).
    cfg["economy"] = {"cost_room": config.COST_ROOM, "cost_generate": config.COST_GENERATE}
    ff = dict(cfg.get("feature_flags") or {})
    ff.setdefault("show_upgrade_button", True)
    ff.setdefault("enable_image_generation", True)
    ff["ads_enabled"] = False  # no ad SDK yet (SPEC-ADS)
    ff["referral_enabled"] = _REFERRALS_SUPPORTED
    ff["gifting_enabled"] = _GIFTING_SUPPORTED
    ff["achievements_enabled"] = _ACHIEVEMENTS_SUPPORTED
    cfg["feature_flags"] = ff
    cfg.setdefault("enabled_game_types", None)
    return cfg


@app.post("/purchases/restore")
async def restore_purchases(req: Request):
    """Restore IAP purchases — credits tokens if not already credited."""
    device_id = tokens.get_device_id(req)
    if not device_id:
        raise HTTPException(status_code=400, detail="X-Device-Id header is required")

    session = auth.get_session_from_request(req)
    user_id = session["user_id"] if session else None

    try:
        ent = db.find_restorable_entitlement(device_id, user_id=user_id)
    except Exception as e:  # noqa: BLE001 — restore is a user-facing best-effort check
        logger.warning("Purchase restore lookup failed: %s", e)
        raise HTTPException(status_code=503, detail="Could not check purchases right now. Please try again.")
    if not ent:
        return {"restored": False}

    if ent["status"] != "active":
        return {"restored": False, "reason": "expired"}

    # Credit remaining games as tokens (if not already migrated)
    wallet_id = user_id or device_id
    tokens_to_credit = ent["games_remaining"] * config.COST_ROOM
    if tokens_to_credit > 0:
        try:
            db.credit_tokens(wallet_id, tokens_to_credit, "restore", reference_id=ent["id"])
        except Exception as e:  # noqa: BLE001 — avoid an opaque 500 in the settings drawer
            logger.warning("Purchase restore credit failed: %s", e)
            raise HTTPException(status_code=503, detail="Could not restore purchases right now. Please try again.")
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


class ConfigOverrideRequest(BaseModel):
    overrides: dict


@app.get("/admin/config")
async def admin_get_config(req: Request):
    """Show the fetched config, the operator override layer, and the effective merge.

    Returning all three (not just the merge) is the point: when something is behaving oddly you
    need to know whether it came from IONOS or from an override somebody set weeks ago.
    """
    _check_admin(req)
    try:
        effective = await remote_config.get_config()
    except Exception:  # noqa: BLE001 — admin visibility must not 500
        effective = {}
    return {
        "fetched": remote_config._cached_config,
        "overrides": remote_config.get_overrides(),
        "effective": effective,
        "source_url": remote_config.REMOTE_CONFIG_URL,
    }


@app.put("/admin/config")
async def admin_set_config(request: ConfigOverrideRequest, req: Request):
    """Replace the override layer. Merged over the IONOS config on read (deep, so you can flip
    one nested flag without restating its whole object).

    Wholesale replace rather than patch-accumulate so the stored state is always exactly what
    was last sent — an override you can't fully see is an override you can't safely remove.
    Send `{"overrides": {}}` (or DELETE) to clear.
    """
    _check_admin(req)
    stored = remote_config.set_overrides(request.overrides)
    logger.info("Remote config overrides updated: keys=%s", sorted(stored.keys()))
    return {"overrides": stored, "effective": await remote_config.get_config()}


@app.delete("/admin/config")
async def admin_clear_config(req: Request):
    _check_admin(req)
    remote_config.clear_overrides()
    logger.info("Remote config overrides cleared")
    return {"overrides": {}, "effective": await remote_config.get_config()}


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
