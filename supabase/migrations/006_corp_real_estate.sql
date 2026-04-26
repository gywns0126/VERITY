-- ═════════════════════════════════════════════════════════════════
-- VERITY ESTATE — 회사별 부동산 자산 시계열 (DART 기반)
-- ─────────────────────────────────────────────────────────────────
-- 목적:
--   상장·등록 법인의 *부동산 보유 자산*과 *사업장·시설 위치* 를 분기 단위로
--   누적 저장. 자산재평가 / 부동산 비중 변화 / 지역별 보유 ranking 등을
--   ESTATE 사이트에서 분석하기 위함.
--
-- 데이터 출처:
--   - api/collectors/DartScout.py
--   - fetch_property_assets(corp_code, bsns_year)         → estate_corp_holdings
--   - fetch_business_facilities_raw(corp_code, ...)        → estate_corp_facilities
--   - scripts/estate_corp_snapshot.py (월간 cron) 가 호출 → 정규화 → upsert
--
-- VERITY 잠금 규칙 (2026-04-25 ~ 07-24):
--   - 이 테이블은 *축적 전용*. Brain 파이프라인은 7/24 잠금 해제 전까지
--     이 데이터를 입력으로 사용하지 않는다 (격리 보장).
--   - VERITY 코드 (api/intelligence/verity_brain.py 등) 가 이 테이블을
--     읽는 코드 추가는 7/24 후 별 PR 로 진행. KB v2.2 PR (#26) 와 묶을 것.
-- ═════════════════════════════════════════════════════════════════


-- ──────────────────────────────────────────────────────────────────
-- 1) Corp Real Estate Holdings — 분기·연 단위 부동산 자산 시계열
-- ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS estate_corp_holdings (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,

    -- 식별
    corp_code       TEXT NOT NULL,                  -- DART 8자리 corp_code
    ticker          TEXT,                            -- KRX 6자리 (비상장은 NULL)
    company_name    TEXT NOT NULL,

    -- 보고 기간
    bsns_year       INT NOT NULL,                    -- 사업연도 (YYYY)
    reprt_code      TEXT NOT NULL,                   -- '11013'=1Q '11012'=반기 '11014'=3Q '11011'=사업
    period          TEXT NOT NULL,                   -- 'YYYY-Q1'/'YYYY-Q2'/'YYYY-Q3'/'YYYY-FY' 정규화
    reported_at     TIMESTAMPTZ,                     -- DART 공시 시각 (rcept_dt)

    -- 부동산 자산 (BS 기준 — 단위 KRW, BIGINT)
    -- DART PROPERTY_KEYWORDS 카테고리별 합산. 개별 line item 은 raw_breakdown 참조.
    land_krw                    BIGINT,              -- 토지
    buildings_krw               BIGINT,              -- 건물
    structures_krw              BIGINT,              -- 구축물
    construction_in_progress_krw BIGINT,             -- 건설중인자산
    investment_property_krw     BIGINT,              -- 투자부동산 (자산주 신호)
    right_of_use_assets_krw     BIGINT,              -- 사용권자산 (리스 IFRS16)

    -- 합계·비율 (DartScout fetch_property_assets 반환값)
    total_property_krw          BIGINT NOT NULL,     -- 부동산 자산 합계 (current)
    prev_property_krw           BIGINT,              -- 직전기 합계 (DART frmtrm_amount)
    total_assets_krw            BIGINT,              -- 자산총계
    property_to_asset_pct       NUMERIC(5,2),        -- 부동산 / 총자산 × 100
    qoq_change_pct              NUMERIC(7,2),        -- 직전기 대비 변화율 (DART 기본 제공)
    yoy_change_pct              NUMERIC(7,2),        -- 전년 동기 대비 (워커가 별도 계산)

    -- 재평가·공정가치 (자산주 핵심 트리거 — Brain 7/24 통합 시 사용)
    book_value_total_krw        BIGINT,              -- 장부가 (= total_property_krw, 명시 필드)
    fair_value_total_krw        BIGINT,              -- 공정가치 (재평가 시만)
    revaluation_flag            BOOLEAN NOT NULL DEFAULT FALSE,  -- 당기 재평가 여부
    revaluation_amount_krw      BIGINT,              -- 재평가 차익 (fair - book)

    -- 메타
    raw_breakdown   JSONB NOT NULL DEFAULT '[]'::jsonb,
                                                    -- DartScout items[] — 개별 계정과목별
                                                    -- {account, current, previous, change, change_pct}
    source          TEXT NOT NULL DEFAULT 'dart',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 동일 회사·기간·보고서 종류 중복 방지
CREATE UNIQUE INDEX IF NOT EXISTS idx_corp_holdings_uniq
    ON estate_corp_holdings(corp_code, bsns_year, reprt_code);

-- 시계열 조회 (단일 회사)
CREATE INDEX IF NOT EXISTS idx_corp_holdings_corp_period
    ON estate_corp_holdings(corp_code, period DESC);

-- 자산주 watchlist (재평가 발생 종목)
CREATE INDEX IF NOT EXISTS idx_corp_holdings_revaluation
    ON estate_corp_holdings(period DESC) WHERE revaluation_flag = TRUE;

-- ticker 기반 조회 (StockDashboard 부동산 섹션용)
CREATE INDEX IF NOT EXISTS idx_corp_holdings_ticker
    ON estate_corp_holdings(ticker, period DESC) WHERE ticker IS NOT NULL;

-- 부동산 비중 ranking
CREATE INDEX IF NOT EXISTS idx_corp_holdings_ratio
    ON estate_corp_holdings(period, property_to_asset_pct DESC NULLS LAST);


-- ──────────────────────────────────────────────────────────────────
-- 2) Corp Real Estate Facilities — 사업장·시설 위치/면적
-- ──────────────────────────────────────────────────────────────────
-- DartScout.fetch_business_facilities_raw + facilities_parser (LLM) 결과 저장.
-- 위치 정규화는 워커에서 (서울 "강남구 역삼동…" → location_gu='강남구').
CREATE TABLE IF NOT EXISTS estate_corp_facilities (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,

    -- 식별
    corp_code       TEXT NOT NULL,
    ticker          TEXT,
    company_name    TEXT NOT NULL,

    -- 보고 기간
    bsns_year       INT NOT NULL,
    reprt_code      TEXT NOT NULL,
    period          TEXT NOT NULL,                   -- 'YYYY-Q1' 등

    -- 시설 분류
    facility_type   TEXT NOT NULL,                   -- HQ | factory | RnD | logistics | store
                                                    -- | investment | overseas | other
    ownership_type  TEXT NOT NULL DEFAULT 'unknown', -- owned | leased | unknown
    facility_name   TEXT,                            -- "본사" / "수원공장" / "동탄 R&D센터" 등

    -- 위치 (정규화)
    location_country TEXT NOT NULL DEFAULT 'KR',     -- ISO 2자리
    location_si     TEXT,                            -- "서울특별시" / "경기도" / NULL (해외)
    location_gu     TEXT,                            -- "강남구" / NULL (해외 또는 시 단위)
    location_address TEXT,                           -- 전체 주소 (정규화 전)

    -- 정량
    area_sqm        NUMERIC(12,2),                   -- 전용면적 (제곱미터)
    acquisition_year INT,                            -- 취득 연도 (nullable, 장기 보유 식별용)
    currency        TEXT NOT NULL DEFAULT 'KRW',     -- 해외 시설은 USD/JPY 등

    -- 원본
    raw_blob        TEXT,                            -- LLM 파싱 전 DART 원본 텍스트
    parsed_by       TEXT,                            -- 'gemini-2.5-flash' / 'manual' / NULL
    source          TEXT NOT NULL DEFAULT 'dart',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 같은 보고기간 내 중복 시설 방지 (동일 회사·동일 시설명·동일 위치)
CREATE UNIQUE INDEX IF NOT EXISTS idx_corp_facilities_uniq
    ON estate_corp_facilities(corp_code, bsns_year, reprt_code, facility_name, location_address);

-- 지역별 ranking (강남구 보유 1위 법인 등 — ESTATE 고유 분석)
CREATE INDEX IF NOT EXISTS idx_corp_facilities_region
    ON estate_corp_facilities(location_gu, period DESC) WHERE location_gu IS NOT NULL;

-- 단일 회사 시설 조회
CREATE INDEX IF NOT EXISTS idx_corp_facilities_corp
    ON estate_corp_facilities(corp_code, period DESC);

-- 시설 종류 ranking
CREATE INDEX IF NOT EXISTS idx_corp_facilities_type
    ON estate_corp_facilities(facility_type, period DESC);


-- ──────────────────────────────────────────────────────────────────
-- updated_at 자동 갱신 (holdings 테이블)
-- ──────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION estate_corp_holdings_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_estate_corp_holdings_updated_at ON estate_corp_holdings;
CREATE TRIGGER trg_estate_corp_holdings_updated_at
    BEFORE UPDATE ON estate_corp_holdings
    FOR EACH ROW EXECUTE FUNCTION estate_corp_holdings_set_updated_at();


-- ──────────────────────────────────────────────────────────────────
-- RLS — 회사 부동산 정보는 DART 공시 (공개 데이터). 모두 SELECT 가능.
-- INSERT/UPDATE 는 service_role 만 (cron 워커 = scripts/estate_corp_snapshot.py).
-- ──────────────────────────────────────────────────────────────────
ALTER TABLE estate_corp_holdings   ENABLE ROW LEVEL SECURITY;
ALTER TABLE estate_corp_facilities ENABLE ROW LEVEL SECURITY;

CREATE POLICY "estate_corp_holdings_public_read" ON estate_corp_holdings
    FOR SELECT TO authenticated, anon USING (true);

CREATE POLICY "estate_corp_facilities_public_read" ON estate_corp_facilities
    FOR SELECT TO authenticated, anon USING (true);


-- ──────────────────────────────────────────────────────────────────
-- 사용 예시 (워커가 작성할 쿼리)
-- ──────────────────────────────────────────────────────────────────
--
-- A) 단일 회사 시계열 (StockDashboard 부동산 섹션):
--   SELECT period, total_property_krw, property_to_asset_pct,
--          revaluation_flag, qoq_change_pct
--     FROM estate_corp_holdings
--    WHERE ticker = '005930'
--    ORDER BY period DESC LIMIT 8;
--
-- B) 강남구 부동산 보유 법인 ranking (ESTATE 고유):
--   SELECT company_name, ticker,
--          COUNT(*) AS facilities_in_gu,
--          SUM(area_sqm) AS total_area_sqm
--     FROM estate_corp_facilities
--    WHERE location_gu = '강남구'
--      AND period = '2026-Q1'
--    GROUP BY corp_code, company_name, ticker
--    ORDER BY total_area_sqm DESC NULLS LAST
--    LIMIT 20;
--
-- C) 자산주 watchlist (당기 재평가 발생 + 부동산 비중 30%+):
--   SELECT company_name, ticker, period,
--          revaluation_amount_krw,
--          property_to_asset_pct,
--          fair_value_total_krw - book_value_total_krw AS hidden_value_krw
--     FROM estate_corp_holdings
--    WHERE revaluation_flag = TRUE
--      AND property_to_asset_pct >= 30
--      AND period = '2026-Q1'
--    ORDER BY revaluation_amount_krw DESC NULLS LAST;
