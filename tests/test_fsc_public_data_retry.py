"""금융위 공공데이터 수집기 연결 재시도 검증 (2026-08-08).

배경: GH 러너 → apis.data.go.kr 이 간헐적으로 ConnectTimeout(거부·403 아님 = 방화벽 드롭).
kr_chart_daily.yml 최근 30 run 중 7 실패가 전부 `<urlopen error timed out>` 단발 호출.
같은 시각 한국 IP(개발 맥)는 0.9초 정상 → 러너 IP 추첨 의존.
연결 계층만 재시도하고, API 응답 에러(resultCode≠00)는 결정적이라 재시도하지 않는다.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(mod_name: str, rel_path: str):
    # 🚨 파일 직접 로드 — `-m`/패키지 import 는 api/collectors/__init__ 이 dotenv 를 당겨 pip 필요.
    path = os.path.join(_REPO_ROOT, *rel_path.split("/"))
    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


fsc_daily = _load("fsc_daily_prices_t", "api/collectors/fsc_daily_prices.py")
fsc_index = _load("fsc_index_prices_t", "api/collectors/fsc_index_prices.py")


class _FakeResp:
    def __init__(self, payload: str):
        self._payload = payload

    def read(self):
        return self._payload.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


_OK_BODY = json.dumps({"response": {"header": {"resultCode": "00"},
                                    "body": {"items": {"item": [{"basDt": "20260807"}]}}}})


@pytest.fixture(params=[fsc_daily, fsc_index], ids=["daily", "index"])
def mod(request, monkeypatch):
    monkeypatch.setattr(request.param, "_api_key", lambda: "k" * 64)
    monkeypatch.setattr(request.param.time, "sleep", lambda *_a: None)  # 백오프 대기 제거
    return request.param


def _patch_urlopen(monkeypatch, mod, behaviours):
    """behaviours = 호출 순서별 동작 리스트 (Exception 인스턴스 또는 응답 본문 str)."""
    calls = {"n": 0}

    def fake(req, timeout=None):
        i = calls["n"]
        calls["n"] += 1
        b = behaviours[min(i, len(behaviours) - 1)]
        if isinstance(b, Exception):
            raise b
        return _FakeResp(b)

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake)
    return calls


def test_transient_timeout_recovers_on_retry(monkeypatch, mod):
    # 1·2차 타임아웃 → 3차 성공. 단발 호출이면 여기서 워크플로가 exit 1 이던 자리.
    calls = _patch_urlopen(monkeypatch, mod, [TimeoutError("timed out"),
                                              TimeoutError("timed out"), _OK_BODY])
    body = mod._call({"numOfRows": 1, "pageNo": 1})
    assert body is not None
    assert calls["n"] == 3


def test_all_attempts_fail_returns_none(monkeypatch, mod):
    # 전 회차 실패 = None → 호출부가 exit 1 로 신고 (조용한 성공 종료 금지).
    calls = _patch_urlopen(monkeypatch, mod, [TimeoutError("timed out")])
    assert mod._call({"numOfRows": 1, "pageNo": 1}) is None
    assert calls["n"] == mod._NET_RETRIES


def test_api_error_code_not_retried(monkeypatch, mod):
    # resultCode≠00 = 결정적(키·쿼터·파라미터). 재시도해도 같은 답 → 1회로 끝낸다.
    err = json.dumps({"response": {"header": {"resultCode": "30", "resultMsg": "SERVICE KEY"}}})
    calls = _patch_urlopen(monkeypatch, mod, [err])
    assert mod._call({"numOfRows": 1, "pageNo": 1}) is None
    assert calls["n"] == 1


def test_malformed_body_not_retried(monkeypatch, mod):
    # 게이트웨이 XML 봉투 = 연결은 됐고 응답이 JSON 이 아닌 것 → 재시도 대상 아님.
    calls = _patch_urlopen(monkeypatch, mod, ["<OpenAPI_ServiceResponse>...</OpenAPI_ServiceResponse>"])
    assert mod._call({"numOfRows": 1, "pageNo": 1}) is None
    assert calls["n"] == 1


def test_retry_budget_is_bounded(mod):
    # 슬롯 timeout 10분 안에 들어와야 한다 — 재시도 대기 총합 상한 검증.
    assert mod._NET_RETRIES == 3
    assert sum(mod._NET_BACKOFF) <= 60
