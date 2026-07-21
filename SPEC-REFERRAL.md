# SPEC-REFERRAL — Invite / referral rewards

Status: **Live on gamma + prod** (activated 2026-07-21; works on SQLite locally without the flag).
See DEPLOY.md's env-status ledger for authoritative live status.
Owner: Avi
Related: `SPEC.md` (spark economy), `SPEC-GIFTING.md` (shares the friend-code + idempotency pattern), `backend/db.py`, `SPEC-ANALYTICS.md`

---

## 0. Goal

A viral growth loop: every wallet gets a shareable **referral code**. When a new player redeems a code,
**both** the referrer and the referee get Sparks. Reuses the wallet + `token_transactions` idempotency
model (mirrors `credit_purchase`). One-time per referee, self-referral blocked, per-day cap on the referrer.

## 1. Economics (env-tunable)

| Var | Default | Meaning |
|---|---|---|
| `REFERRAL_REWARD` | 20 | Sparks credited to **each** party on a successful redeem |
| `MAX_REFERRALS_PER_DAY` | 10 | Cap on how many referees one referrer can be rewarded for per UTC day (anti-farm) |

Both credited at `reason='referral_reward'`, capped at `MAX_TOKEN_BALANCE`.

## 2. Data model

Add to `wallets` (try/except `ALTER TABLE ADD COLUMN`, SQLite + Supabase parity):
- `referral_code TEXT` — the wallet's own code, generated lazily; **unique** (enforce via a unique index
  `CREATE UNIQUE INDEX IF NOT EXISTS idx_wallets_referral_code ON wallets(referral_code) WHERE referral_code IS NOT NULL`).
- `referred_by TEXT` — the referrer's wallet_id; NULL until this wallet redeems a code (one-time gate).

Code format: 6 chars, unambiguous alphabet (no `0/O/1/I/L`), uppercase, e.g. `R7K9QX`. Generate with
retry-on-collision (a handful of attempts).

## 3. Endpoints

### `GET /referral/code`
Resolve wallet (`tokens.get_wallet_id`; require device id / session). Lazily create + persist the wallet's
`referral_code`. Return `{code, share_url}` where `share_url` = a deep/web link carrying the code (e.g.
`${WEB_URL}/?ref=CODE`, host from config; see SPEC-SHARE-CARD for the base). Idempotent — same code each call.

### `POST /referral/redeem` `{code}`
1. Resolve `referee` wallet (must exist / be creatable). Normalize `code` (uppercase, strip).
2. Look up `referrer` by `referral_code == code`. Not found → `404 invalid code`.
3. **Guards:** `referrer != referee` (self-referral → 400); `referee.referred_by` must be NULL (already
   redeemed → 409); referrer's referral count *today* < `MAX_REFERRALS_PER_DAY` (else 429, and **do not**
   set `referred_by` so the referee can retry with a different valid code — log it).
4. In one `BEGIN IMMEDIATE` txn: set `referee.referred_by = referrer_id`; credit both via the idempotent
   path with `reference_id = f"referral:{referrer_id}:{referee_id}"` (reason `referral_reward`). Idempotency
   check mirrors `credit_purchase` (skip if that reference already credited).
5. Return `{redeemed: true, reward: REFERRAL_REWARD, new_balance}`.

**New db functions:** `get_or_create_referral_code(wallet_id) -> str`, `redeem_referral(referee_id, code)
-> dict`, plus a `count_referrals_today(referrer_id) -> int` (COUNT distinct referees credited today).

## 4. Frontend

- `SettingsDrawer`: "Invite friends — you both get N sparks" → shows the code + a **Share** button
  (reuse the `@capacitor/share` / `navigator.share` pattern already in `LobbyScreen`) and a **Redeem a code**
  input.
- The referral UI is hidden unless remote config says `feature_flags.referral_enabled === true` (backend derives
  this from `_REFERRALS_SUPPORTED` on `/config/public`). Static/default config stays `false`; Supabase deployments
  expose it only after the referral SQL/RPCs are applied and `REFERRALS_ENABLED=true` is set. **Both were done on
  gamma + prod 2026-07-21, so referrals are live in all environments.**
- On app open, if URL has `?ref=CODE` and this wallet hasn't redeemed, prompt/auto-fill the redeem field
  (don't auto-submit — show the user what they're claiming).
- On redeem success, toast "+N sparks", refresh balance, fire `referral_redeemed`.

## 5. Abuse considerations (v1, documented)

- Device-id wallets make Sybil farming possible in theory; mitigations: one-time per referee (`referred_by`),
  per-day referrer cap, and (future) gate rewards on the referee having signed in or completed a game.
  v1 accepts the residual risk with the daily cap; logged as a known limitation.

## 6. Testing (`backend/tests/test_referral.py`)
- code is stable + unique per wallet; redeem credits both once; self-referral blocked; double-redeem by same
  referee blocked (409) and no double credit; unknown code 404; daily cap enforced (429) without setting
  `referred_by`; idempotent on the reference_id (replayed redeem doesn't double-credit).

## 7. Files touched
- `backend/config.py` (REFERRAL_REWARD, MAX_REFERRALS_PER_DAY), `backend/db.py` (migration + 3 fns),
  `backend/supabase_db.py` (+ migration/parity), `backend/main.py` (2 endpoints), `backend/tests/test_referral.py`.
- Frontend: `SettingsDrawer` (code/share/redeem UI), `App`/router (`?ref=` capture), balance refresh.
