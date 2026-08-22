# -*- coding: utf-8 -*-
"""대주주 판정 기준가 계약 — 2026-08-22 신설.

## 왜

세금 탭이 대주주(양도세 과세 대상)를 **현재가 × 보유수** 로 판정하고 있었다.
법령은 다르다 — 소득세법 시행령 §157⑥은 **직전 사업연도 종료일 종가**를 쓰고,
없으면 **직전거래일** 종가를 쓴다.

🚨 격차가 작지 않다(2026-08-22 실측): 삼성전자 기준가 119,900 vs 현재 271,000(**+126%**),
   SK하이닉스 651,000 vs 1,691,000(**+160%**). 현재가로 재면 **실제 기준의 절반 이하
   보유액에서도 대주주로 표시**된다. 중앙값 비율은 0.897 이라 방향이 종목마다 갈려
   일괄 보정으로도 못 고친다 — 종목별 기준가가 반드시 필요하다.

## 이 테스트가 지키는 선

① **기준일은 역년 말**이다. 개인 양도자의 '사업연도' = 과세기간 = 역년이라
   종목 결산월(`kr_fiscal_month.json`)과 무관하다. 그 둘을 섞으면 안 된다.
② **휴장 폴백**이 조문에 있다. 2025-12-31 은 연말 폐장이라 실제로 거래가 없고
   전 종목이 12-30 을 쓴다. `==` 로만 찾으면 전 종목 결손이 된다.
③ **0건 산출을 성공으로 끝내지 않는다**(exit 1). 입력 부재·스키마 변경이 조용히 통과한다.
"""
from __future__ import annotations

import datetime
import json
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from api.builders import kr_prior_fy_close_builder as b  # noqa: E402


class TestBasisDate:
    def test_is_prior_calendar_year_end(self):
        assert b.basis_yyyymmdd(datetime.datetime(2026, 8, 22)) == 20251231
        assert b.basis_yyyymmdd(datetime.datetime(2026, 1, 2)) == 20251231
        assert b.basis_yyyymmdd(datetime.datetime(2027, 3, 1)) == 20261231

    def test_does_not_depend_on_corporate_fiscal_month(self):
        """🚨 법인 결산월과 무관 — 개인 과세기간은 역년이다.

        `kr_fiscal_month.json` 은 재무제표 분기 귀속용이지 양도세 판정용이 아니다.
        섞으면 6월 결산 법인 보유분만 다른 기준일로 판정된다.
        """
        src = open(os.path.join(_ROOT, "api", "builders",
                                "kr_prior_fy_close_builder.py"), encoding="utf-8").read()
        assert "kr_fiscal_month" not in src.split('"""')[2], "결산월 맵을 판정에 끌어들이면 안 된다"


class TestHolidayFallback:
    """② 조문 단서 — '없으면 직전거래일'."""

    def _chunk(self, tmp_path, candles):
        d = tmp_path / "kr_chart_daily"
        d.mkdir()
        (d / "chunk_00.json").write_text(json.dumps(
            {"as_of": "20260820", "stocks": {"000000": {"n": "테스트", "m": "KOSPI", "c": candles}}},
            ensure_ascii=False), encoding="utf-8")
        return str(d)

    def test_uses_prior_trading_day_when_year_end_absent(self, tmp_path, monkeypatch):
        monkeypatch.setattr(b, "SRC", self._chunk(tmp_path, [
            [20251229, 1, 1, 1, 900, 10], [20251230, 1, 1, 1, 1000, 10], [20260102, 1, 1, 1, 1200, 10]]))
        r = b.build(datetime.datetime(2026, 8, 22))
        assert r["prices"]["000000"] == 1000, "12-31 부재 시 12-30 을 써야 한다"
        assert r["fallback_used"] == 1

    def test_exact_year_end_preferred(self, tmp_path, monkeypatch):
        monkeypatch.setattr(b, "SRC", self._chunk(tmp_path, [
            [20251230, 1, 1, 1, 1000, 10], [20251231, 1, 1, 1, 1111, 10]]))
        r = b.build(datetime.datetime(2026, 8, 22))
        assert r["prices"]["000000"] == 1111
        assert r["fallback_used"] == 0

    def test_never_uses_future_price(self, tmp_path, monkeypatch):
        """🚨 기준일 이후 가격을 쓰면 룩어헤드다 — 판정이 미래 정보로 오염된다."""
        monkeypatch.setattr(b, "SRC", self._chunk(tmp_path, [
            [20251230, 1, 1, 1, 1000, 10], [20260820, 1, 1, 1, 9999, 10]]))
        r = b.build(datetime.datetime(2026, 8, 22))
        assert r["prices"]["000000"] == 1000, "기준일 이후 종가를 채택했다(룩어헤드)"

    def test_no_candle_before_basis_is_missing_not_zero(self, tmp_path, monkeypatch):
        """상장 전이라 이력이 없으면 **미보유**다. 0 이나 현재가로 채우지 않는다."""
        monkeypatch.setattr(b, "SRC", self._chunk(tmp_path, [[20260820, 1, 1, 1, 5000, 10]]))
        r = b.build(datetime.datetime(2026, 8, 22))
        assert "000000" not in r["prices"]
        assert r["missing"] == 1


class TestRealArtifact:
    """실제 산출물이 있으면 그 정합도 본다(없으면 skip — 로컬 미생성 허용)."""

    @pytest.fixture
    def doc(self):
        p = os.path.join(_ROOT, "data", "kr_prior_fy_close.json")
        if not os.path.exists(p):
            pytest.skip("산출물 미생성")
        return json.load(open(p, encoding="utf-8"))

    def test_meta_declares_rule_and_basis(self, doc):
        m = doc["_meta"]
        assert m["requested_date"] == b.basis_yyyymmdd()
        assert "157" in m["rule"], "근거 조문을 산출물이 자기 입으로 신고해야 한다"
        assert "판정 **전용**" in m["note"] or "판정" in m["note"]

    def test_prices_are_positive(self, doc):
        bad = [k for k, v in doc["prices"].items() if not (isinstance(v, (int, float)) and v > 0)]
        assert not bad, f"0 이하 종가: {bad[:5]}"
