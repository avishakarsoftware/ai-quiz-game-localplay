"""Repository-review regressions for persistence ownership and room lifecycle contracts."""
import asyncio
import json
import time

import config
import httpx

import pytest
from fastapi import WebSocketDisconnect

import db
import supabase_db
from socket_manager import Room, SocketManager, spawn


QUESTIONS = [{"text": "Original?", "options": ["A", "B"], "answer_index": 0}]


def test_foreign_quiz_update_preserves_owner_questions():
    saved = db.save_quiz_pack("owner", "Original", QUESTIONS, pack_id="private-pack")
    with pytest.raises(RuntimeError, match="another wallet"):
        db.save_quiz_pack("stranger", "Overwrite", [dict(QUESTIONS[0], text="Replaced?")], pack_id=saved["id"])
    assert db.get_quiz_pack("owner", saved["id"]) == saved
    assert db.get_quiz_pack("stranger", saved["id"]) is None


def test_failed_quiz_update_rolls_back_old_questions_and_metadata():
    saved = db.save_quiz_pack("owner", "Original", QUESTIONS)
    # A child write failure must leave the last usable pack intact.
    with pytest.raises(TypeError):
        db.save_quiz_pack("owner", "Broken", [dict(QUESTIONS[0], options={"A", "B"})], pack_id=saved["id"])
    assert db.get_quiz_pack("owner", saved["id"]) == saved


@pytest.mark.parametrize("kind", ["quiz", "drawing"])
def test_supabase_foreign_content_update_performs_no_mutation(monkeypatch, kind):
    class ForeignContentClient:
        def select(self, table, **kwargs):
            return [{"id": "private", "owner_wallet_id": "owner", "wallet_id": "owner", "created_at": 1}]

        def __getattr__(self, name):
            raise AssertionError(f"foreign content attempted mutation: {name}")

    monkeypatch.setattr(supabase_db, "_sb", lambda: ForeignContentClient())
    with pytest.raises(supabase_db.SupabaseDBError, match="another wallet"):
        if kind == "quiz":
            supabase_db.save_quiz_pack("stranger", "Overwrite", QUESTIONS, pack_id="private")
        else:
            supabase_db.save_game_content("stranger", kind, "Overwrite", {}, content_id="private")


class Socket:
    def __init__(self):
        self.messages = []
        self.closed = False

    async def send_json(self, message):
        await asyncio.sleep(0)
        self.messages.append(message)

    async def close(self):
        await asyncio.sleep(0)
        self.closed = True


def quiz_room():
    return Room("REVIEW", {"quiz_title": "Quiz", "questions": QUESTIONS}, game_type="quiz")


@pytest.mark.asyncio
@pytest.mark.parametrize("token", ["host-secret", "invalid"])
async def test_empty_lobby_organizer_auth_restores_authoritative_settings(token):
    class OrganizerSocket(Socket):
        headers = {}

        async def accept(self):
            pass

        async def receive_json(self):
            return {"type": "AUTH", "token": token}

        async def receive_text(self):
            raise WebSocketDisconnect()

    game_data = {"game_title": "Custom Would You Rather", "round_count": 4, "scoring_mode": "none"}
    room = Room("EMPTY1", game_data, time_limit=45, organizer_token="host-secret", game_type="would_you_rather")
    manager = SocketManager()
    manager.rooms[room.room_code] = room
    ws = OrganizerSocket()
    await manager.connect(ws, room.room_code, "org", is_organizer=True)
    if token == "host-secret":
        assert ws.messages[0] == {
            "type": "ROOM_CREATED", "room_code": room.room_code,
            "player_count": 0, "players": [], "time_limit": 45,
            "game_type": "would_you_rather", "quiz": game_data,
        }
        cleanup = room._organizer_cleanup_task
        await room.close_all_connections()
        await asyncio.gather(cleanup, return_exceptions=True)
    else:
        assert ws.messages == [{"type": "ERROR", "message": "Invalid organizer token"}]
        assert ws.closed
        assert room.organizer is None
        assert room.connections == {}


@pytest.mark.asyncio
async def test_closing_room_stops_every_timer_and_clears_connections():
    room = quiz_room()
    organizer, player, spectator = Socket(), Socket(), Socket()
    room.organizer = organizer
    room.organizer_id = "org"
    room.connections = {"org": organizer, "player": player}
    room.spectators = {"tv": spectator}
    attrs = ("timer_task", "drawing_auto_task", "housie_auto_task", "mc_auto_stop_task",
             "mc_grab_task", "mafia_timer_task", "_organizer_cleanup_task")
    tasks = []
    for attr in attrs:
        task = spawn(asyncio.sleep(60), name=f"review-{attr}")
        tasks.append(task)
        setattr(room, attr, task)
    await asyncio.sleep(0)
    await room.close_all_connections()
    await asyncio.gather(*tasks, return_exceptions=True)
    assert all(task.cancelled() for task in tasks)
    assert all(getattr(room, attr) is None for attr in attrs)
    assert all(ws.closed for ws in (organizer, player, spectator))
    assert room.connections == room.spectators == {}
    assert room.organizer is None and room.organizer_id is None


@pytest.mark.asyncio
async def test_organizer_grace_can_close_own_room_without_cancelling_itself():
    room = quiz_room()
    ws = Socket()
    room.connections["player"] = ws

    async def cleanup():
        room._organizer_cleanup_task = asyncio.current_task()
        await room.close_all_connections()
        return "session-status-recorded"

    assert await spawn(cleanup(), name="review-grace-close") == "session-status-recorded"
    assert ws.closed


@pytest.mark.asyncio
async def test_question_timer_publishes_results_when_it_closes_its_own_round():
    room = quiz_room()
    manager = SocketManager()
    room.state = "QUESTION"
    room.current_question_index = 0
    room.time_limit = 0
    ws = Socket()
    room.connections["player"] = ws
    room.timer_task = spawn(manager.question_timer(room), name="review-question-timer")
    await room.timer_task
    assert room.state == "LEADERBOARD"
    assert any(message["type"] == "QUESTION_OVER" for message in ws.messages)


@pytest.mark.asyncio
@pytest.mark.parametrize("reclaim", ["disconnected", "replace"])
@pytest.mark.parametrize("state,answered", [("QUESTION", False), ("QUESTION", True), ("LEADERBOARD", True), ("PODIUM", True)])
async def test_quiz_reconnect_restores_answer_and_results_views(reclaim, state, answered):
    room = quiz_room()
    manager = SocketManager()
    room.state = state
    room.current_question_index = 0
    room.question_start_time = time.time()
    old_ws, new_ws = Socket(), Socket()
    room.connections["old"] = old_ws
    room.players["old"] = {"nickname": "Maya", "score": 500, "prev_rank": 1, "streak": 1, "avatar": "M"}
    room.player_tokens["Maya"] = "seat-secret"
    room.teams["Maya"] = "Red"
    if answered:
        room.answered_players.add("old")
    if reclaim == "disconnected":
        room._remove_connection("old")
    room.connections["new"] = new_ws
    await manager.handle_message(room, "new", {"type": "JOIN", "nickname": "Maya", "session_token": "seat-secret"}, False)
    sync = next(message for message in new_ws.messages if message["type"] == "RECONNECTED")
    if state == "QUESTION":
        assert sync["has_answered"] is answered
        assert "answer_index" not in sync["question"]
        assert "answer" not in sync
    else:
        assert sync["leaderboard"][0]["nickname"] == "Maya"
        assert sync["leaderboard"][0]["score"] == 500
        assert sync["team_leaderboard"][0]["team"] == "Red"
    if state == "LEADERBOARD":
        assert sync["has_answered"] is answered
        assert sync["answer"] == 0
        assert sync["answer_text"] == "A"


@pytest.mark.parametrize("source", ["top_results", "leaderboard"])
def test_host_app_result_projection_strips_private_nested_fields(source):
    manager = SocketManager()
    projected = manager._safe_result_summary({
        source: [{"nickname": "Maya", "avatar": "M", "score": 500, "wallet_id": "private", "answers": ["private"]}, "invalid"],
        "winner": {"nickname": "Maya", "avatar": "M", "score": 500, "session_token": "secret"},
    })
    public = {"nickname": "Maya", "avatar": "M", "score": 500}
    assert projected["top_results"] == projected["players"] == projected["leaderboard"] == [public]
    assert projected["winner"] == public


@pytest.mark.asyncio
@pytest.mark.parametrize("reclaim", ["disconnected", "replace"])
async def test_wmlt_podium_reconnect_restores_superlatives(reclaim, monkeypatch):
    room = Room("WMLT01", {"statements": [{"text": "Arrive late?"}]}, game_type="wmlt")
    manager = SocketManager()
    room.state = "PODIUM"
    room.players["old"] = {"nickname": "Maya", "score": 500, "prev_rank": 1, "streak": 0}
    room.connections["old"] = Socket()
    room.player_tokens["Maya"] = "seat-secret"
    awards = [{"title": "Most popular", "nickname": "Maya"}]
    monkeypatch.setattr(manager, "_calculate_wmlt_superlatives", lambda _: awards)
    if reclaim == "disconnected":
        room._remove_connection("old")
    ws = Socket()
    room.connections["new"] = ws
    await manager.handle_message(room, "new", {"type": "JOIN", "nickname": "Maya", "session_token": "seat-secret"}, False)
    sync = next(message for message in ws.messages if message["type"] == "RECONNECTED")
    assert sync["superlatives"] == awards


@pytest.mark.asyncio
async def test_managed_room_reset_requires_new_session_through_party_hub():
    room = quiz_room()
    room.billing_mode = "host_app_managed"
    room.state = "PODIUM"
    room.current_question_index = 0
    ws = Socket()
    room.connections["org"] = ws
    await SocketManager().handle_message(room, "org", {"type": "RESET_ROOM", "game_type": "poker"}, True)
    assert room.state == "PODIUM"
    assert room.game_type == "quiz"
    assert ws.messages[-1]["type"] == "ERROR"
    assert "party games hub" in ws.messages[-1]["message"]


def test_runtime_callbacks_include_host_app_mirror_metadata(monkeypatch):
    captured = []

    class CaptureClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, content, headers):
            captured.append(json.loads(content))
            return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(config, "REVELRY_CALLBACK_URL", "https://revelry.example/callback")
    monkeypatch.setattr("socket_manager.httpx.Client", CaptureClient)
    SocketManager()._send_integration_callback("session.started", {
        "id": "session", "host_app": "revelry", "room_code": "ROOM01",
        "game_type": "poker", "game_id": "content", "status": "active",
        "joinable": False, "expires_at": 1700000000,
    })
    payload = captured[0]["payload"]
    assert payload["content_id"] == "content"
    assert payload["game_type"] == "poker"
    assert payload["room_code"] == "ROOM01"
    assert payload["joinable"] is False
    assert payload["expires_at"] == "2023-11-14T22:13:20Z"
    assert payload["session"]["session_id"] == "session"
