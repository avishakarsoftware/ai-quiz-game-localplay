---
name: Auth & Persistence Plan (Phase 2)
description: Sign-in (Apple/Google), cross-device premium, identity via provider subject ID
type: project
---

## Problem Statement

Phase 1 (monetization) ships device-locked payments with SQLite persistence. This works but has limitations:

1. **Device-locked purchases** — Party Pass is tied to `device_id` (UUID in localStorage/Keychain). Clear browser data, switch phones, or reinstall → purchase is orphaned. No recovery without user identity.
2. **No cross-device usage** — someone who pays on their laptop can't host from their phone.
3. **Free tier gaming** — clearing localStorage gives a fresh device ID, bypassing the 3-free-game limit. Acceptable for now, but sign-in closes this gap.
4. **No purchase history** — can't show "you have X remaining" across sessions reliably without identity.

Phase 2 adds federated auth to solve these. Phase 1 must be stable before starting.

**Cross-references:** This plan depends on Phase 1 infrastructure defined in `monetization_plan.md` — specifically the entitlement state machine, `GET /entitlements/current` endpoint, storage abstraction, request headers, and idempotency keys.

## Proposal: Federated Auth (Phase 2)

### 1. Identity: Provider Subject ID (NOT email)

Using email as primary identity is brittle — Apple Private Relay can change/hide emails, and users can have multiple emails.

**Correct approach:** Use the provider's **subject ID** (`sub` claim in the ID token) as the stable identity. The `sub` is a permanent, unique identifier that never changes for a given account.

```sql
CREATE TABLE users (
    id TEXT PRIMARY KEY,                    -- UUID (internal)
    provider TEXT NOT NULL,                 -- 'google' | 'apple'
    provider_subject_id TEXT NOT NULL,      -- sub claim from ID token (stable, unique per provider)
    email TEXT,                             -- for display only, NOT for lookup
    created_at INTEGER NOT NULL,            -- UTC epoch seconds
    UNIQUE(provider, provider_subject_id)   -- one user per provider identity
);
```

- User lookup: `WHERE provider = ? AND provider_subject_id = ?` (NOT by email)
- Email is stored for display/contact only — never used as a key
- If a user signs in with Google on one device and Apple on another, they are two separate users (acceptable — merging cross-provider identities is complex and not worth it at this stage)

### 2. Auth Flow

**Why both Apple + Google:** Apple requires "Sign in with Apple" if you offer any third-party sign-in (App Store Review Guideline 4.8). Google covers Android + web.

**Flow:**
1. Client gets an ID token from Apple/Google (native SDK or web library)
2. Client sends to `POST /auth/signin` with `{provider, id_token, device_id}`
3. Backend verifies token (see section 2a below)
4. Extract `sub` (subject ID) + email from verified token
5. `INSERT OR IGNORE` into users table (idempotent — same provider+sub = same user)
6. Return session JWT: `{user_id, device_id, exp}` (30-day expiry)
7. Client stores session JWT via storage abstraction (Keychain on iOS, Keystore on Android, localStorage on web)

**Backend endpoints:**
- `POST /auth/signin` — verify ID token, create/find user, merge entitlements, return session JWT
- `GET /auth/me` — return user profile (delegates to `GET /entitlements/current` for entitlement data)
- Sign-out is client-side only (clear JWT) — no server state to invalidate

### 2a. ID Token Verification (Security)

Token verification must check ALL of the following — not just signature:

**Google ID tokens:**
```python
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

claims = google_id_token.verify_oauth2_token(
    id_token,
    google_requests.Request(),
    audience=GOOGLE_CLIENT_ID  # aud check
)
# verify_oauth2_token already checks: sig, exp, iss, aud
assert claims["iss"] in ("accounts.google.com", "https://accounts.google.com")
sub = claims["sub"]
email = claims.get("email")
```

**Apple ID tokens:**
```python
import jwt
# 1. Fetch Apple's JWKS (cache for 24h)
jwks = httpx.get("https://appleid.apple.com/auth/keys").json()
# 2. Decode + verify
claims = jwt.decode(
    id_token,
    jwks,                           # sig check
    algorithms=["RS256"],
    audience=APPLE_CLIENT_ID,       # aud check
    issuer="https://appleid.apple.com",  # iss check
)
# 3. Additional checks
assert claims["exp"] > time.time()  # exp check (PyJWT does this, but be explicit)
# nonce check if we sent one during auth init:
if expected_nonce:
    assert claims.get("nonce") == expected_nonce
sub = claims["sub"]
email = claims.get("email")  # may be relay address or absent
```

**Required claim checks (both providers):**
| Claim | What it proves |
|-------|---------------|
| `sig` | Token wasn't tampered with |
| `aud` | Token was issued for our app (not another app reusing a stolen token) |
| `iss` | Token came from the expected provider |
| `exp` | Token hasn't expired |
| `nonce` | (optional) Prevents replay of intercepted tokens |

### 3. Free Tier: Cross-Device Logic

**Rules:**
- **Guest (no sign-in):** 3 free games per 24h per `device_id`. Each device is independent.
- **Signed-in user:** 3 free games per 24h per `user_id` (across ALL devices).

**Atomic free-usage increment (prevents race conditions):**

Concurrent requests from the same user on different devices could both read "2 used" and both increment to 3, allowing 4 games. Solution: atomic increment with a check in one statement.

```sql
-- Atomic: increment only if under limit, in a single statement
UPDATE device_usage
SET games_used_free = games_used_free + 1
WHERE user_id = ?
  AND window_start > unixepoch('now') - 86400
  AND (SELECT COALESCE(SUM(games_used_free), 0) FROM device_usage
       WHERE user_id = ? AND window_start > unixepoch('now') - 86400) < 3;

-- If rowcount == 0: either no row exists (insert one) or limit reached (return 402)
```

For guests (single device, simpler):
```sql
UPDATE device_usage
SET games_used_free = games_used_free + 1
WHERE device_id = ? AND user_id IS NULL
  AND window_start > unixepoch('now') - 86400
  AND games_used_free < 3;
```

SQLite serializes writes, so concurrent requests from the same user are handled correctly without explicit locks.

### 4. Entitlement Merge on Sign-In

When a user signs in on a device that has a guest entitlement:

```sql
-- Link orphaned entitlements from this device to the user
UPDATE entitlements SET user_id = ? WHERE device_id = ? AND user_id IS NULL;

-- Link device usage
UPDATE device_usage SET user_id = ? WHERE device_id = ? AND user_id IS NULL;
```

- One-time migration per device — afterwards `user_id` is authoritative
- If entitlement already has a `user_id` (from a different user), don't overwrite — that's a shared device scenario, not a merge

### 5. Entitlement Check Priority

When a generate request comes in (uses entitlement state machine from Phase 1):

```
1. Has session JWT (signed in)?
   -> Check entitlements WHERE user_id = ? AND status = 'active'
   -> If found: atomic decrement (with status transition), use premium model
   -> If not: atomic free-usage increment by user_id (SUM across devices)

2. No session JWT (guest)?
   -> Check entitlements WHERE device_id = ? AND user_id IS NULL AND status = 'active'
   -> If found: atomic decrement, use premium model
   -> If not: atomic free-usage increment by device_id only
```

Note: entitlement status `active` already implies `games_remaining > 0 AND expires_at > now` — the state machine (Phase 1) enforces transitions to `exhausted_games` or `expired_time`.

### 6. Transaction Safety

All entitlement operations use SQLite transactions with atomic SQL:

```python
async with db.transaction():
    # Atomic: check + decrement + status transition in one statement
    cursor = await db.execute(
        "UPDATE entitlements SET "
        "  games_remaining = games_remaining - 1, "
        "  status = CASE WHEN games_remaining - 1 = 0 THEN 'exhausted_games' ELSE status END "
        "WHERE id = ? AND status = 'active' AND games_remaining > 0 "
        "  AND expires_at > cast(strftime('%s', 'now') as integer)",
        (entitlement_id,)
    )
    if cursor.rowcount == 0:
        raise NoActiveEntitlement()
```

SQLite's default serialized mode means concurrent writes to the same DB file are serialized — no need for explicit row locks. This is fine for single-instance.

### 7. Restore/Reconcile Purchases (Cross-Device with Auth)

With sign-in, purchase restoration becomes reliable:

- **Signed-in user on new device:** Call `GET /entitlements/current` with session JWT -> server returns all entitlements for `user_id` -> no Apple/Google restore needed
- **Guest switching to signed-in:** Merge flow (section 4) links device entitlements to user -> available on all future devices
- **Native "Restore Purchases" button:** Still needed for App Store compliance. Calls Apple/Google SDK -> sends receipts to backend -> backend checks by `apple_transaction_id`/`google_order_id` -> if entitlement exists, links to current user. If user is signed in, this is redundant but harmless.
- **Reinstall (native, signed in):** Sign in -> `GET /entitlements/current` -> everything restored. Keychain (iOS) persists `device_id` across reinstalls so even guest entitlements may survive.
- **Reinstall (native, guest, no Keychain):** Fresh `device_id`. "Restore Purchases" is the only recovery path — sends Apple/Google receipts, server matches by transaction ID.

### 8. Frontend Changes

- **Settings/profile area:** "Sign In" button (Google/Apple) — non-blocking, always optional
- **Game counter:** "2 of 3 free games" or "47 games remaining" on prompt screen (data from `GET /entitlements/current`)
- **Post-purchase nudge:** "Sign in to keep your Party Pass across devices" (dismissible, shown once)
- **On sign-in:** call `GET /entitlements/current` -> merge entitlements -> update local state
- **Signed-in indicator:** small avatar/initial in header, "Signed in as..." in settings
- **"Restore Purchases" button:** In settings, visible on native apps only. Triggers Apple/Google SDK restore flow.
- **All tokens stored via storage abstraction** (Phase 1) — Keychain/Keystore on native, localStorage on web

**Frontend (web):**
- Google: `accounts.google.com/gsi/client` -> one-tap or button
- Apple: `appleid.auth.init()` via Apple JS SDK — show on Safari/iOS only

**Frontend (native apps via Capacitor):**
- `@capgo/capacitor-social-login` or equivalent
- Both return ID tokens that go through the same `POST /auth/signin`

### 9. Payment Idempotency (Applies to Phase 1 + 2)

All payment processors use UNIQUE constraints (columns added in Phase 1 schema):
```sql
CREATE UNIQUE INDEX idx_entitlements_stripe ON entitlements(stripe_session_id) WHERE stripe_session_id IS NOT NULL;
CREATE UNIQUE INDEX idx_entitlements_apple ON entitlements(apple_transaction_id) WHERE apple_transaction_id IS NOT NULL;
CREATE UNIQUE INDEX idx_entitlements_google ON entitlements(google_order_id) WHERE google_order_id IS NOT NULL;
```

- Stripe: verify webhook signature + reject timestamps > 5min old
- Apple: verify receipt with Apple's `/verifyReceipt` endpoint, use `transaction_id` as key
- Google: verify purchase token with Google Play Developer API, use `orderId` as key
- All use `INSERT OR IGNORE` — duplicate payment ID = no-op

### Implementation Order (Phase 2)
1. `POST /auth/signin` + Google ID token verification (with full claim checks: sig, aud, iss, exp)
2. Apple ID token verification (JWKS + aud/iss/exp/nonce)
3. Users table + provider subject ID lookup
4. Entitlement merge on sign-in
5. Cross-device free limit with atomic increment (SUM by user_id)
6. "Restore Purchases" backend endpoint (match by transaction ID, link to user)
7. Frontend: Google Sign-In (web) — test first
8. Frontend: sign-in UI + game counter + "Restore Purchases" button (native only)
9. Frontend: Apple Sign-In (web + Capacitor)
10. Capacitor: Google Sign-In plugin
11. Support tooling (admin lookup/revoke/grant endpoints)
12. Tests

### Prerequisites
- Phase 1 (SQLite + payments + entitlement state machine + storage abstraction) must be stable and deployed
- Stripe test mode fully working
- Google OAuth client ID configured (Google Cloud Console)
- Apple Sign-In configured (Apple Developer Portal -> Certificates, Identifiers & Profiles)
- Admin API key set for support tooling endpoints
