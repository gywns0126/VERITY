#!/usr/bin/env python3
"""Select and locally capture bounded annual-report customer-table sources.

Default operation is local-only: it may reuse receipt-keyed ZIPs in --archive-dir,
but never accesses the network or updates the source catalog without opt-in flags.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
from calendar import monthrange
import os
from pathlib import Path
import re
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.intelligence.portfolio_filing_excerpts import _legal_name

HELPER_PATH = Path(__file__).with_name("capture-contract-facts.py")
_RECEIPT = re.compile(r"[0-9]{14}\Z", re.ASCII)
_CORP = re.compile(r"[0-9]{8}\Z", re.ASCII)
_TICKER = re.compile(r"[0-9]{6}\Z", re.ASCII)
_DAY = re.compile(r"[0-9]{8}\Z", re.ASCII)
_REPORT = re.compile(r"(?:\[(?:기재정정|첨부정정|첨부추가)\])*사업보고서 \(([0-9]{4})\.([0-9]{2})\)\Z")
_MAX_LIMIT = 6
_DEFAULT_LIMIT = 3
_MAX_JSON_BYTES = 8 * 1024 * 1024
_MAX_OVERVIEW_JSON_BYTES = 32 * 1024 * 1024
_MAX_ARCHIVE_BYTES = 4 * 1024 * 1024
_DART_DOCUMENT_URL = "https://opendart.fss.or.kr/api/document.xml"
_DART_STATUS = re.compile(rb"<status>\s*([0-9]{3})\s*</status>", re.IGNORECASE)
_ATTEMPT_SCHEMA = "local-public-annual-capture-attempts-v1"
_ATTEMPT_REASONS = frozenset({"archive-invalid", "source-fetch-failed", "parse-rejected"})
_ATTEMPT_LEDGER_MAX_BYTES = 512 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("public-redirect-refused")


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate-json-key")
        result[key] = value
    return result


def _read_json(path: Path, *, maximum=_MAX_JSON_BYTES):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("invalid-json-input-path")
        chunks, size = [], 0
        while True:
            chunk = os.read(descriptor, min(65536, maximum + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > maximum:
                raise ValueError("json-input-too-large")
    finally:
        os.close(descriptor)
    try:
        value = json.loads(b"".join(chunks).decode("utf-8"), object_pairs_hook=_strict_object)
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError("invalid-json-input") from None
    if not isinstance(value, dict):
        raise ValueError("invalid-json-input")
    return value


def _identity_catalog(evidence):
    index = evidence.get("tickerIndex")
    if not isinstance(index, dict):
        raise ValueError("evidence-identity-index-missing")
    catalog = []
    for identifier, row in index.items():
        issuer = row.get("issuer") if isinstance(row, dict) else None
        if not isinstance(issuer, dict) or issuer.get("market") != "KR":
            continue
        ticker, name = issuer.get("ticker"), issuer.get("name")
        if (not isinstance(ticker, str) or not _TICKER.fullmatch(ticker)
                or identifier != "KR:" + ticker or not isinstance(name, str) or not name.strip()):
            continue
        catalog.append({"id": identifier, "ticker": ticker, "market": "KR", "name": name})
    return catalog


def _validate_attempt_ledger(value):
    if (type(value) is not dict or set(value) != {"schema", "receipts"}
            or value.get("schema") != _ATTEMPT_SCHEMA or type(value.get("receipts")) is not dict
            or len(value["receipts"]) > 10000):
        raise ValueError("annual-attempt-ledger-invalid")
    for receipt, entry in value["receipts"].items():
        if (not isinstance(receipt, str) or _RECEIPT.fullmatch(receipt) is None
                or type(entry) is not dict or set(entry) != {"failures", "reason"}
                or type(entry["failures"]) is not int or not 0 <= entry["failures"] <= 2
                or entry["reason"] not in _ATTEMPT_REASONS):
            raise ValueError("annual-attempt-ledger-invalid")
    return value


def _read_attempt_ledger(source_dir):
    path = source_dir / "member_map_annual_capture_attempts.json"
    try:
        info = path.lstat()
    except FileNotFoundError:
        return {"schema": _ATTEMPT_SCHEMA, "receipts": {}}, None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ValueError("annual-attempt-ledger-path-invalid")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("annual-attempt-ledger-path-invalid")
        chunks, size = [], 0
        while True:
            chunk = os.read(descriptor, min(65536, _ATTEMPT_LEDGER_MAX_BYTES + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > _ATTEMPT_LEDGER_MAX_BYTES:
                break
        raw = b"".join(chunks)
    finally:
        os.close(descriptor)
    if not raw or len(raw) > _ATTEMPT_LEDGER_MAX_BYTES:
        raise ValueError("annual-attempt-ledger-invalid")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_object)
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError("annual-attempt-ledger-invalid") from None
    return _validate_attempt_ledger(value), raw


def _update_attempt_ledger(ledger, receipt, outcome):
    receipts = ledger["receipts"]
    if outcome == "success":
        receipts.pop(receipt, None)
    elif outcome in _ATTEMPT_REASONS:
        previous = receipts.get(receipt, {"failures": 0, "reason": outcome})
        receipts[receipt] = {"failures": min(2, previous["failures"] + 1), "reason": outcome}
    elif outcome not in {"access-stop", "rate-limit"}:
        raise ValueError("annual-attempt-outcome-invalid")
    return ledger


def _write_attempt_ledger_atomic(source_dir, expected_raw, ledger):
    _validate_attempt_ledger(ledger)
    raw = json.dumps(ledger, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    if len(raw) > _ATTEMPT_LEDGER_MAX_BYTES:
        raise ValueError("annual-attempt-ledger-too-large")
    directory = os.open(source_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    lock_fd = temporary = None
    try:
        lock_fd = os.open(".member-map-contract-update.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
                          0o600, dir_fd=directory)
        if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
            raise ValueError("annual-attempt-ledger-lock-invalid")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            current_fd = os.open("member_map_annual_capture_attempts.json",
                                 os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        except FileNotFoundError:
            current = None
        else:
            with os.fdopen(current_fd, "rb") as handle:
                if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                    raise ValueError("annual-attempt-ledger-path-invalid")
                chunks, size = [], 0
                while True:
                    chunk = handle.read(min(65536, _ATTEMPT_LEDGER_MAX_BYTES + 1 - size))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > _ATTEMPT_LEDGER_MAX_BYTES:
                        break
                current = b"".join(chunks)
        if current != expected_raw:
            raise ValueError("annual-attempt-ledger-changed-during-run")
        temporary = ".member-map-annual-attempts-" + uuid.uuid4().hex + ".tmp"
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, "member_map_annual_capture_attempts.json",
                   src_dir_fd=directory, dst_dir_fd=directory)
        temporary = None
        os.fsync(directory)
    finally:
        if temporary is not None:
            os.unlink(temporary, dir_fd=directory)
        if lock_fd is not None:
            os.close(lock_fd)
        os.close(directory)


def select_candidates(overview, mapping, evidence, *, limit=_DEFAULT_LIMIT, today=None,
                      company_catalog=None, attempt_ledger=None):
    """Return exact-receipt annual candidates and denominator/rejection counts."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= _MAX_LIMIT:
        raise ValueError("limit-out-of-range")
    rows = overview.get("rows") if isinstance(overview, dict) else None
    if not isinstance(rows, dict) or (mapping is not None and not isinstance(mapping, dict)):
        raise ValueError("annual-source-shape-invalid")
    captured_rows = evidence.get("annual_customer_tables", []) if isinstance(evidence, dict) else None
    if not isinstance(captured_rows, list):
        raise ValueError("annual-capture-history-invalid")
    captured = set()
    for item in captured_rows:
        receipt = item.get("receipt_no") if isinstance(item, dict) else None
        if not isinstance(receipt, str) or not _RECEIPT.fullmatch(receipt):
            raise ValueError("annual-capture-history-invalid")
        captured.add(receipt)
    attempt_receipts = (_validate_attempt_ledger(attempt_ledger)["receipts"]
                        if attempt_ledger is not None else {})
    catalog_rows = company_catalog if company_catalog is not None else _identity_catalog(evidence)
    catalog = {item["id"].split(":", 1)[1]: item for item in catalog_rows
               if isinstance(item, dict) and isinstance(item.get("id"), str)
               and item["id"].startswith("KR:")}
    today = today or date.today()
    counts = {"input_rows": len(rows), "exact_corp_matches": 0, "valid_annual_metadata": 0,
              "already_captured": 0, "duplicate_receipts": 0, "rejected": 0}
    reasons = {}
    examples = {}
    by_receipt = {}

    def reject(reason, ticker):
        counts["rejected"] += 1
        reasons[reason] = reasons.get(reason, 0) + 1
        if len(examples.setdefault(reason, [])) < 3:
            examples[reason].append(ticker)

    for ticker, row in rows.items():
        if not isinstance(ticker, str) or not _TICKER.fullmatch(ticker) or not isinstance(row, dict):
            reject("row-shape-invalid", str(ticker)[:24])
            continue
        row_corp = row.get("corp_code")
        corp = mapping.get(ticker) if mapping is not None else row_corp
        if (not isinstance(corp, str) or not _CORP.fullmatch(corp)
                or row_corp != corp):
            reject("corp-code-not-exact", ticker)
            continue
        counts["exact_corp_matches"] += 1
        company = catalog.get(ticker)
        receipt, filed_on = row.get("rcept_no"), row.get("rcept_dt")
        year, report_name = row.get("bsns_year"), row.get("report_nm")
        report_match = _REPORT.fullmatch(report_name) if isinstance(report_name, str) else None
        try:
            filed = date(int(filed_on[:4]), int(filed_on[4:6]), int(filed_on[6:8])) if isinstance(filed_on, str) and _DAY.fullmatch(filed_on) else None
        except ValueError:
            filed = None
        try:
            report_year = int(report_match.group(1)) if report_match else None
            report_month = int(report_match.group(2)) if report_match else None
            report_last_day = monthrange(report_year, report_month)[1] if report_match else None
            period_end = date(report_year, report_month, report_last_day) if report_match else None
        except (TypeError, ValueError, OverflowError):
            period_end = None
        row_name = row.get("name")
        name_matches = (isinstance(row_name, str) and company is not None
                        and _legal_name(row_name).casefold() == _legal_name(company["name"]).casefold())
        receipt_valid = isinstance(receipt, str) and _RECEIPT.fullmatch(receipt) is not None
        if (company is None or not name_matches
                or not receipt_valid
                or not isinstance(year, str) or not re.fullmatch(r"[0-9]{4}", year, re.ASCII)
                or report_match is None or report_match.group(1) != year
                or filed is None or receipt[:8] != filed_on
                or filed > today or period_end is None or filed < period_end):
            reject("annual-source-metadata-invalid", ticker)
            continue
        counts["valid_annual_metadata"] += 1
        if receipt in captured:
            counts["already_captured"] += 1
            continue
        candidate = {"ticker": ticker, "issuer_id": company["id"], "issuer_name": company["name"],
                     "corp_code": corp, "receipt_no": receipt, "filed_on": filed.isoformat(),
                     "fiscal_year": year, "report_name": report_name}
        by_receipt.setdefault(receipt, []).append(candidate)

    eligible = []
    for receipt, matches in by_receipt.items():
        if len(matches) != 1:
            counts["duplicate_receipts"] += len(matches)
            reasons["receipt-multiple-issuers"] = reasons.get("receipt-multiple-issuers", 0) + 1
            continue
        eligible.append(matches[0])
    eligible.sort(key=lambda item: (item["filed_on"], item["receipt_no"]), reverse=True)
    skipped_after_failures = sum(1 for item in eligible
                                 if attempt_receipts.get(item["receipt_no"], {}).get("failures", 0) >= 2)
    eligible = [item for item in eligible
                if attempt_receipts.get(item["receipt_no"], {}).get("failures", 0) < 2]
    return eligible[:limit], {"counts": counts, "rejection_reasons": reasons,
                              "rejection_examples": examples,
                              "unique_uncaptured_receipts": len(eligible),
                              "skipped_after_failures": skipped_after_failures,
                              "selected": min(limit, len(eligible)), "limit": limit}


def _archive_path(archive_dir: Path, receipt: str):
    for name in (receipt + ".zip", "dart-document-" + receipt + ".zip"):
        path = archive_dir / name
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise ValueError("invalid-archive-cache-file")
        return path
    return None


def _read_archive(path: Path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= _MAX_ARCHIVE_BYTES:
            raise ValueError("archive-size-rejected")
        raw = bytearray()
        while len(raw) <= _MAX_ARCHIVE_BYTES:
            chunk = os.read(descriptor, min(65536, _MAX_ARCHIVE_BYTES + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        if not 0 < len(raw) <= _MAX_ARCHIVE_BYTES:
            raise ValueError("archive-size-rejected")
    finally:
        os.close(descriptor)
    try:
        with zipfile.ZipFile(__import__("io").BytesIO(raw)) as archive:
            if not any(name.lower().endswith(".xml") for name in archive.namelist()):
                raise ValueError("archive-xml-missing")
    except (OSError, zipfile.BadZipFile):
        raise ValueError("archive-invalid") from None
    return bytes(raw)


def _fetch_archive(receipt: str, api_key: str, opener=None):
    if not isinstance(receipt, str) or _RECEIPT.fullmatch(receipt) is None:
        raise ValueError("invalid-receipt")
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("dart-key-missing")
    url = _DART_DOCUMENT_URL + "?" + urllib.parse.urlencode({"crtfc_key": api_key, "rcept_no": receipt})
    request = urllib.request.Request(url, headers={"User-Agent": "AlphaNest-Public-Annual-Table-Capture/1.0"})
    opener = opener or urllib.request.build_opener(NoRedirect())
    with opener.open(request, timeout=20) as response:
        status = getattr(response, "status", None)
        if status != 200:
            raise urllib.error.HTTPError(_DART_DOCUMENT_URL, status or 0, "source-http-status", {}, None)
        raw = response.read(_MAX_ARCHIVE_BYTES + 1)
        final_url = urllib.parse.urlsplit(response.geturl())
    if final_url.scheme != "https" or final_url.netloc != "opendart.fss.or.kr" or final_url.path != "/api/document.xml":
        raise ValueError("unexpected-source-endpoint")
    if not raw or len(raw) > _MAX_ARCHIVE_BYTES:
        raise ValueError("archive-size-rejected")
    status_code = None
    if raw.lstrip().startswith((b"{", b"[")):
        try:
            body = json.loads(raw)
        except (UnicodeError, json.JSONDecodeError):
            body = {}
        status_code = body.get("status") if isinstance(body, dict) else None
    else:
        match = _DART_STATUS.search(raw[:65536])
        status_code = match.group(1).decode("ascii") if match else None
    if status_code in {"010", "011", "012", "020", "021", "429"}:
        raise SourceAccessStop("dart-status-" + status_code)
    if status_code == "800":
        raise SourceAccessStop("dart-source-status-800", stopped="source-maintenance")
    if status_code in {"013", "014", "100", "101", "900"}:
        raise ValueError("dart-source-status-" + status_code)
    try:
        with zipfile.ZipFile(__import__("io").BytesIO(raw)) as archive:
            if not any(name.lower().endswith(".xml") for name in archive.namelist()):
                raise ValueError("archive-xml-missing")
    except (OSError, zipfile.BadZipFile):
        raise ValueError("archive-invalid") from None
    return raw


class SourceAccessStop(Exception):
    def __init__(self, reason, *, stopped="source-access-or-rate-limit"):
        super().__init__(reason)
        if stopped not in {"source-access-or-rate-limit", "source-maintenance"}:
            raise ValueError("annual-source-stop-invalid")
        self.stopped = stopped


def _load_capture_module():
    spec = importlib.util.spec_from_file_location("_member_map_capture_contract_facts", HELPER_PATH)
    if spec is None or spec.loader is None:
        raise ValueError("capture-helper-unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--source-dir", type=Path, required=True)
    cli.add_argument("--archive-dir", type=Path)
    cli.add_argument("--output-dir", type=Path, required=True)
    cli.add_argument("--limit", type=int, default=_DEFAULT_LIMIT)
    cli.add_argument("--fetch-public", action="store_true")
    cli.add_argument("--apply-local", action="store_true")
    args = cli.parse_args(argv)
    if not 1 <= args.limit <= _MAX_LIMIT:
        cli.error("--limit must be between 1 and 6")
    if args.source_dir.is_symlink() or not args.source_dir.is_dir():
        cli.error("invalid --source-dir")
    if args.archive_dir and (args.archive_dir.is_symlink() or not args.archive_dir.is_dir()):
        cli.error("invalid --archive-dir")
    if args.output_dir.exists() or args.output_dir.is_symlink():
        cli.error("--output-dir must be new")

    api_key = os.environ.get("DART_API_KEY", "")
    if args.fetch_public and not api_key.strip():
        raise SystemExit("DART_API_KEY is required for --fetch-public")
    helper = _load_capture_module()
    source_dir = args.source_dir
    baseline = helper._read_regular_json(source_dir / "member_map_auto_evidence.json")
    helper._validate_capture_fields(baseline, baseline)
    overview = _read_json(source_dir / "dart_business_overview.json",
                          maximum=_MAX_OVERVIEW_JSON_BYTES)
    universe = _read_json(source_dir / "universe_search.json", maximum=16 * 1024 * 1024)
    mapping_path = source_dir / "mapping.json"
    if mapping_path.is_symlink():
        raise SystemExit("invalid-mapping-input")
    mapping = _read_json(mapping_path) if mapping_path.exists() else None
    attempt_ledger, attempt_ledger_raw = _read_attempt_ledger(source_dir)
    sources = {"universe_search.json": universe,
               "member_map_auto_evidence.json": baseline}
    company_catalog = helper.add_public_company_names(
        sources, helper.project_public_sources(sources)["companies"])
    selected, selection = select_candidates(overview, mapping, baseline, limit=args.limit,
                                           company_catalog=company_catalog,
                                           attempt_ledger=attempt_ledger)
    args.output_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.chmod(args.output_dir, 0o700)
    manifest = {"schema": "local-public-annual-customer-capture-v1",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "available": selection["unique_uncaptured_receipts"],
                "selected": len(selected), "attempted": 0, "parsed": 0, "not_attempted": 0,
                "public_gets": 0, "selection": selection, "documents": []}
    evidence = dict(baseline)
    annual_rows = {row["receipt_no"]: row for row in evidence.get("annual_customer_tables", [])}
    proposed_ledger = {"schema": _ATTEMPT_SCHEMA,
                       "receipts": dict(attempt_ledger["receipts"])}
    for candidate in selected:
        receipt = candidate["receipt_no"]
        record = {**candidate, "status": "pending"}
        manifest["documents"].append(record)
        manifest["attempted"] += 1
        stage = "archive-invalid"
        try:
            cached = _archive_path(args.archive_dir, receipt) if args.archive_dir else None
            if cached is not None:
                raw = _read_archive(cached)
                record["archive_source"] = "local-cache"
            elif args.fetch_public:
                stage = "source-fetch-failed"
                manifest["public_gets"] += 1
                raw = _fetch_archive(receipt, api_key)
                record["archive_source"] = "public-document-api"
            else:
                record.update(status="not-captured", reason="archive-not-cached")
                continue
            stage = "parse-rejected"
            archive_name = receipt + ".zip"
            archive_path = args.output_dir / archive_name
            descriptor = os.open(archive_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            record["archive"] = {"file": archive_name, "bytes": len(raw),
                                 "sha256": hashlib.sha256(raw).hexdigest()}
            capture_module = __import__("api.intelligence.portfolio_annual_customer_tables",
                                       fromlist=["capture_annual_customer_tables"])
            compact = capture_module.capture_annual_customer_tables(
                raw, receipt_no=receipt, issuer_id=candidate["issuer_id"],
                issuer_name=candidate["issuer_name"], corp_code=candidate["corp_code"],
                filed_on=candidate["filed_on"], fiscal_year=candidate["fiscal_year"],
                report_name=candidate["report_name"], expected_member=receipt + ".xml")
            compact = capture_module.validate_annual_customer_capture(compact)
            annual_rows[receipt] = compact
            record.update(status="parsed", table_count=compact["table_count"],
                          captured_table_count=len(compact["tables"]),
                          capture_sha256=hashlib.sha256(json.dumps(compact, ensure_ascii=False, sort_keys=True).encode()).hexdigest())
            manifest["parsed"] += 1
            _update_attempt_ledger(proposed_ledger, receipt, "success")
        except urllib.error.HTTPError as error:
            record.update(status="failed", reason="source-http-error", http_status=error.code)
            if error.code in (401, 403, 429):
                _update_attempt_ledger(proposed_ledger, receipt,
                                       "rate-limit" if error.code == 429 else "access-stop")
                manifest["stopped"] = "source-access-or-rate-limit"
                break
            _update_attempt_ledger(proposed_ledger, receipt, "source-fetch-failed")
        except SourceAccessStop as error:
            record.update(status="failed", reason=str(error))
            _update_attempt_ledger(proposed_ledger, receipt, "access-stop")
            manifest["stopped"] = error.stopped
            break
        except Exception as error:  # keep provider text, URLs and keys out of the journal
            reason = str(error) if isinstance(error, ValueError) and re.fullmatch(r"[a-z0-9-]{1,80}", str(error)) else type(error).__name__
            record.update(status="failed", reason=reason)
            _update_attempt_ledger(proposed_ledger, receipt, stage)
    manifest["not_attempted"] = len(selected) - manifest["attempted"]
    evidence["annual_customer_tables"] = sorted(annual_rows.values(), key=lambda row: row["receipt_no"])
    # Persist the bounded run manifest even if later validation or apply fails.
    helper.write_result(args.output_dir / "manifest.json", manifest)
    try:
        helper._validate_capture_fields(baseline, evidence)
        helper.write_result(args.output_dir / "member_map_auto_evidence.json", evidence)
        helper.write_result(args.output_dir / "member_map_annual_capture_attempts.json",
                            proposed_ledger)
        if args.apply_local:
            update = helper.apply_local(source_dir, baseline, evidence, args.output_dir)
            if update["applied"]:
                helper.write_result(args.output_dir / "local-apply.json", update)
            if proposed_ledger != attempt_ledger:
                _write_attempt_ledger_atomic(source_dir, attempt_ledger_raw, proposed_ledger)
    except (OSError, TypeError, ValueError):
        raise SystemExit("capture-validation-or-local-apply-failed") from None
    print(json.dumps({"available": manifest["available"], "selected": manifest["selected"],
                      "attempted": manifest["attempted"], "parsed": manifest["parsed"],
                      "not_attempted": manifest["not_attempted"], "public_gets": manifest["public_gets"],
                      **({"stopped": manifest["stopped"]} if "stopped" in manifest else {})}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
