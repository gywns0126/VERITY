"""Sprint 11 결함 3 — VAMS sizing 의 변동성 보정 검증.

베테랑 평가: 같은 -5% 손절이면 일변동성 1.2% 종목은 정상 노이즈에 손절당하고
일변동성 4.5% 종목은 -15% 박살. 변동성 정규화 필수.

완전한 ATR 기반 sizing 은 데이터 수집 추가 필요. 임시로 prediction.top_features.
volatility_20d (20일 변동성 %) 를 proxy 사용. tier 별 multiplier (저/중/고).
"""
from __future__ import annotations

from api.vams.engine import _apply_volatility_adj


def _stock_with_vol(vol):
    """volatility_20d 가 vol 인 mock stock."""
    return {
        "prediction": {
            "top_features": {"volatility_20d": vol}
        }
    }


class TestVolatilityTier:
    def test_low_vol_no_change(self):
        """volatility_20d ≤ 15% → 1.0× (그대로)."""
        for vol in [5.0, 10.0, 15.0]:
            adj, meta = _apply_volatility_adj(1_000_000, _stock_with_vol(vol))
            assert adj == 1_000_000
            assert meta["tier"] == "low"
            assert meta["scale"] == 1.0

    def test_mid_vol_15_pct_reduction(self):
        """15 < vol ≤ 30 → 0.85× (15% 축소)."""
        for vol in [15.5, 20.0, 30.0]:
            adj, meta = _apply_volatility_adj(1_000_000, _stock_with_vol(vol))
            assert adj == 850_000
            assert meta["tier"] == "mid"
            assert meta["scale"] == 0.85

    def test_high_vol_30_pct_reduction(self):
        """vol > 30 → 0.70× (30% 축소)."""
        for vol in [30.5, 50.0, 100.0]:
            adj, meta = _apply_volatility_adj(1_000_000, _stock_with_vol(vol))
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


class TestRealisticScenarios:
    def test_kospi_large_cap_low_vol(self):
        """삼성전자급 (일변동성 1.2% × √20 ≈ 5.4%) — 그대로."""
        adj, meta = _apply_volatility_adj(2_000_000, _stock_with_vol(5.4))
        assert adj == 2_000_000  # 변경 없음
        assert meta["tier"] == "low"

    def test_kosdaq_smallcap_high_vol(self):
        """KOSDAQ 바이오주급 (일변동성 4.5% × √20 ≈ 20%) — 15% 축소."""
        adj, meta = _apply_volatility_adj(2_000_000, _stock_with_vol(20.0))
        assert adj == 1_700_000
        assert meta["tier"] == "mid"

    def test_meme_or_penny_extreme_vol(self):
        """페니주 / 작전주 (변동성 50%+) — 30% 축소."""
        adj, meta = _apply_volatility_adj(2_000_000, _stock_with_vol(50.0))
        assert adj == 1_400_000
        assert meta["tier"] == "high"
