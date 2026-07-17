-- 025_super_admin.sql
-- 2단계 관리자: 최종 관리자(super_admin) + 부관리자(admin).
-- PM 결정 2026-07-17:
--   · 최종 관리자 = 소유자 계정(gywns0126@gmail.com). 모든 권한 + 부관리자 지정/해제 독점.
--   · 부관리자 = is_admin=true · is_super_admin=false. 권한은 최종 관리자와 동일하나 부관리자 지정/해제만 불가.
--   · is_super_admin = 앱에서 변경 불가(이 마이그레이션/DB 콘솔 전용) → 권한상승·자가승격 차단.
-- 023 트리거(profiles_block_privileged_change) 를 super 게이트로 강화(함수 교체, 트리거 재연결 불요).

-- ── 1) 컬럼 + 부트스트랩(소유자 = 최종 관리자) ──────────────────────
ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS is_super_admin BOOLEAN NOT NULL DEFAULT FALSE;

-- 소유자 계정을 최종 관리자로 시드 (부트스트랩 — 앱에서는 이후 변경 불가).
UPDATE public.profiles
    SET is_super_admin = TRUE, is_admin = TRUE
    WHERE email = 'gywns0126@gmail.com';

-- ── 2) 권한 변경 트리거 강화 ────────────────────────────────────────
-- is_banned = 관리자(부관리자 포함) 이상 / is_admin(부관리자 지정) = 최종 관리자만 / is_super_admin = 앱 변경 불가.
-- service_role(admin.py) = 예외(RETURN NEW) — admin.py 가 자체적으로 super 게이트 재검증(2중 방어).
CREATE OR REPLACE FUNCTION public.profiles_block_privileged_change()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    v_admin BOOLEAN;
    v_super BOOLEAN;
BEGIN
    IF auth.role() = 'service_role' THEN
        RETURN NEW;
    END IF;
    SELECT COALESCE(p.is_admin, FALSE), COALESCE(p.is_super_admin, FALSE)
      INTO v_admin, v_super
      FROM public.profiles p WHERE p.id = auth.uid();

    -- 제재 필드 = 관리자(부관리자 포함) 이상
    IF NEW.is_banned  IS DISTINCT FROM OLD.is_banned
       OR NEW.ban_reason IS DISTINCT FROM OLD.ban_reason
       OR NEW.banned_at  IS DISTINCT FROM OLD.banned_at THEN
        IF NOT COALESCE(v_admin, FALSE) THEN
            RAISE EXCEPTION '제재 필드는 관리자만 변경할 수 있습니다.';
        END IF;
    END IF;

    -- is_admin(부관리자 지정/해제) = 최종 관리자만
    IF NEW.is_admin IS DISTINCT FROM OLD.is_admin THEN
        IF NOT COALESCE(v_super, FALSE) THEN
            RAISE EXCEPTION '부관리자 지정/해제는 최종 관리자만 가능합니다.';
        END IF;
    END IF;

    -- is_super_admin = 앱에서 절대 변경 불가 (마이그레이션/DB 콘솔 전용)
    IF NEW.is_super_admin IS DISTINCT FROM OLD.is_super_admin THEN
        RAISE EXCEPTION 'is_super_admin 은 앱에서 변경할 수 없습니다.';
    END IF;

    RETURN NEW;
END;
$$;
-- 트리거 trg_block_privileged_profile = 023 에서 이미 BEFORE UPDATE ON public.profiles 연결됨 (함수만 교체).
