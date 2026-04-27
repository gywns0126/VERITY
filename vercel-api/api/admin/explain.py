"""
GET /api/admin/explain — Model Health 탭 (와이어프레임 §4).

반환:
  Brain Score 분포 + 등급별 카운트 + 적중률 (verity_brain 활용)
  + AI 모델 이견 통계 (cross_verification 활용)
"""
from __future__ import annotations

from collections import Counter
from http.server import BaseHTTPRequestHandler

from api.admin._common import (
    fetch_portfolio,
    get_observability,
    authorize,
    write_response,
    write_options,
    headers_to_dict,
)


def _grade_distribution(portfolio: dict) -> dict:
    recs = portfolio.get("recommendations") or []
    grades = [r.get("grade") for r in recs if r.get("grade")]
    counter = Counter(grades)
    total = sum(counter.values()) or 1
    out = {}
    for g in ("STRONG_BUY", "BUY", "WATCH", "CAUTION", "AVOID"):
        c = counter.get(g, 0)
        out[g] = {"count": c, "pct": round(c / total, 4)}
    return out


def _brain_score_histogram(portfolio: dict) -> list:
    """0~100 을 10 bin 으로 분할."""
    recs = portfolio.get("recommendations") or []
    bins = [0] * 10
    for r in recs:
        bs = r.get("brain_score")
        if not isinstance(bs, (int, float)):
            continue
        idx = max(0, min(9, int(bs / 10)))
        bins[idx] += 1
    return [{"bin": f"{i*10}-{(i+1)*10}", "count": bins[i]} for i in range(10)]


def _ai_disagreements(portfolio: dict) -> dict:
    """cross_verification 키에서 Gemini ↔ Claude 이견 통계 추출."""
    cv = portfolio.get("cross_verification")
    if not isinstance(cv, dict):
        return {"total_compared": 0, "disagreements": 0, "by_resolution": {}}
    return {
        "total_compared": cv.get("total_compared", 0),
        "disagreements": cv.get("disagreements", 0),
        "by_resolution": cv.get("by_resolution", {}),
        "agreement_rate": cv.get("agreement_rate"),
    }


def _hit_rate_30d(portfolio: dict) -> dict:
    """verity_brain.brain_acc 또는 backtest_stats 에서 적중률 추출."""
    vb = portfolio.get("verity_brain") or {}
    bq = vb.get("brain_quality") or {}
    bs = portfolio.get("backtest_stats") or {}
    return {
        "brain_quality_score": bq.get("score"),
        "brain_quality_components": bq.get("components", {}),
        "buy_hit_rate": (bs.get("grades", {}).get("BUY", {}) or {}).get("hit_rate"),
        "avoid_avg_return": (bs.get("grades", {}).get("AVOID", {}) or {}).get("avg_return"),
    }


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        write_options(self)

    def do_GET(self):
        ok, reason = authorize(headers_to_dict(self))
        if not ok:
            write_response(self, 401, {"error": "unauthorized", "reason": reason})
            return

        portfolio = fetch_portfolio()
        if not portfolio:
            write_response(self, 503, {"error": "portfolio_unavailable"})
            return

        obs = get_observability(portfolio)
        explanation = obs.get("explanation") or {}

        write_response(self, 200, {
            "avg_brain_score": explanation.get("avg_brain_score"),
            "grade_distribution": _grade_distribution(portfolio),
            "brain_score_histogram": _brain_score_histogram(portfolio),
            "hit_rate": _hit_rate_30d(portfolio),
            "ai_disagreements": _ai_disagreements(portfolio),
            "positive_contributors": explanation.get("positive_contributors", []),
            "negative_contributors": explanation.get("negative_contributors", []),
            "checked_at": obs.get("checked_at"),
        })
