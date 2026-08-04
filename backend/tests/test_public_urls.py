"""User-facing link hosts vs backend-served asset hosts (found by the prod regression suite).

Prod had `PUBLIC_BASE_URL=https://gamesapi.revelryapp.me`, so every referral and share link handed
to a user pointed at the **API host** rather than the canonical site. It works — the backend serves
the SPA — but it is not the branded host and looks untrustworthy in a link preview, which matters
because share links are one of the few organic install paths.

The subtlety that makes this worth a test: the naive fix (repoint PUBLIC_BASE_URL at the site)
would BREAK share cards, because the dynamic OG image is a *backend* route
(`/share/game/{token}/image.png`) that does not exist on the static site. So the two concepts are
now separate and this file pins that separation in both directions.
"""
import importlib

import config
import share


def _reload(monkeypatch, base: str, site: str = ""):
    monkeypatch.setenv("PUBLIC_BASE_URL", base)
    if site:
        monkeypatch.setenv("PUBLIC_SITE_URL", site)
    else:
        monkeypatch.delenv("PUBLIC_SITE_URL", raising=False)
    importlib.reload(config)
    return config


class TestSiteUrlDefaulting:
    def test_site_url_defaults_to_base_so_nothing_changes_until_configured(self, monkeypatch):
        cfg = _reload(monkeypatch, "https://api.example.com")
        assert cfg.PUBLIC_SITE_URL == "https://api.example.com"

    def test_site_url_overrides_independently(self, monkeypatch):
        cfg = _reload(monkeypatch, "https://api.example.com", "https://site.example.com")
        assert cfg.PUBLIC_BASE_URL == "https://api.example.com"
        assert cfg.PUBLIC_SITE_URL == "https://site.example.com"

    def test_trailing_slashes_are_stripped_so_urls_never_double_slash(self, monkeypatch):
        cfg = _reload(monkeypatch, "https://api.example.com/", "https://site.example.com/")
        assert not cfg.PUBLIC_SITE_URL.endswith("/")
        assert not cfg.PUBLIC_BASE_URL.endswith("/")


class TestShareCardHostSplit:
    """The OG image MUST stay on the backend; the tap-through link MUST go to the site."""

    def test_og_image_points_at_the_backend_not_the_site(self, monkeypatch):
        monkeypatch.setattr(config, "PUBLIC_BASE_URL", "https://api.example.com")
        monkeypatch.setattr(config, "PUBLIC_SITE_URL", "https://site.example.com")
        html = share.render_html({
            "token": "tok123", "game_type": "quiz", "winner": "Maya",
            "top_score": 900, "player_count": 4, "created_at": 0,
        })
        # The dynamic image endpoint only exists on the backend. If this ever points at the static
        # site, every shared link renders with a broken preview image.
        assert "https://api.example.com/share/game/tok123/image.png" in html

    def test_tap_through_link_points_at_the_site_not_the_api(self, monkeypatch):
        monkeypatch.setattr(config, "PUBLIC_BASE_URL", "https://api.example.com")
        monkeypatch.setattr(config, "PUBLIC_SITE_URL", "https://site.example.com")
        html = share.render_html({
            "token": "tok123", "game_type": "quiz", "winner": "Maya",
            "top_score": 900, "player_count": 4, "created_at": 0,
        })
        assert "https://site.example.com" in html

    def test_both_hosts_appear_when_they_differ(self, monkeypatch):
        """Guards a lazy fix that collapses the two back into one value."""
        monkeypatch.setattr(config, "PUBLIC_BASE_URL", "https://api.example.com")
        monkeypatch.setattr(config, "PUBLIC_SITE_URL", "https://site.example.com")
        html = share.render_html({
            "token": "t", "game_type": "quiz", "winner": "M",
            "top_score": 1, "player_count": 2, "created_at": 0,
        })
        assert "api.example.com" in html and "site.example.com" in html
