"""Deterministic, offline parsers for SEC Exhibit 21 subsidiary lists.

Rows are statements in a filing exhibit, not proof of current ownership,
exhaustiveness, or direct parentage. Network access belongs to the caller.
"""
from __future__ import annotations

from datetime import date
from urllib.parse import urlsplit
import hashlib
import re

from bs4 import BeautifulSoup

_CIK = re.compile(r"[0-9]{10}\Z", re.ASCII)
_ACCESSION = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}\Z", re.ASCII)
_SAFE_FILE = re.compile(r"[A-Za-z0-9_.-]+\.(?:html?|htm|txt)\Z", re.ASCII | re.I)
_MAX_INDEX = 8 * 1024 * 1024
_MAX_EXHIBIT = 8 * 1024 * 1024
_MAX_ROWS = 1000
_SEC_HOST = "www.sec.gov"
_ARCHIVE = "/Archives/edgar/data/"
_VIE_MARKER = re.compile(
    r"\bVIEs?\b|variable[\s-]+interest(?:ed)?(?:[\s-]+entit(?:y|ies))?|"
    r"consolidated\s+affiliated\s+entities",
    re.I,
)


def _identity(cik: str, accession: str) -> tuple[str, str, str]:
    if (not isinstance(cik, str) or not _CIK.fullmatch(cik) or int(cik) == 0
            or not isinstance(accession, str) or not _ACCESSION.fullmatch(accession)):
        raise ValueError("invalid-sec-identity")
    directory = f"{_ARCHIVE}{int(cik)}/{accession.replace('-', '')}/"
    return cik, accession, directory


def _archive_url(href: str, directory: str) -> str:
    """Resolve only a safe file in the exact filing directory."""
    if not isinstance(href, str) or not href or re.search(r"%(?:2f|5c|2e)", href, re.I):
        raise ValueError("invalid-sec-document-url")
    parts = urlsplit(href)
    if parts.scheme and parts.scheme.lower() != "https":
        raise ValueError("invalid-sec-document-url")
    if parts.netloc and parts.netloc.lower() != _SEC_HOST:
        raise ValueError("invalid-sec-document-url")
    if parts.query or parts.fragment:
        raise ValueError("invalid-sec-document-url")
    path = parts.path
    if not path.startswith("/"):
        if path in ("", ".") or path.startswith("../") or "/" in path or "\\" in path:
            raise ValueError("invalid-sec-document-url")
        path = directory + path
    if ("\\" in path or any(piece in (".", "..") for piece in path.split("/"))
            or not path.startswith(directory)):
        raise ValueError("invalid-sec-document-url")
    filename = path[len(directory):]
    if not _SAFE_FILE.fullmatch(filename) or "/" in filename:
        raise ValueError("invalid-sec-document-url")
    return f"https://{_SEC_HOST}{directory}{filename}"


def find_exhibit(index_html, *, cik, accession, form="10-K"):
    """Return the exact SEC archive URL for a uniquely listed subsidiary exhibit.

    10-K defaults to exact EX-21/EX-21.1 Types. For 20-F, exact EX-8/EX-8.1
    Types are eligible only when the row description explicitly says
    "subsidiaries". Missing rows return None; ambiguity is rejected.
    """
    if form not in {"10-K", "20-F"}:
        raise ValueError("unsupported-sec-form")
    _, _, directory = _identity(cik, accession)
    if isinstance(index_html, bytes):
        if len(index_html) > _MAX_INDEX:
            raise ValueError("sec-index-too-large")
        try:
            index_html = index_html.decode("utf-8", "strict")
        except UnicodeDecodeError:
            index_html = index_html.decode("latin-1")
    if not isinstance(index_html, str) or len(index_html.encode("utf-8")) > _MAX_INDEX:
        raise ValueError("invalid-sec-index")
    soup = BeautifulSoup(index_html, "html.parser")
    matches = []
    index_has_vie = False
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        headers = [" ".join(cell.stripped_strings).strip().casefold()
                   for cell in rows[0].find_all(["th", "td"], recursive=False)]
        type_index = next((i for i, value in enumerate(headers) if value == "type"), None)
        document_index = next((i for i, value in enumerate(headers)
                               if value in {"document", "document name", "name"}), None)
        description_index = next((i for i, value in enumerate(headers)
                                  if value == "description"), None)
        if type_index is None or document_index is None:
            continue
        marker = " ".join([str(table.get("id", "")), " ".join(table.get("class", [])),
                           " ".join(table.stripped_strings)]).casefold()
        if not any(token in marker for token in ("documents", "tablefile", "documentformat")):
            continue
        for row in rows[1:]:
            cells = row.find_all(["th", "td"], recursive=False)
            if max(type_index, document_index) >= len(cells):
                continue
            doc_type = " ".join(cells[type_index].stripped_strings).strip().upper()
            description = (" ".join(cells[description_index].stripped_strings)
                           if description_index is not None and description_index < len(cells)
                           else "")
            index_has_vie = index_has_vie or bool(_VIE_MARKER.search(description))
            if form == "20-F":
                eligible = doc_type in {"EX-8", "EX-8.1"} and "subsidiaries" in description.casefold()
            else:
                eligible = doc_type in {"EX-21", "EX-21.1"}
            if not eligible:
                continue
            link = cells[document_index].find("a", href=True)
            if link is None:
                raise ValueError("sec-exhibit-link-missing")
            matches.append(_archive_url(link["href"], directory))
    if len(matches) > 1:
        raise ValueError("sec-exhibit-ambiguous")
    if matches and index_has_vie:
        raise ValueError("sec-vie-needs-review")
    return matches[0] if matches else None


def _date(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("invalid-sec-metadata")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValueError("invalid-sec-metadata") from None
    return value


def _metadata(metadata):
    if not isinstance(metadata, dict):
        raise ValueError("invalid-sec-metadata")
    cik, accession, directory = _identity(metadata.get("cik"), metadata.get("accession"))
    filed = _date(metadata.get("filedDate"))
    period = _date(metadata.get("periodEnd"))
    if period > filed:
        raise ValueError("invalid-sec-metadata")
    url = _archive_url(metadata.get("url"), directory)
    if url != metadata.get("url"):
        raise ValueError("invalid-sec-metadata")
    return cik, accession, filed, period, url


def _norm(value):
    return " ".join(value.replace("\xa0", " ").split())


def _header_role(value):
    value = re.sub(r"[^a-z0-9 ]", " ", value.casefold())
    value = " ".join(value.split())
    if value == "name" or any(word in value for word in (
            "subsidiary", "subsidiaries", "company name", "legal name", "entity name")):
        return "name"
    if any(word in value for word in ("jurisdiction", "incorporation", "organized", "formed under")):
        return "jurisdiction"
    return None


_OMIT = re.compile(r"\b(?:subtotal|total|domestic|foreign|d\s*/\s*b\s*/\s*a|doing business as|trust|branch|footnote|see note)\b", re.I)


def parse_exhibit(raw_html, metadata):
    """Parse explicit subsidiary/name and jurisdiction columns without ownership inference."""
    cik, accession, filed, period, url = _metadata(metadata)
    if isinstance(raw_html, str):
        raw = raw_html.encode("utf-8")
    elif isinstance(raw_html, bytes):
        raw = raw_html
    else:
        raise ValueError("invalid-sec-exhibit")
    if not raw or len(raw) > _MAX_EXHIBIT:
        raise ValueError("sec-exhibit-size")
    try:
        html = raw.decode("utf-8", "strict")
    except UnicodeDecodeError:
        html = raw.decode("latin-1")
    soup = BeautifulSoup(html, "html.parser")
    result = {"schema": "sec-company-subsidiaries-v1", "cik": cik,
              "accession": accession, "filedDate": filed, "periodEnd": period,
              "url": url, "documentSha256": hashlib.sha256(raw).hexdigest(),
              "scope": "reported-subsidiary-list-not-exhaustive", "rows": [], "status": "needs-review"}
    if _VIE_MARKER.search(html):
        return result
    candidates = []
    for table in soup.find_all("table"):
        trs = table.find_all("tr")
        if not trs:
            continue
        for hi, tr in enumerate(trs[:3]):
            cells = tr.find_all(["th", "td"], recursive=False)
            roles = [_header_role(_norm(cell.get_text(" ", strip=True))) for cell in cells]
            if "name" in roles and "jurisdiction" in roles:
                candidates.append((table, trs, hi, roles))
                break
    if len(candidates) != 1:
        return result
    _, trs, header_i, roles = candidates[0]
    name_i, jurisdiction_i = roles.index("name"), roles.index("jurisdiction")
    rows = []
    needs_review = False
    for row_index, tr in enumerate(trs[header_i + 1:], start=header_i + 1):
        cells = tr.find_all(["th", "td"], recursive=False)
        if not cells:
            continue
        text = _norm(tr.get_text(" ", strip=True))
        if not text or _OMIT.search(text):
            continue
        if max(name_i, jurisdiction_i) >= len(cells):
            needs_review = True
            continue
        name = _norm(cells[name_i].get_text(" ", strip=True))
        jurisdiction = _norm(cells[jurisdiction_i].get_text(" ", strip=True))
        if not name or not jurisdiction or len(cells) != len(roles):
            needs_review = True
            continue
        if len(name) > 300 or len(jurisdiction) > 160 or re.search(r"\b(?:d/b/a|doing business as|formerly known as|f/k/a)\b", name, re.I):
            continue
        rows.append({"name": name, "jurisdiction": jurisdiction, "ownershipPct": None,
                     "directOwnership": "unspecified", "sourceRow": {"index": row_index, "text": text}})
        if len(rows) > _MAX_ROWS:
            result["rows"] = rows[:_MAX_ROWS]
            return result
    result["rows"] = rows
    result["status"] = "parsed" if rows and not needs_review else "needs-review"
    return result
