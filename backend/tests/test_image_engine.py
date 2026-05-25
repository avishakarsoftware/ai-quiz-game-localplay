import asyncio

import httpx

import config
from image_engine import ImageEngine


class _FakeResponse:
    status_code = 200

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body

    def raise_for_status(self):
        return None


class _FakeAsyncClient:
    def __init__(self, response, calls):
        self.response = response
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def test_gemini_image_generation_extracts_inline_image(monkeypatch):
    monkeypatch.setattr(config, "IMAGE_GENERATION_PROVIDER", "gemini")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(config, "GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
    calls = []
    response = _FakeResponse({
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": "image/png",
                                "data": "aGVsbG8=",
                            }
                        }
                    ]
                }
            }
        ]
    })
    monkeypatch.setattr(httpx, "AsyncClient", lambda *args, **kwargs: _FakeAsyncClient(response, calls))

    image = asyncio.run(ImageEngine().generate_image("a party cake"))

    assert image == "aGVsbG8="
    assert "gemini-2.5-flash-image:generateContent" in calls[0][0]
    assert calls[0][1]["headers"]["x-goog-api-key"] == "test-key"
    assert calls[0][1]["json"]["generationConfig"]["responseModalities"] == ["Image"]


def test_gemini_image_generation_availability_is_config_gated(monkeypatch):
    monkeypatch.setattr(config, "IMAGE_GENERATION_PROVIDER", "gemini")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")

    assert asyncio.run(ImageEngine().is_available()) is False

    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(config, "GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")

    assert asyncio.run(ImageEngine().is_available()) is True
