"""Private operator Telegram policy; analysis and stored evidence are unchanged."""
from __future__ import annotations

import html
import os
import re
from typing import Any, Mapping


def essential_only_enabled() -> bool:
    # 2026-11-04: operator explicitly requested only necessary notifications.
    return os.environ.get("TELEGRAM_NOTIFICATION_MODE", "essential").strip().lower() != "all"


_ACTIONABLE_TYPES = frozenset({
    "STOP_LOSS", "EXPOSURE_BLOCK", "PARTIAL_EXIT", "NEW_BUY",
    "ORDER_FILLED", "ORDER_FAILED", "ORDER_REJECTED", "CIRCUIT_BREAKER",
    "ACCOUNT_ERROR", "AUTH_FAILURE", "TOKEN_FAILURE", "SECURITY_ALERT",
})
_INFORMATIONAL_CATEGORIES = frozenset({
    "macro", "earnings", "geopolitical", "news", "market_signal",
    "valuation", "sector", "sentiment", "economic_calendar",
})


def is_essential_alert(alert: Mapping[str, Any]) -> bool:
    """Keep actionable risk/execution and unclassified critical incidents.

    The CRITICAL label on an earnings or market update does not make it urgent.
    Unknown critical types remain visible rather than silently hiding a new risk.
    """
    kind = str(alert.get("type") or alert.get("category") or "").strip()
    if kind.upper() in _ACTIONABLE_TYPES:
        return True
    if kind.lower() in _INFORMATIONAL_CATEGORIES:
        return False
    level = str(alert.get("level", "")).upper()
    if kind.lower() in {"holding", "sec_risk"} and level in {"CRITICAL", "WARNING"}:
        return True
    return level == "CRITICAL"


def _title(text: str) -> str:
    first = str(text or "").split("\n", 1)[0]
    plain = html.unescape(re.sub(r"<[^>]*>", " ", first))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s·-]", " ", plain)).strip().casefold()


# Compatibility for existing direct callers of send_message. Typed callers use
# notification_kind instead; unknown messages retain their prior safety behavior.
_ROUTINE_TITLE_PREFIXES = tuple(_title(title) for title in (
    "일일 브리핑", "모닝 브리핑", "VAMS 시뮬레이션 성과",
    "VERITY 채권·ETF 업데이트", "MarketHorizon Signal 변경",
    "MarketHorizon Cycle 변경", "배리티 속보", "SEC 8-K 신규 filing",
    "brain_audit", "텔레그램 통수 audit",
    "VAMS 월간 검증 리포트", "섹터 로테이션 vs Quadrant 정합성 경고",
))


def should_send_notification(text: str, source: str = "", kind: str = "unspecified") -> bool:
    """Apply notification preferences independently of quiet-hour bypass.

    Never infer importance from bypass_quiet: routine audits also use that flag.
    An explicit essential or command response always reaches existing safety gates.
    """
    if not essential_only_enabled():
        return True
    if kind in {"essential", "command"}:
        return True
    if kind == "routine":
        return False
    title = _title(text)
    return not any(title.startswith(prefix) for prefix in _ROUTINE_TITLE_PREFIXES)
