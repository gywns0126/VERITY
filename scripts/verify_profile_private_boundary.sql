-- Read-only production acceptance: no real member values or IDs are returned.
-- Run as postgres in the SQL editor AFTER the profile privacy migration.
-- This checks database roles, not a signed-in browser/API end-to-end session.
BEGIN READ ONLY;
DO $$
DECLARE
    actor RECORD;
    visible_count BIGINT;
    foreign_count BIGINT;
    total_count BIGINT;
    public_count BIGINT;
    public_after BIGINT;
    checks JSONB := '[]'::JSONB;
BEGIN
    SELECT count(*) INTO total_count FROM public.profiles;
    SELECT count(*) INTO public_count FROM public.public_profiles;
    IF total_count = 0 THEN
        RAISE EXCEPTION 'No profiles: cannot verify real-role visibility';
    END IF;
    FOR actor IN
        SELECT DISTINCT ON (kind) id, kind FROM (
            SELECT id, CASE
                WHEN is_super_admin IS TRUE AND is_admin IS TRUE THEN 'owner'
                WHEN is_admin IS TRUE THEN 'deputy'
                ELSE 'member' END AS kind
            FROM public.profiles
        ) AS candidates ORDER BY kind, id
    LOOP
        PERFORM set_config('request.jwt.claim.sub', actor.id::TEXT, TRUE);
        PERFORM set_config('request.jwt.claim.role', 'authenticated', TRUE);
        PERFORM set_config('request.jwt.claims',
            jsonb_build_object('sub',actor.id,'role','authenticated')::TEXT, TRUE);
        EXECUTE 'SET LOCAL ROLE authenticated';
        SELECT count(*), count(*) FILTER (WHERE id <> auth.uid())
            INTO visible_count, foreign_count FROM public.profiles;
        IF visible_count <> 1 OR foreign_count <> 0 THEN
            RAISE EXCEPTION 'Private profile boundary failed for %', actor.kind;
        END IF;
        checks := checks || jsonb_build_array(jsonb_build_object(
            'case',actor.kind,'visible_rows',visible_count,
            'foreign_rows',foreign_count,'pass',TRUE));
        EXECUTE 'RESET ROLE';
    END LOOP;

    -- Reuse a real sub but remove its JWT role: the restriction must fail closed.
    PERFORM set_config('request.jwt.claim.role', '', TRUE);
    PERFORM set_config('request.jwt.claims', '{}', TRUE);
    EXECUTE 'SET LOCAL ROLE authenticated';
    SELECT count(*) INTO visible_count FROM public.profiles;
    IF visible_count <> 0 THEN RAISE EXCEPTION 'Missing role boundary failed'; END IF;
    checks := checks || jsonb_build_array(jsonb_build_object('case','missing_role','pass',TRUE));
    EXECUTE 'RESET ROLE';

    PERFORM set_config('request.jwt.claim.sub', '', TRUE);
    PERFORM set_config('request.jwt.claim.role', 'anon', TRUE);
    PERFORM set_config('request.jwt.claims', '{"role":"anon"}', TRUE);
    EXECUTE 'SET LOCAL ROLE anon';
    SELECT count(*) INTO visible_count FROM public.profiles;
    SELECT count(*) INTO public_after FROM public.public_profiles;
    IF visible_count <> 0 OR public_after <> public_count THEN
        RAISE EXCEPTION 'Anonymous privacy/public profile availability failed';
    END IF;
    checks := checks || jsonb_build_array(jsonb_build_object(
        'case','anon_and_public_view','private_rows',visible_count,'pass',TRUE));
    EXECUTE 'RESET ROLE';

    PERFORM set_config('request.jwt.claim.role', 'service_role', TRUE);
    PERFORM set_config('request.jwt.claims', '{"role":"service_role"}', TRUE);
    EXECUTE 'SET LOCAL ROLE service_role';
    SELECT count(*) INTO visible_count FROM public.profiles;
    IF visible_count <> total_count THEN RAISE EXCEPTION 'Admin server access failed'; END IF;
    checks := checks || jsonb_build_array(jsonb_build_object('case','admin_server','pass',TRUE));
    EXECUTE 'RESET ROLE';

    IF has_function_privilege('anon','public.admin_approve_profile(uuid)','EXECUTE')
        OR has_function_privilege('anon','public.admin_reject_profile(uuid)','EXECUTE')
        OR NOT has_function_privilege('authenticated','public.admin_approve_profile(uuid)','EXECUTE')
        OR NOT has_function_privilege('authenticated','public.admin_reject_profile(uuid)','EXECUTE')
    THEN RAISE EXCEPTION 'RPC grants failed'; END IF;
    checks := checks || jsonb_build_array(jsonb_build_object('case','rpc_grants','pass',TRUE));
    PERFORM set_config('profile_boundary.verification', checks::TEXT, TRUE);
END;
$$;
SELECT current_setting('profile_boundary.verification')::JSONB AS checks;
ROLLBACK;
