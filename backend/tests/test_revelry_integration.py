from fastapi.testclient import TestClient
import uuid

import config
import db
import main
from main import app
from socket_manager import socket_manager


client = TestClient(app)


def setup_function():
    socket_manager.rooms.clear()
    socket_manager.allowed_origins = []


def _headers():
    return {"Authorization": "Bearer test-revelry-secret"}


def _create_payload(container_id: str = "", game_type: str = "quiz"):
    container_id = container_id or f"party-{uuid.uuid4().hex}"
    host_user_id = f"host-{container_id}"
    return {
        "game_type": game_type,
        "settings": {"time_limit": 20},
        "external_context": {
            "host_app": "revelry",
            "external_container_type": "party",
            "external_container_id": container_id,
            "external_container_title": "Ava's Birthday",
            "host_user_id": host_user_id,
            "return_url": "https://app.revelryapp.me/parties/party-1",
        },
        "actor": {
            "external_user_id": host_user_id,
            "display_name": "Ava",
            "role": "host",
            "capabilities": ["manage_games", "operate_game"],
        },
    }


def test_catalog_lists_launchable_games():
    res = client.get("/catalog?host_app=revelry")
    assert res.status_code == 200
    game_ids = {game["id"] for game in res.json()["games"]}
    assert {"quiz", "wmlt", "drawing"}.issubset(game_ids)


def test_revelry_session_create_launch_token_and_status(monkeypatch):
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", "test-revelry-secret")
    db.init_db()
    container_id = f"party-create-{uuid.uuid4().hex}"

    res = client.post("/integrations/revelry/sessions", headers=_headers(), json=_create_payload(container_id))
    assert res.status_code == 200
    body = res.json()
    assert body["session_id"].startswith("lp_")
    assert body["room_code"] in socket_manager.rooms
    assert body["status"] == "lobby"
    assert body["launch_routes"]["organizer"]["path"].endswith("/organizer")
    session = db.get_game_session(body["session_id"])
    assert session
    assert db.get_wallet_balance(f"revelry:host-{container_id}") == 0
    assert socket_manager.rooms[body["room_code"]].billing_mode == "host_app_managed"

    token_res = client.post(
        f"/integrations/revelry/sessions/{body['session_id']}/launch-token",
        headers=_headers(),
        json={"scope": "organizer", "route": "organizer", "embed": True},
    )
    assert token_res.status_code == 200
    launch = token_res.json()
    assert "launch_token=" in launch["launch_url"]
    assert launch["launch_token_expires_at"]

    token = launch["launch_url"].split("launch_token=", 1)[1].split("&", 1)[0]
    resolve_res = client.get(f"/integrations/revelry/launch-token/resolve?scope=organizer&launch_token={token}")
    assert resolve_res.status_code == 200
    resolved = resolve_res.json()
    assert resolved["room_code"] == body["room_code"]
    assert resolved["organizer_token"]

    status_res = client.get(f"/integrations/revelry/sessions/{body['session_id']}", headers=_headers())
    assert status_res.status_code == 200
    assert status_res.json()["joinable"] is True

    route_res = client.get(
        f"/sessions/{body['session_id']}/organizer?embed=1&launch_token={token}",
        follow_redirects=False,
    )
    assert route_res.status_code == 302
    assert route_res.headers["location"].startswith(f"/organizer?session_id={body['session_id']}")

    with client.websocket_connect(f"/ws/{body['room_code']}/org-1?organizer=true") as ws:
        ws.send_json({"type": "AUTH", "token": session["organizer_token"]})
        assert ws.receive_json()["type"] == "ROOM_CREATED"
        ws.send_json({"type": "START_GAME"})
        assert ws.receive_json()["type"] == "GAME_STARTING"


def test_revelry_session_replacement_requires_confirmation(monkeypatch):
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", "test-revelry-secret")
    db.init_db()
    container_id = f"party-replace-{uuid.uuid4().hex}"

    first = client.post("/integrations/revelry/sessions", headers=_headers(), json=_create_payload(container_id))
    assert first.status_code == 200
    first_id = first.json()["session_id"]

    conflict = client.post("/integrations/revelry/sessions", headers=_headers(), json=_create_payload(container_id))
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "active_session_exists"

    payload = _create_payload(container_id)
    payload["replace_session_id"] = first_id
    payload["replacement_confirmed"] = True
    replacement = client.post("/integrations/revelry/sessions", headers=_headers(), json=payload)
    assert replacement.status_code == 200
    replacement_id = replacement.json()["session_id"]

    old = db.get_game_session(first_id)
    assert old["status"] == "superseded"
    assert old["joinable"] is False
    assert old["superseded_by_session_id"] == replacement_id
