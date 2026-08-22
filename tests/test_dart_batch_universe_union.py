# -*- coding: utf-8 -*-
"""DART fundamentals 수집 대상 = 발행 유니버스를 반드시 포함한다.

## 왜 (2026-08-22 실측)

`financials` 채움율이 80.2% 였고 미보유가 355종목이었다. 원인은 데이터 부재가 아니라
**유니버스 어긋남**이었다:

    수집 대상 `build_extended_universe("KR", …)`   1,611
    사이트 노출 `stock_report_public.json`          1,790
    → 179종목이 **시도조차 되지 않음**

증거 2개:
  · 미보유 '일반' 339종목 중 **332(98%)가 `fin_series`(재무 시계열)를 이미 보유** —
    우리는 그 회사 재무를 알고 있는데 `financials` 만 비어 있었다
  · 미수집 10종목을 DART 에 직접 조회 → **10/10 존재**(계정 98~195행, 매출 계정 포함)

같은 계열 재발 = 2026-08-09 중소형주 채움(ALL_STOCKS 45 하드코딩 · pool 20).
**수집기 유니버스가 발행 유니버스보다 좁은 구조**가 반복된다 → 기계로 막는다.

🚨 이 테스트는 "채움율이 높다" 를 재지 않는다. 채움율은 DART 사정으로도 변한다.
   재는 것은 **"물어보기는 했는가"** 다 — 시도조차 안 하면 영원히 안 채워진다.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.builders import dart_batch_builder as db  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUB = os.path.join(_ROOT, "data", "stock_report_public.json")


def _published():
    with open(PUB, encoding="utf-8") as f:
        return {str(s.get("ticker") or "") for s in (json.load(f).get("stocks") or [])
                if str(s.get("ticker") or "").isdigit()}


@pytest.fixture
def stub_base(monkeypatch):
    """기저 유니버스를 작게 고정 — 네트워크 없이 union 동작만 본다."""
    def fake(market, target_size=None, apply_hard_floor=None):
        return [{"ticker": "005930"}, {"ticker": "000660"}]
    import api.collectors.universe_builder as ub
    monkeypatch.setattr(ub, "build_extended_universe", fake)
    return fake


def test_covers_published_universe(stub_base):
    """🚨 핵심 계약 — 발행 유니버스 전 종목이 수집 대상에 들어간다."""
    got = set(db._build_kr_universe_tickers())
    pub = _published()
    missing = sorted(pub - got)
    assert not missing, (
        f"발행 유니버스 {len(pub)}종목 중 {len(missing)}종목이 DART 수집 대상에서 빠졌다 "
        f"— 이 종목들은 financials 가 영원히 안 채워진다.\n  누락 표본: {missing[:10]}")


def test_base_universe_failure_still_covers_published(monkeypatch):
    """기저 유니버스가 통째로 죽어도 발행 유니버스가 바닥을 받친다.

    KRX OpenAPI 는 transient 실패가 잦다(그래서 원 코드에 3회 재시도가 있다).
    3회 다 실패해도 수집이 0 이 되면 안 된다 — 그날 전 종목 결손이다.
    """
    import api.collectors.universe_builder as ub
    monkeypatch.setattr(ub, "build_extended_universe",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("KRX down")))
    monkeypatch.setattr(db.time, "sleep", lambda *_: None)   # 재시도 대기 skip
    got = set(db._build_kr_universe_tickers())
    assert got >= _published(), "기저 실패 시 발행 유니버스조차 못 담았다"


def test_tickers_are_six_digit_and_unique(stub_base):
    got = db._build_kr_universe_tickers()
    assert len(got) == len(set(got)), "중복 티커 — DART 호출을 두 번 한다"
    bad = [t for t in got if not (t.isdigit() and len(t) == 6)]
    assert not bad, f"6자리 숫자 아닌 티커: {bad[:5]}"
