"""
dart_litigation 분석기 로직 테스트 (캐시/skip/attach). Gemini 호출은 mock.

2026-06-06 DART 2차 원문 심화 — 소송/우발부채/제재 관측 신호. dart_related_party 동형.
"""
import json

import pytest

import api.analyzers.dart_litigation as L


_FAKE = {
    "litigation_risk_score": 62,
    "severity": "medium",
    "pending_litigation": [{"counterparty": "A사", "claim_amount": "120억원", "issue": "특허 침해"}],
    "contingent_liabilities": ["계열사 지급보증 300억"],
    "material_sanctions": [],
    "summary": "특허 소송 1건 계류 — 청구 120억",
}


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "CACHE_PATH", str(tmp_path / "cache.json"))


def _stock(text_len=400, **extra):
    base = {
        "name": "테스트종목", "bsns_year": "2025", "corp_code": "00126380",
        "business_facilities_raw": {"litigation_text": "소" * text_len},
    }
    base.update(extra)
    return {"005930": base}


def test_attaches_when_text_present(monkeypatch):
    monkeypatch.setattr(L, "_analyze", lambda raw, name: dict(_FAKE))
    out = L.analyze_all_litigation(_stock(), auto_fetch_missing=False)
    r = out["005930"]
    assert r["litigation_risk_score"] == 62
    assert r["severity"] == "medium"
    assert r["ticker"] == "005930" and r["bsns_year"] == "2025"
    assert "analyzed_at" in r


def test_skips_short_text_no_fetch(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(L, "_analyze", lambda raw, name: called.__setitem__("n", called["n"] + 1))
    out = L.analyze_all_litigation(_stock(text_len=10), auto_fetch_missing=False)
    assert out["005930"]["_skip_reason"] == "no_litigation_text"
    assert called["n"] == 0  # 짧으면 AI 미호출


def test_ai_fail_marks_skip(monkeypatch):
    monkeypatch.setattr(L, "_analyze", lambda raw, name: None)
    out = L.analyze_all_litigation(_stock(), auto_fetch_missing=False)
    assert out["005930"]["_skip_reason"] == "ai_fail"


def test_cache_hit_skips_reanalyze(monkeypatch):
    # 1차 분석 → 캐시 저장
    monkeypatch.setattr(L, "_analyze", lambda raw, name: dict(_FAKE))
    L.analyze_all_litigation(_stock(), auto_fetch_missing=False)
    # 2차 — _analyze 가 호출되면 실패 처리해서 캐시 경유 확인
    monkeypatch.setattr(L, "_analyze", lambda raw, name: pytest.fail("캐시 미적중 — 재분석됨"))
    out = L.analyze_all_litigation(_stock(), auto_fetch_missing=False)
    assert out["005930"]["litigation_risk_score"] == 62


def test_cache_persisted_to_disk(monkeypatch):
    monkeypatch.setattr(L, "_analyze", lambda raw, name: dict(_FAKE))
    L.analyze_all_litigation(_stock(), auto_fetch_missing=False)
    with open(L.CACHE_PATH, encoding="utf-8") as f:
        cache = json.load(f)
    assert cache["by_ticker"]["005930"]["2025"]["litigation_risk_score"] == 62
