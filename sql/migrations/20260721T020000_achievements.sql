-- Achievements / badges (SPEC-ACHIEVEMENTS) — targeted Supabase migration.
-- Extracted verbatim from the rendered sql/games-schema.sql (do NOT hand-edit the RPC body).
-- Apply to GAMMA first (games_gamma_ prefix), verify, then PROD (games_ prefix).
-- After applying: set ACHIEVEMENTS_ENABLED=true and recreate the backend container.
-- Idempotent: CREATE TABLE/INDEX IF NOT EXISTS, ENABLE RLS, DROP+CREATE POLICY, CREATE OR REPLACE, REVOKE/GRANT.

-- Table + index
CREATE TABLE IF NOT EXISTS games_achievements (
  wallet_id TEXT NOT NULL,
  badge_id TEXT NOT NULL,
  awarded_at BIGINT NOT NULL,
  PRIMARY KEY (wallet_id, badge_id)
);
CREATE INDEX IF NOT EXISTS idx_games_achievements_wallet
  ON games_achievements(wallet_id);

-- Row-level security (service-role only)
ALTER TABLE games_achievements ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS service_role_all_games_achievements ON games_achievements;
CREATE POLICY service_role_all_games_achievements ON games_achievements
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Award RPC
CREATE OR REPLACE FUNCTION games_award_achievement(
  p_wallet_id TEXT,
  p_badge_id TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_now BIGINT := EXTRACT(EPOCH FROM NOW())::BIGINT;
  v_inserted INTEGER;
BEGIN
  INSERT INTO games_achievements (wallet_id, badge_id, awarded_at)
  VALUES (p_wallet_id, p_badge_id, v_now)
  ON CONFLICT (wallet_id, badge_id) DO NOTHING;
  GET DIAGNOSTICS v_inserted = ROW_COUNT;
  RETURN jsonb_build_object('awarded', v_inserted > 0);
END;
$$;

REVOKE EXECUTE ON FUNCTION games_award_achievement(TEXT, TEXT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION games_award_achievement(TEXT, TEXT) TO service_role;
