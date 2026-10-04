"""Bounded network reader for the fixed AlphaConsole public artifacts.

The URLs and filenames are constants.  Callers cannot add headers, credentials,
proxies, redirects, symbols, or identity data.  The process-local cache contains
only common public documents; it never stores a request or analysis result.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import threading
import time
from types import MappingProxyType
import urllib.error
import urllib.request

from .portfolio_public_sources import PUBLIC_SOURCE_FILES, PUBLIC_SOURCE_MAX_BYTES


__all__ = (
    "PUBLIC_BASE_URL",
    "PUBLIC_SOURCE_FILES",
    "PUBLIC_SOURCE_URLS",
    "CACHE_TTL_SECONDS",
    "fetch_public_sources",
)


PUBLIC_BASE_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/"
PUBLIC_SOURCE_URLS = MappingProxyType({
    filename: PUBLIC_BASE_URL + filename for filename in PUBLIC_SOURCE_FILES
})
CACHE_TTL_SECONDS = 60
FETCH_TIMEOUT_SECONDS = 15

_CACHE_LOCK = threading.Lock()
_CACHE_RESULT = None
_CACHE_EXPIRES_AT = 0.0


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("public source redirect rejected")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _download_source(filename):
    """Download one exact allowlisted source; failures are handled by the caller."""
    for attempt in range(2):
        try:
            return _download_source_once(filename)
        except urllib.error.HTTPError as error:
            # Missing artifacts and access denials are not transient outages.
            if attempt or error.code not in {408, 429, 500, 502, 503, 504}:
                raise
        except (ConnectionError, TimeoutError, urllib.error.URLError):
            if attempt:
                raise


def _download_source_once(filename):
    """One bounded attempt. Retry never changes URL, headers or validation."""
    url = PUBLIC_SOURCE_URLS[filename]
    limit = PUBLIC_SOURCE_MAX_BYTES[filename]
    return _read_public_document(url, limit)


def _read_public_document(url, limit):
    """Shared transport for code-owned public URLs, never caller supplied URLs."""
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _NoRedirect(),
    )
    # Do not inherit urllib's default User-Agent or accept caller-supplied headers.
    opener.addheaders = []
    request = urllib.request.Request(url, method="GET")
    with opener.open(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
        status = getattr(response, "status", None)
        if status is None:
            status = response.getcode()
        if status != 200 or response.geturl() != url:
            raise ValueError("public source response rejected")
        declared = response.headers.get("Content-Length")
        if declared is not None:
            try:
                if int(declared) < 0 or int(declared) > limit:
                    raise ValueError("public source response rejected")
            except (TypeError, ValueError):
                raise ValueError("public source response rejected") from None
        raw = response.read(limit + 1)
        if len(raw) > limit:
            raise ValueError("public source response rejected")
    document = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_unique_object,
        parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("invalid number")),
    )
    if type(document) is not dict:
        raise ValueError("public source response rejected")
    return document


def _coverage(documents):
    missing = [name for name in PUBLIC_SOURCE_FILES if name not in documents]
    available = len(PUBLIC_SOURCE_FILES) - len(missing)
    if available == len(PUBLIC_SOURCE_FILES):
        status = "complete"
    elif available:
        status = "partial"
    else:
        status = "unavailable"
    return {
        "expected": len(PUBLIC_SOURCE_FILES),
        "available": available,
        "missing": missing,
        "status": status,
    }


def _document_revision(document):
    digest = hashlib.sha256()
    encoder = json.JSONEncoder(
        sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False
    )
    for chunk in encoder.iterencode(document):
        digest.update(chunk.encode("utf-8"))
    return digest.hexdigest()


def _bundle_revision(source_revisions):
    digest = hashlib.sha256()
    for filename in PUBLIC_SOURCE_FILES:
        digest.update(filename.encode("ascii"))
        digest.update(b"\0")
        digest.update(source_revisions.get(filename, "missing").encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def fetch_public_sources(*, _fetcher=None, _clock=None):
    """Return fixed public documents plus explicit source availability.

    A valid warm entry avoids a refresh.  Once expired, the old entry is never
    returned: the current refresh result (including partial or unavailable) wins.
    The underscored hooks exist only for deterministic local contract tests.
    """
    global _CACHE_RESULT, _CACHE_EXPIRES_AT

    fetcher = _fetcher or _download_source
    clock = _clock or time.monotonic
    with _CACHE_LOCK:
        now = clock()
        if _CACHE_RESULT is not None and now < _CACHE_EXPIRES_AT:
            return deepcopy(_CACHE_RESULT)

        documents = {}
        source_revisions = {}
        with ThreadPoolExecutor(max_workers=len(PUBLIC_SOURCE_FILES)) as pool:
            futures = {name: pool.submit(fetcher, name) for name in PUBLIC_SOURCE_FILES}
            for name in PUBLIC_SOURCE_FILES:
                try:
                    document = futures[name].result()
                except Exception:
                    document = None
                if type(document) is dict:
                    try:
                        source_revision = _document_revision(document)
                    except (TypeError, ValueError, OverflowError, RecursionError):
                        continue
                    documents[name] = document
                    source_revisions[name] = source_revision

        result = {
            "documents": documents,
            "coverage": _coverage(documents),
            "revision": _bundle_revision(source_revisions),
        }
        if documents:
            _CACHE_RESULT = deepcopy(result)
            _CACHE_EXPIRES_AT = clock() + CACHE_TTL_SECONDS
        else:
            _CACHE_RESULT = None
            _CACHE_EXPIRES_AT = 0.0
        return deepcopy(result)


def _reset_cache_for_tests():
    """Clear process-local public data; not used by the deployed handler."""
    global _CACHE_RESULT, _CACHE_EXPIRES_AT
    with _CACHE_LOCK:
        _CACHE_RESULT = None
        _CACHE_EXPIRES_AT = 0.0
