"""ic_backtest — B4 Phase 1 부분 backtest 엔진 (fact_score subset IC/ICIR walk-forward).

PM 사전등록: [[project_verity_backtest_sprint]] (2026-05-19 B4 자문 + PM 결정 B).
**B4 진입 2026-06-12 — 산식 동결 시작 (~2026-08-12 변경 금지, look-ahead bias 회피).**

Full backtest 폐기 사유 (사전등록 그대로):
  1. sentiment 13-source historical 부재
  2. DART/yfinance PIT 미보장
  3. 산식 빠른 진화 → 1회 backtest 가 현재 v5 대표 못 함
→ 정공법 = fact_score 가용 subset (가격 기반 + 재무비율) IC/ICIR 부분 backtest.

측정 spec (사전등록 그대로):
  - walk-forward: 1y train(252d) / 6m test(126d) / 3m step(63d)
  - rank IC (Spearman): component score vs forward return 횡단면 상관
  - ICIR = mean(IC) / std(IC)
  - 합격 밴드: IC>0.05+ICIR>0.3 강 / IC 0.02~0.05 활용 가능 / IC≈0 예측력 없음
  - 다중 검정: Bonferroni α/n_components + t>3.0 + DSR (psr.py 재사용)

가드 (학술 의무, 사전등록 체크리스트):
  - Survivorship bias: yfinance 한계 — 결과 보수 해석, 보고서 caveat 의무
  - Holdout 격리: 최종 HOLDOUT_FRACTION(20%) 개발 중 절대 미접근 — 엔진이 기본 절단
  - 시도 횟수 기록: 측정 config 변경 = trial — DSR n_trials 입력 (TRIAL_LOG)

데이터 어댑터 (yfinance fetch + component 재계산) = 별 모듈 (후속 세션).
본 모듈 = 순수 측정 엔진 (입력: scores/prices DataFrame).

RULE 7: 본 엔진 = infrastructure. 측정 대상 산식 = 아래 FROZEN_COMPONENTS
(2026-06-12 동결). 측정 config (horizon/sampling) 변경 = TRIAL_LOG 기록 의무.
"""
from __future__ import annotations

import math
from typing import Dict, Iterator, List, Optional, Tuple

import numpy as np
import pandas as pd

from api.quant.alpha.psr import compute_deflated_sharpe_ratio

__all__ = [
    "FROZEN_COMPONENTS", "FORMULA_FREEZE_DATE", "walk_forward_windows",
    "cross_sectional_ic", "run_ic_backtest",
]

# ─── 산식 동결 (RULE 7) ──────────────────────────────────────────
# 2026-06-12 B4 진입 시점 Brain v5 component 정의 동결.
# 변경 금지 ~2026-08-12. 대상 = 사전등록 HIGH/MEDIUM 산출 가능 subset.
FORMULA_FREEZE_DATE = "2026-06-12"
FROZEN_COMPONENTS = [
    # 가격 기반 (HIGH 산출 가능)
    "momentum",
    "quant_volatility",
    "quant_momentum",
    "quant_mean_reversion",
    "technical_mean_reversion",
    # 재무비율 (MEDIUM — DART/yfinance top-level, PIT caveat)
    "graham_value",
    "multi_factor",
    "moat_quality",
]
# 제외 (사전등록 그대로): analyst_report/consensus/equity_brief(상업DB),
# dart_health(AI 정성), perplexity_risk/commodity_margin(retroactive 불가)

# ─── 측정 config (변경 = trial 기록 의무) ────────────────────────
TRAIN_DAYS = 252      # 1y
TEST_DAYS = 126       # 6m
STEP_DAYS = 63        # 3m
FORWARD_HORIZON_DAYS = 21   # score → 1개월 forward return
IC_SAMPLING_DAYS = 5        # 주 1회 횡단면 (일별 = forward window 중첩 autocorr)
HOLDOUT_FRACTION = 0.20     # 최종 20% 절대 미접근 (개발 중)
MIN_CROSS_SECTION = 10      # 횡단면 최소 종목 수

# 시도 횟수 기록 (DSR n_trials 입력) — config 변경 시 항목 추가 의무
TRIAL_LOG: List[Dict] = [
    {"date": "2026-06-12", "trial": 1,
     "config": "h21d/w5d/train252/test126/step63/holdout20%", "note": "B4 진입 초기 config"},
]


def walk_forward_windows(
    dates: pd.DatetimeIndex,
    train_days: int = TRAIN_DAYS,
    test_days: int = TEST_DAYS,
    step_days: int = STEP_DAYS,
) -> Iterator[Tuple[pd.DatetimeIndex, pd.DatetimeIndex]]:
    """walk-forward (train, test) 거래일 window 생성 — 1y/6m/3m 사전등록 spec.

    train = 향후 fitted 변환 (정규화 등) 전용. IC 측정 자체는 test 만 사용
    (OOS 규율 — train 구간 IC 는 보고하지 않음).
    """
    n = len(dates)
    start = 0
    while start + train_days + test_days <= n:
        train_idx = dates[start:start + train_days]
        test_idx = dates[start + train_days:start + train_days + test_days]
        yield train_idx, test_idx
        start += step_days


def cross_sectional_ic(scores: pd.Series, fwd_returns: pd.Series) -> Optional[float]:
    """단일 시점 횡단면 rank IC (Spearman) — score vs forward return.

    pandas .rank() = 동순위 평균 rank 처리 (scipy 무의존).
    """
    df = pd.concat([scores, fwd_returns], axis=1, keys=["s", "r"]).dropna()
    if len(df) < MIN_CROSS_SECTION:
        return None
    rs = df["s"].rank()
    rr = df["r"].rank()
    if rs.std() == 0 or rr.std() == 0:
        return None
    return float(rs.corr(rr))


def _component_summary(ics: List[float], n_components: int) -> Dict:
    """IC 시계열 → ICIR/t-stat/Bonferroni/밴드 (사전등록 합격 기준)."""
    arr = np.array([x for x in ics if x is not None and np.isfinite(x)])
    n = len(arr)
    if n < 2:
        return {"n_periods": n, "ic_mean": None, "ic_std": None, "icir": None,
                "t_stat": None, "significant_bonferroni": None, "band": "insufficient"}
    ic_mean = float(arr.mean())
    ic_std = float(arr.std(ddof=1))
    icir = ic_mean / ic_std if ic_std > 0 else None
    t_stat = ic_mean / (ic_std / math.sqrt(n)) if ic_std > 0 else None
    # Bonferroni: α=0.05 / n_components. 양측 t 임계 근사 — 사전등록 보수 기준 t>3.0 병기
    sig = bool(t_stat is not None and abs(t_stat) > 3.0)
    if icir is not None and ic_mean > 0.05 and icir > 0.3:
        band = "strong"            # 사전등록: 강한 예측력
    elif ic_mean > 0.02:
        band = "usable"            # 활용 가능 신호
    elif abs(ic_mean) <= 0.02:
        band = "dead"              # 예측력 없음 → 가중치 0 후보
    else:
        band = "inverse"           # 음의 IC — 역신호 (별도 검토)
    return {
        "n_periods": n,
        "ic_mean": round(ic_mean, 4),
        "ic_std": round(ic_std, 4),
        "icir": round(icir, 4) if icir is not None else None,
        "t_stat": round(t_stat, 4) if t_stat is not None else None,
        "bonferroni_alpha": round(0.05 / max(n_components, 1), 5),
        "significant_bonferroni": sig,
        "band": band,
    }


def _spread_portfolio_returns(
    scores: pd.DataFrame, prices: pd.DataFrame, test_dates: pd.DatetimeIndex,
) -> List[float]:
    """top-bottom quintile spread 일별 수익률 (DSR 입력용 단순 spread).

    리밸런스 = IC_SAMPLING_DAYS 주기, equal weight, 비용 미반영 (gross — caveat).
    """
    rets = prices.pct_change()
    out: List[float] = []
    sample_dates = test_dates[::IC_SAMPLING_DAYS]
    for i, d in enumerate(sample_dates[:-1]):
        if d not in scores.index:
            continue
        s = scores.loc[d].dropna()
        if len(s) < MIN_CROSS_SECTION:
            continue
        q = len(s) // 5
        if q < 1:
            continue
        top = s.nlargest(q).index
        bot = s.nsmallest(q).index
        hold_end = sample_dates[i + 1]
        period = rets.loc[(rets.index > d) & (rets.index <= hold_end)]
        if period.empty:
            continue
        daily_spread = period[top].mean(axis=1) - period[bot].mean(axis=1)
        out.extend([float(x) for x in daily_spread.dropna()])
    return out


def run_ic_backtest(
    component_scores: Dict[str, pd.DataFrame],
    prices: pd.DataFrame,
    apply_holdout: bool = True,
) -> Dict:
    """B4 Phase 1 측정 본체.

    Args:
        component_scores: {component_name: DataFrame(date × ticker score)}.
            FROZEN_COMPONENTS 외 이름 = 거부 (동결 강제).
        prices: DataFrame(date × ticker close). survivorship caveat 호출자 명시 의무.
        apply_holdout: 최종 HOLDOUT_FRACTION 절단 (default True — 개발 중 미접근 가드).

    Returns:
        {
          "freeze_date", "holdout_applied", "data_caveats",
          "windows": int,
          "components": {name: summary + dsr},
          "trial_log": TRIAL_LOG,
        }
    """
    unknown = [c for c in component_scores if c not in FROZEN_COMPONENTS]
    if unknown:
        raise ValueError(
            f"동결 외 component {unknown} — FROZEN_COMPONENTS({FORMULA_FREEZE_DATE}) 만 허용 (RULE 7)"
        )

    prices = prices.sort_index()
    dates = prices.index
    if apply_holdout:
        cutoff = int(len(dates) * (1 - HOLDOUT_FRACTION))
        dates = dates[:cutoff]
        prices = prices.loc[dates]

    fwd = prices.shift(-FORWARD_HORIZON_DAYS) / prices - 1.0

    windows = list(walk_forward_windows(dates))
    n_comp = len(component_scores)
    results: Dict[str, Dict] = {}

    for name, scores in component_scores.items():
        scores = scores.sort_index()
        ics: List[float] = []
        spread_rets: List[float] = []
        for _train_idx, test_idx in windows:
            sample = test_idx[::IC_SAMPLING_DAYS]
            for d in sample:
                if d in scores.index and d in fwd.index:
                    ic = cross_sectional_ic(scores.loc[d], fwd.loc[d])
                    if ic is not None:
                        ics.append(ic)
            spread_rets.extend(_spread_portfolio_returns(scores, prices, test_idx))

        summary = _component_summary(ics, n_comp)

        # DSR — spread 포트폴리오 Sharpe 의 다중검정 보정 (n_trials = 시도 횟수 누적)
        # 주의: Lo(2002) SE 는 관측 단위 SR 전제 — DSR 입력 = 일별 SR (T=일별 관측 수).
        # 연환산 SR 전달 시 z 과대 (거짓 유의성). 연환산은 별도 보고 필드.
        n_trials = n_comp + len(TRIAL_LOG) - 1
        if len(spread_rets) >= 30:
            arr = np.array(spread_rets)
            sd = arr.std(ddof=1)
            if sd > 0:
                sr_daily = arr.mean() / sd
                sr_annual = sr_daily * math.sqrt(252)
                summary["spread_dsr"] = compute_deflated_sharpe_ratio(
                    sr_observed=sr_daily, T=len(arr), n_trials=n_trials,
                    returns=[float(x) for x in arr],
                )
                summary["spread_sharpe_annual_gross"] = round(sr_annual, 4)
            else:
                summary["spread_dsr"] = None
        else:
            summary["spread_dsr"] = None
        results[name] = summary

    return {
        "freeze_date": FORMULA_FREEZE_DATE,
        "holdout_applied": apply_holdout,
        "holdout_fraction": HOLDOUT_FRACTION,
        "windows": len(windows),
        "config": {
            "train_days": TRAIN_DAYS, "test_days": TEST_DAYS, "step_days": STEP_DAYS,
            "forward_horizon_days": FORWARD_HORIZON_DAYS, "ic_sampling_days": IC_SAMPLING_DAYS,
        },
        "data_caveats": [
            "yfinance survivorship bias — 결과 보수 해석 의무 (사전등록 CRITICAL 가드)",
            "spread 수익률 = gross (거래비용 미반영)",
            "재무비율 component = PIT 미보장 (KR 분기 +45d embargo 는 어댑터 책임)",
            f"모든 결과 = 가설 (라이브 N 결합 전, freeze {FORMULA_FREEZE_DATE})",
        ],
        "components": results,
        "trial_log": TRIAL_LOG,
    }
