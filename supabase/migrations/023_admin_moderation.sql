-- 023_admin_moderation.sql
-- 관리자 운영 기능: 회원 제재(ban) + 커뮤니티 모더레이션 + 감사 로그.
-- PM 결정 2026-07-15:
--   · 제재(ban) 범위 = 쓰기(글·좋아요·신고) 차단. 읽기·로그인은 허용.
--   · 회원 '삭제' = 앱단 2단계 확인 후 admin.py(service_role)가 auth 계정 삭제(cascade). 여기선 컬럼만.
-- is_caller_admin() = 008 정의 재사용 (SECURITY DEFINER, 재귀 없음 — feedback_supabase_rls_no_self_subquery 정합).
-- 관리자 변경의 실제 실행 = admin.py 가 service_role 키로 수행(RLS 우회) + 호출자 is_admin 재검증.
--   아래 RLS 정책은 방어층(관리자 JWT 직접 경로 대비) — service_role 은 어차피 RLS 우회.

-- ── 1) profiles 제재 컬럼 ─────────────────────────────────────────────
ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS is_banned  BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS ban_reason TEXT,
    ADD COLUMN IF NOT EXISTS banned_at  TIMESTAMPTZ;

-- ── 2) 제재 유저 쓰기 차단 트리거 ────────────────────────────────────
-- user_thesis(INSERT/UPDATE) · thesis_likes(INSERT) · thesis_reports(INSERT) 시 is_banned 검사.
-- service_role(관리자 API) = 예외. 읽기·로그인은 트리거 미적용이라 영향 없음.
CREATE OR REPLACE FUNCTION public.block_banned_write()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    v_banned BOOLEAN;
BEGIN
    IF auth.role() = 'service_role' THEN
        RETURN NEW;
    END IF;
    SELECT COALESCE(p.is_banned, FALSE) INTO v_banned
      FROM public.profiles p WHERE p.id = auth.uid();
    IF COALESCE(v_banned, FALSE) THEN
        RAISE EXCEPTION '제재된 계정은 커뮤니티 활동이 제한됩니다.';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_block_banned_thesis ON public.user_thesis;
CREATE TRIGGER trg_block_banned_thesis
    BEFORE INSERT OR UPDATE ON public.user_thesis
    FOR EACH ROW EXECUTE FUNCTION public.block_banned_write();

DROP TRIGGER IF EXISTS trg_block_banned_like ON public.thesis_likes;
CREATE TRIGGER trg_block_banned_like
    BEFORE INSERT ON public.thesis_likes
    FOR EACH ROW EXECUTE FUNCTION public.block_banned_write();

DROP TRIGGER IF EXISTS trg_block_banned_report ON public.thesis_reports;
CREATE TRIGGER trg_block_banned_report
    BEFORE INSERT ON public.thesis_reports
    FOR EACH ROW EXECUTE FUNCTION public.block_banned_write();

-- ── 3) 관리자 모더레이션 RLS (방어층) ────────────────────────────────
-- 관리자 = 전체 글 조회·수정·삭제 (숨김/삭제 모더레이션).
DROP POLICY IF EXISTS ut_admin_all ON public.user_thesis;
CREATE POLICY ut_admin_all ON public.user_thesis
    FOR ALL TO authenticated
    USING (public.is_caller_admin())
    WITH CHECK (public.is_caller_admin());

-- 관리자 = 신고 접수함 조회 (신고 큐 대시보드).
DROP POLICY IF EXISTS tr_select_admin ON public.thesis_reports;
CREATE POLICY tr_select_admin ON public.thesis_reports
    FOR SELECT TO authenticated
    USING (public.is_caller_admin());

-- 관리자 = 전 회원 정보 수정 (별명·상태·제재). 008 profiles_select_admin 은 조회만이라 UPDATE 추가.
DROP POLICY IF EXISTS profiles_update_admin ON public.profiles;
CREATE POLICY profiles_update_admin ON public.profiles
    FOR UPDATE TO authenticated
    USING (public.is_caller_admin())
    WITH CHECK (public.is_caller_admin());

-- ── 4) 관리자 감사 로그 ──────────────────────────────────────────────
-- 누가(actor)·뭘(action)·누구를(target)·언제 — 제재/삭제/수정 전부 기록.
-- INSERT = admin.py(service_role) 만 (RLS 우회). SELECT = 관리자.
CREATE TABLE IF NOT EXISTS public.admin_audit_log (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    actor_id    UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    actor_email TEXT,
    action      TEXT NOT NULL,          -- ban_user | unban_user | delete_user | update_profile | delete_post | hide_post | unhide_post
    target_type TEXT NOT NULL,          -- user | thesis
    target_id   TEXT,
    detail      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_admin_audit_created ON public.admin_audit_log (created_at DESC);
ALTER TABLE public.admin_audit_log ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS aal_select_admin ON public.admin_audit_log;
CREATE POLICY aal_select_admin ON public.admin_audit_log
    FOR SELECT TO authenticated
    USING (public.is_caller_admin());
-- INSERT 정책 없음 = service_role(admin.py) 만 기록 가능.
