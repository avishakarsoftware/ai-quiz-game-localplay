"""Revelry bridge regressions found during the October repository review."""
import time
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from fastapi.testclient import TestClient

import config
import db
import main
from host_app_catalog_policy import clear_policy_cache
from socket_manager import socket_manager


SECRET = "review-revelry-secret-at-least-32-bytes"
HEADERS = {"Authorization": f"Bearer {SECRET}"}
client = TestClient(main.app)


@pytest.fixture(autouse=True)
def integration_state(monkeypatch):
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", SECRET)
    monkeypatch.setattr(config, "REVELRY_CALLBACK_URL", "")
    monkeypatch.setattr(config, "ENVIRONMENT", "local")
    socket_manager.rooms.clear()
    clear_policy_cache()
    for key in ("quizzes", "mlt_scenarios", "drawing_games", "housie_games", "bingo_games", "chit_pull_games", "content_owners"):
        monkeypatch.setattr(main, key, {})
    yield
    socket_manager.rooms.clear()
    clear_policy_cache()


def _context(party="party-review"):
    return {"host_app": "revelry", "external_container_id": party, "external_container_title": "Review Party"}


def _actor():
    return {"external_user_id": "host-review", "display_name": "Host", "capabilities": ["manage_games", "operate_game", "author_content"]}


def _save(game_type="quiz", party="party-review", title="Original"):
    _, game = main._default_game_content(game_type, title)
    wallet = main._revelry_party_wallet_id(party)
    if game_type == "quiz":
        return db.save_quiz_pack(wallet, title, game["questions"])
    payload = main._content_game_from_payload(game_type, title, {"game": game})
    return db.save_game_content(wallet, game_type, title, payload)


def _session(game_type="quiz", party="party-review", content_id=""):
    return client.post("/integrations/revelry/sessions", headers=HEADERS, json={
        "external_context": _context(party), "actor": _actor(), "game_type": game_type,
        "settings": {"content_id": content_id},
    })


def _authoring_token(content_id, mode="edit", game_type="quiz"):
    response = client.post("/integrations/revelry/content/authoring-link", headers=HEADERS, json={
        "external_context": _context(), "actor": _actor(), "game_type": game_type,
        "mode": mode, "content_id": content_id,
    })
    assert response.status_code == 200, response.text
    return parse_qs(urlparse(response.json()["authoring_url"]).query)["authoring_token"][0]


def _quiz_payload(title="Updated"):
    return {"quiz": {"quiz_title": title, "questions": [
        {"id": 1, "text": "What changed?", "options": ["One", "Two"], "answer_index": 0, "image_prompt": ""},
    ]}}


def _handoff(party="party-review", scope="player", capabilities=None, **overrides):
    now = int(time.time())
    return jwt.encode({
        "iss": "revelry", "aud": "localplay", "typ": "localplay_launch", "jti": "review-jti",
        **_context(party), "external_container_type": "party", "external_user_id": "signed-user",
        "display_name": "Signed Player", "role": "guest", "scope": scope,
        "capabilities": capabilities if capabilities is not None else [], "iat": now, "exp": now + 600,
        **overrides,
    }, SECRET, algorithm="HS256")


@pytest.mark.parametrize("game_type", ["quiz", "wmlt", "drawing", "housie", "chit_pull"])
def test_cached_content_cannot_cross_party_boundary(game_type):
    saved = _save(game_type)
    assert _session(game_type, content_id=saved["id"]).status_code == 200
    original_rooms = set(socket_manager.rooms)
    response = _session(game_type, party="other-party", content_id=saved["id"])
    assert response.status_code == 404
    assert set(socket_manager.rooms) == original_rooms


@pytest.mark.parametrize("game_type", ["quiz", "drawing"])
def test_deleted_content_is_not_resurrected_from_runtime_cache(game_type):
    saved = _save(game_type)
    main._resolve_revelry_runtime_content(main.RevelryExternalContext(**_context()), game_type, saved["id"])
    wallet = main._revelry_party_wallet_id("party-review")
    delete = db.delete_quiz_pack if game_type == "quiz" else db.delete_game_content
    assert delete(wallet, saved["id"])
    assert _session(game_type, content_id=saved["id"]).status_code == 404


def test_start_reloads_the_current_saved_content_instead_of_stale_cache():
    saved = _save()
    main._resolve_revelry_runtime_content(main.RevelryExternalContext(**_context()), "quiz", saved["id"])
    db.save_quiz_pack(main._revelry_party_wallet_id("party-review"), "Updated", _quiz_payload()["quiz"]["questions"], saved["id"])
    response = _session(content_id=saved["id"])
    assert response.status_code == 200
    room = socket_manager.rooms[response.json()["room_code"]]
    assert room.quiz["quiz_title"] == "Updated"


def test_service_bearer_can_create_fetch_and_delete_party_content():
    response = client.post("/integrations/revelry/content", headers=HEADERS, json={
        "external_context": _context(), "actor": _actor(), "game_type": "quiz", "content_payload": _quiz_payload(),
    })
    assert response.status_code == 200
    content_id = response.json()["localplay_content_id"]
    fetched = client.get(f"/integrations/revelry/content/{content_id}?external_container_id=party-review", headers=HEADERS)
    assert fetched.status_code == 200
    assert fetched.json()["title"] == fetched.json()["content"]["title"] == "Updated"
    assert "quiz" not in fetched.json()
    deleted = client.delete(f"/integrations/revelry/content/{content_id}?external_container_id=party-review", headers=HEADERS)
    assert deleted.status_code == 200
    assert db.get_quiz_pack(main._revelry_party_wallet_id("party-review"), content_id) is None


@pytest.mark.parametrize("content_id", ["missing", "foreign"])
def test_content_update_requires_an_existing_party_owned_id(content_id):
    saved = _save(party="other-party", title="Other Party")
    requested_id = saved["id"] if content_id == "foreign" else content_id
    response = client.post("/integrations/revelry/content", headers=HEADERS, json={
        "external_context": _context(), "actor": _actor(), "game_type": "quiz",
        "content_id": requested_id, "content_payload": _quiz_payload(),
    })
    assert response.status_code == 404
    original = db.get_quiz_pack(main._revelry_party_wallet_id("other-party"), saved["id"])
    assert original["title"] == "Other Party"
    assert original["questions"][0]["text"] != "What changed?"


def test_update_cannot_change_a_saved_games_type():
    saved = _save("drawing")
    response = client.post("/integrations/revelry/content", headers=HEADERS, json={
        "external_context": _context(), "actor": _actor(), "game_type": "quiz",
        "content_id": saved["id"], "content_payload": _quiz_payload(),
    })
    assert response.status_code == 422
    assert db.get_game_content(main._revelry_party_wallet_id("party-review"), saved["id"])["game_type"] == "drawing"


@pytest.mark.parametrize("mode", ["duplicate", "edit"])
def test_copy_or_version_moves_authoring_scope_without_extending_expiry(mode):
    saved = _save()
    if mode == "edit":
        assert _session(content_id=saved["id"]).status_code == 200
    token = _authoring_token(saved["id"], mode)
    response = client.post("/integrations/revelry/content", headers={"Authorization": f"Bearer {token}"}, json={
        "game_type": "quiz", "content_id": saved["id"], "content_payload": _quiz_payload(),
    })
    assert response.status_code == 200
    body = response.json()
    assert body["localplay_content_id"] != saved["id"]
    assert ("previous_content_id" in body) == (mode == "edit")
    next_token = body["authoring_token"]
    next_claims = jwt.decode(next_token, SECRET, algorithms=["HS256"])
    assert next_claims["content_id"] == body["localplay_content_id"]
    assert next_claims["exp"] == jwt.decode(token, SECRET, algorithms=["HS256"])["exp"]
    again = client.post("/integrations/revelry/content", headers={"Authorization": f"Bearer {next_token}"}, json={
        "game_type": "quiz", "content_id": body["localplay_content_id"], "content_payload": _quiz_payload("Saved again"),
    })
    assert again.status_code == 200
    assert again.json()["localplay_content_id"] == body["localplay_content_id"]
    assert db.get_quiz_pack(main._revelry_party_wallet_id("party-review"), saved["id"])["title"] == "Original"


def test_catalog_edit_and_quick_start_overrides_are_enforced(monkeypatch):
    saved = _save()
    monkeypatch.setattr(config, "ENVIRONMENT", "gamma")
    db.upsert_host_app_catalog_flag("gamma", "revelry", "quiz", {
        "enabled": True, "status": "gamma", "capability_overrides": {"can_edit_content": False, "can_quick_start": False},
    })
    clear_policy_cache()
    assert _session().status_code == 422
    edit = client.post("/integrations/revelry/content", headers=HEADERS, json={
        "external_context": _context(), "actor": _actor(), "game_type": "quiz",
        "content_id": saved["id"], "content_payload": _quiz_payload(),
    })
    assert edit.status_code == 422
    assert _session(content_id=saved["id"]).status_code == 200


@pytest.mark.parametrize("scope,route,target", [("player", "join", "join"), ("spectator", "spectate", "spectator")])
def test_session_route_keeps_launch_context_for_players_and_spectators(scope, route, target):
    session = _session().json()
    token, _ = main._create_launch_token(session["session_id"], scope, route, "https://app.revelryapp.me/party/p")
    response = client.get(f"/sessions/{session['session_id']}/{route}?launch_token={token}&embed=1", follow_redirects=False)
    assert response.status_code == 302
    redirect = urlparse(response.headers["location"])
    assert redirect.path == f"/{target}"
    assert parse_qs(redirect.query) == {"session_id": [session["session_id"]], "launch_token": [token], "embed": ["1"]}


@pytest.mark.parametrize("return_url", ["https://evil.example/steal", "javascript:alert(1)", "https://app.revelryapp.me:bad/party"])
def test_service_launch_token_validates_return_url(return_url):
    session = _session().json()
    response = client.post(f"/integrations/revelry/sessions/{session['session_id']}/launch-token", headers=HEADERS, json={
        "scope": "player", "route": "join", "return_url": return_url,
    })
    assert response.status_code == 422


def test_already_summarized_results_still_strip_private_fields():
    summary = main._safe_result_summary({
        "top_results": [{"nickname": "Ava", "avatar": "🎉", "score": 100, "photo_url": "secret", "token": "private"}, "malformed"],
        "winner": {"nickname": "Ava", "avatar": "🎉", "score": 100, "role": "mafia"},
    })
    assert summary["top_results"] == [{"nickname": "Ava", "avatar": "🎉", "score": 100}]
    assert summary["winner"] == summary["top_results"][0]


def test_player_handoff_cannot_create_organizer_session():
    response = client.post("/integrations/revelry/sessions", headers={"Authorization": f"Bearer {_handoff()}"}, json={
        "external_context": _context(), "actor": _actor(),
    })
    assert response.status_code == 403
    assert not socket_manager.rooms


@pytest.mark.parametrize("scope,party,capabilities", [
    ("player", "party-review", []), ("organizer", "other-party", ["operate_game"]), ("organizer", "party-review", []),
])
def test_handoff_launch_token_enforces_scope_party_and_capabilities(scope, party, capabilities):
    session = _session().json()
    token = _handoff(party, scope, capabilities)
    response = client.post(f"/integrations/revelry/sessions/{session['session_id']}/launch-token", headers={"Authorization": f"Bearer {token}"}, json={
        "scope": "organizer", "route": "organizer",
    })
    assert response.status_code == 403


def test_handoff_actor_is_authoritative_and_player_exchange_still_works():
    host_token = _handoff(scope="organizer", capabilities=["operate_game"])
    response = client.post("/integrations/revelry/sessions", headers={"Authorization": f"Bearer {host_token}"}, json={
        "external_context": _context(), "actor": _actor(),
    })
    assert response.status_code == 200
    session = response.json()
    assert db.get_game_session(session["session_id"])["external_host_display_name"] == "Signed Player"
    assert db.get_game_session(session["session_id"])["external_host_user_id"] == "signed-user"
    player = client.post(f"/integrations/revelry/sessions/{session['session_id']}/launch-token", headers={"Authorization": f"Bearer {_handoff()}"}, json={
        "scope": "player", "route": "join",
    })
    assert player.status_code == 200
    launch_token = parse_qs(urlparse(player.json()["launch_url"]).query)["launch_token"][0]
    resolve = client.get(f"/integrations/revelry/launch-token/resolve?launch_token={launch_token}&scope=player")
    assert resolve.json()["launch_context"]["external_user_id"] == "signed-user"
    assert "organizer_token" not in resolve.json()


def test_handoff_cannot_impersonate_service_auth_by_setting_a_type_claim():
    token = _handoff(type="service")
    response = client.post("/integrations/revelry/party-games-link", headers={"Authorization": f"Bearer {token}"}, json={"external_context": _context(), "actor": _actor()})
    assert response.status_code == 403


def test_party_hub_authoring_rejects_unknown_mode():
    with pytest.raises(ValueError):
        main.RevelryPartyGamesAuthoringLinkRequest(party_games_token="unused", mode="overwrite")


def test_party_hub_organizer_reentry_retains_a_fresh_hub_return_url():
    session = _session().json()
    party_token, _, _ = main._create_party_games_token(
        main.RevelryExternalContext(**_context()), main.RevelryActor(**_actor()),
    )
    response = client.post("/integrations/revelry/party-games/launch-token", json={
        "party_games_token": party_token, "session_id": session["session_id"], "scope": "organizer", "route": "organizer",
    })
    assert response.status_code == 200
    launch_token = parse_qs(urlparse(response.json()["launch_url"]).query)["launch_token"][0]
    resolved = client.get(f"/integrations/revelry/launch-token/resolve?launch_token={launch_token}&scope=organizer").json()
    context = resolved["launch_context"]
    hub_token = parse_qs(urlparse(context["party_hub_url"]).query)["party_games_token"][0]
    assert main._resolve_party_games_token(hub_token)["external_container_id"] == "party-review"
    assert context["party_hub_token_expires_at"]


def test_repeated_content_updates_have_distinct_callback_deduplication_keys(monkeypatch):
    import json
    from test_revelry_integration import _FakeAsyncClient

    calls = []
    monkeypatch.setattr(config, "REVELRY_CALLBACK_URL", "https://api-gamma.revelryapp.me/callback")
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda *args, **kwargs: _FakeAsyncClient(calls))
    saved = _save()
    for title in ("First update", "Second update"):
        response = client.post("/integrations/revelry/content", headers=HEADERS, json={
            "external_context": _context(), "actor": _actor(), "game_type": "quiz",
            "content_id": saved["id"], "content_payload": _quiz_payload(title),
        })
        assert response.status_code == 200
    bodies = [json.loads(call["raw"]) for call in calls]
    assert bodies[0]["content_id"] == bodies[1]["content_id"] == saved["id"]
    assert bodies[0]["idempotency_key"] != bodies[1]["idempotency_key"]
    assert bodies[0]["event_id"] != bodies[1]["event_id"]


def test_session_created_callback_has_current_revelry_mirror_fields(monkeypatch):
    from test_revelry_integration import _FakeAsyncClient

    calls = []
    monkeypatch.setattr(config, "REVELRY_CALLBACK_URL", "https://api-gamma.revelryapp.me/callback")
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda *args, **kwargs: _FakeAsyncClient(calls))
    response = _session("party_quests")
    assert response.status_code == 200
    session = response.json()
    payload = calls[0]["body"]["payload"]
    assert payload["game_type"] == "party_quests"
    assert payload["room_code"] == session["room_code"]
    assert payload["launch_routes"] == session["launch_routes"]
    assert payload["joinable"] is True
    assert payload["content_id"] == session["content_id"]
    assert "organizer_token" not in payload
    assert payload["session"]["game_type"] == "party_quests"


@pytest.mark.parametrize("token_type,resolver", [
    ("revelry_party_games", main._resolve_party_games_token),
    ("revelry_authoring", main._resolve_authoring_token),
    ("revelry_launch", main._resolve_launch_token),
])
@pytest.mark.parametrize("missing_or_wrong", ["exp", "iss"])
def test_browser_credentials_require_localplay_issuer_and_expiry(token_type, resolver, missing_or_wrong):
    from fastapi import HTTPException

    now = int(time.time())
    claims = {
        "type": token_type, "iss": "localplay", "exp": now + 600, "iat": now, "jti": "review-browser-jti",
        "launch_context": _context(), "session_id": "unused", "scope": "player",
    }
    if missing_or_wrong == "iss":
        claims["iss"] = "revelry"
    else:
        claims.pop("exp")
    token = jwt.encode(claims, SECRET, algorithm="HS256")
    with pytest.raises(HTTPException) as exc:
        resolver(token)
    assert exc.value.status_code == 401
