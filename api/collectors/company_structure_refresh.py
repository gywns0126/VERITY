"""Public DART structure sources only; missing sources never imply no relations.

The caller serializes runs and checkpoints before each physical GET. Daily
budgets belong to one durable store (KST day), not to a Python process. Only
successful endpoint observations advance checkedAt/lastSuccessAt; build time
and attemptedAt are deliberately separate from source provenance dates.
"""
from __future__ import annotations

import copy
import json
import os
import re
import tempfile
import unicodedata
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

SCHEMA = "alphanest-company-structure-sources-v1"
ENDPOINTS = ("hyslrSttus", "otrCprInvstmntSttus")
MAX_ISSUERS = 300
MAX_GETS = 600
TTL = timedelta(days=7)
KST = timezone(timedelta(hours=9))
BUDGET_STOPS = frozenset({"daily-request-budget"})


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic_json(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class SingleAttemptFailure(RuntimeError):
    """A physical failure must bypass DartScout's connection/timeout retries."""


class RequestBudgetExceeded(RuntimeError):
    """No physical request is allowed after the session budget."""


class BoundedSession:
    """Minimal capture-runner contract, embedded for clean-checkout execution.

    Imports requests only when live collection (or a synthetic test) starts.
    Neither construction nor import reads a DART credential.
    """

    def __init__(self, limit):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 0 <= limit <= MAX_GETS:
            raise ValueError("request limit must be between 0 and 600")
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        self.limit, self.count = limit, 0
        self._request_exception = requests.RequestException
        self._session = requests.Session()
        self._session.mount("https://", HTTPAdapter(max_retries=Retry(
            total=0, connect=0, read=0, redirect=0, status=0)))

    def get(self, *args, **kwargs):
        if self.count >= self.limit:
            raise RequestBudgetExceeded("physical request budget exhausted")
        self.count += 1
        kwargs["allow_redirects"] = False
        try:
            return self._session.get(*args, **kwargs)
        except self._request_exception as exc:
            # Do not expose request URLs/params, which may carry credentials.
            raise SingleAttemptFailure(type(exc).__name__) from None

    def close(self):
        self._session.close()


_SOURCE_FIELDS = {
    "hyslrSttus.json": ("rcept_no", "corp_code", "corp_name", "stlm_dt", "nm",
                        "relate", "stock_knd", "trmend_posesn_stock_qota_rt", "trmend_posesn_stock_co"),
    "otrCprInvstmntSttus.json": ("rcept_no", "corp_code", "corp_name", "stlm_dt",
                               "inv_prm", "trmend_blce_qota_rt", "trmend_blce_qy"),
}
_LEGAL = re.compile(r"주식회사|유한회사|㈜|\(주\)|\b(?:inc\.?|ltd\.?|llc|corp\.?|corporation|incorporated|limited|gmbh|plc)\b", re.I)
_EXCLUDED = re.compile(r"투자조합|개인|펀드|\b(?:fund|trust|individual)\b", re.I)


def _company_name(value):
    if not isinstance(value, str):
        return ""
    return re.sub(r"[\W_]+", "", _LEGAL.sub("", unicodedata.normalize("NFKC", value)).casefold())


def _corporate(value, listed_names):
    return (isinstance(value, str) and not _EXCLUDED.search(value)
            and bool(_company_name(value))
            and (_company_name(value) in listed_names or bool(_LEGAL.search(value))))


def expected_period(now):
    """Conservative fixed calendar policy, not a filing-deadline/legal claim.

    Apr: prior annual; Jun: Q1; Sep: H1; Nov 30: Q3. Jan-Mar retain
    prior Q3. Actual settlement dates remain the source's own stlm_dt.
    """
    month_day = (now.month, now.day)
    if month_day >= (11, 30):
        return {"year": str(now.year), "reportCode": "11014"}
    if month_day >= (9, 1):
        return {"year": str(now.year), "reportCode": "11012"}
    if month_day >= (6, 1):
        return {"year": str(now.year), "reportCode": "11013"}
    return {"year": str(now.year - 1), "reportCode": "11011" if month_day >= (4, 1) else "11014"}


def _safe_block(block, endpoint, corp, listed_names):
    """Whitelist durable fields after original row matching; discard raw/personal metadata."""
    kept = []
    for row in block.get("rows", []):
        if not isinstance(row, dict):
            continue
        fields = row.get("sourceRow", {}).get("fields", {})
        try:
            _attach_source_rows(endpoint + ".json", [row], {"list": [fields]}, corp)
        except (ValueError, TypeError, AttributeError, KeyError):
            continue
        name_key = "nm" if endpoint == "hyslrSttus" else "inv_corp_name"
        if not _corporate(row.get(name_key), listed_names):
            continue
        safe = {name_key: row[name_key]}
        value_keys = (("stock_cnt", "stock_rate") if endpoint == "hyslrSttus" else
                      ("initial_investment", "initial_date", "begin_balance_qty", "increase_qty",
                       "decrease_qty", "end_balance_qty", "ownership_pct", "book_value", "fair_value",
                       "recent_biz_year_revenue", "recent_biz_year_profit"))
        for key in value_keys:
            value = row.get(key)
            if value is None or type(value) in (int, float) or (isinstance(value, str) and re.fullmatch(r"[0-9, .%+/-]*", value)):
                safe[key] = value
        allowed_fields = {"rcept_no", "corp_code", "stlm_dt", "trmend_posesn_stock_qota_rt", "trmend_blce_qota_rt", "trmend_blce_qy", "trmend_posesn_stock_co"}
        source_fields = {k: v for k, v in fields.items() if k in allowed_fields
                         and (v is None or isinstance(v, str) and re.fullmatch(r"[0-9, .%+/-]*", v))}
        source_fields["nm" if endpoint == "hyslrSttus" else "inv_prm"] = row[name_key]
        index = row.get("sourceRow", {}).get("index")
        safe["sourceRow"] = {"index": index if type(index) is int and index >= 0 else 0, "fields": source_fields}
        if endpoint == "otrCprInvstmntSttus":
            safe.pop("end_balance_qty", None)
            safe["quantityStatus"] = "source-quantity-unavailable"
            safe["verificationStatus"] = "needs-review"
            try:
                quantity = Decimal(str(source_fields.get("trmend_blce_qy")).replace(",", "").strip())
                if quantity.is_finite() and quantity >= 0 and quantity == quantity.to_integral_value():
                    safe.update(end_balance_qty=int(quantity), quantityStatus="source-quantity-verified",
                                verificationStatus="source-row-matched")
            except InvalidOperation:
                pass
        provenance = row.get("provenance", {})
        safe["provenance"] = {"endpoint": endpoint, "corp_code": corp,
                              "rcept_no": source_fields.get("rcept_no")}
        for key in ("stlm_dt", "bsns_year", "reprt_code", "sourceDate", "collectedAt"):
            value = provenance.get(key)
            if value is None or isinstance(value, str) and re.fullmatch(r"[0-9T:Z+ .-]*", value):
                safe["provenance"][key] = value
        kept.append(safe)
    safe_block = {"status": block.get("status") if block.get("status") in ("000", "013") else "error", "rows": kept}
    for key in ("attemptedAt", "lastSuccessAt", "checkedAt"):
        value = block.get(key)
        if key in block and (value is None or _time(value)):
            safe_block[key] = value
    attempt = block.get("attemptStatus", "not-attempted")
    safe_block["attemptStatus"] = attempt if isinstance(attempt, str) and re.fullmatch(r"[0-9]{3}|HTTP(?:401|403|429)|error|not-attempted", attempt) else "error"
    count = block.get("raw_row_count", len(block.get("rows", [])))
    count = max(count, len(kept)) if type(count) is int and count >= 0 else len(kept)
    safe_block.update(raw_row_count=count, corporate_row_count=len(kept),
                      omitted_non_corporate_count=count - len(kept))
    for key in ("reportPeriod", "attemptPeriod"):
        period = block.get(key)
        if (isinstance(period, dict) and re.fullmatch(r"[0-9]{4}", str(period.get("year", "")))
                and period.get("reportCode") in ("11011", "11012", "11013", "11014")):
            safe_block[key] = {"year": period["year"], "reportCode": period["reportCode"]}
    safe_block["sourceActualSettlementDates"] = sorted({r["sourceRow"]["fields"]["stlm_dt"] for r in kept
                                                      if r["sourceRow"]["fields"].get("stlm_dt")})
    period = safe_block.get("reportPeriod")
    actual = {value.replace(".", "-").strip() for value in safe_block["sourceActualSettlementDates"]}
    if period:
        end = period["year"] + {"11011": "-12-31", "11012": "-06-30", "11013": "-03-31", "11014": "-09-30"}[period["reportCode"]]
        safe_block["sourcePeriodStatus"] = ("matches-request-period" if actual == {end}
            else "source-period-mismatch" if actual else "source-period-unavailable")
    if endpoint == "otrCprInvstmntSttus":
        safe_block["relationshipScope"] = "reported-investment-not-subsidiary-inference"
    if safe_block["status"] == "000" and not kept:
        safe_block["sourceResult"] = "no-qualifying-corporate-rows"
    return safe_block


def sanitize_document(document):
    """Also sanitizes legacy stores before *any* durable budget checkpoint."""
    names = {_company_name(document["issuers"]["KR:" + t].get("name")) for t in document["universe"]["KR"]}
    clean = {k: copy.deepcopy(document[k]) for k in ("schema", "generatedAt", "universe")}
    budget = document.get("requestBudget")
    if budget:
        clean["requestBudget"] = {k: budget[k] for k in ("day", "requests", "limit") if k in budget}
    clean["issuers"] = {}
    for key, issuer in document["issuers"].items():
        if not re.fullmatch(r"KR:[A-Z0-9]{6}", key):
            continue
        item = {k: issuer.get(k) for k in ("ticker", "market", "name", "corp_code", "collectedAt", "mappingStatus")}
        item["endpoints"] = {e: _safe_block(b, e, issuer.get("corp_code"), names)
                             for e, b in issuer.get("endpoints", {}).items() if e in ENDPOINTS}
        clean["issuers"][key] = item
    return clean


def _attach_source_rows(endpoint, transformed, response, corp_code):
    """Match existing parser output to the SAME response, preserving raw index.

    Only the capture-runner's row matching is embedded here. DartScout still
    owns both endpoint parsers. No source file or secondary request is loaded.
    """
    fields = _SOURCE_FIELDS[endpoint]
    raw_rows = response.get("list", [])
    if not isinstance(raw_rows, list) or not isinstance(transformed, list):
        raise ValueError("source and parsed rows must be lists")
    eligible = []
    for index, raw in enumerate(raw_rows):
        if not isinstance(raw, dict):
            raise ValueError("source row must be an object")
        if raw.get("corp_code") not in (None, "", corp_code):
            continue
        if endpoint == "otrCprInvstmntSttus.json":
            name = raw.get("inv_prm")
            if not isinstance(name, str) or not name.strip() or name.strip() == "-":
                continue
        eligible.append((index, raw))
    if len(eligible) != len(transformed):
        raise ValueError("parser/raw row count mismatch")
    output = []
    for parsed, (index, raw) in zip(transformed, eligible):
        expected = raw.get("nm", "") if endpoint == "hyslrSttus.json" else raw["inv_prm"].strip()
        name_key = "nm" if endpoint == "hyslrSttus.json" else "inv_corp_name"
        if not isinstance(parsed, dict) or parsed.get(name_key) != expected:
            raise ValueError("parser/raw row order mismatch")
        if any(raw.get(key) is not None and not isinstance(raw[key], str) for key in fields):
            raise ValueError("non-string OpenDART source field")
        closed = copy.deepcopy(parsed)
        closed["sourceRow"] = {"index": index, "fields": {key: raw.get(key) for key in fields}}
        output.append(closed)
    return output


class _CaptureHelpers:
    BoundedSession = BoundedSession
    _attach_source_rows = staticmethod(_attach_source_rows)


def _time(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else None
    except (ValueError, TypeError, AttributeError):
        return None


def _checked(issuer):
    endpoints = issuer.get("endpoints", {})
    times = []
    for key in ENDPOINTS:
        block = endpoints.get(key, {})
        stamp = _time(block.get("checkedAt") or block.get("lastSuccessAt"))
        if block.get("status") not in ("000", "013") or stamp is None:
            return None
        times.append(stamp)
    return min(times)


def build_document(source_dir, existing=None, seed=None, now=None):
    now = now or datetime.now(timezone.utc)
    data_dir = Path(source_dir)
    if not (data_dir / "kr_listed.json").is_file():
        data_dir = data_dir / "data"
    listed = read_json(data_dir / "kr_listed.json")
    mapping = read_json(data_dir / "mapping.json")
    if not isinstance(listed, dict) or not isinstance(mapping, dict):
        raise ValueError("listed universe and mapping must be objects")
    document = copy.deepcopy(existing or {})
    if document and document.get("schema") != SCHEMA:
        raise ValueError("unsupported source store schema")
    document.setdefault("issuers", {})
    if not isinstance(document["issuers"], dict):
        raise ValueError("issuers must be an object")
    if seed:
        if seed.get("schema") != "alphaconsole-dart-structured-provenance-source-v1":
            raise ValueError("unsupported seed schema")
        for item in seed["issuers"]:
            stamp = item.get("collected_at")
            converted = copy.deepcopy(item)
            converted.update(market="KR", collectedAt=stamp)
            for block in converted["endpoints"].values():
                block.update(attemptedAt=stamp, attemptStatus=block["status"])
                if block["status"] in ("000", "013"):
                    block.update(lastSuccessAt=stamp, checkedAt=stamp)
            document["issuers"].setdefault("KR:" + item["ticker"], converted)
    universe = []
    for ticker, row in sorted(listed.items()):
        if not isinstance(row, dict):
            raise ValueError("invalid current listed issuer")
        universe.append(ticker)
        corp = mapping.get(ticker)
        mapping_reason = ("unsupported-ticker" if not re.fullmatch(r"[A-Z0-9]{6}", ticker)
                          else "missing-corp-code" if corp is None else
                          "mapped" if isinstance(corp, str) and re.fullmatch(r"[0-9]{8}", corp)
                          else "invalid-corp-code")
        corp = corp if mapping_reason == "mapped" else None
        issuer = document["issuers"].setdefault("KR:" + ticker, {"collectedAt": None, "endpoints": {}})
        issuer.update(ticker=ticker, market="KR", name=row["name"], corp_code=corp,
                      mappingStatus=mapping_reason)
        for key in ENDPOINTS:
            issuer["endpoints"].setdefault(key, {
                "status": "error", "rows": [], "attemptedAt": None,
                "attemptStatus": "not-attempted",
            })
    document.update(schema=SCHEMA, generatedAt=now.isoformat(), universe={"KR": universe})
    return sanitize_document(document)


def select_issuers(document, limit=300, now=None):
    if isinstance(limit, bool) or not isinstance(limit, int) or not 0 <= limit <= MAX_ISSUERS:
        raise ValueError("limit must be between 0 and 300")
    now = now or datetime.now(timezone.utc)
    candidates, unmapped, fresh = [], [], []
    for ticker in document["universe"]["KR"]:
        key = "KR:" + ticker
        issuer = document["issuers"][key]
        if not issuer.get("corp_code"):
            unmapped.append(key)
            continue
        checked = _checked(issuer)
        if any(b.get("reportPeriod") and b["reportPeriod"] != expected_period(now)
               for b in issuer.get("endpoints", {}).values()):
            checked = None
        if checked and now - checked < TTL and checked <= now:
            fresh.append(key)
        else:
            # A partial/error attempt must rotate behind genuinely unvisited
            # issuers, then compete with successful-stale issuers by last try.
            attempts = [_time(b.get("attemptedAt")) or _time(b.get("lastSuccessAt"))
                        for b in issuer.get("endpoints", {}).values()]
            attempted = max((t for t in attempts if t is not None), default=None)
            candidates.append((attempted is not None, attempted or datetime.min.replace(tzinfo=timezone.utc), key))
    candidates.sort()
    return [item[2] for item in candidates[:limit]], unmapped, fresh, [item[2] for item in candidates[limit:]]


def refresh(document, *, source_dir, limit=300, fetch_public=False, now=None,
            checkpoint=None, scout=None, helpers=None):
    """Return (merged document, summary). Injected scout/helpers are for offline tests.

    Summary selected/attempted/unmapped/deferred/retained count issuers;
    success/empty/error count endpoints. Every category includes its list.
    Durable request reservations include interrupted requests conservatively.
    """
    now = now or datetime.now(timezone.utc)
    stamp = now.isoformat()
    period = expected_period(now)
    document = sanitize_document(document)
    selected, unmapped, fresh, deferred = select_issuers(document, limit, now)
    prior_sources = {key + "/" + endpoint
                     for key, issuer in document["issuers"].items()
                     for endpoint, block in issuer.get("endpoints", {}).items()
                     if block.get("status") in ("000", "013")}
    lists = {key: [] for key in ("attempted", "requests", "success", "empty", "error", "retained")}
    lists.update(requested=["KR:" + t for t in document["universe"]["KR"]],
                 selected=selected, unmapped=unmapped, deferred=deferred + fresh)
    summary = {"dryRun": not fetch_public, "stopReason": None}
    day = now.astimezone(KST).date().isoformat()
    previous = document.get("requestBudget", {})
    used = previous.get("requests", 0) if previous.get("day") == day else 0
    if isinstance(used, bool) or not isinstance(used, int) or not 0 <= used <= MAX_GETS:
        raise ValueError("invalid durable daily request budget")
    summary.update(dailyRequestsBefore=used, requestLimit=MAX_GETS, issuerLimit=MAX_ISSUERS)
    if fetch_public and selected and used < MAX_GETS:
        if checkpoint is None:
            raise ValueError("live refresh requires a durable checkpoint")
        helpers = helpers or _CaptureHelpers
        if scout is None:
            # No config imports (or credential reads) in the dry-run path.
            api_key = os.environ.get("DART_API_KEY")
            if not api_key:
                raise ValueError("process DART_API_KEY unavailable")
            from api.collectors import DartScout as scout
            if scout.DART_API_KEY != api_key:
                raise ValueError("DART_API_KEY differs from process credential")
        budget = helpers.BoundedSession(MAX_GETS - used)
        original_get = budget.get
        capture = {}

        class Halt(RuntimeError):
            pass

        def guarded_get(url, **kwargs):
            nonlocal used
            if summary["stopReason"] or used >= MAX_GETS:
                raise Halt("budget-or-stop")
            if url not in {"https://opendart.fss.or.kr/api/" + key + ".json" for key in ENDPOINTS}:
                raise Halt("unexpected-endpoint")
            # Persist a reservation BEFORE the physical request, even on timeout.
            used += 1
            document["requestBudget"] = {"day": day, "requests": used, "limit": MAX_GETS}
            checkpoint(document)
            lists["requests"].append(capture["job"])
            response = original_get(url, **kwargs)
            if response.status_code in (401, 403, 429):
                summary["stopReason"] = "HTTP" + str(response.status_code)
                raise Halt(summary["stopReason"])
            return response

        budget.get = guarded_get
        original_session, original_call = scout._SESSION, scout._call

        def captured_call(endpoint, params):
            if endpoint not in [key + ".json" for key in ENDPOINTS]:
                raise Halt("unexpected-endpoint")
            response = original_call(endpoint, {**params, "bsns_year": period["year"], "reprt_code": period["reportCode"]})
            capture["response"] = copy.deepcopy(response)
            if response.get("status") == "020":
                summary["stopReason"] = "020"
                raise Halt("020")
            return response

        scout._SESSION, scout._call = budget, captured_call
        try:
            for key in selected:
                if summary["stopReason"] or used >= MAX_GETS:
                    break
                issuer = document["issuers"][key]
                lists["attempted"].append(key)
                for endpoint, fetcher in zip(ENDPOINTS, (scout.fetch_major_shareholders, scout.fetch_subsidiary_investments)):
                    if summary["stopReason"] or used >= MAX_GETS:
                        break
                    old = issuer["endpoints"][endpoint]
                    job = key + "/" + endpoint
                    capture.clear()
                    capture["job"] = job
                    old.update(attemptedAt=stamp, attemptStatus="error", attemptPeriod=period)
                    try:
                        parsed = fetcher(issuer["corp_code"], period["year"])
                        raw = capture.get("response")
                        if not isinstance(raw, dict) or raw.get("status") not in ("000", "013"):
                            old["attemptStatus"] = str((raw or {}).get("status", "error"))
                            raise ValueError("source-error")
                        status = raw["status"]
                        if status == "013" and old.get("status") in ("000", "013") and old.get("lastSuccessAt"):
                            old["attemptStatus"] = "013"
                            lists["empty"].append(job)
                            checkpoint(document)
                            continue
                        if status == "000" and (not isinstance(raw.get("list"), list) or not raw["list"]):
                            raise ValueError("invalid-success-list")
                        rows = helpers._attach_source_rows(endpoint + ".json", parsed, raw, issuer["corp_code"])
                        if status == "000" and not rows:
                            raise ValueError("no-eligible-source-rows")
                        for row in rows:
                            fields = row["sourceRow"]["fields"]
                            provenance = row.setdefault("provenance", {})
                            # Keep the existing parser's validated fields intact.
                            for field, value in {
                                "endpoint": endpoint, "rcept_no": fields.get("rcept_no"),
                                "corp_code": issuer["corp_code"], "stlm_dt": fields.get("stlm_dt"),
                                "sourceDate": None, "collectedAt": stamp,
                                "bsns_year": period["year"], "reprt_code": period["reportCode"],
                            }.items():
                                provenance.setdefault(field, value)
                            provenance.update(bsns_year=period["year"], reprt_code=period["reportCode"])
                        issuer["endpoints"][endpoint] = {
                            "status": status, "rows": rows, "attemptedAt": stamp,
                            "attemptStatus": status, "lastSuccessAt": stamp, "checkedAt": stamp,
                            "raw_row_count": len(raw.get("list", [])),
                            "reportPeriod": period, "attemptPeriod": period,
                        }
                        listed_names = {_company_name(document["issuers"]["KR:" + t].get("name")) for t in document["universe"]["KR"]}
                        issuer["endpoints"][endpoint] = _safe_block(issuer["endpoints"][endpoint], endpoint, issuer["corp_code"], listed_names)
                        lists["success" if status == "000" else "empty"].append(job)
                    except Exception:
                        old["attemptStatus"] = summary["stopReason"] or old["attemptStatus"]
                        lists["error"].append(job)
                    checkpoint(document)
                if all(issuer["endpoints"][e].get("lastSuccessAt") == stamp for e in ENDPOINTS):
                    issuer["collectedAt"] = stamp
                    checkpoint(document)
        finally:
            scout._SESSION, scout._call = original_session, original_call
            budget.close()
    if fetch_public and used >= MAX_GETS and not summary["stopReason"]:
        summary["stopReason"] = "daily-request-budget"
    attempted = set(lists["attempted"])
    lists["deferred"] = sorted(set(lists["deferred"]) | (set(selected) - attempted))
    # Include an issuer whose second endpoint was deferred by the physical cap.
    settled_jobs = set(lists["success"] + lists["empty"] + lists["error"])
    budget_deferred = [key for key in selected if any(key + "/" + endpoint not in settled_jobs for endpoint in ENDPOINTS)]
    lists["budgetDeferred"] = budget_deferred if fetch_public and summary["stopReason"] in BUDGET_STOPS else []
    lists["deferred"] = sorted(set(lists["deferred"]) | set(lists["budgetDeferred"]))
    refreshed = set(lists["success"] + [job for job in lists["empty"]
        if document["issuers"][job.split("/")[0]]["endpoints"][job.split("/")[1]].get("lastSuccessAt") == stamp])
    lists["retained"] = [key for key in lists["requested"] if any(
        key + "/" + endpoint in prior_sources - refreshed for endpoint in ENDPOINTS)]
    summary.update({key: len(value) for key, value in lists.items()})
    if summary["error"] and not summary["stopReason"]:
        summary["stopReason"] = "source-error"
    summary["sourceError"] = summary["error"]
    summary["exitCode"] = int(bool(summary["sourceError"]) or
                              summary["stopReason"] is not None and summary["stopReason"] not in BUDGET_STOPS)
    summary.update(lists=lists, dailyRequestsAfter=used,
                   unmappedReasons={key: document["issuers"][key].get("mappingStatus", "missing-corp-code") for key in unmapped},
                   guardedBudget={"valid": len(attempted) <= MAX_ISSUERS and used <= MAX_GETS,
                                  "plannedGets": min(len(selected) * 2, MAX_GETS - summary["dailyRequestsBefore"])})
    return document, summary
