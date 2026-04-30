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
    "PORTFOLIO_URL",
    "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json",
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
    """VERITY Brain 풀 토폴로지 — 모든 데이터 소스 + fact_score 13 + 엔진 + 출력.

    sub_cluster 로 input 을 5 그룹 분리 (price/financial/macro/news/ai).
    """
    health = obs.get("data_health") or {}
    sources = health.get("sources") or {}
    drift = obs.get("drift") or {}
    drifted = set(drift.get("drifted_features") or [])
    explanation = obs.get("explanation") or {}
    vs_yesterday = explanation.get("vs_yesterday") or {}
    avg_score = explanation.get("avg_brain_score")
    negs_set = {n.get("feature") for n in (explanation.get("negative_contributors") or [])}

    def _src_status(key):
        v = sources.get(key)
        if isinstance(v, dict) and v.get("status"):
            return v["status"]
        return "unknown"

    def _src_fresh(key):
        v = sources.get(key)
        if isinstance(v, dict) and isinstance(v.get("freshness_minutes"), (int, float)):
            return v["freshness_minutes"]
        return None

    def _node(id, cluster, sub, label, health_status,
              primary_value=0, primary_label="", yesterday_change=0,
              description="", related=None):
        return {
            "id": id, "cluster": cluster, "sub_cluster": sub, "label": label,
            "health": health_status,
            "health_score": _HEALTH_TO_SCORE.get(health_status, 50),
            "metric": {"primary_value": primary_value,
                      "primary_label": primary_label,
                      "yesterday_change": yesterday_change},
            "detail": {"description": description,
                      "related_data_health_keys": list(related or [])},
        }

    nodes = []

    # ── INPUT — 데이터 소스 (sub_cluster 5 분류) ──
    # price (5)
    for src, label in [("yfinance", "yfinance"), ("kis", "KIS"),
                       ("krx_open_api", "KRX"), ("polygon", "Polygon"),
                       ("finnhub", "Finnhub")]:
        nodes.append(_node(f"src_{src}", "input", "price", label,
                          _src_status(src), _src_fresh(src) or 0, "신선도(분)",
                          description=f"{label} 실시간 가격 데이터", related=[src]))

    # financial (3)
    for src, label, desc in [
        ("dart", "DART", "DART 재무제표 (KR)"),
        ("sec_edgar", "SEC", "SEC EDGAR (US)"),
        ("kipris", "KIPRIS", "특허 데이터")]:
        nodes.append(_node(f"src_{src}", "input", "financial", label,
                          _src_status(src), _src_fresh(src) or 0, "신선도(분)",
                          description=desc, related=[src]))

    # macro (3)
    for src, label, desc in [
        ("fred", "FRED", "미국 매크로 (Fed)"),
        ("ecos", "ECOS", "한국은행 ECOS"),
        ("public_data", "공공데이터", "공공데이터 포털")]:
        nodes.append(_node(f"src_{src}", "input", "macro", label,
                          _src_status(src), _src_fresh(src) or 0, "신선도(분)",
                          description=desc, related=[src]))

    # news/sentiment (2)
    nodes.append(_node("src_rss", "input", "news", "뉴스 RSS",
                      "warning" if "news_sentiment_avg" in drifted else "ok",
                      0, "감성 drift" if "news_sentiment_avg" in drifted else "정상",
                      description="Bloomberg/Google 헤드라인 + sentiment", related=["news"]))
    nodes.append(_node("src_x", "input", "news", "X(Twitter)",
                      "ok", 0, "social",
                      description="X 종목 멘션 sentiment", related=["x_sentiment"]))

    # AI (4)
    for src, label, desc in [
        ("gemini", "Gemini", "Google Gemini Flash/Pro"),
        ("anthropic", "Claude", "Anthropic Claude Haiku/Sonnet"),
        ("perplexity", "Perplexity", "sonar-pro 리스크 조사"),
        ("telegram", "Telegram", "알림 발송 채널")]:
        nodes.append(_node(f"src_{src}", "input", "ai", label,
                          _src_status(src), _src_fresh(src) or 0, "신선도(분)",
                          description=desc, related=[src]))

    # ── ENGINE — fact_score 13 + sentiment/risk/vci/xgb (17) ──
    # fact_score 13 (verity_constitution weights 순)
    fact_components = [
        ("multi_factor", "Multi-Factor", 0.1876, "P/E + P/B + ROE + Momentum"),
        ("consensus", "Consensus", 0.1279, "Gemini ↔ Claude 합치"),
        ("prediction", "Prediction", 0.0853, "XGBoost 5일 상승확률"),
        ("backtest", "Backtest", 0.0682, "30일 white-box 적중률"),
        ("timing", "Timing", 0.0597, "RSI/MACD/볼린저"),
        ("commodity_margin", "Commodity", 0.0341, "원자재-마진 영향"),
        ("export_trade", "Export", 0.0682, "수출 의존도 기반"),
        ("moat_quality", "Moat", 0.0853, "경제적 해자 (Buffett)"),
        ("graham_value", "Graham", 0.0682, "벤저민 그레이엄 가치"),
        ("canslim_growth", "CANSLIM", 0.0682, "윌리엄 오닐 성장"),
        ("analyst_report", "Analyst", 0.0784, "애널리스트 컨센서스"),
        ("dart_health", "DART Health", 0.049, "재무 건전성"),
        ("perplexity_risk", "PPL Risk", 0.02, "Perplexity 리스크"),
    ]
    for fid, label, weight, desc in fact_components:
        h = "warning" if fid in negs_set else ("ok" if avg_score else "unknown")
        nodes.append(_node(f"eng_{fid}", "engine", "fact_score", label, h,
                          weight, f"weight {weight:.2%}",
                          description=desc, related=[]))

    # 추가 엔진 (4)
    nodes.append(_node("eng_sentiment", "engine", "signal", "Sentiment",
                      "warning" if "news_sentiment_avg" in drifted else "ok",
                      0, "news+x+mood", description="뉴스/X/마켓 무드 통합", related=["news"]))
    nodes.append(_node("eng_risk", "engine", "signal", "Risk Filter",
                      "warning" if any(f in negs_set for f in ("red_flags", "macro_override_active")) else "ok",
                      0, "필터",
                      description="red_flags / macro_override / panic_stage",
                      related=["macro"]))
    nodes.append(_node("eng_vci", "engine", "signal", "VCI",
                      "warning" if "vci_extreme" in negs_set else "ok",
                      0, "comparator",
                      description="Verity Contrarian Index — fact↔sentiment 괴리",
                      related=[]))
    nodes.append(_node("eng_xgb", "engine", "signal", "XGBoost",
                      "ok" if avg_score else "unknown",
                      0, "ML 예측",
                      description="up_probability 5일 분류기",
                      related=["recommendations"]))

    # ── OUTPUT (5) ──
    nodes.append(_node("out_score", "output", "result", "Brain Score",
                      "ok" if avg_score else "unknown", avg_score or 0,
                      "0~100", yesterday_change=vs_yesterday.get("score_change", 0),
                      description="평균 Brain Score (포트폴리오)", related=[]))
    nodes.append(_node("out_grade", "output", "result", "Grade",
                      "ok", 0, "5단계",
                      description="STRONG_BUY / BUY / WATCH / CAUTION / AVOID",
                      related=[]))
    nodes.append(_node("out_confidence", "output", "result", "Confidence",
                      "ok", 0, "0~1", description="Brain Score / 100", related=[]))
    nodes.append(_node("out_vams", "output", "result", "VAMS Signal",
                      "ok", 0, "BUY/SELL/HOLD",
                      description="자동 매매 신호 (KIS broker)", related=["kis"]))
    nodes.append(_node("out_recs", "output", "result", "Recommendations",
                      "ok", 0, "52 종목",
                      description="포트폴리오 추천 종목 리스트", related=["recommendations"]))

    # ── EDGES — 데이터 흐름 (의미 있는 연결) ──
    edges = []

    # 가격 → multi_factor / prediction / timing / xgb / backtest
    for src in ("yfinance", "kis", "krx_open_api", "polygon", "finnhub"):
        for tgt, w in [("multi_factor", 0.9), ("prediction", 0.7),
                       ("timing", 0.6), ("backtest", 0.5)]:
            edges.append({"from": f"src_{src}", "to": f"eng_{tgt}", "strength": w})
        edges.append({"from": f"src_{src}", "to": "eng_xgb", "strength": 0.8})

    # 재무 → dart_health / graham_value / canslim_growth / moat_quality
    for src in ("dart", "sec_edgar"):
        for tgt, w in [("dart_health", 1.0), ("graham_value", 0.85),
                       ("canslim_growth", 0.8), ("moat_quality", 0.75),
                       ("analyst_report", 0.5)]:
            edges.append({"from": f"src_{src}", "to": f"eng_{tgt}", "strength": w})
    edges.append({"from": "src_kipris", "to": "eng_moat_quality", "strength": 0.6})

    # 매크로 → eng_risk + commodity / export
    for src in ("fred", "ecos", "public_data"):
        edges.append({"from": f"src_{src}", "to": "eng_risk", "strength": 0.85})
        edges.append({"from": f"src_{src}", "to": "eng_commodity_margin", "strength": 0.6})
        edges.append({"from": f"src_{src}", "to": "eng_export_trade", "strength": 0.6})

    # 뉴스 → sentiment / perplexity_risk
    edges.append({"from": "src_rss", "to": "eng_sentiment", "strength": 0.9})
    edges.append({"from": "src_x", "to": "eng_sentiment", "strength": 0.8})
    edges.append({"from": "src_rss", "to": "eng_perplexity_risk", "strength": 0.5})

    # AI → consensus / analyst_report / perplexity_risk
    edges.append({"from": "src_gemini", "to": "eng_consensus", "strength": 0.9})
    edges.append({"from": "src_anthropic", "to": "eng_consensus", "strength": 0.9})
    edges.append({"from": "src_gemini", "to": "eng_analyst_report", "strength": 0.7})
    edges.append({"from": "src_anthropic", "to": "eng_moat_quality", "strength": 0.5})
    edges.append({"from": "src_perplexity", "to": "eng_perplexity_risk", "strength": 1.0})

    # 엔진 내부 흐름: fact_score 13 → out_score
    for fid, _, _, _ in fact_components:
        edges.append({"from": f"eng_{fid}", "to": "out_score", "strength": 0.6})

    # signal 4 → vci → out_score
    edges.append({"from": "eng_sentiment", "to": "eng_vci", "strength": 0.8})
    edges.append({"from": "eng_xgb", "to": "eng_prediction", "strength": 0.9})
    edges.append({"from": "eng_xgb", "to": "out_score", "strength": 0.7})
    edges.append({"from": "eng_vci", "to": "out_score", "strength": 0.85})
    edges.append({"from": "eng_risk", "to": "out_score", "strength": 0.7})

    # 출력 흐름
    edges.append({"from": "out_score", "to": "out_grade", "strength": 1.0})
    edges.append({"from": "out_score", "to": "out_confidence", "strength": 1.0})
    edges.append({"from": "out_grade", "to": "out_vams", "strength": 0.9})
    edges.append({"from": "out_grade", "to": "out_recs", "strength": 1.0})

    # Telegram = 출력 알림 채널 (out_recs 연결로 표시)
    edges.append({"from": "src_telegram", "to": "out_vams", "strength": 0.5})

    # 에지 health = from/to 중 worst
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

def _rec_grade(r: dict) -> Optional[str]:
    """recommendation 의 grade — verity_brain.grade 가 정본, top-level 은 폴백."""
    vb = r.get("verity_brain") if isinstance(r, dict) else None
    if isinstance(vb, dict) and vb.get("grade"):
        return vb["grade"]
    return r.get("grade") if isinstance(r, dict) else None


def _rec_brain_score(r: dict) -> Optional[float]:
    vb = r.get("verity_brain") if isinstance(r, dict) else None
    if isinstance(vb, dict) and isinstance(vb.get("brain_score"), (int, float)):
        return vb["brain_score"]
    bs = r.get("brain_score") if isinstance(r, dict) else None
    return bs if isinstance(bs, (int, float)) else None


def _grade_distribution(portfolio: dict) -> dict:
    recs = portfolio.get("recommendations") or []
    grades = [g for g in (_rec_grade(r) for r in recs) if g]
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
        bs = _rec_brain_score(r)
        if bs is None:
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
