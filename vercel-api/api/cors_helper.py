"""공용 CORS origin whitelist (/api/chat, /api/watchgroups 등 보호된 엔드포인트 용).

env `API_ALLOWED_ORIGINS` — 쉼표 구분 허용 origin 목록.

정책:
  - 미설정이면 빈 whitelist → `resolve_origin()` 이 빈 문자열 반환 → 호출자가 CORS 헤더
    자체를 안 붙여 브라우저가 크로스오리진 요청 차단.
  - `*` 값은 명시적으로 제거 (wildcard 금지). 필요한 origin 을 명시해야 함.

참고: 주문 엔드포인트(`/api/order`) 는 이미 `ORDER_ALLOWED_ORIGINS` 로 별도 관리.
      더 엄격한 도메인 리스트를 유지하고자 별도 env 로 분리.
"""
from __future__ import annotations

import logging
import os
from typing import FrozenSet

_logger = logging.getLogger(__name__)

_raw = os.environ.get("API_ALLOWED_ORIGINS", "") or ""

# 🚨 2026-07-24 AlphaNest 프로덕션 origin = 코드 기본 허용. env(API_ALLOWED_ORIGINS) 누락/오설정에도
#   공개 사이트가 watchgroups·holdings 등 인증 API 를 호출할 수 있게(별 담기 안 됨·로그인 후 데모종목
#   잔존의 근본 원인 = 프리플라이트에 ACAO 없음). wildcard 아님 — 명시 origin 만(JWT+wildcard CSRF 금지 정합).
_DEFAULT_ORIGINS: FrozenSet[str] = frozenset(
    {
        "https://www.alphanest.kr",
        "https://alphanest.kr",
    }
)

_env_origins: FrozenSet[str] = frozenset(
    o for o in (s.strip() for s in _raw.split(",")) if o and o != "*"
)
ALLOWED_ORIGINS: FrozenSet[str] = _env_origins | _DEFAULT_ORIGINS
_WILDCARD_IN_ENV = any(s.strip() == "*" for s in _raw.split(","))

if not _env_origins:
    _logger.warning(
        "API_ALLOWED_ORIGINS 미설정 — 코드 기본 origin(%s)만 허용",
        ", ".join(sorted(_DEFAULT_ORIGINS)),
    )
if _WILDCARD_IN_ENV:
    _logger.warning("API_ALLOWED_ORIGINS 에 '*' 포함됨 — 무시. 명시 origin 만 사용")


def resolve_origin(request_origin: str) -> str:
    """허용 origin 이면 그대로 반환, 아니면 빈 문자열.

    호출자는 빈 문자열이면 `Access-Control-Allow-Origin` 헤더를 아예 붙이지 않아
    브라우저가 응답을 거부하게 한다.
    """
    request_origin = (request_origin or "").strip()
    if not ALLOWED_ORIGINS:
        return ""
    return request_origin if request_origin in ALLOWED_ORIGINS else ""
