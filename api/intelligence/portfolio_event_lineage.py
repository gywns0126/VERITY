"""DART's explicit document families, not inferred economic-event identity.

Only the official viewer's #family select supplies the lineage. Titles, dates
and receipt-number order alone never merge filings. No IO or account data.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
import hashlib
import re
import unicodedata

from .portfolio_public_sources import safe_public_text

DART = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="
_RECEIPT = re.compile(r"[0-9]{14}\Z", re.ASCII)
_ISSUER = re.compile(r"KR:[0-9]{6}\Z", re.ASCII)
_CORP = re.compile(r"openCorpInfoNew\('([0-9]{8})',")


def _name(value):
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _contract_title(value):
    title = re.sub(r"\[(?:기재|첨부|기타)?정정\]", "", _name(value)).strip()
    return re.sub(r"[ㆍ·ᆞ]", "·", title)


class _FamilyParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.family_count = 0
        self.in_family = False
        self.option = None
        self.options = []
        self.issuer = None
        self.issuers = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "select":
            self.in_family = attrs.get("id") == "family"
            self.family_count += self.in_family
        if tag == "option" and self.in_family:
            if self.option is not None:
                raise ValueError("invalid-dart-family")
            self.option = {"attrs": attrs, "text": ""}
        if tag == "span" and _CORP.match(attrs.get("onclick", "")):
            self.issuer = {"corp_code": _CORP.match(attrs["onclick"]).group(1), "name": ""}

    def handle_data(self, data):
        if self.option is not None:
            self.option["text"] += data
        if self.issuer is not None:
            self.issuer["name"] += data

    def handle_endtag(self, tag):
        if tag == "option" and self.option is not None:
            self.options.append(self.option)
            self.option = None
        if tag == "select":
            self.in_family = False
        if tag == "span" and self.issuer is not None:
            self.issuers.append(self.issuer)
            self.issuer = None


def validate_family(row):
    """Closed, path-free artifact; collection time is not a filing date."""
    if not isinstance(row, dict) or set(row) != {
            "issuer_id", "issuer_name", "corp_code", "receipt_no", "url",
            "observed_at", "content_sha256", "members"}:
        raise ValueError("invalid-dart-family")
    for key, pattern in (("issuer_id", _ISSUER), ("receipt_no", _RECEIPT),
                         ("corp_code", re.compile(r"[0-9]{8}\Z", re.ASCII)),
                         ("content_sha256", re.compile(r"[0-9a-f]{64}\Z", re.ASCII))):
        if not isinstance(row[key], str) or not pattern.fullmatch(row[key]):
            raise ValueError("invalid-dart-family")
    if safe_public_text(row["issuer_name"], 160) is None or row["url"] != DART + row["receipt_no"]:
        raise ValueError("invalid-dart-family")
    stamp = row["observed_at"]
    if not isinstance(stamp, str) or len(stamp) > 40:
        raise ValueError("invalid-dart-family")
    observed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    if observed.tzinfo is None:
        raise ValueError("invalid-dart-family")
    observed_day = observed.astimezone(timezone(timedelta(hours=9))).date()
    if not isinstance(row["members"], list) or not 1 <= len(row["members"]) <= 100:
        raise ValueError("invalid-dart-family")
    receipts, originals, titles = set(), [], set()
    for member in row["members"]:
        if not isinstance(member, dict) or set(member) != {"receipt_no", "title", "published_on", "amendment"}:
            raise ValueError("invalid-dart-family")
        receipt, title, day = member["receipt_no"], member["title"], member["published_on"]
        if (not isinstance(receipt, str) or not _RECEIPT.fullmatch(receipt) or receipt in receipts
                or safe_public_text(title, 300) is None or type(member["amendment"]) is not bool
                or not isinstance(day, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", day)
                or date.fromisoformat(day) > observed_day):
            raise ValueError("invalid-dart-family")
        receipts.add(receipt)
        titles.add(_contract_title(title))
        if not member["amendment"]:
            originals.append(member)
    # One recognized filing family only, not every report in a dropdown.
    if (row["receipt_no"] not in receipts or len(originals) != 1
            or titles != {"단일판매·공급계약체결"}
            or any(m["published_on"] < originals[0]["published_on"] for m in row["members"])):
        raise ValueError("invalid-dart-family")
    return row


def parse_dart_family(html, receipt, issuer_id, expected_name, observed_at):
    if not isinstance(html, str) or len(html.encode("utf-8")) > 2 * 1024 * 1024:
        raise ValueError("invalid-dart-family")
    parser = _FamilyParser()
    parser.feed(html)
    parser.close()
    if (parser.family_count != 1 or parser.option is not None or parser.in_family
            or len(parser.issuers) != 1 or _name(parser.issuers[0]["name"]) != _name(expected_name)):
        raise ValueError("invalid-dart-family")
    members, selected = [], []
    for option in parser.options:
        attrs, text = option["attrs"], _name(option["text"])
        if attrs.get("value") == "null":
            continue
        match = re.fullmatch(r"rcpNo=([0-9]{14})", attrs.get("value", ""))
        dated = re.fullmatch(r"([0-9]{4})\.([0-9]{2})\.([0-9]{2})\s+(\[정정\]\s*)?(.+)", text)
        if not match or not dated or _name(attrs.get("title", "")) != dated.group(5):
            raise ValueError("invalid-dart-family")
        if "selected" in attrs:
            selected.append(match.group(1))
        members.append({"receipt_no": match.group(1), "title": attrs["title"],
                        "published_on": "-".join(dated.group(i) for i in (1, 2, 3)),
                        "amendment": bool(dated.group(4))})
    if selected != [receipt]:
        raise ValueError("invalid-dart-family")
    return validate_family({"issuer_id": issuer_id, "issuer_name": expected_name,
        "corp_code": parser.issuers[0]["corp_code"], "receipt_no": receipt, "url": DART + receipt,
        "observed_at": observed_at, "content_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
        "members": sorted(members, key=lambda m: (m["published_on"], m["receipt_no"]))})


def attach_event_lineage(artifact, document_list, company_catalog):
    """Attach explicit family evidence without replacing documents or user IDs."""
    for doc in document_list:
        doc.pop("event_lineage", None)
    rows = artifact.get("documentFamilies", []) if isinstance(artifact, dict) else []
    coverage = {"input": len(rows) if isinstance(rows, list) else 0, "accepted": 0,
                "rejected": 0, "unmatched": 0, "attached_documents": 0, "families": 0,
                "verified_economic_events": 0}
    if not isinstance(rows, list) or len(rows) > 1000:
        coverage.update(rejected=coverage["input"], shape_errors=1)
        return coverage
    by_id = {c["id"]: c for c in company_catalog}
    names = {}
    for c in company_catalog:
        for name in c.get("source_names", [c["name"]]):
            names.setdefault(_name(name), set()).add(c["id"])
    staged = {}
    for row in rows:
        try:
            validate_family(row)
            issuer = row["issuer_id"]
            if issuer not in by_id or names.get(_name(row["issuer_name"])) != {issuer}:
                raise ValueError("unresolved-issuer")
        except (TypeError, ValueError, KeyError):
            coverage["rejected"] += 1
            continue
        member = next(m for m in row["members"] if m["receipt_no"] == row["receipt_no"])
        matched = [d for d in document_list if d["id"] == "DART:" + row["receipt_no"]
                   and d["url"] == row["url"] and d["source"] == "DART" and d["kind"] == "disclosure"
                   and d["company_ids"] == [issuer] and d["as_of"] == member["published_on"]
                   and _contract_title(d["title"]) == _contract_title(member["title"])
                   and ("정정" in d["title"]) == member["amendment"]]
        if not matched:
            coverage["unmatched"] += 1
            continue
        coverage["accepted"] += 1
        original = next(m for m in row["members"] if not m["amendment"])
        lineage = {"id": f"dart-family:{row['corp_code']}:{original['receipt_no']}",
            "kind": "official-dart-document-family", "issuer_id": issuer,
            "root_receipt": original["receipt_no"], "current_receipt": row["receipt_no"],
            "verified_common_event": False, "current_economic_status": "unverified",
            "members": deepcopy(row["members"])}
        staged.setdefault(matched[0]["id"], []).append((matched[0], lineage))
    families = set()
    for entries in staged.values():
        # Conflicting snapshots cannot silently choose the newest capture.
        if any(lineage != entries[0][1] for _, lineage in entries):
            coverage["rejected"] += len(entries)
            coverage["accepted"] -= len(entries)
            continue
        doc, lineage = entries[0]
        doc["event_lineage"] = lineage
        coverage["attached_documents"] += 1
        families.add(lineage["id"])
    coverage["families"] = len(families)
    return coverage
