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


# ── 데이터 소스 메타 분석 ──────────────────────────────
def _meta_analyze_data_sources(snapshots: list[dict]) -> dict:
    """어떤 데이터 소스가 가장 정확한 예측에 기여했는지 메타 분석."""
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

    for ticker, orig in first_recs.items():
        cur = last_recs.get(ticker)
        if not cur:
            continue
        orig_price = orig.get("price", 0)
        cur_price = cur.get("price", orig_price)
        if not orig_price:
            continue

        actual_up = cur_price > orig_price

        ms = orig.get("multi_factor", {}).get("multi_score", 50)
        source_accuracy["multi_factor"].append(1 if (ms >= 60) == actual_up else 0)

        cs = orig.get("consensus", {}).get("consensus_score", 50)
        source_accuracy["consensus"].append(1 if (cs >= 60) == actual_up else 0)

        ts = orig.get("timing", {}).get("timing_score", 50)
        source_accuracy["timing"].append(1 if (ts >= 60) == actual_up else 0)

        up = orig.get("prediction", {}).get("up_probability", 50)
        source_accuracy["prediction"].append(1 if (up >= 55) == actual_up else 0)

        ss = orig.get("sentiment", {}).get("score", 50)
        source_accuracy["sentiment"].append(1 if (ss >= 55) == actual_up else 0)

        bs = orig.get("verity_brain", {}).get("brain_score", 50)
        source_accuracy["brain"].append(1 if (bs >= 60) == actual_up else 0)

    findings = []
    for source, accuracies in source_accuracy.items():
        if accuracies:
            acc = round(sum(accuracies) / len(accuracies) * 100, 1)
            findings.append({"source": source, "accuracy_pct": acc, "sample_size": len(accuracies)})

    findings.sort(key=lambda x: x["accuracy_pct"], reverse=True)

    labels = {
        "multi_factor": "멀티팩터 종합",
        "consensus": "컨센서스",
        "timing": "매매 타이밍",
        "prediction": "AI 예측(XGBoost)",
        "sentiment": "뉴스 감성",
        "brain": "Verity Brain",
    }

    best = findings[0] if findings else None
    worst = findings[-1] if findings else None
    best_predictor = ""
    if best and worst:
        bl = labels.get(best["source"], best["source"])
        wl = labels.get(worst["source"], worst["source"])
        best_predictor = (
            f"{bl}({best['accuracy_pct']}%)이 가장 정확했고, "
            f"{wl}({worst['accuracy_pct']}%)은 개선 필요"
        )

    return {"findings": findings, "best_predictor": best_predictor}


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
    drawdown = round((trough - peak) / peak * 100, 2) if peak else 0

    return {
        "period_return_pct": period_return,
        "peak_asset": peak,
        "trough_asset": trough,
        "max_drawdown_pct": drawdown,
        "data_points": len(asset_history),
        "asset_history": asset_history[-10:],
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

    result = {
        "period": period,
        "period_label": {
            "daily": "일일", "weekly": "주간", "monthly": "월간",
            "quarterly": "분기", "semi": "반기", "annual": "연간",
        }.get(period, period),
        "days_requested": days,
        "days_available": len(snapshots),
        "date_range": {
            "start": snapshots[0].get("_date", ""),
            "end": snapshots[-1].get("_date", ""),
        },
        "generated_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "status": "ok",
        "sectors": _analyze_sector_trends(snapshots),
        "recommendations": _measure_recommendation_performance(snapshots),
        "macro": _analyze_macro_trends(snapshots),
        "brain_accuracy": _analyze_brain_accuracy(snapshots),
        "meta_analysis": _meta_analyze_data_sources(snapshots),
        "news_keywords": _analyze_news_keywords(snapshots),
        "portfolio": _analyze_portfolio_performance(snapshots),
    }

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
        sp_data = cot.get("instruments", {}).get("SP500", {})
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
    스냅샷이 부족한 기간은 None. portfolio['sector_trends']에 저장용."""
    result: dict = {}
    for label, days in _TREND_PERIOD_DAYS.items():
        snaps = load_snapshots_range(days)
        if len(snaps) < 2:
            result[label] = None
            continue
        result[label] = _analyze_sector_trends(snaps)
    return result
