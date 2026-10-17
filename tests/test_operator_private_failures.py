"""Private source failures stay distinct from empty facts, without secret leakage."""
import io
import json
import time
import urllib.error
from types import SimpleNamespace

import pytest

from api.intelligence import ticker_facts as tf

PATH = "_operator/portfolio_full.json"


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://private.example.test")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "NEVER_PRINT_SECRET")


def fail(monkeypatch, status, body):
    def open_request(*a, **k):
        raise urllib.error.HTTPError("https://private.example.test", status, "NEVER_PRINT_SECRET", {},
                                     io.BytesIO(json.dumps(body).encode()))
    monkeypatch.setattr(tf.urllib.request, "build_opener", lambda *a: SimpleNamespace(open=open_request))


@pytest.mark.parametrize("status,code", [(544, "DatabaseTimeout"), (504, "DatabaseTimeout"),
    (429, "SlowDown"), (404, "NoSuchKey"), (403, "AccessDenied"), (401, "InvalidJWT")])
def test_http_reason_preserved_without_response_text(env, monkeypatch, status, code):
    fail(monkeypatch, status, {"code": code, "message": "NEVER_PRINT_SECRET"})
    with pytest.raises(tf._PrivateSourceError) as err:
        tf._read_private_json(PATH, 1)
    assert err.value.status == status and err.value.code == code
    assert "NEVER_PRINT_SECRET" not in str(err.value)


def test_unknown_error_code_not_echoed(env, monkeypatch):
    fail(monkeypatch, 500, {"code": "NEVER_PRINT_SECRET"})
    with pytest.raises(tf._PrivateSourceError, match="unknown_error"):
        tf._read_private_json(PATH, 1)


@pytest.mark.parametrize("raw,code", [(b'bad', 'invalid_json'), (b'null', 'invalid_document'),
                                    (b'42', 'invalid_document')])
def test_invalid_document_is_failure(env, monkeypatch, raw, code):
    monkeypatch.setattr(tf.urllib.request, 'build_opener',
                        lambda *a: SimpleNamespace(open=lambda *a, **k: io.BytesIO(raw)))
    with pytest.raises(tf._PrivateSourceError, match=code):
        tf._read_private_json(PATH, 1)


def test_transport_failure_is_not_missing_data(env, monkeypatch):
    def request(*a, **k):
        raise urllib.error.URLError('NEVER_PRINT_SECRET')
    monkeypatch.setattr(tf.urllib.request, 'build_opener', lambda *a: SimpleNamespace(open=request))
    with pytest.raises(tf._PrivateSourceError, match='transport_error') as err:
        tf._read_private_json(PATH, 1)
    assert 'NEVER_PRINT_SECRET' not in str(err.value)


def test_redirect_handler_does_not_forward_auth():
    assert tf._PrivateNoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.test') is None


@pytest.mark.parametrize('url', ['http://private.example.test', 'https://[bad',
    'https://NEVER_PRINT_SECRET@private.example.test', 'https://private.example.test?key=NEVER_PRINT_SECRET'])
def test_invalid_config_never_sends_credentials(env, monkeypatch, url):
    monkeypatch.setenv('SUPABASE_URL', url)
    monkeypatch.setattr(tf.urllib.request, 'build_opener', lambda *a: pytest.fail('unsafe request'))
    with pytest.raises(tf._PrivateSourceError, match='invalid_configuration') as err:
        tf._read_private_json(PATH, 1)
    assert 'NEVER_PRINT_SECRET' not in str(err.value)


def test_missing_credentials_are_explicit(env, monkeypatch):
    monkeypatch.delenv('SUPABASE_SERVICE_ROLE_KEY')
    with pytest.raises(tf._PrivateSourceError, match='credentials_missing'):
        tf._read_private_json(PATH, 1)


def test_source_time_and_empty_document_preserved(env, monkeypatch):
    document = {'as_of': '2026-08-01', 'stocks': {}}
    monkeypatch.setattr(tf.urllib.request, 'build_opener', lambda *a:
        SimpleNamespace(open=lambda *a, **k: io.BytesIO(json.dumps(document).encode())))
    assert tf._read_private_json(PATH, 1) == document


def test_deadline_prevents_request(env, monkeypatch):
    monkeypatch.setattr(tf, '_read_private_json', lambda *a: pytest.fail('request after budget'))
    trace = []
    t = tf._FETCH_TRACE.set(trace)
    d = tf._REQUEST_DEADLINE.set(time.monotonic() - 1)
    try:
        assert tf._private_json(PATH) is None
        assert trace[-1]['reason'] == 'budget_exhausted'
    finally:
        tf._FETCH_TRACE.reset(t)
        tf._REQUEST_DEADLINE.reset(d)


def test_failure_reaches_consumer_coverage_and_text(env, monkeypatch):
    fail(monkeypatch, 544, {'code': 'DatabaseTimeout', 'message': 'NEVER_PRINT_SECRET'})
    monkeypatch.setattr(tf, 'resolve_ticker', lambda _: ('005930', 'TEST'))
    for field in ('CORE_FILES', 'SCAN_FILES', 'LOCAL_FILES'):
        monkeypatch.setattr(tf, field, [])
    monkeypatch.setattr(tf, 'PRIVATE_FILES', [(PATH, 'private test')])
    for name in ('_realtime', '_dart_recent_filings', '_daily_bars'):
        monkeypatch.setattr(tf, name, lambda *a: None)
    monkeypatch.setattr(tf, 'past_decisions_section', lambda *a: (None, None))
    result = tf.collect('005930')
    row = next(x for x in result['coverage']['sources'] if x['source'] == 'private:' + PATH)
    assert row['status'] == 'unavailable'
    assert 'DatabaseTimeout' in row['reason']
    assert 'http=544' in result['_meta']['fetch_diagnostics'][0]['reason']
    text = tf.render_text(result)
    assert 'DatabaseTimeout' in text and 'NEVER_PRINT_SECRET' not in text
