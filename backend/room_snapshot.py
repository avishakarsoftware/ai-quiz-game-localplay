"""Room snapshot/restore — live games survive backend deploys and restarts.

Rooms have always been in-memory only, so every deploy killed every live
party game (Revelry sessions then got reconciled to closed_reason=
"runtime_unavailable"). This module periodically snapshots each room's durable
state to JSON files in the data dir (the same Docker-volume-mounted directory
as the SQLite DB, so snapshots survive container rebuilds) and restores rooms
at startup. Reconnection is the existing machinery: players hold session
tokens (room.player_tokens) and the organizer holds organizer_token, both of
which are part of the snapshot — clients that reconnect after the deploy
reclaim their seats and scores exactly as they would after a normal drop.

What is deliberately NOT snapshotted (EXCLUDED_ATTRS): live websockets,
asyncio tasks/locks, and per-socket transients (rate-limit timestamps,
just-disconnected flags). On restore:
  - LOBBY rooms keep their seats, marked offline (mirrors a lobby disconnect).
  - Active rooms move seats to disconnected_players keyed by nickname
    (mirrors an in-game disconnect), ready for session-token reclaim.
  - Rooms in QUESTION state get their question timer restarted by the manager
    (fresh countdown — scoring still uses the original question_start_time).
  - Housie auto-caller restores as "stopped"; the host taps resume.

Known accepted edges (short timed sub-states): a Musical Chairs music round
or Mafia phase timer that was mid-flight does not auto-resume its task; host
controls recover those. The dominant long-running cases (lobbies, Party
Quests, Find Someone Who, quiz between questions) restore seamlessly.
"""
import json
import logging
import os
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

SNAPSHOT_DIR = os.getenv(
    "ROOM_SNAPSHOT_DIR",
    os.path.join(os.getenv("DB_DIR", os.path.join(os.path.dirname(__file__), "data")), "room_snapshots"),
)

# Live/transient members that must never be serialized.
EXCLUDED_ATTRS = {
    "organizer",            # WebSocket
    "organizer_id",         # socket-scoped client id
    "spectators",           # WebSockets
    "connections",          # WebSockets
    "timer_task",           # asyncio.Task
    "lock",                 # asyncio.Lock
    "msg_timestamps",       # per-socket rate limiting
    "draw_op_timestamps",   # per-socket rate limiting
    "_organizer_cleanup_task",
    "_organizer_just_disconnected",
    "_player_event",
    "drawing_auto_task",
    "housie_auto_task",
    "mc_auto_stop_task",
    "mc_grab_task",
    "mafia_timer_task",
}

_SET_MARKER = "__set__"


def _encode_value(value: Any) -> Any:
    if isinstance(value, set):
        return {_SET_MARKER: sorted(value, key=str)}
    return value


def _decode_value(value: Any) -> Any:
    if isinstance(value, dict) and set(value.keys()) == {_SET_MARKER}:
        return set(value[_SET_MARKER])
    return value


def snapshot_room(room: Any) -> Optional[dict]:
    """Return a JSON-safe dict of the room's durable state, or None if it can't be captured."""
    data: Dict[str, Any] = {}
    for attr, value in vars(room).items():
        if attr in EXCLUDED_ATTRS:
            continue
        encoded = _encode_value(value)
        try:
            json.dumps(encoded)
        except (TypeError, ValueError):
            # Future non-serializable attr: skip it rather than break snapshots,
            # but say so loudly — it likely belongs in EXCLUDED_ATTRS.
            logger.warning("room_snapshot: skipping non-serializable attr %r on room %s",
                           attr, getattr(room, "room_code", "?"))
            continue
        data[attr] = encoded
    return data


def _path(room_code: str) -> str:
    safe = "".join(ch for ch in room_code if ch.isalnum()).upper()
    return os.path.join(SNAPSHOT_DIR, f"{safe}.json")


def save_all(rooms: Dict[str, Any]) -> int:
    """Atomically write a snapshot per room; prune files for rooms that no longer exist."""
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    saved = 0
    for code, room in list(rooms.items()):
        data = snapshot_room(room)
        if data is None:
            continue
        path = _path(code)
        tmp = f"{path}.tmp"
        try:
            with open(tmp, "w") as fh:
                json.dump(data, fh)
            os.replace(tmp, path)
            saved += 1
        except OSError as exc:
            logger.error("room_snapshot: failed to write %s: %s", path, exc)
    # prune snapshots for rooms that are gone (closed/expired)
    live = {os.path.basename(_path(code)) for code in rooms}
    try:
        for name in os.listdir(SNAPSHOT_DIR):
            if name.endswith(".json") and name not in live:
                os.remove(os.path.join(SNAPSHOT_DIR, name))
    except OSError:
        pass
    return saved


def delete(room_code: str) -> None:
    try:
        os.remove(_path(room_code))
    except OSError:
        pass


def load_all(room_factory, ttl_seconds: int) -> list:
    """Rebuild Room objects from snapshots. Returns the restored rooms.

    room_factory(room_code, game_data, time_limit, organizer_token, content_id,
    game_type, billing_mode) must return a fresh Room (the real constructor, so
    every non-snapshotted member — locks, connection maps — is initialized).
    """
    if not os.path.isdir(SNAPSHOT_DIR):
        return []
    restored = []
    now = time.time()
    for name in sorted(os.listdir(SNAPSHOT_DIR)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(SNAPSHOT_DIR, name)
        try:
            with open(path) as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            logger.error("room_snapshot: unreadable snapshot %s: %s", name, exc)
            continue
        last_activity = float(data.get("last_activity") or 0)
        if now - last_activity > ttl_seconds:
            try:
                os.remove(path)
            except OSError:
                pass
            continue
        try:
            room = room_factory(
                data.get("room_code", ""),
                data.get("quiz") or {},
                int(data.get("time_limit") or 15),
                str(data.get("organizer_token") or ""),
                str(data.get("content_id") or ""),
                str(data.get("game_type") or "quiz"),
                str(data.get("billing_mode") or "localplay_sparks"),
            )
            for attr, value in data.items():
                setattr(room, attr, _decode_value(value))
            _normalize_restored(room)
            restored.append(room)
        except Exception:
            logger.exception("room_snapshot: failed to restore room from %s", name)
    return restored


def _normalize_restored(room: Any) -> None:
    """Post-restore bookkeeping: no sockets exist anymore, so make the room look
    the way the existing disconnect paths would have left it."""
    now = time.time()
    if room.state == "LOBBY":
        # Mirror the lobby soft-disconnect: seats preserved, marked offline.
        for entry in room.players.values():
            entry["connection_status"] = "offline"
            entry["disconnected_at"] = now
    else:
        # Mirror the in-game disconnect: seat data moves to disconnected_players
        # (nickname-keyed) so a session-token reconnect reclaims score/streak.
        for client_id, entry in list(room.players.items()):
            nickname = entry.get("nickname", "")
            if nickname and nickname not in room.disconnected_players:
                room.disconnected_players[nickname] = {
                    "score": entry.get("score", 0),
                    "prev_rank": entry.get("prev_rank", 0),
                    "streak": entry.get("streak", 0),
                    "avatar": entry.get("avatar", ""),
                    "_answered_client_id": client_id if client_id in room.answered_players else None,
                }
        room.players = {}
    # Auto-callers/timed helpers restart via host action, never implicitly.
    if getattr(room, "housie_auto_status", "") == "running":
        room.housie_auto_status = "stopped"
        room.housie_next_auto_call_at = None
