-- Atomically save custom quiz metadata and its questions.
-- Apply before deploying the backend save_quiz_pack adapter; safe to reapply.

CREATE OR REPLACE FUNCTION games_gamma_save_quiz_pack(
  p_owner_wallet_id TEXT,
  p_pack_id TEXT,
  p_title TEXT,
  p_questions JSONB
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_pack RECORD;
  v_question JSONB;
  v_position INTEGER;
  v_now BIGINT := EXTRACT(EPOCH FROM NOW())::BIGINT;
BEGIN
  IF p_owner_wallet_id IS NULL OR p_owner_wallet_id = '' OR p_pack_id IS NULL OR p_pack_id = '' THEN
    RAISE EXCEPTION 'Quiz pack owner and id are required';
  END IF;
  IF p_questions IS NULL OR jsonb_typeof(p_questions) <> 'array' THEN
    RAISE EXCEPTION 'Quiz questions must be an array';
  END IF;

  -- Insert cannot take over an existing owner's ID. A conflicting concurrent save waits
  -- here and then validates the committed owner under the row lock below.
  INSERT INTO games_gamma_quiz_packs
    (id, owner_wallet_id, title, status, question_count, created_at, updated_at, deleted_at)
  VALUES (p_pack_id, p_owner_wallet_id, p_title, 'ready', jsonb_array_length(p_questions), v_now, v_now, NULL)
  ON CONFLICT (id) DO NOTHING;

  SELECT * INTO v_pack FROM games_gamma_quiz_packs WHERE id = p_pack_id FOR UPDATE;
  IF v_pack.owner_wallet_id <> p_owner_wallet_id THEN
    RAISE EXCEPTION 'Quiz pack belongs to another wallet' USING ERRCODE = '42501';
  END IF;

  UPDATE games_gamma_quiz_packs
  SET title = p_title, status = 'ready', question_count = jsonb_array_length(p_questions),
      updated_at = v_now, deleted_at = NULL
  WHERE id = p_pack_id;
  DELETE FROM games_gamma_quiz_questions WHERE pack_id = p_pack_id;

  FOR v_question, v_position IN
    SELECT value, (ordinality - 1)::INTEGER FROM jsonb_array_elements(p_questions) WITH ORDINALITY
  LOOP
    IF jsonb_typeof(v_question) <> 'object' THEN
      RAISE EXCEPTION 'Quiz question must be an object';
    END IF;
    INSERT INTO games_gamma_quiz_questions
      (id, pack_id, position, question_type, text, options, answer_index,
       image_asset_id, image_url, image_alt, created_at, updated_at)
    VALUES
      (p_pack_id || '_' || v_position, p_pack_id, v_position,
       CASE WHEN jsonb_array_length(COALESCE(v_question->'options', '[]'::jsonb)) = 2
            THEN 'true_false' ELSE 'multiple_choice' END,
       COALESCE(v_question->>'text', ''), COALESCE(v_question->'options', '[]'::jsonb),
       COALESCE((v_question->>'answer_index')::INTEGER, 0),
       v_question->>'image_asset_id', v_question->>'image_url', v_question->>'image_alt', v_now, v_now);
  END LOOP;

  RETURN jsonb_build_object('saved', true, 'id', p_pack_id);
END;
$$;

REVOKE EXECUTE ON FUNCTION games_gamma_save_quiz_pack(TEXT, TEXT, TEXT, JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION games_gamma_save_quiz_pack(TEXT, TEXT, TEXT, JSONB) TO service_role;
NOTIFY pgrst, 'reload schema';
