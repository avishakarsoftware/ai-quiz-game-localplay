# SPEC-GIFTING — Spark gifting (wallet → wallet)

Status: **Deployed 2026-07-26. Migrations applied to BOTH Supabase prefixes. Live + smoke-verified on
gamma (`GIFTING_ENABLED=true`); prod schema is ready but the flag is still OFF.** Activation runbook in
§5; live status tracked in DEPLOY.md's env-status ledger (authoritative — don't restate it here).

Migration order is load-bearing: `…040000_gifting_idempotency_replay` **replaces** the `gift_sparks`
body created by `…010000_gifting`. Out of order leaves the old replay semantics silently in place.
Verify after applying: exactly one `gift_sparks/10` overload per prefix in `pg_proc`.
Owner: Avi
Related: `SPEC-REFERRAL.md` (shared friend-code/idempotency pattern), `SPEC.md` (spark economy), `SPEC-ANALYTICS.md`

---

## 0. Goal

Let a player send N sparks to a friend. A directed transfer — one atomic **debit-then-credit** in a
single transaction — addressed by the recipient's **friend code** (their referral code, reused as a
public handle; no wallet ids exposed). Idempotent on a client-supplied key so a retried request never
double-sends. Reuses the wallet + `token_transactions` model and the `SPEC-REFERRAL` activation gate.

## 1. Economics (env-tunable)

| Var | Default | Meaning |
|---|---|---|
| `GIFT_MIN_AMOUNT` | 1 | Smallest gift |
| `GIFT_MAX_AMOUNT` | 100 | Per-gift ceiling |
| `MAX_GIFTS_PER_DAY` | 20 | Per-sender count cap per UTC day (anti-farm) |
| `MAX_GIFT_TOKENS_PER_DAY` | 200 | Per-sender total-sparks cap per UTC day |
| `GIFTING_ENABLED` | false | Supabase gate (like `REFERRALS_ENABLED`); SQLite works without it |

Debit at `reason='gift_sent'` (negative amount), credit at `reason='gift_received'`, recipient capped
at `MAX_TOKEN_BALANCE`.

## 2. Data model

No new columns. The recipient is looked up by the existing `wallets.referral_code` (SPEC-REFERRAL), so
gifting depends on the referral migration being applied first. Both transaction legs share a
`reference_id = f"gift:{sender_id}:{key}"` when a client idempotency key is supplied.

## 3. Conservation & guards

`gift_sparks(sender_id, recipient_code, amount, idempotency_key) -> dict`, status ∈
`{ok, invalid_amount, invalid_code, self_gift, insufficient, recipient_full, daily_cap}`:

1. `GIFT_MIN_AMOUNT ≤ amount ≤ GIFT_MAX_AMOUNT` (else `invalid_amount`).
2. Look up recipient by `referral_code` (uppercased/trimmed); not found → `invalid_code`.
3. `recipient != sender` (else `self_gift`).
4. **Idempotency:** a prior `gift_sent` row with the same sender/key `reference_id` replays its original
   result (`{status: ok, duplicate: true, …}`) before recipient/balance/cap checks — nothing moves. The
   replayed `amount` and `recipient_id` must come from the stored transaction, not the retry body, so a
   changed retry payload cannot misreport what actually moved or who received it.
5. Sender balance ≥ amount (else `insufficient`).
6. Per-sender daily caps: `COUNT(gift_sent today) < MAX_GIFTS_PER_DAY` **and**
   `SUM(sent today) + amount ≤ MAX_GIFT_TOKENS_PER_DAY` (else `daily_cap`).
7. **Conserve sparks:** if `recipient_balance + amount > MAX_TOKEN_BALANCE`, reject `recipient_full`
   **without debiting** — a gift is never partially destroyed at the recipient's cap.
8. In one `BEGIN IMMEDIATE` txn: debit sender, credit recipient, write both txn rows.

## 4. Endpoint

### `POST /tokens/gift` `{code, amount, idempotency_key}`
Gated by `_GIFTING_SUPPORTED` (`DB_BACKEND != supabase OR GIFTING_ENABLED`) → 503 when off. Rate-limited
per IP. Resolve sender via `tokens.get_wallet_id` (device id / session). Maps status → HTTP:
`invalid_amount`/`self_gift`→400, `invalid_code`→404, `insufficient`→402, `recipient_full`→409,
`daily_cap`→429. Success → `{sent: true, amount, new_balance, duplicate}`. Emits `spark_sent`
(sender) + `spark_received` (recipient) analytics, skipped on a duplicate replay.

`/config/public` exposes `feature_flags.gifting_enabled = _GIFTING_SUPPORTED` so the UI can gate itself.

## 5. Supabase parity

`gift_sparks` RPC in `sql/templates/games-schema.template.sql` (rendered to `sql/games-schema.sql` +
`sql/games-gamma-schema.sql`), doing the whole guarded transaction server-side with row locks.
`supabase_db.gift_sparks` validates the amount before the RPC and normalizes the RPC's `balance` →
`new_balance`. Added to `db.py`'s `_SUPABASE_EXPORTS`. Targeted migrations:
`sql/migrations/20260721T010000_gifting.sql` (+ `_gamma`) for first activation and
`20260721T040000_gifting_idempotency_replay.sql` (+ `_gamma`) for the replay hardening follow-up.
**To activate on gamma/prod:** apply the migrations (after the referral migration), then set
`GIFTING_ENABLED=true` and recreate the container.

## 6. Frontend

- `GiftSection` in `SettingsDrawer`: friend-code + amount inputs + **Send**. Hidden unless
  `feature_flags.gifting_enabled === true`.
- One idempotency key (`randomId()`, backed by `crypto.randomUUID()` when available with a webview-safe
  RFC4122 fallback) is held per in-flight attempt: reused on a retry after a failure (safe), rotated
  only after a confirmed success. Success toasts "Sent N sparks" (or
  "Already sent — no charge." on a duplicate replay), clears the form, fires `refresh-sparks`.

## 7. Abuse considerations (v1, documented)

- Device-id wallets allow self-transfer across two devices; this just moves sparks a player already
  owns (no minting), so the risk is limited to laundering earned/bonus sparks. Per-sender daily count +
  token caps bound it; self-gift on one wallet is blocked. Residual risk accepted, logged.

## 8. Testing
- `backend/tests/test_gifting.py`: happy path moves + records both legs; case/space-insensitive code;
  invalid amounts; unknown/empty code; self-gift; insufficient; recipient-at-cap conserves sparks;
  idempotent replay (no double-send); daily count cap; daily token cap; Supabase `balance`→`new_balance`
  normalization + pre-RPC amount validation; `/tokens/gift` endpoint (200 shape + 404/400 mapping).
- `frontend/.../GiftSection.test.tsx`: success/error copy, duplicate replay copy, and the
  idempotency-key contract (shared on retry, rotated after success).

## 9. Files touched
- `backend/config.py` (5 gift vars), `backend/db.py` (`gift_sparks` + export), `backend/supabase_db.py`
  (`gift_sparks` wrapper), `backend/main.py` (`/tokens/gift` + `/config/public` flag),
  `backend/tests/test_gifting.py`.
- SQL: `sql/templates/games-schema.template.sql` (+ rendered pair) +
  `sql/migrations/20260721T010000_gifting{,_gamma}.sql` and
  `sql/migrations/20260721T040000_gifting_idempotency_replay{,_gamma}.sql`.
- Frontend: `GiftSection.tsx`, `SettingsDrawer.tsx` (wire + gate), `types/remoteConfig.ts` (flag),
  `GiftSection.test.tsx`.
