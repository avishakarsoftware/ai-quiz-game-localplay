-- Migration: operator settings key/value store (SPEC-REMOTE-CONFIG §admin)
-- Generated from sql/templates/games-schema.template.sql — do not hand-edit.
-- Idempotent: CREATE TABLE IF NOT EXISTS, ENABLE RLS, DROP+CREATE POLICY.

-- Operator settings (SPEC-REMOTE-CONFIG §admin). Small durable key/value store; currently holds
-- the remote-config override layer. Persisted rather than in-memory on purpose: an override is a
-- kill switch, and an in-memory one evaporates exactly when it's needed (during a bad rollout).
CREATE TABLE IF NOT EXISTS games_gamma_app_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL DEFAULT '',
  updated_at BIGINT NOT NULL
);

ALTER TABLE games_gamma_app_settings ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS service_role_all_games_gamma_app_settings ON games_gamma_app_settings;
CREATE POLICY service_role_all_games_gamma_app_settings ON games_gamma_app_settings
  FOR ALL TO service_role USING (true) WITH CHECK (true);
