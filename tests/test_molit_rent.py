"""MOLIT 아파트 전월세 실거래 어댑터 — _parse_rent_item 파싱 회귀 테스트.

2026-05-20 신설. 국토부 RTMSDataSvcAptRent 실호출 검증된 필드 기준 (실응답 샘플).
네트워크 없이 XML item 파싱만 검증. [[feedback_real_call_over_llm_consensus]].
"""
from __future__ import annotations

import importlib.util
import os
import sys
from xml.etree import ElementTree as ET

# molit.py 는 `from ._lawd import ...` 상대 import 사용 → 패키지 컨텍스트로 로드.
_SOURCES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "vercel-api", "api", "landex", "_sources",
)
_PKG = "molit_src_pkg"
_pkg_spec = importlib.util.spec_from_file_location(
    _PKG, os.path.join(_SOURCES_DIR, "__init__.py"),
    submodule_search_locations=[_SOURCES_DIR],
)
_pkg = importlib.util.module_from_spec(_pkg_spec)
sys.modules[_PKG] = _pkg
_pkg_spec.loader.exec_module(_pkg)

_spec = importlib.util.spec_from_file_location(
    f"{_PKG}.molit", os.path.join(_SOURCES_DIR, "molit.py"),
)
molit = importlib.util.module_from_spec(_spec)
sys.modules[f"{_PKG}.molit"] = molit
_spec.loader.exec_module(molit)


def _item(xml: str) -> ET.Element:
    return ET.fromstring(xml)


# 실호출(강남구 2026-04)로 확인한 필드 구조 기준 샘플
_WOLSE = """<item>
  <aptNm>대치현대</aptNm><buildYear>1999</buildYear>
  <deposit>20,000</deposit><monthlyRent>220</monthlyRent>
  <excluUseAr>59.82</excluUseAr><floor>22</floor>
  <umdNm>대치동</umdNm><contractType>신규</contractType>
  <dealYear>2026</dealYear><dealMonth>4</dealMonth><dealDay>1</dealDay>
  <preDeposit></preDeposit><preMonthlyRent></preMonthlyRent>
</item>"""

_JEONSE = """<item>
  <aptNm>은마</aptNm><buildYear>1979</buildYear>
  <deposit>85,000</deposit><monthlyRent>0</monthlyRent>
  <excluUseAr>84.43</excluUseAr><floor>5</floor>
  <umdNm>대치동</umdNm><contractType>갱신</contractType>
  <dealYear>2026</dealYear><dealMonth>4</dealMonth><dealDay>10</dealDay>
  <preDeposit>72,000</preDeposit><preMonthlyRent>0</preMonthlyRent>
</item>"""


def test_wolse_parsed():
    """월세: monthlyRent>0 → lease_type 월세, 만원→원 변환."""
    out = molit._parse_rent_item(_item(_WOLSE))
    assert out is not None
    assert out["lease_type"] == "월세"
    assert out["deposit_won"] == 20000 * 10_000
    assert out["monthly_rent_won"] == 220 * 10_000
    assert out["area_m2"] == 59.82
    assert out["floor"] == 22
    assert out["contract_type"] == "신규"
    assert out["deal_date"] == "2026-04-01"
    assert out["pre_deposit_won"] is None  # 신규 → 종전 없음


def test_jeonse_parsed():
    """전세: monthlyRent==0 → lease_type 전세. 갱신이면 종전 보증금 보존."""
    out = molit._parse_rent_item(_item(_JEONSE))
    assert out is not None
    assert out["lease_type"] == "전세"
    assert out["monthly_rent_won"] == 0
    assert out["deposit_won"] == 85000 * 10_000
    assert out["contract_type"] == "갱신"
    assert out["pre_deposit_won"] == 72000 * 10_000  # 갱신 종전 조건


def test_invalid_zero_deposit_rejected():
    """보증금 0/결측 → None (불완전 row 제외)."""
    bad = "<item><aptNm>x</aptNm><deposit></deposit><excluUseAr>59</excluUseAr></item>"
    assert molit._parse_rent_item(_item(bad)) is None


def test_invalid_zero_area_rejected():
    """전용면적 0 → None."""
    bad = "<item><deposit>50,000</deposit><excluUseAr>0</excluUseAr><monthlyRent>0</monthlyRent></item>"
    assert molit._parse_rent_item(_item(bad)) is None


def test_offi_rent_uses_offinm():
    """오피스텔 전월세 = 아파트 전월세 동형 schema, 건물명만 offiNm."""
    xml = """<item><offiNm>강남역센트럴푸르지오시티</offiNm><buildYear>2018</buildYear>
      <deposit>10,000</deposit><monthlyRent>0</monthlyRent><excluUseAr>26.7</excluUseAr>
      <floor>10</floor><umdNm>역삼동</umdNm><contractType>신규</contractType>
      <dealYear>2026</dealYear><dealMonth>4</dealMonth><dealDay>2</dealDay></item>"""
    out = molit._parse_rent_item(_item(xml), "offiNm")
    assert out["name"] == "강남역센트럴푸르지오시티"
    assert out["lease_type"] == "전세"
    assert out["deposit_won"] == 10000 * 10_000


# 비아파트 매매 — 실호출(강남구 2026-04) 확인 필드 기준 샘플
_RH_TRADE = """<item><mhouseNm>역삼빌라</mhouseNm><dealAmount>95,000</dealAmount>
  <excluUseAr>49.5</excluUseAr><floor>3</floor><buildYear>2005</buildYear>
  <dealingGbn>중개거래</dealingGbn><cdealType></cdealType><rgstDate>26.04.20</rgstDate>
  <umdNm>역삼동</umdNm><dealYear>2026</dealYear><dealMonth>4</dealMonth><dealDay>15</dealDay></item>"""

_OFFI_TRADE = """<item><offiNm>롯데캐슬</offiNm><dealAmount>32,000</dealAmount>
  <excluUseAr>28.1</excluUseAr><floor>12</floor><buildYear>2016</buildYear>
  <dealingGbn>중개거래</dealingGbn><cdealType></cdealType>
  <umdNm>대치동</umdNm><dealYear>2026</dealYear><dealMonth>4</dealMonth><dealDay>5</dealDay></item>"""

_SH_TRADE = """<item><houseType>다가구</houseType><dealAmount>1,850,000</dealAmount>
  <plottageAr>180.5</plottageAr><totalFloorAr>320.0</totalFloorAr><buildYear>1998</buildYear>
  <dealingGbn>중개거래</dealingGbn><cdealType></cdealType>
  <umdNm>논현동</umdNm><dealYear>2026</dealYear><dealMonth>4</dealMonth><dealDay>8</dealDay></item>"""


def test_rh_trade_parsed():
    out = molit._parse_dev_trade_item(_item(_RH_TRADE), "mhouseNm")
    assert out["name"] == "역삼빌라"
    assert out["price_won"] == 95000 * 10_000
    assert out["area_m2"] == 49.5
    assert out["floor"] == 3
    assert out["price_pyeong"] > 0
    assert out["deal_date"] == "2026-04-15"


def test_offi_trade_parsed():
    out = molit._parse_dev_trade_item(_item(_OFFI_TRADE), "offiNm")
    assert out["name"] == "롯데캐슬"
    assert out["price_won"] == 32000 * 10_000
    assert out["area_m2"] == 28.1


def test_sh_trade_parsed():
    """단독/다가구 = 전용면적/건물명 없음, 대지·연면적."""
    out = molit._parse_sh_trade_item(_item(_SH_TRADE))
    assert out["house_type"] == "다가구"
    assert out["price_won"] == 1_850_000 * 10_000
    assert out["plottage_ar_m2"] == 180.5
    assert out["total_floor_ar_m2"] == 320.0
    assert "area_m2" not in out  # 전용면적 개념 없음


def test_cancelled_trade_rejected():
    """cdealType 있으면(취소거래) → None."""
    cancelled = _RH_TRADE.replace("<cdealType></cdealType>", "<cdealType>O</cdealType>")
    assert molit._parse_dev_trade_item(_item(cancelled), "mhouseNm") is None
    sh_cancelled = _SH_TRADE.replace("<cdealType></cdealType>", "<cdealType>O</cdealType>")
    assert molit._parse_sh_trade_item(_item(sh_cancelled)) is None
