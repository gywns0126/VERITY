# -*- coding: utf-8 -*-
"""Latest-filing inline XBRL fallback for delayed SEC Company Facts rows.

The monthly US financial collector remains Company Facts-first.  This module is
used only when SEC submissions lists a newer inline-XBRL 10-Q/10-K accession
that is absent from Company Facts.  It converts consolidated ``us-gaap`` facts
from that filing into the same compact shape consumed by ``us_financials``.
"""
from __future__ import annotations

import copy
import math
import re
import urllib.request
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, Optional

from lxml import html

SEC_ARCHIVE = "https://www.sec.gov/Archives/edgar/data"
USER_AGENT = "VERITY research gywns0126@gmail.com"
MAX_INLINE_BYTES = 30 * 1024 * 1024


def filing_url(cik: int, accession: str, primary_document: str) -> str:
    acc = re.sub(r"[^0-9]", "", accession or "")
    doc = str(primary_document or "").lstrip("/")
    return f"{SEC_ARCHIVE}/{int(cik)}/{acc}/{doc}"


def _tag_name(node: Any) -> str:
    tag = str(getattr(node, "tag", "") or "").lower()
    return tag.rsplit("}", 1)[-1].rsplit(":", 1)[-1]


def _nodes(root: Any, local_name: str) -> Iterable[Any]:
    wanted = local_name.lower()
    return (node for node in root.iter() if _tag_name(node) == wanted)


def _text(node: Any) -> str:
    return "".join(node.itertext()).strip()


def _contexts(root: Any) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for node in _nodes(root, "context"):
        context_id = str(node.get("id") or "")
        if not context_id:
            continue
        # Segment/scenario contexts are product, geography, class, or other
        # dimensions.  Public company totals must use consolidated contexts.
        if any(_tag_name(child) in {"segment", "scenario"} for child in node.iter()):
            continue
        row: Dict[str, Any] = {}
        for child in node.iter():
            name = _tag_name(child)
            if name == "startdate":
                row["start"] = _text(child)
            elif name in {"enddate", "instant"}:
                row["end"] = _text(child)
        if row.get("end"):
            out[context_id] = row
    return out


def _unit_name(node: Any) -> Optional[str]:
    measures = [_text(x) for x in node.iter() if _tag_name(x) == "measure"]
    normalized = [m.split(":")[-1].upper() for m in measures]
    if "USD" in normalized and "SHARES" in normalized:
        return "USD/shares"
    if "USD" in normalized:
        return "USD"
    if "SHARES" in normalized:
        return "shares"
    if "PURE" in normalized:
        return "pure"
    return normalized[0] if len(normalized) == 1 else None


def _units(root: Any) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for node in _nodes(root, "unit"):
        unit_id = str(node.get("id") or "")
        value = _unit_name(node)
        if unit_id and value:
            out[unit_id] = value
    return out


def _fallback_unit(unit_ref: str) -> Optional[str]:
    low = str(unit_ref or "").lower()
    if "usd" in low and "share" in low:
        return "USD/shares"
    if "usd" in low:
        return "USD"
    if "share" in low:
        return "shares"
    if "pure" in low or "number" in low:
        return "pure"
    return None


def _number(node: Any) -> Optional[float | int]:
    if str(node.get("nil") or node.get("xsi:nil") or "").lower() in {"1", "true"}:
        return None
    raw = _text(node).replace("\u2212", "-").replace("\u2014", "")
    raw = re.sub(r"[,$%\s]", "", raw)
    if not raw or raw in {"-", "--"}:
        return None
    negative = raw.startswith("(") and raw.endswith(")")
    if negative:
        raw = raw[1:-1]
    try:
        value = Decimal(raw)
        scale = int(node.get("scale") or 0)
        value *= Decimal(10) ** scale
        if negative or str(node.get("sign") or "").strip() == "-":
            value = -abs(value)
    except (InvalidOperation, TypeError, ValueError, OverflowError):
        return None
    as_float = float(value)
    if not math.isfinite(as_float):
        return None
    return int(value) if value == value.to_integral_value() else as_float


def _dei_focus(root: Any) -> tuple[Optional[int], str]:
    fy: Optional[int] = None
    fp = "Q?"
    for node in _nodes(root, "nonnumeric"):
        name = str(node.get("name") or "")
        value = _text(node)
        if name.lower().endswith(":documentfiscalyearfocus") and value.isdigit():
            fy = int(value)
        elif name.lower().endswith(":documentfiscalperiodfocus") and value:
            fp = value.upper()
    return fy, fp


def parse_inline_xbrl(
    body: bytes | str,
    *,
    accession: str,
    form: str,
    filing_date: str = "",
    report_date: str = "",
    fiscal_year: Optional[int] = None,
    fiscal_period: str = "",
) -> Dict[str, Any]:
    """Convert consolidated inline-XBRL numeric facts to Company Facts shape."""
    root = html.fromstring(body)
    contexts = _contexts(root)
    units = _units(root)
    dei_fy, dei_fp = _dei_focus(root)
    fy = fiscal_year or dei_fy
    fp = (fiscal_period or dei_fp or "Q?").upper()
    facts: Dict[str, Any] = {}
    fact_count = 0
    for node in _nodes(root, "nonfraction"):
        full_name = str(node.get("name") or "")
        if ":" not in full_name:
            continue
        prefix, tag = full_name.split(":", 1)
        if prefix.lower() != "us-gaap" or not tag:
            continue
        context = contexts.get(str(node.get("contextref") or ""))
        if not context:
            continue
        if report_date and context.get("end") != report_date:
            continue
        value = _number(node)
        if value is None:
            continue
        unit_ref = str(node.get("unitref") or "")
        unit = units.get(unit_ref) or _fallback_unit(unit_ref)
        if not unit:
            continue
        row: Dict[str, Any] = {
            "end": context["end"],
            "val": value,
            "accn": accession,
            "fy": fy or int(str(context["end"])[:4]),
            "fp": fp,
            "form": form,
            "filed": filing_date,
        }
        if context.get("start"):
            row["start"] = context["start"]
        facts.setdefault(tag, {"units": {}})["units"].setdefault(unit, []).append(row)
        fact_count += 1
    return {
        "facts": {"us-gaap": facts},
        "_inline_meta": {
            "accession": accession,
            "form": form,
            "fiscal_year": fy,
            "fiscal_period": fp,
            "fact_count": fact_count,
            "report_date": report_date or None,
        },
    }


def fetch_inline_xbrl(cik: int, filing: Dict[str, Any], timeout: int = 60) -> Dict[str, Any]:
    url = filing_url(cik, filing.get("accession") or "", filing.get("primary_document") or "")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read(MAX_INLINE_BYTES + 1)
    if len(body) > MAX_INLINE_BYTES:
        raise ValueError("inline filing exceeds size limit")
    out = parse_inline_xbrl(
        body,
        accession=str(filing.get("accession") or ""),
        form=str(filing.get("form") or ""),
        filing_date=str(filing.get("filing_date") or ""),
        report_date=str(filing.get("report_date") or ""),
    )
    out["_inline_meta"]["source_url"] = url
    for concept in ((out.get("facts") or {}).get("us-gaap") or {}).values():
        for rows in (concept.get("units") or {}).values():
            for row in rows:
                row["source_url"] = url
    return out


def has_accession(companyfacts: Dict[str, Any], accession: str) -> bool:
    if not accession:
        return False
    for concept in ((companyfacts.get("facts") or {}).get("us-gaap") or {}).values():
        for rows in (concept.get("units") or {}).values():
            if any(str(row.get("accn") or "") == accession for row in rows):
                return True
    return False


def merge_companyfacts(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy with inline filing rows appended to matching concepts/units."""
    out = copy.deepcopy(base)
    dst = out.setdefault("facts", {}).setdefault("us-gaap", {})
    src = ((overlay.get("facts") or {}).get("us-gaap") or {})
    for tag, concept in src.items():
        target_units = dst.setdefault(tag, {}).setdefault("units", {})
        for unit, rows in (concept.get("units") or {}).items():
            target_units.setdefault(unit, []).extend(copy.deepcopy(rows))
    return out
