-- Verify only disposable synthetic rows, then delete them in this same transaction.
-- No existing wallets, packs, or questions are edited. Run after both 20261003 migrations.
DO $$
DECLARE
  v_suffix TEXT := md5(random()::TEXT || clock_timestamp()::TEXT);
  v_device TEXT := 'review_device_' || v_suffix;
  v_user TEXT := 'review_user_' || v_suffix;
  v_legacy_user TEXT := 'review_legacy_user_' || v_suffix;
  v_owner TEXT := 'review_owner_' || v_suffix;
  v_stranger TEXT := 'review_stranger_' || v_suffix;
  v_pack TEXT := 'review_pack_' || v_suffix;
  v_questions JSONB := '[{"text":"Review question","options":["A","B"],"answer_index":0}]'::JSONB;
  v_paid INTEGER;
  v_balance INTEGER;
  v_count INTEGER;
  v_title TEXT;
BEGIN
  IF position('pg_advisory_xact_lock' in pg_get_functiondef('games_merge_wallet(text,text,integer)'::regprocedure)) = 0 THEN
    RAISE EXCEPTION 'merge_wallet target serialization migration is missing';
  END IF;
  IF has_function_privilege('anon', 'games_save_quiz_pack(text,text,text,jsonb)', 'EXECUTE')
     OR has_function_privilege('authenticated', 'games_save_quiz_pack(text,text,text,jsonb)', 'EXECUTE')
     OR NOT has_function_privilege('service_role', 'games_save_quiz_pack(text,text,text,jsonb)', 'EXECUTE') THEN
    RAISE EXCEPTION 'save_quiz_pack RPC permissions are incorrect';
  END IF;

  PERFORM games_ensure_wallet(v_device, false, 0);
  PERFORM games_credit_purchase(v_device, 110, 'review_payment_' || v_suffix, '', 1000);
  PERFORM games_debit_tokens(v_device, 110, 'review_spend', NULL);
  PERFORM games_merge_wallet(v_device, v_user, 1000);
  PERFORM games_merge_wallet(v_device, v_user, 1000);
  SELECT balance, lifetime_purchased INTO v_balance, v_paid FROM games_wallets WHERE id = v_user;
  IF v_balance IS DISTINCT FROM 0 OR v_paid IS DISTINCT FROM 110 THEN
    RAISE EXCEPTION 'Drained guest purchase entitlement or merge idempotency failed';
  END IF;

  SELECT lifetime_purchased INTO v_paid FROM games_wallets WHERE id = v_device;
  IF v_paid IS DISTINCT FROM 0 THEN
    RAISE EXCEPTION 'Guest purchase entitlement was cloned rather than transferred';
  END IF;

  -- Reproduce history retained by a pre-fix source, then distinguish new purchases
  -- using ledger IDs even if all synthetic transactions share one timestamp.
  UPDATE games_wallets SET lifetime_purchased = 110 WHERE id = v_device;
  PERFORM games_merge_wallet(v_device, v_legacy_user, 1000);
  IF EXISTS (SELECT 1 FROM games_wallets WHERE id = v_legacy_user) THEN
    RAISE EXCEPTION 'Legacy paid history was duplicated into a second account';
  END IF;
  PERFORM games_credit_purchase(v_device, 50, 'review_fresh_payment_' || v_suffix, '', 1000);
  PERFORM games_debit_tokens(v_device, 50, 'review_spend', NULL);
  UPDATE games_token_transactions SET created_at = 123456 WHERE wallet_id = v_device;
  PERFORM games_merge_wallet(v_device, v_legacy_user, 1000);
  SELECT lifetime_purchased INTO v_paid FROM games_wallets WHERE id = v_legacy_user;
  IF v_paid IS DISTINCT FROM 50 THEN
    RAISE EXCEPTION 'Legacy source failed to transfer only fresh purchase credits';
  END IF;

  PERFORM games_save_quiz_pack(v_owner, v_pack, 'Original', v_questions);
  BEGIN
    PERFORM games_save_quiz_pack(v_stranger, v_pack, 'Foreign overwrite', v_questions);
    RAISE EXCEPTION 'Foreign quiz owner was accepted';
  EXCEPTION WHEN insufficient_privilege THEN NULL;
  END;
  BEGIN
    PERFORM games_save_quiz_pack(v_owner, v_pack, 'Broken',
      '[{"text":"Invalid","options":["A","B"],"answer_index":-1}]'::JSONB);
    RAISE EXCEPTION 'Invalid question unexpectedly accepted';
  EXCEPTION WHEN check_violation THEN NULL;
  END;
  SELECT title, question_count INTO v_title, v_count FROM games_quiz_packs WHERE id = v_pack AND owner_wallet_id = v_owner;
  IF v_title IS DISTINCT FROM 'Original' OR v_count IS DISTINCT FROM 1
     OR (SELECT count(*) FROM games_quiz_questions WHERE pack_id = v_pack AND text = 'Review question') <> 1 THEN
    RAISE EXCEPTION 'Failed quiz save changed previous content';
  END IF;

  DELETE FROM games_quiz_packs WHERE id = v_pack AND owner_wallet_id = v_owner;
  DELETE FROM games_token_transactions WHERE wallet_id IN (v_device, v_user, v_legacy_user);
  DELETE FROM games_wallets WHERE id IN (v_device, v_user, v_legacy_user);
  RAISE NOTICE 'Persistence review checks passed; synthetic data removed';
END;
$$;
