from fastapi.testclient import TestClient
import hashlib
import hmac
import httpx
import json
import re
import uuid
from urllib.parse import parse_qs, urlparse

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


class _FakeResponse:
    def raise_for_status(self):
        return None


class _FakeAwaitable:
    def __await__(self):
        if False:
            yield None
        return None


class _FakeStatusResponse:
    def __init__(self, status_code, headers=None):
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://api-gamma.revelryapp.me/api/games/localplay/callback")
            raise httpx.HTTPStatusError("status error", request=request, response=httpx.Response(self.status_code, headers=self.headers, request=request))


class _FakeAsyncClient:
    def __init__(self, calls, *args, **kwargs):
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, content, headers):
        self.calls.append({"url": url, "body": json.loads(content.decode()), "raw": content, "headers": headers})
        return _FakeResponse()


class _FakeAsyncRetryClient:
    def __init__(self, calls, statuses, *args, **kwargs):
        self.calls = calls
        self.statuses = statuses

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, content, headers):
        self.calls.append({"url": url, "body": json.loads(content.decode()), "raw": content, "headers": headers})
        status = self.statuses.pop(0)
        return _FakeStatusResponse(status, {"Retry-After": "0"})


class _FakeSyncClient:
    def __init__(self, calls, *args, **kwargs):
        self.calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def post(self, url, content, headers):
        self.calls.append({"url": url, "body": json.loads(content.decode()), "raw": content, "headers": headers})
        return _FakeResponse()


class _FakeSyncRetryClient:
    def __init__(self, calls, statuses, *args, **kwargs):
        self.calls = calls
        self.statuses = statuses

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def post(self, url, content, headers):
        self.calls.append({"url": url, "body": json.loads(content.decode()), "raw": content, "headers": headers})
        status = self.statuses.pop(0)
        return _FakeStatusResponse(status, {"Retry-After": "0"})


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
        json={
            "scope": "organizer",
            "route": "organizer",
            "embed": True,
            "external_context": {
                "host_app": "revelry",
                "external_container_id": container_id,
                "guest_join_url": "https://app.revelryapp.me/party/party-1/games/join",
            },
            "display": {"guest_join_label": "Scan to join from Revelry"},
        },
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
    assert resolved["launch_context"]["display"]["guest_join_url"] == "https://app.revelryapp.me/party/party-1/games/join"

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


def test_revelry_callbacks_use_game_events_top_level_context_and_integration_secret(monkeypatch):
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", "test-revelry-secret")
    monkeypatch.setattr(config, "REVELRY_CALLBACK_SECRET", "different-callback-secret")
    monkeypatch.setattr(config, "REVELRY_CALLBACK_URL", "https://api-gamma.revelryapp.me/api/games/localplay/callback")
    calls = []
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda *args, **kwargs: _FakeAsyncClient(calls, *args, **kwargs))
    db.init_db()
    container_id = f"party-callback-{uuid.uuid4().hex}"

    res = client.post("/integrations/revelry/sessions", headers=_headers(), json=_create_payload(container_id))

    assert res.status_code == 200
    assert calls
    call = calls[-1]
    body = call["body"]
    assert body["event_type"] == "game.session_created"
    assert body["host_app"] == "revelry"
    assert body["external_container_type"] == "party"
    assert body["external_container_id"] == container_id
    assert body["session_id"] == res.json()["session_id"]
    assert body["idempotency_key"] == f"game.session_created:{res.json()['session_id']}:v1"
    assert re.match(r"^\d{4}-\d{2}-\d{2}T.*Z$", body["occurred_at"])
    timestamp = call["headers"]["X-LocalPlay-Timestamp"]
    expected = hmac.new(
        b"test-revelry-secret",
        f"{timestamp}.".encode() + call["raw"],
        hashlib.sha256,
    ).hexdigest()
    assert call["headers"]["X-LocalPlay-Signature"] == f"sha256={expected}"


def test_revelry_callback_retries_after_429(monkeypatch):
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", "test-revelry-secret")
    monkeypatch.setattr(config, "REVELRY_CALLBACK_URL", "https://api-gamma.revelryapp.me/api/games/localplay/callback")
    calls = []
    statuses = [429, 200]
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda *args, **kwargs: _FakeAsyncRetryClient(calls, statuses, *args, **kwargs))
    monkeypatch.setattr(main.asyncio, "sleep", lambda _delay: _FakeAwaitable())
    db.init_db()

    res = client.post("/integrations/revelry/sessions", headers=_headers(), json=_create_payload(f"party-429-{uuid.uuid4().hex}"))

    assert res.status_code == 200
    assert len(calls) == 2
    assert calls[0]["body"]["event_id"] == calls[1]["body"]["event_id"]
    assert calls[0]["raw"] == calls[1]["raw"]


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


def test_revelry_session_replacement_sends_superseded_callback(monkeypatch):
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", "test-revelry-secret")
    monkeypatch.setattr(config, "REVELRY_CALLBACK_URL", "https://api-gamma.revelryapp.me/api/games/localplay/callback")
    calls = []
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda *args, **kwargs: _FakeAsyncClient(calls, *args, **kwargs))
    db.init_db()
    container_id = f"party-replace-callback-{uuid.uuid4().hex}"
    first = client.post("/integrations/revelry/sessions", headers=_headers(), json=_create_payload(container_id))
    payload = _create_payload(container_id)
    payload["replace_session_id"] = first.json()["session_id"]
    payload["replacement_confirmed"] = True

    replacement = client.post("/integrations/revelry/sessions", headers=_headers(), json=payload)

    assert replacement.status_code == 200
    events = [call["body"]["event_type"] for call in calls]
    assert "game.superseded" in events
    superseded = next(call["body"] for call in calls if call["body"]["event_type"] == "game.superseded")
    assert superseded["session_id"] == first.json()["session_id"]
    assert superseded["payload"]["status"] == "superseded"


def test_revelry_results_endpoint_returns_safe_summary(monkeypatch):
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", "test-revelry-secret")
    db.init_db()
    session_id = f"lp_{uuid.uuid4().hex}"
    db.create_game_session({
        "id": session_id,
        "host_app": "revelry",
        "external_container_id": "party-safe-results",
        "external_container_type": "party",
        "game_type": "quiz",
        "game_id": "quiz-1",
        "game_title": "Secret Answer Quiz",
        "room_code": "SAFE01",
        "organizer_token": "org",
        "status": "complete",
        "joinable": False,
        "result_summary": {
            "game_title": "Secret Answer Quiz",
            "game_type": "quiz",
            "player_count": 1,
            "leaderboard": [{"nickname": "Ava", "avatar": "🎉", "score": 100}],
            "answer_log": [{"answer_index": 2, "correct": True}],
        },
    })

    res = client.get(f"/integrations/revelry/sessions/{session_id}/results", headers=_headers())

    assert res.status_code == 200
    body = res.json()
    assert body["result_summary"]["title"] == "Secret Answer Quiz"
    assert body["result_summary"]["top_results"] == [{"nickname": "Ava", "avatar": "🎉", "score": 100}]
    assert "answer_log" not in json.dumps(body)


def test_runtime_callback_uses_safe_result_summary_and_game_event(monkeypatch):
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", "test-revelry-secret")
    monkeypatch.setattr(config, "REVELRY_CALLBACK_URL", "https://api-gamma.revelryapp.me/api/games/localplay/callback")
    calls = []
    monkeypatch.setattr("socket_manager.httpx.Client", lambda *args, **kwargs: _FakeSyncClient(calls, *args, **kwargs))

    socket_manager._send_integration_callback(
        "session.completed",
        {
            "id": "lp_runtime",
            "host_app": "revelry",
            "external_container_type": "party",
            "external_container_id": "party-runtime",
            "room_code": "RUN123",
            "status": "complete",
            "game_type": "quiz",
            "game_title": "Runtime Quiz",
        },
        {
            "game_title": "Runtime Quiz",
            "game_type": "quiz",
            "player_count": 1,
            "leaderboard": [{"nickname": "Ava", "avatar": "🎉", "score": 100}],
            "answer_log": [{"answer_index": 0, "correct": True}],
        },
    )

    assert calls
    body = calls[0]["body"]
    assert body["event_type"] == "game.completed"
    assert body["host_app"] == "revelry"
    assert body["external_container_id"] == "party-runtime"
    assert body["session_id"] == "lp_runtime"
    assert re.match(r"^\d{4}-\d{2}-\d{2}T.*Z$", body["occurred_at"])
    assert body["payload"]["result_summary"]["top_results"] == [{"nickname": "Ava", "avatar": "🎉", "score": 100}]
    assert "answer_log" not in json.dumps(body)


def test_runtime_callback_retries_after_429(monkeypatch):
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", "test-revelry-secret")
    monkeypatch.setattr(config, "REVELRY_CALLBACK_URL", "https://api-gamma.revelryapp.me/api/games/localplay/callback")
    calls = []
    statuses = [429, 200]
    monkeypatch.setattr("socket_manager.httpx.Client", lambda *args, **kwargs: _FakeSyncRetryClient(calls, statuses, *args, **kwargs))
    monkeypatch.setattr("socket_manager.time.sleep", lambda _delay: None)

    socket_manager._send_integration_callback(
        "session.started",
        {
            "id": "lp_runtime_429",
            "host_app": "revelry",
            "external_container_type": "party",
            "external_container_id": "party-runtime-429",
            "room_code": "RUN429",
            "status": "active",
            "game_type": "quiz",
            "game_title": "Runtime Quiz",
        },
    )

    assert len(calls) == 2
    assert calls[0]["body"]["event_id"] == calls[1]["body"]["event_id"]
    assert calls[0]["raw"] == calls[1]["raw"]


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
            "guest_join_url": "https://app.revelryapp.me/party/1/games/join",
        },
        "actor": {
            "external_user_id": "host-1",
            "display_name": "Ava",
            "role": "host",
            "capabilities": ["manage_games", "author_content", "operate_game"],
        },
        "return_url": "https://app.revelryapp.me/party/1?tab=games",
        "display": {
            "guest_join_label": "Scan to join Ava's Birthday",
        },
    }

    link_res = client.post("/integrations/revelry/party-games-link", headers=_headers(), json=payload)
    assert link_res.status_code == 200
    link_body = link_res.json()
    assert "party_games_token=" in link_body["party_games_url"]
    assert link_body["display"]["container_label"] == "Ava's Birthday"
    assert link_body["display"]["guest_join_url"] == "https://app.revelryapp.me/party/1/games/join"
    assert link_body["display"]["guest_join_label"] == "Scan to join Ava's Birthday"
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
    launch_token = start_body["launch_url"].split("launch_token=", 1)[1].split("&", 1)[0]
    launch_res = client.get(f"/integrations/revelry/launch-token/resolve?scope=organizer&launch_token={launch_token}")
    assert launch_res.status_code == 200
    launch_context = launch_res.json()["launch_context"]
    assert launch_context["display"]["guest_join_url"] == "https://app.revelryapp.me/party/1/games/join"
    assert launch_context["display"]["guest_join_label"] == "Scan to join Ava's Birthday"
    assert "/revelry/games?party_games_token=" in launch_context["party_hub_url"]


def test_revelry_party_games_link_can_mint_start_intent_url(monkeypatch):
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", "test-revelry-secret")
    db.init_db()
    container_id = f"party-start-link-{uuid.uuid4().hex}"
    owner_wallet_id = f"revelry:party:{container_id}"
    pack = db.save_quiz_pack(
        owner_wallet_id,
        "Start Intent Quiz",
        [{"text": "Start?", "options": ["Yes", "No", "Maybe", "Later"], "answer_index": 0}],
    )
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
            "capabilities": ["manage_games", "author_content", "operate_game"],
        },
        "intent": "start",
        "content_id": pack["id"],
        "game_type": "quiz",
        "time_limit": 30,
    }

    link_res = client.post("/integrations/revelry/party-games-link", headers=_headers(), json=payload)

    assert link_res.status_code == 200
    start_url = link_res.json()["start_url"]
    assert "/integrations/revelry/games?party_games_token=" in start_url
    assert f"start_content_id={pack['id']}" in start_url
    assert "time_limit=30" in start_url
    route_res = client.get(start_url.replace("http://testserver", ""), follow_redirects=False)
    assert route_res.status_code == 302
    assert f"start_content_id={pack['id']}" in route_res.headers["location"]


def test_revelry_party_games_start_url_encodes_query_values(monkeypatch):
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", "test-revelry-secret")
    db.init_db()
    payload = {
        "external_context": {
            "host_app": "revelry",
            "external_container_type": "party",
            "external_container_id": f"party-start-encoding-{uuid.uuid4().hex}",
            "external_container_title": "Ava's Birthday",
        },
        "actor": {
            "external_user_id": "host-1",
            "display_name": "Ava",
            "role": "host",
            "capabilities": ["manage_games", "author_content", "operate_game"],
        },
        "intent": "start",
        "content_id": "pack&evil=1",
        "game_type": "quiz",
        "time_limit": 30,
    }

    link_res = client.post("/integrations/revelry/party-games-link", headers=_headers(), json=payload)

    assert link_res.status_code == 200
    parsed = urlparse(link_res.json()["start_url"])
    query = parse_qs(parsed.query)
    assert query["start_content_id"] == ["pack&evil=1"]
    assert "evil" not in query

    route_res = client.get(link_res.json()["start_url"].replace("http://testserver", ""), follow_redirects=False)
    assert route_res.status_code == 302
    redirected = parse_qs(urlparse(route_res.headers["location"]).query)
    assert redirected["start_content_id"] == ["pack&evil=1"]
    assert "evil" not in redirected


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


def test_revelry_editing_used_content_creates_new_version(monkeypatch):
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", "test-revelry-secret")
    monkeypatch.setattr(config, "REVELRY_CALLBACK_URL", "https://api-gamma.revelryapp.me/api/games/localplay/callback")
    calls = []
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda *args, **kwargs: _FakeAsyncClient(calls, *args, **kwargs))
    db.init_db()
    container_id = f"party-version-{uuid.uuid4().hex}"
    owner_wallet_id = f"revelry:party:{container_id}"
    pack = db.save_quiz_pack(
        owner_wallet_id,
        "Played Quiz",
        [{"text": "Original?", "options": ["Yes", "No", "Maybe", "Later"], "answer_index": 0}],
    )
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
            "capabilities": ["manage_games", "author_content", "operate_game"],
        },
    }
    link_res = client.post("/integrations/revelry/party-games-link", headers=_headers(), json=payload)
    party_token = link_res.json()["party_games_url"].split("party_games_token=", 1)[1]
    start_res = client.post(
        "/integrations/revelry/party-games/start",
        json={"party_games_token": party_token, "content_id": pack["id"], "game_type": "quiz"},
    )
    assert start_res.status_code == 200

    edit_link_res = client.post(
        "/integrations/revelry/party-games/authoring-link",
        json={"party_games_token": party_token, "game_type": "quiz", "mode": "edit", "content_id": pack["id"]},
    )
    token = edit_link_res.json()["authoring_url"].split("authoring_token=", 1)[1]
    edited_quiz = {
        "quiz_title": "Played Quiz Edited",
        "questions": [{"id": 1, "text": "Edited?", "options": ["Yes", "No", "Maybe", "Later"], "answer_index": 0, "image_prompt": ""}],
    }
    save_res = client.post(
        "/integrations/revelry/content",
        headers={"Authorization": f"Bearer {token}"},
        json={"game_type": "quiz", "title": "Played Quiz Edited", "content_payload": {"quiz": edited_quiz}},
    )

    assert save_res.status_code == 200
    body = save_res.json()
    assert body["previous_content_id"] == pack["id"]
    assert body["localplay_content_id"] != pack["id"]
    assert db.get_quiz_pack(owner_wallet_id, pack["id"])["title"] == "Played Quiz"
    assert db.get_quiz_pack(owner_wallet_id, body["localplay_content_id"])["title"] == "Played Quiz Edited"
    created = [call["body"] for call in calls if call["body"]["event_type"] == "content.created"]
    assert created
    assert created[-1]["previous_content_id"] == pack["id"]
    assert created[-1]["content_id"] == body["localplay_content_id"]


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


def test_revelry_party_hub_delete_sends_content_deleted_callback(monkeypatch):
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", "test-revelry-secret")
    monkeypatch.setattr(config, "REVELRY_CALLBACK_URL", "https://api-gamma.revelryapp.me/api/games/localplay/callback")
    calls = []
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda *args, **kwargs: _FakeAsyncClient(calls, *args, **kwargs))
    db.init_db()
    container_id = f"party-delete-{uuid.uuid4().hex}"
    owner_wallet_id = f"revelry:party:{container_id}"
    pack = db.save_quiz_pack(
        owner_wallet_id,
        "Delete Me",
        [{"text": "Keep?", "options": ["No", "Yes", "Maybe", "Later"], "answer_index": 0}],
    )
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
            "capabilities": ["manage_games", "author_content", "operate_game"],
        },
    }
    link_res = client.post("/integrations/revelry/party-games-link", headers=_headers(), json=payload)
    party_token = link_res.json()["party_games_url"].split("party_games_token=", 1)[1]

    delete_res = client.request(
        "DELETE",
        f"/integrations/revelry/party-games/content/{pack['id']}",
        json={"party_games_token": party_token},
    )

    assert delete_res.status_code == 200
    assert delete_res.json()["status"] == "deleted_by_host"
    assert db.get_quiz_pack(owner_wallet_id, pack["id"]) is None
    deleted = [call["body"] for call in calls if call["body"]["event_type"] == "content.deleted"]
    assert deleted
    assert deleted[-1]["content_id"] == pack["id"]
    assert deleted[-1]["external_container_id"] == container_id
    assert re.match(r"^\d{4}-\d{2}-\d{2}T.*Z$", deleted[-1]["occurred_at"])


def test_revelry_authoring_token_can_delete_scoped_content(monkeypatch):
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", "test-revelry-secret")
    monkeypatch.setattr(config, "REVELRY_CALLBACK_URL", "https://api-gamma.revelryapp.me/api/games/localplay/callback")
    calls = []
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda *args, **kwargs: _FakeAsyncClient(calls, *args, **kwargs))
    db.init_db()
    container_id = f"party-author-delete-{uuid.uuid4().hex}"
    owner_wallet_id = f"revelry:party:{container_id}"
    pack = db.save_quiz_pack(
        owner_wallet_id,
        "Author Delete",
        [{"text": "Delete?", "options": ["Yes", "No", "Maybe", "Later"], "answer_index": 0}],
    )
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
        "mode": "edit",
        "content_id": pack["id"],
    }
    link_res = client.post("/integrations/revelry/content/authoring-link", headers=_headers(), json=payload)
    token = link_res.json()["authoring_url"].split("authoring_token=", 1)[1]

    delete_res = client.delete(
        f"/integrations/revelry/content/{pack['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert delete_res.status_code == 200
    assert db.get_quiz_pack(owner_wallet_id, pack["id"]) is None
    deleted = [call["body"] for call in calls if call["body"]["event_type"] == "content.deleted"]
    assert deleted
    assert deleted[-1]["payload"]["content"]["status"] == "deleted_by_host"


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
    assert "revelry_party_" in asset["storage_path"]
    assert ":" not in asset["storage_path"]
