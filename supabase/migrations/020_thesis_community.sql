-- ═════════════════════════════════════════════════════════════════
-- 020: 내 관점 커뮤니티 v1 — 공개 토글 + 좋아요 + 신고 + 공개 프로필 view
-- ─────────────────────────────────────────────────────────────────
-- 배경 (2026-07-10 PM 승인): user_thesis(018) 는 본인 저널. 사용자가 공개로
--   전환하면 같은 종목의 공개 관점 피드에 노출 + 좋아요. 댓글 = v2.
--
-- 설계:
--   1) user_thesis.is_public (기본 false=비공개) + hidden (운영자 숨김, 신고 처리용).
--   2) 공개행 SELECT 정책 추가 — 기존 ut_select(본인) 과 OR 결합. anon 도 피드 조회 가능.
--   3) public_profiles view = profiles 에서 (id, nickname, avatar) 만 노출.
--      🚨 019 에서 미룬 "타인 별명·아바타 조회" 경로. security definer(기본) 로
--      profiles RLS 를 의도적으로 우회하되 email/phone 은 view 밖 = 유출 차단.
--      nickname <> '' 행만 (별명 없는 사용자는 공개 피드 표시 대상 아님).
--   4) thesis_likes = (thesis_id, user_id) PK. 좋아요 수 = 공개 정보 → SELECT true.
--      INSERT 는 공개 상태의 thesis 에만 (타 테이블 EXISTS — 같은 테이블 아님, 재귀 없음).
--   5) thesis_reports = 신고 접수함. INSERT 만 열고 SELECT 정책 없음(운영자 대시보드 전용).
--      숨김 처리 = 운영자가 대시보드에서 hidden=true (서비스 role, RLS 밖).
--   6) 별명 없는 사용자의 공개 전환 차단 = API(thesis.py) 레이어 검증 (v1).
-- ═════════════════════════════════════════════════════════════════

-- 1) user_thesis 공개/숨김 컬럼
ALTER TABLE public.user_thesis
    ADD COLUMN IF NOT EXISTS is_public BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE public.user_thesis
    ADD COLUMN IF NOT EXISTS hidden BOOLEAN NOT NULL DEFAULT false;

-- 공개 피드 조회용 인덱스 (ticker 별 공개행)
CREATE INDEX IF NOT EXISTS idx_ut_public_ticker
    ON public.user_thesis(ticker, created_at DESC) WHERE is_public AND NOT hidden;

-- 2) 공개행 SELECT — 누구나(anon 포함). 본인행 정책(ut_select)과 OR.
DROP POLICY IF EXISTS ut_select_public ON public.user_thesis;
CREATE POLICY ut_select_public ON public.user_thesis
    FOR SELECT USING (is_public = true AND hidden = false);

-- 3) 공개 프로필 view — 커뮤니티 표시용 3컬럼만. email/phone/status 노출 금지.
CREATE OR REPLACE VIEW public.public_profiles AS
    SELECT id, nickname, avatar
    FROM public.profiles
    WHERE nickname <> '';
GRANT SELECT ON public.public_profiles TO anon, authenticated;

-- 4) 좋아요
CREATE TABLE IF NOT EXISTS public.thesis_likes (
    thesis_id  UUID NOT NULL REFERENCES public.user_thesis(id) ON DELETE CASCADE,
    user_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (thesis_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_tl_thesis ON public.thesis_likes(thesis_id);

ALTER TABLE public.thesis_likes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tl_select ON public.thesis_likes;
CREATE POLICY tl_select ON public.thesis_likes
    FOR SELECT USING (true);
DROP POLICY IF EXISTS tl_insert ON public.thesis_likes;
CREATE POLICY tl_insert ON public.thesis_likes
    FOR INSERT WITH CHECK (
        auth.uid() = user_id
        AND EXISTS (
            SELECT 1 FROM public.user_thesis t
            WHERE t.id = thesis_id AND t.is_public AND NOT t.hidden
        )
    );
DROP POLICY IF EXISTS tl_delete ON public.thesis_likes;
CREATE POLICY tl_delete ON public.thesis_likes
    FOR DELETE USING (auth.uid() = user_id);

-- 5) 신고 접수함 — 로그인 사용자 INSERT 만. 조회/처리 = 운영자 대시보드.
CREATE TABLE IF NOT EXISTS public.thesis_reports (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    thesis_id   UUID NOT NULL REFERENCES public.user_thesis(id) ON DELETE CASCADE,
    reporter_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    reason      TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT thesis_reports_reason_len CHECK (char_length(reason) <= 500)
);
ALTER TABLE public.thesis_reports ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tr_insert ON public.thesis_reports;
CREATE POLICY tr_insert ON public.thesis_reports
    FOR INSERT WITH CHECK (auth.uid() = reporter_id);
