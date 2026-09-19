"""Cache-only DART evidence for the public Korean stock report.

Only figures whose reporting period, currency, consolidation scope and filing
accession are present in the raw response are promoted.  The module never
fetches data.  It deliberately does not reuse the legacy ``free_cashflow``
field: operating cash flow plus total investing cash flow is not FCF.
"""
from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple


DART_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="
EVIDENCE_SCHEMA_VERSION = "kr-report-evidence-v1"
_DATE_RE = re.compile(r"\d{4}[.]\d{2}[.]\d{2}")
_ACCESSION_RE = re.compile(r"\d{14}")
_TICKER_RE = re.compile(r"\d{6}")

_REPORT_KIND = {
    "11011": ("annual", "thstrm_amount"),
    "11013": ("quarter", "thstrm_amount"),
    # DART single-account responses put the standalone quarter in
    # thstrm_amount and the year-to-date value in thstrm_add_amount.
    "11012": ("ytd", "thstrm_add_amount"),
    "11014": ("ytd", "thstrm_add_amount"),
}

_METRIC_NAMES = {
    "revenue": {"매출액", "수익(매출액)", "영업수익", "매출", "매출 및 지분법손익"},
    "op": {"영업이익", "영업이익(손실)"},
    "net": {
        "당기순이익", "당기순이익(손실)", "당기순손실", "당기순손익",
        "분기순이익", "분기순이익(손실)", "분기순손실", "분기순손익",
        "반기순이익", "반기순이익(손실)", "반기순손실", "반기순손익",
    },
    "ocf": {"영업활동현금흐름", "영업활동 현금흐름", "영업활동으로 인한 현금흐름"},
}
_METRIC_IDS = {
    "revenue": {"ifrs-full_Revenue", "ifrs_Revenue"},
    "op": {"dart_OperatingIncomeLoss"},
    "net": {"ifrs-full_ProfitLoss", "ifrs_ProfitLoss"},
    "ocf": {"ifrs-full_CashFlowsFromUsedInOperatingActivities"},
    # A single, explicit PPE purchase tag is accepted.  Total investing cash
    # flow and fuzzy Korean account names are never treated as capex.
    "capex": {"ifrs-full_PurchaseOfPropertyPlantAndEquipment"},
}


def _amount(value: Any) -> Optional[int]:
    if value is None:
        return None
    raw = str(value).replace(",", "").strip()
    if not raw or raw in {"-", "N/A"}:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _date(value: str) -> Optional[str]:
    try:
        return datetime.strptime(value, "%Y.%m.%d").date().isoformat()
    except (TypeError, ValueError):
        return None


def _identity(row: Dict[str, Any]) -> Optional[Tuple[str, str, str, str, str, str, str, str]]:
    ticker = str(row.get("stock_code") or "")
    accession = str(row.get("rcept_no") or "")
    scope = str(row.get("fs_div") or "")
    currency = str(row.get("currency") or "")
    report = _REPORT_KIND.get(str(row.get("reprt_code") or ""))
    dates = _DATE_RE.findall(str(row.get("thstrm_dt") or ""))
    if (not _TICKER_RE.fullmatch(ticker) or not _ACCESSION_RE.fullmatch(accession)
            or scope not in {"CFS", "OFS"} or not currency or not report or len(dates) != 2):
        return None
    start, end = _date(dates[0]), _date(dates[1])
    if not start or not end or start > end:
        return None
    filed = accession[:8]
    try:
        datetime.strptime(filed, "%Y%m%d")
    except ValueError:
        return None
    kind, amount_field = report
    return ticker, start, end, kind, currency, scope, accession, amount_field


def _metric(row: Dict[str, Any]) -> Optional[str]:
    if str(row.get("sj_div") or "") not in {"IS", "CIS", "CF"}:
        return None
    account_id = str(row.get("account_id") or "").strip()
    name = str(row.get("account_nm") or "").strip()
    for metric, ids in _METRIC_IDS.items():
        if account_id in ids:
            return metric
    for metric, names in _METRIC_NAMES.items():
        if name in names:
            return metric
    return None


def periods_from_rows(rows: Iterable[Dict[str, Any]]) -> Dict[str, list[Dict[str, Any]]]:
    """Parse DART rows into evidence periods keyed by ticker.

    Conflicting values for one metric inside the same exact filing identity are
    withheld.  Identical duplicate rows are harmless.  Corrected filings are
    kept separate until the latest accession is selected below.
    """
    grouped: Dict[Tuple[str, str, str, str, str, str, str], Dict[str, list[Tuple[int, Dict[str, Any]]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in rows:
        if not isinstance(row, dict):
            continue
        ident = _identity(row)
        metric = _metric(row)
        if not ident or not metric:
            continue
        ticker, start, end, kind, currency, scope, accession, amount_field = ident
        value = _amount(row.get(amount_field))
        if value is None:
            continue
        source_url = DART_URL + accession
        grouped[(ticker, start, end, kind, currency, scope, accession)][metric].append((value, {
            "account_id": row.get("account_id") or None,
            "name": str(row.get("account_nm") or ""),
            "start": start,
            "end": end,
            "currency": currency,
            "source_url": source_url,
        }))

    candidates: Dict[str, list[Dict[str, Any]]] = defaultdict(list)
    for (ticker, start, end, kind, currency, scope, accession), metrics in grouped.items():
        period: Dict[str, Any] = {
            "year": int(end[:4]), "start": start, "end": end,
            "period_kind": kind, "currency": currency, "fs_div": scope,
            "source_url": DART_URL + accession,
            "filed": f"{accession[:4]}-{accession[4:6]}-{accession[6:8]}",
            "accession": accession, "rcept_no": accession,
            "revenue": None, "op": None, "net": None, "ocf": None, "capex": None,
            "metric_sources": {},
        }
        for metric in ("revenue", "op", "net", "ocf", "capex"):
            found = metrics.get(metric) or []
            values = {value for value, _source in found}
            if len(values) != 1:
                continue
            value = next(iter(values))
            source = next(source for item_value, source in found if item_value == value)
            period[metric] = value
            period["metric_sources"][metric] = source
        if period["metric_sources"]:
            candidates[ticker].append(period)

    # A correction supersedes an older filing for the same period and scope.
    # CFS is preferred; OFS remains a fallback when no CFS candidate exists.
    out: Dict[str, list[Dict[str, Any]]] = {}
    for ticker, periods in candidates.items():
        latest: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
        for period in periods:
            key = (period["start"], period["end"], period["period_kind"], period["currency"])
            prior = latest.get(key)
            if prior is None:
                latest[key] = period
                continue
            rank = (period["fs_div"] == "CFS", period["accession"])
            prior_rank = (prior["fs_div"] == "CFS", prior["accession"])
            if rank > prior_rank:
                latest[key] = period
        out[ticker] = list(latest.values())
    return out


def load_financial_evidence(
    cache_dir: str,
    tickers: Optional[set[str]] = None,
    annual_limit: int = 4,
    interim_limit: int = 8,
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, int]]:
    """Load local single-account cache files without any network fallback."""
    files = sorted(Path(cache_dir).glob("*.json")) if os.path.isdir(cache_dir) else []
    rows: list[Dict[str, Any]] = []
    parsed_files = nonempty_files = 0
    for path in files:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        parsed_files += 1
        if not isinstance(doc, dict) or doc.get("status") not in {None, "000"}:
            continue
        source_rows = doc.get("list") if isinstance(doc, dict) else None
        if not isinstance(source_rows, list) or not source_rows:
            continue
        nonempty_files += 1
        if tickers:
            source_rows = [r for r in source_rows if isinstance(r, dict)
                           and str(r.get("stock_code") or "") in tickers]
        rows.extend(source_rows)

    parsed = periods_from_rows(rows)
    evidence: Dict[str, Dict[str, Any]] = {}
    for ticker, periods in parsed.items():
        annual = sorted((p for p in periods if p["period_kind"] == "annual"),
                        key=lambda p: (p["end"], p["accession"]), reverse=True)[:annual_limit]
        interim = sorted((p for p in periods if p["period_kind"] != "annual"),
                         key=lambda p: (p["end"], p["accession"]), reverse=True)[:interim_limit]
        selected = sorted(annual + interim, key=lambda p: (p["end"], p["accession"]))
        if selected:
            evidence[ticker] = {
                "schema_version": EVIDENCE_SCHEMA_VERSION,
                "source": "DART 단일회사 주요계정",
                "periods": selected,
            }
    return evidence, {
        "cache_files": len(files),
        "parsed_files": parsed_files,
        "nonempty_files": nonempty_files,
        "tickers": len(parsed),
        "attached": len(evidence),
    }


def _iso_day(value: Any) -> bool:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date().isoformat() == value
    except (TypeError, ValueError):
        return False


def valid_financial_evidence(value: Any) -> bool:
    """Validate a previously published block before carrying it forward."""
    if not isinstance(value, dict) or value.get("schema_version") != EVIDENCE_SCHEMA_VERSION:
        return False
    if value.get("source") != "DART 단일회사 주요계정":
        return False
    periods = value.get("periods")
    if not isinstance(periods, list) or not periods:
        return False
    for period in periods:
        if not isinstance(period, dict):
            return False
        accession = str(period.get("accession") or "")
        source_url = DART_URL + accession
        if (not _ACCESSION_RE.fullmatch(accession) or period.get("rcept_no") != accession
                or period.get("source_url") != source_url
                or period.get("period_kind") not in {"annual", "quarter", "ytd"}
                or period.get("fs_div") not in {"CFS", "OFS"}
                or not re.fullmatch(r"[A-Z]{3}", str(period.get("currency") or ""))
                or not _iso_day(period.get("start")) or not _iso_day(period.get("end"))
                or not _iso_day(period.get("filed"))
                or period["start"] > period["end"]
                or period.get("year") != int(period["end"][:4])
                or period.get("filed") != f"{accession[:4]}-{accession[4:6]}-{accession[6:8]}"):
            return False
        sources = period.get("metric_sources")
        if not isinstance(sources, dict):
            return False
        promoted = 0
        for metric in ("revenue", "op", "net", "ocf", "capex"):
            amount = period.get(metric)
            source = sources.get(metric)
            if amount is None:
                if source is not None:
                    return False
                continue
            if isinstance(amount, bool) or not isinstance(amount, int) or not isinstance(source, dict):
                return False
            if (source.get("start") != period["start"] or source.get("end") != period["end"]
                    or source.get("currency") != period["currency"]
                    or source.get("source_url") != source_url
                    or not any(isinstance(source.get(key), str) and source.get(key)
                               for key in ("account_id", "name"))):
                return False
            promoted += 1
        if promoted == 0 or set(sources) - {"revenue", "op", "net", "ocf", "capex"}:
            return False
    return True


def load_previous_financial_evidence(path: str) -> Dict[str, Dict[str, Any]]:
    """Read only validated financial evidence from the previous public snapshot."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    stocks = doc.get("stocks") if isinstance(doc, dict) else None
    if isinstance(stocks, dict):
        rows = stocks.values()
    elif isinstance(stocks, list):
        rows = stocks
    else:
        return {}
    financial: Dict[str, Dict[str, Any]] = {}
    for stock in rows:
        if not isinstance(stock, dict):
            continue
        ticker = str(stock.get("ticker") or "")
        if not _TICKER_RE.fullmatch(ticker):
            continue
        if valid_financial_evidence(stock.get("financial_evidence")):
            financial[ticker] = stock["financial_evidence"]
    return financial


def reconcile_financial_evidence(
    tickers: Iterable[str],
    current: Dict[str, Dict[str, Any]],
    previous: Dict[str, Dict[str, Any]],
) -> Tuple[Dict[str, Dict[str, Any]], int]:
    """Prefer current cache evidence and preserve validated prior blocks."""
    selected: Dict[str, Dict[str, Any]] = {}
    preserved = 0
    for ticker in tickers:
        evidence = current.get(ticker)
        prior = previous.get(ticker)
        if evidence is None:
            evidence = prior
            preserved += evidence is not None
        elif prior is not None:
            # A partially populated cache must not erase older verified periods.
            # For the same period, keep the preferred CFS/latest filing identity.
            periods: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
            for period in prior["periods"] + evidence["periods"]:
                key = (period["start"], period["end"], period["period_kind"], period["currency"])
                existing = periods.get(key)
                rank = (period["fs_div"] == "CFS", period["accession"])
                old_rank = ((existing or {}).get("fs_div") == "CFS", (existing or {}).get("accession", ""))
                if existing is None or rank > old_rank:
                    periods[key] = period
            annual = sorted((p for p in periods.values() if p["period_kind"] == "annual"),
                            key=lambda p: (p["end"], p["accession"]), reverse=True)[:4]
            interim = sorted((p for p in periods.values() if p["period_kind"] != "annual"),
                             key=lambda p: (p["end"], p["accession"]), reverse=True)[:8]
            evidence = dict(evidence)
            evidence["periods"] = sorted(annual + interim, key=lambda p: (p["end"], p["accession"]))
        if evidence is not None:
            selected[ticker] = evidence
    return selected, preserved
