"""Durable public-only delta snapshots for the existing map consumer.

No holdings, credentials, AI calls, relationship promotion, or remote writes.
SQLite commits feed and cursor together; failed/partial checks cannot reset the
last successful-check clock. Discovery and analysis are deliberately separate.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3

from .member_map_listing_delta import merge_feed
try:
    from .member_map_freshness import collection_health, instant, POLL_SECONDS
except ImportError:
    from api.observability.member_map_freshness import collection_health, instant, POLL_SECONDS

FILES = {"SEC": "us_disclosure_feed.json", "DART": "public_disclosure_feed.json", "news": "portfolio.json"}
NEWS_FIELDS = ("headlines", "bloomberg_google_headlines", "us_headlines")


def state_path(path):
    path = Path(path).absolute()
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError("live-state-symlink")
    if path.exists() and (not path.is_file() or path.stat().st_size > 256 * 1024 * 1024):
        raise ValueError("live-state-file")
    return path


def read_state(path):
    path = state_path(path)
    if not path.exists():
        return {}
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5) as db:
        rows = db.execute("SELECT source, payload FROM public_refresh").fetchall()
    return {source: json.loads(payload) for source, payload in rows if source in FILES}


def save_source(path, source, value):
    if source not in FILES:
        raise ValueError("live-source")
    payload = json.dumps(value, ensure_ascii=False, allow_nan=False)
    if len(payload.encode()) > 20 * 1024 * 1024:
        raise ValueError("live-source-size")
    path = state_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=5) as db:
        os.chmod(path, 0o600)
        db.execute("CREATE TABLE IF NOT EXISTS public_refresh (source TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        db.execute("INSERT OR REPLACE INTO public_refresh VALUES (?, ?)", (source, payload))


def due(source, previous, now):
    current = instant(now)
    if source not in FILES or current is None:
        raise ValueError("live-clock")
    attempt = instant(previous.get("last_attempt_at"))
    return attempt is None or attempt > current or (current - attempt).total_seconds() >= POLL_SECONDS[source]


def apply_result(source, previous, result, now):
    """Partial valid pages can expose facts, but cannot claim complete scanning."""
    if source not in FILES or instant(now) is None:
        raise ValueError("live-result")
    state = deepcopy(previous)
    status = result.get("status")
    complete = status == "success" and result.get("complete") is True
    state.update(last_attempt_at=now, status=status, error=result.get("error"),
                 coverage=result.get("coverage", {}), requests=result.get("requests", 0))
    if complete or status == "initialized":
        state["cursor"] = result.get("cursor")
    if complete:
        state["last_success_at"] = now
    if source != "news":
        # Store only listing-derived public rows. This is not an AI input packet.
        records = result.get("records", [])
        if records:
            state["feed"] = merge_feed(previous.get("feed", {"items": []}), records, now, max_per_ticker=8)
        else:
            state.setdefault("feed", {"items": []})
    elif result.get("feed"):
        state["feed"] = result["feed"]
    state["health"] = collection_health(source, last_success_at=state.get("last_success_at"), now=now)
    # Feed generation/observation does NOT attest to end-user delivery.
    state["screen_delivery_verified"] = False
    state["analysis_delivery_verified"] = False
    return state


def news_result():
    """Reuse existing public collectors, excluding operator portfolio and scores."""
    from api.collectors.news_headlines import (
        collect_headlines, collect_bloomberg_google_news_rss, collect_us_headlines)
    from api.intelligence.portfolio_market_context import _url, _news_date
    from api.intelligence.portfolio_public_sources import safe_public_text
    kr = collect_headlines(max_items=50)
    bloomberg = collect_bloomberg_google_news_rss(max_items=30)
    us = collect_us_headlines(kr, bloomberg, max_items=50)
    feed, rejected = {}, 0
    for field, rows in zip(NEWS_FIELDS, (kr, bloomberg, us)):
        safe = []
        for row in rows:
            title, source = safe_public_text(row.get("title"), 240), safe_public_text(row.get("source"), 100)
            link, stamp = _url(row.get("link")), _news_date(row.get("time"))
            if not all((title, source, link, stamp)):
                rejected += 1
                continue
            safe.append({"title": title, "source": source, "link": link, "time": stamp})
        feed[field] = safe
    # Legacy collectors swallow per-feed failures: nonempty output does not prove
    # all configured feeds succeeded. Preserve that uncertainty, never green it.
    return {"status": "partial", "complete": False, "feed": feed if any(feed.values()) else None,
            "error": "per-feed-completeness-unavailable", "requests": None,
            "coverage": {"accepted": sum(map(len, feed.values())), "rejected": rejected,
                         "whole_market_coverage": False, "all_feeds_verified": False}}


def overlay_sources(documents, path):
    return overlay_states(documents, read_state(path))


def overlay_states(documents, states):
    """Add public facts without replacing baseline company coverage or AI state."""
    result = documents.copy()
    for source, state in states.items():
        if source not in FILES:
            raise ValueError("live-source")
        feed = state.get("feed", {})
        filename = FILES[source]
        if source == "news":
            base = deepcopy(result.get(filename, {}))
            for field in NEWS_FIELDS:
                if feed.get(field):
                    # Keep previous valid rows when a feed is empty/unavailable.
                    rows = feed[field] + base.get(field, [])
                    seen = set()
                    base[field] = [row for row in rows if row.get("link") not in seen
                                   and not seen.add(row.get("link"))][:100]
            result[filename] = base
        else:
            records = [{**row, "ticker": item["ticker"], "name": item["name"]}
                       for item in feed.get("items", []) for row in item.get("disclosures", [])]
            if records:
                result[filename] = merge_feed(result.get(filename, {"items": []}), records,
                                               feed.get("_meta", {}).get("generated_at", state["last_attempt_at"]),
                                               max_per_ticker=8)
    return result
