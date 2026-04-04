"""
컨센서스 원시 데이터 → 기관 심리 점수(0~100) 및 실물(수출) 괴리 경고.
컨센서스 없을 때는 수급(flow) 점수를 대체값으로 사용(표시 분리).
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from api.config import TRADE_ANALYSIS_PATH


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _norm_upside_pct(pct: Optional[float]) -> float:
    """상승여력(%)을 0~100 스케일로 선형 매핑 (-30%→0, +30%→100)."""
    if pct is None:
        return 50.0
    return _clip((pct + 30.0) / 60.0 * 100.0, 0.0, 100.0)


def _norm_op_growth_pct(pct: Optional[float]) -> float:
    """영업이익 전년비 추정 증가율을 0~100으로 (-20%→0, +40%→100)."""
    if pct is None:
        return 50.0
    return _clip((pct + 20.0) / 60.0 * 100.0, 0.0, 100.0)


def _has_consensus_data(raw: Dict[str, Any]) -> bool:
    if raw.get("error"):
        return False
    tp = raw.get("target_price")
    if tp is not None and tp > 0:
        return True
    if (
        raw.get("operating_profit_estimate_bn") is not None
        and raw.get("operating_profit_prior_year_bn") is not None
    ):
        return True
    if raw.get("sales_estimate_bn") is not None:
        return True
    op = raw.get("investment_opinion")
    return bool(op and op != "N/A")


def compute_operating_profit_yoy_pct(raw: Dict[str, Any]) -> Optional[float]:
    prev = raw.get("operating_profit_prior_year_bn")
    est = raw.get("operating_profit_estimate_bn")
    if prev is None or est is None:
        return None
    try:
        p = float(prev)
        e = float(est)
    except (TypeError, ValueError):
        return None
    if p == 0:
        return None
    return round((e - p) / abs(p) * 100.0, 2)


def build_consensus_block(
    raw: Dict[str, Any],
    current_price: float,
    flow: Dict[str, Any],
    export_row: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    종목별 consensus 블록. multi_factor에 넘길 consensus_score 포함.
    """
    warnings: List[str] = []
    op_yoy = compute_operating_profit_yoy_pct(raw)

    upside_pct: Optional[float] = None
    tp = raw.get("target_price")
    if tp and current_price and current_price > 0:
        upside_pct = round((float(tp) - float(current_price)) / float(current_price) * 100.0, 2)

    flow_score = int(flow.get("flow_score", 50) or 50)

    if not _has_consensus_data(raw):
        block = {
            "consensus_available": False,
            "score_source": "flow_fallback",
            "consensus_score": flow_score,
            "investment_opinion": raw.get("investment_opinion", "N/A"),
            "investment_opinion_numeric": raw.get("investment_opinion_numeric"),
            "target_price": None,
            "upside_pct": None,
            "sales_prior_year_bn": raw.get("sales_prior_year_bn"),
            "sales_estimate_bn": raw.get("sales_estimate_bn"),
            "operating_profit_prior_year_bn": raw.get("operating_profit_prior_year_bn"),
            "operating_profit_estimate_bn": raw.get("operating_profit_estimate_bn"),
            "operating_profit_yoy_est_pct": op_yoy,
            "estimate_year_label": raw.get("estimate_year_label"),
            "flow_fallback_note": "컨센서스 없음 — 외국인·기관 수급 점수로 대체",
            "warnings": warnings,
        }
        _attach_export_divergence(block, upside_pct, op_yoy, export_row, warnings)
        return block

    u_n = _norm_upside_pct(upside_pct)
    g_n = _norm_op_growth_pct(op_yoy)
    blended = u_n * 0.4 + g_n * 0.6
    consensus_score = int(round(_clip(blended, 0.0, 100.0)))

    if upside_pct is not None and upside_pct < 0:
        consensus_score = int(round(_clip(consensus_score * 0.5, 0.0, 100.0)))
        warnings.append("목표가가 현재가 아래(하향 여력) — 컨센서스 보수적 해석 권고")

    block = {
        "consensus_available": True,
        "score_source": "consensus",
        "consensus_score": consensus_score,
        "investment_opinion": raw.get("investment_opinion", "N/A"),
        "investment_opinion_numeric": raw.get("investment_opinion_numeric"),
        "target_price": tp if tp else None,
        "upside_pct": upside_pct,
        "sales_prior_year_bn": raw.get("sales_prior_year_bn"),
        "sales_estimate_bn": raw.get("sales_estimate_bn"),
        "operating_profit_prior_year_bn": raw.get("operating_profit_prior_year_bn"),
        "operating_profit_estimate_bn": raw.get("operating_profit_estimate_bn"),
        "operating_profit_yoy_est_pct": op_yoy,
        "estimate_year_label": raw.get("estimate_year_label"),
        "flow_fallback_note": None,
        "warnings": warnings,
    }
    _attach_export_divergence(block, upside_pct, op_yoy, export_row, warnings)
    return block


def _attach_export_divergence(
    block: Dict[str, Any],
    upside_pct: Optional[float],
    op_yoy: Optional[float],
    export_row: Optional[Dict[str, Any]],
    warnings: List[str],
) -> None:
    """관세청 수출 추이가 약한데 컨센서스만 밝을 때 경고."""
    if not export_row:
        return
    mom = export_row.get("mom_export_pct")
    yoy = export_row.get("yoy_export_pct")
    if mom is None and yoy is None:
        return
    try:
        mom_f = float(mom) if mom is not None else None
        yoy_f = float(yoy) if yoy is not None else None
    except (TypeError, ValueError):
        return

    optimistic_consensus = False
    if upside_pct is not None and upside_pct >= 15.0:
        optimistic_consensus = True
    if op_yoy is not None and op_yoy >= 15.0:
        optimistic_consensus = True

    weak_export = False
    if mom_f is not None and mom_f <= -5.0:
        weak_export = True
    if yoy_f is not None and yoy_f <= -5.0:
        weak_export = True

    if optimistic_consensus and weak_export:
        name = export_row.get("name", "")
        warnings.append(
            f"기관 낙관 주의: 컨센서스 상향인데 관세청 수출 추이는 약화"
            f"({name or '해당종목'} MoM {mom_f if mom_f is not None else 'n/a'}% "
            f"/ YoY {yoy_f if yoy_f is not None else 'n/a'}%) — 실물과 전망 괴리 확인"
        )


def load_trade_export_by_ticker() -> Dict[str, Dict[str, Any]]:
    """trade_analysis.json에서 ticker → 수출 메타."""
    if not os.path.isfile(TRADE_ANALYSIS_PATH):
        return {}
    try:
        with open(TRADE_ANALYSIS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for row in data.get("stocks", []):
        t = row.get("ticker")
        if t:
            out[str(t).zfill(6)] = row
    return out


def merge_fundamental_with_consensus(fundamental_score: int, consensus_block: Dict[str, Any]) -> int:
    """펀더멘털에 컨센서스(또는 수급 대체)를 소폭 반영."""
    cs = consensus_block.get("consensus_score")
    if cs is None:
        return fundamental_score
    try:
        c = int(cs)
    except (TypeError, ValueError):
        return fundamental_score
    return int(round(_clip(0.82 * fundamental_score + 0.18 * c, 0, 100)))
