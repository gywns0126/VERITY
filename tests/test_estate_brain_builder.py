"""ESTATE Brain V0.2 builder — 단위 테스트.

검증:
  - build() schema 정합 (gu_aggregates 25 + complexes len(WATCHLIST))
  - macro fetch — ECOS 키 부재 시 None 안전
  - rone 어댑터 부재 시 lead_time 모두 None (silent fallback X — diagnostics 명시)
  - V0_WATCHLIST 의 단지별 brain 산출 (price_won_mock 입력 → L1 PIR 가능)
  - diagnostics 정확 (ecos / kosis / rone 가용 여부)
  - _write_json_atomic + main() smoke
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _make_fake_ecos():
    """ECOS 모듈 stub — 키 없는 듯 동작."""
    fake = MagicMock()
    fake.get_ecos_macro_block.return_value = None
    fake.latest_treasury_10y_pct.return_value = None
    fake.fetch_korea_policy_rate_series.return_value = []
    fake.compute_rate_change_pp.return_value = None
    return fake


def _make_fake_ecos_with_data():
    fake = MagicMock()
    fake.get_ecos_macro_block.return_value = {
        "available": True,
        "korea_gov_10y": {"value": 3.21, "date": "2026-04-29"},
        "korea_policy_rate": {"value": 3.5, "date": "202604"},
    }
    fake.latest_treasury_10y_pct.return_value = 3.21
    fake.fetch_korea_policy_rate_series.return_value = [
        {"DATA_VALUE": str(3.0 + i * 0.05), "TIME": f"20260{i}"} for i in range(1, 8)
    ]
    fake.compute_rate_change_pp.return_value = -0.25
    return fake


def _make_fake_kosis():
    fake = MagicMock()
    fake.fetch_seoul_median_income.return_value = {
        "value_won": 65_000_000,
        "year": 2024,
        "stat_id": "MOCK_STAT",
        "as_of": "2024",
    }
    return fake


def _make_fake_rone():
    fake = MagicMock()
    fake.fetch_weekly_jeonse_index.return_value = {"series": [{"index": 100}] * 14}
    fake.compute_jeonse_3m_change_pct.return_value = 1.2
    fake.fetch_weekly_jeonse_ratio.return_value = {"series": [{"ratio_pct": 58}] * 4}
    fake.latest_jeonse_ratio_pct.return_value = 58.0
    fake.fetch_monthly_unsold.return_value = {"series": [{"unsold": 100}] * 14}
    fake.compute_unsold_yoy_pct.return_value = 18.0
    return fake


class TestBuildSchema:
    def test_no_keys_dry_build(self):
        from api.builders import estate_brain_builder as bld
        # 모든 source down — 빈 vercel-api 어댑터 + ECOS 키 없음
        payload = bld.build(_modules={}, _ecos=_make_fake_ecos())
        assert payload["schema_version"] == "v0.2"
        assert "generated_at" in payload
        # 25구 모두 aggregate brain (lead_time None 도 산출 가능)
        assert len(payload["gu_aggregates"]) == 25
        # watchlist 5단지
        assert len(payload["complexes"]) == 5
        diag = payload["diagnostics"]
        assert diag["ecos_available"] is False
        assert diag["kosis_available"] is False
        assert diag["rone_jeonse_available"] is False
        assert diag["watchlist_size"] == 5

    def test_with_macro_data(self):
        from api.builders import estate_brain_builder as bld
        payload = bld.build(
            _modules={"kosis": _make_fake_kosis()},
            _ecos=_make_fake_ecos_with_data(),
        )
        macro = payload["macro"]
        assert macro["treasury_10y_pct"] == 3.21
        assert macro["rate_change_pp_6m"] == -0.25
        assert macro["annual_median_income_won"] == 65_000_000
        diag = payload["diagnostics"]
        assert diag["ecos_available"] is True
        assert diag["kosis_available"] is True

    def test_with_rone_data(self):
        from api.builders import estate_brain_builder as bld
        payload = bld.build(
            _modules={"rone": _make_fake_rone()},
            _ecos=_make_fake_ecos(),
        )
        diag = payload["diagnostics"]
        assert diag["rone_jeonse_available"] is True
        assert diag["rone_unsold_available"] is True
        # 25구 lead_time 잘 들어갔는지 — 첫 구 cycle_analog.lead_time_signals 검증
        first_gu = list(payload["gu_aggregates"].values())[0]
        leads = first_gu["cycle_analog"]["lead_time_signals"]
        assert "jeonse_3m_lead" in leads
        assert leads["jeonse_3m_lead"]["value_pct"] == 1.2


class TestComplexBrain:
    def test_complex_includes_redev_when_specified(self):
        from api.builders import estate_brain_builder as bld
        payload = bld.build(
            _modules={"rone": _make_fake_rone(), "kosis": _make_fake_kosis()},
            _ecos=_make_fake_ecos_with_data(),
        )
        # 강남구 은마 = 관리처분 인가 (재개발) → max_uplift
        eunma = payload["complexes"]["강남구_대치동_은마_1979"]
        assert eunma["redevelopment_stage"] is not None
        assert eunma["redevelopment_stage"]["price_phase"] == "max_uplift"
        assert eunma["redevelopment_stage"]["project_type"] == "redevelopment"

    def test_complex_no_redev_for_new_build(self):
        from api.builders import estate_brain_builder as bld
        payload = bld.build(
            _modules={},
            _ecos=_make_fake_ecos(),
        )
        # 송파구 잠실엘스 (2008) = 재건축 대상 X
        target = payload["complexes"]["송파구_잠실동_잠실엘스_2008"]
        assert target["redevelopment_stage"] is None

    def test_complex_pir_layer_with_kosis(self):
        from api.builders import estate_brain_builder as bld
        payload = bld.build(
            _modules={"kosis": _make_fake_kosis()},
            _ecos=_make_fake_ecos_with_data(),
        )
        # KOSIS 65M + 은마 mock 26억 → PIR ≈ 40 → high z
        eunma = payload["complexes"]["강남구_대치동_은마_1979"]
        l1 = eunma["valuation"]["layers"]["L1_pir"]
        assert l1 is not None
        assert l1["value"] == pytest.approx(26e8 / 65e6, abs=0.5)
        # MA 18, σ 2 → z 매우 큼 → high
        assert l1["verdict"] == "high"


class TestWatchlist:
    def test_watchlist_size_5(self):
        from api.builders import estate_brain_builder as bld
        assert len(bld.V0_WATCHLIST) == 5

    def test_watchlist_complex_ids_unique(self):
        from api.builders import estate_brain_builder as bld
        ids = [w["complex_id"] for w in bld.V0_WATCHLIST]
        assert len(set(ids)) == len(ids)

    def test_watchlist_all_have_required_fields(self):
        from api.builders import estate_brain_builder as bld
        required = {"complex_id", "gu", "dong", "apt", "build_year",
                    "price_won_mock", "jeonse_won_mock"}
        for w in bld.V0_WATCHLIST:
            assert required <= set(w.keys())


class TestRTMSSwap:
    def _fake_molit(self, trades):
        m = MagicMock()
        m.fetch_recent_trades.return_value = trades
        return m

    def _fake_clustering(self):
        # clustering 실 모듈 그대로 사용 (재구현 X)
        import importlib.util
        from pathlib import Path
        repo = Path(__file__).resolve().parent.parent
        path = repo / "vercel-api" / "api" / "landex" / "_clustering.py"
        spec = importlib.util.spec_from_file_location("clu_for_test", str(path))
        mod = importlib.util.module_from_spec(spec)
        sys.modules["clu_for_test"] = mod
        spec.loader.exec_module(mod)
        return mod

    def test_match_replaces_mock_price(self):
        from api.builders import estate_brain_builder as bld
        # 은마 단지 매칭되도록 trades 박음
        trades = [
            {"apt": "은마", "dong": "대치동", "build_year": 1979,
             "area_m2": 76, "price_won": 22e8,
             "price_pyeong": 22e8 / (76 / 3.305785),
             "deal_date": "2026-04-15", "trade_type": "중개거래"},
            {"apt": "은마", "dong": "대치동", "build_year": 1979,
             "area_m2": 76, "price_won": 23e8,
             "price_pyeong": 23e8 / (76 / 3.305785),
             "deal_date": "2026-04-20", "trade_type": "중개거래"},
        ]
        modules = {"molit": self._fake_molit(trades), "clustering": self._fake_clustering()}
        item = bld.V0_WATCHLIST[0]  # 은마
        real = bld._fetch_watchlist_real_price(item, modules)
        assert real is not None
        assert real["price_source"] == "rtms_actual"
        assert real["trade_count"] == 2
        # 평균가 ≈ 22.5억
        assert 22e8 < real["price_won"] < 23e8

    def test_no_match_returns_none(self):
        from api.builders import estate_brain_builder as bld
        trades = [
            {"apt": "다른단지", "dong": "다른동", "build_year": 2000,
             "area_m2": 84, "price_won": 10e8,
             "price_pyeong": 10e8 / (84 / 3.305785),
             "deal_date": "2026-04-15", "trade_type": "중개거래"},
        ]
        modules = {"molit": self._fake_molit(trades), "clustering": self._fake_clustering()}
        item = bld.V0_WATCHLIST[0]
        assert bld._fetch_watchlist_real_price(item, modules) is None

    def test_no_modules_returns_none(self):
        from api.builders import estate_brain_builder as bld
        item = bld.V0_WATCHLIST[0]
        assert bld._fetch_watchlist_real_price(item, {}) is None

    def test_empty_trades_returns_none(self):
        from api.builders import estate_brain_builder as bld
        modules = {"molit": self._fake_molit([]), "clustering": self._fake_clustering()}
        item = bld.V0_WATCHLIST[0]
        assert bld._fetch_watchlist_real_price(item, modules) is None

    def test_compute_complex_falls_back_to_mock(self):
        from api.builders import estate_brain_builder as bld
        # modules 없음 → mock fallback
        from api.intelligence.estate_brain import compute_estate_brain
        item = bld.V0_WATCHLIST[0]
        brain = bld._compute_complex(
            item, {"annual_median_income_won": 65e6, "treasury_10y_pct": 3.2},
            {}, compute_estate_brain, modules={},
        )
        assert brain["model_meta"]["price_source"] == "v0_mock"
        assert "rtms_meta" not in brain["model_meta"]

    def test_compute_complex_uses_rtms_when_match(self):
        from api.builders import estate_brain_builder as bld
        from api.intelligence.estate_brain import compute_estate_brain
        trades = [
            {"apt": "은마", "dong": "대치동", "build_year": 1979,
             "area_m2": 76, "price_won": 22e8,
             "price_pyeong": 22e8 / (76 / 3.305785),
             "deal_date": "2026-04-15", "trade_type": "중개거래"},
        ]
        modules = {"molit": self._fake_molit(trades), "clustering": self._fake_clustering()}
        item = bld.V0_WATCHLIST[0]
        brain = bld._compute_complex(
            item, {"annual_median_income_won": 65e6, "treasury_10y_pct": 3.2},
            {}, compute_estate_brain, modules=modules,
        )
        assert brain["model_meta"]["price_source"] == "rtms_actual"
        assert "rtms_meta" in brain["model_meta"]
        assert brain["model_meta"]["rtms_meta"]["trade_count"] == 1


class TestWriteAtomic:
    def test_write_creates_dir_and_file(self, tmp_path):
        from api.builders import estate_brain_builder as bld
        target = tmp_path / "subdir" / "out.json"
        bld._write_json_atomic(str(target), {"x": 1})
        assert target.exists()
        with open(target, encoding="utf-8") as f:
            assert json.load(f) == {"x": 1}
