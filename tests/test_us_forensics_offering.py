# -*- coding: utf-8 -*-
"""미장 forensics — 등록 공모(S-1/S-3/F-1/424B) 집계.

🚨 옛 빌더가 docstring 에 스스로 적어둔 한계를 메운 것이다:
   "registered offering(424B/S-1)은 8-K 아님 → dilution 은 Item 3.02(unregistered) 만 포착"

   같은 submissions 응답 안에 이미 들어 있어 추가 HTTP 호출은 0이다.
   dilution(8-K 3.02) 과 **합치지 않는다** — 비등록 매출과 등록 공모는 성격이 달라
   합치면 기존 dilution 카운트의 의미가 바뀐다.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.builders import us_disclosure_forensics_builder as fb  # noqa: E402


@pytest.mark.parametrize(
    "form,expected",
    [
        ("424B4", "offering_priced"),
        ("424B5", "offering_priced"),
        ("424B3", "offering_priced"),
        ("S-1", "offering_registered"),
        ("S-1/A", "offering_registered"),
        ("S-3", "offering_registered"),
        ("S-3/A", "offering_registered"),
        ("F-1", "offering_registered"),
        ("F-3/A", "offering_registered"),
        # 해당 없음
        ("8-K", ""),
        ("10-K", ""),
        ("10-Q", ""),
        ("SC 13D", ""),
        ("4", ""),
        ("S-8", ""),        # 임직원 보상 등록 — 공모 아님
        ("", ""),
    ],
)
def test_offering_category(form, expected):
    assert fb._offering_category(form) == expected


def test_fetch_filings_splits_8k_and_offering(monkeypatch):
    """한 응답에서 8-K 와 등록공모를 나눠 뽑는다 — 추가 호출 0."""
    payload = {
        "filings": {
            "recent": {
                "form": ["8-K", "424B5", "S-1", "10-Q", "S-1/A"],
                "filingDate": ["2026-08-01", "2026-07-20", "2026-06-01",
                               "2026-05-01", "2020-01-01"],
                "items": ["3.02,1.01", "", "", "", ""],
            }
        }
    }

    class _Resp:
        def read(self):
            import json as _j
            return _j.dumps(payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(fb.urllib.request, "urlopen", lambda *a, **k: _Resp())

    eightk, offerings = fb._fetch_filings("0000000320", cutoff="2026-01-01")

    assert eightk == [("2026-08-01", ["3.02", "1.01"])]
    # 2020 년 S-1/A 는 cutoff 밖 → 제외
    assert sorted(offerings) == [
        ("2026-06-01", "offering_registered", "S-1"),
        ("2026-07-20", "offering_priced", "424B5"),
    ]


def test_dilution_and_offering_stay_separate(monkeypatch):
    """8-K 3.02(비등록)와 등록공모가 같은 키로 합쳐지면 안 된다."""
    assert fb.ITEM_CATEGORY.get("3.02") == "dilution"
    assert fb._offering_category("424B5") != "dilution"
    assert fb._offering_category("S-1") != "dilution"
