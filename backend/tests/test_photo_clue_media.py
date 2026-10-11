import time

import jwt
import pytest
from fastapi.testclient import TestClient

import config
import db
import main
import tokens
from photo_clue_engine import PHASE_GUESSING, PHASE_WAITING_FOR_PHOTO, create_initial_state
from photo_clue_media import AUDIENCE, ISSUER, SCOPE, issue_attachment_token, resolve_attachment
from socket_manager import Room, SocketManager


OWNER = "11111111-1111-4111-8111-111111111111"
OTHER_OWNER = "22222222-2222-4222-8222-222222222222"
ASSET_ID = "img_photo_clue_test"
PUBLIC_URL = "https://media.example.test/gamma/uploads/photo.webp"


@pytest.fixture(autouse=True)
def configure_media(monkeypatch):
    monkeypatch.setattr(config, "MEDIA_UPLOAD_SECRET", "photo-clue-test-secret-only-for-isolated-regressions-0123456789abcd")
    monkeypatch.setattr(config, "MEDIA_UPLOAD_TOKEN_TTL_SECONDS", 60)
    monkeypatch.setattr(config, "MEDIA_UPLOAD_URL", "https://media.example.test/upload.php")
    monkeypatch.setattr(config, "MEDIA_PUBLIC_BASE_URL", "https://media.example.test")
    # Undo conftest's wallet bypass so the endpoint exercises device authentication.
    monkeypatch.setattr(tokens, "get_wallet_id", lambda request: tokens.get_device_id(request))


def create_asset(*, owner=OWNER, status="ready", public_url=PUBLIC_URL):
    return db.create_media_asset(ASSET_ID, owner, "gamma/uploads/photo.webp", public_url, "image/webp", 1234, status=status)


def claims():
    now = int(time.time())
    return {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "scope": SCOPE,
        "asset_id": ASSET_ID,
        "owner_wallet_id": OWNER,
        "iat": now,
        "exp": now + 60,
    }


def test_attachment_token_binds_expected_claims_and_resolves_real_ready_asset():
    asset = create_asset(status="pending")
    token = issue_attachment_token(ASSET_ID, OWNER)
    decoded = jwt.decode(token, config.MEDIA_UPLOAD_SECRET, algorithms=["HS256"], issuer=ISSUER, audience=AUDIENCE)
    assert decoded["scope"] == SCOPE
    assert decoded["asset_id"] == ASSET_ID
    assert decoded["owner_wallet_id"] == OWNER
    assert decoded["exp"] - decoded["iat"] == config.MEDIA_UPLOAD_TOKEN_TTL_SECONDS

    with pytest.raises(ValueError, match="not ready"):
        resolve_attachment(ASSET_ID, token)
    db.finalize_media_asset(OWNER, asset["id"], 1234, "A photo clue")
    resolved = resolve_attachment(ASSET_ID, token)
    assert resolved["public_url"] == PUBLIC_URL
    assert resolved["alt_text"] == "A photo clue"


@pytest.mark.parametrize("kind", [
    "missing", "malformed", "expired", "future", "tampered", "wrong_scope", "wrong_audience",
    "wrong_issuer", "missing_owner", "missing_expiry", "wrong_asset", "wrong_algorithm", "invalid_claim_type", "invalid_date_type", "overflowing_date",
])
def test_attachment_rejects_invalid_capabilities(kind):
    create_asset()
    payload = claims()
    secret = config.MEDIA_UPLOAD_SECRET
    algorithm = "HS256"
    if kind == "missing":
        token = ""
    elif kind == "malformed":
        token = "not-a-token"
    else:
        if kind == "expired":
            payload.update(iat=int(time.time()) - 120, exp=int(time.time()) - 60)
        elif kind == "future":
            payload.update(iat=int(time.time()) + 120, exp=int(time.time()) + 180)
        elif kind == "tampered":
            secret = "a-different-test-secret-for-invalid-signatures-0123456789abcdefghij"
        elif kind == "wrong_scope":
            payload["scope"] = "custom_quiz_question"
        elif kind == "wrong_audience":
            payload["aud"] = "quiz"
        elif kind == "wrong_issuer":
            payload["iss"] = "another.issuer"
        elif kind == "missing_owner":
            payload.pop("owner_wallet_id")
        elif kind == "missing_expiry":
            payload.pop("exp")
        elif kind == "wrong_asset":
            payload["asset_id"] = "img_another_asset"
        elif kind == "wrong_algorithm":
            algorithm = "HS512"
        elif kind == "invalid_claim_type":
            payload["owner_wallet_id"] = [OWNER]
        elif kind == "invalid_date_type":
            payload["iat"] = [payload["iat"]]
        elif kind == "overflowing_date":
            payload["exp"] = float("inf")
        token = jwt.encode(payload, secret, algorithm=algorithm)
    with pytest.raises(ValueError):
        resolve_attachment(ASSET_ID, token)


@pytest.mark.parametrize("status", ["pending", "failed", "deleted"])
def test_attachment_requires_ready_record(status):
    create_asset(status=status)
    with pytest.raises(ValueError, match="not ready"):
        resolve_attachment(ASSET_ID, issue_attachment_token(ASSET_ID, OWNER))


def test_attachment_rejects_unknown_asset_and_wrong_owner():
    with pytest.raises(ValueError, match="not found"):
        resolve_attachment(ASSET_ID, issue_attachment_token(ASSET_ID, OWNER))
    create_asset(owner=OTHER_OWNER)
    with pytest.raises(ValueError, match="not found"):
        resolve_attachment(ASSET_ID, issue_attachment_token(ASSET_ID, OWNER))


def test_attachment_rejects_ready_record_without_canonical_url():
    create_asset(public_url="")
    with pytest.raises(ValueError, match="no image URL"):
        resolve_attachment(ASSET_ID, issue_attachment_token(ASSET_ID, OWNER))


@pytest.mark.parametrize("purpose", ["photo_clue_submission", "custom_quiz_question", "another_purpose"])
def test_upload_endpoint_only_issues_photo_clue_capability_for_photo_purpose(purpose):
    with TestClient(main.app) as client:
        response = client.post("/media/upload-url", headers={"X-Device-Id": OWNER}, json={
            "filename": "photo.webp", "mime_type": "image/webp", "bytes": 1234, "purpose": purpose,
        })
    assert response.status_code == 200
    body = response.json()
    asset = db.get_media_asset(OWNER, body["asset"]["id"])
    assert asset["status"] == "pending"
    if purpose == "photo_clue_submission":
        decoded = jwt.decode(body["attachment_token"], config.MEDIA_UPLOAD_SECRET, algorithms=["HS256"], issuer=ISSUER, audience=AUDIENCE)
        assert decoded["owner_wallet_id"] == OWNER
        assert decoded["asset_id"] == asset["id"]
        assert decoded["scope"] == SCOPE
    else:
        assert "attachment_token" not in body


def test_upload_endpoint_requires_authentication_before_issuing_capability():
    with TestClient(main.app) as client:
        response = client.post("/media/upload-url", json={
            "filename": "photo.webp", "mime_type": "image/webp", "bytes": 1234, "purpose": "photo_clue_submission",
        })
    assert response.status_code == 401
    assert "attachment_token" not in response.json()


class MockWebSocket:
    def __init__(self):
        self.messages = []

    async def send_json(self, message):
        self.messages.append(message)


def photo_room():
    room = Room("PHOTO1", {}, time_limit=30, game_type="photo_clue")
    for client_id, nickname in (("alice", "Alice"), ("bob", "Bob")):
        room.players[client_id] = {"nickname": nickname, "score": 0, "prev_rank": 0, "streak": 0, "avatar": ""}
        room.connections[client_id] = MockWebSocket()
    room.photo_clue_state = create_initial_state(["Alice", "Bob"], {})
    room.state = room.photo_clue_state["phase"]
    return room


@pytest.mark.asyncio
async def test_socket_ignores_spoofed_url_and_uses_signed_owner_canonical_url():
    create_asset()
    room = photo_room()
    manager = SocketManager()
    await manager._photo_clue_player_action(room, "alice", {
        "type": "PHOTO_CLUE_UPLOAD_READY", "asset_id": ASSET_ID,
        "attachment_token": issue_attachment_token(ASSET_ID, OWNER),
        "image_url": "https://attacker.example.test/tracker", "owner_wallet_id": OTHER_OWNER,
    })
    assert room.state == PHASE_GUESSING
    assert room.photo_clue_state["assignments"][0]["image_url"] == PUBLIC_URL
    assert room.connections["bob"].messages[-1]["photo_clue"]["image_url"] == PUBLIC_URL


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["proofless", "unknown", "wrong_owner", "pending", "expired", "wrong_actor"])
async def test_socket_rejects_ineligible_uploads_without_mutating_round(kind):
    if kind != "unknown":
        create_asset(owner=OTHER_OWNER if kind == "wrong_owner" else OWNER, status="pending" if kind == "pending" else "ready")
    token = issue_attachment_token(ASSET_ID, OWNER, now=time.time() - 120 if kind == "expired" else None)
    room = photo_room()
    actor = "bob" if kind == "wrong_actor" else "alice"
    await SocketManager()._photo_clue_player_action(room, actor, {
        "type": "PHOTO_CLUE_UPLOAD_READY", "asset_id": ASSET_ID,
        "attachment_token": "" if kind == "proofless" else token,
        "image_url": "https://attacker.example.test/tracker",
    })
    assert room.state == PHASE_WAITING_FOR_PHOTO
    assert not room.photo_clue_state["assignments"][0].get("image_url")
    assert room.answer_log == []
    assert room.connections[actor].messages[-1]["type"] == "ERROR"
