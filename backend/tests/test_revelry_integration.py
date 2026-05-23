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


def test_revelry_party_workspace_is_non_personalized(monkeypatch):
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", "test-revelry-secret")
    db.init_db()
    container_id = f"party-workspace-{uuid.uuid4().hex}"
    owner_wallet_id = f"revelry:party:{container_id}"
    pack = db.save_quiz_pack(
        owner_wallet_id,
        "Ava Trivia",
        [
            {"text": "Favorite color?", "options": ["Pink", "Blue", "Green", "Gold"], "answer_index": 0},
            {"text": "Favorite snack?", "options": ["Cake", "Chips", "Fruit", "Popcorn"], "answer_index": 1},
        ],
    )

    res = client.get(
        f"/integrations/revelry/party-workspace?external_container_id={container_id}&external_container_title=Ava",
        headers=_headers(),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["external_context"]["external_container_id"] == container_id
    assert body["active_session"] is None
    assert body["prepared_content"][0]["localplay_content_id"] == pack["id"]
    assert body["prepared_content"][0]["action_requirements"] == {
        "start": ["operate_game"],
        "edit": ["author_content"],
        "delete": ["manage_games"],
    }
    assert "can_start" not in body["prepared_content"][0]


def test_revelry_party_games_link_resolve_and_start_saved_pack(monkeypatch):
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", "test-revelry-secret")
    db.init_db()
    container_id = f"party-hub-{uuid.uuid4().hex}"
    owner_wallet_id = f"revelry:party:{container_id}"
    pack = db.save_quiz_pack(
        owner_wallet_id,
        "Hub Quiz",
        [
            {"text": "Who is hosting?", "options": ["Ava", "Bo", "Cy", "Dee"], "answer_index": 0},
            {"text": "What are we playing?", "options": ["Quiz", "Chess", "Cards", "Soccer"], "answer_index": 0},
        ],
    )
    payload = {
        "external_context": {
            "host_app": "revelry",
            "external_container_type": "party",
            "external_container_id": container_id,
            "external_container_title": "Ava's Birthday",
            "cover_image_url": "https://media.revelryapp.me/cover.jpg",
            "accent_color": "#ff4f9a",
            "return_url": "https://app.revelryapp.me/party/1?tab=games",
        },
        "actor": {
            "external_user_id": "host-1",
            "display_name": "Ava",
            "role": "host",
            "capabilities": ["manage_games", "author_content", "operate_game"],
        },
        "return_url": "https://app.revelryapp.me/party/1?tab=games",
    }

    link_res = client.post("/integrations/revelry/party-games-link", headers=_headers(), json=payload)
    assert link_res.status_code == 200
    link_body = link_res.json()
    assert "party_games_token=" in link_body["party_games_url"]
    assert link_body["display"]["container_label"] == "Ava's Birthday"
    token = link_body["party_games_url"].split("party_games_token=", 1)[1]

    resolve_res = client.get(f"/integrations/revelry/party-games/resolve?party_games_token={token}")
    assert resolve_res.status_code == 200
    resolved = resolve_res.json()
    assert resolved["launch_context"]["surface"] == "party_hub"
    assert resolved["workspace"]["prepared_content"][0]["localplay_content_id"] == pack["id"]

    start_res = client.post(
        "/integrations/revelry/party-games/start",
        json={"party_games_token": token, "content_id": pack["id"], "game_type": "quiz", "time_limit": 20},
    )
    assert start_res.status_code == 200
    start_body = start_res.json()
    assert start_body["session"]["session_id"].startswith("lp_")
    assert "launch_token=" in start_body["launch_url"]
    assert start_body["session"]["room_code"] in socket_manager.rooms


def test_revelry_authoring_link_save_and_fetch_content(monkeypatch):
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", "test-revelry-secret")
    db.init_db()
    container_id = f"party-author-{uuid.uuid4().hex}"
    payload = {
        "external_context": {
            "host_app": "revelry",
            "external_container_type": "party",
            "external_container_id": container_id,
            "external_container_title": "Ava's Birthday",
            "return_url": "https://app.revelryapp.me/party/1?tab=games",
        },
        "actor": {
            "external_user_id": "host-1",
            "display_name": "Ava",
            "role": "host",
            "capabilities": ["author_content"],
        },
        "game_type": "quiz",
        "mode": "create",
    }

    link_res = client.post("/integrations/revelry/content/authoring-link", headers=_headers(), json=payload)
    assert link_res.status_code == 200
    authoring_url = link_res.json()["authoring_url"]
    token = authoring_url.split("authoring_token=", 1)[1]

    resolve_res = client.get(f"/integrations/revelry/content/authoring-token/resolve?authoring_token={token}")
    assert resolve_res.status_code == 200
    assert resolve_res.json()["mode"] == "create"

    quiz = {
        "quiz_title": "Party Facts",
        "questions": [
            {"id": 1, "text": "What is the theme?", "options": ["Space", "Ocean", "Garden", "Disco"], "answer_index": 0, "image_prompt": ""}
        ],
    }
    save_res = client.post(
        "/integrations/revelry/content",
        headers={"Authorization": f"Bearer {token}"},
        json={"game_type": "quiz", "title": "Party Facts", "content_payload": {"quiz": quiz}},
    )
    assert save_res.status_code == 200
    body = save_res.json()
    content_id = body["localplay_content_id"]
    assert body["content"]["title"] == "Party Facts"
    assert db.get_quiz_pack(f"revelry:party:{container_id}", content_id)

    get_res = client.get(
        f"/integrations/revelry/content/{content_id}?include_payload=true&authoring_token={token}",
    )
    assert get_res.status_code == 200
    assert get_res.json()["quiz"]["quiz_title"] == "Party Facts"


def test_revelry_party_hub_can_mint_authoring_link(monkeypatch):
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", "test-revelry-secret")
    db.init_db()
    container_id = f"party-hub-author-{uuid.uuid4().hex}"
    payload = {
        "external_context": {
            "host_app": "revelry",
            "external_container_type": "party",
            "external_container_id": container_id,
            "external_container_title": "Ava's Birthday",
        },
        "actor": {
            "external_user_id": "host-1",
            "display_name": "Ava",
            "role": "host",
            "capabilities": ["author_content", "operate_game"],
        },
    }
    link_res = client.post("/integrations/revelry/party-games-link", headers=_headers(), json=payload)
    assert link_res.status_code == 200
    party_token = link_res.json()["party_games_url"].split("party_games_token=", 1)[1]

    authoring_res = client.post(
        "/integrations/revelry/party-games/authoring-link",
        json={"party_games_token": party_token, "game_type": "quiz", "mode": "create"},
    )
    assert authoring_res.status_code == 200
    assert "/revelry/author?authoring_token=" in authoring_res.json()["authoring_url"]


def test_revelry_authoring_token_can_upload_media(monkeypatch):
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", "test-revelry-secret")
    monkeypatch.setattr(config, "MEDIA_UPLOAD_URL", "https://upload.example.test/upload.php")
    monkeypatch.setattr(config, "MEDIA_PUBLIC_BASE_URL", "https://media.revelryapp.me/apps/localplay")
    monkeypatch.setattr(config, "MEDIA_UPLOAD_SECRET", "test-media-secret")
    db.init_db()
    container_id = f"party-media-{uuid.uuid4().hex}"
    payload = {
        "external_context": {
            "host_app": "revelry",
            "external_container_type": "party",
            "external_container_id": container_id,
        },
        "actor": {
            "external_user_id": "host-1",
            "display_name": "Ava",
            "role": "host",
            "capabilities": ["author_content"],
        },
        "game_type": "quiz",
        "mode": "create",
    }
    link_res = client.post("/integrations/revelry/content/authoring-link", headers=_headers(), json=payload)
    token = link_res.json()["authoring_url"].split("authoring_token=", 1)[1]

    sign_res = client.post(
        "/media/upload-url",
        headers={"Authorization": f"Bearer {token}"},
        json={"filename": "question.png", "mime_type": "image/png", "bytes": 1234, "purpose": "custom_quiz_question"},
    )
    assert sign_res.status_code == 200
    asset = sign_res.json()["asset"]
    assert asset["owner_wallet_id"] == f"revelry:party:{container_id}"
    assert asset["public_url"].startswith("https://media.revelryapp.me/apps/localplay/")
