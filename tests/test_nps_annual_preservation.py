"""A dated annual cohort cannot regress when an old CSV remains on disk."""
import json
from types import SimpleNamespace

import pytest
from api.collectors import nps_history, nps_holdings


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    import requests
    monkeypatch.setattr(requests.sessions.Session, "request",
                        lambda *a, **k: pytest.fail("network forbidden"))


def _seed(asof="2025-12-31", count=101):
    rows = [{"ticker": f"{i:06d}", "name": f"검증 기업 {i}", "as_of": asof,
             "pct": 7, "eval_amt_100m": count + 1000 - i} for i in range(1, count + 1)]
    return {"schema_version": 1, "as_of": asof, "full_n": count, "full": rows,
            "source": {"url": "https://officialfund.nps.or.kr/annual/domestic", "rows": count}}


def _invalid_seed(kind):
    seed = _seed()
    if kind == "mixed_year":
        seed["full"][0]["as_of"] = "2024-12-31"
    elif kind == "header_date":
        seed["as_of"] = "2024-12-31"
    elif kind == "nonannual":
        seed["as_of"] = "2025-06-30"
        for row in seed["full"]:
            row["as_of"] = seed["as_of"]
    elif kind == "full_count":
        seed["full_n"] += 1
    elif kind == "source_count":
        seed["source"]["rows"] -= 1
    elif kind == "schema":
        seed["schema_version"] = True
    elif kind in ("nan", "infinity", "negative", "missing_value"):
        seed["full"][0]["eval_amt_100m"] = {"nan": "NaN", "infinity": "Infinity",
                                                   "negative": -1, "missing_value": None}[kind]
    elif kind == "duplicate_name":
        seed["full"][1]["name"] = seed["full"][0]["name"]
    elif kind == "duplicate_ticker":
        seed["full"][1]["ticker"] = seed["full"][0]["ticker"]
    elif kind == "source_url":
        seed["source"]["url"] = "https://officialfund.nps.or.kr.example.com/annual"
    elif kind == "top100":
        seed = _seed(count=99)
    elif kind == "missing_name":
        seed["full"][0]["name"] = None
    return seed


INVALID_KINDS = ["mixed_year", "header_date", "nonannual", "full_count", "source_count",
                 "schema", "nan", "infinity", "negative", "missing_value", "duplicate_name",
                 "duplicate_ticker", "source_url", "top100", "missing_name"]


@pytest.mark.parametrize("kind", INVALID_KINDS)
def test_invalid_seed_is_none_by_default_and_strictly_rejected(tmp_path, kind):
    path = tmp_path / "annual.json"
    path.write_text(json.dumps(_invalid_seed(kind)))
    before = path.read_bytes()
    assert nps_history.read_annual_seed(path) is None
    with pytest.raises(ValueError, match="invalid annual seed"):
        nps_history.read_annual_seed(path, strict=True)
    assert path.read_bytes() == before


def test_valid_seed_ranks_all_source_rows_before_mapping(tmp_path):
    seed = _seed(count=1206)
    seed["full"][0]["ticker"] = None
    for row in seed["full"][1:3]:
        row["security_type"] = "preferred"
    path = tmp_path / "annual.json"
    path.write_text(json.dumps(seed))
    assert nps_history.read_annual_seed(path, strict=True) == seed
    out = nps_history.build_history(seed["full"], cache={})
    assert out["selection"]["as_of"] == "2025-12-31"
    assert out["selection"]["annual_input_n"] == 1206
    assert out["coverage"]["selected_count"] == 100
    assert out["selection"]["target_n"] == 99
    assert out["selection"]["annual_top100_unmatched_rows"][0]["rank"] == 1
    assert not any(stock["ticker"] == "000101" for stock in out["stocks"])
    assert out["stocks"][0]["security_type"] == "preferred"
    assert out["stocks"][0]["missing_reason"] == "corp_code_missing"


def _isolate_builder(tmp_path, monkeypatch, previous):
    source = tmp_path / "nps_holdings.json"
    source.write_text(json.dumps(previous))
    monkeypatch.setattr(nps_holdings, "_ROOT", str(tmp_path))
    monkeypatch.setattr(nps_holdings, "OUTPUT_PATH", str(source))
    monkeypatch.setattr(nps_holdings, "ANNUAL_SEED_PATH", str(tmp_path / "annual.json"))
    monkeypatch.setattr(nps_holdings, "NAMES_PATH", str(tmp_path / "names.json"))
    monkeypatch.setattr(nps_holdings, "FUND_OVERVIEW_PATH", str(tmp_path / "fund.json"))
    for name in ("_from_data_go_kr", "_from_major_csv", "_from_previous_live", "_from_dart_existing"):
        monkeypatch.setattr(nps_holdings, name, lambda *_: {})
    for name in ("_from_full_overseas", "_asset_mix"):
        monkeypatch.setattr(nps_holdings, name, lambda *_: [])
    monkeypatch.setattr(nps_holdings, "_from_dart_live", lambda *_: ({}, set(), {}))
    monkeypatch.setattr(nps_history, "CACHE_PATH", tmp_path / "absent-cache.json")
    return source


def _csv(tmp_path, asof, count=2):
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    (data / "nps_full_holdings.csv").write_text(
        "종목명,지분율,평가액,기준일\n"
        f"미매칭 원문 최상위,7,99999,{asof}\n검증 기업,7,100,{asof}\n" +
        "".join(f"원문 기업 {i},7,{102 - i},{asof}\n" for i in range(3, count + 1)))


def test_local_seed_wins_over_older_csv_without_mapping_or_annual_requests(tmp_path, monkeypatch):
    seed = _seed(count=1206)
    source = _isolate_builder(tmp_path, monkeypatch, {"full": _seed("2024-12-31")["full"]})
    seed_path = tmp_path / "annual.json"
    seed_path.write_text(json.dumps(seed))
    _csv(tmp_path, "2024-12-31")
    before = source.read_bytes()
    out = nps_holdings.build_nps_holdings()
    assert out["full"] == seed["full"] and out["full_n"] == 1206
    assert out["detail_history"]["selection"]["as_of"] == "2025-12-31"
    assert source.read_bytes() == before


def test_newer_csv_is_allowed_and_preserves_unmapped_raw_slot(tmp_path, monkeypatch):
    _isolate_builder(tmp_path, monkeypatch, {})
    (tmp_path / "annual.json").write_text(json.dumps(_seed()))
    _csv(tmp_path, "2026-12-31", count=101)
    rows = nps_holdings._from_full_list({"검증기업": "000001"})
    assert len(rows) == 101 and rows[0]["ticker"] is None
    assert nps_history.annual_cohort_as_of(rows) == "2026-12-31"
    targets, selection = nps_history.select_top100(rows)
    assert selection["annual_top100_unmatched_rows"][0]["rank"] == 1
    assert targets[0]["rank"] == 2


@pytest.mark.parametrize("kind", ["missing", "invalid", "401"])
def test_seed_missing_invalid_or_api_401_retains_published_last_good(tmp_path, monkeypatch, kind):
    newest = _seed()["full"]
    source = _isolate_builder(tmp_path, monkeypatch, {"full": newest, "full_n": len(newest)})
    if kind == "invalid":
        (tmp_path / "annual.json").write_text(json.dumps(_invalid_seed("nan")))
        _csv(tmp_path, "2024-12-31")
    elif kind == "401":
        import requests
        monkeypatch.setattr("api.config.PUBLIC_DATA_API_KEY", "fake")
        monkeypatch.setattr(requests, "get", lambda url, **kwargs: SimpleNamespace(
            status_code=401, json=lambda: {"paths": {"/3070507/v1/annual": {}}}
            if url == nps_holdings.FULL_OAS else {}))
    else:
        monkeypatch.setattr(nps_holdings, "_from_full_list", lambda *_: [])
    before = source.read_bytes()
    out = nps_holdings.build_nps_holdings()
    assert out["full"] == newest and out["full_n"] == len(newest)
    assert out["detail_history"]["selection"]["annual_input_status"] == "last_good"
    assert source.read_bytes() == before


@pytest.mark.parametrize("kind", ["nan", "partial", "mixed_year", "duplicate_name"])
def test_invalid_newer_candidate_cannot_replace_last_good(tmp_path, monkeypatch, kind):
    previous = _seed()["full"]
    _isolate_builder(tmp_path, monkeypatch, {"full": previous})
    malformed = _seed("2026-12-31")["full"]
    if kind == "nan":
        malformed[0]["eval_amt_100m"] = "NaN"
    elif kind == "partial":
        malformed = malformed[:99]
    elif kind == "mixed_year":
        malformed[0]["as_of"] = "2025-12-31"
    elif kind == "duplicate_name":
        malformed[0]["name"] = malformed[1]["name"]
    monkeypatch.setattr(nps_holdings, "_from_full_list", lambda *_: malformed)
    assert nps_holdings.build_nps_holdings()["full"] == previous


def test_invalid_seed_without_published_cohort_uses_existing_csv(tmp_path, monkeypatch):
    _isolate_builder(tmp_path, monkeypatch, {})
    (tmp_path / "annual.json").write_text(json.dumps(_invalid_seed("source_count")))
    _csv(tmp_path, "2024-12-31", count=101)
    out = nps_holdings.build_nps_holdings()
    assert out["full_n"] == 101 and out["full"][0]["ticker"] is None
    assert out["detail_history"]["selection"]["as_of"] == "2024-12-31"
    assert out["detail_history"]["coverage"]["selected_count"] == 100


@pytest.mark.parametrize("seed_date,payload_date,use_seed", [
    ("2025-12-31", "2024-12-31", True), ("2025-12-31", "2025-12-31", True),
    ("2024-12-31", "2025-12-31", False),
])
def test_cli_annual_input_only_replaces_full_keys_without_date_downgrade(
    tmp_path, seed_date, payload_date, use_seed
):
    seed = _seed(seed_date)
    payload = {"full": _seed(payload_date, count=102)["full"], "full_n": 102,
               "generated_at": "original", "holdings": [{"ticker": "000001"}],
               "fund": {"unknown": "retain"}, "source": "original source", "future_key": [1, 2]}
    source, annual, output, cache = [tmp_path / name for name in ("in.json", "annual.json", "out.json", "cache.json")]
    source.write_text(json.dumps(payload))
    annual.write_text(json.dumps(seed))
    before = source.read_bytes()
    assert nps_history.main(["--input", str(source), "--annual-input", str(annual),
                             "--output", str(output), "--cache", str(cache)]) == 0
    result = json.loads(output.read_text())
    assert result["full"] == (seed["full"] if use_seed else payload["full"])
    assert result["full_n"] == (101 if use_seed else 102)
    assert {k: v for k, v in result.items() if k not in ("full", "full_n", "detail_history")} == {
        k: v for k, v in payload.items() if k not in ("full", "full_n")}
    assert result["detail_history"]["selection"]["as_of"] == max(seed_date, payload_date)
    assert source.read_bytes() == before and not cache.exists()


@pytest.mark.parametrize("kind", INVALID_KINDS + ["missing", "broken"])
def test_cli_explicit_invalid_seed_fails_before_collection_or_output_mutation(tmp_path, monkeypatch, kind):
    source, annual, output, cache = [tmp_path / name for name in ("in.json", "annual.json", "out.json", "cache.json")]
    source.write_text(json.dumps({"full": _seed()["full"], "full_n": 101}))
    output.write_text("last-good output")
    cache.write_text("last-good cache")
    if kind == "broken":
        annual.write_text("broken seed")
    elif kind != "missing":
        annual.write_text(json.dumps(_invalid_seed(kind)))
    before = [path.read_bytes() for path in (source, output, cache)]
    monkeypatch.setattr(nps_history, "collect_history", lambda *a, **k: pytest.fail("no collection"))
    assert nps_history.main(["--input", str(source), "--annual-input", str(annual), "--output", str(output),
                             "--cache", str(cache), "--collect"]) == 1
    assert [path.read_bytes() for path in (source, output, cache)] == before


def test_cli_annual_input_collection_budget_and_failed_refresh_preserve_last_good(tmp_path, monkeypatch):
    seed = _seed()
    raw = {"repror": "국민연금공단", "corp_code": "00126380", "rcept_no": "20260101000001",
           "rcept_dt": "20260101", "stkqy": "100", "stkrt": "7", "stkqy_irds": "-1"}
    stored = {"entries": {"000001": {"raw_rows": [raw], "last_status": "ok",
                                      "collected_at": "2026-01-02T00:00:00+00:00",
                                      "last_good_at": "2026-01-02T00:00:00+00:00"}}}
    source, annual, output, cache = [tmp_path / name for name in ("in.json", "annual.json", "out.json", "cache.json")]
    source.write_text(json.dumps({"full": _seed("2024-12-31")["full"], "other": "retain"}))
    annual.write_text(json.dumps(seed))
    cache.write_text(json.dumps(stored))
    calls = []
    session = SimpleNamespace(get=lambda *a, **k: calls.append(a) or SimpleNamespace(
        status_code=200, json=lambda: {"status": "013"}))
    collect = nps_history.collect_history
    def bounded(rows, **kwargs):
        return collect(rows, **kwargs, api_key="fake", session=session, corp_resolver=lambda _: "00126380")
    monkeypatch.setattr(nps_history, "collect_history", bounded)
    assert nps_history.main(["--input", str(source), "--annual-input", str(annual), "--output", str(output),
                             "--cache", str(cache), "--collect", "--maxcalls", "1", "--ttl-hours", "168", "--resume"]) == 0
    result = json.loads(output.read_text())
    assert len(calls) == result["detail_history"]["last_collection_run"]["calls"] == 1
    stock = result["detail_history"]["stocks"][0]
    assert stock["events"][0]["raw_rows"] == [raw] and stock["status"] == "stale"
    assert stock["last_success_at"] == "2026-01-02T00:00:00+00:00"
    assert stock["missing_reason"] == "empty_response" and result["other"] == "retain"
    assert json.loads(cache.read_text())["entries"]["000001"]["raw_rows"] == [raw]


def test_older_annual_source_cannot_roll_back_newer_published_cohort(tmp_path, monkeypatch):
    newest = [{"ticker":"005930","name":"검증 기업","as_of":"2025-12-31","pct":7,"eval_amt_100m":100}]
    source = tmp_path / "nps_holdings.json"
    source.write_text(json.dumps({"full":newest}))
    monkeypatch.setattr(nps_holdings,"OUTPUT_PATH",str(source))
    monkeypatch.setattr(nps_holdings,"NAMES_PATH",str(tmp_path/"names.json"))
    monkeypatch.setattr(nps_holdings,"FUND_OVERVIEW_PATH",str(tmp_path/"fund.json"))
    for name in ["_from_data_go_kr","_from_major_csv","_from_previous_live","_from_dart_existing"]:
        monkeypatch.setattr(nps_holdings,name,lambda *_: {})
    for name in ["_from_full_overseas","_asset_mix"]:
        monkeypatch.setattr(nps_holdings,name,lambda *_: [])
    monkeypatch.setattr(nps_holdings,"_from_dart_live",lambda *_: ({},set(),{}))
    monkeypatch.setattr(nps_holdings,"_from_full_list",lambda *_: [{**newest[0],"as_of":"2024-12-31"}])
    monkeypatch.setattr(nps_history,"_read_json",lambda *_args,**_kwargs:{})
    out=nps_holdings.build_nps_holdings()
    assert out["full"]==newest
    assert out["detail_history"]["selection"]["as_of"]=="2025-12-31"
    assert out["detail_history"]["selection"]["annual_input_status"]=="last_good"
    assert json.loads(source.read_text())=={"full":newest}
