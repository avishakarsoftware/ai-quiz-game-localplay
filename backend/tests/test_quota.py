"""Tests for AIQuotaExceeded handling in quiz/MLT generation endpoints."""
import sys
import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import httpx
from fastapi.testclient import TestClient
from main import app
from quiz_engine import AIQuotaExceeded, DailyLimitExceeded, QuizEngine, PROVIDERS
from mlt_engine import MLTEngine, PROVIDERS as MLT_PROVIDERS


client = TestClient(app)


def _fresh_device_headers():
    """Return headers with a unique device ID to avoid free-tier contamination."""
    import uuid
    return {"X-Device-Id": str(uuid.uuid4())}


def _make_httpx_status_error(status_code: int, body: bytes = b"{}") -> httpx.HTTPStatusError:
    """Create an httpx.HTTPStatusError with the given status code."""
    request = httpx.Request("POST", "https://example.com")
    response = httpx.Response(status_code, request=request, content=body)
    return httpx.HTTPStatusError(
        f"HTTP {status_code}",
        request=request,
        response=response,
    )


def _mock_async_client_post(error: Exception):
    """Create a mock httpx.AsyncClient whose post() raises the given error."""
    mock_client = AsyncMock()
    mock_client.post.side_effect = error
    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_client)
    mock_context.__aexit__ = AsyncMock(return_value=False)
    return mock_context


# ---------------------------------------------------------------------------
# Endpoint-level tests (mock at the engine level)
# ---------------------------------------------------------------------------

class TestQuotaEndpoints:
    """Test that AIQuotaExceeded returns 503 from the API endpoints."""

    def test_quiz_generate_returns_503_on_quota_exceeded(self):
        with patch('main.quiz_engine.generate_quiz', new_callable=AsyncMock) as mock_gen:
            mock_gen.side_effect = AIQuotaExceeded("quota exceeded")
            res = client.post("/quiz/generate", json={
                "prompt": "test topic",
                "difficulty": "medium",
                "num_questions": 5,
            }, headers=_fresh_device_headers())
            assert res.status_code == 503
            assert "Free tier limit" in res.json()["detail"]

    def test_mlt_generate_returns_503_on_quota_exceeded(self):
        with patch('main.mlt_engine.generate_statements', new_callable=AsyncMock) as mock_gen:
            mock_gen.side_effect = AIQuotaExceeded("quota exceeded")
            res = client.post("/mlt/generate", json={
                "prompt": "test theme",
                "difficulty": "medium",
                "num_rounds": 5,
            }, headers=_fresh_device_headers())
            assert res.status_code == 503
            assert "Free tier limit" in res.json()["detail"]

    def test_quiz_generate_returns_429_on_daily_limit(self):
        with patch('main.quiz_engine.generate_quiz', new_callable=AsyncMock) as mock_gen:
            mock_gen.side_effect = DailyLimitExceeded()
            res = client.post("/quiz/generate", json={
                "prompt": "test topic",
                "difficulty": "medium",
                "num_questions": 5,
            }, headers=_fresh_device_headers())
            assert res.status_code == 429
            assert "Daily" in res.json()["detail"]

    def test_quiz_generate_returns_500_on_generation_failure(self):
        with patch('main.quiz_engine.generate_quiz', new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = None
            res = client.post("/quiz/generate", json={
                "prompt": "test topic",
                "difficulty": "medium",
                "num_questions": 5,
            }, headers=_fresh_device_headers())
            assert res.status_code == 500
            assert "Failed" in res.json()["detail"]


# ---------------------------------------------------------------------------
# Engine-level tests (mock at the provider function level)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio(loop_scope="function")
class TestQuotaInEngine:
    """Test that the engine handles AIQuotaExceeded correctly."""

    async def test_daily_count_rolls_back_on_quota_exceeded(self):
        engine = QuizEngine()
        initial_count = engine._daily_count

        failing_gen = AsyncMock(side_effect=AIQuotaExceeded("quota exceeded"))
        with patch.dict(PROVIDERS, {"gemini": failing_gen}):
            with pytest.raises(AIQuotaExceeded):
                await engine.generate_quiz("test", "medium", 5, "gemini")
            assert engine._daily_count == initial_count

    async def test_gemini_429_raises_quota_exceeded(self):
        """Simulate a 429 response from Gemini API."""
        error = _make_httpx_status_error(429)
        mock_ctx = _mock_async_client_post(error)

        with patch('quiz_engine.httpx.AsyncClient', return_value=mock_ctx):
            with pytest.raises(AIQuotaExceeded):
                from quiz_engine import _generate_gemini
                await _generate_gemini("test", "medium", 5)

    async def test_gemini_403_raises_quota_exceeded(self):
        """Simulate a 403 response from Gemini API."""
        error = _make_httpx_status_error(403)
        mock_ctx = _mock_async_client_post(error)

        with patch('quiz_engine.httpx.AsyncClient', return_value=mock_ctx):
            with pytest.raises(AIQuotaExceeded):
                from quiz_engine import _generate_gemini
                await _generate_gemini("test", "medium", 5)

    async def test_gemini_500_retries_and_returns_none(self):
        """A 500 from Gemini should NOT raise AIQuotaExceeded — should retry then return None."""
        error = _make_httpx_status_error(500)
        mock_ctx = _mock_async_client_post(error)

        with patch('quiz_engine.httpx.AsyncClient', return_value=mock_ctx), \
             patch('quiz_engine.asyncio.sleep', new_callable=AsyncMock):
            from quiz_engine import _generate_gemini
            result = await _generate_gemini("test", "medium", 5)
            assert result is None


# ---------------------------------------------------------------------------
# MLT engine-level tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio(loop_scope="function")
class TestMLTQuotaInEngine:
    """Test that the MLT engine handles AIQuotaExceeded correctly."""

    async def test_mlt_daily_count_rolls_back_on_quota_exceeded(self):
        engine = MLTEngine()
        initial_count = engine._daily_count

        failing_gen = AsyncMock(side_effect=AIQuotaExceeded("quota exceeded"))
        with patch.dict(MLT_PROVIDERS, {"gemini": failing_gen}):
            with pytest.raises(AIQuotaExceeded):
                await engine.generate_statements("test theme", "medium", 5, "gemini")
            assert engine._daily_count == initial_count

    async def test_mlt_daily_count_rolls_back_on_generation_failure(self):
        """Daily count should decrement when provider returns None."""
        engine = MLTEngine()
        initial_count = engine._daily_count

        failing_gen = AsyncMock(return_value=None)
        with patch.dict(MLT_PROVIDERS, {"gemini": failing_gen}):
            result = await engine.generate_statements("test theme", "medium", 5, "gemini")
            assert result is None
            assert engine._daily_count == initial_count

    async def test_mlt_gemini_429_raises_quota_exceeded(self):
        """Simulate a 429 response from Gemini API in MLT engine."""
        error = _make_httpx_status_error(429)
        mock_ctx = _mock_async_client_post(error)

        with patch('mlt_engine.httpx.AsyncClient', return_value=mock_ctx):
            from mlt_engine import _generate_gemini as mlt_generate_gemini
            with pytest.raises(AIQuotaExceeded):
                await mlt_generate_gemini("test theme", "medium", 5)

    async def test_mlt_gemini_403_raises_quota_exceeded(self):
        """Simulate a 403 response from Gemini API in MLT engine."""
        error = _make_httpx_status_error(403)
        mock_ctx = _mock_async_client_post(error)

        with patch('mlt_engine.httpx.AsyncClient', return_value=mock_ctx):
            from mlt_engine import _generate_gemini as mlt_generate_gemini
            with pytest.raises(AIQuotaExceeded):
                await mlt_generate_gemini("test theme", "medium", 5)

    async def test_mlt_gemini_500_retries_and_returns_none(self):
        """A 500 from Gemini in MLT should NOT raise AIQuotaExceeded."""
        error = _make_httpx_status_error(500)
        mock_ctx = _mock_async_client_post(error)

        with patch('mlt_engine.httpx.AsyncClient', return_value=mock_ctx), \
             patch('mlt_engine.asyncio.sleep', new_callable=AsyncMock):
            from mlt_engine import _generate_gemini as mlt_generate_gemini
            result = await mlt_generate_gemini("test theme", "medium", 5)
            assert result is None


class TestMLTQuotaEndpoints:
    """Test MLT endpoint error responses."""

    def test_mlt_daily_limit_returns_429(self):
        with patch('main.mlt_engine.generate_statements', new_callable=AsyncMock) as mock_gen, \
             patch('main._check_rate_limit', return_value=True):
            mock_gen.side_effect = DailyLimitExceeded()
            res = client.post("/mlt/generate", json={
                "prompt": "test theme",
                "difficulty": "medium",
                "num_rounds": 5,
            }, headers=_fresh_device_headers())
            assert res.status_code == 429
            assert "Daily" in res.json()["detail"]

    def test_mlt_generate_returns_500_on_failure(self):
        with patch('main.mlt_engine.generate_statements', new_callable=AsyncMock) as mock_gen, \
             patch('main._check_rate_limit', return_value=True):
            mock_gen.return_value = None
            res = client.post("/mlt/generate", json={
                "prompt": "test theme",
                "difficulty": "medium",
                "num_rounds": 5,
            }, headers=_fresh_device_headers())
            assert res.status_code == 500
            assert "Failed" in res.json()["detail"]
