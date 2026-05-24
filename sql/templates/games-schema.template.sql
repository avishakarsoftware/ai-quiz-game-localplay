-- LocalPlay Supabase schema template.
-- Render with scripts/render-supabase-sql.py.
-- Prefix examples:
--   prod:  games_
--   gamma: games_gamma_

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS __PREFIX__users (
  id TEXT PRIMARY KEY,
  provider TEXT NOT NULL CHECK (provider IN ('google', 'apple')),
  provider_subject_id TEXT NOT NULL,
  email TEXT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx___PREFIX__users_provider_subject
  ON __PREFIX__users(provider, provider_subject_id);
CREATE INDEX IF NOT EXISTS idx___PREFIX__users_email
  ON __PREFIX__users(email);

CREATE TABLE IF NOT EXISTS __PREFIX__wallets (
  id TEXT PRIMARY KEY,
  balance INTEGER NOT NULL DEFAULT 0 CHECK (balance >= 0),
  lifetime_purchased INTEGER NOT NULL DEFAULT 0 CHECK (lifetime_purchased >= 0),
  last_daily_bonus_date TEXT NOT NULL DEFAULT '',
  ads_watched_today INTEGER NOT NULL DEFAULT 0 CHECK (ads_watched_today >= 0),
  ads_watched_date TEXT NOT NULL DEFAULT '',
  created_at BIGINT NOT NULL,
  updated_at BIGINT
);

CREATE INDEX IF NOT EXISTS idx___PREFIX__wallets_purchased
  ON __PREFIX__wallets(lifetime_purchased)
  WHERE lifetime_purchased > 0;

CREATE TABLE IF NOT EXISTS __PREFIX__token_transactions (
  id BIGSERIAL PRIMARY KEY,
  wallet_id TEXT NOT NULL REFERENCES __PREFIX__wallets(id) ON DELETE CASCADE,
  amount INTEGER NOT NULL,
  reason TEXT NOT NULL,
  reference_id TEXT,
  balance_after INTEGER NOT NULL,
  metadata TEXT NOT NULL DEFAULT '',
  created_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx___PREFIX__txn_wallet
  ON __PREFIX__token_transactions(wallet_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx___PREFIX__txn_reference
  ON __PREFIX__token_transactions(reference_id)
  WHERE reference_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx___PREFIX__txn_reason_reference
  ON __PREFIX__token_transactions(reason, reference_id)
  WHERE reference_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx___PREFIX__purchase_once
  ON __PREFIX__token_transactions(wallet_id, reference_id, reason)
  WHERE reference_id IS NOT NULL AND reason = 'purchase';

CREATE TABLE IF NOT EXISTS __PREFIX__entitlements (
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

CREATE UNIQUE INDEX IF NOT EXISTS idx___PREFIX__entitlements_stripe
  ON __PREFIX__entitlements(stripe_session_id)
  WHERE stripe_session_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx___PREFIX__entitlements_apple
  ON __PREFIX__entitlements(apple_transaction_id)
  WHERE apple_transaction_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx___PREFIX__entitlements_google
  ON __PREFIX__entitlements(google_order_id)
  WHERE google_order_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx___PREFIX__entitlements_user_status
  ON __PREFIX__entitlements(user_id, status)
  WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx___PREFIX__entitlements_device_status
  ON __PREFIX__entitlements(device_id, status);

CREATE TABLE IF NOT EXISTS __PREFIX__device_usage (
  device_id TEXT PRIMARY KEY,
  user_id TEXT,
  games_used_free INTEGER NOT NULL DEFAULT 0 CHECK (games_used_free >= 0),
  window_start BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx___PREFIX__device_usage_user
  ON __PREFIX__device_usage(user_id)
  WHERE user_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS __PREFIX__request_log (
  idempotency_key TEXT PRIMARY KEY,
  device_id TEXT NOT NULL,
  result_id TEXT,
  created_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx___PREFIX__request_log_created
  ON __PREFIX__request_log(created_at);

CREATE TABLE IF NOT EXISTS __PREFIX__pending_tokens (
  device_id TEXT PRIMARY KEY,
  token TEXT NOT NULL,
  created_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx___PREFIX__pending_tokens_created
  ON __PREFIX__pending_tokens(created_at);

CREATE TABLE IF NOT EXISTS __PREFIX__webhook_events (
  event_id TEXT PRIMARY KEY,
  processed_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx___PREFIX__webhook_events_processed
  ON __PREFIX__webhook_events(processed_at);

CREATE TABLE IF NOT EXISTS __PREFIX__generated_content (
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

ALTER TABLE __PREFIX__generated_content
  DROP CONSTRAINT IF EXISTS __PREFIX__generated_content_content_type_check;
ALTER TABLE __PREFIX__generated_content
  ADD CONSTRAINT __PREFIX__generated_content_content_type_check
  CHECK (content_type IN ('quiz', 'mlt', 'drawing'));

CREATE INDEX IF NOT EXISTS idx___PREFIX__generated_content_wallet
  ON __PREFIX__generated_content(wallet_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx___PREFIX__generated_content_type
  ON __PREFIX__generated_content(content_type, created_at DESC);

CREATE TABLE IF NOT EXISTS __PREFIX__quiz_packs (
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

CREATE INDEX IF NOT EXISTS idx___PREFIX__quiz_packs_owner_updated
  ON __PREFIX__quiz_packs(owner_wallet_id, updated_at DESC)
  WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS __PREFIX__quiz_questions (
  id TEXT PRIMARY KEY,
  pack_id TEXT NOT NULL REFERENCES __PREFIX__quiz_packs(id) ON DELETE CASCADE,
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

CREATE INDEX IF NOT EXISTS idx___PREFIX__quiz_questions_pack_position
  ON __PREFIX__quiz_questions(pack_id, position);

CREATE TABLE IF NOT EXISTS __PREFIX__media_assets (
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

CREATE INDEX IF NOT EXISTS idx___PREFIX__media_assets_owner_updated
  ON __PREFIX__media_assets(owner_wallet_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS __PREFIX__game_sessions (
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

CREATE INDEX IF NOT EXISTS idx___PREFIX__game_sessions_external_active
  ON __PREFIX__game_sessions(host_app, external_container_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx___PREFIX__game_sessions_room
  ON __PREFIX__game_sessions(room_code);

CREATE TABLE IF NOT EXISTS __PREFIX__game_history (
  id BIGSERIAL PRIMARY KEY,
  room_code TEXT NOT NULL,
  wallet_id TEXT NOT NULL,
  game_type TEXT NOT NULL DEFAULT 'quiz',
  game_title TEXT NOT NULL DEFAULT '',
  summary JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx___PREFIX__game_history_wallet
  ON __PREFIX__game_history(wallet_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx___PREFIX__game_history_room
  ON __PREFIX__game_history(room_code, created_at DESC);

CREATE TABLE IF NOT EXISTS __PREFIX__rejections (
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

CREATE INDEX IF NOT EXISTS idx___PREFIX__rejections_created
  ON __PREFIX__rejections(created_at DESC);
CREATE INDEX IF NOT EXISTS idx___PREFIX__rejections_reason
  ON __PREFIX__rejections(reason, created_at DESC);

-- ---------------------------------------------------------------------------
-- Row-level security. Backend uses service-role only; no anon/client policies.
-- ---------------------------------------------------------------------------

ALTER TABLE __PREFIX__users ENABLE ROW LEVEL SECURITY;
ALTER TABLE __PREFIX__wallets ENABLE ROW LEVEL SECURITY;
ALTER TABLE __PREFIX__token_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE __PREFIX__entitlements ENABLE ROW LEVEL SECURITY;
ALTER TABLE __PREFIX__device_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE __PREFIX__request_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE __PREFIX__pending_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE __PREFIX__webhook_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE __PREFIX__generated_content ENABLE ROW LEVEL SECURITY;
ALTER TABLE __PREFIX__quiz_packs ENABLE ROW LEVEL SECURITY;
ALTER TABLE __PREFIX__quiz_questions ENABLE ROW LEVEL SECURITY;
ALTER TABLE __PREFIX__media_assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE __PREFIX__game_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE __PREFIX__game_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE __PREFIX__rejections ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS service_role_all___PREFIX__users ON __PREFIX__users;
CREATE POLICY service_role_all___PREFIX__users ON __PREFIX__users
  FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS service_role_all___PREFIX__wallets ON __PREFIX__wallets;
CREATE POLICY service_role_all___PREFIX__wallets ON __PREFIX__wallets
  FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS service_role_all___PREFIX__token_transactions ON __PREFIX__token_transactions;
CREATE POLICY service_role_all___PREFIX__token_transactions ON __PREFIX__token_transactions
  FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS service_role_all___PREFIX__entitlements ON __PREFIX__entitlements;
CREATE POLICY service_role_all___PREFIX__entitlements ON __PREFIX__entitlements
  FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS service_role_all___PREFIX__device_usage ON __PREFIX__device_usage;
CREATE POLICY service_role_all___PREFIX__device_usage ON __PREFIX__device_usage
  FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS service_role_all___PREFIX__request_log ON __PREFIX__request_log;
CREATE POLICY service_role_all___PREFIX__request_log ON __PREFIX__request_log
  FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS service_role_all___PREFIX__pending_tokens ON __PREFIX__pending_tokens;
CREATE POLICY service_role_all___PREFIX__pending_tokens ON __PREFIX__pending_tokens
  FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS service_role_all___PREFIX__webhook_events ON __PREFIX__webhook_events;
CREATE POLICY service_role_all___PREFIX__webhook_events ON __PREFIX__webhook_events
  FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS service_role_all___PREFIX__generated_content ON __PREFIX__generated_content;
CREATE POLICY service_role_all___PREFIX__generated_content ON __PREFIX__generated_content
  FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS service_role_all___PREFIX__quiz_packs ON __PREFIX__quiz_packs;
CREATE POLICY service_role_all___PREFIX__quiz_packs ON __PREFIX__quiz_packs
  FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS service_role_all___PREFIX__quiz_questions ON __PREFIX__quiz_questions;
CREATE POLICY service_role_all___PREFIX__quiz_questions ON __PREFIX__quiz_questions
  FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS service_role_all___PREFIX__media_assets ON __PREFIX__media_assets;
CREATE POLICY service_role_all___PREFIX__media_assets ON __PREFIX__media_assets
  FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS service_role_all___PREFIX__game_sessions ON __PREFIX__game_sessions;
CREATE POLICY service_role_all___PREFIX__game_sessions ON __PREFIX__game_sessions
  FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS service_role_all___PREFIX__game_history ON __PREFIX__game_history;
CREATE POLICY service_role_all___PREFIX__game_history ON __PREFIX__game_history
  FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS service_role_all___PREFIX__rejections ON __PREFIX__rejections;
CREATE POLICY service_role_all___PREFIX__rejections ON __PREFIX__rejections
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ---------------------------------------------------------------------------
-- Wallet RPCs. These preserve SQLite BEGIN IMMEDIATE semantics in Postgres.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION __PREFIX__ensure_wallet(
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
  FROM __PREFIX__wallets
  WHERE id = p_wallet_id;

  IF v_wallet.id IS NOT NULL THEN
    RETURN to_jsonb(v_wallet);
  END IF;

  IF p_signup_bonus THEN
    v_bonus := GREATEST(p_signup_bonus_amount, 0);
  END IF;

  INSERT INTO __PREFIX__wallets
    (id, balance, lifetime_purchased, last_daily_bonus_date, ads_watched_today, ads_watched_date, created_at, updated_at)
  VALUES
    (p_wallet_id, v_bonus, 0, '', 0, '', v_now, v_now)
  ON CONFLICT (id) DO NOTHING
  RETURNING * INTO v_wallet;

  IF v_wallet.id IS NOT NULL THEN
    v_inserted := true;
  ELSE
    SELECT * INTO v_wallet
    FROM __PREFIX__wallets
    WHERE id = p_wallet_id;
  END IF;

  IF v_inserted AND v_bonus > 0 THEN
    INSERT INTO __PREFIX__token_transactions
      (wallet_id, amount, reason, reference_id, balance_after, created_at)
    VALUES
      (p_wallet_id, v_bonus, 'signup_bonus', NULL, v_bonus, v_now);
  END IF;

  RETURN to_jsonb(v_wallet);
END;
$$;

CREATE OR REPLACE FUNCTION __PREFIX__debit_tokens(
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
  FROM __PREFIX__wallets
  WHERE id = p_wallet_id
  FOR UPDATE;

  IF v_balance IS NULL THEN
    RETURN jsonb_build_object('success', false, 'balance', 0);
  END IF;

  IF v_balance < p_amount THEN
    RETURN jsonb_build_object('success', false, 'balance', v_balance);
  END IF;

  v_new_balance := v_balance - p_amount;

  UPDATE __PREFIX__wallets
  SET balance = v_new_balance, updated_at = v_now
  WHERE id = p_wallet_id;

  INSERT INTO __PREFIX__token_transactions
    (wallet_id, amount, reason, reference_id, balance_after, created_at)
  VALUES
    (p_wallet_id, -p_amount, p_reason, NULLIF(p_reference_id, ''), v_new_balance, v_now);

  RETURN jsonb_build_object('success', true, 'balance', v_new_balance);
END;
$$;

CREATE OR REPLACE FUNCTION __PREFIX__credit_tokens(
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

  INSERT INTO __PREFIX__wallets
    (id, balance, lifetime_purchased, last_daily_bonus_date, ads_watched_today, ads_watched_date, created_at, updated_at)
  VALUES
    (p_wallet_id, 0, 0, '', 0, '', v_now, v_now)
  ON CONFLICT (id) DO NOTHING;

  SELECT balance INTO v_balance
  FROM __PREFIX__wallets
  WHERE id = p_wallet_id
  FOR UPDATE;

  v_new_balance := LEAST(v_balance + p_amount, p_max_balance);
  v_actual_credit := v_new_balance - v_balance;

  IF v_actual_credit <= 0 THEN
    RETURN jsonb_build_object('success', true, 'balance', v_balance, 'credited', 0);
  END IF;

  UPDATE __PREFIX__wallets
  SET balance = v_new_balance, updated_at = v_now
  WHERE id = p_wallet_id;

  INSERT INTO __PREFIX__token_transactions
    (wallet_id, amount, reason, reference_id, balance_after, metadata, created_at)
  VALUES
    (p_wallet_id, v_actual_credit, p_reason, NULLIF(p_reference_id, ''), v_new_balance, COALESCE(p_metadata, ''), v_now);

  RETURN jsonb_build_object('success', true, 'balance', v_new_balance, 'credited', v_actual_credit);
END;
$$;

CREATE OR REPLACE FUNCTION __PREFIX__credit_purchase(
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
  FROM __PREFIX__token_transactions
  WHERE wallet_id = p_wallet_id
    AND reference_id = p_reference_id
    AND reason = 'purchase'
  LIMIT 1;

  IF v_existing_balance IS NOT NULL THEN
    RETURN jsonb_build_object('success', true, 'balance', v_existing_balance, 'duplicate', true);
  END IF;

  INSERT INTO __PREFIX__wallets
    (id, balance, lifetime_purchased, last_daily_bonus_date, ads_watched_today, ads_watched_date, created_at, updated_at)
  VALUES
    (p_wallet_id, 0, 0, '', 0, '', v_now, v_now)
  ON CONFLICT (id) DO NOTHING;

  SELECT balance INTO v_balance
  FROM __PREFIX__wallets
  WHERE id = p_wallet_id
  FOR UPDATE;

  v_new_balance := LEAST(v_balance + p_amount, p_max_balance);
  v_actual_credit := v_new_balance - v_balance;

  UPDATE __PREFIX__wallets
  SET balance = v_new_balance,
      lifetime_purchased = lifetime_purchased + GREATEST(v_actual_credit, 0),
      updated_at = v_now
  WHERE id = p_wallet_id;

  INSERT INTO __PREFIX__token_transactions
    (wallet_id, amount, reason, reference_id, balance_after, metadata, created_at)
  VALUES
    (p_wallet_id, GREATEST(v_actual_credit, 0), 'purchase', p_reference_id, v_new_balance, COALESCE(p_metadata, ''), v_now);

  RETURN jsonb_build_object('success', true, 'balance', v_new_balance, 'duplicate', false);
END;
$$;

CREATE OR REPLACE FUNCTION __PREFIX__merge_wallet(
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
  FROM __PREFIX__token_transactions
  WHERE wallet_id = p_to_id AND reason = 'merge_in';

  IF v_existing_merges >= 1 THEN
    RETURN jsonb_build_object('merged', false, 'reason', 'target_already_merged');
  END IF;

  IF EXISTS (
    SELECT 1 FROM __PREFIX__token_transactions
    WHERE wallet_id = p_from_id AND reason = 'merge_out' AND reference_id = p_to_id
  ) THEN
    RETURN jsonb_build_object('merged', false, 'reason', 'already_merged');
  END IF;

  SELECT * INTO v_from
  FROM __PREFIX__wallets
  WHERE id = p_from_id
  FOR UPDATE;

  IF v_from.id IS NULL OR v_from.balance = 0 THEN
    RETURN jsonb_build_object('merged', false, 'reason', 'empty_source');
  END IF;

  INSERT INTO __PREFIX__wallets
    (id, balance, lifetime_purchased, last_daily_bonus_date, ads_watched_today, ads_watched_date, created_at, updated_at)
  VALUES
    (p_to_id, 0, 0, '', 0, '', v_now, v_now)
  ON CONFLICT (id) DO NOTHING;

  SELECT * INTO v_to
  FROM __PREFIX__wallets
  WHERE id = p_to_id
  FOR UPDATE;

  v_transfer := v_from.balance;
  v_new_to_balance := LEAST(v_to.balance + v_transfer, p_max_balance);
  v_actual_transfer := v_new_to_balance - v_to.balance;

  UPDATE __PREFIX__wallets
  SET balance = 0, updated_at = v_now
  WHERE id = p_from_id;

  UPDATE __PREFIX__wallets
  SET balance = v_new_to_balance,
      lifetime_purchased = lifetime_purchased + v_from.lifetime_purchased,
      updated_at = v_now
  WHERE id = p_to_id;

  INSERT INTO __PREFIX__token_transactions
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

CREATE OR REPLACE FUNCTION __PREFIX__grant_daily_bonus(
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
  FROM __PREFIX__wallets
  WHERE id = p_wallet_id
  FOR UPDATE;

  IF v_wallet.id IS NULL THEN
    RETURN jsonb_build_object('granted', false, 'balance', 0);
  END IF;

  IF v_wallet.last_daily_bonus_date = p_today THEN
    RETURN jsonb_build_object('granted', false, 'balance', v_wallet.balance);
  END IF;

  v_new_balance := LEAST(v_wallet.balance + p_amount, p_max_balance);
  v_actual_bonus := v_new_balance - v_wallet.balance;

  UPDATE __PREFIX__wallets
  SET balance = v_new_balance,
      last_daily_bonus_date = p_today,
      ads_watched_today = 0,
      ads_watched_date = p_today,
      updated_at = v_now
  WHERE id = p_wallet_id;

  IF v_actual_bonus > 0 THEN
    INSERT INTO __PREFIX__token_transactions
      (wallet_id, amount, reason, reference_id, balance_after, created_at)
    VALUES
      (p_wallet_id, v_actual_bonus, 'daily_bonus', NULL, v_new_balance, v_now);
  END IF;

  RETURN jsonb_build_object('granted', true, 'balance', v_new_balance, 'credited', v_actual_bonus);
END;
$$;

CREATE OR REPLACE FUNCTION __PREFIX__grant_ad_reward(
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
  FROM __PREFIX__wallets
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

  v_new_balance := LEAST(v_wallet.balance + p_amount, p_max_balance);
  v_actual_reward := v_new_balance - v_wallet.balance;
  v_ads_today := v_ads_today + 1;
  v_remaining := GREATEST(p_max_ads_per_day - v_ads_today, 0);

  UPDATE __PREFIX__wallets
  SET balance = v_new_balance,
      ads_watched_today = v_ads_today,
      ads_watched_date = p_today,
      updated_at = v_now
  WHERE id = p_wallet_id;

  IF v_actual_reward > 0 THEN
    INSERT INTO __PREFIX__token_transactions
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

CREATE OR REPLACE FUNCTION __PREFIX__claim_device_usage(
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
  FROM __PREFIX__device_usage
  WHERE device_id = p_device_id
  FOR UPDATE;

  IF v_usage.device_id IS NULL THEN
    INSERT INTO __PREFIX__device_usage(device_id, games_used_free, window_start)
    VALUES (p_device_id, 1, v_now);
    RETURN jsonb_build_object('allowed', true, 'count_after', 1);
  END IF;

  IF v_usage.window_start <= v_window_cutoff THEN
    UPDATE __PREFIX__device_usage
    SET games_used_free = 1, window_start = v_now
    WHERE device_id = p_device_id;
    RETURN jsonb_build_object('allowed', true, 'count_after', 1);
  END IF;

  IF v_usage.games_used_free >= p_free_tier_limit THEN
    RETURN jsonb_build_object('allowed', false, 'count_after', v_usage.games_used_free);
  END IF;

  UPDATE __PREFIX__device_usage
  SET games_used_free = games_used_free + 1
  WHERE device_id = p_device_id;

  RETURN jsonb_build_object('allowed', true, 'count_after', v_usage.games_used_free + 1);
END;
$$;

CREATE OR REPLACE FUNCTION __PREFIX__claim_user_usage(
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
  PERFORM pg_advisory_xact_lock(hashtext('__PREFIX__usage:' || p_user_id));

  PERFORM 1
  FROM __PREFIX__device_usage
  WHERE user_id = p_user_id
    AND window_start >= v_window_cutoff
  FOR UPDATE;

  SELECT COALESCE(SUM(games_used_free), 0) INTO v_total
  FROM __PREFIX__device_usage
  WHERE user_id = p_user_id
    AND window_start >= v_window_cutoff;

  IF v_total >= p_free_tier_limit THEN
    RETURN jsonb_build_object('allowed', false, 'count_after', v_total);
  END IF;

  SELECT * INTO v_device
  FROM __PREFIX__device_usage
  WHERE device_id = p_device_id
  FOR UPDATE;

  IF v_device.device_id IS NULL THEN
    INSERT INTO __PREFIX__device_usage(device_id, user_id, games_used_free, window_start)
    VALUES (p_device_id, p_user_id, 1, v_now);
  ELSIF v_device.window_start <= v_window_cutoff THEN
    UPDATE __PREFIX__device_usage
    SET user_id = p_user_id, games_used_free = 1, window_start = v_now
    WHERE device_id = p_device_id;
  ELSE
    UPDATE __PREFIX__device_usage
    SET user_id = p_user_id, games_used_free = games_used_free + 1
    WHERE device_id = p_device_id;
  END IF;

  RETURN jsonb_build_object('allowed', true, 'count_after', v_total + 1);
END;
$$;

CREATE OR REPLACE FUNCTION __PREFIX__mark_webhook_processed(p_event_id TEXT)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_now BIGINT := EXTRACT(EPOCH FROM NOW())::BIGINT;
BEGIN
  INSERT INTO __PREFIX__webhook_events(event_id, processed_at)
  VALUES (p_event_id, v_now)
  ON CONFLICT (event_id) DO NOTHING;

  DELETE FROM __PREFIX__webhook_events
  WHERE processed_at < v_now - (7 * 86400);

  RETURN true;
END;
$$;

CREATE OR REPLACE FUNCTION __PREFIX__admin_stats()
RETURNS JSONB
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT jsonb_build_object(
    'wallet_count', (SELECT COUNT(*) FROM __PREFIX__wallets),
    'total_sparks', (SELECT COALESCE(SUM(balance), 0) FROM __PREFIX__wallets),
    'paying_users', (SELECT COUNT(*) FROM __PREFIX__wallets WHERE lifetime_purchased > 0),
    'purchase_count', (SELECT COUNT(*) FROM __PREFIX__token_transactions WHERE reason = 'purchase'),
    'merge_count', (SELECT COUNT(*) FROM __PREFIX__token_transactions WHERE reason = 'merge_in'),
    'users_count', (SELECT COUNT(*) FROM __PREFIX__users)
  );
$$;

-- RPCs are server-only. Supabase service-role bypasses client RLS; anon and
-- authenticated clients must not call these mutation functions directly.
REVOKE EXECUTE ON FUNCTION __PREFIX__ensure_wallet(TEXT, BOOLEAN, INTEGER) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION __PREFIX__debit_tokens(TEXT, INTEGER, TEXT, TEXT) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION __PREFIX__credit_tokens(TEXT, INTEGER, TEXT, TEXT, TEXT, INTEGER) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION __PREFIX__credit_purchase(TEXT, INTEGER, TEXT, TEXT, INTEGER) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION __PREFIX__merge_wallet(TEXT, TEXT, INTEGER) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION __PREFIX__grant_daily_bonus(TEXT, TEXT, INTEGER, INTEGER) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION __PREFIX__grant_ad_reward(TEXT, TEXT, INTEGER, INTEGER, INTEGER) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION __PREFIX__claim_device_usage(TEXT, INTEGER) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION __PREFIX__claim_user_usage(TEXT, TEXT, INTEGER) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION __PREFIX__mark_webhook_processed(TEXT) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION __PREFIX__admin_stats() FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION __PREFIX__ensure_wallet(TEXT, BOOLEAN, INTEGER) TO service_role;
GRANT EXECUTE ON FUNCTION __PREFIX__debit_tokens(TEXT, INTEGER, TEXT, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION __PREFIX__credit_tokens(TEXT, INTEGER, TEXT, TEXT, TEXT, INTEGER) TO service_role;
GRANT EXECUTE ON FUNCTION __PREFIX__credit_purchase(TEXT, INTEGER, TEXT, TEXT, INTEGER) TO service_role;
GRANT EXECUTE ON FUNCTION __PREFIX__merge_wallet(TEXT, TEXT, INTEGER) TO service_role;
GRANT EXECUTE ON FUNCTION __PREFIX__grant_daily_bonus(TEXT, TEXT, INTEGER, INTEGER) TO service_role;
GRANT EXECUTE ON FUNCTION __PREFIX__grant_ad_reward(TEXT, TEXT, INTEGER, INTEGER, INTEGER) TO service_role;
GRANT EXECUTE ON FUNCTION __PREFIX__claim_device_usage(TEXT, INTEGER) TO service_role;
GRANT EXECUTE ON FUNCTION __PREFIX__claim_user_usage(TEXT, TEXT, INTEGER) TO service_role;
GRANT EXECUTE ON FUNCTION __PREFIX__mark_webhook_processed(TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION __PREFIX__admin_stats() TO service_role;
