-- ═════════════════════════════════════════════════════════════════
-- 010: action_queue_heartbeat — Framer 컴포넌트 자가-종결 RPC
-- ─────────────────────────────────────────────────────────────────
-- 배경:
--   009 의 user_action_queue 는 사용자가 Framer 에서 ✓ 클릭으로 done 처리.
--   하지만 paste/republish 자체로 "끝남" 이 명확한 framer_paste 태스크는
--   클릭조차 번거로움. 카드가 처음 렌더되는 순간이 곧 "paste 완료" 신호.
--
-- 메커니즘:
--   - Framer 컴포넌트 useEffect 첫 마운트에서 RPC 1회 호출 (fire-and-forget)
--   - RPC 가 status='pending' AND category='framer_paste' AND
--     component_path 매칭 row 들을 모두 done 처리
--   - 반복 호출은 멱등 (이미 done 인 row 는 0건 update)
--
-- 보안:
--   - admin 전용 (is_caller_admin). AdminDashboard / 큐 카드는 admin 만 접근하므로
--     실제 호출자는 사실상 본인 한 명.
-- ═════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION public.action_queue_heartbeat(
    p_component_path TEXT
)
RETURNS INT
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    closed_count INT := 0;
BEGIN
    IF NOT public.is_caller_admin() THEN
        -- 비-admin 은 silently no-op (로그 남기지 않음, 401 도 안 던짐 — heartbeat 는 best-effort)
        RETURN 0;
    END IF;

    IF p_component_path IS NULL OR length(trim(p_component_path)) = 0 THEN
        RETURN 0;
    END IF;

    UPDATE public.user_action_queue
       SET status = 'done',
           completed_at = now(),
           user_notes = CASE
               WHEN user_notes IS NULL OR user_notes = '' THEN '[auto] heartbeat'
               ELSE user_notes || ' / [auto] heartbeat'
           END
     WHERE status = 'pending'
       AND category = 'framer_paste'
       AND component_path = p_component_path;

    GET DIAGNOSTICS closed_count = ROW_COUNT;
    RETURN closed_count;
END;
$$;

-- 멱등 재실행 안전 — 동일 RPC 가 이미 있어도 OR REPLACE
COMMENT ON FUNCTION public.action_queue_heartbeat(TEXT) IS
    'Framer 컴포넌트 자가-종결. 첫 렌더 useEffect 에서 fire-and-forget 호출. admin-only.';
