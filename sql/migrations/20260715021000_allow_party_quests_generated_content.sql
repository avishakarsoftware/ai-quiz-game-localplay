-- Production Supabase migration applied on 2026-07-14.
-- Expands saved generated-content storage for Party Quests authoring.

ALTER TABLE games_generated_content
  DROP CONSTRAINT IF EXISTS games_generated_content_content_type_check;

ALTER TABLE games_generated_content
  ADD CONSTRAINT games_generated_content_content_type_check
  CHECK (content_type IN ('quiz', 'mlt', 'drawing', 'housie', 'chit_pull', 'party_quests'));
