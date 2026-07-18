-- Account deletion (SPEC-ACCOUNT-DELETION) — Supabase/Postgres migration.
-- Apply to gamma FIRST, verify, then prod. Idempotent: safe to re-run.
--
-- Replace `games_` with `games_gamma_` for the gamma schema.
--
-- Two parts:
--   1. The deleted-accounts denylist (stateless session JWTs cannot be revoked, so without
--      this a token held across deletion would re-create the wallet AND collect a fresh
--      signup bonus — deletion would be cosmetic and farmable).
--   2. Dropping the token_transactions -> wallets CASCADE. This is the important one.

-- ---------------------------------------------------------------------------
-- 1. Denylist
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS games_deleted_accounts (
  user_id TEXT PRIMARY KEY,
  deleted_at BIGINT NOT NULL
);

ALTER TABLE games_deleted_accounts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS service_role_all_games_deleted_accounts ON games_deleted_accounts;
CREATE POLICY service_role_all_games_deleted_accounts ON games_deleted_accounts
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ---------------------------------------------------------------------------
-- 2. Remove the ON DELETE CASCADE from token_transactions.wallet_id
-- ---------------------------------------------------------------------------
-- WHY: the ledger was `REFERENCES games_wallets(id) ON DELETE CASCADE`, so deleting a
-- wallet destroyed that user's entire purchase history. Account deletion deliberately
-- retains the ledger:
--   * it is a financial record with tax/accounting retention obligations
--     (GDPR Art. 17(3)(b) permits retention for legal compliance), and
--   * it is what makes credit_purchase idempotent — dropping it would let a replayed or
--     late webhook double-credit.
-- The ledger is pseudonymous once the users row is gone: its only identifier is a random
-- UUID with nothing linking it to an email or person.
--
-- This also fixes a silent Postgres/SQLite divergence — SQLite never had this FK, so tests
-- asserted "ledger retained" while production would have cascaded it away.
--
-- The constraint is auto-named by Postgres from the inline REFERENCES; drop by that name.
ALTER TABLE games_token_transactions
  DROP CONSTRAINT IF EXISTS games_token_transactions_wallet_id_fkey;

-- ---------------------------------------------------------------------------
-- 3. delete_account RPC — one transaction, so a partial delete is impossible
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION games_delete_account(
  p_user_id TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_now BIGINT := EXTRACT(EPOCH FROM NOW())::BIGINT;
BEGIN
  IF EXISTS (SELECT 1 FROM games_deleted_accounts WHERE user_id = p_user_id) THEN
    RETURN jsonb_build_object('deleted', false, 'reason', 'already_deleted');
  END IF;

  -- wallet id == user id for signed-in users (tokens.get_wallet_id).
  DELETE FROM games_generated_content WHERE wallet_id = p_user_id;
  DELETE FROM games_wallets WHERE id = p_user_id;
  DELETE FROM games_entitlements WHERE user_id = p_user_id;
  DELETE FROM games_device_usage WHERE user_id = p_user_id;
  DELETE FROM games_users WHERE id = p_user_id;

  INSERT INTO games_deleted_accounts (user_id, deleted_at)
  VALUES (p_user_id, v_now);

  RETURN jsonb_build_object('deleted', true);
END;
$$;

REVOKE EXECUTE ON FUNCTION games_delete_account(TEXT) FROM PUBLIC, anon, authenticated;

-- ---------------------------------------------------------------------------
-- Verification (run manually after applying)
-- ---------------------------------------------------------------------------
-- Expect ZERO rows — i.e. the cascade is gone:
--   SELECT conname FROM pg_constraint
--   WHERE conrelid = 'games_token_transactions'::regclass AND contype = 'f';
--
-- Expect the table and function to exist:
--   SELECT to_regclass('games_deleted_accounts');
--   SELECT proname FROM pg_proc WHERE proname = 'games_delete_account';
