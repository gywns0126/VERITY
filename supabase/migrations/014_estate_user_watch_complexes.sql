-- ESTATE 사용자 단지 watchlist (V0_WATCHLIST hardcoded 폐기 → 동적 등록)
-- estate_brain_builder 가 V0_WATCHLIST + 모든 사용자 등록 단지 union → unique complex 별 brain 산출.
--
-- 테이블 분리 (estate_groups vs user_watch_complexes):
--   estate_groups        = 관심지역 그룹 (구 단위)
--   user_watch_complexes = 관심 단지 (단지 단위 — 본 migration)
--
-- RLS: 본인 row 만 RW. builder cron 은 service_role 로 RLS 우회.
-- feedback_supabase_rls_no_self_subquery 정합 — 같은 테이블 EXISTS X (단순 owner 체크).

CREATE TABLE IF NOT EXISTS estate_user_watch_complexes (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id         UUID NOT NULL,                                -- auth.uid()
    gu              TEXT NOT NULL,                                -- 서울 25구
    dong            TEXT NOT NULL,                                -- 법정동 (RTMS umdNm)
    apt             TEXT NOT NULL,                                -- 단지명 raw 입력
    apt_normalized  TEXT NOT NULL,                                -- clustering.normalize_apt_name 적용
    build_year      INT  NOT NULL DEFAULT 0,                      -- 건축년도 (0 = 미상)
    project_type    TEXT,                                         -- 'reconstruction' | 'redevelopment' | NULL
    redev_stage     TEXT,                                         -- 6 stage enum | NULL
    months_in_stage INT  NOT NULL DEFAULT 0,
    valuation_pending      BOOLEAN NOT NULL DEFAULT false,        -- 종전자산평가 발표 대기
    subscription_announced BOOLEAN NOT NULL DEFAULT false,        -- 일반분양 공고
    memo            TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_estate_user_watch_complex_user
    ON estate_user_watch_complexes(user_id, created_at DESC);

-- 동일 user 가 같은 (gu, dong, apt_normalized, build_year) 중복 등록 방지
CREATE UNIQUE INDEX IF NOT EXISTS idx_estate_user_watch_complex_uniq
    ON estate_user_watch_complexes(user_id, gu, dong, apt_normalized, build_year);

ALTER TABLE estate_user_watch_complexes ENABLE ROW LEVEL SECURITY;

-- 본인 row 만 RW (단순 owner 체크 — self EXISTS X, 무한 재귀 위험 없음)
CREATE POLICY "estate_user_watch_complex_owner" ON estate_user_watch_complexes
    FOR ALL TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- updated_at 자동 갱신 트리거
CREATE OR REPLACE FUNCTION trg_estate_user_watch_complex_updated()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS estate_user_watch_complex_set_updated ON estate_user_watch_complexes;
CREATE TRIGGER estate_user_watch_complex_set_updated
    BEFORE UPDATE ON estate_user_watch_complexes
    FOR EACH ROW EXECUTE FUNCTION trg_estate_user_watch_complex_updated();
