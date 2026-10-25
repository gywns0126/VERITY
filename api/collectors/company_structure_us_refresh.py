"""Bounded SEC subsidiary exhibits (10-K EX-21 / 20-F EX-8.1), deduped by CIK.

Missing/stale local submissions are fetched only with explicit fetch_public.
Metadata check time and filing dates are separate. No submission raw bodies,
bulk ZIPs, ownership percentages or direct-parent conclusions are persisted.
"""
from __future__ import annotations

import copy
import gzip
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import urlsplit
import urllib.error
import urllib.request
import zlib

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "alphanest-company-structure-us-sources-v1"
MAX_CIKS, MAX_HTTP, MAX_BYTES = 800, 2400, 8 * 1024 * 1024
MAX_RAW_CACHE_BYTES = 256 * 1024 * 1024
MAX_ELAPSED_SECONDS = 1800
MAX_REPLAY_CIKS, MAX_REPLAY_SECONDS = 160, 120
TTL = timedelta(days=7)
KST = timezone(timedelta(hours=9))
BUDGET_STOPS = frozenset({"daily-http-budget", "daily-cik-budget", "daily-cik-already-attempted", "time-budget"})


class BudgetDeferred(RuntimeError):
    """Expected bounded partial; never a source failure."""


def read_json(path, maximum=MAX_BYTES):
    path = Path(path)
    if maximum is not None and path.stat().st_size > maximum:
        raise ValueError("sec-local-source-size")
    return json.loads(path.read_bytes())


def atomic_json(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _headers():
    # Same public contact identity and no Accept-Encoding as sec_companyfacts_bulk.
    # Kept local to avoid importing its api.config/credential bootstrap.
    return {"User-Agent": "VERITY research gywns0126@gmail.com"}


def get_public(url, maximum=MAX_BYTES):
    """Capture helper's bounded urllib/no-redirect contract, without CLI imports."""
    if not (re.fullmatch(r"https://data\.sec\.gov/submissions/CIK[0-9]{10}\.json", url)
            or re.fullmatch(r"https://www\.sec\.gov/Archives/edgar/data/[0-9]+/[0-9]{18}/[A-Za-z0-9_.-]+\.(?:html?|txt)", url)):
        raise ValueError("sec-url-rejected")
    if not 0 < maximum <= MAX_BYTES:
        raise ValueError("sec-response-size")

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise ValueError("sec-redirect-rejected")

    with urllib.request.build_opener(NoRedirect()).open(
            urllib.request.Request(url, headers=_headers()), timeout=30) as response:
        raw = response.read(maximum + 1)
    if not raw or len(raw) > maximum:
        raise ValueError("sec-response-size")
    return raw


def _valid_exhibit_url(url, cik, accession, proof=None):
    """Validate an exact filing-bound SEC document URL, including co-filers."""
    if (not isinstance(cik, str) or not re.fullmatch(r"[0-9]{10}", cik)
            or not isinstance(accession, str) or not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession)
            or not isinstance(url, str) or len(url) > 2048):
        return False
    try:
        parts = urlsplit(url)
        if (parts.scheme != "https" or parts.netloc != "www.sec.gov" or parts.query or parts.fragment
                or "?" in url or "#" in url
                or not parts.path.startswith("/Archives/edgar/data/")
                or re.search(r"%(?:2f|5c|2e)", url, re.I) or "\\" in parts.path
                or any(piece in (".", "..") for piece in parts.path.split("/"))):
            return False
        match = re.fullmatch(
            r"/Archives/edgar/data/([1-9][0-9]{0,9})/([0-9]{18})/([A-Za-z0-9_.-]+\.(?:htm|html|txt))",
            parts.path, re.I)
        if not match or match.group(2) != accession.replace("-", ""):
            return False
        archive_cik = match.group(1)
        if archive_cik == str(int(cik)) or accession[:10] == cik:
            return proof is None
        return (isinstance(proof, dict) and set(proof) == {"requestedCik", "archiveCik",
                "accession", "issuerName", "exhibitUrl", "indexSha256"}
                and proof.get("requestedCik") == cik
                and proof.get("archiveCik") == archive_cik
                and proof.get("accession") == accession and proof.get("exhibitUrl") == url
                and isinstance(proof.get("issuerName"), str)
                and isinstance(proof.get("indexSha256"), str)
                and re.fullmatch(r"[0-9a-f]{64}", proof.get("indexSha256", "")) is not None)
    except (ValueError, UnicodeError):
        return False


def _ticker_variants(ticker):
    """Only the separator before a final single class letter is equivalent."""
    if not isinstance(ticker, str) or not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,11}", ticker):
        return ()
    match = re.fullmatch(r"([A-Z][A-Z0-9]*)([.-])([A-Z])", ticker)
    if not match:
        return (ticker,)
    other = match[1] + ("-" if match[2] == "." else ".") + match[3]
    return (ticker, other)


def _submission_has_ticker(submission, ticker):
    tickers = submission.get("tickers", [])
    return isinstance(tickers, list) and any(value in tickers for value in _ticker_variants(ticker))


def _mapped_cik(value):
    if isinstance(value, dict):
        value = value.get("cik") or value.get("cik_str")
    if type(value) not in (int, str) or not re.fullmatch(r"[0-9]{1,10}", str(value)):
        return None
    return str(value).zfill(10) if int(value) > 0 else None


def latest_metadata(ticker, cik, submission):
    """Same annual selection/identity/amendment checks as capture-sec-relationships."""
    from api.intelligence.portfolio_sec_relationships import validate_sec_capture
    if str(submission.get("cik", "")).zfill(10) != cik or not _submission_has_ticker(submission, ticker):
        raise ValueError("sec-submission-identity")
    recent = submission.get("filings", {}).get("recent", {})
    fields = ("form", "filingDate", "reportDate", "accessionNumber", "primaryDocument")
    if (not isinstance(recent, dict) or any(not isinstance(recent.get(k), list) for k in fields)
            or len({len(recent[k]) for k in fields}) != 1
            or any(not isinstance(v, str) for k in fields for v in recent[k])):
        raise ValueError("sec-submission-shape")
    # Select the newest annual before checking support. A modern 40-F must
    # never silently fall back to a decades-old 20-F / paper filing.
    eligible = [i for i, form in enumerate(recent["form"]) if form in ("10-K", "20-F", "40-F")]
    if not eligible:
        raise ValueError("source-gap:annual-missing")
    i = max(eligible, key=lambda j: (recent["filingDate"][j], recent["accessionNumber"][j]))
    if recent["form"][i] == "40-F":
        raise ValueError("source-gap:annual-form-40f-needs-review")
    if any(form in ("10-K/A", "20-F/A") and recent["filingDate"][j] >= recent["filingDate"][i]
           for j, form in enumerate(recent["form"])):
        raise ValueError("source-gap:amendment-needs-review")
    accession = recent["accessionNumber"][i]
    if recent["primaryDocument"][i].endswith(".paper"):
        raise ValueError("source-gap:annual-paper-document")
    metadata = {"issuer_id": "US:" + ticker, "issuer_name": submission["name"], "cik": cik,
                "accession": accession, "filed_date": recent["filingDate"][i],
                "period_end": recent["reportDate"][i], "form": recent["form"][i],
                "primary_document": recent["primaryDocument"][i],
                "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{recent['primaryDocument'][i]}"}
    validate_sec_capture({**metadata, "schema": "sec-annual-excerpts-v1", "document_sha256": "0" * 64, "paragraphs": []})
    return metadata


def load_helpers():
    parser = _module(ROOT / "api/intelligence/company_structure_sec.py", "_us_structure_parser")
    return SimpleNamespace(get_public=get_public, latest_metadata=latest_metadata,
                           find_exhibit=parser.find_exhibit, parse_exhibit=parser.parse_exhibit)


def _time(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result if result.tzinfo else None
    except (ValueError, TypeError, AttributeError):
        return None


def _data_dir(source_dir):
    path = Path(source_dir).resolve()
    return path if (path / "universe_search.json").is_file() else path / "data"


def _submission_path(source_dir, cik):
    data = _data_dir(source_dir)
    for name in (f"CIK{cik}.json", f"{cik}.json"):
        candidate = data / "sec_submissions_cache" / name
        if candidate.is_file():
            if data not in candidate.resolve().parents:
                raise ValueError("sec-cache-outside-source-dir")
            return candidate
    return None


def _raw_cache_path(directory, digest):
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("sec-raw-cache-binding")
    directory = Path(directory)
    if any(part.is_symlink() for part in (directory, *directory.parents)) or (directory.exists() and not directory.is_dir()):
        raise ValueError("sec-raw-cache-path")
    return directory / (digest + ".gz")


def _read_raw_exhibit(directory, digest):
    path = _raw_cache_path(directory, digest)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise ValueError("sec-raw-cache-path")
            if os.fstat(handle.fileno()).st_size > MAX_BYTES + 65536:
                raise ValueError("sec-raw-cache-size")
            with gzip.GzipFile(fileobj=io.BytesIO(handle.read()), mode="rb") as zipped:
                raw = zipped.read(MAX_BYTES + 1)
    except FileNotFoundError:
        raise
    except (OSError, EOFError, gzip.BadGzipFile, zlib.error) as exc:
        raise ValueError("sec-raw-cache-invalid") from exc
    if not raw or len(raw) > MAX_BYTES or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("sec-raw-cache-mismatch")
    return raw


def _save_raw_exhibit(directory, raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_BYTES:
        raise ValueError("sec-raw-cache-size")
    digest = hashlib.sha256(raw).hexdigest()
    path = _raw_cache_path(directory, digest)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        _read_raw_exhibit(directory, digest)
        return digest, False, False
    compressed = gzip.compress(raw, mtime=0)
    total = 0
    with os.scandir(path.parent) as entries:
        for entry in entries:
            info = entry.stat(follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("sec-raw-cache-path")
            total += info.st_size
    if total + len(compressed) > MAX_RAW_CACHE_BYTES:
        return digest, False, True
    fd, temp = tempfile.mkstemp(prefix=digest + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(compressed)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp, path)  # Atomic create; never replace another writer's blob.
        except FileExistsError:
            _read_raw_exhibit(directory, digest)
            return digest, False, False
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return digest, True, False


def _review_cache_binding(issuer, cik, metadata, review):
    binding = issuer.get("rawExhibitCache")
    expected = {"cik": cik, "accession": metadata["accession"], "filedDate": metadata["filed_date"],
                "periodEnd": metadata["period_end"], "url": review.get("url"),
                "documentSha256": review.get("documentSha256")}
    proof = review.get("cofilerProof")
    if proof is not None:
        expected["cofilerProof"] = proof
    if ((binding is not None and binding != expected)
            or review.get("cik") != cik or review.get("accession") != metadata["accession"]
            or review.get("filedDate") != metadata["filed_date"]
            or review.get("periodEnd") != metadata["period_end"]
            or not _valid_exhibit_url(review.get("url"), cik, metadata["accession"], proof)
            or (proof is not None and (not isinstance(proof, dict)
                or proof.get("issuerName") != metadata["issuer_name"]))):
        raise ValueError("sec-raw-cache-binding")
    return expected


def _parse_raw_exhibit(raw, cik, metadata, exhibit_url, helpers, proof=None, index_raw=None):
    parse_metadata = {"cik": cik, "accession": metadata["accession"],
        "filedDate": metadata["filed_date"], "periodEnd": metadata["period_end"], "url": exhibit_url,
        "issuerName": metadata["issuer_name"], "form": metadata["form"]}
    if proof is not None:
        parse_metadata.update(cofilerProof=proof, cofilerIndexRaw=index_raw)
    parsed = helpers.parse_exhibit(raw, parse_metadata)
    if not isinstance(parsed, dict) or any(parsed.get(key) != value for key, value in {
            "cik": cik, "accession": metadata["accession"], "filedDate": metadata["filed_date"],
            "periodEnd": metadata["period_end"], "url": exhibit_url,
            "documentSha256": hashlib.sha256(raw).hexdigest(), "cofilerProof": proof}.items()
            if key != "cofilerProof" or proof is not None):
        raise ValueError("sec-raw-cache-parse-mismatch")
    return parsed


def reparse_cached_reviews(document, raw_cache_dir, now=None, helpers=None, current_ciks=None,
                           limit=MAX_REPLAY_CIKS, max_elapsed_seconds=MAX_REPLAY_SECONDS,
                           clock=time.monotonic, checkpoint=None):
    """Bound offline replay independently of collection; preserve source clocks."""
    if raw_cache_dir is None:
        raise ValueError("sec-raw-cache-required")
    if type(limit) is not int or not 0 <= limit <= MAX_REPLAY_CIKS:
        raise ValueError("sec-replay-limit-invalid")
    if (type(max_elapsed_seconds) not in (int, float) or not math.isfinite(max_elapsed_seconds)
            or not 0 <= max_elapsed_seconds <= MAX_REPLAY_SECONDS):
        raise ValueError("sec-replay-time-budget-invalid")
    started = clock()
    from api.intelligence.company_structure_sec import PARSER_REVISION
    helpers = helpers or load_helpers()
    result = copy.deepcopy(document)
    lists = {key: [] for key in ("eligible", "attempted", "cacheHits", "missing", "parsed", "held", "errors", "deferred")}
    ciks = current_ciks if current_ciks is not None else result.get("currentCiks")
    if not isinstance(ciks, list) or any(cik not in result.get("issuers", {}) for cik in ciks):
        raise ValueError("sec-current-ciks-required")
    for cik in ciks:
        issuer = result["issuers"][cik]
        review = issuer.get("reviewExhibit")
        if not (issuer.get("attemptStatus") == "needs-review" and isinstance(review, dict)
                and review.get("status") == "needs-review" and review.get("parserRevision") != PARSER_REVISION):
            continue
        lists["eligible"].append(cik)
    stop = None
    for index, cik in enumerate(lists["eligible"]):
        if len(lists["cacheHits"]) >= limit or clock() - started >= max_elapsed_seconds:
            stop = "replay-limit" if len(lists["cacheHits"]) >= limit else "time-budget"
            lists["deferred"] = lists["eligible"][index:]
            break
        issuer = result["issuers"][cik]
        review = issuer["reviewExhibit"]
        lists["attempted"].append(cik)
        metadata = issuer.get("filingMetadata")
        try:
            if not isinstance(metadata, dict):
                raise ValueError("sec-raw-cache-binding")
            binding = _review_cache_binding(issuer, cik, metadata, review)
            try:
                proof = binding.get("cofilerProof")
                index_raw = (_read_raw_exhibit(raw_cache_dir, proof["indexSha256"])
                             if proof is not None else None)
                raw = _read_raw_exhibit(raw_cache_dir, binding["documentSha256"])
            except FileNotFoundError:
                lists["missing"].append(cik)
                continue
            if clock() - started >= max_elapsed_seconds:
                stop = "time-budget"
                lists["deferred"] = lists["eligible"][index:]
                break
            lists["cacheHits"].append(cik)
            parsed = _parse_raw_exhibit(raw, cik, metadata, binding["url"], helpers, proof, index_raw)
            if parsed.get("status") == "parsed":
                observed = _time(issuer.get("attemptedAt"))
                filed = _time(metadata["filed_date"] + "T00:00:00Z")
                if not observed or not filed or observed < filed:
                    raise ValueError("sec-replay-observation-invalid")
                issuer.pop("reviewExhibit", None)
                issuer.update(exhibit=parsed, attemptStatus="success", sourceGap=None,
                              lastSuccessAt=issuer["attemptedAt"])
                lists["parsed"].append(cik)
            elif parsed.get("status") == "needs-review":
                issuer["reviewExhibit"] = parsed
                issuer["sourceGap"] = "source-gap:ex21-needs-review"
                lists["held"].append(cik)
            else:
                raise ValueError("sec-raw-cache-parse-mismatch")
        except (ValueError, KeyError, TypeError, OSError) as exc:
            reason = str(exc) if isinstance(exc, ValueError) and re.fullmatch(r"sec-[a-z0-9-]+", str(exc)) else "sec-raw-cache-error"
            lists["errors"].append({"cik": cik, "reason": reason})
            continue
        if checkpoint is not None:
            checkpoint(result)  # A durable-write failure must stop, not look like a bad exhibit.
    summary = {"schema": "alphanest-company-structure-us-cache-replay-summary-v1",
               "generatedAt": (now or datetime.now(timezone.utc)).isoformat(),
               "stopReason": stop, "limit": limit, "maxElapsedSeconds": max_elapsed_seconds,
               "elapsedSeconds": max(0, clock() - started),
               **{key: len(value) for key, value in lists.items()}, "lists": lists,
               "exitCode": int(bool(lists["errors"]))}
    return result, summary


def build_document(source_dir, existing=None, now=None):
    now = now or datetime.now(timezone.utc)
    data = _data_dir(source_dir)
    universe = read_json(data / "universe_search.json").get("stocks", [])
    universe = list(universe.values()) if isinstance(universe, dict) else universe
    mapping = read_json(data / "sec_ticker_cik_map.json")
    reviewed_path = data / "member_map_company_structure_aliases.json"
    reviewed = read_json(reviewed_path) if reviewed_path.is_file() else {}
    if reviewed and reviewed.get("schema") != "alphanest-company-structure-reviewed-ticker-aliases-v1":
        raise ValueError("sec-reviewed-alias-schema")
    if not isinstance(universe, list) or not isinstance(mapping, dict):
        raise ValueError("sec-universe-shape")
    document = copy.deepcopy(existing or {})
    if document and document.get("schema") != SCHEMA:
        raise ValueError("sec-store-schema")
    document.setdefault("issuers", {})
    aliases, unmapped = {}, {}
    tickers = sorted({r["ticker"] for r in universe if isinstance(r, dict)
                      and r.get("market") == "US" and isinstance(r.get("ticker"), str)})
    eligible_current = {r["ticker"] for r in universe if isinstance(r, dict)
                        and r.get("market") == "US" and isinstance(r.get("ticker"), str)
                        and re.fullmatch(r"[A-Z][A-Z0-9.-]{0,11}", r["ticker"])
                        and not any(kind in str(r.get("type") or r.get("kind") or r.get("asset_type") or "").upper()
                                    for kind in ("ETF", "ETN", "INDEX"))
                        and not re.search(r"\bETF\b", str(r.get("name") or ""))}
    for ticker in tickers:
        candidates = {_mapped_cik(mapping[key]) for key in _ticker_variants(ticker) if key in mapping}
        # Reviewed same-issuer renames only. Never override an existing/invalid
        # mapping, follow alias chains, or turn a CIK into a source success.
        if not candidates:
            alias = reviewed.get("aliases", {}).get(ticker, {})
            current = alias.get("currentTicker")
            effective = alias.get("effectiveDate")
            expected = _mapped_cik(alias.get("cik"))
            checked = _time(alias.get("reviewedAt"))
            if (alias.get("kind") == "same-issuer-ticker-change" and current != ticker
                    and current in eligible_current and expected and checked and checked <= now
                    and isinstance(effective, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", effective)
                    and _time(effective + "T00:00:00Z") and effective <= now.date().isoformat()
                    and isinstance(alias.get("sources"), list) and len(alias["sources"]) >= 2
                    and f"https://data.sec.gov/submissions/CIK{expected}.json" in alias["sources"]):
                current_candidates = {_mapped_cik(mapping[key]) for key in _ticker_variants(current) if key in mapping}
                if current_candidates == {expected}:
                    candidates = {expected}
        if None in candidates:
            unmapped[ticker] = "source-gap:cik-invalid"
            continue
        if len(candidates) != 1:
            unmapped[ticker] = "source-gap:cik-ambiguous" if candidates else "source-gap:cik-missing"
            continue
        cik = next(iter(candidates))
        aliases.setdefault(cik, []).append(ticker)
    for cik, tickers_for_cik in aliases.items():
        item = document["issuers"].setdefault(cik, {"cik": cik, "attemptStatus": "not-attempted", "attemptedAt": None})
        item["tickerAliases"] = tickers_for_cik
        metadata_checked = _time(item.get("metadataCheckedAt"))
        cached_metadata = metadata_checked and timedelta(0) <= now - metadata_checked < TTL and item.get("filingMetadata")
        item["sourceGap"] = (None if _submission_path(source_dir, cik) or cached_metadata
                             else "source-gap:local-submissions-missing-fetch-required")
    document.update(schema=SCHEMA, generatedAt=now.isoformat(), universe={"US": tickers},
                    currentCiks=sorted(aliases), unmapped=unmapped)
    return document


def _new_local_submission(issuer, source_dir, now):
    """A newer validated local filing can supersede the seven-day check cache."""
    if source_dir is None:
        return False
    try:
        path = _submission_path(source_dir, issuer["cik"])
        if path is None:
            return False
        observed = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    except (OSError, ValueError):
        return False  # The bounded issuer refresh reports invalid local sources.
    checked = _time(issuer.get("metadataCheckedAt"))
    if not timedelta(0) <= now - observed < TTL or (checked and observed <= checked):
        return False
    try:
        submission = read_json(path)
        tickers = sorted(t for t in issuer["tickerAliases"] if _submission_has_ticker(submission, t))
        if not tickers:
            return False
        metadata = latest_metadata(tickers[0], issuer["cik"], submission)
        old = issuer.get("filingMetadata") or {}
        return any(metadata.get(k) != old.get(k) for k in
                   ("accession", "form", "filed_date", "period_end", "issuer_name"))
    except ValueError as exc:
        # A new unsupported annual/amendment must replace the *status*, not
        # silently leave an older filing looking up-to-date. Identity errors
        # do not make another issuer's cache a valid change signal.
        return str(exc).startswith("source-gap:")
    except (KeyError, TypeError, OSError):
        return False


def _refresh_lane(issuer, local_changed=False):
    if local_changed:
        return "fresh"
    status = issuer.get("attemptStatus", "not-attempted")
    if status in ("not-attempted", "success", "cached-same-accession"):
        return "fresh"
    if status == "budget-deferred" and not issuer.get("reviewExhibit"):
        return "fresh"
    return "backlog"


def _due_issuers(document, now, source_dir=None, defer_reviews=False, excluded=()):
    from api.intelligence.company_structure_sec import PARSER_REVISION
    lanes = {"fresh": [], "backlog": []}
    reserved = set(excluded)
    for cik in document["currentCiks"]:
        if cik in reserved:
            continue
        issuer = document["issuers"][cik]
        review = issuer.get("reviewExhibit")
        revised_review = (not defer_reviews and issuer.get("attemptStatus") == "needs-review" and isinstance(review, dict)
                          and review.get("status") == "needs-review"
                          and review.get("parserRevision") != PARSER_REVISION)
        local_changed = _new_local_submission(issuer, source_dir, now)
        checked = _time(issuer.get("checkedAt"))
        if not local_changed and not revised_review and checked and timedelta(0) <= now - checked < TTL:
            continue
        # Missing exhibits/source gaps cannot permanently outrank healthy stale
        # issuers. Historical success is an attempt fallback for legacy stores.
        attempted = _time(issuer.get("attemptedAt")) or _time(issuer.get("lastSuccessAt"))
        lanes[_refresh_lane(issuer, local_changed)].append(
            (not local_changed, attempted is not None,
             attempted or datetime.min.replace(tzinfo=timezone.utc), cik))
    fresh, backlog = ([row[-1] for row in sorted(lanes[key])] for key in ("fresh", "backlog"))
    # Four ordinary/new-filing checks followed by one backlog check. Interleave
    # rather than concatenate: both lanes progress even at a soft deadline.
    # Unused capacity is borrowed when either lane is empty; total caps stay put.
    due = []
    for i in range(max((len(fresh) + 3) // 4, len(backlog))):
        due.extend(fresh[4 * i:4 * i + 4])
        due.extend(backlog[i:i + 1])
    return due


def _selection(document, now, limit, excluded=(), source_dir=None, defer_reviews=False):
    if type(limit) is not int or not 0 <= limit <= MAX_CIKS:
        raise ValueError(f"CIK limit must be 0..{MAX_CIKS}")
    return _due_issuers(document, now, source_dir, defer_reviews, excluded)[:limit]


def refresh(document, *, source_dir, limit=MAX_CIKS, fetch_public=False, checkpoint=None,
            now=None, helpers=None, clock=time.monotonic, sleep=time.sleep,
            max_elapsed_seconds=MAX_ELAPSED_SECONDS, raw_cache_dir=None, defer_reviews=False):
    """Stop new work at a monotonic soft deadline, preserving reservations/results.

    An already-started HTTP request is not cancelled by this deadline: its 30s
    transport timeout can extend collection beyond the deadline (up to 30s for
    a single bounded request). Parsing/checkpoint time is additional; urllib's
    socket timeout is not a strict total-response wall-clock guarantee.
    """
    if (type(max_elapsed_seconds) not in (int, float) or not math.isfinite(max_elapsed_seconds)
            or max_elapsed_seconds < 0):
        raise ValueError("sec-time-budget-invalid")
    started = clock()
    now = now or datetime.now(timezone.utc)
    stamp, day = now.isoformat(), now.astimezone(KST).date().isoformat()
    document = copy.deepcopy(document)
    previous = document.get("requestBudget", {})
    budget = copy.deepcopy(previous) if previous.get("day") == day else {"day": day, "requests": 0, "ciks": []}
    if (type(budget.get("requests")) is not int or not 0 <= budget["requests"] <= MAX_HTTP
            or not isinstance(budget.get("ciks"), list) or len(set(budget["ciks"])) != len(budget["ciks"])
            or len(budget["ciks"]) > MAX_CIKS
            or any(not isinstance(c, str) or not re.fullmatch(r"[0-9]{10}", c) for c in budget["ciks"])):
        raise ValueError("sec-durable-budget-invalid")
    selected = _selection(document, now, limit, excluded=budget["ciks"],
                          source_dir=source_dir, defer_reviews=defer_reviews)
    due = _due_issuers(document, now, source_dir, defer_reviews)
    lane_by_cik = {c: _refresh_lane(document["issuers"][c],
                   _new_local_submission(document["issuers"][c], source_dir, now)) for c in due}
    # Same-day attempts are never retried, including interrupted reservations.
    selected = selected[:MAX_CIKS - len(budget["ciks"])]
    lists = {k: [] for k in ("attempted", "requests", "success", "cached", "sourceGap", "error", "retained", "budgetDeferred", "deferred", "rawCacheHit", "rawCacheSaved", "rawCacheSkipped")}
    lists["selected"] = selected
    summary = {"schema": "alphanest-company-structure-us-refresh-summary-v1", "generatedAt": stamp,
               "dryRun": not fetch_public, "requestedTickers": len(document["universe"]["US"]),
               "requestedCiks": len(document["currentCiks"]), "unmapped": document["unmapped"],
               "stopReason": None, "published": False}

    def time_exhausted():
        if clock() - started >= max_elapsed_seconds:
            summary["stopReason"] = "time-budget"
            return True
        return False

    if not fetch_public:
        lists["sourceGap"] = [{"cik": c, "reason": document["issuers"][c]["sourceGap"]}
                              for c in document["currentCiks"] if document["issuers"][c].get("sourceGap")]
    if fetch_public and selected:
        if checkpoint is None:
            raise ValueError("sec-durable-checkpoint-required")
        helpers = helpers or load_helpers()
        last_get = None

        def get(url, cik, allowed):
            nonlocal last_get
            if url not in allowed:
                raise ValueError("sec-url-not-generated")
            if budget["requests"] >= MAX_HTTP:
                summary["stopReason"] = "daily-http-budget"
                raise BudgetDeferred()
            if time_exhausted():
                raise BudgetDeferred()
            budget["requests"] += 1
            document["requestBudget"] = copy.deepcopy(budget)
            checkpoint(document)  # Reserve before the one physical GET.
            if time_exhausted():
                raise BudgetDeferred()  # Keep the reservation even without a GET.
            # Checkpoint latency must not collapse physical GET start spacing.
            if last_get is not None:
                sleep(max(0, 0.5 - (clock() - last_get)))
            if time_exhausted():
                raise BudgetDeferred()
            last_get = clock()
            lists["requests"].append({"cik": cik, "url": url})
            raw = helpers.get_public(url, MAX_BYTES)
            if not isinstance(raw, bytes) or not raw or len(raw) > MAX_BYTES:
                raise ValueError("sec-response-size")
            return raw

        for cik in selected:
            if summary["stopReason"] or time_exhausted():
                break
            issuer = document["issuers"][cik]
            budget["ciks"].append(cik)
            document["requestBudget"] = copy.deepcopy(budget)
            issuer.update(attemptStatus="attempting", attemptedAt=stamp)
            checkpoint(document)  # CIK reservation also survives crashes.
            lists["attempted"].append(cik)
            try:
                metadata = issuer.get("filingMetadata")
                metadata_checked = _time(issuer.get("metadataCheckedAt"))
                if (_new_local_submission(issuer, source_dir, now) or not (isinstance(metadata, dict) and metadata_checked and timedelta(0) <= now - metadata_checked < TTL
                        and metadata.get("cik") == cik and metadata.get("issuer_id", "")[3:] in issuer["tickerAliases"])):
                    path = _submission_path(source_dir, cik)
                    cached_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) if path else None
                    if path and timedelta(0) <= now - cached_at < TTL:
                        submission = read_json(path)
                        metadata_checked = cached_at
                        issuer["metadataSource"] = "local-submissions-cache"
                    else:
                        # Include submissions, index and EX-21 in ONE daily HTTP budget.
                        if MAX_HTTP - budget["requests"] < 3:
                            summary["stopReason"] = "daily-http-budget"
                            raise BudgetDeferred()
                        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
                        submission = json.loads(get(url, cik, {url}))
                        metadata_checked = now
                        issuer["metadataSource"] = "sec-submissions"
                    candidates = sorted(ticker for ticker in issuer["tickerAliases"]
                                        if _submission_has_ticker(submission, ticker))
                    if not candidates:
                        raise ValueError("source-gap:representative-ticker-missing")
                    metadata = helpers.latest_metadata(candidates[0], cik, submission)
                    # Only minimal filing metadata survives, never submission body.
                    issuer.update(filingMetadata=metadata, metadataCheckedAt=metadata_checked.isoformat(),
                                  representativeTicker=candidates[0])
                    checkpoint(document)
                old = issuer.get("reviewExhibit") or issuer.get("exhibit")
                reusable = isinstance(old, dict) and old.get("status") == "parsed"
                if isinstance(old, dict) and old.get("status") == "needs-review":
                    from api.intelligence.company_structure_sec import PARSER_REVISION
                    reusable = defer_reviews or old.get("parserRevision") == PARSER_REVISION
                if (isinstance(old, dict) and old.get("cik") == cik and old.get("accession") == metadata["accession"]
                        and reusable):
                    issuer.update(attemptStatus="cached-same-accession" if old["status"] == "parsed" else "needs-review",
                                  checkedAt=stamp, sourceGap=None if old["status"] == "parsed" else "source-gap:ex21-needs-review")
                    lists["cached"].append(cik)
                else:
                    accession = metadata["accession"]
                    if not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession):
                        raise ValueError("sec-accession-invalid")
                    from api.intelligence.company_structure_sec import PARSER_REVISION
                    revised = (isinstance(old, dict) and old.get("status") == "needs-review"
                               and old.get("parserRevision") != PARSER_REVISION)
                    same_filing_review = (revised and old.get("cik") == cik and old.get("accession") == accession)
                    raw = None
                    proof = None
                    index_raw = None
                    if raw_cache_dir is not None and same_filing_review:
                        binding = _review_cache_binding(issuer, cik, metadata, old)
                        if time_exhausted():
                            raise BudgetDeferred()
                        try:
                            raw = _read_raw_exhibit(raw_cache_dir, binding["documentSha256"])
                        except FileNotFoundError:
                            pass  # Cache eviction: bounded normal GET remains available.
                        if raw is not None:
                            exhibit_url = binding["url"]
                            proof = binding.get("cofilerProof")
                            if proof is not None:
                                try:
                                    index_raw = _read_raw_exhibit(raw_cache_dir, proof["indexSha256"])
                                except FileNotFoundError:
                                    # The public store retains the proof, not the
                                    # cache binding. Refetch the bounded filing
                                    # index and exhibit when its proof is evicted.
                                    raw, proof = None, None
                            if raw is not None:
                                lists["rawCacheHit"].append(cik)
                    if raw is None:
                        if MAX_HTTP - budget["requests"] < 2:
                            summary["stopReason"] = "daily-http-budget"
                            raise BudgetDeferred()
                        directory = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/"
                        index_url = directory + accession + "-index.html"
                        index = get(index_url, cik, {index_url})
                        try:
                            exhibit_url = helpers.find_exhibit(index, cik=cik, accession=accession,
                                                               form=metadata["form"])
                        except ValueError as exc:
                            if str(exc) != "sec-cofiler-issuer-needs-review":
                                raise
                            exhibit_url, proof = helpers.find_exhibit(index, cik=cik, accession=accession,
                                form=metadata["form"], issuer_name=metadata["issuer_name"], return_proof=True)
                            if proof is None or raw_cache_dir is None:
                                raise ValueError("sec-cofiler-issuer-needs-review")
                            index_digest, _, index_skipped = _save_raw_exhibit(raw_cache_dir, index)
                            if index_skipped or index_digest != proof["indexSha256"]:
                                raise ValueError("sec-cofiler-issuer-needs-review")
                            index_raw = index
                        if exhibit_url is None:
                            raise ValueError("source-gap:ex21-missing")
                        if not _valid_exhibit_url(exhibit_url, cik, accession, proof):
                            raise ValueError("sec-exhibit-url-invalid")
                        raw = get(exhibit_url, cik, {exhibit_url})
                        if raw_cache_dir is not None:
                            digest, saved, skipped = _save_raw_exhibit(raw_cache_dir, raw)
                            if skipped:
                                issuer.pop("rawExhibitCache", None)
                                lists["rawCacheSkipped"].append(cik)
                                if proof is not None:
                                    raise ValueError("sec-cofiler-issuer-needs-review")
                            else:
                                issuer["rawExhibitCache"] = {"cik": cik, "accession": accession,
                                    "filedDate": metadata["filed_date"], "periodEnd": metadata["period_end"],
                                    "url": exhibit_url, "documentSha256": digest}
                                if proof is not None:
                                    issuer["rawExhibitCache"]["cofilerProof"] = proof
                                checkpoint(document)  # Durable source binding precedes parsing.
                                if saved:
                                    lists["rawCacheSaved"].append(cik)
                    parsed = (_parse_raw_exhibit(raw, cik, metadata, exhibit_url, helpers, proof, index_raw) if raw_cache_dir is not None
                              else helpers.parse_exhibit(raw, {"cik": cik, "accession": accession,
                                  "filedDate": metadata["filed_date"], "periodEnd": metadata["period_end"],
                                  "url": exhibit_url, "issuerName": metadata["issuer_name"]}))
                    if parsed["status"] != "parsed":
                        issuer["reviewExhibit"] = parsed
                        raise ValueError("source-gap:ex21-needs-review")
                    issuer.pop("reviewExhibit", None)
                    issuer.update(exhibit=parsed, attemptStatus="success", lastSuccessAt=stamp,
                                  checkedAt=stamp, sourceGap=None)
                    lists["success"].append(cik)
            except BudgetDeferred:
                issuer["attemptStatus"] = "budget-deferred"
                lists["budgetDeferred"].append(cik)
            except urllib.error.HTTPError as exc:
                issuer["attemptStatus"] = "HTTP" + str(exc.code)
                lists["error"].append({"cik": cik, "reason": issuer["attemptStatus"]})
                if exc.code in (401, 403, 429):
                    summary["stopReason"] = issuer["attemptStatus"]
            except (ValueError, KeyError, TypeError, OSError) as exc:
                reason = str(exc) if isinstance(exc, ValueError) and re.fullmatch(r"(?:source-gap:)?[a-z0-9-]+", str(exc)) else "sec-source-error"
                needs_review = reason in ("sec-vie-needs-review", "sec-cofiler-issuer-needs-review",
                                          "source-gap:ex21-needs-review")
                issuer["attemptStatus"] = "needs-review" if needs_review else "source-gap" if reason.startswith("source-gap:") else "error"
                issuer["sourceGap"] = reason
                lists["sourceGap" if issuer["attemptStatus"] in ("source-gap", "needs-review") else "error"].append({"cik": cik, "reason": reason})
            if issuer["attemptStatus"] not in ("success", "cached-same-accession") and "exhibit" in issuer:
                lists["retained"].append(cik)
            checkpoint(document)
    completed_attempts = set(lists["attempted"]) - set(lists["budgetDeferred"])
    lists["deferred"] = [c for c in due if c not in completed_attempts]
    if fetch_public:
        if not summary["stopReason"]:
            if budget["requests"] >= MAX_HTTP:
                summary["stopReason"] = "daily-http-budget"
            elif len(budget["ciks"]) >= MAX_CIKS:
                summary["stopReason"] = "daily-cik-budget"
            elif due and not selected and limit and all(c in budget["ciks"] for c in due):
                summary["stopReason"] = "daily-cik-already-attempted"
        if summary["stopReason"] in BUDGET_STOPS:
            lists["budgetDeferred"] = list(lists["deferred"])
        else:
            lists["budgetDeferred"] = sorted(set(lists["budgetDeferred"]) | (set(due) & set(budget["ciks"]) - set(lists["attempted"])))
    if lists["error"] and not summary["stopReason"]:
        summary["stopReason"] = "source-error"
    summary.update({key: len(value) for key, value in lists.items()})
    summary["sourceError"] = summary["error"]
    summary["exitCode"] = int(bool(summary["sourceError"]) or
                              summary["stopReason"] is not None and summary["stopReason"] not in BUDGET_STOPS)
    summary.update(lists=lists, dailyRequests=budget["requests"], dailyCiks=len(budget["ciks"]),
                   elapsedSeconds=max(0, clock() - started), maxElapsedSeconds=max_elapsed_seconds,
                   guardedBudget={"valid": budget["requests"] <= MAX_HTTP and len(budget["ciks"]) <= MAX_CIKS,
                                  "maxCiks": MAX_CIKS, "maxHttp": MAX_HTTP})
    summary["refreshLanes"] = {lane: {key: sum(lane_by_cik.get(c) == lane for c in values)
        for key, values in (("eligible", due), ("selected", selected),
                            ("attempted", lists["attempted"]), ("deferred", lists["deferred"]))}
        for lane in ("fresh", "backlog")}
    summary["reviewReplayDeferred"] = defer_reviews
    return document, summary
