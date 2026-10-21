"""Bounded SEC subsidiary exhibits (10-K EX-21 / 20-F EX-8.1), deduped by CIK.

Missing/stale local submissions are fetched only with explicit fetch_public.
Metadata check time and filing dates are separate. No submission raw bodies,
bulk ZIPs, ownership percentages or direct-parent conclusions are persisted.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import tempfile
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import urlsplit
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "alphanest-company-structure-us-sources-v1"
MAX_CIKS, MAX_HTTP, MAX_BYTES = 100, 200, 8 * 1024 * 1024
TTL = timedelta(days=7)
KST = timezone(timedelta(hours=9))
BUDGET_STOPS = frozenset({"daily-http-budget", "daily-cik-budget", "daily-cik-already-attempted"})


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
            json.dump(document, handle, ensure_ascii=False, indent=2, allow_nan=False)
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


def _valid_exhibit_url(url, cik, accession):
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
        return archive_cik == str(int(cik)) or accession[:10] == cik
    except (ValueError, UnicodeError):
        return False


def latest_metadata(ticker, cik, submission):
    """Same annual selection/identity/amendment checks as capture-sec-relationships."""
    from api.intelligence.portfolio_sec_relationships import validate_sec_capture
    if str(submission.get("cik", "")).zfill(10) != cik or ticker not in submission.get("tickers", []):
        raise ValueError("sec-submission-identity")
    recent = submission.get("filings", {}).get("recent", {})
    fields = ("form", "filingDate", "reportDate", "accessionNumber", "primaryDocument")
    if (not isinstance(recent, dict) or any(not isinstance(recent.get(k), list) for k in fields)
            or len({len(recent[k]) for k in fields}) != 1
            or any(not isinstance(v, str) for k in fields for v in recent[k])):
        raise ValueError("sec-submission-shape")
    eligible = [i for i, form in enumerate(recent["form"]) if form in ("10-K", "20-F")]
    if not eligible:
        raise ValueError("source-gap:annual-missing")
    i = max(eligible, key=lambda j: (recent["filingDate"][j], recent["accessionNumber"][j]))
    if any(form in ("10-K/A", "20-F/A") and recent["filingDate"][j] >= recent["filingDate"][i]
           for j, form in enumerate(recent["form"])):
        raise ValueError("source-gap:amendment-needs-review")
    accession = recent["accessionNumber"][i]
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


def build_document(source_dir, existing=None, now=None):
    now = now or datetime.now(timezone.utc)
    data = _data_dir(source_dir)
    universe = read_json(data / "universe_search.json").get("stocks", [])
    universe = list(universe.values()) if isinstance(universe, dict) else universe
    mapping = read_json(data / "sec_ticker_cik_map.json")
    if not isinstance(universe, list) or not isinstance(mapping, dict):
        raise ValueError("sec-universe-shape")
    document = copy.deepcopy(existing or {})
    if document and document.get("schema") != SCHEMA:
        raise ValueError("sec-store-schema")
    document.setdefault("issuers", {})
    aliases, unmapped = {}, {}
    tickers = sorted({r["ticker"] for r in universe if isinstance(r, dict)
                      and r.get("market") == "US" and isinstance(r.get("ticker"), str)})
    for ticker in tickers:
        cik = mapping.get(ticker)
        cik = str(cik).zfill(10) if type(cik) in (int, str) else ""
        if not re.fullmatch(r"[0-9]{10}", cik) or int(cik) == 0:
            unmapped[ticker] = "source-gap:cik-missing"
            continue
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


def _due_issuers(document, now):
    due = []
    for cik in document["currentCiks"]:
        issuer = document["issuers"][cik]
        checked = _time(issuer.get("checkedAt"))
        if checked and timedelta(0) <= now - checked < TTL:
            continue
        # Missing exhibits/source gaps cannot permanently outrank healthy stale
        # issuers. Historical success is an attempt fallback for legacy stores.
        attempted = _time(issuer.get("attemptedAt")) or _time(issuer.get("lastSuccessAt"))
        due.append((attempted is not None, attempted or datetime.min.replace(tzinfo=timezone.utc), cik))
    return [row[2] for row in sorted(due)]


def _selection(document, now, limit):
    if type(limit) is not int or not 0 <= limit <= MAX_CIKS:
        raise ValueError("CIK limit must be 0..100")
    return _due_issuers(document, now)[:limit]


def refresh(document, *, source_dir, limit=100, fetch_public=False, checkpoint=None,
            now=None, helpers=None, clock=time.monotonic, sleep=time.sleep):
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
    selected = _selection(document, now, limit)
    due = _due_issuers(document, now)
    # Same-day attempts are never retried, including interrupted reservations.
    selected = [c for c in selected if c not in budget["ciks"]][:MAX_CIKS - len(budget["ciks"])]
    lists = {k: [] for k in ("attempted", "requests", "success", "cached", "sourceGap", "error", "retained", "budgetDeferred", "deferred")}
    lists["selected"] = selected
    summary = {"schema": "alphanest-company-structure-us-refresh-summary-v1", "generatedAt": stamp,
               "dryRun": not fetch_public, "requestedTickers": len(document["universe"]["US"]),
               "requestedCiks": len(document["currentCiks"]), "unmapped": document["unmapped"],
               "stopReason": None, "published": False}
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
            if last_get is not None:
                sleep(max(0, 0.5 - (clock() - last_get)))
            last_get = clock()
            budget["requests"] += 1
            document["requestBudget"] = copy.deepcopy(budget)
            checkpoint(document)  # Reserve before the one physical GET.
            lists["requests"].append({"cik": cik, "url": url})
            raw = helpers.get_public(url, MAX_BYTES)
            if not isinstance(raw, bytes) or not raw or len(raw) > MAX_BYTES:
                raise ValueError("sec-response-size")
            return raw

        for cik in selected:
            if summary["stopReason"]:
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
                if not (isinstance(metadata, dict) and metadata_checked and timedelta(0) <= now - metadata_checked < TTL
                        and metadata.get("cik") == cik and metadata.get("issuer_id", "")[3:] in issuer["tickerAliases"]):
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
                    candidates = sorted(set(issuer["tickerAliases"]) & set(submission.get("tickers", [])))
                    if not candidates:
                        raise ValueError("source-gap:representative-ticker-missing")
                    metadata = helpers.latest_metadata(candidates[0], cik, submission)
                    # Only minimal filing metadata survives, never submission body.
                    issuer.update(filingMetadata=metadata, metadataCheckedAt=metadata_checked.isoformat(),
                                  representativeTicker=candidates[0])
                    checkpoint(document)
                old = issuer.get("reviewExhibit") or issuer.get("exhibit")
                if (isinstance(old, dict) and old.get("cik") == cik and old.get("accession") == metadata["accession"]
                        and old.get("status") in ("parsed", "needs-review")):
                    issuer.update(attemptStatus="cached-same-accession" if old["status"] == "parsed" else "needs-review",
                                  checkedAt=stamp, sourceGap=None if old["status"] == "parsed" else "source-gap:ex21-needs-review")
                    lists["cached"].append(cik)
                else:
                    if MAX_HTTP - budget["requests"] < 2:
                        summary["stopReason"] = "daily-http-budget"
                        raise BudgetDeferred()
                    accession = metadata["accession"]
                    if not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession):
                        raise ValueError("sec-accession-invalid")
                    directory = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/"
                    index_url = directory + accession + "-index.html"
                    index = get(index_url, cik, {index_url})
                    exhibit_url = helpers.find_exhibit(index, cik=cik, accession=accession, form=metadata["form"])
                    if exhibit_url is None:
                        raise ValueError("source-gap:ex21-missing")
                    if not _valid_exhibit_url(exhibit_url, cik, accession):
                        raise ValueError("sec-exhibit-url-invalid")
                    raw = get(exhibit_url, cik, {exhibit_url})
                    parsed = helpers.parse_exhibit(raw, {"cik": cik, "accession": accession,
                        "filedDate": metadata["filed_date"], "periodEnd": metadata["period_end"], "url": exhibit_url,
                        "issuerName": metadata["issuer_name"]})
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
                needs_review = reason in ("sec-vie-needs-review", "source-gap:ex21-needs-review")
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
                   guardedBudget={"valid": budget["requests"] <= MAX_HTTP and len(budget["ciks"]) <= MAX_CIKS,
                                  "maxCiks": MAX_CIKS, "maxHttp": MAX_HTTP})
    return document, summary
