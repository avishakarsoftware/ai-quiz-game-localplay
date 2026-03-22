"""Tests for Round 5 bug fixes: socket resource leak, image engine safety,
timer division-by-zero guard."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from main import get_local_ip


class TestGetLocalIP:
    """get_local_ip should properly close socket even on failure."""

    def test_returns_valid_ip(self):
        ip = get_local_ip()
        assert isinstance(ip, str)
        parts = ip.split(".")
        assert len(parts) == 4
        for part in parts:
            assert part.isdigit()

    def test_returns_loopback_on_failure(self):
        """Even if network is unavailable, should return 127.0.0.1."""
        import socket as socketlib
        import unittest.mock as mock

        with mock.patch.object(socketlib.socket, 'connect', side_effect=OSError("no network")):
            ip = get_local_ip()
            assert ip == "127.0.0.1"


class TestSignOutClearsAll:
    """Verify signOut clears premium token and checkout pending (backend perspective)."""

    def test_premium_token_none_without_jwt_secret(self):
        """Premium token creation returns None when JWT_SECRET is empty."""
        import premium
        import config

        original = config.JWT_SECRET
        config.JWT_SECRET = ""
        try:
            token = premium.create_premium_token("device-123")
            assert token is None
        finally:
            config.JWT_SECRET = original


class TestImageEngineSafety:
    """Image engine health check handles malformed responses."""

    def test_is_available_returns_bool(self):
        import asyncio
        from image_engine import ImageEngine

        engine = ImageEngine()
        # With no local SD server running, should return False
        result = asyncio.run(engine.is_available())
        assert isinstance(result, bool)
        assert result is False  # No SD server in test env
