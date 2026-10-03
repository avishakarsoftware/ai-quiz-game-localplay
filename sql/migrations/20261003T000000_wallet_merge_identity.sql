-- Preserve and transfer purchase entitlement on drained guest sign-in; enforce one merge per target.
-- Safe to reapply; replaces only merge_wallet and does not rewrite existing wallet data.

CREATE OR REPLACE FUNCTION games_merge_wallet(
  p_from_id TEXT,
  p_to_id TEXT,
  p_max_balance INTEGER DEFAULT 1000
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_from RECORD;
  v_to RECORD;
  v_existing_merges INTEGER;
  v_transfer INTEGER;
  v_purchased INTEGER;
  v_last_merge BIGINT;
  v_actual_transfer INTEGER;
  v_new_to_balance INTEGER;
  v_now BIGINT := EXTRACT(EPOCH FROM NOW())::BIGINT;
BEGIN
  IF p_from_id = p_to_id THEN
    RETURN jsonb_build_object('merged', false, 'reason', 'same_wallet');
  END IF;

  -- Serialize the target eligibility check even when no target wallet exists yet.
  -- Row locks below still protect balances against purchases and spends.
  PERFORM pg_advisory_xact_lock(hashtext('games_merge_wallet'), hashtext(p_to_id));

  SELECT COUNT(*) INTO v_existing_merges
  FROM games_token_transactions
  WHERE wallet_id = p_to_id AND reason = 'merge_in';

  IF v_existing_merges >= 1 THEN
    RETURN jsonb_build_object('merged', false, 'reason', 'target_already_merged');
  END IF;

  IF EXISTS (
    SELECT 1 FROM games_token_transactions
    WHERE wallet_id = p_from_id AND reason = 'merge_out' AND reference_id = p_to_id
  ) THEN
    RETURN jsonb_build_object('merged', false, 'reason', 'already_merged');
  END IF;

  SELECT * INTO v_from
  FROM games_wallets
  WHERE id = p_from_id
  FOR UPDATE;

  v_purchased := COALESCE(v_from.lifetime_purchased, 0);
  SELECT MAX(id) INTO v_last_merge FROM games_token_transactions
  WHERE wallet_id = p_from_id AND reason = 'merge_out';
  IF v_last_merge IS NOT NULL THEN
    -- Old versions retained cumulative paid history on the source. Transfer only
    -- later purchases; transaction IDs preserve order even within the same second.
    SELECT LEAST(v_purchased, GREATEST(COALESCE(SUM(amount), 0), 0)) INTO v_purchased
    FROM games_token_transactions
    WHERE wallet_id = p_from_id AND reason = 'purchase' AND id > v_last_merge;
  END IF;

  IF v_from.id IS NULL OR (v_from.balance = 0 AND v_purchased = 0) THEN
    RETURN jsonb_build_object('merged', false, 'reason', 'empty_source');
  END IF;

  INSERT INTO games_wallets
    (id, balance, lifetime_purchased, last_daily_bonus_date, ads_watched_today, ads_watched_date, created_at, updated_at)
  VALUES
    (p_to_id, 0, 0, '', 0, '', v_now, v_now)
  ON CONFLICT (id) DO NOTHING;

  SELECT * INTO v_to
  FROM games_wallets
  WHERE id = p_to_id
  FOR UPDATE;

  v_transfer := v_from.balance;
  v_new_to_balance := GREATEST(v_to.balance, LEAST(v_to.balance + v_transfer, p_max_balance));
  v_actual_transfer := v_new_to_balance - v_to.balance;

  UPDATE games_wallets
  SET balance = 0, lifetime_purchased = 0, updated_at = v_now
  WHERE id = p_from_id;

  UPDATE games_wallets
  SET balance = v_new_to_balance,
      lifetime_purchased = lifetime_purchased + v_purchased,
      updated_at = v_now
  WHERE id = p_to_id;

  INSERT INTO games_token_transactions
    (wallet_id, amount, reason, reference_id, balance_after, created_at)
  VALUES
    (p_from_id, -v_transfer, 'merge_out', p_to_id, 0, v_now),
    (p_to_id, v_actual_transfer, 'merge_in', p_from_id, v_new_to_balance, v_now);

  RETURN jsonb_build_object(
    'merged', true,
    'transferred', v_actual_transfer,
    'lost_to_cap', v_transfer - v_actual_transfer,
    'balance', v_new_to_balance
  );
END;
$$;

REVOKE EXECUTE ON FUNCTION games_merge_wallet(TEXT, TEXT, INTEGER) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION games_merge_wallet(TEXT, TEXT, INTEGER) TO service_role;
