"""
risk_metrics — empyrical-reloaded wrapper. VAMS validation 확장 영역.

audit (general-purpose agent, 2026-05-17) 결과:
- empyrical-reloaded (Stefan Jansen fork, Apache-2.0, 2025-06 활성)
- VAMS validation_report 의 6 지표 = 자기 합격선 유지
- empyrical wrapper = 추가 4 지표 (Sortino / Calmar / Beta / capture ratio)
- thin replace 가능 (Sharpe / MDD) — 단 자기 호환성 보존 위해 별도 모듈

wiring: 현재 dead code. VAMS validation 에 wire = 후속 sprint (frontend 정합 검증 후).

세후 (AT) 호환: empyrical 자체 세후 모드 없음 → 호출자가 AT returns pre-compute 후 전달.
R_f 일관성: [[feedback_rf_pretax_consistency]] — 세전 일관 (empyrical default rf=0 라 부담 X).
"""
from __future__ import annotations
from typing import Optional
import numpy as np
import pandas as pd

try:
    import empyrical as emp
    _EMP_AVAILABLE = True
except ImportError:
    _EMP_AVAILABLE = False


# ──────────────────────────────────────────────────────────────
# 기존 VAMS 지표 thin wrapper (호환성 보존)
# ──────────────────────────────────────────────────────────────

def annualized_sharpe(returns: np.ndarray, risk_free: float = 0.0,
                      periods: int = 252) -> Optional[float]:
    """연환산 Sharpe. VAMS _annualized_sharpe 정합.

    R_f = 0 default (분자/분모 동시 세전 통일 [[feedback_rf_pretax_consistency]]).
    """
    if not _EMP_AVAILABLE:
        return None
    if returns is None or len(returns) < 2:
        return None
    return float(emp.sharpe_ratio(np.asarray(returns), risk_free=risk_free, period='daily', annualization=periods))


def max_drawdown(returns: np.ndarray) -> Optional[float]:
    """최대 낙폭. VAMS _max_drawdown_pct 정합 (음수 magnitude, MDD UI 정합).

    메모리 [[feedback_mdd_magnitude_display]]: UI 양수 magnitude 만, 함수는 음수 반환.
    """
    if not _EMP_AVAILABLE or returns is None or len(returns) < 2:
        return None
    return float(emp.max_drawdown(np.asarray(returns)))


# ──────────────────────────────────────────────────────────────
# 신규 4 지표 (empyrical 도입 가치)
# ──────────────────────────────────────────────────────────────

def sortino_ratio(returns: np.ndarray, required_return: float = 0.0,
                  periods: int = 252) -> Optional[float]:
    """Sortino = (returns - target) / downside σ. 하방 σ 만 패널티.

    Sharpe 의 단점 (상방 σ 도 패널티) 해소. Phase 2 5 모듈 Stress 영역 입력.
    """
    if not _EMP_AVAILABLE or returns is None or len(returns) < 2:
        return None
    return float(emp.sortino_ratio(np.asarray(returns), required_return=required_return, period='daily', annualization=periods))


def calmar_ratio(returns: np.ndarray, periods: int = 252) -> Optional[float]:
    """Calmar = annualized return / |MDD|. MDD 대비 효율.

    Sharpe 보다 risk-aware. Tier 진화 trigger metric.
    """
    if not _EMP_AVAILABLE or returns is None or len(returns) < 2:
        return None
    return float(emp.calmar_ratio(np.asarray(returns), period='daily', annualization=periods))


def alpha_beta(returns: np.ndarray, benchmark_returns: np.ndarray,
               risk_free: float = 0.0, periods: int = 252) -> tuple[Optional[float], Optional[float]]:
    """Jensen's alpha + beta vs 벤치마크 (KOSPI).

    VAMS validation_report 현재 excess_pp 만 기록됨. alpha/beta 별도 필요.
    """
    if not _EMP_AVAILABLE or returns is None or benchmark_returns is None:
        return (None, None)
    r = np.asarray(returns)
    b = np.asarray(benchmark_returns)
    if len(r) < 2 or len(b) < 2 or len(r) != len(b):
        return (None, None)
    try:
        a, beta = emp.alpha_beta(r, b, risk_free=risk_free, period='daily', annualization=periods)
        return (float(a), float(beta))
    except Exception:
        return (None, None)


def capture_ratios(returns: np.ndarray, benchmark_returns: np.ndarray
                   ) -> tuple[Optional[float], Optional[float]]:
    """Up / Down capture ratio.

    Up capture = 벤치 상승일 평균 / 벤치 평균상승
    Down capture = 벤치 하락일 평균 / 벤치 평균하락
    이상 = (Up 높, Down 낮음). Phase 2 5 모듈 Attribution 영역.
    """
    if not _EMP_AVAILABLE or returns is None or benchmark_returns is None:
        return (None, None)
    r = np.asarray(returns)
    b = np.asarray(benchmark_returns)
    if len(r) < 2 or len(b) < 2 or len(r) != len(b):
        return (None, None)
    try:
        up = float(emp.up_capture(r, b))
        down = float(emp.down_capture(r, b))
        return (up, down)
    except Exception:
        return (None, None)


# ──────────────────────────────────────────────────────────────
# 통합 dispatcher — validation_report 확장 1줄 호출
# ──────────────────────────────────────────────────────────────

def compute_risk_metrics(returns: np.ndarray,
                          benchmark_returns: Optional[np.ndarray] = None,
                          risk_free: float = 0.0,
                          periods: int = 252) -> dict:
    """VAMS validation 확장용 — 모든 지표 한 번에.

    Returns:
        {
            "sharpe": float | None,        # 기존 호환
            "sortino": float | None,       # 신규 — 하방 σ
            "calmar": float | None,        # 신규 — annualized / |MDD|
            "max_drawdown": float | None,  # 기존 호환 (음수)
            "alpha": float | None,         # 신규 — vs benchmark
            "beta": float | None,          # 신규 — vs benchmark
            "up_capture": float | None,    # 신규
            "down_capture": float | None,  # 신규
            "available": bool,             # empyrical 설치 여부
        }
    """
    if not _EMP_AVAILABLE:
        return {"available": False}

    a, b = (None, None)
    up, down = (None, None)
    if benchmark_returns is not None:
        a, b = alpha_beta(returns, benchmark_returns, risk_free, periods)
        up, down = capture_ratios(returns, benchmark_returns)

    return {
        "sharpe": annualized_sharpe(returns, risk_free, periods),
        "sortino": sortino_ratio(returns, required_return=0.0, periods=periods),
        "calmar": calmar_ratio(returns, periods),
        "max_drawdown": max_drawdown(returns),
        "alpha": a,
        "beta": b,
        "up_capture": up,
        "down_capture": down,
        "available": True,
    }
