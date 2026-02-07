from fastapi import WebSocket
from typing import Dict, List
import json
import time
import asyncio

class Room:
    def __init__(self, room_code: str, quiz_data: dict, time_limit: int = 15):
        self.room_code = room_code
        self.quiz = quiz_data
        self.time_limit = time_limit  # seconds per question
        self.players: Dict[str, dict] = {}  # socket_id -> {nickname, score, prev_rank}
        self.organizer: WebSocket = None
        self.state = "LOBBY"  # LOBBY, QUESTION, LEADERBOARD, PODIUM
        self.current_question_index = -1
        self.question_start_time: float = 0
        self.answered_players: set = set()
        self.connections: Dict[str, WebSocket] = {}
        self.timer_task = None
        self.previous_leaderboard: List[dict] = []

    async def broadcast(self, message: dict):
        disconnected = []
        for client_id, ws in self.connections.items():
            try:
                await ws.send_json(message)
            except:
                disconnected.append(client_id)
        for client_id in disconnected:
            del self.connections[client_id]

    async def broadcast_to_players(self, message: dict):
        """Broadcast to players only, not organizer"""
        disconnected = []
        for client_id, ws in self.connections.items():
            if client_id in self.players:
                try:
                    await ws.send_json(message)
                except:
                    disconnected.append(client_id)
        for client_id in disconnected:
            del self.connections[client_id]

    async def send_to_organizer(self, message: dict):
        if self.organizer:
            try:
                await self.organizer.send_json(message)
            except:
                self.organizer = None


class SocketManager:
    def __init__(self):
        self.rooms: Dict[str, Room] = {}

    def create_room(self, room_code: str, quiz_data: dict, time_limit: int = 15) -> Room:
        room = Room(room_code, quiz_data, time_limit)
        self.rooms[room_code] = room
        return room

    async def connect(self, websocket: WebSocket, room_code: str, client_id: str, is_organizer: bool = False):
        await websocket.accept()
        if room_code not in self.rooms:
            await websocket.send_json({"type": "ERROR", "message": "Room not found"})
            await websocket.close()
            return

        room = self.rooms[room_code]
        room.connections[client_id] = websocket

        if is_organizer:
            room.organizer = websocket
            await websocket.send_json({"type": "ROOM_CREATED", "room_code": room_code})
        else:
            await websocket.send_json({"type": "JOINED_ROOM", "room_code": room_code})

        try:
            while True:
                data = await websocket.receive_text()
                message = json.loads(data)
                await self.handle_message(room, client_id, message, is_organizer)
        except Exception:
            if client_id in room.connections:
                del room.connections[client_id]
            if not is_organizer and client_id in room.players:
                pass
            if is_organizer:
                room.organizer = None

    async def handle_message(self, room: Room, client_id: str, message: dict, is_organizer: bool):
        msg_type = message.get("type")

        if is_organizer:
            if msg_type == "START_GAME":
                room.state = "INTRO"
                await room.broadcast({"type": "GAME_STARTING"})
            
            elif msg_type == "NEXT_QUESTION":
                await self.start_question(room)
            
            elif msg_type == "SET_TIME_LIMIT":
                room.time_limit = message.get("time_limit", 15)
        
        else:
            if msg_type == "JOIN":
                nickname = message.get("nickname", f"Player {len(room.players) + 1}")
                room.players[client_id] = {"nickname": nickname, "score": 0, "prev_rank": 0}
                await room.broadcast({
                    "type": "PLAYER_JOINED", 
                    "nickname": nickname, 
                    "player_count": len(room.players)
                })
            
            elif msg_type == "ANSWER":
                if room.state == "QUESTION" and client_id not in room.answered_players:
                    room.answered_players.add(client_id)
                    answer_index = message.get("answer_index")
                    question = room.quiz["questions"][room.current_question_index]

                    if answer_index == question["answer_index"]:
                        # Time-based scoring: max 1000 points, minimum 100
                        time_taken = time.time() - room.question_start_time
                        time_ratio = max(0, 1 - (time_taken / room.time_limit))
                        points = int(100 + (900 * time_ratio))  # 100-1000 points
                        room.players[client_id]["score"] += points
                        
                        # Send score feedback to player
                        await room.connections[client_id].send_json({
                            "type": "ANSWER_RESULT",
                            "correct": True,
                            "points": points
                        })
                    else:
                        await room.connections[client_id].send_json({
                            "type": "ANSWER_RESULT",
                            "correct": False,
                            "points": 0
                        })

                    # Check if all players answered
                    if len(room.answered_players) >= len(room.players):
                        await self.end_question(room)

    async def start_question(self, room: Room):
        # Cancel any existing timer
        if room.timer_task:
            room.timer_task.cancel()
        
        room.current_question_index += 1
        
        if room.current_question_index >= len(room.quiz["questions"]):
            room.state = "PODIUM"
            await room.broadcast({
                "type": "PODIUM", 
                "leaderboard": self.get_leaderboard(room)
            })
            return
        
        # Store previous leaderboard for animation
        room.previous_leaderboard = self.get_leaderboard(room)
        
        room.state = "QUESTION"
        room.question_start_time = time.time()
        room.answered_players = set()
        
        question = room.quiz["questions"][room.current_question_index]
        player_question = {k: v for k, v in question.items() if k != "answer_index"}
        
        await room.broadcast({
            "type": "QUESTION",
            "question": player_question,
            "question_number": room.current_question_index + 1,
            "total_questions": len(room.quiz["questions"]),
            "time_limit": room.time_limit
        })
        
        # Start timer
        room.timer_task = asyncio.create_task(self.question_timer(room))

    async def question_timer(self, room: Room):
        """Timer that ends the question after time_limit seconds"""
        try:
            # Send countdown updates
            for remaining in range(room.time_limit, 0, -1):
                await room.broadcast({"type": "TIMER", "remaining": remaining})
                await asyncio.sleep(1)
            
            # Time's up
            if room.state == "QUESTION":
                await self.end_question(room)
        except asyncio.CancelledError:
            pass

    async def end_question(self, room: Room):
        if room.timer_task:
            room.timer_task.cancel()
            room.timer_task = None
        
        room.state = "LEADERBOARD"
        question = room.quiz["questions"][room.current_question_index]
        
        # Get current leaderboard with rank changes
        current_leaderboard = self.get_leaderboard_with_changes(room)
        
        # Check if this was the final question
        is_final = room.current_question_index >= len(room.quiz["questions"]) - 1
        
        await room.broadcast({
            "type": "QUESTION_OVER",
            "answer": question["answer_index"],
            "leaderboard": current_leaderboard,
            "previous_leaderboard": room.previous_leaderboard,
            "is_final": is_final
        })

    def get_leaderboard(self, room: Room) -> List[dict]:
        sorted_players = sorted(
            room.players.values(), 
            key=lambda x: x["score"], 
            reverse=True
        )
        return [{"nickname": p["nickname"], "score": p["score"]} for p in sorted_players]

    def get_leaderboard_with_changes(self, room: Room) -> List[dict]:
        # Get previous rankings
        prev_rankings = {p["nickname"]: i for i, p in enumerate(room.previous_leaderboard)}
        
        sorted_players = sorted(
            room.players.values(),
            key=lambda x: x["score"],
            reverse=True
        )
        
        result = []
        for i, player in enumerate(sorted_players):
            prev_rank = prev_rankings.get(player["nickname"], i)
            result.append({
                "nickname": player["nickname"],
                "score": player["score"],
                "prev_rank": prev_rank,
                "rank_change": prev_rank - i  # positive = moved up
            })
        
        return result


socket_manager = SocketManager()
