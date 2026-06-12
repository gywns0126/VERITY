"""mc_risk — Monte Carlo 리스크 분포 레이어 (block bootstrap, 실 수익률 재추출).

PM 사전등록: [[project_b4_sprint_tools_2026_05_27]] §2026-05-31 (ARENA 흡수).
B4 sprint 진입 (2026-06-12) 구현. seed = scripts/arena_sim_prototype.py
(엔진 prototype, 실데이터 작동 검증 5/31) — bootstrap_paths/evaluate 이식.

WHY: IC/ICIR (신호 예측력) 이 못 주는 차원 = "결정 정책의 위험 분포".
단일 백테스트 = 1 경로. MC = 파산 확률 / MDD 분포 / 최종 자본배수 분위수.

🚨 순환 함정 가드 (사전등록 CRITICAL):
  - 순수 GBM = 넣은 μ/σ 재생산 (정규분포 가정) → 검증 아님.
    `gbm_forward_scenario` 로 분리, 라벨 = "forward_scenario_not_validation".
  - 정공법 = 실 historical 일별 수익률 block bootstrap (fat tail/serial corr 보존).

🚨 block 길이 = 사전등록 파라미터 (5/31 프로토타입 실증):
  최악 MDD 가 block 길이에 비단조 (SPY 3x: block10 48% / block30 51% / block252 41%).
  중간 block = 시대 교차 폭락 합성 (최악 > 실제), 긴 block = 실 연속이나 표본 얇음.
  → **단일 block 값 보고 = 함정. 다 block 동시 보고 + 선택 근거 명시 의무.**
  default blocks = (10, 30, 63, 252): 2주 / 6주(분기 절반) / 분기 / 1년.

성과 메트릭: MDD 산식 = api/quant/risk_metrics.py max_drawdown 와 동일 정의
(running max 대비 낙폭 최소값, 음수). 경로 수 × 다 block 벡터화 위해 내부
numpy 구현 (empyrical per-path 호출 = 비효율 + optional dep).

RULE 7 정합: infrastructure (검증 도구). ruin/MDD 임계 게이트 wire 시
= PM 사전등록 별도 의무.
"""
from __future__ import annotations

from typing import Dict, Optional, Sequence

import numpy as np

__all__ = ["block_bootstrap_paths", "evaluate_paths", "mc_risk_report", "gbm_forward_scenario"]

DEFAULT_BLOCKS = (10, 30, 63, 252)


def block_bootstrap_paths(
    daily_returns: np.ndarray,
    horizon_days: int,
    n_paths: int,
    block: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Block bootstrap — 실 일별 수익률 연속 덩어리 재추출 (wrap-around).

    fat tail / 변동성 군집 (serial correlation) 보존. arena_sim_prototype 이식.

    Args:
        daily_returns: 실 historical 일별 단순수익률 1-D array.
        horizon_days: 시뮬 horizon (일).
        n_paths: 경로 수.
        block: 연속 덩어리 길이 (일).
        rng: np.random.Generator (호출자 seed 관리 — 재현성).

    Returns:
        (n_paths, horizon_days) 일별 단순수익률.
    """
    real = np.asarray(daily_returns, dtype=float)
    m = len(real)
    if m < block * 3:
        raise ValueError(f"historical too short: {m} < block×3 ({block * 3})")
    n_blocks = int(np.ceil(horizon_days / block))
    starts = rng.integers(0, m, size=(n_paths, n_blocks))
    offsets = np.arange(block)
    idx = (starts[:, :, None] + offsets[None, None, :]) % m
    idx = idx.reshape(n_paths, n_blocks * block)[:, :horizon_days]
    return real[idx]


def evaluate_paths(
    path_returns: np.ndarray,
    position: float = 1.0,
    leverage: float = 1.0,
    cost: float = 0.0,
    ruin_threshold: float = 0.5,
) -> Dict:
    """경로 묶음 → 자본배수/MDD/파산확률 분포. arena_sim_prototype evaluate 이식.

    Args:
        path_returns: (n_paths, horizon) 일별 단순수익률.
        position: 자본 대비 포지션 비중.
        leverage: 레버리지 (일일 적용 1차 근사).
        cost: 진입+청산 왕복 비용 (최종 1회 차감).
        ruin_threshold: "파산" 정의 자본배수 (default 0.5 = 반토막).

    Returns:
        분위수 dict — final multiple p5/p50/p95, p_loss, p_ruin, MDD 분포.
        MDD = running max 대비 낙폭 (음수, risk_metrics.max_drawdown 정의 정합).
    """
    daily_port = position * (leverage * path_returns)
    growth = np.cumprod(np.maximum(1.0 + daily_port, 0.0), axis=1)  # 일일 wipeout floor
    final = growth[:, -1] * (1.0 - cost)
    run_max = np.maximum.accumulate(growth, axis=1)
    mdd = (growth / np.maximum(run_max, 1e-12) - 1.0).min(axis=1)
    p = lambda a, q: float(np.percentile(a, q))  # noqa: E731
    return {
        "final_p5": round(p(final, 5), 4),
        "final_p50": round(p(final, 50), 4),
        "final_p95": round(p(final, 95), 4),
        "p_loss": round(float((final < 1.0).mean()), 4),
        "p_ruin": round(float((final < ruin_threshold).mean()), 4),
        "mdd_p50": round(p(mdd, 50), 4),
        "mdd_p95": round(p(mdd, 5), 4),    # 분포 하위 5% = 심한 쪽 MDD
        "mdd_worst": round(float(mdd.min()), 4),
    }


def mc_risk_report(
    daily_returns: Sequence[float],
    horizon_days: int = 252,
    n_paths: int = 10_000,
    blocks: Sequence[int] = DEFAULT_BLOCKS,
    position: float = 1.0,
    leverage: float = 1.0,
    cost: float = 0.0,
    ruin_threshold: float = 0.5,
    seed: int = 7,
) -> Dict:
    """다 block 동시 MC 리스크 리포트 (사전등록 의무 형식).

    단일 block 보고 금지 — block 별 최악 MDD 비단조성 (5/31 실증) 노출 의무.

    Returns:
        {
          "method": "block_bootstrap_real_returns",
          "n_historical_days": int,
          "horizon_days": int, "n_paths": int,
          "position": float, "leverage": float, "ruin_threshold": float,
          "by_block": {block: evaluate dict},
          "blocks_rationale": str,
          "caveat": str,
        }
    """
    real = np.asarray([r for r in daily_returns if np.isfinite(r)], dtype=float)
    rng = np.random.default_rng(seed)
    usable = [b for b in blocks if len(real) >= b * 3]
    skipped = [b for b in blocks if b not in usable]
    by_block = {}
    for b in usable:
        paths = block_bootstrap_paths(real, horizon_days, n_paths, b, rng)
        by_block[int(b)] = evaluate_paths(paths, position, leverage, cost, ruin_threshold)
    return {
        "method": "block_bootstrap_real_returns",
        "n_historical_days": int(len(real)),
        "horizon_days": int(horizon_days),
        "n_paths": int(n_paths),
        "position": position,
        "leverage": leverage,
        "ruin_threshold": ruin_threshold,
        "by_block": by_block,
        "blocks_skipped_short_history": skipped or None,
        "blocks_rationale": "10=2주/30=6주/63=분기/252=1년. 최악MDD 비단조 (5/31 실증) — 단일 block 보고 금지, 전 block 병기.",
        "caveat": "historical estimate (가설). 실 분포 재추출이나 미래 보장 아님. survivorship/기간 의존 명시 의무.",
    }


def gbm_forward_scenario(
    mu_annual: float,
    sigma_annual: float,
    horizon_days: int = 252,
    n_paths: int = 10_000,
    periods_per_year: int = 252,
    position: float = 1.0,
    leverage: float = 1.0,
    cost: float = 0.0,
    ruin_threshold: float = 0.5,
    seed: int = 7,
) -> Dict:
    """GBM forward 시나리오 — 🚨 검증 아님 (순환 함정: 넣은 μ/σ 재생산).

    라벨 의무: "forward_scenario_not_validation". 가정 기반 탐색 전용.
    """
    rng = np.random.default_rng(seed)
    drift = (mu_annual - 0.5 * sigma_annual ** 2) / periods_per_year
    vol = sigma_annual / np.sqrt(periods_per_year)
    z = rng.standard_normal((n_paths, horizon_days))
    paths = np.exp(drift + vol * z) - 1.0
    out = evaluate_paths(paths, position, leverage, cost, ruin_threshold)
    out["label"] = "forward_scenario_not_validation"
    out["caveat"] = "GBM 정규분포 가정 — 입력 μ/σ 재생산. fat tail 부재. 검증 용도 사용 금지."
    return out
