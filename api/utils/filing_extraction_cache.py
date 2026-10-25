"""Digest-bound cache for structured extraction from public SEC/DART filings.

GitHub-side consumers only read this cache.  A separately authorised local
worker may build the prompt from the parser module and write a validated cache
entry after processing the same public filing bytes.
"""
from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse


CACHE_SCHEMA = "filing-extraction-cache-v1"
CACHE_MAX_BYTES = 1_048_576
DEFAULT_CACHE_ROOT = Path(__file__).resolve().parents[2] / "data" / "filing_extraction_cache"

EXTRACTOR_LIMITS = {
    "sec-properties-v1": 40_000,
    "dart-facilities-v1": 60_000,
}

_TOP_LEVEL_KEYS = {"schema", "extractor", "source", "status", "generated_at", "generator", "data"}
_SOURCE_KEYS = {"source_id", "as_of", "raw_sha256", "url"}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SEC_SOURCE_RE = re.compile(r"^source:sec:([0-9-]{10,24})$")
_DART_SOURCE_RE = re.compile(r"^source:dart:([0-9]{10,20})$")


class FilingExtractionCacheError(ValueError):
    """Closed cache-contract failure safe to classify without source text."""


def prepare_filing_text(extractor: str, raw_text: str) -> str:
    """Return the exact source slice used for both prompt and cache digest."""
    limit = EXTRACTOR_LIMITS.get(extractor)
    if limit is None:
        raise FilingExtractionCacheError("unsupported_extractor")
    return str(raw_text or "")[:limit]


def filing_source_sha256(extractor: str, raw_text: str) -> str:
    prepared = prepare_filing_text(extractor, raw_text)
    return hashlib.sha256(prepared.encode("utf-8")).hexdigest()


def validate_filing_source(extractor: str, source_id: str, as_of: str, url: str) -> None:
    """Require an exact public SEC/DART source identity before cache use."""
    if extractor not in EXTRACTOR_LIMITS:
        raise FilingExtractionCacheError("unsupported_extractor")
    try:
        date.fromisoformat(as_of)
    except (TypeError, ValueError):
        raise FilingExtractionCacheError("invalid_source_as_of") from None

    try:
        parsed = urlparse(str(url or ""))
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:
        raise FilingExtractionCacheError("nonpublic_source_url") from None
    if parsed.scheme != "https" or parsed.username or parsed.password or port not in (None, 443) or parsed.fragment:
        raise FilingExtractionCacheError("nonpublic_source_url")

    if extractor == "sec-properties-v1":
        match = _SEC_SOURCE_RE.fullmatch(str(source_id or ""))
        if not match or host != "www.sec.gov" or not parsed.path.startswith("/Archives/") or parsed.query:
            raise FilingExtractionCacheError("source_identity_mismatch")
        if match.group(1).replace("-", "") not in parsed.path:
            raise FilingExtractionCacheError("source_identity_mismatch")
    else:
        match = _DART_SOURCE_RE.fullmatch(str(source_id or ""))
        query = parse_qs(parsed.query, keep_blank_values=True)
        if (
            not match
            or host != "dart.fss.or.kr"
            or parsed.path != "/dsaf001/main.do"
            or set(query) != {"rcpNo"}
            or query.get("rcpNo") != [match.group(1)]
        ):
            raise FilingExtractionCacheError("source_identity_mismatch")


def filing_cache_key(extractor: str, source_id: str, as_of: str, raw_sha256: str) -> str:
    if extractor not in EXTRACTOR_LIMITS or not _SHA256_RE.fullmatch(str(raw_sha256 or "")):
        raise FilingExtractionCacheError("invalid_cache_key_input")
    material = "\0".join((extractor, str(source_id), str(as_of), raw_sha256))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def filing_cache_path(
    extractor: str,
    source_id: str,
    as_of: str,
    raw_sha256: str,
    *,
    cache_root: Path | str = DEFAULT_CACHE_ROOT,
) -> Path:
    key = filing_cache_key(extractor, source_id, as_of, raw_sha256)
    return Path(cache_root) / extractor / f"{key}.json"


def _reject_constant(value: str) -> None:
    raise FilingExtractionCacheError(f"invalid_json_constant:{value}")


def _object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise FilingExtractionCacheError("duplicate_json_key")
        value[key] = item
    return value


def _valid_rfc3339(value: Any) -> bool:
    if not isinstance(value, str) or not value.endswith(("Z", "+00:00")):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def validate_filing_cache(
    value: Mapping[str, Any],
    *,
    extractor: str,
    source_id: str,
    as_of: str,
    raw_sha256: str,
    url: str,
) -> dict[str, Any]:
    """Validate an envelope and its exact binding; return a plain copy."""
    validate_filing_source(extractor, source_id, as_of, url)
    if not isinstance(value, Mapping) or set(value) != _TOP_LEVEL_KEYS:
        raise FilingExtractionCacheError("invalid_envelope_keys")
    source = value.get("source")
    if not isinstance(source, Mapping) or set(source) != _SOURCE_KEYS:
        raise FilingExtractionCacheError("invalid_source_keys")
    expected_source = {
        "source_id": source_id,
        "as_of": as_of,
        "raw_sha256": raw_sha256,
        "url": url,
    }
    if dict(source) != expected_source:
        raise FilingExtractionCacheError("cache_binding_mismatch")
    if value.get("schema") != CACHE_SCHEMA or value.get("extractor") != extractor:
        raise FilingExtractionCacheError("cache_schema_mismatch")
    if value.get("status") != "ready" or value.get("generator") != "codex-cli":
        raise FilingExtractionCacheError("cache_status_mismatch")
    if not _valid_rfc3339(value.get("generated_at")):
        raise FilingExtractionCacheError("invalid_generated_at")
    if not isinstance(value.get("data"), dict):
        raise FilingExtractionCacheError("invalid_cache_data")
    return dict(value)


def _assert_cache_path_safe(path: Path, cache_root: Path) -> None:
    root = cache_root.absolute()
    candidate = path.absolute()
    if root.is_symlink() or candidate.is_symlink():
        raise FilingExtractionCacheError("cache_symlink_rejected")
    if candidate.parent != root / candidate.parent.name:
        raise FilingExtractionCacheError("cache_path_escape")
    if candidate.parent.exists() and candidate.parent.is_symlink():
        raise FilingExtractionCacheError("cache_symlink_rejected")


def cache_read(
    *,
    extractor: str,
    source_id: str,
    as_of: str,
    raw_sha256: str,
    url: str,
    cache_root: Path | str = DEFAULT_CACHE_ROOT,
) -> dict[str, Any] | None:
    validate_filing_source(extractor, source_id, as_of, url)
    root = Path(cache_root)
    path = filing_cache_path(extractor, source_id, as_of, raw_sha256, cache_root=root)
    _assert_cache_path_safe(path, root)
    if not path.exists():
        return None
    stat = path.stat()
    if not path.is_file() or stat.st_size > CACHE_MAX_BYTES:
        raise FilingExtractionCacheError("cache_size_invalid")
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_object_no_duplicates,
            parse_constant=_reject_constant,
        )
    except FilingExtractionCacheError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise FilingExtractionCacheError("cache_json_invalid") from None
    return validate_filing_cache(
        value,
        extractor=extractor,
        source_id=source_id,
        as_of=as_of,
        raw_sha256=raw_sha256,
        url=url,
    )


def cache_write(
    *,
    extractor: str,
    source_id: str,
    as_of: str,
    raw_sha256: str,
    url: str,
    generated_at: str,
    data: Mapping[str, Any],
    cache_root: Path | str = DEFAULT_CACHE_ROOT,
) -> Path:
    """Atomically write one validated Codex CLI result; no model is invoked."""
    envelope = {
        "schema": CACHE_SCHEMA,
        "extractor": extractor,
        "source": {
            "source_id": source_id,
            "as_of": as_of,
            "raw_sha256": raw_sha256,
            "url": url,
        },
        "status": "ready",
        "generated_at": generated_at,
        "generator": "codex-cli",
        "data": dict(data),
    }
    validate_filing_cache(
        envelope,
        extractor=extractor,
        source_id=source_id,
        as_of=as_of,
        raw_sha256=raw_sha256,
        url=url,
    )
    encoded = (json.dumps(envelope, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    if len(encoded) > CACHE_MAX_BYTES:
        raise FilingExtractionCacheError("cache_size_invalid")

    root = Path(cache_root)
    path = filing_cache_path(extractor, source_id, as_of, raw_sha256, cache_root=root)
    _assert_cache_path_safe(path, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    _assert_cache_path_safe(path, root)
    fd, temp_name = tempfile.mkstemp(prefix=".filing-cache-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
    return path
