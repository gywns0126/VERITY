"""Sanitized NPS failure evidence and exact-target one-pass recovery guards."""
import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from api.collectors import nps_holdings as nps
from api.collectors import nps_diagnostics as diag


@pytest.fixture
def local(monkeypatch, tmp_path):
    data = tmp_path / "data";data.mkdir(exist_ok=True)
    monkeypatch.setattr(nps, "_ROOT", str(tmp_path))
    for key, name in [("OUTPUT_PATH", "nps.json"), ("CATALYST_PATH", "events.jsonl"),
                      ("HEARTBEAT_PATH", "heartbeat.json"), ("NAMES_PATH", "names.json"),
                      ("PORTFOLIO_PATH", "portfolio.json")]:
        monkeypatch.setattr(nps, key, str(data / name))
    monkeypatch.setattr(nps, "_dart_api_key", lambda: "DO-NOT-LOG-THIS-KEY")
    monkeypatch.setattr(nps.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(nps, "_notify_failure", lambda *args: True)
    from api.collectors import dart_corp_code
    monkeypatch.setattr(dart_corp_code, "get_corp_code", lambda tk: "00113526")
    events = [{"ticker": "003490", "name": "대한항공", "flr_nm": "국민연금공단",
               "rcept_dt": "20261015", "rcept_no": "20261015000018"}]
    Path(nps.CATALYST_PATH).write_text("\n".join(json.dumps(row) for row in events))
    prior = {"generated_at": "2026-10-15T01:00:00+09:00", "count": 1, "coverage": "operating_pool",
             "holdings": [{"ticker": "003490", "name": "대한항공", "pct": 9.97, "qty_change": None,
                           "date": "2026-10-12", "src": "DART elestock live"}],
             "full": [{"as_of": "2025-12-31", "name": "annual-preserved"}], "detail_history": {"keep": True}}
    Path(nps.OUTPUT_PATH).write_text(json.dumps(prior))
    (data / "mapping.json").write_text(json.dumps({"003490": "00113526"}))
    return tmp_path, prior


def _session(monkeypatch, *, fail=False, receipt="20261015000018", date="20261015", http=200, during=None, pct="9.97"):
    import requests
    calls = []
    class Response:
        status_code = http
        def __init__(self, endpoint): self.endpoint = endpoint
        def json(self):
            if fail:
                raise ValueError("https://key=DO-NOT-LOG-THIS-KEY private-portfolio-body")
            if self.endpoint == "majorstock": return {"status": "013"}
            return {"status": "000", "list": [{"repror": "국민연금공단", "rcept_dt": date,
                    "rcept_no": receipt, "sp_stock_lmp_rate": pct, "sp_stock_lmp_irds_cnt": "1"}]}
    class Session:
        def get(self, url, **kwargs):
            endpoint = url.rsplit("/", 1)[-1].split(".")[0]
            calls.append((endpoint, kwargs))
            if during: during(len(calls))
            return Response(endpoint)
    monkeypatch.setattr(requests, "Session", Session)
    return calls


def _failed_artifact(monkeypatch, local):
    folder, prior = local
    _session(monkeypatch, fail=True)
    doc = diag.begin_diagnostic()
    baseline = {r["ticker"]: r for r in prior["holdings"]}
    _, _, audit = nps._from_dart_live({}, baseline)
    path = folder / "failure.json"
    diag.finish_diagnostic(doc, audit, str(path))
    assert doc["status"] == "failed"
    return path


def test_failed_endpoint_diagnostic_has_identity_status_and_no_secret(monkeypatch, local, capsys):
    path = _failed_artifact(monkeypatch, local)
    doc = json.loads(path.read_text());row = doc["targets"][0]
    assert row["ticker"] == "003490" and row["event_receipt"] == "20261015000018"
    assert row["stage"] == "endpoint_failure"
    assert {r["endpoint"] for r in row["endpoints"]} == {"majorstock", "elestock"}
    assert all(r["http_status"] == 200 and r["exception_class"] == "ValueError" for r in row["endpoints"])
    combined = path.read_text() + capsys.readouterr().out
    assert "DO-NOT-LOG-THIS-KEY" not in combined
    assert "private-portfolio-body" not in combined
    assert "https://" not in combined
    assert "_target_diagnostics" not in doc["audit"]


def test_normal_failure_preserves_last_good_and_heartbeat(monkeypatch, local):
    folder, prior = local
    path = _failed_artifact(monkeypatch, local)
    doc = json.loads(path.read_text());audit = copy.deepcopy(doc["audit"])
    audit.update(_target_diagnostics=doc["targets"], _resolved_updates={}, _resolved_retired=[])
    monkeypatch.setattr(nps, "build_nps_holdings", lambda: {"dart_refresh": audit, "count": 0})
    before = Path(nps.OUTPUT_PATH).read_bytes()
    assert nps.main(diagnostics_path=str(folder / "normal.json")) == 2
    assert Path(nps.OUTPUT_PATH).read_bytes() == before
    assert not Path(nps.HEARTBEAT_PATH).exists()
    assert json.loads((folder / "normal.json").read_text())["status"] == "failed"


def test_target_recovery_exactly_two_existing_endpoint_requests_and_preserves_annual(monkeypatch, local):
    folder, prior = local;failure = _failed_artifact(monkeypatch, local)
    from api.collectors import dart_corp_code
    monkeypatch.setattr(dart_corp_code, "get_corp_code", lambda tk: pytest.fail("mapping refresh forbidden"))
    monkeypatch.setattr(nps, "_from_data_go_kr", lambda *args: pytest.fail("broad collection forbidden"))
    calls = _session(monkeypatch)
    assert diag.retry_unresolved(str(failure), diagnostics_path=str(folder / "retry.json")) == 0
    assert [x[0] for x in calls] == ["majorstock", "elestock"]
    assert all(x[1]["allow_redirects"] is False for x in calls)
    result = json.loads(Path(nps.OUTPUT_PATH).read_text())
    assert result["holdings"][0]["date"] == "2026-10-15"
    assert result["full"] == prior["full"] and result["detail_history"] == prior["detail_history"]
    assert "_target_diagnostics" not in result["dart_refresh"]
    assert json.loads(Path(nps.HEARTBEAT_PATH).read_text())["status"] == "ok"


@pytest.mark.parametrize("change,reason", [
    ("baseline", "baseline_sha256_changed"), ("source", "catalyst_sha256_changed"),
    ("code", "collector_sha256_changed"), ("time", "diagnostic_time_invalid_or_older_than_24h"),
    ("receipt", "target_event_identity_changed_or_missing"),
    ("mapping", "local_corp_identity_changed_or_missing"),
])
def test_stale_or_changed_identity_is_rejected_before_any_request(monkeypatch, local, change, reason):
    folder, prior = local;failure = _failed_artifact(monkeypatch, local)
    doc = json.loads(failure.read_text())
    if change == "baseline": Path(nps.OUTPUT_PATH).write_text(json.dumps({**prior, "generated_at": "newer"}))
    elif change == "source": Path(nps.CATALYST_PATH).write_text(Path(nps.CATALYST_PATH).read_text() + "\n")
    elif change == "code": doc["collector_sha256"] = "old"
    elif change == "time": doc["captured_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    elif change == "receipt": doc["targets"][0]["event_receipt"] = "20261015000019"
    elif change == "mapping": (folder / "data/mapping.json").write_text(json.dumps({"003490": "99999999"}))
    failure.write_text(json.dumps(doc))
    calls = _session(monkeypatch)
    before = Path(nps.OUTPUT_PATH).read_bytes()
    assert diag.retry_unresolved(str(failure), diagnostics_path=str(folder / "retry.json")) == 3
    assert not calls and Path(nps.OUTPUT_PATH).read_bytes() == before
    assert json.loads((folder / "retry.json").read_text())["recovery_reason"] == reason


def test_output_changed_during_requests_wins_over_old_recovery(monkeypatch, local):
    folder, prior = local;failure = _failed_artifact(monkeypatch, local)
    newer = json.dumps({**prior, "generated_at": "newer-writer"})
    def concurrent(n):
        if n == 2: Path(nps.OUTPUT_PATH).write_text(newer)
    _session(monkeypatch, during=concurrent)
    assert diag.retry_unresolved(str(failure), diagnostics_path=str(folder / "retry.json")) == 3
    assert Path(nps.OUTPUT_PATH).read_text() == newer
    assert not Path(nps.HEARTBEAT_PATH).exists()


@pytest.mark.parametrize("receipt,date,stage", [
    ("20261015000019", "20261015", "receipt_identity_mismatch"),
    ("20261012000001", "20261012", "stale_parsed_date"),
])
def test_one_pass_unresolved_preserves_output_no_retry_loop(monkeypatch, local, receipt, date, stage):
    folder, prior = local;failure = _failed_artifact(monkeypatch, local)
    calls = _session(monkeypatch, receipt=receipt, date=date)
    before = Path(nps.OUTPUT_PATH).read_bytes()
    assert diag.retry_unresolved(str(failure), diagnostics_path=str(folder / "retry.json")) == 2
    assert len(calls) == 2 and Path(nps.OUTPUT_PATH).read_bytes() == before
    assert json.loads((folder / "retry.json").read_text())["targets"][0]["stage"] == stage


def test_http_failure_cannot_be_reported_as_success(monkeypatch, local):
    folder, prior = local;failure = _failed_artifact(monkeypatch, local)
    calls = _session(monkeypatch, http=500)
    assert diag.retry_unresolved(str(failure), diagnostics_path=str(folder / "retry.json")) == 2
    assert len(calls) == 2 and not Path(nps.HEARTBEAT_PATH).exists()


def test_recovery_reuses_resolved_public_rows_and_fetches_only_failed_target(monkeypatch, local):
    folder, prior = local
    events = [json.loads(Path(nps.CATALYST_PATH).read_text()),
              {"ticker": "005930", "name": "삼성전자", "flr_nm": "국민연금공단",
               "rcept_dt": "20261015", "rcept_no": "20261015000020"}]
    Path(nps.CATALYST_PATH).write_text("\n".join(json.dumps(row) for row in events))
    (folder / "data/mapping.json").write_text(json.dumps({"003490": "00113526", "005930": "00126380"}))
    from api.collectors import dart_corp_code
    monkeypatch.setattr(dart_corp_code, "get_corp_code", lambda tk: {"003490": "00113526", "005930": "00126380"}[tk])
    import requests
    class Response:
        status_code = 200
        def __init__(self, code, endpoint):self.code,self.endpoint=code,endpoint
        def json(self):
            if self.code == "00113526":return {"status": "020"}
            if self.endpoint == "majorstock":return {"status": "013"}
            return {"status": "000", "list": [{"repror": "국민연금공단", "rcept_dt": "20261015",
                    "rcept_no": "20261015000020", "sp_stock_lmp_rate": "7.5"}]}
    class Session:
        def get(self, url, **kwargs):return Response(kwargs["params"]["corp_code"], url.rsplit("/",1)[-1].split(".")[0])
    monkeypatch.setattr(requests, "Session", Session)
    doc = diag.begin_diagnostic();_,_,audit=nps._from_dart_live({}, {r["ticker"]:r for r in prior["holdings"]})
    failure = folder / "failure.json";diag.finish_diagnostic(doc,audit,str(failure))
    assert len(doc["resolved_updates"]) == 1
    calls = _session(monkeypatch)
    assert diag.retry_unresolved(str(failure), diagnostics_path=str(folder / "retry.json")) == 0
    assert len(calls) == 2
    output=json.loads(Path(nps.OUTPUT_PATH).read_text())
    assert {row["ticker"] for row in output["holdings"]} == {"003490", "005930"}
    assert output["dart_check"]["updated_tickers"] == 2


def test_busy_collection_lock_preserves_output_and_emits_private_diagnostic(local):
    folder, prior = local
    before = Path(nps.OUTPUT_PATH).read_bytes()
    with diag.collection_lock():
        assert nps.main(diagnostics_path=str(folder / "busy.json")) == 3
    assert Path(nps.OUTPUT_PATH).read_bytes() == before
    assert json.loads((folder / "busy.json").read_text())["exception_class"] == "BlockingIOError"


def test_diagnostic_cannot_overwrite_issuer_mapping(local):
    folder, prior = local
    with pytest.raises(ValueError, match="overlaps_source"):
        diag._valid_diagnostic_path(str(folder / "data/mapping.json"))


def test_impossible_fresh_ownership_is_rejected_without_replacing_last_good(monkeypatch, local):
    folder, prior = local;failure = _failed_artifact(monkeypatch, local)
    calls = _session(monkeypatch, pct="100.01")
    before = Path(nps.OUTPUT_PATH).read_bytes()
    assert diag.retry_unresolved(str(failure), diagnostics_path=str(folder / "retry.json")) == 2
    assert len(calls) == 2 and Path(nps.OUTPUT_PATH).read_bytes() == before
    assert not Path(nps.HEARTBEAT_PATH).exists()
    assert json.loads((folder / "retry.json").read_text())["targets"][0]["stage"] == "ownership_out_of_range"
