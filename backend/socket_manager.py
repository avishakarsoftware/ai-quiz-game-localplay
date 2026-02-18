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
    def __init__(self, room_code: str, quiz_data: dict, time_limit: int = 15,
                 organizer_token: str = ""):
        self.room_code = room_code
        self.quiz = quiz_data
        self.time_limit = time_limit
        self.organizer_token = organizer_token  # secret token for organizer auth
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
        # WS rate limiting: client_id -> list of timestamps
        self.msg_timestamps: Dict[str, list] = {}
        # Team mode
        self.teams: Dict[str, str] = {}  # nickname -> team_name
        # Power-ups
        self.power_ups: Dict[str, dict] = {}  # nickname -> {double_points: bool, fifty_fifty: bool}
        # Bonus rounds
        self.bonus_questions: set = set()  # indices of bonus round questions (2x points)

    def reset_for_new_game(self, new_quiz_data: dict, new_time_limit: int):
        """Reset room for a new game round, keeping players connected."""
        self.quiz = new_quiz_data
        self.time_limit = new_time_limit

        self.state = "LOBBY"
        self.current_question_index = -1
        self.question_start_time = 0
        self.answered_players = set()
        self.previous_leaderboard = []
        self.answer_log = []

        if self.timer_task:
            self.timer_task.cancel()
            self.timer_task = None

        # Remove players who are no longer connected
        stale = [cid for cid in self.players if cid not in self.connections]
        for cid in stale:
            nickname = self.players[cid]["nickname"]
            self.teams.pop(nickname, None)
            self.power_ups.pop(nickname, None)
            del self.players[cid]

        for client_id in self.players:
            self.players[client_id]["score"] = 0
            self.players[client_id]["prev_rank"] = 0
            self.players[client_id]["streak"] = 0

        self.disconnected_players.clear()
        self.bonus_questions = set()

        for nickname in self.power_ups:
            self.power_ups[nickname] = {"double_points": True, "fifty_fifty": True}

        self.touch()

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
                    "avatar": self.players[client_id].get("avatar", ""),
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

    def create_room(self, room_code: str, quiz_data: dict, time_limit: int = 15,
                    organizer_token: str = "") -> Room:
        room = Room(room_code, quiz_data, time_limit, organizer_token=organizer_token)
        self.rooms[room_code] = room
        self.start_cleanup_loop()
        return room

    async def connect(self, websocket: WebSocket, room_code: str, client_id: str,
                      is_organizer: bool = False, is_spectator: bool = False,
                      token: str = ""):
        await websocket.accept()
        if room_code not in self.rooms:
            await websocket.send_json({"type": "ERROR", "message": "Room not found"})
            await websocket.close()
            return

        room = self.rooms[room_code]

        # Verify organizer token
        if is_organizer:
            if not token or token != room.organizer_token:
                await websocket.send_json({"type": "ERROR", "message": "Invalid organizer token"})
                await websocket.close()
                return

        room.touch()

        if is_spectator:
            room.spectators[client_id] = websocket
            try:
                # Send current state sync to spectator
                await websocket.send_json({
                    "type": "SPECTATOR_SYNC",
                    "room_code": room_code,
                    "state": room.state,
                    "player_count": len(room.players),
                    "players": [{"nickname": p["nickname"], "avatar": p.get("avatar", "")} for p in room.players.values()],
                    "question_number": room.current_question_index + 1,
                    "total_questions": len(room.quiz["questions"]),
                    "leaderboard": self.get_leaderboard(room),
                })
                while True:
                    await websocket.receive_text()  # spectators are read-only
            except (WebSocketDisconnect, Exception):
                pass
            finally:
                room._remove_connection(client_id)
            return

        room.connections[client_id] = websocket

        if is_organizer:
            # Clean up stale organizer connection if a different client_id
            if room.organizer_id and room.organizer_id != client_id:
                room.connections.pop(room.organizer_id, None)
            room.organizer = websocket
            room.organizer_id = client_id
            # Detect reconnection: room already has players or game has progressed
            if room.current_question_index >= 0 or len(room.players) > 0:
                await self._send_organizer_sync(room)
            else:
                await websocket.send_json({"type": "ROOM_CREATED", "room_code": room_code})
        else:
            await websocket.send_json({"type": "JOINED_ROOM", "room_code": room_code})

        try:
            while True:
                data = await websocket.receive_text()

                # Enforce message size limit
                if len(data) > config.MAX_WS_MESSAGE_SIZE:
                    await websocket.send_json({"type": "ERROR", "message": "Message too large"})
                    continue

                # Per-client rate limiting
                now = time.time()
                timestamps = room.msg_timestamps.setdefault(client_id, [])
                timestamps[:] = [t for t in timestamps if now - t < 1.0]
                if len(timestamps) >= config.WS_RATE_LIMIT_PER_SEC:
                    await websocket.send_json({"type": "ERROR", "message": "Too many messages"})
                    continue
                timestamps.append(now)

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

    async def _send_organizer_sync(self, room: Room):
        """Send full game state to a reconnecting organizer."""
        sync = {
            "type": "ORGANIZER_RECONNECTED",
            "room_code": room.room_code,
            "state": room.state,
            "player_count": len(room.players),
            "players": [
                {"nickname": p["nickname"], "avatar": p.get("avatar", "")}
                for p in room.players.values()
            ],
            "question_number": room.current_question_index + 1,
            "total_questions": len(room.quiz["questions"]),
            "leaderboard": self.get_leaderboard(room),
            "team_leaderboard": self.get_team_leaderboard(room),
            "time_limit": room.time_limit,
            "quiz": room.quiz,
        }

        if room.state == "QUESTION":
            question = room.quiz["questions"][room.current_question_index]
            sync["question"] = question
            sync["answered_count"] = len(room.answered_players)
            sync["is_bonus"] = room.current_question_index in room.bonus_questions
            elapsed = time.time() - room.question_start_time
            sync["time_remaining"] = max(0, room.time_limit - int(elapsed))

        await room.organizer.send_json(sync)
        logger.info("Organizer reconnected to room %s (state: %s)", room.room_code, room.state)

    async def handle_message(self, room: Room, client_id: str, message: dict, is_organizer: bool):
        msg_type = message.get("type")

        if is_organizer:
            if msg_type == "START_GAME":
                self._select_bonus_questions(room)
                room.state = "INTRO"
                await room.broadcast({"type": "GAME_STARTING"})

            elif msg_type == "NEXT_QUESTION":
                if room.state == "QUESTION":
                    await self.end_question(room)
                else:
                    await self.start_question(room)

            elif msg_type == "SET_TIME_LIMIT":
                new_limit = message.get("time_limit", 15)
                if isinstance(new_limit, int) and 5 <= new_limit <= 60:
                    room.time_limit = new_limit

            elif msg_type == "END_QUIZ":
                if room.state in ("QUESTION", "LEADERBOARD"):
                    if room.timer_task:
                        room.timer_task.cancel()
                        room.timer_task = None
                    room.state = "PODIUM"
                    leaderboard = self.get_leaderboard(room)
                    team_leaderboard = self.get_team_leaderboard(room)
                    await room.broadcast({
                        "type": "PODIUM",
                        "leaderboard": leaderboard,
                        "team_leaderboard": team_leaderboard,
                    })
                    try:
                        from main import game_history
                        game_history.append(self.get_game_summary(room))
                    except Exception:
                        logger.warning("Could not save game history for room %s", room.room_code)

            elif msg_type == "RESET_ROOM":
                if room.state != "PODIUM":
                    return
                new_quiz_data = message.get("quiz_data")
                new_time_limit = message.get("time_limit", room.time_limit)
                if not new_quiz_data:
                    return
                room.reset_for_new_game(new_quiz_data, new_time_limit)
                logger.info("Room %s reset for new game", room.room_code)
                await room.broadcast({
                    "type": "ROOM_RESET",
                    "room_code": room.room_code,
                    "player_count": len(room.players),
                    "players": [{"nickname": p["nickname"], "avatar": p.get("avatar", "")} for p in room.players.values()],
                })

        else:
            if msg_type == "JOIN":
                nickname = message.get("nickname", "").strip()
                team = message.get("team", "").strip() or None
                # Sanitize: strip HTML tags to prevent XSS
                nickname = re.sub(r'<[^>]+>', '', nickname).strip()
                if not nickname or len(nickname) > config.MAX_NICKNAME_LENGTH:
                    ws = room.connections.get(client_id)
                    if ws:
                        await ws.send_json({
                            "type": "ERROR",
                            "message": f"Nickname must be 1-{config.MAX_NICKNAME_LENGTH} characters"
                        })
                    return

                # Sanitize team name
                if team:
                    team = re.sub(r'<[^>]+>', '', team).strip()
                    if len(team) > config.MAX_TEAM_NAME_LENGTH:
                        team = team[:config.MAX_TEAM_NAME_LENGTH]
                    if not team:
                        team = None

                # Sanitize and limit avatar length
                avatar = message.get("avatar", "")
                if not isinstance(avatar, str):
                    avatar = ""
                avatar = avatar[:config.MAX_AVATAR_LENGTH]

                # Check for reconnection (disconnected mid-game)
                if nickname in room.disconnected_players:
                    saved = room.disconnected_players.pop(nickname)
                    room.players[client_id] = {
                        "nickname": nickname,
                        "score": saved["score"],
                        "prev_rank": saved["prev_rank"],
                        "streak": saved.get("streak", 0),
                        "avatar": saved.get("avatar", avatar),
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
                            "avatar": saved.get("avatar", avatar),
                        }
                        if room.state == "QUESTION":
                            question = room.quiz["questions"][room.current_question_index]
                            player_question = {k: v for k, v in question.items() if k != "answer_index"}
                            state_info["question"] = player_question
                            state_info["time_limit"] = room.time_limit
                            state_info["is_bonus"] = room.current_question_index in room.bonus_questions
                        await ws.send_json(state_info)
                    return

                # Check for duplicate nickname among active players
                existing_id = None
                for pid, pdata in room.players.items():
                    if pdata["nickname"] == nickname:
                        existing_id = pid
                        break

                if existing_id:
                    # Kick the old connection and let the new one take over
                    old_ws = room.connections.pop(existing_id, None)
                    if old_ws:
                        try:
                            await old_ws.send_json({"type": "KICKED", "message": "You joined from another device"})
                            await old_ws.close()
                        except Exception:
                            pass
                    # Transfer player data to new client_id
                    player_data = room.players.pop(existing_id)
                    room.players[client_id] = player_data
                    logger.info("Player '%s' rejoined room %s (replaced old connection)", nickname, room.room_code)

                    ws = room.connections.get(client_id)
                    if ws:
                        state_info = {
                            "type": "RECONNECTED",
                            "score": player_data["score"],
                            "state": room.state,
                            "question_number": room.current_question_index + 1,
                            "total_questions": len(room.quiz["questions"]),
                            "avatar": player_data.get("avatar", ""),
                        }
                        if room.state == "QUESTION":
                            question = room.quiz["questions"][room.current_question_index]
                            player_question = {k: v for k, v in question.items() if k != "answer_index"}
                            state_info["question"] = player_question
                            state_info["time_limit"] = room.time_limit
                            state_info["is_bonus"] = room.current_question_index in room.bonus_questions
                        await ws.send_json(state_info)
                    return

                room.players[client_id] = {"nickname": nickname, "score": 0, "prev_rank": 0, "streak": 0, "avatar": avatar}
                # Assign team if provided
                if team:
                    room.teams[nickname] = team
                # Initialize power-ups
                room.power_ups[nickname] = {"double_points": True, "fifty_fifty": True}
                await room.broadcast({
                    "type": "PLAYER_JOINED",
                    "nickname": nickname,
                    "player_count": len(room.players),
                    "players": [{"nickname": p["nickname"], "avatar": p.get("avatar", "")} for p in room.players.values()]
                })

            elif msg_type == "ANSWER":
                answer_index = message.get("answer_index")
                # Bounds check to prevent IndexError
                if room.current_question_index < 0 or room.current_question_index >= len(room.quiz["questions"]):
                    return
                question = room.quiz["questions"][room.current_question_index]
                num_options = len(question.get("options", []))
                if not isinstance(answer_index, int) or not (0 <= answer_index < num_options):
                    return

                async with room.lock:
                    if room.state != "QUESTION" or client_id in room.answered_players:
                        return
                    room.answered_players.add(client_id)
                    all_answered = len(room.answered_players) >= len(room.players)

                # Notify organizer about answer progress
                await room.send_to_organizer({
                    "type": "ANSWER_COUNT",
                    "answered": len(room.answered_players),
                    "total": len(room.players),
                })

                ws = room.connections.get(client_id)
                if not ws:
                    return

                nickname = room.players[client_id]["nickname"]
                correct = answer_index == question["answer_index"]
                time_taken = time.time() - room.question_start_time

                if correct:
                    time_ratio = max(0, 1 - (time_taken / room.time_limit))
                    base_points = int(100 + (900 * time_ratio))  # 100-1000 points

                    # Bonus round (2x base points for everyone)
                    is_bonus = room.current_question_index in room.bonus_questions
                    if is_bonus:
                        base_points *= 2

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
                        "is_bonus": is_bonus,
                    })
                else:
                    room.players[client_id]["streak"] = 0
                    await ws.send_json({
                        "type": "ANSWER_RESULT",
                        "correct": False,
                        "points": 0,
                        "streak": 0,
                        "multiplier": 1.0,
                        "is_bonus": room.current_question_index in room.bonus_questions,
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
                ws = room.connections.get(client_id)
                if not ws:
                    return

                async with room.lock:
                    pups = room.power_ups.get(nickname, {})
                    if not pups.get(power_up):
                        await ws.send_json({"type": "ERROR", "message": "Power-up already used"})
                        return
                    if power_up == "double_points":
                        pups["double_points"] = False
                        pups["double_points_active"] = True
                        await ws.send_json({"type": "POWER_UP_ACTIVATED", "power_up": "double_points"})
                    elif power_up == "fifty_fifty":
                        pups["fifty_fifty"] = False
                        # Bounds check before accessing question
                        if room.current_question_index < 0 or room.current_question_index >= len(room.quiz["questions"]):
                            return
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
        """Aggregate player scores by team. Solo players use their nickname."""
        team_scores: Dict[str, list] = {}
        for player in room.players.values():
            team = room.teams.get(player["nickname"]) or player["nickname"]
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
            "team_leaderboard": self.get_team_leaderboard(room),
            "answer_log": room.answer_log,
            "completed_at": time.time(),
        }

    def _select_bonus_questions(self, room: Room):
        """Pre-select which questions will be bonus rounds (2x points)."""
        import random
        total = len(room.quiz["questions"])
        if total < 4:
            room.bonus_questions = set()
            return
        # Eligible: exclude first and last question
        eligible = list(range(1, total - 1))
        num_bonus = max(1, int(total * config.BONUS_ROUND_FRACTION))
        num_bonus = min(num_bonus, len(eligible))
        room.bonus_questions = set(random.sample(eligible, num_bonus))
        logger.info("Room %s bonus questions: %s", room.room_code, room.bonus_questions)

    async def start_question(self, room: Room):
        if room.timer_task:
            room.timer_task.cancel()

        room.current_question_index += 1

        if room.current_question_index >= len(room.quiz["questions"]):
            room.state = "PODIUM"
            leaderboard = self.get_leaderboard(room)
            team_leaderboard = self.get_team_leaderboard(room)
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
        room.answered_players = set()

        question = room.quiz["questions"][room.current_question_index]
        player_question = {k: v for k, v in question.items() if k != "answer_index"}

        is_bonus = room.current_question_index in room.bonus_questions

        await room.broadcast({
            "type": "QUESTION",
            "question": player_question,
            "question_number": room.current_question_index + 1,
            "total_questions": len(room.quiz["questions"]),
            "time_limit": room.time_limit,
            "is_bonus": is_bonus,
        })

        # Delay timer start for bonus rounds so the splash animation plays first
        if is_bonus:
            await asyncio.sleep(2)

        room.question_start_time = time.time()
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

        # Reset streak for players who didn't answer
        for cid, player in room.players.items():
            if cid not in room.answered_players:
                player["streak"] = 0

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
        return [{"nickname": p["nickname"], "score": p["score"], "avatar": p.get("avatar", "")} for p in sorted_players]

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
                "avatar": player.get("avatar", ""),
                "prev_rank": prev_rank,
                "rank_change": prev_rank - i  # positive = moved up
            })

        return result


socket_manager = SocketManager()
