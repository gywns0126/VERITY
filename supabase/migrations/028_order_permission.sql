-- 028_order_permission — 실주문 권한 플래그 (PM 승인 2026-08-05)
--
-- 배경: vercel-api/api/order.py 가 profiles.order_enabled / max_order_krw /
--   daily_order_count_limit 을 읽는데 **컬럼이 존재하지 않았다**. 조회 실패 → 기본값
--   order_enabled=False → 모든 주문이 403. 즉 매매창이 설계상 fail-closed 로 잠겨 있었음.
--
-- 🚨 보안 핵심: profiles 는 공개 알파네스트 회원도 행을 갖는 테이블이다. 회원이 자기
--   order_enabled 를 true 로 UPDATE 하면 **오퍼레이터의 KIS 실계좌로 주문**을 낼 수 있다.
--   → 기존 트리거 profiles_block_privileged_change 에 주문 필드를 추가해
--     service_role(DB 직접) 이외 전부 차단한다. **관리자·최종관리자도 UI 로 못 켠다.**
--     (제재/is_admin 은 관리자 허용이지만 주문은 실자금이라 등급을 한 칸 더 올림.)
--
-- 적용: Supabase 대시보드 SQL Editor 에서 실행 (019·020 과 동일 경로).

-- ── 1) 컬럼 (기본 잠금) ────────────────────────────────────────────
ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS order_enabled BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS max_order_krw INTEGER NOT NULL DEFAULT 1000000;
ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS daily_order_count_limit INTEGER NOT NULL DEFAULT 5;

COMMENT ON COLUMN public.profiles.order_enabled IS
    '실주문 허용 — service_role(DB 직접)만 변경 가능. 실자금 스위치.';
COMMENT ON COLUMN public.profiles.max_order_krw IS '건당 주문 금액 상한(원).';
COMMENT ON COLUMN public.profiles.daily_order_count_limit IS '일일 주문 횟수 상한.';

-- ── 2) 권한 상승 차단 트리거 확장 (주문 필드 = service_role 전용) ──
--   기존 함수(025)를 그대로 계승하고 주문 3필드 가드만 추가. 트리거 연결은 023 에서 이미 됨.
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

    -- 🚨 주문 권한·한도 = 실자금. service_role(DB 직접) 이외 전부 차단(관리자 포함).
    IF NEW.order_enabled IS DISTINCT FROM OLD.order_enabled
       OR NEW.max_order_krw IS DISTINCT FROM OLD.max_order_krw
       OR NEW.daily_order_count_limit IS DISTINCT FROM OLD.daily_order_count_limit THEN
        RAISE EXCEPTION '주문 권한/한도는 DB 직접(service_role)으로만 변경할 수 있습니다.';
    END IF;

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

    -- is_super_admin = 누구도 UI 로 변경 불가 (DB 직접만)
    IF NEW.is_super_admin IS DISTINCT FROM OLD.is_super_admin THEN
        RAISE EXCEPTION '최종 관리자 권한은 DB 직접 변경만 가능합니다.';
    END IF;

    RETURN NEW;
END;
$$;

-- ── 3) 오퍼레이터 본인만 활성화 ────────────────────────────────────
--   건당 100만원 · 일 5회 = 보수적 시작값. 조정도 DB 직접만.
UPDATE public.profiles p
   SET order_enabled = TRUE,
       max_order_krw = 1000000,
       daily_order_count_limit = 5
  FROM auth.users u
 WHERE p.id = u.id
   AND u.email = 'gywns0126@gmail.com';

-- 검증 쿼리 (실행 후 확인용):
--   SELECT u.email, p.order_enabled, p.max_order_krw, p.daily_order_count_limit
--     FROM public.profiles p JOIN auth.users u ON u.id = p.id
--    WHERE p.order_enabled = TRUE;
--   → 오퍼레이터 1행만 나와야 정상.
