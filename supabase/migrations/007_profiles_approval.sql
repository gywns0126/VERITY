-- ═════════════════════════════════════════════════════════════════
-- 007: profiles 승인제 컬럼 보강
-- ─────────────────────────────────────────────────────────────────
-- 배경:
--   framer-components/AuthPage.tsx 가 profiles.status / phone / consent_given_at
--   컬럼을 사용하는데 003_auth_profiles.sql 에는 해당 컬럼이 없어서
--   현재 모든 로그인이 status=missing 으로 분기되어 거절되는 상태였음.
--
-- 추가 항목:
--   1) status            — pending | approved | rejected
--                          기본 'pending' (가입 즉시 가입 신청 상태)
--   2) phone             — 연락처 (가입 폼 필수, 운영자가 본인 확인용)
--   3) consent_given_at  — 개인정보 수집·이용 동의 시각
--   4) handle_new_user trigger 업데이트
--      raw_user_meta_data 에서 phone / consent 추출 + status 'pending' 명시
--   5) admin 승인용 RLS 정책
--      service_role 만 status 컬럼 update 가능 (anon/authenticated 는 읽기만)
--
-- ESTATE RLS 영향:
--   estate_groups, estate_alerts 등은 auth.uid() 만 체크 (status 무관).
--   따라서 가입 직후 (pending) 사용자도 ESTATE 데이터 *조회* 가능.
--   AuthPage 가 status='approved' 만 세션 저장하므로 미승인은 클라이언트 단에서 차단.
-- ═════════════════════════════════════════════════════════════════

-- 1) profiles 컬럼 추가 (idempotent)
ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected'));

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS phone TEXT DEFAULT '';

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS consent_given_at TIMESTAMPTZ;

-- 운영자 콘솔에서 자주 필터링: pending 만 추리거나 status 별 카운트
CREATE INDEX IF NOT EXISTS idx_profiles_status ON public.profiles(status);


-- 2) handle_new_user trigger 업데이트
--    auth.users INSERT 시 raw_user_meta_data 에서 phone / consent 추출.
--    AuthPage.tsx 의 signUp() 이 raw_user_meta_data 에 다음 키 저장함:
--      { name, phone, consent }
--    consent 가 true 면 consent_given_at = now() 로 기록.
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    raw_phone   TEXT;
    raw_consent BOOLEAN;
BEGIN
    raw_phone   := COALESCE(NEW.raw_user_meta_data ->> 'phone', '');
    raw_consent := COALESCE((NEW.raw_user_meta_data ->> 'consent')::BOOLEAN, FALSE);

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
        email = EXCLUDED.email,
        -- 재가입·OAuth 재로그인 케이스에서 phone/consent 비어있지 않으면 갱신
        phone = CASE WHEN EXCLUDED.phone <> '' THEN EXCLUDED.phone ELSE public.profiles.phone END,
        consent_given_at = COALESCE(public.profiles.consent_given_at, EXCLUDED.consent_given_at),
        updated_at = now();
    RETURN NEW;
END;
$$;

-- (트리거 자체는 003 에서 이미 생성됨. 함수만 갱신.)


-- 3) 관리자 승인 RLS — service_role 만 status 변경 가능
--    003 의 profiles_update_own 은 본인이 자기 행 update 가능 (display_name 등).
--    그러나 본인이 자기 status 를 'approved' 로 바꾸면 안 됨 → 별도 보호 필요.
--    PostgreSQL 에 컬럼 단위 정책이 없어서 트리거로 차단.
CREATE OR REPLACE FUNCTION public.profiles_block_self_status_change()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = ''
AS $$
BEGIN
    IF NEW.status IS DISTINCT FROM OLD.status THEN
        -- service_role 은 auth.role() = 'service_role'. 다른 role 은 차단.
        IF auth.role() <> 'service_role' THEN
            RAISE EXCEPTION 'profiles.status 는 service_role 만 변경할 수 있습니다 (현재 role: %)', auth.role();
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS profiles_block_self_status ON public.profiles;
CREATE TRIGGER profiles_block_self_status
    BEFORE UPDATE ON public.profiles
    FOR EACH ROW EXECUTE FUNCTION public.profiles_block_self_status_change();


-- 4) 기존 미승인 계정 마이그레이션
--    003 시점 이후로 이미 가입한 계정이 있다면 모두 'pending' 상태로 시작.
--    (ALTER COLUMN ADD DEFAULT 가 기존 행에도 적용되지만 명시적으로 안전망)
UPDATE public.profiles SET status = 'pending' WHERE status IS NULL;


-- 5) 운영 편의: 관리자가 승인 처리할 때 호출하는 함수 (service_role 전용)
--    Supabase Dashboard SQL Editor 또는 admin 라우트에서 호출.
CREATE OR REPLACE FUNCTION public.admin_approve_profile(target_id UUID)
RETURNS public.profiles
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    row public.profiles;
BEGIN
    IF auth.role() <> 'service_role' THEN
        RAISE EXCEPTION 'admin_approve_profile 는 service_role 전용';
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
BEGIN
    IF auth.role() <> 'service_role' THEN
        RAISE EXCEPTION 'admin_reject_profile 는 service_role 전용';
    END IF;
    UPDATE public.profiles
       SET status = 'rejected', updated_at = now()
     WHERE id = target_id
    RETURNING * INTO row;
    RETURN row;
END;
$$;
