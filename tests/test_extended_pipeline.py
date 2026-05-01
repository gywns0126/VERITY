"""Phase 2-A 통합 테스트 — run_filter_pipeline_with_ramp_up dispatch + 가드."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from api.analyzers import stock_filter


class TestDispatchWhenStageLow:
    def test_stage_85_falls_back_to_classic(self, monkeypatch):
        monkeypatch.setattr(stock_filter, "UNIVERSE_RAMP_UP_STAGE", 85)
        with patch("api.analyzers.stock_filter.run_filter_pipeline") as mock_classic:
            mock_classic.return_value = [{"ticker": "005930"}]
            result = stock_filter.run_filter_pipeline_with_ramp_up(market_scope="kr")
            mock_classic.assert_called_once()
            assert result == [{"ticker": "005930"}]

    def test_stage_zero_falls_back_to_classic(self, monkeypatch):
        monkeypatch.setattr(stock_filter, "UNIVERSE_RAMP_UP_STAGE", 0)
        with patch("api.analyzers.stock_filter.run_filter_pipeline") as mock_classic:
            mock_classic.return_value = []
            stock_filter.run_filter_pipeline_with_ramp_up()
            mock_classic.assert_called_once()


class TestKstWindowGuard:
    def test_in_window_at_10am(self, monkeypatch):
        # KST 10시는 in-window
        from datetime import datetime
        from zoneinfo import ZoneInfo
        kst = ZoneInfo("Asia/Seoul")
        fake_now = datetime(2026, 5, 1, 10, 0, tzinfo=kst)

        class FakeDT:
            @staticmethod
            def now(tz=None):
                return fake_now

        monkeypatch.setattr("api.analyzers.stock_filter.datetime", None, raising=False)  # ensure attr
        # patch the inner import via monkeypatching module attrib
        with patch("api.analyzers.stock_filter._is_within_phase2a_window", return_value=True):
            monkeypatch.setattr(stock_filter, "UNIVERSE_RAMP_UP_STAGE", 500)
            with patch("api.analyzers.stock_filter.run_extended_filter_pipeline") as mock_ext:
                mock_ext.return_value = [{"ticker": "X"}]
                stock_filter.run_filter_pipeline_with_ramp_up()
                mock_ext.assert_called_once()

    def test_out_of_window_falls_back(self, monkeypatch):
        with patch("api.analyzers.stock_filter._is_within_phase2a_window", return_value=False):
            monkeypatch.setattr(stock_filter, "UNIVERSE_RAMP_UP_STAGE", 500)
            with patch("api.analyzers.stock_filter.run_filter_pipeline") as mock_classic:
                mock_classic.return_value = []
                with patch("api.analyzers.stock_filter.run_extended_filter_pipeline") as mock_ext:
                    stock_filter.run_filter_pipeline_with_ramp_up()
                    mock_classic.assert_called_once()
                    mock_ext.assert_not_called()


class TestEmptyUniverseFallback:
    def test_extended_empty_universe_falls_back(self, monkeypatch):
        """universe_builder 가 빈 결과 반환 시 코어 fallback."""
        with patch("api.analyzers.stock_filter._build_custom_universe_for_phase_2a", return_value=None):
            with patch("api.analyzers.stock_filter.run_filter_pipeline") as mock_classic:
                mock_classic.return_value = [{"ticker": "core"}]
                result = stock_filter.run_extended_filter_pipeline(market_scope="all", target_size=500)
                mock_classic.assert_called_once()
                assert result == [{"ticker": "core"}]

    def test_extended_zero_data_falls_back(self, monkeypatch):
        """get_all_stock_data 가 빈 list 반환 시 코어 fallback."""
        with patch("api.analyzers.stock_filter._build_custom_universe_for_phase_2a",
                   return_value={"005930.KS": "삼성전자"}):
            with patch("api.analyzers.stock_filter.get_all_stock_data", return_value=[]):
                with patch("api.analyzers.stock_filter.run_filter_pipeline") as mock_classic:
                    mock_classic.return_value = [{"ticker": "core"}]
                    result = stock_filter.run_extended_filter_pipeline(
                        market_scope="all", target_size=500,
                    )
                    mock_classic.assert_called_once()


class TestBuildCustomUniverse:
    @patch("api.collectors.universe_builder.build_extended_universe")
    def test_kr_only_scope(self, mock_build):
        mock_build.return_value = [
            {"ticker": "005930", "name": "삼성전자", "market": "KOSPI"},
            {"ticker": "000660", "name": "SK하이닉스", "market": "KOSPI"},
            {"ticker": "035420", "name": "NAVER", "market": "KOSPI"},
        ]
        result = stock_filter._build_custom_universe_for_phase_2a("kr", 100)
        assert result is not None
        # KR 종목은 .KS 또는 .KQ suffix
        assert all(k.endswith(".KS") or k.endswith(".KQ") for k in result)
        assert "005930.KS" in result

    @patch("api.collectors.universe_builder.build_extended_universe")
    def test_all_scope_combines_kr_us(self, mock_build):
        def side(market, target_size, apply_hard_floor):
            if market == "KR":
                return [{"ticker": "005930", "name": "삼성", "market": "KOSPI"}]
            return [{"ticker": "AAPL", "name": "Apple"}]
        mock_build.side_effect = side
        result = stock_filter._build_custom_universe_for_phase_2a("all", 100)
        assert "005930.KS" in result
        assert "AAPL" in result

    @patch("api.collectors.universe_builder.build_extended_universe")
    def test_kosdaq_gets_kq_suffix(self, mock_build):
        mock_build.return_value = [
            {"ticker": "247540", "name": "에코프로비엠", "market": "KOSDAQ"},
        ]
        result = stock_filter._build_custom_universe_for_phase_2a("kr", 100)
        assert "247540.KQ" in result

    @patch("api.collectors.universe_builder.build_extended_universe")
    def test_build_failure_returns_none(self, mock_build):
        mock_build.side_effect = RuntimeError("KRX down")
        result = stock_filter._build_custom_universe_for_phase_2a("kr", 100)
        assert result is None
