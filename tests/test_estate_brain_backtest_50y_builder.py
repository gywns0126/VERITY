"""ESTATE Brain V0.3 50y backtest builder — 단위 테스트."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _bis_payload_with_cycle(drop_pct: float, duration_quarters: int):
    """peak → trough → 회복 시계열 합성 (분기 단위)."""
    pre = [{"date": f"a{i:03d}", "quarter": f"a{i}", "index": 100} for i in range(8)]
    drop_step = (100 + drop_pct) - 100
    fall = [{"date": f"b{i:03d}", "quarter": f"b{i}",
             "index": 100 + drop_step * (i + 1) / duration_quarters}
            for i in range(duration_quarters)]
    recovery = [{"date": f"c{i:03d}", "quarter": f"c{i}",
                 "index": (100 + drop_step) + abs(drop_step) * (i + 1) / 8}
                for i in range(8)]
    series = pre + fall + recovery
    return {"series": series, "n_points": len(series), "as_of": "test",
            "source": "fred_bis_korea_real_rppi"}


def _kosis_payload_with_cycle(drop_pct: float, duration_months: int):
    """REB 공동주택 매매 실거래가격지수 시계열 합성 (월 단위, 2006~ 정합)."""
    pre = [{"month": f"19{i:04d}", "index": 100} for i in range(24)]
    drop_step = (100 + drop_pct) - 100
    fall = [{"month": f"20{i:04d}", "index": 100 + drop_step * (i + 1) / duration_months}
            for i in range(duration_months)]
    recovery = [{"month": f"21{i:04d}",
                 "index": (100 + drop_step) + abs(drop_step) * (i + 1) / 24}
                for i in range(24)]
    series = pre + fall + recovery
    return {"series": series, "n_points": len(series), "as_of": "test",
            "source": "KOSIS_REB_APT"}


def _make_fake_modules(bis_payload=None, kosis_payload=None):
    bis = MagicMock()
    bis.fetch_bis_korea_real_rppi.return_value = bis_payload
    kosis = MagicMock()
    kosis.fetch_reb_apt_price_index.return_value = kosis_payload
    return {"bis": bis, "kosis": kosis}


class TestPlanMatch:
    def test_match_with_drop_15_duration_60(self):
        from api.builders import estate_brain_backtest_50y_builder as bld
        plan = {"drop_pct": -15.0, "duration_months": 65, "name": "Supply Glut"}
        detected = [
            {"drop_pct": -16.0, "duration_months": 60},
            {"drop_pct": -5.0, "duration_months": 12},
        ]
        m = bld._match_plan_to_detected(plan, detected)
        assert m is not None
        # nearest = 첫 번째 (drop diff 1, duration diff 5)
        assert m["drop_pct"] == -16.0

    def test_no_detected_returns_none(self):
        from api.builders import estate_brain_backtest_50y_builder as bld
        m = bld._match_plan_to_detected({"drop_pct": -15, "duration_months": 60}, [])
        assert m is None


class TestPlanV03Validation:
    def test_5_patterns_returned(self):
        from api.builders import estate_brain_backtest_50y_builder as bld
        out = bld._validate_plan_v0_3({"bis": [], "kosis_reb": []})
        assert len(out) == 5
        for name in ("Shock-Recovery", "Debt-Deflation Drag",
                     "Rate-Shock Rebound", "Supply Glut", "Policy Shock"):
            assert name in out
            assert out[name]["matched"] is None  # no detected

    def test_within_tolerance_marks_combined(self):
        from api.builders import estate_brain_backtest_50y_builder as bld
        # Rate-Shock Rebound plan = drop -17.2 / duration 15M
        # detected drop -17 / duration 15M → 둘 다 within
        detected = [{"drop_pct": -17.0, "duration_months": 15,
                     "peak_label": "2022Q1", "trough_label": "2023Q1"}]
        out = bld._validate_plan_v0_3({"bis": detected, "kosis_reb": []})
        assert out["Rate-Shock Rebound"]["within_tolerance_combined"] is True


class TestBuild:
    def test_no_modules_graceful(self):
        from api.builders import estate_brain_backtest_50y_builder as bld
        from api.intelligence import estate_brain_backtest as bt
        payload = bld.build(_modules={}, _bt=bt)
        assert payload["schema_version"] == "v0.3"
        assert payload["diagnostics"]["bis_available"] is False
        assert payload["diagnostics"]["kosis_reb_available"] is False
        assert len(payload["plan_v0_3_validation"]) == 5

    def test_bis_only_with_rate_shock_cycle(self):
        from api.builders import estate_brain_backtest_50y_builder as bld
        from api.intelligence import estate_brain_backtest as bt
        # drop -17%, duration 6Q (=18M, Rate-Shock 매칭)
        bis_payload = _bis_payload_with_cycle(drop_pct=-17.0, duration_quarters=6)
        modules = _make_fake_modules(bis_payload=bis_payload)
        payload = bld.build(_modules=modules, _bt=bt)
        assert payload["diagnostics"]["bis_available"] is True
        assert payload["diagnostics"]["bis_cycles_detected"] >= 1
        # Rate-Shock 정합 (drop ≈ -17, duration ≈ 18M)
        rs = payload["plan_v0_3_validation"]["Rate-Shock Rebound"]
        assert rs["matched"] is not None
        assert rs["within_tolerance_combined"] is True

    def test_kosis_with_supply_glut_cycle(self):
        from api.builders import estate_brain_backtest_50y_builder as bld
        from api.intelligence import estate_brain_backtest as bt
        # drop -15%, duration 60M = Supply Glut (1990~95)
        kosis_payload = _kosis_payload_with_cycle(drop_pct=-15.0, duration_months=60)
        modules = _make_fake_modules(kosis_payload=kosis_payload)
        payload = bld.build(_modules=modules, _bt=bt)
        assert payload["diagnostics"]["kosis_reb_available"] is True
        sg = payload["plan_v0_3_validation"]["Supply Glut"]
        assert sg["matched"] is not None
        # drop diff |15-15|=0, duration diff |60-65|=5 → both within tolerance
        assert sg["within_tolerance_combined"] is True

    def test_diagnostics_count_match(self):
        from api.builders import estate_brain_backtest_50y_builder as bld
        from api.intelligence import estate_brain_backtest as bt
        bis_payload = _bis_payload_with_cycle(drop_pct=-17.0, duration_quarters=6)
        kosis_payload = _kosis_payload_with_cycle(drop_pct=-15.0, duration_months=60)
        modules = _make_fake_modules(bis_payload=bis_payload, kosis_payload=kosis_payload)
        payload = bld.build(_modules=modules, _bt=bt)
        diag = payload["diagnostics"]
        # 5 pattern 중 어느 정도는 within (정확한 카운트 변동 허용)
        assert diag["plan_within_tolerance_count"] >= 1
        assert diag["plan_patterns_count"] == 5
