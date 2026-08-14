"""health._check_public_data — 드롭성 실패 재시도 회귀 테스트 (네트워크 0).

2026-08-13 신설. 고정하려는 사고:

  `apis.data.go.kr`(관세청 무역통계)은 GitHub 러너 IP 를 간헐적으로 드롭한다. 원장
  `data/metadata/data_health.jsonl` 244건 실측 = ok 238 / warning 4 / critical 2.
  critical 2건(8/08 07:32 · 8/13 18:25)의 latency 가 8,275ms · 8,574ms 로 **옛 하드코딩
  timeout=8 에 정확히 걸린 값**이었다. 정상 응답은 0.7~1.2초라 "느려짐"이 아니라 무응답이다.
  같은 날 00:32·08:42 는 정상이었으므로 지속 장애가 아니라 단발 드롭인데, 그 1회가
  `overall=critical` 을 만들고 텔레그램 알림을 띄웠다.

이 파일이 지키는 계약은 넷이다.
  ① 드롭성 실패(타임아웃)는 1회 재시도한다 — 2차 성공이면 ok
  ② 2차 성공을 **조용히 삼키지 않는다** — detail 에 1차 실패가 남아야 원장에서 빈도가 보인다
  ③ 결정적 실패(키 거부·요청 오류·비200)는 **재시도하지 않는다** — 진짜 장애 발견이 늦어진다
  ④ 2회 모두 드롭이면 실패로 종결하고 시도 횟수를 남긴다
"""
from __future__ import annotations

import pytest
import requests

import api.health as health


class _Resp:
    def __init__(self, status: int, text: str = "<ok/>"):
        self.status_code = status
        self.text = text


@pytest.fixture(autouse=True)
def _no_sleep_and_key(monkeypatch):
    monkeypatch.setattr(health.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(health, "PUBLIC_DATA_API_KEY", "test-key")
    yield


def _patch(monkeypatch, seq):
    """seq = 호출마다 반환할 값(예외 인스턴스면 raise). 호출 횟수를 함께 돌려준다."""
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(timeout)
        item = seq[min(len(calls) - 1, len(seq) - 1)]
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(health.requests, "get", fake_get)
    return calls


def test_timeout_then_success_is_ok_and_reported(monkeypatch):
    """①② 1차 타임아웃 → 2차 성공 = ok, 단 detail 에 흔적이 남는다."""
    calls = _patch(monkeypatch, [requests.Timeout("drop"), _Resp(200)])

    ok, detail = health._check_public_data()

    assert ok is True
    assert len(calls) == 2, "재시도가 안 걸렸다"
    assert "재시도" in detail and "타임아웃" in detail, f"1차 실패가 삼켜졌다: {detail}"


def test_first_try_success_has_no_retry_noise(monkeypatch):
    """정상 경로는 그대로 '정상' — 잡음 추가 금지."""
    calls = _patch(monkeypatch, [_Resp(200)])

    ok, detail = health._check_public_data()

    assert ok is True and detail == "정상"
    assert len(calls) == 1


@pytest.mark.parametrize(
    "resp,expect",
    [
        (_Resp(500), "HTTP 500"),
        (_Resp(200, "<errMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</errMsg>"), "키 거부"),
        (_Resp(200, "INVALID_REQUEST_PARAMETER_ERROR"), "요청 오류"),
    ],
)
def test_deterministic_failure_is_not_retried(monkeypatch, resp, expect):
    """③ 응답이 온 실패 = 결정적. 두 번 때리지 않는다."""
    calls = _patch(monkeypatch, [resp])

    ok, detail = health._check_public_data()

    assert ok is False
    assert expect in detail
    assert len(calls) == 1, f"결정적 실패인데 {len(calls)}회 호출 — 진짜 장애 발견이 늦어진다"


def test_two_drops_fail_with_attempt_count(monkeypatch):
    """④ 2회 모두 드롭이면 실패 + 시도 횟수 명시."""
    calls = _patch(monkeypatch, [requests.Timeout("drop")])

    ok, detail = health._check_public_data()

    assert ok is False
    assert len(calls) == 2
    assert "2회 시도" in detail


def test_uses_shared_timeout_constant(monkeypatch):
    """하드코딩 8 대신 공용 상수 — 타임아웃 정책이 한 곳에서 바뀌게."""
    calls = _patch(monkeypatch, [_Resp(200)])

    health._check_public_data()

    assert calls[0] == health._TIMEOUT_DEFAULT


def test_missing_key_short_circuits(monkeypatch):
    """키 미설정은 네트워크를 아예 안 탄다."""
    monkeypatch.setattr(health, "PUBLIC_DATA_API_KEY", "")
    calls = _patch(monkeypatch, [_Resp(200)])

    ok, detail = health._check_public_data()

    assert ok is False and detail == "키 미설정"
    assert len(calls) == 0
