#!/usr/bin/env python3
"""Mac mini owner for public filing extraction and cited macro facts.

Separate from the existing account/review/map jobs. Only public SEC/DART text
goes to the existing Codex login. No account, trading, KIS or Google API call.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.utils.mini_codex_reader import atomic_json, read_json_with_codex, strict_json

KST = timezone(timedelta(hours=9))
OFFICIAL_HOSTS = frozenset({"www.bok.or.kr", "bok.or.kr", "www.fsc.go.kr", "fsc.go.kr",
    "www.moef.go.kr", "moef.go.kr", "kostat.go.kr", "www.kostat.go.kr", "www.krx.co.kr",
    "www.federalreserve.gov", "federalreserve.gov", "www.bls.gov", "bls.gov",
    "www.bea.gov", "bea.gov", "www.ecb.europa.eu", "www.boj.or.jp"})


def stamp():
    return datetime.now(timezone.utc).isoformat()


def _official_url(url):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in OFFICIAL_HOSTS
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise ValueError("unapproved_macro_source")
    return url


class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        _official_url(newurl)
        return super().redirect_request(request, fp, code, message, headers, newurl)


def read_official_text(url):
    _official_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": "AlphaNest public-source verification"})
    with urllib.request.build_opener(OfficialRedirect()).open(request, timeout=30) as response:
        body = response.read(4_194_305)
        if len(body) > 4_194_304:
            raise ValueError("official_source_too_large")
        encoding = response.headers.get_content_charset() or "utf-8"
        text = body.decode(encoding, errors="replace")
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text))).strip()


def verify_macro_facts(result, *, now=None, reader=read_official_text):
    now = now or datetime.now(KST)
    if set(result) != {"global", "kr"}:
        raise ValueError("macro_regions_missing")
    accepted = {}
    for region in ("global", "kr"):
        facts = result[region]
        if not isinstance(facts, list) or len(facts) != 1:
            raise ValueError("macro_fact_count")
        checked = []
        for fact in facts:
            if not isinstance(fact, dict) or set(fact) != {"text", "source_url", "source_date", "source_quote"}:
                raise ValueError("macro_fact_shape")
            if any(not isinstance(v, str) for v in fact.values()):
                raise ValueError("macro_fact_type")
            _official_url(fact["source_url"])
            date = datetime.strptime(fact["source_date"], "%Y-%m-%d").replace(tzinfo=KST)
            if date > now or (now.date() - date.date()).days > 3:
                raise ValueError("macro_source_date_outside_window")
            quote = re.sub(r"\s+", " ", fact["source_quote"]).strip()
            if not 24 <= len(quote) <= 400 or not 1 <= len(fact["text"]) <= 600:
                raise ValueError("macro_fact_length")
            source = reader(fact["source_url"])
            if quote not in source:
                raise ValueError("macro_quote_not_in_primary_source")
            # Bind the claimed event/release date to the SAME exact quotation;
            # a model date or the collector's current date is not provenance.
            y, m, day = date.year, date.month, date.day
            date_forms = [date.strftime("%Y-%m-%d"), date.strftime("%B %d, %Y"),
                          f"{date.strftime('%B')} {day}, {y}", f"{date.strftime('%b')} {day}, {y}"]
            date_pattern = rf"{y}\s*(?:[./]|년)\s*0?{m}\s*(?:[./]|월)\s*0?{day}\s*(?:일|\b)"
            if not any(value in quote for value in date_forms) and not re.search(date_pattern, quote):
                raise ValueError("macro_date_not_in_same_primary_quote")
            # All numeric claims must occur in the independently fetched quote.
            if any(number not in quote for number in re.findall(r"\d+(?:[.,]\d+)*", fact["text"])):
                raise ValueError("unsupported_macro_number")
            checked.append(dict(fact, verification="primary_quote_exact_match"))
        accepted[region] = checked
    return accepted


def macro_bundle(verified, *, model, generated_at):
    sources = {}
    for region, facts in verified.items():
        sources["codex_" + region] = {
            "provider": "codex-cli", "model": model,
            "content": "\n".join(f"- {f['source_date']} {f['text']}" for f in facts),
            "citations": [f["source_url"] for f in facts], "facts": facts,
            "source_as_of": max(f["source_date"] for f in facts), "error": None}
    return {"contract": "macro-facts-v1", "producer": "mac-mini-codex",
            "generated_at": generated_at, "source_verification": "2/2", "sources": sources,
            "google_calls": 0, "_cache": "miss",
            "disclosure": {"note": "Primary-source facts only; no forecast, recommendation or score input.",
                           "legacy_chain_retired": True}}


def publish_macro(root, *, executor=subprocess.run):
    # Only public primary-source facts leave the Mini. The Mini never receives
    # a Supabase service-role key; the existing owner-only workflow uploads it.
    document = strict_json((root / "data/macro_synthesis.json").read_bytes())
    payload = json.dumps({"event_type": "mini_macro_facts", "client_payload": {"document": document}},
                         ensure_ascii=False, allow_nan=False).encode()
    result = executor(["gh", "api", "--method", "POST", "repos/gywns0126/VERITY/dispatches", "--input", "-"],
                      input=payload, capture_output=True, timeout=45)
    if result.returncode:
        raise ValueError("macro_delivery_dispatch_failed")
    return {"dispatch_accepted": True, "private_origin_readback": False,
            "delivery_status": "awaiting_owner_workflow_and_readback"}


def receive_dispatch(path, *, root=ROOT, reader=read_official_text, environ=None):
    environ = os.environ if environ is None else environ
    if (environ.get("GITHUB_EVENT_NAME") != "repository_dispatch"
            or not environ.get("GITHUB_REPOSITORY_OWNER")
            or environ.get("GITHUB_ACTOR") != environ.get("GITHUB_REPOSITORY_OWNER")):
        raise ValueError("macro_dispatch_actor_not_owner")
    if path.is_symlink() or path.stat().st_size > 65_536:
        raise ValueError("macro_dispatch_size_or_path")
    event = strict_json(path.read_bytes())
    if event.get("action") != "mini_macro_facts":
        raise ValueError("macro_dispatch_type")
    doc = event.get("client_payload", {}).get("document")
    if not isinstance(doc, dict) or set(doc) != {"contract", "producer", "generated_at", "verified_at",
            "source_verification", "sources", "google_calls", "_cache", "disclosure"}:
        raise ValueError("macro_dispatch_document_shape")
    if (doc["contract"] != "macro-facts-v1" or doc["producer"] != "mac-mini-codex"
            or doc["google_calls"] != 0 or doc["source_verification"] != "2/2"
            or set(doc["sources"]) != {"codex_global", "codex_kr"}):
        raise ValueError("macro_dispatch_contract")
    generated = datetime.fromisoformat(doc["generated_at"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    if generated.tzinfo is None or generated > now or now - generated > timedelta(hours=36):
        raise ValueError("macro_dispatch_generation_clock")
    facts = {region: doc["sources"]["codex_" + region]["facts"] for region in ("global", "kr")}
    # Drop producer-side verification labels before independently verifying.
    facts = {region: [{k: fact[k] for k in ("text", "source_url", "source_date", "source_quote")} for fact in rows]
             for region, rows in facts.items()}
    verified = verify_macro_facts(facts, reader=reader)
    model = doc["sources"]["codex_global"]["model"]
    if model != doc["sources"]["codex_kr"]["model"] or model != "gpt-6.1-sol":
        raise ValueError("macro_dispatch_model")
    value = macro_bundle(verified, model=model, generated_at=doc["generated_at"])
    value["verified_at"] = stamp()
    atomic_json(root / "data/macro_synthesis.json", value)
    return {"status": "verified", "source_verification": "2/2", "google_calls": 0,
            "generated_at": doc["generated_at"]}


def publish_cache(path, *, root, executor=subprocess.run):
    relative = str(path.relative_to(root))
    if not re.fullmatch(r"data/filing_extraction_cache/(sec-properties-v1|dart-facilities-v1)/[0-9a-f]{64}\.json", relative):
        raise ValueError("unapproved_public_cache_path")
    endpoint = "repos/gywns0126/VERITY/contents/" + relative
    body = path.read_bytes()
    existing = executor(["gh", "api", endpoint, "-H", "Accept: application/vnd.github.raw+json"],
                        capture_output=True, timeout=30)
    if existing.returncode == 0:
        if existing.stdout != body:
            raise ValueError("immutable_cache_conflict")
        return {"path": relative, "published": False, "readback_equal": True}
    if b"404" not in existing.stderr:
        raise ValueError("cache_readback_unavailable")
    import base64
    payload = json.dumps({"message": "data: add source-bound Mini filing extraction",
                          "content": base64.b64encode(body).decode(), "branch": "main"}).encode()
    executor(["gh", "api", "--method", "PUT", endpoint, "--input", "-"], input=payload,
             capture_output=True, timeout=45)
    # Read back even if the write response was lost. Never overwrite a cache.
    actual = executor(["gh", "api", endpoint, "-H", "Accept: application/vnd.github.raw+json"],
                      capture_output=True, timeout=30)
    if actual.returncode or actual.stdout != body:
        raise ValueError("cache_publication_not_verified")
    return {"path": relative, "published": True, "readback_equal": True,
            "sha256": hashlib.sha256(body).hexdigest()}


def filing_input(row):
    ticker = str(row.get("ticker") or "")
    if row.get("currency") == "USD" or re.fullmatch(r"[A-Z][A-Z.\-]{0,9}", ticker):
        from api.collectors.sec_edgar import fetch_10k_properties_section
        from api.analyzers.properties_parser import build_10k_properties_prompt, validate_10k_properties_data
        raw = fetch_10k_properties_section(ticker, os.environ.get("SEC_EDGAR_USER_AGENT", ""))
        if raw.get("error") or not raw.get("raw_text"):
            raise ValueError("sec_source_unavailable")
        source = {"source_id": "source:sec:" + raw["accession"], "as_of": raw["filed_date"], "url": raw["url"]}
        return "sec-properties-v1", raw["raw_text"], source, build_10k_properties_prompt, validate_10k_properties_data
    from api.collectors.DartScout import fetch_business_facilities_raw
    from api.analyzers.facilities_parser import build_business_facilities_prompt, validate_business_facilities_data
    corp = row.get("corp_code")
    if not corp:
        mapping = strict_json((ROOT / "data/mapping.json").read_bytes())
        corp = mapping.get(ticker.split(".")[0].zfill(6))
    if not corp:
        raise ValueError("dart_identity_missing")
    raw = fetch_business_facilities_raw(corp)
    if raw.get("error") or not raw.get("raw_text"):
        raise ValueError("dart_source_unavailable")
    source_id = raw["rcept_no"]
    day = raw["rcept_dt"]
    source = {"source_id": "source:dart:" + source_id, "as_of": day[:4] + "-" + day[4:6] + "-" + day[6:8],
              "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + source_id}
    text = raw["raw_text"]
    if raw.get("ppe_note_text"):
        text += "\n\n=== 유형자산 주석 ===\n" + raw["ppe_note_text"]
    return "dart-facilities-v1", text, source, build_business_facilities_prompt, validate_business_facilities_data


def run_filings(args):
    from api.utils.filing_extraction_cache import cache_read, cache_write, filing_source_sha256, filing_cache_path
    if args.ticker:
        domestic = re.fullmatch(r"\d{6}(?:\.(?:KS|KQ))?", args.ticker)
        rows = [{"ticker": args.ticker, "name": args.ticker, "currency": "KRW" if domestic else "USD"}]
    else:
        document = strict_json((ROOT / "data/recommendations.json").read_bytes())
        rows = document if isinstance(document, list) else document.get("recommendations", [])
    state_path = args.runtime / "filing-rotation.json"
    state = strict_json(state_path.read_bytes()) if state_path.exists() else {"cursor": 0}
    count = min(args.max_filings, len(rows))
    results = []
    for index in range(count):
        row = rows[(state["cursor"] + index) % len(rows)]
        result = {"ticker": str(row.get("ticker") or ""), "google_calls": 0}
        try:
            extractor, raw, source, builder, validator = filing_input(row)
            digest = filing_source_sha256(extractor, raw)
            parameters = dict(extractor=extractor, raw_sha256=digest, **source)
            cached = cache_read(**parameters)
            if cached:
                path = filing_cache_path(extractor, source["source_id"], source["as_of"], digest)
                result.update(status="cache_hit", ai_invocations=0)
            else:
                prompt = builder(row.get("name", ""), row["ticker"], raw,
                                 source_id=source["source_id"], as_of=source["as_of"], source_url=source["url"])
                value, receipt = read_json_with_codex(prompt, cli=args.cli, model=args.model, runtime=args.runtime,
                    identity="\0".join((extractor, source["source_id"], source["as_of"], digest)))
                data = validator(value)
                path = cache_write(**parameters, generated_at=receipt["completed_at"], data=data)
                result.update(status="ready", ai_invocations=int(not receipt["reused"]),
                              source_id=source["source_id"], source_as_of=source["as_of"],
                              cache_path=str(path.relative_to(ROOT)))
            result.update(source_id=source["source_id"], source_as_of=source["as_of"],
                          cache_path=str(path.relative_to(ROOT)))
            if args.publish:
                result["delivery"] = publish_cache(path, root=ROOT)
        except Exception as exc:
            result.update(status="pending", error_type=type(exc).__name__)
            if isinstance(exc, ValueError) and re.fullmatch(r"[a-z_]{1,80}", str(exc)):
                result["reason"] = str(exc)
        results.append(result)
    if not args.ticker:
        state["cursor"] = (state["cursor"] + count) % max(1, len(rows))
        atomic_json(state_path, state)
    return {"processed": count, "total_candidates": len(rows), "results": results}


def run_macro(args):
    today = datetime.now(KST).strftime("%Y-%m-%d")
    prompt = (f"Today in Korea is {today}. Collect public macroeconomic FACTS only from the last72hours. "
        "Use primary releases from Bank of Korea, FSC, Korean government/statistics office, Fed, BLS, BEA, ECB, BOJ. "
        "Search and open the exact primary release. No forecast, stock opinion, portfolio or causal speculation. "
        "Return JSON with exactly two arrays: global and kr, each exactly1 fact. Each fact has exactly text "
        "(concise Korean factual statement), source_url (direct official HTML), source_date (YYYY-MM-DD), "
        "source_quote (24to400 consecutive characters copied exactly from the source, including every numeric "
        "claim used in text AND its full source_date including year/month/day in that SAME consecutive quote). "
        "Choose a release whose visible date and first factual paragraph fit in400characters. "
        "No PDF or third-party URLs. Do not invent or infer dates from the current date. "
        "Do not access local files, credentials or accounts. No file edits, commands, APIs or messages.")
    # v1's empty result came from the disabled internal bridge and was never
    # delivered. Keep that receipt; the owner-approved bridge fix gets one
    # separate v2 attempt per day, with the same no-automatic-retry boundary.
    value, receipt = read_json_with_codex(prompt, cli=args.cli, model=args.model, runtime=args.runtime,
                                        identity="macro-facts-v1:bridge-v2:" + today, search=True)
    verified = verify_macro_facts(value)
    document = macro_bundle(verified, model=args.model, generated_at=receipt["completed_at"])
    document["verified_at"] = stamp()
    atomic_json(ROOT / "data/macro_synthesis.json", document)
    result = {"source_verification": "2/2", "ai_invocations": int(not receipt["reused"]), "google_calls": 0,
              "source_as_of": {key: val["source_as_of"] for key, val in document["sources"].items()}}
    if args.publish:
        result["delivery"] = publish_macro(ROOT)
    return result


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--receive-dispatch":
        print(json.dumps(receive_dispatch(Path(sys.argv[2]))))
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--model", default="gpt-6.1-sol")
    parser.add_argument("--phase", choices=("filings", "macro", "all"), default="all")
    parser.add_argument("--max-filings", type=int, default=3)
    parser.add_argument("--ticker")
    parser.add_argument("--dart-key-file", type=Path)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.max_filings <= 5 or not args.cli.is_absolute() or not args.runtime.is_absolute():
        parser.error("bounded absolute Mini runtime required")
    if sys.platform != "darwin" or "macmini" not in socket.gethostname().lower():
        parser.error("this producer runs only on the Mac mini")
    if args.dart_key_file:
        path = args.dart_key_file
        if path.is_symlink() or path.stat().st_mode & 0o077 or path.stat().st_uid != os.getuid():
            parser.error("DART public-reader key file must be owner-only")
        key = strict_json(path.read_bytes())
        if set(key) != {"DART_API_KEY"} or not isinstance(key["DART_API_KEY"], str):
            parser.error("invalid DART public-reader credential")
        os.environ["DART_API_KEY"] = key["DART_API_KEY"]
    args.runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(args.runtime / "worker.lock", "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({"status": "busy", "google_calls": 0})); return 0
        result = {"schema": "mini-document-readers-v1", "host": socket.gethostname(), "started_at": stamp(),
                  "model": args.model, "google_calls": 0, "status": "done"}
        if args.phase in ("filings", "all"):
            result["filings"] = run_filings(args)
        if args.phase in ("macro", "all"):
            try:
                result["macro"] = run_macro(args)
            except Exception as exc:
                result.update(status="partial", macro={"status": "pending", "error_type": type(exc).__name__})
                if isinstance(exc, ValueError) and re.fullmatch(r"[a-z_]{1,80}", str(exc)):
                    result["macro"]["reason"] = str(exc)
        result["completed_at"] = stamp()
        if any(row.get("status") == "pending" for row in result.get("filings", {}).get("results", [])):
            result["status"] = "partial"
        atomic_json(args.runtime / "latest.json", result)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["status"] == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
