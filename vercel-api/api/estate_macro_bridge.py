"""
GET /api/estate/macro-bridge — ESTATE 매크로 ↔ 부동산 영향 다리 (Tier 3 신규 2026-05-13)

macro_snapshot.json (api/builders/macro_collect_builder.py 산출, 30분 cron) 에서
부동산 직결 4지표만 추출 + 룰 기반 LANDEX 방향성 해설.

부동산 직결 4지표 (자체 선정, v0):
    1. korea_policy_rate    한국 기준금리 (BOK)           → 주담대 비용 driver
    2. korea_gov_10y        국고채 10년 yield             → 부동산 valuation discount rate
    3. usd_krw              USD/KRW 환율                  → 외국인 매수/매도 driver
    4. vix_close            VIX (FRED)                    → 위험회피 → 부동산 안전자산 선호

룰 기반 narrative (자체 신호, v0 — feedback_master_rule_drift_audit 정합):
    각 지표 → 부동산 직관 영향 1줄 해설. LLM 호출 X (정적 룰 dict).
    v1 큐잉: LLM 호출 + LANDEX 시계열 cross-correlation 정량.

거짓말 트랩:
    T1·T9  fabricate·silent X — source 미존재 시 503 + 명시 사유
    T2     mock fallback X
    T29    source URL 절대 (env)
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler

import requests

_logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

SOURCE_URL_ENV = "ESTATE_MACRO_BRIDGE_SOURCE_URL"  # 보통 VERITY-data/main/macro_snapshot.json (옵션 B)
TIMEOUT_SEC = 5
CACHE_MAX_AGE = 300

# ─────────────────────────────────────────────────────────────
# 룰 기반 narrative — 4지표별 부동산 영향 1줄 (자체 v0)
# ─────────────────────────────────────────────────────────────
def _interpret_policy_rate(value: float, change_pct: float | None = None) -> str:
    """기준금리 → 부동산 영향."""
    if value >= 3.5:
        return "고금리 구간 — 주담대 부담 ↑, 부동산 수요 압박"
    if value >= 2.5:
        return "중립 금리 — 부동산 수요 횡보 가능"
    return "저금리 — 주담대 부담 ↓, 부동산 수요 자극 가능"


def _interpret_gov_10y(value: float, yoy_pp: float | None = None) -> str:
    """국고채 10년 → 부동산 discount rate."""
    if value is None:
        return "데이터 부재"
    base = f"{value:.2f}%"
    if yoy_pp is not None and yoy_pp >= 1.0:
        return f"장기금리 급등 ({base}, YoY +{yoy_pp:.2f}pp) — 부동산 valuation discount ↑, 가격 압박"
    if yoy_pp is not None and yoy_pp <= -0.5:
        return f"장기금리 하락 ({base}, YoY {yoy_pp:+.2f}pp) — 부동산 valuation 개선 신호"
    return f"장기금리 {base} — 부동산 평가 변동 제한적"


def _interpret_usd_krw(value: float, change_pct: float | None) -> str:
    """환율 → 외국인 매수/매도."""
    if change_pct is not None and change_pct >= 1.0:
        return f"원화 급락 ({value:.0f}원, +{change_pct:.2f}%) — 외국인 한국 자산 매수 압력 ↑"
    if change_pct is not None and change_pct <= -1.0:
        return f"원화 급등 ({value:.0f}원, {change_pct:.2f}%) — 외국인 매도/리스크 회피"
    return f"환율 {value:.0f}원 (안정 구간)"


def _interpret_vix(value: float, trend_1m: float | None) -> str:
    """VIX → 위험회피 → 부동산 선호."""
    if value >= 25:
        return f"VIX 고변동 ({value:.1f}) — 위험회피 → 부동산 안전자산 매수 유입 가능"
    if value <= 15:
        return f"VIX 저변동 ({value:.1f}) — 위험선호 → 부동산 대비 주식 유입"
    return f"VIX {value:.1f} (중립 변동)"


def _build_bridge(snapshot: dict) -> dict:
    """macro_snapshot.json → ESTATE 4지표 + narrative payload."""
    m = snapshot.get("macro", {}) or {}
    ecos = m.get("ecos", {}) or {}
    fred = m.get("fred", {}) or {}

    policy = ecos.get("korea_policy_rate") or {}
    gov10y = ecos.get("korea_gov_10y") or {}
    usd_krw = m.get("usd_krw") or {}
    vix = fred.get("vix_close") or {}

    indicators = {
        "korea_policy_rate": {
            "label": "한국 기준금리",
            "value": policy.get("value"),
            "unit": policy.get("unit") or "연%",
            "as_of": policy.get("date"),
            "narrative": _interpret_policy_rate(policy.get("value")) if policy.get("value") is not None else "데이터 부재",
            "source": policy.get("source", "ecos"),
        },
        "korea_gov_10y": {
            "label": "국고채 10년",
            "value": gov10y.get("value"),
            "unit": "%",
            "yoy_pp": gov10y.get("yoy_pp"),
            "as_of": gov10y.get("date"),
            "narrative": _interpret_gov_10y(gov10y.get("value"), gov10y.get("yoy_pp")),
            "source": gov10y.get("source", "ecos"),
        },
        "usd_krw": {
            "label": "USD/KRW",
            "value": usd_krw.get("value"),
            "unit": "원",
            "change_pct": usd_krw.get("change_pct"),
            "as_of": usd_krw.get("as_of"),
            "narrative": _interpret_usd_krw(
                usd_krw.get("value") or 0.0, usd_krw.get("change_pct"),
            ) if usd_krw.get("value") is not None else "데이터 부재",
            "source": usd_krw.get("source", "yfinance"),
        },
        "vix": {
            "label": "VIX",
            "value": vix.get("value"),
            "unit": "p",
            "trend_1m_change": (vix.get("trend") or {}).get("1m", {}).get("change"),
            "as_of": vix.get("date"),
            "narrative": _interpret_vix(
                vix.get("value") or 0.0,
                (vix.get("trend") or {}).get("1m", {}).get("change"),
            ) if vix.get("value") is not None else "데이터 부재",
            "source": "fred",
        },
    }

    # 종합 verdict — 4지표 narrative 압축. 단순 카운트 (압박 vs 자극)
    pressure_count = 0
    relief_count = 0
    for k, ind in indicators.items():
        narr = ind.get("narrative") or ""
        if any(s in narr for s in ("압박", "급등", "매도", "↑", "고변동")):
            if "valuation 개선" in narr or "안전자산 매수" in narr:
                relief_count += 1
            else:
                pressure_count += 1
        elif any(s in narr for s in ("자극", "매수 압력 ↑", "valuation 개선", "안전자산 매수")):
            relief_count += 1

    if pressure_count >= 3:
        overall = "압박 우세 — LANDEX 가격 약세 압력 강함"
    elif relief_count >= 3:
        overall = "완화 우세 — LANDEX 가격 회복 환경"
    else:
        overall = "혼조 — 지표 간 영향 상쇄, LANDEX 횡보 가능"

    return {
        "schema_version": "1.0",
        "fetched_at": datetime.now(KST).isoformat(timespec="seconds"),
        "namespace": "estate",
        "scenario": "live",
        "collected_at": snapshot.get("collected_at"),
        "indicators": indicators,
        "overall_verdict": overall,
        "pressure_count": pressure_count,
        "relief_count": relief_count,
    }


def _fetch_snapshot(source_url: str) -> tuple[int, dict | None, str | None]:
    try:
        r = requests.get(source_url, timeout=TIMEOUT_SEC)
    except requests.RequestException as e:
        _logger.error("macro_bridge: source fetch failed: %s", e)
        return 503, None, "source_fetch_failed"

    if r.status_code != 200:
        _logger.error("macro_bridge: source returned %d", r.status_code)
        return 503, None, "source_non_200"

    try:
        payload = r.json()
    except (ValueError, json.JSONDecodeError) as e:
        _logger.error("macro_bridge: source not valid JSON: %s", e)
        return 503, None, "source_invalid_json"

    if not isinstance(payload, dict) or "macro" not in payload:
        _logger.error("macro_bridge: payload schema invalid (macro missing)")
        return 503, None, "source_schema_invalid"

    return 200, payload, None


class handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def _json(self, status: int, payload: dict):
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", f"public, max-age={CACHE_MAX_AGE}")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def _err(self, status: int, code: str, message: str):
        self._json(status, {"error": code, "message": message})

    def do_GET(self):
        source_url = (os.environ.get(SOURCE_URL_ENV, "") or "").strip()
        if not source_url:
            _logger.error("macro_bridge: %s missing", SOURCE_URL_ENV)
            self._err(503, "config_missing", f"{SOURCE_URL_ENV} not configured")
            return

        status, payload, err = _fetch_snapshot(source_url)
        if status != 200 or payload is None:
            self._err(503, err or "source_unavailable", "upstream unavailable")
            return

        try:
            bridge = _build_bridge(payload)
        except Exception as e:
            _logger.error("macro_bridge: build failed: %s", e)
            self._err(500, "build_failed", "internal calculation error")
            return

        self._json(200, bridge)
