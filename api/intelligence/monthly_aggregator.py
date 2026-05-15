"""monthly_aggregator — 30일 snapshot 접어 월간 리포트용 enriched dict 산출.

generate_periodic_analysis("monthly") 의 출력은 카테고리 단위 trend 만 채움.
월간 PDF 가 일일 PDF 수준의 풍성함을 가지려면 weekly_breakdown / pnl_curve /
macro_flat / postmortem_monthly / market_horizon_monthly / top_winner-loser 카드 /
헤드라인 30d 집계가 추가로 필요. 이 모듈은 그 격차만 채운다 (renderer 정합용).

기존 aggregator 는 절대 건드리지 않음 — Phase 0 staged_updates 정합.
"""
from __future__ import annotations

import os
import json
from collections import Counter, defaultdict
from datetime import datetime, date as _date
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR


def _iso_week_label(d: str) -> str:
    """YYYY-MM-DD → 'W{ISO_week}'."""
    try:
        dt = datetime.strptime(d[:10], "%Y-%m-%d").date()
        _, wk, _ = dt.isocalendar()
        return f"W{wk}"
    except Exception:
        return "W?"


def _safe_float(v) -> Optional[float]:
    try:
        f = float(v)
        if f != f:  # NaN
            return None
        return f
    except (TypeError, ValueError):
        return None


def _avg(vals: List[float]) -> Optional[float]:
    if not vals:
        return None
    return round(sum(vals) / len(vals), 2)


def _build_weekly_breakdown(snapshots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """주차별 BUY 적중률·평균 수익률 — ISO week 그룹.

    각 스냅샷의 recommendations 중 BUY 등급을 모아 다음 스냅샷 가격으로 매주 평가.
    n>=2 일 때만 산출.
    """
    if len(snapshots) < 2:
        return []
    by_week: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"buy_count": 0, "hits": 0, "rets": []}
    )
    for i, snap in enumerate(snapshots[:-1]):
        wk = _iso_week_label(snap.get("_date") or "")
        if wk == "W?":
            continue
        recs = {r.get("ticker"): r for r in (snap.get("recommendations") or [])
                if r.get("recommendation") == "BUY" and r.get("price")}
        if not recs:
            continue
        # 다음 스냅샷에서 종가 평가
        nxt = snapshots[i + 1]
        nxt_recs = {r.get("ticker"): r for r in (nxt.get("recommendations") or [])
                    if r.get("price")}
        for tk, orig in recs.items():
            cur = nxt_recs.get(tk)
            if not cur:
                continue
            o_p = _safe_float(orig.get("price"))
            c_p = _safe_float(cur.get("price"))
            if not o_p or not c_p:
                continue
            ret = round((c_p - o_p) / o_p * 100, 2)
            row = by_week[wk]
            row["buy_count"] += 1
            row["rets"].append(ret)
            if ret > 0:
                row["hits"] += 1
    out: List[Dict[str, Any]] = []
    for wk in sorted(by_week.keys()):
        row = by_week[wk]
        cnt = row["buy_count"]
        hits = row["hits"]
        avg_ret = _avg(row["rets"]) or 0
        hit_rate = round(hits / cnt * 100, 1) if cnt else 0
        out.append({
            "label": wk,
            "buy_count": cnt,
            "hit_rate": hit_rate,
            "avg_return": avg_ret,
        })
    return out


def _build_pnl_curve(snapshots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """일별 total_asset 곡선 — 풀 30일."""
    curve = []
    for snap in snapshots:
        ta = _safe_float((snap.get("vams") or {}).get("total_asset"))
        if ta is not None:
            curve.append({"date": snap.get("_date", ""), "value": ta})
    return curve


def _compute_mdd_pct(curve: List[Dict[str, Any]]) -> float:
    """running peak 대비 최대 drawdown — 양수 magnitude (feedback_mdd_magnitude_display)."""
    if len(curve) < 2:
        return 0.0
    peak = curve[0]["value"]
    mdd = 0.0
    for p in curve:
        v = p.get("value") or 0
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak * 100
            if dd > mdd:
                mdd = dd
    return round(mdd, 2)


def _flatten_macro(snapshots: List[Dict[str, Any]],
                   trends: Dict[str, Any]) -> Dict[str, Any]:
    """renderer 가 읽기 쉬운 flat key 로 매크로 압축.

    vix_avg / usd_krw_avg / sp500_monthly_pct / kospi_monthly_pct / events_review.
    """
    flat: Dict[str, Any] = {}
    inds = (trends.get("indicators") or {}) if isinstance(trends, dict) else {}
    if "vix" in inds:
        flat["vix_avg"] = inds["vix"].get("avg")
        flat["vix_start"] = inds["vix"].get("start")
        flat["vix_end"] = inds["vix"].get("end")
    if "usd_krw" in inds:
        flat["usd_krw_avg"] = inds["usd_krw"].get("avg")
        flat["usd_krw_end"] = inds["usd_krw"].get("end")

    # SP500 / KOSPI 월간 % — snapshot 의 macro.sp500.value 첫/마지막
    sp_vals = [_safe_float((s.get("macro") or {}).get("sp500", {}).get("value"))
               for s in snapshots]
    sp_vals = [v for v in sp_vals if v]
    if len(sp_vals) >= 2 and sp_vals[0]:
        flat["sp500_monthly_pct"] = round((sp_vals[-1] - sp_vals[0]) / sp_vals[0] * 100, 2)
    else:
        flat["sp500_monthly_pct"] = 0
    kospi_vals = [_safe_float((s.get("market_summary") or {}).get("kospi_index"))
                  for s in snapshots]
    kospi_vals = [v for v in kospi_vals if v]
    if len(kospi_vals) >= 2 and kospi_vals[0]:
        flat["kospi_monthly_pct"] = round((kospi_vals[-1] - kospi_vals[0]) / kospi_vals[0] * 100, 2)
    else:
        flat["kospi_monthly_pct"] = 0

    # 30 일 내 global_events 결산 — surprised/missed
    events_review: List[Dict[str, Any]] = []
    seen = set()
    for snap in snapshots:
        for ev in (snap.get("global_events") or [])[:3]:
            key = (ev.get("name"), ev.get("date"))
            if key in seen or not ev.get("name"):
                continue
            seen.add(key)
            events_review.append({
                "name": ev.get("name"),
                "date": ev.get("date"),
                "consensus": ev.get("consensus") or "-",
                "actual": ev.get("actual") or "-",
                "scenario_match": ev.get("scenario_match") or "-",
            })
            if len(events_review) >= 8:
                break
        if len(events_review) >= 8:
            break
    flat["events_review"] = events_review
    return flat


def _build_top_blocks(perf: Dict[str, Any],
                      snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
    """top winner/loser 5건씩 — 마지막 snapshot rec 매칭으로 mini block 데이터 확장."""
    last = snapshots[-1] if snapshots else {}
    by_ticker = {r.get("ticker"): r for r in (last.get("recommendations") or [])}

    def _enrich(pick: Dict[str, Any]) -> Dict[str, Any]:
        full = by_ticker.get(pick.get("ticker")) or {}
        merged = dict(full)
        merged.update({
            "ticker": pick.get("ticker"),
            "name": pick.get("name") or full.get("name") or "?",
            "buy_price": pick.get("buy_price"),
            "current_price": pick.get("current_price") or full.get("price"),
            "return_pct": pick.get("return_pct"),
            "orig_brain_score": pick.get("orig_brain_score"),
            "orig_multi_score": pick.get("orig_multi_score"),
        })
        return merged

    winners = [_enrich(p) for p in (perf.get("best_picks") or [])[:5]]
    losers = [_enrich(p) for p in (perf.get("worst_picks") or [])[:5]]
    return {"winners": winners, "losers": losers}


def _holdings_monthly_perf(snapshots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """월초 vs 월말 보유 종목 시가 — VAMS holdings 추적."""
    if len(snapshots) < 2:
        return []
    first = (snapshots[0].get("vams") or {}).get("holdings") or []
    last = (snapshots[-1].get("vams") or {}).get("holdings") or []
    last_by = {h.get("ticker"): h for h in last if h.get("ticker")}
    rows = []
    for h0 in first:
        tk = h0.get("ticker")
        if not tk:
            continue
        h1 = last_by.get(tk) or {}
        p0 = _safe_float(h0.get("current_price") or h0.get("avg_price"))
        p1 = _safe_float(h1.get("current_price")) or p0
        if not p0:
            continue
        ret = round((p1 - p0) / p0 * 100, 2) if p1 else 0
        rows.append({
            "ticker": tk,
            "name": h0.get("name") or h1.get("name") or "?",
            "start_price": p0,
            "end_price": p1,
            "return_pct": ret,
            "still_held": tk in last_by,
        })
    rows.sort(key=lambda r: r["return_pct"], reverse=True)
    return rows


def _postmortem_monthly(snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
    """30일 postmortem 결과 합산 — analyzed_count 합, top misleading factor 빈도."""
    total_analyzed = 0
    summaries: List[str] = []
    lessons: List[str] = []
    suggestions: List[str] = []
    mis_counter: Counter = Counter()
    snap_count_with_pm = 0
    for snap in snapshots:
        pm = snap.get("postmortem") or {}
        if not pm or pm.get("status") not in ("ok", "no_failures"):
            continue
        snap_count_with_pm += 1
        total_analyzed += int(pm.get("analyzed_count") or 0)
        if pm.get("summary"):
            summaries.append(str(pm["summary"]))
        if pm.get("lesson"):
            lessons.append(str(pm["lesson"]))
        if pm.get("system_suggestion"):
            suggestions.append(str(pm["system_suggestion"]))
        mis = pm.get("misleading_factors") or {}
        if isinstance(mis, dict):
            for k in mis:
                mis_counter[k] += 1
    top_mis = mis_counter.most_common(5)
    return {
        "snapshot_count_with_pm": snap_count_with_pm,
        "total_analyzed": total_analyzed,
        "summaries_sample": summaries[:3],
        "lessons_sample": lessons[:3],
        "suggestions_sample": suggestions[:3],
        "top_misleading_factors": [{"factor": f, "count": c} for f, c in top_mis],
    }


def _market_horizon_monthly(snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
    """market_horizon verdict 30d 분포 + 현 verdict."""
    verdicts: Counter = Counter()
    cycle_stages: Counter = Counter()
    latest_full = {}
    for snap in snapshots:
        mh = snap.get("market_horizon") or {}
        v = mh.get("verdict") or mh.get("regime")
        if v:
            verdicts[str(v)] += 1
        cs = mh.get("cycle_stage")
        if cs:
            cycle_stages[str(cs)] += 1
        latest_full = mh
    return {
        "verdict_distribution": dict(verdicts),
        "cycle_stage_distribution": dict(cycle_stages),
        "current_verdict": latest_full.get("verdict") or "-",
        "current_cycle_stage": latest_full.get("cycle_stage") or "-",
        "available": bool(verdicts),
    }


def _headlines_monthly(snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
    """헤드라인 30d 카테고리 분포 + top items by source."""
    by_cat: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    seen_titles = set()
    for snap in snapshots[-7:]:  # 최근 1주만 — 30 일 전체는 너무 많음
        hl = snap.get("headlines") or {}
        if isinstance(hl, dict):
            for cat, items in hl.items():
                if not isinstance(items, list):
                    continue
                for h in items[:5]:
                    t = (h.get("title") or "").strip()
                    if not t or t in seen_titles:
                        continue
                    seen_titles.add(t)
                    by_cat[str(cat)].append({
                        "title": t[:200],
                        "source": h.get("source") or "-",
                        "ts": h.get("ts_kst") or h.get("published") or "",
                    })
    return {k: v[:5] for k, v in by_cat.items()}


def _factor_ic_monthly(snapshots: List[Dict[str, Any]],
                       latest_portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """factor_ic monthly_rollup 우선, 없으면 last snapshot factor_ic 사용."""
    fic_now = latest_portfolio.get("factor_ic") or {}
    if fic_now.get("monthly_rollup") or fic_now.get("ranking"):
        return fic_now
    # 백업: 마지막 snapshot 의 factor_ic
    for snap in reversed(snapshots):
        fic = snap.get("factor_ic") or {}
        if fic.get("monthly_rollup") or fic.get("ranking"):
            return fic
    return {}


def _briefing_monthly(analysis: Dict[str, Any],
                      portfolio: Dict[str, Any],
                      flat_macro: Dict[str, Any]) -> Dict[str, Any]:
    """월간 30초 브리핑 3줄 + 다음 달 액션 3개 — 데이터 기반 자동 생성."""
    recs = analysis.get("recommendations", {}) or {}
    port = analysis.get("portfolio", {}) or {}
    hit_rate = recs.get("hit_rate_pct") or 0
    avg_ret = recs.get("avg_return_pct") or 0
    cum = port.get("period_return_pct") or 0
    mdd = port.get("max_drawdown_pct") or 0
    vams = portfolio.get("vams") or {}
    cash = _safe_float(vams.get("cash")) or 0
    total = _safe_float(vams.get("total_asset")) or 0
    cash_pct = round(cash / total * 100, 1) if total else 0

    macro_line = (
        f"VIX 평균 {flat_macro.get('vix_avg', '-')} / "
        f"USD/KRW {flat_macro.get('usd_krw_avg', '-')}원 / "
        f"S&P500 {flat_macro.get('sp500_monthly_pct', 0):+.2f}% · "
        f"KOSPI {flat_macro.get('kospi_monthly_pct', 0):+.2f}%"
    )
    perf_line = (
        f"BUY {recs.get('total_buy_recs', 0)}건 · 적중 {hit_rate}% · "
        f"평균 {avg_ret:+.2f}% · VAMS {cum:+.2f}% (MDD {mdd:.2f}%)"
    )
    if hit_rate >= 55:
        verdict_line = "시스템 정상 작동 — 다음 달 동일 패턴 유지 권장"
    elif hit_rate < 40 and (recs.get("total_buy_recs") or 0) > 5:
        verdict_line = "적중률 부진 — 파라미터·매크로 필터 재검토 트리거"
    else:
        verdict_line = "혼조 — 부분 검토 영역 (섹터·종목 IC 점검)"

    actions = [
        f"현금 비중 {cash_pct}% · 목표 vs 실측 차이 점검",
        f"이달 worst {len(recs.get('worst_picks') or [])}건 회귀 학습 (postmortem 큐)",
        "다음 달 매크로 이벤트 D-7 캘린더 사전 등록",
    ]
    return {
        "macro_line": macro_line,
        "perf_line": perf_line,
        "verdict_line": verdict_line,
        "action_items": actions,
    }


def enrich_monthly_analysis(analysis: Dict[str, Any],
                            portfolio: Dict[str, Any],
                            snapshots: Optional[List[Dict[str, Any]]] = None,
                            ) -> Dict[str, Any]:
    """generate_periodic_analysis('monthly') 결과를 PDF 직접 소비 가능한 형태로 enrich.

    Args:
        analysis: periodic_report.generate_periodic_analysis('monthly') 결과
        portfolio: 최신 portfolio.json (daily 와 동일 source)
        snapshots: 사전 로드된 30일 snapshot (옵션). 없으면 archiver 에서 로드.

    Returns:
        analysis (변경된 dict — 원본 destructive update). Renderer 가 쓰는 key:
          recommendations.weekly_breakdown
          recommendations.top_winner / top_loser
          portfolio.pnl_curve / mdd_pct (양수 magnitude)
          macro_flat (flat key 묶음)
          factor_ic_monthly
          market_horizon_monthly
          postmortem_monthly
          headlines_monthly
          holdings_monthly
          briefing_monthly
          top_blocks {winners, losers}
    """
    if snapshots is None:
        try:
            from api.workflows.archiver import load_snapshots_range
            snapshots = load_snapshots_range(30) or []
        except Exception:
            snapshots = []

    recs = analysis.setdefault("recommendations", {})
    port = analysis.setdefault("portfolio", {})

    # 1. weekly_breakdown
    recs["weekly_breakdown"] = _build_weekly_breakdown(snapshots)

    # 2. top_winner / top_loser (분해 field, cover KPI 용)
    best = recs.get("best_picks") or []
    worst = recs.get("worst_picks") or []
    if best:
        recs["top_winner"] = {"name": best[0].get("name"), "ticker": best[0].get("ticker"),
                              "return_pct": best[0].get("return_pct")}
    if worst:
        recs["top_loser"] = {"name": worst[-1].get("name"), "ticker": worst[-1].get("ticker"),
                              "return_pct": worst[-1].get("return_pct")}

    # 3. pnl_curve + mdd (snapshot 기반, asset_history 보강)
    curve = _build_pnl_curve(snapshots)
    if curve:
        port["pnl_curve"] = curve
        port["mdd_pct"] = _compute_mdd_pct(curve)
        port["cum_return_pct"] = port.get("period_return_pct") or 0

    # 4. macro_flat (renderer 직접 read)
    analysis["macro_flat"] = _flatten_macro(snapshots, analysis.get("macro") or {})

    # 5. top blocks (mini block 데이터 — 마지막 snapshot rec 매칭)
    analysis["top_blocks"] = _build_top_blocks(recs, snapshots)

    # 6. holdings monthly perf
    analysis["holdings_monthly"] = _holdings_monthly_perf(snapshots)

    # 7. postmortem 월간 합산
    analysis["postmortem_monthly"] = _postmortem_monthly(snapshots)

    # 8. market_horizon 월간
    analysis["market_horizon_monthly"] = _market_horizon_monthly(snapshots)

    # 9. 헤드라인 카테고리 분포
    analysis["headlines_monthly"] = _headlines_monthly(snapshots)

    # 10. factor IC monthly — portfolio.factor_ic 우선, snapshot fallback
    analysis["factor_ic_monthly"] = _factor_ic_monthly(snapshots, portfolio)

    # 11. snapshot 카운트 보강
    analysis["snapshot_count"] = len(snapshots)

    # 12. 월간 브리핑 3줄 (cover 용)
    analysis["briefing_monthly"] = _briefing_monthly(analysis, portfolio,
                                                      analysis["macro_flat"])

    return analysis
