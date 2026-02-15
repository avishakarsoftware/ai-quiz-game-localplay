from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, field_validator
from typing import List, Optional, Dict
from contextlib import asynccontextmanager
import uvicorn
import uuid
import random
import string
import base64
import logging
import socket as socketlib

import config
config.setup_logging()

from quiz_engine import quiz_engine
from socket_manager import socket_manager
from image_engine import image_engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting LocalPlay backend")
    socket_manager.start_cleanup_loop()
    yield
    logger.info("Shutting down LocalPlay backend")


app = FastAPI(title="AI Quiz Game Backend", lifespan=lifespan)


def get_local_ip():
    try:
        s = socketlib.socket(socketlib.AF_INET, socketlib.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


@app.get("/system/info")
async def get_system_info():
    return {"ip": get_local_ip()}


# In-memory storage
quizzes: Dict[str, dict] = {}
quiz_images: Dict[str, Dict[int, str]] = {}  # quiz_id -> {question_id: base64_image}

def generate_room_code() -> str:
    """Generate a unique 6-character room code, checking for collisions."""
    for _ in range(config.MAX_ROOM_CODE_ATTEMPTS):
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if code not in socket_manager.rooms:
            return code
    raise RuntimeError("Failed to generate unique room code")


class QuizRequest(BaseModel):
    prompt: str
    difficulty: str = "medium"
    num_questions: int = config.DEFAULT_NUM_QUESTIONS

    @field_validator('prompt')
    @classmethod
    def validate_prompt(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 500:
            raise ValueError('Prompt must be 1-500 characters')
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
    quiz_id: str
    time_limit: int = 15

    @field_validator('time_limit')
    @classmethod
    def validate_time_limit(cls, v: int) -> int:
        if v < 5 or v > 60:
            raise ValueError('Time limit must be between 5 and 60 seconds')
        return v


class ImageGenerateRequest(BaseModel):
    quiz_id: str
    question_id: Optional[int] = None  # If None, generate for all questions


@app.post("/quiz/generate")
async def generate_quiz(request: QuizRequest):
    quiz_data = await quiz_engine.generate_quiz(request.prompt, request.difficulty, request.num_questions)
    if not quiz_data:
        raise HTTPException(status_code=500, detail="Failed to generate quiz")

    quiz_id = str(uuid.uuid4())
    quizzes[quiz_id] = quiz_data
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
            if not isinstance(q['answer_index'], int) or not (0 <= q['answer_index'] < len(opts)):
                raise ValueError('Invalid answer_index')
        return v


@app.put("/quiz/{quiz_id}")
async def update_quiz(quiz_id: str, request: QuizUpdateRequest):
    if quiz_id not in quizzes:
        raise HTTPException(status_code=404, detail="Quiz not found")
    quizzes[quiz_id] = {"quiz_title": request.quiz_title, "questions": request.questions}
    logger.info("Quiz updated: %s ('%s'), %d questions", quiz_id, request.quiz_title, len(request.questions))
    return {"quiz_id": quiz_id, "quiz": quizzes[quiz_id]}


@app.delete("/quiz/{quiz_id}/question/{question_id}")
async def delete_question(quiz_id: str, question_id: int):
    if quiz_id not in quizzes:
        raise HTTPException(status_code=404, detail="Quiz not found")
    quiz = quizzes[quiz_id]
    original_len = len(quiz["questions"])
    quiz["questions"] = [q for q in quiz["questions"] if q["id"] != question_id]
    if len(quiz["questions"]) == original_len:
        raise HTTPException(status_code=404, detail="Question not found")
    if len(quiz["questions"]) == 0:
        raise HTTPException(status_code=400, detail="Cannot delete the last question")
    logger.info("Question %d deleted from quiz %s", question_id, quiz_id)
    return {"quiz_id": quiz_id, "quiz": quiz}


@app.post("/quiz/generate-images")
async def generate_quiz_images(request: ImageGenerateRequest):
    """Generate images for quiz questions using Stable Diffusion"""
    if request.quiz_id not in quizzes:
        raise HTTPException(status_code=404, detail="Quiz not found")

    if not image_engine.is_available():
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
    image_bytes = base64.b64decode(image_data)
    return Response(content=image_bytes, media_type="image/png")


@app.get("/sd/status")
async def sd_status():
    """Check if Stable Diffusion is available"""
    return {"available": image_engine.is_available()}


@app.post("/room/create")
async def create_room(request: RoomCreateRequest):
    if request.quiz_id not in quizzes:
        raise HTTPException(status_code=404, detail="Quiz not found")

    room_code = generate_room_code()
    quiz_data = quizzes[request.quiz_id]

    # Attach image URLs to quiz data if available
    if request.quiz_id in quiz_images:
        for question in quiz_data["questions"]:
            if question["id"] in quiz_images[request.quiz_id]:
                question["image_url"] = f"/quiz/{request.quiz_id}/image/{question['id']}"

    socket_manager.create_room(room_code, quiz_data, request.time_limit)
    logger.info("Room created: %s", room_code)
    return {"room_code": room_code}


@app.websocket("/ws/{room_code}/{client_id}")
async def websocket_endpoint(websocket: WebSocket, room_code: str, client_id: str,
                             organizer: bool = False, spectator: bool = False):
    await socket_manager.connect(websocket, room_code, client_id,
                                 is_organizer=organizer, is_spectator=spectator)


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
            if len(q["options"]) not in (2, 4):
                raise ValueError("Question must have 2 or 4 options")
        return v


@app.post("/quiz/import")
async def import_quiz(request: QuizImportRequest):
    """Import a previously exported quiz."""
    quiz_id = str(uuid.uuid4())
    quizzes[quiz_id] = request.quiz
    logger.info("Quiz imported: %s ('%s')", quiz_id, request.quiz.get("quiz_title", "Untitled"))
    return {"quiz_id": quiz_id, "quiz": quizzes[quiz_id]}


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
        "http://127.0.0.1:5173",
        f"http://{local_ip}:5173",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.get("/")
async def root():
    return {"message": "AI Quiz Game API is running"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=True)
