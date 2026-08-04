# -*- coding: utf-8 -*-
"""llm_cost 관측 배선 (Task#9) — Claude·Perplexity 장부 기록.

핵심 계약: 헬퍼는 절대 raise 하지 않는다(관측이 본업을 못 죽인다) /
Perplexity 는 usage.cost 실비 우선 / 모델 prefix 폴백으로 날짜 suffix 변형 대응.
"""
import json
from types import SimpleNamespace as NS

import api.metadata.llm_cost as lc


def _ledger(tmp_path, monkeypatch):
    p = tmp_path / "llm_cost.jsonl"
    monkeypatch.setattr(lc, "_PATH", str(p))
    return p


def _read(p):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()]


def test_log_anthropic_writes_usage_and_cost(tmp_path, monkeypatch):
    p = _ledger(tmp_path, monkeypatch)
    resp = NS(model="claude-opus-5", usage=NS(input_tokens=1_000_000, output_tokens=0))
    lc.log_anthropic(resp, "unit")
    e = _read(p)[0]
    assert e["provider"] == "anthropic" and e["model"] == "claude-opus-5"
    assert e["input_tokens"] == 1_000_000 and e["cost_usd"] == 5.0  # $5/1M input


def test_log_anthropic_never_raises_on_garbage(tmp_path, monkeypatch):
    _ledger(tmp_path, monkeypatch)
    lc.log_anthropic(None, "unit")
    lc.log_anthropic(object(), "unit")  # usage 없음 — 무기록/무예외면 합격


def test_log_perplexity_prefers_actual_cost(tmp_path, monkeypatch):
    p = _ledger(tmp_path, monkeypatch)
    data = {"model": "sonar-pro", "usage": {"prompt_tokens": 100, "completion_tokens": 50,
                                            "cost": {"total_cost": 0.0042}}}
    lc.log_perplexity(data, "sonar-pro", "unit")
    assert _read(p)[0]["cost_usd"] == 0.0042  # 실비 우선 (단가 추정 아님)


def test_log_perplexity_estimates_without_cost(tmp_path, monkeypatch):
    p = _ledger(tmp_path, monkeypatch)
    data = {"usage": {"prompt_tokens": 1_000_000, "completion_tokens": 0}}
    lc.log_perplexity(data, "sonar", "unit")
    assert _read(p)[0]["cost_usd"] == 1.0  # sonar $1/1M


def test_log_perplexity_ignores_non_dict(tmp_path, monkeypatch):
    p = _ledger(tmp_path, monkeypatch)
    lc.log_perplexity(None, "sonar", "unit")
    lc.log_perplexity("err", "sonar", "unit")
    assert not p.exists()  # 무기록


def test_estimate_cost_prefix_fallback():
    exact = lc.estimate_cost("claude-sonnet-5", 1_000_000, 0)
    dated = lc.estimate_cost("claude-sonnet-5-20260901", 1_000_000, 0)
    assert exact == dated == 3.0
    assert lc.estimate_cost("unknown-model", 1_000_000, 0) == 0.0
