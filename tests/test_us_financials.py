"""us_financials adapter + builder 산식 검증.

network 의존 함수 (fetch_companyfacts 등) 는 mock fixture. 산식/dedupe/derived 만 검증.
"""
from __future__ import annotations

import importlib.util
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MOD_PATH = os.path.join(_REPO_ROOT, "api", "intelligence", "us_financials.py")

_spec = importlib.util.spec_from_file_location("usf", _MOD_PATH)
usf = importlib.util.module_from_spec(_spec)
sys.modules["usf"] = usf
_spec.loader.exec_module(usf)


# ──────────────────────────────────────────────────────────────────────
# _classify_period
# ──────────────────────────────────────────────────────────────────────
class TestClassifyPeriod:
    def test_annual_10k(self):
        p = usf._classify_period("2024-07-01", "2025-06-30", "10-K", "FY", 2025, is_instant=False)
        assert p is not None
        assert p.is_annual is True
        assert p.fiscal_period == "FY"

    def test_quarterly_standalone(self):
        p = usf._classify_period("2025-07-01", "2025-09-30", "10-Q", "Q1", 2026, is_instant=False)
        assert p is not None
        assert p.is_annual is False
        assert p.fiscal_period == "Q1"

    def test_cumulative_6month_rejected(self):
        # 6-month cumulative span ~180d → 분류 X (cumulative 제외)
        p = usf._classify_period("2025-07-01", "2025-12-31", "10-Q", "Q2", 2026, is_instant=False)
        assert p is None

    def test_instant_balance_sheet(self):
        # balance-sheet: start == end
        p = usf._classify_period("2025-06-30", "2025-06-30", "10-K", "FY", 2025, is_instant=True)
        assert p is not None
        assert p.is_annual is True

    def test_instant_quarterly(self):
        p = usf._classify_period("2025-09-30", "2025-09-30", "10-Q", "Q1", 2026, is_instant=True)
        assert p is not None
        assert p.is_annual is False
        assert p.fiscal_period == "Q1"

    def test_form_amendment_accepted(self):
        # 10-K/A 도 annual 로 통과
        p = usf._classify_period("2024-07-01", "2025-06-30", "10-K/A", "FY", 2025, is_instant=False)
        assert p is not None
        assert p.is_annual is True

    def test_invalid_dates(self):
        assert usf._classify_period("invalid", "2025-06-30", "10-K", "FY", 2025, False) is None
        assert usf._classify_period("2024-07-01", "invalid", "10-K", "FY", 2025, False) is None


# ──────────────────────────────────────────────────────────────────────
# extract_metric_series
# ──────────────────────────────────────────────────────────────────────
def _facts_with(concept, rows):
    return {"facts": {"us-gaap": {concept: {"units": {"USD": rows}}}}}


def _facts_multi(tag_rows):
    """multiple alias tags."""
    return {"facts": {"us-gaap": {
        tag: {"units": {"USD": rows}} for tag, rows in tag_rows.items()
    }}}


class TestExtractMetricSeries:
    def test_no_match_returns_empty(self):
        facts = {"facts": {"us-gaap": {}}}
        assert usf.extract_metric_series(facts, "revenue") == []

    def test_simple_annual_revenue(self):
        rows = [
            {"start": "2023-07-01", "end": "2024-06-30", "val": 100_000_000_000,
             "fy": 2024, "fp": "FY", "form": "10-K", "accn": "0001-001"},
            {"start": "2024-07-01", "end": "2025-06-30", "val": 120_000_000_000,
             "fy": 2025, "fp": "FY", "form": "10-K", "accn": "0001-002"},
        ]
        facts = _facts_with("Revenues", rows)
        out = usf.extract_metric_series(facts, "revenue")
        assert len(out) == 2
        assert out[0]["val"] == 100_000_000_000
        assert out[1]["val"] == 120_000_000_000
        assert out[1]["tag"] == "Revenues"

    def test_alias_merge(self):
        """5/20 핵심 fix — old Revenues + new RevenueFromContract... 동시 박힘."""
        old_rows = [
            {"start": "2008-07-01", "end": "2009-06-30", "val": 58_000_000_000,
             "fy": 2009, "fp": "FY", "form": "10-K", "accn": "old-001"},
        ]
        new_rows = [
            {"start": "2024-07-01", "end": "2025-06-30", "val": 280_000_000_000,
             "fy": 2025, "fp": "FY", "form": "10-K", "accn": "new-001"},
        ]
        facts = _facts_multi({
            "Revenues": old_rows,
            "RevenueFromContractWithCustomerExcludingAssessedTax": new_rows,
        })
        out = usf.extract_metric_series(facts, "revenue")
        assert len(out) == 2
        ends = [r["end"] for r in out]
        # 시계열 통합 — old 2009 + new 2025 모두 보존
        assert "2009-06-30" in ends and "2025-06-30" in ends

    def test_accn_restatement_picks_latest(self):
        rows = [
            {"start": "2024-07-01", "end": "2025-06-30", "val": 100,
             "fy": 2025, "fp": "FY", "form": "10-K", "accn": "0001-001"},
            {"start": "2024-07-01", "end": "2025-06-30", "val": 110,  # restated
             "fy": 2025, "fp": "FY", "form": "10-K", "accn": "0001-002"},
        ]
        facts = _facts_with("Revenues", rows)
        out = usf.extract_metric_series(facts, "revenue")
        assert len(out) == 1
        # 최신 accn 우선
        assert out[0]["val"] == 110

    def test_cumulative_quarterly_excluded(self):
        rows = [
            {"start": "2025-07-01", "end": "2025-09-30", "val": 70_000_000_000,
             "fy": 2026, "fp": "Q1", "form": "10-Q", "accn": "x-001"},
            # 6-month cumulative (180+d) — exclude
            {"start": "2025-07-01", "end": "2025-12-31", "val": 150_000_000_000,
             "fy": 2026, "fp": "Q2", "form": "10-Q", "accn": "x-002"},
            # 3-month standalone (90d) — include
            {"start": "2025-10-01", "end": "2025-12-31", "val": 80_000_000_000,
             "fy": 2026, "fp": "Q2", "form": "10-Q", "accn": "x-003"},
        ]
        facts = _facts_with("Revenues", rows)
        out = usf.extract_metric_series(facts, "revenue")
        # 2 standalone 만 (cumulative 6-month 제외)
        assert len(out) == 2
        vals = [r["val"] for r in out]
        assert 70_000_000_000 in vals and 80_000_000_000 in vals
        assert 150_000_000_000 not in vals

    def test_instant_balance_sheet(self):
        rows = [
            {"start": "2025-06-30", "end": "2025-06-30", "val": 50_000_000_000,
             "fy": 2025, "fp": "FY", "form": "10-K", "accn": "z-001"},
        ]
        facts = _facts_with("StockholdersEquity", rows)
        out = usf.extract_metric_series(facts, "stockholders_equity")
        assert len(out) == 1
        assert out[0]["val"] == 50_000_000_000
        assert out[0]["is_annual"] is True


# ──────────────────────────────────────────────────────────────────────
# compute_derived
# ──────────────────────────────────────────────────────────────────────
def _series(values, is_annual, fp="FY", fy_start=2024):
    out = []
    for i, v in enumerate(values):
        out.append({
            "end": f"{fy_start + i}-06-30" if is_annual else f"{fy_start + i//4}-{(((i%4)+1)*3):02d}-30",
            "val": v,
            "fy": fy_start + i if is_annual else fy_start + i // 4,
            "fp": fp if is_annual else ["Q1", "Q2", "Q3", "Q4"][i % 4],
            "form": "10-K" if is_annual else "10-Q",
            "is_annual": is_annual,
            "accn": f"acc-{i:03d}",
            "tag": "T",
        })
    return out


class TestComputeDerived:
    def test_revenue_yoy_annual(self):
        metrics = {
            "revenue": _series([100, 120], is_annual=True),
        }
        d = usf.compute_derived(metrics)
        assert d["revenue_yoy_pct_annual"] == 20.0

    def test_gross_margin(self):
        metrics = {
            "revenue": _series([100], is_annual=True),
            "gross_profit": _series([65], is_annual=True),
        }
        d = usf.compute_derived(metrics)
        assert d["gross_margin_pct"] == 65.0

    def test_net_margin(self):
        metrics = {
            "revenue": _series([100], is_annual=True),
            "net_income": _series([20], is_annual=True),
        }
        d = usf.compute_derived(metrics)
        assert d["net_margin_pct"] == 20.0

    def test_fcf_compute(self):
        metrics = {
            "operating_cash_flow": _series([80], is_annual=True),
            "capex": _series([20], is_annual=True),
        }
        d = usf.compute_derived(metrics)
        assert d["fcf_usd"] == 60

    def test_debt_to_equity(self):
        metrics = {
            "long_term_debt": _series([30], is_annual=True),
            "stockholders_equity": _series([100], is_annual=True),
        }
        d = usf.compute_derived(metrics)
        assert d["debt_to_equity"] == 0.3

    def test_roe(self):
        metrics = {
            "net_income": _series([20], is_annual=True),
            "stockholders_equity": _series([100], is_annual=True),
        }
        d = usf.compute_derived(metrics)
        assert d["roe_pct"] == 20.0

    def test_empty_metrics(self):
        d = usf.compute_derived({})
        assert d == {}

    def test_negative_yoy(self):
        metrics = {
            "revenue": _series([100, 80], is_annual=True),
        }
        d = usf.compute_derived(metrics)
        assert d["revenue_yoy_pct_annual"] == -20.0

    # v0.1 — sector tag calibration
    def test_pretax_margin(self):
        # 은행/에너지 처럼 op_income 부재여도 pretax_income 으로 수익성 산출.
        metrics = {
            "revenue": _series([100], is_annual=True),
            "pretax_income": _series([33], is_annual=True),
        }
        d = usf.compute_derived(metrics)
        assert d["pretax_margin_pct"] == 33.0
        assert "operating_margin_pct" not in d  # op_income 부재 → 안 fabricate

    def test_fcf_suppressed_for_financial(self):
        metrics = {
            "operating_cash_flow": _series([80], is_annual=True),
            "capex": _series([20], is_annual=True),
        }
        d = usf.compute_derived(metrics, is_financial=True)
        assert d["fcf_usd"] is None
        assert d["fcf_na_reason"] == "financial_sector"

    def test_fcf_computed_for_nonfinancial(self):
        metrics = {
            "operating_cash_flow": _series([80], is_annual=True),
            "capex": _series([20], is_annual=True),
        }
        d = usf.compute_derived(metrics, is_financial=False)
        assert d["fcf_usd"] == 60
        assert "fcf_na_reason" not in d

    # v0.2 — quarterly YoY end-date 매칭 (fy 오염 robust)
    def test_quarterly_yoy_endmatch(self):
        # 8 분기: prior-year same quarter (i=3, val=130) vs latest (i=7, val=170)
        q = _series([100, 110, 120, 130, 140, 150, 160, 170], is_annual=False)
        d = usf.compute_derived({"revenue": q})
        assert d["revenue_yoy_pct_quarterly"] == 30.77  # (170-130)/130

    def test_quarterly_yoy_robust_to_fy_contamination(self):
        # SEC fy 필드가 전부 동일하게 오염돼도 end-date 매칭이라 정상 (MSFT 실측 결함 회귀 가드)
        q = _series([100, 110, 120, 130, 140, 150, 160, 170], is_annual=False)
        for r in q:
            r["fy"] = 2099
        d = usf.compute_derived({"revenue": q})
        assert d["revenue_yoy_pct_quarterly"] == 30.77

    def test_quarterly_yoy_no_prior_year_quarter(self):
        # 2 분기만 (1년 전 동기 없음) → null, 인접분기 오매칭 금지
        q = _series([100, 110], is_annual=False)
        d = usf.compute_derived({"revenue": q})
        assert d.get("revenue_yoy_pct_quarterly") is None


class TestIsFinancialSic:
    def test_bank_is_financial(self):
        assert usf.is_financial_sic(6021) is True   # BAC/JPM 국법은행
        assert usf.is_financial_sic(6199) is True   # SOFI 핀테크
        assert usf.is_financial_sic(6331) is True   # BRK 보험

    def test_nonfinancial(self):
        assert usf.is_financial_sic(7372) is False  # MSFT SW
        assert usf.is_financial_sic(2911) is False  # XOM 정유
        assert usf.is_financial_sic(6798) is False  # REIT — capex 유의미, 제외
        assert usf.is_financial_sic(None) is False


# ──────────────────────────────────────────────────────────────────────
# builder integration (load_us_tickers)
# ──────────────────────────────────────────────────────────────────────
class TestBuilderTickerLoad:
    def test_load_us_tickers(self):
        _BUILDER_PATH = os.path.join(_REPO_ROOT, "api", "builders", "us_financials_builder.py")
        bspec = importlib.util.spec_from_file_location("usfb", _BUILDER_PATH)
        bmod = importlib.util.module_from_spec(bspec)
        sys.modules["usfb"] = bmod
        bspec.loader.exec_module(bmod)
        out = bmod.load_us_tickers()
        # KR 6자리 ticker 제외 됨 (현 portfolio.json 가 있다면)
        for t in out:
            assert not (t.isdigit() and len(t) == 6), f"KR ticker leaked: {t}"
        # fallback or 실제 portfolio US 종목 - 최소 1개
        assert len(out) >= 1
