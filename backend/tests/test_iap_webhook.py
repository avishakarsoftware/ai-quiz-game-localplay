"""Tests for native IAP (RevenueCat webhook) fulfillment + the tiered Stripe checkout.

Covers SPEC-IAP §5.1 (webhook), §5.1.1 (event-handling/HTTP policy), §5.2 (platform guard),
§5.6 (tiered /checkout/create), and the §5.7 test matrix. Pure backend — no RevenueCat/Stripe creds.
"""
import json
import uuid

import pytest
from fastapi.testclient import TestClient

import config
import db
from main import app

client = TestClient(app)

SECRET = "rc_test_secret"
AUTH = {"Authorization": f"Bearer {SECRET}"}


@pytest.fixture(autouse=True)
def iap_env(monkeypatch):
    """Configure the RevenueCat secret and a clean sqlite DB for each test."""
    monkeypatch.setattr(config, "REVENUECAT_WEBHOOK_SECRET", SECRET)
    db.init_db()
    conn = db._get_conn()
    conn.execute("DELETE FROM wallets")
    conn.execute("DELETE FROM token_transactions")
    conn.execute("DELETE FROM webhook_events")
    conn.execute("DELETE FROM entitlements")
    conn.commit()
    yield


def _wallet() -> str:
    return uuid.uuid4().hex


def purchase_event(wallet_id, *, product="rc_spark_pack_50", store="APP_STORE",
                   txn=None, event_id=None, event_type="INITIAL_PURCHASE", extra=None):
    txn = txn or f"txn_{uuid.uuid4().hex[:12]}"
    event = {
        "type": event_type,
        "app_user_id": wallet_id,
        "product_id": product,
        "store": store,
        "transaction_id": txn,
    }
    if event_id:
        event["id"] = event_id
    if extra:
        event.update(extra)
    return {"event": event}, txn


# --- Auth / malformed payload --------------------------------------------------

def test_missing_secret_returns_503(monkeypatch):
    monkeypatch.setattr(config, "REVENUECAT_WEBHOOK_SECRET", "")
    body, _ = purchase_event(_wallet())
    res = client.post("/webhook/revenuecat", json=body, headers=AUTH)
    assert res.status_code == 503


def test_bad_bearer_returns_401():
    body, _ = purchase_event(_wallet())
    res = client.post("/webhook/revenuecat", json=body, headers={"Authorization": "Bearer wrong"})
    assert res.status_code == 401


def test_missing_auth_returns_401():
    body, _ = purchase_event(_wallet())
    res = client.post("/webhook/revenuecat", json=body)
    assert res.status_code == 401


def test_missing_event_returns_400():
    res = client.post("/webhook/revenuecat", json={"not_event": 1}, headers=AUTH)
    assert res.status_code == 400


def test_missing_app_user_id_returns_400():
    body, _ = purchase_event(_wallet())
    del body["event"]["app_user_id"]
    res = client.post("/webhook/revenuecat", json=body, headers=AUTH)
    assert res.status_code == 400


def test_missing_event_identifier_returns_400():
    # No event.id and no transaction id → cannot dedupe.
    body = {"event": {"type": "INITIAL_PURCHASE", "app_user_id": _wallet(),
                      "product_id": "rc_spark_pack_50", "store": "APP_STORE"}}
    res = client.post("/webhook/revenuecat", json=body, headers=AUTH)
    assert res.status_code == 400


# --- Grants --------------------------------------------------------------------

def test_initial_purchase_credits_mapped_sparks():
    wallet = _wallet()
    body, _ = purchase_event(wallet, product="rc_spark_pack_200")
    res = client.post("/webhook/revenuecat", json=body, headers=AUTH)
    assert res.status_code == 200
    assert db.get_wallet_balance(wallet) == 200


def test_non_renewing_purchase_also_credits():
    wallet = _wallet()
    body, _ = purchase_event(wallet, product="rc_spark_pack_50", event_type="NON_RENEWING_PURCHASE")
    res = client.post("/webhook/revenuecat", json=body, headers=AUTH)
    assert res.status_code == 200
    assert db.get_wallet_balance(wallet) == 50


def test_store_product_id_also_maps():
    wallet = _wallet()
    body, _ = purchase_event(wallet, product="me.revelryapp.quiz.sparks_500")
    res = client.post("/webhook/revenuecat", json=body, headers=AUTH)
    assert res.status_code == 200
    assert db.get_wallet_balance(wallet) == 500


def test_amount_is_from_catalog_not_body():
    wallet = _wallet()
    body, _ = purchase_event(wallet, product="rc_spark_pack_50",
                             extra={"price": 999999, "price_in_purchased_currency": 999999})
    res = client.post("/webhook/revenuecat", json=body, headers=AUTH)
    assert res.status_code == 200
    assert db.get_wallet_balance(wallet) == 50  # catalog amount, not the tampered price


def test_unknown_product_acks_without_credit():
    wallet = _wallet()
    body, _ = purchase_event(wallet, product="rc_bogus_product")
    res = client.post("/webhook/revenuecat", json=body, headers=AUTH)
    assert res.status_code == 200
    assert res.json()["detail"] == "unknown product"
    assert db.get_wallet_balance(wallet) == 0


def test_missing_transaction_id_for_known_product_returns_400():
    wallet = _wallet()
    body = {"event": {"id": "evt_x", "type": "INITIAL_PURCHASE", "app_user_id": wallet,
                      "product_id": "rc_spark_pack_50", "store": "APP_STORE"}}
    res = client.post("/webhook/revenuecat", json=body, headers=AUTH)
    assert res.status_code == 400


def test_unsupported_event_type_ignored():
    wallet = _wallet()
    body, _ = purchase_event(wallet, event_type="TEST")
    res = client.post("/webhook/revenuecat", json=body, headers=AUTH)
    assert res.status_code == 200
    assert db.get_wallet_balance(wallet) == 0


# --- Idempotency ---------------------------------------------------------------

def test_replay_same_event_id_does_not_double_credit():
    wallet = _wallet()
    body, _ = purchase_event(wallet, product="rc_spark_pack_50", event_id="evt_dup_1")
    assert client.post("/webhook/revenuecat", json=body, headers=AUTH).status_code == 200
    res2 = client.post("/webhook/revenuecat", json=body, headers=AUTH)
    assert res2.status_code == 200
    assert res2.json()["detail"] == "already processed"
    assert db.get_wallet_balance(wallet) == 50


def test_different_event_id_same_txn_does_not_double_credit():
    wallet = _wallet()
    txn = "txn_shared_1"
    body1, _ = purchase_event(wallet, product="rc_spark_pack_50", txn=txn, event_id="evt_a")
    body2, _ = purchase_event(wallet, product="rc_spark_pack_50", txn=txn, event_id="evt_b")
    assert client.post("/webhook/revenuecat", json=body1, headers=AUTH).status_code == 200
    assert client.post("/webhook/revenuecat", json=body2, headers=AUTH).status_code == 200
    # Second event is a new webhook event id, but credit_purchase dedups on iap:store:txn.
    assert db.get_wallet_balance(wallet) == 50


def test_records_audit_entitlement_with_apple_txn():
    wallet = _wallet()
    body, txn = purchase_event(wallet, product="rc_spark_pack_50", store="APP_STORE")
    client.post("/webhook/revenuecat", json=body, headers=AUTH)
    row = db._get_conn().execute(
        "SELECT status, games_remaining FROM entitlements WHERE apple_transaction_id = ?", (txn,)
    ).fetchone()
    assert row is not None
    assert row["status"] == "iap_consumed"
    assert row["games_remaining"] == 0


# --- Refund / clawback ---------------------------------------------------------

def test_refund_debits_once_and_is_idempotent():
    wallet = _wallet()
    txn = "txn_refund_1"
    buy, _ = purchase_event(wallet, product="rc_spark_pack_50", txn=txn, event_id="evt_buy")
    assert client.post("/webhook/revenuecat", json=buy, headers=AUTH).status_code == 200
    assert db.get_wallet_balance(wallet) == 50

    refund1, _ = purchase_event(wallet, product="rc_spark_pack_50", txn=txn,
                                event_id="evt_refund_1", event_type="REFUND")
    assert client.post("/webhook/revenuecat", json=refund1, headers=AUTH).status_code == 200
    assert db.get_wallet_balance(wallet) == 0

    # A second refund event (new id, same txn) must not double-debit into the negative.
    refund2, _ = purchase_event(wallet, product="rc_spark_pack_50", txn=txn,
                                event_id="evt_refund_2", event_type="REFUND")
    assert client.post("/webhook/revenuecat", json=refund2, headers=AUTH).status_code == 200
    assert db.get_wallet_balance(wallet) == 0


# --- Tiered Stripe checkout + platform guard (§5.2, §5.6) ----------------------

CHECKOUT_DEVICE = "11111111-2222-3333-4444-555555555555"


@pytest.fixture
def stripe_configured(monkeypatch):
    monkeypatch.setattr(config, "STRIPE_SECRET_KEY", "sk_test_x")
    import stripe

    captured = {}

    class _FakeSession:
        url = "https://checkout.stripe.com/test"
        id = "cs_test_123"

    def _fake_create(**kwargs):
        captured.update(kwargs)
        return _FakeSession()

    monkeypatch.setattr(stripe.checkout.Session, "create", staticmethod(_fake_create))
    return captured


def test_checkout_blocks_ios():
    res = client.post("/checkout/create", json={"device_id": CHECKOUT_DEVICE},
                      headers={"X-Device-ID": CHECKOUT_DEVICE, "X-Platform": "ios"})
    assert res.status_code == 403


def test_checkout_blocks_android():
    res = client.post("/checkout/create", json={"device_id": CHECKOUT_DEVICE},
                      headers={"X-Device-ID": CHECKOUT_DEVICE, "X-Platform": "android"})
    assert res.status_code == 403


def test_checkout_web_allowed_and_uses_tier_price(stripe_configured):
    res = client.post("/checkout/create",
                      json={"device_id": CHECKOUT_DEVICE, "sku": "spark_pack_200"},
                      headers={"X-Device-ID": CHECKOUT_DEVICE, "X-Platform": "web"})
    assert res.status_code == 200
    # Built the line item inline via price_data from the catalog (no pre-created Price object),
    # and wrote sku + catalog amount into metadata.
    price_data = stripe_configured["line_items"][0]["price_data"]
    assert price_data["unit_amount"] == 499
    assert price_data["currency"] == "usd"
    assert price_data["product_data"]["name"] == "200 Sparks"
    meta = stripe_configured["metadata"]
    assert meta["sku"] == "spark_pack_200"
    assert meta["token_amount"] == "200"


def test_checkout_unknown_sku_falls_back_to_default(stripe_configured):
    res = client.post("/checkout/create",
                      json={"device_id": CHECKOUT_DEVICE, "sku": "spark_pack_9999"},
                      headers={"X-Device-ID": CHECKOUT_DEVICE, "X-Platform": "web"})
    assert res.status_code == 200
    assert stripe_configured["metadata"]["sku"] == config.DEFAULT_SPARK_SKU


# --- Stripe webhook cap (§5.6) -------------------------------------------------

def test_stripe_webhook_caps_tampered_amount(monkeypatch):
    monkeypatch.setattr(config, "STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setattr(config, "STRIPE_WEBHOOK_SECRET", "whsec_test")
    wallet = _wallet()
    import stripe

    fake_event = {
        "id": "evt_stripe_cap",
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": "cs_cap_1",
            "metadata": {
                "device_id": CHECKOUT_DEVICE,
                "wallet_id": wallet,
                "token_amount": "999999",  # tampered
                "sku": "spark_pack_500",
                "promo_id": "",
            },
        }},
    }
    monkeypatch.setattr(stripe.Webhook, "construct_event", staticmethod(lambda *a, **k: fake_event))

    res = client.post("/webhook/stripe", content=b"{}",
                      headers={"stripe-signature": "t=1,v1=x"})
    assert res.status_code == 200
    # Capped to the largest catalog pack (500), not the tampered 999999.
    assert db.get_wallet_balance(wallet) == config.MAX_SPARK_PACK


# --- Cap-overflow purchase gate (REVIEW-2026-08 M1) ----------------------------
#
# credit_purchase clamps at MAX_TOKEN_BALANCE, so before this gate a near-full wallet PAID full
# price and received a partial/zero credit. The 409 must fire BEFORE any Stripe session exists.

def _fund_checkout_wallet(balance: int) -> str:
    """Put the wallet the checkout endpoint will resolve (conftest pins get_wallet_id to
    TEST_DEVICE_ID) at exactly `balance` sparks."""
    from conftest import TEST_DEVICE_ID
    db.get_or_create_wallet(TEST_DEVICE_ID, signup_bonus=False)
    current = db.get_wallet_balance(TEST_DEVICE_ID)
    if current:
        db.debit_tokens(TEST_DEVICE_ID, current, "test_reset")
    if balance:
        db.credit_tokens(TEST_DEVICE_ID, balance, "test_fund")
    assert db.get_wallet_balance(TEST_DEVICE_ID) == balance
    return TEST_DEVICE_ID


def test_checkout_rejects_pack_that_would_overflow_the_cap(stripe_configured):
    _fund_checkout_wallet(config.MAX_TOKEN_BALANCE - 10)  # room for 10, smallest pack is 50
    res = client.post("/checkout/create",
                      json={"device_id": CHECKOUT_DEVICE, "sku": "spark_pack_50"},
                      headers={"X-Device-ID": CHECKOUT_DEVICE, "X-Platform": "web"})
    assert res.status_code == 409
    assert "nearly full" in res.json()["detail"]
    # The refusal happened before Stripe was ever called — nothing to refund, nothing to dispute.
    assert stripe_configured == {}


def test_checkout_allows_pack_landing_exactly_at_the_cap(stripe_configured):
    _fund_checkout_wallet(config.MAX_TOKEN_BALANCE - 50)
    res = client.post("/checkout/create",
                      json={"device_id": CHECKOUT_DEVICE, "sku": "spark_pack_50"},
                      headers={"X-Device-ID": CHECKOUT_DEVICE, "X-Platform": "web"})
    assert res.status_code == 200, res.text
    assert stripe_configured["metadata"]["sku"] == "spark_pack_50"


def test_balance_endpoint_reports_the_cap():
    """The purchase modal greys out packs that won't fit; it needs the cap from the server,
    not a hardcoded copy that drifts."""
    from conftest import TEST_DEVICE_ID
    res = client.get("/tokens/balance", headers={"X-Device-ID": TEST_DEVICE_ID})
    assert res.status_code == 200
    assert res.json()["max_balance"] == config.MAX_TOKEN_BALANCE
