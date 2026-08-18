"""Authoring, media, sessions, share cards, settings and admin lookup — on real PostgREST.

The last large uncovered block of `supabase_db.py` (ANALYSIS-2026-08-09-coverage.md §1). Not money,
but user-created content: a host's custom quiz packs and game content, uploaded images, the
Revelry-integration game sessions, share-card snapshots, the remote-config override store, and the
admin lookup the support runbook uses.

The recurring hazard in this block is OWNERSHIP SCOPING: every getter takes an `owner_wallet_id`,
and a filter that fails to constrain it would leak or delete another user's content. Each accessor
here is therefore tested with a *second, unrelated owner* present, not just a happy path.
"""
import uuid

import pytest

from postgrest_harness import (  # noqa: F401
    HARNESS_READY,
    SKIP_REASON,
    _proxy_base_url,
    postgrest_stack,
    sdb,
)

pytestmark = pytest.mark.skipif(not HARNESS_READY, reason=SKIP_REASON)


def _owner(sdb) -> str:
    wallet = str(uuid.uuid4())
    sdb.get_or_create_wallet(wallet, signup_bonus=False)
    return wallet


QUESTIONS = [
    {"id": 1, "text": "Q1?", "options": ["A", "B", "C", "D"], "answer_index": 0},
    {"id": 2, "text": "Q2?", "options": ["A", "B", "C", "D"], "answer_index": 2},
]


# --- quiz packs --------------------------------------------------------------

def test_quiz_pack_roundtrip(sdb):
    owner = _owner(sdb)
    saved = sdb.save_quiz_pack(owner, "My Pack", QUESTIONS)
    pack_id = saved["id"] if "id" in saved else saved.get("pack_id")
    assert pack_id, saved

    fetched = sdb.get_quiz_pack(owner, pack_id)
    assert fetched is not None
    assert len(fetched.get("questions") or []) == 2, "questions must survive the roundtrip"
    assert [q["text"] for q in fetched["questions"]] == ["Q1?", "Q2?"]

    assert any(p.get("id") == pack_id for p in sdb.list_quiz_packs(owner))


def test_quiz_pack_is_scoped_to_its_owner(sdb):
    owner, stranger = _owner(sdb), _owner(sdb)
    saved = sdb.save_quiz_pack(owner, "Private", QUESTIONS)
    pack_id = saved.get("id") or saved.get("pack_id")

    assert sdb.get_quiz_pack(stranger, pack_id) is None, "another wallet must not read this pack"
    assert sdb.list_quiz_packs(stranger) == [] or all(
        p.get("id") != pack_id for p in sdb.list_quiz_packs(stranger)
    )
    assert sdb.delete_quiz_pack(stranger, pack_id) is False, "another wallet must not delete it"
    assert sdb.get_quiz_pack(owner, pack_id) is not None, "and it must still be there"


def test_quiz_pack_update_replaces_questions(sdb):
    owner = _owner(sdb)
    saved = sdb.save_quiz_pack(owner, "V1", QUESTIONS)
    pack_id = saved.get("id") or saved.get("pack_id")
    sdb.save_quiz_pack(owner, "V2", [QUESTIONS[0]], pack_id=pack_id)
    fetched = sdb.get_quiz_pack(owner, pack_id)
    assert len(fetched["questions"]) == 1, "an edit must not leave orphaned questions behind"
    assert fetched.get("title") == "V2"


def test_quiz_pack_delete(sdb):
    owner = _owner(sdb)
    saved = sdb.save_quiz_pack(owner, "Doomed", QUESTIONS)
    pack_id = saved.get("id") or saved.get("pack_id")
    assert sdb.delete_quiz_pack(owner, pack_id) is True
    assert sdb.get_quiz_pack(owner, pack_id) is None


# --- generated game content --------------------------------------------------

def test_game_content_roundtrip_and_type_mapping(sdb):
    """`wmlt` is stored as content_type `mlt`; the mapping must survive both directions or the
    catalog shows a host's saved content under the wrong game."""
    owner = _owner(sdb)
    saved = sdb.save_game_content(owner, "wmlt", "Who's Most Likely", {"scenarios": ["a", "b"]})
    content_id = saved.get("id") or saved.get("content_id")
    assert content_id, saved
    assert saved.get("game_type") == "wmlt", "the caller must see wmlt, not the stored mlt"

    fetched = sdb.get_game_content(owner, content_id)
    assert fetched is not None
    assert fetched.get("game_type") == "wmlt"

    listed = sdb.list_game_content(owner, game_types=["wmlt"])
    assert any((c.get("id") or c.get("content_id")) == content_id for c in listed)


def test_game_content_is_scoped_to_its_owner(sdb):
    owner, stranger = _owner(sdb), _owner(sdb)
    saved = sdb.save_game_content(owner, "quiz", "Mine", {"questions": []})
    content_id = saved.get("id") or saved.get("content_id")
    assert sdb.get_game_content(stranger, content_id) is None
    assert sdb.delete_game_content(stranger, content_id) is False
    assert sdb.get_game_content(owner, content_id) is not None


# --- media assets ------------------------------------------------------------

def test_media_asset_lifecycle(sdb):
    owner = _owner(sdb)
    asset_id = uuid.uuid4().hex
    created = sdb.create_media_asset(
        asset_id, owner, storage_path=f"uploads/{asset_id}.png",
        public_url=f"/media/{asset_id}", mime_type="image/png", status="pending",
    )
    assert created.get("status") == "pending"

    finalized = sdb.finalize_media_asset(owner, asset_id, bytes_size=2048, alt_text="a cat")
    assert finalized is not None
    assert finalized.get("status") == "ready", "an unfinalized asset must not be servable"
    # The stored column is `bytes` — finalize_media_asset maps the bytes_size argument onto it.
    assert finalized.get("bytes") == 2048

    assert sdb.get_media_asset(owner, asset_id) is not None


def test_media_asset_is_scoped_to_its_owner(sdb):
    owner, stranger = _owner(sdb), _owner(sdb)
    asset_id = uuid.uuid4().hex
    sdb.create_media_asset(asset_id, owner, f"uploads/{asset_id}", f"/media/{asset_id}", "image/png")
    assert sdb.get_media_asset(stranger, asset_id) is None, "uploads must not leak across wallets"
    assert sdb.finalize_media_asset(stranger, asset_id) is None


# --- game sessions (Revelry integration) ------------------------------------

def _session(host_app="revelry", container="party-1", game_type="quiz", room="AAA111",
             game_id=None) -> dict:
    return {
        "id": uuid.uuid4().hex,
        "host_app": host_app,
        "external_container_id": container,
        "game_type": game_type,
        # game_id is a SEPARATE column from game_type, and game_content_has_sessions filters on
        # game_id — conflating them silently returns False for every catalog game.
        "game_id": game_id or game_type,
        "room_code": room,
        "status": "active",
    }


def test_game_session_lookups(sdb):
    payload = _session()
    created = sdb.create_game_session(payload)
    assert created.get("id") == payload["id"]

    assert sdb.get_game_session(payload["id"]) is not None
    assert sdb.get_game_session_by_room(payload["room_code"]) is not None
    active = sdb.get_active_game_session("revelry", "party-1")
    assert active is not None and active.get("id") == payload["id"]
    latest = sdb.get_latest_game_session("revelry", "party-1", "quiz")
    assert latest is not None


def test_game_session_update_and_completion(sdb):
    payload = _session(room="BBB222")
    sdb.create_game_session(payload)
    updated = sdb.update_game_session(payload["id"], {"status": "complete"})
    assert updated is not None and updated.get("status") == "complete"
    assert sdb.get_active_game_session("revelry", "party-1") is None, (
        "a completed session must stop counting as active, or the hub offers a dead room"
    )


def test_game_content_has_sessions(sdb):
    payload = _session(container="party-9", room="CCC333")
    sdb.create_game_session(payload)
    assert sdb.game_content_has_sessions("revelry", "party-9", "quiz") is True
    assert sdb.game_content_has_sessions("revelry", "party-9", "wmlt") is False


# --- share snapshots ---------------------------------------------------------

def test_share_snapshot_roundtrip(sdb):
    token = uuid.uuid4().hex
    sdb.save_share_snapshot(token, "quiz", "Ada", 30, 4, int(__import__("time").time()))
    fetched = sdb.get_share_snapshot(token)
    assert fetched is not None
    assert fetched.get("winner") == "Ada"
    assert sdb.get_share_snapshot(uuid.uuid4().hex) is None


# --- remote-config override store -------------------------------------------

def test_setting_roundtrip(sdb):
    assert sdb.get_setting("nonexistent-key") == ""
    sdb.set_setting("config_overrides", '{"ai_models": {"free_model": "x"}}')
    assert "free_model" in sdb.get_setting("config_overrides")
    # An operator changing it again must overwrite, not append a second row.
    sdb.set_setting("config_overrides", '{"ads_enabled": false}')
    assert "ads_enabled" in sdb.get_setting("config_overrides")
    assert "free_model" not in sdb.get_setting("config_overrides")


# --- host-app catalog flags --------------------------------------------------

def test_host_app_catalog_flag_upsert(sdb):
    sdb.upsert_host_app_catalog_flag("gamma", "revelry", "quiz", {"enabled": True})
    flags = sdb.list_host_app_catalog_flags("gamma", "revelry")
    assert any(f.get("game_id") == "quiz" and f.get("enabled") is True for f in flags), flags

    sdb.upsert_host_app_catalog_flag("gamma", "revelry", "quiz", {"enabled": False})
    flags = sdb.list_host_app_catalog_flags("gamma", "revelry")
    quiz = [f for f in flags if f.get("game_id") == "quiz"]
    assert len(quiz) == 1, "upsert must replace, not duplicate"
    assert quiz[0].get("enabled") is False


# --- pending tokens + admin surface -----------------------------------------

def test_pending_token_is_single_use(sdb):
    device = str(uuid.uuid4())
    sdb.store_pending_token(device, "tok-123")
    assert sdb.pop_pending_token(device) == "tok-123"
    assert sdb.pop_pending_token(device) is None, "a pending token must not be replayable"


def test_admin_lookup_and_stats(sdb):
    wallet = _owner(sdb)
    sdb.credit_tokens(wallet, 25, "test_fund")
    found = sdb.admin_lookup_wallet(wallet)
    # Shape is {"wallet": {...}, "transactions": [...]} — the runbook reads both halves.
    assert found is not None, "the support runbook's first step"
    assert found["wallet"]["balance"] == 25
    assert any(txn["amount"] == 25 for txn in found["transactions"]), (
        "the ledger must accompany the wallet, or a support case cannot be reconstructed"
    )
    stats = sdb.get_admin_stats()
    # The RPC returns a FLAT dict (total_sparks, paying_users, purchase_count, merge_count, ...).
    # main.py's /admin/stats is what nests it under "economy"; the db layer does not.
    assert isinstance(stats, dict)
    assert stats.get("total_sparks") == 25, stats
    for key in ("paying_users", "purchase_count", "merge_count"):
        assert key in stats, f"{key} missing from admin stats: {stats}"
