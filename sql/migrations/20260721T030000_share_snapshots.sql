-- Share-card snapshots (SPEC-SHARE-CARD) — targeted Supabase migration.
-- Extracted verbatim from the rendered sql/games-schema.sql.
-- Apply to GAMMA first (games_gamma_ prefix), verify, then PROD (games_ prefix).
-- No env flag / no backend gate: share.py uses this durable store best-effort and degrades to
-- in-memory until the table exists, so applying it is transparently a no-downtime upgrade.
-- Idempotent: CREATE TABLE/INDEX IF NOT EXISTS, ENABLE RLS, DROP+CREATE POLICY.

-- Table + index
CREATE TABLE IF NOT EXISTS games_share_snapshots (
  token TEXT PRIMARY KEY,
  game_type TEXT NOT NULL DEFAULT '',
  winner TEXT NOT NULL DEFAULT '',
  top_score INTEGER NOT NULL DEFAULT 0,
  player_count INTEGER NOT NULL DEFAULT 0,
  created_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_games_share_snapshots_created
  ON games_share_snapshots(created_at);

-- Row-level security (service-role only)
ALTER TABLE games_share_snapshots ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS service_role_all_games_share_snapshots ON games_share_snapshots;
CREATE POLICY service_role_all_games_share_snapshots ON games_share_snapshots
  FOR ALL TO service_role USING (true) WITH CHECK (true);
