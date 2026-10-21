"""Deterministic, offline parsers for SEC Exhibit 21 subsidiary lists.

Rows are statements in a filing exhibit, not proof of current ownership,
exhaustiveness, or direct parentage. Network access belongs to the caller.
"""
from __future__ import annotations

from datetime import date
from urllib.parse import urlsplit
import hashlib
import re

from bs4 import BeautifulSoup, Comment, NavigableString

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
    """Resolve only a safe file in this filing's SEC archive directory.

    SEC sometimes links a co-registrant's archive CIK for an exhibit while
    retaining the requested issuer's accession directory. Accept that
    alternate archive CIK only when this accession's leading CIK is the
    requested issuer; all other filings must use the exact requested CIK path.
    """
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
    if "\\" in path or any(piece in (".", "..") for piece in path.split("/")):
        raise ValueError("invalid-sec-document-url")
    if path.startswith(directory):
        filename = path[len(directory):]
    else:
        expected = directory.strip("/").split("/")
        parts_path = path.strip("/").split("/")
        if (len(expected) != 5 or len(parts_path) != 6
                or parts_path[:3] != expected[:3]
                or parts_path[4] != expected[4]
                or not re.fullmatch(r"[1-9][0-9]{0,9}", parts_path[3], re.ASCII)
                or expected[3].zfill(10) != expected[4][:10]):
            raise ValueError("invalid-sec-document-url")
        filename = parts_path[5]
    if not _SAFE_FILE.fullmatch(filename) or "/" in filename:
        raise ValueError("invalid-sec-document-url")
    return f"https://{_SEC_HOST}{path.rsplit('/', 1)[0]}/{filename}"


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
_LEGAL_FORM = r"\b(?:Inc(?:orporated)?|Corp(?:oration)?|Ltd|Limited|GmbH|LLC|LLP|PLC|L\.L\.C|L\.P|U\.A|B\.V|N\.V|S\.A|S\.r\.l)\.?"
_LEGAL_END = re.compile(_LEGAL_FORM + r"$", re.I)
_LEGAL_TERMINATOR = re.compile(_LEGAL_FORM + r"(?=$|[\s,;.])", re.I)
_REGISTRANT = re.compile(r"\s*\(\s*registrant\s*\)\s*$", re.I)
_FOOTNOTE = re.compile(r"(?:[0-9]{1,3}|\([0-9]{1,3}\)|[¹²³⁰⁴⁵⁶⁷⁸⁹*†‡§¶]{1,3})\Z")
_ALIAS_HINT = re.compile(r"\(\s*(?:f/k/a|fka|formerly\s+known\s+as)\b", re.I)
_ALIAS_START = re.compile(r"^(?:f/k/a|fka|formerly\s+known\s+as)\s+(.+)$", re.I)
_PERCENT_OWNED = re.compile(r"\s*\(\s*(?:100(?:\.0{1,3})?|[0-9]{1,2}(?:\.[0-9]{1,3})?)\s*%\s+owned\s*\)\s*$", re.I)


def _issuer_name_key(value):
    """Narrow root comparison only; never rewrite emitted company names."""
    if not isinstance(value, str) or not value.strip() or len(value) > 300:
        return None
    if re.search(r"[<>\x00-\x1f]", value):
        return None
    words = re.sub(r"[^\w\s]", "", value.casefold()).split()
    if words and words[-1] in {"corp", "corporation"}:
        words[-1] = "corp"
    return " ".join(words) or None


def _complete_legal_name(name):
    ending = _LEGAL_END.search(name)
    return ending is not None and re.search(r"\w", name[:ending.start()]) is not None


def _current_legal_name(name):
    """Separate explicit trailing annotations; never turn them into ownership facts."""
    if name.endswith("*"):
        name = name[:-1].rstrip()
    if "*" in name or not re.search(r"\w", name):
        return None
    if re.search(r"%\s*owned\b", name, re.I):
        owned = _PERCENT_OWNED.search(name)
        if not owned or not _complete_legal_name(name[:owned.start()].rstrip()):
            return None
        name = name[:owned.start()].rstrip()
    depth, opening, trailing = 0, None, None
    for index, char in enumerate(name):
        if char == "(":
            if depth == 0:
                opening = index
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                return None
            if depth == 0 and index == len(name) - 1:
                trailing = opening
    if depth:
        return None
    if not _ALIAS_HINT.search(name):
        return name
    if trailing is None:
        return None
    alias = _ALIAS_START.fullmatch(name[trailing + 1:-1].strip())
    prefix = name[:trailing].strip()
    if (not alias or not re.search(r"\w", alias.group(1)) or len(prefix) > 300 or
            not _complete_legal_name(prefix) or _ALIAS_HINT.search(prefix)):
        return None
    return prefix


def _small_raised_marker(node):
    """Explicit small raised font/span only, not a general font-size heuristic."""
    if node.name not in {"font", "span"}:
        return False
    style = dict(part.strip().lower().split(":", 1) for part in node.get("style", "").split(";") if ":" in part)
    style = {key.strip(): value.strip() for key, value in style.items()}
    size = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)pt", style.get("font-size", ""))
    return bool(size and 0 < float(size.group(1)) <= 8 and
                (style.get("vertical-align") == "super" or
                 style.get("position") == "relative" and re.fullmatch(r"-(?:[0-9]+(?:\.[0-9]+)?)pt", style.get("top", ""))))


def _cell_blocks(cell, *, name_cell=False):
    """Keep explicit paragraph/BR boundaries, never split inline font/span wraps."""
    if cell.find(["table", "script", "style", "pre", "hr"]):
        return []  # No unambiguous flat cell layout.
    blocks, pending = [], []
    footnote = False
    ambiguous = False

    def flush():
        nonlocal footnote
        value = _norm("".join(pending))
        if value:
            blocks.append(value)
        pending.clear()
        footnote = False

    def visit(node):
        nonlocal footnote, ambiguous
        if isinstance(node, Comment):
            return
        if isinstance(node, NavigableString):
            if footnote and _norm(str(node)):
                ambiguous = True  # Superscript inside a name is not an endnote.
            pending.append(str(node))
            return
        raised_marker = _small_raised_marker(node)
        if node.name == "sup" or raised_marker:
            marker = _norm(node.get_text("", strip=True))
            preceding = _norm("".join(pending))
            current = _current_legal_name(_REGISTRANT.sub("", preceding))
            # Additional complete legal endings in APOG's explicit raised-font
            # rows; this does not broaden the downstream corporate filter.
            complete = current and (_complete_legal_name(current) or raised_marker and
                                    re.fullmatch(r".+\s(?:Ltda|ULC|BVBA)\.?", current, re.I))
            if (not _FOOTNOTE.fullmatch(marker) or not preceding or
                    name_cell and not complete):
                ambiguous = True
            footnote = True
            return
        boundary = node.name in {"p", "div", "li", "br"}
        if boundary:
            flush()
        for child in node.children:
            visit(child)
        if boundary:
            flush()

    for child in cell.children:
        visit(child)
    flush()
    return [] if ambiguous else blocks


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
        names = _cell_blocks(cells[name_i], name_cell=True)
        jurisdictions = _cell_blocks(cells[jurisdiction_i])
        if not names or len(names) != len(jurisdictions) or len(cells) != len(roles):
            needs_review = True
            continue
        entries = []
        for block_index, (name, jurisdiction) in enumerate(zip(names, jurisdictions)):
            name = _current_legal_name(name)
            if name is None:
                needs_review = True
                continue
            marker = _REGISTRANT.search(name)
            if marker:
                root = _issuer_name_key(metadata.get("issuerName"))
                if not root or _issuer_name_key(name[:marker.start()]) != root:
                    needs_review = True
                continue  # Matching registrant is self; unknown/mismatch is quarantined.
            entries.append((block_index, name, jurisdiction))
        # Matching block counts alone are not proof: a wrapped partial name
        # must not become a separate company. Reject the entire physical row.
        if any(";" in name or len(_LEGAL_TERMINATOR.findall(name)) > 1
               or (len(names) > 1 and not _complete_legal_name(name)) for _, name, _ in entries):
            needs_review = True
            continue
        if any(len(name) > 300 or len(jurisdiction) > 160 or ";" in jurisdiction
               or re.search(r"\b(?:d/b/a|doing business as|formerly known as|f/k/a)\b", name, re.I)
               for _, name, jurisdiction in entries):
            needs_review = True
            continue
        for block_index, name, jurisdiction in entries:
            source_row = {"index": row_index, "text": text}
            if len(names) > 1:
                source_row["blockIndex"] = block_index
            rows.append({"name": name, "jurisdiction": jurisdiction, "ownershipPct": None,
                         "directOwnership": "unspecified", "sourceRow": source_row})
            if len(rows) > _MAX_ROWS:
                result["rows"] = rows[:_MAX_ROWS]
                return result
    result["rows"] = rows
    result["status"] = "parsed" if rows and not needs_review else "needs-review"
    return result
