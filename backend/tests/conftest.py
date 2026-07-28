"""Shared test fixtures for backend tests."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
# Also expose the tests dir itself so suites can share test-only helpers (ws_test_utils) without
# shipping them inside the application package.
sys.path.insert(0, os.path.dirname(__file__))

import pytest
import config
import db
import main
import room_snapshot
import tokens as tokens_mod

# Standard test device ID used across test helpers
TEST_DEVICE_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def isolate_room_snapshots(tmp_path, monkeypatch):
    """Keep room snapshots out of the real data dir during tests.

    Without this, every TestClient lifespan startup restores rooms leaked by
    earlier test runs (50 snapshots -> MAX_ROOMS -> 429 on /room/create).
    Snapshotting is disabled by default; test_room_snapshot re-enables it and
    points SNAPSHOT_DIR at its own tmp dir.
    """
    monkeypatch.setattr(room_snapshot, "SNAPSHOT_DIR", str(tmp_path / "room_snapshots"))
    monkeypatch.setattr(config, "ROOM_SNAPSHOT_ENABLED", False)
    yield


@pytest.fixture(autouse=True)
def fund_test_wallet(monkeypatch):
    """Bypass token spending in tests so /room/create and /generate don't fail with 402.
    Tests that specifically test the token system should use their own fixtures."""
    db.init_db()
    main._rate_limit_store.clear()
    main._llm_call_timestamps.clear()

    # Make spend_generate and spend_room always succeed (return True, 999)
    monkeypatch.setattr(tokens_mod, "spend_generate", lambda wallet_id: (True, 999))
    monkeypatch.setattr(tokens_mod, "spend_room", lambda wallet_id: (True, 999))
    # Make can_generate and can_create_room always return True
    monkeypatch.setattr(tokens_mod, "can_generate", lambda wallet_id: True)
    monkeypatch.setattr(tokens_mod, "can_create_room", lambda wallet_id: True)
    # Make ensure_wallet a no-op
    monkeypatch.setattr(tokens_mod, "ensure_wallet", lambda wallet_id: {"id": wallet_id, "balance": 999})
    # Make use_premium_model return False by default
    monkeypatch.setattr(tokens_mod, "use_premium_model", lambda wallet_id: False)
    # Make get_wallet_id return a stable test device ID (so /room/create doesn't 400)
    monkeypatch.setattr(tokens_mod, "get_wallet_id", lambda req: TEST_DEVICE_ID)

    yield
    main._rate_limit_store.clear()
    main._llm_call_timestamps.clear()
