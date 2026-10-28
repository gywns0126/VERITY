"""Incremental rows versus the independent, unchanged whole-bundle matcher.

The harness wraps only the two proposed engine call sites in memory. The oracle
is the original engine function with neither wrapper; no engine file is edited.
"""
from copy import deepcopy
from datetime import date, datetime, timezone, timedelta
import base64
import gzip
import importlib
import json
from pathlib import Path
import sys
import types
from unittest.mock import Mock

import pytest


CORE = Path(__file__).resolve().parents[1] / "vercel-api/api/portfolio_core"


@pytest.fixture
def modules(monkeypatch):
    package = types.ModuleType("incremental_business_test")
    package.__path__ = [str(CORE)]
    monkeypatch.setitem(sys.modules, package.__name__, package)
    engine = importlib.import_module(package.__name__ + ".portfolio_engine")
    helper = importlib.import_module(package.__name__ + ".portfolio_business_incremental")
    engine._reset_projection_cache_for_tests()
    yield engine, helper
    for name in tuple(sys.modules):
        if name == package.__name__ or name.startswith(package.__name__ + "."):
            sys.modules.pop(name, None)


@pytest.fixture
def documents():
    stocks = [{"ticker": ticker, "market": "KR", "name": name} for ticker, name in (
        ("001111", "합성회사"), ("003333", "합성제조사"),
        ("004444", "합성항만"), ("002222", "합성고객"), ("005555", "별도고객"))]
    texts = ["당사의 주요 매출처는 합성고객, 미확인고객입니다. 당사는 전력을 구매하고 있습니다.",
             "당사의 주요 구매처는 별도고객입니다. 당사는 구리를 원재료로 사용하고 있습니다.",
             "당사는 부두를 운영하고 있습니다. 미확인고객에 관한 산업 자료입니다."]
    rows = {stock["ticker"]: {"name": stock["name"], "text": text, "chars": len(text),
        "fiscal_year": "2025", "filed_at": "20260318", "report": "사업보고서 (2025.12)",
        "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo=2026031800000{i}", "truncated": False}
        for i, (stock, text) in enumerate(zip(stocks, texts), 1)}
    return {"universe_search.json": {"stocks": stocks}, "kr_business_overview_public.json": {
        "_meta": {"count": len(rows), "generated_at": "2026-10-12T00:00:00Z"}, "rows": rows}}


def _bytes(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False).encode()


class Harness:
    def __init__(self, modules):
        self.engine, self.helper = modules
        self.memo = self.helper.BusinessRowMemo()

    def run(self, documents, *, catalog=None):
        engine = self.engine
        if catalog is None:
            catalog = {row["id"]: row for row in engine.add_public_company_names(
                documents, engine.project_public_sources(documents)["companies"])}
        business = engine.project_public_business_overviews(documents)
        before = _bytes([documents, catalog, business])
        expected = engine._business_material_index(documents, catalog)
        enabled = self.memo.prepare(documents, catalog, business)
        by_issuer = {row["issuer_id"]: row for row in business["rows"]}
        original = engine._company_mentions
        mentions = Mock(wraps=original)
        context = Mock(wraps=self.helper.index_filing_market_context)

        def match(text, trie, issuer):
            return self.memo.mentions(by_issuer[issuer], lambda: mentions(text, trie, issuer))

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(engine, "_company_mentions", match)
            patch.setattr(engine, "index_filing_market_context", self.memo.market_context)
            patch.setattr(self.helper, "index_filing_market_context", context)
            actual = engine._business_material_index(documents, catalog)
        assert actual == expected
        assert _bytes(actual) == _bytes(expected)
        assert _bytes([documents, catalog, business]) == before
        recomputed = [call.args[2] for call in mentions.call_args_list]
        contexts = sum(len(call.args[0]["rows"]) for call in context.call_args_list)
        return actual, recomputed, contexts, enabled


def test_warm_refresh_reuses_public_rows_and_isolates_returned_values(modules, documents):
    harness = Harness(modules)
    first, calls, contexts, enabled = harness.run(documents)
    assert enabled and len(calls) == contexts == 3
    assert first["reported_roles"]["relations"]
    assert first["market_context"]["power"]["coverage"]["references"]
    assert first["market_context"]["infrastructure"]["coverage"]["references"]
    first["market_context"]["by_indicator"].clear()
    first["materials"].clear()
    documents["portfolio.json"] = {"headlines": []}
    documents["kr_business_overview_public.json"]["_meta"]["generated_at"] = "2026-10-13T00:00:00Z"
    _, calls, contexts, enabled = harness.run(documents)
    assert enabled and calls == [] and contexts == 0


@pytest.mark.parametrize("field,value", [
    ("text", "당사는 합성고객에 관해 보고합니다. 당사는 전력을 공급하고 있습니다."),
    ("name", "변경회사"), ("fiscal_year", "2024"), ("report", "[기재정정]사업보고서 (2025.12)"),
    ("filed_at", "20260319"), ("truncated", True),
    ("url", "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260319000001"),
])
def test_source_correction_only_recomputes_changed_issuer(modules, documents, field, value):
    harness = Harness(modules)
    harness.run(documents)
    row = documents["kr_business_overview_public.json"]["rows"]["001111"]
    row[field] = value
    row["chars"] = len(row["text"])
    _, calls, contexts, _ = harness.run(documents)
    assert calls == ["KR:001111"] and contexts == 1


@pytest.mark.parametrize("change", ["removed", "rejected", "missing"])
def test_removed_rejected_missing_rows_do_not_leave_ghosts(modules, documents, change):
    harness = Harness(modules)
    harness.run(documents)
    overview = documents["kr_business_overview_public.json"]
    if change == "removed":
        overview["rows"].pop("001111")
        overview["_meta"]["count"] -= 1
    elif change == "rejected":
        overview["rows"]["001111"]["chars"] += 1
    else:
        documents.pop("kr_business_overview_public.json")
    _, calls, contexts, _ = harness.run(documents)
    assert calls == [] and contexts == 0
    assert "KR:001111" not in harness.memo._rows
    if change == "missing":
        assert not harness.memo._rows


@pytest.mark.parametrize("change", ["unrelated-add", "matching-add", "alias-add", "ambiguous",
                                     "remove", "rename", "source-alias"])
def test_catalog_changes_invalidate_hits_misses_and_ambiguity(modules, documents, change):
    harness = Harness(modules)
    harness.run(documents)
    stocks = documents["universe_search.json"]["stocks"]
    catalog = None
    if change in ("unrelated-add", "matching-add", "alias-add", "ambiguous"):
        name = {"unrelated-add": "무관한회사", "matching-add": "미확인고객",
                "alias-add": "Unrelated", "ambiguous": "합성고객"}[change]
        stocks.append({"ticker": "006666", "market": "KR", "name": name,
                       "name_ko": "미확인고객" if change == "alias-add" else None})
    elif change == "remove":
        stocks[:] = [row for row in stocks if row["ticker"] != "002222"]
    elif change == "rename":
        stocks[3]["name"] = "변경고객"
    else:
        catalog = {row["id"]: row for row in harness.engine.add_public_company_names(
            documents, harness.engine.project_public_sources(documents)["companies"])}
        catalog["KR:002222"]["source_names"].append("미확인고객")
    _, calls, contexts, _ = harness.run(documents, catalog=catalog)
    expected = ([] if change == "unrelated-add" else ["KR:001111", "KR:004444"]
                if change in ("matching-add", "alias-add", "source-alias") else ["KR:001111"])
    assert calls == expected and contexts == 0


def test_issuer_becomes_known_and_source_order_changes(modules, documents):
    harness = Harness(modules)
    removed = documents["universe_search.json"]["stocks"].pop(0)
    harness.run(documents)
    documents["universe_search.json"]["stocks"].append(removed)
    overview = documents["kr_business_overview_public.json"]
    overview["rows"] = dict(reversed(list(overview["rows"].items())))
    _, calls, contexts, _ = harness.run(documents)
    assert calls == ["KR:001111"] and contexts == 0


def test_ambiguity_removal_restores_unique_matches_and_new_alias_removal_restores_misses(modules, documents):
    harness = Harness(modules)
    harness.run(documents)
    stocks = documents["universe_search.json"]["stocks"]
    stocks.append({"ticker": "006666", "market": "KR", "name": "합성고객"})
    ambiguous, calls, _, _ = harness.run(documents)
    assert calls == ["KR:001111"]
    assert not ambiguous["materials"] or "KR:002222" not in ambiguous["by_company"]
    stocks.pop()
    unique, calls, _, _ = harness.run(documents)
    assert calls == ["KR:001111"] and "KR:002222" in unique["by_company"]
    stocks.append({"ticker": "006666", "market": "KR", "name": "미확인고객"})
    harness.run(documents)
    stocks.pop()
    _, calls, contexts, _ = harness.run(documents)
    assert calls == ["KR:001111", "KR:004444"] and contexts == 0


def test_new_source_row_and_changed_row_after_prepare_are_not_reused(modules, documents):
    harness = Harness(modules)
    harness.run(documents)
    overview = documents["kr_business_overview_public.json"]
    row = deepcopy(overview["rows"]["001111"])
    row["name"] = "추가회사"
    overview["rows"]["006666"] = row
    overview["_meta"]["count"] += 1
    documents["universe_search.json"]["stocks"].append({
        "ticker": "006666", "market": "KR", "name": "추가회사"})
    _, calls, contexts, _ = harness.run(documents)
    assert calls == ["KR:006666"] and contexts == 1
    projected = harness.engine.project_public_business_overviews(documents)["rows"][0]
    projected["source"]["receipt_no"] = "20260319000001"
    sentinel = Mock(return_value=([], 0))
    assert harness.memo.mentions(projected, sentinel) == ([], 0)
    assert sentinel.call_count == 1


@pytest.mark.parametrize("boundary", ["local", "utc", "implementation"])
def test_exact_date_and_implementation_boundaries(modules, documents, monkeypatch, boundary):
    harness = Harness(modules)
    harness.run(documents)
    helper = modules[1]
    if boundary == "local":
        class Tomorrow(date):
            @classmethod
            def today(cls):
                return date.today() + timedelta(days=1)
        monkeypatch.setattr(helper, "date", Tomorrow)
    elif boundary == "utc":
        class Tomorrow(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.now(timezone.utc) + timedelta(days=1)
        monkeypatch.setattr(helper, "datetime", Tomorrow)
    else:
        monkeypatch.setattr(helper, "implementation_sha256", lambda: "changed-code")
    _, calls, contexts, _ = harness.run(documents)
    assert len(calls) == contexts == 3


@pytest.mark.parametrize("limit", ["MAX_ROWS", "MAX_COMPANIES", "MAX_BYTES", "MAX_CATALOG_BYTES"])
def test_capacity_is_a_cache_miss_not_output_truncation(modules, documents, monkeypatch, limit):
    monkeypatch.setattr(modules[1], limit, 1)
    harness = Harness(modules)
    harness.run(documents)
    _, calls, contexts, enabled = harness.run(documents)
    assert len(calls) == contexts == 3
    assert not harness.memo._rows
    assert enabled is (limit == "MAX_BYTES")


def test_large_catalog_delta_uses_full_mention_recomputation(modules, documents, monkeypatch):
    harness = Harness(modules)
    harness.run(documents)
    monkeypatch.setattr(modules[1], "MAX_CHANGED_COMPANIES", 1)
    for ticker in ("006666", "007777"):
        documents["universe_search.json"]["stocks"].append({
            "ticker": ticker, "market": "KR", "name": "무관한회사"})
    _, calls, contexts, _ = harness.run(documents)
    assert len(calls) == 3 and contexts == 0


def test_only_closed_public_fields_are_retained(modules, documents):
    harness = Harness(modules)
    catalog = {row["id"]: row for row in harness.engine.add_public_company_names(
        documents, harness.engine.project_public_sources(documents)["companies"])}
    catalog["KR:001111"]["private_note"] = "DO_NOT_RETAIN"
    documents["universe_search.json"]["stocks"][0]["private_note"] = "DO_NOT_RETAIN"
    harness.run(documents, catalog=catalog)
    assert "DO_NOT_RETAIN" not in repr(vars(harness.memo))
    business = harness.engine.project_public_business_overviews(documents)
    business["rows"][0]["private_note"] = "DO_NOT_RETAIN"
    assert not harness.memo.prepare(documents, catalog, business)
    assert not harness.memo._rows and not harness.memo._catalog
    harness.memo.clear()
    assert not harness.memo._current


@pytest.mark.parametrize("alias", ["주식회사 합성고객", "합성고객(주1)", "합성 고객", "합성고객",
                                  "ＭＩＳＳＩＮＧ", "미확인고객"])
def test_legal_unicode_space_and_footnote_alias_deltas_are_conservative(modules, documents, alias):
    harness = Harness(modules)
    harness.run(documents)
    documents["universe_search.json"]["stocks"].append({
        "ticker": "006666", "market": "US", "name": "New Company", "name_ko": alias})
    # Valid US identity; the full matcher chooses whether the alias is usable.
    documents["universe_search.json"]["stocks"][-1]["ticker"] = "NEW"
    harness.run(documents)
    harness.run(documents)


def test_prepared_index_shape_and_receipt_validation_remain_compatible(modules, documents):
    harness = Harness(modules)
    index, _, _, _ = harness.run(documents)
    engine = modules[0]
    artifact = engine.build_prepared_business_index(documents)
    artifact["index"] = index
    catalog = {row["id"]: row for row in artifact["catalog"]}
    receipt = engine.prepared_business_publisher_receipt(artifact)
    checked = engine.checked_business_index(artifact, receipt, artifact["source_revision"], documents, catalog)
    assert checked == index
    prepared = importlib.import_module(engine.__package__ + ".portfolio_prepared_business")
    assert "portfolio_business_incremental.py" in prepared._IMPLEMENTATION_FILES


def test_real_engine_refresh_only_matches_changed_row_and_clear_rebuilds(modules, documents, monkeypatch):
    engine, helper = modules
    matches = Mock(wraps=engine._company_mentions)
    context = Mock(wraps=helper.index_filing_market_context)
    monkeypatch.setattr(engine, "_company_mentions", matches)
    monkeypatch.setattr(helper, "index_filing_market_context", context)
    first = engine.prepare_public_index(documents, "1" * 64)
    assert matches.call_count == 3
    assert len(engine._PROJECTED_PUBLIC_INDEX._row_memo._rows) == 3
    # The unchanged public bundle itself is also reused under the real lock.
    assert engine.prepare_public_index(documents, "1" * 64) is first
    assert matches.call_count == 3

    changed = deepcopy(documents)
    row = changed["kr_business_overview_public.json"]["rows"]["001111"]
    row["text"] = "당사의 주요 매출처는 합성고객입니다. 당사는 전력을 공급하고 있습니다."
    row["chars"] = len(row["text"])
    matches.reset_mock()
    context.reset_mock()
    refreshed = engine.prepare_public_index(changed, "2" * 64)
    assert matches.call_count == 1
    assert matches.call_args.args[2] == "KR:001111"
    assert sum(len(call.args[0]["rows"]) for call in context.call_args_list) == 1
    uncached = engine._business_material_index(changed, refreshed["by_id"])
    assert _bytes(refreshed["business_materials"]) == _bytes(uncached)

    engine._reset_projection_cache_for_tests()
    memo = engine._PROJECTED_PUBLIC_INDEX._row_memo
    assert not memo._rows and not memo._catalog and not memo._current
    matches.reset_mock()
    context.reset_mock()
    rebuilt = engine.prepare_public_index(changed, "2" * 64)
    assert matches.call_count == 3
    assert sum(len(call.args[0]["rows"]) for call in context.call_args_list) == 3
    assert _bytes(rebuilt["business_materials"]) == _bytes(uncached)


def test_real_engine_unknown_issuer_then_binding_is_exact(modules, documents, monkeypatch):
    engine, _ = modules
    unknown = deepcopy(documents)
    stocks = unknown["universe_search.json"]["stocks"]
    issuer = stocks.pop(0)
    matches = Mock(wraps=engine._company_mentions)
    monkeypatch.setattr(engine, "_company_mentions", matches)
    first = engine.prepare_public_index(unknown, "3" * 64)
    assert matches.call_count == 2
    assert first["business_materials"]["coverage"]["unknown_issuer"] == 1
    assert _bytes(first["business_materials"]) == _bytes(
        engine._business_material_index(unknown, first["by_id"]))
    stocks.append(issuer)
    matches.reset_mock()
    resolved = engine.prepare_public_index(unknown, "4" * 64)
    assert matches.call_count == 1 and matches.call_args.args[2] == "KR:001111"
    assert _bytes(resolved["business_materials"]) == _bytes(
        engine._business_material_index(unknown, resolved["by_id"]))


@pytest.mark.parametrize("failure", ["code-unavailable", "catalog-unbounded", "revision-unbounded"])
def test_real_engine_memo_failure_keeps_whole_matcher_output(modules, documents, monkeypatch, failure):
    engine, helper = modules
    engine.prepare_public_index(documents, "5" * 64)
    if failure == "code-unavailable":
        monkeypatch.setattr(helper, "implementation_sha256", Mock(side_effect=OSError("unavailable")))
    else:
        monkeypatch.setattr(helper, "MAX_COMPANIES", 1)
        if failure == "revision-unbounded":
            monkeypatch.setattr(engine, "_business_index_revision", lambda *_args: None)
    changed = deepcopy(documents)
    changed["kr_business_overview_public.json"]["_meta"]["generated_at"] = "2026-10-14T00:00:00Z"
    matches = Mock(wraps=engine._company_mentions)
    monkeypatch.setattr(engine, "_company_mentions", matches)
    result = engine.prepare_public_index(changed, "6" * 64)
    assert matches.call_count == 3
    assert not engine._PROJECTED_PUBLIC_INDEX._row_memo._rows
    assert _bytes(result["business_materials"]) == _bytes(
        engine._business_material_index(changed, result["by_id"]))


@pytest.mark.parametrize("boundary", ["local", "utc", "implementation"])
def test_real_engine_refresh_does_not_bypass_row_memo_boundaries(modules, documents, monkeypatch, boundary):
    engine, helper = modules
    first = engine.prepare_public_index(documents, "7" * 64)
    if boundary == "local":
        class Tomorrow(date):
            @classmethod
            def today(cls):
                return date.today() + timedelta(days=1)
        monkeypatch.setattr(engine, "date", Tomorrow)
        monkeypatch.setattr(helper, "date", Tomorrow)
    elif boundary == "utc":
        class Tomorrow(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.now(timezone.utc) + timedelta(days=1)
        monkeypatch.setattr(engine, "datetime", Tomorrow)
        monkeypatch.setattr(helper, "datetime", Tomorrow)
    else:
        monkeypatch.setattr(engine, "_prepared_implementation_sha256", lambda: "0" * 64)
        monkeypatch.setattr(helper, "implementation_sha256", lambda: "0" * 64)
    matches = Mock(wraps=engine._company_mentions)
    monkeypatch.setattr(engine, "_company_mentions", matches)
    result = engine.prepare_public_index(documents, "8" * 64)
    assert matches.call_count == 3
    assert result["business_materials"] == first["business_materials"]


def _filing_base(modules, documents, *, codes=True, nullable=False):
    engine = modules[0]
    prepared = importlib.import_module(engine.__package__ + ".portfolio_prepared_business")
    accession = "0000000001-25-000001"
    primary = "" if nullable else "report.htm"
    raw = {"title": "Synthetic amended current report", "label": "8-K/A",
           "is_correction": True, "date": "2025-03-12", "filing_date": "2025-03-12",
           "report_date": "" if nullable else "2024-12-31",
           "acceptance_datetime": "" if nullable else "2025-03-12T23:15:00Z",
           "cik": "0000000123", "accession_number": accession,
           "primary_document": primary, "private_note": "DO_NOT_RETAIN",
           "source_url": "https://www.sec.gov/Archives/edgar/data/123/000000000125000001/"
                         + (primary or accession + "-index.htm")}
    if codes:
        raw["item_codes"] = ["2.02", "8.01"]
    inputs = {**documents, "stock_report_public.json": {"stocks": []},
              "us_stock_report_public.json": {"stocks": [
                  {"ticker": "SYNTH", "name": "Synthetic", "disclosures": [raw]}]}}
    artifact = engine.build_prepared_business_index(inputs)
    companies = json.loads(gzip.decompress(base64.b64decode(artifact["base_projection"]["data"])))
    document = next(row for row in companies if row["id"] == "US:SYNTH")["documents"][0]
    assert "filing" in document
    return prepared, artifact, companies, document


def _decode_base(prepared, artifact, companies):
    artifact["base_projection"]["data"] = base64.b64encode(
        gzip.compress(_bytes(companies), mtime=0)).decode("ascii")
    return prepared.checked_base_projection(artifact, prepared.publisher_receipt_for(artifact),
                                            artifact["base_projection"]["source_revision"])


@pytest.mark.parametrize("codes", [False, True])
@pytest.mark.parametrize("nullable", [False, True])
def test_prepared_sec_filing_roundtrip_and_nullable_fields(modules, documents, codes, nullable):
    prepared, artifact, companies, document = _filing_base(modules, documents, codes=codes, nullable=nullable)
    assert ("item_codes" in document) is codes
    assert _decode_base(prepared, artifact, companies) == companies
    if nullable:
        assert all(document["filing"][key] is None for key in
                   ("primary_document", "report_date", "acceptance_datetime"))
    assert b"DO_NOT_RETAIN" not in _bytes(companies)


@pytest.mark.parametrize("mutation", [
    "extra-field", "missing-field", "wrong-source", "kr-issuer", "wrong-id", "wrong-url",
    "wrong-form", "wrong-amendment", "wrong-cik", "wrong-accession", "future-filing",
    "report-after-filed", "naive-acceptance", "oversize", "nested", "not-dict",
])
def test_prepared_sec_filing_rejects_malformed_or_unbound_metadata(modules, documents, mutation):
    prepared, artifact, companies, document = _filing_base(modules, documents)
    filing = document["filing"]
    if mutation == "extra-field":
        filing["private_note"] = "never copy"
    elif mutation == "missing-field":
        filing.pop("report_date")
    elif mutation == "wrong-source":
        document["source"] = "DART"
    elif mutation == "kr-issuer":
        next(row for row in companies if row["id"] == "KR:001111")["documents"].append(deepcopy(document))
    elif mutation == "wrong-id":
        document["id"] += "wrong"
    elif mutation == "wrong-url":
        document["url"] = document["url"].replace("/123/", "/456/")
    elif mutation == "wrong-form":
        filing["form"] = "arbitrary text"
    elif mutation == "wrong-amendment":
        filing["is_correction"] = False
    elif mutation == "wrong-cik":
        filing["cik"] = "456"
    elif mutation == "wrong-accession":
        filing["accession_number"] = "0000000001-25-000002"
    elif mutation == "future-filing":
        filing["filing_date"] = document["as_of"] = "2100-12-31"
    elif mutation == "report-after-filed":
        filing["report_date"] = "2025-03-13"
    elif mutation == "naive-acceptance":
        filing["acceptance_datetime"] = "2025-03-12T23:15:00"
    elif mutation == "oversize":
        filing["primary_document"] = "a" * 241
    elif mutation == "nested":
        filing["report_date"] = {"private_note": "never copy"}
    else:
        document["filing"] = None
    # Re-sign to exercise validation itself, not just the receipt digest guard.
    assert _decode_base(prepared, artifact, companies) is None
