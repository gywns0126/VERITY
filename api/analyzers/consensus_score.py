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


def _attach_analyst_report_meta(
    block: Dict[str, Any],
    analyst_data: Optional[Dict[str, Any]],
    warnings: List[str],
) -> Optional[float]:
    """analyst_report_data (report_summarizer 의 종목별 집계) 메타를 block 에 부착.

    Returns: analyst_sentiment_score (0-100, blending 용) 또는 None.
    경고 추가:
      - 목표가 분산도(std/mean) > 0.15 → 의견 불일치 심화
      - revision_ratio < 0.3 → 실적 추정 하향 추세
    """
    if not analyst_data:
        return None

    sent = analyst_data.get("analyst_sentiment_score")
    avg_tp = analyst_data.get("avg_target_price")
    disp = analyst_data.get("target_price_dispersion")
    opin_dist = analyst_data.get("opinion_distribution") or {}
    rev_ratio = analyst_data.get("revision_ratio")
    report_count = analyst_data.get("report_count", 0)

    block["analyst_sentiment_score"] = sent
    block["avg_analyst_target_price"] = avg_tp
    block["target_price_dispersion"] = disp
    block["opinion_distribution"] = opin_dist
    block["analyst_report_count"] = report_count

    # 경고 1: 목표가 분산도 (CV > 15%) — 의견 불일치
    try:
        if (avg_tp and disp and float(avg_tp) > 0
                and float(disp) / float(avg_tp) > 0.15):
            warnings.append(
                f"증권사 간 목표가 의견 불일치 심화 (분산 {int(float(disp)):,}원, "
                f"평균 {int(float(avg_tp)):,}원, CV {float(disp)/float(avg_tp)*100:.0f}%)"
            )
    except (TypeError, ValueError, ZeroDivisionError):
        pass

    # 경고 2: revision_ratio < 0.3 (상향/(상향+하향))
    try:
        if rev_ratio is not None and float(rev_ratio) < 0.3:
            warnings.append(
                f"최근 증권사 실적 추정치 하향 추세 (상향 비율 {float(rev_ratio)*100:.0f}%)"
            )
    except (TypeError, ValueError):
        pass

    # 블렌딩용 sentiment 반환 (숫자만)
    try:
        return float(sent) if sent is not None else None
    except (TypeError, ValueError):
        return None


def build_consensus_block(
    raw: Dict[str, Any],
    current_price: float,
    flow: Dict[str, Any],
    export_row: Optional[Dict[str, Any]] = None,
    analyst_report_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    종목별 consensus 블록. multi_factor 에 넘길 consensus_score 포함.

    Phase 3 wiring: analyst_report_data (report_summarizer 종목별 집계)
    제공 시 analyst_sentiment_score 를 30% 가중치로 블렌딩.
    """
    warnings: List[str] = []
    op_yoy = compute_operating_profit_yoy_pct(raw)

    # ── §20: target_price 우선순위 — analyst 다중 의견(n≥3) > 단일 컨센서스 ──
    # 다증권사 평균은 단일 추정치보다 일관적으로 정확 (분산도 ↓, 중심경향성 ↑).
    # 단 n=1~2 면 단일 컨센서스보다 신뢰 낮을 수 있어 임계 3 적용.
    single_tp = raw.get("target_price")
    analyst_avg_tp = None
    analyst_count = 0
    if analyst_report_data:
        analyst_avg_tp = analyst_report_data.get("avg_target_price")
        try:
            analyst_count = int(analyst_report_data.get("report_count", 0) or 0)
        except (TypeError, ValueError):
            analyst_count = 0

    if analyst_avg_tp and analyst_count >= 3:
        tp = analyst_avg_tp
        target_price_source = f"analyst_avg_n={analyst_count}"
    else:
        tp = single_tp
        target_price_source = "single_consensus"

    upside_pct: Optional[float] = None
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
            # §20: analyst 만 있어도 effective target/upside 표시 (audit 가치)
            "target_price": tp if tp else None,
            "single_consensus_target_price": single_tp,
            "target_price_source": target_price_source if tp else None,
            "upside_pct": upside_pct,
            "sales_prior_year_bn": raw.get("sales_prior_year_bn"),
            "sales_estimate_bn": raw.get("sales_estimate_bn"),
            "operating_profit_prior_year_bn": raw.get("operating_profit_prior_year_bn"),
            "operating_profit_estimate_bn": raw.get("operating_profit_estimate_bn"),
            "operating_profit_yoy_est_pct": op_yoy,
            "estimate_year_label": raw.get("estimate_year_label"),
            "flow_fallback_note": "컨센서스 없음 — 외국인·기관 수급 점수로 대체",
            "warnings": warnings,
        }
        # analyst 메타는 항상 부착 (consensus 미가용시에도 audit 가치)
        _attach_analyst_report_meta(block, analyst_report_data, warnings)
        _attach_export_divergence(block, upside_pct, op_yoy, export_row, warnings)
        return block

    u_n = _norm_upside_pct(upside_pct)
    g_n = _norm_op_growth_pct(op_yoy)

    # ── §18: consensus_score 의미 분리 audit ──
    # 변경 전: analyst_sentiment 가 30% 블렌딩 → consensus_score 가
    #          '정량(목표가+영업이익) + AI 정성' 혼합 → 의미 오염, 디버깅 어려움.
    # 변경 후: consensus_score 는 정량만 (upside + 영업이익 YoY).
    #          analyst sentiment 는 verity_brain.fact_score.analyst_report 컴포넌트
    #          (가중 0.08) 에서만 반영 — 단일 경로, 의미 명확.
    # analyst 메타 (sentiment/target/dispersion/opinion_dist/warnings) 는 그대로 부착.
    block_for_meta: Dict[str, Any] = {}
    _attach_analyst_report_meta(block_for_meta, analyst_report_data, warnings)

    blended = u_n * 0.4 + g_n * 0.6
    score_source = "consensus"
    consensus_score = int(round(_clip(blended, 0.0, 100.0)))

    if upside_pct is not None and upside_pct < 0:
        consensus_score = int(round(_clip(consensus_score * 0.5, 0.0, 100.0)))
        warnings.append("목표가가 현재가 아래(하향 여력) — 컨센서스 보수적 해석 권고")

    block = {
        "consensus_available": True,
        "score_source": score_source,
        "consensus_score": consensus_score,
        "investment_opinion": raw.get("investment_opinion", "N/A"),
        "investment_opinion_numeric": raw.get("investment_opinion_numeric"),
        # §20: target_price 가 analyst_avg 또는 single_consensus 중 선택된 effective 값
        "target_price": tp if tp else None,
        "single_consensus_target_price": single_tp,
        "target_price_source": target_price_source if tp else None,
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
    # analyst 메타 키 4개 + sentiment_score 를 block 에 합치기
    block.update(block_for_meta)
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
