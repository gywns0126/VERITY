-- ESTATE 전용 테이블
-- VERITY ESTATE (부동산 터미널) 의 WatchGroups·Alerts·Digest·LANDEX 스냅샷 저장.
-- TERMINAL Watch Groups (watch_groups, watch_group_items) 와 분리 — 다른 도메인.

-- ──────────────────────────────────────────────────────────────
-- 1) Estate Watch Groups (관심지역 그룹)
-- ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS estate_groups (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id     UUID NOT NULL,  -- auth.uid()
    name        TEXT NOT NULL DEFAULT '관심지역',
    color       TEXT NOT NULL DEFAULT '#B8864D',  -- ESTATE 골드
    sort_order  INT NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS estate_group_members (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    group_id    UUID NOT NULL REFERENCES estate_groups(id) ON DELETE CASCADE,
    gu          TEXT NOT NULL,  -- "강남구" 등 서울 25구
    memo        TEXT NOT NULL DEFAULT '',
    sort_order  INT NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_estate_groups_user ON estate_groups(user_id);
CREATE INDEX IF NOT EXISTS idx_estate_members_group ON estate_group_members(group_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_estate_members_uniq ON estate_group_members(group_id, gu);


-- ──────────────────────────────────────────────────────────────
-- 2) Estate Alerts (알림 피드)
-- ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS estate_alerts (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id     UUID,  -- NULL 이면 전체 공개 알림 (기본). 특정 user 만 받을 알림은 user_id 지정.
    category    TEXT NOT NULL,  -- gei | catalyst | regulation | anomaly
    severity    TEXT NOT NULL DEFAULT 'mid',  -- high | mid | low
    title       TEXT NOT NULL,
    body        TEXT NOT NULL DEFAULT '',
    gu          TEXT,  -- 지역 알림이면 구 명, 정책/거시면 NULL
    source_url  TEXT,  -- 원문 RSS/공지 링크
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS estate_alert_marks (
    user_id     UUID NOT NULL,
    alert_id    UUID NOT NULL REFERENCES estate_alerts(id) ON DELETE CASCADE,
    status      TEXT NOT NULL DEFAULT 'read',  -- read | hidden
    marked_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, alert_id)
);

CREATE INDEX IF NOT EXISTS idx_estate_alerts_occurred ON estate_alerts(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_estate_alerts_category ON estate_alerts(category);
CREATE INDEX IF NOT EXISTS idx_estate_alert_marks_user ON estate_alert_marks(user_id);


-- ──────────────────────────────────────────────────────────────
-- 3) LANDEX Snapshots (월별 점수 캐시 — 외부 API 호출 절감)
-- ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS estate_landex_snapshots (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    gu          TEXT NOT NULL,
    month       TEXT NOT NULL,  -- YYYY-MM
    preset      TEXT NOT NULL DEFAULT 'balanced',
    v_score     NUMERIC,
    d_score     NUMERIC,
    s_score     NUMERIC,
    c_score     NUMERIC,
    r_score     NUMERIC,
    landex      NUMERIC,
    tier10      TEXT,
    gei         NUMERIC,
    gei_stage   INT,
    raw_payload JSONB,  -- 디버그·추적용
    methodology_version TEXT NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_estate_snapshots_uniq
    ON estate_landex_snapshots(gu, month, preset, methodology_version);
CREATE INDEX IF NOT EXISTS idx_estate_snapshots_month ON estate_landex_snapshots(month);


-- ──────────────────────────────────────────────────────────────
-- 4) Digest Drafts (발행 전 검증 상태)
-- ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS estate_digest_drafts (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    period          TEXT NOT NULL,  -- "2026-04 4주차"
    title           TEXT NOT NULL,
    summary         TEXT NOT NULL DEFAULT '',
    sections        JSONB NOT NULL DEFAULT '[]'::jsonb,
    public_notes    JSONB NOT NULL DEFAULT '[]'::jsonb,
    checklist_state JSONB NOT NULL DEFAULT '{}'::jsonb,  -- 9종 체크 결과
    confidence_score NUMERIC,
    status          TEXT NOT NULL DEFAULT 'draft',  -- draft | scheduled | published | failed
    scheduled_at    TIMESTAMPTZ,
    published_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_estate_drafts_status ON estate_digest_drafts(status);
CREATE INDEX IF NOT EXISTS idx_estate_drafts_period ON estate_digest_drafts(period);


-- ──────────────────────────────────────────────────────────────
-- RLS (Row Level Security)
-- ──────────────────────────────────────────────────────────────
ALTER TABLE estate_groups        ENABLE ROW LEVEL SECURITY;
ALTER TABLE estate_group_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE estate_alerts        ENABLE ROW LEVEL SECURITY;
ALTER TABLE estate_alert_marks   ENABLE ROW LEVEL SECURITY;
ALTER TABLE estate_landex_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE estate_digest_drafts ENABLE ROW LEVEL SECURITY;

-- 그룹: 본인 행만 RW
CREATE POLICY "estate_groups_owner_all" ON estate_groups
    FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- 그룹 멤버: 본인이 소유한 그룹의 멤버만 RW
CREATE POLICY "estate_members_via_group" ON estate_group_members
    FOR ALL TO authenticated
    USING (EXISTS (SELECT 1 FROM estate_groups g WHERE g.id = group_id AND g.user_id = auth.uid()))
    WITH CHECK (EXISTS (SELECT 1 FROM estate_groups g WHERE g.id = group_id AND g.user_id = auth.uid()));

-- 알림: 공개(user_id IS NULL) + 본인 알림 조회 가능
CREATE POLICY "estate_alerts_visible" ON estate_alerts
    FOR SELECT TO authenticated USING (user_id IS NULL OR user_id = auth.uid());

-- 알림 마킹: 본인 마킹만 RW
CREATE POLICY "estate_alert_marks_owner" ON estate_alert_marks
    FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- LANDEX 스냅샷: 모두 SELECT 가능 (지역 점수는 공개), INSERT/UPDATE 는 service_role 만 (RLS 우회)
CREATE POLICY "estate_snapshots_public_read" ON estate_landex_snapshots
    FOR SELECT TO authenticated, anon USING (true);

-- Digest drafts: service_role 전용 (관리자만 작성·검토)
-- (RLS 정책 없음 → 기본 거부 → service_role 만 접근)
