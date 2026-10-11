-- Account deletion removes owned saved quiz rows and media metadata atomically.
-- Apply to gamma first; source preparation alone does not change hosted databases.
-- Retains the financial ledger and does not delete IONOS bytes.

CREATE OR REPLACE FUNCTION games_gamma_delete_account(
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
  IF EXISTS (SELECT 1 FROM games_gamma_deleted_accounts WHERE user_id = p_user_id) THEN
    RETURN jsonb_build_object('deleted', false, 'reason', 'already_deleted');
  END IF;

  -- wallet id == user id for signed-in users (see tokens.get_wallet_id), so the Sparks
  -- balance and authored content hang off this same value.
  DELETE FROM games_gamma_generated_content WHERE wallet_id = p_user_id;
  DELETE FROM games_gamma_quiz_questions WHERE pack_id IN
    (SELECT id FROM games_gamma_quiz_packs WHERE owner_wallet_id = p_user_id);
  DELETE FROM games_gamma_quiz_packs WHERE owner_wallet_id = p_user_id;
  -- Metadata removal does not physically delete public IONOS media bytes.
  DELETE FROM games_gamma_media_assets WHERE owner_wallet_id = p_user_id;
  DELETE FROM games_gamma_wallets WHERE id = p_user_id;
  DELETE FROM games_gamma_entitlements WHERE user_id = p_user_id;
  DELETE FROM games_gamma_device_usage WHERE user_id = p_user_id;
  DELETE FROM games_gamma_users WHERE id = p_user_id;

  INSERT INTO games_gamma_deleted_accounts (user_id, deleted_at)
  VALUES (p_user_id, v_now);

  RETURN jsonb_build_object('deleted', true);
END;
$$;

REVOKE EXECUTE ON FUNCTION games_gamma_delete_account(TEXT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION games_gamma_delete_account(TEXT) TO service_role;
NOTIFY pgrst, 'reload schema';
