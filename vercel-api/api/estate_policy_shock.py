"""
GET /api/estate/policy-shock — PolicyShockTimeline read-through endpoint

builder cron 이 data/estate_policy_shock.json 갱신 → publish-data 가 gh-pages push.
이 endpoint 는 그 JSON read-through + lookback/category/direction client filter.

Query parameters:
    scenario      = "live" (default) | "empty" | "error"
    lookback_days = int 1~90 (live 시 client filter)
    categories    = comma "regulation,catalyst,supply,..."
    directions    = comma "negative,positive,neutral"

거짓말 트랩:
    T1  fabricate 금지   — fetch 실패 시 503 (mock fallback X)
    T2  mock fallback X  — scenario=live 실패 시 mock 으로 떨어지지 않음
    T9  silent 실패 X    — 모든 실패 _logger.error + 503
    T18 카운트 정합      — filter 후 stats 재계산
    T29 source URL 절대  — builder 산출물에 절대 URL
"""
from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

import requests

_logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

VALID_CATEGORIES = ("regulation", "tax", "loan", "redev", "supply", "rental", "catalyst", "anomaly")
VALID_DIRECTIONS = ("negative", "positive", "neutral")

SOURCE_URL_ENV = "ESTATE_POLICY_SHOCK_SOURCE_URL"
TIMEOUT_SEC = 5
CACHE_MAX_AGE = 300

DEFAULT_LOOKBACK_DAYS = 30
LOOKBACK_DAYS_MAX = 90


def _mock_payload_empty(lookback: int, now: datetime) -> dict:
    return {
        "schema_version": "1.0",
        "fetched_at": now.isoformat(timespec="seconds"),
        "namespace": "estate",
        "scenario": "empty",
        "lookback_days": lookback,
        "items": [],
        "by_day": {},
        "stats": {"by_category": {}, "by_direction": {"negative": 0, "positive": 0, "neutral": 0},
                  "max_impact": 0.0, "mean_impact": 0.0},
        "total": 0,
    }


def _mock_payload_error(lookback: int, now: datetime) -> dict:
    return {
        "schema_version": "1.0",
        "fetched_at": now.isoformat(timespec="seconds"),
        "namespace": "estate",
        "scenario": "error",
        "lookback_days": lookback,
        "error": "정책 충격 피드 일시 불가 (mock error scenario)",
        "items": [],
        "by_day": {},
        "stats": {"by_category": {}, "by_direction": {"negative": 0, "positive": 0, "neutral": 0},
                  "max_impact": 0.0, "mean_impact": 0.0},
        "total": 0,
    }


def _fetch_live(source_url: str) -> tuple[int, dict | None, str | None]:
    try:
        r = requests.get(source_url, timeout=TIMEOUT_SEC)
    except requests.RequestException as e:
        _logger.error("policy_shock: source fetch failed: %s", e)
        return 503, None, "source_fetch_failed"

    if r.status_code != 200:
        _logger.error("policy_shock: source returned %d", r.status_code)
        return 503, None, "source_non_200"

    try:
        payload = r.json()
    except (ValueError, json.JSONDecodeError) as e:
        _logger.error("policy_shock: source not valid JSON: %s", e)
        return 503, None, "source_invalid_json"

    if not isinstance(payload, dict):
        _logger.error("policy_shock: payload not object")
        return 503, None, "source_schema_invalid"

    if not isinstance(payload.get("items"), list):
        _logger.error("policy_shock: items missing or not list")
        return 503, None, "source_schema_invalid"

    return 200, payload, None


def _apply_filters(
    payload: dict,
    lookback_days: int,
    categories: list[str],
    directions: list[str],
) -> dict:
    """client-side filter 후 by_day/stats 재계산 (T18 — 카운트 정합)."""
    items = list(payload.get("items") or [])

    # lookback (published_at 기반)
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    filtered_lookback: list[dict] = []
    for it in items:
        pa = it.get("published_at") or ""
        try:
            ts = datetime.fromisoformat(pa.replace("Z", "+00:00"))
        except ValueError:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=KST)
        if ts.astimezone(timezone.utc) >= cutoff:
            filtered_lookback.append(it)
    items = filtered_lookback

    if categories:
        items = [it for it in items if it.get("category") in categories]
    if directions:
        items = [it for it in items if it.get("direction") in directions]

    # 재계산 stats
    by_day: dict = defaultdict(lambda: {"count": 0, "max_impact": 0.0, "net_direction_score": 0.0})
    cat_counts: dict = defaultdict(int)
    dir_counts: dict = {"negative": 0, "positive": 0, "neutral": 0}
    impact_sum = 0.0
    max_impact = 0.0

    for it in items:
        impact = float(it.get("impact_score") or 0.0)
        direction = it.get("direction") or "neutral"
        day = (it.get("published_at") or "")[:10]
        if day:
            cell = by_day[day]
            cell["count"] += 1
            if impact > cell["max_impact"]:
                cell["max_impact"] = round(impact, 4)
            sign = 1 if direction == "positive" else (-1 if direction == "negative" else 0)
            cell["net_direction_score"] = round(cell["net_direction_score"] + impact * sign, 4)
        cat = it.get("category")
        if cat:
            cat_counts[cat] += 1
        if direction in dir_counts:
            dir_counts[direction] += 1
        impact_sum += impact
        if impact > max_impact:
            max_impact = impact

    mean_impact = (impact_sum / len(items)) if items else 0.0

    return {
        **payload,
        "lookback_days": lookback_days,
        "items": items,
        "by_day": dict(by_day),
        "stats": {
            "by_category": dict(cat_counts),
            "by_direction": dir_counts,
            "max_impact": round(max_impact, 4),
            "mean_impact": round(mean_impact, 4),
        },
        "total": len(items),
    }


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

        try:
            lookback = int(params.get("lookback_days", [str(DEFAULT_LOOKBACK_DAYS)])[0])
            lookback = max(1, min(lookback, LOOKBACK_DAYS_MAX))
        except (ValueError, TypeError):
            lookback = DEFAULT_LOOKBACK_DAYS

        cats_raw = (params.get("categories", [""])[0] or "").strip()
        categories = [c.strip() for c in cats_raw.split(",") if c.strip() in VALID_CATEGORIES] if cats_raw else []

        dirs_raw = (params.get("directions", [""])[0] or "").strip()
        directions = [d.strip() for d in dirs_raw.split(",") if d.strip() in VALID_DIRECTIONS] if dirs_raw else []

        now = datetime.now(KST)

        if scenario == "empty":
            self._json(200, _mock_payload_empty(lookback, now))
            return
        if scenario == "error":
            self._json(200, _mock_payload_error(lookback, now))
            return

        source_url = (os.environ.get(SOURCE_URL_ENV, "") or "").strip()
        if not source_url:
            _logger.error("policy_shock: %s missing", SOURCE_URL_ENV)
            self._err(503, "config_missing", f"{SOURCE_URL_ENV} not configured")
            return

        status, payload, err_code = _fetch_live(source_url)
        if status != 200 or payload is None:
            self._err(503, err_code or "source_unavailable", "upstream unavailable")
            return

        filtered = _apply_filters(payload, lookback, categories, directions)
        self._json(200, filtered, cache_control=f"public, max-age={CACHE_MAX_AGE}")
