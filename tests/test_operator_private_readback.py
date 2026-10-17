"""Fresh authenticated object reads retain exact checks without upload retries."""
import hashlib
import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from scripts import upload_operator_data_to_supabase as uploader
from tests.test_operator_paper_merge import private_full, quick_case


def nonce(url):
    return parse_qs(urlsplit(url).query).get("cacheNonce", [None])[0]


def test_quick_reads_latest_full_and_verifies_post_without_cached_stable_url(quick_case, monkeypatch):
    _, summary, network = quick_case
    fresh = private_full()
    fresh["analysis_provenance"]["analysis_run_id"] = "999"
    fresh["analysis_provenance"]["delivery"]["archive"]["object"] = (
        fresh["analysis_provenance"]["delivery"]["archive"]["object"].replace("/123/", "/999/"))
    fresh["latest_private_marker"] = "preserve"
    stale = private_full()
    network["body"] = json.dumps(fresh).encode()

    def get(url, **kwargs):
        network["gets"].append((url, kwargs))
        if "/bucket/" in url:
            return SimpleNamespace(status_code=200, json=lambda: {"public": False})
        # Model the documented CDN propagation window. Only cacheNonce selects
        # the origin, both for latest baseline and immediate post-write readback.
        body = network["body"] if nonce(url) else json.dumps(stale).encode()
        return SimpleNamespace(status_code=200, content=body, headers={"CF-Cache-Status": "MISS"})

    monkeypatch.setattr(uploader.requests, "get", get)
    assert uploader.main() == 0
    assert json.loads(network["body"]) == {**fresh, "exec_paper": summary}
    assert len(network["posts"]) == 1
    assert urlsplit(network["posts"][0][0]).query == ""
    object_gets = [(url, kw) for url, kw in network["gets"] if "/object/" in url]
    assert len(object_gets) == 2
    assert all(len(nonce(url)) == 32 for url, _ in object_gets)
    assert nonce(object_gets[0][0]) != nonce(object_gets[1][0])
    for url, kwargs in object_gets:
        assert kwargs["headers"]["Authorization"] == "Bearer SECRET"
        assert kwargs["headers"]["apikey"] == "SECRET"
        assert kwargs["headers"]["Cache-Control"] == "no-cache, no-store, max-age=0"
        assert kwargs["allow_redirects"] is False and kwargs["timeout"] == 60
        assert urlsplit(url).path.endswith("/verity-reports/_operator/portfolio_full.json")


def test_nonce_is_unique_for_each_read_and_preserves_existing_query(monkeypatch):
    calls = []
    monkeypatch.setattr(uploader.requests, "get", lambda url, **kw: calls.append((url, kw)))
    url = "https://private.example.test/storage/v1/object/verity-reports/fixed.json?download=1"
    uploader._fresh_private_get(url, "SECRET")
    uploader._fresh_private_get(url, "SECRET")
    assert len(calls) == 2
    assert nonce(calls[0][0]) != nonce(calls[1][0])
    assert all(parse_qs(urlsplit(call[0]).query)["download"] == ["1"] for call in calls)


@pytest.mark.parametrize("correct", [True, False])
def test_immutable_archive_duplicate_still_requires_fresh_exact_readback(monkeypatch, capsys, correct):
    body = b'{"private":"SECRET_SOURCE"}'
    archive = {"object": "_operator/analysis_runs/123/1/fixed.json", "sha256": hashlib.sha256(body).hexdigest()}
    posts, gets = [], []

    def post(url, **kwargs):
        posts.append((url, kwargs))
        return SimpleNamespace(status_code=400, json=lambda: {"code": "KeyAlreadyExists", "message": "SECRET"})

    def get(url, **kwargs):
        gets.append((url, kwargs))
        content = body if nonce(url) and correct else b"stale SECRET_RESPONSE"
        return SimpleNamespace(status_code=200, content=content, headers={"CF-Cache-Status": "MISS"})

    monkeypatch.setattr(uploader.requests, "post", post)
    monkeypatch.setattr(uploader.requests, "get", get)
    assert uploader._preserve_analysis_archive("https://private.example.test", "SECRET", body, archive) is correct
    assert len(posts) == len(gets) == 1
    assert urlsplit(posts[0][0]).query == ""
    assert nonce(gets[0][0]) and gets[0][1]["allow_redirects"] is False
    assert posts[0][1]["data"] == body
    assert posts[0][1]["headers"]["x-upsert"] == "false"
    assert "SECRET" not in capsys.readouterr().err


@pytest.mark.parametrize("status,matching", [(200, False), (302, True), (404, True)])
def test_fresh_readback_failure_remains_failure_without_retry(quick_case, monkeypatch, capsys, status, matching):
    _, _, network = quick_case
    original_get = uploader.requests.get

    def get(url, **kwargs):
        response = original_get(url, **kwargs)
        if "/object/" in url and network["posts"]:
            response.status_code = status
            response.content = network["body"] if matching else b"SECRET_DIFFERENT_BODY"
            response.headers = {"CF-Cache-Status": "HIT", "ETag": "SECRET_HEADER"}
        return response

    monkeypatch.setattr(uploader.requests, "get", get)
    assert uploader.main() == 1
    assert len(network["posts"]) == 1
    assert len(network["gets"]) == 3  # no GET or POST retry
    captured = capsys.readouterr()
    assert "SECRET" not in captured.out + captured.err
    line = next(line for line in captured.err.splitlines() if line.startswith("[operator_readback] "))
    diagnostic = json.loads(line.split("[operator_readback] ", 1)[1])
    expected = network["posts"][0][1]["data"]
    actual = expected if matching else b"SECRET_DIFFERENT_BODY"
    assert diagnostic == {
        "stage": "object_readback", "http_status": status,
        "expected_bytes": len(expected), "actual_bytes": len(actual),
        "expected_sha256": hashlib.sha256(expected).hexdigest(),
        "actual_sha256": hashlib.sha256(actual).hexdigest(), "cf_cache_status": "HIT",
    }


@pytest.mark.parametrize("cache_state", ["MISS", "SECRET_HEADER", {"private": "SECRET_HEADER"}])
def test_readback_diagnostic_drops_unknown_headers_and_body(capsys, cache_state):
    response = SimpleNamespace(status_code=200, content=b"SECRET_RESPONSE",
                               headers={"CF-Cache-Status": cache_state, "Authorization": "SECRET_KEY"})
    uploader._readback_diagnostic("object_readback", response, b"SECRET_EXPECTED")
    captured = capsys.readouterr()
    assert "SECRET" not in captured.out + captured.err
    out = json.loads(captured.err.split("[operator_readback] ", 1)[1])
    assert out["cf_cache_status"] == ("MISS" if cache_state == "MISS" else "unknown")
    assert set(out) == {"stage", "http_status", "expected_bytes", "actual_bytes", "expected_sha256",
                        "actual_sha256", "cf_cache_status"}


@pytest.mark.parametrize("matching", [True, False])
def test_explicit_dart_readback_is_fresh_and_still_exact(tmp_path, monkeypatch, matching):
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"; data.mkdir(exist_ok=True)
    body = b'{"fundamentals":{"001":{"_source_evidence":{"value":0}}}}'
    (data / "dart_fundamentals_kr.json").write_bytes(body)
    monkeypatch.setenv("SUPABASE_URL", "https://private.example.test")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "SECRET")
    monkeypatch.setattr(uploader, "BUCKET", "verity-reports")
    monkeypatch.setattr(uploader.sys, "argv", ["upload", "--only", "dart_fundamentals_kr"])
    posts, gets = [], []
    monkeypatch.setattr(uploader.requests, "post", lambda url, **kw: posts.append((url, kw)) or SimpleNamespace(status_code=200))

    def get(url, **kwargs):
        gets.append(url)
        if "/bucket/" in url:
            return SimpleNamespace(status_code=200, json=lambda: {"public": False})
        return SimpleNamespace(status_code=200, content=body if nonce(url) and matching else b"stale",
                               headers={"CF-Cache-Status": "MISS"})

    monkeypatch.setattr(uploader.requests, "get", get)
    assert uploader.main() == (0 if matching else 1)
    assert len(posts) == 1 and len(gets) == 2
    assert posts[0][1]["data"] == body and nonce(gets[1])
