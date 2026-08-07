# -*- coding: utf-8 -*-
"""SEC 8-K 리스크 공시 — 티커 추출 결함 수리 (2026-08-07).

사고: EDGAR 전문검색이 `_source.tickers` 를 비워 보내는데 그대로 "" 를 저장했다.
하류 매칭이 `if ft and ft in port_tickers` 라 **원천적으로 성립 불가** → `sec_risk_flags`
0/39, SEC 8-K 리스크 downgrade 규칙이 상시 사문화(검사 E 미발동 13종 중 하나).

티커는 표시명 안에 있었다 — "ESAB Corp  (ESAB)  (CIK 0001877322)".
URL 도 깨져 있었다 — entity_id 는 빈 문자열, file_num 은 **리스트**라
".../data//['0001877322-26-...']" 가 생성됐다.

계약: ① 표시명에서 티커·CIK 추출 ② 티커 없는 발행사는 빈 문자열(추측 금지)
③ URL 은 사용 가능한 값일 때만 archive, 아니면 CIK 조회로 폴백 + 경로 기록.
"""
import pytest

from api.collectors.sec_edgar import _cik_from_display, _ticker_from_display


@pytest.mark.parametrize("display,ticker,cik", [
    ("ESAB Corp  (ESAB)  (CIK 0001877322)", "ESAB", "0001877322"),
    ("TELEFLEX INC  (TFX)  (CIK 0000096943)", "TFX", "0000096943"),
    ("NOCOPI TECHNOLOGIES INC/MD/  (NNUP)  (CIK 0000888981)", "NNUP", "0000888981"),
    ("Digital Turbine, Inc.  (APPS)  (CIK 0003177000)", "APPS", "0003177000"),
])
def test_extracts_ticker_and_cik(display, ticker, cik):
    assert _ticker_from_display(display) == ticker
    assert _cik_from_display(display) == cik


def test_issuer_without_ticker_returns_empty():
    """🚨 티커 없는 발행사는 빈 문자열 — 지어내지 않는다(잘못된 종목에 리스크가 붙는다)."""
    d = "ALEXANDER TECH CORP  (CIK 0001347491)"
    assert _ticker_from_display(d) == ""
    assert _cik_from_display(d) == "0001347491"


def test_cik_parens_not_mistaken_for_ticker():
    assert _ticker_from_display("SOME CORP  (CIK 0001234567)") == ""


def test_empty_and_none_safe():
    for v in ("", None):
        assert _ticker_from_display(v) == "" and _cik_from_display(v) == ""


def test_matching_now_possible():
    """수리 전에는 티커가 공백이라 어떤 보유 종목과도 매칭될 수 없었다."""
    filings = ["ESAB Corp  (ESAB)  (CIK 0001877322)",
               "TELEFLEX INC  (TFX)  (CIK 0000096943)"]
    port = {"TFX", "GOOGL"}
    matched = [d for d in filings if _ticker_from_display(d) in port]
    assert len(matched) == 1
