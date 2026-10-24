-- Optional layout origins; no row migration or member-data updates.
-- Approved 2026-10-24: metadata is written only through explicit member save.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '20s';

CREATE OR REPLACE FUNCTION public.save_member_map_state_v1(
    p_expected_revision BIGINT,
    p_document JSONB
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    v_user_id UUID := auth.uid();
    v_role TEXT := auth.role();
    v_current_revision BIGINT;
    v_next_revision BIGINT;
    v_public_event_cursor_at TIMESTAMPTZ;
    v_layout JSONB;
    v_position JSONB;
    v_origin JSONB;
    v_previous_document JSONB;
    v_previous_layout JSONB;
    v_origins JSONB;
    v_merged_layouts JSONB := '[]'::JSONB;
    v_note JSONB;
    v_anchor JSONB;
    v_mark_key TEXT;
    v_mark JSONB;
    v_layout_key TEXT;
    v_seen_layout_keys TEXT[] := ARRAY[]::TEXT[];
    v_seen_ids TEXT[];
    v_count INTEGER;
    v_value NUMERIC;
BEGIN
    IF v_role IS DISTINCT FROM 'authenticated' OR v_user_id IS NULL THEN
        RAISE EXCEPTION 'authentication_required' USING ERRCODE = '42501';
    END IF;
    IF p_expected_revision IS NULL OR p_expected_revision < 0
       OR p_expected_revision >= 9007199254740991 THEN
        RAISE EXCEPTION 'invalid_member_map_revision' USING ERRCODE = '22023';
    END IF;

    -- Strict document boundary also protects direct authenticated RPC callers.
    IF p_document IS NULL OR jsonb_typeof(p_document) <> 'object'
       OR p_document ?| ARRAY['user_id', 'owner_id']
       OR NOT (p_document ?& ARRAY['layouts']::TEXT[])
       OR p_document - ARRAY['layouts']::TEXT[] <> '{}'::JSONB
       OR octet_length(p_document::text) > 65536
       OR jsonb_typeof(p_document->'layouts') <> 'array'
       OR jsonb_array_length(p_document->'layouts') > 3 THEN
        RAISE EXCEPTION 'invalid_member_map_document' USING ERRCODE = '22023';
    END IF;

    FOR v_layout IN SELECT value FROM jsonb_array_elements(p_document->'layouts') LOOP
        IF jsonb_typeof(v_layout) <> 'object'
           OR NOT (v_layout ?& ARRAY['map_key','positions','notes','marks']::TEXT[])
           OR v_layout - ARRAY['map_key','positions','notes','marks','origins']::TEXT[] <> '{}'::JSONB
           OR jsonb_typeof(v_layout->'map_key') <> 'string'
           OR jsonb_typeof(v_layout->'positions') <> 'array'
           OR jsonb_typeof(v_layout->'notes') <> 'array'
           OR jsonb_typeof(v_layout->'marks') <> 'object' THEN
            RAISE EXCEPTION 'invalid_member_map_document' USING ERRCODE = '22023';
        END IF;

        v_layout_key := v_layout->>'map_key';
        IF v_layout_key !~ '^[a-z0-9][a-z0-9_-]{0,31}$'
           OR v_layout_key = ANY(v_seen_layout_keys) THEN
            RAISE EXCEPTION 'invalid_member_map_document' USING ERRCODE = '22023';
        END IF;
        v_seen_layout_keys := array_append(v_seen_layout_keys, v_layout_key);

        v_count := jsonb_array_length(v_layout->'positions');
        IF v_count > 200 THEN RAISE EXCEPTION 'invalid_member_map_document' USING ERRCODE = '22023'; END IF;
        v_seen_ids := ARRAY[]::TEXT[];
        FOR v_position IN SELECT value FROM jsonb_array_elements(v_layout->'positions') LOOP
            IF jsonb_typeof(v_position) <> 'object'
               OR NOT (v_position ?& ARRAY['node_id','x','y']::TEXT[])
               OR v_position - ARRAY['node_id','x','y']::TEXT[] <> '{}'::JSONB
               OR jsonb_typeof(v_position->'node_id') <> 'string'
               OR (v_position->>'node_id') !~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'
               OR jsonb_typeof(v_position->'x') <> 'number'
               OR jsonb_typeof(v_position->'y') <> 'number' THEN
                RAISE EXCEPTION 'invalid_member_map_document' USING ERRCODE = '22023';
            END IF;
            IF (v_position->>'node_id') = ANY(v_seen_ids) THEN
                RAISE EXCEPTION 'invalid_member_map_document' USING ERRCODE = '22023';
            END IF;
            v_seen_ids := array_append(v_seen_ids, v_position->>'node_id');
            v_value := (v_position->>'x')::NUMERIC;
            IF abs(v_value) > 1000000 THEN RAISE EXCEPTION 'invalid_member_map_document' USING ERRCODE = '22023'; END IF;
            v_value := (v_position->>'y')::NUMERIC;
            IF abs(v_value) > 1000000 THEN RAISE EXCEPTION 'invalid_member_map_document' USING ERRCODE = '22023'; END IF;
        END LOOP;

        IF v_layout ? 'origins' THEN
            IF jsonb_typeof(v_layout->'origins') <> 'array'
               OR jsonb_array_length(v_layout->'origins') > 200 THEN
                RAISE EXCEPTION 'invalid_member_map_document' USING ERRCODE = '22023';
            END IF;
            v_seen_ids := ARRAY[]::TEXT[];
            FOR v_origin IN SELECT value FROM jsonb_array_elements(v_layout->'origins') LOOP
                IF jsonb_typeof(v_origin) <> 'object'
                   OR NOT (v_origin ?& ARRAY['node_id','x','y','dx','dy']::TEXT[])
                   OR v_origin - ARRAY['node_id','x','y','dx','dy']::TEXT[] <> '{}'::JSONB
                   OR jsonb_typeof(v_origin->'node_id') <> 'string'
                   OR (v_origin->>'node_id') !~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'
                   OR (v_origin->>'node_id') = ANY(v_seen_ids)
                   OR jsonb_typeof(v_origin->'x') <> 'number'
                   OR jsonb_typeof(v_origin->'y') <> 'number'
                   OR jsonb_typeof(v_origin->'dx') <> 'number'
                   OR jsonb_typeof(v_origin->'dy') <> 'number' THEN
                    RAISE EXCEPTION 'invalid_member_map_document' USING ERRCODE = '22023';
                END IF;
                v_seen_ids := array_append(v_seen_ids, v_origin->>'node_id');
                IF abs((v_origin->>'x')::NUMERIC) > 1000000
                   OR abs((v_origin->>'y')::NUMERIC) > 1000000
                   OR abs((v_origin->>'dx')::NUMERIC) > 1000000
                   OR abs((v_origin->>'dy')::NUMERIC) > 1000000
                   OR NOT EXISTS (
                       SELECT 1 FROM jsonb_array_elements(v_layout->'positions') p
                       WHERE p->>'node_id' = v_origin->>'node_id'
                         AND p->'x' = v_origin->'dx' AND p->'y' = v_origin->'dy'
                   ) THEN
                    RAISE EXCEPTION 'invalid_member_map_document' USING ERRCODE = '22023';
                END IF;
            END LOOP;
        END IF;

        v_count := jsonb_array_length(v_layout->'notes');
        IF v_count > 100 THEN RAISE EXCEPTION 'invalid_member_map_document' USING ERRCODE = '22023'; END IF;
        v_seen_ids := ARRAY[]::TEXT[];
        FOR v_note IN SELECT value FROM jsonb_array_elements(v_layout->'notes') LOOP
            IF jsonb_typeof(v_note) <> 'object'
               OR NOT (v_note ?& ARRAY['note_id','anchor','x','y','text','done']::TEXT[])
               OR v_note - ARRAY['note_id','anchor','x','y','text','done']::TEXT[] <> '{}'::JSONB
               OR jsonb_typeof(v_note->'note_id') <> 'string'
               OR (v_note->>'note_id') !~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'
               OR jsonb_typeof(v_note->'x') <> 'number'
               OR jsonb_typeof(v_note->'y') <> 'number'
               OR jsonb_typeof(v_note->'text') <> 'string'
               OR char_length(v_note->>'text') > 2000
               OR jsonb_typeof(v_note->'done') <> 'boolean' THEN
                RAISE EXCEPTION 'invalid_member_map_document' USING ERRCODE = '22023';
            END IF;
            IF (v_note->>'note_id') = ANY(v_seen_ids) THEN
                RAISE EXCEPTION 'invalid_member_map_document' USING ERRCODE = '22023';
            END IF;
            v_seen_ids := array_append(v_seen_ids, v_note->>'note_id');
            v_anchor := v_note->'anchor';
            IF v_anchor <> 'null'::JSONB THEN
                IF jsonb_typeof(v_anchor) <> 'object'
                   OR NOT (v_anchor ?& ARRAY['kind','id']::TEXT[])
                   OR v_anchor - ARRAY['kind','id']::TEXT[] <> '{}'::JSONB
                   OR jsonb_typeof(v_anchor->'kind') <> 'string'
                   OR v_anchor->>'kind' NOT IN ('node','edge')
                   OR jsonb_typeof(v_anchor->'id') <> 'string'
                   OR (v_anchor->>'id') !~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$' THEN
                    RAISE EXCEPTION 'invalid_member_map_document' USING ERRCODE = '22023';
                END IF;
            END IF;
            v_value := (v_note->>'x')::NUMERIC;
            IF abs(v_value) > 1000000 THEN RAISE EXCEPTION 'invalid_member_map_document' USING ERRCODE = '22023'; END IF;
            v_value := (v_note->>'y')::NUMERIC;
            IF abs(v_value) > 1000000 THEN RAISE EXCEPTION 'invalid_member_map_document' USING ERRCODE = '22023'; END IF;
        END LOOP;

        SELECT count(*) INTO v_count
          FROM jsonb_object_keys(v_layout->'marks');
        IF v_count > 200 THEN
            RAISE EXCEPTION 'invalid_member_map_document' USING ERRCODE = '22023';
        END IF;
        FOR v_mark_key, v_mark IN
            SELECT key, value FROM jsonb_each(v_layout->'marks')
        LOOP
            IF v_mark_key !~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'
               OR jsonb_typeof(v_mark) <> 'object'
               OR NOT (v_mark ?& ARRAY['read_revision','important','disposition']::TEXT[])
               OR v_mark - ARRAY['read_revision','important','disposition']::TEXT[] <> '{}'::JSONB
               OR (v_mark->'read_revision' <> 'null'::JSONB AND
                   (jsonb_typeof(v_mark->'read_revision') <> 'number'
                    OR (v_mark->>'read_revision') !~ '^[1-9][0-9]*$'
                    OR (v_mark->>'read_revision')::NUMERIC >= 9007199254740991))
               OR jsonb_typeof(v_mark->'important') <> 'boolean'
               OR jsonb_typeof(v_mark->'disposition') <> 'string'
               OR v_mark->>'disposition' NOT IN ('inbox','later','irrelevant') THEN
                RAISE EXCEPTION 'invalid_member_map_document' USING ERRCODE = '22023';
            END IF;
        END LOOP;
    END LOOP;

    -- Serialize first-save races too: missing rows do not provide a row lock.
    PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(v_user_id::TEXT, 92701));
    SELECT revision, public_event_cursor_at, document
      INTO v_current_revision, v_public_event_cursor_at, v_previous_document
      FROM public.member_map_state WHERE user_id = v_user_id FOR UPDATE;
    IF NOT FOUND THEN
        v_current_revision := 0;
        v_public_event_cursor_at := NULL;
    END IF;
    IF v_current_revision IS DISTINCT FROM p_expected_revision THEN
        RAISE EXCEPTION 'member_map_revision_conflict' USING ERRCODE = 'PT409';
    END IF;

    -- Only an explicit save changes metadata. Older clients omit origins;
    -- retain each stored origin only while its raw delta is still identical.
    -- Explicit [] clears metadata. Removed layouts/nodes are not resurrected.
    FOR v_layout IN SELECT value FROM jsonb_array_elements(p_document->'layouts') LOOP
        IF NOT (v_layout ? 'origins') THEN
            SELECT value INTO v_previous_layout
              FROM jsonb_array_elements(COALESCE(v_previous_document->'layouts', '[]'::JSONB))
             WHERE value->>'map_key' = v_layout->>'map_key';
            IF v_previous_layout ? 'origins' THEN
                SELECT COALESCE(jsonb_agg(o.value ORDER BY o.ordinality), '[]'::JSONB)
                  INTO v_origins
                  FROM jsonb_array_elements(v_previous_layout->'origins') WITH ORDINALITY AS o(value, ordinality)
                 WHERE EXISTS (
                     SELECT 1 FROM jsonb_array_elements(v_layout->'positions') p
                     WHERE p->>'node_id' = o.value->>'node_id'
                       AND p->'x' = o.value->'dx' AND p->'y' = o.value->'dy'
                 );
                v_layout := v_layout || jsonb_build_object('origins', v_origins);
            END IF;
        END IF;
        v_merged_layouts := v_merged_layouts || jsonb_build_array(v_layout);
    END LOOP;
    p_document := jsonb_build_object('layouts', v_merged_layouts);
    -- Preserved legacy metadata counts toward the same existing storage limit.
    IF octet_length(p_document::text) > 65536 THEN
        RAISE EXCEPTION 'invalid_member_map_document' USING ERRCODE = '22023';
    END IF;

    v_next_revision := v_current_revision + 1;
    INSERT INTO public.member_map_state (user_id, revision, document, updated_at)
    VALUES (v_user_id, v_next_revision, p_document, now())
    ON CONFLICT (user_id) DO UPDATE
       SET revision = EXCLUDED.revision,
           document = EXCLUDED.document,
           updated_at = EXCLUDED.updated_at;

    RETURN jsonb_build_object(
        'user_id', v_user_id,
        'revision', v_next_revision,
        'document', p_document,
        'public_event_cursor_at', v_public_event_cursor_at
    );
END;
$function$;

REVOKE ALL ON FUNCTION public.save_member_map_state_v1(BIGINT, JSONB) FROM PUBLIC, anon, service_role;
GRANT EXECUTE ON FUNCTION public.save_member_map_state_v1(BIGINT, JSONB) TO authenticated;

COMMIT;
