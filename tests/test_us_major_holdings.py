"""us_major_holdings_public_builder — SC 13D/13G primary_doc.xml 파싱 검증 (네트워크 없음).

[[project_us_financials_sec_edgar]] (b) 13D-G 대량보유. SEC 실호출은
[[feedback_real_call_over_llm_consensus]] 스모크 검증(Vanguard AAPL 7.48% 등).
"""
from __future__ import annotations

from api.builders import us_major_holdings_public_builder as b


# SEC Schedule 13G primary_doc.xml 재현 (namespace 포함 — _strip_ns 검증).
DOC_13G = """<?xml version="1.0" encoding="UTF-8"?>
<edgarSubmission xmlns="http://www.sec.gov/edgar/schedule13g" xmlns:com="http://www.sec.gov/edgar/common">
<headerData><submissionType>SCHEDULE 13G</submissionType></headerData>
<formData>
  <coverPageHeader>
    <securitiesClassTitle>Common Stock</securitiesClassTitle>
    <eventDateRequiresFilingThisStatement>03/31/2026</eventDateRequiresFilingThisStatement>
    <issuerInfo><issuerName>Acme Inc</issuerName></issuerInfo>
  </coverPageHeader>
  <coverPageHeaderReportingPersonDetails>
    <reportingPersonName>Vanguard Capital Management</reportingPersonName>
    <classPercent>7.48</classPercent>
    <reportingPersonBeneficiallyOwnedAggregateNumberOfShares>1099168953</reportingPersonBeneficiallyOwnedAggregateNumberOfShares>
  </coverPageHeaderReportingPersonDetails>
</formData>
</edgarSubmission>"""


def test_form_type_labels():
    assert b._form_type("SC 13D") == "13D"
    assert b._form_type("SCHEDULE 13D/A") == "13D/A"
    assert b._form_type("SC 13G") == "13G"
    assert b._form_type("SCHEDULE 13G/A") == "13G/A"


def test_parse_13g_structured():
    filer, pct, shares, cls, ev, filer_cik = b._parse_13dg(DOC_13G)
    assert filer == "Vanguard Capital Management"
    assert pct == 7.48
    assert shares == 1099168953
    assert cls == "Common Stock"
    assert ev == "03/31/2026"


def test_parse_extracts_filer_cik_for_issuer_self_guard():
    # filer CIK 추출 — 호출자가 대상 CIK 와 비교해 issuer-self 신고 제외(2026-06-23 검수).
    doc = """<?xml version="1.0"?>
    <edgarSubmission xmlns="http://www.sec.gov/edgar/schedule13g">
    <headerData><filerInfo><filer><filerCredentials><cik>0000320193</cik></filerCredentials></filer></filerInfo></headerData>
    <formData><coverPageHeaderReportingPersonDetails>
      <reportingPersonName>Apple Inc</reportingPersonName><classPercent>90.0</classPercent>
    </coverPageHeaderReportingPersonDetails></formData></edgarSubmission>"""
    filer, pct, shares, cls, ev, filer_cik = b._parse_13dg(doc)
    assert filer_cik == 320193                 # CIK 정수화(선행 0 제거)
    assert b._cik_int("0000320193") == 320193  # 대상 CIK 와 동일 → 호출자가 self 판정


def test_parse_malformed_returns_none():
    assert b._parse_13dg("<broken") is None


def test_parse_empty_cover_returns_none():
    # 구조화 필드 전무 → None (older/비표준 문서 graceful).
    assert b._parse_13dg("<edgarSubmission><formData></formData></edgarSubmission>") is None


def test_form_set_covers_variants():
    # 대상회사 submissions 의 실제 form 변형 모두 매칭.
    for f in ["SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A",
              "SCHEDULE 13D", "SCHEDULE 13G/A"]:
        assert f.upper() in b.FORM_SET
    assert "13F-HR" not in b.FORM_SET   # 13F 는 별개(CUSIP 스프린트)
