from __future__ import annotations

from api.collectors import sec_inline_xbrl as inline
from api.intelligence import us_financials as usf


INLINE = b"""
<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"
      xmlns:xbrli="http://www.xbrl.org/2003/instance">
<body>
  <xbrli:context id="duration"><xbrli:entity><xbrli:identifier>1</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period>
  </xbrli:context>
  <xbrli:context id="instant"><xbrli:entity><xbrli:identifier>1</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period>
  </xbrli:context>
  <xbrli:context id="segment"><xbrli:entity><xbrli:identifier>1</xbrli:identifier>
    <xbrli:segment><member>product</member></xbrli:segment></xbrli:entity>
    <xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period>
  </xbrli:context>
  <xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
  <ix:nonNumeric name="dei:DocumentFiscalYearFocus" contextRef="duration">2026</ix:nonNumeric>
  <ix:nonNumeric name="dei:DocumentFiscalPeriodFocus" contextRef="duration">Q2</ix:nonNumeric>
  <ix:nonFraction name="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"
      contextRef="duration" unitRef="usd" scale="6">1,250</ix:nonFraction>
  <ix:nonFraction name="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"
      contextRef="segment" unitRef="usd" scale="6">9,999</ix:nonFraction>
  <ix:nonFraction name="us-gaap:Assets" contextRef="instant" unitRef="usd" scale="6">2,500</ix:nonFraction>
</body></html>
"""


def test_parse_inline_xbrl_emits_consolidated_companyfacts_shape():
    parsed = inline.parse_inline_xbrl(
        INLINE, accession="0001-26-000001", form="10-Q", filing_date="2026-08-01"
    )
    assert parsed["_inline_meta"]["fiscal_period"] == "Q2"
    revenue = usf.extract_metric_series(parsed, "revenue")
    assets = usf.extract_metric_series(parsed, "total_assets")
    assert [row["val"] for row in revenue] == [1_250_000_000]
    assert [row["val"] for row in assets] == [2_500_000_000]
    assert revenue[0]["filed"] == "2026-08-01"


def test_merge_and_accession_detection():
    base = {"facts": {"us-gaap": {}}}
    overlay = inline.parse_inline_xbrl(INLINE, accession="A", form="10-Q")
    merged = inline.merge_companyfacts(base, overlay)
    assert inline.has_accession(base, "A") is False
    assert inline.has_accession(merged, "A") is True
    assert base == {"facts": {"us-gaap": {}}}


def test_filing_url_uses_sec_archive_shape():
    assert inline.filing_url(1403161, "0001403161-26-000104", "v-20260630.htm") == (
        "https://www.sec.gov/Archives/edgar/data/1403161/000140316126000104/v-20260630.htm"
    )
