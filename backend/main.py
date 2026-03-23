from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, field_validator
from typing import List, Optional, Dict
from collections import defaultdict
import os
import re
import time
from contextlib import asynccontextmanager
import uvicorn
import uuid
import string
import secrets
import base64
import logging
import socket as socketlib

import config
config.setup_logging()

from quiz_engine import quiz_engine, _sanitize_quiz, _validate_quiz, DailyLimitExceeded, AIQuotaExceeded
from mlt_engine import mlt_engine, _sanitize_mlt, _validate_mlt
from socket_manager import socket_manager
from image_engine import image_engine
import tokens
import db
import auth

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting LocalPlay backend")
    db.init_db()
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
async def get_system_info():
    return {"ip": get_local_ip()}


# In-memory rate limiter
_rate_limit_store: Dict[str, list] = defaultdict(list)


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


# In-memory storage with timestamps for cleanup
quizzes: Dict[str, dict] = {}  # quiz_id -> quiz_data
quiz_timestamps: Dict[str, float] = {}  # quiz_id -> creation time
quiz_images: Dict[str, Dict[int, str]] = {}  # quiz_id -> {question_id: base64_image}

# MLT (Most Likely To) storage
mlt_scenarios: Dict[str, dict] = {}  # scenario_id -> {game_title, statements}
mlt_timestamps: Dict[str, float] = {}  # scenario_id -> creation time


def _evict_old_content():
    """Evict oldest quizzes/MLT scenarios if storage limit exceeded, and expire stale ones."""
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
    # Evict oldest non-active quizzes until under limit
    if len(quizzes) >= config.MAX_QUIZZES:
        for qid in sorted(quiz_timestamps, key=quiz_timestamps.get):
            if len(quizzes) < config.MAX_QUIZZES:
                break
            if qid not in active_content_ids:
                quizzes.pop(qid, None)
                quiz_timestamps.pop(qid, None)
                quiz_images.pop(qid, None)

    # Evict MLT scenarios
    expired_mlt = [sid for sid, ts in mlt_timestamps.items()
                   if now - ts > config.QUIZ_TTL_SECONDS and sid not in active_content_ids]
    for sid in expired_mlt:
        mlt_scenarios.pop(sid, None)
        mlt_timestamps.pop(sid, None)
    if len(mlt_scenarios) >= config.MAX_QUIZZES:
        for sid in sorted(mlt_timestamps, key=mlt_timestamps.get):
            if len(mlt_scenarios) < config.MAX_QUIZZES:
                break
            if sid not in active_content_ids:
                mlt_scenarios.pop(sid, None)
                mlt_timestamps.pop(sid, None)

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


class RoomCreateRequest(BaseModel):
    quiz_id: str = ""      # For quiz game
    mlt_id: str = ""       # For MLT game
    game_type: str = "quiz"
    time_limit: int = 15

    @field_validator('time_limit')
    @classmethod
    def validate_time_limit(cls, v: int) -> int:
        if v < 5 or v > 60:
            raise ValueError('Time limit must be between 5 and 60 seconds')
        return v

    @field_validator('game_type')
    @classmethod
    def validate_game_type(cls, v: str) -> str:
        if v not in ("quiz", "wmlt"):
            raise ValueError('game_type must be "quiz" or "wmlt"')
        return v


class ImageGenerateRequest(BaseModel):
    quiz_id: str
    question_id: Optional[int] = None  # If None, generate for all questions


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

    # Idempotency: return cached result if this request was already processed
    if idem_key:
        cached_id = db.check_idempotency(idem_key, device_id)
        if cached_id and cached_id in quizzes:
            return {"quiz_id": cached_id, "quiz": quizzes[cached_id]}

    # Resolve wallet and check token balance
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=400, detail="X-Device-Id header is required")
    tokens.ensure_wallet(wallet_id)
    if not tokens.can_generate(wallet_id):
        raise HTTPException(status_code=402, detail=f"You need {config.COST_GENERATE} token to generate. Buy tokens or watch an ad!")

    # Spend 1 token for generation
    spent, _ = tokens.spend_generate(wallet_id)
    if not spent:
        raise HTTPException(status_code=402, detail=f"You need {config.COST_GENERATE} token to generate. Buy tokens or watch an ad!")

    model_override = config.GEMINI_PREMIUM_MODEL if tokens.use_premium_model(wallet_id) and (request.provider or config.DEFAULT_PROVIDER) == "gemini" else None
    try:
        quiz_data = await quiz_engine.generate_quiz(request.prompt, request.difficulty, request.num_questions, request.provider, model_override=model_override)
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
    if idem_key:
        db.record_idempotency(idem_key, device_id, quiz_id)
    logger.info("Quiz created: %s ('%s')", quiz_id, quiz_data.get("quiz_title", "Untitled"))
    return {"quiz_id": quiz_id, "quiz": quiz_data}


@app.get("/quiz/{quiz_id}")
async def get_quiz(quiz_id: str):
    if quiz_id not in quizzes:
        raise HTTPException(status_code=404, detail="Quiz not found")
    return quizzes[quiz_id]


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
async def update_quiz(quiz_id: str, request: QuizUpdateRequest):
    if quiz_id not in quizzes:
        raise HTTPException(status_code=404, detail="Quiz not found")
    quiz_data = {"quiz_title": request.quiz_title, "questions": request.questions}
    quiz_data = _sanitize_quiz(quiz_data)
    quizzes[quiz_id] = quiz_data
    logger.info("Quiz updated: %s ('%s'), %d questions", quiz_id, quiz_data["quiz_title"], len(quiz_data["questions"]))
    return {"quiz_id": quiz_id, "quiz": quizzes[quiz_id]}


@app.delete("/quiz/{quiz_id}/question/{question_id}")
async def delete_question(quiz_id: str, question_id: int):
    if quiz_id not in quizzes:
        raise HTTPException(status_code=404, detail="Quiz not found")
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
async def generate_quiz_images(request: ImageGenerateRequest):
    """Generate images for quiz questions using Stable Diffusion"""
    if request.quiz_id not in quizzes:
        raise HTTPException(status_code=404, detail="Quiz not found")

    if not await image_engine.is_available():
        raise HTTPException(status_code=503, detail="Stable Diffusion not available. Start the SD WebUI server.")

    quiz = quizzes[request.quiz_id]

    if request.question_id is not None:
        question = next((q for q in quiz["questions"] if q["id"] == request.question_id), None)
        if not question:
            raise HTTPException(status_code=404, detail="Question not found")

        image = await image_engine.generate_image(question.get("image_prompt", question["text"]))
        if image:
            if request.quiz_id not in quiz_images:
                quiz_images[request.quiz_id] = {}
            quiz_images[request.quiz_id][request.question_id] = image
            return {"status": "success", "question_id": request.question_id}
        raise HTTPException(status_code=500, detail="Image generation failed")
    else:
        images = await image_engine.generate_quiz_images(quiz["questions"])
        quiz_images[request.quiz_id] = images
        return {"status": "success", "generated_count": len(images)}


@app.get("/quiz/{quiz_id}/image/{question_id}")
async def get_question_image(quiz_id: str, question_id: int):
    """Get the generated image for a specific question"""
    if quiz_id not in quiz_images or question_id not in quiz_images[quiz_id]:
        raise HTTPException(status_code=404, detail="Image not found")

    image_data = quiz_images[quiz_id][question_id]
    try:
        image_bytes = base64.b64decode(image_data)
    except Exception:
        raise HTTPException(status_code=500, detail="Corrupt image data")
    return Response(content=image_bytes, media_type="image/png")


@app.get("/sd/status")
async def sd_status():
    """Check if Stable Diffusion is available"""
    return {"available": await image_engine.is_available()}


@app.post("/room/create")
async def create_room(request: RoomCreateRequest, req: Request):
    # Resolve content based on game type
    if request.game_type == "wmlt":
        if request.mlt_id not in mlt_scenarios:
            raise HTTPException(status_code=404, detail="MLT scenario not found")
        game_data = mlt_scenarios[request.mlt_id]
        content_id = request.mlt_id
        if not game_data.get("statements"):
            raise HTTPException(status_code=422, detail="Game has no statements")
    else:
        if request.quiz_id not in quizzes:
            raise HTTPException(status_code=404, detail="Quiz not found")
        game_data = quizzes[request.quiz_id]
        content_id = request.quiz_id
        if not game_data.get("questions"):
            raise HTTPException(status_code=422, detail="Quiz has no questions")

    # Resolve wallet for spark charges (charged on game start, not room creation)
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=400, detail="Device ID required")
    tokens.ensure_wallet(wallet_id)

    # Enforce max rooms limit
    if len(socket_manager.rooms) >= config.MAX_ROOMS:
        raise HTTPException(status_code=429, detail="Too many active rooms. Please try again later.")

    room_code = generate_room_code()
    organizer_token = secrets.token_urlsafe(32)

    # Attach image URLs to quiz data if available (quiz only)
    if request.game_type == "quiz" and content_id in quiz_images:
        for question in game_data["questions"]:
            if question["id"] in quiz_images[content_id]:
                question["image_url"] = f"/quiz/{content_id}/image/{question['id']}"

    room = socket_manager.create_room(room_code, game_data, request.time_limit,
                                      organizer_token=organizer_token, content_id=content_id,
                                      game_type=request.game_type)
    room.wallet_id = wallet_id
    logger.info("Room created: %s (type=%s)", room_code, request.game_type)
    return {"room_code": room_code, "organizer_token": organizer_token}


@app.websocket("/ws/{room_code}/{client_id}")
async def websocket_endpoint(websocket: WebSocket, room_code: str, client_id: str,
                             organizer: bool = False, spectator: bool = False,
                             token: str = ""):
    await socket_manager.connect(websocket, room_code, client_id,
                                 is_organizer=organizer, is_spectator=spectator,
                                 token=token)


# --- Export / Import ---

@app.get("/quiz/{quiz_id}/export")
async def export_quiz(quiz_id: str):
    """Export a quiz as JSON for sharing/reuse."""
    if quiz_id not in quizzes:
        raise HTTPException(status_code=404, detail="Quiz not found")
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
async def import_quiz(request: QuizImportRequest):
    """Import a previously exported quiz."""
    _evict_old_content()
    quiz_id = str(uuid.uuid4())
    quiz_data = _sanitize_quiz(request.quiz)
    if not _validate_quiz(quiz_data, attempt=0):
        raise HTTPException(status_code=422, detail="Invalid quiz data: check questions, options, and answer_index values")
    quizzes[quiz_id] = quiz_data
    quiz_timestamps[quiz_id] = time.time()
    logger.info("Quiz imported: %s ('%s')", quiz_id, quiz_data.get("quiz_title", "Untitled"))
    return {"quiz_id": quiz_id, "quiz": quizzes[quiz_id]}


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

    # Idempotency: return cached result if this request was already processed
    if idem_key:
        cached_id = db.check_idempotency(idem_key, device_id)
        if cached_id and cached_id in mlt_scenarios:
            return {"scenario_id": cached_id, "game": mlt_scenarios[cached_id]}

    # Resolve wallet and check token balance
    wallet_id = tokens.get_wallet_id(req)
    if not wallet_id:
        raise HTTPException(status_code=400, detail="X-Device-Id header is required")
    tokens.ensure_wallet(wallet_id)
    if not tokens.can_generate(wallet_id):
        raise HTTPException(status_code=402, detail=f"You need {config.COST_GENERATE} token to generate. Buy tokens or watch an ad!")

    # Spend 1 token for generation
    spent, _ = tokens.spend_generate(wallet_id)
    if not spent:
        raise HTTPException(status_code=402, detail=f"You need {config.COST_GENERATE} token to generate. Buy tokens or watch an ad!")

    model_override = config.GEMINI_PREMIUM_MODEL if tokens.use_premium_model(wallet_id) and (request.provider or config.DEFAULT_PROVIDER) == "gemini" else None
    try:
        mlt_data = await mlt_engine.generate_statements(request.prompt, request.difficulty, request.num_rounds, request.provider, model_override=model_override)
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
    if idem_key:
        db.record_idempotency(idem_key, device_id, scenario_id)
    logger.info("MLT created: %s ('%s')", scenario_id, mlt_data.get("game_title", "Untitled"))
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
async def update_mlt(scenario_id: str, request: MLTUpdateRequest):
    if scenario_id not in mlt_scenarios:
        raise HTTPException(status_code=404, detail="MLT scenario not found")
    mlt_data = {"game_title": request.game_title, "statements": request.statements}
    mlt_data = _sanitize_mlt(mlt_data)
    mlt_scenarios[scenario_id] = mlt_data
    logger.info("MLT updated: %s ('%s'), %d statements", scenario_id, mlt_data["game_title"], len(mlt_data["statements"]))
    return {"scenario_id": scenario_id, "game": mlt_scenarios[scenario_id]}


@app.delete("/mlt/{scenario_id}/statement/{statement_id}")
async def delete_mlt_statement(scenario_id: str, statement_id: int):
    if scenario_id not in mlt_scenarios:
        raise HTTPException(status_code=404, detail="MLT scenario not found")
    game = mlt_scenarios[scenario_id]
    remaining = [s for s in game["statements"] if s["id"] != statement_id]
    if len(remaining) == len(game["statements"]):
        raise HTTPException(status_code=404, detail="Statement not found")
    if len(remaining) == 0:
        raise HTTPException(status_code=400, detail="Cannot delete the last statement")
    game["statements"] = remaining
    return {"scenario_id": scenario_id, "game": game}


@app.get("/mlt/{scenario_id}/export")
async def export_mlt(scenario_id: str):
    if scenario_id not in mlt_scenarios:
        raise HTTPException(status_code=404, detail="MLT scenario not found")
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
async def import_mlt(request: MLTImportRequest):
    _evict_old_content()
    scenario_id = str(uuid.uuid4())
    mlt_data = _sanitize_mlt(request.game)
    if not _validate_mlt(mlt_data, attempt=0):
        raise HTTPException(status_code=422, detail="Invalid MLT data: check statements have id and text fields")
    mlt_scenarios[scenario_id] = mlt_data
    mlt_timestamps[scenario_id] = time.time()
    logger.info("MLT imported: %s ('%s')", scenario_id, mlt_data.get("game_title", "Untitled"))
    return {"scenario_id": scenario_id, "game": mlt_scenarios[scenario_id]}


# --- Game History ---

game_history: List[dict] = []


@app.get("/history")
async def get_game_history():
    """Get history of completed games."""
    return {"games": game_history}


@app.get("/history/{room_code}")
async def get_game_detail(room_code: str):
    """Get detailed results of a specific game."""
    game = next((g for g in game_history if g["room_code"] == room_code), None)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return game


# Configure CORS
if config.ALLOWED_ORIGINS.strip():
    origins = [o.strip() for o in config.ALLOWED_ORIGINS.split(",")]
else:
    local_ip = get_local_ip()
    origins = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        f"http://{local_ip}:5173",
        f"http://{local_ip}:5174",
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
    allow_headers=["Content-Type", "Authorization", "X-Device-Id", "X-Platform", "X-App-Version", "X-Build", "X-Idempotency-Key", "X-Session-Token"],
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
async def auth_signin(request: SignInRequest):
    result = auth.signin(request.provider, request.id_token, request.device_id)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid or expired ID token")
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
            success_url=f"{origins[0]}?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{origins[0]}?checkout=cancel",
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
        raw_token_amount = int(metadata.get("token_amount", str(config.TOKEN_PACK_AMOUNT)))
        token_amount = min(raw_token_amount, max_allowed) if raw_token_amount > 0 else config.TOKEN_PACK_AMOUNT
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
                    raw_refund = int(refund_metadata.get("token_amount", str(config.TOKEN_PACK_AMOUNT)))
                    refund_max = max(config.TOKEN_PACK_AMOUNT, config.PROMO_TOKEN_AMOUNT) if config.PROMO_TOKEN_AMOUNT > 0 else config.TOKEN_PACK_AMOUNT
                    refund_amount = min(raw_refund, refund_max) if raw_refund > 0 else config.TOKEN_PACK_AMOUNT
                    if wallet_id:
                        success, _ = db.debit_tokens(wallet_id, refund_amount, "refund", stripe_session_id)
                        if not success:
                            logger.warning("Failed to debit tokens for refund: wallet=%s session=%s", wallet_id, stripe_session_id)
                        else:
                            logger.info("Debited %d tokens from wallet %s (refund, session %s)",
                                        refund_amount, wallet_id[:8], stripe_session_id[:8])
            except Exception as e:
                logger.error("Failed to process refund: %s", e)

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
    """Verify admin API key from Authorization header."""
    if not ADMIN_API_KEY:
        raise HTTPException(status_code=503, detail="Admin API not configured")
    auth_header = req.headers.get("Authorization", "")
    if auth_header != f"Bearer {ADMIN_API_KEY}":
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


@app.get("/")
async def root():
    return {"message": "AI Quiz Game API is running"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=True)
