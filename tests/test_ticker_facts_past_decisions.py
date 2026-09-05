# -*- coding: utf-8 -*-
"""사실 조인에 과거 판단(실험 노트)을 붙이는 계약 (Phase 2).

🚨 저장만 하고 안 읽으면 여전히 단발성이다. 사실을 아무리 잘 모아도 "3개월 전에 뭐라고
   했고 결과가 어땠나" 를 모르면 정보량만 많은 1회용 판단이다.

   지키는 선:
     · 기록이 없으면 섹션을 만들지 않는다 — 빈 섹션은 "없는 것을 넣지 않는다" 규율 위반이고
       0 건을 있는 척하면 판단이 흔들린다
     · 조회 실패를 삼키지 않는다 — 조용히 빈 결과를 주면 "판단 이력 없음" 으로 오독된다
     · 순환 임포트가 생기면 안 된다 (decision_journal → operator_ask → ticker_facts)
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.intelligence import decision_journal as dj  # noqa: E402
from api.intelligence import ticker_facts as tf  # noqa: E402


def _facts(ticker="005930", close=71500):
    return {
        "ticker": ticker, "name": "삼성전자", "missing": [],
        "sections": [
            {"label": "종가 (T+1)", "source": "kr_close_latest.json",
             "as_of": "2026-08-08", "data": {"close": close}},
        ],
    }


@pytest.fixture
def journal(tmp_path):
    return str(tmp_path / "verdicts.jsonl")


def test_no_records_makes_no_section(journal):
    """빈 섹션을 만들지 않는다 — 0 건을 있는 척하면 안 된다."""
    sec, err = tf.past_decisions_section("005930", path=journal)
    assert sec is None
    assert err is None


def test_section_shape_and_fields(journal):
    dj.record(_facts(), "관심", "medium", ["fscore8"], "근거 문장",
              brain_verdict="B", path=journal)

    sec, err = tf.past_decisions_section("005930", path=journal)
    assert err is None
    assert sec["label"].startswith("과거 판단")
    assert sec["source"] == "private:decisions/verdicts.jsonl"
    assert sec["as_of"][:4] == "2026"

    row = sec["data"][0]
    assert row["verdict"] == "관심"
    assert row["confidence"] == "medium"
    assert row["ref_price"] == 71500
    assert row["basis_axes"] == ["fscore8"]
    assert row["brain_verdict"] == "B", "산식 baseline 이 같이 보여야 짝지은 비교가 된다"
    assert row["scored"] is None
    assert row["brief"] == "근거 문장"


def test_only_same_ticker(journal):
    dj.record(_facts(ticker="005930"), "관심", "medium", [], "삼전", path=journal)
    dj.record(_facts(ticker="000660"), "회피", "low", [], "하이닉스", path=journal)

    sec, _ = tf.past_decisions_section("005930", path=journal)
    assert len(sec["data"]) == 1
    assert sec["data"][0]["brief"] == "삼전"


def test_limit_applied(journal):
    for i in range(8):
        dj.record(_facts(), "보류", "low", [], f"{i}번", path=journal)

    sec, _ = tf.past_decisions_section("005930", limit=3, path=journal)
    assert len(sec["data"]) == 3


def test_read_failure_is_reported_not_swallowed(monkeypatch, journal):
    """조용히 빈 결과를 주면 '판단 이력 없음' 으로 오독된다."""
    def _boom(*a, **k):
        raise OSError("디스크 오류")

    monkeypatch.setattr(dj, "read_recent", _boom)
    sec, err = tf.past_decisions_section("005930", path=journal)
    assert sec is None
    assert err and "과거 판단 조회 실패" in err
    assert "OSError" in err


def test_module_absence_is_not_a_failure(monkeypatch, journal):
    """🚨 배포본(vercel-api)에는 decision_journal 이 복제되지 않는다.

    sync_operator_ask.sh 는 ticker_facts.py·operator_ask.py·us_filing_probe.py 만 복제한다. 실험 노트는
    터미널 전용·비공개라 배포 대상이 아니다. 모듈 부재를 "실패" 로 보고하면 오퍼레이터
    사이트에서 매 조회마다 없는 결함이 뜬다.
    """
    import builtins

    real_import = builtins.__import__

    def _no_journal(name, *a, **k):
        if name == "api.intelligence" and a and "decision_journal" in (a[2] or ()):
            raise ImportError("No module named 'api.intelligence.decision_journal'")
        if name.endswith("decision_journal"):
            raise ImportError("No module named 'decision_journal'")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _no_journal)
    sec, err = tf.past_decisions_section("005930", path=journal)
    assert sec is None
    assert err is None, "모듈 부재는 결함으로 보고하지 않는다"


def test_script_mode_import_fallback(monkeypatch, journal):
    """🚨 2026-08-12 실사고 — 주 경로에서 섹션이 조용히 사라졌다.

    스킬의 기본 명령이 `python3 api/intelligence/operator_ask.py` = 스크립트 모드다.
    이때 sys.path[0] 이 api/intelligence 라 repo 루트가 없고, 절대 임포트
    `from api.intelligence import decision_journal` 이 ImportError 를 낸다.
    그걸 "배포본엔 없음" 으로 삼켜서 collect 32섹션 / CLI 출력 31섹션이 됐다.

    패키지 임포트가 막혀도 top-level `decision_journal` 로 살아나야 한다.
    """
    import builtins

    real = builtins.__import__

    def _no_pkg(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "api.intelligence" and fromlist and "decision_journal" in fromlist:
            raise ImportError("No module named 'api'")
        return real(name, globals, locals, fromlist, level)

    dj.record(_facts(), "관심", "medium", ["fscore8"], "스크립트 모드", path=journal)
    monkeypatch.setattr(builtins, "__import__", _no_pkg)
    monkeypatch.setitem(sys.modules, "decision_journal", dj)  # 스크립트 모드의 top-level

    sec, err = tf.past_decisions_section("005930", path=journal)
    assert err is None
    assert sec is not None, "스크립트 모드에서 섹션이 사라지면 안 된다"
    assert sec["data"][0]["verdict"] == "관심"


def test_render_text_handles_section(journal):
    """조인 결과가 실제로 렌더되는지 — 섹션만 만들고 안 보이면 의미가 없다."""
    dj.record(_facts(), "관심", "medium", ["fscore8"], "F-Score 8점", path=journal)
    sec, _ = tf.past_decisions_section("005930", path=journal)

    facts = _facts()
    facts["sections"].append(sec)
    facts["_meta"] = {"collected_at": "2026-08-09T17:00:00+09:00", "note": "테스트"}

    text = tf.render_text(facts)
    assert "과거 판단" in text
    assert "관심" in text


def test_no_circular_import_either_order():
    """decision_journal → operator_ask → ticker_facts 고리가 닫히면 안 된다."""
    import importlib

    for first, second in (
        ("api.intelligence.ticker_facts", "api.intelligence.decision_journal"),
        ("api.intelligence.decision_journal", "api.intelligence.ticker_facts"),
    ):
        for name in (first, second):
            sys.modules.pop(name, None)
        importlib.import_module(first)
        importlib.import_module(second)


def test_fingerprint_still_works_after_lazy_import():
    """지연 임포트로 바꾼 뒤에도 지문이 나와야 한다."""
    fp = dj.facts_fingerprint(_facts())
    assert isinstance(fp, str) and len(fp) == 20
