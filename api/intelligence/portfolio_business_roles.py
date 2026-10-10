"""Issuer-qualified business-report counterparties from public excerpts.

No IO, fuzzy aliases, model calls or inferred contracts. A named customer or
purchase source at the reported fiscal period is not current exposure, a
contract, a common economic event, a capital weight or a price direction.
"""
from collections import Counter
from calendar import monthrange
from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json
import re

from .portfolio_filing_excerpts import _legal_name
from .portfolio_public_sources import safe_public_text


_LIST = re.compile(
    r"당사의\s*(?:주요\s*)?(?P<label>매출처|고객사|고객|구매처|공급업체)"
    r"(?:는|은|으로는|로는)\s*(?P<names>.+?)(?:\s*등)?"
    r"(?:입니다|(?:이|가)\s*있습니다)\."
)
_PURCHASE = re.compile(
    r"당사의\s*(?:주요\s*)?원재료는\s*.+?이며\s*"
    r"(?P<names>.+?)(?:\s*등)?에서\s*(?:안정적으로\s*)?"
    r"구매하고\s*있습니다\."
)
_COMPOUND_LIST = re.compile(
    r"당사의\s*(?:주요\s*)?(?P<label>매출처|고객사|고객|구매처|공급업체)"
    r"(?:는|은|으로는|로는)\s*(?P<names>.+?)(?:\s*등)?\s*(?:이)?며,\s*(?P<tail>.+)\."
)
_AS_CUSTOMER = re.compile(
    r"당사는\s*(?P<names>.+?)(?:\s*등)?(?:을|를)\s*(?:주요\s*)?"
    r"(?P<label>고객사|고객|매출처)(?:으로|로)\s*"
    r"(?:두고\s*(?:거래하고\s*)?|확보하고\s*)있습니다\."
)
_DELIVERY = re.compile(
    r"당사는\s*(?:(?:(?:국내|해외|국내외)\s*)?(?:주요\s*)?"
    r"[A-Za-z가-힣]+(?:\s+[A-Za-z가-힣]+)?\s*(?:제조사|업체)인\s*)?"
    r"(?P<names>.+?)(?:\s*등)?에\s*"
    r"(?P<product>[A-Za-z0-9가-힣\s·ㆍ()+/\-]+?)(?:을|를)\s*"
    r"(?:공급|납품)하고\s*(?:있습니다|있으며,\s*(?P<tail>.+))\."
)
_FROM_SUPPLIER = re.compile(
    r"(?:[●•]\s*)?당사는\s*"
    r"(?:[A-Za-z0-9가-힣\s·ㆍ(),/\-]{1,120}(?:을|를|하여)\s+)?"
    r"(?P<names>[A-Za-z0-9가-힣&()+\-\s、/,·ㆍ]+?)(?:\s*등)?로부터\s*"
    r"(?:구입(?:\([A-Za-z0-9가-힣\s·ㆍ/\-]{1,40}\))?하고\s*"
    r"(?:있습니다|있으며,\s*(?P<tail>.+))|"
    r"(?:(?P<supply_product>[A-Za-z0-9가-힣\s·ㆍ()+/\-]{1,80}?)(?:을|를)\s*)?"
    r"공급받아\s*(?P<received_tail>.+))\."
)
_UNRESOLVED_SCOPE = re.compile(
    r"예정|계획|추진|가능|가정|예시|예를|정의|경쟁|제품명|브랜드|"
    r"타사|과거|이전|(?<![A-Za-z0-9가-힣])전기(?=$|\s|말|초|대비|기준|회계|분기|에는|의|와|에)|전년|작년|향후|"
    r"않|아니|아닙|없|중단|종료|해지|취소|철회|중지|미확인|제외|만약|조건|경우|하지만|그러나|반면|실제로|여부|[\"'“”‘’]"
)
_OTHER_SUBJECT = re.compile(r"종속|연결|그룹|계열")
_SEPARATOR = re.compile(r"[,、/·ㆍ]|\s+및\s+|(?<=\))(?:와|과)\s*|(?:와|과)(?=\s)")
_BARE_DELIVERY_NAME = re.compile(r"[A-Za-z0-9가-힣&()+\-\s]{1,80}")
_NAME_CONTEXT = re.compile(
    r"(?:에서|으로|하여|위해|통해|하고|하며|을|를)(?:\s|$)|(?:^|\s)(?:현재|경우|것|대한)(?:\s|$)"
)
_PRODUCT_CONTEXT = re.compile(r"공급|납품|구매|매입|받|하여|통해|위해|에서|에게|(?:을|를)(?:\s|$)")
_ANNUAL = re.compile(r"(?:\[(?:기재정정|첨부정정|첨부추가)\])*사업보고서 \(([0-9]{4})\.(0[1-9]|1[0-2])\)")
_ID = re.compile(r"(?:KR:[0-9]{6}|US:[A-Z][A-Z0-9]{0,9}(?:[.-][A-Z0-9]{1,2})?)\Z", re.ASCII)
_GENERIC_NAME = re.compile(
    r"(?:국내및해외|국내외|국내|해외|글로벌|주요|대형|중소|기타|불특정|다수|일반|각종)*"
    r"(?:기업|고객사?|거래처|매출처|구매처|유통업체|공급업체|업체|회사)"
)


def _revision(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _names(companies):
    by_id, aliases = {}, {}
    for company in companies:
        if type(company) is not dict or not _ID.fullmatch(str(company.get("id", ""))):
            continue
        primary = safe_public_text(company.get("name"), 160)
        if primary is None:
            continue
        by_id[company["id"]] = company
        names = company.get("source_names", [primary])
        # Use only the existing public, bound report-name alias contract.
        if type(names) is not list or not 1 <= len(names) <= 4 or names[0] != primary:
            names = [primary]
        for name in names:
            if safe_public_text(name, 160) is not None:
                key = _legal_name(name).casefold()
                if (len(key) >= 2 and any(char.isalpha() for char in key)
                        and _GENERIC_NAME.fullmatch(key) is None):
                    aliases.setdefault(key, set()).add(company["id"])
    return by_id, aliases


def _source(row, by_id, aliases):
    if type(row) is not dict:
        return None
    issuer = row.get("issuer_id")
    raw = row.get("source")
    text = row.get("text")
    if (issuer not in by_id or type(raw) is not dict
            or safe_public_text(row.get("name"), 160) is None
            or issuer not in aliases.get(_legal_name(row["name"]).casefold(), set())
            or safe_public_text(text, 600) is None or type(row.get("truncated")) is not bool
            or raw.get("kind") != "dart-filing-excerpt" or raw.get("document_issuer") != issuer):
        return None
    receipt, stamp, title = (raw.get(key) for key in ("receipt_no", "as_of", "report_name"))
    if (type(receipt) is not str or not re.fullmatch(r"[0-9]{14}", receipt, re.ASCII)
            or type(stamp) is not str or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", stamp, re.ASCII)
            or receipt[:8] != stamp.replace("-", "")
            or raw.get("id") != "source:dart:" + receipt
            or raw.get("url") != "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + receipt
            or type(title) is not str or safe_public_text(title, 240) is None):
        return None
    report = _ANNUAL.fullmatch(title)
    if report is None or row.get("fiscal_year") != report[1]:
        return None
    try:
        filed = date.fromisoformat(stamp)
        year, month = int(report[1]), int(report[2])
        if (filed < date(year, month, monthrange(year, month)[1])
                or filed > datetime.now(timezone.utc).date()):
            return None
    except ValueError:
        return None
    source = {key: raw[key] for key in ("id", "kind", "receipt_no", "as_of", "report_name", "url", "document_issuer")}
    source["artifact_observed_at"] = None
    source["revision"] = _revision(source)
    return source


def index_business_roles(business, company_catalog):
    """Index complete explicit issuer-owned statements once per public bundle.

    Exact list entries, not substrings, resolve counterparties. Full stops are
    required even when the source excerpt is truncated. Other text remains in
    the existing co-mention/market-context contracts rather than being promoted.
    """
    rows = business.get("rows", []) if type(business) is dict else []
    by_id, aliases = _names(company_catalog)
    relations, by_company, reasons = {}, {}, Counter()
    candidates, unresolved = 0, 0
    for row in rows:
        source = _source(row, by_id, aliases)
        if source is None:
            reasons["source-or-issuer-not-bound"] += 1
            continue
        issuer, text = row["issuer_id"], row["text"]
        # A grammar match may not silently start in the middle of an assertion.
        # Paragraph breaks are already normalized by the public excerpt gate.
        for sentence in re.finditer(r"[^.!?]*[.!?]", text):
            raw_quote = sentence.group()
            quote = raw_quote.strip()
            parsed = (_COMPOUND_LIST.fullmatch(quote) or _AS_CUSTOMER.fullmatch(quote) or _DELIVERY.fullmatch(quote)
                      or _LIST.fullmatch(quote) or _PURCHASE.fullmatch(quote)
                      or _FROM_SUPPLIER.fullmatch(quote))
            if parsed is None:
                continue
            candidates += 1
            # Keep the entire sentence as evidence. Only an explicit first
            # clause owns the role; an unrelated subsidiary in the continuation
            # is not its subject. Negation/conditions anywhere still withhold it.
            tail_key = "received_tail" if parsed.groupdict().get("received_tail") else "tail"
            tail = parsed.groupdict().get(tail_key)
            assertion = quote[:parsed.start(tail_key)] if tail else quote
            if _UNRESOLVED_SCOPE.search(quote) or _OTHER_SUBJECT.search(assertion):
                reasons["uncertain-or-different-subject"] += 1
                continue
            delivery = parsed.re is _DELIVERY
            role = ("customer" if delivery or parsed.groupdict().get("label") in {"매출처", "고객사", "고객"} else "supplier")
            names = [name.strip() for name in _SEPARATOR.split(parsed["names"]) if name.strip()]
            if not names or len(names) > 12:
                reasons["counterparty-list-not-bounded"] += 1
                continue
            if delivery or parsed.re in (_FROM_SUPPLIER, _AS_CUSTOMER):
                # An exact first counterparty anchors the list. A prose prefix
                # that happens to contain a later known name cannot establish a
                # sale. Unresolved *later* bare names stay unresolved, not guessed.
                first = aliases.get(_legal_name(names[0]).casefold(), set())
                product = parsed.groupdict().get("product") or parsed.groupdict().get("supply_product")
                product = product.strip() if product else None
                if (len(first) != 1 or issuer in first
                        or any(not _BARE_DELIVERY_NAME.fullmatch(name) or _NAME_CONTEXT.search(name) for name in names)
                        or (delivery and not product)
                        or (product and (len(product) > 80 or _PRODUCT_CONTEXT.search(product)))):
                    reason = ("delivery-clause-not-bound" if delivery else
                              "customer-clause-not-bound" if parsed.re is _AS_CUSTOMER else
                              "supplier-clause-not-bound")
                    reasons[reason] += 1
                    continue
            for raw_name in names:
                targets = aliases.get(_legal_name(raw_name).casefold(), set())
                if len(targets) != 1 or issuer in targets:
                    unresolved += 1
                    continue
                target = next(iter(targets))
                stable_id = "relation:business-role:" + _revision([issuer, role, target])[:16]
                if stable_id in relations:
                    continue  # One earliest complete statement per same-filing role/pair.
                start = sentence.start() + len(raw_quote) - len(raw_quote.lstrip())
                evidence = {"role": role, "raw_name": raw_name, "quote": quote,
                            "char_start": start, "char_end": start + len(quote),
                            "source_field": "business_overview", "field_sha256": hashlib.sha256(text.encode()).hexdigest(),
                            "fiscal_year": row["fiscal_year"], "published_excerpt_truncated": row["truncated"]}
                relation = {"stable_id": stable_id, "type": "reported-business-counterparty",
                            "status": "accepted_reported", "verification": "reported-business-excerpt",
                            "snapshot_scope": "reported-fiscal-year-not-current",
                            "label": "보고서상 매출처" if role == "customer" else "보고서상 공급처",
                            "participants": [{"id": issuer, "role": "document_issuer", "name": by_id[issuer]["name"]},
                                             {"id": target, "role": "reported_" + role}],
                            "source": source, "evidence": evidence}
                # Display names do not make an unchanged source fact unread.
                relation["revision"] = _revision({**relation, "participants": [
                    {"id": person["id"], "role": person["role"]} for person in relation["participants"]
                ]})
                relations[stable_id] = relation
                for identifier in (issuer, target):
                    by_company.setdefault(identifier, []).append(stable_id)
    return {"relations": sorted(relations.values(), key=lambda row: row["stable_id"]),
            "by_company": by_company,
            "coverage": {"input": len(rows), "candidate_sentences": candidates,
                         "relationships": len(relations), "unresolved_names": unresolved,
                         "rejection_reasons": dict(reasons)}}


def attach_business_relationships(projection, index, positions):
    if projection is None or not index["coverage"]["input"]:
        return projection
    selected = {f"{row['market']}:{row['ticker']}" for row in positions}
    ids = {key for identifier in selected for key in index["by_company"].get(identifier, [])}
    result = deepcopy(projection)
    existing = {row["stable_id"] for row in result["relationships"]}
    sources = {row["id"]: row for row in result["sources"]}
    for row in index["relations"]:
        if row["stable_id"] in ids and row["stable_id"] not in existing:
            result["relationships"].append(deepcopy(row))
            sources.setdefault(row["source"]["id"], deepcopy(row["source"]))
    result["sources"] = list(sources.values())
    result["coverage"]["business_roles"] = deepcopy(index["coverage"])
    return result
