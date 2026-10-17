"""PDF-only identity assets. No user-supplied URLs or credentials are accepted."""
from __future__ import annotations

import re
import struct
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from collections import OrderedDict
from pathlib import Path

_LOGO_BASE = "https://static.toss.im/png-icons/securities/icn-sec-fill-"
_MAX_BYTES = 256 * 1024
_CACHE = OrderedDict()
_LOCK = threading.Lock()
_FLAG_DIR = Path(__file__).resolve().parent / '_templates' / 'flags'


def flag_svg(market: str) -> str:
    """Local vectors avoid external flag requests; a missing asset is optional."""
    try:
        raw = (_FLAG_DIR / ('kr.svg' if market == 'KR' else 'us.svg')).read_text()
        if len(raw) <= 8192 and ET.fromstring(raw).tag == '{http://www.w3.org/2000/svg}svg':
            return raw
    except (OSError, UnicodeError, ET.ParseError):
        pass
    return ''


def reject_logo(ticker: str, raw: bytes) -> None:
    """A decoder failure is a short negative cache entry, not an hour of success."""
    key = str(ticker).upper().replace('-', '.')
    with _LOCK:
        if key in _CACHE and _CACHE[key][1] == raw:
            _CACHE[key] = (time.monotonic() + 60, b'')


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def logo_png(ticker: str) -> bytes:
    """Embed the same public PNG used by the stock page; fail to initials.

    A bounded warm-instance cache avoids re-downloading per PDF. Negative
    results expire sooner so a temporary CDN error does not hide a logo all day.
    """
    ticker = str(ticker).upper().replace("-", ".")
    if not re.fullmatch(r"(?:\d{6}|[A-Z][A-Z0-9.]{0,9})", ticker):
        return b""
    with _LOCK:
        cached = _CACHE.get(ticker)
        if cached and time.monotonic() < cached[0]:
            _CACHE.move_to_end(ticker)
            return cached[1]
    raw = b""
    try:
        request = urllib.request.Request(
            _LOGO_BASE + ticker + ".png", headers={"User-Agent": "AlphaNest fact-report"})
        deadline = time.monotonic() + 2
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=1) as response:
            candidate = b''
            # read1 returns available data instead of waiting to fill the whole
            # buffer. Check elapsed time even when a server drips small chunks.
            while len(candidate) <= _MAX_BYTES:
                if time.monotonic() >= deadline:
                    raise TimeoutError('logo_body_deadline')
                chunk = response.read1(min(16384, _MAX_BYTES + 1 - len(candidate)))
                if not chunk:
                    break
                candidate += chunk
        if (24 <= len(candidate) <= _MAX_BYTES
                and candidate.startswith(b"\x89PNG\r\n\x1a\n")
                and candidate[12:16] == b"IHDR"):
            width, height = struct.unpack(">II", candidate[16:24])
            if 0 < width <= 2048 and 0 < height <= 2048:
                raw = candidate
    except Exception:
        # Decorative assets must not make financial evidence unavailable.
        pass
    with _LOCK:
        _CACHE[ticker] = (time.monotonic() + (3600 if raw else 60), raw)
        _CACHE.move_to_end(ticker)
        while len(_CACHE) > 128:
            _CACHE.popitem(last=False)
    return raw
