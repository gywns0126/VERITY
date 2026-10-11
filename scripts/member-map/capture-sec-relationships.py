#!/usr/bin/env python3
"""Bounded SEC annual source capture using existing SEC transport identity.

Whole listed-US catalog selection, no member portfolio or model. The source
catalog is updated only with --apply-local; public posting remains separate.
"""
import argparse
from copy import deepcopy
from datetime import date
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from api.collectors.sec_companyfacts_bulk import _headers, TICKER_URL
from api.intelligence.portfolio_sec_relationships import capture_sec_html, validate_sec_capture


def helper_module():
    spec = importlib.util.spec_from_file_location("sec_capture_io", Path(__file__).with_name("capture-contract-facts.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get_public(url, maximum=16 * 1024 * 1024):
    if not (url == TICKER_URL or re.fullmatch(r"https://data\.sec\.gov/submissions/CIK[0-9]{10}\.json", url)
            or re.fullmatch(r"https://www\.sec\.gov/Archives/edgar/data/[0-9]+/[0-9]{18}/[A-Za-z0-9_-]+\.html?", url)):
        raise ValueError("sec-url-rejected")
    time.sleep(0.15)
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise ValueError("sec-redirect-rejected")
    with urllib.request.build_opener(NoRedirect()).open(
            urllib.request.Request(url, headers=_headers()), timeout=30) as response:
        raw = response.read(maximum + 1)
    if not raw or len(raw) > maximum:
        raise ValueError("sec-response-size")
    return raw


def select_catalog(universe, *, offset, limit):
    rows = universe.get("stocks", [])
    rows = list(rows.values()) if type(rows) is dict else rows
    if type(rows) is not list:
        raise ValueError("sec-universe-shape")
    ids = sorted({r["ticker"] for r in rows if type(r) is dict and r.get("market") == "US"
                  and type(r.get("ticker")) is str and re.fullmatch(r"[A-Z][A-Z0-9]{0,9}(?:[.-][A-Z0-9]{1,2})?", r["ticker"])})
    # Explicit offset supports resumable batches without a handpicked ticker list.
    return ids[offset:offset + limit], len(ids)


def latest_metadata(ticker, cik, submission):
    if (str(submission.get("cik", "")).zfill(10) != cik
            or ticker not in submission.get("tickers", [])):
        raise ValueError("sec-submission-identity")
    recent = submission.get("filings", {}).get("recent", {})
    fields = ("form", "filingDate", "reportDate", "accessionNumber", "primaryDocument")
    if (type(recent) is not dict or any(type(recent.get(key)) is not list for key in fields)
            or len({len(recent[key]) for key in fields}) != 1
            or any(type(value) is not str for key in fields for value in recent[key])):
        raise ValueError("sec-submission-shape")
    eligible = [i for i, form in enumerate(recent.get("form", [])) if form in ("10-K", "20-F")]
    if not eligible:
        raise ValueError("sec-no-annual")
    index = max(eligible, key=lambda i: (recent["filingDate"][i], recent["accessionNumber"][i]))
    accession, primary = recent["accessionNumber"][index], recent["primaryDocument"][index]
    # Amendments require their own original/amended comparison; don't silently
    # use the old annual as if it includes a newer amendment.
    filed = recent["filingDate"][index]
    if any(form in ("10-K/A", "20-F/A") and recent["filingDate"][i] >= filed
           for i, form in enumerate(recent.get("form", []))):
        raise ValueError("sec-amendment-needs-review")
    metadata = {"issuer_id": "US:" + ticker, "issuer_name": submission["name"],
                "cik": cik, "accession": accession, "filed_date": filed,
                "period_end": recent["reportDate"][index], "form": recent["form"][index],
                "primary_document": primary,
                "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{primary}"}
    validate_sec_capture({**metadata, "schema": "sec-annual-excerpts-v1", "document_sha256": "0" * 64, "paragraphs": []})
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--fetch-public", action="store_true")
    parser.add_argument("--apply-local", action="store_true")
    args = parser.parse_args()
    if args.offset < 0 or not 1 <= args.limit <= 20 or (args.apply_local and not args.fetch_public):
        parser.error("offset >= 0, limit 1..20; apply requires fetch-public")
    helper = helper_module()
    baseline = helper._read_regular_json(args.source_dir / "member_map_auto_evidence.json")
    helper._validate_capture_fields(baseline, baseline)
    universe = helper._read_regular_json(args.source_dir / "universe_search.json")
    selected, total = select_catalog(universe, offset=args.offset, limit=args.limit)
    summary = {"schema": "sec-relationship-capture-run-v1", "as_of": date.today().isoformat(),
               "catalog_total": total, "selected": len(selected), "offset": args.offset,
               "next_offset": args.offset + len(selected), "attempted": 0, "captured": 0,
               "cached": 0, "public_gets": 0, "model_calls": 0, "rows": [], "published": False}
    if not args.fetch_public:
        print(json.dumps(summary)); return 0
    args.output_dir.mkdir(parents=True, exist_ok=False)
    captures = {(r["issuer_id"], r["accession"]): r for r in baseline.get("sec_filing_excerpts", [])}
    try:
        summary["public_gets"] += 1
        mapping = json.loads(get_public(TICKER_URL, 4 * 1024 * 1024), object_pairs_hook=helper._strict_object)
        ticker_map = {r["ticker"]: str(r["cik_str"]).zfill(10) for r in mapping.values()}
        for ticker in selected:
            summary["attempted"] += 1
            record = {"ticker": ticker}
            summary["rows"].append(record)
            try:
                cik = ticker_map.get(ticker)
                if cik is None:
                    record["status"] = "sec-identity-not-found"; continue
                summary["public_gets"] += 1
                submission = json.loads(get_public(f"https://data.sec.gov/submissions/CIK{cik}.json", 8 * 1024 * 1024),
                                        object_pairs_hook=helper._strict_object)
                metadata = latest_metadata(ticker, cik, submission)
                key = (metadata["issuer_id"], metadata["accession"])
                if key in captures:
                    record["status"] = "cached"; summary["cached"] += 1; continue
                summary["public_gets"] += 1
                raw = get_public(metadata["url"])
                capture = capture_sec_html(raw, metadata)
                captures[key] = capture
                record.update(status="captured", accession=metadata["accession"], paragraphs=len(capture["paragraphs"]))
                summary["captured"] += 1
            except urllib.error.HTTPError as error:
                record.update(status="source-http-error", http_status=error.code)
                if error.code in (401, 403, 429):
                    summary["stopped"] = "sec-access-or-rate-limit"; break
            except (ValueError, KeyError, TypeError, OSError) as error:
                record["status"] = (str(error) if isinstance(error, ValueError) and re.fullmatch(r"sec-[a-z-]+", str(error))
                                    else "sec-source-rejected")
    except (ValueError, KeyError, TypeError, OSError) as error:
        summary["stopped"] = "sec-catalog-fetch-failed"
        if isinstance(error, urllib.error.HTTPError):
            summary["http_status"] = error.code
    summary["next_offset"] = args.offset + summary["attempted"]
    evidence = deepcopy(baseline)
    evidence["sec_filing_excerpts"] = sorted(captures.values(), key=lambda r: (r["issuer_id"], r["accession"]))
    helper._validate_capture_fields(baseline, evidence)
    helper.write_result(args.output_dir / "manifest.json", summary)
    helper.write_result(args.output_dir / "member_map_auto_evidence.json", evidence)
    if args.apply_local and summary["captured"]:
        helper.write_result(args.output_dir / "local-apply.json", helper.apply_local(args.source_dir, baseline, evidence, args.output_dir))
    print(json.dumps(summary))
    return 2 if summary.get("stopped") else 0


if __name__ == "__main__":
    raise SystemExit(main())
