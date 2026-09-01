"""
Brain Observatory admin API — 단일 파일 통합 (Hobby 12 함수 제한 회피).

구 5개 파일을 통합:
  /api/admin?type=brain_health   ← brain_health.py
  /api/admin?type=data_health    ← data_health.py
  /api/admin?type=drift          ← drift.py
  /api/admin?type=explain        ← explain.py
  /api/admin?type=trust          ← trust.py

추가 라우트:
  /api/admin?type=member_management  ← 회원 관리(부관리자 지정=최종 관리자만, 2026-07-17)
  /api/admin?type=community_moderation · audit_log · growth_stats
  /api/admin?type=security           ← IP 침입 추적·차단 (Railway 미들웨어와 blocked_ips 공유)

인증: X-Admin-Token 또는 Bearer JWT (profiles.is_admin=true)
"""
from __future__ import annotations
# deploy-marker: 206 fix (2026-07-17)

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
    # 2026-05-24 VERITY-data private 전환 cutover — Vercel Blob 으로 이동.
    # raw.githubusercontent.com 은 private repo public fetch 불가 (404 → 503 portfolio_unavailable).
    # base=rte5guenhonw9fzn ([[project_repo_visibility_plan]]).
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/portfolio.json",
)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
ADMIN_BYPASS_TOKEN = os.environ.get("ADMIN_BYPASS_TOKEN", "")
# service_role = 관리자 운영 변경(회원 제재·삭제·글 삭제) 서버 실행용. RLS 우회 — authorize() 통과 후에만 사용.
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

_PORTFOLIO_CACHE: Dict[str, Any] = {"data": None, "fetched_at": 0}
_PORTFOLIO_TTL = 60

# ──────────────────────────────────────────────────────────────────────
# 요청 예산 (2026-08-23 신설)
#
# 🚨 왜 — 이 파일의 `vercel.json` maxDuration 은 **15초**인데, 인증된 요청 하나가 타는
#   외부 호출의 고정 타임아웃 합은 최악 **27초**였다(인증 5 + 관리자확인 6 + 감사로그 6 +
#   데이터조회 10). 개별 호출은 각자 예산 안이지만 **합이 함수 예산을 넘는다.**
#   그러면 상류가 조금만 느려질 때 우리 코드가 에러를 내기 전에 플랫폼이 먼저 끊어
#   **원인이 안 적힌 504** 가 나간다. 화면은 "왜 안 되는지 모름" 상태가 된다.
#   (실측 2026-08-23: 평시 쿼리 합 1.96s 라 아직 안 터진다 — 지금 고치는 건 잠재 결함이다.)
#
# 해법 = 요청 시작 시각을 기준으로 **남은 예산 안으로 매 호출 타임아웃을 깎는다.**
#   예산이 바닥나면 504 를 기다리지 않고 **어느 단계에서 막혔는지 담아 503** 으로 끝낸다.
_REQ_BUDGET_SEC = float(os.environ.get("ADMIN_REQ_BUDGET_SEC", "12") or "12")  # maxDuration 15 - 여유 3
_MIN_TMO = 0.6          # 이보다 적게 남았으면 시도 자체가 무의미
_budget: Dict[str, Any] = {"t0": 0.0, "stage": "start"}


class _BudgetExceeded(Exception):
    """요청 예산 소진 — 플랫폼 504 대신 우리가 원인을 적어 끝낸다."""

    def __init__(self, stage: str, spent: float):
        super().__init__(f"budget exceeded at {stage} ({spent:.1f}s)")
        self.stage = stage
        self.spent = spent


def _budget_start() -> None:
    _budget["t0"] = time.monotonic()
    _budget["stage"] = "start"


def _budget_timeout_response(h: Any, e: "_BudgetExceeded", endpoint: str) -> None:
    """예산 소진 → 503. 🚨 504 와 달리 **어디서 막혔는지** 화면이 읽을 수 있다.

    504 는 플랫폼이 함수를 끊은 것이라 본문이 없다 — 관리자 화면에 "왜 안 되는지 모름" 만
    남는다(2026-08-23 PM 신고가 정확히 그 상태였다). 여기서는 단계·경과·예산을 실어 보낸다.
    """
    _logger.error("admin budget exceeded: endpoint=%s stage=%s spent=%.1fs",
                  endpoint, e.stage, e.spent)
    write_response(h, 503, {
        "error": "upstream_slow",
        "endpoint": endpoint,
        "stage": e.stage,
        "spent_sec": round(e.spent, 1),
        "budget_sec": _REQ_BUDGET_SEC,
        "detail": "상류 응답이 느려 요청 예산 안에 끝내지 못했어요. 잠시 후 다시 시도해 주세요.",
    })


def _stage(name: str) -> None:
    """현재 단계 표시 — 예산 소진 시 응답에 실린다."""
    _budget["stage"] = name


def _t(want: float) -> float:
    """남은 예산 안으로 요청 타임아웃을 깎는다.

    🚨 `timeout=_t(10)` 을 그대로 쓰면 앞 단계가 8초를 먹었을 때 합이 18초가 되어 함수가 죽는다.
    남은 시간이 `_MIN_TMO` 미만이면 호출하지 않고 예산 소진으로 끝낸다.
    """
    if not _budget["t0"]:      # 진입점 밖(모듈 로드·테스트) — 예산 미적용
        return want
    spent = time.monotonic() - _budget["t0"]
    left = _REQ_BUDGET_SEC - spent
    if left < _MIN_TMO:
        raise _BudgetExceeded(_budget["stage"], spent)
    return max(_MIN_TMO, min(float(want), left))

# 2026-07-23 VERITY↔AlphaNest 분리 Stage 1: 오퍼레이터 full portfolio = private Supabase Storage.
# 공개 blob(sanitize 예정)과 별도. fetch_portfolio 가 이 private 소스 우선, 미populate/실패 시 공개 blob fallback.
OPERATOR_BUCKET = os.environ.get("OPERATOR_BUCKET", "verity-reports")
OPERATOR_PORTFOLIO_PATH = os.environ.get("OPERATOR_PORTFOLIO_PATH", "_operator/portfolio_full.json")


def _download_operator_file(path: str) -> Optional[Any]:
    """private Supabase Storage 에서 오퍼레이터 파일 다운로드 (service_role). 없으면 None → 공개 fallback.
    분리 Stage 1(portfolio) + Stage 3 후속(history/system_health/brain_kb/admin_todos) 공용."""
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return None
    try:
        r = requests.get(
            f"{SUPABASE_URL}/storage/v1/object/{OPERATOR_BUCKET}/{path}",
            headers={"apikey": SUPABASE_SERVICE_ROLE_KEY,
                     "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"},
            timeout=_t(10),
        )
        if r.status_code == 200:
            return r.json()
        if r.status_code != 404:
            _logger.warning("operator file %s fetch %s", path, r.status_code)
    except (requests.RequestException, ValueError) as e:
        _logger.warning("operator file %s fetch failed: %s", path, e)
    return None


def _download_operator_portfolio() -> Optional[dict]:
    """full portfolio (분리 Stage 1). private 우선, 미populate 시 None → 공개 blob fallback."""
    return _download_operator_file(OPERATOR_PORTFOLIO_PATH)


def fetch_portfolio() -> Optional[dict]:
    now = time.time()
    if _PORTFOLIO_CACHE["data"] and (now - _PORTFOLIO_CACHE["fetched_at"] < _PORTFOLIO_TTL):
        return _PORTFOLIO_CACHE["data"]
    # 2026-07-23 분리 Stage 1: private bucket(full·오퍼레이터) 우선. 미populate/실패 시 공개 blob fallback
    # (전환기 무파손 — 공개 blob sanitize 전엔 둘 다 full, 후엔 private 만 full 유지).
    data = _download_operator_portfolio()
    if data is None:
        try:
            r = requests.get(PORTFOLIO_URL, timeout=_t(10))
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException, ValueError) as e:
            _logger.warning("portfolio fetch failed: %s", e)
            return _PORTFOLIO_CACHE["data"]
    _PORTFOLIO_CACHE["data"] = data
    _PORTFOLIO_CACHE["fetched_at"] = now
    return data


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
            timeout=_t(5),
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
            timeout=_t(5),
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
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Admin-Token")
    handler.end_headers()
    handler.wfile.write(payload)


def write_options(handler) -> None:
    handler.send_response(200)
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
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


def _build_topology(obs: dict, portfolio: Optional[dict] = None) -> dict:
    """알파브레인 토폴로지 — 발행 산출물의 실효 fact 가중을 우선한다.

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

    # ── ENGINE — 발행 산출물이 신고한 실효 fact 가중 + 신호 엔진 ──
    _fact_labels = {
        "graham_value": ("Graham", "그레이엄 가치·안전마진"),
        "canslim_growth": ("CANSLIM", "오닐 CANSLIM 성장·상대강도"),
        "quant_quality": ("Quality", "Piotroski·Novy-Marx·Altman 퀄리티"),
        "quant_volatility": ("Low Vol", "실현변동성·베타·고유변동성"),
    }
    effective_weights: Dict[str, float] = {}
    weight_source = "constitution_fallback"
    for rec in ((portfolio or {}).get("recommendations") or []):
        fact = ((rec.get("verity_brain") or {}).get("fact_score") or {}) if isinstance(rec, dict) else {}
        candidate = fact.get("weights_effective") or {}
        if isinstance(candidate, dict):
            effective_weights = {
                str(k): float(v) for k, v in candidate.items()
                if k in _fact_labels and isinstance(v, (int, float)) and v > 0
            }
        if effective_weights:
            weight_source = "issued.weights_effective"
            break
    if not effective_weights:
        effective_weights = {
            "graham_value": 0.28,
            "canslim_growth": 0.19,
            "quant_quality": 0.28,
            "quant_volatility": 0.25,
        }
    fact_components = [
        (fid, _fact_labels[fid][0], weight, _fact_labels[fid][1])
        for fid, weight in effective_weights.items()
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

    # 가격 → CANSLIM / 저변동 / XGBoost 관측
    for src in ("yfinance", "kis", "krx_open_api", "polygon", "finnhub"):
        for tgt, w in [("canslim_growth", 0.8), ("quant_volatility", 0.9)]:
            edges.append({"from": f"src_{src}", "to": f"eng_{tgt}", "strength": w})
        edges.append({"from": f"src_{src}", "to": "eng_xgb", "strength": 0.8})

    # 재무 → 현재 활성 가치·성장·퀄리티
    for src in ("dart", "sec_edgar"):
        for tgt, w in [("graham_value", 0.9), ("canslim_growth", 0.8),
                       ("quant_quality", 1.0)]:
            edges.append({"from": f"src_{src}", "to": f"eng_{tgt}", "strength": w})

    # 매크로 → 리스크 필터
    for src in ("fred", "ecos", "public_data"):
        edges.append({"from": f"src_{src}", "to": "eng_risk", "strength": 0.85})

    # 뉴스 → sentiment
    edges.append({"from": "src_rss", "to": "eng_sentiment", "strength": 0.9})
    edges.append({"from": "src_x", "to": "eng_sentiment", "strength": 0.8})

    # 엔진 내부 흐름: 실효 fact 축 → out_score
    for fid, _, _, _ in fact_components:
        edges.append({"from": f"eng_{fid}", "to": "out_score", "strength": 0.6})

    # signal 4 → vci → out_score
    edges.append({"from": "eng_sentiment", "to": "eng_vci", "strength": 0.8})
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

    return {
        "nodes": nodes,
        "edges": edges,
        "fact_axis_count": len(fact_components),
        "fact_axis_source": weight_source,
    }


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
            "topology": _build_topology({}, portfolio), "alerts": [],
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
        "topology": _build_topology(obs, portfolio),
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
    # 결정-trail 무결성 (main.py STEP 9.52 산출, 2026-06-13). slim 으로 노출.
    ti = portfolio.get("trail_integrity") if isinstance(portfolio, dict) else None
    trail_integrity = None
    if isinstance(ti, dict):
        h = ti.get("history") or {}
        trail_integrity = {
            "severity": ti.get("severity"),
            "findings": ti.get("findings", []),
            "checked_at": ti.get("ts_kst"),
            "history_snapshots": h.get("snapshot_count"),
            "history_gaps": h.get("business_day_gaps", []),
            "rec_field_count": h.get("latest_rec_field_count"),
            "latest_parseable": h.get("latest_parseable"),
            "trails": [
                {"name": t.get("trail"), "size": t.get("size"), "ok": t.get("ok")}
                for t in (ti.get("trails") or [])
            ],
            "gate_progress": ti.get("gate_progress") or [],
        }
    return {"_status": 200, "_body": {
        "verdict": trust.get("verdict"),
        "recommendation": trust.get("recommendation"),
        "satisfied": trust.get("satisfied"),
        "total": trust.get("total", 8),
        "conditions": trust.get("conditions", {}),
        "details": trust.get("details", {}),
        "blocking_reasons": trust.get("blocking_reasons", []),
        "recent_pdfs": recent_pdfs,
        "trail_integrity": trail_integrity,
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


# ══════════════════════════════════════════════════════════════════════
# 관리자 운영 (회원 관리 + 커뮤니티 모더레이션) — service_role 실행
# authorize()(is_admin/bypass) 통과 후에만 도달. 모든 변경 = admin_audit_log 기록.
# 제재(ban) = 쓰기 차단(023 트리거). 삭제 = UI 2단계 확인 후 auth 계정 제거(cascade). (PM 2026-07-15)
# ══════════════════════════════════════════════════════════════════════

def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _svc_headers(extra: Optional[dict] = None) -> Dict[str, str]:
    h = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def _svc_ready() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


def _read_body(handler) -> dict:
    try:
        n = int(handler.headers.get("Content-Length", 0) or 0)
        if n <= 0:
            return {}
        raw = handler.rfile.read(n)
        return json.loads(raw.decode("utf-8")) if raw else {}
    except (ValueError, json.JSONDecodeError):
        return {}


def _caller_identity(headers_dict: Dict[str, str]) -> Dict[str, Optional[str]]:
    # 감사 로그 actor — Bearer JWT 경로면 id/email, bypass_token 경로면 unknown.
    auth = headers_dict.get("authorization") or ""
    if not auth.lower().startswith("bearer ") or not SUPABASE_URL:
        return {"id": None, "email": None}
    jwt = auth.split(" ", 1)[1].strip()
    try:
        r = requests.get(f"{SUPABASE_URL}/auth/v1/user",
                         headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {jwt}"}, timeout=_t(5))
        if r.status_code == 200:
            u = r.json()
            return {"id": u.get("id"), "email": u.get("email")}
    except (requests.RequestException, ValueError):
        pass
    return {"id": None, "email": None}


def _is_super_admin(user_id: Optional[str]) -> bool:
    # 최종 관리자(super) 여부 — profiles.is_super_admin. 부관리자 지정/해제 권한 게이트.
    if not user_id or not _svc_ready():
        return False
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/profiles", headers=_svc_headers(),
                         params={"id": f"eq.{user_id}", "select": "is_super_admin"}, timeout=_t(6))
        if r.status_code == 200:
            rows = r.json()
            return bool(rows and rows[0].get("is_super_admin") is True)
    except requests.RequestException:
        pass
    return False


def _audit(actor: dict, action: str, target_type: str, target_id: Optional[str], detail: Optional[dict] = None) -> None:
    if not _svc_ready():
        return
    try:
        requests.post(f"{SUPABASE_URL}/rest/v1/admin_audit_log",
                      headers=_svc_headers({"Prefer": "return=minimal"}),
                      json={"actor_id": actor.get("id"), "actor_email": actor.get("email"),
                            "action": action, "target_type": target_type,
                            "target_id": str(target_id) if target_id else None,
                            "detail": detail or {}}, timeout=_t(6))
    except requests.RequestException as e:
        _logger.warning("audit write failed: %s", e)


def handle_member_management(handler, method: str, body: dict) -> dict:
    if not _svc_ready():
        return {"_status": 503, "_body": {"error": "service_role_unconfigured"}}
    actor = _caller_identity(headers_to_dict(handler))

    if method == "GET":
        params = parse_qs(urlparse(handler.path).query)
        q = (params.get("q", [""])[0] or "").strip()
        limit = min(200, max(1, int((params.get("limit", ["100"])[0] or "100"))))
        offset = max(0, int((params.get("offset", ["0"])[0] or "0")))
        sel = "id,email,display_name,nickname,status,is_admin,is_super_admin,is_banned,ban_reason,banned_at,created_at"
        qp = {"select": sel, "order": "created_at.desc", "limit": str(limit), "offset": str(offset)}
        if q:
            qp["or"] = f"(email.ilike.*{q}*,nickname.ilike.*{q}*,display_name.ilike.*{q}*)"
        r = requests.get(f"{SUPABASE_URL}/rest/v1/profiles",
                         headers=_svc_headers({"Prefer": "count=exact"}), params=qp, timeout=_t(10))
        # PostgREST count=exact + 부분범위(limit<total) = 206 Partial Content(정상). 206 도 성공으로 수용.
        if r.status_code not in (200, 206):
            return {"_status": 502, "_body": {"error": "list_failed", "detail": r.text[:200]}}
        total = None
        cr = r.headers.get("Content-Range", "")
        if "/" in cr:
            try:
                total = int(cr.split("/")[-1])
            except ValueError:
                pass
        return {"_status": 200, "_body": {"members": r.json(), "total": total, "caller_is_super": _is_super_admin(actor.get("id"))}}

    if method == "POST":
        action = str(body.get("action", "")).strip()
        uid = str(body.get("user_id", "")).strip()
        if not uid:
            return {"_status": 400, "_body": {"error": "user_id_required"}}
        if action == "ban":
            patch = {"is_banned": True, "ban_reason": str(body.get("reason", "")).strip()[:500], "banned_at": _now_iso()}
            audit_action = "ban_user"
        elif action == "unban":
            patch = {"is_banned": False, "ban_reason": None, "banned_at": None}
            audit_action = "unban_user"
        elif action == "update":
            patch = {}
            for k in ("nickname", "status", "bio", "display_name"):
                if k in body:
                    patch[k] = body[k]
            if "is_admin" in body:
                # 부관리자 지정/해제 = 최종 관리자(super)만. (부관리자는 나머지 권한 동일하나 이것만 불가.)
                if not _is_super_admin(actor.get("id")):
                    return {"_status": 403, "_body": {"error": "super_admin_only", "detail": "부관리자 지정/해제는 최종 관리자만 가능해요"}}
                patch["is_admin"] = bool(body["is_admin"])
            # is_super_admin 은 API 로 변경 불가 (마이그레이션/DB 콘솔 전용) — 화이트리스트에 없어 자동 차단.
            if not patch:
                return {"_status": 400, "_body": {"error": "no_fields"}}
            audit_action = "update_profile"
        else:
            return {"_status": 400, "_body": {"error": "unknown_action", "valid": ["ban", "unban", "update"]}}
        r = requests.patch(f"{SUPABASE_URL}/rest/v1/profiles",
                           headers=_svc_headers({"Prefer": "return=representation"}),
                           params={"id": f"eq.{uid}"}, json=patch, timeout=_t(10))
        if r.status_code not in (200, 204):
            return {"_status": 502, "_body": {"error": "update_failed", "detail": r.text[:200]}}
        _audit(actor, audit_action, "user", uid, patch)
        rows = r.json() if r.text else []
        return {"_status": 200, "_body": {"ok": True, "member": rows[0] if rows else None}}

    if method == "DELETE":
        # 완전 삭제 = auth 계정 제거 → profiles·user_thesis cascade. UI 2단계 확인(confirm) 후 호출.
        uid = str(body.get("user_id", "")).strip()
        if not uid or not body.get("confirm"):
            return {"_status": 400, "_body": {"error": "user_id_and_confirm_required"}}
        r = requests.delete(f"{SUPABASE_URL}/auth/v1/admin/users/{uid}", headers=_svc_headers(), timeout=_t(10))
        if r.status_code not in (200, 204):
            return {"_status": 502, "_body": {"error": "delete_failed", "detail": r.text[:200]}}
        _audit(actor, "delete_user", "user", uid, {"email": body.get("email")})
        return {"_status": 200, "_body": {"ok": True, "deleted": uid}}

    return {"_status": 405, "_body": {"error": "method_not_allowed"}}


def _visit_stats_from_rows(rows: list, now: Any) -> dict:
    """익명 방문 일별 행을 KST 날짜 기준 관리자 집계로 변환한다."""
    from datetime import date, timedelta

    today = now.date()
    start_7 = today - timedelta(days=6)
    start_30 = today - timedelta(days=29)
    by_day: Dict[str, set] = {}
    days_by_visitor: Dict[str, set] = {}
    visits_30d = 0
    for row in rows if isinstance(rows, list) else []:
        visitor = str((row or {}).get("visitor_id") or "")
        day_text = str((row or {}).get("visit_date") or "")[:10]
        if not visitor or len(day_text) != 10:
            continue
        try:
            day = date.fromisoformat(day_text)
        except ValueError:
            continue
        if day < start_30 or day > today:
            continue
        by_day.setdefault(day_text, set()).add(visitor)
        days_by_visitor.setdefault(visitor, set()).add(day_text)
        try:
            visits_30d += max(0, int((row or {}).get("visit_count") or 0))
        except (TypeError, ValueError):
            pass

    visitors_30d = len(days_by_visitor)
    returning = sum(1 for days in days_by_visitor.values() if len(days) >= 2)
    daily = []
    for i in range(29, -1, -1):
        day_text = (today - timedelta(days=i)).isoformat()
        daily.append({"date": day_text, "count": len(by_day.get(day_text, set()))})
    return {
        "status": "measured",
        "today": len(by_day.get(today.isoformat(), set())),
        "d7": len({v for v, days in days_by_visitor.items() if any(d >= start_7.isoformat() for d in days)}),
        "d30": visitors_30d,
        "returning_30d": returning,
        "return_rate_30d_pct": round(returning / visitors_30d * 100, 1) if visitors_30d else None,
        "visitor_days_30d": sum(len(days) for days in days_by_visitor.values()),
        "visits_30d": visits_30d,
        "daily": daily,
    }


def handle_growth_stats(handler, method: str, body: dict) -> dict:
    # 성장·사용 통계 (AlphaNest 자체 데이터) — 익명 방문·가입 추이·회원·커뮤니티 활동. GET only.
    if not _svc_ready():
        return {"_status": 503, "_body": {"error": "service_role_unconfigured"}}
    if method != "GET":
        return {"_status": 405, "_body": {"error": "method_not_allowed"}}
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    d1 = (now - timedelta(days=1)).isoformat()
    d7 = (now - timedelta(days=7)).isoformat()
    d30 = (now - timedelta(days=30)).isoformat()

    def _count(table: str, extra=None):
        params = {"select": "id", "limit": "1"}
        if extra:
            params.update(extra)
        try:
            r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=_svc_headers({"Prefer": "count=exact"}), params=params, timeout=_t(10))
            cr = r.headers.get("Content-Range", "")
            if "/" in cr:
                return int(cr.split("/")[-1])
        except (requests.RequestException, ValueError):
            pass
        return None

    members = {
        "total": _count("profiles"),
        "d1": _count("profiles", {"created_at": f"gte.{d1}"}),
        "d7": _count("profiles", {"created_at": f"gte.{d7}"}),
        "d30": _count("profiles", {"created_at": f"gte.{d30}"}),
        "pending": _count("profiles", {"status": "eq.pending"}),
        "banned": _count("profiles", {"is_banned": "eq.true"}),
    }
    community = {
        "total": _count("user_thesis"),
        "public": _count("user_thesis", {"is_public": "eq.true", "hidden": "eq.false"}),
        "d7": _count("user_thesis", {"created_at": f"gte.{d7}"}),
    }

    # PublicSessionKeeper → record_site_visit RPC가 기록한 익명 일별 방문.
    # 페이지·검색어·종목·IP는 저장하지 않고 visitor_id와 KST 날짜만 집계한다.
    visitors = {
        "status": "unavailable",
        "today": None,
        "d7": None,
        "d30": None,
        "returning_30d": None,
        "return_rate_30d_pct": None,
        "visitor_days_30d": None,
        "visits_30d": None,
        "daily": [],
    }
    try:
        cutoff_date = (now - timedelta(days=29)).strftime("%Y-%m-%d")
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/site_visit_days",
            headers=_svc_headers(),
            params={
                "select": "visitor_id,visit_date,visit_count",
                "visit_date": f"gte.{cutoff_date}",
                "order": "visit_date.asc",
                "limit": "50000",
            },
            timeout=_t(10),
        )
        if r.status_code == 200:
            visitors = _visit_stats_from_rows(r.json() or [], now)
        elif r.status_code != 404:
            _logger.warning("site_visit_days fetch %s: %s", r.status_code, r.text[:200])
    except (requests.RequestException, ValueError) as e:
        _logger.warning("site_visit_days fetch failed: %s", e)

    # 최근 30일 일별 가입 (created_at 버킷팅)
    daily: Dict[str, int] = {}
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/profiles", headers=_svc_headers(),
                         params={"select": "created_at", "created_at": f"gte.{d30}", "limit": "5000"}, timeout=_t(10))
        if r.status_code == 200:
            for row in r.json():
                ca = str(row.get("created_at", ""))[:10]
                if ca:
                    daily[ca] = daily.get(ca, 0) + 1
    except requests.RequestException:
        pass
    series = []
    for i in range(29, -1, -1):
        day = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        series.append({"date": day, "count": daily.get(day, 0)})

    return {"_status": 200, "_body": {"visitors": visitors, "members": members, "community": community, "signups_daily": series}}


def handle_audit_log(handler, method: str, body: dict) -> dict:
    # 관리자 조치 로그 조회 (제재·삭제·수정 이력). GET only.
    if not _svc_ready():
        return {"_status": 503, "_body": {"error": "service_role_unconfigured"}}
    if method != "GET":
        return {"_status": 405, "_body": {"error": "method_not_allowed"}}
    params = parse_qs(urlparse(handler.path).query)
    limit = min(200, max(1, int((params.get("limit", ["20"])[0] or "20"))))
    offset = max(0, int((params.get("offset", ["0"])[0] or "0")))
    sel = "id,actor_email,action,target_type,target_id,detail,created_at"
    r = requests.get(f"{SUPABASE_URL}/rest/v1/admin_audit_log",
                     headers=_svc_headers({"Prefer": "count=exact"}),
                     params={"select": sel, "order": "created_at.desc", "limit": str(limit),
                             "offset": str(offset)}, timeout=_t(10))
    if r.status_code not in (200, 206):
        return {"_status": 502, "_body": {"error": "list_failed", "detail": r.text[:200]}}
    total = None
    cr = r.headers.get("Content-Range", "")
    if "/" in cr:
        try:
            total = int(cr.split("/")[-1])
        except ValueError:
            pass
    return {"_status": 200, "_body": {"items": r.json(), "total": total,
                                        "limit": limit, "offset": offset}}


_NOTICE_KINDS = ("notice", "event")
_NOTICE_FIELDS = ("kind", "title", "body", "link", "pinned", "starts_at", "ends_at", "is_active")


def _notice_payload(body: dict) -> dict:
    """요청 body → notices 컬럼. 미동봉 키는 넣지 않음(부분 수정 시 기존값 보존)."""
    out: dict = {}
    for k in _NOTICE_FIELDS:
        if k not in body:
            continue
        v = body[k]
        if k == "kind":
            v = str(v or "notice").strip()
            if v not in _NOTICE_KINDS:
                v = "notice"
        elif k in ("title", "body", "link"):
            v = str(v or "").strip()[: (120 if k == "title" else 2000)]
        elif k in ("pinned", "is_active"):
            v = bool(v)
        elif k in ("starts_at", "ends_at"):
            v = (str(v).strip() or None) if v else None
        out[k] = v
    return out


def handle_notices(handler, method: str, body: dict) -> dict:
    """공지·이벤트 발행 (027 migration). 공개 읽기는 /api/notices — 여기는 운영 쓰기·전량 목록."""
    if not _svc_ready():
        return {"_status": 503, "_body": {"error": "service_role_unconfigured"}}
    actor = _caller_identity(headers_to_dict(handler))

    if method == "GET":
        # 관리자 목록 = 비활성·기간 지난 것 포함 전량
        params = parse_qs(urlparse(handler.path).query)
        limit = min(200, max(1, int((params.get("limit", ["100"])[0] or "100"))))
        r = requests.get(f"{SUPABASE_URL}/rest/v1/notices", headers=_svc_headers(),
                         params={"select": "id,kind,title,body,link,pinned,starts_at,ends_at,is_active,created_at,updated_at",
                                 "order": "pinned.desc,created_at.desc", "limit": str(limit)}, timeout=_t(10))
        if r.status_code == 404 or "PGRST205" in (r.text or ""):
            # 🚨 027 미적용 = 흔한 상태. 502 로 뭉개면 화면에 "HTTP 502" 만 떠 원인을 못 봄(2026-07-27 실사고).
            return {"_status": 200, "_body": {"items": [], "migration_required": "027_notices"}}
        if r.status_code != 200:
            return {"_status": 502, "_body": {"error": "list_failed", "detail": r.text[:200]}}
        return {"_status": 200, "_body": {"items": r.json()}}

    if method == "POST":
        nid = str(body.get("id", "")).strip()
        payload = _notice_payload(body)
        if nid:  # 수정
            if not payload:
                return {"_status": 400, "_body": {"error": "no_fields"}}
            r = requests.patch(f"{SUPABASE_URL}/rest/v1/notices",
                               headers=_svc_headers({"Prefer": "return=representation"}),
                               params={"id": f"eq.{nid}"}, json=payload, timeout=_t(10))
            if r.status_code not in (200, 204):
                return {"_status": 502, "_body": {"error": "update_failed", "detail": r.text[:200]}}
            _audit(actor, "update_notice", "notice", nid, {"fields": sorted(payload.keys())})
            rows = r.json() if r.text else []
            return {"_status": 200, "_body": {"ok": True, "item": (rows[0] if rows else None)}}
        # 신규 — title 필수
        if not payload.get("title"):
            return {"_status": 400, "_body": {"error": "title_required"}}
        payload.setdefault("kind", "notice")
        payload["created_by"] = actor.get("id")
        r = requests.post(f"{SUPABASE_URL}/rest/v1/notices",
                          headers=_svc_headers({"Prefer": "return=representation"}),
                          json=payload, timeout=_t(10))
        if r.status_code not in (200, 201):
            return {"_status": 502, "_body": {"error": "insert_failed", "detail": r.text[:200]}}
        rows = r.json() if r.text else []
        item = rows[0] if rows else None
        _audit(actor, "create_notice", "notice", (item or {}).get("id"), {"kind": payload.get("kind"), "title": payload.get("title")})
        return {"_status": 201, "_body": {"ok": True, "item": item}}

    if method == "DELETE":
        nid = str(body.get("id", "")).strip()
        if not nid:
            return {"_status": 400, "_body": {"error": "id_required"}}
        r = requests.delete(f"{SUPABASE_URL}/rest/v1/notices",
                            headers=_svc_headers({"Prefer": "return=minimal"}),
                            params={"id": f"eq.{nid}"}, timeout=_t(10))
        if r.status_code not in (200, 204):
            return {"_status": 502, "_body": {"error": "delete_failed", "detail": r.text[:200]}}
        _audit(actor, "delete_notice", "notice", nid, None)
        return {"_status": 200, "_body": {"ok": True, "deleted": nid}}

    return {"_status": 405, "_body": {"error": "method_not_allowed"}}


def handle_community_moderation(handler, method: str, body: dict) -> dict:
    if not _svc_ready():
        return {"_status": 503, "_body": {"error": "service_role_unconfigured"}}
    actor = _caller_identity(headers_to_dict(handler))

    if method == "GET":
        params = parse_qs(urlparse(handler.path).query)
        view = (params.get("view", ["reports"])[0] or "reports").strip()
        limit = min(200, max(1, int((params.get("limit", ["100"])[0] or "100"))))
        if view == "reports":
            sel = "id,reason,created_at,reporter_id,thesis:thesis_id(id,user_id,ticker,stance,note,is_public,hidden,created_at)"
            r = requests.get(f"{SUPABASE_URL}/rest/v1/thesis_reports", headers=_svc_headers(),
                             params={"select": sel, "order": "created_at.desc", "limit": str(limit)}, timeout=_t(10))
        else:  # posts — 전체 공개 글
            sel = "id,user_id,ticker,market,stance,note,is_public,hidden,created_at"
            r = requests.get(f"{SUPABASE_URL}/rest/v1/user_thesis", headers=_svc_headers(),
                             params={"select": sel, "order": "created_at.desc", "limit": str(limit), "is_public": "eq.true"}, timeout=_t(10))
        if r.status_code != 200:
            return {"_status": 502, "_body": {"error": "list_failed", "detail": r.text[:200]}}
        return {"_status": 200, "_body": {"items": r.json(), "view": view}}

    if method == "POST":
        action = str(body.get("action", "")).strip()
        tid = str(body.get("thesis_id", "")).strip()
        if not tid:
            return {"_status": 400, "_body": {"error": "thesis_id_required"}}
        if action in ("hide", "unhide"):
            r = requests.patch(f"{SUPABASE_URL}/rest/v1/user_thesis",
                               headers=_svc_headers({"Prefer": "return=minimal"}),
                               params={"id": f"eq.{tid}"}, json={"hidden": action == "hide"}, timeout=_t(10))
            if r.status_code not in (200, 204):
                return {"_status": 502, "_body": {"error": "update_failed", "detail": r.text[:200]}}
            _audit(actor, action + "_post", "thesis", tid, None)
            return {"_status": 200, "_body": {"ok": True}}
        return {"_status": 400, "_body": {"error": "unknown_action", "valid": ["hide", "unhide"]}}

    if method == "DELETE":
        tid = str(body.get("thesis_id", "")).strip()
        if not tid:
            return {"_status": 400, "_body": {"error": "thesis_id_required"}}
        r = requests.delete(f"{SUPABASE_URL}/rest/v1/user_thesis",
                            headers=_svc_headers({"Prefer": "return=minimal"}), params={"id": f"eq.{tid}"}, timeout=_t(10))
        if r.status_code not in (200, 204):
            return {"_status": 502, "_body": {"error": "delete_failed", "detail": r.text[:200]}}
        _audit(actor, "delete_post", "thesis", tid, None)
        return {"_status": 200, "_body": {"ok": True, "deleted": tid}}

    return {"_status": 405, "_body": {"error": "method_not_allowed"}}


# ──────────────────────────────────────────────────────────────────────
# 보안 — IP 침입 시도 추적 · 차단 (방어층). Railway 미들웨어와 blocked_ips 공유.
# 민감 데이터는 이미 인증+RLS로 잠김. 이건 그 위 스캐너 소음↓·가시성·악성 IP 속도저하.
# ──────────────────────────────────────────────────────────────────────

_SEC_BLOCK_ENABLED = os.environ.get("SEC_DISABLED", "").strip() not in ("1", "true", "True")
_sec_blocked: set = set()
_sec_blocked_ts = 0.0


def _sec_iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(ts))


def _sec_client_ip(headers_dict: Dict[str, str]) -> str:
    xff = (headers_dict.get("x-forwarded-for") or "").strip()
    if xff:
        return xff.split(",")[0].strip()
    return (headers_dict.get("x-real-ip") or "").strip()


def _sec_refresh_blocklist() -> None:
    global _sec_blocked, _sec_blocked_ts
    if not _svc_ready():
        return
    if _sec_blocked_ts and time.time() - _sec_blocked_ts < 60:
        return
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/blocked_ips", headers=_svc_headers(),
                         params={"select": "ip", "or": f"(expires_at.is.null,expires_at.gt.{_sec_iso(time.time())})"},
                         timeout=_t(4))
        if r.status_code == 200:
            _sec_blocked = {row["ip"] for row in r.json() if row.get("ip")}
            _sec_blocked_ts = time.time()
    except requests.RequestException:
        pass


def _sec_is_blocked(ip: str) -> bool:
    if not (_SEC_BLOCK_ENABLED and ip):
        return False
    _sec_refresh_blocklist()
    return ip in _sec_blocked


def _sec_note_unauthorized(ip: str, path: str, method: str, ua: str, reason: str = "admin_unauth") -> None:
    """어드민 인증 실패를 관측용으로 기록한다.

    만료된 브라우저 세션은 여러 패널을 동시에 재조회하므로 짧은 시간에 401이 반복될 수 있다.
    인증 실패만으로 공유 blocked_ips에 추가하면 같은 IP의 Railway 시세까지 함께 차단된다.
    실제 자동 차단은 Railway SecurityMiddleware의 명백한 스캔 패턴에만 맡긴다.
    """
    if not (ip and _svc_ready()):
        return
    try:
        requests.post(f"{SUPABASE_URL}/rest/v1/security_probe_log",
                      headers=_svc_headers({"Prefer": "return=minimal"}),
                      json={"ip": ip, "path": (path or "")[:400], "method": method,
                            "user_agent": (ua or "")[:400], "reason": reason, "surface": "vercel"},
                      timeout=_t(4))
    except requests.RequestException:
        pass


def handle_security(handler, method: str, body: dict) -> dict:
    """IP 침입 시도 추적 + 차단 관리 (어드민 가시화 + 수동 차단/해제)."""
    if not _svc_ready():
        return {"_status": 503, "_body": {"error": "service_role_unconfigured"}}

    if method == "GET":
        probes = []
        try:
            r = requests.get(f"{SUPABASE_URL}/rest/v1/security_probe_log", headers=_svc_headers(),
                             params={"select": "ip,path,method,user_agent,country,reason,surface,created_at",
                                     "order": "created_at.desc", "limit": "200"}, timeout=_t(10))
            if r.status_code == 200:
                probes = r.json()
        except requests.RequestException:
            pass
        blocked = []
        try:
            r = requests.get(f"{SUPABASE_URL}/rest/v1/blocked_ips", headers=_svc_headers(),
                             params={"select": "ip,reason,hits,auto,surface,created_by,created_at,expires_at",
                                     "or": f"(expires_at.is.null,expires_at.gt.{_sec_iso(time.time())})",
                                     "order": "created_at.desc", "limit": "500"}, timeout=_t(10))
            if r.status_code == 200:
                blocked = r.json()
        except requests.RequestException:
            pass
        counter = Counter(p.get("ip") for p in probes if p.get("ip"))
        blocked_set = {b.get("ip") for b in blocked}
        top_ips = [{"ip": ip, "count": n, "blocked": ip in blocked_set} for ip, n in counter.most_common(10)]
        return {"_status": 200, "_body": {
            "probes": probes, "blocked": blocked, "top_ips": top_ips,
            "stats": {"probes_recent": len(probes), "blocked_active": len(blocked)},
        }}

    if method == "POST":
        actor = _caller_identity(headers_to_dict(handler))
        action = str(body.get("action", "")).strip()
        ip = str(body.get("ip", "")).strip()
        if not ip:
            return {"_status": 400, "_body": {"error": "ip_required"}}
        if action == "block":
            reason = str(body.get("reason", "manual"))[:200]
            r = requests.post(f"{SUPABASE_URL}/rest/v1/blocked_ips",
                              headers=_svc_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
                              json={"ip": ip, "reason": reason, "auto": False, "surface": "manual",
                                    "created_by": actor.get("email") or "admin", "expires_at": None}, timeout=_t(10))
            if r.status_code not in (200, 201, 204):
                return {"_status": 502, "_body": {"error": "block_failed", "detail": r.text[:200]}}
            _sec_blocked.add(ip)
            _audit(actor, "block_ip", "ip", ip, {"reason": reason})
            return {"_status": 200, "_body": {"ok": True, "ip": ip, "blocked": True}}
        if action == "unblock":
            r = requests.delete(f"{SUPABASE_URL}/rest/v1/blocked_ips",
                                headers=_svc_headers({"Prefer": "return=minimal"}),
                                params={"ip": f"eq.{ip}"}, timeout=_t(10))
            if r.status_code not in (200, 204):
                return {"_status": 502, "_body": {"error": "unblock_failed", "detail": r.text[:200]}}
            _sec_blocked.discard(ip)
            _audit(actor, "unblock_ip", "ip", ip, {})
            return {"_status": 200, "_body": {"ok": True, "ip": ip, "blocked": False}}
        return {"_status": 400, "_body": {"error": "unknown_action", "valid": ["block", "unblock"]}}

    return {"_status": 405, "_body": {"error": "method_not_allowed"}}


# ──────────────────────────────────────────────────────────────────────
# Router
# ──────────────────────────────────────────────────────────────────────

def handle_portfolio_full(request_handler) -> dict:
    """오퍼레이터 authed full portfolio 서빙 (분리 Stage 1, 2026-07-23).
    do_GET 이 authorize()(X-Admin-Token OR JWT+is_admin) 선행 → 통과분만 도달. pages/* 오퍼레이터 카드가
    공개 blob(sanitized 예정) 대신 이 라우트(?type=portfolio_full)로 full 데이터 fetch."""
    portfolio = fetch_portfolio()
    if not portfolio:
        return {"_status": 503, "_body": {"error": "portfolio_unavailable"}}
    return {"_status": 200, "_body": portfolio}


# 터미널 화면이 실제 쓰는 키만 — full(3.57MB) 대비 ≈ 4~6%. (2026-08-03 Safari 메모리 킬 대응)
_TERMINAL_KEYS = (
    "updated_at", "vams", "briefing", "sector_rotation", "global_events",
    "headlines", "bloomberg_google_headlines", "market_horizon", "daily_report",
    "sectors", "macro",
    "system_action",  # 2026-08-03 /macro 시스템 작용 패널 (VERITY #267 — 작은 dict, 슬림 무해)
    # 2026-08-12 구 프레이머 admin 카드 이관 — /system 페이지의 자본 path·AI 사용량·사후분석.
    # 아래 항목은 작은 dict 라 슬림 취지(추천 27KB/건 배제)를 해치지 않는다. portfolio_full(3.57MB)을
    # 컴포넌트가 직접 당기면 Safari 메모리 킬이 재발하므로 슬림 경로로만 노출한다.
    "cost_monitor", "brain_quality", "postmortem", "exec_paper",
)
_TERMINAL_REC_FIELDS = (
    "name", "ticker", "currency", "recommendation", "per", "pbr", "roe",
    "rec_price", "ai_verdict", "drop_from_high_pct", "brain_score",
)


def handle_portfolio_terminal(request_handler) -> dict:
    """오퍼레이터 터미널 슬림 페이로드 — 추천은 필드 화이트리스트(개당 ~27KB → ~0.7KB)."""
    portfolio = fetch_portfolio()
    if not portfolio:
        return {"_status": 503, "_body": {"error": "portfolio_unavailable"}}
    out = {k: portfolio.get(k) for k in _TERMINAL_KEYS if k in portfolio}
    slim_recs = []
    for r in portfolio.get("recommendations") or []:
        if not isinstance(r, dict):
            continue
        s = {k: r.get(k) for k in _TERMINAL_REC_FIELDS if r.get(k) is not None}
        vb = r.get("verity_brain")
        if isinstance(vb, dict):
            s["verity_brain"] = {
                k: vb.get(k) for k in ("brain_score", "grade_label", "grade") if vb.get(k) is not None
            }
        fl = r.get("flow")
        if isinstance(fl, dict) and fl.get("foreign_net") is not None:
            s["flow"] = {"foreign_net": fl.get("foreign_net")}
        ly = r.get("lynch_kr")
        if isinstance(ly, dict) and ly.get("label"):
            s["lynch_kr"] = {"label": ly.get("label")}
        de = r.get("dart_disclosure_events")
        if isinstance(de, dict) and de.get("severity") is not None:
            s["dart_disclosure_events"] = {"severity": de.get("severity")}
        av = s.get("ai_verdict")
        if isinstance(av, str) and len(av) > 240:
            s["ai_verdict"] = av[:240]
        slim_recs.append(s)
    out["recommendations"] = slim_recs
    return {"_status": 200, "_body": out}


# ── 오퍼레이터 파일 authed 서빙 (VERITY↔AlphaNest 분리 Stage 3 후속, 2026-07-23) ──
# history/system_health_snapshot/brain_kb_usage/admin_todos = 오퍼레이터 전용(public-probe 소비 0).
# 공개 발행 제거 → private bucket(_operator/*) 우선, 전환기 공개 blob fallback(제거 전엔 존재). do_GET
# authorize() 통과분만 도달 = authed. pages/* 오퍼레이터 카드가 공개 blob 대신 이 라우트로 fetch.
_BLOB_BASE = PORTFOLIO_URL.rsplit("/", 1)[0] + "/"


def _make_operator_file_handler(public_name: str):
    """public_name(예: 'history.json') → private '_operator/<name>' 우선 서빙 핸들러."""
    private_path = f"_operator/{public_name}"

    def _handler(request_handler) -> dict:
        data = _download_operator_file(private_path)
        if data is None:
            # 전환기 fallback: 공개 blob 제거 전엔 존재 (제거 후 private 만).
            try:
                r = requests.get(_BLOB_BASE + public_name, timeout=_t(10))
                r.raise_for_status()
                data = r.json()
            except (requests.RequestException, ValueError):
                data = None
        if data is None:
            return {"_status": 503, "_body": {"error": "operator_file_unavailable", "file": public_name}}
        return {"_status": 200, "_body": data}

    return _handler


ROUTES = {
    "brain_health": handle_brain_health,
    "data_health": handle_data_health,
    "drift": handle_drift,
    "trust": handle_trust,
    "explain": handle_explain,
    "portfolio_full": handle_portfolio_full,
    # 터미널 슬림 페이로드 (2026-08-03) — full 3.57MB(추천 1.67MB) 파싱이 Safari WebContent
    # 메모리 킬 유발(This page couldn't load 반복). 화면 필요 키 + 추천 필드 화이트리스트만 ≈ 4~6%.
    "portfolio_terminal": handle_portfolio_terminal,
    "history": _make_operator_file_handler("history.json"),
    "system_health_snapshot": _make_operator_file_handler("system_health_snapshot.json"),
    "brain_kb_usage": _make_operator_file_handler("brain_kb_usage.json"),
    "admin_todos": _make_operator_file_handler("admin_todos.json"),
    # 3종 LLM 종합 (2026-08-01) — 오퍼레이터 전용. private _operator/tri_synthesis.json.
    # 공개 blob 미발행이라 fallback 없음(미존재 → 503) = 노출 0. Brain grounding 이라 authed 필수.
    "tri_synthesis": _make_operator_file_handler("tri_synthesis.json"),
    # 후보 편입/이탈 diff (2026-08-04) — 오퍼레이터 전용, 공개 fallback 없음.
    "candidates_diff": _make_operator_file_handler("candidates_diff.json"),
    # 거시 3종 LLM 시나리오 (2026-08-03) — 오퍼레이터 전용. 공개 fallback 없음(미존재 → 503).
    "macro_synthesis": _make_operator_file_handler("macro_synthesis.json"),
    # ④ 검증 층(오퍼레이터 authed) — IC/팩터건강/성과. authed=본인전용이라 공개 노출 아님(봉인 무관).
    "verification": _make_operator_file_handler("verification_report.json"),
    # 중용 목표비중(③척추) — 태생 봉인 자산. authed=본인전용이라 노출 아님(공개 blob fallback 도 없음 — gitignore).
    "moderation_portfolio": _make_operator_file_handler("moderation_portfolio.json"),
    # 2026-08-21 멀티배거 워치 — 오퍼레이터(알파콘솔) 전용. 종목 신호라 공개 노출 금지.
    #   🚨 생산물 _meta.decision_use=False (로깅 전용, active gate 2026-09) — UI 가 관측으로만 쓴다.
    "multibagger": _make_operator_file_handler("multibagger_watch.json"),
    # 2026-08-22 멀티배거 선별 리스트 — 승격→채점 결과 분리 집계(PM 지시).
    "multibagger_picks": _make_operator_file_handler("multibagger_picks.json"),
}

# 운영 변경(POST/DELETE) + 목록(GET) 라우트 — method-aware.
MOD_ROUTES = {
    "member_management": handle_member_management,
    "community_moderation": handle_community_moderation,
    "audit_log": handle_audit_log,
    "growth_stats": handle_growth_stats,
    "security": handle_security,
    "notices": handle_notices,
}


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        write_options(self)

    def _mod_dispatch(self, method: str):
        # 운영 변경/목록 (member_management · community_moderation) — 공통 인증 + method-aware.
        _budget_start()
        hdrs = headers_to_dict(self)
        ip = _sec_client_ip(hdrs)
        endpoint = ""
        try:
            _stage("blocklist")
            if _sec_is_blocked(ip):
                write_response(self, 403, {"error": "forbidden"})
                return
            _stage("authorize")
            ok, reason = authorize(hdrs)
            if not ok:
                _sec_note_unauthorized(ip, self.path, method, hdrs.get("user-agent", ""))
                write_response(self, 401, {"error": "unauthorized", "reason": reason})
                return
            endpoint = (parse_qs(urlparse(self.path).query).get("type", [""])[0] or "").strip()
            fn = MOD_ROUTES.get(endpoint)
            if not fn:
                write_response(self, 400, {"error": "unknown_endpoint", "valid": list(MOD_ROUTES.keys())})
                return
            body = _read_body(self) if method in ("POST", "DELETE") else {}
            _stage(endpoint)
            result = fn(self, method, body)
            write_response(self, result.get("_status", 200), result.get("_body") or {})
        except _BudgetExceeded as e:
            _budget_timeout_response(self, e, endpoint or "mod")
        except Exception as e:  # noqa: BLE001
            _logger.error("admin mod %s %s error: %s", method, endpoint, e, exc_info=True)
            write_response(self, 500, {"error": "internal", "endpoint": endpoint})

    def do_POST(self):
        self._mod_dispatch("POST")

    def do_DELETE(self):
        self._mod_dispatch("DELETE")

    def do_GET(self):
        _budget_start()
        hdrs = headers_to_dict(self)
        ip = _sec_client_ip(hdrs)
        try:
            _stage("blocklist")
            if _sec_is_blocked(ip):
                write_response(self, 403, {"error": "forbidden"})
                return
            _stage("authorize")
            ok, reason = authorize(hdrs)
            if not ok:
                _sec_note_unauthorized(ip, self.path, "GET", hdrs.get("user-agent", ""))
                write_response(self, 401, {"error": "unauthorized", "reason": reason})
                return
        except _BudgetExceeded as e:
            _budget_timeout_response(self, e, "auth")
            return

        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        endpoint = (params.get("type", [""])[0] or "").strip()

        # 운영 목록(회원/모더레이션)은 method-aware 핸들러로 위임
        if endpoint in MOD_ROUTES:
            self._mod_dispatch("GET")
            return

        fn = ROUTES.get(endpoint)
        if not fn:
            write_response(self, 400, {
                "error": "unknown_endpoint",
                "valid": list(ROUTES.keys()) + list(MOD_ROUTES.keys()),
                "hint": "use ?type=brain_health|data_health|drift|trust|explain|member_management|community_moderation",
            })
            return

        try:
            _stage(endpoint)
            result = fn(self)
            write_response(self, result.get("_status", 200), result.get("_body") or {})
        except _BudgetExceeded as e:
            _budget_timeout_response(self, e, endpoint)
        except Exception as e:  # noqa: BLE001
            _logger.error("admin %s error: %s", endpoint, e, exc_info=True)
            write_response(self, 500, {"error": "internal", "endpoint": endpoint})
