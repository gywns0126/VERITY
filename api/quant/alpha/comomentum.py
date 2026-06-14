"""
comomentum.py — CoMOM(comomentum) 팩터 crowding 지표 코어. Lou & Polk (2022, RFS) 정밀 구현.

2026-06-14 신설. 사전등록: docs/crowding_observation_spec_v0_2026_06_14.md → v1(조합식).
학술: Lou, D. & Polk, C. (2022) "Comomentum: Inferring Arbitrage Activity from Return
Correlations", Review of Financial Studies 35(7):3272-3302.

🚨 관측/측정 only — 점수/결정 wire 0 (RULE 7). CoMOM = 팩터 extreme decile 내 종목들의
FF3-residual 수익률 *상호상관*. 높을수록 동일 팩터에 차익거래(기관) 자본 집중 = crowding.
Lou-Polk: 높은 CoMOM → 이후 1~2년 팩터수익 *하락*(단기엔 오히려 +). = forward IC decay 선행지표.

산식 (Lou-Polk eq. 3):
  CoMOM^D = (1/N_D) Σ_i corr(r̃_i, r̃_{-i})          # decile D 내 종목 i vs 나머지 평균
  CoMOM   = 0.5 × (CoMOM^Winner + CoMOM^Loser)
  r̃ = FF3 잔차 (주간 초과수익을 Mkt-RF/SMB/HML 로 회귀한 잔차). 윈도 = 52주.

🚨 v1 단순화(주석 명시): 산업조정(FF30) + Lewellen-Nagel rolling beta 는 v1.1 정밀화 후보.
본 v1 = 전-윈도 FF3 beta (Perplexity robustness: 단순화 허용). [[project_academic_grounding_2026_06_13]].
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

WINDOW_WEEKS = 52       # Lou-Polk §2.3 상관 윈도
MIN_OVERLAP = 30        # 잔차 회귀/상관 최소 중첩 주수
MIN_DECILE_N = 3        # decile 내 최소 종목 (corr 의미 확보)


def ff3_residual(
    stock_weekly_ret: pd.Series, ff3: pd.DataFrame, min_obs: int = MIN_OVERLAP,
) -> Optional[pd.Series]:
    """종목 주간수익률을 FF3 로 잔차화. excess = ret - RF 를 [1, Mkt-RF, SMB, HML] 회귀, 잔차 반환.

    날짜 inner-join 후 유효 중첩 < min_obs 면 None. (Lou-Polk: 산업조정 선행은 v1.1.)
    """
    if stock_weekly_ret is None or stock_weekly_ret.empty:
        return None
    df = pd.concat([stock_weekly_ret.rename("ret"), ff3], axis=1, join="inner").dropna()
    if len(df) < min_obs:
        return None
    excess = (df["ret"] - df["rf"]).to_numpy(dtype=float)
    X = np.column_stack([np.ones(len(df)), df["mkt_rf"], df["smb"], df["hml"]]).astype(float)
    try:
        beta, *_ = np.linalg.lstsq(X, excess, rcond=None)
    except np.linalg.LinAlgError:
        return None
    resid = excess - X @ beta
    return pd.Series(resid, index=df.index)


def _decile_comomentum(residuals: Dict[str, pd.Series]) -> Optional[float]:
    """decile 내 각 종목 i: corr(r̃_i, mean(r̃_{-i})). 평균 반환 (Lou-Polk eq.3 leg).

    종목 < MIN_DECILE_N 또는 유효 corr 0 → None.
    """
    valid = {t: s for t, s in residuals.items() if s is not None and not s.empty}
    if len(valid) < MIN_DECILE_N:
        return None
    mat = pd.DataFrame(valid)  # date × ticker, 자동 outer-align (NaN)
    corrs: List[float] = []
    for t in valid:
        others = mat.drop(columns=[t]).mean(axis=1, skipna=True)  # 나머지 평균 (r̃_{-i})
        pair = pd.concat([mat[t].rename("i"), others.rename("rest")], axis=1).dropna()
        if len(pair) < MIN_OVERLAP:
            continue
        if pair["i"].std() == 0 or pair["rest"].std() == 0:
            continue
        c = pair["i"].corr(pair["rest"])
        if c is not None and np.isfinite(c):
            corrs.append(float(c))
    if not corrs:
        return None
    return round(float(np.mean(corrs)), 4)


def compute_comom(
    weekly_returns: Dict[str, pd.Series],
    factor_deciles: Dict[str, Dict[str, List[str]]],
    ff3: pd.DataFrame,
    window: int = WINDOW_WEEKS,
) -> Dict[str, Any]:
    """팩터별 CoMOM 계산.

    weekly_returns: {ticker: 주간수익률 Series(date-indexed)} — 최근 window 주만 사용.
    factor_deciles: {factor: {"top": [tickers], "bottom": [tickers]}} — extreme decile 멤버.
    ff3: fetch_ff3_weekly() 결과.
    반환: {factor: {comom, comom_winner, comom_loser, n_winner, n_loser}} (계산불가 = None 필드).
    """
    # 최근 window 주로 잔차 1회 산출 후 재사용 (모든 decile 공유)
    resid_cache: Dict[str, Optional[pd.Series]] = {}

    def _resid(t: str) -> Optional[pd.Series]:
        if t not in resid_cache:
            s = weekly_returns.get(t)
            if s is not None and len(s) > window:
                s = s.iloc[-window:]
            resid_cache[t] = ff3_residual(s, ff3) if s is not None else None
        return resid_cache[t]

    out: Dict[str, Any] = {}
    for factor, legs in (factor_deciles or {}).items():
        top = [t for t in (legs.get("top") or []) if t]
        bot = [t for t in (legs.get("bottom") or []) if t]
        win_res = {t: _resid(t) for t in top}
        los_res = {t: _resid(t) for t in bot}
        cm_w = _decile_comomentum(win_res)
        cm_l = _decile_comomentum(los_res)
        legs_valid = [c for c in (cm_w, cm_l) if c is not None]
        comom = round(float(np.mean(legs_valid)), 4) if legs_valid else None
        out[factor] = {
            "comom": comom,
            "comom_winner": cm_w,
            "comom_loser": cm_l,
            "n_winner": sum(1 for s in win_res.values() if s is not None),
            "n_loser": sum(1 for s in los_res.values() if s is not None),
        }
    return out
