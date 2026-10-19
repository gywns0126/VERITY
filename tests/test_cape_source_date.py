"""CAPE dates must come from a matching dated source row, never fetch time."""
from types import SimpleNamespace

import pytest

from api.collectors import cape_multpl as C
from api.collectors import fred_macro as F


def table(day="Oct 16, 2026", value="40.54"):
    return (f'<table id="datatable"><tr><th>Date</th><th>Value</th></tr>'
            f'<tr class="odd"><td>{day}</td><td>&#x2002;\n{value}</td></tr>'
            '<tr><td>Oct 1, 2026</td><td>40.54</td></tr></table>')


def test_explicit_date_tied_to_current_value():
    assert C._source_date(table(), 40.54) == "2026-10-16"


@pytest.mark.parametrize("html", [
    '<div id="timestamp">4:00 PM EDT, Fri Oct 16</div>',
    table("Oct 16"), table("Feb 30, 2026"), table("Foo 16, 2026"),
    table(value="40.55"), table(value="bad"),
    table().replace('<td>&#x2002;\n40.54</td>', '', 1),
    table().replace('id="datatable"', 'id="other"'),
])
def test_missing_invalid_or_mismatched_date_stays_unknown(html):
    assert C._source_date(html, 40.54) is None


def test_single_fetch_preserves_receipt_and_source_date(monkeypatch):
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        return SimpleNamespace(status_code=200, text=(
            '<meta content="Current Shiller PE Ratio is 40.54, '
            'a change of -0.46 from previous market close.">' + table()))
    monkeypatch.setattr(C.requests, "get", get)
    result = C.fetch_cape()
    assert calls == [C.MULTPL_URL]
    assert result["value"] == 40.54 and result["change_from_prev_close"] == -0.46
    assert result["source_as_of"] == "2026-10-16"
    assert result["source_url"] == C.MULTPL_URL
    assert result["as_of"].endswith("+09:00")


@pytest.mark.parametrize("source_date,status", [
    ("2026-10-16", "ok"), (None, "missing"), ("2026-10-20", "invalid"),
])
def test_fred_uses_only_valid_source_day(monkeypatch, source_date, status):
    monkeypatch.setattr(F, "FRED_API_KEY", "offline-test")
    monkeypatch.setattr(F, "_fetch_series", lambda *args: [])
    monkeypatch.setattr(F, "now_iso", lambda: "2026-10-19T20:00:00+09:00")
    monkeypatch.setattr(C, "fetch_cape", lambda: {
        "value": 40.54, "as_of": "2026-10-19T19:59:59+09:00",
        "source_as_of": source_date,
    })
    row = F.get_fred_macro_block()["cape"]
    assert row["source_date_status"] == status
    assert row["source_as_of"] == (source_date if status == "ok" else None)
    assert row["stale"] is (status != "ok")
    assert row["fetched_at"] == "2026-10-19T20:00:00+09:00"
