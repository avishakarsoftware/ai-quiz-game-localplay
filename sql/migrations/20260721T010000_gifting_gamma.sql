-- Spark gifting activation (SPEC-GIFTING) — targeted Supabase migration.
-- Extracted verbatim from the rendered sql/games-schema.sql (do NOT hand-edit the RPC body).
-- Apply to GAMMA first (games_gamma_ prefix), verify, then PROD (games_ prefix).
-- After applying: set GIFTING_ENABLED=true and recreate the backend container.
-- Idempotent: CREATE OR REPLACE FUNCTION / REVOKE / GRANT. Depends on the referral migration
-- (wallets.referral_code is the recipient handle) — apply 20260721T000000_referrals.sql first.

CREATE OR REPLACE FUNCTION games_gamma_gift_sparks(
  p_sender_id TEXT,
  p_code TEXT,
  p_amount INTEGER,
  p_key TEXT,
  p_min_amount INTEGER,
  p_max_amount INTEGER,
  p_max_per_day INTEGER,
  p_max_tokens_per_day INTEGER,
  p_max_balance INTEGER,
  p_since BIGINT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_recipient_id TEXT;
  v_recipient_bal INTEGER;
  v_sender_bal INTEGER;
  v_reference_id TEXT;
  v_prior INTEGER;
  v_count INTEGER;
  v_sum INTEGER;
  v_new_sender INTEGER;
  v_new_recipient INTEGER;
  v_now BIGINT := EXTRACT(EPOCH FROM NOW())::BIGINT;
BEGIN
  IF p_amount < p_min_amount OR p_amount > p_max_amount THEN
    RETURN jsonb_build_object('status', 'invalid_amount');
  END IF;

  SELECT id, balance INTO v_recipient_id, v_recipient_bal
  FROM games_gamma_wallets WHERE referral_code = p_code;
  IF v_recipient_id IS NULL THEN
    RETURN jsonb_build_object('status', 'invalid_code');
  END IF;
  IF v_recipient_id = p_sender_id THEN
    RETURN jsonb_build_object('status', 'self_gift');
  END IF;

  v_reference_id := CASE WHEN COALESCE(p_key, '') <> '' THEN 'gift:' || p_sender_id || ':' || p_key ELSE '' END;

  -- Idempotent replay: an identical keyed send returns its prior result, nothing moves.
  IF v_reference_id <> '' THEN
    SELECT balance_after INTO v_prior FROM games_gamma_token_transactions
      WHERE reference_id = v_reference_id AND wallet_id = p_sender_id AND reason = 'gift_sent' LIMIT 1;
    IF FOUND THEN
      RETURN jsonb_build_object('status', 'ok', 'duplicate', true, 'amount', p_amount,
                                'new_balance', v_prior, 'recipient_id', v_recipient_id);
    END IF;
  END IF;

  -- Lock the sender row for the debit.
  SELECT balance INTO v_sender_bal FROM games_gamma_wallets WHERE id = p_sender_id FOR UPDATE;
  v_sender_bal := COALESCE(v_sender_bal, 0);
  IF v_sender_bal < p_amount THEN
    RETURN jsonb_build_object('status', 'insufficient', 'new_balance', v_sender_bal);
  END IF;

  SELECT COUNT(*), COALESCE(-SUM(amount), 0) INTO v_count, v_sum
    FROM games_gamma_token_transactions
    WHERE wallet_id = p_sender_id AND reason = 'gift_sent' AND created_at >= p_since;
  IF v_count >= p_max_per_day OR v_sum + p_amount > p_max_tokens_per_day THEN
    RETURN jsonb_build_object('status', 'daily_cap', 'new_balance', v_sender_bal);
  END IF;

  -- Re-read the recipient under a lock; reject if it can't hold the full gift (conserve sparks).
  SELECT balance INTO v_recipient_bal FROM games_gamma_wallets WHERE id = v_recipient_id FOR UPDATE;
  IF v_recipient_bal + p_amount > p_max_balance THEN
    RETURN jsonb_build_object('status', 'recipient_full', 'new_balance', v_sender_bal);
  END IF;

  v_new_sender := v_sender_bal - p_amount;
  UPDATE games_gamma_wallets SET balance = v_new_sender, updated_at = v_now WHERE id = p_sender_id;
  INSERT INTO games_gamma_token_transactions (wallet_id, amount, reason, reference_id, balance_after, created_at)
    VALUES (p_sender_id, -p_amount, 'gift_sent', NULLIF(v_reference_id, ''), v_new_sender, v_now);

  v_new_recipient := v_recipient_bal + p_amount;
  UPDATE games_gamma_wallets SET balance = v_new_recipient, updated_at = v_now WHERE id = v_recipient_id;
  INSERT INTO games_gamma_token_transactions (wallet_id, amount, reason, reference_id, balance_after, created_at)
    VALUES (v_recipient_id, p_amount, 'gift_received', NULLIF(v_reference_id, ''), v_new_recipient, v_now);

  RETURN jsonb_build_object('status', 'ok', 'amount', p_amount,
                            'new_balance', v_new_sender, 'recipient_id', v_recipient_id);
END;
$$;

REVOKE EXECUTE ON FUNCTION games_gamma_gift_sparks(TEXT, TEXT, INTEGER, TEXT, INTEGER, INTEGER, INTEGER, INTEGER, INTEGER, BIGINT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION games_gamma_gift_sparks(TEXT, TEXT, INTEGER, TEXT, INTEGER, INTEGER, INTEGER, INTEGER, INTEGER, BIGINT) TO service_role;
