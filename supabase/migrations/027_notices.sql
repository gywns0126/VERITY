-- ═════════════════════════════════════════════════════════════════
-- 027: 공지 · 이벤트 (notices) — 관리자 발행, 공개 읽기
-- ─────────────────────────────────────────────────────────────────
-- 배경 (2026-07-26 PM): 커뮤니티 페이지에 공지/이벤트 배관. 이벤트는 별도 테이블이
--   아니라 kind='event' 로 같은 배관 재사용 (사용자 0명 시점에 이벤트 전용 빌드는 과함).
--
-- 설계:
--   1) 공개 읽기 = 활성 + 노출 기간 내 행만. anon 포함 (RLS SELECT 정책).
--   2) 쓰기 정책 없음 = 서비스 role(admin API `/api/admin?type=notices`) 만 가능.
--      020 의 thesis_reports 와 동일 패턴 — 운영 쓰기는 RLS 밖에서.
--   3) pinned = 상단 고정. 커뮤니티 배너는 pinned 우선 → 최신순 1건 노출.
--   4) starts_at/ends_at NULL = 무기한. 이벤트 종료 시 자동으로 공개에서 빠짐
--      (is_active 를 손대지 않아도 됨 = 운영 실수 방지).
--
-- 번호 주의: 026 은 브랜치(fix/newstab-window-lazy)의 026_harden_handle_new_user.sql 이
--   main 에 아직 미머지 상태라 번호 충돌 회피 목적으로 027 사용.
-- ═════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS public.notices (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind        TEXT NOT NULL DEFAULT 'notice' CHECK (kind IN ('notice', 'event')),
    title       TEXT NOT NULL CHECK (char_length(title) BETWEEN 1 AND 120),
    body        TEXT NOT NULL DEFAULT '' CHECK (char_length(body) <= 2000),
    link        TEXT NOT NULL DEFAULT '' CHECK (char_length(link) <= 500),
    pinned      BOOLEAN NOT NULL DEFAULT false,
    starts_at   TIMESTAMPTZ,
    ends_at     TIMESTAMPTZ,
    is_active   BOOLEAN NOT NULL DEFAULT true,
    created_by  UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 공개 목록 조회용 (고정 우선 → 최신)
CREATE INDEX IF NOT EXISTS idx_notices_live
    ON public.notices(pinned DESC, created_at DESC) WHERE is_active;

ALTER TABLE public.notices ENABLE ROW LEVEL SECURITY;

-- 공개 읽기 = 활성 + 노출 기간 내. anon 포함.
DROP POLICY IF EXISTS nt_select_public ON public.notices;
CREATE POLICY nt_select_public ON public.notices
    FOR SELECT USING (
        is_active = true
        AND (starts_at IS NULL OR starts_at <= now())
        AND (ends_at   IS NULL OR ends_at   >= now())
    );

-- 🚨 INSERT/UPDATE/DELETE 정책 없음 = 사용자 JWT 로는 쓰기 불가.
--    발행/수정/삭제 = admin API 의 서비스 role 경로만 (감사 로그 동반).

-- updated_at 자동 갱신
CREATE OR REPLACE FUNCTION public.touch_notices_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_notices_touch ON public.notices;
CREATE TRIGGER trg_notices_touch
    BEFORE UPDATE ON public.notices
    FOR EACH ROW EXECUTE FUNCTION public.touch_notices_updated_at();
