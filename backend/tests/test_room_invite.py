"""GET /room/{code}/invite — the host's referral code, for their guests (REVIEW-2026-08 P2).

Referrals were only visible in the host's SettingsDrawer, so guests never saw the loop. This
endpoint feeds the player podium, which is the actual viral moment: the guest who just had fun is
the most likely next host.

The contract that matters is that it NEVER breaks a podium: every failure path returns 200 with
available:false rather than an error the podium would have to handle.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

import config
import db
import main
from main import app
from socket_manager import socket_manager

client = TestClient(app)
HEADERS = {"X-Device-ID": "00000000-0000-0000-0000-000000000001"}


@pytest.fixture(autouse=True)
def _clean_rooms():
    socket_manager.rooms.clear()
    yield
    socket_manager.rooms.clear()


def _room_with_host_wallet(wallet_id: str) -> str:
    res = client.post("/room/create", json={"game_type": "two_truths", "time_limit": 30},
                      headers=HEADERS)
    assert res.status_code == 200, res.text
    code = res.json()["room_code"]
    socket_manager.rooms[code].wallet_id = wallet_id
    return code


def test_returns_the_hosts_code_and_reward():
    wallet = str(uuid.uuid4())
    db.get_or_create_wallet(wallet, signup_bonus=False)
    code = _room_with_host_wallet(wallet)

    res = client.get(f"/room/{code}/invite")
    assert res.status_code == 200
    body = res.json()
    assert body["available"] is True
    assert body["code"] == db.get_or_create_referral_code(wallet), "must be the HOST's own code"
    assert body["reward"] == config.REFERRAL_REWARD


def test_share_url_uses_the_brand_host_not_the_api_host(monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_SITE_URL", "https://games.revelryapp.me")
    wallet = str(uuid.uuid4())
    db.get_or_create_wallet(wallet, signup_bonus=False)
    code = _room_with_host_wallet(wallet)
    body = client.get(f"/room/{code}/invite").json()
    assert body["share_url"].startswith("https://games.revelryapp.me/?ref=")


def test_room_code_is_case_insensitive():
    """Guests type the code by hand; a lowercase entry must not silently lose the invite."""
    wallet = str(uuid.uuid4())
    db.get_or_create_wallet(wallet, signup_bonus=False)
    code = _room_with_host_wallet(wallet)
    assert client.get(f"/room/{code.lower()}/invite").json()["available"] is True


def test_unknown_room_is_unavailable_not_an_error():
    res = client.get("/room/ZZZZZZ/invite")
    assert res.status_code == 200, "a podium must never have to handle an error here"
    assert res.json()["available"] is False


def test_room_without_a_host_wallet_is_unavailable():
    """Revelry-hosted rooms have no organizer wallet to credit, so there is nobody to refer."""
    code = _room_with_host_wallet(str(uuid.uuid4()))
    socket_manager.rooms[code].wallet_id = None
    assert client.get(f"/room/{code}/invite").json()["available"] is False


def test_unavailable_when_referrals_are_disabled(monkeypatch):
    monkeypatch.setattr(main, "_REFERRALS_SUPPORTED", False)
    code = _room_with_host_wallet(str(uuid.uuid4()))
    res = client.get(f"/room/{code}/invite")
    assert res.status_code == 200
    assert res.json()["available"] is False, "the flag must hide the CTA, not 503 the podium"


def test_db_failure_degrades_to_unavailable(monkeypatch):
    wallet = str(uuid.uuid4())
    db.get_or_create_wallet(wallet, signup_bonus=False)
    code = _room_with_host_wallet(wallet)

    def boom(_wallet_id):
        raise RuntimeError("referral store down")

    monkeypatch.setattr(db, "get_or_create_referral_code", boom)
    res = client.get(f"/room/{code}/invite")
    assert res.status_code == 200
    assert res.json()["available"] is False
