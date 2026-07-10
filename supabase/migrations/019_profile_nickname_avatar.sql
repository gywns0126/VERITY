-- ═════════════════════════════════════════════════════════════════
-- 019: profiles 별명(nickname)·프로필 사진(avatar) — 커뮤니티 표시명 선행 인프라
-- ─────────────────────────────────────────────────────────────────
-- 배경 (2026-07-10 PM "프로필 설정해서 자기 아이디(별명), 프로필 사진 넣을 수 있게 고고"):
--   내 관점 커뮤니티(공개 메모 피드) 전에 표시명 체계 필요 — 이메일 노출 불가.
--   /me(PublicProfilePage)에서 본인이 별명·사진 설정.
--
-- 설계:
--   1) avatar = 클라이언트 리사이즈(128×128 JPEG) base64 data-URL (~10KB) 인라인 저장.
--      Supabase Storage 대신 컬럼 인라인 = v1 단순화(신규 버킷/정책 0, 기존 REST 패턴 재사용).
--      스케일 시 Storage 이전 경로 열려 있음. CHECK 로 150KB 상한(폭주 차단).
--   2) nickname = 2~16자, 유일(대소문자 무시, 빈 값 제외). 충돌 = PostgREST 409 → 프론트 안내.
--   3) UPDATE 권한 = 기존 profiles_update_own(003) 커버 — 본인 행 update 가능.
--      status 변경 차단 trigger(007/008)는 nickname/avatar 와 무관(해당 컬럼만 감시).
--   4) 🚨 커뮤니티 "타인 별명·아바타 조회"는 이 파일에서 안 엶 — profiles 행 전체를
--      공개 SELECT 하면 email/phone 유출. 후속 마이그레이션에서 전용 view
--      (id, nickname, avatar 만 노출) 로 처리 예정.
-- ═════════════════════════════════════════════════════════════════

-- 1) 컬럼 추가 (idempotent)
ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS nickname TEXT NOT NULL DEFAULT '';

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS avatar TEXT NOT NULL DEFAULT '';

-- 2) 길이 상한 (avatar base64 폭주 차단 / nickname 16자)
ALTER TABLE public.profiles DROP CONSTRAINT IF EXISTS profiles_nickname_len;
ALTER TABLE public.profiles
    ADD CONSTRAINT profiles_nickname_len CHECK (char_length(nickname) <= 16);

ALTER TABLE public.profiles DROP CONSTRAINT IF EXISTS profiles_avatar_len;
ALTER TABLE public.profiles
    ADD CONSTRAINT profiles_avatar_len CHECK (char_length(avatar) <= 150000);

-- 3) 별명 유일 (대소문자 무시 · 빈 값 제외) — 충돌 시 PostgREST 409
CREATE UNIQUE INDEX IF NOT EXISTS idx_profiles_nickname_uniq
    ON public.profiles (lower(nickname)) WHERE nickname <> '';
