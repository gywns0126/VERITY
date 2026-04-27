"""
GET /api/admin/brain_health — Overview 탭용 종합 응답.

반환:
  {
    "kpi": {
      "brain_health_score": 78,
      "data_freshness_minutes": 5,
      "drift_score": 0.12,
      "confidence": 0.71,
    },
    "data_health_meta": {...},
    "drift_meta": {...},
    "trust": {...},
    "topology": {  # 3D Brain 노드/에지 (Phase 3 에서 시각화)
      "nodes": [...],
      "edges": [...],
    },
    "alerts": [...],  # Phase 4 에서 enrich
    "checked_at": "2026-04-27T22:00:00+09:00"
  }
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler

from api.admin._common import (
    fetch_portfolio,
    get_observability,
    authorize,
    write_response,
    write_options,
    headers_to_dict,
)


def _compute_kpi(obs: dict, portfolio: dict) -> dict:
    """4개 KPI 카드 (와이어프레임 §2)."""
    health = obs.get("data_health") or {}
    drift = obs.get("drift") or {}
    explanation = obs.get("explanation") or {}
    trust = obs.get("trust") or {}

    # Brain Health Score: trust 충족률 × 100
    satisfied = trust.get("satisfied", 0)
    total = trust.get("total", 0) or 1
    brain_health_score = round((satisfied / total) * 100)

    # Data Freshness: 가장 오래된 소스
    sources = health.get("sources") or {}
    freshness_values = [v.get("freshness_minutes") for v in sources.values()
                       if isinstance(v, dict) and isinstance(v.get("freshness_minutes"), (int, float))]
    max_freshness = max(freshness_values) if freshness_values else None

    # Drift Score
    drift_score = drift.get("overall_drift_score", 0.0)

    # Confidence: avg_brain_score / 100, 또는 trust 만족률
    avg_score = explanation.get("avg_brain_score")
    confidence = round(avg_score / 100, 3) if isinstance(avg_score, (int, float)) else round(satisfied / total, 3)

    return {
        "brain_health_score": brain_health_score,
        "data_freshness_minutes": max_freshness,
        "drift_score": drift_score,
        "confidence": confidence,
    }


_HEALTH_TO_SCORE = {"ok": 95, "warning": 75, "critical": 40, "unknown": 50}


def _build_topology(obs: dict) -> dict:
    """3D Brain 노드/에지 — 12개 (5 input + 4 engine + 3 output, 와이어프레임 §7).

    spec §3.1 BrainNode 인터페이스 준수:
      id / cluster / health / health_score / metric{primary_value, primary_label, yesterday_change}
      / detail{description, related_data_health_keys}
    """
    health = obs.get("data_health") or {}
    sources = health.get("sources") or {}
    drift = obs.get("drift") or {}
    drifted = set(drift.get("drifted_features") or [])
    explanation = obs.get("explanation") or {}
    vs_yesterday = explanation.get("vs_yesterday") or {}
    avg_score = explanation.get("avg_brain_score")

    def _agg_status(*keys):
        worst = None
        order = {"ok": 0, "warning": 1, "critical": 2, "unknown": 1}
        for k in keys:
            v = sources.get(k)
            if isinstance(v, dict) and v.get("status"):
                if worst is None or order.get(v["status"], 0) > order.get(worst, 0):
                    worst = v["status"]
        return worst or "unknown"

    def _agg_freshness(*keys):
        vals = []
        for k in keys:
            v = sources.get(k)
            if isinstance(v, dict) and isinstance(v.get("freshness_minutes"), (int, float)):
                vals.append(v["freshness_minutes"])
        return max(vals) if vals else None

    def _has_neg(*features):
        negs = explanation.get("negative_contributors") or []
        return any(n.get("feature") in features for n in negs)

    def _node(id, cluster, label, health_status, primary_value, primary_label,
              yesterday_change=0, description="", related=None):
        return {
            "id": id, "cluster": cluster, "label": label,
            "health": health_status,
            "health_score": _HEALTH_TO_SCORE.get(health_status, 50),
            "metric": {
                "primary_value": primary_value,
                "primary_label": primary_label,
                "yesterday_change": yesterday_change,
            },
            "detail": {
                "description": description,
                "related_data_health_keys": list(related or []),
            },
        }

    nodes = [
        # Input 5
        _node("input_price", "input", "가격",
              _agg_status("yfinance", "kis"),
              _agg_freshness("yfinance", "kis"),
              "신선도(분)",
              description="yfinance + KIS 실시간 가격",
              related=["yfinance", "kis"]),
        _node("input_financials", "input", "재무",
              _agg_status("dart", "sec_edgar"),
              _agg_freshness("dart", "sec_edgar"),
              "신선도(분)",
              description="DART/SEC 재무제표",
              related=["dart", "sec_edgar"]),
        _node("input_macro", "input", "매크로",
              _agg_status("fred", "ecos"),
              _agg_freshness("fred", "ecos"),
              "신선도(분)",
              description="FRED/ECOS 매크로 지표",
              related=["fred", "ecos"]),
        _node("input_news", "input", "뉴스",
              "warning" if "news_sentiment_avg" in drifted else "ok",
              0,
              "drift" if "news_sentiment_avg" in drifted else "정상",
              description="RSS / sentiment",
              related=["news"]),
        _node("input_sector", "input", "섹터",
              _agg_status("krx_open_api"),
              _agg_freshness("krx_open_api"),
              "신선도(분)",
              description="KRX OpenAPI 섹터 데이터",
              related=["krx_open_api"]),
        # Engine 4
        _node("engine_fact", "engine", "Fact",
              "ok" if avg_score else "unknown",
              avg_score or 0,
              "avg Brain Score",
              yesterday_change=vs_yesterday.get("score_change", 0),
              description="multi_factor / consensus / prediction / backtest",
              related=["recommendations"]),
        _node("engine_sentiment", "engine", "Sentiment",
              "warning" if "news_sentiment_avg" in drifted else "ok",
              0, "신호",
              description="news / x sentiment / market mood",
              related=["news"]),
        _node("engine_risk", "engine", "Risk",
              "warning" if _has_neg("red_flags", "macro_override_active") else "ok",
              0, "필터",
              description="red_flags / macro_override / panic_stage",
              related=["macro"]),
        _node("engine_vci", "engine", "VCI",
              "warning" if _has_neg("vci_extreme") else "ok",
              0, "VCI",
              description="Verity Contrarian Index — fact↔sentiment 괴리",
              related=[]),
        # Output 3
        _node("output_score", "output", "Brain Score",
              "ok" if avg_score else "unknown",
              avg_score or 0,
              "0~100",
              yesterday_change=vs_yesterday.get("score_change", 0),
              description="평균 Brain Score (포트폴리오 전체)",
              related=[]),
        _node("output_grade", "output", "Grade",
              "ok",
              0,
              "5단계",
              description="STRONG_BUY / BUY / WATCH / CAUTION / AVOID",
              related=[]),
        _node("output_confidence", "output", "Confidence",
              "ok",
              0,
              "0~1",
              description="Brain Score 평균 / 100",
              related=[]),
    ]

    edges = [
        {"from": "input_price", "to": "engine_fact", "strength": 0.9},
        {"from": "input_financials", "to": "engine_fact", "strength": 0.8},
        {"from": "input_macro", "to": "engine_risk", "strength": 0.85},
        {"from": "input_news", "to": "engine_sentiment", "strength": 0.7},
        {"from": "input_sector", "to": "engine_fact", "strength": 0.5},
        {"from": "engine_fact", "to": "engine_vci", "strength": 0.7},
        {"from": "engine_sentiment", "to": "engine_vci", "strength": 0.7},
        {"from": "engine_risk", "to": "output_score", "strength": 0.6},
        {"from": "engine_vci", "to": "output_score", "strength": 0.9},
        {"from": "engine_fact", "to": "output_score", "strength": 0.9},
        {"from": "output_score", "to": "output_grade", "strength": 1.0},
        {"from": "output_score", "to": "output_confidence", "strength": 1.0},
    ]
    # 에지 health = from/to 중 worst
    node_health = {n["id"]: n["health"] for n in nodes}
    order = {"ok": 0, "warning": 1, "critical": 2, "unknown": 1}
    for e in edges:
        a, b = node_health.get(e["from"], "unknown"), node_health.get(e["to"], "unknown")
        e["health"] = a if order.get(a, 0) >= order.get(b, 0) else b

    return {"nodes": nodes, "edges": edges}


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
        if not obs:
            write_response(self, 200, {
                "kpi": {"brain_health_score": None, "data_freshness_minutes": None,
                       "drift_score": 0, "confidence": None},
                "data_health_meta": {}, "drift_meta": {}, "trust": {},
                "topology": _build_topology({}),
                "alerts": [],
                "checked_at": None,
                "status": "no_observability_data",
                "hint": "main.py full 모드 아직 미실행 — 첫 cron 후 데이터 누적",
            })
            return

        write_response(self, 200, {
            "kpi": _compute_kpi(obs, portfolio),
            "data_health_meta": {
                "overall_status": (obs.get("data_health") or {}).get("overall_status"),
                "core_sources_ok": (obs.get("data_health") or {}).get("core_sources_ok"),
                "sources_count": (obs.get("data_health") or {}).get("sources_count"),
            },
            "drift_meta": {
                "level": (obs.get("drift") or {}).get("level"),
                "overall_drift_score": (obs.get("drift") or {}).get("overall_drift_score"),
                "comparable_count": (obs.get("drift") or {}).get("comparable_count"),
            },
            "trust": obs.get("trust") or {},
            "topology": _build_topology(obs),
            "alerts": [],  # Phase 4 에서 enrich
            "checked_at": obs.get("checked_at"),
        })
