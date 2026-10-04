"""Quiz-pack ownership failures have a stable API contract without hiding DB failures."""
from functools import partial
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

import config
import db
import main
import supabase_db
from persistence_errors import QuizPackOwnershipError


QUESTIONS = [{"id": 1, "text": "Original?", "options": ["A", "B"], "answer_index": 0}]
PAYLOAD = {"pack_id": "private-pack", "quiz": {"quiz_title": "Overwrite", "questions": QUESTIONS}}


@pytest.fixture
def client():
    client = TestClient(main.app, raise_server_exceptions=False)
    yield client
    client.close()


def test_foreign_save_returns_404_and_preserves_owner_pack(monkeypatch, client):
    saved = db.save_quiz_pack("owner", "Original", QUESTIONS, pack_id="private-pack")
    monkeypatch.setattr(main.tokens, "get_wallet_id", lambda req: "stranger")
    response = client.post("/quiz-packs", json=PAYLOAD)
    assert response.status_code == 404
    assert response.json() == {"detail": "Quiz pack not found"}
    assert db.get_quiz_pack("owner", saved["id"]) == saved
    assert db.get_quiz_pack("stranger", saved["id"]) is None


def test_owner_can_create_explicit_id_update_and_restore_deleted_pack(monkeypatch, client):
    monkeypatch.setattr(main.tokens, "get_wallet_id", lambda req: "owner")
    created = client.post("/quiz-packs", json=PAYLOAD)
    assert created.status_code == 200
    saved = created.json()["pack"]
    assert saved["id"] == "private-pack"
    replacement = dict(PAYLOAD, quiz={"quiz_title": "Updated", "questions": [dict(QUESTIONS[0], text="New?")]})
    updated = client.post("/quiz-packs", json=replacement)
    assert updated.status_code == 200
    assert updated.json()["pack"]["questions"][0]["text"] == "New?"
    assert client.delete("/quiz-packs/private-pack").status_code == 200
    assert db.get_quiz_pack("owner", "private-pack") is None
    restored = client.post("/quiz-packs", json=replacement)
    assert restored.status_code == 200
    pack = restored.json()["pack"]
    assert pack["owner_wallet_id"] == "owner"
    assert pack["created_at"] == saved["created_at"]
    assert pack["deleted_at"] is None and pack["status"] == "ready"
    assert pack["questions"][0]["text"] == "New?"


def _postgrest_error(monkeypatch, status, body):
    """Exercise the real HTTP adapter with a stale preflight and an RPC rejection."""
    requests = []

    def respond(request):
        requests.append(request)
        if request.method == "GET":
            assert request.url.path == "/rest/v1/games_quiz_packs"
            return httpx.Response(200, json=[])
        assert request.method == "POST"
        assert request.url.path == "/rest/v1/rpc/games_save_quiz_pack"
        if isinstance(body, str):
            return httpx.Response(status, text=body)
        return httpx.Response(status, json=body)

    monkeypatch.setattr(config, "SUPABASE_URL", "http://supabase.invalid")
    monkeypatch.setattr(config, "SUPABASE_SERVICE_KEY", "test-service-key")
    monkeypatch.setattr(config, "TABLE_PREFIX", "games_")
    # Replace only the adapter's HTTP module, leaving TestClient's HTTP client intact.
    monkeypatch.setattr(supabase_db, "httpx", SimpleNamespace(
        Client=partial(httpx.Client, transport=httpx.MockTransport(respond)),
    ))
    adapter = supabase_db.SupabaseClient()
    monkeypatch.setattr(supabase_db, "_sb", lambda: adapter)
    return requests


def test_atomic_rpc_ownership_rejection_is_typed_and_returns_404(monkeypatch, client):
    requests = _postgrest_error(monkeypatch, 403, {
        "code": "42501", "message": "Quiz pack belongs to another wallet", "details": None, "hint": None,
    })
    with pytest.raises(QuizPackOwnershipError) as raised:
        supabase_db.save_quiz_pack("stranger", "Overwrite", QUESTIONS, pack_id="private-pack")
    assert isinstance(raised.value.__cause__, supabase_db.SupabaseDBError)
    assert raised.value.__cause__.code == "42501"
    monkeypatch.setattr(db, "save_quiz_pack", supabase_db.save_quiz_pack)
    response = client.post("/quiz-packs", json=PAYLOAD)
    assert response.status_code == 404
    assert response.json() == {"detail": "Quiz pack not found"}
    assert [request.method for request in requests] == ["GET", "POST", "GET", "POST"]


@pytest.mark.parametrize("status,body", [
    (403, {"code": "42501", "message": "permission denied for function games_save_quiz_pack"}),
    (500, {"code": "XX000", "message": "Quiz pack belongs to another wallet"}),
    (500, {"code": "XX000", "message": "database unavailable"}),
    (403, {"message": "Quiz pack belongs to another wallet"}),
    (403, [{"code": "42501", "message": "Quiz pack belongs to another wallet"}]),
    (502, "upstream database unavailable"),
])
def test_other_rpc_failures_remain_database_errors_and_http_500(monkeypatch, client, status, body):
    _postgrest_error(monkeypatch, status, body)
    with pytest.raises(supabase_db.SupabaseDBError):
        supabase_db.save_quiz_pack("owner", "Original", QUESTIONS, pack_id="private-pack")
    monkeypatch.setattr(db, "save_quiz_pack", supabase_db.save_quiz_pack)
    response = client.post("/quiz-packs", json=PAYLOAD)
    assert response.status_code == 500


@pytest.mark.parametrize("failure", [
    RuntimeError("Quiz pack belongs to another wallet"),
    supabase_db.SupabaseDBError("Quiz pack belongs to another wallet"),
    supabase_db.SupabaseDBError("Database unavailable"),
])
def test_route_does_not_translate_untyped_database_errors(monkeypatch, client, failure):
    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(db, "save_quiz_pack", fail)
    assert client.post("/quiz-packs", json=PAYLOAD).status_code == 500
