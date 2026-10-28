"""Regression checks for the cold contract-fact document lookup."""
from __future__ import annotations

from copy import deepcopy
import importlib
from pathlib import Path
import sys
import types

import pytest

from tests.test_portfolio_contract_facts import _document, _parse


CORE = Path(__file__).resolve().parents[1] / "vercel-api" / "api" / "portfolio_core"


@pytest.fixture
def contract_facts(monkeypatch):
    package = types.ModuleType("contract_index_hotpath_test")
    package.__path__ = [str(CORE)]
    monkeypatch.setitem(sys.modules, package.__name__, package)
    module = importlib.import_module(package.__name__ + ".portfolio_contract_facts")
    yield module
    for name in tuple(sys.modules):
        if name == package.__name__ or name.startswith(package.__name__ + "."):
            monkeypatch.delitem(sys.modules, name, raising=False)


class CountedDocuments(list):
    def __init__(self, values):
        super().__init__(values)
        self.iterations = 0

    def __iter__(self):
        self.iterations += 1
        return super().__iter__()


def _bound_fact(receipt):
    fact = deepcopy(_parse())
    old_receipt = fact["receipt_no"]
    fact["receipt_no"] = receipt
    fact["source"]["main_url"] = fact["source"]["main_url"].replace(old_receipt, receipt)
    fact["source"]["viewer_url"] = fact["source"]["viewer_url"].replace(old_receipt, receipt)
    return fact


def test_valid_facts_scan_catalog_once_and_keep_all_exact_bindings(contract_facts):
    issuer = "KR:028050"
    company = {"id": issuer, "name": "삼성E&A"}
    facts, documents = [], []
    for index in range(12):
        receipt = f"20261029{index:06d}"
        fact = _bound_fact(receipt)
        facts.append(fact)
        wrong_binding = _document()
        wrong_binding.update(id="DART:" + receipt, url="https://dart.fss.or.kr/other", company_ids=[issuer])
        correct_binding = _document()
        correct_binding.update(id="DART:" + receipt,
                               url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + receipt,
                               company_ids=[issuer])
        documents.extend((wrong_binding, correct_binding))
    documents.extend({"id": f"OTHER:{index:06d}", "source": "DART"} for index in range(5000))
    counted = CountedDocuments(documents)

    coverage = contract_facts.attach_contract_facts(
        {"contract_facts": facts}, counted, [company]
    )

    # One pass clears stale fields; one builds the ID index. Facts then inspect
    # only the matching-ID bucket, not the full catalog per row.
    assert counted.iterations == 2
    assert coverage == {
        "input": 12, "accepted": 12, "rejected": 0, "unmatched": 0,
        "attached_documents": 12, "resolved_counterparties": 0,
        "verified_relationships": 0,
    }
    assert sum("contract_facts" in document for document in documents) == 12
    assert all("contract_facts" not in document for document in documents[::2])


def test_malformed_rows_and_unhashable_document_ids_keep_fail_closed_coverage(contract_facts):
    documents = [{"id": [], "source": "DART"}, {"id": {"nested": "value"}}]
    coverage = contract_facts.attach_contract_facts(
        {"contract_facts": [None, {}]}, documents, [{"id": "KR:028050", "name": "삼성E&A"}]
    )

    assert coverage == {
        "input": 2, "accepted": 0, "rejected": 2, "unmatched": 0,
        "attached_documents": 0, "resolved_counterparties": 0,
        "verified_relationships": 0,
    }
    assert documents == [{"id": [], "source": "DART"}, {"id": {"nested": "value"}}]
