"""Quick preserves the latest private full analysis; all network calls are mocked."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pytest

from scripts import upload_operator_data_to_supabase as uploader
from tests.test_exec_paper_promotion import _documents

NOW = datetime(2026, 10, 16, 21, tzinfo=timezone(timedelta(hours=9)))


def private_full():
    digest = "a" * 64
    return {
        "analysis_provenance": {
            "status": "completed", "analysis_mode": "full", "analysis_run_id": "123",
            "analysis_run_attempt": "1", "analysis_completed_at": (NOW - timedelta(hours=2)).isoformat(),
            "resulting_analysis_count": 1, "scan_id": "gh:456:1",
            "delivery": {"phase": "final", "source_portfolio_sha256": digest,
                         "archive": {"status": "preserved", "sha256": digest,
                                     "object": f"_operator/analysis_runs/123/1/{digest}.json"}},
        },
        "recommendations": [{"ticker": "PRIVATE", "score": 71, "evidence_snapshot": {
            "input_snapshot": {"candidate": {"dart_financials": {"revenue": 100}}}}}],
        "analysis_changes": {"known": 1}, "vams": {"holdings": [{"ticker": "PRIVATE", "qty": 3}]},
        # Quick must not invoke the legacy performance invalidator on this document.
        "backtest_stats": {"periods": {"30d": {"return_pct": 7}}},
        "brain_accuracy": {"grades": {"A": 0.5}}, "brain_quality": {"score": 31},
        "verification_report": {"performance": {"return": 9}},
        "exec_paper": {"as_of": (NOW - timedelta(hours=1)).isoformat()},
    }


@pytest.fixture
def quick_case(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"; data.mkdir(exist_ok=True)
    production, staging, state = _documents()
    staging["updated_at"] = (NOW - timedelta(minutes=10)).isoformat()
    staging["exec_paper"]["as_of"] = (NOW - timedelta(minutes=5)).isoformat()
    production["exec_paper"] = deepcopy(staging["exec_paper"])
    for name, document in (("portfolio.json", production), ("portfolio.dev.json", staging),
                           ("exec_paper_state.json", state)):
        (data / name).write_text(json.dumps(document))
    for key, value in {"SUPABASE_URL": "https://private.example.test", "SUPABASE_SERVICE_ROLE_KEY": "SECRET",
                       "ANALYSIS_MODE": "quick", "VERITY_MODE": "staging", "GITHUB_RUN_ID": "777",
                       "GITHUB_RUN_ATTEMPT": "1"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(uploader, "BUCKET", "verity-reports")
    monkeypatch.setattr(uploader, "datetime", SimpleNamespace(now=lambda tz: NOW))
    monkeypatch.setattr(uploader.sys, "argv", ["upload", "--only", "portfolio_full", "--merge-exec-paper"])
    network = {"body": json.dumps(private_full()).encode(), "posts": [], "gets": [],
               "bucket_status": 200, "public": False, "object_status": 200, "post_status": 200,
               "readback_mismatch": False}

    def get(url, **kwargs):
        network["gets"].append((url, kwargs))
        if "/bucket/" in url:
            return SimpleNamespace(status_code=network["bucket_status"], json=lambda: {"public": network["public"]})
        content = network["body"]
        if network["posts"] and network["readback_mismatch"]:
            content = b"{}"
        return SimpleNamespace(status_code=network["object_status"], content=content)

    def post(url, **kwargs):
        network["posts"].append((url, kwargs))
        network["body"] = kwargs["data"]
        return SimpleNamespace(status_code=network["post_status"], text="SECRET response")

    monkeypatch.setattr(uploader.requests, "get", get)
    monkeypatch.setattr(uploader.requests, "post", post)
    return data, staging["exec_paper"], network


def test_merges_only_current_summary_into_latest_private_full(quick_case):
    data, summary, network = quick_case
    before = deepcopy(private_full())
    local_before = {path.name: path.read_bytes() for path in data.iterdir()}
    assert uploader.main() == 0
    saved = json.loads(network["body"])
    assert saved == {**before, "exec_paper": summary}
    assert saved["analysis_provenance"] == before["analysis_provenance"]
    assert saved["recommendations"][0]["ticker"] == "PRIVATE"
    assert {path.name: path.read_bytes() for path in data.iterdir()} == local_before
    assert len(network["posts"]) == 1
    url, kwargs = network["posts"][0]
    assert url.endswith("/verity-reports/_operator/portfolio_full.json")
    assert kwargs["allow_redirects"] is False
    assert len(network["gets"]) == 3  # bucket, latest private baseline, exact readback
    assert "/bucket/" in network["gets"][0][0]
    assert all(call[1]["allow_redirects"] is False for call in network["gets"])


@pytest.mark.parametrize("corruption", ["stripped", "partial", "quick", "no_archive", "wrong_archive",
                                         "wrong_count", "missing_evidence", "missing_changes"])
def test_rejects_unproven_private_base_before_any_write(quick_case, corruption):
    _, _, network = quick_case
    doc = private_full(); proof = doc["analysis_provenance"]
    if corruption == "stripped":
        proof.pop("delivery"); doc["recommendations"][0].pop("evidence_snapshot")
    elif corruption == "partial": proof["status"] = "started"
    elif corruption == "quick": proof["analysis_mode"] = "quick"
    elif corruption == "no_archive": proof["delivery"]["archive"]["status"] = "failed"
    elif corruption == "wrong_archive": proof["delivery"]["archive"]["object"] = "foreign.json"
    elif corruption == "wrong_count": proof["resulting_analysis_count"] = 2
    elif corruption == "missing_evidence": doc["recommendations"][0].pop("evidence_snapshot")
    elif corruption == "missing_changes": doc.pop("analysis_changes")
    network["body"] = json.dumps(doc).encode()
    assert uploader.main() == 2
    assert network["posts"] == []


@pytest.mark.parametrize("timestamp", [NOW + timedelta(minutes=1), NOW - timedelta(hours=3),
                                       NOW - timedelta(hours=1, minutes=1)])
def test_rejects_future_preanalysis_or_older_summary(timestamp):
    with pytest.raises(ValueError):
        uploader._merge_paper_summary(json.dumps(private_full()).encode(), {"as_of": timestamp.isoformat()}, NOW)


def test_rejects_equal_timestamp_conflicting_summary():
    doc = private_full()
    with pytest.raises(ValueError):
        uploader._merge_paper_summary(json.dumps(doc).encode(), {**doc["exec_paper"], "cash": 1}, NOW)


@pytest.mark.parametrize("problem", ["public", "bucket_redirect", "object_missing", "post_failed", "readback"])
def test_transport_and_readback_failure_are_visible_without_private_output(quick_case, capsys, problem):
    _, _, network = quick_case
    if problem == "public": network["public"] = True
    elif problem == "bucket_redirect": network["bucket_status"] = 302
    elif problem == "object_missing": network["object_status"] = 404
    elif problem == "post_failed": network["post_status"] = 500
    else: network["readback_mismatch"] = True
    assert uploader.main() in (1, 2)
    assert len(network["posts"]) == (1 if problem in ("post_failed", "readback") else 0)
    captured = capsys.readouterr()
    assert "SECRET" not in captured.out + captured.err
    assert "PRIVATE" not in captured.out + captured.err


@pytest.mark.parametrize("change", ["mode", "staging", "run", "state", "promotion"])
def test_rejects_invalid_current_promotion_before_network(quick_case, monkeypatch, change):
    data, _, network = quick_case
    if change == "mode": monkeypatch.setenv("ANALYSIS_MODE", "full")
    elif change == "staging": monkeypatch.setenv("VERITY_MODE", "prod")
    elif change == "run": monkeypatch.setenv("GITHUB_RUN_ID", "")
    else:
        path = data / ("exec_paper_state.json" if change == "state" else "portfolio.json")
        doc = json.loads(path.read_bytes())
        if change == "state": doc["trades"] = 99
        else: doc["exec_paper"]["cash"] = 1
        path.write_text(json.dumps(doc))
    assert uploader.main() == 2
    assert network["gets"] == network["posts"] == []


def test_naked_portfolio_selector_is_blocked_before_network(quick_case, monkeypatch):
    _, _, network = quick_case
    monkeypatch.setattr(uploader.sys, "argv", ["upload", "--only", "portfolio_full"])
    assert uploader.main() == 2
    assert network["gets"] == network["posts"] == []


def test_default_keeps_other_outputs_but_never_writes_portfolio(quick_case, monkeypatch):
    data, _, network = quick_case
    (data / "moderation_portfolio.json").write_text('{"moderation":true}')
    (data / "rebalance_review.json").write_text('{"rebalance":true}')
    monkeypatch.setattr(uploader.sys, "argv", ["upload"])
    assert uploader.main() == 0
    destinations = [url.rsplit("/", 1)[-1] for url, _ in network["posts"]]
    assert sorted(destinations) == ["moderation_portfolio.json", "rebalance_review.json"]
    assert network["gets"] == []
