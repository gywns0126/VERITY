"""ESTATE Brain V0 backtest builder — 단위 테스트.

검증:
  - build() schema 정합 (rone 어댑터 부재 시 graceful)
  - _compute_seoul_avg_series (25구 평균 시계열)
  - _compute_per_gu_returns (mean / median / std)
  - _compute_core_vs_noncore_drop (core_outperform 판단)
  - cycle_analog_validation 정합 (mock 시계열 → drop 산출)
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _make_series(weeks: int, start: float, end: float) -> list:
    """선형 시계열 helper."""
    if weeks <= 1:
        return [{"week": "202601", "index": start}]
    step = (end - start) / (weeks - 1)
    return [{"week": f"2026{i:04d}", "index": start + i * step} for i in range(weeks)]


def _make_payload(series: list) -> dict:
    return {"gu": "test", "series": series, "as_of": "2026-04-29",
            "source": "rone_weekly", "stat_id": "TEST"}


def _fake_rone(per_gu_drop_target: dict):
    """gu별 다른 시계열 반환하는 fake rone."""
    fake = MagicMock()

    def _fetch(gu: str, weeks: int = 260, **kwargs):
        # peak 100 → trough 100*(1+drop/100) 단조 하락 → 다시 회복 (W shape)
        drop_pct = per_gu_drop_target.get(gu, -10.0)
        peak = 100.0
        trough = peak * (1 + drop_pct / 100)
        # 60주 peak → 60주 trough → 60주 회복 → 80주 평탄
        n_each = max(weeks // 4, 10)
        s = []
        for i in range(n_each):
            s.append({"week": f"a{i:03d}", "index": peak})
        for i in range(n_each):
            s.append({"week": f"b{i:03d}", "index": peak + (trough - peak) * (i / max(n_each - 1, 1))})
        for i in range(n_each):
            s.append({"week": f"c{i:03d}", "index": trough + (peak * 0.95 - trough) * (i / max(n_each - 1, 1))})
        for i in range(weeks - 3 * n_each):
            s.append({"week": f"d{i:03d}", "index": peak * 0.95})
        return _make_payload(s)

    fake.fetch_weekly_index.side_effect = _fetch
    return fake


class TestSeoulAvg:
    def test_simple_avg_two_gu(self):
        from api.builders import estate_brain_backtest_builder as bld
        indices = {
            "강남구": _make_payload([{"week": "202601", "index": 100},
                                    {"week": "202602", "index": 110}]),
            "노원구": _make_payload([{"week": "202601", "index": 80},
                                    {"week": "202602", "index": 84}]),
        }
        avg = bld._compute_seoul_avg_series(indices)
        assert len(avg) == 2
        assert avg[0]["index"] == 90.0  # (100+80)/2
        assert avg[1]["index"] == 97.0  # (110+84)/2
        assert avg[0]["n_gu"] == 2

    def test_skip_none_payload(self):
        from api.builders import estate_brain_backtest_builder as bld
        indices = {"강남구": None, "노원구": _make_payload([{"week": "202601", "index": 80}])}
        avg = bld._compute_seoul_avg_series(indices)
        assert len(avg) == 1
        assert avg[0]["index"] == 80.0

    def test_empty_returns_empty(self):
        from api.builders import estate_brain_backtest_builder as bld
        assert bld._compute_seoul_avg_series({}) == []


class TestPerGuReturns:
    def test_typical_stats(self):
        from api.builders import estate_brain_backtest_builder as bld
        from api.intelligence import estate_brain_backtest as bt
        # 100 → 110 (52w 후) → 일관 +10%
        series = [{"week": f"w{i:03d}", "index": 100 + i * 0.2}
                  for i in range(105)]  # 105 주 → 53 시점 forward return
        indices = {"강남구": _make_payload(series)}
        out = bld._compute_per_gu_returns(indices, horizon_weeks=52, bt_module=bt)
        assert out["강남구"]["available"] is True
        assert out["강남구"]["mean_return_pct"] > 0  # 시계열 단조 상승

    def test_no_payload_returns_unavailable(self):
        from api.builders import estate_brain_backtest_builder as bld
        from api.intelligence import estate_brain_backtest as bt
        out = bld._compute_per_gu_returns({"강남구": None}, horizon_weeks=52, bt_module=bt)
        assert out["강남구"]["available"] is False


class TestCoreVsNoncore:
    def test_core_outperforms_when_smaller_drop(self):
        from api.builders import estate_brain_backtest_builder as bld
        from api.intelligence import estate_brain_backtest as bt
        # 핵심지(강남구) drop -10, 비핵심지(노원구) drop -25
        gangnam_series = [{"index": v} for v in [100, 95, 90, 100]]   # peak 100, trough 90 → -10%
        nowon_series = [{"index": v} for v in [100, 80, 75, 90]]      # peak 100, trough 75 → -25%
        indices = {
            "강남구": _make_payload(gangnam_series),
            "노원구": _make_payload(nowon_series),
        }
        out = bld._compute_core_vs_noncore_drop(indices, bt)
        assert out["core_mean_drop_pct"] == -10.0
        assert out["non_core_mean_drop_pct"] == -25.0
        # core 가 덜 떨어졌으니 outperform True
        assert out["core_outperform"] is True

    def test_none_data_no_outperform(self):
        from api.builders import estate_brain_backtest_builder as bld
        from api.intelligence import estate_brain_backtest as bt
        out = bld._compute_core_vs_noncore_drop({}, bt)
        assert out["core_outperform"] is None


class TestBuild:
    def test_build_with_rone_payload(self):
        from api.builders import estate_brain_backtest_builder as bld
        from api.intelligence import estate_brain_backtest as bt
        # 25구 모두 -20% drop 시계열 → seoul_avg 도 -20% drop
        per_gu = {gu: -20.0 for gu in bld.SEOUL_25_GU}
        rone = _fake_rone(per_gu)
        payload = bld.build(weeks=200, _modules={"rone": rone}, _bt=bt)
        assert payload["schema_version"] == "v0"
        assert payload["scope"] == "v0_partial"
        # cycle_analog 2022 정합 (drop ≈ -20% vs plan -20%, tolerance 5)
        cv = payload["cycle_analog_validation"].get("Rate-Shock Rebound")
        assert cv is not None
        assert cv["within_tolerance"] is True
        # 25구 데이터
        assert payload["diagnostics"]["gu_with_data"] == 25

    def test_build_no_rone_graceful(self):
        from api.builders import estate_brain_backtest_builder as bld
        from api.intelligence import estate_brain_backtest as bt
        payload = bld.build(weeks=100, _modules={}, _bt=bt)
        assert payload["schema_version"] == "v0"
        assert payload["diagnostics"]["rone_available"] is False
        assert payload["diagnostics"]["gu_with_data"] == 0
        assert payload["cycle_analog_validation"] == {}
