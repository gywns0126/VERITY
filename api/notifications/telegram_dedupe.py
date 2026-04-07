"""
장중(realtime) 텔레그램 알림 중복 방지 — portfolio.json 내 메타에 타임스탬프 저장(GH Actions 유지).
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List

from api.config import TELEGRAM_ALERT_DEDUPE_HOURS

_META_KEY = "_telegram_realtime_dedupe"


def _fingerprint(alert: Dict[str, Any]) -> str:
    cat = str(alert.get("category", ""))
    msg = str(alert.get("message", "")).strip()
    raw = f"{cat}|{msg}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _prune_bucket(bucket: Dict[str, float], now: float, ttl_sec: float) -> None:
    drop_before = now - ttl_sec * 3
    stale = [k for k, ts in bucket.items() if float(ts) < drop_before]
    for k in stale:
        del bucket[k]


def filter_deduped_realtime_alerts(
    alerts: List[Dict[str, Any]],
    portfolio: Dict[str, Any],
) -> List[Dict[str, Any]]:
    if not alerts:
        return []
    raw = portfolio.get(_META_KEY)
    bucket: Dict[str, float] = raw if isinstance(raw, dict) else {}
    portfolio[_META_KEY] = bucket

    now = time.time()
    ttl = max(1, TELEGRAM_ALERT_DEDUPE_HOURS) * 3600
    _prune_bucket(bucket, now, ttl)

    out: List[Dict[str, Any]] = []
    for a in alerts:
        fp = _fingerprint(a)
        last = bucket.get(fp)
        if last is not None and (now - float(last)) < ttl:
            continue
        out.append(a)
    return out


def mark_realtime_alerts_sent(
    portfolio: Dict[str, Any],
    alerts: List[Dict[str, Any]],
) -> None:
    if not alerts:
        return
    bucket = portfolio.setdefault(_META_KEY, {})
    if not isinstance(bucket, dict):
        bucket = {}
        portfolio[_META_KEY] = bucket
    now = time.time()
    ttl = max(1, TELEGRAM_ALERT_DEDUPE_HOURS) * 3600
    _prune_bucket(bucket, now, ttl)
    for a in alerts:
        bucket[_fingerprint(a)] = now
