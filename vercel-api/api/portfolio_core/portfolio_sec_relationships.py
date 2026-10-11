"""Dated SEC annual excerpts; exact issuer/party binding, no model or price claim.

Only complete explicit issuer-owned lists establish a reported-period role.
Other paragraphs remain captured evidence, never a verified relationship.
"""
from collections import Counter
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
import re

from .portfolio_public_sources import safe_public_text

_ID = re.compile(r"US:[A-Z][A-Z0-9]{0,9}(?:[.-][A-Z0-9]{1,2})?\Z")
_HASH = re.compile(r"[a-f0-9]{64}\Z")
_LIST = re.compile(r"Our (?:major |principal )?(customers|suppliers) (?:include|are) (.+)\.", re.I)
_FOUNDRIES = re.compile(r"(?:^|\.\s+)We utilize foundries, such as ([^;!?]+?), or [A-Za-z][A-Za-z0-9-]*, and ([^;!?]+?), or [A-Za-z][A-Za-z0-9-]*, to produce our semiconductor wafers\.(?:$|\s)")
_RISK = re.compile(r"\b(?:not|no|may|might|could|would|will|expect|plan|former|previous|potential|indirect|subsidiar\w*|affiliate\w*|competitor\w*|except|excluding|terminated|ceased|historical|if|unless|subject to|provided that|conditional\w*|contingent|pending|according to|states?|stated|said|says?|quot\w*|example|illustrat\w*)\b|[\"“”]", re.I)
_FIELDS = {"schema", "issuer_id", "issuer_name", "cik", "accession", "filed_date",
           "period_end", "form", "primary_document", "url", "document_sha256", "paragraphs"}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def legal_name(value):
    name = re.sub(r"\s+", " ", value).strip().casefold()
    name = re.sub(r",?\s+(?:incorporated|inc\.?|corporation|corp\.?|limited|ltd\.?)$", "", name)
    return name.strip()


def validate_sec_capture(row):
    if type(row) is not dict or set(row) != _FIELDS or row["schema"] != "sec-annual-excerpts-v1":
        raise ValueError("sec-capture-shape")
    if (type(row["issuer_id"]) is not str or not _ID.fullmatch(row["issuer_id"])
            or safe_public_text(row["issuer_name"], 160) is None
            or type(row["cik"]) is not str or not re.fullmatch(r"[0-9]{10}", row["cik"])
            or int(row["cik"]) == 0 or type(row["accession"]) is not str
            or not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", row["accession"])
            or row["form"] not in ("10-K", "20-F")
            or type(row["primary_document"]) is not str
            or not re.fullmatch(r"[A-Za-z0-9_-]+\.html?", row["primary_document"])
            or type(row["document_sha256"]) is not str or not _HASH.fullmatch(row["document_sha256"])):
        raise ValueError("sec-capture-source")
    expected = (f"https://www.sec.gov/Archives/edgar/data/{int(row['cik'])}/"
                f"{row['accession'].replace('-', '')}/{row['primary_document']}")
    if row["url"] != expected:
        raise ValueError("sec-capture-url")
    for key in ("filed_date", "period_end"):
        if type(row[key]) is not str or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", row[key]):
            raise ValueError("sec-capture-date")
        date.fromisoformat(row[key])
    if not row["period_end"] <= row["filed_date"] <= date.today().isoformat():
        raise ValueError("sec-capture-date")
    paragraphs = row["paragraphs"]
    if type(paragraphs) is not list or len(paragraphs) > 24 or len(set(map(str, paragraphs))) != len(paragraphs):
        raise ValueError("sec-capture-paragraphs")
    if any(safe_public_text(text, 1200) is None or text != text.strip() for text in paragraphs):
        raise ValueError("sec-capture-paragraph")
    return row


def capture_sec_html(raw, metadata):
    """Bind SEC submissions metadata to inline-XBRL issuer/period before slicing.

    No tables are flattened into prose. Quotes are whole normalized paragraphs;
    paragraph offsets/financial numbers are not fabricated from table text.
    """
    if type(raw) is not bytes or not 0 < len(raw) <= 16 * 1024 * 1024:
        raise ValueError("sec-html-size")
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(raw, "html.parser")
    facts = {}
    for tag in soup.find_all(attrs={"name": True}):
        name = tag.get("name", "").lower()
        if name in {"dei:entitycentralindexkey", "dei:documentperiodenddate", "dei:documenttype"}:
            value = tag.get_text(" ", strip=True)
            if name == "dei:documentperiodenddate":
                # SEC inline-XBRL may display an English month with a declared
                # transform. Normalize only the explicitly supported format.
                transform = tag.get("format", "").split(":")[-1]
                if transform == "date-monthname-day-year-en":
                    value = re.sub(r"\s*,\s*", ", ", " ".join(value.split()))
                    try:
                        value = datetime.strptime(value, "%B %d, %Y").date().isoformat()
                    except ValueError:
                        raise ValueError("sec-html-date-transform") from None
            facts.setdefault(name, set()).add(value)
    if (facts.get("dei:entitycentralindexkey") != {metadata["cik"]}
            and facts.get("dei:entitycentralindexkey") != {str(int(metadata["cik"]))}):
        raise ValueError("sec-html-issuer")
    if (facts.get("dei:documentperiodenddate") != {metadata["period_end"]}
            or facts.get("dei:documenttype") != {metadata["form"]}):
        raise ValueError("sec-html-period")
    for tag in soup.find_all(["script", "style", "table", "ix:hidden", "blockquote", "q"]):
        tag.decompose()
    paragraphs = []
    for tag in soup.find_all(["p", "div"]):
        if tag.find(["p", "div"]) is not None:
            continue
        text = " ".join(tag.get_text(" ", strip=True).split())
        if (re.search(r"\b(?:customers?|suppliers?|foundr\w*|manufactur\w*)\b", text, re.I)
                and safe_public_text(text, 1200) is not None and text not in paragraphs):
            paragraphs.append(text)
    return validate_sec_capture({**metadata, "schema": "sec-annual-excerpts-v1",
                                 "document_sha256": hashlib.sha256(raw).hexdigest(),
                                 "paragraphs": paragraphs[:24]})


def index_sec_relationships(captures, companies):
    if type(captures) is not list or len(captures) > 1000:
        raise ValueError("sec-capture-count")
    by_id, names = {}, {}
    for company in companies:
        identifier, name = company.get("id"), company.get("name")
        if not isinstance(identifier, str) or not _ID.fullmatch(identifier) or safe_public_text(name, 160) is None:
            continue
        by_id[identifier] = company
        for alias in company.get("source_names", [name]):
            if safe_public_text(alias, 160) is not None and len(legal_name(alias)) >= 3:
                names.setdefault(legal_name(alias), set()).add(identifier)
    relations, by_company, rejected = {}, {}, Counter()
    paragraphs = bound = 0
    seen = set()
    for raw in captures:
        row = validate_sec_capture(raw)
        key = (row["issuer_id"], row["accession"])
        if key in seen:
            raise ValueError("sec-capture-duplicate")
        seen.add(key)
        issuer = row["issuer_id"]
        if names.get(legal_name(row["issuer_name"])) != {issuer}:
            rejected["issuer-name-not-uniquely-bound"] += 1
            continue
        bound += 1
        source = {"id": f"source:sec:{row['cik']}:{row['accession']}",
                  "kind": "sec-filing-excerpt", "cik": row["cik"], "accession": row["accession"],
                  "as_of": row["filed_date"], "period_end": row["period_end"], "form": row["form"],
                  "url": row["url"], "document_issuer": issuer}
        for quote in row["paragraphs"]:
            paragraphs += 1
            match, foundries = _LIST.fullmatch(quote), _FOUNDRIES.search(quote)
            if (match is None and foundries is None) or _RISK.search(quote):
                rejected["not-explicit-unqualified-issuer-list"] += 1
                continue
            role = "customer" if match and match[1].lower() == "customers" else "supplier"
            # Company suffix commas are not list separators.
            if foundries:
                entries = [foundries[1], foundries[2]]
            else:
                listing = re.sub(r",\s+(Inc\.?|Ltd\.?|Corp\.?)\b", r" \1", match[2], flags=re.I)
                entries = [s.strip() for s in re.split(r",\s*(?:and\s+)?|\s+and\s+", listing) if s.strip()]
            if not 1 <= len(entries) <= 12:
                rejected["party-list-limit"] += 1
                continue
            if not foundries and any(len(names.get(legal_name(name), set())) != 1
                                     or issuer in names.get(legal_name(name), set()) for name in entries):
                rejected["party-not-uniquely-bound"] += 1
                continue
            for name in entries:
                targets = names.get(legal_name(name), set())
                if len(targets) != 1 or issuer in targets:
                    rejected["party-not-uniquely-bound"] += 1
                    continue
                target = next(iter(targets))
                identifier = "relation:sec-role:" + _digest([issuer, role, target, row["accession"]])[:16]
                relation = {"stable_id": identifier, "type": "reported-sec-counterparty",
                            "status": "accepted_reported", "verification": "reported-sec-excerpt",
                            "snapshot_scope": "reported-filing-period-not-current",
                            "label": "SEC 보고서상 매출처" if role == "customer" else "SEC 보고서상 공급처",
                            "participants": [{"id": issuer, "role": "document_issuer", "name": by_id[issuer]["name"]},
                                             {"id": target, "role": "reported_" + role, "name": by_id[target]["name"]}],
                            "source": source, "evidence": {"role": role, "raw_name": name, "quote": quote,
                            "paragraph_sha256": hashlib.sha256(quote.encode()).hexdigest(),
                            "document_sha256": row["document_sha256"]}}
                relation["revision"] = _digest(relation)
                relations[identifier] = relation
                for person in (issuer, target):
                    by_company.setdefault(person, set()).add(identifier)
    return {"relations": sorted(relations.values(), key=lambda r: r["stable_id"]),
            "by_company": {k: sorted(v) for k, v in by_company.items()},
            "coverage": {"input": len(captures), "issuer_bound": bound, "paragraphs": paragraphs,
                         "relationships": len(relations), "rejection_reasons": dict(rejected)}}


def attach_sec_relationships(projection, index, positions):
    if projection is None or not index["coverage"]["input"]:
        return projection
    result = deepcopy(projection)
    selected = {f"{p['market']}:{p['ticker']}" for p in positions}
    ids = {r for p in selected for r in index["by_company"].get(p, [])}
    sources = {r["id"]: r for r in result["sources"]}
    for row in index["relations"]:
        if row["stable_id"] in ids:
            result["relationships"].append(deepcopy(row))
            sources[row["source"]["id"]] = deepcopy(row["source"])
    result["sources"] = list(sources.values())
    result["coverage"]["sec_relationships"] = deepcopy(index["coverage"])
    return result
