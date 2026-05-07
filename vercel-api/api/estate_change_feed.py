"""
GET /api/estate/change-feed — Page 1 ChangeFeed broadcast feed (P2 read-through)

estate/docs/contract_change_feed.md (v0.2 — 2 카테고리 = regulation + catalyst). anonymous endpoint.

흐름 (hero_briefing read-through 패턴 정합):
    1. scenario=live (default)  → ESTATE_CHANGE_FEED_SOURCE_URL fetch
    2. scenario=empty/error     → mock 응답 (개발 toggle 보존)
    3. live fetch 실패          → 503 (T2 — mock fallback X). 컴포넌트가 명시 에러 렌더.

builder cron (평일 KST 09:30) 가 data/estate_change_feed.json 갱신 → publish-data action 이
gh-pages 로 publish. 이 endpoint 는 그 JSON 을 그대로 return.

Query parameters:
    scenario   = "live" (default) | "empty" | "error"
    categories = comma-sep "regulation,catalyst" (live 한정 client filter)
    hours      = lookback hours (live 시 client filter, mock 시 lookback_hours 표기만)

거짓말 트랩:
    T1  fabricate 금지   — fetch 실패 시 503 (mock fallback X)
    T2  mock fallback X  — scenario=live 실패 시 mock 으로 떨어지지 않음
    T9  silent 실패 X    — 모든 실패 _logger.error + 503
    T18 카운트 정합      — category_counts 합 = total
    T29 source URL 절대  — builder 산출물에 절대 URL 만 있음
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

import requests

_logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

VALID_CATEGORIES = ("regulation", "catalyst")  # contract v0.2

SOURCE_URL_ENV = "ESTATE_CHANGE_FEED_SOURCE_URL"
TIMEOUT_SEC = 5            # vercel.json maxDuration=5 일치
CACHE_MAX_AGE = 300        # 5분 — builder cron 1회/일 + 빠른 dispatch 회복


# ─────────────────────────────────────────────────
# Mock (scenario=empty / scenario=error 만 — 개발 toggle 보존)
# ─────────────────────────────────────────────────

def _mock_payload_empty(hours: int, now: datetime) -> dict:
    return {
        "schema_version": "1.0",
        "fetched_at": now.isoformat(timespec="seconds"),
        "namespace": "estate",
        "scenario": "empty",
        "lookback_hours": hours,
        "items": [],
        "category_counts": {c: 0 for c in VALID_CATEGORIES},
        "total": 0,
    }


def _mock_payload_error(hours: int, now: datetime) -> dict:
    return {
        "schema_version": "1.0",
        "fetched_at": now.isoformat(timespec="seconds"),
        "namespace": "estate",
        "scenario": "error",
        "lookback_hours": hours,
        "error": "변동 피드 일시 불가 (mock error scenario)",
        "items": [],
        "category_counts": {},
        "total": 0,
    }


# ─────────────────────────────────────────────────
# Live fetch (read-through)
# ─────────────────────────────────────────────────

def _fetch_live(source_url: str) -> tuple[int, dict | None, str | None]:
    """gh-pages JSON read-through. 반환 (status, payload, error_code)."""
    try:
        r = requests.get(source_url, timeout=TIMEOUT_SEC)
    except requests.RequestException as e:
        _logger.error("change_feed: source fetch failed: %s", e)
        return 503, None, "source_fetch_failed"

    if r.status_code != 200:
        _logger.error("change_feed: source returned %d", r.status_code)
        return 503, None, "source_non_200"

    try:
        payload = r.json()
    except (ValueError, json.JSONDecodeError) as e:
        _logger.error("change_feed: source not valid JSON: %s", e)
        return 503, None, "source_invalid_json"

    if not isinstance(payload, dict):
        _logger.error("change_feed: payload not object")
        return 503, None, "source_schema_invalid"

    # 최소 schema 검증 — ChangeFeed 컴포넌트 필수 필드
    if not isinstance(payload.get("items"), list):
        _logger.error("change_feed: items missing or not list")
        return 503, None, "source_schema_invalid"
    if not isinstance(payload.get("category_counts"), dict):
        _logger.error("change_feed: category_counts missing or not dict")
        return 503, None, "source_schema_invalid"

    return 200, payload, None


def _apply_filters(payload: dict, categories_filter: list[str], hours: int) -> dict:
    """live 응답에 클라이언트 측 filter 적용. T18 — counts/total 재계산."""
    items = list(payload.get("items") or [])

    # category filter
    if categories_filter:
        items = [it for it in items if it.get("category") in categories_filter]

    # lookback filter — occurred_at 기반
    cutoff = datetime.now(KST) - timedelta(hours=hours)
    filtered: list[dict] = []
    for it in items:
        occurred = it.get("occurred_at") or ""
        try:
            ts = datetime.fromisoformat(occurred.replace("Z", "+00:00"))
        except ValueError:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=KST)
        if ts >= cutoff:
            filtered.append(it)
    items = filtered

    # T18 — recompute counts
    counts = {c: 0 for c in VALID_CATEGORIES}
    for it in items:
        cat = it.get("category")
        if cat in counts:
            counts[cat] += 1

    return {
        **payload,
        "lookback_hours": hours,
        "items": items,
        "category_counts": counts,
        "total": len(items),
    }


# ─────────────────────────────────────────────────
# HTTP handler
# ─────────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def _json(self, status: int, payload: dict, cache_control: str | None = None):
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if cache_control:
            self.send_header("Cache-Control", cache_control)
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def _err(self, status: int, code: str, message: str):
        self._json(status, {"error": code, "message": message})

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)

        scenario = (params.get("scenario", ["live"])[0] or "live").strip().lower()
        if scenario not in ("live", "empty", "error"):
            scenario = "live"

        cats_raw = (params.get("categories", [""])[0] or "").strip()
        categories_filter = [
            c.strip() for c in cats_raw.split(",")
            if c.strip() in VALID_CATEGORIES
        ] if cats_raw else []

        try:
            hours = int(params.get("hours", ["72"])[0])
            hours = max(1, min(hours, 168))
        except (ValueError, TypeError):
            hours = 72

        now = datetime.now(KST)

        # 개발 toggle — empty/error 는 mock 유지 (Framer P1 검증용)
        if scenario == "empty":
            self._json(200, _mock_payload_empty(hours, now))
            return
        if scenario == "error":
            self._json(200, _mock_payload_error(hours, now))
            return

        # live — gh-pages read-through
        source_url = (os.environ.get(SOURCE_URL_ENV, "") or "").strip()
        if not source_url:
            _logger.error("change_feed: %s missing", SOURCE_URL_ENV)
            self._err(503, "config_missing", f"{SOURCE_URL_ENV} not configured")
            return

        status, payload, err_code = _fetch_live(source_url)
        if status != 200 or payload is None:
            self._err(503, err_code or "source_unavailable", "upstream unavailable")
            return

        filtered = _apply_filters(payload, categories_filter, hours)
        self._json(200, filtered, cache_control=f"public, max-age={CACHE_MAX_AGE}")
