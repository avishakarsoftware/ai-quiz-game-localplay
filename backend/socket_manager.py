from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Optional
import json
import time
import asyncio
import logging
import re

import config

logger = logging.getLogger(__name__)


class Room:
    def __init__(self, room_code: str, quiz_data: dict, time_limit: int = 15):
        self.room_code = room_code
        self.quiz = quiz_data
        self.time_limit = time_limit
        self.players: Dict[str, dict] = {}  # socket_id -> {nickname, score, prev_rank, streak, ...}
        self.organizer: Optional[WebSocket] = None
        self.organizer_id: Optional[str] = None
        self.spectators: Dict[str, WebSocket] = {}  # client_id -> ws
        self.state = "LOBBY"  # LOBBY, INTRO, QUESTION, LEADERBOARD, PODIUM
        self.current_question_index = -1
        self.question_start_time: float = 0
        self.answered_players: set = set()
        self.connections: Dict[str, WebSocket] = {}
        self.timer_task: Optional[asyncio.Task] = None
        self.previous_leaderboard: List[dict] = []
        self.lock = asyncio.Lock()
        self.last_activity = time.time()
        self.disconnected_players: Dict[str, dict] = {}  # nickname -> {score, prev_rank, streak}
        self.answer_log: List[dict] = []  # game history: per-question answer records
        # Team mode
        self.teams: Dict[str, str] = {}  # nickname -> team_name
        # Power-ups
        self.power_ups: Dict[str, dict] = {}  # nickname -> {double_points: bool, fifty_fifty: bool}

    def touch(self):
        """Update last activity timestamp."""
        self.last_activity = time.time()

    def is_expired(self) -> bool:
        return time.time() - self.last_activity > config.ROOM_TTL_SECONDS

    def _remove_connection(self, client_id: str):
        """Remove a connection. During active game, preserve player data for reconnection."""
        self.connections.pop(client_id, None)
        self.spectators.pop(client_id, None)
        if client_id in self.players:
            nickname = self.players[client_id]["nickname"]
            if self.state in ("LOBBY",):
                # In lobby, fully remove the player
                del self.players[client_id]
                logger.info("Player '%s' left room %s", nickname, self.room_code)
            else:
                # During active game, preserve data for reconnection
                self.disconnected_players[nickname] = {
                    "score": self.players[client_id]["score"],
                    "prev_rank": self.players[client_id]["prev_rank"],
                    "streak": self.players[client_id].get("streak", 0),
                }
                del self.players[client_id]
                logger.info("Player '%s' disconnected from room %s (data preserved)", nickname, self.room_code)
        if self.organizer_id == client_id:
            self.organizer = None
            self.organizer_id = None
            logger.info("Organizer disconnected from room %s", self.room_code)

    async def broadcast(self, message: dict):
        disconnected = []
        for client_id, ws in self.connections.items():
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(client_id)
        # Also broadcast to spectators
        spec_disconnected = []
        for client_id, ws in self.spectators.items():
            try:
                await ws.send_json(message)
            except Exception:
                spec_disconnected.append(client_id)
        for client_id in disconnected + spec_disconnected:
            self._remove_connection(client_id)

    async def broadcast_to_players(self, message: dict):
        """Broadcast to players only, not organizer."""
        disconnected = []
        for client_id, ws in self.connections.items():
            if client_id in self.players:
                try:
                    await ws.send_json(message)
                except Exception:
                    disconnected.append(client_id)
        for client_id in disconnected:
            self._remove_connection(client_id)

    async def send_to_organizer(self, message: dict):
        if self.organizer:
            try:
                await self.organizer.send_json(message)
            except Exception:
                self.organizer = None
                self.organizer_id = None


class SocketManager:
    def __init__(self):
        self.rooms: Dict[str, Room] = {}
        self._cleanup_task: Optional[asyncio.Task] = None

    def start_cleanup_loop(self):
        """Start the background room cleanup task."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_expired_rooms())

    async def _cleanup_expired_rooms(self):
        """Periodically remove expired rooms."""
        while True:
            try:
                await asyncio.sleep(60)
                expired = [code for code, room in self.rooms.items() if room.is_expired()]
                for code in expired:
                    room = self.rooms.pop(code, None)
                    if room and room.timer_task:
                        room.timer_task.cancel()
                    logger.info("Cleaned up expired room %s", code)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in room cleanup loop")

    def create_room(self, room_code: str, quiz_data: dict, time_limit: int = 15) -> Room:
        room = Room(room_code, quiz_data, time_limit)
        self.rooms[room_code] = room
        self.start_cleanup_loop()
        return room

    async def connect(self, websocket: WebSocket, room_code: str, client_id: str,
                      is_organizer: bool = False, is_spectator: bool = False):
        await websocket.accept()
        if room_code not in self.rooms:
            await websocket.send_json({"type": "ERROR", "message": "Room not found"})
            await websocket.close()
            return

        room = self.rooms[room_code]
        room.touch()

        if is_spectator:
            room.spectators[client_id] = websocket
            # Send current state sync to spectator
            await websocket.send_json({
                "type": "SPECTATOR_SYNC",
                "room_code": room_code,
                "state": room.state,
                "player_count": len(room.players),
                "players": [p["nickname"] for p in room.players.values()],
                "question_number": room.current_question_index + 1,
                "total_questions": len(room.quiz["questions"]),
                "leaderboard": self.get_leaderboard(room),
            })
            try:
                while True:
                    await websocket.receive_text()  # spectators are read-only
            except (WebSocketDisconnect, Exception):
                pass
            finally:
                room._remove_connection(client_id)
            return

        room.connections[client_id] = websocket

        if is_organizer:
            room.organizer = websocket
            room.organizer_id = client_id
            await websocket.send_json({"type": "ROOM_CREATED", "room_code": room_code})
        else:
            await websocket.send_json({"type": "JOINED_ROOM", "room_code": room_code})

        try:
            while True:
                data = await websocket.receive_text()
                try:
                    message = json.loads(data)
                except json.JSONDecodeError:
                    logger.warning("Malformed JSON from client %s: %s", client_id, data[:100])
                    await websocket.send_json({"type": "ERROR", "message": "Invalid message format"})
                    continue

                room.touch()
                await self.handle_message(room, client_id, message, is_organizer)
        except WebSocketDisconnect:
            logger.info("Client %s disconnected from room %s", client_id, room_code)
        except Exception:
            logger.exception("WebSocket error for client %s in room %s", client_id, room_code)
        finally:
            room._remove_connection(client_id)

    async def handle_message(self, room: Room, client_id: str, message: dict, is_organizer: bool):
        msg_type = message.get("type")

        if is_organizer:
            if msg_type == "START_GAME":
                room.state = "INTRO"
                await room.broadcast({"type": "GAME_STARTING"})

            elif msg_type == "NEXT_QUESTION":
                await self.start_question(room)

            elif msg_type == "SET_TIME_LIMIT":
                new_limit = message.get("time_limit", 15)
                if isinstance(new_limit, int) and 5 <= new_limit <= 60:
                    room.time_limit = new_limit

        else:
            if msg_type == "JOIN":
                nickname = message.get("nickname", "").strip()
                team = message.get("team", "").strip() or None
                # Sanitize first: strip HTML tags to prevent XSS
                nickname = re.sub(r'<[^>]+>', '', nickname).strip()
                if not nickname or len(nickname) > config.MAX_NICKNAME_LENGTH:
                    ws = room.connections.get(client_id)
                    if ws:
                        await ws.send_json({
                            "type": "ERROR",
                            "message": f"Nickname must be 1-{config.MAX_NICKNAME_LENGTH} characters"
                        })
                    return

                # Check for reconnection
                if nickname in room.disconnected_players:
                    saved = room.disconnected_players.pop(nickname)
                    room.players[client_id] = {
                        "nickname": nickname,
                        "score": saved["score"],
                        "prev_rank": saved["prev_rank"],
                        "streak": saved.get("streak", 0),
                    }
                    logger.info("Player '%s' reconnected to room %s with score %d", nickname, room.room_code, saved["score"])
                    ws = room.connections.get(client_id)
                    if ws:
                        state_info: dict = {
                            "type": "RECONNECTED",
                            "score": saved["score"],
                            "state": room.state,
                            "question_number": room.current_question_index + 1,
                            "total_questions": len(room.quiz["questions"]),
                        }
                        if room.state == "QUESTION":
                            question = room.quiz["questions"][room.current_question_index]
                            player_question = {k: v for k, v in question.items() if k != "answer_index"}
                            state_info["question"] = player_question
                            state_info["time_limit"] = room.time_limit
                        await ws.send_json(state_info)
                    return

                room.players[client_id] = {"nickname": nickname, "score": 0, "prev_rank": 0, "streak": 0}
                # Assign team if provided
                if team:
                    room.teams[nickname] = team
                # Initialize power-ups
                room.power_ups[nickname] = {"double_points": True, "fifty_fifty": True}
                await room.broadcast({
                    "type": "PLAYER_JOINED",
                    "nickname": nickname,
                    "player_count": len(room.players),
                    "players": [p["nickname"] for p in room.players.values()]
                })

            elif msg_type == "ANSWER":
                answer_index = message.get("answer_index")
                question = room.quiz["questions"][room.current_question_index]
                num_options = len(question.get("options", []))
                if not isinstance(answer_index, int) or not (0 <= answer_index < num_options):
                    return

                async with room.lock:
                    if room.state != "QUESTION" or client_id in room.answered_players:
                        return
                    room.answered_players.add(client_id)
                    all_answered = len(room.answered_players) >= len(room.players)
                ws = room.connections.get(client_id)
                if not ws:
                    return

                nickname = room.players[client_id]["nickname"]
                correct = answer_index == question["answer_index"]
                time_taken = time.time() - room.question_start_time

                if correct:
                    time_ratio = max(0, 1 - (time_taken / room.time_limit))
                    base_points = int(100 + (900 * time_ratio))  # 100-1000 points

                    # Streak bonus
                    room.players[client_id]["streak"] = room.players[client_id].get("streak", 0) + 1
                    streak = room.players[client_id]["streak"]
                    multiplier = 1.0
                    for threshold, mult in sorted(config.STREAK_THRESHOLDS.items()):
                        if streak >= threshold:
                            multiplier = mult
                    points = int(base_points * multiplier)

                    # Double points power-up
                    if room.power_ups.get(nickname, {}).get("double_points_active"):
                        points *= 2
                        room.power_ups[nickname]["double_points_active"] = False

                    room.players[client_id]["score"] += points

                    await ws.send_json({
                        "type": "ANSWER_RESULT",
                        "correct": True,
                        "points": points,
                        "streak": streak,
                        "multiplier": multiplier,
                    })
                else:
                    room.players[client_id]["streak"] = 0
                    await ws.send_json({
                        "type": "ANSWER_RESULT",
                        "correct": False,
                        "points": 0,
                        "streak": 0,
                        "multiplier": 1.0,
                    })

                # Log answer for game history
                room.answer_log.append({
                    "question_index": room.current_question_index,
                    "nickname": nickname,
                    "answer_index": answer_index,
                    "correct": correct,
                    "time_taken": round(time_taken, 2),
                })

                if all_answered:
                    await self.end_question(room)

            elif msg_type == "USE_POWER_UP":
                power_up = message.get("power_up")
                nickname = room.players.get(client_id, {}).get("nickname")
                if not nickname or power_up not in ("double_points", "fifty_fifty"):
                    return
                pups = room.power_ups.get(nickname, {})
                ws = room.connections.get(client_id)
                if not ws:
                    return
                if not pups.get(power_up):
                    await ws.send_json({"type": "ERROR", "message": "Power-up already used"})
                    return
                if power_up == "double_points":
                    pups["double_points"] = False
                    pups["double_points_active"] = True
                    await ws.send_json({"type": "POWER_UP_ACTIVATED", "power_up": "double_points"})
                elif power_up == "fifty_fifty":
                    pups["fifty_fifty"] = False
                    question = room.quiz["questions"][room.current_question_index]
                    correct_idx = question["answer_index"]
                    wrong_indices = [i for i in range(len(question["options"])) if i != correct_idx]
                    import random
                    remove = random.sample(wrong_indices, min(2, len(wrong_indices)))
                    await ws.send_json({
                        "type": "POWER_UP_ACTIVATED",
                        "power_up": "fifty_fifty",
                        "remove_indices": remove,
                    })

    def get_team_leaderboard(self, room: Room) -> List[dict]:
        """Aggregate player scores by team."""
        team_scores: Dict[str, list] = {}
        for player in room.players.values():
            team = room.teams.get(player["nickname"])
            if team:
                team_scores.setdefault(team, []).append(player["score"])
        result = []
        for team_name, scores in team_scores.items():
            result.append({
                "team": team_name,
                "score": int(sum(scores) / len(scores)),  # average
                "members": len(scores),
            })
        return sorted(result, key=lambda x: x["score"], reverse=True)

    def get_game_summary(self, room: Room) -> dict:
        """Build a game summary for history storage."""
        return {
            "room_code": room.room_code,
            "quiz_title": room.quiz.get("quiz_title", "Untitled"),
            "total_questions": len(room.quiz["questions"]),
            "player_count": len(room.players),
            "leaderboard": self.get_leaderboard(room),
            "team_leaderboard": self.get_team_leaderboard(room) if room.teams else [],
            "answer_log": room.answer_log,
            "completed_at": time.time(),
        }

    async def start_question(self, room: Room):
        if room.timer_task:
            room.timer_task.cancel()

        room.current_question_index += 1

        if room.current_question_index >= len(room.quiz["questions"]):
            room.state = "PODIUM"
            leaderboard = self.get_leaderboard(room)
            team_leaderboard = self.get_team_leaderboard(room) if room.teams else []
            await room.broadcast({
                "type": "PODIUM",
                "leaderboard": leaderboard,
                "team_leaderboard": team_leaderboard,
            })
            # Save game history — import here to avoid circular dependency
            try:
                from main import game_history
                game_history.append(self.get_game_summary(room))
                logger.info("Game history saved for room %s", room.room_code)
            except Exception:
                logger.warning("Could not save game history for room %s", room.room_code)
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

        room.timer_task = asyncio.create_task(self.question_timer(room))

    async def question_timer(self, room: Room):
        """Timer that ends the question after time_limit seconds."""
        try:
            for remaining in range(room.time_limit, 0, -1):
                await room.broadcast({"type": "TIMER", "remaining": remaining})
                await asyncio.sleep(1)

            await self.end_question(room)
        except asyncio.CancelledError:
            pass

    async def end_question(self, room: Room):
        # Guard against double-fire (timer + all-answered race)
        if room.state != "QUESTION":
            return

        room.state = "LEADERBOARD"

        if room.timer_task:
            room.timer_task.cancel()
            room.timer_task = None

        question = room.quiz["questions"][room.current_question_index]
        current_leaderboard = self.get_leaderboard_with_changes(room)
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
        prev_rankings = {p["nickname"]: i for i, p in enumerate(room.previous_leaderboard)}

        sorted_players = sorted(
            room.players.values(),
            key=lambda x: x["score"],
            reverse=True
        )

        result = []
        for i, player in enumerate(sorted_players):
            prev_rank = prev_rankings.get(player["nickname"], len(prev_rankings))
            result.append({
                "nickname": player["nickname"],
                "score": player["score"],
                "prev_rank": prev_rank,
                "rank_change": prev_rank - i  # positive = moved up
            })

        return result


socket_manager = SocketManager()
