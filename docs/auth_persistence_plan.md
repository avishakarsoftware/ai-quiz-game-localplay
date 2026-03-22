---
name: Auth & Persistence Plan
description: Sign-in (Apple/Google), SQLite database, cross-device premium, 50-game Party Pass tracking
type: project
---

## Problem Statement

Revelry currently has no database and no user accounts. Everything is in-memory dicts — quizzes, rooms, players, rate limits, premium tokens. This means:

1. **Server restart wipes everything** — a deploy or crash resets all rate limits and premium status. Someone who paid $2.99 loses their Party Pass.
2. **No game count tracking** — the Party Pass is time-based only (12h JWT). To enforce a 50-game limit, we need persistent state that survives restarts.
3. **Device-locked purchases** — the Party Pass JWT is tied to a `device_id` (UUID in localStorage). Clear the browser, switch phones, or use a different device → you lose your purchase. No way to recover without sign-in.
4. **No user identity** — can't offer cross-device usage, purchase history, or account recovery. The "sign in to use across devices" messaging currently has no implementation behind it.

## Proposal: SQLite + Federated Auth

### 1. SQLite Database (on GCP VM)

Single file (`~/app/revelry.db`), persisted via Docker volume mount. No extra services, no cost. Python `sqlite3` is built-in — no new dependencies for basic access (or use `aiosqlite` for async).

**Schema:**
```sql
CREATE TABLE users (
    id TEXT PRIMARY KEY,           -- UUID
    email TEXT UNIQUE NOT NULL,
    provider TEXT NOT NULL,        -- 'google' | 'apple'
    created_at TEXT NOT NULL       -- ISO timestamp
);

CREATE TABLE entitlements (
    id TEXT PRIMARY KEY,           -- UUID
    user_id TEXT,                  -- nullable (guest purchases)
    device_id TEXT,                -- always present
    games_remaining INTEGER NOT NULL DEFAULT 50,
    expires_at TEXT NOT NULL,      -- ISO timestamp
    stripe_session_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE device_usage (
    device_id TEXT PRIMARY KEY,
    user_id TEXT,                  -- linked after sign-in
    games_used_free INTEGER NOT NULL DEFAULT 0,
    window_start TEXT NOT NULL,    -- ISO timestamp, reset every 24h
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

**Why SQLite over Supabase/Cloud SQL:**
- Zero cost, zero setup, zero network latency
- Single-instance is fine — the generate endpoints all hit one server (room-sharding doesn't change this since game generation isn't sharded)
- If/when we need multi-instance, migrate to Postgres — the schema is simple enough that this is a one-time effort

**Docker change:**
```bash
docker run -d --name games-backend --env-file .env \
  -p 8000:8000 \
  -v ~/app/data:/app/data \        # <-- persist SQLite
  --restart unless-stopped revelry-backend
```
Database file lives at `/app/data/revelry.db` inside the container, backed by `~/app/data/` on the host.

### 2. Auth: Sign in with Apple + Google

**Why both:** Apple requires "Sign in with Apple" if you offer any third-party sign-in (App Store Review Guideline 4.8). Google covers Android + web.

**Flow:**
1. Client gets an ID token from Apple/Google (native SDK or web library)
2. Client sends token to `POST /auth/signin` with `{provider, id_token, device_id}`
3. Backend verifies token with Apple/Google's public keys
4. Creates or finds user by email
5. Returns session JWT: `{user_id, device_id, email, exp}`
6. Client stores session JWT alongside premium token

**Backend endpoints:**
- `POST /auth/signin` — verify ID token, create/find user, return session JWT
- `GET /auth/me` — return user profile + entitlements (for re-sync on app launch)
- `POST /auth/signout` — client-side only (just clear JWT), no server state

**Libraries:**
- `PyJWT` (already installed) for session JWTs
- `google-auth` for verifying Google ID tokens
- Apple ID token verification: decode JWT + verify against Apple's JWKS endpoint (no special library needed)

**Frontend (web):**
- Google: `accounts.google.com/gsi/client` script → `google.accounts.id.initialize()` → one-tap or button
- Apple: `appleid.auth.init()` via Apple JS SDK — only show on Safari/iOS (Apple requires it, but not useful on Chrome/Android)

**Frontend (native apps via Capacitor):**
- `@capgo/capacitor-social-login` or `@codetrix-studio/capacitor-google-auth` + `@capacitor-community/apple-sign-in`
- Both return ID tokens that go through the same `POST /auth/signin` backend endpoint

### 3. Entitlement Logic

**Guest (no sign-in):**
- 3 free games per 24h per device (current behavior, now tracked in SQLite instead of in-memory)
- Party Pass purchase → entitlement row with `device_id` only, `user_id = NULL`
- 50 games + 12h expiry, whichever comes first

**Signed-in user:**
- 3 free games per 24h per user (not per device) — tracked in `device_usage` by `user_id`
- Party Pass → entitlement row with `user_id` — works on any device
- Same 50 games + 12h expiry

**Merge on sign-in:**
- When user signs in, find any `entitlements` or `device_usage` rows with matching `device_id` and `user_id = NULL`
- Link them to the user: set `user_id` on those rows
- This is a one-time migration per device — afterwards the `user_id` is authoritative

**Game count decrement:**
- On successful generation: find active entitlement (not expired, `games_remaining > 0`), decrement `games_remaining`
- If no active entitlement: check free tier limit in `device_usage`
- If over free limit: return 402

### 4. JWT Changes

**Current:** `{device_id, exp, tier}` (premium token, 12h)

**New premium token:** `{device_id, user_id?, entitlement_id, exp, tier, games_remaining}`
- `games_remaining` is a snapshot for client display — backend always checks DB
- `user_id` present if signed in, absent for guest purchases

**New session token (for auth):** `{user_id, email, device_id, exp}`
- Longer-lived (30 days), refreshed on app launch via `GET /auth/me`
- Separate from premium token — you can be signed in without a Party Pass

### 5. Frontend Changes

- **Settings/profile area:** "Sign In" button (Google/Apple) — non-blocking, users can always play as guest
- **Game counter:** "2 of 3 free games used" or "47 games remaining" — shown on prompt screen
- **Post-purchase nudge:** "Sign in to keep your Party Pass across devices" (dismissible)
- **On sign-in:** re-fetch `GET /auth/me` to merge entitlements, update local state

### Implementation Order

1. `backend/db.py` — SQLite schema init, connection helper, async wrapper
2. Migrate `premium.py` from in-memory dicts to SQLite (device_usage + entitlements tables)
3. Auth endpoints (`POST /auth/signin`, `GET /auth/me`) — Google ID token verification first
4. Apple ID token verification
5. Entitlement merge on sign-in
6. Game count decrement on generation (time + count enforcement)
7. Docker volume mount for SQLite persistence
8. Frontend: Google Sign-In (web) — easiest to test first
9. Frontend: sign-in UI + game counter display
10. Frontend: Apple Sign-In (web + Capacitor)
11. Capacitor: Google Sign-In plugin for Android app
12. Tests

### Edge Cases

- **Server restart:** SQLite persists — no data loss
- **Expired entitlement with games left:** Both time AND count must be valid. Expired = done, even if games remain.
- **Multiple active entitlements:** Use the one expiring soonest (FIFO). If they buy again before expiry, create a new row — don't extend the old one.
- **localStorage cleared (guest):** Device ID gone, entitlement orphaned. If they sign in, they can recover via `user_id`. If not, it's lost — same as clearing app data.
- **Refunds:** For $2.99 at this scale, not worth building automated revocation. Handle manually if needed.
