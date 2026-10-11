"""Authorize Photo Clue attachment without trusting a socket's wallet or URL."""

import time

import jwt

import config
import tokens as token_module


ISSUER = "localplay.media"
AUDIENCE = "photo_clue"
SCOPE = "photo_clue_submission"


def issue_attachment_token(asset_id: str, owner_wallet_id: str, *, now: float | None = None) -> str:
    if not config.MEDIA_UPLOAD_SECRET or not asset_id or not owner_wallet_id:
        raise ValueError("Photo upload attachment is unavailable")
    issued_at = int(time.time() if now is None else now)
    return jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "scope": SCOPE,
            "asset_id": asset_id,
            "owner_wallet_id": owner_wallet_id,
            "iat": issued_at,
            "exp": issued_at + config.MEDIA_UPLOAD_TOKEN_TTL_SECONDS,
        },
        config.MEDIA_UPLOAD_SECRET,
        algorithm="HS256",
    )


def resolve_attachment(asset_id: str, attachment_token: str) -> dict:
    """Resolve only the signed owner's ready asset; remote bytes are not verified here."""
    if not config.MEDIA_UPLOAD_SECRET or not isinstance(attachment_token, str) or not attachment_token:
        raise ValueError("Photo upload attachment token is required")
    try:
        claims = jwt.decode(
            attachment_token,
            config.MEDIA_UPLOAD_SECRET,
            algorithms=["HS256"],
            issuer=ISSUER,
            audience=AUDIENCE,
            options={
                "require": ["iss", "aud", "scope", "asset_id", "owner_wallet_id", "iat", "exp"],
                "strict_aud": True,
            },
        )
    except (jwt.PyJWTError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Photo upload attachment is invalid or expired; upload it again") from exc
    owner_wallet_id = claims.get("owner_wallet_id")
    if (
        claims.get("scope") != SCOPE
        or not isinstance(asset_id, str)
        or not asset_id
        or claims.get("asset_id") != asset_id
        or not isinstance(owner_wallet_id, str)
        or not owner_wallet_id
        or type(claims.get("iat")) is not int
        or type(claims.get("exp")) is not int
        or claims["exp"] <= claims["iat"]
    ):
        raise ValueError("Photo upload attachment does not match this asset")
    asset = token_module.db.get_media_asset(owner_wallet_id, asset_id)
    if not asset:
        raise ValueError("Photo upload was not found for its owner")
    if asset.get("status") != "ready":
        raise ValueError("Photo upload is not ready yet")
    if not isinstance(asset.get("public_url"), str) or not asset["public_url"].strip():
        raise ValueError("Photo upload has no image URL")
    return asset
