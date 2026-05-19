# LocalPlay Supabase Migration Spec

## Goal

Move LocalPlay's persistent server data from VM-local SQLite to the shared Supabase Postgres project already used by VibePix.

This migration should:

- Remove the single-VM SQLite durability constraint.
- Keep prod and gamma isolated inside the same shared Supabase project.
- Preserve the existing LocalPlay API, auth, wallet, Stripe, and admin behavior.
- Prepare the persistence layer for a future Cloud Run migration.
- Avoid adopting Supabase Auth. LocalPlay should continue using direct Google/Apple ID tokens with server-issued LocalPlay session JWTs.

This migration does **not** immediately make LocalPlay safe for autoscaled Cloud Run. Live rooms, WebSocket connections, generated content ownership, and some game history are still in process memory today. Supabase persistence is a prerequisite for Cloud Run, not the whole Cloud Run migration.

## Source Of Truth

VibePix already uses the shared Supabase project:

```text
Project ref: hosbtyylacluziugwjfd
Project name: LearningCompanion
Region: us-west-2
URL: https://hosbtyylacluziugwjfd.supabase.co
```

VibePix environment separation is by table prefix:

```text
Prod:  vp_*
Gamma: vp_gamma_*
```

LocalPlay must follow the same shared-project convention:

```text
Prod:  games_*
Gamma: games_gamma_*
```

## Current Status

As of 2026-05-19, the LocalPlay Supabase objects have been created in the shared VibePix/LearningCompanion Supabase project using the same Management API pattern VibePix uses.

Applied SQL:

- `sql/games-schema.sql` creates production `games_*` tables and RPCs.
- `sql/games-gamma-schema.sql` creates gamma `games_gamma_*` tables and RPCs.

Verified objects:

- Tables: `games_users`, `games_wallets`, `games_token_transactions`, `games_entitlements`, `games_device_usage`, `games_request_log`, `games_pending_tokens`, `games_webhook_events`, `games_generated_content`, `games_game_history`, `games_rejections`.
- Gamma equivalents with the `games_gamma_` prefix.
- RPCs: `ensure_wallet`, `debit_tokens`, `credit_tokens`, `credit_purchase`, `merge_wallet`, `grant_daily_bonus`, `grant_ad_reward`, `claim_device_usage`, `claim_user_usage`, `mark_webhook_processed`, with both prefixes.

Runtime is still SQLite. No deployed LocalPlay environment uses these Supabase tables until `DB_BACKEND=supabase` and `SUPABASE_SERVICE_KEY` are set in that environment.

The repository contains migration scaffolding:

- `backend/config.py` exposes Supabase env settings, but `DB_BACKEND` defaults to `sqlite`.
- `sql/templates/games-schema.template.sql` defines prefixed tables, indexes, RLS, and server-only RPCs.
- `sql/games-schema.sql` is the rendered production SQL with the `games_` prefix.
- `sql/games-gamma-schema.sql` is the rendered gamma SQL with the `games_gamma_` prefix.
- `scripts/render-supabase-sql.py` regenerates both SQL files from the template.
- `scripts/deploy-gcp.sh` validates that production uses `games_` and gamma uses `games_gamma_`; it does not switch either runtime to Supabase.

Future SQL changes must still be applied deliberately; editing files in this repo does not automatically mutate Supabase. No deployed runtime changes persistence until a human sets `DB_BACKEND=supabase` and `SUPABASE_SERVICE_KEY` in the VM env.

## Current SQLite Surface

Current SQLite file locations:

```text
Prod:  /home/revelry-games/revelry-data/revelry.db
Gamma: /home/revelry-games/revelry-data-gamma/revelry.db
```

Current persistent tables in `backend/db.py`:

| SQLite table | Purpose | Must migrate |
|--------------|---------|--------------|
| `users` | Direct Google/Apple account records | Yes |
| `wallets` | Spark wallet balance and daily/ad counters | Yes |
| `token_transactions` | Spark ledger, purchases, spends, merges, refunds | Yes |
| `entitlements` | Legacy entitlement/IAP restore data | Yes, keep for restore/backcompat |
| `device_usage` | Legacy free-tier usage | Yes, keep while code references it |
| `request_log` | Idempotency for generation requests | Yes |
| `pending_tokens` | Stripe checkout return notification pickup | Yes |
| `webhook_events` | Stripe webhook deduplication | Yes |

Current in-memory state not covered by SQLite:

| In-memory state | Current location | Supabase phase |
|-----------------|------------------|----------------|
| Generated quiz/MLT content | `main.py` dictionaries | Phase 2 |
| Content ownership | `content_owners` dict | Phase 2 |
| Completed game history | `game_history` list | Phase 2 |
| Live room state | `socket_manager.rooms` | Future Cloud Run phase |
| WebSocket connection objects | `socket_manager` | Must remain process-local |

## Target Architecture

### Phase 1: Supabase For Existing SQLite Tables

```text
Browser/PWA
  -> FastAPI backend
      -> db.py facade
          -> SQLite adapter, local/dev fallback
          -> Supabase adapter, deployed prod/gamma
              -> shared Supabase project
                  -> games_* tables
                  -> games_gamma_* tables
```

Phase 1 keeps:

- Current GCP VM deployment.
- Current IONOS frontend.
- Current backend-served SPA gamma/prod preview.
- Current in-memory live rooms.
- Current API shapes.

Phase 1 changes:

- `backend/db.py` becomes a stable facade over a pluggable storage backend.
- Production and gamma use Supabase.
- Local tests can continue using SQLite unless explicitly testing Supabase.
- Atomic wallet/payment operations move to Postgres RPCs.

### Phase 2: Persist Generated Content And Game History

Add Supabase tables for generated content, content ownership, and completed game history. This removes a major restart/durability weakness and is required before serious Cloud Run work.

### Future Cloud Run Phase

Cloud Run still needs a live-room strategy:

- Single instance only: possible early Cloud Run shape with `max-instances=1`, long request timeout, and min instances as desired.
- Multi-instance: requires external live room state plus WebSocket routing/fanout, likely Redis/Memorystore or another shared realtime layer.

Do not claim Cloud Run readiness after Phase 1.

## Runtime Configuration

Add these env vars:

```env
DB_BACKEND=sqlite
TABLE_PREFIX=games_
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
SUPABASE_ANON_KEY=
SUPABASE_TIMEOUT_SECONDS=10
```

Production:

```env
DB_BACKEND=supabase
TABLE_PREFIX=games_
SUPABASE_URL=https://hosbtyylacluziugwjfd.supabase.co
SUPABASE_SERVICE_KEY=<service-role-key>
SUPABASE_ANON_KEY=<anon-key>
```

Gamma:

```env
DB_BACKEND=supabase
TABLE_PREFIX=games_gamma_
SUPABASE_URL=https://hosbtyylacluziugwjfd.supabase.co
SUPABASE_SERVICE_KEY=<service-role-key>
SUPABASE_ANON_KEY=<anon-key>
```

Rules:

- `TABLE_PREFIX` must end in `_`.
- Production deploy must refuse `TABLE_PREFIX=games_gamma_`.
- Gamma deploy must refuse `TABLE_PREFIX=games_`.
- `SUPABASE_SERVICE_KEY` must never be exposed to frontend builds.
- `SUPABASE_ANON_KEY` is optional for the current backend-only implementation but useful for parity with VibePix env conventions.
- Supabase Auth remains unused.

## Table Naming

Use the same schema shape for prod and gamma, differing only by prefix:

| Logical table | Prod | Gamma |
|---------------|------|-------|
| Users | `games_users` | `games_gamma_users` |
| Wallets | `games_wallets` | `games_gamma_wallets` |
| Token transactions | `games_token_transactions` | `games_gamma_token_transactions` |
| Entitlements | `games_entitlements` | `games_gamma_entitlements` |
| Device usage | `games_device_usage` | `games_gamma_device_usage` |
| Request log | `games_request_log` | `games_gamma_request_log` |
| Pending tokens | `games_pending_tokens` | `games_gamma_pending_tokens` |
| Webhook events | `games_webhook_events` | `games_gamma_webhook_events` |
| Generated content | `games_generated_content` | `games_gamma_generated_content` |
| Game history | `games_game_history` | `games_gamma_game_history` |
| Rejections/debug events | `games_rejections` | `games_gamma_rejections` |

RPC/function names must also be prefixed:

| Logical RPC | Prod | Gamma |
|-------------|------|-------|
| Debit wallet | `games_debit_tokens` | `games_gamma_debit_tokens` |
| Credit wallet | `games_credit_tokens` | `games_gamma_credit_tokens` |
| Credit purchase | `games_credit_purchase` | `games_gamma_credit_purchase` |
| Merge wallet | `games_merge_wallet` | `games_gamma_merge_wallet` |
| Grant daily bonus | `games_grant_daily_bonus` | `games_gamma_grant_daily_bonus` |
| Grant ad reward | `games_grant_ad_reward` | `games_gamma_grant_ad_reward` |
| Claim device free usage | `games_claim_device_usage` | `games_gamma_claim_device_usage` |
| Claim user free usage | `games_claim_user_usage` | `games_gamma_claim_user_usage` |
| Mark webhook processed | `games_mark_webhook_processed` | `games_gamma_mark_webhook_processed` |

## Schema

Prefer keeping integer epoch timestamps for Phase 1 compatibility with the existing Python code. A later cleanup can move to `TIMESTAMPTZ`.

Use `TEXT` for UUID values in Phase 1 because wallet IDs can be either UUID-like device IDs or app user IDs, and keeping text avoids broad call-site churn.

### Users

```sql
CREATE TABLE IF NOT EXISTS games_users (
  id TEXT PRIMARY KEY,
  provider TEXT NOT NULL CHECK (provider IN ('google', 'apple')),
  provider_subject_id TEXT NOT NULL,
  email TEXT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_games_users_provider_subject
  ON games_users(provider, provider_subject_id);
CREATE INDEX IF NOT EXISTS idx_games_users_email
  ON games_users(email);
```

### Wallets

```sql
CREATE TABLE IF NOT EXISTS games_wallets (
  id TEXT PRIMARY KEY,
  balance INTEGER NOT NULL DEFAULT 0 CHECK (balance >= 0),
  lifetime_purchased INTEGER NOT NULL DEFAULT 0 CHECK (lifetime_purchased >= 0),
  last_daily_bonus_date TEXT NOT NULL DEFAULT '',
  ads_watched_today INTEGER NOT NULL DEFAULT 0 CHECK (ads_watched_today >= 0),
  ads_watched_date TEXT NOT NULL DEFAULT '',
  created_at BIGINT NOT NULL,
  updated_at BIGINT
);

CREATE INDEX IF NOT EXISTS idx_games_wallets_purchased
  ON games_wallets(lifetime_purchased)
  WHERE lifetime_purchased > 0;
```

### Token Transactions

```sql
CREATE TABLE IF NOT EXISTS games_token_transactions (
  id BIGSERIAL PRIMARY KEY,
  wallet_id TEXT NOT NULL REFERENCES games_wallets(id) ON DELETE CASCADE,
  amount INTEGER NOT NULL,
  reason TEXT NOT NULL,
  reference_id TEXT,
  balance_after INTEGER NOT NULL,
  metadata TEXT NOT NULL DEFAULT '',
  created_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_games_txn_wallet
  ON games_token_transactions(wallet_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_games_txn_reference
  ON games_token_transactions(reference_id)
  WHERE reference_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_games_txn_reason_reference
  ON games_token_transactions(reason, reference_id)
  WHERE reference_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_games_purchase_once
  ON games_token_transactions(wallet_id, reference_id, reason)
  WHERE reference_id IS NOT NULL AND reason = 'purchase';
```

### Entitlements

```sql
CREATE TABLE IF NOT EXISTS games_entitlements (
  id TEXT PRIMARY KEY,
  user_id TEXT,
  device_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending_payment',
  games_remaining INTEGER NOT NULL DEFAULT 50,
  expires_at BIGINT NOT NULL,
  stripe_session_id TEXT,
  apple_transaction_id TEXT,
  google_order_id TEXT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_games_entitlements_stripe
  ON games_entitlements(stripe_session_id)
  WHERE stripe_session_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_games_entitlements_apple
  ON games_entitlements(apple_transaction_id)
  WHERE apple_transaction_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_games_entitlements_google
  ON games_entitlements(google_order_id)
  WHERE google_order_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_games_entitlements_user_status
  ON games_entitlements(user_id, status)
  WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_games_entitlements_device_status
  ON games_entitlements(device_id, status);
```

### Device Usage

```sql
CREATE TABLE IF NOT EXISTS games_device_usage (
  device_id TEXT PRIMARY KEY,
  user_id TEXT,
  games_used_free INTEGER NOT NULL DEFAULT 0 CHECK (games_used_free >= 0),
  window_start BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_games_device_usage_user
  ON games_device_usage(user_id)
  WHERE user_id IS NOT NULL;
```

### Request Log

```sql
CREATE TABLE IF NOT EXISTS games_request_log (
  idempotency_key TEXT PRIMARY KEY,
  device_id TEXT NOT NULL,
  result_id TEXT,
  created_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_games_request_log_created
  ON games_request_log(created_at);
```

### Pending Tokens

```sql
CREATE TABLE IF NOT EXISTS games_pending_tokens (
  device_id TEXT PRIMARY KEY,
  token TEXT NOT NULL,
  created_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_games_pending_tokens_created
  ON games_pending_tokens(created_at);
```

### Webhook Events

```sql
CREATE TABLE IF NOT EXISTS games_webhook_events (
  event_id TEXT PRIMARY KEY,
  processed_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_games_webhook_events_processed
  ON games_webhook_events(processed_at);
```

### Phase 2 Generated Content

```sql
CREATE TABLE IF NOT EXISTS games_generated_content (
  id TEXT PRIMARY KEY,
  wallet_id TEXT NOT NULL,
  content_type TEXT NOT NULL CHECK (content_type IN ('quiz', 'mlt')),
  title TEXT NOT NULL DEFAULT '',
  payload JSONB NOT NULL,
  prompt TEXT,
  model TEXT,
  provider TEXT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT
);

CREATE INDEX IF NOT EXISTS idx_games_generated_content_wallet
  ON games_generated_content(wallet_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_games_generated_content_type
  ON games_generated_content(content_type, created_at DESC);
```

### Phase 2 Game History

```sql
CREATE TABLE IF NOT EXISTS games_game_history (
  id BIGSERIAL PRIMARY KEY,
  room_code TEXT NOT NULL,
  wallet_id TEXT NOT NULL,
  game_type TEXT NOT NULL DEFAULT 'quiz',
  game_title TEXT NOT NULL DEFAULT '',
  summary JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_games_game_history_wallet
  ON games_game_history(wallet_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_games_game_history_room
  ON games_game_history(room_code, created_at DESC);
```

### Optional Rejections/Diagnostics

```sql
CREATE TABLE IF NOT EXISTS games_rejections (
  id BIGSERIAL PRIMARY KEY,
  endpoint TEXT NOT NULL,
  reason TEXT NOT NULL,
  status_code INTEGER NOT NULL,
  wallet_id TEXT,
  device_id TEXT,
  user_id TEXT,
  origin TEXT,
  ip_hash TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_games_rejections_created
  ON games_rejections(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_games_rejections_reason
  ON games_rejections(reason, created_at DESC);
```

## Row-Level Security

Enable RLS on every `games_*` and `games_gamma_*` table.

Current LocalPlay backend should use only the Supabase service-role key. The frontend should not talk directly to Supabase in this migration.

Initial RLS policy:

```sql
ALTER TABLE games_wallets ENABLE ROW LEVEL SECURITY;
-- repeat for every table

CREATE POLICY "service_role_all_games_wallets"
ON games_wallets
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);
```

Repeat for each prod and gamma table. Do not add public `anon` policies unless a later feature intentionally exposes client-side Supabase access.

## Atomic Operations

SQLite currently relies on `BEGIN IMMEDIATE`. Supabase/Postgres must use RPC functions for operations that need read-modify-write correctness.

Use `SECURITY DEFINER` RPCs owned by a privileged role and callable only by `service_role`.

Required RPC behavior:

- Lock target wallet rows with `FOR UPDATE`.
- Create missing wallets where current SQLite does.
- Enforce `MAX_TOKEN_BALANCE`.
- Return JSON matching current Python helper return shapes where practical.
- Be idempotent for purchases and webhook processing.
- Never silently double-credit or double-debit.

### Debit Tokens RPC

Inputs:

```text
p_wallet_id TEXT
p_amount INTEGER
p_reason TEXT
p_reference_id TEXT DEFAULT NULL
```

Returns:

```json
{"success": true, "balance": 123}
```

Behavior:

- Fail if amount <= 0.
- Lock wallet row.
- Return `success=false` with current balance if wallet is missing or insufficient.
- Insert negative transaction on success.

### Credit Tokens RPC

Inputs:

```text
p_wallet_id TEXT
p_amount INTEGER
p_reason TEXT
p_reference_id TEXT DEFAULT NULL
p_metadata TEXT DEFAULT ''
p_max_balance INTEGER
```

Behavior:

- Create wallet if missing.
- Cap at `p_max_balance`.
- Insert positive transaction only for actual credited amount.

### Credit Purchase RPC

Must be idempotent on `(wallet_id, reference_id, reason='purchase')`.

Behavior:

- If purchase transaction exists, return existing `balance_after`.
- Create wallet if missing.
- Credit up to max balance.
- Increment `lifetime_purchased` by actual credit.
- Insert transaction with metadata.

### Merge Wallet RPC

Behavior must match current `merge_wallet`:

- No-op when `from_id == to_id`.
- Reject if target wallet already has a `merge_in`.
- Reject if the same `from_id -> to_id` merge already has a `merge_out`.
- Transfer balance up to max.
- Set source balance to 0.
- Add `merge_out` and `merge_in` transactions.
- Merge `lifetime_purchased`.

The current "max one merge per user wallet" behavior is product-sensitive and should be reviewed separately, but the migration should preserve it first.

### Daily Bonus RPC

Behavior:

- Lock wallet.
- No-op if `last_daily_bonus_date == today`.
- Grant up to max balance.
- Reset ad counter for the new UTC day.

### Ad Reward RPC

Behavior:

- Lock wallet.
- Reset ad counter if date changed.
- No-op if daily ad cap reached.
- Grant up to max balance.
- Increment ad counter.

### Usage RPCs

Preserve existing legacy free-usage behavior:

- Device usage: one row by `device_id`.
- User usage: sum rows for `user_id` in the active window, then increment current device row atomically.

## Application Code Changes

### Dependencies

Add one of:

```text
supabase
```

or:

```text
httpx
```

`httpx` already exists in the backend for auth. A small internal Supabase REST/RPC client using `httpx` may be preferable to adding a large dependency.

### Config

Add to `backend/config.py`:

```python
DB_BACKEND = os.getenv("DB_BACKEND", "sqlite").lower()
TABLE_PREFIX = os.getenv("TABLE_PREFIX", "games_")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_TIMEOUT_SECONDS = float(os.getenv("SUPABASE_TIMEOUT_SECONDS", "10"))
```

Startup validation:

- If `DB_BACKEND=supabase`, require `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, and `TABLE_PREFIX`.
- Refuse unknown prefixes outside `games_` and `games_gamma_` in production deploy scripts.
- Keep SQLite as the default for local tests/dev until Supabase tests are explicit.

### Storage Abstraction

Keep `backend/db.py` as the public facade so call sites do not churn.

Suggested file layout:

```text
backend/db.py                 # facade, exports existing functions
backend/storage/
  __init__.py
  base.py                     # optional protocol/interface
  sqlite_store.py             # current implementation moved mostly as-is
  supabase_store.py           # Supabase implementation
```

`db.py` selects implementation at import/startup:

```python
if config.DB_BACKEND == "supabase":
    _store = SupabaseStore(config.TABLE_PREFIX, ...)
else:
    _store = SQLiteStore(...)
```

Each existing function in `db.py` delegates to `_store`.

Required existing functions to preserve:

- `init_db`
- `create_entitlement`
- `get_active_entitlement`
- `decrement_entitlement`
- `revoke_entitlement_by_stripe`
- `activate_pending_entitlement`
- `get_entitlement_by_stripe_session`
- `check_and_increment_free_usage`
- `get_free_usage_count`
- `peek_free_usage`
- `check_idempotency`
- `record_idempotency`
- `store_pending_token`
- `pop_pending_token`
- `find_or_create_user`
- `get_user`
- `merge_device_to_user`
- `get_active_entitlement_for_user`
- `get_user_free_usage_count`
- `check_and_increment_user_free_usage`
- `peek_user_free_usage`
- `lookup_by_device`
- `lookup_entitlement`
- `admin_revoke`
- `find_restorable_entitlement`
- `admin_grant`
- `lookup_by_user`
- `lookup_user_by_email`
- `get_or_create_wallet`
- `get_wallet_balance`
- `debit_tokens`
- `credit_tokens`
- `check_and_grant_daily_bonus`
- `check_and_grant_ad_reward`
- `has_ever_purchased`
- `credit_purchase`
- `merge_wallet`
- `migrate_entitlements_to_wallets`
- `admin_grant_tokens`
- `admin_lookup_wallet`
- `is_webhook_event_processed`
- `get_refund_debits_for_session`
- `mark_webhook_event_processed`

### Admin Stats

`backend/main.py` currently reaches into SQLite with `db._get_conn()` for `/admin/stats`.

Replace this with facade helpers:

```python
db.get_admin_stats()
```

The helper should return:

```json
{
  "wallet_count": 0,
  "total_sparks": 0,
  "paying_users": 0,
  "purchase_count": 0,
  "merge_count": 0,
  "users_count": 0
}
```

This removes the last known raw SQL call outside `db.py`.

### Content Persistence Phase 2

Add facade helpers:

```python
save_generated_content(...)
get_generated_content(content_id, wallet_id=None)
delete_generated_content(content_id, wallet_id)
list_generated_content(wallet_id, limit=50)
record_game_history(...)
list_game_history(wallet_id, limit=50)
get_game_history_detail(wallet_id, history_id)
```

Then replace:

- `generated_quizzes`
- `generated_mlt_scenarios`
- `content_owners`
- `game_history`

Do this before any multi-instance Cloud Run deployment.

## SQL File Layout

Add:

```text
sql/
  games-schema.sql                 # prod tables + indexes + RLS
  games-gamma-schema.sql           # gamma tables + indexes + RLS
  games-migrate-from-sqlite.sql    # optional staging helpers/reference
  templates/
    games-schema.template.sql       # source for both prod/gamma SQL files
scripts/
  render-supabase-sql.py
```

Prefer generating prod/gamma SQL from a template to avoid drift:

```text
sql/templates/games-schema.template.sql
scripts/render-supabase-sql.py --prefix games_ > sql/games-schema.sql
scripts/render-supabase-sql.py --prefix games_gamma_ > sql/games-gamma-schema.sql
```

If no generator is added, every schema/RPC change must be applied to both prod and gamma files in the same commit.

## Deploying SQL To Supabase

Use the same pattern as VibePix:

```bash
TOKEN=$(security find-generic-password -s "Supabase CLI" -w | sed 's/^go-keyring-base64://' | base64 -d)

curl -X POST "https://api.supabase.com/v1/projects/hosbtyylacluziugwjfd/database/query" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "$(jq -n --arg q "$(cat sql/games-gamma-schema.sql)" '{query: $q}')"
```

HTTP 201 means success.

Verification query:

```bash
curl -s -X POST "https://api.supabase.com/v1/projects/hosbtyylacluziugwjfd/database/query" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT tablename FROM pg_tables WHERE schemaname = '\''public'\'' AND (tablename LIKE '\''games_%'\'' OR tablename LIKE '\''games_gamma_%'\'') ORDER BY tablename;"}'
```

RPC verification:

```bash
curl -s -X POST "https://api.supabase.com/v1/projects/hosbtyylacluziugwjfd/database/query" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT proname FROM pg_proc WHERE proname LIKE '\''games_%'\'' ORDER BY proname;"}'
```

## Data Migration

### Recommended Order

1. Build and test Supabase schema/RPCs against gamma prefix.
2. Add Supabase adapter behind `DB_BACKEND`.
3. Deploy gamma with `DB_BACKEND=supabase` and empty gamma tables.
4. Exercise signup, Google, Apple, wallet balance, generation spend, room spend, Stripe test checkout, webhook dedup, admin lookup.
5. Export gamma SQLite and import into `games_gamma_*` only if gamma data is worth preserving.
6. Deploy prod schema/RPCs.
7. Take prod maintenance window.
8. Stop prod container or block writes.
9. Back up SQLite.
10. Export SQLite to JSON/CSV.
11. Import into `games_*` tables.
12. Run row-count and balance reconciliation.
13. Start prod with `DB_BACKEND=supabase`.
14. Keep SQLite file as rollback backup.

### Export

Use a Python script to export each SQLite table to JSONL:

```text
scripts/export-sqlite-to-jsonl.py
```

Outputs:

```text
/tmp/localplay-sqlite-export/
  users.jsonl
  wallets.jsonl
  token_transactions.jsonl
  entitlements.jsonl
  device_usage.jsonl
  request_log.jsonl
  pending_tokens.jsonl
  webhook_events.jsonl
```

### Import

Use service-role Supabase REST inserts or SQL `COPY` through the management API.

For production, imports must be idempotent:

- Use `upsert` on natural primary keys.
- Preserve `token_transactions.id` if possible, or let Postgres assign new ids only if no code depends on the old integer ID. Current code does not appear to depend on transaction IDs externally.
- Preserve transaction ordering by `created_at`.
- Preserve all `reference_id` values.

### Reconciliation Queries

Before cutover:

```sql
SELECT COUNT(*) FROM games_users;
SELECT COUNT(*) FROM games_wallets;
SELECT COUNT(*) FROM games_token_transactions;
SELECT COALESCE(SUM(balance), 0) FROM games_wallets;
SELECT COALESCE(SUM(amount), 0) FROM games_token_transactions;
SELECT COUNT(*) FROM games_token_transactions WHERE reason = 'purchase';
SELECT COUNT(*) FROM games_webhook_events;
```

Compare against SQLite:

```sql
SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM wallets;
SELECT COUNT(*) FROM token_transactions;
SELECT COALESCE(SUM(balance), 0) FROM wallets;
SELECT COALESCE(SUM(amount), 0) FROM token_transactions;
SELECT COUNT(*) FROM token_transactions WHERE reason = 'purchase';
SELECT COUNT(*) FROM webhook_events;
```

Note: wallet balance sum and ledger sum are not expected to be identical if signup/daily bonuses and caps create non-purchase credits. The important checks are row counts, current balances, purchase idempotency references, and sample wallet histories.

### Cutover Safety

Before prod cutover:

- Disable or pause Stripe webhooks if the maintenance window is long.
- Stop `games-backend` or put it into read-only/maintenance mode.
- Export SQLite after writes are stopped.
- Import into Supabase.
- Set prod env to Supabase.
- Start prod.
- Send a test Stripe webhook or perform a low-risk checkout only after reconciliation.

Rollback:

- Stop prod.
- Set `DB_BACKEND=sqlite`.
- Restore the pre-cutover SQLite volume if needed.
- Restart prod.
- Any writes accepted by Supabase after cutover must be replayed manually if rolling back.

## Deploy Script Changes

Update `scripts/deploy-gcp.sh` bootstrap:

Production additions:

```env
DB_BACKEND=supabase
TABLE_PREFIX=games_
SUPABASE_URL=https://hosbtyylacluziugwjfd.supabase.co
SUPABASE_SERVICE_KEY=<manual secret>
SUPABASE_ANON_KEY=<manual secret>
```

Gamma additions:

```env
DB_BACKEND=supabase
TABLE_PREFIX=games_gamma_
SUPABASE_URL=https://hosbtyylacluziugwjfd.supabase.co
SUPABASE_SERVICE_KEY=<manual secret>
SUPABASE_ANON_KEY=<manual secret>
```

Do not make bootstrap invent Supabase keys. If missing, deploy should fail clearly when `DB_BACKEND=supabase`.

Add preflight:

- If deploying prod and `TABLE_PREFIX=games_gamma_`, fail.
- If deploying gamma and `TABLE_PREFIX=games_`, fail.
- If `DB_BACKEND=supabase`, check service key presence.
- Print table prefix in deploy summary.

## Testing Plan

### Unit Tests

Keep existing SQLite-backed tests passing.

Add Supabase adapter unit tests with mocked HTTP/RPC client:

- Table prefix is applied to every table.
- Unknown prefix is rejected.
- Missing service key raises startup error.
- RPC failures are surfaced with useful messages.
- Returned Supabase rows normalize to existing dict shapes.

### Integration Tests Against Gamma Supabase

Guard behind an explicit env var so tests never hit Supabase accidentally:

```bash
RUN_SUPABASE_TESTS=1 DB_BACKEND=supabase TABLE_PREFIX=games_gamma_ ...
```

Coverage:

- `find_or_create_user` idempotency and email update.
- `get_or_create_wallet` with signup bonus.
- `debit_tokens` insufficient and success paths.
- `credit_purchase` duplicate reference id.
- `merge_wallet` first merge, repeated merge, and capped merge.
- `check_and_grant_daily_bonus` idempotency.
- `check_and_grant_ad_reward` daily cap.
- `check_idempotency` and `record_idempotency`.
- `store_pending_token` and `pop_pending_token`.
- `is_webhook_event_processed` and `mark_webhook_event_processed`.
- `/auth/signin` Google/Apple mocked token path.
- `/tokens/balance`.
- Quiz generation spend.
- Room start spend.
- Stripe test checkout webhook.

### Deployment Smoke

Gamma:

```bash
curl -sS https://gamesapi-gamma.revelryapp.me/health
curl -sS https://gamesapi-gamma.revelryapp.me/providers
```

Manual:

- Google sign-in.
- Apple sign-in.
- Generate quiz.
- Start room.
- Check spark balance decreases.
- Admin lookup by wallet/user.

Production:

- Same health/API checks.
- Manual Google and Apple sign-in on `https://games.revelryapp.me/quiz/`.
- One low-risk wallet/admin grant check.

## Data Retention

Permanent:

- `games_users`
- `games_wallets`
- `games_token_transactions`
- `games_entitlements`

Short-lived:

- `games_request_log`: delete older than 1 day.
- `games_pending_tokens`: delete older than 1 day.
- `games_webhook_events`: delete older than 7 days.
- `games_rejections`: delete older than 30 days.

Phase 2:

- `games_game_history`: define product retention before production use. Current in-memory history is volatile, so starting with 90 days is reasonable.
- `games_generated_content`: define retention and deletion UX. Current in-memory content is volatile.

## Cleanup Jobs

Use one of:

- Supabase `pg_cron`, if enabled.
- A protected backend admin endpoint called by Cloud Scheduler.
- A manual admin script during early rollout.

Cleanup SQL examples:

```sql
DELETE FROM games_request_log
WHERE created_at < EXTRACT(EPOCH FROM NOW() - INTERVAL '1 day')::BIGINT;

DELETE FROM games_pending_tokens
WHERE created_at < EXTRACT(EPOCH FROM NOW() - INTERVAL '1 day')::BIGINT;

DELETE FROM games_webhook_events
WHERE processed_at < EXTRACT(EPOCH FROM NOW() - INTERVAL '7 days')::BIGINT;

DELETE FROM games_rejections
WHERE created_at < EXTRACT(EPOCH FROM NOW() - INTERVAL '30 days')::BIGINT;
```

Duplicate for `games_gamma_*`.

## Security Notes

- Service-role key stays server-only.
- Do not include Supabase keys in Vite frontend env.
- RLS must be enabled on all tables even if only service role is used.
- No raw provider ID tokens should be stored.
- No raw IP addresses should be stored; hash IPs before inserting diagnostic/rejection rows.
- Stripe webhook idempotency must remain DB-backed before Cloud Run.
- Wallet RPCs must be the only code path for balance mutations in Supabase mode.

## Implementation Checklist

1. Add `SPEC-SUPABASE-MIGRATION.md`.
2. Add SQL template or separate prod/gamma SQL files.
3. Deploy `games_gamma_*` schema and RPCs to Supabase.
4. Add config env vars and startup validation.
5. Split current `db.py` into facade + SQLite adapter.
6. Implement Supabase adapter.
7. Replace raw `db._get_conn()` use in `/admin/stats`.
8. Add mocked Supabase adapter tests.
9. Add optional gamma Supabase integration tests.
10. Deploy gamma with `DB_BACKEND=supabase`.
11. Exercise auth, wallet, generation, room, admin, and Stripe test checkout.
12. Decide whether to migrate gamma SQLite data.
13. Deploy prod schema and RPCs.
14. Export prod SQLite during maintenance window.
15. Import into `games_*`.
16. Reconcile counts, balances, and sample wallets.
17. Deploy prod with `DB_BACKEND=supabase`.
18. Keep SQLite volume backups for rollback.
19. Implement Phase 2 generated content/history persistence.
20. Revisit Cloud Run only after Phase 2 and live room strategy are designed.

## Acceptance Criteria

Phase 1 is complete when:

- Gamma uses `DB_BACKEND=supabase` and `TABLE_PREFIX=games_gamma_`.
- Prod uses `DB_BACKEND=supabase` and `TABLE_PREFIX=games_`.
- No deployed backend writes to SQLite for users, wallets, transactions, entitlements, request logs, pending tokens, or webhook events.
- Existing API and WebSocket gameplay behavior is unchanged.
- Google and Apple sign-in still work on gamma and IONOS production.
- Spark balances, daily bonuses, ad rewards, purchases, refunds, and wallet merges are correct under concurrent requests.
- Stripe webhook retries are deduplicated in Supabase.
- Admin lookup/grant/stats work without direct SQLite access.
- Prod and gamma data are isolated by table prefix in the shared Supabase project.
- Rollback to SQLite remains documented and possible during the initial rollout window.

Phase 2 is complete when:

- Generated quiz/MLT content survives backend restart.
- Content ownership is enforced from Supabase.
- Game history survives backend restart and is scoped by wallet/user.
- In-memory generated content/history dictionaries are removed or treated only as optional caches.

Cloud Run readiness is not achieved until:

- Phase 1 and Phase 2 are complete.
- Live room state strategy is explicitly designed.
- WebSocket reconnect behavior is tested under process restart and, if applicable, multi-instance routing.
