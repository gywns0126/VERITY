"""Exact pre-bucket lineage semantics, using synthetic public documents only."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
import types

import pytest


CORE = Path(__file__).resolve().parents[1] / "vercel-api/api/portfolio_core"


@pytest.fixture
def lineage(monkeypatch):
    package = types.ModuleType("lineage_hotpath_test")
    package.__path__ = [str(CORE)]
    monkeypatch.setitem(sys.modules, package.__name__, package)
    module = importlib.import_module(package.__name__ + ".portfolio_event_lineage")
    yield module
    for name in tuple(sys.modules):
        if name == package.__name__ or name.startswith(package.__name__ + "."):
            monkeypatch.delitem(sys.modules, name, raising=False)


def _reference(module, artifact, document_list, company_catalog):
    """Frozen pre-change attach_event_lineage body; independent full-list lookup."""
    validate_family, _name, _contract_title = module.validate_family, module._name, module._contract_title
    for doc in document_list:
        doc.pop("event_lineage", None)
    rows = artifact.get("documentFamilies", []) if isinstance(artifact, dict) else []
    coverage = {"input": len(rows) if isinstance(rows, list) else 0, "accepted": 0,
                "rejected": 0, "unmatched": 0, "attached_documents": 0, "families": 0,
                "verified_economic_events": 0}
    if not isinstance(rows, list) or len(rows) > 1000:
        coverage.update(rejected=coverage["input"], shape_errors=1)
        return coverage
    by_id = {c["id"]: c for c in company_catalog}
    names = {}
    for c in company_catalog:
        for name in c.get("source_names", [c["name"]]):
            names.setdefault(_name(name), set()).add(c["id"])
    staged = {}
    for row in rows:
        try:
            validate_family(row)
            issuer = row["issuer_id"]
            if issuer not in by_id or names.get(_name(row["issuer_name"])) != {issuer}:
                raise ValueError("unresolved-issuer")
        except (TypeError, ValueError, KeyError):
            coverage["rejected"] += 1
            continue
        member = next(m for m in row["members"] if m["receipt_no"] == row["receipt_no"])
        matched = [d for d in document_list if d["id"] == "DART:" + row["receipt_no"]
                   and d["url"] == row["url"] and d["source"] == "DART" and d["kind"] == "disclosure"
                   and d["company_ids"] == [issuer] and d["as_of"] == member["published_on"]
                   and _contract_title(d["title"]) == _contract_title(member["title"])
                   and ("정정" in d["title"]) == member["amendment"]]
        if not matched:
            coverage["unmatched"] += 1
            continue
        coverage["accepted"] += 1
        original = next(m for m in row["members"] if not m["amendment"])
        lineage = {"id": f"dart-family:{row['corp_code']}:{original['receipt_no']}",
            "kind": "official-dart-document-family", "issuer_id": issuer,
            "root_receipt": original["receipt_no"], "current_receipt": row["receipt_no"],
            "verified_common_event": False, "current_economic_status": "unverified",
            "members": deepcopy(row["members"])}
        staged.setdefault(matched[0]["id"], []).append((matched[0], lineage))
    families = set()
    for entries in staged.values():
        if any(lineage != entries[0][1] for _, lineage in entries):
            coverage["rejected"] += len(entries)
            coverage["accepted"] -= len(entries)
            continue
        doc, lineage = entries[0]
        doc["event_lineage"] = lineage
        coverage["attached_documents"] += 1
        families.add(lineage["id"])
    coverage["families"] = len(families)
    return coverage


def _case(number=1):
    receipt = f"20260318{number:06d}"
    title = "단일판매ㆍ공급계약체결"
    row = {"issuer_id": "KR:001111", "issuer_name": "합성제조사", "corp_code": "00000001",
        "receipt_no": receipt, "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + receipt,
        "observed_at": "2026-03-19T00:00:00Z", "content_sha256": "a" * 64,
        "members": [{"receipt_no": receipt, "title": title,
                     "published_on": "2026-03-18", "amendment": False}]}
    document = {"id": "DART:" + receipt, "url": row["url"], "source": "DART",
        "kind": "disclosure", "company_ids": [row["issuer_id"]], "as_of": "2026-03-18",
        "title": title, "event_lineage": {"stale": True}}
    catalog = [{"id": row["issuer_id"], "name": row["issuer_name"]}]
    return row, document, catalog


def _bytes(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False).encode()


def _compare(module, artifact, documents, catalog):
    original_artifact, original_catalog = _bytes(artifact), _bytes(catalog)
    legacy, actual = deepcopy(documents), deepcopy(documents)
    expected = _reference(module, artifact, legacy, catalog)
    coverage = module.attach_event_lineage(artifact, actual, catalog)
    assert _bytes([actual, coverage]) == _bytes([legacy, expected])
    assert _bytes(artifact) == original_artifact
    assert _bytes(catalog) == original_catalog
    return actual, coverage


@pytest.mark.parametrize("mode", ["normal", "duplicate_documents", "first_wrong", "duplicate_families",
    "conflicting_families", "conflicting_issuers", "non_string_ids", "unmatched", "ambiguous_alias", "legal_alias",
    "correction", "invalid_family"])
def test_output_and_coverage_match_original(lineage, mode):
    row, document, catalog = _case()
    artifact, documents = {"documentFamilies": [row]}, [document]
    if mode == "duplicate_documents":
        documents.append(deepcopy(document))
    elif mode == "first_wrong":
        documents.insert(0, {**document, "url": "https://dart.fss.or.kr/wrong"})
    elif mode == "duplicate_families":
        artifact["documentFamilies"].append(deepcopy(row))
    elif mode == "conflicting_families":
        artifact["documentFamilies"].append({**deepcopy(row), "corp_code": "00000002"})
    elif mode == "conflicting_issuers":
        artifact["documentFamilies"].append({**deepcopy(row), "corp_code": "00000002",
            "issuer_id": "KR:002222", "issuer_name": "다른회사"})
        catalog.append({"id": "KR:002222", "name": "다른회사"})
        documents.append({**deepcopy(document), "company_ids": ["KR:002222"]})
    elif mode == "non_string_ids":
        documents[:0] = [{"id": []}, {"id": {}}, {"id": None}, {"id": 123}]
    elif mode == "unmatched":
        documents[0]["id"] = "DART:20260318000002"
    elif mode == "ambiguous_alias":
        catalog.append({"id": "KR:002222", "name": row["issuer_name"]})
    elif mode == "legal_alias":
        catalog[0].update(name="합성회사", source_names=["합성회사", row["issuer_name"]])
    elif mode == "correction":
        row["members"].insert(0, {**row["members"][0], "receipt_no": "20260317000001",
                                "published_on": "2026-03-17"})
        row["members"][-1]["amendment"] = True
        document["title"] = "[정정]" + document["title"]
    elif mode == "invalid_family":
        row["issuer_name"] = "person@example.com"
    actual, coverage = _compare(lineage, artifact, documents, catalog)
    if mode == "duplicate_documents":
        assert "event_lineage" in actual[0] and "event_lineage" not in actual[1]
    elif mode == "first_wrong":
        assert "event_lineage" not in actual[0] and "event_lineage" in actual[1]
    elif mode in ("conflicting_families", "conflicting_issuers"):
        assert coverage["accepted"] == 0 and coverage["rejected"] == 2
        assert "event_lineage" not in actual[0]
    elif mode == "duplicate_families":
        assert coverage["accepted"] == 2 and coverage["attached_documents"] == 1


@pytest.mark.parametrize("key,value", [("id", "DART:20260318000002"), ("url", "https://dart.fss.or.kr/wrong"),
    ("source", "SEC"), ("kind", "report"), ("company_ids", ["KR:002222"]),
    ("company_ids", ["KR:001111", "KR:002222"]), ("as_of", "2026-03-17"),
    ("title", "다른공시"), ("title", "[정정]단일판매ㆍ공급계약체결")])
def test_exact_source_checks_remain_required(lineage, key, value):
    row, document, catalog = _case()
    document[key] = value
    actual, coverage = _compare(lineage, {"documentFamilies": [row]}, [document], catalog)
    assert coverage["unmatched"] == 1 and coverage["attached_documents"] == 0
    assert "event_lineage" not in actual[0]


@pytest.mark.parametrize("rows", [None, [], [None, {}], [{}] * 1001])
def test_rejected_families_never_require_document_ids(lineage, rows):
    _compare(lineage, {"documentFamilies": rows}, [{"event_lineage": {"stale": True}}], [])


def test_document_members_are_isolated_from_source_and_next_call(lineage):
    row, document, catalog = _case()
    artifact = {"documentFamilies": [row]}
    first, _ = _compare(lineage, artifact, [document], catalog)
    first[0]["event_lineage"]["members"][0]["title"] = "local edit"
    second, _ = _compare(lineage, artifact, [document], catalog)
    assert second[0]["event_lineage"]["members"][0]["title"] == document["title"]


def test_many_families_use_one_document_bucket_pass(lineage):
    class CountedDocuments(list):
        iterations = 0

        def __iter__(self):
            self.iterations += 1
            return super().__iter__()

    rows, documents = [], []
    for number in range(1, 13):
        row, document, catalog = _case(number)
        rows.append(row)
        documents.append(document)
    documents += [{"id": f"OTHER:{number}"} for number in range(5000)]
    counted = CountedDocuments(documents)
    coverage = lineage.attach_event_lineage({"documentFamilies": rows}, counted, catalog)
    assert counted.iterations == 2  # Clear stale fields, then build buckets once.
    assert coverage["accepted"] == 12 and coverage["attached_documents"] == 12
