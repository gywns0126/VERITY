"""Period-safe adapter for the published US financial snapshot.

The per-ticker Blob identifies the SEC concepts selected by the existing
collector.  Older published rows omit ``start`` and ``unit``.  A caller may
therefore provide the matching SEC Company Facts response; this module restores
those source fields without inventing values or combining different filings.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Tuple


_METRICS = {
    "revenue": "revenue",
    "operating_income": "op",
    "net_income": "net",
    "operating_cash_flow": "ocf",
    "capex": "capex",
}
_ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}
_QUARTER_FORMS = {"10-Q", "10-Q/A"}
_ACCESSION = re.compile(r"^\d{10}-\d{2}-\d{6}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")


def _integer(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _period_kind(start: str, end: str, form: str) -> Optional[str]:
    try:
        days = (date.fromisoformat(end) - date.fromisoformat(start)).days
    except (TypeError, ValueError):
        return None
    if form in _ANNUAL_FORMS and 330 <= days <= 380:
        return "annual"
    if form in _QUARTER_FORMS and 75 <= days <= 105:
        return "quarter"
    if form in _QUARTER_FORMS and 106 <= days <= 300:
        return "ytd"
    return None


def _source_url(cik: int, accession: str) -> str:
    compact = accession.replace("-", "")
    return (f"https://www.sec.gov/Archives/edgar/data/{cik}/{compact}/"
            f"{accession}-index.html")


def _raw_references(raw: Dict[str, Any]) -> Iterable[Tuple[str, Dict[str, Any]]]:
    for bucket_name in ("series_annual", "series_quarterly"):
        bucket = raw.get(bucket_name) or {}
        if not isinstance(bucket, dict):
            continue
        for source_key in _METRICS:
            rows = bucket.get(source_key) or []
            if not isinstance(rows, list):
                continue
            for row in rows:
                if isinstance(row, dict):
                    yield source_key, row


def _valid_unit(unit: Any, expected: str) -> Optional[str]:
    value = str(unit or "").upper()
    if not _CURRENCY.fullmatch(value):
        return None
    if expected and value != expected:
        return None
    return value


def _companyfact_candidates(
    raw: Dict[str, Any], companyfacts: Dict[str, Any], cik: int, expected_currency: str,
) -> List[Dict[str, Any]]:
    facts_cik = _integer(companyfacts.get("cik"))
    if facts_cik != cik:
        raise ValueError("companyfacts_cik_mismatch")
    gaap = ((companyfacts.get("facts") or {}).get("us-gaap") or {})
    out: List[Dict[str, Any]] = []
    # Blob rows choose the accepted concept for each normalized metric.  Their
    # accession/end may lag the current SEC feed, so they are hints rather than
    # a period whitelist.
    seen_hints = set()
    for source_key, reference in _raw_references(raw):
        tag = str(reference.get("tag") or "")
        hint = (source_key, tag)
        if not tag or hint in seen_hints:
            continue
        seen_hints.add(hint)
        units = (gaap.get(tag) or {}).get("units") or {}
        if not isinstance(units, dict):
            continue
        monetary_units = [str(name).upper() for name in units if _CURRENCY.fullmatch(str(name).upper())]
        if not expected_currency and len(set(monetary_units)) != 1:
            continue
        for unit_name, rows in units.items():
            unit = _valid_unit(unit_name, expected_currency)
            if not unit or not isinstance(rows, list):
                continue
            for fact in rows:
                if not isinstance(fact, dict):
                    continue
                accession = str(fact.get("accn") or "")
                start = str(fact.get("start") or "")
                end = str(fact.get("end") or "")
                form = str(fact.get("form") or "")
                if not _ACCESSION.fullmatch(accession):
                    continue
                kind = _period_kind(start, end, form)
                if not kind or fact.get("val") is None:
                    continue
                out.append({
                    "metric": _METRICS[source_key], "tag": tag,
                    "start": start, "end": end, "unit": unit,
                    "accession": accession, "form": form, "kind": kind,
                    "filed": str(fact.get("filed") or ""),
                    # SEC ``fy`` is the filing's fiscal-year focus and can label
                    # prior-period comparatives with the current filing year.
                    "year": int(end[:4]),
                    "val": fact.get("val"), "cik": cik,
                })
    if not out:
        return []
    latest_end = max(date.fromisoformat(row["end"]) for row in out)
    try:
        cutoff = latest_end.replace(year=latest_end.year - 5)
    except ValueError:  # February 29
        cutoff = latest_end.replace(year=latest_end.year - 5, day=28)
    return [row for row in out if date.fromisoformat(row["end"]) > cutoff]


def _published_candidates(raw: Dict[str, Any], cik: int, expected_currency: str) -> List[Dict[str, Any]]:
    """Use future provenance-complete Blob rows when Company Facts is omitted."""
    out: List[Dict[str, Any]] = []
    for source_key, source in _raw_references(raw):
        start, end = str(source.get("start") or ""), str(source.get("end") or "")
        form = str(source.get("form") or "")
        accession = str(source.get("accn") or source.get("accession") or "")
        unit = _valid_unit(source.get("unit"), expected_currency)
        kind = _period_kind(start, end, form)
        if (not unit or not kind or not _ACCESSION.fullmatch(accession)
                or source.get("val") is None or not source.get("tag")):
            continue
        out.append({
            "metric": _METRICS[source_key], "tag": str(source["tag"]),
            "start": start, "end": end, "unit": unit,
            "accession": accession, "form": form, "kind": kind,
            "filed": str(source.get("filed") or ""),
            "year": int(end[:4]),
            "val": source.get("val"), "cik": cik,
        })
    return out


def us_periods(raw: Dict[str, Any], companyfacts: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Return SEC financial periods with exact metric-level provenance.

    Metrics are first deduplicated by period and unit using the latest filing.
    They are then grouped only when start, end, unit, and accession are equal.
    Partial rows are retained so a missing concept remains an explicit unknown.
    """
    if not isinstance(raw, dict):
        return []
    meta = raw.get("meta") or {}
    cik = _integer(meta.get("cik"))
    if not cik:
        return []
    expected = str(meta.get("currency") or "").upper()
    expected = expected if _CURRENCY.fullmatch(expected) else ""
    if companyfacts is not None:
        if not isinstance(companyfacts, dict):
            return []
        candidates = _companyfact_candidates(raw, companyfacts, cik, expected)
        fs_div: Optional[str] = "ENTITY"
        scope_basis: Optional[str] = "SEC entity-wide company facts (consolidation not separately verified)"
    else:
        candidates = _published_candidates(raw, cik, expected)
        fs_div = None
        scope_basis = None

    by_period: Dict[Tuple[str, str, str, str, str], List[Dict[str, Any]]] = {}
    for candidate in candidates:
        key = (candidate["metric"], candidate["start"], candidate["end"],
               candidate["unit"], candidate["kind"])
        by_period.setdefault(key, []).append(candidate)

    latest: Dict[Tuple[str, str, str, str, str], Dict[str, Any]] = {}
    for key, choices in by_period.items():
        newest = max((row["filed"], row["accession"]) for row in choices)
        finalists = [row for row in choices
                     if (row["filed"], row["accession"]) == newest]
        # Two concepts surviving at the same latest filing are not resolved by
        # iteration order.  The report must leave that metric unknown.
        signatures = {(row["tag"], repr(row["val"])) for row in finalists}
        if len(signatures) != 1:
            continue
        latest[key] = finalists[0]

    grouped: Dict[Tuple[str, str, str, str, str], Dict[str, Any]] = {}
    for candidate in latest.values():
        key = (candidate["start"], candidate["end"], candidate["unit"],
               candidate["accession"], candidate["kind"])
        row = grouped.setdefault(key, {
            "year": candidate["year"], "start": candidate["start"],
            "end": candidate["end"], "period_kind": candidate["kind"],
            "currency": candidate["unit"], "fs_div": fs_div,
            "scope_basis": scope_basis,
            "source_url": _source_url(cik, candidate["accession"]),
            "filed": candidate["filed"], "accession": candidate["accession"],
            "revenue": None, "op": None, "net": None, "ocf": None,
            "capex": None, "metric_sources": {},
        })
        metric = candidate["metric"]
        row[metric] = candidate["val"]
        source_url = _source_url(cik, candidate["accession"])
        row["metric_sources"][metric] = {
            "tag": candidate["tag"], "start": candidate["start"],
            "end": candidate["end"], "unit": candidate["unit"],
            "accession": candidate["accession"], "source_url": source_url,
        }
        if candidate["filed"] > row["filed"]:
            row["filed"] = candidate["filed"]
    return sorted(grouped.values(), key=lambda row: (
        row["end"], row["start"], row["accession"], row["currency"]))
