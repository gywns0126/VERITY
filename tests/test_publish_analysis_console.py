"""The manual publisher may write only after private-bucket proof and must read back."""
import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("publish_analysis_console", ROOT / "scripts/publish_analysis_console.py")
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)

PAYLOAD = {"schema": "analysis-console-v1", "items": {"TEST": {"state": "awaiting_review"}}}
BASE = "https://private.example"
BUCKET_URL = BASE + "/storage/v1/bucket/verity-reports"
OBJECT_URL = BASE + "/storage/v1/object/verity-reports/_operator/analysis_reviews.json"


def response(status=200, body=None):
    result = Mock(status_code=status)
    result.json.return_value = body
    return result


@pytest.fixture
def network(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", BASE + "/")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "unit-test-only")
    monkeypatch.setenv("OPERATOR_BUCKET", "wrong-bucket-must-not-be-used")
    get = Mock(side_effect=[response(body={"public": False}), response(body=PAYLOAD)])
    post = Mock(return_value=response(201))
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "post", post)
    return get, post


def test_publish_fixed_private_location_and_readback(network):
    get, post = network
    publisher.publish(PAYLOAD)
    assert [call.args[0] for call in get.call_args_list] == [BUCKET_URL, OBJECT_URL]
    assert post.call_args.args == (OBJECT_URL,)
    assert post.call_args.kwargs["data"] == publisher.ctx.encode(PAYLOAD)
    assert post.call_args.kwargs["headers"]["Cache-Control"] == "no-store"
    assert get.call_args.kwargs["headers"]["Cache-Control"] == "no-store"
    for call in [*get.call_args_list, post.call_args]:
        assert call.kwargs["allow_redirects"] is False


@pytest.mark.parametrize("body", [{"public": True}, {}, {"public": "false"}, {"public": 0}, None, []])
def test_private_bucket_must_be_explicitly_false(network, body):
    get, post = network
    get.side_effect = [response(body=body)]
    with pytest.raises(ValueError, match="private bucket verification failed"):
        publisher.publish(PAYLOAD)
    post.assert_not_called()
    assert get.call_count == 1


@pytest.mark.parametrize("status", [301, 302, 307, 308, 401, 404, 500])
def test_bucket_failure_or_redirect_prevents_upload(network, status):
    get, post = network
    get.side_effect = [response(status, {"public": False})]
    with pytest.raises(ValueError, match="private bucket verification failed"):
        publisher.publish(PAYLOAD)
    assert get.call_args.kwargs["allow_redirects"] is False
    post.assert_not_called()


@pytest.mark.parametrize("status", [302, 307, 400, 401, 500])
def test_upload_failure_does_not_claim_success_or_readback(network, status):
    get, post = network
    post.return_value = response(status)
    with pytest.raises(ValueError, match="private upload failed"):
        publisher.publish(PAYLOAD)
    assert get.call_count == 1
    assert post.call_args.kwargs["allow_redirects"] is False


@pytest.mark.parametrize("status,body", [(200, {}), (200, None), (302, PAYLOAD), (403, PAYLOAD), (500, PAYLOAD)])
def test_readback_mismatch_or_failure_rejects_completion(network, status, body):
    get, post = network
    get.side_effect = [response(body={"public": False}), response(status, body)]
    with pytest.raises(ValueError, match="private readback mismatch"):
        publisher.publish(PAYLOAD)
    assert post.call_count == 1 and get.call_count == 2


@pytest.mark.parametrize("name", ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"])
def test_credentials_required_before_network(network, monkeypatch, name):
    get, post = network
    monkeypatch.delenv(name)
    with pytest.raises(ValueError, match="credentials missing"):
        publisher.publish(PAYLOAD)
    get.assert_not_called()
    post.assert_not_called()


def test_network_exception_propagates_without_retry(network):
    get, post = network
    get.side_effect = requests.Timeout()
    with pytest.raises(publisher.PublishError, match="stage=metadata http=None code=transport_error"):
        publisher.publish(PAYLOAD)
    assert get.call_count == 1
    post.assert_not_called()


@pytest.mark.parametrize("stage", ["metadata", "upload", "readback"])
def test_timeout_reports_only_safe_stage_status_code(network, stage):
    get, post = network
    failed = response(544, {"error": "DatabaseTimeout", "message": "secret-token private-account",
                            "url": "https://secret.invalid"})
    if stage == "metadata":
        get.side_effect = [failed]
    elif stage == "upload":
        post.return_value = failed
    else:
        get.side_effect = [response(body={"public": False}), failed]
    with pytest.raises(publisher.PublishError) as caught:
        publisher.publish(PAYLOAD)
    assert caught.value.stage == stage and caught.value.status == 544
    assert caught.value.code == "DatabaseTimeout"
    assert "secret" not in str(caught.value)


def test_unknown_server_error_text_is_never_exposed(network):
    get, _ = network
    get.side_effect = [response(500, {"code": "secret-token", "error": "private-account"})]
    with pytest.raises(publisher.PublishError) as caught:
        publisher.publish(PAYLOAD)
    assert caught.value.code == "unknown_error"
    assert "secret" not in str(caught.value) and "private-account" not in str(caught.value)


def test_invalid_metadata_json_fails_closed(network):
    get, post = network
    bad = response()
    bad.json.side_effect = ValueError("secret-response")
    get.side_effect = [bad]
    with pytest.raises(publisher.PublishError, match="code=invalid_json") as caught:
        publisher.publish(PAYLOAD)
    assert "secret" not in str(caught.value)
    post.assert_not_called()
