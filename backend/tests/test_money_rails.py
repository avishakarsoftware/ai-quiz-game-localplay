"""L2 tests for the money rails: refund/clawback, restore, and checkout guards.

Everything here is real currency. A regression in any of these either takes sparks a user paid
for, or hands out sparks nobody paid for. The Stripe `charge.refunded` path had NO test coverage
before this file, and `/purchases/restore` had no happy-path coverage at all — which is where the
spark-minting bug below was hiding.
"""
import os
import sys
import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import config
import db
import tokens as tokens_mod


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Isolated sqlite file per test — these tests move balances around and must not see
    each other's ledgers (a leaked transaction row silently changes idempotency answers)."""
    monkeypatch.setattr(db, "_local", threading.local())
    monkeypatch.setattr(db, "DB_DIR", str(tmp_path))
    monkeypatch.setattr(db, "DB_PATH", os.path.join(str(tmp_path), "revelry.db"))
    db.init_db()
    # conftest neutralises spending so game tests don't 402; here the real ledger IS the subject.
    monkeypatch.setattr(tokens_mod, "ensure_wallet", tokens_mod.ensure_wallet)
    yield


@pytest.fixture
def client():
    from main import app
    return TestClient(app)


@pytest.fixture
def real_spend():
    """conftest pins spend_generate/spend_room to "always succeeds, balance 999" for the whole
    suite. Restore the real debit path for the tests that are about refusal."""
    import importlib
    importlib.reload(tokens_mod)
    yield tokens_mod


@pytest.fixture
def stripe_env(monkeypatch):
    monkeypatch.setattr(config, "STRIPE_SECRET_KEY", "sk_test_money_rails")
    monkeypatch.setattr(config, "STRIPE_WEBHOOK_SECRET", "whsec_test_money_rails")
    return monkeypatch


DEVICE = "aaaaaaaa-1111-2222-3333-444444444444"


def _fake_event(monkeypatch, event: dict):
    """Bypass Stripe signature verification and hand the endpoint a known event."""
    import stripe
    monkeypatch.setattr(stripe.Webhook, "construct_event", staticmethod(lambda *a, **k: event))


def _fake_session_lookup(monkeypatch, session_id: str, metadata: dict):
    """Fake stripe.checkout.Session.list(payment_intent=...) used by the refund path."""
    import stripe

    class _Session:
        id = session_id

    _Session.metadata = metadata

    class _Page:
        data = [_Session()]

    monkeypatch.setattr(stripe.checkout.Session, "list", staticmethod(lambda **kwargs: _Page()))


def _purchase(client, monkeypatch, wallet: str, session_id: str, sparks: int, event_id: str):
    _fake_event(monkeypatch, {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": session_id,
            "metadata": {"device_id": DEVICE, "wallet_id": wallet,
                         "token_amount": str(sparks), "sku": "spark_pack_200", "promo_id": ""},
        }},
    })
    res = client.post("/webhook/stripe", content=b"{}", headers={"stripe-signature": "t=1,v1=x"})
    assert res.status_code == 200
    return res


def _refund(client, monkeypatch, *, session_id, metadata, charge_amount, refunded,
            event_id, event_type="charge.refunded"):
    _fake_session_lookup(monkeypatch, session_id, metadata)
    _fake_event(monkeypatch, {
        "id": event_id,
        "type": event_type,
        "data": {"object": {
            "payment_intent": "pi_test_1",
            "amount": charge_amount,
            "amount_refunded": refunded,
        }},
    })
    return client.post("/webhook/stripe", content=b"{}", headers={"stripe-signature": "t=1,v1=x"})


# ---------------------------------------------------------------------------
# BUG: /purchases/restore mints sparks on every call
# ---------------------------------------------------------------------------

class TestRestoreIsIdempotent:
    """`/purchases/restore` is behind a user-tappable "Restore purchases" button in the settings
    drawer. It credits `games_remaining * COST_ROOM` sparks via db.credit_tokens, which — unlike
    credit_purchase — has NO reference_id de-duplication. Without a guard, a user holding one
    legacy active IAP entitlement can tap the button repeatedly and mint sparks up to
    MAX_TOKEN_BALANCE: free games, forever, for a purchase made once."""

    def _legacy_iap_entitlement(self, device_id: str, games: int = 5,
                                created_at: int | None = None) -> str:
        eid = str(uuid.uuid4())
        now = int(time.time())
        conn = db._get_conn()
        conn.execute(
            "INSERT INTO entitlements (id, device_id, user_id, status, games_remaining, "
            "expires_at, created_at, apple_transaction_id) "
            "VALUES (?, ?, NULL, 'active', ?, ?, ?, ?)",
            (eid, device_id, games, now + 86400, created_at or now, f"apple_txn_{eid[:12]}"),
        )
        conn.commit()
        return eid

    def test_first_restore_credits_the_remaining_games(self, client):
        """The legitimate case must keep working: a real unrestored purchase pays out once."""
        db.get_or_create_wallet(DEVICE, signup_bonus=False)
        self._legacy_iap_entitlement(DEVICE, games=5)

        res = client.post("/purchases/restore", headers={"X-Device-Id": DEVICE})

        assert res.status_code == 200
        assert res.json()["restored"] is True
        assert res.json()["tokens_added"] == 5 * config.COST_ROOM
        assert db.get_wallet_balance(DEVICE) == 5 * config.COST_ROOM

    def test_repeat_restore_does_not_mint_more_sparks(self, client):
        """Cost of breaking: unlimited free sparks from one purchase — direct revenue loss and a
        broken ledger (many 'restore' credits for a single entitlement)."""
        db.get_or_create_wallet(DEVICE, signup_bonus=False)
        self._legacy_iap_entitlement(DEVICE, games=5)

        for _ in range(4):
            res = client.post("/purchases/restore", headers={"X-Device-Id": DEVICE})
            assert res.status_code == 200

        assert db.get_wallet_balance(DEVICE) == 5 * config.COST_ROOM

    def test_repeat_restore_reports_nothing_added(self, client):
        """The second answer must not claim it added sparks — the frontend fires a
        `purchases_restored` analytics event with tokens_added, and shows the user a success
        state. Reporting a phantom credit trains users to keep tapping."""
        db.get_or_create_wallet(DEVICE, signup_bonus=False)
        self._legacy_iap_entitlement(DEVICE, games=5)

        client.post("/purchases/restore", headers={"X-Device-Id": DEVICE})
        second = client.post("/purchases/restore", headers={"X-Device-Id": DEVICE}).json()

        assert second["tokens_added"] == 0
        assert second["new_balance"] == 5 * config.COST_ROOM

    def test_restore_ledger_has_exactly_one_credit(self, client):
        """Support and finance read the ledger. One purchase must leave one 'restore' row."""
        db.get_or_create_wallet(DEVICE, signup_bonus=False)
        eid = self._legacy_iap_entitlement(DEVICE, games=3)

        client.post("/purchases/restore", headers={"X-Device-Id": DEVICE})
        client.post("/purchases/restore", headers={"X-Device-Id": DEVICE})

        rows = db._get_conn().execute(
            "SELECT amount FROM token_transactions WHERE reference_id = ? AND reason = 'restore'",
            (eid,),
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["amount"] == 3 * config.COST_ROOM

    def test_two_distinct_entitlements_each_restore_once(self, client):
        """The guard must key on the entitlement, not on the wallet — a user with two genuine
        past purchases is still owed both."""
        db.get_or_create_wallet(DEVICE, signup_bonus=False)
        first = self._legacy_iap_entitlement(DEVICE, games=2)
        client.post("/purchases/restore", headers={"X-Device-Id": DEVICE})
        assert db.get_wallet_balance(DEVICE) == 2 * config.COST_ROOM

        # find_restorable_entitlement returns the newest first, so a second purchase is next.
        second = self._legacy_iap_entitlement(DEVICE, games=4, created_at=int(time.time()) + 5)
        assert second != first
        client.post("/purchases/restore", headers={"X-Device-Id": DEVICE})

        assert db.get_wallet_balance(DEVICE) == (2 + 4) * config.COST_ROOM


# ---------------------------------------------------------------------------
# Stripe refund / chargeback clawback
# ---------------------------------------------------------------------------

class TestStripeRefundClawback:
    """A refunded or disputed charge must claw back exactly what was granted — no more (we'd be
    stealing sparks the user still paid for) and no less (we'd be giving away the product)."""

    def test_full_refund_debits_exactly_what_was_credited(self, client, stripe_env, monkeypatch):
        wallet = str(uuid.uuid4())
        _purchase(client, monkeypatch, wallet, "cs_full_1", 200, "evt_buy_1")
        assert db.get_wallet_balance(wallet) == 200

        res = _refund(client, monkeypatch, session_id="cs_full_1",
                      metadata={"wallet_id": wallet, "token_amount": "200"},
                      charge_amount=499, refunded=499, event_id="evt_refund_1")

        assert res.status_code == 200
        assert db.get_wallet_balance(wallet) == 0

    def test_partial_refund_prorates_and_rounds_up(self, client, stripe_env, monkeypatch):
        """Half the money back means about half the sparks back. Rounding is deliberately in the
        user's favour (ceil), so a 50% refund of 200 sparks claws 101, never 100.5 silently
        truncated to 100."""
        wallet = str(uuid.uuid4())
        _purchase(client, monkeypatch, wallet, "cs_part_1", 200, "evt_buy_2")

        res = _refund(client, monkeypatch, session_id="cs_part_1",
                      metadata={"wallet_id": wallet, "token_amount": "200"},
                      charge_amount=499, refunded=250, event_id="evt_refund_2")

        assert res.status_code == 200
        # ceil(200 * 250 / 499) == 101
        assert db.get_wallet_balance(wallet) == 200 - 101

    def test_second_refund_only_debits_the_remainder(self, client, stripe_env, monkeypatch):
        """Stripe sends cumulative amount_refunded. Debiting the cumulative figure again on the
        second event would double-charge the user for one refund."""
        wallet = str(uuid.uuid4())
        _purchase(client, monkeypatch, wallet, "cs_part_2", 200, "evt_buy_3")
        _refund(client, monkeypatch, session_id="cs_part_2",
                metadata={"wallet_id": wallet, "token_amount": "200"},
                charge_amount=499, refunded=250, event_id="evt_refund_3a")
        assert db.get_wallet_balance(wallet) == 99

        # Now the rest of the money is refunded (cumulative 499 of 499) → owes 200 total.
        _refund(client, monkeypatch, session_id="cs_part_2",
                metadata={"wallet_id": wallet, "token_amount": "200"},
                charge_amount=499, refunded=499, event_id="evt_refund_3b")

        assert db.get_wallet_balance(wallet) == 0

    def test_replayed_refund_event_id_is_a_no_op(self, client, stripe_env, monkeypatch):
        """Stripe retries webhooks. The event-id dedupe must stop a replay before it debits."""
        wallet = str(uuid.uuid4())
        _purchase(client, monkeypatch, wallet, "cs_replay_1", 200, "evt_buy_4")
        db.credit_tokens(wallet, 100, "admin_grant")  # user also earned/bought sparks elsewhere
        _refund(client, monkeypatch, session_id="cs_replay_1",
                metadata={"wallet_id": wallet, "token_amount": "200"},
                charge_amount=499, refunded=499, event_id="evt_refund_4")
        after_first = db.get_wallet_balance(wallet)
        assert after_first == 100

        res = _refund(client, monkeypatch, session_id="cs_replay_1",
                      metadata={"wallet_id": wallet, "token_amount": "200"},
                      charge_amount=499, refunded=499, event_id="evt_refund_4")

        assert res.status_code == 200
        assert db.get_wallet_balance(wallet) == after_first

    def test_dispute_claws_back_like_a_refund(self, client, stripe_env, monkeypatch):
        """A chargeback is money gone with fees on top — it must not be a softer outcome than a
        refund."""
        wallet = str(uuid.uuid4())
        _purchase(client, monkeypatch, wallet, "cs_dispute_1", 500, "evt_buy_5")

        res = _refund(client, monkeypatch, session_id="cs_dispute_1",
                      metadata={"wallet_id": wallet, "token_amount": "500"},
                      charge_amount=999, refunded=999, event_id="evt_dispute_1",
                      event_type="charge.dispute.created")

        assert res.status_code == 200
        assert db.get_wallet_balance(wallet) == 0

    def test_refund_metadata_amount_is_capped(self, client, stripe_env, monkeypatch):
        """Metadata is attacker-influenced (it round-trips through Stripe). An inflated
        token_amount on the refund side would debit more than was ever granted — draining sparks
        the user legitimately holds."""
        wallet = str(uuid.uuid4())
        _purchase(client, monkeypatch, wallet, "cs_tamper_1", 200, "evt_buy_6")
        db.credit_tokens(wallet, 700, "admin_grant")
        assert db.get_wallet_balance(wallet) == 900

        _refund(client, monkeypatch, session_id="cs_tamper_1",
                metadata={"wallet_id": wallet, "token_amount": "999999"},
                charge_amount=499, refunded=499, event_id="evt_refund_6")

        # Capped at the largest real pack, not the tampered figure.
        assert db.get_wallet_balance(wallet) == 900 - config.MAX_SPARK_PACK

    def test_refund_of_spent_sparks_does_not_go_negative(self, client, stripe_env, monkeypatch):
        """The user bought 200, spent them, then refunded. We cannot take back what is gone;
        a negative balance would wedge the wallet (every future check reads "insufficient")."""
        wallet = str(uuid.uuid4())
        _purchase(client, monkeypatch, wallet, "cs_spent_1", 200, "evt_buy_7")
        db.debit_tokens(wallet, 200, "spend_room")
        assert db.get_wallet_balance(wallet) == 0

        res = _refund(client, monkeypatch, session_id="cs_spent_1",
                      metadata={"wallet_id": wallet, "token_amount": "200"},
                      charge_amount=499, refunded=499, event_id="evt_refund_7")

        assert res.status_code == 200
        assert db.get_wallet_balance(wallet) == 0

    def test_failed_refund_lookup_is_not_marked_processed(self, client, stripe_env, monkeypatch):
        """If our own processing blows up we must NOT record the event as done — Stripe's retry
        is the only thing standing between a failed clawback and permanently free sparks."""
        from main import app
        wallet = str(uuid.uuid4())
        _purchase(client, monkeypatch, wallet, "cs_boom_1", 200, "evt_buy_8")

        import stripe

        def boom(**kwargs):
            raise RuntimeError("stripe api down")

        monkeypatch.setattr(stripe.checkout.Session, "list", staticmethod(boom))
        _fake_event(monkeypatch, {
            "id": "evt_refund_boom",
            "type": "charge.refunded",
            "data": {"object": {"payment_intent": "pi_x", "amount": 499, "amount_refunded": 499}},
        })

        res = TestClient(app, raise_server_exceptions=False).post(
            "/webhook/stripe", content=b"{}", headers={"stripe-signature": "t=1,v1=x"})

        assert res.status_code == 500
        assert db.is_webhook_event_processed("evt_refund_boom") is False
        assert db.get_wallet_balance(wallet) == 200


class TestStripePurchaseCredit:
    def test_purchase_is_idempotent_across_different_event_ids(self, client, stripe_env, monkeypatch):
        """Stripe can deliver the same completed session under a new event id. credit_purchase's
        reference_id gate is the second line of defence — losing it double-credits every retry."""
        wallet = str(uuid.uuid4())
        _purchase(client, monkeypatch, wallet, "cs_dupe_1", 200, "evt_a")
        _purchase(client, monkeypatch, wallet, "cs_dupe_1", 200, "evt_b")

        assert db.get_wallet_balance(wallet) == 200

    def test_purchase_notification_is_one_time(self, client, stripe_env, monkeypatch):
        """/checkout/token is how the web client learns the purchase landed. It must pop exactly
        once, or a refresh loop shows "you got 200 sparks!" forever."""
        wallet = str(uuid.uuid4())
        _purchase(client, monkeypatch, wallet, "cs_notify_1", 200, "evt_notify")

        first = client.get("/checkout/token", headers={"X-Device-Id": DEVICE})
        second = client.get("/checkout/token", headers={"X-Device-Id": DEVICE})

        assert first.status_code == 200
        assert first.json()["tokens_added"] == 200
        assert second.status_code == 404

    def test_missing_wallet_id_credits_nobody(self, client, stripe_env, monkeypatch):
        """No wallet in metadata → ack and drop. Guessing a wallet would credit a stranger."""
        _fake_event(monkeypatch, {
            "id": "evt_no_wallet",
            "type": "checkout.session.completed",
            "data": {"object": {"id": "cs_no_wallet", "metadata": {}}},
        })
        res = client.post("/webhook/stripe", content=b"{}", headers={"stripe-signature": "t=1,v1=x"})

        assert res.status_code == 200
        assert res.json()["detail"] == "No wallet_id in metadata"
        rows = db._get_conn().execute("SELECT COUNT(*) c FROM token_transactions").fetchone()
        assert rows["c"] == 0

    def test_device_id_only_metadata_still_credits(self, client, stripe_env, monkeypatch):
        """Backward compat: sessions created before wallet_id existed carry only device_id. A
        paying user from an old client must still get their sparks."""
        _fake_event(monkeypatch, {
            "id": "evt_legacy_meta",
            "type": "checkout.session.completed",
            "data": {"object": {"id": "cs_legacy_1",
                                "metadata": {"device_id": DEVICE, "token_amount": "50"}}},
        })
        client.post("/webhook/stripe", content=b"{}", headers={"stripe-signature": "t=1,v1=x"})

        assert db.get_wallet_balance(DEVICE) == 50


class TestSpendingRefusal:
    """The last gate before a paid action runs. `can_*` is advisory; `spend_*` is the one that
    must hold, because it is the only atomic check-and-debit."""

    def test_spend_room_refuses_and_debits_nothing(self, real_spend):
        wallet = str(uuid.uuid4())
        db.get_or_create_wallet(wallet, signup_bonus=False)
        db.credit_tokens(wallet, config.COST_ROOM - 1, "admin_grant")

        ok, balance = tokens_mod.spend_room(wallet)

        assert ok is False
        # Cost of breaking: a partial debit on a refused action takes sparks and gives no game.
        assert balance == config.COST_ROOM - 1
        assert db.get_wallet_balance(wallet) == config.COST_ROOM - 1

    def test_spend_generate_refuses_on_an_empty_wallet(self, real_spend):
        wallet = str(uuid.uuid4())
        db.get_or_create_wallet(wallet, signup_bonus=False)

        ok, balance = tokens_mod.spend_generate(wallet)

        assert ok is False
        assert balance == 0

    def test_spend_on_an_unknown_wallet_refuses_instead_of_creating_one(self, real_spend):
        """A typo'd/absent wallet must not be auto-funded into existence by a spend attempt."""
        ok, balance = tokens_mod.spend_room(str(uuid.uuid4()))
        assert ok is False and balance == 0
        assert db._get_conn().execute("SELECT COUNT(*) c FROM wallets").fetchone()["c"] == 0

    def test_exact_balance_is_spendable(self, real_spend):
        """Off-by-one the other way is just as bad: a user with exactly the price must be able
        to buy."""
        wallet = str(uuid.uuid4())
        db.get_or_create_wallet(wallet, signup_bonus=False)
        db.credit_tokens(wallet, config.COST_ROOM, "admin_grant")

        ok, balance = tokens_mod.spend_room(wallet)

        assert ok is True and balance == 0


class TestAdminMoneyStats:
    """`/admin/stats` is the operator's read on the economy. Wrong numbers here mean pricing and
    promo decisions get made on fiction."""

    def test_stats_reflect_the_ledger(self):
        buyer = str(uuid.uuid4())
        freeloader = str(uuid.uuid4())
        db.get_or_create_wallet(buyer, signup_bonus=False)
        db.get_or_create_wallet(freeloader, signup_bonus=False)
        db.credit_purchase(buyer, 200, "cs_stats_1")
        db.credit_tokens(freeloader, 30, "admin_grant")

        stats = db.get_admin_stats()

        assert stats["wallet_count"] == 2
        assert stats["total_sparks"] == 230
        assert stats["paying_users"] == 1  # lifetime_purchased > 0
        assert stats["purchase_count"] == 1
        assert stats["merge_count"] == 0

    def test_a_refund_does_not_uncount_the_purchase(self):
        """Refunds claw back sparks but the purchase still happened — conflating the two would
        make purchase_count drift from Stripe's own totals."""
        buyer = str(uuid.uuid4())
        db.get_or_create_wallet(buyer, signup_bonus=False)
        db.credit_purchase(buyer, 200, "cs_stats_2")
        db.debit_tokens(buyer, 200, "refund", "cs_stats_2")

        stats = db.get_admin_stats()

        assert stats["purchase_count"] == 1
        assert stats["total_sparks"] == 0


class TestCheckoutGuards:
    def test_unsigned_webhook_is_rejected(self, client, stripe_env):
        """The signature is the only proof an event came from Stripe. Accepting an unsigned body
        would let anyone POST themselves unlimited sparks."""
        res = client.post("/webhook/stripe", json={"type": "checkout.session.completed"},
                          headers={"stripe-signature": "t=1,v1=forged"})
        assert res.status_code == 400

    def test_webhook_disabled_without_keys(self, client, monkeypatch):
        monkeypatch.setattr(config, "STRIPE_SECRET_KEY", "")
        monkeypatch.setattr(config, "STRIPE_WEBHOOK_SECRET", "")
        res = client.post("/webhook/stripe", content=b"{}", headers={"stripe-signature": "x"})
        assert res.status_code == 503

    def test_device_id_mismatch_rejected(self, client, stripe_env):
        """Body and header must agree, else a caller could open a checkout that credits someone
        else's wallet (or attribute their own purchase to a victim)."""
        res = client.post(
            "/checkout/create",
            json={"device_id": DEVICE},
            headers={"X-Device-Id": "bbbbbbbb-1111-2222-3333-444444444444", "X-Platform": "web"},
        )
        assert res.status_code == 400
        assert res.json()["detail"] == "Device ID mismatch"

    def test_non_uuid_device_id_rejected(self, client, stripe_env):
        """A free-text device id would let one caller mint wallets/ledger rows under arbitrary keys."""
        res = client.post("/checkout/create", json={"device_id": "not-a-uuid"},
                          headers={"X-Platform": "web"})
        assert res.status_code == 422

    def test_checkout_unavailable_without_stripe_key(self, client, monkeypatch):
        monkeypatch.setattr(config, "STRIPE_SECRET_KEY", "")
        res = client.post("/checkout/create", json={"device_id": DEVICE},
                          headers={"X-Platform": "web"})
        assert res.status_code == 503

    def test_active_promo_overrides_the_tier_amount(self, client, stripe_env, monkeypatch):
        """Promos are configured out-of-band and logged per transaction. If the promo amount does
        not reach Stripe metadata, the webhook credits the base tier and the promo silently
        under-delivers what the storefront advertised."""
        monkeypatch.setattr(config, "PROMO_ID", "launch_2026")
        monkeypatch.setattr(config, "PROMO_TOKEN_AMOUNT", 300)
        captured = {}

        import stripe

        class _S:
            url = "https://checkout.stripe.com/x"
            id = "cs_promo_1"

        monkeypatch.setattr(stripe.checkout.Session, "create",
                            staticmethod(lambda **kw: (captured.update(kw), _S())[1]))

        res = client.post("/checkout/create",
                          json={"device_id": DEVICE, "promo_id": "launch_2026"},
                          headers={"X-Platform": "web"})

        assert res.status_code == 200
        assert captured["metadata"]["token_amount"] == "300"
        assert captured["metadata"]["promo_id"] == "launch_2026"

    def test_wrong_promo_id_falls_back_to_tier_amount(self, client, stripe_env, monkeypatch):
        """A guessed/stale promo code must not grant promo sparks."""
        monkeypatch.setattr(config, "PROMO_ID", "launch_2026")
        monkeypatch.setattr(config, "PROMO_TOKEN_AMOUNT", 300)
        captured = {}

        import stripe

        class _S:
            url = "https://checkout.stripe.com/x"
            id = "cs_promo_2"

        monkeypatch.setattr(stripe.checkout.Session, "create",
                            staticmethod(lambda **kw: (captured.update(kw), _S())[1]))

        res = client.post("/checkout/create",
                          json={"device_id": DEVICE, "promo_id": "not_the_promo"},
                          headers={"X-Platform": "web"})

        assert res.status_code == 200
        assert captured["metadata"]["token_amount"] == "50"  # default tier
        assert captured["metadata"]["promo_id"] == ""
