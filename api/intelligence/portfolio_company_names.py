"""Exact public report-name aliases for Korean catalog companies."""
from __future__ import annotations

from copy import deepcopy
import unicodedata
from collections.abc import Mapping

from .portfolio_public_sources import (
    PublicSourceError,
    _row_identity,
    _validated_rows,
    safe_public_text,
)


_MAX_SOURCE_NAMES = 4


def _name_key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def add_public_company_names(documents, company_catalog):
    """Return a copied catalog with unique, exact-ticker report names only.

    No translation, fuzzy matching, or input-specific selection is performed.
    A report-name disagreement for one ticker, or a global name collision,
    suppresses that alias rather than replacing the catalog's primary name.
    """
    if not isinstance(documents, Mapping) or not isinstance(company_catalog, list):
        raise PublicSourceError("public company names input rejected")
    catalog = deepcopy(company_catalog)
    for company in catalog:
        if isinstance(company, dict):
            company.pop("source_names", None)
            primary = company.get("name")
            if safe_public_text(primary, 160) is not None:
                # The consumer relies on this first slot to validate against
                # the catalog's authoritative display name.
                company["source_names"] = [primary]
    report = documents.get("stock_report_public.json")
    if report is None:
        return catalog
    if not isinstance(report, Mapping):
        raise PublicSourceError("public company names source rejected")

    company_by_id = {}
    primary_owners = {}
    for company in catalog:
        if not isinstance(company, dict):
            continue
        primary = company.get("name")
        identifier = company.get("id")
        if isinstance(identifier, str) and isinstance(primary, str) and primary.strip():
            primary_owners.setdefault(_name_key(primary), set()).add(identifier)
        ticker = company.get("ticker")
        if (company.get("market") != "KR" or not isinstance(ticker, str)
                or identifier != f"KR:{ticker}"):
            continue
        company_by_id[identifier] = company

    ticker_names = {}
    for hint, row in _validated_rows(report, "stocks"):
        identity = _row_identity(row, ticker_hint=hint)
        if identity is None or identity[0] != "KR":
            continue
        ticker = identity[1]
        if hint is not None and hint != ticker:
            continue
        name = safe_public_text(row.get("name"), 160)
        identifier = f"KR:{ticker}"
        if name is None or identifier not in company_by_id:
            continue
        ticker_names.setdefault(identifier, set()).add(name)

    # Conflicting spellings on a single ticker are not arbitrarily ranked.
    candidates = {
        identifier: sorted(names)[0]
        for identifier, names in ticker_names.items()
        if len({_name_key(name) for name in names}) == 1
    }
    owners = {key: set(value) for key, value in primary_owners.items()}
    for identifier, name in candidates.items():
        owners.setdefault(_name_key(name), set()).add(identifier)

    for identifier, name in candidates.items():
        key = _name_key(name)
        if len(owners[key]) != 1:
            continue
        company = company_by_id[identifier]
        primary = company.get("name")
        if isinstance(primary, str) and _name_key(primary) == key:
            continue
        if safe_public_text(primary, 160) is not None:
            company["source_names"] = [primary, name][:_MAX_SOURCE_NAMES]
    return catalog


def public_news_name_catalog(documents, company_catalog):
    """Return a separate news-only {id, name} catalog from bound public rows.

    Only exact declared name_ko values are added. Source-local disagreements
    withhold that source's aliases; different sources may declare different
    names. Keep cross-company owners for the existing news index to reject
    ambiguous names and enforce its three-character minimum. Legal-party
    source_names and the original company catalog are never changed.
    """
    if not isinstance(documents, Mapping) or not isinstance(company_catalog, list):
        raise PublicSourceError("public news names input rejected")
    primaries = {}
    for company in company_catalog:
        if not isinstance(company, Mapping) or company.get("market") not in ("KR", "US"):
            continue
        identity = _row_identity(company)
        primary = safe_public_text(company.get("name"), 160)
        identifier = company.get("id")
        if (identity is None or identifier != f"{identity[0]}:{identity[1]}" or primary is None
                or safe_public_text(_name_key(primary), 160) is None):
            continue
        primaries.setdefault(identifier, set()).add(primary)
    bound = {identifier: min(names) for identifier, names in primaries.items()
             if len({_name_key(name) for name in names}) == 1}
    by_ticker = {identifier.split(":", 1)[1]: identifier for identifier in bound}
    entries = {(identifier, name) for identifier, name in bound.items()}
    for filename, default_market in (
        ("universe_search.json", None), ("us_stock_report_public.json", "US"),
    ):
        document = documents.get(filename)
        if document is None:
            continue
        if not isinstance(document, Mapping):
            raise PublicSourceError("public news names source rejected")
        aliases, blocked = {}, set()
        for hint, row in _validated_rows(document, "stocks"):
            # Track contradictory declarations within this source rather than
            # silently retaining a second, apparently valid row for that ticker.
            claimed = {by_ticker[value] for value in (hint, row.get("ticker"))
                       if isinstance(value, str) and value in by_ticker}
            identity = _row_identity(row, default_market=default_market, ticker_hint=hint)
            if (identity is None or (default_market is not None and identity[0] != default_market)
                    or (hint is not None and hint != identity[1])):
                blocked.update(claimed)
                continue
            identifier = f"{identity[0]}:{identity[1]}"
            if identifier not in bound:
                continue
            primary = safe_public_text(row.get("name"), 160)
            localized = row.get("name_ko")
            alias = safe_public_text(localized, 160) if localized not in (None, "") else None
            if alias is not None and safe_public_text(_name_key(alias), 160) is None:
                alias = None
            if (primary is None or _name_key(primary) != _name_key(bound[identifier])
                    or (localized not in (None, "") and alias is None)):
                blocked.add(identifier)
                continue
            if alias is not None:
                aliases.setdefault(identifier, set()).add(alias)
        for identifier, names in aliases.items():
            if identifier in blocked or len({_name_key(name) for name in names}) != 1:
                continue
            alias = min(names)
            if _name_key(alias) != _name_key(bound[identifier]):
                entries.add((identifier, alias))
    return [{"id": identifier, "name": name} for identifier, name in sorted(entries)]
