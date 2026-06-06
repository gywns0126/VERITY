"""
generate_with_cache 503/일시적 과부하 내성 회귀 테스트.

2026-06-06 사고: 월간/주간(periodic) 리포트가 Gemini 503 UNAVAILABLE 에 단발로 실패 →
_fallback_periodic("AI 리포트 생성 실패 (503...)"). 6/3 503 fix(f16e11c5)는 공개 일일
리포트 caller(daily_public._default_gemini_caller)에만 들어가 있었고, periodic/stock_analysis/
chat 의 단일 chokepoint generate_with_cache 는 보호 부재였음.

게이트: generate_with_cache = 모델별 backoff 2회 + 모델 폴백(GEMINI_MODEL_CHAT).
transient(503/429/500/overloaded)만 재시도, 비일시적(400)은 즉시 raise.
"""
import os

import pytest

import api.utils.gemini_cache as gc


class _Resp:
    text = '{"ok": 1}'


class _Models:
    def __init__(self, fail_models):
        self.fail = set(fail_models)
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        if model in self.fail:
            raise Exception("503 UNAVAILABLE high demand")
        return _Resp()


class _Client:
    def __init__(self, fail_models):
        self.models = _Models(fail_models)


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    # 캐시 등록 우회 + backoff 즉시
    monkeypatch.setattr(gc, "get_or_create_cache", lambda *a, **k: None)
    monkeypatch.setattr(gc.time, "sleep", lambda s: None)
    monkeypatch.setenv("GEMINI_MODEL_CHAT", "gemini-2.5-flash-lite")


def _call(client):
    return gc.generate_with_cache(
        client, model="gemini-2.5-flash", contents="x", system_instruction="s"
    )


def test_primary_ok_single_call():
    c = _Client(set())
    assert _call(c).text == '{"ok": 1}'
    assert c.models.calls == ["gemini-2.5-flash"]


def test_primary_503_falls_back_to_secondary():
    c = _Client({"gemini-2.5-flash"})
    assert _call(c).text == '{"ok": 1}'
    # primary 2회 시도 후 flash-lite 폴백 성공
    assert c.models.calls == [
        "gemini-2.5-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite",
    ]


def test_all_models_exhausted_raises():
    c = _Client({"gemini-2.5-flash", "gemini-2.5-flash-lite"})
    with pytest.raises(Exception) as ei:
        _call(c)
    assert "503" in str(ei.value)
    assert c.models.calls.count("gemini-2.5-flash") == 2
    assert c.models.calls.count("gemini-2.5-flash-lite") == 2


def test_non_transient_400_raises_immediately():
    c = _Client(set())

    def _raise400(model, contents, config):
        c.models.calls.append(model)
        raise Exception("400 INVALID_ARGUMENT")

    c.models.generate_content = _raise400
    with pytest.raises(Exception) as ei:
        _call(c)
    assert "400" in str(ei.value)
    # 비일시적 = 재시도/폴백 0 (단발)
    assert c.models.calls == ["gemini-2.5-flash"]
