-- ═════════════════════════════════════════════════════════════════
-- 009: user_action_queue — 사용자 수동 작업 큐 (Claude Code ↔ Framer 동기화)
-- ─────────────────────────────────────────────────────────────────
-- 배경:
--   매 세션 "내가 뭐 해야 했지?" 를 사용자가 묻고 Claude Code 가 메모리/git log
--   을 뒤져 답하는 패턴이 누적됨. Framer paste 4건 + Supabase 마이그/Gemini 검증
--   /1주 점검 등 8+ 백로그.
--
--   해결: Supabase 단일 테이블로 SoT 통합.
--     - Claude Code (service_role) → 작업 끝나면 큐 insert
--     - 사용자 Framer UserActionQueueCard → status 표시 + Done/Skip 버튼
--     - 다음 세션 Claude Code → status='pending' 만 조회 → "뭐 해야지?" 안 물음
--
-- 의존성:
--   008_profile_is_admin.sql 적용 필요. 미적용 시 본 스크립트가 idempotent 하게
--   is_admin 컬럼 + admin 체크 함수만 안전하게 보강. (008 의 다른 RLS 정책은 별개)
--
-- 적용 후 1회:
--   UPDATE public.profiles SET is_admin = TRUE WHERE email = 'gywns0126@gmail.com';
-- ═════════════════════════════════════════════════════════════════


-- 1) profiles.is_admin 컬럼 (008 미적용 시 fallback — idempotent)
ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_profiles_is_admin
    ON public.profiles(id) WHERE is_admin = TRUE;


-- 2) admin 체크 헬퍼 — RLS·RPC 어디서나 재사용
CREATE OR REPLACE FUNCTION public.is_caller_admin()
RETURNS BOOLEAN
LANGUAGE plpgsql
STABLE
SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    v BOOLEAN;
BEGIN
    IF auth.role() = 'service_role' THEN
        RETURN TRUE;
    END IF;
    SELECT COALESCE(p.is_admin, FALSE) INTO v
      FROM public.profiles p WHERE p.id = auth.uid();
    RETURN COALESCE(v, FALSE);
END;
$$;


-- 3) user_action_queue 테이블
CREATE TABLE IF NOT EXISTS public.user_action_queue (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT NOT NULL,
    detail          TEXT,
    category        TEXT NOT NULL DEFAULT 'misc'
                    CHECK (category IN (
                        'framer_paste',     -- Framer 코드 컴포넌트 paste/republish
                        'supabase_migration', -- supabase/migrations/*.sql 적용
                        'verification',     -- 외부 검증 (Gemini 캐시, 1주 점검 등)
                        'monitoring',       -- 정기 점검 / dashboard 확인
                        'misc'
                    )),
    priority        TEXT NOT NULL DEFAULT 'p2'
                    CHECK (priority IN ('p0', 'p1', 'p2')),
    commit_hash     TEXT,                  -- Claude Code 가 만든 commit (paste 대상)
    component_path  TEXT,                  -- 예: framer-components/StockDashboard.tsx
    code_snippet    TEXT,                  -- paste 용 raw URL or 코드 블록
    due_at          TIMESTAMPTZ,           -- 마감 (없으면 NULL)
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'in_progress', 'done', 'skipped')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    user_notes      TEXT,                  -- Done/Skip 시 사용자가 남기는 메모
    created_by      TEXT DEFAULT 'claude_code'  -- 'claude_code' / 'user' / 'cron'
);

CREATE INDEX IF NOT EXISTS idx_uaq_status_priority
    ON public.user_action_queue(status, priority, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_uaq_category
    ON public.user_action_queue(category, status);


-- 4) RLS — admin only (read/write)
ALTER TABLE public.user_action_queue ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS uaq_admin_select ON public.user_action_queue;
CREATE POLICY uaq_admin_select ON public.user_action_queue
    FOR SELECT TO authenticated
    USING (public.is_caller_admin());

DROP POLICY IF EXISTS uaq_admin_insert ON public.user_action_queue;
CREATE POLICY uaq_admin_insert ON public.user_action_queue
    FOR INSERT TO authenticated
    WITH CHECK (public.is_caller_admin());

DROP POLICY IF EXISTS uaq_admin_update ON public.user_action_queue;
CREATE POLICY uaq_admin_update ON public.user_action_queue
    FOR UPDATE TO authenticated
    USING (public.is_caller_admin())
    WITH CHECK (public.is_caller_admin());

DROP POLICY IF EXISTS uaq_admin_delete ON public.user_action_queue;
CREATE POLICY uaq_admin_delete ON public.user_action_queue
    FOR DELETE TO authenticated
    USING (public.is_caller_admin());


-- 5) RPC — Done / Skip (admin)
--    Framer 에서 한 번 호출로 status + completed_at + user_notes 일관성 있게 update.
CREATE OR REPLACE FUNCTION public.action_queue_complete(
    target_id UUID,
    note TEXT DEFAULT NULL
)
RETURNS public.user_action_queue
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    row public.user_action_queue;
BEGIN
    IF NOT public.is_caller_admin() THEN
        RAISE EXCEPTION 'action_queue_complete: 권한 없음 (admin 만)';
    END IF;
    UPDATE public.user_action_queue
       SET status = 'done',
           completed_at = now(),
           user_notes = COALESCE(note, user_notes)
     WHERE id = target_id
    RETURNING * INTO row;
    RETURN row;
END;
$$;

CREATE OR REPLACE FUNCTION public.action_queue_skip(
    target_id UUID,
    note TEXT DEFAULT NULL
)
RETURNS public.user_action_queue
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    row public.user_action_queue;
BEGIN
    IF NOT public.is_caller_admin() THEN
        RAISE EXCEPTION 'action_queue_skip: 권한 없음';
    END IF;
    UPDATE public.user_action_queue
       SET status = 'skipped',
           completed_at = now(),
           user_notes = COALESCE(note, user_notes)
     WHERE id = target_id
    RETURNING * INTO row;
    RETURN row;
END;
$$;


-- 6) 초기 백로그 시드 (2026-05-01 기준)
--    이미 있는 같은 title + status='pending' 은 중복 insert 안 함 (간단 ON CONFLICT 대신
--    title UNIQUE WHERE pending 패턴 — partial unique index 로 멱등 보장).
CREATE UNIQUE INDEX IF NOT EXISTS uniq_uaq_pending_title
    ON public.user_action_queue(title) WHERE status = 'pending';

INSERT INTO public.user_action_queue
    (title, detail, category, priority, commit_hash, component_path, due_at)
VALUES
    ('UserActionQueueCard Framer paste',
     '본 큐 자체를 운영하기 위한 신규 카드. AdminDashboard 옆 또는 별도 페이지에 배치.',
     'framer_paste', 'p0', NULL,
     'framer-components/UserActionQueueCard.tsx', NULL),

    ('008 + 009 마이그레이션 Supabase 적용',
     'Supabase Dashboard SQL Editor 에 008_profile_is_admin.sql 과 009_user_action_queue.sql 을 순서대로 실행. 이후 UPDATE profiles SET is_admin=TRUE WHERE email=...; 1회.',
     'supabase_migration', 'p0', NULL,
     'supabase/migrations/009_user_action_queue.sql', NULL),

    ('gh-pages URL Phase B — 41 컴포넌트 republish',
     '기존 main 의 portfolio.json 직접 fetch 컴포넌트들을 gh-pages raw URL 로 일괄 교체 후 republish.',
     'framer_paste', 'p1', NULL, NULL, NULL),

    ('TodayActionsCard 신규 paste',
     'Sprint 11 결함 7 — 단일 액션 게이트 (BUY/SELL/WATCH).',
     'framer_paste', 'p1', '10379c6',
     'framer-components/TodayActionsCard.tsx', NULL),

    ('StockDashboard 업데이트 — TimingSignal + TradePlan',
     'Sprint 11 결함 5 — TimingSignalCard + TradePlanSection 추가.',
     'framer_paste', 'p1', 'f6d3eed',
     'framer-components/StockDashboard.tsx', NULL),

    ('AdminDashboard 업데이트 — CardTradePlanV0',
     'trade_plan v0 인프라 카드.',
     'framer_paste', 'p2', 'dbb79e4',
     'framer-components/AdminDashboard.tsx', NULL),

    ('DigestPublishPanel wiring',
     '2-3h. 별도 세션 추천 (UI + 검증 흐름 통합).',
     'framer_paste', 'p2', NULL,
     'framer-components/DigestPublishPanel.tsx', NULL),

    ('Gemini 캐시 검증',
     'Gemini Flash/Pro 캐시 hit ratio 운영 점검.',
     'verification', 'p1', NULL, NULL,
     '2026-05-03T09:00:00+09:00'::TIMESTAMPTZ),

    ('1주 운영 점검 (Sprint 11 후속 효과 측정)',
     'trade_plan_v0_log.jsonl row 수 / brain_weights_cv 일관성 / cross_asset_corr 분포 등 1주 누적 검토.',
     'monitoring', 'p2', NULL, NULL,
     '2026-05-07T09:00:00+09:00'::TIMESTAMPTZ)
ON CONFLICT (title) WHERE status = 'pending' DO NOTHING;


-- 7) 운영 편의 view — 우선순위 + 마감 정렬
CREATE OR REPLACE VIEW public.v_action_queue_pending AS
SELECT id, title, category, priority, commit_hash, component_path,
       due_at, created_at,
       CASE
           WHEN due_at IS NOT NULL AND due_at < now() THEN 'overdue'
           WHEN due_at IS NOT NULL AND due_at < now() + INTERVAL '2 days' THEN 'due_soon'
           ELSE 'normal'
       END AS due_status
  FROM public.user_action_queue
 WHERE status = 'pending'
 ORDER BY
     CASE priority WHEN 'p0' THEN 0 WHEN 'p1' THEN 1 ELSE 2 END,
     CASE WHEN due_at IS NOT NULL AND due_at < now() THEN 0 ELSE 1 END,
     created_at DESC;
