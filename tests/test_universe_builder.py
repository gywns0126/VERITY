"""universe_builder 단위 테스트 (Phase 2-A) — 외부 API 호출 mock."""
from __future__ import annotations

from unittest.mock import patch

from api.collectors.universe_builder import (
    build_extended_universe,
    build_us_universe,
    _row_to_universe_entry,
    _to_int,
    _load_core_pools,
)


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _krx_row(ticker, name, mkt="KOSPI", cap=100_000_000_000, tv=5_000_000_000, sect=""):
    return {
        "BAS_DD": "20260430", "ISU_CD": ticker, "ISU_NM": name, "MKT_NM": mkt,
        "SECT_TP_NM": sect, "TDD_CLSPRC": "100000", "MKTCAP": str(cap),
        "ACC_TRDVAL": str(tv), "LIST_SHRS": "1000000",
    }


# ─────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────

class TestRowNormalization:
    def test_basic_kr_row(self):
        e = _row_to_universe_entry(_krx_row("005930", "삼성전자"), set(), "")
        assert e["ticker"] == "005930"
        assert e["name"] == "삼성전자"
        assert e["market"] == "KOSPI"
        assert e["currency"] == "KRW"
        assert e["market_cap"] == 100_000_000_000
        assert e["is_managed"] is False
        assert e["is_suspended"] is False

    def test_managed_detection(self):
        e = _row_to_universe_entry(_krx_row("005930", "테스트", sect="관리종목"), set(), "")
        assert e["is_managed"] is True

    def test_suspended_via_sect(self):
        e = _row_to_universe_entry(_krx_row("005930", "테스트", sect="거래정지"), set(), "")
        assert e["is_suspended"] is True

    def test_suspended_via_zero_trading_value(self):
        e = _row_to_universe_entry(_krx_row("005930", "테스트", tv=0), set(), "")
        assert e["is_suspended"] is True

    def test_invalid_ticker_returns_none(self):
        bad = {"ISU_CD": "ABC", "MKTCAP": "100"}
        assert _row_to_universe_entry(bad, set(), "") is None

    def test_core_flag(self):
        e = _row_to_universe_entry(_krx_row("005930", "삼성전자"), {"005930"}, "")
        assert e["is_core"] is True
        assert e["tier"] == "core"


class TestKrUniverseBuild:
    @patch("api.collectors.krx_openapi.krx_stk_ksq_rows_sorted_by_trading_value")
    def test_kr_basic_build(self, mock_krx):
        rows = [
            _krx_row("005930", "삼성전자", cap=300_000_000_000_000),
            _krx_row("000660", "SK하이닉스", cap=200_000_000_000_000),
            _krx_row("100001", "Penny", cap=1_000_000_000, tv=10_000_000),
            _krx_row("100002", "Junk", cap=500_000_000, tv=1_000_000),
        ]
        mock_krx.return_value = ("20260430", rows)
        # disable hard floor 로 raw entries 확인
        u = build_extended_universe("KR", target_size=4, apply_hard_floor=False)
        assert len(u) == 4
        # 시총 정렬
        assert u[0]["ticker"] == "005930"
        assert u[1]["ticker"] == "000660"

    @patch("api.collectors.krx_openapi.krx_stk_ksq_rows_sorted_by_trading_value")
    def test_kr_target_size_caps(self, mock_krx):
        rows = [
            _krx_row(f"10{i:04d}", f"종목{i}", cap=(100 - i) * 1_000_000_000_000)
            for i in range(10)
        ]
        mock_krx.return_value = ("20260430", rows)
        u = build_extended_universe("KR", target_size=3, apply_hard_floor=False)
        # 코어 union 가능성 → 길이는 >=3, <=10
        assert 3 <= len(u) <= 10
        # 상위 3 개 시총 보장
        top3_caps = [e["market_cap"] for e in u[:3]]
        assert top3_caps == sorted(top3_caps, reverse=True)

    @patch("api.collectors.krx_openapi.krx_stk_ksq_rows_sorted_by_trading_value")
    def test_kr_hard_floor_cuts_penny(self, mock_krx):
        rows = [
            _krx_row("005930", "삼성", cap=300_000_000_000_000),
            _krx_row("100001", "Penny", cap=1_000_000_000, tv=10_000_000),
        ]
        mock_krx.return_value = ("20260430", rows)
        u = build_extended_universe("KR", target_size=10, apply_hard_floor=True)
        # Penny 가 cut 되었는지
        tickers = [e["ticker"] for e in u]
        assert "100001" not in tickers or any(e.get("is_core") for e in u if e["ticker"] == "100001")

    @patch("api.collectors.krx_openapi.krx_stk_ksq_rows_sorted_by_trading_value")
    def test_empty_response_raises(self, mock_krx):
        mock_krx.return_value = ("", [])
        import pytest
        with pytest.raises(RuntimeError, match="KRX OpenAPI"):
            build_extended_universe("KR", target_size=10)


class TestUsUniverseBuild:
    def test_us_returns_tickers(self):
        u = build_us_universe(target_size=10)
        assert len(u) >= 10
        assert all("ticker" in e for e in u)
        assert all(e["currency"] == "USD" for e in u)
        assert any(e["is_core"] for e in u)


class TestInvalidMarket:
    def test_invalid_market_raises(self):
        import pytest
        with pytest.raises(ValueError, match="market"):
            build_extended_universe("EU", target_size=10)


class TestToInt:
    def test_to_int_basic(self):
        assert _to_int("1,000,000") == 1_000_000
        assert _to_int(None) == 0
        assert _to_int("") == 0
        assert _to_int("abc", default=42) == 42
        assert _to_int(123.45) == 123


class TestCorePoolsLoad:
    def test_core_pools_load(self):
        kr, us = _load_core_pools()
        assert len(kr) >= 30  # KOSPI_MAJOR 30개 + KOSDAQ_MAJOR 15개
        assert len(us) >= 30
        # 삼성전자
        assert "005930" in kr
