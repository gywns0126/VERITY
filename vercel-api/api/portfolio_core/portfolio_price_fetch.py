"""Reuse the public KR closing-price artifacts already used by AlphaNest.

Only validated identifiers select fixed chart chunks. No brokerage request,
member identity, authentication header, private result cache or realtime feed
is involved. US history remains outside this existing-public-display scope.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import threading
import time

from .portfolio_prices import KR_CHART_FILES, KR_CLOSE_FILE
from .portfolio_public_fetch import (
    PUBLIC_BASE_URL, _document_revision, _read_public_document,
)


_FILES = frozenset((KR_CLOSE_FILE, *KR_CHART_FILES))
_MAX_BYTES = 4 * 1024 * 1024
_TTL_SECONDS = 60
_CACHE = {}  # Public file content only, bounded to the 41 fixed filenames.
_LOCK = threading.Lock()


def _download_price(filename):
    if filename not in _FILES:
        raise ValueError("unrecognized-public-price-file")
    return _read_public_document(PUBLIC_BASE_URL + filename, _MAX_BYTES)


def _read_file(filename, fetcher, clock):
    with _LOCK:
        entry = _CACHE.get(filename)
        if entry is not None and entry[0] > clock():
            return deepcopy(entry[1])
    try:
        document = fetcher(filename)
        if type(document) is not dict:
            raise ValueError("invalid-public-price-document")
        _document_revision(document)  # Reject nonfinite or unserializable content.
    except Exception:
        document = None
    with _LOCK:
        _CACHE[filename] = (clock() + _TTL_SECONDS, deepcopy(document))
    return document


def fetch_public_prices(positions, *, _fetcher=None, _clock=None):
    """Return optional price_documents for the existing pure analysis engine.

    Validation precedes all IO. A failed price request never discards other
    public facts. Cache expiry never substitutes stale values for a failed read.
    Underscored hooks are solely for deterministic tests, not HTTP parameters.
    """
    from .portfolio_engine import validate_positions

    requested = validate_positions(positions)
    tickers = {item["ticker"] for item in requested if item["market"] == "KR"}
    if not tickers:
        return {}
    fetcher, clock = _fetcher or _download_price, _clock or time.monotonic
    close = _read_file(KR_CLOSE_FILE, fetcher, clock)
    if close is None:
        return {}
    names = sorted({KR_CHART_FILES[int(ticker, 36) % len(KR_CHART_FILES)]
                    for ticker in tickers})
    charts = {}
    with ThreadPoolExecutor(max_workers=min(8, len(names))) as pool:
        results = pool.map(lambda name: _read_file(name, fetcher, clock), names)
        for name, document in zip(names, results):
            if document is not None:
                charts[name] = document
    return {"kr_close": close, "kr_charts": charts}


def _reset_cache_for_tests():
    with _LOCK:
        _CACHE.clear()
