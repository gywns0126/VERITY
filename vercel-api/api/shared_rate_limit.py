"""Shared Supabase rate decision; no raw user IDs or IPs persisted.

Apply 2026100301_api_rate_boundaries.sql before deploying consumers. Missing
configuration, timeout, or malformed results fail closed (503), never silently
fall back to per-instance counters. Fixed windows are not a DDoS firewall.
"""
import hashlib
import hmac
import ipaddress
import os

import requests


def client_ip(handler):
    """Vercel overwrites forwarding headers. Never trust them off Vercel."""
    raw = (handler.headers.get('x-vercel-forwarded-for') or handler.headers.get('x-forwarded-for') or '') if os.environ.get('VERCEL') == '1' else ''
    raw = raw.split(',')[0].strip() or (handler.client_address[0] if handler.client_address else '')
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError:
        return 'unknown'


def subject_digest(scope, subject, key):
    """Server-only pseudonym; survey RPC consumes its budget atomically with insert."""
    if scope not in ('holdings', 'visitor_ping', 'survey') or not key:
        raise ValueError('invalid rate configuration')
    digest = hmac.new(key.encode(), (scope + ':' + str(subject)).encode(), hashlib.sha256).hexdigest()
    # Bounded 4096-bucket anonymous counters; collisions/NAT share a rate budget,
    # never survey identity. Survey client uniqueness uses a separate full HMAC.
    return digest[:3] + '0' * 61 if scope in ('visitor_ping', 'survey') else digest


def consume(scope, subject):
    """Return (allowed, public_error_or_none); only service-role RPC access."""
    url = os.environ.get('SUPABASE_URL', '').rstrip('/')
    key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')
    unavailable = {'error': '요청 제한 확인이 지연되고 있어요. 잠시 후 다시 시도해 주세요.', 'status': 503, 'retry_after_sec': 5}
    if not url or not key or scope not in ('holdings', 'visitor_ping', 'survey'):
        return False, unavailable
    digest = subject_digest(scope, subject, key)
    try:
        result = requests.post(
            url + '/rest/v1/rpc/consume_api_rate',
            headers={'apikey': key, 'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'},
            json={'p_scope': scope, 'p_subject': digest}, timeout=3,
        )
        result.raise_for_status()
        data = result.json()
        if not isinstance(data, dict) or type(data.get('allowed')) is not bool:
            return False, unavailable
        if data['allowed']:
            return True, None
        retry = data.get('retry_after_sec')
        if type(retry) is not int or not 1 <= retry <= 3600:
            return False, unavailable
        return False, {'error': '요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.', 'status': 429, 'retry_after_sec': retry}
    except Exception:
        # Never log response bodies, credentials, headers, raw IPs, or tokens.
        return False, unavailable
