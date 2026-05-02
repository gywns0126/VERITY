"""
test_estate_hero_briefing_builder.py — Step 4 통합 빌더 검증

명령서 4 케이스 (정상 / 정책0건폴백 / AI실패폴백 / 수집실패) + 보강.

T20 meta 통계 가짜 X — policy_24h, success_rate_7d 실측 검증.
T21 JSON 갱신 정책 — 3단계 분기 (정상/부분실패/전체실패) 모두 검증.
T22 단위 테스트 mock 기반 — DI 로 collector·classifier·LLM·LANDEX 주입.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from api.builders import estate_hero_briefing_builder as builder
from api.builders.estate_hero_briefing_builder import (
    LANDEX_RULE_BASED_MODEL,
    NARRATIVE_AI_MODEL,
    SCHEMA_VERSION,
    build,
    build_landex_fallback,
    main,
)


NOW = datetime(2026, 5, 2, 14, 0, 0, tzinfo=timezone.utc)


def _policy(
    pid: str,
    title: str,
    pub_offset_h: int = 0,
    raw_text: str = "공시가격 상승",
    source: str = "국토교통부",
    url: str = "https://www.korea.kr/news/x",
) -> dict:
    pub = NOW - timedelta(hours=pub_offset_h)
    return {
        "id": pid,
        "title": title,
        "source_url": url,
        "source_name": source,
        "published_at": pub.isoformat(),
        "raw_text": raw_text,
    }


def _landex_payload(generated_at: str = None) -> dict:
    g = generated_at or NOW.isoformat()
    return build_landex_fallback(
        landex_rows=[
            {"gu": "성동구", "landex_wow_delta": 3.2},
            {"gu": "강남구", "landex_wow_delta": 2.8},
            {"gu": "송파구", "landex_wow_delta": 2.5},
            {"gu": "용산구", "landex_wow_delta": 1.1},
        ],
        generated_at=g,
    )


# ───────────────────────── 케이스 1: 정상 — 24h 정책 ─────────────────────────

def test_case1_normal_24h_policy_triggers_ai_narrative():
    """정상 — 24h 정책 1건 + AI 성공 → policy 트리거 + AI narrative."""
    pol = _policy("p1", "공시가격 9.13% 상승", pub_offset_h=2,
                  raw_text="공시가격 상승으로 종부세 재산세 부담 증가")

    def fake_collect(lookback_hours: int, now=None):
        return [pol] if lookback_hours >= 24 else [pol]

    def fake_classify(p):
        return {"category": "tax", "stage": 3, "affected_regions": ["서울 강남구"],
                "confidence": 0.85, "method": "keywords",
                "keywords_matched": {}, "llm": None}

    def fake_generate(p):
        return {"headline": "보유세 충격이 매도 압력으로 전환되는 구간",
                "confidence": 0.78, "tokens_used": 412}

    out = build(
        now=NOW,
        _collect=fake_collect, _classify=fake_classify,
        _generate=fake_generate,
        _fetch_landex=lambda _now: None,  # 도달하지 않음
        _success_rate_7d=lambda _now: 0.93,
    )

    assert out is not None
    assert out["schema_version"] == SCHEMA_VERSION
    assert out["generated_at"] == NOW.isoformat()
    # policy section
    assert out["policy"]["id"] == "p1"
    assert out["policy"]["title"] == "공시가격 9.13% 상승"
    assert out["policy"]["source"] == "국토교통부"
    assert out["policy"]["category"] == "tax"
    assert "서울 강남구" in out["policy"]["affected_regions"]
    # narrative
    assert out["narrative"]["headline"] == "보유세 충격이 매도 압력으로 전환되는 구간"
    assert out["narrative"]["ai"]["model"] == NARRATIVE_AI_MODEL
    assert out["narrative"]["ai"]["fallback_used"] is False
    assert out["narrative"]["ai"]["tokens"] == 412
    # operator_meta
    assert out["operator_meta"]["data_source"] == "policy_24h"
    assert out["operator_meta"]["wire_status"] == "P2"
    assert out["operator_meta"]["policy_24h"] == 1  # T20 — 실측
    assert out["operator_meta"]["ai_success_7d"] == 0.93
    assert out["operator_meta"]["freshness_minutes"] == 120  # 2시간 = 120분


# ───────────────────────── 케이스 2: 정책 0건 → LANDEX 폴백 ─────────────────────────

def test_case2_zero_policy_falls_back_to_landex():
    """24h·72h 모두 0건 → LANDEX delta 폴백 (룰 기반 narrative, AI 호출 X)."""
    landex_payload = _landex_payload()
    fetch_landex_called = {"n": 0}

    def fake_collect(lookback_hours: int, now=None):
        return []  # 모든 윈도우 빈

    def fake_fetch(_now):
        fetch_landex_called["n"] += 1
        return landex_payload

    fail_if_called = {"n": 0}
    def must_not_be_called(_p):
        fail_if_called["n"] += 1
        return {"headline": "should not be called", "confidence": 1.0, "tokens_used": 0}

    out = build(
        now=NOW,
        _collect=fake_collect,
        _classify=lambda _p: {"category": "n/a", "stage": 0, "affected_regions": [],
                              "confidence": 0, "method": "no_match",
                              "keywords_matched": {}, "llm": None},
        _generate=must_not_be_called,
        _fetch_landex=fake_fetch,
        _success_rate_7d=lambda _now: None,
    )

    assert out is not None
    assert fetch_landex_called["n"] == 1
    assert fail_if_called["n"] == 0  # AI 호출 X — 룰 기반 narrative
    # trigger type
    assert out["operator_meta"]["data_source"] == "landex"
    # narrative — 룰 기반
    assert out["narrative"]["headline"] == landex_payload["title"]
    assert out["narrative"]["ai"]["model"] == LANDEX_RULE_BASED_MODEL
    assert out["narrative"]["ai"]["fallback_used"] is False
    assert out["narrative"]["ai"]["tokens"] == 0
    # policy section — LANDEX 매핑 (결정 3)
    assert out["policy"]["source"] == "VERITY ESTATE LANDEX"
    assert out["policy"]["category"] == "catalyst"  # delta1 +3.2 → 상승 → catalyst
    assert "성동구" in out["policy"]["affected_regions"]
    # key_metrics top3
    assert len(out["policy"]["key_metrics"]) == 3
    assert out["policy"]["key_metrics"][0]["label"] == "성동구"
    assert out["policy"]["key_metrics"][0]["value"] == 3.2


# ───────────────────────── 케이스 3: AI 실패 폴백 ─────────────────────────

def test_case3_ai_failure_keeps_dict_with_fallback_used_true():
    """AI 호출 실패 → headline=null + fallback_used=true. dict 유지 (T21 부분 실패)."""
    pol = _policy("p2", "공시가격 상승", pub_offset_h=1,
                  raw_text="공시가격 상승으로 종부세 부담")

    out = build(
        now=NOW,
        _collect=lambda lookback_hours, now=None: [pol],
        _classify=lambda _p: {"category": "tax", "stage": 2, "affected_regions": [],
                              "confidence": 0.7, "method": "keywords",
                              "keywords_matched": {}, "llm": None},
        _generate=lambda _p: None,  # AI 실패
        _fetch_landex=lambda _now: None,
        _success_rate_7d=lambda _now: 0.4,
    )

    # T21 — 부분 실패에서도 dict 반환 (JSON 갱신 됨)
    assert out is not None
    assert out["narrative"]["headline"] is None
    assert out["narrative"]["ai"]["fallback_used"] is True
    assert out["narrative"]["ai"]["model"] == NARRATIVE_AI_MODEL
    assert out["narrative"].get("fallback_reason") == "anthropic_call_failed"
    # policy 자체는 정상 채워짐
    assert out["policy"]["id"] == "p2"
    assert out["operator_meta"]["data_source"] == "policy_24h"


# ───────────────────────── 케이스 4: 수집 실패 + LANDEX 실패 → None ─────────────────────────

def test_case4_collect_fail_and_landex_fail_returns_none(caplog):
    """T21 — 전체 실패. None 반환 → JSON 갱신 X."""
    def raising_collect(lookback_hours, now=None):
        raise RuntimeError("supabase 5xx")

    with caplog.at_level("ERROR", logger="api.builders.estate_hero_briefing_builder"):
        out = build(
            now=NOW,
            _collect=raising_collect,
            _classify=lambda _p: {},
            _generate=lambda _p: None,
            _fetch_landex=lambda _now: None,  # LANDEX 도 실패
            _success_rate_7d=lambda _now: None,
        )

    assert out is None  # T21 — JSON 갱신 안 함
    # 명시 로그 (T9)
    assert any("all triggers failed" in r.message for r in caplog.records)


# ───────────────────────── 보강 1: 72h 폴백 ─────────────────────────

def test_72h_fallback_when_24h_empty():
    """24h 0건 + 72h 1건 → 2순위 트리거. data_source=policy_72h."""
    pol_72 = _policy("p_72", "정책", pub_offset_h=48,  # 48h 전 → 24h 윈도우 밖
                     raw_text="공시가격 종부세")

    out = build(
        now=NOW,
        _collect=lambda lookback_hours, now=None: [pol_72] if lookback_hours >= 48 else [],
        _classify=lambda _p: {"category": "tax", "stage": 2, "affected_regions": [],
                              "confidence": 0.7, "method": "keywords",
                              "keywords_matched": {}, "llm": None},
        _generate=lambda _p: {"headline": "h", "confidence": 0.7, "tokens_used": 50},
        _fetch_landex=lambda _now: None,
        _success_rate_7d=lambda _now: 0.5,
    )

    assert out is not None
    assert out["operator_meta"]["data_source"] == "policy_72h"
    # 24h 카운트 — 24h 호출이 빈 리스트 반환 (lookback < 48)
    assert out["operator_meta"]["policy_24h"] == 0


# ───────────────────────── 보강 2: stage DESC 정렬 ─────────────────────────

def test_top_trigger_is_highest_stage_then_recent():
    """24h 안에 stage 3 + stage 1 동시 → stage 3 이 트리거."""
    pol_low = _policy("p_low", "낮은 stage", pub_offset_h=1, raw_text="공시가격")
    pol_high = _policy("p_high", "높은 stage", pub_offset_h=2, raw_text="공시가격")

    captured = {}
    def fake_classify(p):
        captured.setdefault("calls", []).append(p["id"])
        if p["id"] == "p_high":
            return {"category": "anomaly", "stage": 3, "affected_regions": [],
                    "confidence": 0.8, "method": "keywords",
                    "keywords_matched": {}, "llm": None}
        return {"category": "tax", "stage": 1, "affected_regions": [],
                "confidence": 0.6, "method": "keywords",
                "keywords_matched": {}, "llm": None}

    out = build(
        now=NOW,
        _collect=lambda lookback_hours, now=None: [pol_low, pol_high],
        _classify=fake_classify,
        _generate=lambda _p: {"headline": "h", "confidence": 0.7, "tokens_used": 50},
        _fetch_landex=lambda _now: None,
        _success_rate_7d=lambda _now: None,
    )

    assert out is not None
    # stage 3 (p_high) 가 선택됐는지 — 비록 더 오래된 (2h vs 1h) published_at 이지만 stage 우선
    assert out["policy"]["id"] == "p_high"


# ───────────────────────── 보강 3: T20 — success_rate 실측 (jsonl 파싱) ─────────────────────────

def test_success_rate_7d_reads_jsonl_real(tmp_path, monkeypatch):
    """logs/anthropic_calls.jsonl 7일 윈도우 — 실 파일 파싱 (T20 임의 상수 X)."""
    log_path = tmp_path / "logs" / "anthropic_calls.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(builder, "ANTHROPIC_LOG_PATH", str(log_path))

    # 7일 안 3건 + 7일 밖 2건
    in_window = [
        {"timestamp": (NOW - timedelta(days=1)).isoformat(),
         "function_name": "generate_policy_briefing",
         "model": "x", "input_tokens": 1, "output_tokens": 1},
        {"timestamp": (NOW - timedelta(days=3)).isoformat(),
         "function_name": "generate_policy_briefing",
         "model": "x", "input_tokens": 1, "output_tokens": 1},
        {"timestamp": (NOW - timedelta(days=6)).isoformat(),
         "function_name": "generate_policy_briefing",
         "model": "x", "input_tokens": 1, "output_tokens": 1},
    ]
    out_of_window = [
        {"timestamp": (NOW - timedelta(days=10)).isoformat(),
         "function_name": "generate_policy_briefing",
         "model": "x", "input_tokens": 1, "output_tokens": 1},
        # 다른 function — classifier — 분모 분자 둘 다 제외
        {"timestamp": (NOW - timedelta(days=2)).isoformat(),
         "function_name": "policy_classifier.classify",
         "model": "x", "input_tokens": 1, "output_tokens": 1},
    ]
    with open(log_path, "w", encoding="utf-8") as f:
        for r in in_window + out_of_window:
            f.write(json.dumps(r) + "\n")

    rate = builder._compute_narrative_success_rate_7d(NOW)
    # 3 / 5 (expected_attempts) = 0.6
    assert rate == 0.6


def test_success_rate_7d_returns_none_when_log_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(builder, "ANTHROPIC_LOG_PATH", str(tmp_path / "nope.jsonl"))
    assert builder._compute_narrative_success_rate_7d(NOW) is None


# ───────────────────────── 보강 4: LANDEX stage 사다리 (결정 3) ─────────────────────────

@pytest.mark.parametrize("delta_abs,expected_stage", [
    (0.5, 0), (0.99, 0),
    (1.0, 1), (1.5, 1),
    (2.0, 2), (2.99, 2),
    (3.0, 3), (4.99, 3),
    (5.0, 4), (10.0, 4),
])
def test_landex_stage_ladder(delta_abs, expected_stage):
    assert builder._landex_stage(delta_abs) == expected_stage


def test_landex_fallback_title_format():
    """결정 3 — title 템플릿 정확성."""
    payload = _landex_payload()
    assert payload is not None
    assert "성동구 LANDEX +3.2% (WoW)" in payload["title"]
    assert "강남구·송파구 동반 상승" in payload["title"]
    assert payload["category"] == "catalyst"
    assert payload["stage"] == 3  # |3.2| → 3~5% 사다리


def test_landex_fallback_negative_delta_anomaly():
    """delta1 < 0 → category=anomaly, direction=하락."""
    p = build_landex_fallback(
        landex_rows=[
            {"gu": "강북구", "landex_wow_delta": -2.5},
            {"gu": "도봉구", "landex_wow_delta": -2.0},
            {"gu": "노원구", "landex_wow_delta": -1.5},
        ],
        generated_at=NOW.isoformat(),
    )
    assert p is not None
    assert p["category"] == "anomaly"
    assert "하락" in p["title"]
    assert p["stage"] == 2  # |2.5| → 2~3%


def test_landex_fallback_returns_none_on_empty():
    assert build_landex_fallback([], NOW.isoformat()) is None
    assert build_landex_fallback([{"gu": "a", "landex_wow_delta": 1.0}], NOW.isoformat()) is None


# ───────────────────────── 보강 5: T21 main() write 분기 ─────────────────────────

def test_main_skips_write_when_build_returns_none(tmp_path, monkeypatch):
    """T21 — build()=None → JSON 안 씀."""
    out_path = tmp_path / "data" / "estate_hero_briefing.json"
    monkeypatch.setattr(builder, "OUTPUT_PATH", str(out_path))
    monkeypatch.setattr(builder, "build", lambda: None)
    rc = main()
    assert rc == 1  # 실패 exit code
    assert not out_path.exists()


def test_main_writes_when_build_returns_dict(tmp_path, monkeypatch):
    """T21 — build()=dict → JSON 새로 씀 (atomic)."""
    out_path = tmp_path / "data" / "estate_hero_briefing.json"
    monkeypatch.setattr(builder, "OUTPUT_PATH", str(out_path))
    monkeypatch.setattr(builder, "build", lambda: {"schema_version": "1.0", "generated_at": "x"})
    rc = main()
    assert rc == 0
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == "1.0"
