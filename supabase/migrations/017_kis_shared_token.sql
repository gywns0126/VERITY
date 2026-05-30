-- 017_kis_shared_token.sql
-- 🚨 RULE 1 — KIS 1일 1토큰 ABSOLUTE. GH Actions 단일 발급원 + Supabase 공유 토큰 store.
-- PM 결정 2026-05-31: 발급원 일원화 (GH Actions 만 발급 → 토큰 값 publish, Railway/Vercel = 읽기 소비).
--
-- 사고 배경 (2026-05-31):
--   발급원이 둘 — GH Actions(api/trading/kis_broker.py, file lock 24h) +
--   Railway(server/kis_rest_client.py, /tmp cache 6h) — 가 서로 모른 채 독립 발급.
--   → 하루 2토큰 (사용자 KIS 알림 2건). Railway 는 /tmp 가 재시작마다 초기화돼
--   6h 가드가 읽을 stale cache 가 사라짐 → 재시작마다 신규 발급.
--   근본: 라이브 토큰 필요 subsystem 이 2개인데 토큰 '값' 공유 저장소가 없었음.
--   lock 파일은 timestamp 만 있고 token 값이 없어 재사용 불가.
--
-- 해법: GH Actions 가 기존 file-lock 24h 가드로 1일 1발급 → 발급 직후 이 테이블에 토큰 값 publish.
--   Railway/Vercel = service_role 읽기 소비 (자체 발급 절대 금지). GH = 가장 관측성 높은 발급원
--   (file lock 트레일 + cron_health_monitor 재사용). 가용성 결합 안전 방향 (always-on 소비자가 read).
--
-- ⚠ access_token = 실거래 자격증명. anon/authenticated 접근 절대 금지.
--    RLS enable + 정책 0개 = service_role(RLS bypass) 만 read/write. 일반 role = 전면 거부.
--    Supabase SQL Editor 에서 실행. 적용 후 SUPABASE_SERVICE_ROLE_KEY 로만 접근.

CREATE TABLE IF NOT EXISTS public.kis_shared_token (
    id           text        PRIMARY KEY DEFAULT 'kis_rest',  -- 단일 행 강제 (singleton)
    access_token text        NOT NULL,
    expires_at   timestamptz NOT NULL,                         -- KIS 토큰 만료 (발급 후 ~24h)
    issued_at    timestamptz NOT NULL,                         -- 발급 시각 — 24h 재발급 가드 기준
    app_key_fp   text        NOT NULL,                         -- app_key fingerprint (키 회전/오설정 detect)
    updated_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT kis_shared_token_singleton CHECK (id = 'kis_rest')
);

COMMENT ON TABLE  public.kis_shared_token IS
  'KIS REST 토큰 공유 store. GH Actions 단일 발급 publish → Railway/Vercel 소비. RULE 1 1일 1토큰. service_role only.';
COMMENT ON COLUMN public.kis_shared_token.issued_at  IS '발급 시각. now()-issued_at < 24h 면 재발급 금지 (RULE 1).';
COMMENT ON COLUMN public.kis_shared_token.app_key_fp IS 'sha256(KIS_APP_KEY)[:12]. 소비자가 자기 키와 일치 검증.';

-- RLS: enable, 정책 미생성 → service_role 만 접근 (anon/authenticated 전면 거부).
ALTER TABLE public.kis_shared_token ENABLE ROW LEVEL SECURITY;
