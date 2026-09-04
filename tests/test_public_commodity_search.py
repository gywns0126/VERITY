from pathlib import Path


COMMODITY = Path("framer-components/public-probe/PublicCommodityReport.tsx")
SEARCH = Path("framer-components/public-probe/PublicStockSearch.tsx")


def test_commodity_report_reuses_the_canonical_search_component() -> None:
    body = COMMODITY.read_text(encoding="utf-8")
    assert 'import PublicStockSearch from "https://framer.com/m/PublicStockSearch-' in body
    assert '<PublicStockSearch placeholder="종목·ETF·원자재 검색"' in body
    assert 'stockPath="/stock"' in body
    assert "stockUrl={SEARCH_UNIVERSE}" in body


def test_canonical_search_keeps_commodity_alias_support() -> None:
    body = SEARCH.read_text(encoding="utf-8")
    assert "function isCommoditySearchItem" in body
    assert 'startsWith("CMD_")' in body


def test_search_is_inside_report_flow_not_an_absolute_page_node() -> None:
    body = COMMODITY.read_text(encoding="utf-8")
    search = body.index("<PublicStockSearch")
    first_section = body.index("<section", search)
    assert search < first_section
    assert 'height: 44' in body[search - 100 : search]
