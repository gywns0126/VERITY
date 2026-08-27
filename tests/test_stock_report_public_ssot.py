"""KR 공개 종목 리포트의 시장 규모·Lynch 단일 기준 계약."""
from __future__ import annotations

from api.builders.stock_report_public_builder import (
    _apply_krx_market_facts,
    _verity_lens_from_lynch,
)


def test_krx_official_market_facts_override_rich_estimates():
    stock = {
        "facts": {"시가총액": "8640억"},
        "facts_note": {},
        "header": {"market_cap": "8640억"},
        "overview": {"shares": "31,078,385주"},
    }
    _apply_krx_market_facts(
        stock,
        {"mktcap": 1_004_631_726_250, "shares": 35_562_185},
    )

    assert stock["facts"]["시가총액"] == "1.0조"
    assert stock["header"]["market_cap"] == "1.0조"
    assert stock["facts_note"]["시가총액"] == "KRX 공식 시가총액"
    assert stock["overview"]["shares"] == "35,562,185주"
    assert stock["overview"]["shares_source"] == "KRX 상장주식수"


def test_low_quality_central_lynch_is_hidden():
    assert _verity_lens_from_lynch({
        "class": "SLOW_GROWER",
        "data_quality": "low",
    }) is None


def test_ok_central_lynch_is_renderable():
    lens = _verity_lens_from_lynch({
        "class": "STALWART",
        "label": "Stalwart",
        "summary": "안정 성장 8~15%",
        "reasons": ["revenue_growth 10.9%"],
        "color": "info",
        "data_quality": "ok",
    })
    assert lens and lens["lynch"]["class"] == "STALWART"
