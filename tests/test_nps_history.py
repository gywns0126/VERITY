"""NPS public history contract, loss prevention and bounded collection (offline)."""
from __future__ import annotations

import copy
import json
import sys
from types import SimpleNamespace

import pytest

from api.collectors import nps_history as history

NOW = "2026-10-08T12:00:00+00:00"
OLD = "2026-09-01T12:00:00+00:00"


def annual(ticker="005930", amount=100, asof="2024-12-31", pct=7.2):
    return {"ticker": ticker, "name": f"회사{ticker}", "eval_amt_100m": amount,
            "as_of": asof, "pct": pct}


def filing(receipt="20260701000345", filed="20260701", pct="7.2", qty="1,000", change="-100", **kwargs):
    return {"rcept_no": receipt, "rcept_dt": filed, "repror": "국민연금공단",
            "corp_code": "00126380", "stkqy": qty, "stkrt": pct,
            "stkqy_irds": change, "stkrt_irds": "-0.5", "report_resn": "단순투자",
            **kwargs}


def cache(rows, *, collected=OLD, **kwargs):
    return {"schema_version": 1, "entries": {"005930": {
        "raw_rows": rows, "last_status": "ok", "collected_at": collected,
        "last_good_at": collected, "last_attempt_at": collected, **kwargs}}}


def build(rows=None, **kwargs):
    return history.build_history([annual()] if rows is None else rows, now=NOW,
                                 cache_path=None, **kwargs)


class Session:
    def __init__(self, document=None, *, error=None, http=200):
        self.document = document if document is not None else {"status": "000", "list": [filing()]}
        self.error = error
        self.http = http
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return SimpleNamespace(status_code=self.http, json=lambda: copy.deepcopy(self.document))


def collect(session, rows=None, **kwargs):
    return history.collect_history([annual()] if rows is None else rows, now=NOW,
                                   allow_network=True, api_key="synthetic-secret",
                                   corp_resolver=lambda _: "00126380", session=session,
                                   cache_path=None, **kwargs)


def test_top100_is_evaluation_sorted_and_distinct():
    rows = [annual(f"{i:06d}", i) for i in range(1, 112)]
    rows += [annual("000111", "111"), annual("000112", -9), annual("000113", "NaN"),
             annual("000114", None), annual("000115", float("inf")), annual("000116", True)]
    targets, info = history.select_top100(list(reversed(rows)))
    assert len(targets) == len({t["ticker"] for t in targets}) == 100
    assert [t["eval_amt_100m"] for t in targets] == list(range(111, 11, -1))
    assert info["annual_input_n"] == 117
    assert info["eligible_n"] == 111 and info["duplicate_rows_n"] == 1
    assert info["excluded_rows"]["invalid_valuation"] == 5
    assert targets[0]["rank"] == 1 and targets[-1]["rank"] == 100


def test_cohort_never_blends_years_or_assigns_missing_dates():
    rows = [annual("000001", 9999), annual("000002", 10, "2025-12-31"),
            annual("000003", 20, "20251231"), annual("000004", 99999, None),
            annual("000005", 99999, "csv"), annual("000006", 99999, "2025-06-30")]
    targets, info = history.select_top100(rows)
    assert info["as_of"] == "2025-12-31"
    assert [t["ticker"] for t in targets] == ["000003", "000002"]
    assert all(t["selection_as_of"] == "2025-12-31" for t in targets)
    assert info["excluded_rows"] == {"other_annual_date": 1, "missing_or_nonannual_date": 3}
    # A newer cohort with invalid values must not quietly revive the older ranking.
    targets, info = history.select_top100([annual(), annual("000002", "NaN", "2025-12-31")])
    assert targets == [] and info["as_of"] == "2025-12-31"


def test_conflicting_duplicates_excluded_ties_deterministic_and_zero_valid():
    rows = [annual("000001", 100), annual("000001", 9999), annual("000002", 1),
            annual("000003", 1), annual("000004", 0), annual("0004Y0", 0, "2024")]
    targets, info = history.select_top100(rows[::-1])
    assert info["conflicting_tickers"] == ["000001"]
    assert [t["ticker"] for t in targets] == ["000002", "000003", "000004", "0004Y0"]
    assert targets[-1]["selection_as_of"] == "2024-12-31"


def test_invalid_duplicate_cannot_inflate_or_rescue_another_duplicate():
    targets, info = history.select_top100([annual(), annual(amount=None)])
    assert targets == [] and info["excluded_rows"]["invalid_valuation"] == 2


def test_unmatched_top1_keeps_slot_and_cannot_promote_rank101():
    rows = [dict(annual(None, 2000), name="원문 최고평가액 미확인")]
    rows += [annual(f"{i:06d}", 101 - i) for i in range(1, 102)]
    targets, info = history.select_top100(rows)
    assert info["annual_top100_n"] == 100 and info["target_n"] == len(targets) == 99
    assert info["annual_top100_unmatched_n"] == 1
    assert info["annual_top100_unmatched_rows"][0]["rank"] == 1
    assert info["annual_top100_unmatched_rows"][0]["name"] == "원문 최고평가액 미확인"
    assert targets[0]["rank"] == 2 and targets[-1]["rank"] == 100
    assert {t["ticker"] for t in targets} == {f"{i:06d}" for i in range(1, 100)}
    assert not any(t["ticker"] in {"000100", "000101"} for t in targets)
    output = build(rows, cache={})
    assert output["coverage"]["selected_count"] == 100
    assert output["coverage"]["mapped_count"] == len(output["stocks"]) == 99
    assert len(output["coverage"]["missing_or_stale"]) == 100


def test_original_top100_with_85_mapped_discloses_85_without_lower_rank_replacements():
    rows = [dict(annual(f"{i:06d}" if i > 15 else None, 200 - i), name=f"원문 종목 {i}")
            for i in range(1, 116)]
    targets, info = history.select_top100(rows)
    assert info["target_n"] == len(targets) == 85
    assert info["annual_top100_unmatched_n"] == 15
    assert info["annual_top100_n"] == 100
    assert min(t["rank"] for t in targets) == 16 and max(t["rank"] for t in targets) == 100
    result = collect(Session(), rows, maxcalls=0)
    assert result["last_collection_run"]["target_n"] == 85
    assert result["last_collection_run"]["annual_top100_unmatched_n"] == 15
    assert result["last_collection_run"]["calls"] == 0


def test_issuer_collision_does_not_combine_distinct_preferred_and_ordinary_source_rows():
    rows = [dict(annual("005930", 100), name="공개회사 보통주"),
            dict(annual("005930", 90), name="공개회사 우선주")]
    targets, info = history.select_top100(rows)
    assert targets == [] and info["annual_top100_n"] == 2
    assert info["annual_top100_unmatched_n"] == 2
    assert {row["reason"] for row in info["annual_top100_unmatched_rows"]} == {"duplicate_ticker_mapping"}


def test_raw_rows_receipt_dedup_correction_and_stable_order():
    old = filing("20260101000001", "20260101", pct="0", qty="0", change="-1000")
    new = filing(report_tp="[기재정정]대량보유", repror="국민 연금기금")
    rows = [new, old, copy.deepcopy(new), filing(repror="다른운용사")]
    before = copy.deepcopy(rows)
    normalized = history.normalize_history(rows)
    assert rows == before
    assert normalized["raw_n"] == 3 and normalized["duplicate_n"] == 1
    assert [e["rcept_no"] for e in normalized["events"]] == [old["rcept_no"], new["rcept_no"]]
    event = normalized["events"][1]
    assert event["raw_rows"] == [new]
    assert event["qty"] == 1000 and event["qty_change"] == -100
    assert event["pct_change_pp"] == -0.5 and event["reason"] == "단순투자"
    assert event["as_of"] is None and event["trade_date"] is None
    assert event["date_basis"] == "filing_date" and event["filed_at"] == "2026-07-01"
    assert event["is_correction"] and event["correction_of"] is None
    assert event["source_url"].endswith(new["rcept_no"])
    assert normalized["events"][0]["pct"] == 0  # Exit/zero observations are historical data.
    assert event["change_label"] == "보유 수량 감소"


def test_same_receipt_conflicts_preserve_both_originals_and_null_conflicting_values():
    first, second = filing(pct="7.2"), filing(pct="8.1", qty="1,500")
    normalized = history.normalize_history([first, second])
    event = normalized["events"][0]
    assert event["raw_rows"] == [first, second]
    assert event["pct"] is None and event["qty"] is None
    assert event["conflicting_fields"] == ["qty", "pct"]
    assert normalized["conflict_receipt_n"] == 1


def test_unknown_dates_missing_receipts_nonfinite_and_fractional_qty_preserved():
    rows = [filing(filed="not-a-date", pct="NaN", qty="1.5"), filing(receipt="", pct="101")]
    output = build(cache=cache(rows))
    stock = output["stocks"][0]
    assert stock["events"] == [] and len(stock["unparsed_rows"]) == 2
    assert output["coverage"]["with_history_count"] == 0
    assert stock["observed_pct"]["max"] is None
    json.dumps(output, allow_nan=False)
    normalized = history.normalize_history([filing(qty="9007199254740993", change="+500")])
    assert normalized["events"][0]["qty"] == 9007199254740993
    assert normalized["events"][0]["change_label"] == "보유 수량 증가"


def test_selected_period_extrema_are_filing_observations():
    rows = [filing("20260101000001", "20260101", pct="12"),
            filing("20260201000001", "20260201", pct="5"),
            filing("20260301000001", "20260301", pct="8")]
    output = build(cache=cache(rows), period_start="2026-02-01", period_end="2026-03-01")
    stock = output["stocks"][0]
    assert len(stock["events"]) == 2
    assert stock["observed_pct"]["max"]["pct"] == 8
    assert stock["observed_pct"]["min"]["pct"] == 5
    assert stock["observed_pct"]["date_basis"] == "filing_date"
    assert stock["observed_pct"]["period"]["start"] == "2026-02-01"
    assert output["coverage"]["selected_count"] == 1
    assert output["coverage"]["with_history_count"] == 1


def test_unlinked_correction_defers_extrema_even_if_correction_outside_selected_period():
    rows = [filing("20260101000001", "20260101", pct="12"),
            filing("20260301000001", "20260301", pct="8", report_tp="[기재정정]")]
    output = build(cache=cache(rows), period_start="2026-01-01", period_end="2026-02-01")
    stock = output["stocks"][0]
    assert len(stock["events"]) == 1
    assert stock["observed_pct"]["correction_links_unverified"] is True
    assert stock["observed_pct"]["max"] is stock["observed_pct"]["min"] is None


def test_build_network_is_disabled_by_default(monkeypatch):
    import requests
    def forbidden(*args, **kwargs):
        pytest.fail("unexpected network request")
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    output = build(cache={})
    assert output["network_enabled"] is False
    assert output["stocks"][0]["status"] == "not_collected"
    with pytest.raises(ValueError, match="explicit --collect"):
        history.collect_history([annual()], cache_path=None)


def test_unchanged_projection_keeps_timestamp_but_new_event_updates_it():
    first_cache = cache([filing()], collected=NOW)
    first = build(cache=first_cache)
    later = "2026-10-08T12:01:00+00:00"
    unchanged = history.build_history([annual()], previous=first, cache=first_cache, now=later)
    assert unchanged == first
    new_cache = cache([filing(), filing("20261008000001", "20261008")], collected=NOW)
    changed = history.build_history([annual()], previous=first, cache=new_cache, now=later)
    assert changed["generated_at"] == later and len(changed["stocks"][0]["events"]) == 2


@pytest.mark.parametrize("document,http,error,reason", [
    ({"status": "013"}, 200, None, "empty_response"),
    ({"status": "000", "list": []}, 200, None, "empty_response"),
    ({"status": "000", "list": [filing(repror="다른운용사")]}, 200, None, "no_nps_rows"),
    ({"status": "020", "message": "synthetic-secret"}, 200, None, "dart_error"),
    ({}, 503, None, "http_error"),
    ([], 200, None, "invalid_response"),
    (None, 200, RuntimeError("URL contains synthetic-secret"), "transport_or_json_error"),
])
def test_failed_or_empty_response_retains_last_good(document, http, error, reason, capsys):
    original = cache([filing()])
    before = copy.deepcopy(original)
    result = collect(Session(document, http=http, error=error), cache=original)
    entry = result["entries"]["005930"]
    assert original == before
    assert entry["raw_rows"] == before["entries"]["005930"]["raw_rows"]
    assert entry["collected_at"] == entry["last_good_at"] == OLD
    assert entry["last_attempt_at"] == NOW and entry["missing_reason"] == reason
    stock = build(cache=result)["stocks"][0]
    assert stock["status"] == "stale" and stock["last_success_at"] == OLD
    assert stock["events"] and stock["missing_reason"] == reason
    assert "synthetic-secret" not in json.dumps(result) + capsys.readouterr().out


def test_nonempty_refresh_is_additive_not_a_historical_snapshot_replacement():
    old = filing("20260101000001", "20260101")
    result = collect(Session(), cache=cache([old]))
    stock = build(cache=result)["stocks"][0]
    assert len(stock["events"]) == 2 and stock["status"] == "ok"
    assert stock["last_success_at"] == NOW
    assert stock["selection_pct"] == 7.2 and stock["rank"] == 1


def test_budget_ttl_resume_and_per_attempt_checkpoint(tmp_path):
    rows = [annual("005930", 300), annual("000660", 200), annual("035420", 100)]
    target = tmp_path / "checkpoint.json"
    first_session = Session({"status": "013"})
    first = history.collect_history(rows, now=NOW, allow_network=True, maxcalls=1,
                                    api_key="fake", corp_resolver=lambda _: "00126380",
                                    session=first_session, cache_path=target)
    assert len(first_session.calls) == first["last_collection_run"]["calls"] == 1
    assert len(first["last_collection_run"]["unattempted"]) == 2
    assert json.loads(target.read_text()) == first
    second_session = Session()
    second = history.collect_history(rows, now=NOW, allow_network=True, maxcalls=1,
                                     api_key="fake", corp_resolver=lambda _: "00126380",
                                     session=second_session, cache_path=target, resume=True)
    assert second["last_collection_run"]["ttl_skipped_n"] == 1
    assert second_session.calls[0][1]["timeout"] == 15
    assert second["entries"]["000660"]["last_good_at"] == NOW
    assert second["entries"]["005930"]["last_status"] == "error"


def test_fresh_success_skipped_and_unresolved_mapping_does_not_consume_budget():
    session = Session()
    result = collect(session, cache=cache([filing()], collected=NOW))
    assert not session.calls and result["last_collection_run"]["ttl_skipped_n"] == 1
    result = history.collect_history([annual()], now=NOW, allow_network=True, api_key="fake",
                                     corp_resolver=lambda _: None, session=session, cache_path=None)
    assert not session.calls and result["last_collection_run"]["calls"] == 0
    assert result["last_collection_run"]["unattempted"][0]["reason"] == "corp_code_missing"


def test_existing_corp_resolver_is_reused_without_mapping_or_name_refresh(monkeypatch, tmp_path):
    # Stub the existing module's resolver; prove its load_mapping receives a
    # preloaded cache instead of invoking the existing network self-heal path.
    from api import collectors
    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps({"005930": "00126380"}))
    module = SimpleNamespace(_mapping_cache=None, MAPPING_PATH=str(mapping))
    def get_corp_code(ticker):
        assert module._mapping_cache is not None
        return module._mapping_cache.get(ticker.split(".")[0])
    module.get_corp_code = get_corp_code
    monkeypatch.setitem(sys.modules, "api.collectors.dart_corp_code", module)
    monkeypatch.setattr(collectors, "dart_corp_code", module, raising=False)
    assert history._cached_resolver()("005930.KS") == "00126380"


def test_absent_mapping_file_reports_unavailable_without_refresh_or_requests(monkeypatch, tmp_path):
    from api import collectors
    module = SimpleNamespace(_mapping_cache=None, MAPPING_PATH=str(tmp_path / "missing.json"),
                             get_corp_code=lambda _: pytest.fail("resolver must not self-heal"))
    monkeypatch.setitem(sys.modules, "api.collectors.dart_corp_code", module)
    monkeypatch.setattr(collectors, "dart_corp_code", module, raising=False)
    with pytest.raises(FileNotFoundError, match="mapping unavailable"):
        history._cached_resolver()
    session = Session()
    result = history.collect_history([annual()], allow_network=True, api_key="fake", session=session,
                                     cache_path=None, now=NOW)
    assert result["last_collection_run"]["calls"] == 0 and not session.calls
    assert result["last_collection_run"]["unattempted"][0]["reason"] == "corp_mapping_unavailable"
    assert module._mapping_cache is None


def test_preloaded_mapping_works_without_canonical_file_or_hidden_refresh(monkeypatch, tmp_path):
    from api import collectors
    module = SimpleNamespace(_mapping_cache={"005930": "00126380"}, MAPPING_PATH=str(tmp_path / "missing.json"))
    module.get_corp_code = lambda ticker: module._mapping_cache.get(ticker.split(".")[0])
    monkeypatch.setitem(sys.modules, "api.collectors.dart_corp_code", module)
    monkeypatch.setattr(collectors, "dart_corp_code", module, raising=False)
    monkeypatch.setattr(history, "_read_json", lambda *a, **k: pytest.fail("no file load or self-heal"))
    assert history._cached_resolver()("005930") == "00126380"
    assert not (tmp_path / "missing.json").exists()


def test_preferred_without_exact_mapping_is_not_collected_or_substituted_with_issuer(monkeypatch, tmp_path):
    from api import collectors
    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps({"005930": "00126380"}))
    module = SimpleNamespace(_mapping_cache=None, MAPPING_PATH=str(mapping))
    module.get_corp_code = lambda ticker: module._mapping_cache.get(ticker.split(".")[0])
    monkeypatch.setitem(sys.modules, "api.collectors.dart_corp_code", module)
    monkeypatch.setattr(collectors, "dart_corp_code", module, raising=False)
    preferred = [dict(annual("005935"), name="공개회사 우선주")]
    session = Session()
    result = history.collect_history(preferred, allow_network=True, api_key="fake", session=session,
                                     cache_path=None, now=NOW)
    assert not session.calls and result["last_collection_run"]["calls"] == 0
    stock = build(preferred, cache=result)["stocks"][0]
    assert stock["status"] == "not_collected" and stock["events"] == []
    assert stock["missing_reason"] == "corp_code_missing"


def test_preferred_tag_blocks_issuer_mapping_and_cached_issuer_values():
    preferred = dict(annual("005935", 200), name="공개회사 우선주", security_type="preferred")
    original = cache([filing()], collected=NOW)
    original["entries"]["005935"] = copy.deepcopy(original["entries"]["005930"])
    before = copy.deepcopy(original)
    resolved = []
    session = Session()
    result = history.collect_history([preferred, annual()], now=NOW, allow_network=True,
                                     maxcalls=1, api_key="fake", session=session,
                                     corp_resolver=lambda ticker: resolved.append(ticker) or "00126380",
                                     cache=original, cache_path=None)
    assert not resolved and not session.calls
    assert result["entries"]["005935"]["raw_rows"] == before["entries"]["005935"]["raw_rows"]
    assert original == before
    preferred_stock = build([preferred, annual()], cache=result)["stocks"][0]
    assert preferred_stock["rank"] == 1 and preferred_stock["security_type"] == "preferred"
    assert preferred_stock["status"] == "not_collected"
    assert preferred_stock["missing_reason"] == "corp_code_missing"
    assert preferred_stock["events"] == preferred_stock["unparsed_rows"] == []
    assert preferred_stock["observed_pct"]["max"] is None
    assert preferred_stock["last_success_at"] is None
    assert result["last_collection_run"]["unattempted"][0]["reason"] == "corp_code_missing"
    # Even a resolver that returns the ordinary issuer cannot cause a request.
    cold = history.collect_history([preferred], now=NOW, allow_network=True, maxcalls=1,
                                   api_key="fake", session=session,
                                   corp_resolver=lambda ticker: resolved.append(ticker) or "00126380",
                                   cache={}, cache_path=None)
    assert cold["last_collection_run"]["calls"] == 0 and not resolved and not session.calls


def test_recover_embedded_history_if_cache_missing_or_new_attempt_empty():
    previous = build(cache=cache([filing()]))
    recovered = build(previous=previous, cache={})
    assert recovered["stocks"][0]["events"] == previous["stocks"][0]["events"]
    result = collect(Session({"status": "013"}), previous=previous, cache={})
    assert build(cache=result)["stocks"][0]["last_success_at"] == OLD
    assert len(build(cache=result)["stocks"][0]["events"]) == 1


def test_bad_local_cache_is_not_overwritten_by_collection(tmp_path):
    target = tmp_path / "broken.json"
    target.write_text("broken original")
    with pytest.raises(ValueError, match="refusing to overwrite"):
        history.collect_history([annual()], allow_network=True, cache_path=target, api_key="fake")
    assert target.read_text() == "broken original"


def test_valid_json_with_invalid_cache_shape_is_not_overwritten(tmp_path):
    target = tmp_path / "invalid-shape.json"
    original = json.dumps({"entries": [cache([filing()])]})
    target.write_text(original)
    with pytest.raises(ValueError, match="refusing to overwrite"):
        history.collect_history([annual()], allow_network=True, cache_path=target, api_key="fake")
    assert target.read_text() == original


def test_newer_embedded_success_wins_over_older_cache_metadata():
    previous = build(cache=cache([filing()], collected=NOW))
    older_cache = cache([filing()], last_status="error", missing_reason="empty_response")
    output = build(previous=previous, cache=older_cache)
    stock = output["stocks"][0]
    assert stock["status"] == "ok" and stock["last_success_at"] == NOW
    assert stock["missing_reason"] is None


@pytest.mark.parametrize("kwargs", [{"maxcalls": -1}, {"maxcalls": 101}, {"maxcalls": True},
                                    {"ttl_hours": 0}, {"ttl_hours": float("nan")}])
def test_invalid_budget_and_ttl_rejected_before_network(kwargs):
    session = Session()
    with pytest.raises(ValueError):
        collect(session, **kwargs)
    assert not session.calls


def test_offline_cli_preserves_payload_fields_and_does_not_write_cache(tmp_path, monkeypatch):
    import requests
    monkeypatch.setattr(requests.sessions.Session, "request", lambda *a, **k: pytest.fail("network forbidden"))
    payload = {"generated_at": OLD, "full": [annual()], "full_n": 1,
               "full_us": [{"ticker": "EXAMPLE"}], "coverage": "original",
               "holdings": [{"ticker": "005930", "pct": 7}], "other_field": {"unknown": True}}
    source, output, local_cache = [tmp_path / name for name in ("in.json", "out.json", "cache.json")]
    source.write_text(json.dumps(payload))
    assert history.main(["--input", str(source), "--output", str(output), "--cache", str(local_cache)]) == 0
    result = json.loads(output.read_text())
    assert {k: v for k, v in result.items() if k != "detail_history"} == payload
    assert not local_cache.exists()
    assert result["detail_history"]["stocks"][0]["selection_as_of"] == "2024-12-31"
    assert result["detail_history"]["selection"]["limit"] == 100
    assert result["detail_history"]["selection"]["rank_by"] == "eval_amt_100m"


def test_cli_invalid_period_and_input_output_collision_cannot_request(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "collect_history", lambda *a, **k: pytest.fail("network forbidden"))
    source = tmp_path / "in.json"
    source.write_text(json.dumps({"full": [annual()]}))
    assert history.main(["--input", str(source), "--output", str(tmp_path / "out.json"),
                         "--collect", "--period-start", "bad"]) == 1
    with pytest.raises(SystemExit):
        history.main(["--input", str(source), "--output", str(source)])


def test_holdings_integration_preserves_annual_last_good_and_existing_detail(tmp_path, monkeypatch):
    from api.collectors import nps_holdings as holdings
    prior = {"full": [annual(f"{i:06d}", i) for i in range(1, 1057)], "full_n": 1056}
    previous = build(cache=cache([filing()]))
    # Put the stock with history into the actual previous annual top 100.
    prior["full"].append(annual(amount=99999))
    prior["detail_history"] = previous
    source = tmp_path / "nps_holdings.json"
    source.write_text(json.dumps(prior))
    monkeypatch.setattr(holdings, "OUTPUT_PATH", str(source))
    for name in ("NAMES_PATH", "FUND_OVERVIEW_PATH"):
        monkeypatch.setattr(holdings, name, str(tmp_path / (name + ".json")))
    for name in ("_from_dart_existing", "_from_data_go_kr", "_from_major_csv", "_from_previous_live"):
        monkeypatch.setattr(holdings, name, lambda *_: {})
    monkeypatch.setattr(holdings, "_from_dart_live", lambda *_: ({}, set(), {}))
    for name in ("_from_full_list", "_from_full_overseas", "_asset_mix"):
        monkeypatch.setattr(holdings, name, lambda *_: [])
    monkeypatch.setattr(history, "_read_json", lambda *_args, **_kwargs: {})
    result = holdings.build_nps_holdings()
    assert result["full"] == prior["full"] and result["full_n"] == 1057
    assert result["detail_history"]["selection"]["annual_input_status"] == "last_good"
    stock = next(s for s in result["detail_history"]["stocks"] if s["ticker"] == "005930")
    assert stock["events"] and stock["last_success_at"] == OLD
    assert json.loads(source.read_text()) == prior  # build does not write the source.
