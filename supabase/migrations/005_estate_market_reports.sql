-- ESTATE 월간 시장 리포트 테이블 (Perplexity API 자동 수집)
-- 매월 1일 KST 09:00 GitHub Actions cron 이 Perplexity 호출 → 이 테이블에 저장.
-- 추후 LANDEX CURRENT_REGIME 자동 갱신·DigestPublishPanel 컨텍스트 카드 등에 활용.

CREATE TABLE IF NOT EXISTS estate_market_reports (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    month       TEXT NOT NULL,                -- YYYY-MM (전월 기준 — cron 이 1일에 전월 리포트 생성)
    raw_report  TEXT NOT NULL,                -- Perplexity 원문 (JSON 또는 markdown)
    parsed      JSONB NOT NULL DEFAULT '{}'::jsonb,
                                              -- 추출된 구조화 dict:
                                              --   summary / policy_changes / macro_indicators /
                                              --   recommended_regime / regime_rationale /
                                              --   proptech_movements / user_trends_summary /
                                              --   verity_action_items / next_month_key_events
    citations   JSONB NOT NULL DEFAULT '[]'::jsonb,  -- Perplexity 출처 URL 목록
    model       TEXT NOT NULL DEFAULT 'sonar-pro',
    source      TEXT NOT NULL DEFAULT 'perplexity',  -- perplexity | manual
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_market_reports_month_source
    ON estate_market_reports(month, source);
CREATE INDEX IF NOT EXISTS idx_market_reports_created
    ON estate_market_reports(created_at DESC);

ALTER TABLE estate_market_reports ENABLE ROW LEVEL SECURITY;

-- 공개 읽기 (지역 시장 분석은 비밀 아님)
CREATE POLICY "market_reports_public_read" ON estate_market_reports
    FOR SELECT TO authenticated, anon USING (true);

-- INSERT 는 service_role 전용 (cron 워커만 작성)
