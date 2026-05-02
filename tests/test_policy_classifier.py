"""
test_policy_classifier.py — Step 2 분류기 검증

T7  테스트 통과 위해 함수 로직 변경 X — fixture 변경은 OK.
T17 모델 = claude-haiku-4-5-20251001 검증 (mock).
T18 anthropic_calls.jsonl 기록 검증.
T19 1차 종결 (LLM skip) 검증.
"""
import json
import sys

import pytest

from api.analyzers import policy_classifier
from api.analyzers.policy_classifier import ANTHROPIC_MODEL, classify


def _p(title: str = "", raw_text: str = "") -> dict:
    return {
        "id": "test-id",
        "title": title,
        "source_url": "https://www.korea.kr/test",
        "source_name": "국토교통부",
        "published_at": "2026-05-01T00:00:00+00:00",
        "raw_text": raw_text,
    }


# ───────────────── 6 카테고리 1차 종결 (T19) ─────────────────

def test_classify_tax_short_circuit():
    """공시가격·종부세·재산세·양도세·보유세 → tax 1차 종결."""
    p = _p(
        title="공시가격 상승에 따른 종부세·재산세 부담 증가",
        raw_text="공시가격 상승으로 종부세 산정 기준이 올라가고 재산세도 함께 상승. 양도세 보유세도 영향.",
    )
    out = classify(p)
    assert out["category"] == "tax"
    assert out["method"] == "keywords"
    assert out["llm"] is None
    assert out["confidence"] >= 0.7
    assert out["stage"] >= 2


def test_classify_supply_public_housing():
    p = _p(
        title="도심 공공주택 3.4만호 공급 분양 청약",
        raw_text="공공주택 신축 분양 일정 청약 입주 안내",
    )
    out = classify(p)
    assert out["category"] == "supply"
    assert out["method"] == "keywords"


def test_classify_loan_dsr_ltv():
    p = _p(
        title="DSR 강화 LTV 규제 주담대 한도 조정",
        raw_text="DSR LTV 주택담보대출 디딤돌",
    )
    out = classify(p)
    assert out["category"] == "loan"
    assert out["method"] == "keywords"


def test_classify_redev():
    p = _p(
        title="재건축·재개발 정비사업 활성화",
        raw_text="재건축 재개발 정비사업 인가 리모델링",
    )
    out = classify(p)
    assert out["category"] == "redev"
    assert out["method"] == "keywords"


def test_classify_rental_jeonse_fraud():
    p = _p(
        title="전세사기 피해자 지원, 임대차 임차인 보호",
        raw_text="전세사기특별법 임대차 임차인 임대인 임대주택 보호",
    )
    out = classify(p)
    assert out["category"] == "rental"
    assert out["method"] == "keywords"


def test_classify_anomaly_irregular_trade():
    p = _p(
        title="서울 강남구 주택 이상거래 단속, 미분양 급등 우려",
        raw_text="이상거래 미분양 급등 주택 단속 강화",
    )
    out = classify(p)
    assert out["category"] == "anomaly"
    assert out["method"] == "keywords"
    # affected_regions 추출 검증
    assert "서울 강남구" in out["affected_regions"]


# ───────────────── 모호 케이스 → LLM 분기 ─────────────────

def test_ambiguous_triggers_llm():
    """매칭 분산 (90% 집중 미달) → LLM 호출."""
    p = _p(
        title="공시가격 LTV 토지거래허가",
        raw_text="공시가격 LTV 토지거래허가",
    )
    captured = {}

    def fake_llm(_policy):
        captured["called"] = True
        return {
            "category": "regulation",
            "stage": 3,
            "affected_regions": ["서울 강남구"],
            "confidence": 0.82,
            "_meta": {"model": ANTHROPIC_MODEL, "input_tokens": 100, "output_tokens": 50},
        }

    out = classify(p, _llm_fn=fake_llm)
    assert captured.get("called") is True
    assert out["category"] == "regulation"
    assert out["method"] == "llm"
    assert out["llm"]["model"] == ANTHROPIC_MODEL  # T17
    assert out["confidence"] == 0.82


def test_llm_failure_falls_back_to_keywords():
    """LLM None → 1차 폴백 (T1, T9) — fabricate X, silent X."""
    p = _p(
        title="공시가격 LTV 토지거래허가",
        raw_text="공시가격 LTV 토지거래허가",
    )
    out = classify(p, _llm_fn=lambda _x: None)
    assert out["method"] == "keywords_fallback"
    assert out["llm"] is None
    # 페널티 적용 — 일반 1차 종결보다 confidence 낮음
    assert out["confidence"] < 0.9


def test_no_keyword_match_returns_no_match():
    """prefilter 통과했지만 keyword_matches 0건 → no_match (보수적 분류)."""
    p = _p(title="위성 발사", raw_text="우주 항공 일정")
    out = classify(p)
    assert out["method"] == "no_match"
    assert out["category"] == "catalyst"
    assert out["confidence"] == 0.0


# ───────────────── T17·T18 통합 (실 호출 path mock) ─────────────────

def test_real_llm_path_uses_haiku_and_logs(tmp_path, monkeypatch):
    """T17 모델 검증 + T18 anthropic_calls.jsonl 기록 검증."""
    log_path = tmp_path / "logs" / "anthropic_calls.jsonl"
    monkeypatch.setattr(policy_classifier, "ANTHROPIC_LOG_PATH", str(log_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake-test")

    captured_kwargs = {}

    class FakeUsage:
        input_tokens = 123
        output_tokens = 45

    class FakeContentBlock:
        text = '{"category": "tax", "stage": 2, "affected_regions": [], "confidence": 0.71}'

    class FakeMsg:
        usage = FakeUsage()
        content = [FakeContentBlock()]

    class FakeMessages:
        def create(self, **kwargs):
            captured_kwargs.update(kwargs)
            return FakeMsg()

    class FakeClient:
        def __init__(self, **kwargs):
            self.messages = FakeMessages()

    fake_anthropic_module = type("anthropic_mock", (), {"Anthropic": FakeClient})
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic_module)

    p = _p(
        title="공시가격 LTV 토지거래허가",
        raw_text="공시가격 LTV 토지거래허가",
    )
    out = classify(p)

    # T17 — 호출 모델 검증
    assert captured_kwargs["model"] == "claude-haiku-4-5-20251001"
    assert captured_kwargs["max_tokens"] == 300
    assert out["method"] == "llm"
    assert out["category"] == "tax"
    assert out["llm"]["model"] == "claude-haiku-4-5-20251001"
    assert out["llm"]["input_tokens"] == 123
    assert out["llm"]["output_tokens"] == 45

    # T18 — 로그 파일 한 줄
    assert log_path.exists()
    lines = [l for l in log_path.read_text(encoding="utf-8").split("\n") if l.strip()]
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["model"] == "claude-haiku-4-5-20251001"
    assert rec["input_tokens"] == 123
    assert rec["output_tokens"] == 45
    assert rec["function_name"] == "policy_classifier.classify"
    assert rec["timestamp"]


def test_llm_missing_api_key_returns_none(monkeypatch, caplog):
    """ANTHROPIC_API_KEY 없음 → None + 명시 로그 (T9)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with caplog.at_level("ERROR", logger="api.analyzers.policy_classifier"):
        result = policy_classifier._classify_with_llm(_p(title="ambiguous"))
    assert result is None
    assert any("ANTHROPIC_API_KEY missing" in r.message for r in caplog.records)


def test_llm_invalid_category_falls_back_to_top_cat(monkeypatch):
    """LLM 이 invalid category 반환 → top_cat 으로 폴백 + warning."""
    p = _p(
        title="공시가격 LTV 토지거래허가",
        raw_text="공시가격 LTV 토지거래허가",
    )

    def bad_llm(_policy):
        return {
            "category": "FAKE_CATEGORY",  # invalid
            "stage": 2,
            "affected_regions": [],
            "confidence": 0.6,
            "_meta": {"model": ANTHROPIC_MODEL, "input_tokens": 1, "output_tokens": 1},
        }

    out = classify(p, _llm_fn=bad_llm)
    assert out["category"] in {"tax", "loan", "regulation"}  # top_cat 중 하나
    assert out["method"] == "llm"  # llm path 는 유지


def test_keyword_confidence_formula():
    """T4 — confidence 산식 도출 검증 (임의 상수 X)."""
    from api.analyzers.policy_classifier import _keyword_confidence
    # base = min(0.9, 0.5+0.1*3) = 0.8, factor = 0.4+0.6*1.0 = 1.0 → 0.800
    assert _keyword_confidence(3, 1.0) == 0.800
    # base = min(0.9, 0.5+0.1*4) = 0.9, factor = 0.4+0.6*0.9 = 0.94 → 0.846
    assert _keyword_confidence(4, 0.9) == 0.846
    # cap: top_count=10, concentration=1.0 → base 0.9 * 1.0 = 0.900
    assert _keyword_confidence(10, 1.0) == 0.900
