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


def _build_topology(obs: dict) -> dict:
    """3D Brain 노드/에지 — 12개 (5 input + 4 engine + 3 output, 와이어프레임 §7)."""
    health = obs.get("data_health") or {}
    sources = health.get("sources") or {}
    drift = obs.get("drift") or {}
    drifted = set(drift.get("drifted_features") or [])
    explanation = obs.get("explanation") or {}

    def src_status(*keys):
        for k in keys:
            v = sources.get(k)
            if isinstance(v, dict) and v.get("status"):
                return v["status"]
        return "unknown"

    # Input 5
    nodes = [
        {"id": "input_price", "cluster": "input", "label": "가격",
         "health": src_status("yfinance", "kis"),
         "metric": "yfinance/KIS"},
        {"id": "input_financials", "cluster": "input", "label": "재무",
         "health": src_status("dart", "sec_edgar"),
         "metric": "DART/SEC"},
        {"id": "input_macro", "cluster": "input", "label": "매크로",
         "health": src_status("fred", "ecos"),
         "metric": "FRED/ECOS"},
        {"id": "input_news", "cluster": "input", "label": "뉴스",
         "health": "warning" if "news_sentiment_avg" in drifted else "ok",
         "metric": "RSS/sentiment"},
        {"id": "input_sector", "cluster": "input", "label": "섹터",
         "health": src_status("krx_open_api"),
         "metric": "KRX"},
        # Engine 4
        {"id": "engine_fact", "cluster": "engine", "label": "Fact",
         "health": "ok" if explanation.get("avg_brain_score") else "unknown",
         "metric": f"avg {explanation.get('avg_brain_score', '-')}"},
        {"id": "engine_sentiment", "cluster": "engine", "label": "Sentiment",
         "health": "warning" if "news_sentiment_avg" in drifted else "ok",
         "metric": "news/x"},
        {"id": "engine_risk", "cluster": "engine", "label": "Risk",
         "health": "warning" if any(n["feature"] in ("red_flags", "macro_override_active")
                                    for n in (explanation.get("negative_contributors") or []))
                  else "ok",
         "metric": "filters"},
        {"id": "engine_vci", "cluster": "engine", "label": "VCI",
         "health": "warning" if any(n["feature"] == "vci_extreme"
                                    for n in (explanation.get("negative_contributors") or []))
                  else "ok",
         "metric": "comparator"},
        # Output 3
        {"id": "output_score", "cluster": "output", "label": "Brain Score",
         "health": "ok" if explanation.get("avg_brain_score") else "unknown",
         "metric": f"{explanation.get('avg_brain_score', '-')}"},
        {"id": "output_grade", "cluster": "output", "label": "Grade",
         "health": "ok",
         "metric": "5단계"},
        {"id": "output_confidence", "cluster": "output", "label": "Confidence",
         "health": "ok",
         "metric": "0~1"},
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
