"""
매크로(특히 FRED DGS10)에 따른 멀티팩터 펀더멘털 감점 등.
"""
import os
from typing import Any, Dict


def fundamental_penalty_from_macro(macro: Dict[str, Any]) -> int:
    """
    미 10년물 급등 구간에서 펀더멘털 점수(merge_fundamental_with_consensus 입력) 감점.
    FRED change_5d_pp 우선, 없으면 yfinance us_10y.change_pct(일) 임계.
    """
    pen = int(os.environ.get("MACRO_FUNDAMENTAL_PENALTY_SURGE", "15"))
    fred = macro.get("fred") or {}
    d = fred.get("dgs10") or {}
    ch = d.get("change_5d_pp")
    if ch is not None:
        thr_pp = float(os.environ.get("MACRO_DGS10_SURGE_PP", "0.12"))
        if float(ch) >= thr_pp:
            return pen
        return 0
    u = macro.get("us_10y") or {}
    chg = float(u.get("change_pct") or 0)
    thr_pct = float(os.environ.get("MACRO_DGS10_SURGE_YF_PCT", "3"))
    if chg >= thr_pct:
        return pen
    return 0
