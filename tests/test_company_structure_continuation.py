"""Fail-closed tests for issuer-bound unheaded SEC table continuations."""

import gzip
import hashlib
import json
import os
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from api.intelligence.company_structure_sec_sections import parse_unheaded_continuation


def _table(rows):
    return "<table>" + "".join(
        "<tr><td colspan='3'>" + name + "</td><td colspan='3'></td>"
        "<td colspan='3'>" + jurisdiction + "</td></tr>"
        for name, jurisdiction in rows
    ) + "</table>"


def _html(*, title="Subsidiaries of Example Corporation", first=None, second=None,
          between="", after=""):
    first = first if first is not None else [
        ("NAME OF SUBSIDIARY OR ORGANIZATION", "STATE OF INCORPORATION OR FORMATION"),
        ("Alpha Holdings LLC", "Delaware"),
    ]
    second = second if second is not None else [("Beta Services Inc.", "California")]
    return "<html><body><p>Exhibit 21.1</p><p>" + title + "</p>" + _table(first) + between + _table(second) + after + "</body></html>"


def _parse(html, *, issuer="Example Corp", period="2025-12-31"):
    result = {"status": "needs-review", "rows": [], "periodEnd": period,
              "reviewReason": "unreviewed-exhibit-table"}
    return parse_unheaded_continuation(
        BeautifulSoup(html, "html.parser"), {"issuerName": issuer}, result
    )


def test_two_physical_pages_have_one_exact_header_and_no_inferred_date():
    result = _parse(_html(title="Subsidiaries of Example Corporation"))
    assert result["status"] == "parsed"
    assert [(r["name"], r["jurisdiction"], r["sourceRow"]["tableIndex"])
            for r in result["rows"]] == [
        ("Alpha Holdings LLC", "Delaware", 0),
        ("Beta Services Inc.", "California", 1),
    ]
    assert all(r["ownershipPct"] is None and r["directOwnership"] == "unspecified"
               for r in result["rows"])
    assert "statedAsOf" not in result


def test_exact_date_and_identical_repeated_header_are_allowed():
    second = [("NAME OF SUBSIDIARY OR ORGANIZATION", "STATE OF INCORPORATION OR FORMATION"),
              ("Beta Services Inc.", "California")]
    result = _parse(_html(title="Subsidiaries of Example Corp as of December 31, 2025",
                          second=second))
    assert result["status"] == "parsed"
    assert len(result["rows"]) == 2


@pytest.mark.parametrize("change", [
    {"title": "Subsidiaries of Other Corp"},
    {"title": "Subsidiaries of Example Corp as of December 30, 2025"},
    {"between": "<p>Subsidiaries of Another Parent</p>"},
    {"between": "<p>As of December 30, 2025</p>"},
    {"after": "<p>Some subsidiaries omitted.</p>"},
    {"after": "<p>Parent: Alpha Holdings LLC</p>"},
    {"after": "<img alt='Gamma Holdings LLC'>"},
    {"second": [("Beta Services Inc. (25%)", "California")]},
    {"second": [("Beta Services Inc. d/b/a Beta", "California")]},
    {"second": [("Beta VIE LLC", "California")]},
    {"second": [("Beta Trust", "California")]},
    {"second": [("Beta Services Inc.", "")]},
    {"second": [("Subsidiary", "Country"), ("Beta Services Inc.", "California")]},
    {"second": [("Alpha Holdings LLC", "Delaware")]},
])
def test_any_scope_or_row_ambiguity_holds_all_rows(change):
    result = _parse(_html(**change))
    assert result is not None
    assert result["status"] == "needs-review"
    assert result["rows"] == []


@pytest.mark.parametrize("mutator", [
    lambda html: html.replace("<td colspan='3'></td>", "<td colspan='3'>ownership</td>", 1),
    lambda html: html.replace("<td colspan='3'></td>", "<td colspan='3'>hidden continuation</td>", 1),
    lambda html: html.replace("<td colspan='3'></td>", "<td colspan='2'></td>", 1),
    lambda html: html.replace("Beta Services Inc.</td>", "Beta<br>Services Inc.</td>"),
    lambda html: html.replace("<table>", "<table><caption>Other entities</caption>", 1),
    lambda html: html.replace("<table>", "<table><td>orphan entity</td>", 1),
    lambda html: html.replace("</table><table>", "</table><table><tr><td>unexpected</td></tr>"),
])
def test_nonblank_unmatched_physical_content_is_never_omitted(mutator):
    result = _parse(mutator(_html()))
    assert result["status"] == "needs-review"
    assert result["rows"] == []


_evidence_dir = os.environ.get("COFILER_AUDIT_EVIDENCE_DIR")
EVIDENCE_DIR = Path(_evidence_dir) if _evidence_dir else None
_REAL = [
    ("KRC", "15f5294b4eb0324512b35de93496d68d0566f67334ac5db23a401df63c664d2a", 78,
     "96da3aecfc96bcde9cc69d78d24b9cef2066f10910e3a041858b0e7a0044f5c9"),
    ("CMPR", "68d9cbfadd4b518dda4acebdbcb706d0ef29fd8cdf9fa71fcaf68a473745d62e", 52,
     "fe9cf5641aafb35196ffe671932c334b648c52b9277454bb423f7cc675e090e9"),
]


@pytest.mark.parametrize("ticker,sha,count,pair_sha", _REAL)
def test_cached_original_entire_pair_sequence(ticker, sha, count, pair_sha):
    if EVIDENCE_DIR is None or not EVIDENCE_DIR.is_dir():
        pytest.skip("Set COFILER_AUDIT_EVIDENCE_DIR to the preserved replay evidence directory")
    path = EVIDENCE_DIR / "raw-cache" / (sha + ".gz")
    ledger = EVIDENCE_DIR / "held-common-cause-replay-v18-accepted-20261025.json"
    assert path.exists() and ledger.exists()
    raw = gzip.open(path, "rb").read()
    assert hashlib.sha256(raw).hexdigest() == sha
    entry = next(row for row in json.loads(ledger.read_text())["rows"]
                 if ticker in row["tickers"])
    meta = entry["filingMetadata"]
    result = parse_unheaded_continuation(
        BeautifulSoup(raw, "html.parser"),
        {"issuerName": meta["issuer_name"]},
        {"status": "needs-review", "rows": [], "periodEnd": meta["period_end"],
         "reviewReason": "unreviewed-exhibit-table"},
    )
    assert result["status"] == "parsed"
    assert len(result["rows"]) == count
    pairs = [(row["name"], row["jurisdiction"]) for row in result["rows"]]
    assert hashlib.sha256(json.dumps(pairs, ensure_ascii=False).encode()).hexdigest() == pair_sha
    assert {row["sourceRow"]["tableIndex"] for row in result["rows"]} == {0, 1}


@pytest.mark.parametrize("ticker,sha", [
    ("PII", "0e52778fc67000f1939c73639f726260faa77445754b5e52bfc04fbdd0639a98"),
    ("DIN", "f7801c6a66d2f83ab19783c393640976ac36c61dd19ed1d18c4f38cbd2281a55"),
    ("TNET", "989fb2d68ca818b2ec370d07a5d553d678b00031f1516f7b13e6cfd713abae56"),
])
def test_cached_adverse_originals_never_drop_valid_rows(ticker, sha):
    if EVIDENCE_DIR is None or not EVIDENCE_DIR.is_dir():
        pytest.skip("Set COFILER_AUDIT_EVIDENCE_DIR to the preserved replay evidence directory")
    path = EVIDENCE_DIR / "raw-cache" / (sha + ".gz")
    ledger = EVIDENCE_DIR / "held-common-cause-replay-v18-accepted-20261025.json"
    assert path.exists() and ledger.exists()
    raw = gzip.open(path, "rb").read()
    assert hashlib.sha256(raw).hexdigest() == sha
    entry = next(row for row in json.loads(ledger.read_text())["rows"]
                 if ticker in row["tickers"])
    meta = entry["filingMetadata"]
    result = parse_unheaded_continuation(
        BeautifulSoup(raw, "html.parser"),
        {"issuerName": meta["issuer_name"]},
        {"status": "needs-review", "rows": [], "periodEnd": meta["period_end"],
         "reviewReason": "unreviewed-exhibit-table"},
    )
    if ticker == "TNET":
        # The source splits "Exhibit" and "21.1" into separate visible blocks;
        # this helper deliberately does not claim that title layout.
        assert result is None
    else:
        assert result is not None
        assert result["status"] == "needs-review"
        assert result["rows"] == []
