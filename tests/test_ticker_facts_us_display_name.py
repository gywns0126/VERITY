"""Offline ETF display-name fallback contract for local and Vercel layouts."""
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture(params=["api/intelligence/ticker_facts.py",
                       "vercel-api/api/operator_core/ticker_facts.py"])
def tf(request, monkeypatch):
    path = Path(__file__).resolve().parents[1] / request.param
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location("display_name_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "_load_local", lambda _: None)
    return mod


def test_local_name_wins_without_network(tf, monkeypatch):
    monkeypatch.setattr(tf, "_load_local", lambda _: {"names": {"VT": " 글로벌 주식 ETF "}})
    monkeypatch.setattr(tf, "_fetch_json", lambda *a, **k: pytest.fail("unneeded network"))
    assert tf._us_display_name("VT") == "글로벌 주식 ETF"


def test_missing_bundled_dictionary_reads_public_tracked_full_names(tf, monkeypatch, tmp_path):
    # Undo the fixture's _load_local stub to exercise the deployed filesystem path.
    path = Path(tf.__file__)
    spec = importlib.util.spec_from_file_location("display_name_deployed", path)
    deployed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(deployed)
    monkeypatch.setattr(deployed, "_ROOT", str(tmp_path))
    calls = []
    def fetch(url, cache_key):
        calls.append((url, cache_key))
        assert url == "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/us_etf_universe.json"
        assert cache_key == "public_local_us_etf_universe.json"
        return {"names": {"VT": "Vanguard Total World Stock ETF",
                          "JEPQ": "J.P. Morgan Nasdaq Equity Premium Income ETF"}}
    monkeypatch.setattr(deployed, "_fetch_json", fetch)
    assert deployed._us_display_name("VT") == "Vanguard Total World Stock ETF"
    assert deployed._us_display_name("JEPQ") == "J.P. Morgan Nasdaq Equity Premium Income ETF"
    assert len(calls) == 2


@pytest.mark.parametrize("ticker,name", [
    ("JEPQ", "JPMorgan Nasdaq Equity Premium "),
    ("VT", "Vanguard Total World Stock Inde"),
])
def test_public_name_uses_existing_join_cache(tf, monkeypatch, ticker, name):
    calls = []
    def fetch(url, cache_key):
        calls.append((url, cache_key))
        return {"etfs": [{"ticker": ticker, "name": name}]}
    monkeypatch.setattr(tf, "_fetch_json", fetch)
    assert tf._us_display_name(ticker) == name.strip()
    assert calls == [(f"{tf.BLOB}/us_etf.json", "us_etf.json")]


@pytest.mark.parametrize("doc", [None, [], {}, {"etfs": {}}, {"etfs": []},
    {"etfs": [{"ticker": "JEPQ", "name": " "}]},
    {"etfs": [{"ticker": "JEPQ", "name": "JEPQ"}]},
    {"etfs": [{"ticker": "JEPQ", "name": 123}]},
    {"etfs": [{"ticker": "JEPQX", "name": "Other fund"}]},
    {"etfs": [{"ticker": "JEPQ", "name": "First"},
              {"ticker": "JEPQ", "name": "Conflicting"}]},
    {"etfs": [{"ticker": "OTHER", "top_holdings": [{"ticker": "JEPQ", "name": "Nested"}]}]},
])
def test_empty_invalid_ambiguous_or_nonexact_rows_fail_closed(tf, monkeypatch, doc):
    monkeypatch.setattr(tf, "_fetch_json", lambda *a, **k: doc)
    assert tf._us_display_name("JEPQ") == ""


def test_duplicate_identical_names_are_not_ambiguous(tf, monkeypatch):
    monkeypatch.setattr(tf, "_fetch_json", lambda *a, **k: {"etfs": [
        {"ticker": "VT", "name": "Global fund"},
        {"ticker": "VT", "name": " Global fund "},
    ]})
    assert tf._us_display_name("VT") == "Global fund"


@pytest.mark.parametrize("query", ["", "JEPQ VT", "JEP*", "jepq", None])
def test_invalid_query_does_not_fetch(tf, monkeypatch, query):
    monkeypatch.setattr(tf, "_fetch_json", lambda *a, **k: pytest.fail("invalid lookup"))
    assert tf._us_display_name(query) == ""
