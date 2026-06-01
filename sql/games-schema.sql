-- LocalPlay Supabase schema template.
-- Render with scripts/render-supabase-sql.py.
-- Prefix examples:
--   prod:  games_
--   gamma: games_gamma_

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

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

CREATE TABLE IF NOT EXISTS games_device_usage (
  device_id TEXT PRIMARY KEY,
  user_id TEXT,
  games_used_free INTEGER NOT NULL DEFAULT 0 CHECK (games_used_free >= 0),
  window_start BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_games_device_usage_user
  ON games_device_usage(user_id)
  WHERE user_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS games_request_log (
  idempotency_key TEXT PRIMARY KEY,
  device_id TEXT NOT NULL,
  result_id TEXT,
  created_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_games_request_log_created
  ON games_request_log(created_at);

CREATE TABLE IF NOT EXISTS games_pending_tokens (
  device_id TEXT PRIMARY KEY,
  token TEXT NOT NULL,
  created_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_games_pending_tokens_created
  ON games_pending_tokens(created_at);

CREATE TABLE IF NOT EXISTS games_webhook_events (
  event_id TEXT PRIMARY KEY,
  processed_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_games_webhook_events_processed
  ON games_webhook_events(processed_at);

CREATE TABLE IF NOT EXISTS games_generated_content (
  id TEXT PRIMARY KEY,
  wallet_id TEXT NOT NULL,
  content_type TEXT NOT NULL CHECK (content_type IN ('quiz', 'mlt', 'drawing')),
  title TEXT NOT NULL DEFAULT '',
  payload JSONB NOT NULL,
  prompt TEXT,
  model TEXT,
  provider TEXT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT
);

ALTER TABLE games_generated_content
  DROP CONSTRAINT IF EXISTS games_generated_content_content_type_check;
ALTER TABLE games_generated_content
  ADD CONSTRAINT games_generated_content_content_type_check
  CHECK (content_type IN ('quiz', 'mlt', 'drawing'));

CREATE INDEX IF NOT EXISTS idx_games_generated_content_wallet
  ON games_generated_content(wallet_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_games_generated_content_type
  ON games_generated_content(content_type, created_at DESC);

CREATE TABLE IF NOT EXISTS games_quiz_packs (
  id TEXT PRIMARY KEY,
  owner_wallet_id TEXT NOT NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft', 'ready', 'archived', 'deleted')),
  question_count INTEGER NOT NULL DEFAULT 0 CHECK (question_count >= 0),
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  deleted_at BIGINT
);

CREATE INDEX IF NOT EXISTS idx_games_quiz_packs_owner_updated
  ON games_quiz_packs(owner_wallet_id, updated_at DESC)
  WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS games_quiz_questions (
  id TEXT PRIMARY KEY,
  pack_id TEXT NOT NULL REFERENCES games_quiz_packs(id) ON DELETE CASCADE,
  position INTEGER NOT NULL CHECK (position >= 0),
  question_type TEXT NOT NULL DEFAULT 'multiple_choice'
    CHECK (question_type IN ('multiple_choice', 'true_false')),
  text TEXT NOT NULL,
  options JSONB NOT NULL,
  answer_index INTEGER NOT NULL CHECK (answer_index >= 0),
  image_asset_id TEXT,
  image_url TEXT,
  image_alt TEXT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_games_quiz_questions_pack_position
  ON games_quiz_questions(pack_id, position);

CREATE TABLE IF NOT EXISTS games_media_assets (
  id TEXT PRIMARY KEY,
  owner_wallet_id TEXT NOT NULL,
  storage_backend TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  public_url TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'ready', 'failed', 'deleted')),
  mime_type TEXT NOT NULL,
  bytes INTEGER NOT NULL DEFAULT 0 CHECK (bytes >= 0),
  alt_text TEXT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_games_media_assets_owner_updated
  ON games_media_assets(owner_wallet_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS games_game_sessions (
  id TEXT PRIMARY KEY,
  host_app TEXT NOT NULL,
  external_container_id TEXT NOT NULL,
  external_container_type TEXT NOT NULL DEFAULT '',
  external_container_title TEXT NOT NULL DEFAULT '',
  external_host_user_id TEXT NOT NULL DEFAULT '',
  external_host_display_name TEXT NOT NULL DEFAULT '',
  game_type TEXT NOT NULL,
  game_id TEXT NOT NULL DEFAULT '',
  game_title TEXT NOT NULL DEFAULT '',
  room_code TEXT NOT NULL,
  organizer_token TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'lobby'
    CHECK (status IN ('lobby', 'active', 'paused', 'complete', 'expired', 'cancelled', 'superseded')),
  joinable BOOLEAN NOT NULL DEFAULT TRUE,
  closed_reason TEXT,
  closed_message TEXT,
  superseded_by_session_id TEXT,
  launch_routes JSONB NOT NULL DEFAULT '{}'::jsonb,
  feed_card JSONB NOT NULL DEFAULT '{}'::jsonb,
  result_summary JSONB,
  created_at BIGINT NOT NULL,
  started_at BIGINT,
  completed_at BIGINT,
  expires_at BIGINT NOT NULL,
  last_activity_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_games_game_sessions_external_active
  ON games_game_sessions(host_app, external_container_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_games_game_sessions_room
  ON games_game_sessions(room_code);

CREATE TABLE IF NOT EXISTS games_host_app_catalog_flags (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  environment TEXT NOT NULL,
  host_app TEXT NOT NULL,
  game_id TEXT NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT FALSE,
  status TEXT NOT NULL DEFAULT 'disabled'
    CHECK (status IN ('live', 'gamma', 'planned', 'disabled')),
  allowlist_party_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  allowlist_external_user_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  rollout_percentage INTEGER
    CHECK (rollout_percentage IS NULL OR (rollout_percentage >= 0 AND rollout_percentage <= 100)),
  capability_overrides JSONB NOT NULL DEFAULT '{}'::jsonb,
  notes TEXT NOT NULL DEFAULT '',
  updated_by TEXT NOT NULL DEFAULT '',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (environment, host_app, game_id)
);

CREATE INDEX IF NOT EXISTS idx_games_host_app_catalog_flags_lookup
  ON games_host_app_catalog_flags(environment, host_app, game_id);

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

-- ---------------------------------------------------------------------------
-- Row-level security. Backend uses service-role only; no anon/client policies.
-- ---------------------------------------------------------------------------

ALTER TABLE games_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE games_wallets ENABLE ROW LEVEL SECURITY;
ALTER TABLE games_token_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE games_entitlements ENABLE ROW LEVEL SECURITY;
ALTER TABLE games_device_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE games_request_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE games_pending_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE games_webhook_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE games_generated_content ENABLE ROW LEVEL SECURITY;
ALTER TABLE games_quiz_packs ENABLE ROW LEVEL SECURITY;
ALTER TABLE games_quiz_questions ENABLE ROW LEVEL SECURITY;
ALTER TABLE games_media_assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE games_game_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE games_host_app_catalog_flags ENABLE ROW LEVEL SECURITY;
ALTER TABLE games_game_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE games_rejections ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS service_role_all_games_users ON games_users;
CREATE POLICY service_role_all_games_users ON games_users
  FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS service_role_all_games_wallets ON games_wallets;
CREATE POLICY service_role_all_games_wallets ON games_wallets
  FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS service_role_all_games_token_transactions ON games_token_transactions;
CREATE POLICY service_role_all_games_token_transactions ON games_token_transactions
  FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS service_role_all_games_entitlements ON games_entitlements;
CREATE POLICY service_role_all_games_entitlements ON games_entitlements
  FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS service_role_all_games_device_usage ON games_device_usage;
CREATE POLICY service_role_all_games_device_usage ON games_device_usage
  FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS service_role_all_games_request_log ON games_request_log;
CREATE POLICY service_role_all_games_request_log ON games_request_log
  FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS service_role_all_games_pending_tokens ON games_pending_tokens;
CREATE POLICY service_role_all_games_pending_tokens ON games_pending_tokens
  FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS service_role_all_games_webhook_events ON games_webhook_events;
CREATE POLICY service_role_all_games_webhook_events ON games_webhook_events
  FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS service_role_all_games_generated_content ON games_generated_content;
CREATE POLICY service_role_all_games_generated_content ON games_generated_content
  FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS service_role_all_games_quiz_packs ON games_quiz_packs;
CREATE POLICY service_role_all_games_quiz_packs ON games_quiz_packs
  FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS service_role_all_games_quiz_questions ON games_quiz_questions;
CREATE POLICY service_role_all_games_quiz_questions ON games_quiz_questions
  FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS service_role_all_games_media_assets ON games_media_assets;
CREATE POLICY service_role_all_games_media_assets ON games_media_assets
  FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS service_role_all_games_game_sessions ON games_game_sessions;
CREATE POLICY service_role_all_games_game_sessions ON games_game_sessions
  FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS service_role_all_games_host_app_catalog_flags ON games_host_app_catalog_flags;
CREATE POLICY service_role_all_games_host_app_catalog_flags ON games_host_app_catalog_flags
  FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS service_role_all_games_game_history ON games_game_history;
CREATE POLICY service_role_all_games_game_history ON games_game_history
  FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS service_role_all_games_rejections ON games_rejections;
CREATE POLICY service_role_all_games_rejections ON games_rejections
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ---------------------------------------------------------------------------
-- Wallet RPCs. These preserve SQLite BEGIN IMMEDIATE semantics in Postgres.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION games_ensure_wallet(
  p_wallet_id TEXT,
  p_signup_bonus BOOLEAN DEFAULT true,
  p_signup_bonus_amount INTEGER DEFAULT 20
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_wallet RECORD;
  v_bonus INTEGER := 0;
  v_now BIGINT := EXTRACT(EPOCH FROM NOW())::BIGINT;
  v_inserted BOOLEAN := false;
BEGIN
  SELECT * INTO v_wallet
  FROM games_wallets
  WHERE id = p_wallet_id;

  IF v_wallet.id IS NOT NULL THEN
    RETURN to_jsonb(v_wallet);
  END IF;

  IF p_signup_bonus THEN
    v_bonus := GREATEST(p_signup_bonus_amount, 0);
  END IF;

  INSERT INTO games_wallets
    (id, balance, lifetime_purchased, last_daily_bonus_date, ads_watched_today, ads_watched_date, created_at, updated_at)
  VALUES
    (p_wallet_id, v_bonus, 0, '', 0, '', v_now, v_now)
  ON CONFLICT (id) DO NOTHING
  RETURNING * INTO v_wallet;

  IF v_wallet.id IS NOT NULL THEN
    v_inserted := true;
  ELSE
    SELECT * INTO v_wallet
    FROM games_wallets
    WHERE id = p_wallet_id;
  END IF;

  IF v_inserted AND v_bonus > 0 THEN
    INSERT INTO games_token_transactions
      (wallet_id, amount, reason, reference_id, balance_after, created_at)
    VALUES
      (p_wallet_id, v_bonus, 'signup_bonus', NULL, v_bonus, v_now);
  END IF;

  RETURN to_jsonb(v_wallet);
END;
$$;

CREATE OR REPLACE FUNCTION games_debit_tokens(
  p_wallet_id TEXT,
  p_amount INTEGER,
  p_reason TEXT,
  p_reference_id TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_balance INTEGER;
  v_new_balance INTEGER;
  v_now BIGINT := EXTRACT(EPOCH FROM NOW())::BIGINT;
BEGIN
  IF p_amount <= 0 THEN
    RAISE EXCEPTION 'debit amount must be positive';
  END IF;

  SELECT balance INTO v_balance
  FROM games_wallets
  WHERE id = p_wallet_id
  FOR UPDATE;

  IF v_balance IS NULL THEN
    RETURN jsonb_build_object('success', false, 'balance', 0);
  END IF;

  IF v_balance < p_amount THEN
    RETURN jsonb_build_object('success', false, 'balance', v_balance);
  END IF;

  v_new_balance := v_balance - p_amount;

  UPDATE games_wallets
  SET balance = v_new_balance, updated_at = v_now
  WHERE id = p_wallet_id;

  INSERT INTO games_token_transactions
    (wallet_id, amount, reason, reference_id, balance_after, created_at)
  VALUES
    (p_wallet_id, -p_amount, p_reason, NULLIF(p_reference_id, ''), v_new_balance, v_now);

  RETURN jsonb_build_object('success', true, 'balance', v_new_balance);
END;
$$;

CREATE OR REPLACE FUNCTION games_credit_tokens(
  p_wallet_id TEXT,
  p_amount INTEGER,
  p_reason TEXT,
  p_reference_id TEXT DEFAULT NULL,
  p_metadata TEXT DEFAULT '',
  p_max_balance INTEGER DEFAULT 1000
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_balance INTEGER;
  v_new_balance INTEGER;
  v_actual_credit INTEGER;
  v_now BIGINT := EXTRACT(EPOCH FROM NOW())::BIGINT;
BEGIN
  IF p_amount <= 0 THEN
    RAISE EXCEPTION 'credit amount must be positive';
  END IF;

  INSERT INTO games_wallets
    (id, balance, lifetime_purchased, last_daily_bonus_date, ads_watched_today, ads_watched_date, created_at, updated_at)
  VALUES
    (p_wallet_id, 0, 0, '', 0, '', v_now, v_now)
  ON CONFLICT (id) DO NOTHING;

  SELECT balance INTO v_balance
  FROM games_wallets
  WHERE id = p_wallet_id
  FOR UPDATE;

  v_new_balance := GREATEST(v_balance, LEAST(v_balance + p_amount, p_max_balance));
  v_actual_credit := v_new_balance - v_balance;

  IF v_actual_credit <= 0 THEN
    RETURN jsonb_build_object('success', true, 'balance', v_balance, 'credited', 0);
  END IF;

  UPDATE games_wallets
  SET balance = v_new_balance, updated_at = v_now
  WHERE id = p_wallet_id;

  INSERT INTO games_token_transactions
    (wallet_id, amount, reason, reference_id, balance_after, metadata, created_at)
  VALUES
    (p_wallet_id, v_actual_credit, p_reason, NULLIF(p_reference_id, ''), v_new_balance, COALESCE(p_metadata, ''), v_now);

  RETURN jsonb_build_object('success', true, 'balance', v_new_balance, 'credited', v_actual_credit);
END;
$$;

CREATE OR REPLACE FUNCTION games_credit_purchase(
  p_wallet_id TEXT,
  p_amount INTEGER,
  p_reference_id TEXT,
  p_metadata TEXT DEFAULT '',
  p_max_balance INTEGER DEFAULT 1000
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_existing_balance INTEGER;
  v_balance INTEGER;
  v_new_balance INTEGER;
  v_actual_credit INTEGER;
  v_now BIGINT := EXTRACT(EPOCH FROM NOW())::BIGINT;
BEGIN
  IF p_amount <= 0 THEN
    RAISE EXCEPTION 'purchase credit amount must be positive';
  END IF;

  SELECT balance_after INTO v_existing_balance
  FROM games_token_transactions
  WHERE wallet_id = p_wallet_id
    AND reference_id = p_reference_id
    AND reason = 'purchase'
  LIMIT 1;

  IF v_existing_balance IS NOT NULL THEN
    RETURN jsonb_build_object('success', true, 'balance', v_existing_balance, 'duplicate', true);
  END IF;

  INSERT INTO games_wallets
    (id, balance, lifetime_purchased, last_daily_bonus_date, ads_watched_today, ads_watched_date, created_at, updated_at)
  VALUES
    (p_wallet_id, 0, 0, '', 0, '', v_now, v_now)
  ON CONFLICT (id) DO NOTHING;

  SELECT balance INTO v_balance
  FROM games_wallets
  WHERE id = p_wallet_id
  FOR UPDATE;

  v_new_balance := GREATEST(v_balance, LEAST(v_balance + p_amount, p_max_balance));
  v_actual_credit := v_new_balance - v_balance;

  UPDATE games_wallets
  SET balance = v_new_balance,
      lifetime_purchased = lifetime_purchased + GREATEST(v_actual_credit, 0),
      updated_at = v_now
  WHERE id = p_wallet_id;

  INSERT INTO games_token_transactions
    (wallet_id, amount, reason, reference_id, balance_after, metadata, created_at)
  VALUES
    (p_wallet_id, GREATEST(v_actual_credit, 0), 'purchase', p_reference_id, v_new_balance, COALESCE(p_metadata, ''), v_now);

  RETURN jsonb_build_object('success', true, 'balance', v_new_balance, 'duplicate', false);
END;
$$;

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
  v_actual_transfer INTEGER;
  v_new_to_balance INTEGER;
  v_now BIGINT := EXTRACT(EPOCH FROM NOW())::BIGINT;
BEGIN
  IF p_from_id = p_to_id THEN
    RETURN jsonb_build_object('merged', false, 'reason', 'same_wallet');
  END IF;

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

  IF v_from.id IS NULL OR v_from.balance = 0 THEN
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
  SET balance = 0, updated_at = v_now
  WHERE id = p_from_id;

  UPDATE games_wallets
  SET balance = v_new_to_balance,
      lifetime_purchased = lifetime_purchased + v_from.lifetime_purchased,
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

CREATE OR REPLACE FUNCTION games_grant_daily_bonus(
  p_wallet_id TEXT,
  p_today TEXT,
  p_amount INTEGER,
  p_max_balance INTEGER DEFAULT 1000
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_wallet RECORD;
  v_new_balance INTEGER;
  v_actual_bonus INTEGER;
  v_now BIGINT := EXTRACT(EPOCH FROM NOW())::BIGINT;
BEGIN
  SELECT * INTO v_wallet
  FROM games_wallets
  WHERE id = p_wallet_id
  FOR UPDATE;

  IF v_wallet.id IS NULL THEN
    RETURN jsonb_build_object('granted', false, 'balance', 0);
  END IF;

  IF v_wallet.last_daily_bonus_date = p_today THEN
    RETURN jsonb_build_object('granted', false, 'balance', v_wallet.balance);
  END IF;

  v_new_balance := GREATEST(v_wallet.balance, LEAST(v_wallet.balance + p_amount, p_max_balance));
  v_actual_bonus := v_new_balance - v_wallet.balance;

  UPDATE games_wallets
  SET balance = v_new_balance,
      last_daily_bonus_date = p_today,
      ads_watched_today = 0,
      ads_watched_date = p_today,
      updated_at = v_now
  WHERE id = p_wallet_id;

  IF v_actual_bonus > 0 THEN
    INSERT INTO games_token_transactions
      (wallet_id, amount, reason, reference_id, balance_after, created_at)
    VALUES
      (p_wallet_id, v_actual_bonus, 'daily_bonus', NULL, v_new_balance, v_now);
  END IF;

  RETURN jsonb_build_object('granted', true, 'balance', v_new_balance, 'credited', v_actual_bonus);
END;
$$;

CREATE OR REPLACE FUNCTION games_grant_ad_reward(
  p_wallet_id TEXT,
  p_today TEXT,
  p_amount INTEGER,
  p_max_ads_per_day INTEGER,
  p_max_balance INTEGER DEFAULT 1000
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_wallet RECORD;
  v_ads_today INTEGER;
  v_new_balance INTEGER;
  v_actual_reward INTEGER;
  v_remaining INTEGER;
  v_now BIGINT := EXTRACT(EPOCH FROM NOW())::BIGINT;
BEGIN
  SELECT * INTO v_wallet
  FROM games_wallets
  WHERE id = p_wallet_id
  FOR UPDATE;

  IF v_wallet.id IS NULL THEN
    RETURN jsonb_build_object('granted', false, 'balance', 0, 'ads_remaining', 0);
  END IF;

  IF v_wallet.ads_watched_date = p_today THEN
    v_ads_today := v_wallet.ads_watched_today;
  ELSE
    v_ads_today := 0;
  END IF;

  IF v_ads_today >= p_max_ads_per_day THEN
    RETURN jsonb_build_object('granted', false, 'balance', v_wallet.balance, 'ads_remaining', 0);
  END IF;

  v_new_balance := GREATEST(v_wallet.balance, LEAST(v_wallet.balance + p_amount, p_max_balance));
  v_actual_reward := v_new_balance - v_wallet.balance;
  v_ads_today := v_ads_today + 1;
  v_remaining := GREATEST(p_max_ads_per_day - v_ads_today, 0);

  UPDATE games_wallets
  SET balance = v_new_balance,
      ads_watched_today = v_ads_today,
      ads_watched_date = p_today,
      updated_at = v_now
  WHERE id = p_wallet_id;

  IF v_actual_reward > 0 THEN
    INSERT INTO games_token_transactions
      (wallet_id, amount, reason, reference_id, balance_after, created_at)
    VALUES
      (p_wallet_id, v_actual_reward, 'ad_reward', NULL, v_new_balance, v_now);
  END IF;

  RETURN jsonb_build_object('granted', true, 'balance', v_new_balance, 'ads_remaining', v_remaining);
END;
$$;

-- ---------------------------------------------------------------------------
-- Usage RPCs. These preserve the current one-day rolling free-tier window.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION games_claim_device_usage(
  p_device_id TEXT,
  p_free_tier_limit INTEGER DEFAULT 3
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_usage RECORD;
  v_now BIGINT := EXTRACT(EPOCH FROM NOW())::BIGINT;
  v_window_cutoff BIGINT := v_now - 86400;
BEGIN
  SELECT * INTO v_usage
  FROM games_device_usage
  WHERE device_id = p_device_id
  FOR UPDATE;

  IF v_usage.device_id IS NULL THEN
    INSERT INTO games_device_usage(device_id, games_used_free, window_start)
    VALUES (p_device_id, 1, v_now);
    RETURN jsonb_build_object('allowed', true, 'count_after', 1);
  END IF;

  IF v_usage.window_start <= v_window_cutoff THEN
    UPDATE games_device_usage
    SET games_used_free = 1, window_start = v_now
    WHERE device_id = p_device_id;
    RETURN jsonb_build_object('allowed', true, 'count_after', 1);
  END IF;

  IF v_usage.games_used_free >= p_free_tier_limit THEN
    RETURN jsonb_build_object('allowed', false, 'count_after', v_usage.games_used_free);
  END IF;

  UPDATE games_device_usage
  SET games_used_free = games_used_free + 1
  WHERE device_id = p_device_id;

  RETURN jsonb_build_object('allowed', true, 'count_after', v_usage.games_used_free + 1);
END;
$$;

CREATE OR REPLACE FUNCTION games_claim_user_usage(
  p_user_id TEXT,
  p_device_id TEXT,
  p_free_tier_limit INTEGER DEFAULT 3
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_total INTEGER;
  v_device RECORD;
  v_now BIGINT := EXTRACT(EPOCH FROM NOW())::BIGINT;
  v_window_cutoff BIGINT := v_now - 86400;
BEGIN
  PERFORM pg_advisory_xact_lock(hashtext('games_usage:' || p_user_id));

  PERFORM 1
  FROM games_device_usage
  WHERE user_id = p_user_id
    AND window_start >= v_window_cutoff
  FOR UPDATE;

  SELECT COALESCE(SUM(games_used_free), 0) INTO v_total
  FROM games_device_usage
  WHERE user_id = p_user_id
    AND window_start >= v_window_cutoff;

  IF v_total >= p_free_tier_limit THEN
    RETURN jsonb_build_object('allowed', false, 'count_after', v_total);
  END IF;

  SELECT * INTO v_device
  FROM games_device_usage
  WHERE device_id = p_device_id
  FOR UPDATE;

  IF v_device.device_id IS NULL THEN
    INSERT INTO games_device_usage(device_id, user_id, games_used_free, window_start)
    VALUES (p_device_id, p_user_id, 1, v_now);
  ELSIF v_device.window_start <= v_window_cutoff THEN
    UPDATE games_device_usage
    SET user_id = p_user_id, games_used_free = 1, window_start = v_now
    WHERE device_id = p_device_id;
  ELSE
    UPDATE games_device_usage
    SET user_id = p_user_id, games_used_free = games_used_free + 1
    WHERE device_id = p_device_id;
  END IF;

  RETURN jsonb_build_object('allowed', true, 'count_after', v_total + 1);
END;
$$;

CREATE OR REPLACE FUNCTION games_mark_webhook_processed(p_event_id TEXT)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_now BIGINT := EXTRACT(EPOCH FROM NOW())::BIGINT;
BEGIN
  INSERT INTO games_webhook_events(event_id, processed_at)
  VALUES (p_event_id, v_now)
  ON CONFLICT (event_id) DO NOTHING;

  DELETE FROM games_webhook_events
  WHERE processed_at < v_now - (7 * 86400);

  RETURN true;
END;
$$;

CREATE OR REPLACE FUNCTION games_admin_stats()
RETURNS JSONB
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT jsonb_build_object(
    'wallet_count', (SELECT COUNT(*) FROM games_wallets),
    'total_sparks', (SELECT COALESCE(SUM(balance), 0) FROM games_wallets),
    'paying_users', (SELECT COUNT(*) FROM games_wallets WHERE lifetime_purchased > 0),
    'purchase_count', (SELECT COUNT(*) FROM games_token_transactions WHERE reason = 'purchase'),
    'merge_count', (SELECT COUNT(*) FROM games_token_transactions WHERE reason = 'merge_in'),
    'users_count', (SELECT COUNT(*) FROM games_users)
  );
$$;

-- RPCs are server-only. Supabase service-role bypasses client RLS; anon and
-- authenticated clients must not call these mutation functions directly.
REVOKE EXECUTE ON FUNCTION games_ensure_wallet(TEXT, BOOLEAN, INTEGER) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION games_debit_tokens(TEXT, INTEGER, TEXT, TEXT) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION games_credit_tokens(TEXT, INTEGER, TEXT, TEXT, TEXT, INTEGER) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION games_credit_purchase(TEXT, INTEGER, TEXT, TEXT, INTEGER) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION games_merge_wallet(TEXT, TEXT, INTEGER) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION games_grant_daily_bonus(TEXT, TEXT, INTEGER, INTEGER) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION games_grant_ad_reward(TEXT, TEXT, INTEGER, INTEGER, INTEGER) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION games_claim_device_usage(TEXT, INTEGER) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION games_claim_user_usage(TEXT, TEXT, INTEGER) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION games_mark_webhook_processed(TEXT) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION games_admin_stats() FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION games_ensure_wallet(TEXT, BOOLEAN, INTEGER) TO service_role;
GRANT EXECUTE ON FUNCTION games_debit_tokens(TEXT, INTEGER, TEXT, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION games_credit_tokens(TEXT, INTEGER, TEXT, TEXT, TEXT, INTEGER) TO service_role;
GRANT EXECUTE ON FUNCTION games_credit_purchase(TEXT, INTEGER, TEXT, TEXT, INTEGER) TO service_role;
GRANT EXECUTE ON FUNCTION games_merge_wallet(TEXT, TEXT, INTEGER) TO service_role;
GRANT EXECUTE ON FUNCTION games_grant_daily_bonus(TEXT, TEXT, INTEGER, INTEGER) TO service_role;
GRANT EXECUTE ON FUNCTION games_grant_ad_reward(TEXT, TEXT, INTEGER, INTEGER, INTEGER) TO service_role;
GRANT EXECUTE ON FUNCTION games_claim_device_usage(TEXT, INTEGER) TO service_role;
GRANT EXECUTE ON FUNCTION games_claim_user_usage(TEXT, TEXT, INTEGER) TO service_role;
GRANT EXECUTE ON FUNCTION games_mark_webhook_processed(TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION games_admin_stats() TO service_role;
