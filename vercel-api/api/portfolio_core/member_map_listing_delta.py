"""Shared public filing discovery; no persistence, orchestration or document fetches.

Runner contract: collect_*_delta returns feed, cursor, next_cursor, status,
complete, requests, records, unmapped, duplicates, error and coverage. Only
success merges into the prior feed. SEC bootstrap has an explicit initialized
state: it establishes an anchor without claiming historical completeness or
updating the feed/last_success. Subsequent success advances it. Partial/error
results preserve that feed exactly. ``records`` are bounded flat disclosures
with ticker/name, suitable for discovery, not a replacement snapshot.

SEC scope is the shared latest 8-K Atom listing, not historical completeness.
A saved anchor must be encountered; an expired anchor needs backfill by the
parent. DART replays the entire boundary day because list.json has date-only
sorting. Its page denominator must be exhausted before advancing. Atom updated
is preserved as source_reported_at; it is not claimed to be a filingDate from
submissions. No summary HTML is inspected. Mapping inputs are public catalog
and official company_tickers.json, supplied/cached by the parent.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json
import hashlib
import re
import time
from typing import Any, Callable, Mapping
import xml.etree.ElementTree as ET

import requests

SEC_LATEST = "https://www.sec.gov/cgi-bin/browse-edgar"
SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"
DART_LIST = "https://opendart.fss.or.kr/api/list.json"
MAX_BYTES = 2 * 1024 * 1024
KST = timezone(timedelta(hours=9))
ATOM = "{http://www.w3.org/2005/Atom}"
Transport = Callable[..., bytes]


class ListingError(ValueError):
    """Fixed reason codes only: never echo remote bodies, URLs or keys."""


def _stamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed
    except (AttributeError, TypeError, ValueError):
        raise ListingError("invalid_timestamp") from None


def _text(value: Any, limit: int = 300) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise ListingError("invalid_text")
    value = value.strip()
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ListingError("invalid_text")
    return value


def _cik(value: Any) -> str:
    value = str(value)
    if not re.fullmatch(r"[0-9]{1,10}", value) or int(value) == 0:
        raise ListingError("invalid_cik")
    return str(int(value))


def _public_sources():
    try:
        from . import portfolio_public_sources
    except ImportError:
        from api.intelligence import portfolio_public_sources
    return portfolio_public_sources


def _catalog(catalog: Mapping[str, Any], market: str, coverage: dict | None = None) -> dict[str, str]:
    _row_identity = _public_sources()._row_identity

    rows = catalog.get("stocks")
    if isinstance(rows, Mapping):
        pairs = rows.items()
    elif isinstance(rows, list):
        pairs = ((None, row) for row in rows)
    else:
        raise ListingError("invalid_catalog")
    report = {"rows_total": len(rows), "rows_mapped": 0, "rows_excluded": 0, "reasons": {}}
    if coverage is not None:
        coverage["catalog"] = report
    def reason(code):
        report["reasons"][code] = report["reasons"].get(code, 0) + 1
    result = {}
    for hint, row in pairs:
        if not isinstance(row, Mapping):
            report["rows_excluded"] += 1
            reason("invalid_row")
            continue
        identity = _row_identity(row, ticker_hint=hint)
        if identity is None or identity[0] != market:
            report["rows_excluded"] += 1
            reason("invalid_identity" if identity is None else "other_market")
            continue
        name = None
        for field in ("name", "name_ko"):
            if row.get(field) in (None, ""):
                continue
            try:
                name = _text(row[field], 160)
            except ListingError:
                reason("invalid_" + field)
                continue
            if field == "name_ko":
                reason("name_ko_fallback")
            break
        if name is None:
            # Only the catalog's already validated identity may be used here.
            # No truncation, guessed ticker, or SEC title/name identity inference.
            name = identity[1]
            reason("ticker_name_fallback")
        result[identity[1]] = name
        report["rows_mapped"] += 1
    report["unique_tickers"] = len(result)
    return result


def build_kr_universe(catalog: Mapping[str, Any], *, coverage: dict | None = None) -> dict[str, str]:
    """Catalog -> ticker/name map; optional coverage receives bounded reason counts."""
    return _catalog(catalog, "KR", coverage)


def build_issuer_map(catalog: Mapping[str, Any], company_tickers: Mapping[str, Any],
                     *, coverage: dict | None = None) -> dict:
    """Official SEC index intersected with catalog; retain multiple share classes."""
    universe = _catalog(catalog, "US", coverage)
    report = {"rows_total": len(company_tickers), "rows_mapped": 0, "rows_excluded": 0, "reasons": {}}
    if coverage is not None:
        coverage["sec_index"] = report
    def exclude(code):
        report["rows_excluded"] += 1
        report["reasons"][code] = report["reasons"].get(code, 0) + 1
    result: dict[str, list[dict]] = {}
    seen = set()
    for row in company_tickers.values():
        if not isinstance(row, Mapping):
            exclude("invalid_row")
            continue
        ticker = str(row.get("ticker", "")).upper()
        # Official SEC share-class spelling uses '-', catalogs may use '.'.
        candidates = [t for t in (ticker, ticker.replace("-", ".")) if t in universe]
        if not candidates:
            exclude("outside_catalog")
            continue
        try:
            cik = _cik(row.get("cik_str"))
        except ListingError:
            exclude("invalid_cik")
            continue
        report["rows_mapped"] += 1
        for mapped in dict.fromkeys(candidates):
            if (cik, mapped) not in seen:
                result.setdefault(cik, []).append({"ticker": mapped, "name": universe[mapped]})
                seen.add((cik, mapped))
    return result


def bounded_transport(endpoint: str, *, params: Mapping[str, str], headers: Mapping[str, str],
                      timeout: float = 10, max_bytes: int = MAX_BYTES) -> bytes:
    """Fixed destinations, no redirects, retries, unbounded body or error logging."""
    if endpoint not in (SEC_LATEST, SEC_TICKERS, DART_LIST):
        raise ListingError("endpoint_rejected")
    if not 0 < timeout <= 10 or not 0 < max_bytes <= MAX_BYTES:
        raise ListingError("invalid_transport_limits")
    if endpoint in (SEC_LATEST, SEC_TICKERS):
        from api.collectors.sec_edgar import _throttle
        _throttle()
    started = time.monotonic()
    try:
        with requests.get(endpoint, params=dict(params), headers=dict(headers),
                          timeout=timeout, allow_redirects=False, stream=True) as response:
            if response.status_code != 200:
                raise ListingError("http_failure")
            chunks, size = [], 0
            for chunk in response.iter_content(chunk_size=16384):
                size += len(chunk)
                if size > max_bytes:
                    raise ListingError("body_limit")
                if time.monotonic() - started > timeout:
                    raise ListingError("transport_timeout")
                chunks.append(chunk)
            return b"".join(chunks)
    except ListingError:
        raise
    except Exception:
        raise ListingError("transport_failure") from None


def _body(body: bytes) -> bytes:
    if not isinstance(body, bytes) or len(body) > MAX_BYTES:
        raise ListingError("body_limit")
    return body


def parse_sec_atom(body: bytes) -> list[dict]:
    """Strict Atom metadata parser. Any invalid entry invalidates the page."""
    body = _body(body)
    try:
        body.decode("utf-8")
    except UnicodeError:
        raise ListingError("invalid_atom_encoding") from None
    if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
        raise ListingError("xml_declaration_rejected")
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        raise ListingError("invalid_atom") from None
    if root.tag != ATOM + "feed":
        raise ListingError("invalid_atom")
    result = []
    for entry in root.findall(ATOM + "entry"):
        title = _text(entry.findtext(ATOM + "title"))
        category = entry.find(ATOM + "category")
        form = _text(category.get("term") if category is not None else None, 30)
        identity = re.fullmatch(r"(.+?) - (.+) \(([0-9]{1,10})\) \((?:Filer|Subject|Reporting)\)", title)
        if not identity or identity[1] != form:
            raise ListingError("invalid_sec_identity")
        cik = _cik(identity[3])
        entry_id = entry.findtext(ATOM + "id") or ""
        accession = re.search(r"accession-number=([0-9]{10}-[0-9]{2}-[0-9]{6})$", entry_id)
        if not accession:
            raise ListingError("invalid_accession")
        acc = accession[1].replace("-", "")
        links = [link.get("href", "") for link in entry.findall(ATOM + "link")
                 if link.get("rel", "alternate") == "alternate"]
        if len(links) != 1:
            raise ListingError("invalid_sec_link")
        target = _public_sources()._canonical_disclosure_url(links[0], "SEC")
        prefix = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/"
        if target is None or not target[0].startswith(prefix):
            raise ListingError("invalid_sec_link")
        updated = _stamp(entry.findtext(ATOM + "updated"))
        # CIK is an identity field; exclude it from display text so the existing
        # public consumer's long-identifier text guard accepts this title.
        display_title = f"{form} - {identity[2]}"
        result.append({"id": f"SEC:{cik}:{acc}", "cik": cik, "title": display_title,
                       "label": form, "date": updated.date().isoformat(),
                       "source_reported_at": updated.isoformat(), "date_precision": "timestamp",
                       "source_date_field": "atom.updated", "source_url": target[0],
                       "source": "SEC", "is_correction": form.endswith("/A"),
                       "filer": _text(identity[2], 160)})
    return result


def parse_dart_list(payload: Mapping[str, Any]) -> dict:
    """DART list metadata; date stays date-only, category is not inferred."""
    if not isinstance(payload, Mapping):
        raise ListingError("invalid_dart")
    if payload.get("status") == "013":
        return {"rows": [], "page_no": 1, "page_count": 0, "total_count": 0, "total_page": 0}
    if payload.get("status") == "020":
        raise ListingError("dart-quota-exceeded")
    if payload.get("status") != "000":
        raise ListingError("dart_api_failure")
    meta = {}
    for field in ("page_no", "page_count", "total_count", "total_page"):
        value = payload.get(field)
        if type(value) not in (str, int) or not re.fullmatch(r"[0-9]{1,9}", str(value)):
            raise ListingError("invalid_pagination")
        meta[field] = int(value)
    count, total, pages, page = (meta[f] for f in ("page_count", "total_count", "total_page", "page_no"))
    if not (1 <= count <= 100 and total > 0 and 1 <= page <= pages
            and pages == (total + count - 1) // count):
        raise ListingError("invalid_pagination")
    rows = payload.get("list")
    expected = min(count, total - (page - 1) * count)
    if not isinstance(rows, list) or len(rows) != expected:
        raise ListingError("incomplete_page")
    result = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ListingError("invalid_dart_row")
        receipt, stamp = row.get("rcept_no"), row.get("rcept_dt")
        if not isinstance(receipt, str) or not re.fullmatch(r"[0-9]{14}", receipt):
            raise ListingError("invalid_receipt")
        if not isinstance(stamp, str) or not re.fullmatch(r"[0-9]{8}", stamp):
            raise ListingError("invalid_reported_date")
        try:
            reported = datetime.strptime(stamp, "%Y%m%d").date().isoformat()
        except ValueError:
            raise ListingError("invalid_reported_date") from None
        # Listing identity only; the existing public universe still controls mapping.
        ticker = row.get("stock_code", "")
        if not isinstance(ticker, str) or ticker and not re.fullmatch(r"[0-9][0-9A-Z]{5}", ticker):
            raise ListingError("invalid_stock_code")
        title = _text(row.get("report_nm"))
        result.append({"id": f"DART:{receipt}", "ticker": ticker, "title": title,
                       "label": "DART", "date": reported, "date_precision": "date",
                       "source_date_field": "rcept_dt", "source": "DART",
                       "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + receipt,
                       "is_correction": any(marker in title for marker in
                                            ("[기재정정]", "[첨부정정]", "[변경등록]")),
                       "filer": _text(row["flr_nm"], 160) if row.get("flr_nm") else ""})
    return {**meta, "rows": result}


def _limits(max_pages: int, page_size: int, max_records: int, max_per_ticker: int) -> None:
    for value, maximum in ((max_pages, 10), (page_size, 100), (max_records, 1000), (max_per_ticker, 50)):
        if type(value) is not int or not 1 <= value <= maximum:
            raise ListingError("invalid_limits")


def _filing_id(url: Any) -> str | None:
    _canonical_disclosure_url = _public_sources()._canonical_disclosure_url
    for source in ("SEC", "DART"):
        target = _canonical_disclosure_url(url, source)
        if target:
            # A legacy accession directory and its new Atom index link refer
            # to the same filing, regardless of the document filename.
            return ":".join(target[1].split(":")[:3]) if source == "SEC" else target[1]
    return None


def _known(previous: Mapping[str, Any]) -> set[str]:
    return {identifier for item in previous.get("items", [])
            for d in item.get("disclosures", [])
            if (identifier := _filing_id(d.get("source_url"))) is not None}


def merge_feed(previous: Mapping[str, Any], records: list[dict], checked_at: str,
               *, max_per_ticker: int) -> dict:
    """Merge touched companies only; never replace the universe with listing hits."""
    feed = deepcopy(previous)
    groups = {item["ticker"]: item for item in feed.get("items", [])}
    touched = set()
    for record in records:
        ticker = record["ticker"]
        group = groups.setdefault(ticker, {"ticker": ticker, "name": record["name"], "disclosures": []})
        disclosure = {key: value for key, value in record.items() if key not in ("ticker", "name", "cik")}
        if _filing_id(disclosure["source_url"]) not in {_filing_id(d.get("source_url")) for d in group["disclosures"]}:
            group["disclosures"].append(disclosure)
        touched.add(ticker)
    for ticker in touched:
        group = groups[ticker]
        group["disclosures"].sort(key=lambda d: (d["date"], d.get("source_reported_at", ""), d.get("id", "")), reverse=True)
        group["disclosures"] = group["disclosures"][:max_per_ticker]
        group["latest"] = group["disclosures"][0]["date"]
    feed["items"] = sorted(groups.values(), key=lambda item: item.get("latest", ""), reverse=True)
    feed.setdefault("_meta", {}).update(generated_at=checked_at, count=len(groups),
                                        disclosure_count=sum(len(g.get("disclosures", [])) for g in groups.values()))
    return feed


def _result(previous: Mapping[str, Any], cursor: dict | None) -> dict:
    return {"feed": deepcopy(previous), "cursor": deepcopy(cursor), "next_cursor": None,
            "status": "error", "complete": False, "requests": 0, "records": [],
            "unmapped": 0, "duplicates": 0, "error": None, "historical_gap": False,
            "coverage": {"pages_succeeded": 0, "listing_records": 0,
                         "whole_market_coverage": False, "raw_body_checked": False,
                         "bounded": True}}


def _success(result: dict, previous: Mapping[str, Any], next_cursor: dict,
             checked_at: str, max_per_ticker: int) -> dict:
    result.update(status="success", complete=True, cursor=next_cursor, next_cursor=next_cursor)
    if result["records"]:
        result["feed"] = merge_feed(previous, result["records"], checked_at, max_per_ticker=max_per_ticker)
    return result


def _failure(result: dict, error: str) -> dict:
    result.update(status="partial" if result["coverage"]["pages_succeeded"] else "error", error=error)
    return result


def _initialize_sec(result: dict, head: str | None, checked_at: str) -> dict:
    """A bootstrap baseline is deliberately not a successful incremental pass."""
    result.update(status="initialized", complete=False, historical_gap=True, error=None)
    result["coverage"]["historical_gap"] = True
    if head is not None:
        next_cursor = {"source": "SEC", "anchor_id": head, "checked_at": checked_at,
                       "historical_gap": True}
        result.update(cursor=next_cursor, next_cursor=next_cursor)
    return result


def collect_sec_delta(issuer_map: Mapping[str, list[dict]], previous_feed: Mapping[str, Any],
                      cursor: dict | None, checked_at: str, *, transport: Transport | None = None,
                      max_pages: int = 3, page_size: int = 100, max_records: int = 500,
                      max_per_ticker: int = 5) -> dict:
    """Bounded shared 8-K listing pass; transport(endpoint, **kwargs) -> bytes."""
    result = _result(previous_feed, cursor)
    try:
        _stamp(checked_at)
        _limits(max_pages, page_size, max_records, max_per_ticker)
        if cursor is not None and (cursor.get("source") != "SEC" or not isinstance(cursor.get("anchor_id"), str)
                                   or not re.fullmatch(r"SEC:[1-9][0-9]{0,9}:[0-9]{18}", cursor["anchor_id"])):
            raise ListingError("invalid_cursor")
        result["historical_gap"] = bool(cursor and cursor.get("historical_gap"))
        result["coverage"].update(scope="shared_latest_8-K", historical_gap=result["historical_gap"])
        from api.collectors.sec_edgar import _headers
        from api.intelligence.us_financials import SEC_USER_AGENT
        headers = {**_headers(SEC_USER_AGENT), "Accept": "application/atom+xml"}
        fetch = transport or bounded_transport
        anchor = cursor["anchor_id"] if cursor else None
        head, seen, known = None, set(), _known(previous_feed)
        for page in range(max_pages):
            result["requests"] += 1
            rows = parse_sec_atom(fetch(SEC_LATEST, params={"action": "getcurrent", "type": "8-K",
                "owner": "include", "output": "atom", "count": str(page_size), "start": str(page * page_size)},
                headers=headers, timeout=10, max_bytes=MAX_BYTES))
            if len(rows) > page_size:
                raise ListingError("invalid_page_size")
            result["coverage"]["pages_succeeded"] += 1
            result["coverage"]["listing_records"] += len(rows)
            if rows and head is None:
                head = rows[0]["id"]
            boundary, new_ids = False, 0
            for row in rows:
                if row["id"] == anchor:
                    boundary = True
                if row["id"] in seen:
                    result["duplicates"] += 1
                    continue
                seen.add(row["id"])
                new_ids += 1
                if boundary:
                    continue
                issuers = issuer_map.get(row["cik"], [])
                if not issuers:
                    result["unmapped"] += 1
                    continue
                if row["label"] not in ("8-K", "8-K/A"):
                    continue
                if row["id"] in known:
                    result["duplicates"] += 1
                    continue
                for issuer in issuers:
                    if len(result["records"]) >= max_records:
                        raise ListingError("record_limit")
                    result["records"].append({**row, **issuer, "observed_at": checked_at})
            if boundary or (anchor is None and len(rows) < page_size):
                if anchor is None:
                    return _initialize_sec(result, head, checked_at)
                next_cursor = {"source": "SEC", "anchor_id": head, "checked_at": checked_at,
                               "historical_gap": result["historical_gap"]}
                return _success(result, previous_feed, next_cursor, checked_at, max_per_ticker)
            if not rows or not new_ids:
                raise ListingError("cursor_not_found" if not rows else "pagination_stalled")
        if anchor is None:
            return _initialize_sec(result, head, checked_at)
        raise ListingError("page_limit")
    except ListingError as exc:
        return _failure(result, str(exc))
    except Exception:
        return _failure(result, "collection_failure")


def collect_dart_delta(universe: Mapping[str, str], previous_feed: Mapping[str, Any],
                       cursor: dict | None, checked_at: str, api_key: str, *,
                       transport: Transport | None = None, max_pages: int = 3,
                       page_size: int = 100, max_records: int = 500,
                       max_per_ticker: int = 8, window_days: int = 2,
                       catchup_phase: str | None = None) -> dict:
    """Exhaust one DART date per pass; replay the completed boundary before advancing."""
    result = _result(previous_feed, cursor)
    try:
        now = _stamp(checked_at)
        _limits(max_pages, page_size, max_records, max_per_ticker)
        if (type(window_days) is not int or not 1 <= window_days <= 90 or not isinstance(api_key, str)
                or not api_key or catchup_phase not in (None, "replayed", "advanced")):
            raise ListingError("invalid_configuration")
        today = now.astimezone(KST).date()
        begin = end = today
        next_phase = None
        old_ids = set()
        if cursor is None:
            begin = end = today - timedelta(days=window_days - 1)
            if end < today:
                next_phase = "replayed"
        else:
            if cursor.get("source") != "DART" or not isinstance(cursor.get("ids"), list):
                raise ListingError("invalid_cursor")
            try:
                boundary_date = date.fromisoformat(cursor["through_date"])
            except (KeyError, TypeError, ValueError):
                raise ListingError("invalid_cursor") from None
            if boundary_date > today:
                raise ListingError("cursor_outside_window")
            if boundary_date < today:
                if catchup_phase == "replayed":
                    begin = end = boundary_date + timedelta(days=1)
                    next_phase = "advanced"
                else:
                    begin = end = boundary_date
                    next_phase = "replayed"
            old_ids = set(cursor["ids"])
        fetch = transport or bounded_transport
        seen, known, totals, last_day = set(), _known(previous_feed), None, []
        for page in range(1, max_pages + 1):
            result["requests"] += 1
            body = fetch(DART_LIST, params={"crtfc_key": api_key, "bgn_de": begin.strftime("%Y%m%d"),
                "end_de": end.strftime("%Y%m%d"), "sort": "date", "sort_mth": "desc",
                "page_no": str(page), "page_count": str(page_size)}, headers={"Accept": "application/json"},
                timeout=10, max_bytes=MAX_BYTES)
            try:
                payload = json.loads(_body(body))
            except (ValueError, UnicodeError):
                raise ListingError("invalid_json") from None
            parsed = parse_dart_list(payload)
            if parsed["page_no"] != page or parsed["total_page"] and parsed["page_count"] != page_size:
                raise ListingError("invalid_pagination")
            current_totals = (parsed["total_count"], parsed["total_page"])
            if totals is not None and totals != current_totals:
                raise ListingError("pagination_changed")
            totals = current_totals
            if any(not begin.isoformat() <= row["date"] <= end.isoformat() for row in parsed["rows"]):
                raise ListingError("date_outside_window")
            result["coverage"].update(total_pages=parsed["total_page"], total_records=parsed["total_count"])
            result["coverage"]["pages_succeeded"] += 1
            result["coverage"]["listing_records"] += len(parsed["rows"])
            for row in parsed["rows"]:
                if row["id"] in seen:
                    result["duplicates"] += 1
                    continue
                seen.add(row["id"])
                if row["date"] == end.isoformat():
                    last_day.append(row["id"])
                name = universe.get(row["ticker"])
                if name is None:
                    result["unmapped"] += 1
                    continue
                if row["id"] in old_ids or row["id"] in known:
                    result["duplicates"] += 1
                    continue
                if len(result["records"]) >= max_records:
                    raise ListingError("record_limit")
                result["records"].append({**row, "name": name, "observed_at": checked_at})
            if page >= parsed["total_page"]:
                if len(seen) != parsed["total_count"]:
                    raise ListingError("incomplete_unique_records")
                # Preserve previously observed IDs when replaying the same boundary.
                next_ids = (list(dict.fromkeys(last_day + cursor["ids"]))
                            if cursor is not None and end == boundary_date else last_day)
                if len(next_ids) > 1000:
                    raise ListingError("record_limit")
                next_cursor = {"source": "DART", "through_date": end.isoformat(),
                               "ids": next_ids, "checked_at": checked_at}
                completed = _success(result, previous_feed, next_cursor, checked_at, max_per_ticker)
                if end < today:
                    completed.update(status="partial", complete=False, catchup_phase=next_phase)
                    completed["historical_gap"] = True
                    completed["coverage"]["historical_gap"] = True
                return completed
        raise ListingError("page_limit")
    except ListingError as exc:
        return _failure(result, str(exc))
    except Exception:
        return _failure(result, "collection_failure")


# DART v2 is deliberately source-specific. SQL replays these bounded page proofs
# under the same lease/revision; the worker cannot submit a new checkpoint alone.
DART_CHECKPOINT_BYTES = 4 * 1024 * 1024


def dart_ids_digest(ids):
    return hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest()


def dart_v2_cursor(committed):
    return {"source": "DART", "version": 2, "through_date": committed["date"],
            "checked_at": committed["checked_at"], "id_count": len(committed["ids"]),
            "ids_sha256": dart_ids_digest(committed["ids"])}


def dart_aggregate_size(state, checkpoint):
    # Default separators match jsonb::text spacing; neither JSON contains floats
    # except the already validated health clock. Enforce again in PostgreSQL.
    return sum(len(json.dumps(v, ensure_ascii=False, allow_nan=False).encode())
               for v in (state, checkpoint) if v is not None)


def _dart_map(value):
    return (type(value) is dict and all(type(k) is str and re.fullmatch(r"DART:[0-9]{14}", k)
            and type(v) is str and re.fullmatch(r"[0-9a-f]{64}", v) for k, v in value.items()))


def validate_dart_checkpoint(checkpoint):
    """Closed public evidence only; no provider body, names, URLs or keys."""
    if checkpoint is None:
        return None
    try:
        if (type(checkpoint) is not dict or set(checkpoint) != {"version", "committed", "pending"}
                or type(checkpoint["version"]) is not int or checkpoint["version"] != 2
                or dart_aggregate_size({}, checkpoint) > DART_CHECKPOINT_BYTES):
            raise ValueError
        committed, p = checkpoint["committed"], checkpoint["pending"]
        if committed is not None:
            if type(committed) is not dict or set(committed) != {"date", "ids", "checked_at"}:
                raise ValueError
            date.fromisoformat(committed["date"]); _stamp(committed["checked_at"])
            ids = committed["ids"]
            if (type(ids) is not list or any(type(i) is not str or not re.fullmatch(r"DART:[0-9]{14}", i) for i in ids)
                    or ids != sorted(set(ids))):
                raise ValueError
        if p is not None:
            if type(p) is not dict or set(p) != {"date", "catalog", "started_at", "phase", "next_page",
                    "total", "rows", "baseline", "first", "last", "observed"}:
                raise ValueError
            day = date.fromisoformat(p["date"]); _stamp(p["started_at"])
            if (type(p["catalog"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", p["catalog"])
                    or p["phase"] not in ("scan", "verify") or type(p["next_page"]) is not int
                    or not 1 <= p["next_page"] <= 10000000
                    or not all(_dart_map(p[k]) for k in ("rows", "baseline", "first", "last"))
                    or any(i[5:13] != p["date"].replace("-", "") for k in ("rows", "baseline", "first", "last") for i in p[k])
                    or type(p["observed"]) is not list
                    or any(type(i) is not str or not re.fullmatch(r"DART:[0-9]{14}", i) for i in p["observed"])
                    or p["observed"] != sorted(set(p["observed"]))):
                raise ValueError
            total = p["total"]
            if total is not None and (type(total) is not int or not 0 <= total <= 999999999):
                raise ValueError
            if total is None:
                if p["next_page"] != 1 or p["phase"] != "scan" or any(p[k] for k in ("rows", "baseline", "first", "last")):
                    raise ValueError
            else:
                if len(p["rows"]) != min((p["next_page"] - 1) * 100, total):
                    raise ValueError
                if p["next_page"] > max(1, (total + 99) // 100):
                    raise ValueError
                if p["phase"] == "scan" and p["baseline"] or p["phase"] == "verify" and len(p["baseline"]) != total:
                    raise ValueError
            if p["next_page"] == 1:
                if p["first"] or p["last"]:
                    raise ValueError
            elif (len(p["first"]) != 100 or len(p["last"]) != 100
                    or any(p["rows"].get(k) != v for part in ("first", "last") for k, v in p[part].items())):
                raise ValueError
            if not set(p["rows"]) | set(p["baseline"]) <= set(p["observed"]):
                raise ValueError
            if committed is not None and not date.fromisoformat(committed["date"]) <= day <= date.fromisoformat(committed["date"]) + timedelta(days=1):
                raise ValueError
        return deepcopy(checkpoint)
    except (ValueError, TypeError, KeyError, OverflowError):
        raise ListingError("invalid_cursor") from None


def _dart_pending(day, catalog, now, observed=()):
    return {"date": day, "catalog": catalog, "started_at": now, "phase": "scan", "next_page": 1,
            "total": None, "rows": {}, "baseline": {}, "first": {}, "last": {}, "observed": sorted(set(observed))}


def dart_begin(checkpoint, cursor, now, catalog):
    today = _stamp(now).astimezone(KST).date()
    if type(catalog) is not str or not re.fullmatch(r"[0-9a-f]{64}", catalog):
        raise ListingError("invalid_configuration")
    cp = validate_dart_checkpoint(checkpoint)
    if cp is None:
        if cursor and "version" in cursor:
            raise ListingError("invalid_cursor")
        committed = ({"date": cursor["through_date"], "ids": sorted(set(cursor["ids"])),
                      "checked_at": cursor["checked_at"]} if cursor else None)
        cp = {"version": 2, "committed": committed, "pending": None}
    c, p = cp["committed"], cp["pending"]
    if c is not None:
        if date.fromisoformat(c["date"]) > today or _stamp(c["checked_at"]) > _stamp(now):
            raise ListingError("invalid_cursor")
        if cursor and cursor.get("version") == 2 and cursor != dart_v2_cursor(c):
            raise ListingError("invalid_cursor")
    if p is None:
        day = date.fromisoformat(c["date"]) if c else today - timedelta(days=1)
        # A boundary last checked while that day was live must be replayed after
        # midnight. Two completed historical sweeps permit exactly one next day.
        if c and day < today and _stamp(c["checked_at"]).astimezone(KST).date() > day:
            day += timedelta(days=1)
        cp["pending"] = _dart_pending(day.isoformat(), catalog, now)
    elif p["catalog"] != catalog:
        cp["pending"] = _dart_pending(p["date"], catalog, now, p["observed"])
    if date.fromisoformat(cp["pending"]["date"]) > today or _stamp(cp["pending"]["started_at"]) > _stamp(now):
        raise ListingError("invalid_cursor")
    return cp


def dart_replay_pages(checkpoint, cursor, now, catalog, pages):
    """Deterministic transition also implemented by the private SQL helper.

    Proofs carry only receipt IDs and canonical row digests. Guards consume the
    same ten HTTP requests as forward pages. A phase boundary ends this batch.
    """
    if type(pages) is not list or len(pages) > 10:
        raise ListingError("invalid_pagination")
    cp = dart_begin(checkpoint, cursor, now, catalog)
    p = cp["pending"]
    guards = list(dict.fromkeys((1, p["next_page"] - 1))) if p["next_page"] > 1 else []
    for index, proof in enumerate(pages):
        if (type(proof) is not dict or set(proof) != {"page_no", "total_count", "rows"}
                or type(proof["page_no"]) is not int or type(proof["total_count"]) is not int
                or not 0 <= proof["total_count"] <= 999999999 or type(proof["rows"]) is not list
                or any(type(pair) is not list or len(pair) != 2
                       or any(type(value) is not str for value in pair) for pair in proof["rows"])):
            raise ListingError("invalid_pagination")
        rows = dict(proof["rows"])
        page, total = proof["page_no"], proof["total_count"]
        if (not _dart_map(rows) or any(i[5:13] != p["date"].replace("-", "") for i in rows)
                or len(rows) != len(proof["rows"]) or not 1 <= page <= max(1, (total + 99) // 100)
                or len(rows) != min(100, max(0, total - (page - 1) * 100))):
            raise ListingError("incomplete_unique_records")
        expected = guards[index] if index < len(guards) else p["next_page"]
        if page != expected:
            raise ListingError("invalid_pagination")
        p["observed"] = sorted(set(p["observed"]) | rows.keys())
        changed = p["total"] is not None and p["total"] != total
        if index < len(guards):
            changed = changed or rows != p["first" if page == 1 else "last"]
        elif set(rows) & p["rows"].keys():
            changed = True
        if changed:
            if index != len(pages) - 1:
                raise ListingError("invalid_pagination")
            cp["pending"] = _dart_pending(p["date"], catalog, now, p["observed"])
            return cp, False, "pagination_changed"
        if index < len(guards):
            continue
        p["total"] = total
        p["rows"].update(rows)
        if page == 1:
            p["first"] = rows
        p["last"] = rows
        p["next_page"] = page + 1
        if page >= max(1, (total + 99) // 100):
            if index != len(pages) - 1 or len(p["rows"]) != total:
                raise ListingError("incomplete_unique_records")
            if p["phase"] == "scan":
                p.update(phase="verify", next_page=1, baseline=p["rows"], rows={}, first={}, last={})
                return cp, False, None
            if p["baseline"] != p["rows"]:
                cp["pending"] = _dart_pending(p["date"], catalog, now, p["observed"])
                return cp, False, "pagination_changed"
            ids = set(p["observed"])
            if cp["committed"] and cp["committed"]["date"] == p["date"]:
                ids.update(cp["committed"]["ids"])
            cp["committed"] = {"date": p["date"], "ids": sorted(ids), "checked_at": now}
            cp["pending"] = None
            return cp, True, None
    return cp, False, None


def collect_dart_continuation(universe, previous_feed, cursor, checked_at, api_key, checkpoint, *, transport=None):
    """Unfiltered DART list: at most ten requests/1000 rows including guards."""
    result = _result(previous_feed, cursor)
    catalog = hashlib.sha256(json.dumps(sorted(universe.items()), ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    result.update(dart_checkpoint=deepcopy(checkpoint), dart_pages=[], dart_catalog=catalog, dart_sealed=False)
    try:
        if type(api_key) is not str or not api_key.strip():
            raise ListingError("invalid_configuration")
        start = dart_begin(checkpoint, cursor, checked_at, catalog)
        p = start["pending"]
        guards = list(dict.fromkeys((1, p["next_page"] - 1))) if p["next_page"] > 1 else []
        next_page, known = p["next_page"], _known(previous_feed)
        # Exact committed IDs, not the eight-row display feed, preserve replay
        # deduplication. All listing IDs still participate in completeness proof.
        old_ids = set(start["committed"]["ids"]) if start["committed"] and start["committed"]["date"] == p["date"] else set()
        fetch = transport or bounded_transport
        for index in range(10):
            page = guards[index] if index < len(guards) else next_page
            result["requests"] += 1
            body = fetch(DART_LIST, params={"crtfc_key": api_key, "bgn_de": p["date"].replace("-", ""),
                "end_de": p["date"].replace("-", ""), "sort": "date", "sort_mth": "desc",
                "page_no": str(page), "page_count": "100"}, headers={"Accept": "application/json"}, timeout=10, max_bytes=MAX_BYTES)
            try:
                parsed = parse_dart_list(json.loads(_body(body)))
            except (ValueError, UnicodeError) as exc:
                if isinstance(exc, ListingError):
                    raise
                raise ListingError("invalid_json") from None
            if parsed["page_no"] != page or parsed["total_page"] and parsed["page_count"] != 100:
                raise ListingError("invalid_pagination")
            if any(row["date"] != p["date"] for row in parsed["rows"]):
                raise ListingError("date_outside_window")
            proof = {"page_no": page, "total_count": parsed["total_count"], "rows": [[row["id"],
                hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()]
                for row in parsed["rows"]]}
            pages = result["dart_pages"] + [proof]
            cp, sealed, error = dart_replay_pages(checkpoint, cursor, checked_at, catalog, pages)
            result.update(dart_checkpoint=cp, dart_pages=pages, dart_sealed=sealed)
            result["coverage"].update(total_pages=parsed["total_page"], total_records=parsed["total_count"])
            result["coverage"]["pages_succeeded"] += 1
            result["coverage"]["listing_records"] += len(parsed["rows"])
            for row in parsed["rows"]:
                name = universe.get(row["ticker"])
                if name is None:
                    result["unmapped"] += 1
                elif row["id"] in known or row["id"] in old_ids:
                    result["duplicates"] += 1
                else:
                    known.add(row["id"])
                    result["records"].append({**row, "name": name, "observed_at": checked_at})
            if error:
                return _failure(result, error)
            if sealed:
                new_cursor = dart_v2_cursor(cp["committed"])
                result.update(cursor=new_cursor, next_cursor=new_cursor)
                if cp["committed"]["date"] == _stamp(checked_at).astimezone(KST).date().isoformat():
                    return _success(result, previous_feed, new_cursor, checked_at, 8)
                result.update(status="partial", complete=False)
                return result
            if cp["pending"]["phase"] != p["phase"]:
                break
            if index >= len(guards):
                next_page += 1
        result.update(status="partial", complete=False)
        return result
    except ListingError as exc:
        return _failure(result, str(exc))
    except Exception:
        return _failure(result, "collection_failure")
