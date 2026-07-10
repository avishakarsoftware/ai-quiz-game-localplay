import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from main import app, game_history
from party_quests_engine import PHASE_FINAL_CALL, PHASE_REVEAL
from socket_manager import socket_manager


client = TestClient(app)


def _teardown_rooms():
    for room in socket_manager.rooms.values():
        if room.timer_task:
            room.timer_task.cancel()
            room.timer_task = None
        if getattr(room, "mafia_timer_task", None):
            room.mafia_timer_task.cancel()
            room.mafia_timer_task = None
        if room._organizer_cleanup_task:
            room._organizer_cleanup_task.cancel()
            room._organizer_cleanup_task = None
    socket_manager.rooms.clear()
    socket_manager.stop_cleanup_loop()


@pytest.fixture(autouse=True)
def clear_state():
    _teardown_rooms()
    game_history.clear()
    saved_origins = socket_manager.allowed_origins
    socket_manager.allowed_origins = []
    yield
    _teardown_rooms()
    game_history.clear()
    socket_manager.allowed_origins = saved_origins


def recv_until(ws, msg_type, max_messages=80):
    for index in range(max_messages):
        try:
            data = ws.receive_json()
        except Exception as exc:
            raise TimeoutError(f"Connection closed while waiting for {msg_type} after {index} messages: {exc}")
        if data.get("type") == msg_type:
            return data
    raise TimeoutError(f"Never received {msg_type}")


def recv_quests_sync(ws, phase=None, max_messages=120):
    for _ in range(max_messages):
        data = recv_until(ws, "QUESTS_SYNC", max_messages=max_messages)
        quests = data.get("party_quests", {})
        if phase is None or quests.get("phase") == phase:
            return quests
    raise TimeoutError(f"Never received Party Quests phase {phase}")


def recv_quests_sync_matching(ws, predicate, description, max_messages=120):
    for _ in range(max_messages):
        quests = recv_quests_sync(ws, max_messages=max_messages)
        if predicate(quests):
            return quests
    raise TimeoutError(f"Never received Party Quests sync matching {description}")


def org_url(room_code, client_id="org-1"):
    return f"/ws/{room_code}/{client_id}?organizer=true"


def player_url(room_code, client_id):
    return f"/ws/{room_code}/{client_id}"


def test_party_quests_socket_confirmation_late_join_and_reveal(monkeypatch):
    monkeypatch.setattr(socket_manager, "start_cleanup_loop", lambda: None)
    room = socket_manager.create_room(
        "QUEST1",
        {
            "game_title": "Party Quests",
            "quests_per_player": 3,
            "duration_minutes": 30,
            "allow_late_join": True,
        },
        time_limit=30,
        organizer_token="secret",
        game_type="party_quests",
        billing_mode="host_app_managed",
    )
    room.wallet_id = "wallet-test"

    with client.websocket_connect(org_url("QUEST1")) as org_ws:
        org_ws.send_json({"type": "AUTH", "token": "secret"})
        assert org_ws.receive_json()["type"] == "ROOM_CREATED"

        player_contexts = []
        try:
            sockets = {}
            for client_id, nickname in [("p1", "Avi"), ("p2", "Ruchi")]:
                ctx = client.websocket_connect(player_url("QUEST1", client_id))
                ws = ctx.__enter__()
                player_contexts.append(ctx)
                sockets[nickname] = ws
                ws.send_json({"type": "JOIN", "nickname": nickname, "avatar": "🙂"})
                assert recv_until(ws, "JOINED_ROOM")["room_code"] == "QUEST1"
                recv_until(org_ws, "PLAYER_JOINED")

            org_ws.send_json({"type": "START_GAME"})
            assert recv_until(org_ws, "GAME_STARTING")["game_type"] == "party_quests"
            avi_sync = recv_quests_sync(sockets["Avi"])
            assert avi_sync["phase"] == "QUESTS_ACTIVE"
            assert len(avi_sync["my_board"]) == 3

            quest_id = avi_sync["my_board"][0]["quest_id"]
            sockets["Avi"].send_json({
                "type": "QUESTS_REQUEST_CONFIRMATION",
                "quest_id": quest_id,
                "partner_player_id": "Ruchi",
            })
            ack = recv_until(sockets["Avi"], "QUESTS_REQUEST_ACK")
            assert ack["request_id"]

            ruchi_sync = recv_quests_sync_matching(
                sockets["Ruchi"],
                lambda quests: bool(quests.get("incoming_requests")),
                "incoming confirmation request",
            )
            assert ruchi_sync["incoming_requests"][0]["id"] == ack["request_id"]
            sockets["Ruchi"].send_json({
                "type": "QUESTS_CONFIRM",
                "request_id": ack["request_id"],
                "accepted": True,
            })
            avi_confirmed = recv_quests_sync_matching(
                sockets["Avi"],
                lambda quests: any(
                    item["quest_id"] == quest_id and item["status"] == "confirmed"
                    for item in quests.get("my_board", [])
                ),
                "confirmed quest",
            )
            confirmed_item = next(item for item in avi_confirmed["my_board"] if item["quest_id"] == quest_id)
            assert confirmed_item["status"] == "confirmed"
            assert confirmed_item["confirmed_by_player_id"] == "Ruchi"
            assert avi_confirmed["my_score"] > 0

            late_ctx = client.websocket_connect(player_url("QUEST1", "p3"))
            late_ws = late_ctx.__enter__()
            player_contexts.append(late_ctx)
            late_ws.send_json({"type": "JOIN", "nickname": "Ashu", "avatar": "😎"})
            late_join = recv_until(late_ws, "JOINED_ROOM")
            assert late_join["game_type"] == "party_quests"
            assert late_join["party_quests"]["phase"] == "QUESTS_ACTIVE"
            assert len(late_join["party_quests"]["my_board"]) == 3
            assert "Ashu" in {player["nickname"] for player in late_join["party_quests"]["players"]}

            org_ws.send_json({"type": "QUESTS_FINAL_CALL"})
            assert recv_quests_sync(org_ws, phase=PHASE_FINAL_CALL)["phase"] == PHASE_FINAL_CALL
            org_ws.send_json({"type": "QUESTS_REVEAL"})
            reveal = recv_quests_sync(org_ws, phase=PHASE_REVEAL)
            assert reveal["phase"] == PHASE_REVEAL
            assert any(row["nickname"] == "Avi" and row["score"] > 0 for row in reveal["standings"])
        finally:
            for ctx in reversed(player_contexts):
                ctx.__exit__(None, None, None)


def test_party_quests_checkin_auto_starts_when_first_guest_joins(monkeypatch):
    monkeypatch.setattr(socket_manager, "start_cleanup_loop", lambda: None)
    room = socket_manager.create_room(
        "AUTOQ1",
        {
            "game_title": "Check-in Party Quests",
            "quests": [
                "Meet someone who knows a campfire song.",
                "Find someone who can recommend a trail snack.",
                "Meet someone who has tried rafting.",
            ],
            "quests_per_player": 3,
            "duration_minutes": 30,
            "allow_late_join": True,
            "default_for_checkin": True,
            "auto_start_on_first_checkin": True,
        },
        time_limit=30,
        organizer_token="secret",
        game_type="party_quests",
        billing_mode="host_app_managed",
    )
    room.wallet_id = "revelry:party:auto-checkin"

    with client.websocket_connect(player_url("AUTOQ1", "p1")) as player_ws:
        player_ws.send_json({"type": "JOIN", "nickname": "Avi", "avatar": "🙂"})

        assert recv_until(player_ws, "JOINED_ROOM")["room_code"] == "AUTOQ1"
        assert recv_until(player_ws, "GAME_STARTING")["game_type"] == "party_quests"
        sync = recv_quests_sync(player_ws)
        assert sync["phase"] == "QUESTS_ACTIVE"
        assert len(sync["my_board"]) == 3
        assert room.state == "QUESTS_ACTIVE"


def test_party_quests_checkin_can_wait_for_host_start(monkeypatch):
    monkeypatch.setattr(socket_manager, "start_cleanup_loop", lambda: None)
    room = socket_manager.create_room(
        "WAITQ1",
        {
            "game_title": "Host-paced Party Quests",
            "quests_per_player": 3,
            "default_for_checkin": True,
            "auto_start_on_first_checkin": False,
        },
        organizer_token="secret",
        game_type="party_quests",
        billing_mode="host_app_managed",
    )
    room.wallet_id = "revelry:party:host-paced"

    with client.websocket_connect(player_url("WAITQ1", "p1")) as player_ws:
        player_ws.send_json({"type": "JOIN", "nickname": "Avi", "avatar": "🙂"})
        assert recv_until(player_ws, "JOINED_ROOM")["room_code"] == "WAITQ1"
        assert room.state == "LOBBY"
        assert room.party_quests_state == {}
