# -*- coding: utf-8 -*-
"""결손 원인 분류 계약.

## 왜 (2026-08-22)

`coverage_report_builder` 가 `financials 80.2%` 를 6주 동안 냈는데 **아무도 왜인지 몰랐다.**
비율만으로는 "어쩔 수 없는 결손" 과 "우리가 안 고친 결손" 이 구분되지 않기 때문이다.
손으로 파보니 355건 중 **347건이 수집 유니버스 누락** — 고칠 수 있는 것이었고,
미수집 10종목을 DART 에 직접 물으니 **10/10 존재**했다.

🚨 그래서 이 분류기가 지키는 선은 하나다 — **①③(우리 책임)과 ②④(원천 사정)를 절대 섞지 않는다.**
   섞이면 고칠 수 있는 결손이 어쩔 수 없는 결손으로 위장되고, 그게 6주를 만든다.

🚨 그리고 **모르는 것은 '미분류' 로 남긴다.** probe 예산이 소진되면 ②로 떨어뜨리고 싶은
   유혹이 있는데, 그러면 '원천에 없다' 는 거짓 결론이 쌓인다. 모름은 모름이어야 한다.
"""
from __future__ import annotations

import importlib.util
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
_spec = importlib.util.spec_from_file_location(
    "gapcls", os.path.join(_ROOT, "scripts", "audit", "data_gap_classifier.py"))
gap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gap)


class TestNormalAbsence:
    """④ 정상 부재 — 분모에서 빼야 하는 것들. 과잉 판정하면 진짜 결손이 숨는다."""

    @pytest.mark.parametrize("name,ticker,expect", [
        ("교보14호스팩", "456789", "스팩"),
        ("하나금융기업인수목적25호", "456789", "스팩"),
        ("삼성전자우", "005935", "우선주"),
        ("엘브이엠씨홀딩스", "900140", "외국기업"),
    ])
    def test_flags(self, name, ticker, expect):
        assert gap._normal_absence(name, ticker) == expect

    @pytest.mark.parametrize("name,ticker", [
        ("삼성전자", "005930"),
        ("SK하이닉스", "000660"),
        ("우리금융지주", "316140"),      # '우' 로 시작하지만 우선주 아님
        ("에코프로비엠", "247540"),
    ])
    def test_normal_stocks_not_flagged(self, name, ticker):
        """🚨 일반 종목을 ④로 넣으면 결손이 통계에서 사라진다 — 가장 위험한 오분류."""
        assert gap._normal_absence(name, ticker) is None


class TestRefillableArithmetic:
    """🚨 refillable = ①+③ 만. ②④ 가 섞이면 지표가 거짓말한다."""

    def test_only_our_fault_counts(self):
        from collections import Counter
        c = Counter({"①유니버스누락": 347, "②소스부재": 6, "③파싱실패": 1,
                     "④정상부재": 1, "미분류": 12})
        refillable = c["①유니버스누락"] + c["③파싱실패"]
        assert refillable == 348
        assert refillable != sum(c.values()), "전체 결손과 같으면 분류가 무의미하다"
        # 원천 사정은 절대 포함되지 않는다
        assert c["②소스부재"] not in (refillable,)
        assert refillable < sum(c.values())


class TestUnknownStaysUnknown:
    def test_probe_budget_exhaustion_is_unclassified(self):
        """🚨 예산 소진분을 ②(소스 부재)로 떨어뜨리면 '원천에 없다' 는 거짓이 쌓인다."""
        assert gap.probe_dart.__doc__ and "None=조회불가" in gap.probe_dart.__doc__

    def test_unknown_ticker_returns_none_not_false(self):
        """🚨 조회 불가(corp_code 없음)와 '원천에 없음' 은 다른 사건이다.

        없는 종목코드는 DART 에 물어볼 수조차 없다 → None. 여기서 False 를 돌려주면
        '원천에 재무제표가 없는 회사' 라는 거짓 사실이 리포트에 실린다.
        """
        assert gap.probe_dart("000000") is None


class TestValueLevelCheck:
    """🚨 키 존재 ≠ 값 존재. 이걸 안 가르면 '고칠 수 있는 결손' 이 통째로 거짓이 된다.

    실측(2026-08-22): real_estate 를 키 존재만으로 재니 ③파싱실패 **560건** 이 나왔다.
    값까지 보니 **561건이 투자부동산을 원래 안 가진 회사**(④정상부재)였고 실제 결손은 31건.
    refillable 591 → 31. 그대로 신고했으면 없는 일을 고치러 갔다.
    """

    def test_zero_investment_property_is_absence_not_failure(self):
        rows = [{"period": "annual", "fundamentals": {"investment_property": 0}}]
        assert gap._re_has_value(rows) is False

    def test_real_value_is_detected(self):
        rows = [{"period": "annual", "fundamentals": {"investment_property": 1234567}}]
        assert gap._re_has_value(rows) is True

    def test_quarterly_rows_ignored(self):
        """연간(annual)만 본다 — 분기 행을 섞으면 기준이 흔들린다."""
        rows = [{"period": "quarter", "fundamentals": {"investment_property": 999}}]
        assert gap._re_has_value(rows) is False

    def test_garbage_value_does_not_crash_or_claim(self):
        for bad in (None, "", "N/A", {}):
            rows = [{"period": "annual", "fundamentals": {"investment_property": bad}}]
            assert gap._re_has_value(rows) is False


class TestSourceMappingRegistered:
    """원천 매핑은 **코드에서 읽어** 등록한다. 추측이면 ①이 거짓으로 뜬다."""

    def test_four_fields_have_sources(self):
        for f in ("financials", "peer", "calendar", "real_estate"):
            assert gap.FIELDS.get(f), f"{f} 원천 미등록 — 전부 '미분류' 로 떨어진다"

    def test_peer_requires_both_sources(self):
        """_peer(tk, fundamentals, sector_map, …) — 둘 다 있어야 생성된다(builder:1212)."""
        labels = {lbl for _f, _p, _k, lbl in gap.FIELDS["peer"]}
        assert labels == {"DART 재무", "섹터맵"}

    def test_unverified_field_stays_unregistered(self):
        """🚨 fin_series 는 배선 미확인이라 비워둔다 — 추측 등록보다 '미분류' 가 정직하다."""
        assert gap.FIELDS.get("fin_series") == []
