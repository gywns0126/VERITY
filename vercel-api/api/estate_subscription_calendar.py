"""
GET /api/estate/subscription-calendar — ESTATE D / SubscriptionCalendar read-through endpoint

builder cron 이 data/estate_subscription_calendar.json 갱신 → publish-data gh-pages push.
이 endpoint 는 그 JSON read-through + client filter (event_types, regions, window_days).

Query parameters:
    scenario      = "live" (default) | "empty" | "error"
    past_days     = int 0~365  (today 기준 과거 N일)
    future_days   = int 0~365  (today 기준 미래 N일)
    event_types   = comma "recruit,application,announcement,contract,move_in"
    regions       = comma "서울,경기,부산,..."

거짓말 트랩:
    T1·T9  fabricate·silent X — fetch 실패 시 503 (mock fallback X)
    T2     mock fallback X    — scenario=live 실패 시 mock 으로 떨어지지 않음
    T18    카운트 정합        — filter 후 by_month/by_region 재계산
    T29    source URL 절대    — builder 산출물에 PBLANC_URL 그대로
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

VALID_EVENT_TYPES = ("recruit", "application", "announcement", "contract", "move_in")

SOURCE_URL_ENV = "ESTATE_SUBSCRIPTION_CALENDAR_SOURCE_URL"
TIMEOUT_SEC = 5
CACHE_MAX_AGE = 300

DEFAULT_PAST_DAYS = 30
DEFAULT_FUTURE_DAYS = 90
WINDOW_DAYS_MAX = 365


def _mock_empty(past: int, future: int, now: datetime) -> dict:
    return {
        "schema_version": "1.0",
        "fetched_at": now.isoformat(timespec="seconds"),
        "namespace": "estate",
        "scenario": "empty",
        "window": {"past_days": past, "future_days": future},
        "total_subscriptions": 0,
        "events": [],
        "by_month": {},
        "by_region": {},
        "upcoming_high_impact": [],
    }


def _mock_error(past: int, future: int, now: datetime) -> dict:
    return {
        **_mock_empty(past, future, now),
        "scenario": "error",
        "error": "분양 캘린더 일시 불가 (mock error scenario)",
    }


def _fetch_live(source_url: str) -> tuple[int, dict | None, str | None]:
    try:
        r = requests.get(source_url, timeout=TIMEOUT_SEC)
    except requests.RequestException as e:
        _logger.error("subscription_calendar: source fetch failed: %s", e)
        return 503, None, "source_fetch_failed"

    if r.status_code != 200:
        _logger.error("subscription_calendar: source returned %d", r.status_code)
        return 503, None, "source_non_200"

    try:
        payload = r.json()
    except (ValueError, json.JSONDecodeError) as e:
        _logger.error("subscription_calendar: source not valid JSON: %s", e)
        return 503, None, "source_invalid_json"

    if not isinstance(payload, dict):
        _logger.error("subscription_calendar: payload not object")
        return 503, None, "source_schema_invalid"

    if not isinstance(payload.get("events"), list):
        _logger.error("subscription_calendar: events missing or not list")
        return 503, None, "source_schema_invalid"

    return 200, payload, None


def _apply_filters(
    payload: dict,
    past_days: int,
    future_days: int,
    event_types: list[str],
    regions: list[str],
) -> dict:
    """T18 — client filter 후 by_month/by_region/upcoming_high_impact 재계산."""
    events = list(payload.get("events") or [])

    today = datetime.now(KST).date()
    cutoff_past = today - timedelta(days=past_days)
    cutoff_future = today + timedelta(days=future_days)

    filtered: list[dict] = []
    for e in events:
        try:
            d = datetime.strptime(e.get("date_start") or "", "%Y-%m-%d").date()
        except ValueError:
            continue
        if not (cutoff_past <= d <= cutoff_future):
            continue
        if event_types and e.get("event_type") not in event_types:
            continue
        if regions and e.get("region") not in regions:
            continue
        filtered.append(e)

    by_month: dict = defaultdict(
        lambda: {"count": 0, "by_event_type": defaultdict(int), "regions": defaultdict(int), "total_supply": 0}
    )
    by_region: dict = defaultdict(int)
    for e in filtered:
        m = e["date_start"][:7]
        cell = by_month[m]
        cell["count"] += 1
        cell["by_event_type"][e.get("event_type")] += 1
        cell["regions"][e.get("region")] += 1
        if e.get("total_supply"):
            cell["total_supply"] += int(e["total_supply"])
        by_region[e.get("region")] += 1

    horizon = (today + timedelta(days=30)).isoformat()
    today_iso = today.isoformat()
    upcoming = [
        e for e in filtered
        if e.get("event_type") == "recruit"
        and today_iso <= e.get("date_start", "") <= horizon
        and (e.get("total_supply") or 0) >= 1000
    ]

    return {
        **payload,
        "window": {"past_days": past_days, "future_days": future_days},
        "events": filtered,
        "by_month": {
            k: {
                "count": v["count"],
                "by_event_type": dict(v["by_event_type"]),
                "regions": dict(v["regions"]),
                "total_supply": v["total_supply"],
            } for k, v in by_month.items()
        },
        "by_region": dict(by_region),
        "upcoming_high_impact": upcoming,
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

        def _int_param(name: str, default: int) -> int:
            try:
                v = int(params.get(name, [str(default)])[0])
                return max(0, min(v, WINDOW_DAYS_MAX))
            except (ValueError, TypeError):
                return default

        past_days = _int_param("past_days", DEFAULT_PAST_DAYS)
        future_days = _int_param("future_days", DEFAULT_FUTURE_DAYS)

        ets_raw = (params.get("event_types", [""])[0] or "").strip()
        event_types = [t.strip() for t in ets_raw.split(",") if t.strip() in VALID_EVENT_TYPES] if ets_raw else []

        regs_raw = (params.get("regions", [""])[0] or "").strip()
        regions = [r.strip() for r in regs_raw.split(",") if r.strip()] if regs_raw else []

        now = datetime.now(KST)

        if scenario == "empty":
            self._json(200, _mock_empty(past_days, future_days, now))
            return
        if scenario == "error":
            self._json(200, _mock_error(past_days, future_days, now))
            return

        source_url = (os.environ.get(SOURCE_URL_ENV, "") or "").strip()
        if not source_url:
            _logger.error("subscription_calendar: %s missing", SOURCE_URL_ENV)
            self._err(503, "config_missing", f"{SOURCE_URL_ENV} not configured")
            return

        status, payload, err_code = _fetch_live(source_url)
        if status != 200 or payload is None:
            self._err(503, err_code or "source_unavailable", "upstream unavailable")
            return

        filtered = _apply_filters(payload, past_days, future_days, event_types, regions)
        self._json(200, filtered, cache_control=f"public, max-age={CACHE_MAX_AGE}")
