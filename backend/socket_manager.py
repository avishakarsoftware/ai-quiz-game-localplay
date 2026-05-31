from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Optional
from datetime import datetime, timezone
import copy
import json
import hmac
import hashlib
import secrets
import time
import asyncio
import logging
import re
import uuid
import httpx

import config
import tokens as token_module
from bingo_engine import (
    BINGO_PATTERN_ORDER,
    create_bingo_call_deck,
    generate_bingo_card,
    validate_bingo_claim,
)
from housie_engine import (
    PATTERN_ORDER,
    create_call_deck,
    generate_ticket,
    validate_claim,
)

logger = logging.getLogger(__name__)


class Room:
    def __init__(self, room_code: str, game_data: dict, time_limit: int = 15,
                 organizer_token: str = "", content_id: str = "",
                 game_type: str = "quiz", billing_mode: str = "localplay_sparks"):
        self.room_code = room_code
        self.quiz = game_data  # generic game content (quiz or WMLT)
        self.content_id = content_id
        self.game_type = game_type  # "quiz", "wmlt", "drawing", "housie", or "bingo"
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
        self.wallet_id: Optional[str] = None  # organizer's wallet for spark charges
        self.billing_mode = billing_mode
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
        # DrawingGame state
        self.drawer_order: List[str] = []
        self.current_drawer: str = ""
        self.correct_guessers: set = set()
        self.drawing_ops: List[dict] = []
        self.guess_log: List[dict] = []
        self.draw_op_timestamps: Dict[str, list] = {}
        # Housie state
        self.housie_deck: List[dict] = []
        self.housie_called: List[dict] = []
        self.housie_tickets: Dict[str, dict] = {}  # nickname -> ticket
        self.housie_winners: List[dict] = []
        self.housie_claimed_patterns: set = set()
        self.housie_claim_log: List[dict] = []
        self.housie_play_mode: str = str(game_data.get("play_mode") or "beginner").lower()
        self.housie_caller_mode: str = str(game_data.get("caller_mode") or "manual").lower()
        self.housie_auto_status: str = "stopped"
        self.housie_auto_interval_seconds: int = int(game_data.get("auto_interval_seconds") or 8)
        self.housie_auto_pause_on_claim: bool = bool(game_data.get("auto_pause_on_claim", True))
        self.housie_next_auto_call_at: Optional[str] = None
        self.housie_auto_task: Optional[asyncio.Task] = None

    def reset_for_new_game(self, new_game_data: dict, new_time_limit: int,
                           game_type: Optional[str] = None,
                           content_id: Optional[str] = None):
        """Reset room for a new game round, keeping players connected."""
        self.quiz = copy.deepcopy(new_game_data)
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
        self.mlt_round_history.clear()
        self.msg_timestamps.clear()
        self.drawer_order = []
        self.current_drawer = ""
        self.correct_guessers = set()
        self.drawing_ops = []
        self.guess_log = []
        self.draw_op_timestamps.clear()
        self.housie_deck = []
        self.housie_called = []
        self.housie_tickets = {}
        self.housie_winners = []
        self.housie_claimed_patterns = set()
        self.housie_claim_log = []
        self.housie_play_mode = str(new_game_data.get("play_mode") or "beginner").lower()
        self.housie_caller_mode = str(new_game_data.get("caller_mode") or "manual").lower()
        self.housie_auto_status = "stopped"
        self.housie_auto_interval_seconds = int(new_game_data.get("auto_interval_seconds") or 8)
        self.housie_auto_pause_on_claim = bool(new_game_data.get("auto_pause_on_claim", True))
        self.housie_next_auto_call_at = None
        if self.housie_auto_task:
            self.housie_auto_task.cancel()
            self.housie_auto_task = None

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
        if self.game_type == "drawing":
            return len(self.quiz.get("prompts", []))
        if self.game_type in ("housie", "bingo"):
            return len(self.quiz.get("deck", [])) or 90
        return len(self.quiz.get("questions", []))

    def current_round_data(self) -> Optional[dict]:
        """Current round item (question or statement)."""
        idx = self.current_question_index
        if idx < 0 or idx >= self.total_rounds():
            return None
        if self.game_type == "wmlt":
            return self.quiz["statements"][idx]
        if self.game_type == "drawing":
            return self.quiz["prompts"][idx]
        if self.game_type in ("housie", "bingo"):
            if 0 <= idx < len(self.housie_called):
                return self.housie_called[idx]
            return None
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
            self.draw_op_timestamps.pop(client_id, None)
            return
        self.connections.pop(client_id, None)
        self.msg_timestamps.pop(client_id, None)
        self.draw_op_timestamps.pop(client_id, None)
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
        if self.housie_auto_task:
            self.housie_auto_task.cancel()
            self.housie_auto_task = None
        self.housie_auto_status = "stopped"
        self.housie_next_auto_call_at = None
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
                        self._mark_game_session_closed(room, "expired", "This game expired. Ask the host to start a new one.")
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
                self._mark_game_session_closed(room, "cancelled", "The host left this game.")
                logger.info("Room %s deleted (organizer did not reconnect within %ds)", room_code, delay)
        except asyncio.CancelledError:
            pass

    async def _send_to_client(self, room: Room, client_id: str, message: dict):
        """Send a JSON message to a specific client in the room."""
        ws = room.connections.get(client_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception:
                pass

    def create_room(self, room_code: str, game_data: dict, time_limit: int = 15,
                    organizer_token: str = "", content_id: str = "",
                    game_type: str = "quiz", billing_mode: str = "localplay_sparks") -> Room:
        room = Room(room_code, game_data, time_limit, organizer_token=organizer_token,
                    content_id=content_id, game_type=game_type, billing_mode=billing_mode)
        self.rooms[room_code] = room
        self.start_cleanup_loop()
        return room

    async def connect(self, websocket: WebSocket, room_code: str, client_id: str,
                      is_organizer: bool = False, is_spectator: bool = False):
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

        # Organizer auth: first-frame AUTH message required
        if is_organizer:
            try:
                auth_msg = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
                auth_token = auth_msg.get("token", "") if isinstance(auth_msg, dict) and auth_msg.get("type") == "AUTH" else ""
                if not auth_token or not hmac.compare_digest(auth_token, room.organizer_token):
                    await websocket.send_json({"type": "ERROR", "message": "Invalid organizer token"})
                    await websocket.close()
                    return
            except (asyncio.TimeoutError, Exception):
                await websocket.send_json({"type": "ERROR", "message": "Organizer authentication required"})
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
                    elif room.game_type == "drawing":
                        sync["drawing_prompt"] = {k: v for k, v in round_data.items() if k != "aliases"}
                        sync["drawer"] = room.current_drawer
                        sync["drawing_ops"] = room.drawing_ops[-config.MAX_DRAW_OPS_PER_SYNC:]
                        sync["correct_guessers"] = list(room.correct_guessers)
                        sync["guess_log"] = room.guess_log[-10:]
                    else:
                        sync["question"] = {k: v for k, v in round_data.items() if k != "answer_index"}
                    sync["time_limit"] = room.time_limit
                    elapsed = time.time() - room.question_start_time
                    sync["time_remaining"] = max(0, room.time_limit - int(elapsed))
                    sync["is_bonus"] = room.current_question_index in room.bonus_questions
                if room.game_type in ("housie", "bingo"):
                    sync["bingo"] = self._housie_public_state(room)
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

                try:
                    message = json.loads(data)
                except json.JSONDecodeError:
                    logger.warning("Malformed JSON from client %s: %s", client_id, data[:100])
                    await websocket.send_json({"type": "ERROR", "message": "Invalid message format"})
                    continue

                msg_type = message.get("type") if isinstance(message, dict) else None
                now = time.time()
                if room.game_type == "drawing" and msg_type == "DRAW_OP":
                    if len(data) > config.MAX_DRAW_OP_MESSAGE_SIZE:
                        await websocket.send_json({"type": "ERROR", "message": "Drawing message too large"})
                        continue
                    timestamps = room.draw_op_timestamps.setdefault(client_id, [])
                    timestamps[:] = [t for t in timestamps if now - t < 1.0]
                    if len(timestamps) >= config.DRAW_OP_RATE_LIMIT_PER_SEC:
                        await websocket.send_json({"type": "ERROR", "message": "Too many drawing messages"})
                        continue
                    timestamps.append(now)
                else:
                    # Per-client rate limiting for non-drawing messages
                    timestamps = room.msg_timestamps.setdefault(client_id, [])
                    timestamps[:] = [t for t in timestamps if now - t < 1.0]
                    if len(timestamps) >= config.WS_RATE_LIMIT_PER_SEC:
                        await websocket.send_json({"type": "ERROR", "message": "Too many messages"})
                        continue
                    timestamps.append(now)

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
                    if room.game_type in ("housie", "bingo") and room.housie_auto_status == "running":
                        await self._set_housie_auto_status(room, "paused")
                    await room.broadcast({"type": "ORGANIZER_DISCONNECTED"})
                    # Start grace period — delete room if organizer doesn't reconnect
                    room._organizer_cleanup_task = asyncio.create_task(
                        self._delayed_room_cleanup(room_code, delay=config.ORGANIZER_RECONNECT_GRACE_SECONDS)
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
            elif room.game_type == "drawing":
                sync["drawing_prompt"] = round_data
                sync["drawer"] = room.current_drawer
                sync["drawing_ops"] = room.drawing_ops[-config.MAX_DRAW_OPS_PER_SYNC:]
                sync["correct_guessers"] = list(room.correct_guessers)
                sync["guess_log"] = room.guess_log[-10:]
                sync["answered_count"] = len(room.correct_guessers)
            else:
                sync["question"] = round_data
                sync["answered_count"] = len(room.answered_players)
            sync["is_bonus"] = room.current_question_index in room.bonus_questions
            elapsed = time.time() - room.question_start_time
            sync["time_remaining"] = max(0, room.time_limit - int(elapsed))

        if room.game_type in ("housie", "bingo"):
            sync["bingo"] = self._housie_public_state(room)

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
                async with room.lock:
                    if room.state != "LOBBY":
                        return
                    # Charge sparks to start the game
                    if not room.wallet_id:
                        await self._send_to_client(room, client_id, {
                            "type": "ERROR",
                            "message": "Internal error: wallet not configured.",
                        })
                        return
                    # WMLT requires minimum players — check before charging
                    if room.game_type == "wmlt":
                        player_count = len([p for p in room.players.values() if p.get("nickname")])
                        if player_count < config.MIN_WMLT_PLAYERS:
                            await self._send_to_client(room, client_id, {
                                "type": "ERROR",
                                "message": f"Most Likely To needs at least {config.MIN_WMLT_PLAYERS} players to start",
                            })
                            return
                    elif room.game_type == "drawing":
                        player_count = len([p for p in room.players.values() if p.get("nickname")])
                        if player_count < config.MIN_DRAWING_PLAYERS:
                            await self._send_to_client(room, client_id, {
                                "type": "ERROR",
                                "message": f"Drawing Game needs at least {config.MIN_DRAWING_PLAYERS} players to start",
                            })
                            return
                    elif room.game_type == "housie":
                        player_count = len([p for p in room.players.values() if p.get("nickname")])
                        if player_count < config.MIN_HOUSIE_PLAYERS:
                            await self._send_to_client(room, client_id, {
                                "type": "ERROR",
                                "message": f"Housie needs at least {config.MIN_HOUSIE_PLAYERS} players to start",
                            })
                            return
                    elif room.game_type == "bingo":
                        player_count = len([p for p in room.players.values() if p.get("nickname")])
                        if player_count < config.MIN_BINGO_PLAYERS:
                            await self._send_to_client(room, client_id, {
                                "type": "ERROR",
                                "message": f"Bingo needs at least {config.MIN_BINGO_PLAYERS} players to start",
                            })
                            return
                    if room.billing_mode == "host_app_managed":
                        spent = True
                    else:
                        spent, _ = token_module.spend_room(room.wallet_id)
                    if not spent:
                        await self._send_to_client(room, client_id, {
                            "type": "INSUFFICIENT_SPARKS",
                            "message": f"You need {config.COST_ROOM} sparks to start a game.",
                        })
                        return
                    room.locked = True
                    if room.game_type == "quiz":
                        self._select_bonus_questions(room)
                    self._mark_game_session_started(room)
                    if room.game_type in ("housie", "bingo"):
                        room.locked = True
                        room.state = "BINGO_CALLING"
                        self._start_housie_round(room)
                        await room.broadcast({"type": "GAME_STARTING", "game_type": room.game_type})
                        await self._broadcast_housie_sync(room)
                        if room.housie_caller_mode == "auto":
                            await self._set_housie_auto_status(room, "running")
                    else:
                        room.state = "INTRO"
                        await room.broadcast({"type": "GAME_STARTING"})

            elif msg_type == "NEXT_QUESTION":
                if room.game_type in ("housie", "bingo"):
                    return
                if room.state == "QUESTION":
                    await self.end_question(room)
                elif room.state in ("INTRO", "LEADERBOARD"):
                    await self.start_question(room)

            elif msg_type == "BINGO_CALL_NEXT" and room.game_type in ("housie", "bingo"):
                await self._housie_call_next(room)

            elif msg_type == "BINGO_UNDO_LAST_CALL" and room.game_type in ("housie", "bingo"):
                await self._housie_undo_last_call(room)

            elif msg_type == "BINGO_SET_CALLER_MODE" and room.game_type in ("housie", "bingo"):
                mode = str(message.get("caller_mode") or "").strip().lower()
                if mode not in ("manual", "auto"):
                    await self._send_to_client(room, client_id, {"type": "ERROR", "message": "Invalid caller mode"})
                    return
                interval = message.get("auto_interval_seconds")
                if interval is not None:
                    try:
                        room.housie_auto_interval_seconds = max(3, min(30, int(interval)))
                    except (TypeError, ValueError):
                        pass
                room.housie_caller_mode = mode
                if mode == "auto":
                    await self._set_housie_auto_status(room, "running")
                else:
                    await self._set_housie_auto_status(room, "stopped")

            elif msg_type == "BINGO_PAUSE" and room.game_type in ("housie", "bingo"):
                await self._set_housie_auto_status(room, "paused")

            elif msg_type == "BINGO_RESUME" and room.game_type in ("housie", "bingo"):
                room.housie_caller_mode = "auto"
                await self._set_housie_auto_status(room, "running")

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
                if room.game_type in ("housie", "bingo") and room.state == "BINGO_CALLING":
                    await self._complete_housie(room)
                    return
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
                        summary = self.get_game_summary(room)
                        game_history.append(summary)
                        if len(game_history) > config.MAX_GAME_HISTORY:
                            del game_history[:len(game_history) - config.MAX_GAME_HISTORY]
                        self._mark_game_session_complete(room, summary)
                    except Exception:
                        logger.warning("Could not save game history for room %s", room.room_code)

            elif msg_type == "RESET_ROOM":
                async with room.lock:
                    if room.state != "PODIUM":
                        return
                    new_content_id = message.get("content_id", "")
                    raw_game_type = message.get("game_type", room.game_type)
                    new_game_type = raw_game_type if raw_game_type in ("quiz", "wmlt", "drawing", "housie", "bingo") else room.game_type
                    raw_time_limit = message.get("time_limit", room.time_limit)

                    # Validate time_limit
                    try:
                        new_time_limit = int(raw_time_limit)
                    except (TypeError, ValueError):
                        new_time_limit = room.time_limit
                    new_time_limit = max(5, min(60, new_time_limit))

                    # Validate content BEFORE charging
                    from main import quizzes, mlt_scenarios, drawing_games, housie_games, bingo_games
                    if new_game_type == "wmlt":
                        new_game_data = mlt_scenarios.get(new_content_id)
                    elif new_game_type == "drawing":
                        new_game_data = drawing_games.get(new_content_id)
                    elif new_game_type == "housie":
                        new_game_data = housie_games.get(new_content_id)
                    elif new_game_type == "bingo":
                        new_game_data = bingo_games.get(new_content_id)
                    else:
                        new_game_data = quizzes.get(new_content_id)

                    if not new_game_data:
                        logger.warning("RESET_ROOM rejected: content_id %s not found for room %s",
                                       new_content_id, room.room_code)
                        await self._send_to_client(room, client_id, {"type": "ERROR", "message": "Game content not found. Please generate a new game."})
                        return

                    # Check content ownership
                    from main import content_owners, pending_generation_charges
                    owner = content_owners.get(new_content_id)
                    if owner and room.wallet_id and owner != room.wallet_id:
                        logger.warning("RESET_ROOM rejected: content %s owned by %s, room wallet %s",
                                       new_content_id, owner[:8], room.wallet_id[:8])
                        await self._send_to_client(room, client_id, {"type": "ERROR", "message": "You don't have permission to use this content."})
                        return

                    # Charge sparks only after content is validated
                    if not room.wallet_id:
                        await self._send_to_client(room, client_id, {
                            "type": "ERROR",
                            "message": "Internal error: wallet not configured.",
                        })
                        return
                    if (
                        room.billing_mode != "host_app_managed"
                        and pending_generation_charges.get(new_content_id) == room.wallet_id
                    ):
                        required = config.COST_GENERATE + config.COST_ROOM
                        if token_module.db.get_wallet_balance(room.wallet_id) < required:
                            await self._send_to_client(room, client_id, {
                                "type": "INSUFFICIENT_SPARKS",
                                "message": f"You need {required} sparks to use generated content and start a new game.",
                            })
                            return
                        generated_spent, _ = token_module.spend_generate(room.wallet_id)
                        if not generated_spent:
                            await self._send_to_client(room, client_id, {
                                "type": "INSUFFICIENT_SPARKS",
                                "message": f"You need {config.COST_GENERATE} sparks to use generated content.",
                            })
                            return
                        pending_generation_charges.pop(new_content_id, None)
                    if room.billing_mode == "host_app_managed":
                        spent = True
                    else:
                        spent, _ = token_module.spend_room(room.wallet_id)
                    if not spent:
                        await self._send_to_client(room, client_id, {
                            "type": "INSUFFICIENT_SPARKS",
                            "message": f"You need {config.COST_ROOM} sparks to start a new game.",
                        })
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
                        if room.game_type in ("housie", "bingo"):
                            state_info["bingo"] = self._housie_player_state(room, nickname)
                        elif room.state == "QUESTION":
                            round_data = room.current_round_data()
                            if room.game_type == "wmlt":
                                state_info["statement"] = round_data
                                state_info["players"] = [
                                    {"nickname": p["nickname"], "avatar": p.get("avatar", "")}
                                    for p in room.players.values()
                                ]
                            elif room.game_type == "drawing":
                                state_info.update(self._drawing_player_state(room, nickname, round_data))
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
                        if room.game_type in ("housie", "bingo"):
                            state_info["bingo"] = self._housie_player_state(room, player_data["nickname"])
                        elif room.state == "QUESTION":
                            round_data = room.current_round_data()
                            if room.game_type == "wmlt":
                                state_info["statement"] = round_data
                                state_info["players"] = [
                                    {"nickname": p["nickname"], "avatar": p.get("avatar", "")}
                                    for p in room.players.values()
                                ]
                            elif room.game_type == "drawing":
                                state_info.update(self._drawing_player_state(room, player_data["nickname"], round_data))
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

            elif msg_type == "DRAW_OP" and room.game_type == "drawing":
                await self._handle_draw_op(room, client_id, message)

            elif msg_type == "GUESS" and room.game_type == "drawing":
                await self._handle_drawing_guess(room, client_id, message)

            elif msg_type == "BINGO_CLAIM" and room.game_type in ("housie", "bingo"):
                await self._handle_housie_claim(room, client_id, message)

            elif msg_type == "ANSWER":
                if room.game_type in ("wmlt", "drawing", "housie", "bingo"):
                    return  # Other games use their own input messages
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

    def _start_housie_round(self, room: Room):
        room.housie_deck = create_bingo_call_deck(room.quiz.get("deck", [])) if room.game_type == "bingo" else create_call_deck()
        room.housie_called = []
        room.housie_winners = []
        room.housie_claimed_patterns = set()
        room.housie_claim_log = []
        room.housie_tickets = {}
        room.housie_play_mode = str(room.quiz.get("play_mode") or "beginner").lower()
        if room.housie_play_mode not in ("beginner", "pro"):
            room.housie_play_mode = "beginner"
        room.housie_caller_mode = str(room.quiz.get("caller_mode") or "manual").lower()
        if room.housie_caller_mode not in ("manual", "auto"):
            room.housie_caller_mode = "manual"
        try:
            room.housie_auto_interval_seconds = max(3, min(30, int(room.quiz.get("auto_interval_seconds") or 8)))
        except (TypeError, ValueError):
            room.housie_auto_interval_seconds = 8
        room.housie_auto_pause_on_claim = bool(room.quiz.get("auto_pause_on_claim", True))
        room.housie_auto_status = "stopped"
        room.housie_next_auto_call_at = None
        for idx, (client_id, player) in enumerate(room.players.items()):
            nickname = player["nickname"]
            ticket_id = f"{room.room_code}-{idx + 1}"
            if room.game_type == "bingo":
                room.housie_tickets[nickname] = generate_bingo_card(
                    ticket_id,
                    client_id,
                    nickname,
                    room.quiz.get("deck", []),
                    free_center=bool(room.quiz.get("free_center", True)),
                    free_center_label=str(room.quiz.get("free_center_label") or "FREE"),
                    seed=secrets.randbits(32),
                )
            else:
                room.housie_tickets[nickname] = generate_ticket(ticket_id, client_id, nickname)

    def _housie_patterns(self, room: Room) -> list[dict]:
        patterns = room.quiz.get("patterns") if isinstance(room.quiz.get("patterns"), list) else []
        known = {pattern["id"]: pattern for pattern in patterns if isinstance(pattern, dict) and pattern.get("id")}
        order = BINGO_PATTERN_ORDER if room.game_type == "bingo" else PATTERN_ORDER
        return [known[pid] for pid in order if pid in known]

    def _housie_public_state(self, room: Room) -> dict:
        return {
            "game_title": room.game_title(),
            "state": room.state,
            "called_items": room.housie_called,
            "latest_item": room.housie_called[-1] if room.housie_called else None,
            "remaining_count": len(room.housie_deck),
            "patterns": self._housie_patterns(room),
            "winners": room.housie_winners,
            "claim_log": room.housie_claim_log[-10:],
            "play_mode": room.housie_play_mode,
            "caller_mode": room.housie_caller_mode,
            "auto_status": room.housie_auto_status,
            "auto_interval_seconds": room.housie_auto_interval_seconds,
            "auto_pause_on_claim": room.housie_auto_pause_on_claim,
            "next_auto_call_at": room.housie_next_auto_call_at,
            "claim_requires_latest_call": bool(room.quiz.get("claim_requires_latest_call", room.game_type == "housie")),
            "layout": room.quiz.get("layout", "housie_3x9_15" if room.game_type == "housie" else "bingo_5x5_free"),
            "free_center": bool(room.quiz.get("free_center", False)),
        }

    def _housie_player_state(self, room: Room, nickname: str) -> dict:
        return {
            **self._housie_public_state(room),
            "ticket": room.housie_tickets.get(nickname),
        }

    async def _broadcast_housie_sync(self, room: Room):
        base = {
            "type": "BINGO_SYNC",
            "game_type": room.game_type,
            "bingo": self._housie_public_state(room),
            "player_count": len(room.players),
            "players": [{"nickname": p["nickname"], "avatar": p.get("avatar", "")} for p in room.players.values()],
        }
        for client_id, ws in list(room.connections.items()):
            if client_id in room.players:
                nickname = room.players[client_id]["nickname"]
                payload = dict(base)
                payload["bingo"] = self._housie_player_state(room, nickname)
                try:
                    await ws.send_json(payload)
                except Exception:
                    room._remove_connection(client_id)
        await room.send_to_organizer(base)
        for ws in list(room.spectators.values()):
            try:
                await ws.send_json(base)
            except Exception:
                pass

    async def _broadcast_housie_auto_status(self, room: Room):
        await room.broadcast({
            "type": "BINGO_AUTO_STATUS",
            "game_type": room.game_type,
            "caller_mode": room.housie_caller_mode,
            "auto_status": room.housie_auto_status,
            "auto_interval_seconds": room.housie_auto_interval_seconds,
            "auto_pause_on_claim": room.housie_auto_pause_on_claim,
            "next_auto_call_at": room.housie_next_auto_call_at,
        })

    async def _set_housie_auto_status(self, room: Room, status: str):
        if room.housie_auto_task:
            room.housie_auto_task.cancel()
            room.housie_auto_task = None
        room.housie_auto_status = status
        room.housie_next_auto_call_at = None
        if status == "running" and room.state == "BINGO_CALLING" and room.housie_deck:
            room.housie_caller_mode = "auto"
            room.housie_auto_task = asyncio.create_task(self._housie_auto_loop(room))
        elif status == "stopped":
            room.housie_caller_mode = "manual"
        await self._broadcast_housie_auto_status(room)

    async def _housie_auto_loop(self, room: Room):
        try:
            while room.state == "BINGO_CALLING" and room.housie_auto_status == "running" and room.housie_deck:
                next_at = datetime.now(timezone.utc).timestamp() + room.housie_auto_interval_seconds
                room.housie_next_auto_call_at = datetime.fromtimestamp(next_at, tz=timezone.utc).isoformat()
                await self._broadcast_housie_auto_status(room)
                await asyncio.sleep(room.housie_auto_interval_seconds)
                if room.state != "BINGO_CALLING" or room.housie_auto_status != "running":
                    break
                await self._housie_call_next(room, from_auto=True)
        except asyncio.CancelledError:
            pass
        finally:
            if room.housie_auto_task is asyncio.current_task():
                room.housie_auto_task = None

    async def _housie_call_next(self, room: Room, from_auto: bool = False):
        async with room.lock:
            if room.state != "BINGO_CALLING" or not room.housie_deck:
                return
            item = room.housie_deck.pop(0)
            room.housie_called.append(item)
            room.current_question_index = len(room.housie_called) - 1
            room.answer_log.append({"kind": "call", "item": item, "index": len(room.housie_called)})
        await room.broadcast({
            "type": "BINGO_CALL",
            "game_type": room.game_type,
            "item": item,
            "called_items": room.housie_called,
            "remaining_count": len(room.housie_deck),
            "call_index": len(room.housie_called),
            "animation": "latest_call",
            "auto_status": room.housie_auto_status,
        })
        if not room.housie_deck:
            if room.housie_auto_task and not from_auto:
                room.housie_auto_task.cancel()
                room.housie_auto_task = None
            room.housie_auto_status = "stopped"
            room.housie_next_auto_call_at = None
            await self._complete_housie(room)

    async def _housie_undo_last_call(self, room: Room):
        async with room.lock:
            if room.state != "BINGO_CALLING" or not room.housie_called:
                return
            # Block undo if any accepted claim was validated at or after the last call index.
            last_call_index = len(room.housie_called)
            if any(w.get("called_count", 0) >= last_call_index for w in room.housie_winners):
                return
            item = room.housie_called.pop()
            room.housie_deck.insert(0, item)
            room.current_question_index = len(room.housie_called) - 1
        await self._broadcast_housie_sync(room)

    async def _handle_housie_claim(self, room: Room, client_id: str, message: dict):
        if client_id not in room.players or room.state != "BINGO_CALLING":
            return
        pattern_id = str(message.get("pattern_id") or "").strip()
        if pattern_id not in {pattern["id"] for pattern in self._housie_patterns(room)}:
            await self._send_to_client(room, client_id, {"type": "BINGO_CLAIM_REJECTED", "pattern_id": pattern_id, "reason": "unknown_pattern", "message": "Unknown prize"})
            return
        if pattern_id in room.housie_claimed_patterns:
            await self._send_to_client(room, client_id, {"type": "BINGO_CLAIM_REJECTED", "pattern_id": pattern_id, "reason": "already_awarded", "message": "That prize has already been awarded"})
            return
        auto_paused_for_claim = room.housie_auto_status == "running" and room.housie_auto_pause_on_claim
        if auto_paused_for_claim:
            await self._set_housie_auto_status(room, "paused")
        nickname = room.players[client_id]["nickname"]
        ticket = room.housie_tickets.get(nickname)
        if room.game_type == "bingo":
            valid, reason, winning_values = validate_bingo_claim(
                ticket or {},
                room.housie_called,
                pattern_id,
                require_latest=bool(room.quiz.get("claim_requires_latest_call", False)),
            )
        else:
            valid, reason = validate_claim(ticket or {}, room.housie_called, pattern_id, require_latest=True)
            winning_values = []
        if not valid:
            await self._send_to_client(room, client_id, {"type": "BINGO_CLAIM_REJECTED", "pattern_id": pattern_id, "reason": reason, "message": reason})
            if auto_paused_for_claim:
                await self._set_housie_auto_status(room, "running")
            return
        pattern = next((p for p in self._housie_patterns(room) if p["id"] == pattern_id), {"label": pattern_id})
        latest_item = room.housie_called[-1] if room.housie_called else {}
        winner = {
            "pattern_id": pattern_id,
            "label": pattern.get("label", pattern_id),
            "nickname": nickname,
            "called_count": len(room.housie_called),
            "winning_number": latest_item.get("value"),
            "winning_values": winning_values,
        }
        async with room.lock:
            if pattern_id in room.housie_claimed_patterns:
                duplicate_claim = True
            else:
                duplicate_claim = False
                room.housie_claimed_patterns.add(pattern_id)
                room.housie_winners.append(winner)
                room.housie_claim_log.append(winner)
                if pattern_id == "full_house":
                    room.players[client_id]["score"] += 1000
                else:
                    room.players[client_id]["score"] += 250
                room.answer_log.append({"kind": "claim", **winner})
        if duplicate_claim:
            if auto_paused_for_claim:
                await self._set_housie_auto_status(room, "running")
            await self._send_to_client(room, client_id, {"type": "BINGO_CLAIM_REJECTED", "pattern_id": pattern_id, "reason": "already_awarded", "message": "That prize has already been awarded"})
            return
        await room.broadcast({
            "type": "BINGO_CLAIM_ACCEPTED",
            "game_type": room.game_type,
            "winner": winner,
            "winners": room.housie_winners,
            "leaderboard": self.get_leaderboard(room),
            "announce": True,
        })
        is_terminal = pattern.get("terminal", pattern_id == "full_house")
        if is_terminal:
            await self._set_housie_auto_status(room, "stopped")
            await self._complete_housie(room)
        elif auto_paused_for_claim:
            await self._set_housie_auto_status(room, "running")

    async def _complete_housie(self, room: Room):
        if room.state == "PODIUM":
            return
        if room.housie_auto_task and room.housie_auto_task is not asyncio.current_task():
            room.housie_auto_task.cancel()
            room.housie_auto_task = None
        room.housie_auto_status = "stopped"
        room.housie_next_auto_call_at = None
        room.state = "PODIUM"
        leaderboard = self.get_leaderboard(room)
        await room.broadcast({
            "type": "BINGO_COMPLETE",
            "game_type": room.game_type,
            "winners": room.housie_winners,
            "leaderboard": leaderboard,
            "team_leaderboard": self.get_team_leaderboard(room),
        })
        await room.broadcast({
            "type": "PODIUM",
            "leaderboard": leaderboard,
            "team_leaderboard": self.get_team_leaderboard(room),
            "housie_winners": room.housie_winners,
        })
        try:
            from main import game_history
            summary = self.get_game_summary(room)
            game_history.append(summary)
            if len(game_history) > config.MAX_GAME_HISTORY:
                del game_history[:len(game_history) - config.MAX_GAME_HISTORY]
            self._mark_game_session_complete(room, summary)
        except Exception:
            logger.warning("Could not save Housie history for room %s", room.room_code)

    def _drawing_player_state(self, room: Room, nickname: str, prompt: Optional[dict]) -> dict:
        is_drawer = nickname == room.current_drawer
        return {
            "drawing_prompt": prompt if is_drawer else ({k: v for k, v in (prompt or {}).items() if k not in ("text", "aliases")}),
            "drawer": room.current_drawer,
            "is_drawer": is_drawer,
            "drawing_ops": room.drawing_ops[-config.MAX_DRAW_OPS_PER_SYNC:],
            "correct_guessers": list(room.correct_guessers),
            "guess_log": room.guess_log[-10:],
        }

    def _ensure_drawer_order(self, room: Room):
        current = room.player_nicknames()
        if not room.drawer_order:
            room.drawer_order = current[:]
        for nickname in current:
            if nickname not in room.drawer_order:
                room.drawer_order.append(nickname)
        room.drawer_order = [n for n in room.drawer_order if n in set(current) or n in room.disconnected_players]

    def _drawer_for_round(self, room: Room) -> str:
        self._ensure_drawer_order(room)
        if not room.drawer_order:
            return ""
        return room.drawer_order[room.current_question_index % len(room.drawer_order)]

    async def _broadcast_drawing_question(self, room: Room, prompt: dict, is_bonus: bool):
        base = {
            "type": "QUESTION",
            "question_number": room.current_question_index + 1,
            "total_questions": room.total_rounds(),
            "time_limit": room.time_limit,
            "is_bonus": is_bonus,
            "game_type": "drawing",
            "drawer": room.current_drawer,
            "correct_guessers": [],
            "drawing_ops": [],
            "guess_log": [],
        }
        for client_id, ws in list(room.connections.items()):
            if client_id not in room.players:
                continue
            nickname = room.players[client_id]["nickname"]
            payload = dict(base)
            payload["is_drawer"] = nickname == room.current_drawer
            payload["drawing_prompt"] = prompt if payload["is_drawer"] else {"id": prompt.get("id"), "difficulty": prompt.get("difficulty")}
            try:
                await ws.send_json(payload)
            except Exception:
                room._remove_connection(client_id)
        await room.send_to_organizer({
            **base,
            "drawing_prompt": prompt,
            "is_drawer": False,
        })
        for ws in list(room.spectators.values()):
            try:
                await ws.send_json({
                    **base,
                    "drawing_prompt": {"id": prompt.get("id"), "difficulty": prompt.get("difficulty")},
                    "is_drawer": False,
                })
            except Exception:
                pass

    def _valid_draw_op(self, op: dict) -> bool:
        if not isinstance(op, dict):
            return False
        if op.get("kind") not in ("stroke", "clear", "undo"):
            return False
        if op.get("kind") in ("clear", "undo"):
            return True
        points = op.get("points")
        if not isinstance(points, list) or len(points) == 0 or len(points) > 80:
            return False
        width = op.get("width", 4)
        if not isinstance(width, (int, float)) or width <= 0 or width > 32:
            return False
        color = op.get("color", "#ffffff")
        if not isinstance(color, str) or not re.match(r"^#[0-9a-fA-F]{6}$", color):
            return False
        for point in points:
            if not isinstance(point, list) or len(point) != 2:
                return False
            x, y = point
            if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                return False
            if x < 0 or x > 1 or y < 0 or y > 1:
                return False
        return True

    async def _handle_draw_op(self, room: Room, client_id: str, message: dict):
        if client_id not in room.players or room.state != "QUESTION":
            return
        nickname = room.players[client_id]["nickname"]
        if nickname != room.current_drawer:
            await self._send_to_client(room, client_id, {"type": "ERROR", "message": "Only the drawer can draw"})
            return
        op = message.get("op")
        if not self._valid_draw_op(op):
            await self._send_to_client(room, client_id, {"type": "ERROR", "message": "Invalid drawing operation"})
            return
        op = dict(op)
        op["drawer"] = nickname
        op["seq"] = len(room.drawing_ops) + 1
        if op["kind"] == "clear":
            room.drawing_ops.clear()
        elif op["kind"] == "undo":
            if room.drawing_ops:
                room.drawing_ops.pop()
        else:
            room.drawing_ops.append(op)
            if len(room.drawing_ops) > config.MAX_DRAW_OPS_PER_SYNC:
                room.drawing_ops = room.drawing_ops[-config.MAX_DRAW_OPS_PER_SYNC:]
        await room.broadcast({"type": "DRAW_OP", "op": op})

    async def _handle_drawing_guess(self, room: Room, client_id: str, message: dict):
        if client_id not in room.players or room.state != "QUESTION":
            return
        nickname = room.players[client_id]["nickname"]
        if nickname == room.current_drawer or nickname in room.correct_guessers:
            return
        raw_guess = message.get("guess", "")
        guess = (raw_guess if isinstance(raw_guess, str) else "").strip()[:80]
        if not guess:
            return
        prompt = room.current_round_data()
        if not prompt:
            return
        from drawing_engine import is_correct_guess
        correct = is_correct_guess(guess, prompt)
        if correct:
            elapsed = max(0, time.time() - room.question_start_time)
            time_remaining = max(0, room.time_limit - elapsed)
            points = 300 + round(600 * (time_remaining / max(1, room.time_limit)))
            async with room.lock:
                if nickname in room.correct_guessers:
                    return
                room.correct_guessers.add(nickname)
                room.answered_players.add(client_id)
                room.players[client_id]["score"] += points
                drawer_id = next((cid for cid, p in room.players.items() if p["nickname"] == room.current_drawer), None)
                if drawer_id:
                    room.players[drawer_id]["score"] += 200
                all_guessed = len(room.correct_guessers) >= max(0, len(room.players) - 1)
            room.guess_log.append({"nickname": nickname, "guess": guess, "correct": True})
            await self._send_to_client(room, client_id, {"type": "GUESS_RESULT", "correct": True, "points": points})
            await room.broadcast({
                "type": "GUESS_ACCEPTED",
                "nickname": nickname,
                "correct_guessers": list(room.correct_guessers),
                "guess": guess,
            })
            await room.send_to_organizer({
                "type": "ANSWER_COUNT",
                "answered": len(room.correct_guessers),
                "total": max(0, len(room.players) - 1),
            })
            if all_guessed:
                if drawer_id:
                    room.players[drawer_id]["score"] += 500
                await self.end_question(room)
        else:
            room.guess_log.append({"nickname": nickname, "guess": guess, "correct": False})
            room.guess_log = room.guess_log[-20:]
            await self._send_to_client(room, client_id, {"type": "GUESS_RESULT", "correct": False, "points": 0})
            await room.broadcast({"type": "GUESS_LOG", "guess_log": room.guess_log[-10:]})

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
        summary = {
            "room_code": room.room_code,
            "game_type": room.game_type,
            "game_title": room.game_title(),
            "total_questions": room.total_rounds(),
            "player_count": all_player_count,
            "leaderboard": self.get_leaderboard(room),
            "team_leaderboard": self.get_team_leaderboard(room),
            "answer_log": room.answer_log,
            "completed_at": time.time(),
            "wallet_id": room.wallet_id or "",
        }
        if room.game_type in ("housie", "bingo"):
            summary["total_questions"] = len(room.housie_called)
            summary["total_rounds"] = len(room.housie_called)
            summary["winners"] = room.housie_winners
            summary["top_results"] = [
                {
                    "nickname": winner.get("nickname"),
                    "score": next((p.get("score", 0) for p in self._all_players_for_leaderboard(room) if p.get("nickname") == winner.get("nickname")), 0),
                    "prize": winner.get("label"),
                }
                for winner in room.housie_winners[:5]
            ]
        return summary

    def _callback_event_type(self, event_type: str) -> str:
        return {
            "session.created": "game.session_created",
            "session.started": "game.started",
            "session.completed": "game.completed",
            "session.cancelled": "game.cancelled",
            "session.expired": "game.expired",
            "session.superseded": "game.superseded",
        }.get(event_type, event_type)

    def _callback_signing_secret(self) -> str:
        return config.REVELRY_INTEGRATION_SECRET or config.REVELRY_CALLBACK_SECRET

    def _callback_retry_delay(self, response: Optional[httpx.Response], attempt: int) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After", "")
            try:
                return max(0.0, min(float(retry_after), 5.0))
            except ValueError:
                pass
        return min(0.25 * (2 ** attempt), 2.0)

    def _safe_result_summary(self, summary: Optional[dict]) -> Optional[dict]:
        if not isinstance(summary, dict):
            return None
        if isinstance(summary.get("top_results"), list):
            top_results = summary["top_results"][:5]
            return {
                "title": summary.get("title") or summary.get("game_title") or "LocalPlay results",
                "game_type": summary.get("game_type"),
                "total_rounds": summary.get("total_rounds") or summary.get("total_questions"),
                "player_count": summary.get("player_count"),
                "top_results": top_results,
                "players": top_results,
                "leaderboard": top_results,
                "winner": summary.get("winner") if isinstance(summary.get("winner"), dict) else (top_results[0] if top_results else None),
                "completed_at": summary.get("completed_at"),
            }
        leaderboard = summary.get("leaderboard") if isinstance(summary.get("leaderboard"), list) else []
        top_results = []
        for row in leaderboard[:5]:
            if not isinstance(row, dict):
                continue
            top_results.append({
                "nickname": row.get("nickname"),
                "avatar": row.get("avatar"),
                "score": row.get("score"),
            })
        return {
            "title": summary.get("title") or summary.get("game_title") or "LocalPlay results",
            "game_type": summary.get("game_type"),
            "total_rounds": summary.get("total_questions") or summary.get("total_rounds"),
            "player_count": summary.get("player_count"),
            "top_results": top_results,
            "players": top_results,
            "leaderboard": top_results,
            "winner": top_results[0] if top_results else None,
            "completed_at": summary.get("completed_at"),
        }

    def _safe_actor_payload(self, session: dict) -> Optional[dict]:
        actor = {
            "external_user_id": session.get("external_host_user_id") or "",
            "display_name": session.get("external_host_display_name") or "",
            "role": "host",
        }
        actor = {key: value for key, value in actor.items() if value}
        return actor or None

    def _mark_game_session_complete(self, room: Room, summary: dict):
        """Attach completed result metadata to an integration session, if present."""
        try:
            import db
            session = db.get_game_session_by_room(room.room_code)
            if not session:
                return
            now = int(time.time())
            safe_summary = self._safe_result_summary(summary)
            updated = db.update_game_session(session["id"], {
                "status": "complete",
                "joinable": False,
                "result_summary": safe_summary,
                "completed_at": now,
                "last_activity_at": now,
            })
            self._send_integration_callback("session.completed", updated or session, safe_summary)
        except Exception:
            logger.warning("Could not update game session for room %s", room.room_code)

    def _send_integration_callback(self, event_type: str, session: dict, result_summary: Optional[dict] = None):
        if not config.REVELRY_CALLBACK_URL or session.get("host_app") != "revelry":
            return
        event_type = self._callback_event_type(event_type)
        session_id = session.get("id")
        result_summary = self._safe_result_summary(result_summary) if result_summary else None
        actor_payload = self._safe_actor_payload(session)
        body = {
            "event_id": f"lp_evt_{uuid.uuid4().hex}",
            "event_type": event_type,
            "occurred_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "host_app": session.get("host_app"),
            "external_container_type": session.get("external_container_type"),
            "external_container_id": session.get("external_container_id"),
            "session_id": session_id,
            "idempotency_key": f"{event_type}:{session_id or uuid.uuid4().hex}:v1",
            "payload": {
                "room_code": session.get("room_code"),
                "status": session.get("status"),
                "actor": actor_payload,
                "game_type": session.get("game_type"),
                "game_title": session.get("game_title"),
                "result_summary": result_summary,
                "feed_card": session.get("feed_card"),
                "closed_reason": session.get("closed_reason"),
                "closed_message": session.get("closed_message"),
                "superseded_by_session_id": session.get("superseded_by_session_id"),
            },
        }
        body["payload"] = {key: value for key, value in body["payload"].items() if value is not None}
        body = {key: value for key, value in body.items() if value is not None}
        raw = json.dumps(body, separators=(",", ":")).encode()
        timestamp = str(int(time.time()))
        headers = {
            "Content-Type": "application/json",
            "X-LocalPlay-Event-Id": body["event_id"],
            "X-LocalPlay-Timestamp": timestamp,
        }
        signing_secret = self._callback_signing_secret()
        if signing_secret:
            signature = hmac.new(
                signing_secret.encode(),
                f"{timestamp}.".encode() + raw,
                hashlib.sha256,
            ).hexdigest()
            headers["X-LocalPlay-Signature"] = f"sha256={signature}"
        with httpx.Client(timeout=5.0) as client:
            for attempt in range(3):
                try:
                    response = client.post(config.REVELRY_CALLBACK_URL, content=raw, headers=headers)
                    response.raise_for_status()
                    return
                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code
                    if status not in (429, 500, 502, 503, 504) or attempt == 2:
                        logger.warning("Integration callback failed for %s: %s", event_type, exc)
                        return
                    time.sleep(self._callback_retry_delay(exc.response, attempt))
                except httpx.HTTPError as exc:
                    if attempt == 2:
                        logger.warning("Integration callback failed for %s: %s", event_type, exc)
                        return
                    time.sleep(self._callback_retry_delay(None, attempt))

    def _mark_game_session_started(self, room: Room):
        try:
            import db
            session = db.get_game_session_by_room(room.room_code)
            if not session or session.get("started_at"):
                return
            now = int(time.time())
            updated = db.update_game_session(session["id"], {
                "status": "active",
                "started_at": now,
                "expires_at": now + config.REVELRY_SESSION_IDLE_TTL_SECONDS,
                "last_activity_at": now,
            })
            self._send_integration_callback("session.started", updated or session)
        except Exception:
            logger.warning("Could not mark game session started for room %s", room.room_code)

    def _mark_game_session_closed(self, room: Room, reason: str, message: str):
        try:
            import db
            session = db.get_game_session_by_room(room.room_code)
            if not session or session.get("status") in ("complete", "superseded", "cancelled", "expired"):
                return
            now = int(time.time())
            updated = db.update_game_session(session["id"], {
                "status": reason,
                "joinable": False,
                "closed_reason": reason,
                "closed_message": message,
                "last_activity_at": now,
            })
            self._send_integration_callback(f"session.{reason}", updated or session)
        except Exception:
            logger.warning("Could not mark game session closed for room %s", room.room_code)

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
                summary = self.get_game_summary(room)
                game_history.append(summary)
                if len(game_history) > config.MAX_GAME_HISTORY:
                    del game_history[:len(game_history) - config.MAX_GAME_HISTORY]
                self._mark_game_session_complete(room, summary)
                logger.info("Game history saved for room %s", room.room_code)
            except Exception:
                logger.warning("Could not save game history for room %s", room.room_code)
            return

        # Store previous leaderboard for animation
        room.previous_leaderboard = self.get_leaderboard(room)

        room.answered_players = set()
        room.votes = {}  # Clear WMLT votes for new round
        room.correct_guessers = set()
        room.drawing_ops = []
        room.guess_log = []

        # Clear per-question power-up state from previous question
        for pups in room.power_ups.values():
            pups.pop("fifty_fifty_remove_indices", None)
            pups.pop("double_points_active", None)

        is_bonus = room.current_question_index in room.bonus_questions

        # Set state to QUESTION before broadcast so answers/votes are accepted immediately
        room.state = "QUESTION"

        if room.game_type == "wmlt":
            statement = room.current_round_data()
            if not statement:
                return
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
        elif room.game_type == "drawing":
            prompt = room.current_round_data()
            if not prompt:
                return
            room.current_drawer = self._drawer_for_round(room)
            await self._broadcast_drawing_question(room, prompt, is_bonus)
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
        if room.game_type == "drawing":
            await self._end_drawing_round(room)
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

    async def _end_drawing_round(self, room: Room):
        prompt = room.current_round_data()
        if not prompt:
            return
        current_leaderboard = self.get_leaderboard_with_changes(room)
        is_final = room.current_question_index >= room.total_rounds() - 1
        room.answer_log.append({
            "question_index": room.current_question_index,
            "game_type": "drawing",
            "prompt": prompt.get("text", ""),
            "drawer": room.current_drawer,
            "correct_guessers": list(room.correct_guessers),
            "guess_log": room.guess_log[-20:],
        })
        await room.broadcast({
            "type": "QUESTION_OVER",
            "game_type": "drawing",
            "prompt": prompt.get("text", ""),
            "drawer": room.current_drawer,
            "correct_guessers": list(room.correct_guessers),
            "leaderboard": current_leaderboard,
            "previous_leaderboard": room.previous_leaderboard,
            "is_final": is_final,
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
