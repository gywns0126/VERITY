# -*- coding: utf-8 -*-
"""미장 forensics — 위임장(DEF 14A 계열) 집계.

소비처는 공개 화면이 아니라 **오퍼레이터 판단 레이어**다. ticker_facts 가
us_disclosure_forensics.json 을 이미 소스로 등록하고 있어 별도 배선 없이
종목 질의에 조인된다.

🚨 폼 코드까지만 사실이다. 역분할·수권주식수 증가 같은 안건 내용은 문서 파싱이
   필요해 미구현이므로, proxy_annual 을 "희석 예고" 로 읽으면 안 된다.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.builders import us_disclosure_forensics_builder as fb  # noqa: E402


@pytest.mark.parametrize(
    "form,expected",
    [
        # 경영권 분쟁 — 판단 가치가 가장 높은 축
        ("DEFC14A", "proxy_contest"),
        ("PREC14A", "proxy_contest"),
        # 합병·중대거래
        ("DEFM14A", "proxy_merger"),
        ("PREM14A", "proxy_merger"),
        # 정기 주총 (공백 표기 혼재 → 정규화 확인)
        ("DEF 14A", "proxy_annual"),
        ("DEF14A", "proxy_annual"),
        ("PRE 14A", "proxy_annual"),
        # 추가 권유자료 = 같은 건에 여러 번 붙어 카운트를 부풀린다 → 제외
        ("DEFA14A", ""),
        # 해당 없음
        ("8-K", ""),
        ("S-1", ""),
        ("424B5", ""),
        ("SC 13D", ""),
        ("", ""),
    ],
)
def test_proxy_category(form, expected):
    assert fb._proxy_category(form) == expected


def test_proxy_and_offering_do_not_overlap():
    """한 폼이 두 축에 동시에 잡히면 카운트가 중복된다."""
    for form in ("DEF 14A", "DEFC14A", "DEFM14A", "PRE 14A"):
        assert fb._offering_category(form) == ""
    for form in ("S-1", "S-3/A", "424B4", "F-1"):
        assert fb._proxy_category(form) == ""


def test_fetch_filings_returns_three_buckets(monkeypatch):
    """8-K · 등록공모 · 위임장을 한 응답에서 나눠 뽑는다 — 추가 호출 0."""
    payload = {
        "filings": {
            "recent": {
                "form": ["8-K", "424B5", "DEFC14A", "DEF 14A", "DEFA14A", "10-K"],
                "filingDate": ["2026-08-01", "2026-07-20", "2026-07-01",
                               "2026-05-10", "2026-05-11", "2026-03-01"],
                "items": ["3.02", "", "", "", "", ""],
            }
        }
    }

    class _Resp:
        def read(self):
            return json.dumps(payload).encode()

    monkeypatch.setattr(fb.urllib.request, "urlopen", lambda *a, **k: _Resp())

    eightk, offerings, proxies = fb._fetch_filings("0000000320", cutoff="2026-01-01")

    assert eightk == [("2026-08-01", ["3.02"])]
    assert offerings == [("2026-07-20", "offering_priced", "424B5")]
    # DEFA14A 는 제외, 10-K 는 해당 없음
    assert sorted(proxies) == [
        ("2026-05-10", "proxy_annual", "DEF 14A"),
        ("2026-07-01", "proxy_contest", "DEFC14A"),
    ]


def test_cutoff_applies_to_proxy(monkeypatch):
    payload = {
        "filings": {
            "recent": {
                "form": ["DEFC14A", "DEF 14A"],
                "filingDate": ["2019-01-01", "2026-06-01"],
                "items": ["", ""],
            }
        }
    }

    class _Resp:
        def read(self):
            return json.dumps(payload).encode()

    monkeypatch.setattr(fb.urllib.request, "urlopen", lambda *a, **k: _Resp())

    _e, _o, proxies = fb._fetch_filings("0000000320", cutoff="2026-01-01")
    assert proxies == [("2026-06-01", "proxy_annual", "DEF 14A")]
