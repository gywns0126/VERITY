"""Index dated DART table entries once per public bundle and select either endpoint."""
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import re

from .portfolio_evidence import _legal_name
from .portfolio_public_sources import safe_public_text

FILENAME = "member_map_listed_ownership.json"
SCHEMA = "member-map-listed-ownership-v1"
_FIELDS = {"issuer", "party", "issuer_name", "party_name", "endpoint", "receipt",
           "settled_on", "pct", "row_index"}
_ENDPOINTS = {"hyslrSttus", "otrCprInvstmntSttus"}
_MAX_ROWS = 12000


def index_listed_ownership(document, companies):
    if (type(document) is not dict or set(document) != {"schema", "rows"}
            or document["schema"] != SCHEMA or type(document["rows"]) is not list
            or len(document["rows"]) > _MAX_ROWS):
        return None

    # Recheck the names against this generation of the company catalog. A rename
    # or name collision must not move a historical filing to the wrong company.
    owners = defaultdict(set)
    for identifier, company in companies.items():
        if identifier.startswith("KR:"):
            for name in (company["name"], *company.get("source_names", [])):
                owners[_legal_name(name)].add(identifier)

    by_company = defaultdict(list)
    seen = set()
    today = datetime.now(timezone(timedelta(hours=9))).date()
    receipt_issuers = {}
    for row in document["rows"]:
        if type(row) is not dict or set(row) != _FIELDS:
            continue
        a, b = row["issuer"], row["party"]
        if not all(type(value) is str and re.fullmatch(r"KR:[0-9]{6}", value) for value in (a, b)) or a == b:
            continue
        if (type(row["endpoint"]) is not str or row["endpoint"] not in _ENDPOINTS
                or type(row["receipt"]) is not str or not re.fullmatch(r"[0-9]{14}", row["receipt"])
                or type(row["settled_on"]) is not str or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", row["settled_on"])
                or type(row["row_index"]) is not int or row["row_index"] < 0
                or type(row["pct"]) not in (float, int) or not 0 < row["pct"] <= 100):
            continue
        try:
            receipt = row["receipt"]
            filed = date.fromisoformat(f"{receipt[:4]}-{receipt[4:6]}-{receipt[6:8]}")
            if not date.fromisoformat(row["settled_on"]) <= filed <= today:
                continue
        except ValueError:
            continue
        if not all(safe_public_text(row[key], 160) and owners.get(_legal_name(row[key])) == {identifier}
                   for key, identifier in (("issuer_name", a), ("party_name", b))):
            continue
        if receipt_issuers.setdefault(receipt, a) != a:
            return None
        identity = (receipt, row["endpoint"], row["row_index"])
        if identity in seen:
            # A single original row cannot have two public interpretations.
            return None
        seen.add(identity)
        by_company[a].append(row)
        by_company[b].append(row)
    return by_company


def select_listed_ownership(index, requested, limit=20):
    selected = set(requested)
    entries = {(r["issuer"], r["receipt"], r["endpoint"], r["row_index"]): r
               for identifier in selected for r in index.get(identifier, ())}
    rows = sorted(entries.values(), key=lambda r: (
        r["issuer"] in selected and r["party"] in selected, r["settled_on"], r["receipt"],
        r["issuer"], r["party"], r["endpoint"], r["row_index"]), reverse=True)
    return {"schema": SCHEMA, "rows": [r.copy() for r in rows[:limit]], "total": len(rows)}
