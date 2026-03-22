from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Optional
import json
import hmac
import secrets
import time
import asyncio
import logging
import re

import config

logger = logging.getLogger(__name__)


class Room:
    def __init__(self, room_code: str, game_data: dict, time_limit: int = 15,
                 organizer_token: str = "", content_id: str = "",
                 game_type: str = "quiz"):
        self.room_code = room_code
        self.quiz = game_data  # generic game content (quiz or WMLT)
        self.content_id = content_id
        self.game_type = game_type  # "quiz" or "wmlt"
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
        self._organizer_just_disconnected = False  # flag for post-disconnect notification
        self._player_event: Optional[tuple] = None  # ('left'|'disconnected'|'reconnected', nickname)
        self.disconnected_players: Dict[str, dict] = {}  # nickname -> {score, prev_rank, streak}
        self.answer_log: List[dict] = []  # game history: per-question answer records
        # WS rate limiting: client_id -> list of timestamps
        self.msg_timestamps: Dict[str, list] = {}
        self._organizer_cleanup_task: Optional[asyncio.Task] = None
        # Team mode
        self.teams: Dict[str, str] = {}  # nickname -> team_name
        # Power-ups
        self.power_ups: Dict[str, dict] = {}  # nickname -> {double_points: bool, fifty_fifty: bool}
        # Session tokens for nickname ownership
        self.player_tokens: Dict[str, str] = {}  # nickname -> session_token
        # Bonus rounds
        self.bonus_questions: set = set()  # indices of bonus round questions (2x points)
        self.locked: bool = False  # True = no new players can join
        # WMLT voting state
        self.votes: Dict[str, str] = {}  # nickname -> voted_for_nickname (per-round)
        self.show_votes: bool = True  # Show vote breakdown after each round
        self.mlt_round_history: List[dict] = []  # per-round vote data for superlatives

    def reset_for_new_game(self, new_game_data: dict, new_time_limit: int,
                           game_type: Optional[str] = None,
                           content_id: Optional[str] = None):
        """Reset room for a new game round, keeping players connected."""
        self.quiz = new_game_data
        self.time_limit = new_time_limit
        if game_type:
            self.game_type = game_type
        if content_id:
            self.content_id = content_id

        self.state = "LOBBY"
        self.locked = False
        self.current_question_index = -1
        self.question_start_time = 0
        self.answered_players = set()
        self.previous_leaderboard = []
        self.answer_log = []
        self.votes = {}

        if self.timer_task:
            self.timer_task.cancel()
            self.timer_task = None

        # Remove players who are no longer connected
        stale = [cid for cid in self.players if cid not in self.connections]
        for cid in stale:
            nickname = self.players[cid]["nickname"]
            self.teams.pop(nickname, None)
            self.power_ups.pop(nickname, None)
            self.player_tokens.pop(nickname, None)
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

    def total_rounds(self) -> int:
        """Total number of rounds (questions for quiz, statements for WMLT)."""
        if self.game_type == "wmlt":
            return len(self.quiz.get("statements", []))
        return len(self.quiz.get("questions", []))

    def current_round_data(self) -> Optional[dict]:
        """Current round item (question or statement)."""
        idx = self.current_question_index
        if idx < 0 or idx >= self.total_rounds():
            return None
        if self.game_type == "wmlt":
            return self.quiz["statements"][idx]
        return self.quiz["questions"][idx]

    def game_title(self) -> str:
        """Title of the game content."""
        return self.quiz.get("game_title", self.quiz.get("quiz_title", "Untitled"))

    def player_nicknames(self) -> List[str]:
        """List of active player nicknames."""
        return [p["nickname"] for p in self.players.values()]

    def _remove_connection(self, client_id: str):
        """Remove a connection. During active game, preserve player data for reconnection."""
        # Spectator cleanup: only touch spectator dict, never player/organizer state
        if client_id in self.spectators:
            self.spectators.pop(client_id, None)
            self.msg_timestamps.pop(client_id, None)
            return
        self.connections.pop(client_id, None)
        self.msg_timestamps.pop(client_id, None)
        if client_id in self.players:
            nickname = self.players[client_id]["nickname"]
            if self.state in ("LOBBY",):
                # In lobby, fully remove the player
                del self.players[client_id]
                self.teams.pop(nickname, None)
                self.power_ups.pop(nickname, None)
                self._player_event = ("left", nickname)
                logger.info("Player '%s' left room %s", nickname, self.room_code)
            else:
                # During active game, preserve data for reconnection
                self.disconnected_players[nickname] = {
                    "score": self.players[client_id]["score"],
                    "prev_rank": self.players[client_id]["prev_rank"],
                    "streak": self.players[client_id].get("streak", 0),
                    "avatar": self.players[client_id].get("avatar", ""),
                    "_answered_client_id": client_id if client_id in self.answered_players else None,
                }
                del self.players[client_id]
                self._player_event = ("disconnected", nickname)
                logger.info("Player '%s' disconnected from room %s (data preserved)", nickname, self.room_code)
        if self.organizer_id == client_id:
            self.organizer = None
            self.organizer_id = None
            self._organizer_just_disconnected = True
            logger.info("Organizer disconnected from room %s", self.room_code)

    async def close_all_connections(self):
        """Close all player, organizer, and spectator websockets."""
        for ws in list(self.connections.values()):
            try:
                await ws.close()
            except Exception:
                pass
        for ws in list(self.spectators.values()):
            try:
                await ws.close()
            except Exception:
                pass

    async def broadcast(self, message: dict):
        disconnected = []
        for client_id, ws in list(self.connections.items()):
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(client_id)
        # Also broadcast to spectators
        spec_disconnected = []
        for client_id, ws in list(self.spectators.items()):
            try:
                await ws.send_json(message)
            except Exception:
                spec_disconnected.append(client_id)
        for client_id in disconnected + spec_disconnected:
            self._remove_connection(client_id)

    async def broadcast_to_players(self, message: dict):
        """Broadcast to players only, not organizer."""
        disconnected = []
        for client_id, ws in list(self.connections.items()):
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
        self.allowed_origins: List[str] = []

    def start_cleanup_loop(self):
        """Start the background room cleanup task."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_expired_rooms())

    def stop_cleanup_loop(self):
        """Cancel the background room cleanup task."""
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            self._cleanup_task = None

    async def _cleanup_expired_rooms(self):
        """Periodically remove expired rooms."""
        while True:
            try:
                await asyncio.sleep(60)
                expired = [code for code, room in self.rooms.items() if room.is_expired()]
                for code in expired:
                    room = self.rooms.pop(code, None)
                    if room:
                        if room.timer_task:
                            room.timer_task.cancel()
                        await room.close_all_connections()
                    logger.info("Cleaned up expired room %s", code)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in room cleanup loop")

    async def _delayed_room_cleanup(self, room_code: str, delay: int = 30):
        """Delete a room after a grace period if the organizer hasn't reconnected."""
        try:
            await asyncio.sleep(delay)
            room = self.rooms.get(room_code)
            if room and room.organizer is None:
                await room.broadcast({"type": "ROOM_CLOSED"})
                self.rooms.pop(room_code, None)
                if room.timer_task:
                    room.timer_task.cancel()
                await room.close_all_connections()
                logger.info("Room %s deleted (organizer did not reconnect within %ds)", room_code, delay)
        except asyncio.CancelledError:
            pass

    def create_room(self, room_code: str, game_data: dict, time_limit: int = 15,
                    organizer_token: str = "", content_id: str = "",
                    game_type: str = "quiz") -> Room:
        room = Room(room_code, game_data, time_limit, organizer_token=organizer_token,
                    content_id=content_id, game_type=game_type)
        self.rooms[room_code] = room
        self.start_cleanup_loop()
        return room

    async def connect(self, websocket: WebSocket, room_code: str, client_id: str,
                      is_organizer: bool = False, is_spectator: bool = False,
                      token: str = ""):
        # Validate WebSocket origin
        origin = websocket.headers.get("origin", "")
        if self.allowed_origins and origin not in self.allowed_origins:
            logger.warning("Rejected WebSocket from unauthorized origin: %s", origin)
            await websocket.close(code=1008)
            return

        await websocket.accept()
        if room_code not in self.rooms:
            await websocket.send_json({"type": "ERROR", "message": "Room not found"})
            await websocket.close()
            return

        room = self.rooms[room_code]

        # Verify organizer token
        if is_organizer:
            if not token or not hmac.compare_digest(token, room.organizer_token):
                await websocket.send_json({"type": "ERROR", "message": "Invalid organizer token"})
                await websocket.close()
                return

        room.touch()

        if is_spectator:
            room.spectators[client_id] = websocket
            try:
                # Send current state sync to spectator
                sync: dict = {
                    "type": "SPECTATOR_SYNC",
                    "room_code": room_code,
                    "state": room.state,
                    "game_type": room.game_type,
                    "player_count": len(room.players),
                    "players": [{"nickname": p["nickname"], "avatar": p.get("avatar", "")} for p in room.players.values()],
                    "question_number": room.current_question_index + 1,
                    "total_questions": room.total_rounds(),
                    "leaderboard": self.get_leaderboard(room),
                    "team_leaderboard": self.get_team_leaderboard(room),
                }
                # Include round data if game is in progress
                if room.state == "QUESTION" and room.current_round_data() is not None:
                    round_data = room.current_round_data()
                    if room.game_type == "wmlt":
                        sync["statement"] = round_data
                        sync["vote_count"] = len(room.votes)
                    else:
                        sync["question"] = {k: v for k, v in round_data.items() if k != "answer_index"}
                    sync["time_limit"] = room.time_limit
                    elapsed = time.time() - room.question_start_time
                    sync["time_remaining"] = max(0, room.time_limit - int(elapsed))
                    sync["is_bonus"] = room.current_question_index in room.bonus_questions
                await websocket.send_json(sync)
                while True:
                    try:
                        await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
                    except asyncio.TimeoutError:
                        # No message in 60s — ping to check liveness
                        try:
                            await websocket.send_json({"type": "PING"})
                        except Exception:
                            break  # connection is dead
            except (WebSocketDisconnect, Exception):
                pass
            finally:
                room._remove_connection(client_id)
            return

        room.connections[client_id] = websocket

        if is_organizer:
            # Cancel pending room cleanup if organizer is reconnecting
            was_disconnected = room.organizer is None
            if room._organizer_cleanup_task:
                room._organizer_cleanup_task.cancel()
                room._organizer_cleanup_task = None
                logger.info("Organizer reconnected to room %s, cleanup cancelled", room_code)
            # Close and clean up stale organizer connection if a different client_id
            if room.organizer_id and room.organizer_id != client_id:
                old_org_ws = room.connections.pop(room.organizer_id, None)
                if old_org_ws:
                    try:
                        await old_org_ws.close()
                    except Exception:
                        pass
            room.organizer = websocket
            room.organizer_id = client_id
            # Notify players and spectators that host is back (only on actual reconnect, not first connect)
            if was_disconnected and (room.current_question_index >= 0 or len(room.players) > 0):
                await room.broadcast({"type": "HOST_RECONNECTED"})
            # Detect reconnection: room already has players or game has progressed
            if room.current_question_index >= 0 or len(room.players) > 0:
                await self._send_organizer_sync(room)
            else:
                await websocket.send_json({"type": "ROOM_CREATED", "room_code": room_code})
        else:
            # Don't send JOINED_ROOM yet — wait until JOIN validation succeeds
            # to avoid the client entering LOBBY before nickname is accepted
            pass

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
                # Revoke organizer privileges if this socket was replaced by a newer organizer
                effective_organizer = is_organizer and client_id == room.organizer_id
                await self.handle_message(room, client_id, message, effective_organizer)
        except WebSocketDisconnect:
            logger.info("Client %s disconnected from room %s", client_id, room_code)
        except Exception:
            logger.exception("WebSocket error for client %s in room %s", client_id, room_code)
        finally:
            room._remove_connection(client_id)
            if room._organizer_just_disconnected:
                room._organizer_just_disconnected = False
                # Re-check: organizer may have already reconnected via a new socket
                if room.organizer is None:
                    await room.broadcast({"type": "ORGANIZER_DISCONNECTED"})
                    # Start grace period — delete room if organizer doesn't reconnect
                    room._organizer_cleanup_task = asyncio.create_task(
                        self._delayed_room_cleanup(room_code, delay=5)
                    )
            if room._player_event:
                event_type, nickname = room._player_event
                room._player_event = None
                msg_type = "PLAYER_LEFT" if event_type == "left" else "PLAYER_DISCONNECTED"
                await room.broadcast({
                    "type": msg_type,
                    "nickname": nickname,
                    "player_count": len(room.players),
                    "players": [{"nickname": p["nickname"], "avatar": p.get("avatar", "")} for p in room.players.values()],
                })
                # Re-evaluate all_answered: if remaining players have all answered,
                # end the question instead of waiting for the full timer
                if room.state == "QUESTION" and len(room.players) > 0:
                    if all(cid in room.answered_players for cid in room.players):
                        await self.end_question(room)

    async def _send_organizer_sync(self, room: Room):
        """Send full game state to a reconnecting organizer."""
        sync = {
            "type": "ORGANIZER_RECONNECTED",
            "room_code": room.room_code,
            "state": room.state,
            "game_type": room.game_type,
            "player_count": len(room.players),
            "players": [
                {"nickname": p["nickname"], "avatar": p.get("avatar", "")}
                for p in room.players.values()
            ],
            "question_number": room.current_question_index + 1,
            "total_questions": room.total_rounds(),
            "leaderboard": self.get_leaderboard(room),
            "team_leaderboard": self.get_team_leaderboard(room),
            "time_limit": room.time_limit,
            "quiz": room.quiz,
            "locked": room.locked,
        }

        if room.state == "QUESTION":
            round_data = room.current_round_data()
            if room.game_type == "wmlt":
                sync["statement"] = round_data
                sync["vote_count"] = len(room.votes)
                sync["voted_count"] = len(room.votes)
            else:
                sync["question"] = round_data
                sync["answered_count"] = len(room.answered_players)
            sync["is_bonus"] = room.current_question_index in room.bonus_questions
            elapsed = time.time() - room.question_start_time
            sync["time_remaining"] = max(0, room.time_limit - int(elapsed))

        if room.organizer:
            await room.organizer.send_json(sync)
        logger.info("Organizer reconnected to room %s (state: %s)", room.room_code, room.state)

    async def handle_message(self, room: Room, client_id: str, message: dict, is_organizer: bool):
        if not isinstance(message, dict):
            return
        msg_type = message.get("type")
        if not isinstance(msg_type, str):
            return

        if is_organizer:
            if msg_type == "START_GAME":
                if room.state != "LOBBY":
                    return
                # WMLT requires minimum players
                if room.game_type == "wmlt":
                    player_count = len([p for p in room.players.values() if p.get("nickname")])
                    if player_count < config.MIN_WMLT_PLAYERS:
                        await self._send_to_client(room, client_id, {
                            "type": "ERROR",
                            "message": f"Most Likely To needs at least {config.MIN_WMLT_PLAYERS} players to start",
                        })
                        return
                room.locked = True
                if room.game_type != "wmlt":
                    self._select_bonus_questions(room)
                room.state = "INTRO"
                await room.broadcast({"type": "GAME_STARTING"})

            elif msg_type == "NEXT_QUESTION":
                if room.state == "QUESTION":
                    await self.end_question(room)
                elif room.state in ("INTRO", "LEADERBOARD"):
                    await self.start_question(room)

            elif msg_type == "SET_TIME_LIMIT":
                if room.state in ("LOBBY", "LEADERBOARD", "PODIUM"):
                    new_limit = message.get("time_limit", 15)
                    if isinstance(new_limit, int) and 5 <= new_limit <= 60:
                        room.time_limit = new_limit

            elif msg_type == "SET_SHOW_VOTES":
                if room.game_type == "wmlt":
                    val = message.get("show_votes")
                    if isinstance(val, bool):
                        room.show_votes = val

            elif msg_type == "END_QUIZ":
                if room.state in ("QUESTION", "LEADERBOARD"):
                    if room.timer_task:
                        room.timer_task.cancel()
                        room.timer_task = None
                    room.state = "PODIUM"
                    leaderboard = self.get_leaderboard(room)
                    team_leaderboard = self.get_team_leaderboard(room)
                    podium_msg = {
                        "type": "PODIUM",
                        "leaderboard": leaderboard,
                        "team_leaderboard": team_leaderboard,
                    }
                    if room.game_type == "wmlt":
                        podium_msg["superlatives"] = self._calculate_wmlt_superlatives(room)
                    await room.broadcast(podium_msg)
                    try:
                        from main import game_history
                        game_history.append(self.get_game_summary(room))
                        if len(game_history) > config.MAX_GAME_HISTORY:
                            del game_history[:len(game_history) - config.MAX_GAME_HISTORY]
                    except Exception:
                        logger.warning("Could not save game history for room %s", room.room_code)

            elif msg_type == "RESET_ROOM":
                if room.state != "PODIUM":
                    return
                new_content_id = message.get("content_id", "")
                raw_game_type = message.get("game_type", room.game_type)
                new_game_type = raw_game_type if raw_game_type in ("quiz", "wmlt") else room.game_type
                raw_time_limit = message.get("time_limit", room.time_limit)

                # Validate time_limit
                try:
                    new_time_limit = int(raw_time_limit)
                except (TypeError, ValueError):
                    new_time_limit = room.time_limit
                new_time_limit = max(5, min(60, new_time_limit))

                # Resolve game data from content store by ID
                from main import quizzes, mlt_scenarios
                if new_game_type == "wmlt":
                    new_game_data = mlt_scenarios.get(new_content_id)
                else:
                    new_game_data = quizzes.get(new_content_id)

                if not new_game_data:
                    logger.warning("RESET_ROOM rejected: content_id %s not found for room %s",
                                   new_content_id, room.room_code)
                    ws = room.connections.get(client_id)
                    if ws:
                        await ws.send_json({"type": "ERROR", "message": "Game content not found. Please generate a new game."})
                    return

                room.reset_for_new_game(new_game_data, new_time_limit,
                                        game_type=new_game_type,
                                        content_id=new_content_id)
                logger.info("Room %s reset for new game (type=%s, content=%s)",
                            room.room_code, new_game_type, new_content_id)
                await room.broadcast({
                    "type": "ROOM_RESET",
                    "room_code": room.room_code,
                    "game_type": new_game_type,
                    "player_count": len(room.players),
                    "players": [{"nickname": p["nickname"], "avatar": p.get("avatar", "")} for p in room.players.values()],
                })

            elif msg_type == "TOGGLE_LOCK":
                if room.state == "LOBBY":
                    room.locked = not room.locked
                    await room.broadcast({"type": "ROOM_LOCK_STATUS", "locked": room.locked})

        else:
            if msg_type == "JOIN":
                raw_nick = message.get("nickname", "")
                raw_team = message.get("team", "")
                nickname = (raw_nick if isinstance(raw_nick, str) else "").strip()
                team = (raw_team if isinstance(raw_team, str) else "").strip() or None
                # Sanitize: strip HTML tags and control characters
                nickname = re.sub(r'<[^>]+>', '', nickname)
                nickname = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', nickname).strip()
                if not nickname or len(nickname) > config.MAX_NICKNAME_LENGTH:
                    ws = room.connections.get(client_id)
                    if ws:
                        await ws.send_json({
                            "type": "ERROR",
                            "message": f"Nickname must be 1-{config.MAX_NICKNAME_LENGTH} characters"
                        })
                        await ws.close()
                    return

                # Sanitize team name
                if team:
                    team = re.sub(r'<[^>]+>', '', team)
                    team = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', team).strip()
                    if len(team) > config.MAX_TEAM_NAME_LENGTH:
                        team = team[:config.MAX_TEAM_NAME_LENGTH]
                    if not team:
                        team = None

                # Sanitize and limit avatar length
                avatar = message.get("avatar", "")
                if not isinstance(avatar, str):
                    avatar = ""
                avatar = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', avatar)[:config.MAX_AVATAR_LENGTH]

                # Check for reconnection (disconnected mid-game)
                if nickname in room.disconnected_players:
                    # Verify session token to prevent nickname hijacking
                    provided_token = message.get("session_token", "")
                    expected_token = room.player_tokens.get(nickname, "")
                    if expected_token and not hmac.compare_digest(str(provided_token), expected_token):
                        ws = room.connections.get(client_id)
                        if ws:
                            await ws.send_json({"type": "ERROR", "message": "Nickname is taken"})
                            await ws.close()
                        return
                    saved = room.disconnected_players.pop(nickname)
                    room.players[client_id] = {
                        "nickname": nickname,
                        "score": saved["score"],
                        "prev_rank": saved["prev_rank"],
                        "streak": saved.get("streak", 0),
                        "avatar": saved.get("avatar", avatar),
                    }
                    # Transfer answered status to new client_id
                    old_cid = saved.get("_answered_client_id")
                    if old_cid and old_cid in room.answered_players:
                        room.answered_players.discard(old_cid)
                        room.answered_players.add(client_id)
                    logger.info("Player '%s' reconnected to room %s with score %d", nickname, room.room_code, saved["score"])
                    ws = room.connections.get(client_id)
                    if ws:
                        state_info: dict = {
                            "type": "RECONNECTED",
                            "score": saved["score"],
                            "state": room.state,
                            "game_type": room.game_type,
                            "question_number": room.current_question_index + 1,
                            "total_questions": room.total_rounds(),
                            "avatar": saved.get("avatar", avatar),
                        }
                        if room.state == "QUESTION":
                            round_data = room.current_round_data()
                            if room.game_type == "wmlt":
                                state_info["statement"] = round_data
                                state_info["players"] = [
                                    {"nickname": p["nickname"], "avatar": p.get("avatar", "")}
                                    for p in room.players.values()
                                ]
                            else:
                                player_question = {k: v for k, v in round_data.items() if k != "answer_index"}
                                state_info["question"] = player_question
                                # Include fifty-fifty state if it was used
                                pups = room.power_ups.get(nickname, {})
                                if "fifty_fifty_remove_indices" in pups:
                                    state_info["remove_indices"] = pups["fifty_fifty_remove_indices"]
                            state_info["time_limit"] = room.time_limit
                            elapsed = time.time() - room.question_start_time
                            state_info["time_remaining"] = max(0, room.time_limit - int(elapsed))
                            state_info["is_bonus"] = room.current_question_index in room.bonus_questions
                        state_info["session_token"] = room.player_tokens.get(nickname, "")
                        state_info["power_ups"] = {
                            "double_points": room.power_ups.get(nickname, {}).get("double_points", False),
                            "fifty_fifty": room.power_ups.get(nickname, {}).get("fifty_fifty", False),
                        }
                        await ws.send_json(state_info)
                    await room.broadcast({
                        "type": "PLAYER_RECONNECTED",
                        "nickname": nickname,
                        "player_count": len(room.players),
                        "players": [{"nickname": p["nickname"], "avatar": p.get("avatar", "")} for p in room.players.values()],
                    })
                    return

                # Check for duplicate nickname among active players (case-insensitive)
                existing_id = None
                for pid, pdata in room.players.items():
                    if pdata["nickname"].lower() == nickname.lower():
                        existing_id = pid
                        break

                if existing_id:
                    # Verify session token to prevent nickname hijacking
                    existing_nickname = room.players[existing_id]["nickname"]
                    provided_token = message.get("session_token", "")
                    expected_token = room.player_tokens.get(existing_nickname, "")
                    if expected_token and not hmac.compare_digest(str(provided_token), expected_token):
                        ws = room.connections.get(client_id)
                        if ws:
                            await ws.send_json({"type": "ERROR", "message": "Nickname is taken"})
                            await ws.close()
                        return
                    # Kick the old connection and let the new one take over
                    old_ws = room.connections.pop(existing_id, None)
                    if old_ws:
                        try:
                            await old_ws.send_json({"type": "KICKED", "message": "You joined from another device"})
                            await old_ws.close()
                        except Exception:
                            pass
                    # Transfer player data and answered status to new client_id
                    player_data = room.players.pop(existing_id)
                    room.players[client_id] = player_data
                    if existing_id in room.answered_players:
                        room.answered_players.discard(existing_id)
                        room.answered_players.add(client_id)
                    logger.info("Player '%s' rejoined room %s (replaced old connection)", nickname, room.room_code)

                    ws = room.connections.get(client_id)
                    if ws:
                        state_info = {
                            "type": "RECONNECTED",
                            "score": player_data["score"],
                            "state": room.state,
                            "game_type": room.game_type,
                            "question_number": room.current_question_index + 1,
                            "total_questions": room.total_rounds(),
                            "avatar": player_data.get("avatar", ""),
                        }
                        if room.state == "QUESTION":
                            round_data = room.current_round_data()
                            if room.game_type == "wmlt":
                                state_info["statement"] = round_data
                                state_info["players"] = [
                                    {"nickname": p["nickname"], "avatar": p.get("avatar", "")}
                                    for p in room.players.values()
                                ]
                            else:
                                player_question = {k: v for k, v in round_data.items() if k != "answer_index"}
                                state_info["question"] = player_question
                                # Include fifty-fifty state if it was used
                                pups = room.power_ups.get(nickname, {})
                                if "fifty_fifty_remove_indices" in pups:
                                    state_info["remove_indices"] = pups["fifty_fifty_remove_indices"]
                            state_info["time_limit"] = room.time_limit
                            elapsed = time.time() - room.question_start_time
                            state_info["time_remaining"] = max(0, room.time_limit - int(elapsed))
                            state_info["is_bonus"] = room.current_question_index in room.bonus_questions
                        state_info["session_token"] = room.player_tokens.get(nickname, "")
                        state_info["power_ups"] = {
                            "double_points": room.power_ups.get(nickname, {}).get("double_points", False),
                            "fifty_fifty": room.power_ups.get(nickname, {}).get("fifty_fifty", False),
                        }
                        await ws.send_json(state_info)
                    return

                # Block new players if room is locked
                if room.locked:
                    conn = room.connections.get(client_id)
                    if conn:
                        await conn.send_json({"type": "ERROR", "message": "Room is locked by the host"})
                        await conn.close()
                    return

                # Block new players if game is in progress
                if room.state != "LOBBY":
                    conn = room.connections.get(client_id)
                    if conn:
                        await conn.send_json({
                            "type": "GAME_IN_PROGRESS",
                            "question_number": room.current_question_index + 1,
                            "total_questions": room.total_rounds(),
                        })
                        await conn.close()
                    return

                if len(room.players) >= config.MAX_PLAYERS_PER_ROOM:
                    conn = room.connections.get(client_id)
                    if conn:
                        await conn.send_json({"type": "ERROR", "message": "Room is full"})
                        await conn.close()
                    return

                room.players[client_id] = {"nickname": nickname, "score": 0, "prev_rank": 0, "streak": 0, "avatar": avatar}
                # Assign team if provided
                if team:
                    room.teams[nickname] = team
                # Initialize power-ups
                room.power_ups[nickname] = {"double_points": True, "fifty_fifty": True}
                # Generate session token for nickname ownership
                player_session_token = secrets.token_urlsafe(16)
                room.player_tokens[nickname] = player_session_token
                # Confirm join to the player (after validation succeeded)
                ws = room.connections.get(client_id)
                if ws:
                    await ws.send_json({"type": "JOINED_ROOM", "room_code": room.room_code, "session_token": player_session_token})
                await room.broadcast({
                    "type": "PLAYER_JOINED",
                    "nickname": nickname,
                    "player_count": len(room.players),
                    "players": [{"nickname": p["nickname"], "avatar": p.get("avatar", "")} for p in room.players.values()]
                })

            elif msg_type == "VOTE" and room.game_type == "wmlt":
                if client_id not in room.players:
                    return
                if room.state != "QUESTION":
                    return
                raw_vote = message.get("voted_for", "")
                voted_for = (raw_vote if isinstance(raw_vote, str) else "").strip()
                nickname = room.players[client_id]["nickname"]
                # Validate voted_for is a player in the room (including disconnected)
                valid_nicknames = set(room.player_nicknames()) | set(room.disconnected_players.keys())
                if voted_for not in valid_nicknames:
                    ws = room.connections.get(client_id)
                    if ws:
                        await ws.send_json({"type": "ERROR", "message": "Invalid vote target"})
                    return

                async with room.lock:
                    if room.state != "QUESTION" or nickname in room.votes:
                        return  # State changed or already voted
                    room.votes[nickname] = voted_for
                    room.answered_players.add(client_id)
                    all_voted = len(room.votes) >= len(room.players)

                ws = room.connections.get(client_id)
                if ws:
                    await ws.send_json({
                        "type": "VOTE_CONFIRMED",
                        "voted_for": voted_for,
                    })

                # Notify organizer about vote progress
                await room.send_to_organizer({
                    "type": "VOTE_COUNT",
                    "voted": len(room.votes),
                    "total": len(room.players),
                })

                if all_voted:
                    await self.end_question(room)

            elif msg_type == "ANSWER":
                if room.game_type == "wmlt":
                    return  # WMLT uses VOTE, not ANSWER
                if client_id not in room.players:
                    return
                answer_index = message.get("answer_index")
                # Bounds check to prevent IndexError
                question = room.current_round_data()
                if not question:
                    return
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
                if room.state != "QUESTION" or room.game_type == "wmlt":
                    return  # Power-ups are quiz-only
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
                        if room.game_type == "wmlt":
                            return  # 50/50 not applicable to WMLT
                        pups["fifty_fifty"] = False
                        question = room.current_round_data()
                        if not question:
                            return
                        correct_idx = question["answer_index"]
                        wrong_indices = [i for i in range(len(question["options"])) if i != correct_idx]
                        import random
                        remove = random.sample(wrong_indices, min(2, len(wrong_indices)))
                        pups["fifty_fifty_remove_indices"] = remove
                        await ws.send_json({
                            "type": "POWER_UP_ACTIVATED",
                            "power_up": "fifty_fifty",
                            "remove_indices": remove,
                        })

    def get_team_leaderboard(self, room: Room) -> List[dict]:
        """Aggregate player scores by team. Solo players use their nickname."""
        team_scores: Dict[str, list] = {}
        for player in self._all_players_for_leaderboard(room):
            team = room.teams.get(player["nickname"]) or player["nickname"]
            team_scores.setdefault(team, []).append(player["score"])
        result = []
        for team_name, scores in team_scores.items():
            result.append({
                "team": team_name,
                "score": int(sum(scores) / len(scores)) if scores else 0,  # average
                "members": len(scores),
            })
        return sorted(result, key=lambda x: x["score"], reverse=True)

    def get_game_summary(self, room: Room) -> dict:
        """Build a game summary for history storage."""
        all_player_count = len(room.players) + len(room.disconnected_players)
        return {
            "room_code": room.room_code,
            "game_type": room.game_type,
            "game_title": room.game_title(),
            "total_questions": room.total_rounds(),
            "player_count": all_player_count,
            "leaderboard": self.get_leaderboard(room),
            "team_leaderboard": self.get_team_leaderboard(room),
            "answer_log": room.answer_log,
            "completed_at": time.time(),
        }

    def _select_bonus_questions(self, room: Room):
        """Pre-select which rounds will be bonus rounds (2x points)."""
        import random
        total = room.total_rounds()
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

        if room.current_question_index >= room.total_rounds():
            room.state = "PODIUM"
            leaderboard = self.get_leaderboard(room)
            team_leaderboard = self.get_team_leaderboard(room)
            podium_msg: dict = {
                "type": "PODIUM",
                "leaderboard": leaderboard,
                "team_leaderboard": team_leaderboard,
            }
            if room.game_type == "wmlt":
                podium_msg["superlatives"] = self._calculate_wmlt_superlatives(room)
            await room.broadcast(podium_msg)
            # Save game history — import here to avoid circular dependency
            try:
                from main import game_history
                game_history.append(self.get_game_summary(room))
                if len(game_history) > config.MAX_GAME_HISTORY:
                    del game_history[:len(game_history) - config.MAX_GAME_HISTORY]
                logger.info("Game history saved for room %s", room.room_code)
            except Exception:
                logger.warning("Could not save game history for room %s", room.room_code)
            return

        # Store previous leaderboard for animation
        room.previous_leaderboard = self.get_leaderboard(room)

        room.answered_players = set()
        room.votes = {}  # Clear WMLT votes for new round

        # Clear per-question power-up state from previous question
        for pups in room.power_ups.values():
            pups.pop("fifty_fifty_remove_indices", None)
            pups.pop("double_points_active", None)

        is_bonus = room.current_question_index in room.bonus_questions

        # Set state to QUESTION before broadcast so answers/votes are accepted immediately
        room.state = "QUESTION"

        if room.game_type == "wmlt":
            statement = room.current_round_data()
            await room.broadcast({
                "type": "QUESTION",
                "statement": statement,
                "question_number": room.current_question_index + 1,
                "total_questions": room.total_rounds(),
                "time_limit": room.time_limit,
                "is_bonus": is_bonus,
                "game_type": "wmlt",
                "players": [
                    {"nickname": p["nickname"], "avatar": p.get("avatar", "")}
                    for p in room.players.values()
                ],
            })
        else:
            question = room.current_round_data()
            if not question:
                return
            player_question = {k: v for k, v in question.items() if k != "answer_index"}
            await room.broadcast({
                "type": "QUESTION",
                "question": player_question,
                "question_number": room.current_question_index + 1,
                "total_questions": room.total_rounds(),
                "time_limit": room.time_limit,
                "is_bonus": is_bonus,
            })

        # Delay timer start for bonus rounds so the splash animation plays first
        if is_bonus:
            await asyncio.sleep(2)

        # If all players answered during the bonus splash, end_question was
        # already called — don't start the timer.
        if room.state != "QUESTION":
            return

        room.question_start_time = time.time()
        room.timer_task = asyncio.create_task(self.question_timer(room))

    async def question_timer(self, room: Room):
        """Timer that ends the question after time_limit seconds."""
        try:
            for remaining in range(room.time_limit, -1, -1):
                await room.broadcast({"type": "TIMER", "remaining": remaining})
                if remaining > 0:
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

        if room.game_type == "wmlt":
            await self._end_wmlt_round(room)
            return

        # Reset streak for players who didn't answer
        for cid, player in room.players.items():
            if cid not in room.answered_players:
                player["streak"] = 0

        question = room.current_round_data()
        if not question:
            return
        current_leaderboard = self.get_leaderboard_with_changes(room)
        is_final = room.current_question_index >= room.total_rounds() - 1

        await room.broadcast({
            "type": "QUESTION_OVER",
            "answer": question["answer_index"],
            "leaderboard": current_leaderboard,
            "previous_leaderboard": room.previous_leaderboard,
            "is_final": is_final
        })

    async def _end_wmlt_round(self, room: Room):
        """Handle end-of-round scoring and results for Who's Most Likely To."""
        statement = room.current_round_data()

        # Tally votes: voted_for_nickname -> list of voter nicknames
        vote_tally: Dict[str, List[str]] = {}
        for voter, voted_for in room.votes.items():
            vote_tally.setdefault(voted_for, []).append(voter)

        # Find winner(s) — all players tied for most votes are winners
        winners: List[str] = []
        winner_votes = 0
        if vote_tally:
            max_votes = max(len(voters) for voters in vote_tally.values())
            winners = sorted(n for n, voters in vote_tally.items() if len(voters) == max_votes)
            winner_votes = max_votes

        is_bonus = room.current_question_index in room.bonus_questions
        is_unanimous = winner_votes == len(room.votes) and winner_votes > 1 and len(winners) == 1

        # Score players
        winners_set = set(winners)
        for cid, player in room.players.items():
            nickname = player["nickname"]
            voted_for = room.votes.get(nickname)

            if voted_for is None:
                # Didn't vote — break streak
                player["streak"] = 0
                continue

            if voted_for in winners_set:
                # Voted for a winner
                base_points = 500
                if is_bonus:
                    base_points *= 2
                if is_unanimous:
                    base_points += 200

                # Streak bonus
                player["streak"] = player.get("streak", 0) + 1
                streak = player["streak"]
                multiplier = 1.0
                for threshold, mult in sorted(config.STREAK_THRESHOLDS.items()):
                    if streak >= threshold:
                        multiplier = mult
                points = int(base_points * multiplier)
                player["score"] += points
            else:
                # Voted for someone else — break streak
                player["streak"] = 0

        # Bonus for each winner (most-voted person) if they're a player
        for cid, player in room.players.items():
            if player["nickname"] in winners_set:
                player["score"] += 100

        # Build round podium: all voted-for players sorted by vote count
        player_avatars = {p["nickname"]: p.get("avatar", "") for p in room.players.values()}
        round_podium = []
        for nickname, voters in sorted(vote_tally.items(), key=lambda x: len(x[1]), reverse=True):
            round_podium.append({
                "nickname": nickname,
                "avatar": player_avatars.get(nickname, ""),
                "vote_count": len(voters),
                "voters": voters if room.show_votes else [],
            })

        # Store round data for superlatives
        room.mlt_round_history.append({
            "votes": dict(room.votes),  # voter -> target
            "winner": winners[0] if winners else None,
            "winners": winners,
            "winner_votes": winner_votes,
            "round_podium": round_podium,
        })

        # Log for game history
        room.answer_log.append({
            "question_index": room.current_question_index,
            "game_type": "wmlt",
            "statement": statement.get("text", "") if statement else "",
            "votes": dict(room.votes),
            "winners": winners,
            "winner_votes": winner_votes,
            "unanimous": is_unanimous,
        })

        current_leaderboard = self.get_leaderboard_with_changes(room)
        is_final = room.current_question_index >= room.total_rounds() - 1

        # winner = first for backward compat, winners = full list for tie display
        await room.broadcast({
            "type": "QUESTION_OVER",
            "game_type": "wmlt",
            "statement": statement.get("text", "") if statement else "",
            "votes": vote_tally if room.show_votes else {},
            "round_podium": round_podium,
            "winner": winners[0] if winners else None,
            "winners": winners,
            "winner_votes": winner_votes,
            "unanimous": is_unanimous,
            "show_votes": room.show_votes,
            "leaderboard": current_leaderboard,
            "previous_leaderboard": room.previous_leaderboard,
            "is_final": is_final,
            "is_bonus": is_bonus,
        })

    def _calculate_wmlt_superlatives(self, room: Room) -> List[dict]:
        """Calculate fun end-of-game superlatives for WMLT."""
        from collections import Counter
        superlatives = []
        if not room.mlt_round_history:
            return superlatives

        player_avatars = {p["nickname"]: p.get("avatar", "") for p in room.players.values()}
        for nickname, data in room.disconnected_players.items():
            player_avatars[nickname] = data.get("avatar", "")

        # "Most Likely To Everything" — most total votes received
        total_votes_received: Counter = Counter()
        for rnd in room.mlt_round_history:
            for voter, target in rnd.get("votes", {}).items():
                total_votes_received[target] += 1
        if total_votes_received and total_votes_received.most_common(1):
            top = total_votes_received.most_common(1)[0]
            superlatives.append({
                "title": "Most Likely To Everything",
                "icon": "🏆",
                "winner": top[0],
                "avatar": player_avatars.get(top[0], ""),
                "detail": f"Received {top[1]} total votes",
            })

        # "Narcissist Award" — most self-votes
        self_votes: Counter = Counter()
        for rnd in room.mlt_round_history:
            for voter, target in rnd.get("votes", {}).items():
                if voter == target:
                    self_votes[voter] += 1
        if self_votes and self_votes.most_common(1):
            top = self_votes.most_common(1)[0]
            if top[1] > 0:
                superlatives.append({
                    "title": "Narcissist Award",
                    "icon": "🪞",
                    "winner": top[0],
                    "avatar": player_avatars.get(top[0], ""),
                    "detail": f"Voted for themselves {top[1]} time{'s' if top[1] != 1 else ''}",
                })

        # "Mind Reader" — voted with the majority most often
        majority_counts: Counter = Counter()
        for rnd in room.mlt_round_history:
            round_winners = set(rnd.get("winners", []))
            if not round_winners and rnd.get("winner"):
                round_winners = {rnd["winner"]}
            if round_winners:
                for voter, target in rnd.get("votes", {}).items():
                    if target in round_winners:
                        majority_counts[voter] += 1
        if majority_counts and majority_counts.most_common(1):
            top = majority_counts.most_common(1)[0]
            if top[1] > 0:
                superlatives.append({
                    "title": "Mind Reader",
                    "icon": "🔮",
                    "winner": top[0],
                    "avatar": player_avatars.get(top[0], ""),
                    "detail": f"Voted with the majority {top[1]} time{'s' if top[1] != 1 else ''}",
                })

        # "Most Controversial" — involved in closest vote splits
        controversial: Counter = Counter()
        for rnd in room.mlt_round_history:
            podium = rnd.get("round_podium", [])
            if len(podium) >= 2:
                top_two = sorted(podium, key=lambda x: x["vote_count"], reverse=True)[:2]
                if top_two[0]["vote_count"] - top_two[1]["vote_count"] <= 1:
                    controversial[top_two[0]["nickname"]] += 1
                    controversial[top_two[1]["nickname"]] += 1
        if controversial and controversial.most_common(1):
            top = controversial.most_common(1)[0]
            if top[1] > 0:
                superlatives.append({
                    "title": "Most Controversial",
                    "icon": "🔥",
                    "winner": top[0],
                    "avatar": player_avatars.get(top[0], ""),
                    "detail": f"Part of {top[1]} close vote{'s' if top[1] != 1 else ''}",
                })

        return superlatives

    def _all_players_for_leaderboard(self, room: Room) -> List[dict]:
        """Combine active and disconnected players for leaderboard inclusion."""
        all_players = list(room.players.values())
        for nickname, data in room.disconnected_players.items():
            all_players.append({
                "nickname": nickname,
                "score": data["score"],
                "avatar": data.get("avatar", ""),
                "prev_rank": data.get("prev_rank", 0),
                "streak": data.get("streak", 0),
            })
        return all_players

    def get_leaderboard(self, room: Room) -> List[dict]:
        sorted_players = sorted(
            self._all_players_for_leaderboard(room),
            key=lambda x: x["score"],
            reverse=True
        )
        return [{"nickname": p["nickname"], "score": p["score"], "avatar": p.get("avatar", "")} for p in sorted_players]

    def get_leaderboard_with_changes(self, room: Room) -> List[dict]:
        prev_rankings = {p["nickname"]: i for i, p in enumerate(room.previous_leaderboard)}

        sorted_players = sorted(
            self._all_players_for_leaderboard(room),
            key=lambda x: x["score"],
            reverse=True
        )

        result = []
        for i, player in enumerate(sorted_players):
            prev_rank = prev_rankings.get(player["nickname"], len(prev_rankings) + 1)
            result.append({
                "nickname": player["nickname"],
                "score": player["score"],
                "avatar": player.get("avatar", ""),
                "prev_rank": prev_rank,
                "rank_change": prev_rank - i  # positive = moved up
            })

        return result


socket_manager = SocketManager()
