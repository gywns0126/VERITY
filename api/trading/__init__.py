"""
Trading module — KIS Broker (실계좌) + MockKISBroker (로컬 검증) 팩토리.

환경변수 우선순위:
  1. USE_MOCK_BROKER=true  → 무조건 Mock
  2. USE_MOCK_BROKER=false → 무조건 실계좌 (토큰 없으면 예외)
  3. 미지정 시: VERITY_MODE != prod 이거나 KIS 토큰 부재 시 Mock 자동 선택
"""
from __future__ import annotations

import os
from typing import Optional


def _env_bool(name: str) -> Optional[bool]:
    raw = os.environ.get(name, "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return None


def get_broker(force_mock: bool = False):
    """환경에 따라 KISBroker 또는 MockKISBroker 반환.

    Args:
        force_mock: True면 환경변수 무시하고 Mock 반환 (테스트용).
    """
    from api.config import VERITY_MODE, KIS_ENABLED

    if force_mock:
        return _mock_broker()

    explicit = _env_bool("USE_MOCK_BROKER")
    if explicit is True:
        return _mock_broker()
    if explicit is False:
        return _real_broker()

    if VERITY_MODE != "prod":
        return _mock_broker()
    if not KIS_ENABLED:
        return _mock_broker()

    return _real_broker()


def _mock_broker():
    from api.trading.mock_kis_broker import MockKISBroker
    return MockKISBroker.from_portfolio()


def _real_broker():
    from api.trading.kis_broker import KISBroker
    broker = KISBroker()
    if not broker.is_configured:
        raise RuntimeError(
            "KIS_APP_KEY/KIS_APP_SECRET 미설정. "
            "로컬 검증은 USE_MOCK_BROKER=true 로 실행하세요."
        )
    return broker


__all__ = ["get_broker"]
