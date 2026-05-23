"""
VERITY — 정기 리포트 생성 엔진

주간(7일) / 월간(30일) / 분기(90일) / 반기(180일) / 연간(365일)
누적 스냅샷을 분석하여 성과 복기 + 메타 분석 데이터 생성.
Gemini는 이 데이터를 받아 자연어 리포트를 작성함.
"""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from typing import Any

from api.workflows.archiver import load_snapshots_range
from api.config import now_kst
from api.intelligence.tail_risk_digest import load_black_swan_ledger


PERIOD_DAYS = {
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
    "quarterly": 90,
    "semi": 180,
    "annual": 365,
}


def _safe_avg(nums: list) -> float:
    return round(statistics.mean(nums), 1) if nums else 0


def _safe_stdev(nums: list) -> float:
    return round(statistics.stdev(nums), 2) if len(nums) >= 2 else 0


# ── 섹터 동향 분석 ─────────────────────────────────────
def _analyze_sector_trends(snapshots: list[dict]) -> dict:
    """기간 내 섹터별 평균 등락률, TOP/BOTTOM 섹터, 자금 흐름 방향."""
    sector_changes: dict[str, list] = defaultdict(list)

    for snap in snapshots:
        for s in snap.get("sectors", []):
            name = s.get("name", "?")
            pct = s.get("change_pct")
            if pct is not None:
                sector_changes[name].append(pct)

    sector_avg = {
        name: round(statistics.mean(vals), 2)
        for name, vals in sector_changes.items()
        if vals
    }

    sorted_sectors = sorted(sector_avg.items(), key=lambda x: x[1], reverse=True)

    top3 = [{"name": n, "avg_change_pct": v} for n, v in sorted_sectors[:3]]
    bottom3 = [{"name": n, "avg_change_pct": v} for n, v in sorted_sectors[-3:]]

    first_snap = snapshots[0] if snapshots else {}
    last_snap = snapshots[-1] if snapshots else {}
    first_hot = {s["name"] for s in (first_snap.get("sectors") or [])[:5]}
    last_hot = {s["name"] for s in (last_snap.get("sectors") or [])[:5]}
    new_hot = list(last_hot - first_hot)
    fallen_off = list(first_hot - last_hot)

    return {
        "top3_sectors": top3,
        "bottom3_sectors": bottom3,
        "sector_count": len(sector_avg),
        "rotation_in": new_hot,
        "rotation_out": fallen_off,
    }


# ── 추천 종목 성과 측정 (Hit Rate) ────────────────────
def _measure_recommendation_performance(snapshots: list[dict]) -> dict:
    """기간 초 BUY 추천 종목들의 현재 가격 대비 수익률 추적."""
    if len(snapshots) < 2:
        return {"total_buy_recs": 0, "hit_rate_pct": 0, "avg_return_pct": 0, "stocks": []}

    first_snap = snapshots[0]
    last_snap = snapshots[-1]

    first_recs = {r["ticker"]: r for r in first_snap.get("recommendations", [])
                  if r.get("recommendation") == "BUY"}
    last_recs = {r["ticker"]: r for r in last_snap.get("recommendations", [])}

    results = []
    for ticker, orig in first_recs.items():
        current = last_recs.get(ticker)
        orig_price = orig.get("price", 0)
        if not orig_price:
            continue

        if current and current.get("price"):
            cur_price = current["price"]
        else:
            cur_price = orig_price

        ret_pct = round((cur_price - orig_price) / orig_price * 100, 2) if orig_price else 0
        orig_score = orig.get("multi_factor", {}).get("multi_score", 0)
        brain_score = orig.get("verity_brain", {}).get("brain_score", 0)

        results.append({
            "ticker": ticker,
            "name": orig.get("name", "?"),
            "buy_price": orig_price,
            "current_price": cur_price,
            "return_pct": ret_pct,
            "orig_multi_score": orig_score,
            "orig_brain_score": brain_score,
            "hit": ret_pct > 0,
        })

    results.sort(key=lambda x: x["return_pct"], reverse=True)

    total = len(results)
    hits = sum(1 for r in results if r["hit"])
    hit_rate = round(hits / total * 100, 1) if total else 0
    avg_ret = _safe_avg([r["return_pct"] for r in results])

    high_score_stocks = [r for r in results if r["orig_multi_score"] >= 70]
    high_score_hit = sum(1 for r in high_score_stocks if r["hit"])
    high_score_total = len(high_score_stocks)
    high_score_hit_rate = round(high_score_hit / high_score_total * 100, 1) if high_score_total else 0

    return {
        "total_buy_recs": total,
        "hit_rate_pct": hit_rate,
        "avg_return_pct": avg_ret,
        "high_score_hit_rate_pct": high_score_hit_rate,
        "high_score_count": high_score_total,
        "best_picks": results[:5],
        "worst_picks": results[-3:] if total >= 3 else [],
        "stocks": results,
    }


# ── 이번 리포트 기대 수익률 (목표가 대비 Upside) ──────
def _measure_expected_return(snapshots: list[dict]) -> dict:
    """리포트 시점(최신 snapshot)의 BUY/STRONG_BUY 종목 목표가 대비 기대수익률."""
    if not snapshots:
        return {"count": 0, "avg_upside_pct": 0, "median_upside_pct": 0, "top_picks": []}

    latest = snapshots[-1]
    recs = latest.get("recommendations", []) or []
    buy_grades = {"BUY", "STRONG_BUY"}

    upsides: list[dict] = []
    for r in recs:
        grade = (r.get("recommendation") or r.get("verity_brain", {}).get("grade") or "").upper()
        if grade not in buy_grades:
            continue
        price = r.get("price") or r.get("current_price")
        target = r.get("target_price")
        if not price or not target:
            continue
        try:
            upside = round((float(target) - float(price)) / float(price) * 100, 2)
        except Exception:
            continue
        upsides.append({
            "ticker": r.get("ticker"),
            "name": r.get("name", "?"),
            "grade": grade,
            "price": price,
            "target_price": target,
            "upside_pct": upside,
        })

    if not upsides:
        return {"count": 0, "avg_upside_pct": 0, "median_upside_pct": 0, "top_picks": []}

    upsides.sort(key=lambda x: x["upside_pct"], reverse=True)
    pcts = [u["upside_pct"] for u in upsides]
    avg = round(statistics.mean(pcts), 2)
    median = round(statistics.median(pcts), 2)

    return {
        "count": len(upsides),
        "avg_upside_pct": avg,
        "median_upside_pct": median,
        "max_upside_pct": upsides[0]["upside_pct"],
        "min_upside_pct": upsides[-1]["upside_pct"],
        "top_picks": upsides[:5],
        "snapshot_date": latest.get("_date", ""),
    }


# ── 매크로 지표 추이 ──────────────────────────────────
def _analyze_macro_trends(snapshots: list[dict]) -> dict:
    """매크로 지표의 기간 내 추이 + 변화 방향."""
    keys = ["vix", "usd_krw", "gold", "wti_oil", "us_10y"]
    trends: dict[str, dict] = {}

    for key in keys:
        vals = []
        for snap in snapshots:
            macro = snap.get("macro", {})
            v = macro.get(key, {}).get("value")
            if v is not None:
                vals.append(float(v))
        if vals:
            trends[key] = {
                "start": vals[0],
                "end": vals[-1],
                "change_pct": round((vals[-1] - vals[0]) / vals[0] * 100, 2) if vals[0] else 0,
                "avg": _safe_avg(vals),
                "max": max(vals),
                "min": min(vals),
                "stdev": _safe_stdev(vals),
            }

    mood_scores = []
    for snap in snapshots:
        ms = snap.get("macro", {}).get("market_mood", {}).get("score")
        if ms is not None:
            mood_scores.append(ms)

    return {
        "indicators": trends,
        "mood_avg": _safe_avg(mood_scores),
        "mood_trend": "improving" if len(mood_scores) >= 2 and mood_scores[-1] > mood_scores[0] else "declining" if len(mood_scores) >= 2 and mood_scores[-1] < mood_scores[0] else "stable",
    }


# ── 브레인 성과 분석 ──────────────────────────────────
def _analyze_brain_accuracy(snapshots: list[dict]) -> dict:
    """Verity Brain 등급의 실제 수익률과의 상관 분석."""
    grade_returns: dict[str, list] = defaultdict(list)

    if len(snapshots) < 2:
        return {"grades": {}, "insight": "데이터 부족"}

    first_snap = snapshots[0]
    last_snap = snapshots[-1]

    first_recs = {r["ticker"]: r for r in first_snap.get("recommendations", [])}
    last_recs = {r["ticker"]: r for r in last_snap.get("recommendations", [])}

    for ticker, orig in first_recs.items():
        brain = orig.get("verity_brain", {})
        grade = brain.get("grade", "WATCH")
        orig_price = orig.get("price", 0)
        cur = last_recs.get(ticker)
        cur_price = cur.get("price", orig_price) if cur else orig_price

        if orig_price:
            ret = round((cur_price - orig_price) / orig_price * 100, 2)
            grade_returns[grade].append(ret)

    grade_stats = {}
    for grade, rets in grade_returns.items():
        grade_stats[grade] = {
            "count": len(rets),
            "avg_return": _safe_avg(rets),
            "hit_rate": round(sum(1 for r in rets if r > 0) / len(rets) * 100, 1) if rets else 0,
        }

    sb = grade_stats.get("STRONG_BUY", {}).get("avg_return", 0)
    avoid = grade_stats.get("AVOID", {}).get("avg_return", 0)
    if sb > 0 and avoid < 0:
        insight = f"브레인 등급 정확: 강력매수 평균 +{sb}%, 회피 평균 {avoid}%"
    elif sb <= 0:
        insight = f"브레인 강력매수 평균 {sb}% — 팩트 가중치 조정 검토 필요"
    else:
        insight = "등급별 수익률 차이 미미 — 판별력 개선 필요"

    return {"grades": grade_stats, "insight": insight}


# ── 보조 입력 신호 단독 적중률 (Brain 결정 input 검증용) ──────────
# 주의: 이 함수는 Brain 의 보조 입력(멀티팩터/컨센서스/타이밍/예측/뉴스감성)이
#       단독으로 사용됐을 때 얼마나 맞았는지 측정한다. Brain 과 경쟁시키는
#       비교가 아니라 Brain 결정의 input 품질을 진단하는 검증 지표.
#       Brain 자체의 등급별 적중률은 _analyze_brain_accuracy 가 다룸.
def _meta_analyze_data_sources(snapshots: list[dict]) -> dict:
    """Brain 보조 입력 신호의 단독 적중률 — input 품질 검증용."""
    if len(snapshots) < 2:
        return {"findings": [], "best_predictor": "데이터 부족"}

    first_snap = snapshots[0]
    last_snap = snapshots[-1]

    first_recs = {r["ticker"]: r for r in first_snap.get("recommendations", [])}
    last_recs = {r["ticker"]: r for r in last_snap.get("recommendations", [])}

    source_accuracy: dict[str, list] = {
        "multi_factor": [],
        "consensus": [],
        "timing": [],
        "prediction": [],
        "sentiment": [],
        "brain": [],
    }
    # 상승장 거품 제거용 — actual_up 비율 = 무뇌 "전부 BUY" predictor 적중률.
    # 실력 = source 적중률 - market_drift_baseline (excess accuracy).
    actual_ups: list[bool] = []

    for ticker, orig in first_recs.items():
        cur = last_recs.get(ticker)
        if not cur:
            continue
        orig_price = orig.get("price", 0)
        cur_price = cur.get("price", orig_price)
        if not orig_price:
            continue

        actual_up = cur_price > orig_price
        actual_ups.append(actual_up)

        ms = (orig.get("multi_factor") or {}).get("multi_score", 50)
        source_accuracy["multi_factor"].append(1 if (ms >= 60) == actual_up else 0)

        cs = (orig.get("consensus") or {}).get("consensus_score", 50)
        source_accuracy["consensus"].append(1 if (cs >= 60) == actual_up else 0)

        ts = (orig.get("timing") or {}).get("timing_score", 50)
        source_accuracy["timing"].append(1 if (ts >= 60) == actual_up else 0)

        up = (orig.get("prediction") or {}).get("up_probability", 50)
        source_accuracy["prediction"].append(1 if (up >= 55) == actual_up else 0)

        ss = (orig.get("sentiment") or {}).get("score", 50)
        source_accuracy["sentiment"].append(1 if (ss >= 55) == actual_up else 0)

        bs = (orig.get("verity_brain") or {}).get("brain_score", 50)
        source_accuracy["brain"].append(1 if (bs >= 60) == actual_up else 0)

    # market_drift baseline — 같은 기간 종목 상승 비율. 70% 상승장 = "전부 BUY" 도 70% accuracy.
    market_drift_pct = (
        round(sum(actual_ups) / len(actual_ups) * 100, 1) if actual_ups else 50.0
    )

    findings = []
    for source, accuracies in source_accuracy.items():
        if accuracies:
            acc = round(sum(accuracies) / len(accuracies) * 100, 1)
            findings.append({
                "source": source,
                "accuracy_pct": acc,
                "sample_size": len(accuracies),
                # excess = source 실력 (baseline 위 / 아래). regime-neutral.
                "excess_accuracy_pct": round(acc - market_drift_pct, 1),
            })

    # excess (실력) 기준 정렬 — 상승장 거품 제거된 ranking. accuracy_pct 보다 우선.
    findings.sort(key=lambda x: x["excess_accuracy_pct"], reverse=True)

    labels = {
        "multi_factor": "멀티팩터 종합",
        "consensus": "컨센서스",
        "timing": "매매 타이밍",
        "prediction": "AI 예측(XGBoost)",
        "sentiment": "뉴스 감성",
        "brain": "Verity Brain (종합 판단)",
    }

    # Brain 은 input 신호가 아니라 종합 판단자 — 보조 신호와 분리해서 표시.
    # feedback_brain_synthesizer_role: 동급 BarChart/ranking 금지.
    # findings_aux = 5 보조 입력 / findings_brain = 1 종합 판단자.
    aux = [f for f in findings if f["source"] != "brain"]
    # aux 도 excess 기준 정렬 — 상승장 거품 제거
    aux.sort(key=lambda x: x["excess_accuracy_pct"], reverse=True)
    brain = next((f for f in findings if f["source"] == "brain"), None)
    if brain:
        brain = dict(brain)  # mutate-safe copy
        brain["label"] = labels.get("brain", "Verity Brain (종합 판단)")
        brain["note"] = "보조 신호 ranking 동급 비교 금지 — 종합 판단자 참고치"

    best_predicter_aux = ""
    if aux:
        helpful = aux[0]
        noisy = aux[-1]
        hl = labels.get(helpful["source"], helpful["source"])
        nl = labels.get(noisy["source"], noisy["source"])
        brain_excess = (
            f"{brain['excess_accuracy_pct']:+.1f}%p (적중률 {brain['accuracy_pct']}%)"
            if brain else "N/A"
        )
        best_predicter_aux = (
            f"Brain 보조 입력 신호 — 시장 baseline {market_drift_pct}% 대비 excess. "
            f"{hl}({helpful['excess_accuracy_pct']:+.1f}%p) 가장 유용 / "
            f"{nl}({noisy['excess_accuracy_pct']:+.1f}%p) 노이즈 가능. "
            f"Brain 종합 판단 excess {brain_excess} (참고). "
            f"※ excess > 0 → 시장 drift 대비 실력 / < 0 → 노이즈 또는 역방향. "
            f"단순 accuracy_pct 는 상승장에서 무뇌 'BUY 전부' 와 구분 불가."
        )

    return {
        # 신규 분리 schema (5+1) — VerityReport / monthly PDF 가 우선 read
        "findings_aux": aux,
        "findings_brain": brain,
        "aux_labels": {k: v for k, v in labels.items() if k != "brain"},
        # 시장 drift baseline — 같은 기간 종목 상승 비율 (regime 표기)
        "market_drift_pct": market_drift_pct,
        "sample_size": len(actual_ups),
        # 기존 findings (혼합) 도 유지 — 호환성 (gemini_analyst 등 downstream 참조)
        "findings": findings,
        "best_predictor": best_predicter_aux,
    }


# ── 뉴스 키워드 빈도 ──────────────────────────────────
def _analyze_news_keywords(snapshots: list[dict]) -> dict:
    """기간 내 뉴스 키워드 빈도 분석."""
    word_counter: Counter = Counter()

    for snap in snapshots:
        for h in snap.get("headlines", []):
            title = h.get("title", "")
            words = title.split()
            for w in words:
                if len(w) >= 2:
                    word_counter[w] += 1

    top20 = word_counter.most_common(20)
    return {
        "top_keywords": [{"word": w, "count": c} for w, c in top20],
        "total_headlines": sum(
            len(snap.get("headlines", [])) for snap in snapshots
        ),
    }


# ── 포트폴리오 성과 추이 ──────────────────────────────
def _compute_max_drawdown_pct(asset_history: list[dict]) -> float:
    """표준 Max Drawdown (%): 시점별 running peak 대비 최대 하락률.
    값은 0 이하(하락)로 반환. asset_history는 시간 순 정렬 전제."""
    if not asset_history:
        return 0.0
    running_peak = None
    max_dd = 0.0
    for a in asset_history:
        v = a.get("total_asset", 0)
        if not v or v <= 0:
            continue
        if running_peak is None or v > running_peak:
            running_peak = v
            continue
        dd = (v - running_peak) / running_peak * 100
        if dd < max_dd:
            max_dd = dd
    return round(max_dd, 2)


def _analyze_portfolio_performance(snapshots: list[dict]) -> dict:
    """VAMS 포트폴리오의 기간 내 자산 추이."""
    asset_history = []
    return_history = []

    for snap in snapshots:
        vams = snap.get("vams", {})
        ta = vams.get("total_asset")
        tr = vams.get("total_return_pct")
        if ta is not None:
            asset_history.append({"date": snap.get("_date", ""), "total_asset": ta})
        if tr is not None:
            return_history.append({"date": snap.get("_date", ""), "return_pct": tr})

    if len(return_history) >= 2:
        start_ret = return_history[0]["return_pct"]
        end_ret = return_history[-1]["return_pct"]
        period_return = round(end_ret - start_ret, 2)
    else:
        period_return = 0

    peak = max((a["total_asset"] for a in asset_history), default=0)
    trough = min((a["total_asset"] for a in asset_history), default=0)
    # 표준 MDD: 시퀀스 기반 running peak 대비 최대 하락
    drawdown = _compute_max_drawdown_pct(asset_history)

    return {
        "period_return_pct": period_return,
        "peak_asset": peak,
        "trough_asset": trough,
        "max_drawdown_pct": drawdown,
        "data_points": len(asset_history),
        "asset_history": asset_history[-10:],
    }


# ── Black Swan 이벤트 집계 ────────────────────────────
def _analyze_black_swan_events(days: int) -> dict:
    """tail_risk_digest 가 적재한 ledger 에서 직전 N 일 이벤트 집계.

    daily=24h, weekly=7d, monthly=30d. severity/category 분포 + top events.
    """
    hours = max(1, days) * 24
    events = load_black_swan_ledger(hours=hours)
    if not events:
        return {
            "available": False,
            "count": 0,
            "window_days": days,
            "top_events": [],
            "category_dist": {},
            "severity_dist": {"high_8plus": 0, "mid_5to7": 0},
            "telegram_sent_count": 0,
        }

    # category 분포
    cat_counter: Counter = Counter()
    for e in events:
        cat_counter[str(e.get("category") or "unknown")] += 1

    # severity 분포 (telegram cutoff = 8, ledger cutoff = 5)
    high = sum(1 for e in events if int(e.get("severity") or 0) >= 8)
    mid = sum(1 for e in events if 5 <= int(e.get("severity") or 0) < 8)
    sent = sum(1 for e in events if e.get("telegram_sent"))

    # top events (severity desc, ts desc)
    sorted_events = sorted(
        events,
        key=lambda e: (int(e.get("severity") or 0), str(e.get("ts_kst") or "")),
        reverse=True,
    )
    top_events = []
    for e in sorted_events[:5]:
        top_events.append({
            "ts_kst": e.get("ts_kst"),
            "severity": e.get("severity"),
            "category": e.get("category"),
            "summary_ko": e.get("summary_ko"),
            "portfolio_angle": e.get("portfolio_angle") or "",
            "primary_title": e.get("primary_title") or "",
            "link": e.get("link") or "",
            "cycle_stage": e.get("cycle_stage"),
        })

    return {
        "available": True,
        "count": len(events),
        "window_days": days,
        "category_dist": dict(cat_counter),
        "severity_dist": {"high_8plus": high, "mid_5to7": mid},
        "telegram_sent_count": sent,
        "top_events": top_events,
    }


# ── 메인 엔트리 ───────────────────────────────────────
def generate_periodic_analysis(period: str) -> dict:
    """
    주간/월간/분기/반기/연간 정기 분석 데이터 생성.

    Returns:
        dict: Gemini에 전달할 구조화된 분석 데이터
    """
    days = PERIOD_DAYS.get(period, 7)
    snapshots = load_snapshots_range(days)

    if not snapshots:
        return {
            "period": period,
            "days_requested": days,
            "days_available": 0,
            "status": "no_data",
            "message": f"최근 {days}일 내 아카이빙된 데이터가 없습니다.",
        }

    # ── 2026-05-24 trail span 메타 박음 (acb2c12c / Q4 정합 보강) ──
    # Q4 답변 (Perplexity, Bloomberg/LSEG point-in-time) 정합:
    #   ratio ≥ 0.7 → OK / 0.5 ≤ ratio < 0.7 → amber / ratio < 0.5 → insufficient.
    from datetime import datetime as _dt
    oldest_date_str = snapshots[0].get("_date") if snapshots and snapshots[0] else None
    actual_span_days = None
    coverage_ratio = None
    if oldest_date_str:
        try:
            oldest_date = _dt.strptime(oldest_date_str, "%Y-%m-%d").date()
            actual_span_days = (now_kst().date() - oldest_date).days
            coverage_ratio = round(actual_span_days / days, 3) if days > 0 else None
        except (ValueError, TypeError):
            actual_span_days = None
    trail_sufficient = (
        coverage_ratio is not None and coverage_ratio >= 0.7
    )
    quality_label = (
        "OK" if (coverage_ratio is not None and coverage_ratio >= 0.7)
        else "amber" if (coverage_ratio is not None and coverage_ratio >= 0.5)
        else "insufficient"
    )

    result = {
        "period": period,
        "period_label": {
            "daily": "일일", "weekly": "주간", "monthly": "월간",
            "quarterly": "분기", "semi": "반기", "annual": "연간",
        }.get(period, period),
        "days_requested": days,
        "days_available": len(snapshots),
        "actual_span_days": actual_span_days,
        "coverage_ratio": coverage_ratio,
        "trail_sufficient": trail_sufficient,
        "quality_label": quality_label,
        "date_range": {
            "start": snapshots[0].get("_date", ""),
            "end": snapshots[-1].get("_date", ""),
        },
        "generated_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "status": "ok",
        "sectors": _analyze_sector_trends(snapshots),
        "recommendations": _measure_recommendation_performance(snapshots),
        "expected_return": _measure_expected_return(snapshots),
        "macro": _analyze_macro_trends(snapshots),
        "brain_accuracy": _analyze_brain_accuracy(snapshots),
        "meta_analysis": _meta_analyze_data_sources(snapshots),
        "news_keywords": _analyze_news_keywords(snapshots),
        "portfolio": _analyze_portfolio_performance(snapshots),
        "black_swan_events": _analyze_black_swan_events(days),
    }

    if not trail_sufficient and actual_span_days is not None:
        result["trail_warning"] = (
            f"trail 부족 — 요청 {days}d / 실제 {actual_span_days}d (coverage {coverage_ratio:.2f}, "
            f"quality={quality_label}). N≥{int(days * 0.7)}d 자연 회복 필요. "
            f"본 리포트의 sectors / brain_accuracy / portfolio 등 분석 결과는 "
            f"실제 누적 기간 ({actual_span_days}d) 기준으로 해석 의무. "
            f"Gemini caller: do not compare period labels as equal horizons when coverage differs."
        )

    # CFTC COT 기관 포지셔닝 추이 (주간 이상)
    if days >= 7:
        result["cftc_cot_trend"] = _analyze_cot_trend(snapshots)
    # 펀드 플로우 추이 (주간 이상)
    if days >= 7:
        result["fund_flow_trend"] = _analyze_fund_flow_trend(snapshots)

    return result


# ── CFTC COT 기관 포지셔닝 추이 ───────────────────────
def _analyze_cot_trend(snapshots: list[dict]) -> dict:
    """기간 내 CFTC COT 기관 포지셔닝 변화 추적."""
    signals = []
    sp500_nets = []

    for snap in snapshots:
        cot = snap.get("cftc_cot", {})
        if not cot.get("ok"):
            continue
        summary = cot.get("summary", {})
        sig = summary.get("overall_signal", "neutral")
        signals.append(sig)
        sp_data = (cot.get("instruments") or {}).get("SP500") or {}
        if sp_data.get("ok"):
            sp500_nets.append(sp_data.get("net_managed_money", 0))

    if not signals:
        return {"available": False}

    signal_counts = Counter(signals)
    dominant = signal_counts.most_common(1)[0][0] if signal_counts else "neutral"

    return {
        "available": True,
        "data_points": len(signals),
        "dominant_signal": dominant,
        "signal_distribution": dict(signal_counts),
        "sp500_net_range": {
            "min": min(sp500_nets) if sp500_nets else None,
            "max": max(sp500_nets) if sp500_nets else None,
            "latest": sp500_nets[-1] if sp500_nets else None,
        },
    }


# ── 펀드 플로우 추이 ─────────────────────────────────
def _analyze_fund_flow_trend(snapshots: list[dict]) -> dict:
    """기간 내 펀드 플로우 로테이션 시그널 추이."""
    signals = []

    for snap in snapshots:
        ff = snap.get("fund_flows", {})
        if not ff.get("ok"):
            continue
        sig = ff.get("rotation_signal", "neutral")
        signals.append(sig)

    if not signals:
        return {"available": False}

    signal_counts = Counter(signals)
    dominant = signal_counts.most_common(1)[0][0] if signal_counts else "neutral"

    return {
        "available": True,
        "data_points": len(signals),
        "dominant_signal": dominant,
        "signal_distribution": dict(signal_counts),
    }


# ── 섹터 추이 요약 (프론트 시각화용) ──────────────────────
_TREND_PERIOD_DAYS = {"1m": 30, "3m": 90, "6m": 180, "1y": 365}


def compute_sector_trend_summary() -> dict:
    """일별 스냅샷 기반 1M/3M/6M/1Y 섹터 추이 계산.

    2026-05-24 Q4 정합 fix (Perplexity Sonar Pro, docs/PERPLEXITY_ANSWERS_20260524.md):
      Bloomberg/LSEG point-in-time history 관행 정합 — 라벨 vs 실제 trail 길이 분리.
      coverage_ratio + quality_label (OK/amber/insufficient) + 0.5 hard floor.

      이전 (acb2c12c) = 0.7 hard floor (0.7 미만 통계 미생성). Q4 권고 완화:
        - ratio ≥ 0.7  → quality_label = "OK" (정상)
        - 0.5 ≤ ratio < 0.7 → quality_label = "amber" (계산 허용 + trail_warning)
        - ratio < 0.5  → quality_label = "insufficient" (통계 미생성, flag dict 만 반환)
      외부 caller (sector_rotation_detector._fallback_from_sector_trends) = top3/bottom3
      list 사용 → amber band 도 top3/bottom3 박음 (insufficient case 만 빈 list).
    """
    from datetime import datetime as _dt
    result: dict = {}
    today_date = now_kst().date()
    for label, days in _TREND_PERIOD_DAYS.items():
        snaps = load_snapshots_range(days)
        if len(snaps) < 2:
            result[label] = None
            continue
        oldest_date_str = snaps[0].get("_date") if snaps[0] else None
        actual_span_days = None
        coverage_ratio = None
        if oldest_date_str:
            try:
                oldest_date = _dt.strptime(oldest_date_str, "%Y-%m-%d").date()
                actual_span_days = (today_date - oldest_date).days
                coverage_ratio = round(actual_span_days / days, 3) if days > 0 else None
            except (ValueError, TypeError):
                actual_span_days = None
        # Q4 권고 — 3 band (OK / amber / insufficient)
        if coverage_ratio is not None and coverage_ratio < 0.5:
            result[label] = {
                "insufficient_trail": True,
                "quality_label": "insufficient",
                "required_days": days,
                "actual_span_days": actual_span_days,
                "coverage_ratio": coverage_ratio,
                "snapshots_available": len(snaps),
                "top3_sectors": [],
                "bottom3_sectors": [],
                "sector_count": 0,
                "rotation_in": [],
                "rotation_out": [],
            }
            continue
        # ratio ≥ 0.5 → 통계 박음 (OK 또는 amber)
        analysis = _analyze_sector_trends(snaps)
        analysis["required_days"] = days
        analysis["actual_span_days"] = actual_span_days
        analysis["coverage_ratio"] = coverage_ratio
        if coverage_ratio is not None and coverage_ratio < 0.7:
            analysis["quality_label"] = "amber"
            analysis["trail_warning"] = (
                f"trail 부족 — 요청 {days}d / 실제 {actual_span_days}d (coverage {coverage_ratio:.2f}). "
                f"라벨 ≠ full-window. amber band — 통계 노출 but 보수 해석 의무."
            )
        else:
            analysis["quality_label"] = "OK"
        result[label] = analysis
    return result
