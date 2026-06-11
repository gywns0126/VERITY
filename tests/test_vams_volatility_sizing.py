"""Sprint 11 결함 3 — VAMS sizing 의 변동성 보정 검증.

베테랑 평가: 같은 -5% 손절이면 일변동성 1.2% 종목은 정상 노이즈에 손절당하고
일변동성 4.5% 종목은 손절선 도달 전 -15% 손실. 변동성 정규화 필수.

우선순위: ① technical.atr_14d_pct (percent, 직접 수집, production 상존)
  ② fallback = top-level volatility_20d (일간 분수) → 연환산%(×√252×100).
2026-06-12 정정: 옛 fallback 은 prediction.top_features.volatility_20d(=xgb feature
  importance, vol 아님)를 읽어 항상 dead 였음. 실 vol(분수) 재배선 + √252 연환산.
  본 테스트는 fallback 경로 검증(atr 부재 → top-level volatility_20d 분수 주입).
"""
from __future__ import annotations

from api.vams.engine import _apply_volatility_adj


def _stock_with_vol(vol_frac):
    """top-level volatility_20d(일간 분수) = vol_frac 인 mock stock (atr 부재 → fallback 경로)."""
    return {"volatility_20d": vol_frac}


class TestVolatilityTier:
    def test_low_vol_no_change(self):
        """연환산 ≤ 15% → 1.0× (그대로). 일간분수 ×√252×100 ≤ 15."""
        for frac in [0.005, 0.008, 0.0094]:  # 연 7.9 / 12.7 / 14.9%
            adj, meta = _apply_volatility_adj(1_000_000, _stock_with_vol(frac))
            assert adj == 1_000_000
            assert meta["tier"] == "low"
            assert meta["scale"] == 1.0

    def test_mid_vol_15_pct_reduction(self):
        """15 < 연환산 ≤ 30 → 0.85× (15% 축소)."""
        for frac in [0.010, 0.015, 0.0185]:  # 연 15.9 / 23.8 / 29.4%
            adj, meta = _apply_volatility_adj(1_000_000, _stock_with_vol(frac))
            assert adj == 850_000
            assert meta["tier"] == "mid"
            assert meta["scale"] == 0.85

    def test_high_vol_30_pct_reduction(self):
        """연환산 > 30 → 0.70× (30% 축소)."""
        for frac in [0.020, 0.030, 0.060]:  # 연 31.7 / 47.6 / 95.2%
            adj, meta = _apply_volatility_adj(1_000_000, _stock_with_vol(frac))
            assert adj == 700_000
            assert meta["tier"] == "high"
            assert meta["scale"] == 0.70


class TestEdgeCases:
    def test_no_volatility_data(self):
        """데이터 없으면 변경 없음 + applied=False."""
        adj, meta = _apply_volatility_adj(1_000_000, {})
        assert adj == 1_000_000
        assert meta["applied"] is False

    def test_empty_prediction(self):
        adj, meta = _apply_volatility_adj(1_000_000, {"prediction": {}})
        assert adj == 1_000_000
        assert meta["applied"] is False

    def test_negative_vol_treated_as_missing(self):
        """음수 / 0 변동성 → 데이터 invalid 처리 (변경 없음)."""
        adj, meta = _apply_volatility_adj(1_000_000, _stock_with_vol(-1.0))
        assert adj == 1_000_000
        assert meta["applied"] is False

    def test_string_vol_treated_as_missing(self):
        """문자열 등 비-숫자 — 가드."""
        adj, meta = _apply_volatility_adj(1_000_000, _stock_with_vol("high"))
        assert adj == 1_000_000
        assert meta["applied"] is False

    def test_atr_primary_takes_precedence(self):
        """🚨 production 경로: atr_14d_pct 존재 시 fallback 무시(primary 우선)."""
        stock = {"technical": {"atr_14d_pct": 4.0}, "volatility_20d": 0.001}
        adj, meta = _apply_volatility_adj(1_000_000, stock)
        assert meta["source"] == "atr_14d"  # fallback 아닌 primary
        assert meta["tier"] == "high"  # atr 4.0% > 3.0 → high


class TestRealisticScenarios:
    def test_kospi_large_cap_low_vol(self):
        """대형주 (일변동성 0.8% → 연 12.7%) — 그대로."""
        adj, meta = _apply_volatility_adj(2_000_000, _stock_with_vol(0.008))
        assert adj == 2_000_000  # 변경 없음
        assert meta["tier"] == "low"

    def test_kosdaq_smallcap_high_vol(self):
        """KOSDAQ 중소형 (일변동성 1.5% → 연 23.8%) — 15% 축소."""
        adj, meta = _apply_volatility_adj(2_000_000, _stock_with_vol(0.015))
        assert adj == 1_700_000
        assert meta["tier"] == "mid"

    def test_meme_or_penny_extreme_vol(self):
        """페니주 / 작전주 (일변동성 4.0% → 연 63.5%) — 30% 축소."""
        adj, meta = _apply_volatility_adj(2_000_000, _stock_with_vol(0.040))
        assert adj == 1_400_000
        assert meta["tier"] == "high"
