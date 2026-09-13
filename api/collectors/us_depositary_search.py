"""Search-only US depositary/registered shares. Never expands the trading universe.

Polygon CS excludes ADRC (TSM/BABA/NVO). Preserve a separate typed reference
catalog for universe_search, with Naver display names (metadata only, no prices).
The existing monthly universe job refreshes this catalog; failed/incomplete
reference fetches preserve the last successful file without changing its date.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "data/us_depositary_search.json"
TYPES = ("ADRC", "NYRS")
EXCHANGES = {"XNAS", "XNYS", "XASE", "ARCX", "BATS"}


def _json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 AlphaNest-reference"})
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.load(response)


def reference_rows(key, get=_json, pause=time.sleep):
    """Complete pages only. No prices, financials, OTC, preferreds or warrants."""
    rows = {}
    counts = {}
    for kind in TYPES:
        url = "https://api.polygon.io/v3/reference/tickers?" + urllib.parse.urlencode(
            {"market": "stocks", "active": "true", "type": kind, "limit": 1000})
        count = 0
        pages = 0
        while url:
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme != "https" or parsed.hostname not in {"api.polygon.io", "api.massive.com"}:
                raise ValueError("untrusted_reference_page")
            if pages >= 12:
                raise ValueError("incomplete_reference_pages")
            doc = get(url + ("&" if "?" in url else "?") + urllib.parse.urlencode({"apiKey": key}))
            if doc.get("status") not in {"OK", "DELAYED"} or not isinstance(doc.get("results", []), list):
                raise ValueError("invalid_reference_response")
            pages += 1
            for item in doc.get("results", []):
                ticker = str(item.get("ticker") or "").strip().upper()
                name = str(item.get("name") or "").strip()
                if (item.get("active") is not True or item.get("locale") != "us"
                        or item.get("type") != kind or item.get("primary_exchange") not in EXCHANGES
                        or not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,14}", ticker) or not name):
                    continue
                rows[ticker] = {"ticker": ticker, "name": name, "market": "US",
                                "reference_type": kind, "exchange": item["primary_exchange"]}
                count += 1
            url = doc.get("next_url")
            if url:
                pause(13)
        counts[kind] = count
        if kind != TYPES[-1]:
            pause(13)
    if len(rows) < 100:
        raise ValueError("reference_coverage_below_floor")
    return [rows[t] for t in sorted(rows)], counts


def display_name(ticker, get=_json):
    """Accept exact US symbol only; Latin display names such as TSMC are valid."""
    url = "https://ac.stock.naver.com/ac?" + urllib.parse.urlencode({"q": ticker, "target": "stock,worldstock,index"})
    try:
        for item in get(url).get("items", []):
            if str(item.get("code", "")).upper() == ticker and item.get("nationCode") == "USA":
                return str(item.get("name") or "").strip()
    except Exception:
        pass
    return ""


def refresh_catalog(key, output=OUTPUT, name_budget=240):
    rows, counts = reference_rows(key)
    try:
        old = json.loads(Path(output).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    previous = {r["ticker"]: r.get("name_ko", "") for r in old.get("stocks", [])}
    started = time.monotonic()
    for index, row in enumerate(rows):
        name = previous.get(row["ticker"], "")
        if not name and time.monotonic() - started < name_budget:
            name = display_name(row["ticker"])
            time.sleep(0.35)
        if name:
            row["name_ko"] = name
        if (index + 1) % 25 == 0:
            print(f"[depositary_search] names {index+1}/{len(rows)}", flush=True)
    doc = {"_meta": {"generated_at": datetime.now(timezone.utc).isoformat(),
                      "source": "Polygon active ADRC/NYRS reference; Naver exact-US-symbol display names",
                      "scope": "search_only_not_trading_universe", "count": len(rows),
                      "types": counts, "with_display_name": sum(bool(r.get("name_ko")) for r in rows)},
           "stocks": rows}
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output)
    return doc


def append_catalog(uni, path=OUTPUT):
    """Merge slim catalog into search only, preserving existing records/metadata."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if doc.get("_meta", {}).get("scope") != "search_only_not_trading_universe":
        raise ValueError("wrong_catalog_scope")
    catalog = doc.get("stocks")
    if (not isinstance(catalog, list) or len(catalog) < 100
            or doc.get("_meta", {}).get("count") != len(catalog)):
        raise ValueError("incomplete_catalog")
    # Validate the complete catalog before mutating the caller's list.
    for row in catalog:
        if (not isinstance(row, dict) or row.get("market") != "US"
                or row.get("reference_type") not in TYPES
                or row.get("exchange") not in EXCHANGES
                or not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,14}", str(row.get("ticker", "")))
                or not isinstance(row.get("name"), str) or not row["name"].strip()):
            raise ValueError("invalid_catalog_row")
    if len({r["ticker"] for r in catalog}) != len(catalog):
        raise ValueError("duplicate_catalog_ticker")
    existing = {str(r.get("ticker", "")).upper(): r for r in uni}
    added = 0
    for row in catalog:
        ticker = row["ticker"]
        if ticker in existing:
            # Only fill missing display metadata; never overwrite a newer name/market.
            if not existing[ticker].get("name_ko") and row.get("name_ko"):
                existing[ticker]["name_ko"] = row["name_ko"]
            continue
        entry = {k: row[k] for k in ("ticker", "name", "market", "reference_type", "exchange", "name_ko") if k in row}
        uni.append(entry)
        existing[ticker] = entry
        added += 1
    return added, doc.get("_meta", {})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--name-budget", type=int, default=240)
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv()
    key = os.environ.get("POLYGON_API_KEY")
    if not key:
        print("[depositary_search] missing key; existing catalog preserved")
        return 1
    try:
        doc = refresh_catalog(key, args.output, args.name_budget)
        print(json.dumps(doc["_meta"], ensure_ascii=False))
        return 0
    except Exception as exc:
        # Exception strings/URLs can contain the API key. Only expose the class.
        print(f"[depositary_search] failed {type(exc).__name__}; existing catalog preserved")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
