from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from typing import List, Optional, Dict
import uvicorn
import os
import uuid
import random
import string
import base64
from quiz_engine import quiz_engine
from socket_manager import socket_manager
from image_engine import image_engine

import socket

app = FastAPI(title="AI Quiz Game Backend")

def get_local_ip():
    try:
        # Create a dummy socket connection to determine the local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
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

def generate_room_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

class QuizRequest(BaseModel):
    prompt: str

class RoomCreateRequest(BaseModel):
    quiz_id: str
    time_limit: int = 15

class ImageGenerateRequest(BaseModel):
    quiz_id: str
    question_id: Optional[int] = None  # If None, generate for all questions

@app.post("/quiz/generate")
async def generate_quiz(request: QuizRequest):
    quiz_data = await quiz_engine.generate_quiz(request.prompt)
    if not quiz_data:
        raise HTTPException(status_code=500, detail="Failed to generate quiz")
    
    quiz_id = str(uuid.uuid4())
    quizzes[quiz_id] = quiz_data
    return {"quiz_id": quiz_id, "quiz": quiz_data}

@app.get("/quiz/{quiz_id}")
async def get_quiz(quiz_id: str):
    if quiz_id not in quizzes:
        raise HTTPException(status_code=404, detail="Quiz not found")
    return quizzes[quiz_id]

@app.post("/quiz/generate-images")
async def generate_quiz_images(request: ImageGenerateRequest):
    """Generate images for quiz questions using Stable Diffusion"""
    if request.quiz_id not in quizzes:
        raise HTTPException(status_code=404, detail="Quiz not found")
    
    if not image_engine.is_available():
        raise HTTPException(status_code=503, detail="Stable Diffusion not available. Start the SD WebUI server.")
    
    quiz = quizzes[request.quiz_id]
    
    if request.question_id is not None:
        # Generate for specific question
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
        # Generate for all questions
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
    return {"room_code": room_code}

@app.websocket("/ws/{room_code}/{client_id}")
async def websocket_endpoint(websocket: WebSocket, room_code: str, client_id: str, organizer: bool = False):
    await socket_manager.connect(websocket, room_code, client_id, is_organizer=organizer)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "AI Quiz Game API is running"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
