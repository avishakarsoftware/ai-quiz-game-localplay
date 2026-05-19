"""Tests for remote_config module: URL construction, provider/model resolution,
cache behavior, and model_override propagation to all providers."""
import sys
import os
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import config


class TestRemoteConfigURL:
    """REMOTE_CONFIG_URL should include /quiz/ path prefix."""

    def test_url_from_allowed_origins_includes_quiz_path(self):
        """URL derived from ALLOWED_ORIGINS must include /quiz/config.json."""
        with mock.patch.object(config, 'REMOTE_CONFIG_URL', ''):
            with mock.patch.object(config, 'ALLOWED_ORIGINS', 'https://games.revelryapp.me'):
                # Re-import to re-evaluate module-level constant
                import importlib
                import remote_config
                importlib.reload(remote_config)
                assert remote_config.REMOTE_CONFIG_URL == 'https://games.revelryapp.me/quiz/config.json'

    def test_url_from_allowed_origins_strips_trailing_slash(self):
        """Trailing slash on origin should not cause double-slash."""
        with mock.patch.object(config, 'REMOTE_CONFIG_URL', ''):
            with mock.patch.object(config, 'ALLOWED_ORIGINS', 'https://games.revelryapp.me/'):
                import importlib
                import remote_config
                importlib.reload(remote_config)
                assert remote_config.REMOTE_CONFIG_URL == 'https://games.revelryapp.me/quiz/config.json'

    def test_explicit_env_var_takes_precedence(self):
        """Explicit REMOTE_CONFIG_URL env var should override derivation."""
        with mock.patch.object(config, 'REMOTE_CONFIG_URL', 'https://custom.example.com/config.json'):
            with mock.patch.object(config, 'ALLOWED_ORIGINS', 'https://games.revelryapp.me'):
                import importlib
                import remote_config
                importlib.reload(remote_config)
                assert remote_config.REMOTE_CONFIG_URL == 'https://custom.example.com/config.json'

    def test_empty_origins_yields_empty_url(self):
        """If no ALLOWED_ORIGINS and no explicit URL, URL should be empty."""
        with mock.patch.object(config, 'REMOTE_CONFIG_URL', ''):
            with mock.patch.object(config, 'ALLOWED_ORIGINS', ''):
                import importlib
                import remote_config
                importlib.reload(remote_config)
                assert remote_config.REMOTE_CONFIG_URL == ''

    def test_multiple_origins_uses_first(self):
        """When ALLOWED_ORIGINS has multiple entries, use the first one."""
        with mock.patch.object(config, 'REMOTE_CONFIG_URL', ''):
            with mock.patch.object(config, 'ALLOWED_ORIGINS', 'https://games.revelryapp.me, https://localhost:5173'):
                import importlib
                import remote_config
                importlib.reload(remote_config)
                assert remote_config.REMOTE_CONFIG_URL == 'https://games.revelryapp.me/quiz/config.json'


class TestRemoteConfigProviderResolution:
    """get_provider() should return remote config value, falling back to DEFAULT_PROVIDER."""

    def test_returns_remote_provider(self):
        import remote_config
        remote_config._cached_config = {"ai_models": {"provider": "claude"}}
        assert remote_config.get_provider() == "claude"

    def test_falls_back_to_default_provider(self):
        import remote_config
        remote_config._cached_config = {"ai_models": {}}
        assert remote_config.get_provider() == config.DEFAULT_PROVIDER

    def test_falls_back_on_malformed_config(self):
        import remote_config
        remote_config._cached_config = "not a dict"
        assert remote_config.get_provider() == config.DEFAULT_PROVIDER

    def test_falls_back_on_empty_string_provider(self):
        import remote_config
        remote_config._cached_config = {"ai_models": {"provider": ""}}
        assert remote_config.get_provider() == config.DEFAULT_PROVIDER


class TestRemoteConfigModelResolution:
    """get_free_model() and get_paid_model() should respect remote config."""

    def test_returns_configured_models(self):
        import remote_config
        remote_config._cached_config = {
            "ai_models": {"free_model": "gemini-2.5-flash-lite", "paid_model": "gemini-2.5-flash-lite"}
        }
        assert remote_config.get_free_model() == "gemini-2.5-flash-lite"
        assert remote_config.get_paid_model() == "gemini-2.5-flash-lite"

    def test_falls_back_to_gemini_model(self):
        import remote_config
        remote_config._cached_config = {}
        assert remote_config.get_free_model() == config.GEMINI_MODEL
        assert remote_config.get_paid_model() == config.GEMINI_MODEL


class TestRemoteConfigCacheBehavior:
    """Cache should not clear on fetch failure."""

    def test_cache_preserved_on_failure(self):
        import remote_config
        remote_config._cached_config = {"ai_models": {"free_model": "good-model"}}
        remote_config._last_fetch = 0  # force stale

        async def _mock_fetch():
            # Simulate failure — don't touch _cached_config
            return None

        with mock.patch.object(remote_config, '_fetch_remote_config', _mock_fetch):
            import asyncio
            result = asyncio.run(remote_config.get_config())
            assert result.get("ai_models", {}).get("free_model") == "good-model"


class TestModelOverrideAllProviders:
    """model_override should propagate to all provider functions (gemini, ollama, claude)."""

    def test_quiz_ollama_accepts_model_override(self):
        from quiz_engine import _generate_ollama
        import inspect
        sig = inspect.signature(_generate_ollama)
        assert 'model_override' in sig.parameters

    def test_quiz_claude_accepts_model_override(self):
        from quiz_engine import _generate_claude
        import inspect
        sig = inspect.signature(_generate_claude)
        assert 'model_override' in sig.parameters

    def test_quiz_gemini_accepts_model_override(self):
        from quiz_engine import _generate_gemini
        import inspect
        sig = inspect.signature(_generate_gemini)
        assert 'model_override' in sig.parameters

    def test_mlt_ollama_accepts_model_override(self):
        from mlt_engine import _generate_ollama
        import inspect
        sig = inspect.signature(_generate_ollama)
        assert 'model_override' in sig.parameters

    def test_mlt_claude_accepts_model_override(self):
        from mlt_engine import _generate_claude
        import inspect
        sig = inspect.signature(_generate_claude)
        assert 'model_override' in sig.parameters

    def test_mlt_gemini_accepts_model_override(self):
        from mlt_engine import _generate_gemini
        import inspect
        sig = inspect.signature(_generate_gemini)
        assert 'model_override' in sig.parameters
