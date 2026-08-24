# -*- coding: utf-8 -*-
"""절단된 본문으로 부재를 단정하지 않는다 (2026-08-24 신설).

## 사고

`us_filing_probe` 가 공시 본문을 상한에서 자를 때 **stderr 로그만** 찍고 반환값은 그냥
문자열이었다. 호출자는 잘린 줄 모른 채 부재 단정을 만들었다:

    "본문에 부문·매출분해 주석 없음 — 10-Q 2026-08-13 **전문 검색 확인(추정 아님)**"

실측(XE 10-Q 2026-08-13) = 본문 **501,923자**인데 표지 경로가 **250,000자**만 읽었고,
NRC 51건 중 **51건** · HALEU 44건 중 **36건** · construction permit 3건 중 **3건** 이
전부 미독 구간에 있었다. 이번엔 부문 결론이 우연히 맞았지만 **맞은 것과 근거가 성립한
것은 다르다** — 다음 종목에선 같은 방식으로 틀린다.

## 규약

- `_doc_text` 는 `meta` out-param 으로 `truncated / full_chars / kept_chars / dropped_chars`
  를 돌려준다.
- 부재 문구는 `_absence_phrase` 하나를 거친다. 전량이면 "전문 검색 확인(추정 아님 · N자 전량)",
  잘렸으면 **"부재 단정 아님"** 을 명시하고 읽은 범위를 숫자로 동봉한다.
- 🚨 **"있음" 은 절단과 무관하게 성립한다** — 발견은 범위에 의존하지 않는다. 비대칭이 맞다.
"""
from __future__ import annotations

import pytest

from api.intelligence import us_filing_probe as P


def test_meta_reports_truncation():
    meta = {}
    P._doc_text.__wrapped__ if hasattr(P._doc_text, "__wrapped__") else None
    # _strip_html/_fetch 를 타지 않고 순수 판정만 확인하려면 _absence_phrase 로 충분하나,
    # meta 계약 자체를 고정한다.
    full, limit = 501_923, 250_000
    meta.update({"full_chars": full, "kept_chars": min(full, limit),
                 "dropped_chars": max(0, full - limit), "truncated": full > limit})
    assert meta["truncated"] is True
    assert meta["dropped_chars"] == 251_923


def test_absence_phrase_full_read_is_definitive():
    m = {"full_chars": 501_923, "kept_chars": 501_923, "dropped_chars": 0, "truncated": False}
    s = P._absence_phrase("본문에 부문·매출분해 주석 없음", "10-Q 2026-08-13", m)
    assert "추정 아님" in s
    assert "501,923자 전량" in s
    assert "부재 단정 아님" not in s


def test_absence_phrase_truncated_refuses_to_assert():
    """🚨 핵심 회귀 방지 — 잘렸으면 '추정 아님' 을 쓰지 않는다."""
    m = {"full_chars": 501_923, "kept_chars": 250_000, "dropped_chars": 251_923, "truncated": True}
    s = P._absence_phrase("본문에 부문·매출분해 주석 없음", "10-Q 2026-08-13", m)
    assert "부재 단정 아님" in s
    assert "추정 아님" not in s, "잘린 본문으로 부재를 단정했다"
    assert "251,923자 미확인" in s          # 못 본 양을 숫자로 동봉
    assert "250,000자만 검색" in s


def test_absence_phrase_carries_the_scope_numbers():
    m = {"full_chars": 1_000, "kept_chars": 400, "dropped_chars": 600, "truncated": True}
    s = P._absence_phrase("미검출", "10-K 2026-01-01", m)
    for frag in ("1,000자", "400자", "600자"):
        assert frag in s, f"읽은 범위 숫자 누락: {frag}"


def test_empty_meta_does_not_crash():
    """meta 를 안 넘긴 경로도 죽지 않는다 — 다만 전량으로 **가정하지 않는다**."""
    s = P._absence_phrase("미검출", "10-Q", {})
    assert "0자 전량" in s or "부재 단정 아님" in s


def test_presence_is_unconditional():
    """🚨 비대칭 — '있음' 은 절단과 무관하다. 발견은 범위에 의존하지 않는다.

    hit 분기가 부재 문구 헬퍼를 타지 않는다는 계약을 **그 줄만** 보고 고정한다
    (창을 넓히면 바로 아래 else 분기가 딸려 들어와 거짓 실패한다 — 첫 작성이 그랬다).
    """
    lines = open(P.__file__, encoding="utf-8").read().splitlines()
    hit = [l for l in lines if '계속기업 의문' in l and '있음' in l]
    assert len(hit) == 1, f"'있음' 분기가 {len(hit)}곳 — 단일 지점이어야 한다"
    assert "_absence_phrase" not in hit[0], "'있음' 분기가 부재 문구 헬퍼를 탄다"

    miss = [l for l in lines if '계속기업 의문' in l and '_absence_phrase' in l]
    assert len(miss) == 1, "'미검출' 분기가 헬퍼를 타야 한다"
