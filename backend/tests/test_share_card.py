"""Tests for shareable result cards (SPEC-SHARE-CARD)."""
from fastapi.testclient import TestClient

import share
import config
from main import app

client = TestClient(app)


def test_snapshot_roundtrip_and_render():
    token = share.create_snapshot("quiz", "Maya", 973, 3)
    snap = share.get_snapshot(token)
    assert snap and snap["winner"] == "Maya" and snap["top_score"] == 973
    html_out = share.render_html(snap)
    assert "Maya won with 973" in html_out
    assert "3 players" in html_out
    assert "og:title" in html_out


def test_unknown_token_renders_generic_page():
    assert share.get_snapshot("does-not-exist") is None
    html_out = share.render_html(None)
    assert "Revelry Games" in html_out
    assert "<title>" in html_out


def test_winner_html_tags_are_stripped():
    # A full tag payload is removed entirely on store — no active markup reaches the page.
    token = share.create_snapshot("quiz", "<img src=x onerror=alert(1)>Bob", 10, 2)
    html_out = share.render_html(share.get_snapshot(token))
    assert "onerror" not in html_out
    assert "<img" not in html_out
    assert "Bob" in html_out


def test_bare_angle_brackets_are_escaped():
    # A lone '<' (not a full tag) survives stripping but must be HTML-escaped on render.
    token = share.create_snapshot("quiz", "A<B", 10, 2)
    html_out = share.render_html(share.get_snapshot(token))
    assert "A&lt;B" in html_out
    assert "A<B" not in html_out


def test_ttl_expiry(monkeypatch):
    token = share.create_snapshot("quiz", "Leo", 500, 4)
    # Age the snapshot beyond TTL.
    share._snapshots[token]["created_at"] -= (config.SHARE_TTL_SECONDS + 10)
    assert share.get_snapshot(token) is None


def test_eviction_bounds_store(monkeypatch):
    monkeypatch.setattr(config, "MAX_SHARE_SNAPSHOTS", 5)
    share._snapshots.clear()
    tokens = [share.create_snapshot("quiz", f"P{i}", i, 2) for i in range(20)]
    assert len(share._snapshots) <= 5
    # newest survive, oldest evicted
    assert share.get_snapshot(tokens[-1]) is not None


def test_get_endpoint_returns_html():
    token = share.create_snapshot("wmlt", "Ada", 42, 5)
    res = client.get(f"/share/game/{token}")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "Ada won with 42" in res.text
