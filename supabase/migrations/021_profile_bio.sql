-- ═════════════════════════════════════════════════════════════════
-- 021: profiles 한 줄 소개(bio) — 인스타식 프로필 편집 화면 (2026-07-10 PM 선택)
-- ─────────────────────────────────────────────────────────────────
-- 019(별명·아바타) → 020(커뮤니티) 이후 실행 권장. 단독 실행도 안전(idempotent).
-- bio = 공개 의도 필드 → public_profiles view 에 포함 (커뮤니티 피드 v2 에서 표시명 옆 노출 예정).
-- ═════════════════════════════════════════════════════════════════

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS bio TEXT NOT NULL DEFAULT '';

ALTER TABLE public.profiles DROP CONSTRAINT IF EXISTS profiles_bio_len;
ALTER TABLE public.profiles
    ADD CONSTRAINT profiles_bio_len CHECK (char_length(bio) <= 40);

-- 공개 프로필 view 갱신 (020 미실행 상태여도 이 문장이 view 를 생성 — 3+1 컬럼만, email/phone 차단 유지)
CREATE OR REPLACE VIEW public.public_profiles AS
    SELECT id, nickname, avatar, bio
    FROM public.profiles
    WHERE nickname <> '';
GRANT SELECT ON public.public_profiles TO anon, authenticated;
