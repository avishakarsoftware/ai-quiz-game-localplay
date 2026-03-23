"""Shared test fixtures for backend tests."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
import db
import tokens as tokens_mod

# Standard test device ID used across test helpers
TEST_DEVICE_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def fund_test_wallet(monkeypatch):
    """Bypass token spending in tests so /room/create and /generate don't fail with 402.
    Tests that specifically test the token system should use their own fixtures."""
    db.init_db()

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

    yield
