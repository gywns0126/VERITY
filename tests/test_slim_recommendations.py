"""2026-05-20 — _slim_recommendations backtest scalar 보존 검증.

backtest @50 결함 root cause: backtest 가 _REC_EXCLUDE_FIELDS 로 portfolio.json 에서 통째 strip
→ brain quick mode 가 50 fallback. fix: scalar(total_trades/win_rate/sharpe_ratio) 보존,
recent_trades 배열만 drop. recommendations.json(전체본)은 영향 X.
"""
from __future__ import annotations

from api.vams.engine import _slim_recommendations


def test_slim_keeps_backtest_scalars_drops_recent_trades():
    rec = {
        "ticker": "X",
        "current_price": 100,
        "backtest": {
            "total_trades": 30, "win_rate": 60.0, "sharpe_ratio": 0.9,
            "avg_return": 1.2, "max_drawdown": -5.0,
            "recent_trades": [{"a": 1}] * 20,
        },
        "dart_financials": {"big": "x"},   # exclude
        "quant_factors": {"x": 1},          # exclude
    }
    out = _slim_recommendations([rec])[0]
    assert out["current_price"] == 100
    assert "dart_financials" not in out
    assert "quant_factors" not in out
    # backtest scalar 보존 — brain _backtest_to_score 입력
    assert out["backtest"]["total_trades"] == 30
    assert out["backtest"]["win_rate"] == 60.0
    assert out["backtest"]["sharpe_ratio"] == 0.9
    # 큰 배열만 drop
    assert "recent_trades" not in out["backtest"]


def test_slim_no_backtest_key_unchanged():
    out = _slim_recommendations([{"ticker": "Y", "current_price": 1}])[0]
    assert out == {"ticker": "Y", "current_price": 1}
