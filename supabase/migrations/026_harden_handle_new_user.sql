-- ═══════════════════════════════════════════════════════════════
-- 026: 회원가입 "Database error saving new user" 방어 (2026-07-24)
-- ───────────────────────────────────────────────────────────────
-- 증상 = 신규 가입 시도 → Supabase Auth "Database error saving new user".
-- 원인 = auth.users INSERT 후 on_auth_user_created(handle_new_user) 트리거가
--        profiles INSERT 중 예외를 던지면 auth signup 트랜잭션 전체가 롤백됨.
-- 조치:
--   (1) profiles 컬럼을 안전 default 로 재확인(부분/누락 적용 대비, 전부 idempotent)
--   (2) handle_new_user 를 예외-안전화 — profiles 생성이 실패해도 회원가입은 성공시킴
--       (프로필은 AuthPage.ensureProfile 또는 다음 로그인에서 복구됨)
--   (3) consent 값을 boolean/문자열 무엇이든 cast 예외 없이 파싱
-- Supabase Dashboard → SQL Editor 에서 실행. 재실행 안전.
-- ═══════════════════════════════════════════════════════════════

-- 1) profiles 컬럼 안전 default 재확인 (idempotent · 이미 있으면 무변경)
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS display_name     TEXT DEFAULT '';
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS avatar_url       TEXT DEFAULT '';
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS phone            TEXT DEFAULT '';
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS status           TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS consent_given_at TIMESTAMPTZ;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS is_admin         BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS is_super_admin   BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS nickname         TEXT NOT NULL DEFAULT '';
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS avatar           TEXT NOT NULL DEFAULT '';
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS bio              TEXT NOT NULL DEFAULT '';

-- 2) handle_new_user 예외-안전화
--    · INSERT 를 서브블록(BEGIN…EXCEPTION)으로 감싸 profiles 실패가 signup 을 막지 않게 함.
--    · consent 는 boolean/'true'/'t'/'1'/'yes' 모두 안전 파싱 (::BOOLEAN cast 예외 제거).
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    raw_phone   TEXT;
    raw_consent BOOLEAN;
BEGIN
    BEGIN
        raw_phone   := COALESCE(NEW.raw_user_meta_data ->> 'phone', '');
        raw_consent := COALESCE(
            lower(NEW.raw_user_meta_data ->> 'consent') IN ('true', 't', '1', 'yes'),
            FALSE
        );

        INSERT INTO public.profiles (id, email, display_name, phone, consent_given_at, status)
        VALUES (
            NEW.id,
            NEW.email,
            COALESCE(NEW.raw_user_meta_data ->> 'name', split_part(NEW.email, '@', 1)),
            raw_phone,
            CASE WHEN raw_consent THEN now() ELSE NULL END,
            'pending'
        )
        ON CONFLICT (id) DO UPDATE SET
            email            = EXCLUDED.email,
            phone            = CASE WHEN EXCLUDED.phone <> '' THEN EXCLUDED.phone ELSE public.profiles.phone END,
            consent_given_at = COALESCE(public.profiles.consent_given_at, EXCLUDED.consent_given_at),
            updated_at       = now();
    EXCEPTION WHEN OTHERS THEN
        -- 프로필 생성이 실패해도 회원가입 자체는 성공시킴 (프로필은 이후 복구).
        RAISE WARNING 'handle_new_user: profile 생성 실패(무시하고 signup 진행) — %', SQLERRM;
    END;
    RETURN NEW;
END;
$$;

-- 트리거 자체(on_auth_user_created)는 003 에서 이미 생성됨 — 함수만 교체.
