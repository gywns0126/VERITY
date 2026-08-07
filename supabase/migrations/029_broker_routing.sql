-- 029_broker_routing — 사용자별 증권계좌 라우팅 + 시드 규모 (PM 승인 2026-08-07)
--
-- 🚨 선행 조건: 028_order_permission.sql 을 **먼저** 적용해야 한다. 아래 트리거 함수가
--   NEW.order_enabled 를 참조하므로 028 의 컬럼이 없으면 런타임에 깨진다.
--
-- 배경 (PM 2026-08-07): "내 친구랑 나만 이 사이트를 쓸건데, 각각의 계좌를 API 연동해서
--   분배 관리 및 투자가 이뤄지도록" — A안 채택. 즉 **각자 자기 계좌에서 자기가 승인**하고,
--   시스템은 목표비중과 각자 시드 규모에 따른 배분 갭만 계산한다. 타인 자금을 대신
--   운용(B안)하지 않는다 — 미등록 투자일임은 자본시장법 제17조·제445조 대상.
--
-- 🚨 이 마이그레이션이 막는 사고: 친구가 주문을 냈는데 **오퍼레이터 계좌로 체결**되는 것.
--   주문 경로는 이미 사용자별 인증(JWT→uid→profiles)이지만, 실제 계좌는 배포 env 의
--   단일 KIS 자격증명 하나였다. broker_slug 가 없으면 서버가 fail-closed 로 거절한다
--   (기본값을 두지 않는 이유 = 기본값이 곧 남의 계좌로 새는 경로).
--
-- 적용: Supabase 대시보드 SQL Editor (019·020·028 과 동일 경로).

-- ── 1) 컬럼 ────────────────────────────────────────────────────────
ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS broker_slug TEXT;
ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS seed_krw BIGINT;

COMMENT ON COLUMN public.profiles.broker_slug IS
    '증권계좌 자격증명 슬러그(서버 env 세트 키). service_role 전용 — 실계좌 라우팅.';
COMMENT ON COLUMN public.profiles.seed_krw IS
    '이 전략에 배정한 시드(원). NULL = 실계좌 평가총액 전액. 비중 배분의 분모.';

-- 슬러그 형식 고정 — 서버가 env 키를 조립하므로 형식 이탈은 곧 주입 표면.
--   서버도 allowlist 로 한 번 더 막지만(이중 방어), 저장 시점에서 먼저 끊는다.
ALTER TABLE public.profiles
    DROP CONSTRAINT IF EXISTS profiles_broker_slug_format;
ALTER TABLE public.profiles
    ADD CONSTRAINT profiles_broker_slug_format
    CHECK (broker_slug IS NULL OR broker_slug ~ '^[a-z][a-z0-9_]{0,15}$');

-- 한 계좌를 두 사람이 공유하는 상태를 스키마에서 차단.
CREATE UNIQUE INDEX IF NOT EXISTS profiles_broker_slug_uniq
    ON public.profiles (broker_slug) WHERE broker_slug IS NOT NULL;

-- 시드는 양수만. 0/음수는 배분 분모가 되어 0 나눗셈·부호 반전을 만든다.
ALTER TABLE public.profiles
    DROP CONSTRAINT IF EXISTS profiles_seed_krw_positive;
ALTER TABLE public.profiles
    ADD CONSTRAINT profiles_seed_krw_positive
    CHECK (seed_krw IS NULL OR seed_krw > 0);

-- ── 2) 오퍼레이터 슬러그 지정 — 🚨 반드시 3) 함수 교체 **이전** ─────────
--   028 과 동일한 순서 이유: 방금 설치할 가드가 SQL Editor(비 service_role) UPDATE 를
--   RAISE 로 차단해 자기잠금이 된다. 현행 함수엔 broker 가드가 없어 이 시점 UPDATE 는 통과.
--   친구 행은 친구가 가입(= profiles 행 생성)한 뒤 아래 형태로 별도 실행:
--     ALTER TABLE public.profiles DISABLE TRIGGER trg_block_privileged_profile;
--     UPDATE public.profiles p SET broker_slug='friend'
--       FROM auth.users u WHERE p.id=u.id AND u.email='<친구 이메일>';
--     ALTER TABLE public.profiles ENABLE TRIGGER trg_block_privileged_profile;
--   그리고 서버 env 에 KIS_APP_KEY__FRIEND / KIS_APP_SECRET__FRIEND /
--   KIS_ACCOUNT_NO__FRIEND + BROKER_SLUGS='operator,friend' 를 설정해야 실제로 붙는다.
UPDATE public.profiles p
   SET broker_slug = 'operator'
  FROM auth.users u
 WHERE p.id = u.id
   AND u.email = 'gywns0126@gmail.com'
   AND p.broker_slug IS DISTINCT FROM 'operator';

-- ── 3) 권한 상승 차단 트리거 확장 (broker_slug = service_role 전용) ──
--   028 함수를 그대로 계승하고 broker_slug 가드만 추가.
--   seed_krw 는 **일부러 제외** — 본인 자금 배정 비율은 권한이 아니라 본인 설정이고,
--   집행은 여전히 max_order_krw / daily_order_count_limit 이 막는다. 본인 행만 수정
--   가능한 것은 기존 RLS 가 보장.
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

    -- 🚨 계좌 라우팅 = 남의 실계좌로 주문이 나가는 경로. 관리자도 UI 로 못 바꾼다.
    IF NEW.broker_slug IS DISTINCT FROM OLD.broker_slug THEN
        RAISE EXCEPTION '증권계좌 라우팅은 DB 직접(service_role)으로만 변경할 수 있습니다.';
    END IF;

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

-- 검증 쿼리 (실행 후 확인용):
--   SELECT u.email, p.broker_slug, p.seed_krw, p.order_enabled
--     FROM public.profiles p JOIN auth.users u ON u.id = p.id
--    WHERE p.broker_slug IS NOT NULL;
--   → 사람 1명당 슬러그 1개, 중복 0 이어야 정상.
