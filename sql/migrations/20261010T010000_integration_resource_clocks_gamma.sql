-- PREPARED, UNAPPLIED: durable callback/poll resource clocks.
-- Install the matching environment migration before deploying this adapter.
-- Existing seconds units and old writer inputs remain compatible; no backfill.
-- Opaque content tombstones retain no wallet, owner, payload or media.

-- Durable provider ordering clocks. Existing seconds-based columns keep their
-- units. Historical rows stay NULL until their next actual write; installation
-- does not create fresh evidence. Triggers also cover permitted old writers.
ALTER TABLE public.games_gamma_quiz_packs ADD COLUMN IF NOT EXISTS integration_updated_at_us BIGINT;
ALTER TABLE public.games_gamma_generated_content ADD COLUMN IF NOT EXISTS integration_updated_at_us BIGINT;
ALTER TABLE public.games_gamma_game_sessions ADD COLUMN IF NOT EXISTS integration_updated_at_us BIGINT;

-- Retain only opaque resource identity/time across physical content deletion,
-- including account deletion. No owner, wallet, title, payload or media is kept.
CREATE TABLE IF NOT EXISTS public.games_gamma_integration_content_tombstones (
  content_type TEXT NOT NULL CHECK(content_type IN ('quiz','game')),
  content_id TEXT NOT NULL,
  occurred_at_us BIGINT NOT NULL CHECK(occurred_at_us > 0),
  PRIMARY KEY(content_type,content_id)
);
ALTER TABLE public.games_gamma_integration_content_tombstones ENABLE ROW LEVEL SECURITY;
-- Supabase defaults may grant service_role every table privilege. Reset that
-- inherited ACL too before granting only the operations required here.
REVOKE ALL ON public.games_gamma_integration_content_tombstones FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT, UPDATE ON public.games_gamma_integration_content_tombstones TO service_role;

CREATE OR REPLACE FUNCTION public.games_gamma_stamp_integration_clock()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE
  v_now BIGINT := floor(extract(epoch FROM clock_timestamp()) * 1000000)::BIGINT;
  v_previous BIGINT := 0;
  v_deleted BIGINT := 0;
BEGIN
  IF TG_OP='UPDATE' THEN v_previous:=COALESCE(OLD.integration_updated_at_us,0); END IF;
  SELECT COALESCE(occurred_at_us,0) INTO v_deleted
    FROM public.games_gamma_integration_content_tombstones
    WHERE content_type=TG_ARGV[0] AND content_id=NEW.id;
  NEW.integration_updated_at_us:=greatest(v_now,v_previous+1,COALESCE(v_deleted,0)+1);
  IF NEW.integration_updated_at_us > v_now+300000000 THEN
    RAISE EXCEPTION 'integration_clock_ahead';
  END IF;
  RETURN NEW;
END;
$$;
CREATE OR REPLACE FUNCTION public.games_gamma_record_content_deletion_clock()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE
  v_now BIGINT := floor(extract(epoch FROM clock_timestamp()) * 1000000)::BIGINT;
  v_clock BIGINT;
BEGIN
  v_clock:=greatest(v_now,COALESCE(OLD.integration_updated_at_us,0)+1);
  IF v_clock>v_now+300000000 THEN RAISE EXCEPTION 'integration_clock_ahead'; END IF;
  INSERT INTO public.games_gamma_integration_content_tombstones AS tombstone(content_type,content_id,occurred_at_us)
    VALUES(TG_ARGV[0],OLD.id,v_clock)
    ON CONFLICT(content_type,content_id) DO UPDATE
      SET occurred_at_us=greatest(EXCLUDED.occurred_at_us,tombstone.occurred_at_us+1);
  RETURN OLD;
END;
$$;
CREATE OR REPLACE FUNCTION public.games_gamma_validate_inserted_integration_clock()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE v_deleted BIGINT;
BEGIN
  -- BEFORE INSERT can run before waiting on a concurrent delete's unique-index
  -- lock. Recheck afterward, without changing the exact RETURNING snapshot.
  SELECT occurred_at_us INTO v_deleted FROM public.games_gamma_integration_content_tombstones
    WHERE content_type=TG_ARGV[0] AND content_id=NEW.id;
  IF v_deleted IS NOT NULL AND NEW.integration_updated_at_us<=v_deleted THEN
    RAISE EXCEPTION 'integration_clock_retry' USING ERRCODE='40001';
  END IF;
  RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION public.games_gamma_stamp_integration_clock() FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.games_gamma_record_content_deletion_clock() FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.games_gamma_validate_inserted_integration_clock() FROM PUBLIC, anon, authenticated, service_role;

DROP TRIGGER IF EXISTS integration_resource_clock ON public.games_gamma_quiz_packs;
CREATE TRIGGER integration_resource_clock BEFORE INSERT OR UPDATE ON public.games_gamma_quiz_packs
  FOR EACH ROW EXECUTE FUNCTION public.games_gamma_stamp_integration_clock('quiz');
DROP TRIGGER IF EXISTS integration_resource_clock ON public.games_gamma_generated_content;
CREATE TRIGGER integration_resource_clock BEFORE INSERT OR UPDATE ON public.games_gamma_generated_content
  FOR EACH ROW EXECUTE FUNCTION public.games_gamma_stamp_integration_clock('game');
DROP TRIGGER IF EXISTS integration_resource_clock ON public.games_gamma_game_sessions;
CREATE TRIGGER integration_resource_clock BEFORE INSERT OR UPDATE ON public.games_gamma_game_sessions
  FOR EACH ROW EXECUTE FUNCTION public.games_gamma_stamp_integration_clock('session');
DROP TRIGGER IF EXISTS integration_content_deletion_clock ON public.games_gamma_quiz_packs;
CREATE TRIGGER integration_content_deletion_clock AFTER DELETE ON public.games_gamma_quiz_packs
  FOR EACH ROW EXECUTE FUNCTION public.games_gamma_record_content_deletion_clock('quiz');
DROP TRIGGER IF EXISTS integration_content_deletion_clock ON public.games_gamma_generated_content;
CREATE TRIGGER integration_content_deletion_clock AFTER DELETE ON public.games_gamma_generated_content
  FOR EACH ROW EXECUTE FUNCTION public.games_gamma_record_content_deletion_clock('game');
DROP TRIGGER IF EXISTS integration_insert_clock_validation ON public.games_gamma_quiz_packs;
CREATE TRIGGER integration_insert_clock_validation AFTER INSERT ON public.games_gamma_quiz_packs
  FOR EACH ROW EXECUTE FUNCTION public.games_gamma_validate_inserted_integration_clock('quiz');
DROP TRIGGER IF EXISTS integration_insert_clock_validation ON public.games_gamma_generated_content;
CREATE TRIGGER integration_insert_clock_validation AFTER INSERT ON public.games_gamma_generated_content
  FOR EACH ROW EXECUTE FUNCTION public.games_gamma_validate_inserted_integration_clock('game');

CREATE OR REPLACE FUNCTION public.games_gamma_delete_integration_content(
  p_owner_wallet_id TEXT, p_content_id TEXT, p_content_type TEXT
) RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE v_snapshot JSONB; v_clock BIGINT;
BEGIN
  IF p_content_type='quiz' THEN
    UPDATE public.games_gamma_quiz_packs AS pack SET status='deleted',
      deleted_at=floor(extract(epoch FROM clock_timestamp()))::BIGINT,
      updated_at=floor(extract(epoch FROM clock_timestamp()))::BIGINT
      WHERE pack.id=p_content_id AND pack.owner_wallet_id=p_owner_wallet_id AND pack.deleted_at IS NULL
      RETURNING to_jsonb(pack) INTO v_snapshot;
  ELSIF p_content_type='game' THEN
    DELETE FROM public.games_gamma_generated_content AS content
      WHERE content.id=p_content_id AND content.wallet_id=p_owner_wallet_id
      RETURNING to_jsonb(content) INTO v_snapshot;
    IF v_snapshot IS NOT NULL THEN
      SELECT occurred_at_us INTO STRICT v_clock FROM public.games_gamma_integration_content_tombstones
        WHERE content_type='game' AND content_id=p_content_id;
      v_snapshot:=v_snapshot||jsonb_build_object('integration_updated_at_us',v_clock);
    END IF;
  ELSE RAISE EXCEPTION 'Invalid integration content type';
  END IF;
  RETURN v_snapshot;
END;
$$;
REVOKE ALL ON FUNCTION public.games_gamma_delete_integration_content(TEXT,TEXT,TEXT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.games_gamma_delete_integration_content(TEXT,TEXT,TEXT) TO service_role;

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

  -- Return the exact saved version under this transaction's row lock. A later
  -- metadata read could otherwise pair another save's clock with this payload.
  SELECT * INTO v_pack FROM games_gamma_quiz_packs WHERE id = p_pack_id;
  RETURN jsonb_build_object('saved', true, 'id', p_pack_id, 'pack',
    to_jsonb(v_pack) || jsonb_build_object('questions', COALESCE(
      (SELECT jsonb_agg(to_jsonb(q) ORDER BY q.position)
       FROM games_gamma_quiz_questions q WHERE q.pack_id = p_pack_id), '[]'::jsonb)));
END;
$$;

REVOKE EXECUTE ON FUNCTION games_gamma_save_quiz_pack(TEXT,TEXT,TEXT,JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION games_gamma_save_quiz_pack(TEXT,TEXT,TEXT,JSONB) TO service_role;
NOTIFY pgrst, 'reload schema';
