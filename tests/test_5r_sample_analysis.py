"""5R 표본 가능성 분석 — 단위 테스트 (5 cases).

Cases:
  1. ATR-stop 거리 계산 — entry_close + ATR + multiplier 로 stop_price/target 산출
  2. 5R 도달 판정 — high 가 target 도달 시 5r_hit, days_held 정확
  3. 손절 hit 시 종료 — low 가 stop 도달 시 stop_loss, r_multiple=-1.0
  4. 252일 만기 종료 — 손절·5R 미도달 시 max_days exit
  5. 데이터 부족 — entry 후 max_days 미충족 시 delisted_or_insufficient
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# scripts/ 는 패키지가 아니라 importlib 로 모듈 로드
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "analyze_5r_sample_feasibility.py"
_spec = importlib.util.spec_from_file_location("analyze_5r", str(_SCRIPT_PATH))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

simulate_position = _mod.simulate_position
ATR_MULTIPLIER = _mod.ATR_MULTIPLIER
DELISTED_R_MULTIPLE = _mod.DELISTED_R_MULTIPLE


def _make_ohlcv(prices: list[tuple[float, float, float]]) -> pd.DataFrame:
    """(high, low, close) 튜플 → DataFrame. open=close 가정."""
    return pd.DataFrame({
        "open": [c for _, _, c in prices],
        "high": [h for h, _, _ in prices],
        "low": [l for _, l, _ in prices],
        "close": [c for _, _, c in prices],
    })


class Test5RSimulation:
    def test_atr_stop_distance_no_trigger(self):
        # entry close=100, ATR=2 → R=5 → stop=95, 5R target=125
        # 진입 후 5봉 변동 100~100.5 → 손절·5R 미도달 + 데이터 부족
        prices = [(99, 99, 99)] * 60 + [(100, 100, 100)]
        prices += [(100.5, 99.5, 100)] * 5
        df = _make_ohlcv(prices)
        result = simulate_position(df, entry_idx=60, atr_value=2.0, max_days=252)
        # 데이터 5봉만, max_days=252 미충족 → delisted_or_insufficient
        assert result["exit_reason"] == "delisted_or_insufficient"
        assert result["r_multiple"] == DELISTED_R_MULTIPLE
        # max_high=100.5 → (100.5-100)/5 = 0.1 R
        assert result["max_excursion_r"] == pytest.approx(0.1, abs=0.01)
        assert result["hit_5r"] is False

    def test_5r_hit(self):
        # entry=100, ATR=1 → R=2.5, 5R target=112.5
        # idx 70 (entry+10) 에서 high=113 도달
        prices = [(99, 99, 99)] * 60 + [(100, 100, 100)]
        for _ in range(9):
            prices.append((101, 99, 100.5))
        prices.append((113, 100, 112))   # 5R hit (113 > 112.5)
        prices += [(110, 105, 108)] * 5  # 종료 후 노이즈 (영향 X)
        df = _make_ohlcv(prices)
        result = simulate_position(df, entry_idx=60, atr_value=1.0, max_days=252)
        assert result["exit_reason"] == "5r_hit"
        assert result["r_multiple"] == pytest.approx(5.0)
        assert result["hit_5r"] is True
        assert result["days_held"] == 10

    def test_stop_loss_hit(self):
        # entry=100, ATR=2 → R=5 → stop=95
        # idx 65 (entry+5) 에서 low=94 → stop hit
        prices = [(99, 99, 99)] * 60 + [(100, 100, 100)]
        for _ in range(4):
            prices.append((101, 98, 99.5))
        prices.append((96, 94, 95))      # stop hit (low 94 ≤ 95)
        prices += [(95, 90, 92)] * 5
        df = _make_ohlcv(prices)
        result = simulate_position(df, entry_idx=60, atr_value=2.0, max_days=252)
        assert result["exit_reason"] == "stop_loss"
        assert result["r_multiple"] == pytest.approx(-1.0)
        assert result["days_held"] == 5
        assert result["hit_5r"] is False  # 손절 전 5R 미도달

    def test_max_days_exit(self):
        # entry=100, ATR=2 → R=5 → stop=95, target=125
        # 252봉 동안 100~104.5 oscillate → 손절·5R 미도달, max_days 만기
        prices = [(99, 99, 99)] * 60 + [(100, 100, 100)]
        for i in range(252):
            base = 100 + (i % 10) * 0.5  # 100~104.5
            prices.append((base + 0.3, base - 0.3, base))
        df = _make_ohlcv(prices)
        result = simulate_position(df, entry_idx=60, atr_value=2.0, max_days=252)
        assert result["exit_reason"] == "max_days"
        assert result["days_held"] == 252
        assert result["hit_5r"] is False
        # max excursion = (104.8-100)/5 ≈ 0.96R, 5 미만
        assert result["max_excursion_r"] < 5.0

    def test_data_insufficient_after_entry(self):
        # entry 후 50봉만 → 252 < 50 → delisted_or_insufficient
        prices = [(99, 99, 99)] * 60 + [(100, 100, 100)]
        for _ in range(50):
            prices.append((101, 99, 100))
        df = _make_ohlcv(prices)
        result = simulate_position(df, entry_idx=60, atr_value=2.0, max_days=252)
        assert result["exit_reason"] == "delisted_or_insufficient"
        assert result["days_held"] == 50  # 사용 가능한 데이터 끝까지
        assert result["r_multiple"] == DELISTED_R_MULTIPLE
