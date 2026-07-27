-- Migration: per-wallet game results / stats (SPEC-GAME-STATS)
-- Generated from sql/templates/games-schema.template.sql — do not hand-edit.
-- Idempotent: CREATE TABLE/INDEX IF NOT EXISTS, ENABLE RLS, DROP+CREATE POLICY.

-- Durable per-wallet game completions (SPEC-GAME-STATS). main.py's `game_history` is an
-- in-memory ring that dies with the process, so lifetime stats were impossible. wallet_id is
-- the HOST's wallet — guests join without wallets — so these are "games hosted".
-- room_code is the PK so a re-broadcast podium cannot double-count one game.
CREATE TABLE IF NOT EXISTS games_gamma_game_results (
  room_code TEXT PRIMARY KEY,
  wallet_id TEXT NOT NULL,
  game_type TEXT NOT NULL DEFAULT '',
  game_title TEXT NOT NULL DEFAULT '',
  player_count INTEGER NOT NULL DEFAULT 0,
  winner_nickname TEXT NOT NULL DEFAULT '',
  top_score INTEGER NOT NULL DEFAULT 0,
  completed_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_games_gamma_game_results_wallet
  ON games_gamma_game_results(wallet_id, completed_at DESC);

ALTER TABLE games_gamma_game_results ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS service_role_all_games_gamma_game_results ON games_gamma_game_results;
CREATE POLICY service_role_all_games_gamma_game_results ON games_gamma_game_results
  FOR ALL TO service_role USING (true) WITH CHECK (true);
