"""Hardening tests for the Revelry partner integration contract.

Covers fixes made June 2026:
- Session/party-link game_type validators accept every Revelry host-app start
  type, not just quiz (the dedicated-authoring-route copy/paste leftover).
- _require_revelry_auth only trusts handoff JWTs that are addressed to LocalPlay
  (aud=localplay), issued by Revelry (iss=revelry), and typed as a launch token.
- _validate_revelry_return_url normalizes explicit default ports.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import config
import main
from main import (
    REVELRY_PARTY_GAME_START_TYPES,
    RevelryExternalContext,
    RevelryPartyGamesLinkRequest,
    RevelrySessionCreateRequest,
    _require_revelry_auth,
    _validate_revelry_return_url,
)


SECRET = "test-revelry-secret"


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", SECRET)
    yield


def _ctx():
    return {"external_container_id": "party-1", "host_app": "revelry"}


# --- game_type validators ---------------------------------------------------

@pytest.mark.parametrize("game_type", list(REVELRY_PARTY_GAME_START_TYPES))
def test_session_create_accepts_all_launchable_game_types(game_type):
    req = RevelrySessionCreateRequest(external_context=_ctx(), game_type=game_type)
    assert req.game_type == game_type


@pytest.mark.parametrize("game_type", list(REVELRY_PARTY_GAME_START_TYPES))
def test_party_link_accepts_all_launchable_game_types(game_type):
    req = RevelryPartyGamesLinkRequest(external_context=_ctx(), game_type=game_type)
    assert req.game_type == game_type


def test_session_create_rejects_unknown_game_type():
    with pytest.raises(ValidationError):
        RevelrySessionCreateRequest(external_context=_ctx(), game_type="not_a_real_game")


def test_party_link_rejects_unknown_game_type():
    with pytest.raises(ValidationError):
        RevelryPartyGamesLinkRequest(external_context=_ctx(), game_type="not_a_real_game")


# --- _require_revelry_auth handoff validation -------------------------------

def _handoff_token(
    *,
    iss="revelry",
    aud="localplay",
    typ="localplay_launch",
    exp_delta=600,
    include_aud=True,
    include_typ=True,
):
    now = datetime.now(timezone.utc)
    payload = {
        "iss": iss,
        "scope": "player",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=exp_delta)).timestamp()),
    }
    if include_aud:
        payload["aud"] = aud
    if include_typ:
        payload["typ"] = typ
    return jwt.encode(payload, SECRET, algorithm="HS256")


def _req(token=None):
    headers = {}
    if token is not None:
        headers["authorization"] = f"Bearer {token}"
    return SimpleNamespace(headers=headers)


def test_auth_accepts_service_secret():
    claims = _require_revelry_auth(_req(SECRET))
    assert claims["type"] == "service"


def test_auth_accepts_valid_revelry_handoff_token():
    claims = _require_revelry_auth(_req(), handoff_token=_handoff_token())
    assert claims["iss"] == "revelry"
    assert claims["aud"] == "localplay"


def test_auth_rejects_handoff_without_audience():
    with pytest.raises(HTTPException) as exc:
        _require_revelry_auth(_req(), handoff_token=_handoff_token(include_aud=False))
    assert exc.value.status_code == 401


def test_auth_rejects_handoff_with_wrong_audience():
    with pytest.raises(HTTPException) as exc:
        _require_revelry_auth(_req(), handoff_token=_handoff_token(aud="someone-else"))
    assert exc.value.status_code == 401


def test_auth_rejects_localplay_issued_token_as_partner_credential():
    # A token LocalPlay minted for another purpose must not be accepted as a
    # partner handoff credential, even though it is signed with the same secret.
    with pytest.raises(HTTPException) as exc:
        _require_revelry_auth(_req(), handoff_token=_handoff_token(iss="localplay"))
    assert exc.value.status_code == 401


def test_auth_rejects_handoff_without_launch_type():
    with pytest.raises(HTTPException) as exc:
        _require_revelry_auth(_req(), handoff_token=_handoff_token(include_typ=False))
    assert exc.value.status_code == 401


def test_auth_rejects_handoff_with_wrong_launch_type():
    with pytest.raises(HTTPException) as exc:
        _require_revelry_auth(_req(), handoff_token=_handoff_token(typ="party_games"))
    assert exc.value.status_code == 401


def test_auth_rejects_expired_handoff_token():
    with pytest.raises(HTTPException) as exc:
        _require_revelry_auth(_req(), handoff_token=_handoff_token(exp_delta=-30))
    assert exc.value.status_code == 401


def test_auth_rejects_missing_credential():
    with pytest.raises(HTTPException) as exc:
        _require_revelry_auth(_req())
    assert exc.value.status_code == 401


# --- return url default-port normalization ----------------------------------

def test_return_url_accepts_explicit_default_https_port():
    assert (
        _validate_revelry_return_url("https://app.revelryapp.me:443/party/p1?tab=games")
        == "https://app.revelryapp.me:443/party/p1?tab=games"
    )


def test_return_url_accepts_host_without_port():
    assert (
        _validate_revelry_return_url("https://app.revelryapp.me/party/p1?tab=games")
        == "https://app.revelryapp.me/party/p1?tab=games"
    )


def test_return_url_still_rejects_spoofed_host():
    with pytest.raises(HTTPException) as exc:
        _validate_revelry_return_url("https://app.revelryapp.me.evil.com/steal")
    assert exc.value.status_code == 422


def test_return_url_rejects_wrong_explicit_port():
    with pytest.raises(HTTPException) as exc:
        _validate_revelry_return_url("https://app.revelryapp.me:8443/party/p1")
    assert exc.value.status_code == 422
