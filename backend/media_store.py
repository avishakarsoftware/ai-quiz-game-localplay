"""Shared media asset helpers for generated and uploaded game images.

Phase 0 keeps assets in memory, matching the existing quiz image behavior, while
giving future image games a stable `/media/{asset_id}` surface to build on.
"""

from __future__ import annotations

import base64
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class ImageAsset:
    id: str
    owner_wallet_id: str
    source: str
    provider: str
    status: str
    mime_type: str
    width: int
    height: int
    bytes: int
    url: str
    thumbnail_url: Optional[str]
    prompt: Optional[str]
    alt_text: Optional[str]
    safety_status: str
    created_at: int
    expires_at: Optional[int]

    def to_dict(self) -> dict:
        return asdict(self)


class InMemoryMediaStore:
    def __init__(self):
        self._assets: Dict[str, ImageAsset] = {}
        self._image_b64: Dict[str, str] = {}

    def create_generated_image(
        self,
        image_b64: str,
        *,
        owner_wallet_id: str,
        provider: str,
        prompt: str,
        alt_text: str = "",
        mime_type: str = "image/png",
        width: int = 768,
        height: int = 432,
        ttl_seconds: int = 3600,
    ) -> ImageAsset:
        raw = base64.b64decode(image_b64, validate=True)
        asset_id = f"img_{uuid.uuid4().hex}"
        now = int(time.time())
        asset = ImageAsset(
            id=asset_id,
            owner_wallet_id=owner_wallet_id,
            source="generated",
            provider=provider,
            status="ready",
            mime_type=mime_type,
            width=width,
            height=height,
            bytes=len(raw),
            url=f"/media/{asset_id}",
            thumbnail_url=None,
            prompt=prompt,
            alt_text=alt_text or prompt,
            safety_status="passed",
            created_at=now,
            expires_at=now + ttl_seconds if ttl_seconds > 0 else None,
        )
        self._assets[asset_id] = asset
        self._image_b64[asset_id] = image_b64
        return asset

    def get_asset(self, asset_id: str) -> Optional[ImageAsset]:
        asset = self._assets.get(asset_id)
        if not asset:
            return None
        if asset.expires_at and asset.expires_at < int(time.time()):
            self.delete(asset_id)
            return None
        return asset

    def get_image_bytes(self, asset_id: str) -> Optional[bytes]:
        asset = self.get_asset(asset_id)
        if not asset:
            return None
        image_b64 = self._image_b64.get(asset_id)
        if not image_b64:
            return None
        return base64.b64decode(image_b64, validate=True)

    def delete(self, asset_id: str):
        self._assets.pop(asset_id, None)
        self._image_b64.pop(asset_id, None)

    def clear(self):
        self._assets.clear()
        self._image_b64.clear()


media_store = InMemoryMediaStore()
