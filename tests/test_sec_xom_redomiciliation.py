from __future__ import annotations

from api.collectors import sec_edgar


class _Response:
    status_code = 200
    headers = {"Content-Type": "application/json"}

    def __init__(self, payload=None, text=""):
        self._payload = payload
        self.text = text
        self.content = text.encode("utf-8")

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _submissions(cik: int, forms=(), *, dates=(), accessions=(), primary_docs=()):
    return {
        "cik": cik,
        "filings": {
            "recent": {
                "form": list(forms),
                "filingDate": list(dates),
                "accessionNumber": list(accessions),
                "primaryDocument": list(primary_docs),
            },
            "files": [],
        },
    }


def _properties_html():
    body = "Verified public filing property facts. " * 20
    return (
        "<html><body><p>Item 2. Properties</p><p>"
        + body
        + "</p><p>Item 3. Legal Proceedings</p></body></html>"
    )


def test_xom_redomiciliation_uses_predecessor_filing_and_preserves_its_identity(monkeypatch):
    current = _submissions(2115436, ("10-Q",), dates=("2026-11-02",),
                           accessions=("0002115436-26-000020",), primary_docs=("xom-20260930.htm",))
    predecessor = _submissions(34088, ("10-K",), dates=("2026-02-18",),
                               accessions=("0000034088-26-000045",),
                               primary_docs=("xom-20251231.htm",))
    responses = {
        "https://data.sec.gov/submissions/CIK0002115436.json": _Response(current),
        "https://data.sec.gov/submissions/CIK0000034088.json": _Response(predecessor),
        "https://www.sec.gov/Archives/edgar/data/34088/000003408826000045/xom-20251231.htm": _Response(text=_properties_html()),
    }
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        return responses[url]

    monkeypatch.setattr(sec_edgar, "_resolve_cik", lambda ticker, ua: "0002115436")
    monkeypatch.setattr(sec_edgar, "_throttle", lambda: None)
    monkeypatch.setattr(sec_edgar._SESSION, "get", fake_get)

    result = sec_edgar.fetch_10k_properties_section("XOM", "test-user-agent")

    assert result.get("error") is None
    assert result["accession"] == "0000034088-26-000045"
    assert result["filed_date"] == "2026-02-18"
    assert "/data/34088/" in result["url"]
    assert "/data/2115436/" not in result["url"]
    # The reader derives source:sec:<accession>; this must remain the accession
    # of the document actually fetched, never the successor CIK's 10-Q ID.
    assert "source:sec:" + result["accession"] == "source:sec:0000034088-26-000045"
    assert calls == [
        "https://data.sec.gov/submissions/CIK0002115436.json",
        "https://data.sec.gov/submissions/CIK0000034088.json",
        "https://www.sec.gov/Archives/edgar/data/34088/000003408826000045/xom-20251231.htm",
    ]


def test_xom_current_cik_10k_is_preferred_without_predecessor_lookup(monkeypatch):
    current = _submissions(2115436, ("10-K",), dates=("2027-02-17",),
                           accessions=("0002115436-27-000010",), primary_docs=("xom-20261231.htm",))
    doc_url = "https://www.sec.gov/Archives/edgar/data/2115436/000211543627000010/xom-20261231.htm"
    responses = {
        "https://data.sec.gov/submissions/CIK0002115436.json": _Response(current),
        doc_url: _Response(text=_properties_html()),
    }
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        return responses[url]

    monkeypatch.setattr(sec_edgar, "_resolve_cik", lambda ticker, ua: "0002115436")
    monkeypatch.setattr(sec_edgar, "_throttle", lambda: None)
    monkeypatch.setattr(sec_edgar._SESSION, "get", fake_get)

    result = sec_edgar.fetch_10k_properties_section("XOM", "test-user-agent")

    assert result["accession"] == "0002115436-27-000010"
    assert result["filed_date"] == "2027-02-17"
    assert calls == ["https://data.sec.gov/submissions/CIK0002115436.json", doc_url]


def test_predecessor_fallback_is_not_used_for_other_tickers(monkeypatch):
    current = _submissions(123, ("10-Q",), dates=("2026-11-02",),
                           accessions=("0000000123-26-000020",), primary_docs=("issuer-20260930.htm",))
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        return _Response(current)

    monkeypatch.setattr(sec_edgar, "_resolve_cik", lambda ticker, ua: "0000000123")
    monkeypatch.setattr(sec_edgar, "_throttle", lambda: None)
    monkeypatch.setattr(sec_edgar._SESSION, "get", fake_get)

    result = sec_edgar.fetch_10k_properties_section("ABC", "test-user-agent")

    assert result == {"error": "no_10k"}
    assert calls == ["https://data.sec.gov/submissions/CIK0000000123.json"]


def test_predecessor_cik_identity_must_match_before_archive_fetch(monkeypatch):
    current = _submissions(2115436, ("10-Q",))
    wrong_predecessor = _submissions(999, ("10-K",), dates=("2026-02-18",),
                                     accessions=("0000000999-26-000045",),
                                     primary_docs=("not-xom.htm",))
    responses = {
        "https://data.sec.gov/submissions/CIK0002115436.json": _Response(current),
        "https://data.sec.gov/submissions/CIK0000034088.json": _Response(wrong_predecessor),
    }
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        return responses[url]

    monkeypatch.setattr(sec_edgar, "_resolve_cik", lambda ticker, ua: "0002115436")
    monkeypatch.setattr(sec_edgar, "_throttle", lambda: None)
    monkeypatch.setattr(sec_edgar._SESSION, "get", fake_get)

    result = sec_edgar.fetch_10k_properties_section("XOM", "test-user-agent")

    assert result == {"error": "predecessor_identity_mismatch"}
    assert len(calls) == 2
