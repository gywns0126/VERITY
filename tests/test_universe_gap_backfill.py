"""Recovery must preserve missingness, provenance, and actual-observation isolation."""
import importlib.util
import json
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "scripts/recovery/universe_gap_backfill.py"
SPEC = importlib.util.spec_from_file_location("gap_backfill", PATH)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)

TARGET = {"key": "US:AAPL", "ticker": "AAPL", "market": "NASDAQ",
          "provider_symbol": "AAPL", "currency": "USD"}
LOG = "\n".join([
    "scan\tUNKNOWN STEP\t2026-09-11T12:41:32.2341905Z [quarterly_history] appended n=2704 skipped=0 → 2026-Q3.jsonl",
    "scan\tUNKNOWN STEP\t2026-09-11T12:41:33.0000000Z [Phase 2-B wide_scan SHADOW] input=2704 target=594 passed=594 logged=True",
    "scan\tUNKNOWN STEP\t2026-09-11T12:41:34.4173529Z [cand_diff] ok · 편입 28 · 이탈 28 · 유지 17 / 45",
    "scan\tUNKNOWN STEP\t2026-09-11T12:41:51.7572360Z remote: error: File data/stock_history/2026-Q3.jsonl is 101.09 MB",
    "scan\tUNKNOWN STEP\t2026-09-11T12:41:51.7572360Z OTHER_SECRET=never_save_this",
])


def payload():
    return {"chart": {"error": None, "result": [{
        "meta": {"symbol": "AAPL", "currency": "USD", "exchangeTimezoneName": "America/New_York"},
        "timestamp": [int(m.datetime(2026, 9, 8, 13, 30, tzinfo=m.timezone.utc).timestamp())],
        "indicators": {"quote": [{"open": [100], "high": [102], "low": [98], "close": [101], "volume": [1000]}],
                       "adjclose": [{"adjclose": [100.5]}]},
    }]}}


def test_log_recovery_is_allowlisted_and_not_new_observation():
    result = m.parse_log(LOG)
    assert result["reported_unsaved_rows"] == 2704
    assert result["coarse"]["passed"] == 594
    assert result["candidate_diff"]["total"] == 45
    assert result["not_full_snapshot"] is True
    assert "never_save_this" not in json.dumps(result)
    assert "last_persisted" in result["candidate_diff"]["baseline"]


@pytest.mark.parametrize("change", ["missing", "duplicate", "inconsistent", "not_failed"])
def test_bad_evidence_fails_closed(change):
    text = LOG
    if change == "missing":
        text = "\n".join(text.splitlines()[1:])
    elif change == "duplicate":
        text += "\n" + text.splitlines()[0]
    elif change == "inconsistent":
        text = text.replace("input=2704", "input=2703")
    else:
        text = text.replace("remote: error: File", "not_an_error")
    with pytest.raises(ValueError):
        m.parse_log(text)


def test_prices_have_separate_dates_and_no_fake_snapshot_timestamp():
    rows, issues = m.parse_chart(payload(), TARGET, "2026-09-13T00:00:00Z")
    assert not issues
    row = rows[0]
    assert row["date"] == "2026-09-08"
    assert row["retrieved_at"].startswith("2026-09-13")
    assert row["is_backfilled"] is True
    assert row["eligible_for_observation_trail"] is False
    assert row["close"] == 101 and row["adj_close"] == 100.5
    assert not ({"ts", "price", "per", "roe", "held_pct_insiders"} & row.keys())


@pytest.mark.parametrize("field,value", [("close", None), ("close", float("nan")),
                                        ("volume", -1), ("volume", 0.5), ("high", 90)])
def test_invalid_values_stay_missing(field, value):
    p = payload()
    p["chart"]["result"][0]["indicators"]["quote"][0][field][0] = value
    rows, issues = m.parse_chart(p, TARGET, m.now())
    assert rows == [] and len(issues) == 1


@pytest.mark.parametrize("field,value", [("symbol", "MSFT"), ("currency", "EUR")])
def test_wrong_provider_instrument_rejected(field, value):
    p = payload()
    p["chart"]["result"][0]["meta"][field] = value
    with pytest.raises(ValueError):
        m.parse_chart(p, TARGET, m.now())


def test_duplicate_day_rejected():
    p = payload()
    d = p["chart"]["result"][0]
    d["timestamp"] *= 2
    for key in d["indicators"]["quote"][0]:
        d["indicators"]["quote"][0][key] *= 2
    with pytest.raises(ValueError, match="duplicate"):
        m.parse_chart(p, TARGET, m.now())


def test_partial_denominator_counts_missing_not_zero_prices():
    rows, _ = m.parse_chart(payload(), TARGET, m.now())
    other = {**TARGET, "key": "US:MSFT"}
    cov = m.price_coverage([TARGET, other], rows, {TARGET["key"]: {"error": None}})
    assert cov["target_tickers"] == 2 and cov["attempted_tickers"] == 1
    assert cov["expected_ticker_days"] == 8 and cov["recovered_ticker_days"] == 1
    assert cov["missing_ticker_days"] == 7
    assert len(cov["unresolved"]) == 2


def test_saved_rows_round_trip_and_duplicates_rejected(tmp_path):
    rows, _ = m.parse_chart(payload(), TARGET, m.now())
    path = tmp_path / "prices.jsonl"
    m.write_prices(path, rows)
    assert m.read_prices(path) == rows
    m.write_prices(path, rows + rows)
    with pytest.raises(ValueError, match="Duplicate"):
        m.read_prices(path)


def test_boundary_roster_is_proxy_and_does_not_copy_fundamentals(tmp_path):
    root = tmp_path / "data/stock_history"
    root.mkdir(parents=True)
    before = [{"ticker": "005930", "market": "KOSPI", "currency": "KRW", "ts": "2026-09-07T10:00:00+09:00", "per": 15},
              {"ticker": "005930", "market": "KOSPI", "currency": "KRW", "ts": "2026-09-07T20:00:00+09:00"},
              {"ticker": "OLD", "market": "NYSE", "currency": "USD", "ts": "2026-09-04T20:00:00+09:00"}]
    after = [{"ticker": "AAPL", "market": "NASDAQ", "currency": "USD", "ts": "2026-09-12T10:40:00+09:00"}]
    for rel, records in zip(m.SOURCES, [before, after]):
        (tmp_path / rel).write_text("".join(json.dumps(row) + "\n" for row in records))
    rows, sources = m.build_targets(tmp_path)
    assert [r["key"] for r in rows] == ["KR:005930", "US:AAPL"]
    assert rows[0]["provider_symbol"] == "005930.KS"
    assert rows[0]["anchor_last_observed_at"].startswith("2026-09-07T20:")
    assert all("per" not in r for r in rows)
    assert [s["rows"] for s in sources] == [3, 1]


def test_output_guard_prevents_production_snapshot_insertion(monkeypatch):
    monkeypatch.setattr("sys.argv", [str(PATH), "--output", "/tmp/data/stock_history"])
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 2


@pytest.mark.parametrize("key,value", [("key", "US:OTHER"), ("date", "2026-09-07"),
                                       ("currency", "KRW"), ("is_backfilled", False),
                                       ("close", float("inf")), ("ts", "2026-09-08"),
                                       ("source_url", "https://example.com"),
                                       ("retrieved_at", "2026-09-01T00:00:00Z")])
def test_resume_rejects_polluted_or_backdated_rows(key, value):
    rows, _ = m.parse_chart(payload(), TARGET, m.now())
    rows[0][key] = value
    with pytest.raises(ValueError):
        m.validate_saved_prices(rows, [TARGET])


def test_resume_accepts_verified_sidecar():
    rows, _ = m.parse_chart(payload(), TARGET, m.now())
    m.validate_saved_prices(rows, [TARGET])


def test_production_consumer_does_not_ingest_research_sidecar(tmp_path, monkeypatch):
    from api.builders import stock_change_public_builder as consumer

    history = tmp_path / "data/stock_history"
    history.mkdir(parents=True)
    original = [{"ticker": "AAPL", "ts": "2026-09-07T10:00:00+09:00", "price": 100},
                {"ticker": "AAPL", "ts": "2026-09-12T10:00:00+09:00", "price": 110}]
    (history / "2026-Q3.jsonl").write_text("".join(json.dumps(x) + "\n" for x in original))
    research = tmp_path / "data/research/universe_gap_20260908_20260911"
    research.mkdir(parents=True)
    rows, _ = m.parse_chart(payload(), TARGET, m.now())
    m.write_prices(research / "prices_daily.jsonl", rows)
    monkeypatch.setattr(consumer, "STOCK_HISTORY_DIR", history)
    result, meta = consumer._read_latest_daily_snapshots()
    assert result["AAPL"] == original
    assert meta["rows_parsed"] == 2


def test_parse_chart_uses_exchange_date_not_utc_date():
    p = payload()
    # UTC Sep 9 00:30 remains Sep 8 in New York.
    p["chart"]["result"][0]["timestamp"] = [int(m.datetime(2026, 9, 9, 0, 30, tzinfo=m.timezone.utc).timestamp())]
    rows, _ = m.parse_chart(p, TARGET, m.now())
    assert rows[0]["date"] == "2026-09-08"


@pytest.fixture
def verification_fixture(tmp_path):
    spec = importlib.util.spec_from_file_location("gap_verify", PATH.with_name("verify_universe_gap_backfill.py"))
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    rows, _ = m.parse_chart(payload(), TARGET, m.now())
    attempts = {TARGET["key"]: {"error": "provider_missing_dates", "issues": []}}
    evidence = [{**m.parse_log(LOG), "run_id": run_id} for run_id in m.RUN_IDS]
    m.atomic_json(tmp_path / "targets.json", {"count": 1, "targets": [TARGET]})
    m.atomic_json(tmp_path / "run_evidence.json", evidence)
    m.atomic_json(tmp_path / "attempts.json", attempts)
    m.atomic_json(tmp_path / "coverage.json", m.price_coverage([TARGET], rows, attempts))
    m.write_prices(tmp_path / "prices_daily.jsonl", rows)
    manifest = {"status": "partial_original_recovery", "original_missing_snapshot_rows_restored": 0,
                "observation_trail_eligible": False,
                "files_sha256": {p.name: m.sha256(p) for p in tmp_path.iterdir() if p.is_file()}}
    m.atomic_json(tmp_path / "manifest.json", manifest)
    return verifier, tmp_path


def test_verifier_reads_back_actual_files(verification_fixture):
    verifier, path = verification_fixture
    result = verifier.verify(path)
    assert result["schema_valid_rows"] == 1
    assert result["coverage"]["missing_ticker_days"] == 3
    assert result["run_evidence_checked"] == 8


def test_verifier_rejects_mutated_file(verification_fixture):
    verifier, path = verification_fixture
    (path / "attempts.json").write_text("{}")
    with pytest.raises(ValueError, match="Checksum"):
        verifier.verify(path)


def test_verifier_rejects_in_progress_manifest(verification_fixture):
    verifier, path = verification_fixture
    manifest = json.loads((path / "manifest.json").read_text())
    manifest["status"] = "running"
    m.atomic_json(path / "manifest.json", manifest)
    with pytest.raises(ValueError, match="still running"):
        verifier.verify(path)


def test_naver_fallback_does_not_invent_timestamp_or_adjusted_price():
    target = {"key": "KR:487400", "ticker": "487400", "market": "KOSDAQ",
              "currency": "KRW", "provider_symbol": "487400.KQ"}
    data = [["날짜", "시가", "고가", "저가", "종가", "거래량", "외국인소진율"],
            ["20260908", 8000, 8720, 7730, 7830, 498091, 0.94]]
    rows = m.parse_naver(data, target, m.now())
    assert rows[0]["provider_bar_timestamp"] is None
    assert rows[0]["adj_close"] is None
    assert rows[0]["source"] == "Naver Finance daily"
    assert rows[0]["close"] == 7830
    m.validate_saved_prices(rows, [target])


def test_naver_rejects_us_instrument_and_bad_header():
    with pytest.raises(ValueError):
        m.parse_naver([], TARGET, m.now())
    target = {**TARGET, "key": "KR:005930", "currency": "KRW"}
    with pytest.raises(ValueError):
        m.parse_naver([["date", "price"]], target, m.now())
