"""chat_hybrid.metrics 집계기 검증 — scripts/report_chat_hybrid.py.

텍스트 리포트/Telegram 전송은 side-effect 이므로 제외하고,
순수 함수(aggregate, _extract_payload, iter_payloads, format_report) 만 단위 테스트.
"""
import json
import os
import sys

import pytest

# scripts/ 가 sys.path 에 없으므로 파일 경로로 import
_SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import report_chat_hybrid as rep  # type: ignore


def _metric_line(payload: dict) -> str:
    """Vercel 로그 한 줄 모사 — prefix + JSON."""
    return f"2026-04-23T14:22:10 [info] chat_hybrid.metrics {json.dumps(payload)}"


# ──────────────────────────────────────────────
# 1. _extract_payload — 파서 견고성
# ──────────────────────────────────────────────

def test_extract_happy_path():
    line = _metric_line({"outcome": "success", "total_ms": 100})
    assert rep._extract_payload(line) == {"outcome": "success", "total_ms": 100}


def test_extract_ignores_unrelated_line():
    assert rep._extract_payload("2026-04-23 some other log message") is None


def test_extract_ignores_prefix_without_json():
    assert rep._extract_payload("chat_hybrid.metrics not json here") is None


def test_extract_handles_trailing_noise():
    """raw_decode 는 첫 JSON object 만 — 뒤에 텍스트 붙어도 OK."""
    payload = {"outcome": "success"}
    line = _metric_line(payload) + " trailing noise"
    assert rep._extract_payload(line) == payload


def test_iter_payloads_filters_mixed_lines():
    lines = [
        "random line",
        _metric_line({"outcome": "success"}),
        "other log",
        _metric_line({"outcome": "reject:empty"}),
    ]
    out = list(rep.iter_payloads(lines))
    assert len(out) == 2
    assert out[0]["outcome"] == "success"
    assert out[1]["outcome"] == "reject:empty"


# ──────────────────────────────────────────────
# 2. aggregate — 외형/분류
# ──────────────────────────────────────────────

def test_aggregate_empty():
    s = rep.aggregate([])
    assert s["total"] == 0
    assert s["outcomes"] == {}
    assert s["outcome_groups"] == {}
    assert s["cost_est_sum"] == 0


def test_aggregate_outcome_groups():
    payloads = [
        {"outcome": "success"},
        {"outcome": "success"},
        {"outcome": "reject:empty"},
        {"outcome": "reject:rate_limit:ip"},
        {"outcome": "error:RuntimeError"},
        {"outcome": "deadline_exceeded"},
        {"outcome": "weird_custom"},
    ]
    s = rep.aggregate(payloads)
    assert s["total"] == 7
    assert s["outcome_groups"]["success"] == 2
    assert s["outcome_groups"]["reject"] == 2
    assert s["outcome_groups"]["error"] == 2
    assert s["outcome_groups"]["other"] == 1


def test_aggregate_intent_types_and_sources():
    payloads = [
        {"outcome": "success", "intent_type": "hybrid", "intent_source": "gemini"},
        {"outcome": "success", "intent_type": "hybrid", "intent_source": "cache"},
        {"outcome": "success", "intent_type": "portfolio_only", "intent_source": "quick_rules"},
    ]
    s = rep.aggregate(payloads)
    assert s["intent_types"] == {"hybrid": 2, "portfolio_only": 1}
    assert s["intent_sources"] == {"gemini": 1, "cache": 1, "quick_rules": 1}


def test_aggregate_intent_cache_hit_rate():
    payloads = [
        {"outcome": "success", "intent_cache_hit": True},
        {"outcome": "success", "intent_cache_hit": False},
        {"outcome": "success", "intent_cache_hit": True},
        {"outcome": "success"},  # intent_cache_hit 없음 → seen 에 미포함
    ]
    s = rep.aggregate(payloads)
    assert s["intent_cache"]["hit"] == 2
    assert s["intent_cache"]["seen"] == 3
    assert s["intent_cache"]["hit_pct"] == round(2 / 3 * 100, 1)


def test_aggregate_perplexity_and_grounding_stats():
    payloads = [
        {"outcome": "success",
         "perplexity": {"ok": True, "cache_hit": False},
         "grounding": {"ok": True, "cache_hit": True}},
        {"outcome": "success",
         "perplexity": {"ok": False, "cache_hit": False}},
        {"outcome": "success"},  # 외부 호출 없음
    ]
    s = rep.aggregate(payloads)
    assert s["perplexity"]["called"] == 2
    assert s["perplexity"]["ok"] == 1
    assert s["perplexity"]["cache_hit"] == 0
    assert s["grounding"]["called"] == 1
    assert s["grounding"]["ok"] == 1
    assert s["grounding"]["cache_hit"] == 1


def test_aggregate_latency_only_from_success():
    """reject/error 의 total_ms 는 집계에 포함되지 않아야 함."""
    payloads = [
        {"outcome": "success", "total_ms": 100, "stages": {"intent": 10, "brain": 5}},
        {"outcome": "success", "total_ms": 200, "stages": {"intent": 20, "brain": 8}},
        {"outcome": "success", "total_ms": 300, "stages": {"intent": 30, "brain": 10}},
        {"outcome": "reject:empty", "total_ms": 9999},
        {"outcome": "error:X", "total_ms": 9999},
    ]
    s = rep.aggregate(payloads)
    lat = s["latency_success"]["total_ms"]
    assert lat["n"] == 3
    assert lat["p50"] == 200
    assert lat["max"] == 300
    intent_lat = s["latency_success"]["stages"]["intent"]
    assert intent_lat["n"] == 3
    assert intent_lat["p50"] == 20


def test_aggregate_cost_sum_and_avg():
    payloads = [
        {"outcome": "success", "cost_est": 0.01},
        {"outcome": "success", "cost_est": 0.03},
        {"outcome": "reject:empty", "cost_est": 0},  # reject 는 avg 분모에 미포함
        {"outcome": "success", "cost_est": None},    # None 안전 처리
    ]
    s = rep.aggregate(payloads)
    assert s["cost_est_sum"] == 0.04
    # avg 분모 = success 수(3)
    assert s["cost_est_avg_success"] == round(0.04 / 3, 4)


def test_aggregate_error_samples_truncated():
    payloads = [
        {"outcome": f"error:Err{i}", "error_msg": f"msg {i}"} for i in range(7)
    ]
    s = rep.aggregate(payloads)
    assert len(s["error_samples"]) == 5  # 최대 5건
    for sample in s["error_samples"]:
        assert "msg " in sample


# ──────────────────────────────────────────────
# 3. format_report — 출력 형식
# ──────────────────────────────────────────────

def test_format_empty_report():
    s = rep.aggregate([])
    text = rep.format_report(s, label="2026-04-23")
    assert "VERITY Chat Hybrid" in text
    assert "2026-04-23" in text
    assert "로그 없음" in text


def test_format_non_empty_contains_key_sections():
    payloads = [
        {"outcome": "success", "intent_type": "hybrid", "intent_source": "gemini",
         "intent_cache_hit": True, "total_ms": 1500,
         "stages": {"intent": 50, "brain": 20, "external": 800, "synth": 600},
         "perplexity": {"ok": True, "cache_hit": False},
         "grounding": {"ok": True, "cache_hit": False},
         "cost_est": 0.012},
        {"outcome": "reject:rate_limit:ip"},
        {"outcome": "error:RuntimeError", "error_msg": "connection reset"},
    ]
    s = rep.aggregate(payloads)
    text = rep.format_report(s)
    assert "요청 수: 3" in text
    assert "✅ 1" in text and "reject 1" in text and "error 1" in text
    assert "hybrid=1" in text
    assert "Perplexity" in text
    assert "Grounding" in text
    assert "총 지연" in text
    assert "connection reset" in text


def test_format_no_error_section_when_no_errors():
    payloads = [{"outcome": "success", "total_ms": 100, "cost_est": 0.001}]
    s = rep.aggregate(payloads)
    text = rep.format_report(s)
    assert "최근 에러 샘플" not in text
