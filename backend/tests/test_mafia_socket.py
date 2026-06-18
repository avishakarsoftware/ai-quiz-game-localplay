import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from main import app, game_history
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


def recv_mafia_phase(ws, phase, max_messages=120):
    for index in range(max_messages):
        data = recv_until(ws, "MAFIA_SYNC", max_messages=max_messages)
        current = data.get("mafia", {}).get("phase")
        if current == phase:
            return data["mafia"]
    raise TimeoutError(f"Never received Mafia phase {phase}")


def org_url(room_code, client_id="org-1"):
    return f"/ws/{room_code}/{client_id}?organizer=true"


def player_url(room_code, client_id):
    return f"/ws/{room_code}/{client_id}"


def test_mafia_start_sends_private_roles_and_public_redacts_living_roles(monkeypatch):
    monkeypatch.setattr(socket_manager, "start_cleanup_loop", lambda: None)
    room = socket_manager.create_room(
        "MAFIA1",
        {"game_title": "Mafia", "role_reveal_seconds": 20},
        time_limit=30,
        organizer_token="secret",
        game_type="mafia",
        billing_mode="host_app_managed",
    )
    room.wallet_id = "wallet-test"

    with client.websocket_connect(org_url("MAFIA1")) as org_ws:
        org_ws.send_json({"type": "AUTH", "token": "secret"})
        assert org_ws.receive_json()["type"] == "ROOM_CREATED"

        player_contexts = []
        player_sockets = []
        try:
            for index in range(6):
                ctx = client.websocket_connect(player_url("MAFIA1", f"p{index}"))
                ws = ctx.__enter__()
                player_contexts.append(ctx)
                player_sockets.append(ws)
                ws.send_json({"type": "JOIN", "nickname": f"P{index}", "avatar": "🙂"})
                assert recv_until(ws, "JOINED_ROOM")["room_code"] == "MAFIA1"
                recv_until(org_ws, "PLAYER_JOINED")

            org_ws.send_json({"type": "START_GAME"})
            recv_until(org_ws, "GAME_STARTING")
            public = recv_until(org_ws, "MAFIA_SYNC")

            assert public["game_type"] == "mafia"
            assert public["mafia"]["phase"] == "MAFIA_ROLE_REVEAL"
            assert "my_role" not in public["mafia"]
            assert all(player["role"] is None for player in public["mafia"]["players"])

            private_roles = []
            for ws in player_sockets:
                recv_until(ws, "GAME_STARTING")
                private = recv_until(ws, "MAFIA_SYNC")
                private_roles.append(private["mafia"]["my_role"])
                assert private["mafia"]["my_action"]["kind"] == "none"

            assert private_roles.count("mafia") == 1
            assert "detective" in private_roles
            assert "doctor" in private_roles
            assert room.locked is True
        finally:
            for ctx in reversed(player_contexts):
                ctx.__exit__(None, None, None)


def test_mafia_socket_flow_resolves_night_vote_and_podium(monkeypatch):
    monkeypatch.setattr(socket_manager, "start_cleanup_loop", lambda: None)
    room = socket_manager.create_room(
        "MAFIA2",
        {
            "game_title": "Mafia",
            "role_reveal_seconds": 20,
            "night_timer_seconds": 20,
            "discussion_timer_seconds": 20,
            "vote_timer_seconds": 20,
        },
        time_limit=30,
        organizer_token="secret",
        game_type="mafia",
        billing_mode="host_app_managed",
    )
    room.wallet_id = "wallet-test"

    with client.websocket_connect(org_url("MAFIA2")) as org_ws:
        org_ws.send_json({"type": "AUTH", "token": "secret"})
        assert org_ws.receive_json()["type"] == "ROOM_CREATED"

        player_contexts = []
        player_sockets = {}
        try:
            for index in range(6):
                nickname = f"P{index}"
                ctx = client.websocket_connect(player_url("MAFIA2", f"p{index}"))
                ws = ctx.__enter__()
                player_contexts.append(ctx)
                player_sockets[nickname] = ws
                ws.send_json({"type": "JOIN", "nickname": nickname, "avatar": "🙂"})
                assert recv_until(ws, "JOINED_ROOM")["room_code"] == "MAFIA2"
                recv_until(org_ws, "PLAYER_JOINED")

            org_ws.send_json({"type": "START_GAME"})
            recv_until(org_ws, "GAME_STARTING")
            role_reveal_public = recv_until(org_ws, "MAFIA_SYNC")["mafia"]
            assert role_reveal_public["phase"] == "MAFIA_ROLE_REVEAL"
            assert all(player["role"] is None for player in role_reveal_public["players"])

            role_by_nickname = {}
            for nickname, ws in player_sockets.items():
                recv_until(ws, "GAME_STARTING")
                private = recv_until(ws, "MAFIA_SYNC")["mafia"]
                role_by_nickname[nickname] = private["my_role"]

            mafia_player = next(nick for nick, role in role_by_nickname.items() if role == "mafia")
            detective_player = next(nick for nick, role in role_by_nickname.items() if role == "detective")
            doctor_player = next(nick for nick, role in role_by_nickname.items() if role == "doctor")
            villager_targets = [nick for nick, role in role_by_nickname.items() if role == "villager"]
            night_target = villager_targets[0]
            doctor_target = villager_targets[1]

            org_ws.send_json({"type": "MAFIA_SKIP_TIMER"})
            night_public = recv_until(org_ws, "MAFIA_SYNC")["mafia"]
            assert night_public["phase"] == "MAFIA_NIGHT"

            player_sockets[mafia_player].send_json({"type": "MAFIA_NIGHT_ACTION", "target": night_target})
            assert recv_until(player_sockets[mafia_player], "MAFIA_NIGHT_ACTION_ACK")["target"] == night_target
            player_sockets[detective_player].send_json({"type": "MAFIA_NIGHT_ACTION", "target": mafia_player})
            assert recv_until(player_sockets[detective_player], "MAFIA_NIGHT_ACTION_ACK")["target"] == mafia_player
            player_sockets[doctor_player].send_json({"type": "MAFIA_NIGHT_ACTION", "target": doctor_target})
            assert recv_until(player_sockets[doctor_player], "MAFIA_NIGHT_ACTION_ACK")["target"] == doctor_target
            for nickname, ws in player_sockets.items():
                target = mafia_player if nickname != mafia_player else night_target
                ws.send_json({"type": "MAFIA_NIGHT_READ", "target": target})
                assert recv_until(ws, "MAFIA_NIGHT_READ_ACK")["target"] == target

            day_public = recv_mafia_phase(org_ws, "MAFIA_DAY_DISCUSSION")
            assert day_public["last_night"]["killed"] == night_target
            assert day_public["last_night"]["killed_role"] == "villager"
            assert "mafia_target" not in day_public["last_night"]
            assert day_public["last_night"]["night_read_highlights"]
            alive_players = {player["nickname"]: player for player in day_public["players"] if player["alive"]}
            assert all(player["role"] is None for player in alive_players.values())

            detective_sync = recv_mafia_phase(player_sockets[detective_player], "MAFIA_DAY_DISCUSSION")
            assert detective_sync["my_investigations"] == [
                {"round": 1, "target": mafia_player, "result": "mafia"}
            ]

            org_ws.send_json({"type": "MAFIA_SKIP_TIMER"})
            vote_public = recv_mafia_phase(org_ws, "MAFIA_DAY_VOTE")

            for nickname in alive_players:
                target = "skip" if nickname == mafia_player else mafia_player
                player_sockets[nickname].send_json({"type": "MAFIA_VOTE", "target": target})
                assert recv_until(player_sockets[nickname], "MAFIA_VOTE_ACK")["target"] == target

            podium = recv_until(org_ws, "PODIUM")
            assert podium["game_type"] == "mafia"
            assert podium["mafia"]["phase"] == "PODIUM"
            assert podium["mafia"]["winner"] == "town"
            assert any(
                player["nickname"] == mafia_player and player["role"] == "mafia"
                for player in podium["mafia"]["players"]
            )
            assert game_history[-1]["mafia_result"]["winner"] == "town"
        finally:
            for ctx in reversed(player_contexts):
                ctx.__exit__(None, None, None)
