"""Order API 이상 감지 Telegram 경보.

audit payload 에서 임계 outcome 을 감지하면 Telegram 으로 fire-and-forget 알림.
주문 응답 흐름을 절대 block 하지 않도록 daemon thread 로 POST.

트리거 outcome:
  - exception:*   → 🚨 브로커 호출 중 예외 발생
  - broker_error  → ⚠️ 브로커 rt_cd != 0 실패 응답
  - auth_denied   → 🔒 인증 거부 (denied / none)

Dedupe: 동일 (outcome, ticker, auth_path) 키는 5분 내 억제.

Env:
  TELEGRAM_BOT_TOKEN   — 미설정 시 알림 비활성 (no-op)
  TELEGRAM_CHAT_ID     — 미설정 시 알림 비활성
  ORDER_ALERT_ENABLED  — "false"/"0"/"off" 이면 비활성 (기본: 활성)
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, Tuple

import requests

logger = logging.getLogger("order.alerts")

_DEDUPE_WINDOW_SEC = 300  # 5분
_dedupe_lock = threading.Lock()
_dedupe: Dict[Tuple[str, str, str], float] = {}

_TELEGRAM_API = "https://api.telegram.org"


def _enabled() -> bool:
    v = os.environ.get("ORDER_ALERT_ENABLED", "true").strip().lower()
    return v not in ("false", "0", "no", "off", "")


def _credentials() -> Tuple[str, str]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip().strip('"')
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip().strip('"')
    return token, chat


def _should_alert(audit: Dict[str, Any]) -> bool:
    outcome = str(audit.get("outcome", ""))
    if outcome.startswith("exception:"):
        return True
    if outcome == "broker_error":
        return True
    if outcome == "auth_denied":
        return True
    return False


def _dedupe_key(audit: Dict[str, Any]) -> Tuple[str, str, str]:
    return (
        str(audit.get("outcome", "?")),
        str(audit.get("ticker", "-")),
        str(audit.get("auth_path", "-")),
    )


def _is_duplicate(key: Tuple[str, str, str]) -> bool:
    """5분 dedupe. 처음 보면 False + 기록, 윈도 안이면 True."""
    now = time.time()
    with _dedupe_lock:
        last = _dedupe.get(key)
        if last is not None and (now - last) < _DEDUPE_WINDOW_SEC:
            return True
        _dedupe[key] = now
        if len(_dedupe) > 256:
            stale = [k for k, ts in _dedupe.items() if (now - ts) > _DEDUPE_WINDOW_SEC]
            for k in stale:
                _dedupe.pop(k, None)
    return False


def _html_escape(s: Any) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _format_message(audit: Dict[str, Any]) -> str:
    outcome = str(audit.get("outcome", ""))
    auth_path = str(audit.get("auth_path", "-"))
    http_status = audit.get("http_status", "?")
    latency = audit.get("latency_ms", "?")
    method = str(audit.get("method", "?"))
    ts = audit.get("ts")
    try:
        ts_str = datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        ts_str = "-"

    if outcome == "auth_denied":
        icon, title = "🔒", "주문 API 인증 실패"
    elif outcome == "broker_error":
        icon, title = "⚠️", "브로커 실패 응답"
    else:
        icon, title = "🚨", "주문 처리 예외"

    lines = [f"{icon} <b>VERITY {_html_escape(title)}</b>", ""]
    lines.append(f"endpoint: {_html_escape(method)} /api/order")
    lines.append(f"auth: <code>{_html_escape(auth_path)}</code>")
    lines.append(f"outcome: <code>{_html_escape(outcome)}</code>")

    ticker = audit.get("ticker")
    if ticker:
        lines.append(
            f"order: {_html_escape(ticker)} "
            f"({_html_escape(audit.get('side', '?'))} × {audit.get('qty', '?')} "
            f"@ {audit.get('price', '?')}) "
            f"[{_html_escape(audit.get('market', '?'))}]"
        )

    rt_cd = audit.get("broker_rt_cd")
    msg_cd = audit.get("broker_msg_cd")
    if rt_cd is not None or msg_cd is not None:
        lines.append(
            f"broker: rt_cd={_html_escape(rt_cd or '-')} "
            f"msg_cd={_html_escape(msg_cd or '-')}"
        )

    err = audit.get("error_msg")
    if err:
        lines.append(f"error: {_html_escape(str(err)[:200])}")

    lines.append(f"http: {http_status} · {latency}ms")
    lines.append(f"ts: {ts_str}")
    return "\n".join(lines)


def _post_telegram(token: str, chat_id: str, text: str) -> None:
    url = f"{_TELEGRAM_API}/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code != 200:
            logger.error(
                "telegram order alert 실패: %s %s",
                resp.status_code,
                resp.text[:200],
            )
    except Exception as e:
        logger.error("telegram order alert 예외: %s", e)


def _dispatch(token: str, chat_id: str, text: str) -> None:
    """Telegram POST 를 daemon thread 에 offload. 테스트에서 monkeypatch 지점."""
    threading.Thread(
        target=_post_telegram, args=(token, chat_id, text), daemon=True
    ).start()


def maybe_alert_from_audit(audit: Dict[str, Any]) -> bool:
    """audit payload 기반 알림 판단/전송.

    반환값: 실제 dispatch 가 일어났으면 True, 아니면 False (no-op).
    알림 실패는 로깅만 하고 예외를 던지지 않는다.
    """
    try:
        if not _should_alert(audit):
            return False
        if not _enabled():
            return False
        token, chat_id = _credentials()
        if not token or not chat_id:
            return False
        if _is_duplicate(_dedupe_key(audit)):
            return False
        text = _format_message(audit)
        _dispatch(token, chat_id, text)
        return True
    except Exception as e:
        logger.error("alert 파이프라인 예외: %s", e)
        return False


def reset_dedupe_cache() -> None:
    """테스트/수동 리셋용."""
    with _dedupe_lock:
        _dedupe.clear()
