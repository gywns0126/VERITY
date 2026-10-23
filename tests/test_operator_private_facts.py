"""Approved private facts stay private and preserve their source data/dates."""
from types import SimpleNamespace
from pathlib import Path
import io
import json

import pytest
import yaml

from api.intelligence import ticker_facts as tf
from scripts import upload_operator_data_to_supabase as publisher


@pytest.fixture
def private_source(monkeypatch, tmp_path):
    monkeypatch.setattr(tf, "_ROOT", str(tmp_path))
    monkeypatch.setenv("SUPABASE_URL", "https://private.example.test")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "SECRET")
    monkeypatch.setenv("OPERATOR_BUCKET", "verity-reports")
    return tmp_path


@pytest.mark.parametrize("rel", ["data/analyst_reports.json", "data/dart_kr_backfill_result.json"])
def test_fallback_uses_only_private_endpoint_preserving_document(private_source, monkeypatch, rel):
    document = {"generated_at": "2026-05-30", "rows": [{"ticker": "005930", "year": 2024}]}
    calls = []
    def fetch(request, timeout):
        calls.append(request)
        return io.BytesIO(json.dumps(document).encode())
    monkeypatch.setattr(tf.urllib.request, "build_opener", lambda *a: SimpleNamespace(open=fetch))
    origins = {}
    token = tf._LOCAL_ORIGINS.set(origins)
    try:
        assert tf._load_local(rel) == document
        assert origins[rel] == "private:" + tf.PRIVATE_LOCAL_FALLBACKS[rel]
    finally:
        tf._LOCAL_ORIGINS.reset(token)
    request = calls[0]
    url, headers = request.full_url, dict(request.header_items())
    assert "/storage/v1/object/verity-reports/_operator/" in url
    assert "/public/" not in url and "github" not in url
    assert headers["Cache-control"] == "no-cache"
    assert headers["Authorization"] == "Bearer SECRET"
    assert tf._meta_as_of(document) == ""  # write time is not the underlying reporting period


def test_recommendations_reuse_does_not_include_holdings(private_source, monkeypatch):
    monkeypatch.setattr(tf, "_private_json", lambda path: {
        "recommendations": [{"ticker": "005930"}], "holdings": [{"ticker": "AAPL"}],
        "as_of": "2026-09-25", "account": "not-a-recommendation",
    })
    doc = tf._load_local("data/recommendations.json")
    assert doc == {"recommendations": [{"ticker": "005930"}], "as_of": "2026-09-25"}
    assert tf._extract_for_ticker(doc, "AAPL") is None


def test_missing_recommendations_is_not_an_empty_valid_dataset(private_source, monkeypatch):
    monkeypatch.setattr(tf, "_private_json", lambda path: {"holdings": []})
    assert tf._load_local("data/recommendations.json") is None


def test_private_disabled_blocks_even_local_file(private_source, monkeypatch):
    (private_source / "data").mkdir(exist_ok=True)
    (private_source / "data/analyst_reports.json").write_text('{"company_reports": []}')
    monkeypatch.setattr(tf, "_fetch_json", lambda *a, **k: pytest.fail("private request"))
    token = tf._INCLUDE_PRIVATE.set(False)
    try:
        assert tf._load_local("data/analyst_reports.json") is None
        assert tf._private_json("_operator/portfolio_full.json") is None
    finally:
        tf._INCLUDE_PRIVATE.reset(token)


def test_private_request_memo_does_not_survive_collection(private_source, monkeypatch):
    calls = []
    monkeypatch.setattr(tf, "_read_private_json", lambda *a, **k: calls.append(1) or {})
    def collect(query, include_private):
        tf._private_json("_operator/portfolio_full.json")
        tf._private_json("_operator/portfolio_full.json")
        return {"ticker": query, "sections": [], "missing": [], "_meta": {}}
    monkeypatch.setattr(tf, "_collect", collect)
    tf.collect("JEPQ")
    tf.collect("JEPQ")
    assert len(calls) == 2
    assert tf._PRIVATE_DOCS.get() is None


def test_upload_registry_contains_exact_approved_routes():
    selected = {(src, dest) for src, dest, _ in publisher.UPLOADS
                if dest in publisher.APPROVED_PRIVATE_DESTS and dest not in publisher.EXPLICIT_ONLY_DESTS}
    assert selected == {(rel, dest) for rel, dest in tf.PRIVATE_LOCAL_FALLBACKS.items()
                        if rel != "data/recommendations.json"}


@pytest.mark.parametrize("status,payload,expected,diagnostic", [
    (200, {"public": False}, 0, None),
    (200, {"public": True}, 2, {"http_status": 200, "content_type": "application/json", "json_parsed": True, "public": True, "code": "unknown", "exception_class": None}),
    (200, {}, 2, {"http_status": 200, "content_type": "application/json", "json_parsed": True, "public": None, "code": "unknown", "exception_class": None}),
    (403, {"public": False}, 2, {"http_status": 403, "content_type": "application/json", "json_parsed": True, "public": False, "code": "unknown", "exception_class": None}),
    (544, {"code": "DatabaseTimeout", "message": "SECRET_RESPONSE"}, 2,
     {"http_status": 544, "content_type": "application/json", "json_parsed": True, "public": None, "code": "DatabaseTimeout", "exception_class": None}),
])
def test_new_uploads_require_verified_private_bucket(monkeypatch, tmp_path, capsys, status, payload, expected, diagnostic):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)
    original = b'{"updated_at":"2026-08-14","company_reports":[]}'
    (tmp_path / "data/analyst_reports.json").write_bytes(original)
    monkeypatch.setenv("SUPABASE_URL", "https://private.example.test")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "SECRET")
    monkeypatch.setattr(publisher, "BUCKET", "verity-reports")
    monkeypatch.setattr(publisher.sys, "argv", ["upload", "--only", "analyst_reports"])
    monkeypatch.setattr(publisher.requests, "get", lambda *a, **k:
                        SimpleNamespace(status_code=status, headers={"Content-Type": "application/json; charset=utf-8"},
                                        json=lambda: payload))
    sent = []
    monkeypatch.setattr(publisher.requests, "post", lambda *a, **k:
                        sent.append(k["data"]) or SimpleNamespace(status_code=200))
    assert publisher.main() == expected
    assert sent == ([original] if expected == 0 else [])
    captured = capsys.readouterr()
    assert "SECRET_RESPONSE" not in captured.out + captured.err
    assert "application/secret-response-canary" not in captured.out + captured.err
    lines = [line for line in captured.err.splitlines() if line.startswith("[operator_bucket] ")]
    if diagnostic is None:
        assert lines == []
    else:
        assert len(lines) == 1
        entry = json.loads(lines[0].split("[operator_bucket] ", 1)[1])
        assert entry == {"stage": "verification", **diagnostic}


@pytest.mark.parametrize("error,expected_class", [
    (ValueError("SECRET_RESPONSE"), None),
    (None, "ReadTimeout"),
])
@pytest.mark.parametrize("content_type,expected_content_type", [
    ("text/html", "unknown"),
    ("application/secret-response-canary", "unknown"),
    ("application/problem+json", "application/problem+json"),
])
def test_private_bucket_diagnostic_sanitizes_invalid_json_and_transport_errors(
        monkeypatch, tmp_path, capsys, error, expected_class, content_type, expected_content_type):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data/analyst_reports.json").write_text('{"company_reports":[]}')
    monkeypatch.setenv("SUPABASE_URL", "https://private.example.test")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "SECRET")
    monkeypatch.setattr(publisher, "BUCKET", "verity-reports")
    monkeypatch.setattr(publisher.sys, "argv", ["upload", "--only", "analyst_reports"])

    def get(*args, **kwargs):
        if error is None:
            import requests
            raise requests.ReadTimeout("SECRET_RESPONSE")
        return SimpleNamespace(status_code=200, headers={"Content-Type": content_type},
                               json=lambda: (_ for _ in ()).throw(error))

    monkeypatch.setattr(publisher.requests, "get", get)
    sent = []
    monkeypatch.setattr(publisher.requests, "post", lambda *a, **k: sent.append(1))
    assert publisher.main() == 2
    assert sent == []
    captured = capsys.readouterr()
    assert "SECRET_RESPONSE" not in captured.out + captured.err
    assert "application/secret-response-canary" not in captured.out + captured.err
    lines = [line for line in captured.err.splitlines() if line.startswith("[operator_bucket] ")]
    assert len(lines) == 1
    entry = json.loads(lines[0].split("[operator_bucket] ", 1)[1])
    assert entry["stage"] == "verification"
    expected_content_type = expected_content_type if expected_class is None else "unknown"
    if expected_class is None:
        assert entry == {"stage": "verification", "http_status": 200, "content_type": expected_content_type,
                         "json_parsed": False, "public": None, "code": "unknown", "exception_class": None}
    else:
        assert entry == {"stage": "verification", "http_status": None, "content_type": "unknown",
                         "json_parsed": False, "public": None, "code": "unknown", "exception_class": expected_class}


def test_explicit_missing_approved_upload_fails(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SUPABASE_URL", "https://private.example.test")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "SECRET")
    monkeypatch.setattr(publisher.sys, "argv", ["upload", "--only", "analyst_reports"])
    assert publisher.main() == 1


def test_backfill_subset_cannot_replace_history():
    one = {"ticker": "005930", "fiscal_year": 2024, "period": "annual"}
    two = {"ticker": "005930", "fiscal_year": 2023, "period": "annual"}
    previous = SimpleNamespace(status_code=200, json=lambda: {"rows": [one, two]})
    assert not publisher._backfill_preserves_coverage({"rows": [one]}, previous)
    assert publisher._backfill_preserves_coverage({"rows": [one, two]}, previous)
    assert not publisher._backfill_preserves_coverage({"rows": []}, previous)
    denied = SimpleNamespace(status_code=403, json=lambda: {"error": "forbidden"})
    assert not publisher._backfill_preserves_coverage({"rows": [one]}, denied)
    absent = SimpleNamespace(status_code=400, json=lambda: {"statusCode": "404", "error": "not_found"})
    assert publisher._backfill_preserves_coverage({"rows": [one]}, absent)


def test_analyst_refresh_is_private_facts_only_after_public_commit():
    root = Path(__file__).resolve().parents[1]
    doc = yaml.safe_load((root / ".github/workflows/daily_analysis_full.yml").read_text())
    steps = doc["jobs"]["analyze"]["steps"]
    refresh = next(s for s in steps if s.get("id") == "operator_analyst")
    commit = next(s for s in steps if s["name"] == "Commit & push results")
    upload = next(s for s in steps if s["name"] == "Upload operator full data to private Supabase Storage")
    assert steps.index(commit) < steps.index(refresh) < steps.index(upload)
    assert "== 'full'" in refresh["if"]
    assert refresh["env"] == {"VERITY_MODE": "prod"}
    assert "from api.collectors.ReportScout import scout_reports" in refresh["run"]
    assert "summar" not in refresh["run"] and "gemini" not in refresh["run"].lower()
    assert any("steps.operator_analyst.outcome == 'failure'" in str(s.get("if")) and "exit 1" in s.get("run", "") for s in steps)
    ignored = (root / "data/.gitignore").read_text().splitlines()
    for name in ("analyst_reports.json", "dart_kr_backfill_result.json"):
        assert name in ignored
        assert name not in (root / ".github/actions/publish-data/action.yml").read_text()
