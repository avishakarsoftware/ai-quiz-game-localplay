import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from generic_prompt_engine import PHASE_REVEAL, PHASE_SUBMITTING, PHASE_VOTING
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


def recv_generic_sync(ws, phase=None, max_messages=120):
    for _ in range(max_messages):
        data = recv_until(ws, "GENERIC_PROMPT_SYNC", max_messages=max_messages)
        prompt_state = data.get("generic_prompt", {})
        if phase is None or prompt_state.get("phase") == phase:
            return data
    raise TimeoutError(f"Never received generic prompt phase {phase}")


def recv_generic_sync_matching(ws, predicate, description, max_messages=120):
    for _ in range(max_messages):
        data = recv_until(ws, "GENERIC_PROMPT_SYNC", max_messages=max_messages)
        prompt_state = data.get("generic_prompt", {})
        if predicate(prompt_state):
            return data
    raise TimeoutError(f"Never received generic prompt sync matching {description}")


def org_url(room_code, client_id="org-1"):
    return f"/ws/{room_code}/{client_id}?organizer=true"


def player_url(room_code, client_id):
    return f"/ws/{room_code}/{client_id}"


def test_generic_prompt_socket_submit_vote_reveal_and_podium(monkeypatch):
    monkeypatch.setattr(socket_manager, "start_cleanup_loop", lambda: None)
    room = socket_manager.create_room(
        "GEN001",
        {
            "game_title": "Caption Contest",
            "round_count": 3,
        },
        time_limit=30,
        organizer_token="secret",
        game_type="caption_contest",
        billing_mode="host_app_managed",
    )
    room.wallet_id = "wallet-test"

    with client.websocket_connect(org_url("GEN001")) as org_ws:
        org_ws.send_json({"type": "AUTH", "token": "secret"})
        assert org_ws.receive_json()["type"] == "ROOM_CREATED"

        player_contexts = []
        try:
            sockets = {}
            for client_id, nickname in [("p1", "Avi"), ("p2", "Ruchi")]:
                ctx = client.websocket_connect(player_url("GEN001", client_id))
                ws = ctx.__enter__()
                player_contexts.append(ctx)
                sockets[nickname] = ws
                ws.send_json({"type": "JOIN", "nickname": nickname, "avatar": "🙂"})
                joined = recv_until(ws, "JOINED_ROOM")
                assert joined["room_code"] == "GEN001"
                recv_until(org_ws, "PLAYER_JOINED")

            org_ws.send_json({"type": "START_GAME"})
            assert recv_until(org_ws, "GAME_STARTING")["game_type"] == "caption_contest"
            sync = recv_generic_sync(sockets["Avi"], phase=PHASE_SUBMITTING)
            assert sync["generic_prompt"]["game_title"] == "Caption Contest"
            assert sync["generic_prompt"]["entries"] == []

            sockets["Avi"].send_json({"type": "GENERIC_SUBMIT", "text": "The cake is doing yoga."})
            sockets["Ruchi"].send_json({"type": "GENERIC_SUBMIT", "text": "Structural frosting issue."})
            host_sync = recv_generic_sync_matching(
                org_ws,
                lambda prompt_state: (
                    prompt_state.get("phase") == PHASE_SUBMITTING
                    and prompt_state.get("submitted_count", 0) >= 2
                ),
                "two caption submissions",
            )
            assert host_sync["generic_prompt"]["submitted_count"] == 2

            org_ws.send_json({"type": "GENERIC_START_VOTING"})
            voting = recv_generic_sync(sockets["Ruchi"], phase=PHASE_VOTING)["generic_prompt"]
            # Voting is blind: authorship must not leak to other players.
            for entry in voting["entries"]:
                assert "player_id" not in entry
                assert "normalized" not in entry
            # Ruchi votes for the entry that is not her own (Avi's).
            avi_entry = next(entry for entry in voting["entries"] if not entry.get("is_mine"))
            sockets["Ruchi"].send_json({"type": "GENERIC_VOTE", "entry_id": avi_entry["entry_id"]})

            org_ws.send_json({"type": "GENERIC_REVEAL"})
            reveal = recv_generic_sync(org_ws, phase=PHASE_REVEAL)["generic_prompt"]
            assert reveal["scores"]["Avi"] == 1
            assert reveal["result"]["vote_counts"][avi_entry["entry_id"]] == 1

            org_ws.send_json({"type": "END_QUIZ"})
            podium = recv_until(org_ws, "PODIUM")
            assert podium["game_type"] == "caption_contest"
            assert podium["generic_prompt"]["phase"] == "PODIUM"
            assert podium["leaderboard"][0]["nickname"] == "Avi"
        finally:
            for ctx in reversed(player_contexts):
                ctx.__exit__(None, None, None)
