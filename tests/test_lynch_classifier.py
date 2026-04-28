"""Lynch 6분류 한국 기준 회귀 테스트."""
from __future__ import annotations

import pytest

from api.intelligence.lynch_classifier import (
    classify_lynch_kr,
    attach_classifications,
    CLASSES,
)


# ─────────────────────────────────────────────────────────────────────
# 분류 정확성
# ─────────────────────────────────────────────────────────────────────

class TestClassification:
    def test_fast_grower(self):
        s = {"revenue_growth": 25, "market_cap": 2e12, "operating_margin": 18,
             "pbr": 3, "sector": "IT"}
        assert classify_lynch_kr(s)["class"] == "FAST_GROWER"

    def test_fast_grower_too_big_falls_to_stalwart(self):
        # 성장 25% but 시총 50조 → Fast 아님 (대형). Stalwart 임계 5~15% 미충족.
        # 우선순위상 Stalwart 도 아님 → ASSET_PLAY 또는 SLOW
        s = {"revenue_growth": 25, "market_cap": 50e12, "operating_margin": 12, "pbr": 3}
        cls = classify_lynch_kr(s)["class"]
        # 거대 성장 종목인데 Fast/Stalwart 둘 다 fail → SLOW (default)
        assert cls in ("SLOW_GROWER",)

    def test_stalwart(self):
        s = {"revenue_growth": 8, "market_cap": 50e12, "operating_margin": 12,
             "pbr": 1.5, "sector": "IT"}
        assert classify_lynch_kr(s)["class"] == "STALWART"

    def test_slow_grower_with_dividend(self):
        s = {"revenue_growth": 2, "market_cap": 10e12, "operating_margin": 5,
             "pbr": 1.2, "div_yield": 4.5, "sector": "통신"}
        assert classify_lynch_kr(s)["class"] == "SLOW_GROWER"

    def test_cyclical(self):
        s = {"revenue_growth": 30, "market_cap": 20e12, "operating_margin": 10,
             "pbr": 1.0, "sector": "철강"}
        assert classify_lynch_kr(s)["class"] == "CYCLICAL"

    def test_turnaround_with_revenue_growth(self):
        # 검수 정정 후: ROE<0 + op_margin>0 + revenue_growth>0
        s = {"revenue_growth": 8, "market_cap": 1e12, "operating_margin": 3,
             "kis_financial_ratio": {"source": "kis", "roe": -5,
                                     "operating_margin": 3, "debt_ratio": 150}}
        assert classify_lynch_kr(s)["class"] == "TURNAROUND"

    def test_turnaround_without_revenue_growth_fails(self):
        # revenue_growth 없거나 음수 → Turnaround 분류 안 됨 (false positive 차단)
        s = {"revenue_growth": -5, "market_cap": 1e12, "operating_margin": 3,
             "kis_financial_ratio": {"source": "kis", "roe": -5,
                                     "operating_margin": 3, "debt_ratio": 150}}
        result = classify_lynch_kr(s)
        assert result["class"] != "TURNAROUND"

    def test_asset_play_low_pbr(self):
        s = {"revenue_growth": 3, "market_cap": 2e12, "operating_margin": 5,
             "pbr": 0.5, "sector": "지주"}
        assert classify_lynch_kr(s)["class"] == "ASSET_PLAY"


# ─────────────────────────────────────────────────────────────────────
# 우선순위 (특수 상황 우선)
# ─────────────────────────────────────────────────────────────────────

class TestPriority:
    def test_turnaround_beats_cyclical(self):
        # 둘 다 매칭 가능한 상황 → Turnaround 우선
        s = {"revenue_growth": 10, "market_cap": 1e12, "operating_margin": 3,
             "sector": "철강",  # cyclical
             "kis_financial_ratio": {"source": "kis", "roe": -5,
                                     "operating_margin": 3, "debt_ratio": 150}}
        assert classify_lynch_kr(s)["class"] == "TURNAROUND"

    def test_cyclical_beats_fast_grower(self):
        # 철강 + 매출 25% → Cyclical (반등기 매출 급증)
        s = {"revenue_growth": 25, "market_cap": 2e12, "operating_margin": 15,
             "sector": "철강"}
        assert classify_lynch_kr(s)["class"] == "CYCLICAL"

    def test_asset_play_beats_slow(self):
        # PBR 0.5 + 저성장 → Asset Play (Slow Grower 보다 우선)
        s = {"revenue_growth": 1, "market_cap": 2e12, "operating_margin": 4,
             "pbr": 0.5}
        assert classify_lynch_kr(s)["class"] == "ASSET_PLAY"


# ─────────────────────────────────────────────────────────────────────
# Data Quality
# ─────────────────────────────────────────────────────────────────────

class TestDataQuality:
    def test_full_data_ok(self):
        s = {"revenue_growth": 10, "market_cap": 5e12, "operating_margin": 8}
        assert classify_lynch_kr(s)["data_quality"] == "ok"

    def test_missing_revenue_growth_low(self):
        s = {"market_cap": 5e12, "operating_margin": 8}
        assert classify_lynch_kr(s)["data_quality"] == "low"

    def test_missing_market_cap_low(self):
        s = {"revenue_growth": 10, "operating_margin": 8}
        assert classify_lynch_kr(s)["data_quality"] == "low"

    def test_attach_counts_low_quality(self):
        portfolio = {"recommendations": [
            {"revenue_growth": 10, "market_cap": 5e12, "operating_margin": 8},  # ok
            {"revenue_growth": None, "market_cap": 5e12},  # low
            {},  # low
        ]}
        attach_classifications(portfolio)
        d = portfolio["lynch_kr_distribution"]
        assert d["total"] == 3
        assert d["low_quality_count"] == 2


# ─────────────────────────────────────────────────────────────────────
# 분포 카운트
# ─────────────────────────────────────────────────────────────────────

class TestAttachClassifications:
    def test_distribution_sum_equals_total(self):
        recs = [
            {"revenue_growth": 25, "market_cap": 2e12, "operating_margin": 18, "pbr": 3},  # Fast
            {"revenue_growth": 8, "market_cap": 50e12, "operating_margin": 12},  # Stalwart
            {"revenue_growth": 30, "market_cap": 20e12, "operating_margin": 10, "sector": "철강"},  # Cyclical
        ]
        portfolio = {"recommendations": recs}
        attach_classifications(portfolio)
        counts = portfolio["lynch_kr_distribution"]["counts"]
        assert sum(counts.values()) == 3

    def test_each_stock_has_lynch_kr(self):
        recs = [{"revenue_growth": 25, "market_cap": 2e12, "operating_margin": 18}]
        portfolio = {"recommendations": recs}
        attach_classifications(portfolio)
        assert "lynch_kr" in recs[0]
        assert recs[0]["lynch_kr"]["class"] in CLASSES

    def test_empty_portfolio(self):
        portfolio = {"recommendations": []}
        attach_classifications(portfolio)
        assert portfolio["lynch_kr_distribution"]["total"] == 0
