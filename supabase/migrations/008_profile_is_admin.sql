-- ═════════════════════════════════════════════════════════════════
-- 008: profiles.is_admin + 관리자 RLS·RPC 권한 확장
-- ─────────────────────────────────────────────────────────────────
-- 배경:
--   007 에서 profiles.status 추가했지만 status 변경은 service_role 전용.
--   운영자가 가입 승인 처리하려면 매번 SQL 직접 호출하거나 service_role 키를
--   클라이언트에 노출해야 함 (보안 위험).
--
--   008 은 `is_admin` 컬럼 + admin 사용자도 RLS·RPC 우회 가능하게 보강.
--   AdminDashboard 카드가 본인 JWT 만으로 가입 승인 처리 가능.
--
-- 변경 항목:
--   1) profiles.is_admin BOOLEAN 컬럼 (default FALSE)
--   2) profiles_select_admin 정책 — admin 은 모든 profile 조회
--   3) profiles_block_self_status_change trigger — admin 도 허용
--   4) admin_approve_profile / admin_reject_profile RPC — admin 도 허용
-- ═════════════════════════════════════════════════════════════════

-- 1) is_admin 컬럼 (idempotent)
ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE;

-- partial index — admin 검색 빠르게 (대부분 row 는 false)
CREATE INDEX IF NOT EXISTS idx_profiles_is_admin
    ON public.profiles(id) WHERE is_admin = TRUE;


-- 2) admin 은 모든 profile 조회 가능 (003 의 profiles_select_own 과 OR 결합)
DROP POLICY IF EXISTS profiles_select_admin ON public.profiles;
CREATE POLICY profiles_select_admin ON public.profiles
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.profiles p
            WHERE p.id = auth.uid() AND p.is_admin = TRUE
        )
    );


-- 3) status 변경 trigger — admin 도 허용
CREATE OR REPLACE FUNCTION public.profiles_block_self_status_change()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    is_caller_admin BOOLEAN;
BEGIN
    IF NEW.status IS DISTINCT FROM OLD.status THEN
        SELECT COALESCE(p.is_admin, FALSE) INTO is_caller_admin
          FROM public.profiles p
         WHERE p.id = auth.uid();

        IF auth.role() <> 'service_role' AND NOT COALESCE(is_caller_admin, FALSE) THEN
            RAISE EXCEPTION 'profiles.status 는 service_role 또는 admin 사용자만 변경할 수 있습니다 (현재 role: %)', auth.role();
        END IF;
    END IF;
    RETURN NEW;
END;
$$;


-- 4) admin RPC — admin 사용자도 호출 가능
CREATE OR REPLACE FUNCTION public.admin_approve_profile(target_id UUID)
RETURNS public.profiles
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    row public.profiles;
    is_caller_admin BOOLEAN;
BEGIN
    SELECT COALESCE(p.is_admin, FALSE) INTO is_caller_admin
      FROM public.profiles p WHERE p.id = auth.uid();

    IF auth.role() <> 'service_role' AND NOT COALESCE(is_caller_admin, FALSE) THEN
        RAISE EXCEPTION 'admin_approve_profile: 권한 없음 (service_role 또는 admin 만)';
    END IF;
    UPDATE public.profiles
       SET status = 'approved', updated_at = now()
     WHERE id = target_id
    RETURNING * INTO row;
    RETURN row;
END;
$$;

CREATE OR REPLACE FUNCTION public.admin_reject_profile(target_id UUID)
RETURNS public.profiles
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    row public.profiles;
    is_caller_admin BOOLEAN;
BEGIN
    SELECT COALESCE(p.is_admin, FALSE) INTO is_caller_admin
      FROM public.profiles p WHERE p.id = auth.uid();

    IF auth.role() <> 'service_role' AND NOT COALESCE(is_caller_admin, FALSE) THEN
        RAISE EXCEPTION 'admin_reject_profile: 권한 없음';
    END IF;
    UPDATE public.profiles
       SET status = 'rejected', updated_at = now()
     WHERE id = target_id
    RETURNING * INTO row;
    RETURN row;
END;
$$;


-- 5) 운영자 본인 admin 으로 (사용자 직접 실행 — 적용 후 한 번)
-- 다른 admin 추가 시 동일 패턴.
--   UPDATE public.profiles SET is_admin = TRUE WHERE email = 'gywns0126@gmail.com';
