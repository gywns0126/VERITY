-- Keep financial/account fields in profiles private to the signed-in member.
-- General site administration uses /api/admin?type=member_management, whose
-- server-side service role projects administrative fields only. Do not restore
-- broad raw profile access to make an admin UI work: extend that projection.
-- Existing permissive policies OR together. A restrictive policy ANDs this
-- boundary with them, including future permissive policies.
-- https://www.postgresql.org/docs/current/sql-createpolicy.html
BEGIN;

DROP POLICY IF EXISTS profiles_private_row_boundary ON public.profiles;
CREATE POLICY profiles_private_row_boundary ON public.profiles
    AS RESTRICTIVE FOR ALL TO anon, authenticated
    USING (auth.role() = 'authenticated' AND auth.uid() = id)
    WITH CHECK (auth.role() = 'authenticated' AND auth.uid() = id);

-- Preserve the legacy RPC signatures, but never return a whole private row.
-- A composite built from an allowlist also masks columns added in the future.
-- The deployed profiles schema has no updated_at column; change status only.
CREATE OR REPLACE FUNCTION public.admin_approve_profile(target_id UUID)
RETURNS public.profiles
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    result_id UUID;
    result_status TEXT;
BEGIN
    IF NOT COALESCE(
        auth.role() = 'service_role'
        OR (auth.role() = 'authenticated' AND public.is_caller_admin()),
        FALSE
    ) THEN
        RAISE EXCEPTION 'admin_approve_profile: permission denied'
            USING ERRCODE = '42501';
    END IF;
    UPDATE public.profiles
       SET status = 'approved'
     WHERE id = target_id
    RETURNING id, status INTO result_id, result_status;
    IF NOT FOUND THEN
        RETURN NULL;
    END IF;
    RETURN jsonb_populate_record(NULL::public.profiles,
        jsonb_build_object('id', result_id, 'status', result_status));
END;
$$;

CREATE OR REPLACE FUNCTION public.admin_reject_profile(target_id UUID)
RETURNS public.profiles
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    result_id UUID;
    result_status TEXT;
BEGIN
    IF NOT COALESCE(
        auth.role() = 'service_role'
        OR (auth.role() = 'authenticated' AND public.is_caller_admin()),
        FALSE
    ) THEN
        RAISE EXCEPTION 'admin_reject_profile: permission denied'
            USING ERRCODE = '42501';
    END IF;
    UPDATE public.profiles
       SET status = 'rejected'
     WHERE id = target_id
    RETURNING id, status INTO result_id, result_status;
    IF NOT FOUND THEN
        RETURN NULL;
    END IF;
    RETURN jsonb_populate_record(NULL::public.profiles,
        jsonb_build_object('id', result_id, 'status', result_status));
END;
$$;

REVOKE ALL ON FUNCTION public.admin_approve_profile(UUID) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.admin_reject_profile(UUID) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.admin_approve_profile(UUID) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.admin_reject_profile(UUID) TO authenticated, service_role;

COMMIT;
