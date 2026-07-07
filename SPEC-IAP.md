# SPEC-IAP — Native In-App Purchases (Apple StoreKit + Google Play Billing)

Status: **Implemented — backend + frontend on master & verified on gamma; store/console setup in progress** (2026-06-29)
Owner: Avi
Related: `SPEC.md` (spark economy), `DEPLOY.md` (§3c IAP runbook, §3d native sign-in, build contexts), `token_economy_migration.md`, VibePix `SPEC.md`/`server.js` (reference implementation)

---

## 0. Status (as-built, updated 2026-07-06)

**Done & on master:**
- **Backend** — `POST /webhook/revenuecat` (bearer auth, double idempotency via `webhook_events` + `credit_purchase(reference_id="iap:{store}:{txn}")`, refund clawback, unknown-product ack), tiered `/checkout/create` (inline Stripe `price_data` from `config.SPARK_PRODUCTS`, no Stripe Price objects), Android+iOS Stripe block. Unit tests in `backend/tests/test_iap_webhook.py`.
- **Frontend** — `SparkPurchaseModal` (3 tiers, web Stripe / native RevenueCat), `utils/iap.ts` wrapper, `utils/sparkPacks.ts`, `platform.ts`; `@revenuecat/purchases-capacitor@^12.3.2` installed (iOS SPM + Android Gradle registered). Native build scripts `npm run cap:sync:gamma|cap:sync:prod` (bake API host + publishable RevenueCat/OAuth ids).
- **Deployed to gamma & verified** — `/webhook/revenuecat` smoke-tested end-to-end: auth 401s, credit (+200), event-id replay dedup, same-txn dedup, unknown-product ack, refund clawback + no over-debit. `REVENUECAT_WEBHOOK_SECRET` set on gamma; gamma `ALLOWED_ORIGINS` includes `capacitor://localhost,http://localhost,https://localhost`.
- **RevenueCat** — project `Revelry Games` (`proj0cdf24b0`); iOS + Android apps (`me.revelryapp.quiz`); webhook → gamma (bearer). The **current** `default` offering has 3 packages (`rc_spark_pack_50/200/500`), each serving **both** the App Store product and the Play Store product (`me.revelryapp.quiz.sparks_*`). Play credential validated (service account granted the required Play permissions). NOTE: App Store products still show "Could not check" until the iOS IAPs are submitted/approved.
- **Apple** — 3 consumables `me.revelryapp.quiz.sparks_50/200/500` created (Ready to Submit) + sandbox tester.
- **Android Play (2026-07-06)** — lost original upload-key password → generated `revelry-quiz-upload-v2.keystore` (documented in `backupenv/quiz/local/`), Play **upload-key reset** approved. AAB **v5 (3.1.0)** with the BILLING permission published to **internal testing**. 3 one-time products created + **Active** ($1.99/$4.99/$9.99; purchase options `sparks-50/200/500`), imported into RevenueCat and mapped into the offering. Verified end-to-end on gamma: a synthetic `PLAY_STORE` webhook for each real store id (`me.revelryapp.quiz.sparks_50/200/500`) credits 50/200/500 and dedups on replay.
- **Native sign-in** — wired (`utils/socialAuth.ts` `SocialLogin.initialize()`, iOS Google URL scheme in `Info.plist`); see §6.7. App version bumped to **3.1.0 / build 5** (both platforms).

**Pending (manual — console/Xcode/device):**
- **Native device test** — the only thing left to prove real purchases end-to-end. Android: install the internal-testing build on a device via the tester opt-in link with a **license tester**, buy a pack, confirm the live webhook credits sparks. iOS: real device + sandbox account (see also the Apple-approval note below).
- **Native sign-in console** — "Sign in with Apple" capability in Xcode; GCP Android OAuth client (package `me.revelryapp.quiz` + Play App Signing SHA-1).
- **Web Stripe** — set `STRIPE_SECRET_KEY` + a `/webhook/stripe` endpoint per env (test on gamma, live on prod); inline `price_data` needs no Price objects.
- **Prod** — set `REVENUECAT_WEBHOOK_SECRET` + add the prod RevenueCat webhook, then deploy prod backend + ship the native builds.

---

## 1. Goal & scope

Let the **native iOS and Android apps** sell Sparks through the platform stores, the same way the
**web** app sells them through Stripe. Today:

- Web checkout (Stripe) is fully built (`/checkout/create`, `/webhook/stripe`) — only missing live keys.
- The native iOS app **blocks** Stripe (`platform == "ios"` → `403`) but has **no IAP path** to fulfill the purchase, so iOS cannot sell anything.
- The native Android app would currently **fall through to Stripe** — a Google Play policy violation, because Sparks are digital goods consumed in-app. (Mitigated only by the fact that the Play build is still in Draft.)

This spec adds native IAP for **both** stores and closes the Android-uses-Stripe hole.

**In scope:** consumable Spark packs on iOS + Android, server-side fulfillment, idempotency, refund/chargeback clawback, restore semantics, the platform guard fix, store/console setup, env, testing, rollout. **Also re-prices the web Stripe pack onto the same three-tier ladder** (single-tier → 50/200/500) so all three surfaces sell identical packs — the Stripe `/checkout/create` change is in §5.6.

**Out of scope (explicit non-goals for v1):** subscriptions, non-consumable entitlements (watermark/day-pass — those are VibePix concepts LocalPlay does not have), promotional offers/intro pricing.

---

## 2. Key decision — use RevenueCat (mirror VibePix)

There are two ways to do server-side IAP validation:

| Approach | What the backend does | Effort | Risk |
|---|---|---|---|
| **A. RevenueCat (RECOMMENDED)** | Trust one bearer-authed webhook from RevenueCat; RevenueCat validates Apple+Google receipts. | Low — one webhook handler, one client SDK. Reuses existing idempotent `credit_purchase`. | Low — battle-tested; VibePix already runs it in prod on the same Apple/GCP accounts. |
| B. Direct verification | Implement Apple App Store Server API (JWS/`signedTransactionInfo` via the App Store Server Library) **and** Google Play Developer API (`androidpublisher` service account) **and** their server notifications (ASSN v2 + RTDN/Pub-Sub). | High — two independent receipt-validation stacks, key management (.p8, service-account JSON), notification plumbing. | Higher — more surface area to get wrong; LocalPlay would be the first project to maintain it. |

**Decision: Approach A (RevenueCat).** Rationale:
- VibePix (same developer accounts: Apple key `655WPHCMD7`, GCP project `revelryapp`, service account `revenuecat-play@revelryapp.iam.gserviceaccount.com`) already validated this path end-to-end in production — we reuse the playbook and the RevenueCat account.
- The LocalPlay backend already has everything RevenueCat fulfillment needs: idempotent `credit_purchase(reference_id)`, `webhook_events` dedup, `entitlements.apple_transaction_id`/`google_order_id` unique columns.
- No Apple/Google verification libraries enter the Python backend; the only new dependency is the RevenueCat **client** SDK.

Everything below assumes Approach A. (Appendix C sketches the direct-verification fallback in case we ever drop RevenueCat.)

### 2.1 VibePix reference implementation

Use VibePix as the reference implementation, but port only the spark-pack/RevenueCat patterns that fit
LocalPlay's spark economy:

Reference files:
- `/Users/Avi/Desktop/dev/antigravity/gamesworkspace/vibepix/server.js`
  - `PRODUCTS` spark tiers (`spark_pack_50/200/500`) and `RC_PRODUCT_MAP`.
  - `/api/revenuecat/webhook` auth, event parsing, product mapping, unknown-product acknowledgement, purchase
    idempotency, and webhook retry behavior.
  - `/api/checkout/session` SKU-driven Stripe path.
- `/Users/Avi/Desktop/dev/antigravity/gamesworkspace/vibepix/public/app.js`
  - `SKU_TO_RC_PRODUCT` / `SKU_TO_STORE_PRODUCT`.
  - `handleNativePurchase(sku)` offering unwrap, product/package matching, purchase cancellation handling, and
    8 x 2s polling for fulfillment.
  - `updateNativePrices(Purchases)` localized store price replacement.
  - native `restorePurchases()` and RevenueCat initialization flow.
- `/Users/Avi/Desktop/dev/antigravity/gamesworkspace/vibepix/tests/api/endpoints.test.js`
  - RevenueCat webhook auth/product-map tests and webhook route-structure tests.

Port these patterns:
- Product ids map through a server-owned catalog; spark grants never trust client/webhook amounts.
- Match native packages by RevenueCat id, fully qualified store id, then SKU suffix fallback with a warning.
- Treat RevenueCat user cancellation as a no-op.
- Poll the server-side balance after native purchase because fulfillment is webhook-driven.
- Acknowledge unknown products with 200 to avoid infinite RevenueCat retries, but do not credit anything.
- Use `transaction_id || store_transaction_id` and `event.id || rc_<transaction>` as the dedupe key source.

Do **not** port these VibePix-specific concepts:
- `remove_watermark`, `day_pass_24h`, `pro_monthly`, `pro_annual`, subscription renewals, billing issues, or
  no-watermark entitlements.
- VibePix's `purchases` status table/locking model unless we later discover LocalPlay's existing
  `webhook_events` + `credit_purchase(reference_id)` double-idempotency is insufficient. LocalPlay should start
  with the simpler existing wallet primitives.

---

## 3. Architecture & data flow

```
                          ┌─────────────────────────────────────────┐
  iOS / Android native    │  RevenueCat Capacitor SDK                │
  app (Capacitor shell,   │  @revenuecat/purchases-capacitor         │
  appId me.revelryapp.quiz)│  - configure(apiKey per platform)        │
                          │  - logIn(appUserID = LocalPlay wallet_id)│
                          │  - getOfferings() / purchasePackage()    │
                          └───────────────┬─────────────────────────┘
                                          │ purchase
                                          ▼
                        Apple App Store / Google Play  ──────────┐
                                          │ receipt                │
                                          ▼                        │
                                  ┌───────────────┐                │
                                  │  RevenueCat    │  validates     │
                                  │  (cloud)       │  receipt       │
                                  └──────┬────────┘                 │
                                         │ webhook (Bearer secret)  │
                                         ▼                          │
   LocalPlay backend  POST /webhook/revenuecat                      │
     1. auth: Authorization == "Bearer <REVENUECAT_WEBHOOK_SECRET>" │
     2. dedup: webhook_events(event_id)                             │
     3. map product_id → spark amount (PRODUCTS catalog)            │
     4. wallet_id = event.app_user_id                               │
     5. credit_purchase(wallet_id, amount, reference_id=iap:store:txn)│ idempotent
     6. record entitlements.apple_transaction_id/google_order_id    │
     7. optionally store pending-token notification for UX polling  │
                                         │                          │
                                         ▼                          │
   Native client polls GET /tokens/balance after purchase ─────────┘
     → refreshed balance; web Stripe still polls /checkout/token
```

**Why `app_user_id == wallet_id`:** RevenueCat's `appUserID` is set to the LocalPlay wallet id (the
signed-in `user_id` if present, else the `device_id`). The webhook then carries the wallet id directly —
no checkout metadata round-trip needed (unlike Stripe, where we stuff `wallet_id` into session metadata).
On sign-in we call `Purchases.logIn(user_id)` so future purchases attach to the user wallet; past
device-scoped purchases are reconciled by the existing `merge_wallet(device_id, user_id)` on sign-in.

---

## 4. Product catalog

LocalPlay sells **consumable Spark packs only**. We deliberately **mirror VibePix's spark-pack tier ladder**
(50 / 200 / 500 sparks at $1.99 / $4.99 / $9.99) — same SKU names, same RevenueCat product IDs, same spark
amounts and prices. This is intentional: the two apps may **merge their spark economies** into a shared
wallet later (see §4.3), and identical SKUs/RC IDs/amounts make that merge a backend join rather than a
re-pricing/re-mapping exercise.

> **One ladder across all surfaces:** the **web** Stripe pack is also moved onto this same ladder. The
> legacy single web pack (110 sparks @ $0.99, `TOKEN_PACK_AMOUNT` = 110, product `prod_UCI5z14xGpyjhu`) is
> **retired** in favor of the three tiers below, so web (Stripe) and native (IAP) sell identical packs at
> identical prices. The catalog (§4.1) is the single source of truth for spark amounts on every surface;
> per-surface it just carries a different price/product handle (Stripe price id vs store product id). The
> Stripe `/checkout/create` changes for this are in §5.6.

### 4.1 Server catalog (`backend/config.py` or a new `backend/iap_products.py`)

This is the **single source of truth for spark amounts on every surface** (web Stripe + iOS + Android).
Each sku carries the spark grant plus the per-surface product handle.

```python
# Amounts/SKUs/RC-ids/prices deliberately mirror VibePix (server.js PRODUCTS) so the economies can merge.
# `sparks` and `price_cents` are authoritative; never trust client- or webhook-body-supplied amounts.
# Web checkout builds Stripe `price_data` inline from price_cents (VibePix-style) — NO pre-created Stripe
# Price objects and NO per-tier price env vars.
SPARK_PRODUCTS = {
    "spark_pack_50": {
        "sparks": 50, "price_cents": 199, "name": "50 Sparks",
        "rc_id": "rc_spark_pack_50",
        "ios": "me.revelryapp.quiz.sparks_50", "android": "me.revelryapp.quiz.sparks_50",
    },
    "spark_pack_200": {
        "sparks": 200, "price_cents": 499, "name": "200 Sparks",
        "rc_id": "rc_spark_pack_200",
        "ios": "me.revelryapp.quiz.sparks_200", "android": "me.revelryapp.quiz.sparks_200",
    },
    "spark_pack_500": {
        "sparks": 500, "price_cents": 999, "name": "500 Sparks",
        "rc_id": "rc_spark_pack_500",
        "ios": "me.revelryapp.quiz.sparks_500", "android": "me.revelryapp.quiz.sparks_500",
    },
}

# Reverse lookup: any store/rc product id → sku (built at import time)
SPARK_PRODUCT_BY_ANY_ID = {}
for _sku, _p in SPARK_PRODUCTS.items():
    for _key in ("rc_id", "ios", "android"):
        SPARK_PRODUCT_BY_ANY_ID[_p[_key]] = _sku
```

(The map is named `SPARK_PRODUCTS` rather than `IAP_PRODUCTS` because it also drives the web Stripe path.
The webhook handlers reference `SPARK_PRODUCT_BY_ANY_ID` for product→sku resolution. Because Stripe uses
inline `price_data`, the web side needs **no Stripe Product/Price objects and no price-id env** — only
`STRIPE_SECRET_KEY` + the webhook secret.)

> Note: with a multi-tier catalog the per-purchase grant is keyed off the **product id → sku → sparks**
> lookup, not off the single `TOKEN_PACK_AMOUNT`. `MAX_TOKEN_BALANCE` (default 1000) must be ≥ the largest
> single pack (500) — it is. The webhook still caps to the catalog amount, never a client/body value.

### 4.2 Store + RevenueCat IDs (matches VibePix tiers)

| SKU (== VibePix) | Sparks | Price | App Store / Play product ID | RevenueCat ID |
|---|---|---|---|---|
| `spark_pack_50` | 50 | $1.99 (Tier 2) | `me.revelryapp.quiz.sparks_50` | `rc_spark_pack_50` |
| `spark_pack_200` | 200 | $4.99 (Tier 5) | `me.revelryapp.quiz.sparks_200` | `rc_spark_pack_200` |
| `spark_pack_500` | 500 | $9.99 (Tier 10) | `me.revelryapp.quiz.sparks_500` | `rc_spark_pack_500` |

- **Type:** Consumable (iOS "Consumable", Android "In-app product / consumable").
- SKUs, RevenueCat IDs, spark amounts, and prices are **identical to VibePix** (`server.js:199-207`); only the
  store product id prefix differs (`me.revelryapp.quiz.*` vs VibePix's `com.avishkarsoftware.vibepix.*`),
  because store products are bundle-scoped and cannot be literally shared across apps.
- Bundle id is `me.revelryapp.quiz` (from `frontend/capacitor.config.ts`).

### 4.3 Designing for a future economy merge

Mirroring VibePix is the cheap insurance for merging the wallets later. To keep that path open:
- **Identical SKUs + RC product IDs + amounts** (done above) — a merged backend can treat a
  `rc_spark_pack_200` from either app as "200 sparks" with no per-app branching.
- The wallet/`token_transactions` model is already shared in shape between the apps (both Supabase, both
  `wallet_id = user_id || device_id`, both idempotent on `reference_id`). A merge would unify on
  `user_id` and reconcile device wallets via the existing `merge_wallet` mechanism.
- Do **not** bake `vibepix`/`localplay` assumptions into the spark amount or the webhook; the only
  app-specific values are the store product-id prefix and the RevenueCat app/keys.
- VibePix's non-spark products (`remove_watermark`, `day_pass_24h`, `pro_monthly`, `pro_annual`) are **not**
  adopted — LocalPlay has no watermark/day-pass/subscription concept (Appendix B). A merge would keep those
  VibePix-only.

---

## 5. Backend changes

All changes are additive. **No schema migration is required** — the Supabase prod/gamma schema already
has `entitlements.apple_transaction_id`/`google_order_id` (partial-unique), `token_transactions.reference_id`
dedup, the `webhook_events` table, and the `credit_purchase`/`debit_tokens` RPCs.

### 5.1 New endpoint: `POST /webhook/revenuecat`

Mirror `webhook/stripe` (`backend/main.py:5786`). Pseudocode:

```python
@app.post("/webhook/revenuecat")
async def revenuecat_webhook(req: Request):
    if not config.REVENUECAT_WEBHOOK_SECRET:
        raise HTTPException(503, "IAP not configured")
    auth = req.headers.get("authorization", "")
    if auth != f"Bearer {config.REVENUECAT_WEBHOOK_SECRET}":
        logger.warning("RevenueCat webhook auth failure from %s", _get_client_ip(req))
        raise HTTPException(401, "Unauthorized")

    body = await req.json()
    event = body.get("event") or {}
    if not isinstance(event, dict):
        raise HTTPException(400, "Missing event")
    event_type = (event.get("type") or "").upper()

    wallet_id = (event.get("app_user_id") or "").strip()
    product_id = (event.get("product_id") or "").strip()
    store = (event.get("store") or "").upper()       # "APP_STORE" | "PLAY_STORE"
    txn_id = (event.get("transaction_id") or event.get("store_transaction_id") or "").strip()
    event_id = (event.get("id") or (f"rc_{store}_{txn_id}" if txn_id else "")).strip()
    if not event_id:
        raise HTTPException(400, "Missing event identifier")
    if not wallet_id:
        raise HTTPException(400, "Missing app_user_id")

    # Idempotency: skip already-processed events (survives restarts).
    # A later event with a new id but the same transaction id is still protected by credit_purchase.
    if event_id and db.is_webhook_event_processed(event_id):
        return {"status": "ok", "detail": "already processed"}

    sku = config.SPARK_PRODUCT_BY_ANY_ID.get(product_id)
    reference_id = f"iap:{store or 'UNKNOWN'}:{txn_id}"

    if event_type in ("INITIAL_PURCHASE", "NON_RENEWING_PURCHASE"):
        # consumable grant
        if not sku:
            logger.warning("RevenueCat unknown product: %s", product_id)
            db.mark_webhook_event_processed(event_id)
            return {"status": "ok", "detail": "unknown product"}
        if not txn_id:
            raise HTTPException(400, "Missing transaction_id")
        sparks = config.SPARK_PRODUCTS[sku]["sparks"]

        # reference_id = store transaction id → credit_purchase is idempotent on it
        credited, new_balance = db.credit_purchase(
            wallet_id, sparks, reference_id,
            metadata=json.dumps({"source": "iap", "store": store, "product_id": product_id}),
        )
        # Best-effort: record the store transaction id for restore/audit (unique index dedups)
        _record_iap_entitlement(wallet_id, store, txn_id)
        if credited:
            # Optional UX notification for guest/device wallets. Native signed-in clients poll balance (§5.4).
            db.store_pending_token(wallet_id, json.dumps(
                {"tokens_added": sparks, "new_balance": new_balance}))

    elif event_type in ("REFUND", "CANCELLATION"):
        # Clawback — mirror the Stripe charge.refunded path (debit_tokens, idempotent)
        if sku and txn_id:
            already = db.get_refund_debits_for_session(reference_id)
            owed = config.SPARK_PRODUCTS[sku]["sparks"]
            refund_tokens = max(0, owed - already)
            if refund_tokens:
                db.debit_tokens(wallet_id, refund_tokens, "refund", reference_id)

    # else: TEST, TRANSFER, etc. → ack and ignore

    if event_id:
        db.mark_webhook_event_processed(event_id)
    return {"status": "ok"}
```

Notes:
- **Idempotency is double-layered:** `webhook_events(event_id)` (skips exact event replays) **and**
  `credit_purchase(reference_id=f"iap:{store}:{txn_id}")` (the existing `(wallet_id, reference_id, reason='purchase')`
  unique index prevents a second credit even if RevenueCat sends a different event id for the same transaction).
- **Amounts come from the server catalog**, never from the webhook body — same anti-tamper stance as Stripe.
- **`store_pending_token` keying:** the existing Stripe flow stores the notification under `device_id`.
  For IAP the `app_user_id` is the wallet id. For guests `wallet_id == device_id`, so polling works as-is.
  For signed-in users, see §5.4.

#### 5.1.1 RevenueCat event handling rules

Implement this exact response policy so RevenueCat retries only when retrying is useful:

| Condition | HTTP | Mark `webhook_events`? | Behavior |
|---|---:|---|---|
| Backend missing `REVENUECAT_WEBHOOK_SECRET` | 503 | No | Misconfiguration; operator fixes env. |
| Bad/missing bearer token | 401 | No | Log auth failure. |
| Missing/non-object `event` | 400 | No | Malformed payload. |
| Missing both `event.id` and transaction id | 400 | No | Cannot dedupe safely. |
| Missing `app_user_id` | 400 | No | Cannot choose wallet. |
| Unknown `product_id` | 200 | Yes | Ack and ignore to avoid infinite retries. |
| Unsupported event type (`TEST`, `TRANSFER`, renewal/subscription-only events) | 200 | Yes | Ack and ignore. |
| Grant/refund DB error | 500 | No | Let RevenueCat retry. |

Allowed grant event types for v1 are `INITIAL_PURCHASE` and `NON_RENEWING_PURCHASE`. Treat `RENEWAL`,
`EXPIRATION`, `BILLING_ISSUE`, and subscription lifecycle events as unsupported/ignored because LocalPlay v1 has
no subscriptions.

#### 5.1.2 `_record_iap_entitlement`

Add a helper in `backend/main.py` or `backend/db.py`:

```python
def _record_iap_entitlement(wallet_id: str, store: str, transaction_id: str) -> None:
    # Best effort audit/restore marker only. Spark credit is authoritative in token_transactions.
    # Store "APP_STORE" transactions in apple_transaction_id and "PLAY_STORE" in google_order_id.
    # For signed-in users wallet_id is user_id; for guests wallet_id is device_id.
    # Swallow unique-conflict duplicates because credit_purchase is the authoritative idempotency gate.
```

Implementation may call the existing `db.create_entitlement(...)` with `games_remaining=0` and a neutral
status such as `iap_consumed`, or add a small explicit DB helper. Do not make restored legacy entitlements
grant games again for these rows; they are audit markers, not active game-pass entitlements.

### 5.2 Fix the platform guard (block Android too)

`backend/main.py:5739` currently blocks only iOS. Native platforms must use IAP, not Stripe:

```python
# before
if platform == "ios":
    raise HTTPException(403, "Use in-app purchase on iOS")
# after
if platform in ("ios", "android"):
    raise HTTPException(403, "Use in-app purchase on native platforms")
```

This matches VibePix (`server.js:2207`). Web is unaffected.

### 5.3 Restore semantics

Consumables are generally **not restorable** by the stores once consumed — Apple/Google won't re-deliver a
consumed consumable, and RevenueCat won't re-fire a grant for it. So for Sparks, restore is effectively a
no-op. Keep the existing `POST /purchases/restore` (`main.py:5955`) for the legacy entitlement path; on the
client, `Purchases.restorePurchases()` covers any future non-consumable/subscription SKU. **Document that
"Restore" will not re-credit already-consumed Spark packs** — this is expected store behavior, not a bug.

### 5.4 Signed-in vs guest notification delivery (small follow-up)

`store_pending_token`/`pop_pending_token` are keyed by `device_id`. When a signed-in user buys, the
webhook's `app_user_id` is the `user_id`, but the client polls `/checkout/token` with its `X-Device-Id`.
Two options:
- **(Recommended, simplest)** On the client, after a successful `purchasePackage`, **re-fetch the balance**
  (`GET /tokens/balance`) on the 2s poll instead of relying solely on `/checkout/token`. Balance reflects
  the credited sparks regardless of keying. This also matches VibePix's "poll fetchSparks()" approach and
  avoids backend keying changes.
- (Alt) Have the webhook also write the pending-token under the user's current `device_id` (requires a
  user→device lookup). More code; not needed if the client polls balance.

Spec adopts the recommended option: **client polls `/tokens/balance` after purchase**; `/checkout/token`
remains the Stripe path.

### 5.5 Config / env additions (`backend/config.py`)

```python
REVENUECAT_WEBHOOK_SECRET = os.getenv("REVENUECAT_WEBHOOK_SECRET", "")
# (RevenueCat client keys are NOT backend secrets — they're public SDK keys baked into the app build, §6.4)
```

No per-tier Stripe price env vars: prices live in `SPARK_PRODUCTS[*]["price_cents"]` and the web checkout
builds Stripe `price_data` inline. `TOKEN_PACK_AMOUNT` and the single `STRIPE_PRICE_ID` are **deprecated**
(no longer used for checkout; left defined for now). Startup notice (`_check_payment_config`): if
`REVENUECAT_WEBHOOK_SECRET` is unset → native IAP disabled; if `STRIPE_SECRET_KEY` is unset → web checkout 503.

### 5.6 Web Stripe checkout — tiered ladder via inline `price_data` (`/checkout/create`)

`/checkout/create` takes a **sku** and builds the Stripe line item inline from the catalog — the
**VibePix-style `price_data` approach** (`vibepix/server.js:2248`), so there are **no pre-created Stripe
Price objects** to manage:

```python
class CheckoutRequest(BaseModel):
    device_id: str
    sku: str = config.DEFAULT_SPARK_SKU   # which tier; default keeps old clients working
    promo_id: str = ""
    # validator coerces unknown/blank sku → DEFAULT_SPARK_SKU

# in create_checkout, after the platform guard + device match:
if not config.STRIPE_SECRET_KEY:
    raise HTTPException(503, "Payments not configured")
pack = config.SPARK_PRODUCTS[request.sku]
# stripe.checkout.Session.create(line_items=[{
#     "price_data": {"currency": "usd", "product_data": {"name": pack["name"]},
#                    "unit_amount": pack["price_cents"]},
#     "quantity": 1}], ...)
# metadata: {"device_id", "wallet_id", "token_amount": pack["sparks"], "sku": request.sku, "promo_id"}
```

The **Stripe webhook** (`/webhook/stripe`) reads `token_amount` from session metadata and caps it to
`max(MAX_SPARK_PACK, PROMO_TOKEN_AMOUNT)` (500). Refund proration keys off the session's stored
`token_amount`, unchanged.

**Stripe dashboard:** nothing to create for the catalog — inline `price_data` means no Product/Price
objects. The **only** Stripe setup is one webhook endpoint (§7). (VibePix uses the same inline approach, which
is why its spark packs never appear in the Stripe product catalog.)

**Frontend web buy UI** shows the same three tiers and sends `sku` in the `/checkout/create` body
(`OrganizerPage.tsx:2969`).

### 5.7 Backend tests (`backend/tests/`)

Add `test_iap_webhook.py` mirroring the Stripe webhook tests:
- auth: missing/!= bearer → 401; missing secret → 503; malformed/missing event → 400.
- `INITIAL_PURCHASE` credits the mapped sparks once; **replaying the same `event_id` does not double-credit**;
  a **different `event_id` with the same `transaction_id` does not double-credit** (`iap:{store}:{txn_id}` reference-id dedup).
- unknown `product_id` → no credit, 200 ack.
- `REFUND` debits the granted amount once; second refund event does not double-debit (`get_refund_debits_for_session`).
- amount is taken from the server catalog, not from a tampered `price`/amount field in the body.
- `app_user_id` missing → 400, no credit.
- `/checkout/create` blocks both `X-Platform: ios` and `X-Platform: android`, while `X-Platform: web` remains allowed.
- `/checkout/create` accepts `sku`, chooses the matching Stripe price id, and writes `sku` + tier amount into metadata.
- Stripe webhook caps metadata grants to `max(p["sparks"] for p in SPARK_PRODUCTS.values())`.

---

## 6. Client (Capacitor) changes — `frontend/`

### 6.1 Dependency

**Installed:** `@revenuecat/purchases-capacitor@^12.3.2` (Capacitor 8 line; registered for iOS via SPM
`Package.swift` and Android via Gradle on `cap sync` — **no CocoaPods**, this project uses SPM).

`utils/iap.ts` loads it via a **code-split dynamic import** (`await import('@revenuecat/purchases-capacitor')`)
so it's bundled as a lazy chunk: never pulled into the web critical path (`initIAP` returns early on
`platform==='web'`), but available to the native Capacitor bridge.

### 6.2 Initialization (native only)

First extract the private `getPlatform()` helper from `frontend/src/utils/api.ts` into a shared
`frontend/src/utils/platform.ts`:

```ts
export type LocalPlayPlatform = 'web' | 'ios' | 'android';
export function getPlatform(): LocalPlayPlatform {
  // Same behavior as current api.ts: only native Capacitor reports ios/android.
  // Mobile Safari/Chrome remains "web" and uses Stripe.
}
export function isNativePlatform() {
  return getPlatform() === 'ios' || getPlatform() === 'android';
}
```

Then update `api.ts`, `SettingsDrawer.tsx`, and the new IAP helper to import this shared function so the
payment/IAP platform decision is consistent.

> **Do NOT fold `utils/analytics.ts`'s own `getPlatform()` into this helper.** It deliberately returns
> finer labels (`pwa` for standalone web, `native` as a fallback) for telemetry only; collapsing it into the
> strict `ios|android|web` payment-gating helper would change analytics semantics and lose the `pwa` bucket.
> The two are separate on purpose — only the `api.ts` copy moves to `platform.ts`.

Create `frontend/src/utils/iap.ts`, called once at app start when `getPlatform() !== 'web'`:

```ts
import { Purchases } from '@revenuecat/purchases-capacitor';

export async function initIAP() {
  const platform = getPlatform();                  // 'ios' | 'android' | 'web'
  if (platform === 'web') return;
  const apiKey = platform === 'ios'
    ? import.meta.env.VITE_REVENUECAT_IOS_KEY
    : import.meta.env.VITE_REVENUECAT_ANDROID_KEY;
  if (!apiKey) return;                             // not configured → IAP disabled, UI hides buy on native
  await Purchases.configure({ apiKey, appUserID: getWalletAppUserId() });
}

// appUserID = signed-in user_id if available else device_id (mirrors backend wallet_id resolution)
function getWalletAppUserId(): string {
  return getUserId() /* from session */ || getDeviceId();
}
```

Concrete wiring:
- In `App.tsx`, add a small `IAPBootstrap` component inside `AuthProvider` that calls `initIAP()` once on mount.
- In `AuthContext.tsx`, after `signInWithBackend` succeeds and `result.user.id` is known, call
  `iapLogIn(result.user.id)` best-effort. On sign-out, call `iapLogOut()` best-effort before/after
  `storageSignOut()`. IAP failures must not block auth.
- The existing `merge_wallet` reconciles device-scoped sparks bought before sign-in.

### 6.3 Purchase flow (replace the iOS 403 dead-end)

Today `OrganizerPage.tsx:2969` calls `/checkout/create` and shows "Use the in-app purchase option on iOS"
when it gets a 403. Replace that branch: when `getPlatform() !== 'web'`, **do not call `/checkout/create`** —
call the native flow instead:

```ts
async function buySparksNative(sku: 'spark_pack_50' | 'spark_pack_200' | 'spark_pack_500') {
  const offerings = unwrap(await Purchases.getOfferings());   // RC wraps as {offerings:...}
  const pkg = findPackage(offerings, sku);                    // match by rc_id / store id / suffix
  await Purchases.purchasePackage({ aPackage: pkg });         // throws on user cancel (code 1)
  // Fulfillment is server-side via webhook; poll balance for up to ~16s
  await pollForSparkCredit();                                 // GET /tokens/balance every 2s
}
```

The native buy UI shows the **three tiers** (50 / 200 / 500) with store-localized prices from
`getOfferings()`. Reuse VibePix's hardening: unwrap the `{offerings}` envelope, match each product by
rc_id → fully-qualified store id → suffix fallback (log a warning on suffix match), and treat
purchase-cancel as a silent no-op.

Web keeps calling `/checkout/create`, but now passes the selected `sku`.

Concrete UI change:
- Add a reusable `frontend/src/components/SparkPurchaseModal.tsx`.
- `ErrorModal`'s upgrade action should open `SparkPurchaseModal` instead of immediately starting checkout.
- The modal shows the three packs, disabled/loading state per pack, and copy like "Sparks are used to generate
  and host games." It hides entirely on host-app/Revelry surfaces.
- On native, prices come from RevenueCat offerings. On web, prices can use static catalog copy until Stripe
  price lookup is added.
- Native unconfigured state: show a non-purchase message ("Purchases are not available in this build") and no
  broken buy button.

### 6.4 Native price display & store gating

- Fetch live store prices via `getOfferings()` and render the localized price string (don't hardcode $0.99
  in the native UI — stores localize/currency-convert).
- If RC isn't configured (no API key) or `getOfferings()` returns nothing, **hide the buy button on native**
  and fall back to ad-reward/daily-bonus only. Never show a buy button that can't transact.

### 6.5 Restore button

`SettingsDrawer.tsx:226` already calls `POST /purchases/restore`. On native, **also** call
`Purchases.restorePurchases()` first, then re-fetch balance/entitlements (VibePix `app.js:2462`). Show
"Purchases restored" / "Nothing to restore". Copy should set expectations that consumed Spark packs aren't
re-credited (§5.3).

Implementation detail: keep the button only on native builds with a configured RevenueCat key. Web restore stays
hidden because Stripe purchases are fulfilled by webhook and visible through the wallet balance. Backend
`/purchases/restore` is best-effort legacy entitlement compatibility; Supabase/credit failures return a user-facing
`503` instead of an opaque `500`.

RevenueCat identity must always map to a LocalPlay wallet id:

- On launch before sign-in, configure RevenueCat with the LocalPlay `device_id`.
- On successful app sign-in, call `Purchases.logIn({ appUserID: user.id })`.
- On sign-out, switch RevenueCat back to `Purchases.logIn({ appUserID: device_id })`. Do **not** leave the app in
  bare `Purchases.logOut()` state because RevenueCat can create its own anonymous id, and LocalPlay webhooks require
  `app_user_id` to be either a LocalPlay signed-in user id or LocalPlay device id.

### 6.6 Client env (`.env` / Vite)

Public RevenueCat SDK keys (these are **publishable**, safe to bake into the build):

```
VITE_REVENUECAT_IOS_KEY=appl_xxx
VITE_REVENUECAT_ANDROID_KEY=goog_xxx
```

`scripts/cap-build.mjs` bakes these (and the OAuth client ids in §6.7) into native builds; the IONOS web
build does not need them.

### 6.7 Native sign-in (rides this release)

LocalPlay's sign-in is **not Firebase** (unlike revelryapp/VibePix). Web uses Google Identity Services +
Apple JS directly; native uses `@capgo/capacitor-social-login` → ID token → backend verifies it (`auth.py`:
Google via `verify_oauth2_token`, Apple via JWKS). The native path was added web-only and was never wired
(no `SocialLogin.initialize()`), so native sign-in never worked. Now fixed:

- `utils/socialAuth.ts` `ensureSocialLoginInitialized()` calls `SocialLogin.initialize(...)` on native (no-op on web); `SettingsDrawer` calls it before `login()`. iOS Apple intentionally uses `apple: {}` so the plugin resolves with the local `ASAuthorizationAppleIDProvider` ID token; Android Apple uses `{ clientId, redirectUrl }` for the web-based Apple flow.
- `webClientId` = the web Google OAuth client; `iOSClientId` = the iOS Google OAuth client. Backend Google verification must accept both through `GOOGLE_CLIENT_IDS=<web-client>,<ios-client>` because native iOS Google Sign-In can return an ID token whose `aud` is the iOS OAuth client. Apple `clientId` = the Service ID (`me.revelryapp.quiz.web`) for the Android/web Apple flow, not the native iOS flow.
- Backend Apple verification must accept both Apple audiences: the web/Android Service ID (`me.revelryapp.quiz.web`) and the native iOS bundle id (`me.revelryapp.quiz`) through `APPLE_CLIENT_IDS=me.revelryapp.quiz.web,me.revelryapp.quiz`.
- Frontend session revalidation keeps the cached signed-in user on `/auth/me` network/timeout/server failures and only clears the session on `401/403`, so a slow mobile network does not silently sign users out.
- Frontend auth changes dispatch `refresh-sparks` after successful sign-in and sign-out so the fixed spark badge does not keep showing the previous device/signed-in wallet balance after the wallet switches.
- iOS `Info.plist` carries the Google reversed-client-id **URL scheme** for the OAuth redirect.
- iOS `App/App.entitlements` carries `com.apple.developer.applesignin = Default`, wired through `CODE_SIGN_ENTITLEMENTS`, so native Apple Sign In can complete before posting the Apple ID token to `/auth/signin`.
- `cap-build.mjs` bakes the **public** `VITE_GOOGLE_CLIENT_ID` / `VITE_GOOGLE_IOS_CLIENT_ID` / `VITE_APPLE_CLIENT_ID`.

**Pending console (see DEPLOY.md §3d):** create a **GCP Android OAuth client** (package `me.revelryapp.quiz` + the Play App Signing SHA-1) so native Android Google sign-in works. iOS Google client, redirect scheme, and Apple entitlement are configured.

---

## 7. Store & RevenueCat console setup (one-time)

### 7.1 RevenueCat dashboard
1. Create a **new RevenueCat project** "LocalPlay/Revelry Games" (or a new app within the existing org).
2. Add an **App Store app** (bundle `me.revelryapp.quiz`) and a **Play Store app** (package `me.revelryapp.quiz`).
3. **Apple credential:** upload the **In-App Purchase key** (.p8). The existing VibePix key
   `SubscriptionKey_655WPHCMD7.p8` is app-specific to VibePix — generate a **new In-App Purchase key** for
   the Revelry Games app in App Store Connect → Users and Access → Integrations → In-App Purchase.
4. **Google credential:** reuse the GCP service account `revenuecat-play@revelryapp.iam.gserviceaccount.com`
   (project `revelryapp`) — grant it access to the Play Console app. Ensure APIs are enabled:
   ```bash
   gcloud services enable androidpublisher.googleapis.com --project revelryapp
   gcloud services enable pubsub.googleapis.com --project revelryapp
   ```
   > Gotcha from VibePix: "Credentials need attention / could not validate inappproducts API permissions"
   > is almost always `androidpublisher.googleapis.com` not being enabled — fix that first.
5. Create the **products/offerings** in RevenueCat: products `rc_spark_pack_50` / `rc_spark_pack_200` /
   `rc_spark_pack_500`, each mapped to its App Store and Play store product
   (`me.revelryapp.quiz.sparks_50` / `_200` / `_500`); put all three in the default Offering.
6. **Webhook:** Integrations → Webhooks → add `https://gamesapi.revelryapp.me/webhook/revenuecat` (prod) and
   `https://gamesapi-gamma.revelryapp.me/webhook/revenuecat` (gamma) with the Authorization header
   `Bearer <REVENUECAT_WEBHOOK_SECRET>`. Use **separate** secrets per environment.
7. Get the **public SDK keys** (Apple `appl_…`, Google `goog_…`) → into the native Vite build env.

### 7.2 App Store Connect (Apple)
1. Create three **Consumable** IAPs: `me.revelryapp.quiz.sparks_50` (Tier 2, $1.99, "50 Sparks"),
   `…sparks_200` (Tier 5, $4.99, "200 Sparks"), `…sparks_500` (Tier 10, $9.99, "500 Sparks").
2. Fill each IAP's metadata + review screenshot (Apple requires a review screenshot **per IAP**).
3. Create a **Sandbox tester** (Users and Access → Sandbox → Testers).
4. IAPs must be in "Ready to Submit" (draft) state to work in sandbox.

### 7.3 Google Play Console
1. The app must be on at least an **internal testing** track (currently Draft — needs an internal build).
2. Create three **in-app products** `me.revelryapp.quiz.sparks_50` / `_200` / `_500` (consumable),
   $1.99 / $4.99 / $9.99, and activate them.
3. Add **license testers** (Settings → License testing) — their purchases are free.
4. Server-side: nothing extra beyond the RevenueCat service-account binding.

---

## 8. Environment variables summary

Backend (GCP, gamma + prod `.env`/`.env.gamma`) — set via the existing deploy upsert mechanism:

| Var | Where | Notes |
|---|---|---|
| `REVENUECAT_WEBHOOK_SECRET` | gamma + prod | **distinct per env**; never printed/committed |
| `STRIPE_SECRET_KEY` | gamma + prod | enables web checkout (test key for gamma, live for prod) |
| `STRIPE_WEBHOOK_SECRET` | gamma + prod | from the per-env Stripe webhook endpoint |

(No per-tier Stripe price env vars — prices are inline `price_data` from the catalog.)

Native client build (Vite, native builds only — all **public**, baked by `scripts/cap-build.mjs`):

| Var | Notes |
|---|---|
| `VITE_REVENUECAT_IOS_KEY` | publishable `appl_…` |
| `VITE_REVENUECAT_ANDROID_KEY` | publishable `goog_…` |
| `VITE_GOOGLE_CLIENT_ID` | web Google OAuth client (also serverClientId for native sign-in) |
| `VITE_GOOGLE_IOS_CLIENT_ID` | iOS Google OAuth client |
| `VITE_APPLE_CLIENT_ID` | Apple Service ID (`me.revelryapp.quiz.web`) for the Android/web Apple flow |

(No Apple `.p8` or GCP service-account JSON lives in the LocalPlay backend — RevenueCat holds those.)

---

## 9. Testing plan

1. **Backend unit tests** (`test_iap_webhook.py`, §5.7) — run in the normal `pytest` set; do NOT require RevenueCat.
2. **Gamma webhook smoke:** from RevenueCat, send a **test event** to the gamma webhook; assert
   `webhook_events` row created and (for a synthetic INITIAL_PURCHASE) sparks credited to a test wallet.
   A scripted variant: `curl -H "Authorization: Bearer $GAMMA_RC_SECRET" -d @sample_initial_purchase.json
   https://gamesapi-gamma.revelryapp.me/webhook/revenuecat` (sample body in `frontend/e2e/fixtures/`).
3. **iOS sandbox (gamma build):** build the iOS app pointing at gamma (`VITE_API_URL=gamesapi-gamma…` +
   RC keys), sign in with a Sandbox tester, buy a pack (e.g. `spark_pack_50`), confirm balance increments and a
   `token_transactions` purchase row appears. **Must be a bundled build, not live-reload** (webhooks need a
   publicly reachable server — VibePix lesson, `DEPLOY.md`).
4. **Android internal-testing build:** signed release build on the internal track, license tester buys
   a pack (free for testers), confirm credit. Emulator/debug builds won't transact.
5. **Idempotency/refund:** issue a sandbox refund (or re-send the webhook) → assert no double-credit and a
   single clawback debit.
6. **Platform guard:** assert native `X-Platform: android`/`ios` → `/checkout/create` returns 403; web → 200.
7. **Restore:** confirm restore is a clean no-op for consumed consumables and doesn't error.

---

## 10. Security considerations

- Webhook authenticated by a per-env bearer secret; auth failures logged with hashed IP (mirror Stripe).
- Spark amounts are **server-authoritative** (catalog lookup), never trusted from the webhook body.
- Double idempotency (event id + transaction-id reference) prevents replay/double-grant.
- `app_user_id` is the wallet id; a malicious client could in principle log in as another wallet id — but
  RC `app_user_id` is set from the device/session the same way the backend resolves the wallet, and crediting
  someone else's wallet only *gives them* sparks (no theft vector). Signed-in users are bound via the
  session-derived `user_id`.
- Keep the existing WS/HTTP rate limits; the webhook is exempt from per-device limits but bearer-gated.

---

## 11. Implementation order, rollout, and deploy steps

Implementation should land in this order so each step is testable:

1. **Backend catalog + guards:** add `SPARK_PRODUCTS`, block Android/iOS Stripe checkout, add SKU validation to
   `/checkout/create`, update Stripe cap logic, and cover with unit tests.
2. **RevenueCat webhook:** add `/webhook/revenuecat`, `_record_iap_entitlement`, idempotency/refund tests, and
   local curl fixtures. This can ship to gamma before any native UI is enabled.
3. **Frontend purchase surface:** add `SparkPurchaseModal`, web tier selection, shared platform helper, and tests
   for web/native branching with the RevenueCat module mocked.
4. **Native RevenueCat integration:** add plugin, `iap.ts`, app bootstrap, auth login/logout hooks, native restore,
   and native build env.
5. **Console setup + gamma smoke:** configure RevenueCat/store products and test webhooks, iOS sandbox, Android
   internal testing.
6. **Production rollout:** set prod secrets/webhooks, deploy backend/frontend, submit native builds, and archive the
   legacy Stripe price only after the three-tier web flow is live.

Deploy steps:

1. Land backend (`/webhook/revenuecat`, platform-guard fix, config, tests) + client (iap.ts, purchase wiring)
   on master.
2. Configure RevenueCat (gamma webhook + products + credentials) and store consoles (§7).
3. Set `REVENUECAT_WEBHOOK_SECRET` on **gamma**, deploy gamma (`./scripts/deploy-gcp.sh --gamma --with-frontend`).
4. Run the gamma webhook smoke + iOS sandbox + Android internal-testing tests (§9).
5. Set `REVENUECAT_WEBHOOK_SECRET` on **prod**, add the prod webhook in RevenueCat, deploy prod backend.
6. Submit the iOS app + IAP for App Store review; promote the Android build off Draft to a testing track,
   then production.
7. **Web Stripe:** no Stripe Products to create (inline `price_data`). Set `STRIPE_SECRET_KEY` +
   `STRIPE_WEBHOOK_SECRET` per env (test on gamma; live on prod, per `launch_feature_gaps.md`) and register
   one webhook endpoint per env. The legacy $0.99 single-price Product can be archived.
8. Record the deploy in `DEPLOY.md`.

---

## 12. File-change checklist (implementation)

Backend (DONE 2026-06-29):
- [x] `backend/config.py` — `SPARK_PRODUCTS` (incl. `price_cents`/`name`), `SPARK_PRODUCT_BY_ANY_ID`,
      `REVENUECAT_WEBHOOK_SECRET`, `MAX_SPARK_PACK`, `DEFAULT_SPARK_SKU` (no per-tier Stripe price env).
- [x] `backend/main.py` — `POST /webhook/revenuecat`; widen platform guard at `/checkout/create` to block `android` too.
- [x] `backend/main.py` — `/checkout/create` takes `sku`, resolves price+sparks from the catalog (§5.6);
      `/webhook/stripe` cap updated to `MAX_SPARK_PACK` (credit + refund paths).
- [x] `backend/main.py` — helper `_record_iap_entitlement(wallet_id, store, txn_id)` (games=0/`iap_consumed`,
      best-effort, swallows errors). Startup notices moved to `_check_payment_config()` (not secret-strength).
- [x] `backend/tests/test_iap_webhook.py` — 22 tests: webhook auth/idempotency/refund/unknown-product/amount-from-catalog,
      platform guard (ios+android), tiered `/checkout/create`, Stripe webhook cap. Full backend suite 937 passing.
- [x] (no schema migration — Supabase gamma/prod schema already matches.)

Frontend (DONE 2026-06-29):
- [x] `frontend/package.json` — `@revenuecat/purchases-capacitor@^12.3.2` installed; `iap.ts` loads it via a
      code-split dynamic import (lazy chunk, web never loads it at runtime).
- [x] `frontend/scripts/cap-build.mjs` + `npm run cap:sync:gamma|cap:sync:prod` — native build with baked
      API host + publishable RevenueCat/OAuth ids; `cap sync` registers RevenueCat (iOS SPM + Android Gradle).
- [x] `frontend/src/utils/socialAuth.ts` + `SettingsDrawer` — `SocialLogin.initialize()` for native sign-in (§6.7);
      iOS Google URL scheme added to `Info.plist`, and Apple Sign In entitlement added to `App.entitlements`.
      App version → 3.1.0 / build 5.
- [x] `frontend/src/utils/platform.ts` — shared `getPlatform()`/`isNativePlatform()`; `api.ts` now imports it.
      (`SettingsDrawer.tsx` keeps its local `isNativePlatform`; `analytics.ts` intentionally separate.)
- [x] `frontend/src/utils/iap.ts` — initIAP, iapLogIn/Out, getNativePrices, buySparksNative, restoreNative;
      offerings unwrap + rc/store/suffix product match; graceful no-op when plugin/keys absent.
- [x] `frontend/src/utils/sparkPacks.ts` — client catalog mirroring backend `SPARK_PRODUCTS`.
- [x] `frontend/src/components/SparkPurchaseModal.tsx` — 3 tiers, web checkout+poll / native buy+poll-balance,
      native price display, gating, loading/error states.
- [x] `frontend/src/pages/OrganizerPage.tsx` — ErrorModal upgrade path opens `SparkPurchaseModal`; removed the
      inline iOS-403 dead-end and the duplicated checkout poll.
- [x] `frontend/src/components/SettingsDrawer.tsx` — native `restoreNative()` before `/purchases/restore`.
- [x] `frontend/src/App.tsx` / `frontend/src/context/AuthContext.tsx` — `initIAP()` on mount; `iapLogIn/Out`
      on sign-in/out.
- [x] Tests: `platform.test.ts`, `sparkPacks.test.ts`, `SparkPurchaseModal.test.tsx`; full vitest 268 passing,
      tsc clean, web `vite build` clean (RevenueCat stays external).

Docs/config:
- [x] `DEPLOY.md` — §3c RevenueCat setup, native build env vars, plugin install, gamma+prod webhook URLs.
- [x] `SPEC.md` — cross-links this spec from the monetization section.
- [ ] `.env`/`.env.gamma` (GCP) — `REVENUECAT_WEBHOOK_SECRET`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` (per env). **Pending — needs Stripe/RevenueCat values.**

---

## 13. External setup decisions

1. **Catalog:** **RESOLVED** — all three surfaces (web Stripe + iOS + Android) use VibePix's tiers
   (50 / 200 / 500 @ $1.99 / $4.99 / $9.99) with identical SKUs/RC-ids to enable a future economy merge
   (§4.3). The legacy web pack (110 @ $0.99) is retired; web moves to the ladder via §5.6.
2. **RevenueCat project:** use the existing RevenueCat org, create a new LocalPlay/Revelry Games app/project unless
   RevenueCat support recommends a different structure.
3. **Apple IAP key:** generate a fresh In-App Purchase .p8 for Revelry Games; do not reuse the VibePix app-scoped key.
4. **Android off-Draft:** the Play app must reach at least internal testing before IAP can be tested.
5. **Ad reward on native:** out of scope; it must not block IAP implementation.

---

## Appendix A — RevenueCat webhook event fields used
`event.id`, `event.type` (`INITIAL_PURCHASE`/`NON_RENEWING_PURCHASE`/`REFUND`/`CANCELLATION`/`TEST`),
`event.app_user_id`, `event.product_id`, `event.store` (`APP_STORE`/`PLAY_STORE`), `event.transaction_id`,
and fallback `event.store_transaction_id`.

## Appendix B — Why no subscriptions
LocalPlay's economy is purely consumable Sparks spent per generation/room (`COST_GENERATE`, `COST_ROOM`).
VibePix layered subscriptions (`pro_monthly`/`pro_annual`) and entitlements (`no_watermark`) on top — LocalPlay
deliberately does not, so the webhook only handles consumable grants + clawbacks. Revisit if a "Revelry Pro"
tier is ever introduced (the schema's `subscriptions` concepts would need adding then).

## Appendix C — Direct-verification fallback (only if dropping RevenueCat)
- **Apple:** App Store Server Library (Python) to verify `signedTransactionInfo` JWS; subscribe to App Store
  Server Notifications V2. Requires the In-App Purchase .p8, issuer id, key id, bundle id.
- **Google:** `androidpublisher` (`purchases.products.get`) with the service-account JSON; consume/acknowledge
  the purchase token; subscribe to RTDN via Pub/Sub.
- New endpoint `POST /purchases/iap-complete` taking `{platform, product_id, transaction_id, receipt}` and
  fulfilling through the same `credit_purchase(reference_id=f"iap:{store}:{transaction_id}")` path. Strictly
  more code and key management than RevenueCat; only pursue if RevenueCat's revenue share or dependency becomes
  unacceptable.
