"""recommendations.json 의 rec_price / current_price 필드 주입 로직 검증.

api/main.py 에서 직접 테스트하기 어려워 (main() 함수가 매우 크고 IO 가 많음),
주입 로직과 동일한 최소 헬퍼를 재현해 핵심 동작만 확인한다.
"""
import json
from pathlib import Path

import pytest


def _apply_snapshot(analyzed, prev_rec_price_map):
    """api/main.py:3219 전후 블록의 최소 재현 — 단위 테스트용."""
    for rec in analyzed:
        price = rec.get("price")
        if price is None:
            continue
        rec.setdefault("current_price", price)
        rec.setdefault("rec_price", prev_rec_price_map.get(rec.get("ticker"), price))
    return analyzed


def test_new_ticker_snapshots_current_price_as_rec_price():
    analyzed = [{"ticker": "005930", "price": 93200.0}]
    out = _apply_snapshot(analyzed, {})
    assert out[0]["current_price"] == 93200.0
    assert out[0]["rec_price"] == 93200.0  # 첫 추천 → rec_price = 당시 price


def test_existing_ticker_preserves_prior_rec_price():
    analyzed = [{"ticker": "005930", "price": 95000.0}]  # 현재가 변함
    prev = {"005930": 93200.0}  # 이전 저장 rec_price
    out = _apply_snapshot(analyzed, prev)
    assert out[0]["current_price"] == 95000.0
    assert out[0]["rec_price"] == 93200.0  # 유지됨 — 추천 시점 고정


def test_skips_when_price_missing():
    analyzed = [{"ticker": "NOPRICE"}]
    out = _apply_snapshot(analyzed, {})
    assert "current_price" not in out[0]
    assert "rec_price" not in out[0]


def test_multiple_tickers_mixed():
    analyzed = [
        {"ticker": "005930", "price": 95000.0},  # 기존
        {"ticker": "000660", "price": 120000.0},  # 신규
        {"ticker": "NOPRICE"},  # price 없음
    ]
    prev = {"005930": 93200.0}
    out = _apply_snapshot(analyzed, prev)
    assert out[0]["rec_price"] == 93200.0
    assert out[1]["rec_price"] == 120000.0
    assert "rec_price" not in out[2]


def test_does_not_overwrite_existing_fields():
    """이미 current_price/rec_price 가 세팅돼 있으면 setdefault 로 보존."""
    analyzed = [{"ticker": "005930", "price": 95000.0,
                 "current_price": 95500.0, "rec_price": 90000.0}]
    out = _apply_snapshot(analyzed, {"005930": 93200.0})  # prev 있어도 안 덮음
    assert out[0]["current_price"] == 95500.0
    assert out[0]["rec_price"] == 90000.0


def test_live_recommendations_schema_will_include_fields_after_next_full():
    """현재 repo 의 recommendations.json 에 아직 rec_price/current_price 없음 — 다음 full cron 이후 생김.

    스키마 확장을 문서화하는 회귀 방지 테스트. 지금은 skip 조건 + xfail 로 후속 검증."""
    path = Path(__file__).resolve().parent.parent / "data" / "recommendations.json"
    if not path.exists():
        pytest.skip("recommendations.json 없음")
    recs = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(recs, list) or not recs:
        pytest.skip("recommendations 비어 있음")
    # 다음 Full cron 실행 후부터 True 가 되어야 하는 invariant.
    # 아직 적용 안 된 상태라 xfail 로 표시 — Full 실행 후 자연스럽게 PASS 전환.
    sample = recs[0]
    if "rec_price" not in sample or "current_price" not in sample:
        pytest.xfail("다음 Full cron 실행 이후부터 주입됨 (현재 스키마 확장 대기)")
    assert "rec_price" in sample
    assert "current_price" in sample
