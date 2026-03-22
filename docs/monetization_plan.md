---
name: Monetization Plan
description: $2.99/12h party pass (50 games), device tracking, SQLite from day 1, Stripe + IAP
type: project
---

## Monetization: $2.99 / 12-Hour Party Pass (50 games)

**Model:** 3 free game generations per 24h, then paywall. Payment unlocks 50 games for 12 hours (whichever runs out first) + better AI model (Gemini 2.5 Flash).

### Architecture

**SQLite from day 1.** The earlier "no-DB" approach is not viable for paid users — a server restart or deploy would wipe entitlements, creating support pain. SQLite on the GCP VM (Docker volume mount) solves this at zero cost.

**Time storage:** All timestamps stored as UTC epoch integers (`int(time.time())`). No ISO strings, no timezone ambiguity. Python `time.time()` and SQLite integer comparison are both UTC-native. This applies to `expires_at`, `window_start`, `created_at` everywhere.

**1. Device ID & Token Storage Abstraction (Frontend)**
- Generate UUID on first visit, send as header (`X-Device-Id`) with every generate request
- **Storage abstraction layer** — web uses `localStorage`, native apps use platform secure storage:
  - iOS: Keychain (via `@capacitor-community/secure-storage`)
  - Android: Keystore (via same plugin)
  - Web: `localStorage` (fallback)
- All token/ID reads go through a `storage.get(key)` / `storage.set(key, value)` wrapper
- This prevents tokens from being wiped on app updates (Keychain persists across reinstalls on iOS) and keeps secrets out of plaintext storage on mobile
- Keys stored: `revelry_device_id`, `revelry_premium_token`, `revelry_session_token`, `checkout_pending`

**2. Backend Usage Tracking (SQLite)**
- `device_usage` table: `device_id`, `user_id` (nullable), `games_used_free`, `window_start` (UTC epoch int)
- On generate request: check count in current 24h window
- If count >= 3 and no valid entitlement → return HTTP 402
- Window resets after 24h from `window_start`

**3. Entitlements (SQLite)**

**State machine:** Every entitlement has an explicit status. This avoids ambiguity around edge cases.

```
                    ┌─────────────┐
  payment confirmed │             │ games_remaining hits 0
  ─────────────────►│   active    ├──────────────────────►  exhausted_games
                    │             │
                    └──────┬──────┘
                           │ expires_at passes
                           ▼
                     expired_time

  pending_payment ──► active (on webhook)
                  └─► expired_time (if webhook never arrives after 1h)

  active / exhausted / expired ──► revoked_refunded (on refund/chargeback)
```

| Status | Meaning | Can generate? |
|--------|---------|--------------|
| `pending_payment` | Checkout started, webhook not yet received | No |
| `active` | Paid, games remaining, not expired | Yes |
| `exhausted_games` | Paid, 0 games remaining, time not expired | No |
| `expired_time` | Paid, time expired (regardless of games left) | No |
| `revoked_refunded` | Refund/chargeback processed | No |

```sql
CREATE TABLE entitlements (
    id TEXT PRIMARY KEY,
    user_id TEXT,                          -- nullable (guest purchases)
    device_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending_payment',  -- state machine
    games_remaining INTEGER NOT NULL DEFAULT 50,
    expires_at INTEGER NOT NULL,           -- UTC epoch seconds
    stripe_session_id TEXT,                -- web payments
    apple_transaction_id TEXT,             -- iOS IAP
    google_order_id TEXT,                  -- Android Play Billing
    created_at INTEGER NOT NULL            -- UTC epoch seconds
);

CREATE UNIQUE INDEX idx_entitlements_stripe ON entitlements(stripe_session_id) WHERE stripe_session_id IS NOT NULL;
CREATE UNIQUE INDEX idx_entitlements_apple ON entitlements(apple_transaction_id) WHERE apple_transaction_id IS NOT NULL;
CREATE UNIQUE INDEX idx_entitlements_google ON entitlements(google_order_id) WHERE google_order_id IS NOT NULL;
```

- On successful generation: `UPDATE entitlements SET games_remaining = games_remaining - 1, status = CASE WHEN games_remaining - 1 = 0 THEN 'exhausted_games' ELSE status END WHERE id = ? AND status = 'active' AND games_remaining > 0`
- Status transitions enforced in SQL (only `active` → `exhausted_games` on decrement, etc.)
- Apple/Google ID columns are nullable and unused in Phase 1 — present in schema to avoid migration later

**4. Generate Request Idempotency**

Mobile apps on flaky networks may retry generate requests. Without idempotency, a retry could double-decrement the free or premium game counter.

- Client generates an idempotency key (UUID) per generate attempt, sent as `X-Idempotency-Key` header
- Backend stores recent keys in a `request_log` table (or in-memory with TTL):
  ```sql
  CREATE TABLE request_log (
      idempotency_key TEXT PRIMARY KEY,
      device_id TEXT NOT NULL,
      result_id TEXT,          -- quiz_id or scenario_id
      created_at INTEGER NOT NULL
  );
  ```
- On generate request: check if key exists → if so, return cached result (no decrement, no LLM call)
- TTL: 1 hour (cleanup old entries periodically)
- This also protects against the "user double-taps generate" bug

**5. Premium Token: Signed JWT (cache layer over DB)**
- JWT contains `{device_id, user_id?, entitlement_id, exp, tier, games_remaining}`
- `games_remaining` is a snapshot for client display — **backend always checks DB** as source of truth
- JWT is a fast-path check; DB is authoritative

**6. Authoritative Entitlement Sync Endpoint**

Single source of truth for the client on app launch and foreground resume:

```
GET /entitlements/current
Headers: X-Device-Id, Authorization (optional session + premium tokens)
Response: {
    "premium": true/false,
    "status": "active" | "exhausted_games" | "expired_time" | null,
    "games_remaining": 47,      // -1 if premium without limit (future)
    "expires_at": 1711036800,   // UTC epoch, null if no entitlement
    "free_games_used": 2,
    "free_games_limit": 3,
    "pending_purchase": false   // true if checkout started but not confirmed
}
```

- Called on: app launch, foreground resume (mobile), after sign-in, after purchase
- Replaces scattered premium status checks with one endpoint
- Client updates local state from this response

**7. Paywall UI (Frontend)**
- When backend returns 402, show upgrade prompt
- Pricing pulled from `config.json` remote config (changeable without redeploy)
- `feature_flags.show_upgrade_button` gates visibility
- Message: "Works on this device only — sign in to use across devices"

**8. Payment Flow**

**iOS compliance rule:** The iOS app MUST use Apple IAP only — no Stripe purchase path inside the native app. Stripe is for web browsers only. This is an App Store rejection risk if violated (Apple Review Guideline 3.1.1). The frontend must detect native context (`Capacitor.isNativePlatform()`) and route to IAP instead of Stripe.

- **Web only (Stripe Checkout):**
  - `POST /checkout/create` → Stripe hosted page → webhook confirms → entitlement activated in DB → client polls `GET /checkout/token` for JWT
  - Token is NOT returned via redirect URL (avoids leakage in browser history/logs)
  - Client polls every 2s for up to 60s after Stripe redirect
  - **Deep-link return flow:** Stripe `success_url` uses a universal link (`https://games.revelryapp.me/quiz/?checkout=success&session_id=xxx`) so mobile browsers return to the app. Web just loads the page with the query param.
- **iOS (Apple IAP only):** receipt → `POST /purchase/validate-apple` → verify with Apple → create entitlement
- **Android (Google Play Billing):** purchase token → `POST /purchase/validate-google` → verify with Google → create entitlement

**9. `/checkout/token` Polling Contract**
- **One-time retrieval:** Token is deleted from pending store on first successful GET. Second call returns 404.
- **Short TTL:** Pending tokens expire after 5 minutes. Background cleanup removes stale entries.
- **Bound to device:** Request must include `device_id` query param. Token is only returned if it matches the `device_id` the checkout was created for.
- **Not guessable:** Tokens are keyed by `device_id` (UUID) — cannot be enumerated.
- **Fallback for delayed webhooks ("resume purchase"):** If 60s poll misses (webhook arrives late), the client stores `checkout_pending: true` + `stripe_session_id` in secure storage. On next app launch/foreground resume, it calls `GET /entitlements/current` which checks for any `pending_payment` entitlements and reconciles with Stripe if needed (`stripe.checkout.Session.retrieve()`). This catches purchases where the webhook was slow or the user closed the browser.

**10. Webhook Idempotency & Replay Protection**
- UNIQUE constraints on `stripe_session_id`, `apple_transaction_id`, `google_order_id` (all in schema from day 1)
- On webhook: `INSERT OR IGNORE` / check existing → if payment ID already exists, skip (idempotent)
- Verify Stripe webhook signature (`stripe.Webhook.construct_event`)
- Reject webhooks with timestamps older than 5 minutes (replay protection)

**11. Refund & Chargeback Hooks**

Model revocation now, even if manual at first:

- Entitlement status: `active` → `revoked_refunded`
- **Stripe:** Register `charge.refunded` and `charge.dispute.created` webhook events. On receipt, look up entitlement by `stripe_session_id`, set status to `revoked_refunded`.
- **Apple/Google:** Manual for now. Admin endpoint `POST /admin/revoke?entitlement_id=xxx` sets status.
- Client sees revocation on next `GET /entitlements/current` call — premium features stop working.
- No need to invalidate JWT — the DB check on generate will reject it.

**12. Restore/Reconcile Purchases (Reinstall/New Device)**

For native apps, users expect "Restore Purchases" to work:

- **Apple:** Client calls `SKPaymentQueue.restoreCompletedTransactions()` → gets receipts → sends to `POST /purchase/validate-apple` → backend checks `apple_transaction_id` in DB → if found, returns existing entitlement (or links to current device/user)
- **Google:** Client calls `BillingClient.queryPurchaseHistoryAsync()` → sends tokens → same pattern
- Backend logic: if entitlement exists for this transaction ID, update `device_id` to current device (if user is signed in) or return it as-is
- This is critical for App Store review — Apple tests "Restore Purchases" during review

**13. Request Headers for Platform Tracking**

All API requests include:
```
X-Device-Id: <uuid>
X-Platform: web | ios | android
X-App-Version: 1.2.0
X-Build: 42
X-Idempotency-Key: <uuid>  (generate requests only)
```

- Set in a shared fetch wrapper / interceptor
- Backend logs these for analytics and debugging
- Enables: rollout controls (feature flags by platform/version), backward-compat handling (old app versions get different behavior), and per-platform error tracking
- `X-Platform` also used to enforce iOS IAP-only rule server-side: if `X-Platform: ios` and request hits `/checkout/create`, return 403

**14. Remote Config Emergency Kill Switches**

Current 24h cache TTL is too long for urgent incidents. Add:

- `config.json` gains `cache_ttl_seconds` field (default: 86400, can be lowered to 300 for incidents)
- New `operations` flags:
  ```json
  {
    "operations": {
      "maintenance": false,
      "maintenance_message": "...",
      "kill_generate": false,
      "kill_payments": false,
      "force_config_refresh": false
    }
  }
  ```
- `kill_generate`: frontend disables generate buttons, shows message (no backend call needed)
- `kill_payments`: frontend hides upgrade button (prevents purchases during payment issues)
- `force_config_refresh`: client ignores cache, fetches fresh config immediately
- **Foreground refresh:** On mobile, re-fetch config on every foreground resume (not just on launch). On web, re-fetch on visibility change (`document.visibilityState === 'visible'`). Respects `cache_ttl_seconds` — won't fetch more than once per TTL unless `force_config_refresh` is set.

**15. Model Upgrade for Paid Users**
- Free: `gemma-3-27b-it` (current default via Gemini API)
- Paid: `gemini-2.5-flash` — noticeably better quality, cheap (~$0.15/1M input tokens)
- Backend checks active entitlement → selects model accordingly

**16. WebSocket Disconnect Grace Periods**

Mobile backgrounding pauses WebSocket connections. Current behavior may kick players too aggressively.

- Make heartbeat/disconnect timeouts configurable per platform:
  ```python
  WS_HEARTBEAT_TIMEOUT = {
      "web": 15,       # seconds — tabs are reliably connected
      "ios": 45,       # iOS suspends apps quickly, needs more grace
      "android": 30,   # Android is more lenient but still backgrounds
  }
  ```
- Client sends `X-Platform` on WebSocket connect (as query param or first message)
- Server uses platform-appropriate timeout for that connection
- On reconnect, existing session restoration logic already handles the gap

### Implementation Order (Phase 1 — ship payments)
1. `backend/db.py` — SQLite schema (entitlements with status + all 3 payment ID columns + request_log)
2. Storage abstraction (`frontend/src/utils/storage.ts`) — web localStorage / native Keychain
3. Migrate `premium.py` from in-memory to SQLite (device_usage + entitlements)
4. Entitlement state machine (status transitions in SQL)
5. Generate request idempotency (`X-Idempotency-Key` + request_log table)
6. `GET /entitlements/current` — authoritative sync endpoint
7. Stripe webhook with idempotency (UNIQUE on stripe_session_id)
8. Harden `/checkout/token` — one-time retrieval, 5min TTL, device binding
9. "Resume purchase" flow (pending entitlement reconciliation on launch)
10. Refund webhook handler (Stripe `charge.refunded` → revoked status)
11. Request headers (`X-Platform`, `X-App-Version`, `X-Build`, `X-Idempotency-Key`)
12. Platform detection — route iOS to IAP, web to Stripe (enforce server-side too)
13. Remote config: emergency kill switches + foreground refresh + configurable cache TTL
14. WS disconnect grace periods by platform
15. Paywall UI with remote config pricing
16. Model selection based on active entitlement
17. Docker volume mount for SQLite persistence
18. Tests

### Phase 2 Additions (support tooling — before native launch)
- `GET /admin/lookup?device_id=xxx` — find entitlements, usage, user by device
- `GET /admin/lookup?transaction_id=xxx` — find entitlement by any payment ID
- `GET /admin/lookup?user_id=xxx` — full user profile + all entitlements
- `POST /admin/revoke?entitlement_id=xxx` — manual revocation
- `POST /admin/grant?device_id=xxx&games=50&hours=12` — manual grant (for support/testing)
- Protected by admin API key (not user-facing)
- Build before native app launch to reduce ops pain

### Edge Cases
- **Server restart:** SQLite persists via Docker volume — no data loss
- **Concurrent requests:** Atomic SQL decrement prevents double-spend
- **Flaky mobile retries:** Idempotency keys on generate requests prevent double-decrement
- **Webhook replay:** UNIQUE constraint on payment session ID + timestamp check
- **Token leakage:** Token never in URL params or redirect — only via polling endpoint, one-time retrieval
- **Failed generations:** Do NOT decrement game count — only on success
- **Expired entitlement with games left:** Status → `expired_time`. Both time AND count must be valid.
- **0 games but time remaining:** Status → `exhausted_games`. Clear to user what happened.
- **localStorage cleared (guest):** On mobile, Keychain persists across reinstalls. On web, entitlement orphaned — recovery via sign-in (Phase 2).
- **Delayed webhook:** "Resume purchase" via `GET /entitlements/current` on next launch
- **iOS purchase via Stripe:** Blocked client-side (platform detection) AND server-side (`X-Platform: ios` + `/checkout/create` = 403)
- **Timezone bugs:** All timestamps are UTC epoch integers
- **Refunds:** Webhook-driven status change to `revoked_refunded`; admin endpoint for manual cases
- **App reinstall (native):** "Restore Purchases" flow queries Apple/Google, reconciles with server
- **Urgent incident:** Remote config kill switches + foreground refresh override 24h cache
