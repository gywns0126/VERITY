"""Closed source excerpts from locally retained public filings; no I/O.

Report-time statements are not current holdings, impact direction, a market
benchmark or a verified common economic event. Raw operator caches never enter
the consumer; only this small, explicit projection does.
"""
from copy import deepcopy
from datetime import date
import hashlib
import json
import re
import unicodedata

from .portfolio_public_sources import safe_public_text
from .portfolio_parent_excerpts import extract_related_party_parent_rows
from .portfolio_rate_excerpts import extract_interest_rate_excerpts


FIELDS = {"schema", "receipt_no", "issuer_id", "issuer_name", "corp_code",
          "filed_on", "report_name", "report_type", "request_year", "excerpts"}
QUOTE_FIELDS = {"role", "quote", "char_start", "char_end", "source_field", "field_sha256"}
MAX_RECORDS = 1000


def _text(value, limit):
    if not isinstance(value, str) or safe_public_text(" ".join(value.split()), limit) is None:
        raise ValueError("filing-excerpt-text-rejected")
    if len(value) > limit or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", value):
        raise ValueError("filing-excerpt-text-rejected")
    return value


def _pattern(value, pattern):
    if type(value) is not str or not re.fullmatch(pattern, value, re.ASCII):
        raise ValueError("filing-excerpt-identity-rejected")
    return value


def validate_filing_excerpts(record):
    if type(record) is not dict or set(record) != FIELDS or record.get("schema") != 1:
        raise ValueError("filing-excerpt-shape-rejected")
    _pattern(record["receipt_no"], r"[0-9]{14}")
    _pattern(record["issuer_id"], r"KR:[0-9]{6}")
    _pattern(record["corp_code"], r"[0-9]{8}")
    _pattern(record["request_year"], r"[0-9]{4}")
    _pattern(record["filed_on"], r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
    date.fromisoformat(record["filed_on"])
    _text(record["issuer_name"], 160)
    title = _text(record["report_name"], 240)
    # Cache request year is kept separately; fiscal period comes from the title.
    if record["report_type"] != "A001" or not re.fullmatch(
            r"(?:\[(?:기재정정|첨부정정|첨부추가)\])*사업보고서 \([0-9]{4}\.(?:0[1-9]|1[0-2])\)", title):
        raise ValueError("filing-excerpt-report-rejected")
    rows = record["excerpts"]
    if type(rows) is not list or not 1 <= len(rows) <= 3:
        raise ValueError("filing-excerpt-count-rejected")
    seen = set()
    for row in rows:
        if type(row) is not dict:
            raise ValueError("filing-excerpt-shape-rejected")
        parent = row.get("role") == "reported-parent"
        expected = QUOTE_FIELDS | ({"raw_name", "as_of_phrase"} if parent else set())
        if set(row) != expected or row.get("role") not in {"reported-parent", "floating-rate-borrowing"}:
            raise ValueError("filing-excerpt-role-rejected")
        quote = _text(row["quote"], 600)
        start, end = row["char_start"], row["char_end"]
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= (30000 if parent else 60000) or end - start != len(quote):
            raise ValueError("filing-excerpt-offset-rejected")
        _pattern(row["field_sha256"], r"[0-9a-f]{64}")
        if row["source_field"] != ("related_party_text" if parent else "raw_text"):
            raise ValueError("filing-excerpt-field-rejected")
        if row["role"] in seen:
            raise ValueError("filing-excerpt-duplicate-role")
        seen.add(row["role"])
        # Re-run the narrow source grammar before any consumer promotion.
        parsed = (extract_related_party_parent_rows(quote) if parent else extract_interest_rate_excerpts(quote))
        if not any(candidate["quote"] == quote and candidate["role"] == row["role"]
                   and (not parent or (candidate["raw_name"] == row["raw_name"]
                                       and candidate["as_of_phrase"] == row["as_of_phrase"])) for candidate in parsed):
            raise ValueError("filing-excerpt-grammar-rejected")
        if parent:
            _text(row["raw_name"], 160)
            _text(row["as_of_phrase"], 120)
    return deepcopy(record)


def validated_records(artifact):
    if not isinstance(artifact, dict) or "filing_excerpts" not in artifact:
        return []
    rows = artifact["filing_excerpts"]
    if type(rows) is not list or len(rows) > MAX_RECORDS:
        raise ValueError("filing-excerpt-count-rejected")
    result = [validate_filing_excerpts(row) for row in rows]
    if len({row["receipt_no"] for row in result}) != len(result):
        raise ValueError("filing-excerpt-duplicate-receipt")
    return result


def _revision(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()


def _legal_name(value):
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"\(주[0-9]+\)|\(주석[0-9]+\)", "", value)
    value = re.sub(r"\s+", "", value)
    return re.sub(r"^(?:주식회사|\(주\))|(?:주식회사|\(주\))$", "", value)


def index_filing_excerpts(artifact, companies):
    """Bind exact unique public legal names, retaining explicit report scope."""
    rows = validated_records(artifact)
    by_id = {row["id"]: row for row in companies}
    names = {}
    for company in companies:
        if company["id"].startswith("KR:"):
            names.setdefault(_legal_name(company["name"]), set()).add(company["id"])
    relations, rates = [], []
    rejected = 0
    for row in rows:
        issuer = by_id.get(row["issuer_id"])
        if not issuer or _legal_name(issuer["name"]) != _legal_name(row["issuer_name"]):
            rejected += 1
            continue
        source = {"id": "source:dart:" + row["receipt_no"], "kind": "dart-filing-excerpt",
                  "receipt_no": row["receipt_no"], "as_of": row["filed_on"],
                  "report_name": row["report_name"], "document_issuer": row["issuer_id"],
                  "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + row["receipt_no"],
                  "artifact_observed_at": None}
        source["revision"] = _revision(source)
        for quote in row["excerpts"]:
            if quote["role"] == "reported-parent":
                targets = names.get(_legal_name(quote["raw_name"]), set())
                if len(targets) != 1 or row["issuer_id"] in targets:
                    rejected += 1
                    continue
                target = next(iter(targets))
                relation = {"stable_id": "relation:filing-parent:" + _revision([row["receipt_no"], row["issuer_id"], target])[:8],
                            "status": "accepted_reported", "type": "reported-parent-company",
                            "verification": "reported-filing-excerpt", "snapshot_scope": "reported-period-not-current",
                            "label": "보고서상 지배기업", "source": source,
                            "participants": [{"id": target, "role": "from"}, {"id": row["issuer_id"], "role": "to"}],
                            "evidence": {"role": "지배기업", **deepcopy(quote)}}
                relation["revision"] = _revision(relation)
                relations.append(relation)
            else:
                rates.append({"company_id": row["issuer_id"], "term": "변동", "excerpt": " ".join(quote["quote"].split()),
                              "url": source["url"], "as_of": source["as_of"], "source": source["report_name"],
                              "fiscal_year": re.search(r"\(([0-9]{4})\.", row["report_name"])[1], "truncated": True,
                              "channels": [{"kind": "floating-rate-borrowing", "quote": " ".join(quote["quote"].split())}]})
    return {"relations": relations, "rates": rates, "rates_revision": _revision(sorted(rates, key=lambda row: (row["company_id"], row["url"]))),
            "coverage": {"input": len(rows), "relationships": len(relations), "rate_references": len(rates), "rejected": rejected}}


def attach_parent_relationships(projection, index, positions):
    if projection is None or not index["coverage"]["input"]:
        return projection
    selected = {f"{row['market']}:{row['ticker']}" for row in positions}
    sources = {row["id"]: row for row in projection["sources"]}
    for row in index["relations"]:
        if any(person["id"] in selected for person in row["participants"]):
            projection["relationships"].append(deepcopy(row))
            sources.setdefault(row["source"]["id"], deepcopy(row["source"]))
    projection["sources"] = list(sources.values())
    projection["coverage"]["filing_excerpts"] = deepcopy(index["coverage"])
    return projection
