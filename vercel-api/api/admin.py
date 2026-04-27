"""
Brain Observatory admin API — 단일 파일 통합 (Hobby 12 함수 제한 회피).

구 5개 파일을 통합:
  /api/admin?type=brain_health   ← brain_health.py
  /api/admin?type=data_health    ← data_health.py
  /api/admin?type=drift          ← drift.py
  /api/admin?type=explain        ← explain.py
  /api/admin?type=trust          ← trust.py

인증: X-Admin-Token 또는 Bearer JWT (profiles.is_admin=true)
"""
from __future__ import annotations

import json
import logging
import os
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import requests

_logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# helper (구 _common.py)
# ──────────────────────────────────────────────────────────────────────

PORTFOLIO_URL = os.environ.get(
    "PORTFOLIO_RAW_URL",
    "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
ADMIN_BYPASS_TOKEN = os.environ.get("ADMIN_BYPASS_TOKEN", "")

_PORTFOLIO_CACHE: Dict[str, Any] = {"data": None, "fetched_at": 0}
_PORTFOLIO_TTL = 60


def fetch_portfolio() -> Optional[dict]:
    now = time.time()
    if _PORTFOLIO_CACHE["data"] and (now - _PORTFOLIO_CACHE["fetched_at"] < _PORTFOLIO_TTL):
        return _PORTFOLIO_CACHE["data"]
    try:
        r = requests.get(PORTFOLIO_URL, timeout=10)
        r.raise_for_status()
        data = r.json()
        _PORTFOLIO_CACHE["data"] = data
        _PORTFOLIO_CACHE["fetched_at"] = now
        return data
    except (requests.RequestException, ValueError) as e:
        _logger.warning("portfolio fetch failed: %s", e)
        return _PORTFOLIO_CACHE["data"]


def get_observability(portfolio: Optional[dict]) -> Dict[str, Any]:
    if not isinstance(portfolio, dict):
        return {}
    obs = portfolio.get("observability")
    return obs if isinstance(obs, dict) else {}


def is_admin_token(token: str) -> bool:
    return bool(ADMIN_BYPASS_TOKEN and token and token == ADMIN_BYPASS_TOKEN)


def verify_admin_jwt(jwt: str) -> bool:
    if not jwt or not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return False
    try:
        r = requests.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {jwt}"},
            timeout=5,
        )
        if r.status_code != 200:
            return False
        user_id = r.json().get("id")
        if not user_id:
            return False
        p = requests.get(
            f"{SUPABASE_URL}/rest/v1/profiles",
            params={"id": f"eq.{user_id}", "select": "is_admin"},
            headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {jwt}"},
            timeout=5,
        )
        if p.status_code != 200:
            return False
        rows = p.json()
        return bool(rows and rows[0].get("is_admin") is True)
    except (requests.RequestException, ValueError) as e:
        _logger.warning("admin verify failed: %s", e)
        return False


def authorize(headers_dict: Dict[str, str]) -> Tuple[bool, str]:
    bypass = headers_dict.get("x-admin-token") or headers_dict.get("X-Admin-Token")
    if bypass and is_admin_token(bypass):
        return True, "bypass_token"
    auth = headers_dict.get("authorization") or headers_dict.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        jwt = auth.split(" ", 1)[1].strip()
        if verify_admin_jwt(jwt):
            return True, "supabase_admin"
    if not ADMIN_BYPASS_TOKEN and not SUPABASE_URL:
        return False, "no_auth_configured"
    return False, "unauthorized"


def write_response(handler, status: int, body: dict, cache: str = "no-store") -> None:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", cache)
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Admin-Token")
    handler.end_headers()
    handler.wfile.write(payload)


def write_options(handler) -> None:
    handler.send_response(200)
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Admin-Token")
    handler.end_headers()


def headers_to_dict(handler) -> Dict[str, str]:
    return {k.lower(): v for k, v in handler.headers.items()}


# ──────────────────────────────────────────────────────────────────────
# brain_health: KPI + topology
# ──────────────────────────────────────────────────────────────────────

_HEALTH_TO_SCORE = {"ok": 95, "warning": 75, "critical": 40, "unknown": 50}


def _compute_kpi(obs: dict, portfolio: dict) -> dict:
    health = obs.get("data_health") or {}
    drift = obs.get("drift") or {}
    explanation = obs.get("explanation") or {}
    trust = obs.get("trust") or {}
    satisfied = trust.get("satisfied", 0)
    total = trust.get("total", 0) or 1
    brain_health_score = round((satisfied / total) * 100)
    sources = health.get("sources") or {}
    freshness_values = [v.get("freshness_minutes") for v in sources.values()
                       if isinstance(v, dict) and isinstance(v.get("freshness_minutes"), (int, float))]
    max_freshness = max(freshness_values) if freshness_values else None
    drift_score = drift.get("overall_drift_score", 0.0)
    avg_score = explanation.get("avg_brain_score")
    confidence = round(avg_score / 100, 3) if isinstance(avg_score, (int, float)) else round(satisfied / total, 3)
    return {
        "brain_health_score": brain_health_score,
        "data_freshness_minutes": max_freshness,
        "drift_score": drift_score,
        "confidence": confidence,
    }


def _build_topology(obs: dict) -> dict:
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
            "metric": {"primary_value": primary_value,
                      "primary_label": primary_label,
                      "yesterday_change": yesterday_change},
            "detail": {"description": description,
                      "related_data_health_keys": list(related or [])},
        }

    nodes = [
        _node("input_price", "input", "가격",
              _agg_status("yfinance", "kis"), _agg_freshness("yfinance", "kis"),
              "신선도(분)", description="yfinance + KIS 실시간 가격",
              related=["yfinance", "kis"]),
        _node("input_financials", "input", "재무",
              _agg_status("dart", "sec_edgar"), _agg_freshness("dart", "sec_edgar"),
              "신선도(분)", description="DART/SEC 재무제표",
              related=["dart", "sec_edgar"]),
        _node("input_macro", "input", "매크로",
              _agg_status("fred", "ecos"), _agg_freshness("fred", "ecos"),
              "신선도(분)", description="FRED/ECOS 매크로 지표",
              related=["fred", "ecos"]),
        _node("input_news", "input", "뉴스",
              "warning" if "news_sentiment_avg" in drifted else "ok",
              0, "drift" if "news_sentiment_avg" in drifted else "정상",
              description="RSS / sentiment", related=["news"]),
        _node("input_sector", "input", "섹터",
              _agg_status("krx_open_api"), _agg_freshness("krx_open_api"),
              "신선도(분)", description="KRX OpenAPI 섹터 데이터",
              related=["krx_open_api"]),
        _node("engine_fact", "engine", "Fact",
              "ok" if avg_score else "unknown", avg_score or 0,
              "avg Brain Score", yesterday_change=vs_yesterday.get("score_change", 0),
              description="multi_factor / consensus / prediction / backtest",
              related=["recommendations"]),
        _node("engine_sentiment", "engine", "Sentiment",
              "warning" if "news_sentiment_avg" in drifted else "ok",
              0, "신호", description="news / x sentiment / market mood",
              related=["news"]),
        _node("engine_risk", "engine", "Risk",
              "warning" if _has_neg("red_flags", "macro_override_active") else "ok",
              0, "필터", description="red_flags / macro_override / panic_stage",
              related=["macro"]),
        _node("engine_vci", "engine", "VCI",
              "warning" if _has_neg("vci_extreme") else "ok",
              0, "VCI", description="Verity Contrarian Index — fact↔sentiment 괴리",
              related=[]),
        _node("output_score", "output", "Brain Score",
              "ok" if avg_score else "unknown", avg_score or 0,
              "0~100", yesterday_change=vs_yesterday.get("score_change", 0),
              description="평균 Brain Score (포트폴리오 전체)", related=[]),
        _node("output_grade", "output", "Grade",
              "ok", 0, "5단계",
              description="STRONG_BUY / BUY / WATCH / CAUTION / AVOID", related=[]),
        _node("output_confidence", "output", "Confidence",
              "ok", 0, "0~1",
              description="Brain Score 평균 / 100", related=[]),
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
    node_health = {n["id"]: n["health"] for n in nodes}
    order = {"ok": 0, "warning": 1, "critical": 2, "unknown": 1}
    for e in edges:
        a, b = node_health.get(e["from"], "unknown"), node_health.get(e["to"], "unknown")
        e["health"] = a if order.get(a, 0) >= order.get(b, 0) else b
    return {"nodes": nodes, "edges": edges}


def handle_brain_health(request_handler) -> dict:
    portfolio = fetch_portfolio()
    if not portfolio:
        return {"_status": 503, "_body": {"error": "portfolio_unavailable"}}
    obs = get_observability(portfolio)
    if not obs:
        return {"_status": 200, "_body": {
            "kpi": {"brain_health_score": None, "data_freshness_minutes": None,
                   "drift_score": 0, "confidence": None},
            "data_health_meta": {}, "drift_meta": {}, "trust": {},
            "topology": _build_topology({}), "alerts": [],
            "checked_at": None, "status": "no_observability_data",
            "hint": "main.py full 모드 아직 미실행 — 첫 cron 후 데이터 누적",
        }}
    return {"_status": 200, "_body": {
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
        "alerts": [],
        "checked_at": obs.get("checked_at"),
    }}


# ──────────────────────────────────────────────────────────────────────
# data_health
# ──────────────────────────────────────────────────────────────────────

def handle_data_health(request_handler) -> dict:
    portfolio = fetch_portfolio()
    if not portfolio:
        return {"_status": 503, "_body": {"error": "portfolio_unavailable"}}
    obs = get_observability(portfolio)
    health = obs.get("data_health") or {}
    sources = health.get("sources") or {}
    rows = []
    for src, meta in sources.items():
        if not isinstance(meta, dict):
            continue
        rows.append({
            "source": src,
            "status": meta.get("status"),
            "freshness_minutes": meta.get("freshness_minutes"),
            "latency_ms_p50": meta.get("latency_ms_p50"),
            "missing_pct": meta.get("missing_pct"),
            "success_count_7d": meta.get("success_count_7d"),
            "failure_count_7d": meta.get("failure_count_7d"),
            "detail": meta.get("detail", ""),
        })
    order = {"critical": 0, "warning": 1, "ok": 2, "unknown": 3}
    rows.sort(key=lambda r: order.get(r.get("status") or "unknown", 4))
    return {"_status": 200, "_body": {
        "rows": rows,
        "overall_status": health.get("overall_status"),
        "core_sources_ok": health.get("core_sources_ok"),
        "checked_at": obs.get("checked_at"),
    }}


# ──────────────────────────────────────────────────────────────────────
# drift
# ──────────────────────────────────────────────────────────────────────

def handle_drift(request_handler) -> dict:
    portfolio = fetch_portfolio()
    if not portfolio:
        return {"_status": 503, "_body": {"error": "portfolio_unavailable"}}
    obs = get_observability(portfolio)
    drift = obs.get("drift") or {}
    explanation = obs.get("explanation") or {}
    bars = []
    for feature, info in (drift.get("feature_drifts") or {}).items():
        if not isinstance(info, dict):
            continue
        bars.append({
            "feature": feature,
            "psi": info.get("psi"),
            "level": info.get("level"),
            "yesterday": info.get("yesterday"),
            "today": info.get("today"),
        })
    bars.sort(key=lambda b: b.get("psi") or 0, reverse=True)
    return {"_status": 200, "_body": {
        "level": drift.get("level"),
        "overall_drift_score": drift.get("overall_drift_score"),
        "drifted_features": drift.get("drifted_features", []),
        "comparable_count": drift.get("comparable_count", 0),
        "feature_psi_bars": bars,
        "explanation": {
            "avg_brain_score": explanation.get("avg_brain_score"),
            "positive_top5": explanation.get("positive_contributors", [])[:5],
            "negative_top5": explanation.get("negative_contributors", [])[:5],
            "vs_yesterday": explanation.get("vs_yesterday", {}),
        },
        "checked_at": obs.get("checked_at"),
    }}


# ──────────────────────────────────────────────────────────────────────
# trust
# ──────────────────────────────────────────────────────────────────────

def handle_trust(request_handler) -> dict:
    portfolio = fetch_portfolio()
    if not portfolio:
        return {"_status": 503, "_body": {"error": "portfolio_unavailable"}}
    obs = get_observability(portfolio)
    trust = obs.get("trust") or {}
    meta = portfolio.get("reports_meta") if isinstance(portfolio, dict) else None
    recent_pdfs = meta[-10:] if isinstance(meta, list) else []
    return {"_status": 200, "_body": {
        "verdict": trust.get("verdict"),
        "recommendation": trust.get("recommendation"),
        "satisfied": trust.get("satisfied"),
        "total": trust.get("total", 8),
        "conditions": trust.get("conditions", {}),
        "details": trust.get("details", {}),
        "blocking_reasons": trust.get("blocking_reasons", []),
        "recent_pdfs": recent_pdfs,
        "checked_at": obs.get("checked_at"),
    }}


# ──────────────────────────────────────────────────────────────────────
# explain (model health)
# ──────────────────────────────────────────────────────────────────────

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
    vb = portfolio.get("verity_brain") or {}
    bq = vb.get("brain_quality") or {}
    bs = portfolio.get("backtest_stats") or {}
    return {
        "brain_quality_score": bq.get("score"),
        "brain_quality_components": bq.get("components", {}),
        "buy_hit_rate": (bs.get("grades", {}).get("BUY", {}) or {}).get("hit_rate"),
        "avoid_avg_return": (bs.get("grades", {}).get("AVOID", {}) or {}).get("avg_return"),
    }


def handle_explain(request_handler) -> dict:
    portfolio = fetch_portfolio()
    if not portfolio:
        return {"_status": 503, "_body": {"error": "portfolio_unavailable"}}
    obs = get_observability(portfolio)
    explanation = obs.get("explanation") or {}
    return {"_status": 200, "_body": {
        "avg_brain_score": explanation.get("avg_brain_score"),
        "grade_distribution": _grade_distribution(portfolio),
        "brain_score_histogram": _brain_score_histogram(portfolio),
        "hit_rate": _hit_rate_30d(portfolio),
        "ai_disagreements": _ai_disagreements(portfolio),
        "positive_contributors": explanation.get("positive_contributors", []),
        "negative_contributors": explanation.get("negative_contributors", []),
        "checked_at": obs.get("checked_at"),
    }}


# ──────────────────────────────────────────────────────────────────────
# Router
# ──────────────────────────────────────────────────────────────────────

ROUTES = {
    "brain_health": handle_brain_health,
    "data_health": handle_data_health,
    "drift": handle_drift,
    "trust": handle_trust,
    "explain": handle_explain,
}


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        write_options(self)

    def do_GET(self):
        ok, reason = authorize(headers_to_dict(self))
        if not ok:
            write_response(self, 401, {"error": "unauthorized", "reason": reason})
            return

        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        endpoint = (params.get("type", [""])[0] or "").strip()

        fn = ROUTES.get(endpoint)
        if not fn:
            write_response(self, 400, {
                "error": "unknown_endpoint",
                "valid": list(ROUTES.keys()),
                "hint": "use ?type=brain_health|data_health|drift|trust|explain",
            })
            return

        try:
            result = fn(self)
            write_response(self, result.get("_status", 200), result.get("_body") or {})
        except Exception as e:  # noqa: BLE001
            _logger.error("admin %s error: %s", endpoint, e, exc_info=True)
            write_response(self, 500, {"error": "internal", "endpoint": endpoint})
