"""Public-only source boundary for the AlphaConsole portfolio sidecar.

This module is deliberately a small projection layer. It reads only the fixed
published artifacts named in ``PUBLIC_SOURCE_FILES`` and emits fixed schemas.
The company/report feeds drive the company projection; optional evidence and
business-overview artifacts remain separate candidate projections.
It never imports an operator collector, consults environment variables, or
performs network I/O.

Accepted explicit fact object::

    {"metric": "revenue", "value": 123.0, "unit": "USD",
     "as_of": "2025-12-31", "source": "SEC"}

Annual ``fin_series`` rows from the existing report builders are also accepted.
Legacy producers only preserve a fiscal year, so ``as_of`` remains ``YYYY``.
Optional SEC metric provenance preserves the actual period end separately; it
must never become an invented filing/publication date or currency assertion.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import stat
from typing import Any, Iterable, Mapping


PUBLIC_SOURCE_FILES = (
    "universe_search.json",
    "stock_report_public.json",
    "us_stock_report_public.json",
    "public_disclosure_feed.json",
    "us_disclosure_feed.json",
    "member_map_auto_evidence.json",
    "kr_business_overview_public.json",
    "macro_snapshot.json",
    "commodity_exposure.json",
    "portfolio.json",
    "member_map_ai_candidates.json",
)

OPTIONAL_PUBLIC_SOURCE_FILES = (
    "member_map_auto_evidence.json",
    "kr_business_overview_public.json",
    "macro_snapshot.json",
    "commodity_exposure.json",
    "portfolio.json",
    "member_map_ai_candidates.json",
)

PUBLIC_SOURCE_MAX_BYTES = {
    "universe_search.json": 16 * 1024 * 1024,
    "stock_report_public.json": 64 * 1024 * 1024,
    "us_stock_report_public.json": 64 * 1024 * 1024,
    "public_disclosure_feed.json": 16 * 1024 * 1024,
    "us_disclosure_feed.json": 16 * 1024 * 1024,
    "member_map_auto_evidence.json": 8 * 1024 * 1024,
    "kr_business_overview_public.json": 8 * 1024 * 1024,
    "macro_snapshot.json": 8 * 1024 * 1024,
    "commodity_exposure.json": 2 * 1024 * 1024,
    "portfolio.json": 8 * 1024 * 1024,
    "member_map_ai_candidates.json": 2_000_000,
}

PUBLIC_COMPANY_FIELDS = ("id", "ticker", "market", "name", "sector", "facts", "documents")
PUBLIC_FACT_FIELDS = ("metric", "value", "unit", "as_of", "source")
# SEC documents may additionally carry validated item_codes/filing metadata.
PUBLIC_DOCUMENT_FIELDS = ("id", "title", "url", "as_of", "kind", "source")
PUBLIC_SEC_FILING_FIELDS = ("form", "is_correction", "cik", "accession_number",
                            "primary_document", "filing_date", "report_date", "acceptance_datetime")
_SEC_ITEM_CODE_RE = re.compile(r"[1-9]\.[0-9]{2}", re.ASCII)
_SEC_ITEM_CODES_MAX = 32

_MARKET_ALIASES = {
    "KR": "KR",
    "KOSPI": "KR",
    "KOSDAQ": "KR",
    "KONEX": "KR",
    "US": "US",
    "NASDAQ": "US",
    "NYSE": "US",
    "AMEX": "US",
    "NYSEARCA": "US",
    "ARCA": "US",
    "BATS": "US",
}
_KR_TICKER_RE = re.compile(r"[0-9]{6}\Z", re.ASCII)
_US_TICKER_RE = re.compile(
    r"[A-Z][A-Z0-9]{0,9}(?:[.-][A-Z0-9]{1,2})?\Z",
    re.ASCII,
)
_SECURITY_TYPE_MARKETS = frozenset({"ETF", "ETN"})

_METRIC_ALIASES = {
    "revenue": "revenue",
    "매출": "revenue",
    "operating_income": "operating_income",
    "operating_profit": "operating_income",
    "op": "operating_income",
    "영업이익": "operating_income",
    "net_income": "net_income",
    "net": "net_income",
    "순이익": "net_income",
    "total_assets": "total_assets",
    "총자산": "total_assets",
    "total_liabilities": "total_liabilities",
    "총부채": "total_liabilities",
    "equity": "equity",
    "자기자본": "equity",
    "cash": "cash",
    "현금성자산": "cash",
    "free_cash_flow": "free_cash_flow",
    "fcf": "free_cash_flow",
    "eps": "eps",
    "market_cap": "market_cap",
    "시가총액": "market_cap",
    "per": "per",
    "pbr": "pbr",
    "roe": "roe",
    "debt_ratio": "debt_ratio",
    "부채비율": "debt_ratio",
    "operating_margin": "operating_margin",
    "영업이익률": "operating_margin",
    "revenue_growth": "revenue_growth",
    "매출성장": "revenue_growth",
    "매출성장(분기yoy)": "revenue_growth_quarterly_yoy",
}
_UNIT_ALIASES = {
    "KRW": "KRW",
    "USD": "USD",
    "CAD": "CAD",
    "AUD": "AUD",
    "EUR": "EUR",
    "GBP": "GBP",
    "JPY": "JPY",
    "HKD": "HKD",
    "CNY": "CNY",
    "CHF": "CHF",
    "ILS": "ILS",
    "SGD": "SGD",
    "NZD": "NZD",
    "BRL": "BRL",
    "%": "pct",
    "pct": "pct",
    "ratio": "ratio",
    "times": "times",
    "KRW/share": "KRW/share",
    "USD/share": "USD/share",
}
_CURRENCY_UNITS = frozenset({
    "KRW", "USD", "CAD", "AUD", "EUR", "GBP", "JPY", "HKD",
    "CNY", "CHF", "ILS", "SGD", "NZD", "BRL",
})
_SOURCE_ALIASES = {
    "DART": "DART",
    "DART OpenAPI": "DART",
    "DART OpenAPI (전자공시)": "DART",
    "DART 전자공시": "DART",
    "DART(전자공시·재무)": "DART",
    "SEC": "SEC",
    "SEC EDGAR": "SEC",
    "SEC EDGAR XBRL": "SEC",
    "SEC EDGAR XBRL (us_financials)": "SEC",
    "KRX": "KRX",
    "KRX 정보데이터시스템": "KRX",
}
_SOURCE_MARKETS = {"DART": "KR", "KRX": "KR", "SEC": "US"}

_EMAIL_RE = re.compile(r"(?i)(?<![\w.+-])[\w.+-]+@[a-z0-9.-]+\.[a-z]{2,}(?![\w.-])")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[- .]?)?\(?\d{2,4}\)?[- .]\d{3,4}[- .]\d{4}(?!\d)")
_LONG_ID_RE = re.compile(r"(?<![0-9])[0-9]{10,}(?![0-9])", re.ASCII)
_UUID_RE = re.compile(
    r"(?i)(?<![0-9a-f])[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}(?![0-9a-f])"
)
_JWT_RE = re.compile(
    r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."
    r"[A-Za-z0-9_-]{10,}(?![A-Za-z0-9_-])",
    re.ASCII,
)
_SECRET_KEY_RE = re.compile(r"(?i)(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{8,}(?![A-Za-z0-9_-])")
_SECRET_RE = re.compile(
    r"(?i)\b(?:secret|password|passwd|api[ _-]?key|access[ _-]?token|refresh[ _-]?token|"
    r"authorization|bearer|private[ _-]?key|owner[ _-]?id|member[ _-]?id|tenant[ _-]?id)\b|"
    r"(?:비밀번호|인증토큰|접근토큰|개인키|주민등록번호)"
)
_PATH_RE = re.compile(
    r"(?i)(?:file://|(?:^|[\s\"'(])(?:/Users/|/home/|/private/|/var/|\.\.?/|[a-z]:\\))"
)
_URL_IN_TEXT_RE = re.compile(r"(?i)(?:https?|ftp|data|javascript):")
_HTML_RE = re.compile(r"<[^>]*>|&(?:lt|gt|#(?:x[0-9a-f]+|\d+));", re.IGNORECASE)


class PublicSourceError(ValueError):
    """A non-reflecting public-boundary error."""


class _DuplicateKeyError(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError
        result[key] = value
    return result


def load_public_sources(directory: str | os.PathLike[str]) -> dict[str, dict[str, Any]]:
    """Load every exact allowlisted public artifact from a local directory.

    The directory and each source must be real directories/files rather than
    symbolic links.  Errors intentionally contain neither filesystem paths nor
    source values.
    """

    if not isinstance(directory, (str, os.PathLike)):
        raise PublicSourceError("public source directory rejected")
    try:
        raw_directory = os.fspath(directory)
        if not isinstance(raw_directory, str) or "\x00" in raw_directory:
            raise ValueError
        directory_path = Path(raw_directory)
        if ".." in directory_path.parts:
            raise ValueError
        directory_stat = directory_path.lstat()
        if stat.S_ISLNK(directory_stat.st_mode) or not stat.S_ISDIR(directory_stat.st_mode):
            raise ValueError
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        directory_fd = os.open(directory_path, flags)
    except (OSError, TypeError, ValueError):
        raise PublicSourceError("public source directory rejected") from None

    documents: dict[str, dict[str, Any]] = {}
    try:
        for filename in PUBLIC_SOURCE_FILES:
            limit = PUBLIC_SOURCE_MAX_BYTES[filename]
            try:
                before = os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
            except FileNotFoundError:
                if filename in OPTIONAL_PUBLIC_SOURCE_FILES:
                    continue
                raise PublicSourceError("public source file rejected") from None
            try:
                if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
                    raise ValueError
                file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                file_fd = os.open(filename, file_flags, dir_fd=directory_fd)
                try:
                    after = os.fstat(file_fd)
                    if (
                        not stat.S_ISREG(after.st_mode)
                        or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
                        or after.st_size > limit
                    ):
                        raise ValueError
                    with os.fdopen(file_fd, "rb", closefd=True) as handle:
                        file_fd = -1
                        payload = handle.read(limit + 1)
                finally:
                    if file_fd >= 0:
                        os.close(file_fd)
                if len(payload) > limit:
                    raise ValueError
                document = json.loads(
                    payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys
                )
                if not isinstance(document, dict):
                    raise ValueError
                documents[filename] = document
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
                raise PublicSourceError("public source file rejected") from None
    finally:
        os.close(directory_fd)
    return documents


def _source_market(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return _MARKET_ALIASES.get(value.strip().upper())


def _ticker(value: Any, market: str) -> str | None:
    if not isinstance(value, str):
        return None
    pattern = _KR_TICKER_RE if market == "KR" else _US_TICKER_RE
    return value if pattern.fullmatch(value) else None


def _safe_text(value: Any, maximum: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > maximum:
        return None
    if any(ord(char) < 32 or ord(char) == 127 for char in text):
        return None
    if any(pattern.search(text) for pattern in (
        _EMAIL_RE,
        _PHONE_RE,
        _LONG_ID_RE,
        _UUID_RE,
        _JWT_RE,
        _SECRET_KEY_RE,
        _SECRET_RE,
        _PATH_RE,
        _URL_IN_TEXT_RE,
        _HTML_RE,
    )):
        return None
    return text


def safe_public_text(value: Any, maximum: int) -> str | None:
    """Apply the shared sensitive-text boundary to an explicit narrative field."""
    return _safe_text(value, maximum)


def _as_of(value: Any, *, annual_ok: bool = False) -> str | None:
    if annual_ok and isinstance(value, int) and not isinstance(value, bool):
        return str(value) if 1900 <= value <= 2100 else None
    if annual_ok and isinstance(value, str) and re.fullmatch(r"[0-9]{4}", value, re.ASCII):
        year = int(value)
        return value if 1900 <= year <= 2100 else None
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value, re.ASCII
    ):
        return None
    try:
        date.fromisoformat(value)
    except ValueError:
        return None
    return value


def _finite_number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    if not math.isfinite(number) or abs(number) > 1e30:
        return None
    return value


def _iter_rows(value: Any) -> Iterable[tuple[str | None, Mapping[str, Any]]]:
    if isinstance(value, list):
        for row in value:
            if isinstance(row, Mapping):
                yield None, row
    elif isinstance(value, Mapping):
        for key, row in value.items():
            if isinstance(key, str) and isinstance(row, Mapping):
                yield key, row


def _validated_rows(
    document: Mapping[str, Any], field: str
) -> Iterable[tuple[str | None, Mapping[str, Any]]]:
    value = document.get(field)
    if isinstance(value, list):
        if any(not isinstance(row, Mapping) for row in value):
            raise PublicSourceError("public source shape rejected")
    elif isinstance(value, Mapping):
        if any(
            not isinstance(key, str) or not isinstance(row, Mapping)
            for key, row in value.items()
        ):
            raise PublicSourceError("public source shape rejected")
    else:
        raise PublicSourceError("public source shape rejected")
    return _iter_rows(value)


def _row_identity(
    row: Mapping[str, Any],
    *,
    default_market: str | None = None,
    ticker_hint: str | None = None,
) -> tuple[str, str] | None:
    raw_ticker = row.get("ticker") if row.get("ticker") is not None else ticker_hint
    raw_market = row.get("market")
    if raw_market is None or (default_market is not None and raw_market == ""):
        raw_market = default_market
    market = _source_market(raw_market)
    if (
        market is None
        and isinstance(raw_market, str)
        and raw_market.strip().upper() in _SECURITY_TYPE_MARKETS
        and isinstance(raw_ticker, str)
    ):
        if _KR_TICKER_RE.fullmatch(raw_ticker):
            market = "KR"
        elif _US_TICKER_RE.fullmatch(raw_ticker):
            market = "US"
    if market is None or (default_market is not None and market != default_market):
        return None
    ticker = _ticker(raw_ticker, market)
    return (market, ticker) if ticker else None


def _sector(row: Mapping[str, Any]) -> str | None:
    candidates: list[Any] = [row.get("sector"), row.get("gics_ko"), row.get("gics")]
    overview = row.get("overview")
    if isinstance(overview, Mapping):
        candidates.append(overview.get("sector"))
    peer = row.get("peer")
    if isinstance(peer, Mapping):
        candidates.append(peer.get("sector"))
    for candidate in candidates:
        if candidate in (None, ""):
            continue
        safe = _safe_text(candidate, 120)
        if safe:
            return safe
    return None


def _canonical_metric(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return _METRIC_ALIASES.get(value.strip().lower())


def _canonical_source(value: Any) -> str | None:
    return _SOURCE_ALIASES.get(value) if isinstance(value, str) else None


def _fact_from_object(
    raw: Mapping[str, Any], market: str, metric_hint: str | None = None
) -> dict[str, Any] | None:
    metric = _canonical_metric(raw.get("metric") if raw.get("metric") is not None else metric_hint)
    value = _finite_number(raw.get("value"))
    unit = _UNIT_ALIASES.get(raw.get("unit")) if isinstance(raw.get("unit"), str) else None
    stamp = _as_of(raw.get("as_of"), annual_ok=True)
    if raw.get("source") is not None:
        source = _canonical_source(raw.get("source"))
        if source is None:
            raise PublicSourceError("public fact source rejected")
    else:
        source = None
    if source is not None and _SOURCE_MARKETS[source] != market:
        raise PublicSourceError("public fact source rejected")
    if None in (metric, value, unit, stamp, source):
        return None
    return {"metric": metric, "value": value, "unit": unit, "as_of": stamp, "source": source}


def _explicit_facts(row: Mapping[str, Any], market: str) -> Iterable[dict[str, Any]]:
    facts = row.get("facts")
    if isinstance(facts, list):
        for raw in facts:
            if isinstance(raw, Mapping):
                fact = _fact_from_object(raw, market)
                if fact:
                    yield fact
        return
    if not isinstance(facts, Mapping):
        return
    notes = row.get("facts_note") if isinstance(row.get("facts_note"), Mapping) else {}
    for metric, raw in facts.items():
        if isinstance(raw, Mapping):
            fact = _fact_from_object(raw, market, str(metric))
        elif _finite_number(raw) is not None and isinstance(notes.get(metric), Mapping):
            fact = _fact_from_object(
                {**dict(notes[metric]), "metric": metric, "value": raw}, market
            )
        else:
            fact = None
        if fact:
            yield fact


def _series_facts(
    row: Mapping[str, Any], market: str, source: str
) -> Iterable[dict[str, Any]]:
    series = row.get("fin_series")
    if not isinstance(series, list):
        return
    for point in series:
        if not isinstance(point, Mapping):
            continue
        stamp = _as_of(point.get("year"), annual_ok=True)
        if market == "KR":
            # The legacy KR public-report builder emits DART annual values as
            # {year, revenue, op, net} with no currency field; that fixed shape
            # is KRW.  A newly explicit non-KRW unit is unsupported, not relabeled.
            if "currency" not in point:
                unit = "KRW"
            else:
                unit = "KRW" if point.get("currency") == "KRW" else None
        else:
            raw_unit = point.get("currency")
            unit = raw_unit if isinstance(raw_unit, str) and raw_unit in _CURRENCY_UNITS else None
        if stamp is None:
            continue
        for input_key, metric in (
            ("revenue", "revenue"),
            ("op", "operating_income"),
            ("net", "net_income"),
        ):
            value = _finite_number(point.get(input_key))
            if value is not None:
                fact = {
                    "metric": metric,
                    "value": value,
                    "unit": unit,
                    "as_of": stamp,
                    "source": source,
                }
                sources = point.get("metric_sources")
                if market == "US" and isinstance(sources, Mapping) and input_key in sources:
                    provenance = _sec_metric_provenance(sources[input_key], stamp)
                    if provenance is None:
                        continue  # Invalid claimed proof cannot fall back to a verified-looking value.
                    fact["provenance"] = provenance
                    if not provenance["currency_verified"]:
                        fact["unit"] = "currency-unverified"
                if market == "KR" and source == "DART" and unit == "KRW":
                    provenance = _dart_annual_provenance(row, stamp, input_key, value)
                    if provenance is not None:
                        fact["provenance"] = provenance
                if fact["unit"] is not None:
                    yield fact


def _dart_annual_provenance(
    row: Mapping[str, Any], annual_stamp: str, metric: str, raw_value: int | float
) -> dict[str, Any] | None:
    """Bind an existing annual value to one unambiguous same-row DART proof.

    This does not select a newer value or infer a reporting period. Invalid
    evidence is optional and must not remove or relabel the legacy fact.
    """
    evidence = row.get("financial_evidence")
    if (len(annual_stamp) != 4 or not isinstance(evidence, Mapping)
            or evidence.get("schema_version") != "kr-report-evidence-v1"):
        return None
    periods = evidence.get("periods")
    if not isinstance(periods, list) or len(periods) > 64:
        return None
    proof = None
    for period in periods:
        if (not isinstance(period, Mapping) or period.get("period_kind") != "annual"
                or _as_of(period.get("year"), annual_ok=True) != annual_stamp
                or period.get("currency") != "KRW"
                or period.get("fs_div") not in ("CFS", "OFS")):
            continue
        candidate_value = _finite_number(period.get(metric))
        # _finite_number returns the original int/float. Never compare float(...)
        # conversions: distinct large JSON integers can round to the same float.
        if candidate_value is None or candidate_value != raw_value:
            continue
        start, end, filed = (_as_of(period.get(key)) for key in ("start", "end", "filed"))
        if (start is None or end is None or filed is None or end[:4] != annual_stamp
                or any(stamp[:2] not in {"19", "20", "21"} for stamp in (start, end, filed))):
            continue
        first, last = date.fromisoformat(start), date.fromisoformat(end)
        if not 330 <= (last - first).days + 1 <= 371 or date.fromisoformat(filed) < last:
            continue  # Same bounded annual-duration contract as the consumer.
        receipt = period.get("rcept_no")
        if (not isinstance(receipt, str) or not re.fullmatch(r"[0-9]{14}", receipt, re.ASCII)
                or period.get("accession") != receipt or receipt[:8] != filed.replace("-", "")):
            continue
        source_url = period.get("source_url")
        if _canonical_disclosure_url(source_url, "DART") != (source_url, f"DART:{receipt}"):
            continue
        sources = period.get("metric_sources")
        metric_source = sources.get(metric) if isinstance(sources, Mapping) else None
        if (not isinstance(metric_source, Mapping) or metric_source.get("start") != start
                or metric_source.get("end") != end or metric_source.get("currency") != "KRW"
                or metric_source.get("source_url") != source_url):
            continue
        account_name = _safe_text(metric_source.get("name"), 200)
        if account_name is None:
            continue
        candidate = {"kind": "dart-annual", "rcept_no": receipt,
                     "period_start": start, "period_end": end, "filed": filed,
                     "fs_div": period["fs_div"], "account_name": account_name,
                     "source_url": source_url}
        if proof is not None and candidate != proof:
            return None
        proof = candidate
    return proof


def _sec_metric_provenance(value: Any, annual_stamp: str) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    cik, accession = value.get("cik"), value.get("accession")
    if not isinstance(cik, str) or not re.fullmatch(r"[0-9]{1,10}", cik, re.ASCII) or int(cik) <= 0:
        return None
    cik = str(int(cik))
    if not isinstance(accession, str) or not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession, re.ASCII):
        return None
    period = _as_of(value.get("period_end"))
    form, tag, verified = value.get("form"), value.get("tag"), value.get("currency_verified")
    if period is None or len(period) != 10 or period[:4] != annual_stamp:
        return None
    if not isinstance(form, str) or form not in {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}:
        return None
    if not isinstance(tag, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_:]{0,199}", tag, re.ASCII):
        return None
    if not isinstance(verified, bool):
        return None
    # Accession prefix may be a filing agent's CIK; do not require it to match
    # the registrant. Both identities originate in the same cached metric row.
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{accession}-index"
    source_url = value.get("source_url")
    if source_url not in (base + ".htm", base + ".html"):
        return None
    return {"cik": cik, "accession": accession, "form": form, "period_end": period,
            "tag": tag, "source_url": source_url, "currency_verified": verified}


def _canonical_disclosure_url(value: Any, source: str) -> tuple[str, str] | None:
    if not isinstance(value, str) or len(value) > 600 or any(ord(c) < 32 for c in value):
        return None
    if source == "DART":
        match = re.fullmatch(
            r"https://dart\.fss\.or\.kr/dsaf001/main\.do\?rcpNo=([0-9]{14})",
            value,
            re.ASCII,
        )
        if not match:
            return None
        receipt = match.group(1)
        return f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}", f"DART:{receipt}"

    if source == "SEC":
        match = re.fullmatch(
            r"https://(?:www\.)?sec\.gov/Archives/edgar/data/"
            r"([1-9][0-9]{0,9})/([0-9]{18})/"
            r"(?:([A-Za-z0-9][A-Za-z0-9._-]{0,199})/?)?",
            value,
            re.ASCII,
        )
        if not match:
            return None
        cik, accession, filename = match.groups()
        canonical_path = f"/Archives/edgar/data/{cik}/{accession}/"
        if filename:
            canonical_path += filename
        identifier = f"SEC:{cik}:{accession}:{filename or 'filing'}"
        return f"https://www.sec.gov{canonical_path}", identifier
    return None


def _sec_item_codes(value: Any) -> list[str] | None:
    """Preserve bounded code syntax only, without interpreting item meanings."""
    if (not isinstance(value, list) or not 1 <= len(value) <= _SEC_ITEM_CODES_MAX
            or any(not isinstance(code, str) or not _SEC_ITEM_CODE_RE.fullmatch(code)
                   for code in value)):
        return None
    if len(set(value)) != len(value):
        return None
    return list(value)



def _sec_filing(raw: Mapping[str, Any], url: str, filed: str) -> dict[str, Any] | None:
    """Bind optional typed metadata to this canonical filing, never to its title."""
    form, correction = raw.get("label"), raw.get("is_correction")
    if (not isinstance(form, str) or form not in {
            "8-K", "8-K/A", "6-K", "6-K/A", "20-F", "20-F/A",
            "40-F", "40-F/A", "10-K", "10-K/A", "10-Q", "10-Q/A"}
            or type(correction) is not bool or correction != form.endswith("/A")):
        return None
    cik, accession, primary = raw.get("cik"), raw.get("accession_number"), raw.get("primary_document")
    if (not isinstance(cik, str) or not re.fullmatch(r"[0-9]{1,10}", cik, re.ASCII)
            or int(cik) <= 0 or not isinstance(accession, str)
            or not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession, re.ASCII)
            or not isinstance(primary, str)):
        return None
    cik = str(int(cik))
    if primary and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}", primary, re.ASCII):
        return None
    # A co-filer/agent may own the accession prefix; only the URL's issuer CIK
    # must match the supplied issuer. Missing primary documents use this index.
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/"
    if url not in ((base + primary,) if primary else
                   (base + accession + "-index.htm", base + accession + "-index.html")):
        return None
    filing_date = _as_of(raw.get("filing_date"))
    if (filing_date is None or filing_date != filed or not 1900 <= int(filed[:4]) <= 2100
            or filing_date > date.today().isoformat()):
        return None
    report = raw.get("report_date")
    if report in (None, ""):
        report = None
    elif _as_of(report) is None or report > filed or int(report[:4]) < 1900:
        return None
    acceptance = raw.get("acceptance_datetime")
    if acceptance in (None, ""):
        acceptance = None
    else:
        if _generated_at(acceptance) is None:
            return None
        parsed = datetime.fromisoformat(acceptance.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed > datetime.now(timezone.utc):
            return None
    # SEC acceptance time is retained literally; it is not public availability
    # or the collector's observation clock and may cross the filing day's UTC boundary.
    return {"form": form, "is_correction": correction, "cik": cik,
            "accession_number": accession, "primary_document": primary or None,
            "filing_date": filing_date, "report_date": report, "acceptance_datetime": acceptance}


def _disclosure(
    raw: Mapping[str, Any], source: str
) -> dict[str, Any] | None:
    if raw.get("source") is not None:
        explicit_source = _canonical_source(raw.get("source"))
        if explicit_source is None or explicit_source != source:
            raise PublicSourceError("public document source rejected")
    title = _safe_text(raw.get("title"), 300)
    stamp = _as_of(raw.get("date"))
    target = _canonical_disclosure_url(raw.get("source_url"), source)
    if title is None or stamp is None or target is None:
        return None
    url, identifier = target
    projected = {
        "id": identifier,
        "title": title,
        "url": url,
        "as_of": stamp,
        "kind": "disclosure",
        "source": source,
    }
    if source == "SEC":
        filing = _sec_filing(raw, url, stamp)
        if filing is not None:
            projected["filing"] = filing
    if source == "SEC" and raw.get("label") in ("8-K", "8-K/A"):
        codes = _sec_item_codes(raw.get("item_codes"))
        if codes is not None:
            projected["item_codes"] = codes
            suffix = " · 항목 " + " · ".join(codes)
            # Keep the original title intact, including at the existing cap.
            if not title.endswith(suffix) and len(title + suffix) <= 300:
                projected["title"] = title + suffix
    return projected


def _dart_source_collection(document: Mapping[str, Any]) -> dict[str, Any] | None:
    """Optional listing-check evidence, separate from file/fact availability.

    Never copy the source payload, error text, scope or group records. A legacy
    feed remains unchanged; invalid optional metadata cannot remove its filings.
    Counts describe bounded query groups/pages, never issuers or raw documents.
    """
    meta = document.get("_meta")
    if not isinstance(meta, Mapping) or "source_collection" not in meta:
        return None
    unknown = {
        "file_present": True, "endpoint": "list.json", "status": "unknown",
        "attempted_at": None, "completed_at": None, "successful_checked_at": None,
        "groups_expected": None, "groups_completed": None,
        "pages_attempted": None, "pages_succeeded": None,
        "raw_body_checked": False, "whole_market_coverage": False,
    }
    source = meta["source_collection"]
    if (not isinstance(source, Mapping) or type(source.get("schema_version")) is not int
            or source["schema_version"] != 1 or source.get("endpoint") != "list.json"
            or source.get("status") not in ("running", "success", "partial", "failed")):
        return unknown
    now = datetime.now(timezone.utc)

    def timestamp(value):
        if _generated_at(value) is None:
            raise ValueError
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp > now:
            raise ValueError
        return stamp

    try:
        status = source["status"]
        attempted = timestamp(source["attempted_at"])
        if status == "running":
            if source["completed_at"] is not None or source["successful_checked_at"] is not None:
                return unknown
        else:
            completed = timestamp(source["completed_at"])
            if completed < attempted:
                return unknown
            if status == "success":
                if timestamp(source["successful_checked_at"]) != completed:
                    return unknown
            elif source["successful_checked_at"] is not None:
                return unknown  # A prior success cannot certify the current attempt.
        scope = source["scope"]
        classes = scope["corp_cls"]
        if (not isinstance(classes, list) or not 1 <= len(classes) <= 2
                or any(cls not in ("Y", "K") for cls in classes)
                or len(set(classes)) != len(classes)
                or scope["pblntf_ty"] != ["B", "C", "D", "I"]
                or scope["requires_stock_code"] is not True):
            return unknown
        expected = {(cls, ty) for cls in classes for ty in scope["pblntf_ty"]}
        cap = source["max_pages_per_group"]
        # Current producer's existing 20-page cap, not a freshness/impact threshold.
        if type(cap) is not int or not 1 <= cap <= 20:
            return unknown
        count_keys = ("groups_expected", "groups_completed", "pages_attempted", "pages_succeeded")
        if (any(type(source[key]) is not int or source[key] < 0 for key in count_keys)
                or source["groups_expected"] != len(expected)):
            return unknown
        groups = source["groups"]
        if (not isinstance(groups, list) or len(groups) > len(expected)
                or status != "running" and len(groups) != len(expected)):
            return unknown
        seen, finished, tried, succeeded = set(), 0, 0, 0
        for group in groups:
            if not isinstance(group, Mapping):
                return unknown
            identity = (group["corp_cls"], group["pblntf_ty"])
            if identity not in expected or identity in seen:
                return unknown
            seen.add(identity)
            a, s = group["pages_attempted"], group["pages_succeeded"]
            if (type(a) is not int or type(s) is not int or not 0 <= s <= a <= cap
                    or group["status"] not in ("success", "failed", "truncated")):
                return unknown
            if group["status"] == "success":
                total = group["total_pages"]
                if (type(total) is not int or total < 0 or s != max(1, total)
                        or a != s or group["failure"] is not None):
                    return unknown
                finished += 1
            tried += a
            succeeded += s
        if (source["groups_completed"] != finished or source["pages_attempted"] != tried
                or source["pages_succeeded"] != succeeded):
            return unknown
        if status != "running":
            actual = "success" if finished == len(expected) else ("partial" if succeeded else "failed")
            if status != actual:
                return unknown
        return {**unknown, "status": status,
                **{key: source[key] for key in (
                    "attempted_at", "completed_at", "successful_checked_at", *count_keys)}}
    except (KeyError, TypeError, ValueError, OverflowError):
        return unknown


def project_public_sources(documents: Mapping[str, Any]) -> dict[str, Any]:
    """Project allowlisted public documents into a fixed company/fact schema."""

    if not isinstance(documents, Mapping):
        raise PublicSourceError("public source set rejected")
    keys = set(documents.keys())
    if not keys.issubset(PUBLIC_SOURCE_FILES):
        raise PublicSourceError("public source set rejected")
    if any(not isinstance(documents[key], Mapping) for key in keys):
        raise PublicSourceError("public source set rejected")

    companies: dict[str, dict[str, Any]] = {}
    fact_keys: dict[str, set[tuple[Any, ...]]] = {}
    document_keys: dict[str, dict[str, dict[str, Any]]] = {}
    filing_updates: dict[tuple[str, str], dict[str, Any] | None] = {}

    container_fields = {
        "universe_search.json": "stocks",
        "stock_report_public.json": "stocks",
        "us_stock_report_public.json": "stocks",
        "public_disclosure_feed.json": "items",
        "us_disclosure_feed.json": "items",
        "kr_business_overview_public.json": "rows",
    }
    for filename in keys:
        # Presence is counted only after the file exposes its fixed top-level
        # record container.  Errors never include the filename or source value.
        if filename in container_fields:
            tuple(_validated_rows(documents[filename], container_fields[filename]))

    def register(
        row: Mapping[str, Any],
        *,
        default_market: str | None = None,
        ticker_hint: str | None = None,
    ) -> tuple[str, dict[str, Any]] | None:
        identity = _row_identity(
            row, default_market=default_market, ticker_hint=ticker_hint
        )
        if identity is None:
            return None
        market, ticker = identity
        raw_name = row.get("name")
        name = _safe_text(raw_name, 160) if raw_name not in (None, "") else None
        if name is None:
            name = _safe_text(row.get("name_ko"), 160)
        company_id = f"{market}:{ticker}"
        company = companies.get(company_id)
        if company is None:
            if name is None:
                return None
            company = {
                "id": company_id,
                "ticker": ticker,
                "market": market,
                "name": name,
                "sector": _sector(row),
                "facts": [],
                "documents": [],
            }
            companies[company_id] = company
            fact_keys[company_id] = set()
            document_keys[company_id] = {}
        elif company["sector"] is None:
            company["sector"] = _sector(row)
        return company_id, company

    universe = documents.get("universe_search.json")
    if isinstance(universe, Mapping):
        for hint, row in _validated_rows(universe, "stocks"):
            register(row, ticker_hint=hint)

    def append_disclosures(
        company_id: str,
        company: dict[str, Any],
        row: Mapping[str, Any],
        source: str,
    ) -> None:
        disclosures = row.get("disclosures")
        if disclosures is None:
            return
        if not isinstance(disclosures, list):
            raise PublicSourceError("public source shape rejected")
        for raw in disclosures:
            if not isinstance(raw, Mapping):
                raise PublicSourceError("public source shape rejected")
            projected = _disclosure(raw, source)
            if projected and projected["id"] not in document_keys[company_id]:
                document_keys[company_id][projected["id"]] = projected
                company["documents"].append(projected)
            elif projected and "filing" in projected:
                existing = document_keys[company_id][projected["id"]]
                if ("filing" not in existing
                        and all(existing.get(key) == projected[key]
                                for key in ("id", "url", "as_of", "kind", "source"))):
                    key = (company_id, projected["id"])
                    # Wait until every duplicate has been inspected: two valid
                    # but conflicting optional claims must not select a winner.
                    if key not in filing_updates:
                        filing_updates[key] = projected["filing"]
                    elif filing_updates[key] != projected["filing"]:
                        filing_updates[key] = None

    for filename, default_market, source in (
        ("stock_report_public.json", "KR", "DART"),
        ("us_stock_report_public.json", "US", "SEC"),
    ):
        document = documents.get(filename)
        if not isinstance(document, Mapping):
            continue
        for hint, row in _validated_rows(document, "stocks"):
            registered = register(row, default_market=default_market, ticker_hint=hint)
            if registered is None:
                continue
            company_id, company = registered
            for fact in (*_explicit_facts(row, default_market), *_series_facts(row, default_market, source)):
                key = tuple(fact[field] for field in PUBLIC_FACT_FIELDS)
                if key not in fact_keys[company_id]:
                    fact_keys[company_id].add(key)
                    company["facts"].append(fact)
            # Both report builders attach current public disclosures.  Keep
            # them as a sanitized fallback when a rotating feed is unavailable.
            append_disclosures(company_id, company, row, source)

    for filename, default_market, source in (
        ("public_disclosure_feed.json", "KR", "DART"),
        ("us_disclosure_feed.json", "US", "SEC"),
    ):
        document = documents.get(filename)
        if not isinstance(document, Mapping):
            continue
        for hint, row in _validated_rows(document, "items"):
            registered = register(row, default_market=default_market, ticker_hint=hint)
            if registered is None:
                continue
            company_id, company = registered
            append_disclosures(company_id, company, row, source)

    enriched_companies = set()
    for (company_id, identifier), filing in filing_updates.items():
        if filing is not None:
            # Prepared bases share nested documents across bundle revisions.
            # Replace only enriched objects; never write into a cached header.
            document_keys[company_id][identifier] = {
                **document_keys[company_id][identifier], "filing": filing}
            enriched_companies.add(company_id)
    for company_id in enriched_companies:
        company = companies[company_id]
        companies[company_id] = {**company, "documents": [
            document_keys[company_id][item["id"]] for item in company["documents"]]}
    result_companies = sorted(companies.values(), key=lambda company: company["id"])
    facts_projected = 0
    documents_projected = 0
    for company in result_companies:
        company["facts"].sort(
            key=lambda fact: (fact["metric"], fact["as_of"], fact["source"], fact["unit"])
        )
        company["documents"].sort(
            key=lambda item: (item["as_of"], item["id"]), reverse=True
        )
        facts_projected += len(company["facts"])
        documents_projected += len(company["documents"])

    collection = (_dart_source_collection(documents["public_disclosure_feed.json"])
                  if "public_disclosure_feed.json" in documents else None)
    loaded = len(keys)
    # This status reports fixed-source availability only.  It does not claim
    # complete company, fact, filing, market, or time-window coverage.
    if loaded == 0:
        status_value = "empty"
    elif loaded == len(PUBLIC_SOURCE_FILES):
        status_value = "complete"
    else:
        status_value = "partial"
    return {
        "companies": result_companies,
        "coverage": {
            "expected": len(PUBLIC_SOURCE_FILES),
            "available": loaded,
            "missing": len(PUBLIC_SOURCE_FILES) - loaded,
            "companies": len(result_companies),
            "facts": facts_projected,
            "documents": documents_projected,
            "status": status_value,
            **({"source_collection": {"public_disclosure_feed.json": collection}}
               if collection is not None else {}),
        },
    }


# Receipt scope is deliberately limited to these existing issuer containers.
# Other public artifacts retain their own projection/coverage contracts.
_COMPANY_COVERAGE_SOURCES = (
    ("universe_search.json", "stocks", None, None),
    ("stock_report_public.json", "stocks", "KR", "DART"),
    ("us_stock_report_public.json", "stocks", "US", "SEC"),
    ("public_disclosure_feed.json", "items", "KR", "DART"),
    ("us_disclosure_feed.json", "items", "US", "SEC"),
    ("kr_business_overview_public.json", "rows", "KR", "DART"),
)


def _coverage_row(row, filename, market, source):
    """Count retained payloads with existing guards, never certify their truth."""
    if filename == "universe_search.json":
        accepted = int(bool(_safe_text(row.get("name"), 160)
                            or _safe_text(row.get("name_ko"), 160)))
        return 1, accepted, [], []
    supplied = False
    inputs, accepted, publications, periods = 0, 0, set(), set()
    if filename.endswith("stock_report_public.json"):
        for field in ("facts", "fin_series"):
            raw = row.get(field)
            if raw is None:
                continue
            supplied = True
            if not isinstance(raw, (list, Mapping)) or field == "fin_series" and not isinstance(raw, list):
                raise PublicSourceError("public source shape rejected")
            if field == "facts":
                inputs += len(raw)
            else:
                for point in raw:
                    if not isinstance(point, Mapping):
                        inputs += 1
                    else:
                        inputs += max(1, sum(point.get(key) is not None for key in ("revenue", "op", "net")))
        facts = [*_explicit_facts(row, market), *_series_facts(row, market, source)]
        accepted += len(facts)
        for fact in facts:
            proof = fact.get("provenance", {})
            periods.add(proof.get("period_end", fact["as_of"]))
            filed = _as_of(proof.get("filed"))
            if filed:
                publications.add(filed)
    disclosures = row.get("disclosures")
    if disclosures is not None:
        supplied = True
        if not isinstance(disclosures, list):
            raise PublicSourceError("public source shape rejected")
        inputs += len(disclosures)
        for raw in disclosures:
            if not isinstance(raw, Mapping):
                raise PublicSourceError("public source shape rejected")
            document = _disclosure(raw, source)
            if document:
                accepted += 1
                publications.add(document["as_of"])
                report_date = document.get("filing", {}).get("report_date")
                if report_date is not None:
                    periods.add(report_date)
    return (inputs if supplied else None), accepted, sorted(publications), sorted(periods)



def _us_source_collection(document):
    """Read the existing SEC builder receipt; its clock is batch-scoped only."""
    unknown = {"status": "unknown", "attempted_at": None, "completed_at": None,
               "successful_checked_at": None}
    meta = document.get("_meta")
    if not isinstance(meta, Mapping) or "source_collection" not in meta:
        return None, {}
    value, coverage = meta["source_collection"], document.get("_coverage")
    try:
        if (not isinstance(value, Mapping) or not isinstance(coverage, Mapping)
                or value.get("endpoint") != "https://data.sec.gov/submissions/CIK{cik10}.json"
                or value.get("scope") != "submissions.filings.recent; excludes ticker-map request and historical files"
                or value.get("whole_market_coverage") is not False):
            return unknown, {}
        count_fields = ("requests", "requests_succeeded", "requests_failed", "reused_cik_tickers",
                        "universe_n", "processed_n", "empty_n", "unavailable_n",
                        "unresolved_n", "deferred_n")
        if any(type(value.get(key)) is not int or value[key] < 0 for key in count_fields):
            return unknown, {}
        fields = {"processed": "processed_n", "empty": "empty_n", "unavailable": "unavailable_n",
                  "unresolved": "unresolved_n", "unprocessed": "deferred_n",
                  "carry_forward": None}
        groups = {}
        for name, count in fields.items():
            tickers = coverage.get(name + "_tickers")
            if (not isinstance(tickers, list)
                    or any(_ticker(ticker, "US") is None for ticker in tickers)
                    or len(set(tickers)) != len(tickers)
                    or count is not None and len(tickers) != value[count]):
                return unknown, {}
            groups[name] = set(tickers)
        partition = [groups[name] for name in ("processed", "unavailable", "unresolved", "unprocessed")]
        if (sum(len(group) for group in partition) != len(set().union(*partition))
                or sum(len(group) for group in partition) != value["universe_n"]
                or coverage.get("universe_n") != value["universe_n"]
                or not groups["empty"].issubset(groups["processed"])
                or groups["carry_forward"] & groups["processed"]
                or value["requests"] != value["requests_succeeded"] + value["requests_failed"]
                or value["requests"] + value["reused_cik_tickers"] != value["processed_n"] + value["unavailable_n"]
                or value["requests_succeeded"] > value["processed_n"]
                or value["requests_failed"] > value["unavailable_n"]):
            return unknown, {}
        complete = value["universe_n"] > 0 and value["processed_n"] == value["universe_n"]
        status = ("success" if complete else "partial" if value["processed_n"] or value["deferred_n"]
                  else "error" if value["universe_n"] else "unknown")
        if type(value.get("universe_complete")) is not bool or value["universe_complete"] != complete or value.get("status") != status:
            return unknown, {}
        now = datetime.now(timezone.utc)

        def timestamp(raw):
            if _generated_at(raw) is None:
                raise ValueError
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed > now:
                raise ValueError
            return parsed

        completed = timestamp(value["completed_at"])
        if value["requests"]:
            if timestamp(value["attempted_at"]) > completed:
                return unknown, {}
        elif value["attempted_at"] is not None:
            return unknown, {}
        if complete:
            if timestamp(value["successful_checked_at"]) != completed:
                return unknown, {}
        elif value["successful_checked_at"] is not None:
            return unknown, {}
        return {key: value[key] for key in unknown}, groups
    except (KeyError, TypeError, ValueError, OverflowError):
        return unknown, {}


def project_public_source_coverage(
    documents: Mapping[str, Any], selected_company_ids: Iterable[str]
) -> dict[str, Any]:
    """Describe selected issuer payloads in supplied artifacts, with no I/O.

    available means a payload survived existing projection guards, not that its
    financial values/relationships were independently verified. empty requires
    an explicit empty company payload. Missing issuer rows remain not-collected
    in this loaded scope, never evidence that the issuer has no filings.
    Observation time is only copied from validated collection evidence; artifact
    generation, filing dates and fiscal dates never stand in for observation.
    This helper neither registers issuers nor changes the legacy projection.
    Each of the six source containers is visited once; only selected payloads
    are validated/projected. SEC batch-check timestamps remain collection
    metadata and never become a selected issuer's observed_at.
    """
    if not isinstance(documents, Mapping) or not set(documents).issubset(PUBLIC_SOURCE_FILES):
        raise PublicSourceError("public source set rejected")
    if isinstance(selected_company_ids, (str, bytes, Mapping)):
        raise PublicSourceError("public coverage selection rejected")
    try:
        identifiers = set()
        for index, identifier in enumerate(selected_company_ids):
            if index >= 30 or not isinstance(identifier, str):
                raise ValueError
            market, separator, ticker = identifier.partition(":")
            if separator != ":" or market not in ("KR", "US") or _ticker(ticker, market) is None:
                raise ValueError
            identifiers.add(identifier)
    except (TypeError, ValueError):
        raise PublicSourceError("public coverage selection rejected") from None

    receipts = []
    for filename, field, default_market, source in _COMPANY_COVERAGE_SOURCES:
        loaded = filename in documents
        document = documents.get(filename)
        meta = document.get("_meta") if isinstance(document, Mapping) else None
        generated = _generated_at(meta.get("generated_at")) if isinstance(meta, Mapping) else None
        collection = (_dart_source_collection(document)
                      if filename == "public_disclosure_feed.json" and isinstance(document, Mapping) else None)
        us_collection, us_groups = (_us_source_collection(document)
                                   if filename == "us_disclosure_feed.json" and isinstance(document, Mapping)
                                   else (None, {}))
        rows, invalid = {}, False
        if loaded:
            try:
                if not isinstance(document, Mapping):
                    raise PublicSourceError("public source shape rejected")
                if filename == "kr_business_overview_public.json":
                    raw_rows = document.get("rows")
                    if (not isinstance(raw_rows, Mapping) or not isinstance(meta, Mapping)
                            or generated is None or type(meta.get("count")) is not int
                            or meta["count"] != len(raw_rows)):
                        raise PublicSourceError("public source metadata rejected")
                value = document.get(field)
                if isinstance(value, Mapping):
                    entries = value.items()
                elif isinstance(value, list):
                    entries = ((None, row) for row in value)
                else:
                    raise PublicSourceError("public source shape rejected")
                # Combine shape validation and identity selection in one pass,
                # including invalid unselected rows, without building a catalog.
                for hint, row in entries:
                    if (not isinstance(row, Mapping)
                            or isinstance(value, Mapping) and not isinstance(hint, str)):
                        raise PublicSourceError("public source shape rejected")
                    identity = _row_identity(row, default_market=default_market, ticker_hint=hint)
                    if identity is not None:
                        identifier = ":".join(identity)
                        if identifier in identifiers:
                            rows.setdefault(identifier, []).append((hint, row))
            except PublicSourceError:
                invalid = True
        for identifier in sorted(identifiers):
            market, ticker = identifier.split(":")
            if default_market is not None and market != default_market:
                continue
            matches = rows.get(identifier, [])
            receipt = {
                "company_id": identifier, "source_file": filename,
                "status": "not-collected",
                "reason": "no-company-row-in-loaded-scope" if loaded else "source-not-loaded",
                "matched_rows": len(matches), "input_records": 0, "accepted_records": 0,
                "publication_dates": [], "data_dates": [], "observed_at": None,
                "artifact_generated_at": generated,
            }
            if invalid:
                receipt.update(status="error", reason="source-shape-rejected")
            elif matches:
                inputs, accepted, supplied, publications, periods = 0, 0, False, set(), set()
                truncated = False
                try:
                    for hint, row in matches:
                        if filename == "kr_business_overview_public.json":
                            # The original metadata/container was checked above;
                            # reuse the row validator without projecting other issuers.
                            projected = project_public_business_overviews({
                                filename: {"_meta": {**(meta if isinstance(meta, Mapping) else {}),
                                                     "count": 1}, "rows": {ticker: row}}})
                            n, kept = 1, len(projected["rows"])
                            filed = [entry["source"]["as_of"] for entry in projected["rows"]]
                            dates = [entry["fiscal_year"] for entry in projected["rows"]]
                            truncated = truncated or any(entry["truncated"] for entry in projected["rows"])
                        else:
                            n, kept, filed, dates = _coverage_row(row, filename, market, source)
                        supplied = supplied or n is not None
                        inputs += n or 0
                        accepted += kept
                        publications.update(filed)
                        periods.update(dates)
                    receipt.update(input_records=inputs, accepted_records=accepted,
                                   publication_dates=sorted(publications), data_dates=sorted(periods))
                    if accepted:
                        receipt.update(status="partial" if accepted < inputs or truncated else "available",
                                       reason=("payload-partly-rejected" if accepted < inputs else
                                               "payload-truncated" if truncated else "payload-present"))
                    elif inputs:
                        receipt.update(status="partial", reason="payload-rejected")
                    elif supplied:
                        receipt.update(status="empty", reason="explicit-empty-company-payload")
                    else:
                        receipt["reason"] = "company-payload-not-supplied"
                except PublicSourceError:
                    receipt.update(status="error", reason="company-payload-rejected")
            if collection is not None:
                receipt["collection_status"] = collection["status"]
                receipt["collection_scope"] = "feed-query-groups"
                receipt["observed_at"] = collection["successful_checked_at"]
                receipt["collection_attempted_at"] = collection["attempted_at"]
                receipt["collection_completed_at"] = collection["completed_at"]
                if receipt["status"] != "error" and collection["status"] in ("partial", "running", "failed"):
                    receipt.update(
                        status="error" if collection["status"] == "failed" else "partial",
                        reason="feed-collection-" + collection["status"])
            if us_collection is not None:
                receipt.update(
                    collection_status=us_collection["status"],
                    collection_scope="submissions.filings.recent",
                    collection_attempted_at=us_collection["attempted_at"],
                    collection_completed_at=us_collection["completed_at"],
                    collection_checked_at=us_collection["successful_checked_at"],
                    issuer_collection_status="unknown")
                issuer_status = next((name for name in
                    ("empty", "processed", "unavailable", "unresolved", "unprocessed", "carry_forward")
                    if ticker in us_groups.get(name, ())), None)
                if issuer_status is not None:
                    receipt["issuer_collection_status"] = issuer_status
                if receipt["status"] != "error":
                    if issuer_status == "empty":
                        if receipt["accepted_records"]:
                            receipt.update(status="error", reason="collection-payload-conflict")
                        else:
                            receipt.update(status="empty", reason="checked-empty-recent-filings")
                    elif issuer_status == "unavailable":
                        receipt.update(status="error", reason="issuer-collection-failed")
                    elif issuer_status == "unresolved":
                        receipt.update(status="not-collected", reason="issuer-identity-unresolved")
                    elif issuer_status in ("unprocessed", "carry_forward"):
                        receipt.update(status="partial" if receipt["accepted_records"] else "not-collected",
                                       reason="issuer-deferred" if issuer_status == "unprocessed"
                                       else "retained-payload-not-checked")
                    elif issuer_status == "processed" and not matches:
                        receipt.update(status="partial", reason="checked-issuer-payload-missing")
            receipts.append(receipt)
    assessed = {entry[0] for entry in _COMPANY_COVERAGE_SOURCES}
    return {
        "scope": "selected-companies-in-loaded-sources",
        "selected_companies": len(identifiers),
        "loaded_sources": sorted(documents),
        "assessed_sources": sorted(assessed),
        "unassessed_loaded_sources": sorted(set(documents) - assessed),
        "receipt_count": len(receipts),
        "status_counts": {status: sum(row["status"] == status for row in receipts)
                          for status in ("available", "empty", "not-collected", "partial", "error")},
        "accuracy_verified": False,
        "receipts": receipts,
    }


def _generated_at(value: Any) -> str | None:
    if (not isinstance(value, str) or len(value) > 64
            or not re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
                r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})?", value, re.ASCII
            )):
        return None
    try:
        from datetime import datetime

        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value


def project_public_business_overviews(documents: Mapping[str, Any]) -> dict[str, Any]:
    """Project filing excerpts as bounded source candidates, never companies."""

    if not isinstance(documents, Mapping) or not set(documents).issubset(PUBLIC_SOURCE_FILES):
        raise PublicSourceError("public source set rejected")
    if "kr_business_overview_public.json" not in documents:
        return {
            "rows": [],
            "coverage": {
                "status": "not-supplied", "input": 0, "accepted": 0,
                "rejected": 0, "missing": True, "generated_at": None,
            },
        }
    document = documents["kr_business_overview_public.json"]
    if not isinstance(document, Mapping):
        raise PublicSourceError("public source shape rejected")
    meta = document.get("_meta")
    raw_rows = document.get("rows")
    if (not isinstance(meta, Mapping) or not isinstance(raw_rows, Mapping)
            or any(not isinstance(ticker, str) or not isinstance(row, Mapping)
                   for ticker, row in raw_rows.items())):
        raise PublicSourceError("public source shape rejected")
    generated_at = _generated_at(meta.get("generated_at"))
    count = meta.get("count")
    if generated_at is None or isinstance(count, bool) or not isinstance(count, int) or count != len(raw_rows):
        raise PublicSourceError("public source metadata rejected")

    projected: list[dict[str, Any]] = []
    rejected = 0
    for ticker, row in raw_rows.items():
        name = _safe_text(row.get("name"), 160)
        original_text = row.get("text")
        chars = row.get("chars")
        text = original_text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ") if isinstance(original_text, str) else None
        safe_text = safe_public_text(text, 600) if text is not None else None
        fiscal_year = row.get("fiscal_year")
        filed_at = row.get("filed_at")
        report = _safe_text(row.get("report"), 240)
        url = row.get("url")
        truncated = row.get("truncated")
        receipt_match = re.fullmatch(
            r"https://dart\.fss\.or\.kr/dsaf001/main\.do\?rcpNo=([0-9]{14})",
            url if isinstance(url, str) else "", re.ASCII,
        )
        filed_date = None
        if isinstance(filed_at, str) and re.fullmatch(r"[0-9]{8}", filed_at, re.ASCII):
            try:
                filed_date = date(int(filed_at[:4]), int(filed_at[4:6]), int(filed_at[6:8]))
            except ValueError:
                pass
        if not (
            _KR_TICKER_RE.fullmatch(ticker) and name and isinstance(original_text, str)
            and len(original_text) <= 600 and isinstance(chars, int) and not isinstance(chars, bool)
            and chars == len(original_text) and safe_text and isinstance(fiscal_year, str)
            and re.fullmatch(r"[0-9]{4}", fiscal_year, re.ASCII)
            and filed_date is not None and report and type(truncated) is bool and receipt_match
        ):
            rejected += 1
            continue
        receipt = receipt_match.group(1)
        issuer = f"KR:{ticker}"
        projected.append({
            "issuer_id": issuer,
            "name": name,
            "text": safe_text,
            "truncated": truncated,
            "fiscal_year": fiscal_year,
            "source": {
                "id": f"source:dart:{receipt}",
                "kind": "dart-filing-excerpt",
                "receipt_no": receipt,
                "as_of": filed_date.isoformat(),
                "report_name": report,
                "url": url,
                "document_issuer": issuer,
            },
        })
    projected.sort(key=lambda row: row["issuer_id"])
    accepted = len(projected)
    return {
        "rows": projected,
        "coverage": {
            "status": "complete" if rejected == 0 else "partial",
            "input": len(raw_rows),
            "accepted": accepted,
            "rejected": rejected,
            "missing": False,
            "generated_at": generated_at,
        },
    }
