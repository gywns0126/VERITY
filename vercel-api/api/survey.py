"""Anonymous, private survey v2026-10-v1. POST/OPTIONS only; no user JWT.

Prerequisites: 2026100301_api_rate_boundaries.sql followed by
2026100601_public_survey.sql, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY and
SURVEY_HMAC_SECRET (>=32 UTF-8 bytes, stable for the survey's lifetime).
The dedicated HMAC secret must survive service-role key rotation: changing it
resets browser deduplication. Never expose either secret to the client.

Dependency boundary: the sparse checkout lacks cors_helper/supabase_client;
do not restore them here. Use requests + the existing shared rate helper.
CORS follows HEAD cors_helper's two production origins and API_ALLOWED_ORIGINS.
No account/telemetry joins, raw client IDs/IPs, answers in logs, or public reads.
The browser owns its survey-only UUID; this is not one-response-per-person.
"""
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler
import json
import os
import re
from uuid import UUID

import requests

try:
    from api.shared_rate_limit import client_ip, subject_digest
except ModuleNotFoundError:  # Direct local module loading; no common DB client.
    from shared_rate_limit import client_ip, subject_digest


VERSION = '2026-10-v1'
MAX_BODY_BYTES = 8192
_UUID = re.compile(r'^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$')
_CHOICES = {
    'purpose': {'company', 'market', 'gurus', 'learn', 'browse', 'other'},
    'outcome': {'yes', 'partly', 'no', 'not_yet', 'no_goal'},
    'discovery': {'search', 'community', 'friend', 'unknown', 'other'},
}
_FEATURES = {'report', 'map', 'market', 'gurus', 'education', 'other', 'not_used'}
_FIELDS = {'survey_version', 'request_id', 'client_id', 'purpose', 'features', 'outcome', 'discovery', 'comment'}
_RPC_ERRORS = {'invalid_payload': 400, 'idempotency_conflict': 409,
               'already_submitted': 429, 'rate_limited': 429}


def _origin(headers):
    origin = headers.get('Origin', '')
    allowed = {'https://www.alphanest.kr', 'https://alphanest.kr'}
    allowed.update(o.strip() for o in os.environ.get('API_ALLOWED_ORIGINS', '').split(',')
                   if o.strip() and o.strip() != '*')
    return origin if origin in allowed else ''


def _uuid(value, field):
    if not isinstance(value, str) or not _UUID.fullmatch(value):
        raise ValueError('invalid_' + field)
    return str(UUID(value))


def _validate(data):
    if not isinstance(data, dict) or set(data) != _FIELDS:
        raise ValueError('invalid_payload')
    if data['survey_version'] != VERSION:
        raise ValueError('invalid_version')
    request_id = _uuid(data['request_id'], 'request_id')
    browser_id = _uuid(data['client_id'], 'client_id')
    for field, choices in _CHOICES.items():
        value = data[field]
        if value is not None and (not isinstance(value, str) or value not in choices):
            raise ValueError('invalid_' + field)
    features = data['features']
    if (not isinstance(features, list) or len(features) > len(_FEATURES)
            or any(not isinstance(v, str) or v not in _FEATURES for v in features)
            or len(set(features)) != len(features)
            or ('not_used' in features and len(features) != 1)):
        raise ValueError('invalid_features')
    comment = data['comment']
    if (not isinstance(comment, str) or len(comment) > 500 or '\x00' in comment
            or any(0xD800 <= ord(c) <= 0xDFFF for c in comment)):
        raise ValueError('invalid_comment')
    if not any(data[field] for field in _CHOICES) and not features and not comment.strip():
        raise ValueError('empty_response')
    answers = {field: data[field] for field in _CHOICES}
    # A checkbox selection is a set: changing click order is still the same retry.
    answers.update(features=sorted(features), comment=comment)
    return request_id, browser_id, answers


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('invalid_payload')
        result[key] = value
    return result


def _reject_constant(_value):
    raise ValueError('invalid_payload')


def _read_body(h):
    if h.headers.get('Content-Type', '').split(';', 1)[0].strip().lower() != 'application/json':
        raise ValueError('invalid_content_type')
    try:
        length = int(h.headers.get('Content-Length', '0'))
        if not 0 < length <= MAX_BODY_BYTES or h.headers.get('Transfer-Encoding'):
            raise ValueError('invalid_payload')
        raw = h.rfile.read(length)
        if len(raw) != length:
            raise ValueError('invalid_payload')
        return json.loads(raw.decode('utf-8'), object_pairs_hook=_strict_object,
                          parse_constant=_reject_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError('invalid_payload') from None


def _submit(request_id, browser_id, answers, ip):
    url = os.environ.get('SUPABASE_URL', '').rstrip('/')
    key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')
    secret = os.environ.get('SURVEY_HMAC_SECRET', '')
    if not url or not key or len(secret.encode('utf-8')) < 32:
        return 503, {'error': 'survey_unavailable'}, None
    browser_hash = hmac.new(secret.encode('utf-8'),
                            ('survey:' + VERSION + ':' + browser_id).encode('utf-8'),
                            hashlib.sha256).hexdigest()
    try:
        response = requests.post(
            url + '/rest/v1/rpc/submit_public_survey',
            headers={'apikey': key, 'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'},
            json={'p_version': VERSION, 'p_request_id': request_id, 'p_client_hash': browser_hash,
                  'p_answers': answers, 'p_rate_subject': subject_digest('survey', ip, key)},
            timeout=(2, 5), allow_redirects=False,
        )
        if response.status_code != 200:
            return 503, {'error': 'survey_unavailable'}, None
        result = response.json()
        if isinstance(result, dict):
            if (set(result) == {'ok', 'duplicate'} and result['ok'] is True
                    and type(result['duplicate']) is bool):
                duplicate = result['duplicate']
                return (200 if duplicate else 201), ({'ok': True, 'duplicate': True} if duplicate else {'ok': True}), None
            error = result.get('error')
            if isinstance(error, str) and error in _RPC_ERRORS:
                retry = result.get('retry_after_sec')
                if error == 'rate_limited':
                    if set(result) != {'error', 'retry_after_sec'} or type(retry) is not int or not 1 <= retry <= 3600:
                        return 503, {'error': 'survey_unavailable'}, None
                elif set(result) != {'error'}:
                    return 503, {'error': 'survey_unavailable'}, None
                return _RPC_ERRORS[error], {'error': error}, retry
    except Exception:
        # A timeout may occur AFTER commit. Keep request_id and retry unchanged;
        # never include exception text, response content or credentials in logs.
        pass
    return 503, {'error': 'survey_unavailable'}, None


class handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        # BaseHTTPRequestHandler otherwise logs the request path/query and IP.
        pass

    def _respond(self, status, data=None, retry=None):
        raw = json.dumps(data, ensure_ascii=False).encode('utf-8') if data is not None else b''
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'private, no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Vary', 'Origin')
        origin = _origin(self.headers)
        if origin:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.send_header('Access-Control-Expose-Headers', 'Retry-After')
        if retry is not None:
            self.send_header('Retry-After', str(retry))
        if status == 405:
            self.send_header('Allow', 'POST, OPTIONS')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(raw)

    def do_OPTIONS(self):
        if self.headers.get('Origin') and not _origin(self.headers):
            return self._respond(400, {'error': 'invalid_origin'})
        return self._respond(204)

    def do_POST(self):
        if self.headers.get('Origin') and not _origin(self.headers):
            return self._respond(400, {'error': 'invalid_origin'})
        try:
            request_id, browser_id, answers = _validate(_read_body(self))
        except ValueError as exc:
            return self._respond(400, {'error': str(exc)})
        status, body, retry = _submit(request_id, browser_id, answers, client_ip(self))
        return self._respond(status, body, retry)

    def do_GET(self):
        return self._respond(405, {'error': 'method_not_allowed'})

    do_HEAD = do_GET
    do_PUT = do_GET
    do_PATCH = do_GET
    do_DELETE = do_GET
