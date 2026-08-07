-- 030_kis_shared_token_multikey — 공유 토큰 store 다중 키 (PM 2026-08-07, 회원 2명)
--
-- 🚨 RULE 1 (1일 1토큰) 구역. 이 마이그레이션 자체는 발급을 바꾸지 않는다 — **행을 하나 더
--   담을 수 있게만** 한다. 발급 로직은 api/trading/kis_broker.py 가 키마다 독립 락으로 건다.
--
-- 배경: 017 이 `CHECK (id = 'kis_rest')` 로 싱글턴을 강제한다. 지인이 자기 KIS 앱키로
--   참여하면 토큰 버킷이 하나 더 필요한데, 이 제약이 두 번째 행을 막는다.
--   (KIS 토큰은 앱키에 묶여 있어 한 토큰을 두 계좌가 나눠 쓸 수 없다. 공유하려 들면
--    한쪽 계좌 주문이 다른 쪽 자격증명으로 나가는 사고가 된다.)
--
-- 🚨 오퍼레이터 행 id 는 'kis_rest' 그대로 둔다. 바꾸면 Railway/Vercel 소비자가 토큰을
--   못 찾고, RULE 1 상 재발급도 못 해 거래가 멈춘다. 추가 계좌만 'kis_rest__<slug>'.
--
-- 적용: Supabase 대시보드 SQL Editor. 029 와 순서 의존 없음(다른 테이블).

ALTER TABLE public.kis_shared_token
    DROP CONSTRAINT IF EXISTS kis_shared_token_singleton;

-- 형식 고정 — 임의 id 로 행이 늘어나면 어느 것이 누구 토큰인지 추적 불가.
-- 슬러그 규칙은 profiles.broker_slug(029) 와 동일하게 맞춘다.
ALTER TABLE public.kis_shared_token
    ADD CONSTRAINT kis_shared_token_id_format
    CHECK (id = 'kis_rest' OR id ~ '^kis_rest__[a-z][a-z0-9_]{0,15}$');

-- 같은 앱키가 두 행에 걸치면 24h 가드가 서로를 못 보고 하루 2토큰이 된다(= RULE 1 위반).
-- 지문 단위로 유일성을 강제해 그 조합 자체를 만들 수 없게 한다.
CREATE UNIQUE INDEX IF NOT EXISTS kis_shared_token_app_key_fp_uniq
    ON public.kis_shared_token (app_key_fp);

COMMENT ON TABLE public.kis_shared_token IS
  'KIS REST 토큰 공유 store. GH Actions 단일 발급 publish → Railway/Vercel 소비. '
  'RULE 1 = 앱키마다 1일 1토큰(행마다 독립 가드). id: 오퍼레이터=kis_rest, 추가=kis_rest__<slug>. '
  'service_role only.';

-- 검증 쿼리:
--   SELECT id, app_key_fp, issued_at, expires_at FROM public.kis_shared_token ORDER BY id;
--   → 행마다 app_key_fp 가 서로 달라야 정상. 같으면 즉시 조사(RULE 1 이중발급 징후).
