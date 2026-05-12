"""
test_subscription_collector.py — odcloud API collector 검증.

DI 로 http_get 주입 (실 호출 X). 핵심:
    1) key 누락 → [] + log
    2) 정상 응답 → data 추출
    3) 페이지네이션 (matchCount 까지 누적)
    4) non-200 / JSON 오류 → [] (T1)
"""
import os
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from api.collectors import subscription_collector as collector


NOW = datetime(2026, 5, 12, 1, 0, 0, tzinfo=timezone.utc)


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, raise_json=False):
        self.status_code = status_code
        self._payload = payload
        self._raise_json = raise_json

    def json(self):
        if self._raise_json:
            raise ValueError("invalid json")
        return self._payload


def test_missing_api_key_returns_empty(monkeypatch):
    monkeypatch.delenv("PUBLIC_DATA_API_KEY", raising=False)
    out = collector.collect_subscriptions(now=NOW)
    assert out == []


def test_single_page_response(monkeypatch):
    monkeypatch.setenv("PUBLIC_DATA_API_KEY", "test_key")
    rows = [{"HOUSE_MANAGE_NO": "M1"}, {"HOUSE_MANAGE_NO": "M2"}]
    fake = _FakeResponse(200, {"data": rows, "matchCount": 2, "totalCount": 2, "currentCount": 2})

    def http_get(url, params=None, timeout=None):
        return fake

    out = collector.collect_subscriptions(now=NOW, _http_get=http_get)
    assert len(out) == 2
    assert out[0]["HOUSE_MANAGE_NO"] == "M1"


def test_pagination_until_match_count(monkeypatch):
    monkeypatch.setenv("PUBLIC_DATA_API_KEY", "test_key")

    page1 = _FakeResponse(200, {
        "data": [{"HOUSE_MANAGE_NO": "M1"}, {"HOUSE_MANAGE_NO": "M2"}],
        "matchCount": 3, "totalCount": 3, "currentCount": 2,
    })
    page2 = _FakeResponse(200, {
        "data": [{"HOUSE_MANAGE_NO": "M3"}],
        "matchCount": 3, "totalCount": 3, "currentCount": 1,
    })
    responses = iter([page1, page2])

    def http_get(url, params=None, timeout=None):
        return next(responses)

    out = collector.collect_subscriptions(now=NOW, _http_get=http_get)
    assert [r["HOUSE_MANAGE_NO"] for r in out] == ["M1", "M2", "M3"]


def test_non_200_returns_empty(monkeypatch):
    monkeypatch.setenv("PUBLIC_DATA_API_KEY", "test_key")
    fake = _FakeResponse(500, None)

    def http_get(url, params=None, timeout=None):
        return fake

    out = collector.collect_subscriptions(now=NOW, _http_get=http_get)
    assert out == []


def test_invalid_json_returns_empty(monkeypatch):
    monkeypatch.setenv("PUBLIC_DATA_API_KEY", "test_key")
    fake = _FakeResponse(200, None, raise_json=True)

    def http_get(url, params=None, timeout=None):
        return fake

    out = collector.collect_subscriptions(now=NOW, _http_get=http_get)
    assert out == []
