"""
test_policy_narrative.py — Step 3 한줄평 모듈 검증

명령서 4 케이스 (정상 / 5xx / timeout / 빈 입력) + 보강 (T17·T18·trim).
"""
import json
import sys

import pytest

from api import policy_narrative
from api.policy_narrative import ANTHROPIC_MODEL, generate_policy_briefing


def _p(title: str = "공시가격 9.13% 상승 발표", raw_text: str = "전국 공동주택 공시가격 평균 9.13% 상승") -> dict:
    return {
        "id": "x-1",
        "title": title,
        "source_url": "https://www.korea.kr/news/test",
        "source_name": "국토교통부",
        "published_at": "2026-04-30T05:00:00+00:00",
        "raw_text": raw_text,
    }


# ───────────────── 1. 정상 응답 ─────────────────

def test_normal_returns_headline_confidence_tokens():
    """LLM 정상 응답 → headline·confidence·tokens_used 반환."""
    def fake_llm(_policy):
        return {
            "headline": "보유세 충격이 매도 압력으로 전환되는 구간",
            "confidence": 0.78,
            "tokens_used": 412,
        }
    out = generate_policy_briefing(_p(), _llm_fn=fake_llm)
    assert out is not None
    assert out["headline"] == "보유세 충격이 매도 압력으로 전환되는 구간"
    assert out["confidence"] == 0.78
    assert out["tokens_used"] == 412


# ───────────────── 2. 5xx ─────────────────

def test_5xx_returns_none_and_logs(monkeypatch, caplog):
    """T1·T2·T9 — Anthropic 5xx 시 None + 명시 로그 (mock 폴백 X)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")

    class _FakeAPIError(Exception):
        pass

    class FakeMessages:
        def create(self, **kwargs):
            raise _FakeAPIError("upstream 503")

    class FakeClient:
        def __init__(self, **kwargs):
            self.messages = FakeMessages()

    monkeypatch.setitem(sys.modules, "anthropic", type("m", (), {"Anthropic": FakeClient}))

    with caplog.at_level("ERROR", logger="api.policy_narrative"):
        out = generate_policy_briefing(_p())

    assert out is None  # T2 — mock 텍스트 없음
    assert any("anthropic call failed" in r.message for r in caplog.records)


# ───────────────── 3. timeout ─────────────────

def test_timeout_returns_none_and_logs(monkeypatch, caplog):
    """timeout 도 5xx 와 동일 처리 — None + 로그."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")

    class FakeMessages:
        def create(self, **kwargs):
            raise TimeoutError("read timeout 15s")

    class FakeClient:
        def __init__(self, **kwargs):
            self.messages = FakeMessages()

    monkeypatch.setitem(sys.modules, "anthropic", type("m", (), {"Anthropic": FakeClient}))

    with caplog.at_level("ERROR", logger="api.policy_narrative"):
        out = generate_policy_briefing(_p())

    assert out is None
    assert any("anthropic call failed" in r.message for r in caplog.records)


# ───────────────── 4. 빈 정책 dict (입력 검증) ─────────────────

def test_empty_policy_returns_none_and_logs(caplog):
    """입력 검증 실패 — None + 명시 로그."""
    with caplog.at_level("ERROR", logger="api.policy_narrative"):
        assert generate_policy_briefing({}) is None
        assert generate_policy_briefing({"title": ""}) is None
        assert generate_policy_briefing({"title": None}) is None
        assert generate_policy_briefing(None) is None
    assert any("invalid input" in r.message for r in caplog.records)


# ───────────────── 5. T17 + T18 통합 (실 호출 path mock) ─────────────────

def test_uses_sonnet_model_and_logs_to_jsonl(tmp_path, monkeypatch):
    """T17 모델 검증 + T18 anthropic_calls.jsonl 기록 검증."""
    log_path = tmp_path / "logs" / "anthropic_calls.jsonl"
    monkeypatch.setattr(policy_narrative, "ANTHROPIC_LOG_PATH", str(log_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")

    captured = {}

    class FakeUsage:
        input_tokens = 200
        output_tokens = 30

    class FakeContent:
        text = '{"headline": "보유세 충격이 매도 압력으로 전환되는 구간", "confidence": 0.78}'

    class FakeMsg:
        usage = FakeUsage()
        content = [FakeContent()]

    class FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return FakeMsg()

    class FakeClient:
        def __init__(self, **kwargs):
            self.messages = FakeMessages()

    monkeypatch.setitem(sys.modules, "anthropic", type("m", (), {"Anthropic": FakeClient}))

    out = generate_policy_briefing(_p())

    # T17 — 모델 확인 (claude-sonnet-4-20250514 — haiku/opus 금지)
    assert captured["model"] == "claude-sonnet-4-20250514"
    assert captured["max_tokens"] == 200
    # 출력 검증
    assert out is not None
    assert out["headline"] == "보유세 충격이 매도 압력으로 전환되는 구간"
    assert out["confidence"] == 0.78
    assert out["tokens_used"] == 230  # input + output

    # T18 — 로그 한 줄
    assert log_path.exists()
    lines = [l for l in log_path.read_text(encoding="utf-8").split("\n") if l.strip()]
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["model"] == "claude-sonnet-4-20250514"
    assert rec["input_tokens"] == 200
    assert rec["output_tokens"] == 30
    assert rec["function_name"] == "generate_policy_briefing"
    assert rec["timestamp"]


# ───────────────── 6. 50자 cap ─────────────────

def test_headline_over_50_chars_is_trimmed():
    """LLM이 50자 초과 응답해도 50자로 자동 trim."""
    long_text = "보유세 충격이 매도 압력으로 전환되는 구간이며 Q2~Q3 동안 핵심 5구의 매물 증감이 가속화될 것"
    assert len(long_text) > 50
    out = generate_policy_briefing(_p(), _llm_fn=lambda _x: {
        "headline": long_text, "confidence": 0.7, "tokens_used": 100,
    })
    assert out is not None
    assert len(out["headline"]) == 50
    assert out["headline"] == long_text[:50]


# ───────────────── 7. 응답 파싱 실패 ─────────────────

def test_unparseable_response_returns_none(monkeypatch, caplog):
    """LLM 이 JSON 외 텍스트 반환 → None + 로그."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")

    class FakeUsage:
        input_tokens = 100
        output_tokens = 10
    class FakeContent:
        text = "응답 형식이 깨짐 — JSON 없음"
    class FakeMsg:
        usage = FakeUsage()
        content = [FakeContent()]
    class FakeMessages:
        def create(self, **kwargs):
            return FakeMsg()
    class FakeClient:
        def __init__(self, **kwargs):
            self.messages = FakeMessages()
    monkeypatch.setitem(sys.modules, "anthropic", type("m", (), {"Anthropic": FakeClient}))

    with caplog.at_level("ERROR", logger="api.policy_narrative"):
        out = generate_policy_briefing(_p())
    assert out is None
    assert any("response parse failed" in r.message for r in caplog.records)


# ───────────────── 8. API key 없음 ─────────────────

def test_no_api_key_returns_none(monkeypatch, caplog):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with caplog.at_level("ERROR", logger="api.policy_narrative"):
        out = generate_policy_briefing(_p())
    assert out is None
    assert any("ANTHROPIC_API_KEY missing" in r.message for r in caplog.records)


# ───────────────── 9. confidence 없는 응답 — default 처리 ─────────────────

def test_missing_confidence_defaults_to_06(caplog):
    out = generate_policy_briefing(_p(), _llm_fn=lambda _x: {
        "headline": "정책 영향 시그널", "tokens_used": 50,
    })
    assert out is not None
    assert out["confidence"] == 0.6  # default 명시
