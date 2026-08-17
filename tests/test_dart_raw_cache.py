# -*- coding: utf-8 -*-
"""DART 사업보고서 원문 슬라이스 디스크 캐시 (2026-08-17 신설).

## 왜

`fetch_business_facilities_raw` 는 사업보고서 ZIP 다운로드 + 정규식 슬라이스라 무겁다 —
실측 코너 3종목이 13분 35초에도 미완(종목당 4분대). 그런데 이 함수를 소비하는 LLM 축이
**4개**(kam · litigation · related_party · business)이고, 캐시가 없어 **각각 따로 받았다**.
인수인계 문서는 "추가 DART 호출 0" 이라 적어뒀는데 근거가 없었다 — 코너 레코드의
`business_facilities_raw` 보유는 0이었다.

연 1회 갱신되는 문서라 `(corp_code, bsns_year)` 키가 자연히 안정적이다.

## 규약

- 성공분만 저장 — `char_count < 500`(downstream MIN 과 동일)은 저장하지 않는다.
  🚨 실패를 캐시하면 다음 run 이 영구히 재시도하지 않는다(공시 정정 반영 불가).
- 손상 파일은 fail-open(미스 처리) — 조용히 옛 값을 쓰거나 터지지 않는다.
- `use_cache=False` 로 강제 우회 가능.
"""
from __future__ import annotations

import gzip
import json
import os

import pytest

from api.collectors import DartScout as D


@pytest.fixture(autouse=True)
def _tmp_cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "_RAW_CACHE_DIR", str(tmp_path / "raw"))
    yield


def test_roundtrip_preserves_document():
    doc = {"rcept_no": "20260101000001", "report_nm": "사업보고서",
           "raw_text": "가" * 1200, "char_count": 1200, "source_report_ty": "A001"}
    D._raw_cache_put("00126380", "2025", doc)
    got = D._raw_cache_get("00126380", "2025")
    assert got is not None
    assert got["char_count"] == 1200 and got["raw_text"] == doc["raw_text"]
    assert got["rcept_no"] == doc["rcept_no"]


def test_short_document_is_not_cached():
    """🚨 500 미달 미저장 — 다음 run 이 더 긴 본문을 잡을 여지를 남긴다."""
    D._raw_cache_put("00000001", "2025", {"raw_text": "짧음", "char_count": 4})
    assert D._raw_cache_get("00000001", "2025") is None


def test_missing_raw_text_is_not_cached():
    D._raw_cache_put("00000002", "2025", {"error": "no_report_found"})
    assert D._raw_cache_get("00000002", "2025") is None


def test_corrupt_file_is_a_miss_not_a_crash():
    os.makedirs(D._RAW_CACHE_DIR, exist_ok=True)
    with open(D._raw_cache_path("00000003", "2025"), "wb") as f:
        f.write(b"this is not gzip")
    assert D._raw_cache_get("00000003", "2025") is None


def test_year_is_part_of_the_key():
    """연도가 키에 들어가야 회계연도 갱신분을 옛 값으로 덮어 읽지 않는다."""
    doc = {"raw_text": "가" * 900, "char_count": 900}
    D._raw_cache_put("00126380", "2024", doc)
    assert D._raw_cache_get("00126380", "2024") is not None
    assert D._raw_cache_get("00126380", "2025") is None


def test_cache_hit_marks_itself():
    """소비처가 캐시 히트를 구분할 수 있어야 한다 (신선도 판단·계측용)."""
    doc = {"raw_text": "가" * 900, "char_count": 900}
    D._raw_cache_put("00126380", "2025", doc)
    hit = D._raw_cache_get("00126380", "2025")
    assert hit is not None
    # `_from_cache` 는 fetch 함수가 붙인다 — 캐시 자체는 원문을 그대로 보존한다
    assert "_from_cache" not in hit


def test_fetch_returns_cached_without_network(monkeypatch):
    """🚨 핵심 회귀: 캐시가 있으면 네트워크 경로에 들어가지 않는다."""
    doc = {"raw_text": "가" * 1000, "char_count": 1000, "report_nm": "사업보고서"}
    D._raw_cache_put("00126380", "2025", doc)

    def _boom(*a, **k):                     # 호출되면 캐시가 안 먹은 것
        raise AssertionError("캐시 히트인데 _list_reports 가 호출됐다")
    monkeypatch.setattr(D, "_list_reports", _boom)
    monkeypatch.setattr(D, "DART_API_KEY", "fake")

    out = D.fetch_business_facilities_raw("00126380", "2025")
    assert out["char_count"] == 1000 and out.get("_from_cache") is True


def test_use_cache_false_bypasses(monkeypatch):
    doc = {"raw_text": "가" * 1000, "char_count": 1000}
    D._raw_cache_put("00126380", "2025", doc)
    monkeypatch.setattr(D, "DART_API_KEY", "fake")
    monkeypatch.setattr(D, "_list_reports", lambda *a, **k: [])
    out = D.fetch_business_facilities_raw("00126380", "2025", use_cache=False)
    assert out.get("_from_cache") is not True
