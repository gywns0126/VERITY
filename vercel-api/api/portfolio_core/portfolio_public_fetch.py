"""Bounded network reader for the fixed AlphaConsole public artifacts.

The URLs and filenames are constants.  Callers cannot add headers, credentials,
proxies, redirects, symbols, or identity data.  The process-local cache contains
only common public documents; it never stores a request or analysis result.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json
import re
import sys
import threading
import time
from typing import NamedTuple
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
AI_SOURCE_TIMEOUT_SECONDS = 3
_OPTIONAL_AI_SOURCE = "member_map_ai_candidates.json"

_CACHE_LOCK = threading.Lock()
_CACHE_RESULT = None
_CACHE_EXPIRES_AT = 0.0
_CACHE_SOURCE_REVISIONS = {}
_LIVE_STATES = {}
_REFRESH_STORE = None
_VALIDATED_SOURCES = {}
_STRONG_ETAG = re.compile(r'"[\x21\x23-\x7e]{1,126}"\Z', re.ASCII)


class _SourceResponse(NamedTuple):
    document: dict
    etag: str | None
    revision: str | None


def _safe_etag(value):
    return value if type(value) is str and _STRONG_ETAG.fullmatch(value) else None


def _read_refresh_states():
    """Read public checkpoint facts independently of the Blob downloads."""
    global _REFRESH_STORE
    from .member_map_refresh_store import RefreshStore
    if _REFRESH_STORE is None:
        _REFRESH_STORE = RefreshStore.from_environment()
    return _REFRESH_STORE.read_states()


def _refresh_overlay(documents, reader=None):
    """Optional public-fact checkpoints only; never pass a caller's identity.

    Failed reads retain earlier validated facts, not a new success clock. The
    fixed service-role adapter never reads member, price or AI tables. Only
    existing public feed fields enter the documents returned to the engine.
    """
    global _LIVE_STATES
    try:
        from .member_map_refresh_store import validate_state
        from .member_map_live_refresh import overlay_states
        states = (reader or _read_refresh_states)()
        if type(states) is not dict or not set(states) <= {"DART", "SEC", "news"}:
            raise ValueError("refresh states rejected")
        validated = {source: validate_state(source, state) for source, state in states.items()}
        merged = overlay_states(documents, validated)
        _LIVE_STATES = deepcopy(validated)
        return merged
    except Exception as error:
        try:
            from .member_map_refresh_store import safe_error_code
            print(f"member_map_checkpoint status={safe_error_code(error)}", file=sys.stderr)
        except Exception:
            pass
        try:
            from .member_map_live_refresh import overlay_states
            return overlay_states(documents, deepcopy(_LIVE_STATES))
        except Exception:
            return documents


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
    # Optional enrichment must not incur the full core-source retry delay.
    attempts = 1 if filename == _OPTIONAL_AI_SOURCE else 2
    for attempt in range(attempts):
        try:
            return _download_source_once(filename)
        except urllib.error.HTTPError as error:
            # Missing artifacts and access denials are not transient outages.
            if attempt + 1 == attempts or error.code not in {408, 429, 500, 502, 503, 504}:
                raise
        except (ConnectionError, TimeoutError, urllib.error.URLError):
            if attempt + 1 == attempts:
                raise


def _download_source_once(filename):
    """One bounded attempt. Retry never changes URL, headers or validation."""
    url = PUBLIC_SOURCE_URLS[filename]
    limit = PUBLIC_SOURCE_MAX_BYTES[filename]
    timeout = AI_SOURCE_TIMEOUT_SECONDS if filename == _OPTIONAL_AI_SOURCE else FETCH_TIMEOUT_SECONDS
    previous = _VALIDATED_SOURCES.get(filename)
    etag = previous[1] if previous is not None and previous[0] == url else None
    document, received_etag, unchanged = _read_public_document(
        url, limit, timeout=timeout, _etag=etag, _with_etag=True)
    if unchanged:
        # Only a successful prior 200 parse and canonical hash can enter this store.
        return _SourceResponse(previous[2], etag, previous[3])
    return _SourceResponse(document, received_etag, None)


def _read_public_document(url, limit, *, timeout=FETCH_TIMEOUT_SECONDS,
                          _etag=None, _with_etag=False):
    """Shared transport for code-owned public URLs, never caller supplied URLs."""
    if _with_etag and url not in PUBLIC_SOURCE_URLS.values():
        raise ValueError("public source response rejected")
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _NoRedirect(),
    )
    # Do not inherit urllib's default User-Agent or accept caller-supplied headers.
    opener.addheaders = []
    request = urllib.request.Request(
        url, headers={"If-None-Match": _etag} if _with_etag and _safe_etag(_etag) else {},
        method="GET")
    try:
        response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as error:
        if (error.code == 304 and _with_etag and _safe_etag(_etag)
                and error.geturl() == url and _safe_etag(error.headers.get("ETag")) == _etag):
            error.close()
            return None, _etag, True
        raise
    with response:
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
        received_etag = _safe_etag(response.headers.get("ETag")) if _with_etag else None
    document = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_unique_object,
        parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("invalid number")),
    )
    if type(document) is not dict:
        raise ValueError("public source response rejected")
    return (document, received_etag, False) if _with_etag else document


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
    def chunks(value, depth=0):
        # Encode individual records in C, not the entire multi-market artifact.
        # Splitting the first two container levels keeps the canonical bytes
        # while avoiding a second artifact-sized JSON string in memory.
        if depth == 2 or type(value) not in (dict, list):
            yield encoder.encode(value)
        elif type(value) is dict:
            if not all(type(key) is str for key in value):
                yield from encoder.iterencode(value)
                return
            yield "{"
            for index, key in enumerate(sorted(value)):
                if index:
                    yield ","
                yield encoder.encode(key)
                yield ":"
                yield from chunks(value[key], depth + 1)
            yield "}"
        else:
            yield "["
            for index, item in enumerate(value):
                if index:
                    yield ","
                yield from chunks(item, depth + 1)
            yield "]"

    for chunk in chunks(document):
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


def _index_revision(source_revisions):
    """Reuse only the public index; dynamic projections still use fresh inputs.

    These four artifacts are read after _ProjectedPublicIndexCache.get, not by
    its builders. Their presence still changes index coverage. All other file
    hashes, including live disclosure overlays, retain normal invalidation.
    Keep the full bundle revision separately; this is not a freshness clock.
    """
    dynamic = {"macro_snapshot.json", "commodity_exposure.json", "portfolio.json",
               "member_map_ai_candidates.json"}
    dependencies = {name: "present" if name in dynamic else revision
                    for name, revision in source_revisions.items()}
    days = date.today().isoformat() + "/" + datetime.now(timezone.utc).date().isoformat()
    return hashlib.sha256(("public-index-v1/" + days + "/" +
                           _bundle_revision(dependencies)).encode("ascii")).hexdigest()


def _copy_public_bundle(value):
    """Copy the JSON-shaped public bundle with deepcopy-equivalent alias isolation."""
    memo = {}
    atomic = {str, int, float, bool, type(None)}

    def clone(item):
        item_type = type(item)
        if item_type is dict:
            identifier = id(item)
            if identifier in memo:
                return memo[identifier]
            copied = {}
            memo[identifier] = copied
            for key, nested in item.items():
                copied[key] = nested if type(nested) in atomic else clone(nested)
            return copied
        if item_type is list:
            identifier = id(item)
            if identifier in memo:
                return memo[identifier]
            copied = []
            memo[identifier] = copied
            copied.extend(nested if type(nested) in atomic else clone(nested) for nested in item)
            return copied
        if item_type in atomic:
            return item
        return deepcopy(item, memo)

    return clone(value)


def _log_fetch_timing(*, cache, status, available, started, lock_wait_ms=0,
                      fetch_phase_ms=0, download_parse_max_ms=0, hash_ms=0,
                      overlay_ms=0, copy_ms=0, revalidated=0):
    """Fixed public-stage timings and 304 count; a warm hit revalidates nothing."""
    try:
        if cache not in {"hit", "miss"} or status not in {"complete", "partial", "unavailable"}:
            return
        if type(revalidated) is not int or not 0 <= revalidated <= len(PUBLIC_SOURCE_FILES):
            return
        values = (lock_wait_ms, fetch_phase_ms, download_parse_max_ms,
                  hash_ms, overlay_ms, copy_ms)
        metrics = " ".join(f"{name}={max(0, int(value))}" for name, value in zip(
            ("lock_wait_ms", "fetch_phase_ms", "download_parse_max_ms",
             "hash_ms", "overlay_ms", "copy_ms"), values))
        print(f"member_map_public_fetch cache={cache} status={status} "
              f"available={int(available)} revalidated={revalidated} {metrics} "
              f"elapsed_ms={max(0, int((time.monotonic() - started) * 1000))}",
              file=sys.stderr)
    except Exception:
        pass


def fetch_public_sources(*, _fetcher=None, _clock=None, _refresh_reader=None,
                         _borrow_snapshot=False):
    """Return fixed public documents plus explicit source availability.

    A valid warm entry avoids a refresh.  Once expired, the old entry is never
    returned: the current refresh result (including partial or unavailable) wins.
    The underscored hooks exist only for deterministic local contract tests.
    """
    global _CACHE_RESULT, _CACHE_EXPIRES_AT, _CACHE_SOURCE_REVISIONS

    timing_started = time.monotonic()
    production = _fetcher is None and _refresh_reader is None
    copy_bundle = (lambda value: {**value}) if production and _borrow_snapshot else (
        _copy_public_bundle if production else deepcopy)
    fetcher = _fetcher or _download_source
    clock = _clock or time.monotonic
    with _CACHE_LOCK:
        lock_wait_ms = (time.monotonic() - timing_started) * 1000
        now = clock()
        if _CACHE_RESULT is not None and now < _CACHE_EXPIRES_AT:
            copy_started = time.monotonic()
            result = copy_bundle(_CACHE_RESULT)
            # Re-evaluate date-dependent validation even across a warm midnight.
            result["index_revision"] = _index_revision(_CACHE_SOURCE_REVISIONS)
            if production:
                _log_fetch_timing(cache="hit", status=result["coverage"]["status"],
                                  available=result["coverage"]["available"],
                                  started=timing_started, lock_wait_ms=lock_wait_ms,
                                  copy_ms=(time.monotonic() - copy_started) * 1000)
            return result

        documents = {}
        source_revisions = {}
        revalidated = 0
        hash_ms = 0.0
        download_parse_max_ms = 0.0
        timing_lock = threading.Lock()

        def timed_fetch(name):
            nonlocal download_parse_max_ms
            started = time.monotonic()
            try:
                return fetcher(name)
            finally:
                elapsed = (time.monotonic() - started) * 1000
                with timing_lock:
                    download_parse_max_ms = max(download_parse_max_ms, elapsed)

        def timed_revision(document):
            nonlocal hash_ms
            started = time.monotonic()
            try:
                return _document_revision(document)
            finally:
                hash_ms += (time.monotonic() - started) * 1000

        fetch_started = time.monotonic()
        read_overlay = _fetcher is None or _refresh_reader is not None
        with ThreadPoolExecutor(max_workers=len(PUBLIC_SOURCE_FILES) + int(read_overlay)) as pool:
            # The checkpoint adapter has its own bounded deadline. Overlap its
            # read with independent public downloads, but merge and validate only
            # after both finish. A failed future still uses the last-good overlay.
            refresh_future = pool.submit(_refresh_reader or _read_refresh_states) if read_overlay else None
            futures = {name: pool.submit(timed_fetch, name) for name in PUBLIC_SOURCE_FILES}
            for name in PUBLIC_SOURCE_FILES:
                try:
                    fetched = futures[name].result()
                except Exception:
                    fetched = None
                source_response = fetched if isinstance(fetched, _SourceResponse) else None
                document = source_response.document if source_response else fetched
                if type(document) is dict:
                    try:
                        source_revision = (source_response.revision if source_response
                                           and source_response.revision is not None
                                           else timed_revision(document))
                    except (TypeError, ValueError, OverflowError, RecursionError):
                        continue
                    documents[name] = document
                    source_revisions[name] = source_revision
                    if source_response and source_response.revision is not None:
                        revalidated += 1
                    if source_response and source_response.revision is None:
                        if source_response.etag is None:
                            _VALIDATED_SOURCES.pop(name, None)
                        else:
                            _VALIDATED_SOURCES[name] = (
                                PUBLIC_SOURCE_URLS[name], source_response.etag,
                                document, source_revision)
        fetch_phase_ms = (time.monotonic() - fetch_started) * 1000

        # Explicit fake-source hooks remain network-free. Production reads only
        # the existing private public-refresh table; failed optional reads never
        # remove the existing Blob source bundle or promote an AI relation.
        if read_overlay:
            overlay_started = time.monotonic()
            baseline_documents = documents.copy()
            documents = _refresh_overlay(documents, refresh_future.result)
            # The overlay replaces changed documents and preserves other objects.
            source_revisions = {
                name: source_revisions[name]
                if name in source_revisions and document is baseline_documents.get(name)
                else timed_revision(document)
                for name, document in documents.items()
            }
            overlay_ms = (time.monotonic() - overlay_started) * 1000
        else:
            overlay_ms = 0.0

        result = {
            "documents": documents,
            "coverage": _coverage(documents),
            "revision": _bundle_revision(source_revisions),
            "index_revision": _index_revision(source_revisions),
        }
        if documents:
            _CACHE_SOURCE_REVISIONS = dict(source_revisions)
            _CACHE_RESULT = result if _fetcher is None and _refresh_reader is None else deepcopy(result)
            _CACHE_EXPIRES_AT = clock() + CACHE_TTL_SECONDS
        else:
            _CACHE_SOURCE_REVISIONS = {}
            _CACHE_RESULT = None
            _CACHE_EXPIRES_AT = 0.0
        copy_started = time.monotonic()
        returned = copy_bundle(result)
        if production:
            _log_fetch_timing(cache="miss", status=result["coverage"]["status"],
                              available=result["coverage"]["available"],
                              revalidated=revalidated,
                              started=timing_started, lock_wait_ms=lock_wait_ms,
                              fetch_phase_ms=fetch_phase_ms,
                              download_parse_max_ms=download_parse_max_ms,
                              hash_ms=hash_ms, overlay_ms=overlay_ms,
                              copy_ms=(time.monotonic() - copy_started) * 1000)
        return returned


def borrow_public_sources_for_analysis():
    """Internal read-only snapshot for the pure analysis consumer only.

    Refresh replaces snapshots rather than mutating them. The engine copies
    selected response values; it must never mutate or expose these documents.
    Ordinary consumers retain the isolated-copy contract above.
    """
    return fetch_public_sources(_borrow_snapshot=True)


def _reset_cache_for_tests():
    """Clear process-local public data; not used by the deployed handler."""
    global _CACHE_RESULT, _CACHE_EXPIRES_AT, _CACHE_SOURCE_REVISIONS, _LIVE_STATES, _REFRESH_STORE
    with _CACHE_LOCK:
        _CACHE_RESULT = None
        _CACHE_EXPIRES_AT = 0.0
        _CACHE_SOURCE_REVISIONS = {}
        _LIVE_STATES = {}
        _REFRESH_STORE = None
        _VALIDATED_SOURCES.clear()
