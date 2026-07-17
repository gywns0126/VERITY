-- 024_security_ip_tracking.sql
-- IP 침입 시도 추적 + 자동/수동 차단 (방어층 — 민감 데이터는 이미 인증+RLS로 잠김).
-- PM 결정 2026-07-17: 관리자/env 스캔 IP 추적·자동차단 + 어드민 가시화 (풀빌드).
--   · 대상 표면 = Railway(server/main.py FastAPI, 상시) + Vercel(vercel-api) — 단일 blocked_ips 공유.
--   · 쓰기 = 백엔드(service_role) 만. 어드민 조회 = is_caller_admin(). anon/authenticated 직접 접근 0.
--   · 자동차단 = 스캔 N회 → blocked_ips(TTL, auto). 수동차단/해제 = admin.py(service_role) + admin_audit_log 기록.
-- 🚨 개인정보(PIPA): IP = 개인정보. 목적=보안, 보관기간 한정(아래 90일 자동 정리), 정책 페이지 고지 필요.
-- is_caller_admin() = 008 정의 재사용 (SECURITY DEFINER, 재귀 없음).

-- ── 1) 침입 시도 로그 ────────────────────────────────────────────────
-- .env/.git/wp-/경로순회/시크릿 파일 스캔 등 요청을 표면(surface)·사유(reason)와 함께 기록.
CREATE TABLE IF NOT EXISTS public.security_probe_log (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ip          TEXT NOT NULL,
    path        TEXT NOT NULL,
    method      TEXT,
    user_agent  TEXT,
    country     TEXT,
    reason      TEXT,                      -- env_probe | git_probe | wp_probe | path_traversal | secret_probe | cgi_probe | admin_unauth
    surface     TEXT,                      -- railway | vercel
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_probe_ip      ON public.security_probe_log (ip);
CREATE INDEX IF NOT EXISTS idx_probe_created ON public.security_probe_log (created_at DESC);

ALTER TABLE public.security_probe_log ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS spl_select_admin ON public.security_probe_log;
CREATE POLICY spl_select_admin ON public.security_probe_log
    FOR SELECT TO authenticated
    USING (public.is_caller_admin());
-- INSERT/UPDATE/DELETE 정책 없음 = 백엔드 service_role 만 (RLS 우회). 클라 직접 접근 차단.

-- ── 2) 차단 IP 목록 (TTL) ────────────────────────────────────────────
-- auto=true 자동차단(TTL 만료), auto=false 수동차단(expires_at NULL=영구).
-- 미들웨어는 (expires_at IS NULL OR expires_at > now()) 인 행만 유효 차단으로 읽음.
CREATE TABLE IF NOT EXISTS public.blocked_ips (
    ip          TEXT PRIMARY KEY,
    reason      TEXT,
    hits        INT NOT NULL DEFAULT 1,
    auto        BOOLEAN NOT NULL DEFAULT TRUE,   -- true=자동, false=수동
    surface     TEXT,                            -- 최초 탐지 표면
    created_by  TEXT,                            -- 'auto' | 관리자 email/id
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ                      -- NULL=영구(수동), 자동=TTL
);
CREATE INDEX IF NOT EXISTS idx_blocked_expires ON public.blocked_ips (expires_at);

ALTER TABLE public.blocked_ips ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS bip_select_admin ON public.blocked_ips;
CREATE POLICY bip_select_admin ON public.blocked_ips
    FOR SELECT TO authenticated
    USING (public.is_caller_admin());
-- 쓰기(자동차단/수동차단/해제) = 백엔드 service_role 만. 어드민 UI → admin.py(service_role) 경유.

-- ── 3) 보관기간 정리 (PIPA) ──────────────────────────────────────────
-- 침입 로그 90일 초과분 삭제. pg_cron 있으면 스케줄, 없으면 admin.py/워크플로가 주기 호출.
CREATE OR REPLACE FUNCTION public.purge_old_security_logs()
RETURNS void
LANGUAGE sql
SECURITY DEFINER SET search_path = ''
AS $$
    DELETE FROM public.security_probe_log WHERE created_at < now() - INTERVAL '90 days';
    DELETE FROM public.blocked_ips WHERE auto = TRUE AND expires_at IS NOT NULL AND expires_at < now() - INTERVAL '7 days';
$$;

-- pg_cron 사용 가능 시 (없으면 이 블록은 무시/실패 무해 — 주석 처리 상태로 두고 대시보드에서 활성화):
-- SELECT cron.schedule('purge-security-logs', '0 4 * * *', $$ SELECT public.purge_old_security_logs() $$);
