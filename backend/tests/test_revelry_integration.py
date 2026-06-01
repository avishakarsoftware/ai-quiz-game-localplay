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
    games = res.json()["games"]
    game_ids = {game["id"] for game in games}
    assert {"quiz", "wmlt", "drawing"}.issubset(game_ids)
    quiz = next(game for game in games if game["id"] == "quiz")
    drawing = next(game for game in games if game["id"] == "drawing")
    assert quiz["can_create_content"] is True
    assert quiz["embedded_authoring_supported"] is True
    assert quiz["supports_ai_generation"] is True
    assert "manual" in quiz["creation_modes"]
    assert "ai" in quiz["creation_modes"]
    assert drawing["can_create_content"] is True
    assert drawing["can_edit_content"] is True
    assert drawing["can_quick_start"] is False
    assert drawing["supports_ai_generation"] is True
    assert "ai" in drawing["creation_modes"]
    assert drawing["config_schema"]["time_limit"]["default"] == 30


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


def test_revelry_return_url_validation_parses_origins(monkeypatch):
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", "test-revelry-secret")
    db.init_db()
    payload = _create_payload(f"party-return-{uuid.uuid4().hex}")

    for allowed in (
        "https://app.revelryapp.me/party/1?tab=games",
        "https://api-gamma.revelryapp.me/party/1?tab=games",
        "revelry://party/1/games",
    ):
        payload["return_url"] = allowed
        payload["external_context"]["return_url"] = allowed
        res = client.post("/integrations/revelry/party-games-link", headers=_headers(), json=payload)
        assert res.status_code == 200

    for blocked in (
        "https://app.revelryapp.me.evil.com/steal",
        "https://app.revelryapp.me@evil.com/steal",
        "not-a-url",
        "ftp://app.revelryapp.me/party/1",
        "revelryevil://party/1/games",
        "revelry://evil/party/1/games",
    ):
        payload["return_url"] = blocked
        payload["external_context"]["return_url"] = blocked
        res = client.post("/integrations/revelry/party-games-link", headers=_headers(), json=payload)
        assert res.status_code == 422


def test_revelry_party_games_link_honors_extended_ttl_outside_production(monkeypatch):
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", "test-revelry-secret")
    monkeypatch.setattr(config, "ENVIRONMENT", "gamma")
    db.init_db()
    payload = _create_payload(f"party-long-ttl-{uuid.uuid4().hex}")
    payload["ttl_seconds"] = 30 * 24 * 60 * 60

    res = client.post("/integrations/revelry/party-games-link", headers=_headers(), json=payload)

    assert res.status_code == 200
    data = res.json()
    token = parse_qs(urlparse(data["party_games_url"]).query)["party_games_token"][0]
    claims = main.jwt.decode(token, "test-revelry-secret", algorithms=["HS256"])
    assert claims["exp"] - claims["iat"] == 30 * 24 * 60 * 60


def test_revelry_party_games_link_rejects_custom_ttl_in_production(monkeypatch):
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", "test-revelry-secret")
    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    db.init_db()
    payload = _create_payload(f"party-prod-ttl-{uuid.uuid4().hex}")
    payload["ttl_seconds"] = 3600

    res = client.post("/integrations/revelry/party-games-link", headers=_headers(), json=payload)

    assert res.status_code == 422
    assert "not available in production" in res.json()["detail"]


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
    assert body["payload"]["actor"] == {
        "external_user_id": f"host-{container_id}",
        "display_name": "Ava",
        "role": "host",
    }
    assert "organizer_token" not in json.dumps(body["payload"]["actor"])
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
    assert conflict.json()["detail"]["game_type"] == "quiz"
    assert conflict.json()["detail"]["game_title"]

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
    assert body["result_summary"]["players"] == [{"nickname": "Ava", "avatar": "🎉", "score": 100}]
    assert body["result_summary"]["leaderboard"] == [{"nickname": "Ava", "avatar": "🎉", "score": 100}]
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
    assert body["payload"]["result_summary"]["players"] == [{"nickname": "Ava", "avatar": "🎉", "score": 100}]
    assert body["payload"]["result_summary"]["leaderboard"] == [{"nickname": "Ava", "avatar": "🎉", "score": 100}]
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
            "external_host_user_id": "host-runtime",
            "external_host_display_name": "Ava",
        },
    )

    assert len(calls) == 2
    assert calls[0]["body"]["event_id"] == calls[1]["body"]["event_id"]
    assert calls[0]["raw"] == calls[1]["raw"]
    assert calls[-1]["body"]["event_type"] == "game.started"
    assert calls[-1]["body"]["payload"]["actor"] == {
        "external_user_id": "host-runtime",
        "display_name": "Ava",
        "role": "host",
    }


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


def test_revelry_authoring_token_can_generate_ai_quiz(monkeypatch):
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", "test-revelry-secret")
    db.init_db()
    container_id = f"party-ai-quiz-{uuid.uuid4().hex}"
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

    async def fake_generate(prompt, difficulty, num_questions, provider, model_override=None, mode="classic"):
        assert prompt == "Ava birthday trivia"
        assert difficulty == "easy"
        assert num_questions == 3
        assert mode == "classic"
        return {
            "quiz_title": "Ava Birthday Quiz",
            "questions": [
                {"id": 1, "text": "Theme?", "options": ["Space", "Ocean", "Garden", "Disco"], "answer_index": 0, "image_prompt": ""},
                {"id": 2, "text": "Cake?", "options": ["Chocolate", "Vanilla", "Lemon", "Berry"], "answer_index": 1, "image_prompt": ""},
                {"id": 3, "text": "Song?", "options": ["A", "B", "C", "D"], "answer_index": 2, "image_prompt": ""},
            ],
        }

    monkeypatch.setattr(main.quiz_engine, "generate_quiz", fake_generate)

    link_res = client.post("/integrations/revelry/content/authoring-link", headers=_headers(), json=payload)
    assert link_res.status_code == 200
    token = link_res.json()["authoring_url"].split("authoring_token=", 1)[1]

    generate_res = client.post(
        "/integrations/revelry/party-games/prompts/generate",
        json={
            "party_games_token": token,
            "game_type": "quiz",
            "prompt": "Ava birthday trivia",
            "difficulty": "easy",
            "num_prompts": 3,
        },
    )

    assert generate_res.status_code == 200
    body = generate_res.json()
    assert body["game_type"] == "quiz"
    quiz = body["content_payload"]["quiz"]
    assert quiz["quiz_title"] == "Ava Birthday Quiz"
    assert quiz["questions"][0]["answer_index"] == 0


def test_revelry_authoring_token_can_import_quiz_and_generate_question_image(monkeypatch):
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", "test-revelry-secret")
    db.init_db()
    container_id = f"party-ai-image-{uuid.uuid4().hex}"
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
    token = link_res.json()["authoring_url"].split("authoring_token=", 1)[1]

    async def fake_available():
        return True

    async def fake_generate(prompt, style="vivid"):
        assert prompt == "party cake with fox topper"
        return "aGVsbG8="

    monkeypatch.setattr(main.image_engine, "is_available", fake_available)
    monkeypatch.setattr(main.image_engine, "generate_image", fake_generate)

    quiz = {
        "quiz_title": "Image Quiz",
        "questions": [
            {
                "id": 1,
                "text": "What is on the cake?",
                "options": ["Fox", "Bear", "Cat", "Dog"],
                "answer_index": 0,
                "image_prompt": "party cake with fox topper",
            }
        ],
    }
    import_res = client.post("/quiz/import", headers={"Authorization": f"Bearer {token}"}, json={"quiz": quiz})
    assert import_res.status_code == 200
    quiz_id = import_res.json()["quiz_id"]

    image_res = client.post(
        "/quiz/generate-images",
        headers={"Authorization": f"Bearer {token}"},
        json={"quiz_id": quiz_id, "question_id": 1},
    )
    assert image_res.status_code == 200
    body = image_res.json()
    assert body["asset"]["url"].startswith("/media/img_")
    assert main.quizzes[quiz_id]["questions"][0]["image_url"] == body["asset"]["url"]
    assert main.content_owners[quiz_id] == f"revelry:party:{container_id}"


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
    updated = [call["body"] for call in calls if call["body"]["event_type"] == "content.updated"]
    assert updated
    assert updated[-1]["previous_content_id"] == pack["id"]
    assert updated[-1]["content_id"] == body["localplay_content_id"]


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


def test_revelry_party_hub_can_save_and_start_catalog_game_content(monkeypatch):
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", "test-revelry-secret")
    db.init_db()
    container_id = f"party-hub-drawing-{uuid.uuid4().hex}"
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

    save_res = client.post(
        "/integrations/revelry/party-games/content",
        json={
            "party_games_token": party_token,
            "game_type": "drawing",
            "title": "Christmas Drawing",
            "content_payload": {
                "game": {
                    "game_title": "Christmas Drawing",
                    "prompts": [
                        {"id": 1, "text": "gingerbread house", "aliases": ["gingerbread"], "difficulty": "medium"},
                        {"id": 2, "text": "snow globe", "aliases": ["snowglobe"], "difficulty": "medium"},
                    ],
                },
                "time_limit": 25,
            },
        },
    )

    assert save_res.status_code == 200
    assert save_res.json()["status"] == "ready"
    assert save_res.json()["game_type"] == "drawing"
    assert save_res.json()["localplay_content_id"] == save_res.json()["content"]["localplay_content_id"]
    saved = save_res.json()["content"]
    assert saved["game_type"] == "drawing"
    assert saved["question_count"] == 2
    assert saved["time_limit"] == 25

    start_res = client.post(
        "/integrations/revelry/party-games/start",
        json={"party_games_token": party_token, "game_type": "drawing", "content_id": saved["localplay_content_id"]},
    )

    assert start_res.status_code == 200
    body = start_res.json()
    assert body["session"]["status"] == "lobby"
    assert body["session"]["room_code"] in socket_manager.rooms
    room = socket_manager.rooms[body["session"]["room_code"]]
    assert room.game_type == "drawing"
    assert room.time_limit == 25

    reentry_res = client.post(
        "/integrations/revelry/party-games/launch-token",
        json={
            "party_games_token": party_token,
            "session_id": body["session"]["session_id"],
            "scope": "organizer",
            "route": "organizer",
            "embed": True,
        },
    )
    assert reentry_res.status_code == 200
    assert "/organizer?session_id=" in reentry_res.json()["launch_url"]
    assert "launch_token=" in reentry_res.json()["launch_url"]
    launch_token = reentry_res.json()["launch_url"].split("launch_token=", 1)[1].split("&", 1)[0]
    resolve_res = client.get(f"/integrations/revelry/launch-token/resolve?scope=organizer&launch_token={launch_token}")
    assert resolve_res.status_code == 200
    assert resolve_res.json()["organizer_token"]


def test_revelry_party_hub_can_save_and_start_housie(monkeypatch):
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", "test-revelry-secret")
    db.init_db()
    container_id = f"party-hub-housie-{uuid.uuid4().hex}"
    payload = {
        "external_context": {
            "host_app": "revelry",
            "external_container_type": "party",
            "external_container_id": container_id,
            "external_container_title": "Ava's Housie Night",
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

    resolve_res = client.get(f"/integrations/revelry/party-games/resolve?party_games_token={party_token}")
    assert resolve_res.status_code == 200
    assert "housie" in {game["id"] for game in resolve_res.json()["workspace"]["catalog"]}

    save_res = client.post(
        "/integrations/revelry/party-games/content",
        json={
            "party_games_token": party_token,
            "game_type": "housie",
            "title": "Ava's Housie",
            "content_payload": {
                "game": {
                    "game_title": "Ava's Housie",
                    "pattern_ids": ["quick_5", "four_corners", "top_row", "middle_row", "bottom_row", "full_house"],
                    "play_mode": "beginner",
                    "caller_mode": "manual",
                },
            },
        },
    )
    assert save_res.status_code == 200, save_res.text
    saved = save_res.json()["content"]
    assert saved["game_type"] == "housie"
    assert saved["question_count"] == 6
    prepared_ids = {
        item["localplay_content_id"]
        for item in save_res.json()["workspace"]["prepared_content"]
    }
    assert saved["localplay_content_id"] in prepared_ids

    start_res = client.post(
        "/integrations/revelry/party-games/start",
        json={"party_games_token": party_token, "game_type": "housie", "content_id": saved["localplay_content_id"]},
    )
    assert start_res.status_code == 200, start_res.text
    body = start_res.json()
    room = socket_manager.rooms[body["session"]["room_code"]]
    assert room.game_type == "housie"
    assert room.quiz["game_title"] == "Ava's Housie"


def test_revelry_replacement_closes_superseded_runtime_room(monkeypatch):
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", "test-revelry-secret")
    db.init_db()
    container_id = f"replace-room-{uuid.uuid4().hex}"
    payload = _create_payload(container_id=container_id, game_type="quiz")

    first_res = client.post("/integrations/revelry/sessions", headers=_headers(), json=payload)
    assert first_res.status_code == 200
    first = first_res.json()
    first_room_code = first["room_code"]
    assert first_room_code in socket_manager.rooms

    second_payload = {
        **payload,
        "replacement_confirmed": True,
        "replace_session_id": first["session_id"],
    }
    second_res = client.post("/integrations/revelry/sessions", headers=_headers(), json=second_payload)
    assert second_res.status_code == 200, second_res.text
    second = second_res.json()

    assert first_room_code not in socket_manager.rooms
    assert second["room_code"] in socket_manager.rooms
    old_session = db.get_game_session(first["session_id"])
    assert old_session["status"] == "superseded"
    assert old_session["joinable"] is False


def test_revelry_party_hub_can_generate_drawing_setup_prompts(monkeypatch):
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", "test-revelry-secret")
    db.init_db()
    container_id = f"party-hub-drawing-ai-{uuid.uuid4().hex}"
    payload = {
        "external_context": {
            "host_app": "revelry",
            "external_container_type": "party",
            "external_container_id": container_id,
            "external_container_title": "Christmas Bash",
        },
        "actor": {
            "external_user_id": "host-1",
            "display_name": "Ava",
            "role": "host",
            "capabilities": ["author_content", "operate_game"],
        },
    }

    async def fake_generate(prompt, difficulty, num_prompts, provider, model_override=None):
        assert prompt == "Christmas Bash drawing prompts"
        assert difficulty == "medium"
        assert num_prompts == 3
        return {
            "game_title": "Christmas Drawing",
            "prompts": [
                {"id": 1, "text": "Santa hat", "aliases": ["hat"], "difficulty": "easy"},
                {"id": 2, "text": "Snow globe", "aliases": ["globe"], "difficulty": "medium"},
                {"id": 3, "text": "Gingerbread house", "aliases": ["gingerbread"], "difficulty": "medium"},
            ],
        }

    monkeypatch.setattr(main.drawing_engine, "generate_prompts", fake_generate)

    link_res = client.post("/integrations/revelry/party-games-link", headers=_headers(), json=payload)
    assert link_res.status_code == 200
    party_token = link_res.json()["party_games_url"].split("party_games_token=", 1)[1]

    generate_res = client.post(
        "/integrations/revelry/party-games/prompts/generate",
        json={
            "party_games_token": party_token,
            "game_type": "drawing",
            "prompt": "Christmas Bash drawing prompts",
            "difficulty": "medium",
            "num_prompts": 3,
        },
    )

    assert generate_res.status_code == 200
    body = generate_res.json()
    assert body["game_type"] == "drawing"
    assert [item["text"] for item in body["content_payload"]["game"]["prompts"]] == [
        "Santa hat",
        "Snow globe",
        "Gingerbread house",
    ]
    assert db.list_game_content(f"revelry:party:{container_id}") == []


def test_revelry_party_hub_rejects_invalid_catalog_game_content(monkeypatch):
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", "test-revelry-secret")
    db.init_db()
    container_id = f"party-hub-invalid-{uuid.uuid4().hex}"
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
            "capabilities": ["author_content", "operate_game"],
        },
    }
    link_res = client.post("/integrations/revelry/party-games-link", headers=_headers(), json=payload)
    assert link_res.status_code == 200
    party_token = link_res.json()["party_games_url"].split("party_games_token=", 1)[1]

    save_res = client.post(
        "/integrations/revelry/party-games/content",
        json={
            "party_games_token": party_token,
            "game_type": "drawing",
            "title": "Broken Drawing",
            "content_payload": {"game": {"game_title": "Broken Drawing", "prompts": [{"id": 1, "text": ""}]}},
        },
    )

    assert save_res.status_code == 422
    assert "Invalid drawing game content" in save_res.text
    assert db.list_game_content(f"revelry:party:{container_id}") == []


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
