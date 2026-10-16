"""Private completed analysis delivery ordering and failure boundaries; no network."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from scripts import upload_operator_data_to_supabase as uploader
from scripts.ci.operator_portfolio_delivery import prepare_portfolio_delivery, portfolio_archive

NOW = datetime(2026, 10, 15, 2, 0, tzinfo=timezone(timedelta(hours=9)))


def artifacts(age=2):
    source = (NOW - timedelta(hours=age)).isoformat()
    scan = {"schema_version": "v1", "scan_id": "gh:123:1", "scan_mode": "prod",
            "collected_at": source, "completed_at": source, "producer_sha": "producer-code",
            "diagnostics": {"ok": True}, "candidates": [{"ticker": "ABC"}]}
    scan_body = json.dumps(scan).encode()
    portfolio = {"recommendations": [{"ticker": "ABC", "price": 42}],
                 "vams": {"holdings": [{"ticker": "ABC", "qty": 1}]},
                 "observability": {"trust": {"verdict": "known"}},
                 "analysis_provenance": {
                     "scan_id": scan["scan_id"], "producer_sha": "producer-code",
                     "collected_at": source, "completed_at": source,
                     "snapshot_sha256": hashlib.sha256(scan_body).hexdigest(),
                     "loaded_at": (NOW - timedelta(hours=1)).isoformat(),
                     "analysis_completed_at": (NOW - timedelta(seconds=20)).isoformat(),
                     "analysis_run_id": "456", "analysis_run_attempt": "2",
                     "analysis_mode": "full", "status": "completed",
                     "scan_candidate_count": 1, "resulting_analysis_count": 1}}
    return portfolio, scan_body


def prepare(portfolio, scan, **changes):
    context = {"run_id": "456", "run_attempt": "2", "expected_scan_id": "gh:123:1",
               "analysis_mode": "full", "verity_mode": "prod", "phase": "analysis_complete", "now": NOW}
    context.update(changes)
    return json.loads(prepare_portfolio_delivery(json.dumps(portfolio).encode(), scan, **context))


def test_early_and_final_keep_analysis_and_label_delivery_separately():
    portfolio, scan = artifacts(); before = deepcopy(portfolio)
    early = prepare(portfolio, scan)
    final = prepare(portfolio, scan, phase="final", now=NOW + timedelta(minutes=30))
    for result in (early, final):
        for key in ("recommendations", "vams", "observability"):
            assert result[key] == before[key]
    assert portfolio == before
    first = early["analysis_provenance"]["delivery"]
    last = final["analysis_provenance"]["delivery"]
    assert first["phase"] == "analysis_complete" and last["phase"] == "final"
    assert first["analysis_to_prepare_seconds"] == 20
    assert last["analysis_to_prepare_seconds"] == 1820
    assert first["source_portfolio_sha256"] == last["source_portfolio_sha256"]


@pytest.mark.parametrize("field,value", [
    ("status", "started"), ("scan_id", "gh:old:1"), ("analysis_run_id", "old"),
    ("analysis_run_attempt", "1"), ("snapshot_sha256", "a" * 64),
    ("resulting_analysis_count", 99), ("scan_candidate_count", 0),
    ("analysis_completed_at", (NOW + timedelta(hours=1)).isoformat()),
])
def test_foreign_partial_or_rewritten_analysis_is_rejected(field, value):
    portfolio, scan = artifacts(); portfolio["analysis_provenance"][field] = value
    with pytest.raises(ValueError):
        prepare(portfolio, scan)


def test_us_completion_and_existing_weekend_freshness_are_supported():
    portfolio, scan = artifacts(age=72)
    portfolio["analysis_provenance"]["analysis_mode"] = "full_us"
    with pytest.raises(ValueError):
        prepare(portfolio, scan, expected_scan_id="", analysis_mode="full_us")
    weekend = NOW + timedelta(days=2)
    # Preserve the scan age at 72h while moving the complete analysis to Saturday.
    portfolio, scan = artifacts(age=24)
    portfolio["analysis_provenance"]["analysis_mode"] = "full_us"
    assert prepare(portfolio, scan, expected_scan_id="", analysis_mode="full_us", now=weekend)
    with pytest.raises(ValueError):
        prepare(portfolio, scan, expected_scan_id="", analysis_mode="full_us", now=weekend + timedelta(days=2))


@pytest.fixture
def upload_case(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"; data.mkdir(exist_ok=True)
    portfolio, scan = artifacts()
    body = json.dumps(portfolio).encode()
    (data / "portfolio.json").write_bytes(body)
    (data / "universe_candidates.json").write_bytes(scan)
    for name, value in {"SUPABASE_URL": "https://private.example.test", "SUPABASE_SERVICE_ROLE_KEY": "SECRET",
                        "GITHUB_RUN_ID": "456", "GITHUB_RUN_ATTEMPT": "2", "ANALYSIS_MODE": "full",
                        "VERITY_MODE": "prod", "UNIVERSE_EXPECTED_SCAN_ID": "gh:123:1"}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(uploader, "BUCKET", "verity-reports")
    monkeypatch.setattr(uploader, "datetime", SimpleNamespace(now=lambda tz: NOW))
    monkeypatch.setattr(uploader.sys, "argv", ["upload", "--only", "portfolio_full",
                                              "--require-completed-analysis", "--delivery-phase", "analysis_complete"])
    calls = []
    monkeypatch.setattr(uploader.requests, "get", lambda *a, **kw: SimpleNamespace(status_code=200, json=lambda: {"public": False}, content=body))
    monkeypatch.setattr(uploader.requests, "post", lambda url, **kw: calls.append((url, kw)) or SimpleNamespace(status_code=200))
    return data, body, calls


def test_only_exact_portfolio_uploaded_privately_with_no_source_mutation(upload_case):
    data, body, calls = upload_case
    assert uploader.main() == 0
    assert (data / "portfolio.json").read_bytes() == body
    assert len(calls) == 2
    archive_url, archive_request = calls[0]
    assert archive_url.endswith("/" + portfolio_archive(body, run_id="456", run_attempt="2")["object"])
    assert archive_request["headers"]["x-upsert"] == "false"
    assert archive_request["data"] == body
    url, request = calls[-1]
    assert url == "https://private.example.test/storage/v1/object/verity-reports/_operator/portfolio_full.json"
    assert "/public/" not in url and request["allow_redirects"] is False
    assert request["headers"]["Cache-Control"] == "no-store"
    assert json.loads(request["data"])["analysis_provenance"]["delivery"]["phase"] == "analysis_complete"
    proof = json.loads(request["data"])["analysis_provenance"]["delivery"]
    assert proof["archive"]["status"] == "preserved"
    assert proof["archive"]["sha256"] == proof["source_portfolio_sha256"]


@pytest.mark.parametrize("public,status", [(True, 200), (None, 200), (False, 403), (False, 302)])
def test_private_bucket_confirmation_fails_closed(upload_case, monkeypatch, public, status):
    _, _, calls = upload_case
    monkeypatch.setattr(uploader.requests, "get", lambda *a, **kw: SimpleNamespace(status_code=status, json=lambda: {"public": public}))
    assert uploader.main() != 0 and calls == []


@pytest.mark.parametrize("change", ["old_run", "old_scan", "staging", "wrong_bucket", "missing", "malformed"])
def test_invalid_source_never_starts_network_upload(upload_case, monkeypatch, change):
    data, body, calls = upload_case
    if change == "old_run": monkeypatch.setenv("GITHUB_RUN_ID", "old")
    if change == "old_scan": monkeypatch.setenv("UNIVERSE_EXPECTED_SCAN_ID", "gh:old:1")
    if change == "staging": monkeypatch.setenv("VERITY_MODE", "staging")
    if change == "wrong_bucket": monkeypatch.setattr(uploader, "BUCKET", "public")
    if change == "missing": (data / "portfolio.json").unlink()
    if change == "malformed": (data / "portfolio.json").write_text("invalid")
    monkeypatch.setattr(uploader.requests, "get", lambda *a, **kw: pytest.fail("network on invalid source"))
    assert uploader.main() != 0 and calls == []


def test_failed_upload_is_not_success_or_payload_disclosure(upload_case, monkeypatch, capsys):
    _, _, calls = upload_case
    monkeypatch.setattr(uploader.requests, "post", lambda *a, **kw: SimpleNamespace(status_code=500, text="SECRET private payload"))
    assert uploader.main() == 1
    assert "SECRET" not in capsys.readouterr().err


def test_request_error_does_not_print_private_credentials(upload_case, monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise uploader.requests.RequestException("SECRET private payload")
    monkeypatch.setattr(uploader.requests, "post", fail)
    assert uploader.main() == 1
    assert "SECRET" not in capsys.readouterr().err


def test_bytes_verified_before_bucket_probe_are_the_uploaded_bytes(upload_case, monkeypatch):
    data, body, calls = upload_case
    def bucket(*args, **kwargs):
        (data / "portfolio.json").write_text('{"foreign":"changed during request"}')
        return SimpleNamespace(status_code=200, json=lambda: {"public": False}, content=body)
    monkeypatch.setattr(uploader.requests, "get", bucket)
    assert uploader.main() == 0
    assert calls[0][1]["data"] == body
    assert json.loads(calls[-1][1]["data"])["analysis_provenance"]["analysis_run_id"] == "456"


@pytest.mark.parametrize("status", [409, 400])
@pytest.mark.parametrize("identical", [True, False])
def test_archive_duplicate_requires_exact_readback_before_claiming_preservation(upload_case, monkeypatch, status, identical):
    _, body, calls = upload_case
    def post(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(status_code=status if "analysis_runs/" in url else 200,
                               json=lambda: {"statusCode": "409"})
    def get(url, **kwargs):
        assert kwargs["allow_redirects"] is False
        return SimpleNamespace(status_code=200, json=lambda: {"public": False},
                               content=body if identical else b'{"foreign":true}')
    monkeypatch.setattr(uploader.requests, "post", post)
    monkeypatch.setattr(uploader.requests, "get", get)
    assert uploader.main() == (0 if identical else 1)
    delivery = json.loads(calls[-1][1]["data"])["analysis_provenance"]["delivery"]
    assert delivery["archive"]["status"] == ("preserved" if identical else "failed")
    assert calls[0][1]["headers"]["x-upsert"] == "false"


def test_archive_failure_still_delivers_current_results_and_fails_run(upload_case, monkeypatch):
    _, _, calls = upload_case
    def post(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(status_code=503 if "analysis_runs/" in url else 200)
    monkeypatch.setattr(uploader.requests, "post", post)
    assert uploader.main() == 1
    assert calls[-1][0].endswith("/_operator/portfolio_full.json")
    assert json.loads(calls[-1][1]["data"])["analysis_provenance"]["delivery"]["archive"]["status"] == "failed"


def test_archive_keeps_every_evidence_record_and_separate_final_content(upload_case, monkeypatch):
    data, _, calls = upload_case
    portfolio = json.loads((data / "portfolio.json").read_bytes())
    portfolio["analysis_changes"] = {"unavailable": 1}
    portfolio["recommendations"][0].update({"analysis_change": {"status": "first_observation"},
        "evidence_snapshot": {"source": "unknown"}, "rec_price_evidence": {"status": "unknown"}})
    body = json.dumps(portfolio).encode()
    (data / "portfolio.json").write_bytes(body)
    monkeypatch.setattr(uploader.requests, "get", lambda *a, **kw: SimpleNamespace(status_code=200, json=lambda: {"public": False}, content=body))
    assert uploader.main() == 0
    assert calls[0][1]["data"] == body
    archived = json.loads(calls[0][1]["data"])
    current = json.loads(calls[-1][1]["data"])
    assert archived["recommendations"] == current["recommendations"] == portfolio["recommendations"]
    assert archived["analysis_changes"] == current["analysis_changes"]
    first_archive = calls[0][0]
    portfolio["postprocessing"] = {"completed": True}
    body = json.dumps(portfolio).encode()
    (data / "portfolio.json").write_bytes(body)
    monkeypatch.setattr(uploader.sys, "argv", ["upload", "--only", "portfolio_full", "--require-completed-analysis", "--delivery-phase", "final"])
    assert uploader.main() == 0
    assert calls[2][0] != first_archive
    assert calls[2][1]["data"] == body
    assert all(call[1]["headers"]["x-upsert"] == "false" for call in (calls[0], calls[2]))


def test_actual_input_snapshot_survives_slim_disk_save_and_private_archive(upload_case, monkeypatch):
    from api.utils.analysis_evidence import capture_analysis_inputs, attach_analysis_evidence
    from api.vams import engine
    data, _, calls = upload_case
    portfolio = json.loads((data / "portfolio.json").read_bytes())
    record = {"ticker": "ABC", "currency": "USD", "price": 42,
              "dart_financials": {"annual_revenue": 100},
              "quant_factors": {"quality": 0.75}, "yf_extended": {"shares": 12},
              "group_structure": {"parent": "fixture"}}
    portfolio["recommendations"] = [record]
    portfolio["macro"] = {"reference_date": "2026-10-14", "rate": 3.5}
    captured = capture_analysis_inputs([record], portfolio)
    original = deepcopy(captured["records"][("ABC", "USD")])
    attach_analysis_evidence([record], {}, captured, portfolio["analysis_provenance"], NOW.isoformat(), "full")
    monkeypatch.setattr(engine, "DATA_DIR", str(data))
    monkeypatch.setattr(engine, "PORTFOLIO_PATH", str(data / "portfolio.json"))
    monkeypatch.setattr(engine, "RECOMMENDATIONS_PATH", str(data / "recommendations.json"))
    monkeypatch.setattr(engine, "VERITY_MODE", "prod")
    engine.save_portfolio(portfolio)
    body = (data / "portfolio.json").read_bytes()
    slim = json.loads(body)["recommendations"][0]
    assert "dart_financials" not in slim and "quant_factors" not in slim
    snapshot = slim["evidence_snapshot"]
    assert snapshot["input_snapshot"] == original["input_snapshot"]
    canonical = json.dumps(snapshot["input_snapshot"], sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"), allow_nan=False).encode()
    assert hashlib.sha256(canonical).hexdigest() == original["input_hash"] == snapshot["input_hash"]
    monkeypatch.setattr(uploader.requests, "get", lambda *a, **kw: SimpleNamespace(status_code=200, json=lambda: {"public": False}, content=body))
    assert uploader.main() == 0
    assert calls[0][1]["data"] == body
    archived = json.loads(calls[0][1]["data"])["recommendations"][0]["evidence_snapshot"]
    current = json.loads(calls[-1][1]["data"])["recommendations"][0]["evidence_snapshot"]
    assert archived == current == snapshot


@pytest.mark.parametrize("run,attempt", [("../456", "2"), ("456", "x/2"), ("", "2")])
def test_archive_identity_cannot_escape_private_prefix(run, attempt):
    with pytest.raises(ValueError):
        portfolio_archive(b"{}", run_id=run, run_attempt=attempt)


def test_final_upload_uses_captured_postprocessing_source_after_git_strip(upload_case, tmp_path, monkeypatch):
    from scripts.ci.private_analysis_files import capture_final_sources, strip_private_fields
    data, _, calls = upload_case
    portfolio = json.loads((data / "portfolio.json").read_bytes())
    portfolio["postprocessing"] = {"verified_after_analysis": True}
    portfolio["recommendations"][0]["evidence_snapshot"] = {"input_snapshot": {"private": 42}}
    body = json.dumps(portfolio).encode()
    (data / "portfolio.json").write_bytes(body)
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path.parent / (tmp_path.name + "-runner")))
    paths = capture_final_sources(tmp_path, dict(uploader.os.environ), NOW)
    (data / "portfolio.json").write_text(json.dumps(strip_private_fields(portfolio)))
    monkeypatch.setattr(uploader.sys, "argv", ["upload", "--only", "portfolio_full",
        "--require-completed-analysis", "--delivery-phase", "final",
        "--portfolio-source", str(paths[0]), "--snapshot-source", str(paths[1])])
    monkeypatch.setattr(uploader.requests, "get", lambda *a, **kw: SimpleNamespace(status_code=200, json=lambda: {"public": False}, content=body))
    assert uploader.main() == 0
    assert calls[0][1]["data"] == body
    delivered = json.loads(calls[-1][1]["data"])
    assert delivered["postprocessing"] == {"verified_after_analysis": True}
    assert delivered["recommendations"][0]["evidence_snapshot"]["input_snapshot"] == {"private": 42}
    assert "evidence_snapshot" not in json.loads((data / "portfolio.json").read_bytes())["recommendations"][0]


@pytest.mark.parametrize("kind", ["unpaired", "foreign_path", "foreign_attempt"])
def test_final_source_options_fail_closed_before_network(upload_case, tmp_path, monkeypatch, kind):
    _, _, calls = upload_case
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path.parent / "runner"))
    supplied = tmp_path.parent / "runner/operator-final-456-2/portfolio.json"
    options = ["--portfolio-source", str(supplied)]
    if kind != "unpaired":
        path = tmp_path / "foreign.json" if kind == "foreign_path" else tmp_path.parent / "runner/operator-final-456-1/universe_candidates.json"
        options += ["--snapshot-source", str(path)]
    monkeypatch.setattr(uploader.sys, "argv", ["upload", "--only", "portfolio_full", "--require-completed-analysis", "--delivery-phase", "final", *options])
    monkeypatch.setattr(uploader.requests, "get", lambda *a, **kw: pytest.fail("network on foreign source"))
    assert uploader.main() == 2 and calls == []


@pytest.mark.parametrize("readback_matches", [True, False])
def test_dart_producer_upload_is_explicit_private_and_requires_readback(tmp_path, monkeypatch, readback_matches):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)
    body = b'{"000001":{"roe":5,"_source_evidence":{"roe":{"value":5}}}}'
    (tmp_path / "data/dart_fundamentals_kr.json").write_bytes(body)
    monkeypatch.setenv("SUPABASE_URL", "https://private.example.test")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "SECRET")
    monkeypatch.setattr(uploader, "BUCKET", "verity-reports")
    posts = []
    monkeypatch.setattr(uploader.requests, "post", lambda url, **kw: posts.append((url, kw)) or SimpleNamespace(status_code=200))
    monkeypatch.setattr(uploader.requests, "get", lambda url, **kw: SimpleNamespace(status_code=200,
        json=lambda: {"public": False}, content=body if readback_matches else b"foreign bytes"))
    monkeypatch.setattr(uploader.sys, "argv", ["upload"])
    assert uploader.main() == 0 and posts == []
    monkeypatch.setattr(uploader.sys, "argv", ["upload", "--only", "dart_fundamentals_kr"])
    assert uploader.main() == (0 if readback_matches else 1)
    assert len(posts) == 1 and posts[0][0].endswith("/_operator/dart_fundamentals_kr.json")
    assert posts[0][1]["allow_redirects"] is False and posts[0][1]["data"] == body


def test_nps_diagnostics_survive_collector_failure_without_retry_or_publication():
    root = Path(__file__).resolve().parents[1]
    steps = yaml.safe_load((root / ".github/workflows/daily_analysis_full.yml").read_text())["jobs"]["analyze"]["steps"]
    collector_index = next(i for i, step in enumerate(steps) if step.get("id") == "nps_holdings")
    collector = steps[collector_index]
    assert '--diagnostics "$RUNNER_TEMP/nps-holdings-diagnostic.json"' in collector["run"]
    assert "recover" not in collector["run"]
    artifact = steps[collector_index + 1]
    assert artifact["uses"] == "actions/upload-artifact@v4"
    assert "always()" in artifact["if"] and "steps.writer_gate.outputs.run == '1'" in artifact["if"]
    assert "steps.analysis_contract" not in artifact["if"]
    assert artifact["with"]["path"] == "${{ runner.temp }}/nps-holdings-diagnostic.json"
    assert artifact["with"]["retention-days"] == 7
    assert artifact["with"]["if-no-files-found"] == "warn"


def test_full_workflow_delivers_before_postprocessing_and_retains_final_refresh():
    root = Path(__file__).resolve().parents[1]
    steps = yaml.safe_load((root / ".github/workflows/daily_analysis_full.yml").read_text())["jobs"]["analyze"]["steps"]
    ids = {step.get("id"): i for i, step in enumerate(steps) if step.get("id")}
    names = {step["name"]: i for i, step in enumerate(steps)}
    assert ids["early_operator_upload"] == ids["run_analysis"] + 1
    assert ids["early_operator_upload"] < names["Score predictions (Prediction Layer v0 채점 cron)"] < ids["operator_analyst"] < ids["final_operator_upload"]
    early = steps[ids["early_operator_upload"]]; final = steps[ids["final_operator_upload"]]
    for step in (early, final):
        assert "steps.writer_gate.outputs.run == '1'" in step["if"]
        assert "!cancelled()" in step["if"]
        assert "--require-completed-analysis" in step["run"]
        assert "UNIVERSE_EXPECTED_SCAN_ID" in step["env"]
    assert "steps.run_analysis.outcome == 'success'" in early["if"]
    assert "== 'prod'" in early["if"]
    assert "--only portfolio_full" in early["run"] and "--delivery-phase analysis_complete" in early["run"]
    assert "--delivery-phase final" in final["run"]
    assert "--only portfolio_full" not in final["run"]
