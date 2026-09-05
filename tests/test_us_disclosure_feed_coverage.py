from __future__ import annotations

from datetime import datetime, timezone

from api.builders import us_disclosure_feed_builder as builder


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class _Session:
    def get(self, url, **_kwargs):
        if "0000000001" in url:
            return _Response({
                "filings": {
                    "recent": {
                        "form": ["8-K"],
                        "filingDate": ["2026-09-04"],
                        "primaryDocDescription": ["Current report"],
                        "primaryDocument": ["report.htm"],
                        "accessionNumber": ["0001-26-000001"],
                        "items": ["3.02, 8.01"],
                    }
                }
            })
        return _Response({"filings": {"recent": {"form": []}}})


def test_feed_reports_processed_empty_and_unresolved(monkeypatch, tmp_path):
    monkeypatch.setattr(builder, "_universe", lambda: ["AAA", "BBB", "CCC"])
    monkeypatch.setattr(builder, "_name_map", lambda: {"AAA": "Alpha"})
    monkeypatch.setattr(builder, "OUTPUT_PATH", str(tmp_path / "feed.json"))
    monkeypatch.setattr(builder, "MAX_SECONDS", 999)
    monkeypatch.setattr(builder, "_now_kst", lambda: datetime(2026, 9, 5, tzinfo=timezone.utc))
    monkeypatch.setattr(builder.time, "sleep", lambda _seconds: None)

    import requests
    from api.builders import us_insider_trades_public_builder as insider_builder

    monkeypatch.setattr(requests, "Session", _Session)
    monkeypatch.setattr(
        insider_builder,
        "_ticker_cik_map",
        lambda _session: {"AAA": "0000000001", "BBB": "0000000002"},
    )

    result = builder.build_feed(window_days=90)

    assert result["_meta"]["processed_n"] == 2
    assert result["_meta"]["unresolved_n"] == 1
    assert result["_coverage"]["processed_tickers"] == ["AAA", "BBB"]
    assert result["_coverage"]["unresolved_tickers"] == ["CCC"]
    assert [row["ticker"] for row in result["items"]] == ["AAA"]
    disclosure = result["items"][0]["disclosures"][0]
    assert disclosure["item_codes"] == ["3.02", "8.01"]
    assert disclosure["source_url"].endswith("/000126000001/report.htm")
