"""Independently reviewed DART HTML facts, separate from collected API payloads.

The bundled registry is a bounded editorial evidence set. It is neither a DART
API response cache nor a general collection fallback. No network calls occur.
"""
from copy import deepcopy
from datetime import date, datetime
from functools import lru_cache
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit

if __package__:
    from .report_reader import valid_period
else:
    from report_reader import valid_period


REGISTRY_PATH = Path(__file__).parent / "_content" / "report_kr_primary_reviews.json"
METRICS = ("revenue", "op", "net", "ocf", "capex", "cost_of_sales", "sga")
UNIT_MULTIPLIERS = {"원": 1, "천원": 1000, "백만원": 1000000}
_DART = "https://dart.fss.or.kr/"


@lru_cache(maxsize=1)
def _registry():
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))["entries"]


def _date(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _amount(raw):
    text = str(raw or "").replace(",", "").strip()
    if re.fullmatch(r"\(\d+\)", text):
        return -int(text[1:-1])
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return None


def _document_ok(doc, today):
    if not isinstance(doc, dict):
        return False
    filed = _date(doc.get("filed"))
    accession = str(doc.get("accession") or "")
    url = str(doc.get("url") or "")
    return bool(filed and filed <= today and re.fullmatch(r"\d{14}", accession)
                and url.startswith(_DART + "report/viewer.do?")
                and "rcpNo=" + accession in url
                and re.fullmatch(r"[0-9a-f]{64}", str(doc.get("sha256") or "")))


def reviewed_entry(ticker, stock, now):
    """Return the eligible reviewed record, or None on identity/date mismatch.

    The current public stock payload has ticker/name but no DART corp_code. A
    supplied corp_code is checked strictly; absence is not represented as an
    independent corp-code match.
    """
    if not isinstance(stock, dict) or not isinstance(now, (date, datetime)):
        return None
    entry = _registry().get(str(ticker))
    if not entry or str(ticker) != str(stock.get("ticker") or ""):
        return None
    if entry.get("ticker") != str(ticker) or entry.get("name") != (stock.get("name_ko") or stock.get("name")):
        return None
    evidence = stock.get("financial_evidence") or {}
    supplied_corps = (stock.get("corp_code"), stock.get("dart_corp_code"), evidence.get("corp_code"))
    supplied_corp = any(supplied_corps)
    if any(corp and str(corp) != str(entry.get("corp_code")) for corp in supplied_corps):
        return None
    today = now.date() if isinstance(now, datetime) else now
    reviewed = _date(entry.get("reviewed_at"))
    max_age = entry.get("max_review_age_days")
    if not reviewed or not isinstance(max_age, int) or not 0 <= (today - reviewed).days <= max_age:
        return None
    result = deepcopy(entry)
    result["corp_code_match"] = "input_verified" if supplied_corp else "registry_only_input_missing"
    result["documents"] = {key: doc for key, doc in result["documents"].items() if _document_ok(doc, today)}
    result["periods"] = [row for row in result["periods"] if _period_ok(row, result["documents"], today)]
    business_doc = result.get("business_context", {}).get("document")
    if business_doc not in result["documents"]:
        result.pop("business_context", None)
    return result if result["periods"] else None


def _period_ok(row, documents, today):
    if not isinstance(row, dict) or row.get("period_kind") not in ("annual", "quarter", "ytd"):
        return False
    filed = _date(row.get("filed"))
    start, end = _date(row.get("start")), _date(row.get("end"))
    if not filed or filed > today or not start or not end or start >= end:
        return False
    if row.get("year") != end.year or row.get("currency") != "KRW" or row.get("fs_div") not in ("CFS", "OFS"):
        return False
    metrics = row.get("metrics") or {}
    if not metrics or any(key not in METRICS for key in metrics):
        return False
    for key, metric in metrics.items():
        doc = documents.get(metric.get("document")) if isinstance(metric, dict) else None
        raw = _amount(metric.get("raw")) if isinstance(metric, dict) else None
        multiplier = UNIT_MULTIPLIERS.get((doc or {}).get("unit"))
        expected = raw * multiplier if raw is not None and multiplier is not None else None
        if key == "capex" and expected is not None:
            expected = -expected
        if (not doc or doc.get("filed") != row.get("filed")
                or doc.get("accession") != row.get("accession")
                or doc.get("currency") != row.get("currency")
                or doc.get("fs_div") != row.get("fs_div")
                or not isinstance(metric.get("value"), int) or expected != metric["value"]):
            return False
    for key, derived in (row.get("derived_metrics") or {}).items():
        doc = documents.get(derived.get("document")) if isinstance(derived, dict) else None
        parts = derived.get("components") if isinstance(derived, dict) else None
        if (key != "sga" or key in metrics or not doc or doc.get("filed") != row.get("filed")
                or doc.get("accession") != row.get("accession") or not isinstance(parts, list)
                or len(parts) != 2 or any(_amount(part.get("raw")) != part.get("value") for part in parts)
                or sum(part["value"] for part in parts) != derived.get("value")):
            return False
    return True


def _materialize(row, documents, reviewed_at):
    filing_url = _DART + "dsaf001/main.do?rcpNo=" + row["accession"]
    result = {key: row[key] for key in ("year", "start", "end", "period_kind", "currency", "fs_div", "accession", "filed")}
    result.update(source_url=filing_url, reviewed_at=reviewed_at,
                  source="DART 공개 HTML 직접 검수 · API 원응답 아님",
                  metric_sources={})
    if row.get("start_basis"):
        result["start_basis"] = row["start_basis"]
    for key, metric in row["metrics"].items():
        doc = documents[metric["document"]]
        result[key] = metric["value"]
        result["metric_sources"][key] = {
            "name": metric["account"], "raw_text": metric["raw"], "column": metric["column"],
            "source_url": doc["url"], "source_type": "DART 공개 HTML 직접 검수 · API 원응답 아님",
            "sha256": doc["sha256"], "reviewed_at": reviewed_at,
            "start": row["start"], "end": row["end"], "currency": row["currency"], "fs_div": row["fs_div"],
            "reported_unit": doc["unit"], "unit_multiplier": UNIT_MULTIPLIERS[doc["unit"]],
        }
        if metric.get("normalization"):
            result["metric_sources"][key]["normalization"] = metric["normalization"]
    for key in row.get("unreported_metrics", []):
        if key in METRICS:
            result.setdefault(key, None)
    if row.get("derived_metrics"):
        derived = deepcopy(row["derived_metrics"])
        for item in derived.values():
            doc = documents[item["document"]]
            item.update(source_url=doc["url"], sha256=doc["sha256"], reviewed_at=reviewed_at)
        result["derived_metrics"] = derived
    return result


def _key(row):
    return tuple(row.get(k) for k in ("start", "end", "period_kind", "currency", "fs_div"))


def reviewed_financials(ticker, stock, periods, now):
    """Merge eligible reviewed rows without overwriting a newer same-period row.

    Same-filing rows receive only missing values, or corroborating HTML evidence
    for an exactly equal number whose collected source has no raw/hash evidence.
    An older filing is replaced as a complete period, never mixing versions.
    """
    merged = deepcopy(periods) if isinstance(periods, list) else []
    entry = reviewed_entry(ticker, stock, now)
    if not entry:
        return merged
    index = {_key(row): i for i, row in enumerate(merged) if isinstance(row, dict)}
    for raw in entry["periods"]:
        reviewed = _materialize(raw, entry["documents"], entry["reviewed_at"])
        if not valid_period(reviewed):
            continue
        key = _key(reviewed)
        if key not in index:
            index[key] = len(merged)
            merged.append(reviewed)
            continue
        i = index[key]
        existing = merged[i]
        existing_filed, reviewed_filed = _date(existing.get("filed")), _date(reviewed["filed"])
        if existing_filed is None or existing_filed > reviewed_filed:
            continue  # Unknown or newer provenance is not silently replaced.
        if existing_filed < reviewed_filed:
            merged[i] = reviewed
            continue
        if existing.get("accession") != reviewed["accession"]:
            continue  # Same-day different filing may be a correction; preserve it.
        augmented = deepcopy(existing)
        sources = dict(augmented.get("metric_sources") or {})
        for metric in METRICS:
            if augmented.get(metric) is None and reviewed.get(metric) is not None:
                augmented[metric] = reviewed[metric]
                sources[metric] = reviewed["metric_sources"][metric]
            elif (type(augmented.get(metric)) in (int, float)
                  and augmented[metric] == reviewed.get(metric)):
                collected = sources.get(metric, {})
                if (isinstance(collected, dict) and collected.get("source_url")
                        and collected.get("source_type") in (None, "", "DART", "DART API")
                        and collected.get("account_id") in (None, "")
                        and set(collected).issubset({"name", "account_id", "source_url", "source_type",
                            "start", "end", "currency", "fs_div", "ticker", "stock_code",
                            "corp_code", "issuer_id", "accession", "rcept_no", "filed"})
                        and "raw_text" not in collected
                        and "sha256" not in collected
                        and all(collected.get(k) in (None, "", reviewed[k])
                                for k in ("start", "end", "currency", "fs_div"))
                        and all(collected.get(k) in (None, "", value) for k, value in
                                (("ticker", str(ticker)), ("stock_code", str(ticker)),
                                 ("corp_code", entry["corp_code"]), ("issuer_id", entry["corp_code"])))
                        and all(collected.get(k) in (None, "", reviewed["accession"])
                                for k in ("accession", "rcept_no"))
                        and collected.get("filed") in (None, "", reviewed["filed"])
                        and str(collected["source_url"]).startswith(_DART)
                        and urlsplit(collected["source_url"]).path == "/dsaf001/main.do"
                        and set(parse_qs(urlsplit(collected["source_url"]).query,
                                         keep_blank_values=True)) == {"rcpNo"}
                        and parse_qs(urlsplit(collected["source_url"]).query,
                                     keep_blank_values=True).get("rcpNo") == [reviewed["accession"]]):
                    sources[metric] = deepcopy(reviewed["metric_sources"][metric])
                    if collected:
                        sources[metric]["collected_source"] = deepcopy(collected)
        if sources:
            augmented["metric_sources"] = sources
        if reviewed.get("start_basis"):
            augmented.setdefault("start_basis", reviewed["start_basis"])
        if reviewed.get("derived_metrics"):
            augmented.setdefault("derived_metrics", reviewed["derived_metrics"])
        merged[i] = augmented
    return merged
