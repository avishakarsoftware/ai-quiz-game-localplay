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
def isolate_test_database(tmp_path, monkeypatch):
    """Give every test its own SQLite file instead of the shared dev database.

    Before this, `DB_DIR` defaulted to `backend/data`, so pytest wrote to the SAME
    `backend/data/revelry.db` used by `make dev` and the local e2e suite. Consequences seen in
    practice:
      - two agents running suites concurrently produced four "insufficient balance" failures that
        looked exactly like an economy bug and were pure cross-contamination;
      - `test_e2e.py::TestTokenEconomyE2E::test_history_scoped_to_wallet` asserts an ABSOLUTE row
        count, so it broke whenever anything else had written — the documented flake where three
        consecutive runs gave 20 pass / 1 fail / 3 fail with runtime doubling each time;
      - running the tests mutated the developer's own dev data.

    Five test files already did this by hand (test_auth, test_admin, test_money_rails,
    test_round1_fixes, test_wallet_identity); the other 76 did not. Doing it here covers all of them.
    Those five keep their own fixtures — harmless, they just nest into another tmp dir.

    Replacing `db._local` wholesale is the load-bearing part: connections are cached thread-locally
    and `_get_conn()` only reads `DB_PATH` when it opens one, so without a fresh `threading.local()`
    an already-open handle to the old path would survive the patch.
    """
    import threading
    monkeypatch.setattr(db, "_local", threading.local())
    monkeypatch.setattr(db, "DB_DIR", str(tmp_path))
    monkeypatch.setattr(db, "DB_PATH", os.path.join(str(tmp_path), "revelry.db"))
    # Create the schema HERE, not in fund_test_wallet. test_e2e.py overrides fund_test_wallet with a
    # no-op (it wants the real token functions), so an init_db() living there never runs for that
    # suite. That went unnoticed only because the shared dev database was already initialised — the
    # moment each test got a fresh empty file, all 20 e2e tests failed with "no such table: wallets".
    # Schema creation belongs with database creation, and this fixture is not overridden anywhere.
    db.init_db()
    yield


@pytest.fixture(autouse=True)
def fund_test_wallet(isolate_test_database, monkeypatch):
    """Bypass token spending in tests so /room/create and /generate don't fail with 402.
    Tests that specifically test the token system should use their own fixtures."""
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
