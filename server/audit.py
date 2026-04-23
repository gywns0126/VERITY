"""Order API 감사 로그 — 실자금 주문 경로 추적.

구조화 JSON 한 줄을 `order.audit` 로거로 emit. Railway/Vercel 로그에서:

    logs | grep 'order.audit' | jq '.'

대표 필드:
    ts, endpoint, method, auth_path (primary/legacy/denied/none),
    outcome (success/auth_denied/validation:*/broker_error/exception:*),
    http_status, latency_ms
  POST 추가:
    market, ticker, side, qty, price, order_type, excd
  브로커 응답:
    broker_rt_cd, broker_msg_cd, broker_order_no
  실패:
    error_type, error_msg (200자 절단)

미포함 (의도):
    토큰/비밀/Authorization 헤더 값은 절대 로그에 남기지 않는다.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

_audit_logger = logging.getLogger("order.audit")


def emit(payload: Dict[str, Any]) -> None:
    """감사 로그 한 줄 emit. 로깅 실패가 요청 흐름을 깨지 않도록 swallow."""
    try:
        _audit_logger.info(
            "order.audit %s",
            json.dumps(payload, ensure_ascii=False, default=str),
        )
    except Exception:
        pass
