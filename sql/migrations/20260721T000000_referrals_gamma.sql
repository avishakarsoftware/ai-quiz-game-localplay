-- Referral activation (SPEC-REFERRAL) — targeted Supabase migration.
-- Extracted verbatim from the rendered sql/games-schema.sql (do NOT hand-edit the RPC bodies).
-- GAMMA variant (games_gamma_ prefix). Apply to gamma Supabase only.
-- After applying: set REFERRALS_ENABLED=true and recreate the gamma backend container.
-- Idempotent: ADD COLUMN IF NOT EXISTS / CREATE UNIQUE INDEX IF NOT EXISTS / CREATE OR REPLACE.
--
-- The referral RPCs write wallets.updated_at (verified present on both prefixes 2026-07-21).

ALTER TABLE games_gamma_wallets ADD COLUMN IF NOT EXISTS referral_code TEXT;

ALTER TABLE games_gamma_wallets ADD COLUMN IF NOT EXISTS referred_by TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_games_gamma_wallets_referral_code
  ON games_gamma_wallets(referral_code)
  WHERE referral_code IS NOT NULL;

CREATE OR REPLACE FUNCTION games_gamma_set_referral_code(
  p_wallet_id TEXT,
  p_code TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_existing TEXT;
  v_now BIGINT := EXTRACT(EPOCH FROM NOW())::BIGINT;
BEGIN
  INSERT INTO games_gamma_wallets (id, created_at) VALUES (p_wallet_id, v_now)
  ON CONFLICT (id) DO NOTHING;

  SELECT referral_code INTO v_existing FROM games_gamma_wallets WHERE id = p_wallet_id FOR UPDATE;
  IF v_existing IS NOT NULL THEN
    RETURN jsonb_build_object('code', v_existing, 'collision', false);
  END IF;

  BEGIN
    UPDATE games_gamma_wallets SET referral_code = p_code WHERE id = p_wallet_id;
  EXCEPTION WHEN unique_violation THEN
    RETURN jsonb_build_object('code', NULL, 'collision', true);
  END;
  RETURN jsonb_build_object('code', p_code, 'collision', false);
END;
$$;

CREATE OR REPLACE FUNCTION games_gamma_redeem_referral(
  p_referee_id TEXT,
  p_code TEXT,
  p_reward INTEGER,
  p_max_balance INTEGER,
  p_max_per_day INTEGER,
  p_since BIGINT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_referrer_id TEXT;
  v_referee RECORD;
  v_reference_id TEXT;
  v_count INTEGER;
  v_referee_bal INTEGER;
  v_referrer_bal INTEGER;
  v_new INTEGER;
  v_now BIGINT := EXTRACT(EPOCH FROM NOW())::BIGINT;
BEGIN
  SELECT id INTO v_referrer_id FROM games_gamma_wallets WHERE referral_code = p_code;
  IF v_referrer_id IS NULL THEN
    RETURN jsonb_build_object('status', 'invalid_code');
  END IF;
  IF v_referrer_id = p_referee_id THEN
    RETURN jsonb_build_object('status', 'self_referral');
  END IF;

  INSERT INTO games_gamma_wallets (id, created_at) VALUES (p_referee_id, v_now)
  ON CONFLICT (id) DO NOTHING;
  SELECT * INTO v_referee FROM games_gamma_wallets WHERE id = p_referee_id FOR UPDATE;
  IF v_referee.referred_by IS NOT NULL THEN
    RETURN jsonb_build_object('status', 'already_redeemed');
  END IF;

  v_reference_id := 'referral:' || v_referrer_id || ':' || p_referee_id;
  PERFORM 1 FROM games_gamma_token_transactions
    WHERE reference_id = v_reference_id AND reason = 'referral_reward' LIMIT 1;
  IF FOUND THEN
    RETURN jsonb_build_object('status', 'already_redeemed');
  END IF;

  SELECT COUNT(*) INTO v_count FROM games_gamma_token_transactions
    WHERE wallet_id = v_referrer_id AND reason = 'referral_reward' AND created_at >= p_since;
  IF v_count >= p_max_per_day THEN
    RETURN jsonb_build_object('status', 'cap_reached');
  END IF;

  UPDATE games_gamma_wallets SET referred_by = v_referrer_id WHERE id = p_referee_id;

  -- Credit referee (capped); always write a txn row for idempotency + counts.
  v_new := GREATEST(v_referee.balance, LEAST(v_referee.balance + p_reward, p_max_balance));
  INSERT INTO games_gamma_token_transactions (wallet_id, amount, reason, reference_id, balance_after, created_at)
    VALUES (p_referee_id, v_new - v_referee.balance, 'referral_reward', v_reference_id, v_new, v_now);
  UPDATE games_gamma_wallets SET balance = v_new, updated_at = v_now WHERE id = p_referee_id;
  v_referee_bal := v_new;

  -- Credit referrer (capped) under a row lock.
  SELECT balance INTO v_referrer_bal FROM games_gamma_wallets WHERE id = v_referrer_id FOR UPDATE;
  v_new := GREATEST(v_referrer_bal, LEAST(v_referrer_bal + p_reward, p_max_balance));
  INSERT INTO games_gamma_token_transactions (wallet_id, amount, reason, reference_id, balance_after, created_at)
    VALUES (v_referrer_id, v_new - v_referrer_bal, 'referral_reward', v_reference_id, v_new, v_now);
  UPDATE games_gamma_wallets SET balance = v_new, updated_at = v_now WHERE id = v_referrer_id;

  RETURN jsonb_build_object('status', 'ok', 'reward', p_reward,
                            'balance', v_referee_bal, 'referrer_id', v_referrer_id);
END;
$$;

REVOKE EXECUTE ON FUNCTION games_gamma_set_referral_code(TEXT, TEXT) FROM PUBLIC, anon, authenticated;

REVOKE EXECUTE ON FUNCTION games_gamma_redeem_referral(TEXT, TEXT, INTEGER, INTEGER, INTEGER, BIGINT) FROM PUBLIC, anon, authenticated;
