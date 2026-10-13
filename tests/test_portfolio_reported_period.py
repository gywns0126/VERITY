"""Offline reported-period boundaries; native case8 is an optional local witness."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import socket
import subprocess
import sys
import urllib.request
import zipfile

import pytest

from api.intelligence.portfolio_reported_period import (
    build_reported_customer_period, validate_reported_customer_period,
    validate_reported_period_projection,
)

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = "20260330000218"
SOURCE_ID = "source:dart:" + RECEIPT
QUOTE = "당사의 항공사업 주요 고객은 대한항공 등이 있습니다."
REGISTRY = {"KR:288180": {"name": "케이피항공산업", "corp_code": "01101254"}}
TABLE = """<TABLE><TR><TD>업 체</TD><TD>2025년</TD><TD>2024년</TD></TR>
<TR><TD>㈜대한항공</TD><TD>18,925</TD><TD>16,440</TD></TR>
<TR><TD>기타</TD><TD>9,246</TD><TD>8,399</TD></TR></TABLE>"""


@pytest.fixture(autouse=True)
def _isolate_data_dir(monkeypatch):
    # This module is pure: do not import unrelated account/trading fixtures.
    def denied(*args, **kwargs):
        raise AssertionError("network forbidden in reported-period tests")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(urllib.request, "urlopen", denied)


def _digest(value, *, compact=True):
    options = {"separators": (",", ":")} if compact else {}
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                             allow_nan=False, **options).encode()).hexdigest()


def _source(quote=QUOTE):
    return {"source_id": SOURCE_ID, "issuer_id": "KR:288180", "issuer_name": "케이피항공산업",
            "as_of": "2026-03-30", "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + RECEIPT,
            "text": quote, "counterparties": [{"id": "KR:003490", "name": "대한항공"}]}


def _row(source=None):
    source = _source() if source is None else source
    return {"company_id": "KR:288180", "counterparty_id": "KR:003490", "quote": source["text"],
            "scope_quote": "당사의 항공사업", "period_quote": "2025년", "source_id": SOURCE_ID,
            "source_version": _digest(source, compact=False)}


def _zip(*, quote=QUOTE, table=TABLE, member=RECEIPT + ".xml", corp="01101254",
         issuer="케이피항공산업주식회사", start="20250101", end="20251231", extra="", overview=None):
    overview = f"<P>{quote}</P>" if overview is None else overview
    xml = f"""<DOCUMENT><COMPANY-NAME AREGCIK="{corp}">{issuer}</COMPANY-NAME>
<DOCUMENT-NAME ACODE="11011">사업보고서</DOCUMENT-NAME>
<TU AUNIT="PERIODFROM" AUNITVALUE="{start}">시작</TU>
<TU AUNIT="PERIODTO" AUNITVALUE="{end}">끝</TU>{extra}
<SECTION-1><TITLE>II. 사업의 내용</TITLE>
<SECTION-2><TITLE>1. 사업의 개요</TITLE>{overview}</SECTION-2>
<SECTION-2><TITLE>4. 매출 및 수주상황</TITLE>{table}</SECTION-2></SECTION-1></DOCUMENT>"""
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, xml.encode())
    return output.getvalue()


def _build(source=None, row=None, archive=None, registry=None):
    source = _source() if source is None else source
    return build_reported_customer_period(
        source, _row(source) if row is None else row,
        archives={SOURCE_ID: _zip() if archive is None else archive},
        issuer_registry=REGISTRY if registry is None else registry,
    )


def _rehash(value):
    value["table_sha256"] = _digest(value["rows"])
    value["revision"] = _digest({k: v for k, v in value.items() if k != "revision"})
    return value


def test_valid_source_binds_closed_witness_without_mutating_inputs():
    source, row, registry, archive = _source(), _row(), deepcopy(REGISTRY), _zip()
    before = deepcopy((source, row, registry))
    context = _build(source, row, archive, registry)
    assert len(context) == 22
    assert context["report_period_start"] == "2025-01-01"
    assert context["report_period_end"] == "2025-12-31"
    assert context["rows"] == [["업 체", "2025년", "2024년"], ["㈜대한항공", "18,925", "16,440"],
                               ["기타", "9,246", "8,399"]]
    assert (context["header_row"], context["row_index"], context["column_index"]) == (0, 1, 1)
    assert validate_reported_period_projection(context, {**row, "counterparty_name": "대한항공"}) == context
    assert validate_reported_customer_period(context, source, row,
            archives={SOURCE_ID: archive}, issuer_registry=registry) == context
    assert (source, row, registry) == before
    projected = validate_reported_period_projection(context, row)
    projected["rows"][1][1] = "canary"
    assert context["rows"][1][1] == "18,925"
    assert not {"degree", "impact", "current", "core"} & set(context)


def test_factory_five_field_row_and_full_gate_type_equality_boundary():
    row = {k: v for k, v in _row().items() if k not in {"source_id", "source_version"}}
    context = _build(row=row)
    assert validate_reported_customer_period(context, _source(), row,
            archives={SOURCE_ID: _zip()}, issuer_registry=REGISTRY) == context
    context["row_index"] = True  # bool == 1 must not bypass exact type validation.
    with pytest.raises(ValueError):
        validate_reported_customer_period(context, _source(), row,
                archives={SOURCE_ID: _zip()}, issuer_registry=REGISTRY)


def test_compact_validator_fresh_process_has_no_raw_provider_or_ledger_imports():
    context = _build()
    code = """
import json, sys
from api.intelligence.portfolio_reported_period import validate_reported_period_projection
context, row = json.loads(sys.stdin.read())
validate_reported_period_projection(context, row)
blocked = ('api.intelligence.portfolio_ai_fallback', 'api.intelligence.portfolio_annual_customer_tables',
           'api.metadata.llm_cost', 'api.intelligence.portfolio_business_judgment',
           'bs4', 'openai', 'anthropic', 'google.genai', 'sqlite3')
assert not any(n == p or n.startswith(p + '.') for n in sys.modules for p in blocked)
print('compact imports PASS')
"""
    result = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT,
            input=json.dumps([context, {**_row(), "counterparty_name": "대한항공"}], ensure_ascii=False),
            text=True, capture_output=True, timeout=10, check=True)
    assert result.stdout.strip() == "compact imports PASS"


@pytest.mark.parametrize("kwargs", [
    {"member": "20260330000219.xml"}, {"corp": "00000000"}, {"issuer": "다른법인"},
    {"start": "20260101"}, {"end": "20241231"}, {"end": "20261301"},
    {"quote": QUOTE.replace("주요", "과거 주요")},
    {"overview": f"<P>{QUOTE}</P><P>{QUOTE}</P>"},
    {"overview": f"<P>{QUOTE[:-1]}</P><P>.</P>"},
    {"table": TABLE.replace("2025년", "2023년")},
    {"table": TABLE.replace("2024년", "2027년")},
    {"table": TABLE.replace("㈜대한항공", "대한항공그룹")},
    {"table": TABLE.replace("㈜대한항공", "익명")},
    {"table": TABLE.replace("<TD>㈜대한항공", '<TD colspan="2">㈜대한항공')},
    {"table": TABLE.replace("18,925", "<TABLE><TR><TD>18,925</TD></TR></TABLE>")},
    {"table": TABLE.replace("18,925", "미상")},
    {"table": TABLE + TABLE},
    {"table": TABLE.replace("기타", "㈜대한항공")},
    {"extra": '<COMPANY-NAME AREGCIK="01101254">케이피항공산업</COMPANY-NAME>'},
])
def test_source_member_header_quote_and_table_rejections(kwargs):
    with pytest.raises(ValueError):
        _build(archive=_zip(**kwargs))


@pytest.mark.parametrize("quote", [
    "당사의 항공사업 주요 고객은 대한항공이 아니며 거래가 없습니다.",
    "당사의 항공사업 과거 주요 고객은 대한항공 등이 있습니다.",
    "당사의 항공사업 2024년 주요 고객은 대한항공 등이 있습니다.",
    "당사의 항공사업 주요 고객은 대한항공 등이 될 예정입니다.",
    "당사의 항공사업 주요 고객은 대한항공 등이 있습니다",
    "당사의 항공사업 주요 고객은 대한항공 등이 있습니다. 다른 문장입니다.",
])
def test_relation_qualifiers_never_inherit_report_period(quote):
    with pytest.raises(ValueError):
        _build(source=_source(quote), archive=_zip(quote=quote))


@pytest.mark.parametrize("update", [
    {"company_id": "KR:000001"}, {"counterparty_id": "KR:000001"},
    {"source_id": "source:dart:20260330000219"}, {"source_version": "0" * 64},
    {"period_quote": "2025년도"}, {"period_quote": "2024년"}, {"scope_quote": "항공사업"},
])
def test_row_identity_source_and_year_rejections(update):
    with pytest.raises(ValueError):
        _build(row={**_row(), **update})


@pytest.mark.parametrize("update", [
    {"company_id": "KR:000001"}, {"counterparty_id": "KR:000001"},
    {"source_version": "0" * 64}, {"period_quote": "2024년"},
    {"report_period_start": "2026-01-01"}, {"report_period_end": "2025-02-30"},
    {"column_index": 0}, {"row_index": True}, {"archive_member": "other.xml"},
    {"extra": "not allowed"},
])
def test_compact_closed_shape_and_calendar_even_with_rehashed_forgery(update):
    context = _build()
    context.update(update)
    _rehash(context)
    with pytest.raises(ValueError):
        validate_reported_period_projection(context, _row())


def test_compact_name_exact_and_original_recompute_reject_stale_or_missing_body():
    source, row, archive = _source(), _row(), _zip()
    context = _build(archive=archive)
    with pytest.raises(ValueError):
        validate_reported_period_projection(context, {**row, "counterparty_name": "대한항공그룹"})
    forged = deepcopy(context)
    forged["rows"][1][1] = "999"
    with pytest.raises(ValueError):
        validate_reported_period_projection(forged, row)
    _rehash(forged)
    # Compact proof is not original authenticity. Full gate must reject it.
    assert validate_reported_period_projection(forged, row) == forged
    with pytest.raises(ValueError):
        validate_reported_customer_period(forged, source, row, archives={SOURCE_ID: archive}, issuer_registry=REGISTRY)
    for archives in ({}, {SOURCE_ID: _zip(extra="<P>changed raw body</P>")}):
        with pytest.raises(ValueError):
            validate_reported_customer_period(context, source, row, archives=archives, issuer_registry=REGISTRY)


def test_company_overview_duplicate_does_not_replace_unique_business_overview():
    extra = f"<SECTION-1><TITLE>I. 회사의 개요</TITLE><SECTION-2><TITLE>1. 회사의 개요</TITLE><P>{QUOTE}</P></SECTION-2></SECTION-1>"
    assert _build(archive=_zip(extra=extra))["paragraph_index"] == 1


def test_whitespace_only_original_match_and_full_paragraph_retention():
    overview = "<P>당사는 항공 부품을 생산합니다. " + QUOTE.replace(" ", "  ") + "</P>"
    context = _build(archive=_zip(overview=overview))
    assert context["paragraph_quote"] == "당사는 항공 부품을 생산합니다. " + QUOTE
    with pytest.raises(ValueError):
        _build(archive=_zip(overview="<P>2024년 매출 기준입니다. " + QUOTE + "</P>"))
    with pytest.raises(ValueError):
        _build(archive=_zip(overview="<P>과거 자료입니다. " + QUOTE + "</P>"))


def test_changed_scalar_and_wrong_registry_cannot_reuse_context():
    context = _build()
    source = _source()
    source["text"] = "당사는 항공 부품을 생산합니다. " + QUOTE
    with pytest.raises(ValueError):
        validate_reported_customer_period(context, source, _row(),
                archives={SOURCE_ID: _zip()}, issuer_registry=REGISTRY)
    for registry in ({}, {"KR:288180": {"name": "다른법인", "corp_code": "01101254"}},
                     {"KR:288180": {"name": "케이피항공산업", "corp_code": "00000000"}}):
        with pytest.raises(ValueError):
            _build(registry=registry)


def test_scalar_authority_unchanged_and_compact_private_fields_rejected():
    source = _source()
    for update in ({"report_period": "2025"}, {"source_version": _digest(source, compact=False)},
                   {"url": "https://example.com/"}, {"text": QUOTE * 30}):
        with pytest.raises(ValueError):
            _build(source={**source, **update})
    context = _build()
    context["rows"][1][1] = "api_key=sk-private-canary"
    _rehash(context)
    with pytest.raises(ValueError):
        validate_reported_period_projection(context, _row())


@pytest.mark.parametrize("name", ["A사", "고객1", "대한항공그룹", "기타"])
def test_anonymous_or_group_customer_not_bindable(name):
    quote = QUOTE.replace("대한항공", name)
    source = _source(quote)
    source["counterparties"][0]["name"] = name
    with pytest.raises(ValueError):
        _build(source=source, archive=_zip(quote=quote, table=TABLE.replace("㈜대한항공", name)))


def test_wrong_business_scope_and_cross_paragraph_quote_assembly_rejected():
    quote = "당사의 항공사업 주요 고객은 다른회사 등이 있으며, 방산사업 주요 고객은 대한항공 등이 있습니다."
    with pytest.raises(ValueError):
        _build(source=_source(quote), archive=_zip(quote=quote))
    with pytest.raises(ValueError):
        _build(archive=_zip(overview="<P>당사의 항공사업 주요 고객은</P><P>대한항공 등이 있습니다.</P>"))


ARCHIVE = ROOT / "data/dart_raw_cache/dart-document-20260330000218.zip"
CORPUS = ROOT / "output/member-map-integration-20260927/provider-100-20261005/corpus.json"


@pytest.mark.skipif(not ARCHIVE.is_file() or not CORPUS.is_file(), reason="case8 originals are local-only")
def test_actual_case8_native_witness_and_immutable_351_character_packet():
    source = next(c["doc"] for c in json.loads(CORPUS.read_text())["cases"]
                  if c["doc"]["source_id"] == SOURCE_ID)
    quote = "당사의 항공사업 주요 고객은 한국항공우주산업, 대한항공, Spirit 등이 있으며, 방산 및 우주사업의 주요 고객은 스페이스프로 등이 있습니다."
    row = {**_row(source), "quote": quote}
    before = deepcopy(source)
    archive = ARCHIVE.read_bytes()
    context = _build(source, row, archive)
    assert source == before and len(source["text"]) == 351
    assert context["source_version"] == "b71577b485e52ae0ab887470f94422c7a813df051c39828c5399b34dad569556"
    assert context["archive_sha256"] == "b2b8a7604637e59151e62042ef15e6b1f4c26ec1455273242b563e252b9f6fe7"
    assert context["xml_sha256"] == "d942d4e1d3026c5f779a82fcdcc29e9e123130d79788ab3122b77986c0eee49b"
    assert (context["paragraph_index"], context["table_index"], context["row_index"], context["column_index"]) == (48, 29, 1, 1)
    assert len(context["rows"]) == 6 and context["rows"][1] == ["㈜대한항공", "18,925", "16,440", "10,797"]
    assert validate_reported_customer_period(context, source, row,
            archives={SOURCE_ID: archive}, issuer_registry=REGISTRY) == context
