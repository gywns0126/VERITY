"""Deterministic, offline parsers for SEC Exhibit 21 subsidiary lists.

Rows are statements in a filing exhibit, not proof of current ownership,
exhaustiveness, or direct parentage. Network access belongs to the caller.
"""
from __future__ import annotations

from datetime import date, datetime
from urllib.parse import urlsplit
import hashlib
import re

from bs4 import BeautifulSoup, Comment, NavigableString

PARSER_REVISION = "2026-10-25-bound-continuations-v19"
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
# Closed spellings verified in the saved AVT Exhibit 21.1 Country column.
# This is not a world-country registry or a country-code inference rule; it
# applies only to the issuer-bound Company Name/Country continuation layout.
_OBSERVED_COUNTRY_COLUMN_VALUES = frozenset({
    "Australia", "Austria", "Belgium", "Brazil", "Bulgaria", "Canada", "China",
    "Czech Republic", "Denmark", "Estonia", "Finland", "France", "Germany",
    "Hong Kong", "Hungary", "India", "Ireland", "Israel", "Italy", "Japan",
    "Korea, Republic of", "Lithuania", "Luxembourg", "Malaysia", "Malta",
    "Mexico", "Netherlands", "New Zealand", "Norway", "Philippines", "Poland",
    "Portugal", "Romania", "Serbia", "Singapore", "Slovakia", "Slovenia",
    "South Africa", "Spain", "Sweden", "Switzerland", "Taiwan (Province of China)",
    "Thailand", "Turkey", "Ukraine", "United Kingdom", "United States",
})


def _identity(cik: str, accession: str) -> tuple[str, str, str]:
    if (not isinstance(cik, str) or not _CIK.fullmatch(cik) or int(cik) == 0
            or not isinstance(accession, str) or not _ACCESSION.fullmatch(accession)):
        raise ValueError("invalid-sec-identity")
    directory = f"{_ARCHIVE}{int(cik)}/{accession.replace('-', '')}/"
    return cik, accession, directory


def _archive_url(href: str, directory: str, allowed_archive_ciks=()) -> str:
    """Resolve only a safe file in this filing's SEC archive directory.

    SEC sometimes links a co-registrant's archive CIK for an exhibit while
    retaining the requested issuer's accession directory. Accept that
    alternate archive CIK only when this accession's leading CIK is the
    requested issuer or when the caller supplies a rechecked index-filer CIK.
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
                or not re.fullmatch(r"[1-9][0-9]{0,9}", parts_path[3], re.ASCII)):
            raise ValueError("invalid-sec-document-url")
        filename = parts_path[5]
        if not _SAFE_FILE.fullmatch(filename):
            raise ValueError("invalid-sec-document-url")
        if expected[3].zfill(10) != expected[4][:10] and parts_path[3] not in allowed_archive_ciks:
            # A valid same-filing co-filer path is not a transport failure.
            # Its subsidiary list may belong to a different registrant (EMP),
            # so retain the strict issuer gate rather than accepting all CIKs.
            raise ValueError("sec-cofiler-issuer-needs-review")
    if not _SAFE_FILE.fullmatch(filename) or "/" in filename:
        raise ValueError("invalid-sec-document-url")
    return f"https://{_SEC_HOST}{path.rsplit('/', 1)[0]}/{filename}"


def find_exhibit(index_html, *, cik, accession, form="10-K", issuer_name=None,
                 return_proof=False):
    """Return the exact SEC archive URL for a uniquely listed subsidiary exhibit.

    10-K defaults to exact EX-21/EX-21.1 Types. For 20-F, exact EX-8/EX-8.1
    Types are eligible only when the row description explicitly says
    "subsidiaries". Missing rows return None; ambiguity is rejected.
    """
    if form not in {"10-K", "20-F"}:
        raise ValueError("unsupported-sec-form")
    _, _, directory = _identity(cik, accession)
    index_raw = index_html if isinstance(index_html, bytes) else None
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
    filers = {}
    for node in soup.select(".companyInfo"):
        heading = node.find(["span", "a"])
        heading = heading.get_text(" ", strip=True) if heading else node.get_text(" ", strip=True)
        match = re.match(r"^(.+?)\s*\(Filer\)\s*CIK\s*:\s*([0-9]{10})\b", heading, re.I)
        if match:
            filers.setdefault(match.group(2), []).append(_norm(match.group(1)).casefold())
    issuer_key = _norm(issuer_name).casefold() if isinstance(issuer_name, str) else None
    issuer_bound = bool(issuer_key and filers.get(cik) == [issuer_key])
    allowed = {str(int(value)) for value, names in filers.items()
               if issuer_bound and value != cik and len(names) == 1}
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
            href = link["href"]
            if href.lower().endswith(".pdf"):
                # Validate its exact archive directory through the same gate;
                # only the paired HTML rendition can become the selected source.
                safe_html = _archive_url(href[:-4] + ".htm", directory, allowed)
                matches.append(safe_html[:-4] + ".pdf")
            else:
                matches.append(_archive_url(href, directory, allowed))
    # A same-stem PDF rendition is not another source list. Never select PDF
    # or collapse distinct HTML exhibits.
    html_matches = [url for url in matches if not url.lower().endswith(".pdf")]
    if len(matches) != len(html_matches):
        pdfs = [url for url in matches if url.lower().endswith(".pdf")]
        if (len(html_matches) != 1 or len(pdfs) != 1
                or any(pdf[:-4] != html_matches[0].rsplit(".", 1)[0]
                                           for pdf in pdfs)):
            raise ValueError("sec-exhibit-ambiguous")
        matches = html_matches
    if len(matches) > 1:
        raise ValueError("sec-exhibit-ambiguous")
    if matches and index_has_vie:
        raise ValueError("sec-vie-needs-review")
    url = matches[0] if matches else None
    proof = None
    if url and issuer_bound:
        archive_cik = url.split("/Archives/edgar/data/", 1)[1].split("/", 1)[0]
        if archive_cik != str(int(cik)) and accession[:10] != cik:
            proof = {"requestedCik": cik, "archiveCik": archive_cik,
                     "accession": accession, "issuerName": issuer_name,
                     "exhibitUrl": url,
                     "indexSha256": hashlib.sha256(index_raw if index_raw is not None
                                                    else index_html.encode("utf-8")).hexdigest()}
    return (url, proof) if return_proof else url


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
    proof = metadata.get("cofilerProof")
    index_raw = metadata.get("cofilerIndexRaw")
    allowed = ()
    if proof is not None or index_raw is not None:
        if not isinstance(index_raw, bytes) or not isinstance(proof, dict):
            raise ValueError("sec-cofiler-proof-invalid")
        found_url, found_proof = find_exhibit(index_raw, cik=cik, accession=accession,
            form=metadata.get("form", "10-K"), issuer_name=metadata.get("issuerName"), return_proof=True)
        if found_url != metadata.get("url") or found_proof != proof:
            raise ValueError("sec-cofiler-proof-invalid")
        allowed = (proof["archiveCik"],)
    url = _archive_url(metadata.get("url"), directory, allowed)
    if url != metadata.get("url"):
        raise ValueError("invalid-sec-metadata")
    return cik, accession, filed, period, url, proof


def _norm(value):
    return " ".join(value.replace("\xa0", " ").split())


def _header_role(value):
    if re.fullmatch(r"name\s*\([0-9]{1,3}\)", value, re.I):
        return "name"
    value = re.sub(r"[^a-z0-9 ]", " ", value.casefold())
    value = " ".join(value.split())
    if value in {"name", "company", "name of company", "name of entity", "entity"} or any(word in value for word in (
            "subsidiary", "subsidiaries", "company name", "legal name", "entity name")):
        return "name"
    if value in {"state of organization", "state or country of organization",
                 "state incorporated", "country or state of organization"} or any(
            word in value for word in ("jurisdiction", "incorporation", "organized", "formed under")):
        return "jurisdiction"
    return None


_OMIT = re.compile(r"\b(?:subtotal|total|domestic|foreign|d\s*/\s*b\s*/\s*a|doing business as|trust|branch|footnote|see note)\b", re.I)
_LEGAL_FORM = r"\b(?:Inc(?:orporated)?|Corp(?:oration)?|Ltd|Limited|GmbH|LLC|LLP|PLC|L\.L\.C|L\.P|U\.A|B\.V|N\.V|S\.A|S\.r\.l)\.?"
_LEGAL_END = re.compile(_LEGAL_FORM + r"$", re.I)
_LEGAL_TERMINATOR = re.compile(_LEGAL_FORM + r"(?=$|[\s,;.])", re.I)
_COMPOUND_LEGAL_END = re.compile(r".+\sPty Ltd\., Inc\.$", re.I)
_REGISTRANT = re.compile(r"\s*\(\s*registrant\s*\)\s*$", re.I)
_FOOTNOTE = re.compile(r"(?:[0-9]{1,3}|\([0-9]{1,3}\)|[¹²³⁰⁴⁵⁶⁷⁸⁹*†‡§¶]{1,3})\Z")
_ALIAS_HINT = re.compile(r"\(\s*(?:f/k/a|fka|formerly(?:\s+known\s+as)?)\b", re.I)
_ALIAS_START = re.compile(r"^(?:f/k/a|fka|formerly(?:\s+known\s+as)?)\s+(.+)$", re.I)
_PERCENT_OWNED = re.compile(r"\s*\(\s*(?:100(?:\.0{1,3})?|[0-9]{1,2}(?:\.[0-9]{1,3})?)\s*%\s+owned\s*\)\s*$", re.I)
_COUNT_WORDS = {word: count for count, word in enumerate(
    ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"), 1)}
_FLAT_TABLE_JURISDICTIONS = _OBSERVED_COUNTRY_COLUMN_VALUES | frozenset({
    "Alberta", "California", "Chile", "Colombia", "Colorado", "Cyprus", "Delaware",
    "District of Columbia", "England", "England and Wales", "Florida", "Greece", "Korea",
    "Louisiana", "Mississippi", "New York", "Taiwan", "Vermont", "Vietnam", "Virginia",
})


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


def _issuer_title_pattern(root):
    # Same narrow terminal legal-form equivalence as _issuer_name_key; apply
    # it to the issuer span, not the whole title ending in an as-of date.
    return (re.escape(root[:-5]) + r" (?:corp|corporation)"
            if root.endswith(" corp") else re.escape(root))


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


def _jurisdiction_qualified_legal_name(name, jurisdiction, issuer_name):
    """One issuer-prefixed flat name, e.g. Analog Devices Limited Egypt LLC."""
    if not isinstance(issuer_name, str) or not jurisdiction:
        return False
    match = re.fullmatch(r"(.+) Limited " + re.escape(jurisdiction) + r" LLC", name)
    issuer = _LEGAL_END.sub("", issuer_name).strip()
    return bool(match and _issuer_name_key(match[1]) == _issuer_name_key(issuer))


def _statement_list(soup, metadata, result):
    """Accept only a complete issuer-bound, flat, table-free exhibit list."""
    body = soup.body
    if body is None or body.find(["table", "ol", "ul", "pre"]):
        return None
    blocks = [node for node in body.find_all(["p", "div"])
              if not node.find(["p", "div"]) and _norm(node.get_text(" ", strip=True))]
    texts = [_norm(node.get_text(" ", strip=True)) for node in blocks]
    if not texts or _norm(" ".join(body.stripped_strings)) != _norm(" ".join(texts)):
        return None  # Unbound text outside physical statement blocks.
    if any(node.find(["br", "sup", "table"]) for node in blocks):
        return None
    root = _issuer_name_key(metadata.get("issuerName"))
    if not root:
        return None
    if re.fullmatch(r"exhibit 21(?:\.1)?", texts[0], re.I):
        texts, blocks = texts[1:], blocks[1:]
    if not texts or _issuer_name_key(texts[0]) not in {
            "subsidiaries of " + root, "list of subsidiaries of " + root}:
        return None
    texts, blocks = texts[1:], blocks[1:]
    stated_count = None
    if texts and texts[0].casefold().startswith("as of "):
        statement = re.fullmatch(
            r"As of ([A-Za-z]+ \d{1,2}, \d{4}), (.+) had ([a-z]+) sole subsidiaries:",
            texts[0], re.I)
        if not statement or _issuer_name_key(statement[2]) != root:
            result["reviewReason"] = "continuation-scope-text"
            return result
        try:
            stated_day = datetime.strptime(statement[1], "%B %d, %Y").date().isoformat()
        except ValueError:
            result["reviewReason"] = "invalid-exhibit-as-of-date"
            return result
        if stated_day != result["periodEnd"]:
            result["reviewReason"] = "exhibit-as-of-differs-from-period-end"
            result["statedAsOf"] = stated_day
            return result
        stated_count = _COUNT_WORDS.get(statement[3].casefold())
        if stated_count is None:
            result["reviewReason"] = "ambiguous-row-binding"
            return result
        texts, blocks = texts[1:], blocks[1:]
    if not texts or len(texts) > _MAX_ROWS:
        result["reviewReason"] = "no-eligible-subsidiary-rows" if not texts else "row-limit"
        return result
    rows = []
    numbered = None
    for index, (text, block) in enumerate(zip(texts, blocks), 1):
        match = re.fullmatch(
            r"(?:(\d{1,3})\. )?(.+), (?:a|an) ([A-Za-z][A-Za-z ]{0,158}?) "
            r"(?:corporation|limited liability company)(?:;(?: and)?|\.)?", text, re.I)
        if not match or match[1] is not None and int(match[1]) != index:
            result["reviewReason"] = "ambiguous-row-binding"
            return result
        if numbered is None:
            numbered = match[1] is not None
        if (numbered != (match[1] is not None) or
                not _complete_legal_name(match[2]) or
                len(_LEGAL_TERMINATOR.findall(match[2])) != 1 or
                _issuer_name_key(match[2]) == root or
                re.search(r"\band\b|/", match[2], re.I) or
                _ALIAS_HINT.search(text) or
                re.search(r"\b(?:owned|ownership|parent|subsidiar|formerly|fka|dba|aka|doing business as)\b|d/b/a|%|\*", text, re.I)):
            result["reviewReason"] = "ambiguous-row-binding"
            return result
        rows.append({"name": match[2], "jurisdiction": match[3], "ownershipPct": None,
                     "directOwnership": "unspecified", "sourceRow": {"index": index, "text": text}})
    if stated_count is not None and len(rows) != stated_count:
        result["reviewReason"] = "ambiguous-row-binding"
        return result
    result["rows"] = rows
    result["status"] = "parsed"
    return result


def _flat_issuer_table(soup, table, metadata, result):
    """Review one fully bound table, including spacer cells and late headers."""
    if table.find("table") or table.find_parent("table"):
        return None
    root = _issuer_name_key(metadata.get("issuerName"))
    if not root:
        return None
    prefix = []
    for node in (soup.body or soup).descendants:
        if node is table:
            break
        if (isinstance(node, NavigableString) and not isinstance(node, Comment)
                and not node.find_parent(["head", "style", "script"])):
            prefix.append(str(node))
    heading = _issuer_name_key(_norm(" ".join(prefix)))
    title = {"subsidiaries of " + root, "significant subsidiaries of " + root}
    exhibit = {"exhibit 21", "exhibit 211"}
    title_in_prefix = any(heading == marker + " " + name for marker in exhibit for name in title)
    if not title_in_prefix and heading not in exhibit:
        return None
    last = list(table.descendants)[-1]
    following = _norm(" ".join(str(node) for node in last.next_elements
                               if isinstance(node, NavigableString) and not isinstance(node, Comment)
                               and not node.find_parent(["head", "style", "script"])))
    if following:
        result["reviewReason"] = "continuation-scope-text"
        return result

    def cells_with_starts(tr):
        cells, start, positions = tr.find_all(["th", "td"], recursive=False), 0, []
        for cell in cells:
            span = cell.get("colspan", "1")
            if cell.get("rowspan") or not re.fullmatch(r"[1-9][0-9]?", str(span)):
                return None
            value = _norm(cell.get_text(" ", strip=True).replace("\u200b", "").replace("\ufeff", ""))
            positions.append((start, value, cell))
            start += int(span)
        return start, positions

    trs = table.find_all("tr")
    if len(trs) < 3:
        return None
    header_i = None
    title_in_table = False
    expected_width = None
    anchors = None
    for index, tr in enumerate(trs[:6]):
        parsed = cells_with_starts(tr)
        if parsed is None:
            return None
        width, positions = parsed
        if expected_width is None:
            expected_width = width
        if width != expected_width:
            return None
        filled = [(start, value) for start, value, _ in positions if value]
        if not filled:
            continue
        if (not title_in_prefix and not title_in_table and len(filled) == 1
                and _issuer_name_key(filled[0][1]) in title):
            title_in_table = True
            continue
        if (len(filled) == 2 and filled[0][1].casefold() in {
                "name", "subsidiary", "name of subsidiary", "name of corporation"}
                and filled[1][1].casefold() in {
                    "jurisdiction", "jurisdiction of formation", "state of incorporation", "incorporated"}):
            header_i = index
            anchors = (filled[0][0], filled[1][0])
            break
        return None
    if header_i is None or (not title_in_prefix and not title_in_table):
        return None
    rows = []
    for row_index, tr in enumerate(trs[header_i + 1:], header_i + 1):
        parsed = cells_with_starts(tr)
        if parsed is None or parsed[0] != expected_width:
            result["reviewReason"] = "ambiguous-row-binding"
            return result
        filled = [(start, value, cell) for start, value, cell in parsed[1] if value]
        if not filled:
            continue
        if (len(filled) != 2 or tuple(start for start, _, _ in filled) != anchors
                or any(cell.find(["br", "sup", "table", "script", "style"])
                       or len(cell.find_all(["p", "div"])) > 1 for _, _, cell in filled)):
            result["reviewReason"] = "ambiguous-row-binding"
            return result
        name, jurisdiction = filled[0][1], filled[1][1]
        if (len(name) > 300 or jurisdiction not in _FLAT_TABLE_JURISDICTIONS
                or re.search(r"\b(?:dba|fka|aka|formerly|owned|ownership|parent|trade name)\b|d/b/a|f/k/a|%|\*", name, re.I)
                or len(_LEGAL_TERMINATOR.findall(name)) > 1
                or (_LEGAL_TERMINATOR.search(name) and not (
                    _complete_legal_name(name)
                    or re.fullmatch(r".+\sS\.A\.S\.", name, re.I)
                    or re.fullmatch(r".+\sS\.A\. de C\.V\.", name, re.I)))
                or re.search(r"\(\s*[0-9]{1,3}\s*\)$", name)
                or any(row["name"] == name for row in rows)):
            result["reviewReason"] = "ambiguous-row-binding"
            return result
        if _issuer_name_key(name) == root:
            continue
        rows.append({"name": name, "jurisdiction": jurisdiction, "ownershipPct": None,
                     "directOwnership": "unspecified", "sourceRow": {"index": row_index,
                     "text": _norm(tr.get_text(" ", strip=True))}})
        if len(rows) > _MAX_ROWS:
            result["reviewReason"] = "row-limit"
            return result
    if not rows:
        result["reviewReason"] = "no-eligible-subsidiary-rows"
        return result
    result["rows"] = rows
    result["status"] = "parsed"
    return result


def _check_exhibit_as_of(soup, period, result):
    """Reject an explicit exhibit date that differs from the filing period."""
    visible_root = soup.body or soup
    visible_text = _norm(" ".join(
        str(node) for node in visible_root.descendants
        if isinstance(node, NavigableString) and not isinstance(node, Comment)
        and not node.find_parent(["head", "style", "script"])))
    for match in re.finditer(r"\bas of\s+([A-Za-z]+\s+\d{1,2},\s*\d{4}|\d{4}-\d{2}-\d{2})\b", visible_text, re.I):
        stated = match.group(1)
        try:
            stated_day = (date.fromisoformat(stated).isoformat() if re.match(r"\d", stated)
                          else datetime.strptime(re.sub(r",\s*", ", ", stated), "%B %d, %Y").date().isoformat())
        except ValueError:
            result["reviewReason"] = "invalid-exhibit-as-of-date"
            return False
        if stated_day != period:
            result["reviewReason"] = "exhibit-as-of-differs-from-period-end"
            result["statedAsOf"] = stated_day
            return False
    return True


def _leading_title_table(soup, table, metadata, result):
    """Bind a late two-column header to an issuer and date stated in that table."""
    if table.find("table") or table.find_parent("table"):
        return None
    trs = table.find_all("tr")
    root = _issuer_name_key(metadata.get("issuerName"))
    if not root or len(trs) < 7:
        return None
    header_i = None
    for index, tr in enumerate(trs[3:9], 3):
        cells = tr.find_all(["th", "td"], recursive=False)
        roles = [_header_role(_norm(cell.get_text(" ", strip=True))) for cell in cells]
        if roles.count("name") == roles.count("jurisdiction") == 1 and len(cells) in (2, 3):
            header_i = index
            break
    if header_i is None:
        return None

    def hold(reason):
        result["reviewReason"] = reason
        return result

    # A SEC document wrapper is not an issuer title. Any other outside-table
    # text may alter the scope, so it cannot be inherited by this layout.
    prefix = []
    for node in soup.descendants:
        if node is table:
            break
        if isinstance(node, NavigableString) and not isinstance(node, Comment) and not node.find_parent(
                ["head", "style", "script"]):
            prefix.append(str(node))
    before = _norm(" ".join(prefix))
    wrapper = re.fullmatch(
        r"EX-(21(?:\.1)?) [0-9]{1,3} [A-Za-z0-9_.-]+\.html? EX-\1", before, re.I)
    if before and not wrapper:
        return hold("continuation-scope-text")
    last = list(table.descendants)[-1]
    following = _norm(" ".join(str(node) for node in last.next_elements
                               if isinstance(node, NavigableString) and not isinstance(node, Comment)
                               and not node.find_parent(["head", "style", "script"])))
    if following:
        return hold("continuation-scope-text")

    leading = []
    for tr in trs[:header_i]:
        cells = tr.find_all(["th", "td"], recursive=False)
        if not cells or any(cell.get("rowspan") or cell.find(["table", "br", "sup"])
                            for cell in cells):
            return hold("ambiguous-row-binding")
        filled = [_norm(cell.get_text(" ", strip=True)) for cell in cells]
        filled = [value for value in filled if value]
        if len(filled) > 1:
            return hold("ambiguous-row-binding")
        if filled:
            leading.append(filled[0])
    if len(leading) != 4 or not re.fullmatch(r"exhibit 21(?:\.1)?", leading[0], re.I):
        return hold("issuer-scope-unbound")
    if wrapper and leading[0].split()[-1].casefold() != wrapper[1].casefold():
        return hold("issuer-scope-unbound")
    if _issuer_name_key(leading[1]) != root:
        return hold("issuer-scope-unbound")
    if leading[2].casefold() not in {"schedule of certain subsidiaries", "list of subsidiaries"}:
        return hold("issuer-scope-unbound")
    stated = re.fullmatch(r"(?:at|as of) ([A-Za-z]+ [0-9]{1,2}, [0-9]{4})", leading[3], re.I)
    if not stated:
        return hold("invalid-exhibit-as-of-date")
    try:
        stated_day = datetime.strptime(stated[1], "%B %d, %Y").date().isoformat()
    except ValueError:
        return hold("invalid-exhibit-as-of-date")
    if stated_day != result["periodEnd"]:
        result["statedAsOf"] = stated_day
        return hold("exhibit-as-of-differs-from-period-end")

    header = trs[header_i].find_all(["th", "td"], recursive=False)
    header_values = [_norm(cell.get_text(" ", strip=True)) for cell in header]
    roles = [_header_role(value) for value in header_values]
    if (roles.count("name") != 1 or roles.count("jurisdiction") != 1
            or roles.index("name") >= roles.index("jurisdiction")
            or any(value and role is None for value, role in zip(header_values, roles))
            or any(cell.get("rowspan") or cell.get("colspan") != header[0].get("colspan")
                   for cell in header)):
        return hold("ambiguous-row-binding")
    if len(trs) - header_i - 1 > _MAX_ROWS:
        return hold("row-limit")
    for tr in trs[header_i + 1:]:
        cells = tr.find_all(["th", "td"], recursive=False)
        if (len(cells) != len(header) or any(cell.get("rowspan") or
                cell.get("colspan") != header[i].get("colspan") for i, cell in enumerate(cells))):
            return hold("ambiguous-row-binding")
        values = [_norm(cell.get_text(" ", strip=True)) for cell in cells]
        if (not values[roles.index("name")] or not values[roles.index("jurisdiction")]
                or any(values[i] for i, role in enumerate(roles) if role is None)
                or "%" in " ".join(values)):
            return hold("ambiguous-row-binding")
    return header_i, roles


def _parse_exhibit_columns(raw_html, metadata):
    """Parse explicit subsidiary/name and jurisdiction columns without ownership inference."""
    cik, accession, filed, period, url, proof = _metadata(metadata)
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
    result = {"schema": "sec-company-subsidiaries-v1", "parserRevision": PARSER_REVISION, "cik": cik,
              "accession": accession, "filedDate": filed, "periodEnd": period,
              "url": url, "documentSha256": hashlib.sha256(raw).hexdigest(),
              "scope": "reported-subsidiary-list-not-exhaustive", "rows": [], "status": "needs-review"}
    if proof is not None:
        result["cofilerProof"] = proof
    if _VIE_MARKER.search(html):
        result["reviewReason"] = "vie-scope-needs-review"
        return result
    candidates = []
    country_table = None
    registrant_header = False
    blank_name_header = False
    embedded_title = False
    all_tables = soup.find_all("table")
    for table in all_tables:
        trs = table.find_all("tr")
        if not trs:
            continue
        for hi, tr in enumerate(trs[:3]):
            cells = tr.find_all(["th", "td"], recursive=False)
            roles = [_header_role(_norm(cell.get_text(" ", strip=True))) for cell in cells]
            if (len(cells) == 2 and
                    [_norm(cell.get_text(" ", strip=True)).casefold() for cell in cells]
                    == ["company name", "country"]):
                candidates.append((table, trs, hi, ["name", "jurisdiction"]))
                country_table = table
                break
            if "name" in roles and "jurisdiction" in roles:
                candidates.append((table, trs, hi, roles))
                if any(_norm(cell.get_text(" ", strip=True)).casefold() in {
                        "state incorporated", "country or state of organization"} for cell in cells):
                    registrant_header = True
                break
            if (len(all_tables) == 1 and len(cells) == 2 and not _norm(cells[0].get_text(" ", strip=True))
                    and roles[1] == "jurisdiction"):
                # A missing Name label is recoverable only for one issuer-bound
                # two-column exhibit; validate its title and physical rows below.
                candidates.append((table, trs, hi, ["name", "jurisdiction"]))
                blank_name_header = True
                break
    if not candidates:
        if not all_tables:
            statement = _statement_list(soup, metadata, result)
            if statement is not None:
                return statement
        elif len(all_tables) == 1:
            flat_table = _flat_issuer_table(soup, all_tables[0], metadata, result)
            if flat_table is not None:
                if flat_table["status"] == "parsed" and not _check_exhibit_as_of(soup, period, flat_table):
                    flat_table["status"] = "needs-review"
                    flat_table["rows"] = []
                return flat_table
            leading = _leading_title_table(soup, all_tables[0], metadata, result)
            if isinstance(leading, dict):
                return leading
            if leading is not None:
                trs = all_tables[0].find_all("tr")
                candidates.append((all_tables[0], trs, leading[0], leading[1]))
                embedded_title = True
        if not candidates:
            result["reviewReason"] = "explicit-name-jurisdiction-header-missing"
            return result
    # Downstream currently dates relationships with periodEnd. An explicit
    # different exhibit date must not silently inherit the financial year end.
    prefix = []
    for node in soup.descendants:
        if node is candidates[0][0]:
            break
        if (isinstance(node, NavigableString) and not isinstance(node, Comment)
                and not node.find_parent(["head", "style", "script"])):
            prefix.append(str(node))
    heading_text = _norm(" ".join(prefix))
    root = _issuer_name_key(metadata.get("issuerName"))
    root_pattern = _issuer_title_pattern(root) if root else None
    heading = _issuer_name_key(heading_text) or ""
    # AIR states the registrant before "Subsidiaries" and repeats headers on
    # each page. Require that complete title, not merely a name prefix.
    root_first_title = bool(root and re.search(
        r"(?:^|\b)" + root_pattern + r" subsidiaries(?= as of |$)", heading)
        and not re.search(r"\b(?:former|previous|non|not|disposed|sold)\b", heading))
    root_first_title = root_first_title or embedded_title
    registrant_title = bool(root and re.search(
        r"\b" + root_pattern + r" subsidiaries of the registrant(?= |$)", heading)
        and not re.search(r"\b(?:former|previous|non|not|disposed|sold)\b", heading))
    issuer_title = bool(root and re.search(
        r"\bsubsidiaries of " + root_pattern + r"(?= as of |$)", heading)
        and not re.search(r"\b(?:former|previous|non|not|disposed|sold)\b", heading))
    if blank_name_header:
        title = r"subsidiaries of " + root_pattern if root else ""
        if (not root or not (re.fullmatch(title, heading) or
                             re.search(r"\bexhibit (?:21|211) " + title + r"$", heading))
                or re.search(r"\b(?:former|previous|non|not|disposed|sold)\b", heading)):
            result["reviewReason"] = "issuer-scope-unbound"
            return result
        header_cells = candidates[0][1][candidates[0][2]].find_all(["th", "td"], recursive=False)
        spans = [cell.get("colspan") for cell in header_cells]
        if any(len(cells := tr.find_all(["th", "td"], recursive=False)) != 2 or
               [cell.get("colspan") for cell in cells] != spans or
               any(cell.get("rowspan") for cell in cells)
               for tr in candidates[0][1][candidates[0][2]:]):
            result["reviewReason"] = "ambiguous-row-binding"
            return result
        # The observed omission note limits completeness. Any other following
        # text could change the table's issuer or relationship scope.
        last = list(all_tables[0].descendants)[-1]
        following = _norm(" ".join(str(node) for node in last.next_elements
                                   if isinstance(node, NavigableString) and not isinstance(node, Comment)
                                   and not node.find_parent(["head", "style", "script"])))
        omission = (r"\* Pursuant to Item 601\(b\)\(21\)\(ii\) of Regulation S-K, the names of "
                    r"other subsidiaries of " + re.escape(metadata["issuerName"]) +
                    r" are omitted because, considered in the aggregate, they would not constitute "
                    r"a significant subsidiary as of the end of the year covered by this report\.")
        if following and not re.fullmatch(omission, following, re.I):
            result["reviewReason"] = "continuation-scope-text"
            return result
    if registrant_header and not registrant_title:
        result["reviewReason"] = "issuer-scope-unbound"
        return result
    if registrant_header:
        root_first_title = True
    if country_table is not None:
        # The country-only header is eligible only under the registrant's own
        # explicit exhibit title. Do not infer the issuer from URL or row names.
        if (len(candidates) != 1 or candidates[0][0] is not country_table or
                all_tables[0] is not country_table or not root or
                not re.search(r"\b" + root_pattern + r" foreign and domestic subsidiaries(?= |$)", heading) or
                re.search(r"\b(?:former|previous|non|not|disposed|sold|subsidiaries of)\b", heading)):
            result["reviewReason"] = "issuer-scope-unbound"
            return result
        first_trs = candidates[0][1]
        if any(len(cells := tr.find_all(["th", "td"], recursive=False)) != 2 or
               any(cell.get("colspan") or cell.get("rowspan") for cell in cells)
               for tr in first_trs):
            result["reviewReason"] = "ambiguous-row-binding"
            return result
        root_first_title = True
        for table in all_tables[1:]:
            trs = table.find_all("tr")
            if (table.find_parent("table") is not None or not trs or
                    any(len(cells := tr.find_all(["th", "td"], recursive=False)) != 2 or
                        any(cell.get("colspan") or cell.get("rowspan") for cell in cells) or
                        not all(_norm(cell.get_text(" ", strip=True)) for cell in cells)
                        for tr in trs)):
                result["reviewReason"] = "continuation-headers-differ"
                return result
            candidates.append((table, trs, -1, ["name", "jurisdiction"]))
    # A dated footnote after the tables also constrains the exhibit's as-of
    # time. Check the entire visible body, not just the first table's title.
    if not _check_exhibit_as_of(soup, period, result):
        return result
    if any(table.find_parent("table") is not None for table, *_ in candidates):
        result["reviewReason"] = "nested-table-scope"
        return result
    if len(candidates) > 1:
        # Repeated page headers are a continuation only when the document names
        # this registrant and no intervening text changes the table's scope.
        # Similar-looking tables for multiple parents must remain quarantined.
        root = _issuer_name_key(metadata.get("issuerName"))
        prefix = []
        for node in soup.descendants:
            if node is candidates[0][0]:
                break
            if (isinstance(node, NavigableString) and not isinstance(node, Comment)
                    and not node.find_parent(["head", "style", "script"])):
                prefix.append(str(node))
        heading = _issuer_name_key(_norm(" ".join(prefix))) or ""
        registrant_page_title = bool(not root_first_title and not registrant_header and registrant_title and re.search(
            r"\b" + root_pattern + r" subsidiaries of the registrant$", heading))
        if (not root or re.search(r"\b(?:former|previous|non|not|disposed|sold)\b", heading)
                or not (root_first_title or registrant_page_title or
                        re.search(r"\bsubsidiaries of " + root_pattern + r"(?= as of |$)", heading))):
            result["reviewReason"] = "multiple-tables-issuer-scope-unbound"
            return result
        if country_table is None:
            headers = []
            for table, trs, header_i, roles in candidates:
                if table.find_parent("table") is not None:
                    result["reviewReason"] = "nested-table-scope"
                    return result
                headers.append([_norm(cell.get_text(" ", strip=True)).casefold()
                                for cell in trs[header_i].find_all(["th", "td"], recursive=False)])
            if any(header != headers[0] for header in headers[1:]):
                result["reviewReason"] = "continuation-headers-differ"
                return result
        for previous, following in zip(candidates, candidates[1:]):
            last = list(previous[0].descendants)[-1]
            gap = []
            for node in last.next_elements:
                if node is following[0]:
                    break
                if isinstance(node, NavigableString) and not isinstance(node, Comment):
                    value = _norm(str(node).replace("\u200b", ""))
                    if value:
                        gap.append(value)
            gap_text = " ".join(gap)
            exhibit_marker = re.fullmatch(r"exhibit\s+(21(?:\.1)?)", gap_text, re.I)
            repeated_exhibit = bool(exhibit_marker and re.search(
                r"\bexhibit\s+" + re.escape(exhibit_marker[1]) + r"(?![\w.])", heading_text, re.I))
            repeated_registrant_title = bool(registrant_header and re.search(
                r"\b" + root_pattern + r" subsidiaries of the registrant exhibit 21(?= |$)", heading)
                and re.fullmatch(root_pattern + r" subsidiaries of the registrant exhibit 21",
                                 _issuer_name_key(gap_text) or ""))
            if gap and not (re.fullmatch(r"(?:page\s*)?[0-9]{1,3}", gap_text, re.I)
                            or repeated_exhibit or repeated_registrant_title):
                result["reviewReason"] = "continuation-scope-text"
                return result
            if country_table is not None:
                # AVT's unheaded country tables are separate pages in the same
                # exhibit, divided by an explicit page-break HR. Adjacent bare
                # two-column tables alone do not inherit the first header.
                def page_container(table):
                    for parent in table.parents:
                        if parent.parent is soup.body:
                            return parent
                    return None

                before, after = page_container(previous[0]), page_container(following[0])
                separator = before.find_next_sibling() if before is not None else None
                if (before is None or after is None or before.name != "div" or after.name != "div"
                        or before.get("style") != after.get("style")
                        or before.find_all("table") != [previous[0]]
                        or after.find_all("table") != [following[0]]
                        or separator is None or separator.name != "hr"
                        or not re.search(r"(?:^|;)\s*page-break-after\s*:\s*always\s*(?:;|$)",
                                         separator.get("style", ""), re.I)
                        or separator.find_next_sibling() is not after):
                    result["reviewReason"] = "continuation-page-break-unbound"
                    return result
    reviewed_tables = {id(table) for table, *_ in candidates}
    for table in all_tables:
        if id(table) in reviewed_tables:
            continue
        for tr in table.find_all("tr"):
            values = [_norm(cell.get_text(" ", strip=True))
                      for cell in tr.find_all(["th", "td"], recursive=False)]
            values = [value for value in values if value]
            if len(values) < 2:
                continue  # Empty layout rows are not another data table.
            if (re.fullmatch(r"\(?[0-9]{1,3}\)?", values[0])
                    and not any(_complete_legal_name(value) for value in values[1:])):
                continue  # Numbered footnote/explanation, not a company row.
            result["reviewReason"] = "unreviewed-exhibit-table"
            return result
    _, _, _, roles = candidates[0]
    name_i, jurisdiction_i = roles.index("name"), roles.index("jurisdiction")
    rows = []
    needs_review = False
    source_rows = [(table_index, row_index, tr)
                   for table_index, (_, trs, header_i, _) in enumerate(candidates)
                   for row_index, tr in enumerate(trs[header_i + 1:], start=header_i + 1)]
    for table_index, row_index, tr in source_rows:
        cells = tr.find_all(["th", "td"], recursive=False)
        if not cells:
            continue
        text = _norm(tr.get_text(" ", strip=True))
        if not text:
            continue
        if _OMIT.search(text):
            # In an issuer-bound list, a populated name/jurisdiction pair may
            # itself contain "Trust", "Foreign", or "Branch". Do not publish
            # the rest of the table after silently discarding that entity.
            if (root_first_title or registrant_title or issuer_title) and country_table is None and \
                    max(name_i, jurisdiction_i) < len(cells):
                omitted_name = _norm(cells[name_i].get_text(" ", strip=True))
                omitted_jurisdiction = _norm(cells[jurisdiction_i].get_text(" ", strip=True))
                label = r"(?:domestic|foreign)(?: subsidiaries)?|(?:sub)?total|footnote|see note|branch"
                if (omitted_name and omitted_jurisdiction and
                        not re.fullmatch(label, omitted_name, re.I)):
                    result["reviewReason"] = "partial-table-row-omission"
                    return result  # rows are local until the entire table passes.
            continue
        if country_table is not None and ("%" in text or re.search(
                r"\b(?:subsidiar(?:y|ies)|ownership|owned)\b", text, re.I)):
            needs_review = True
            continue
        if max(name_i, jurisdiction_i) >= len(cells):
            needs_review = True
            continue
        if registrant_header and _header_role(_norm(cells[name_i].get_text(" ", strip=True))) == "name" and \
                _header_role(_norm(cells[jurisdiction_i].get_text(" ", strip=True))) == "jurisdiction":
            first_header = candidates[0][1][candidates[0][2]].find_all(["th", "td"], recursive=False)
            if any(_norm(cells[index].get_text(" ", strip=True)).casefold() !=
                   _norm(first_header[index].get_text(" ", strip=True)).casefold()
                   for index in (name_i, jurisdiction_i)):
                needs_review = True  # A new intermediate parent changes scope.
            continue  # Exact repeated headers are not company rows either.
        names = _cell_blocks(cells[name_i], name_cell=True)
        jurisdictions = _cell_blocks(cells[jurisdiction_i])
        if not names or len(names) != len(jurisdictions) or len(cells) != len(roles):
            needs_review = True
            continue
        entries = []
        for block_index, (name, jurisdiction) in enumerate(zip(names, jurisdictions)):
            if country_table is not None and jurisdiction not in _OBSERVED_COUNTRY_COLUMN_VALUES:
                needs_review = True  # Unknown Country value needs source review.
                continue
            if (country_table is not None or registrant_header) and re.fullmatch(r"[A-Z]{3}", jurisdiction):
                needs_review = True  # A currency-like code is not country evidence.
                continue
            name = _current_legal_name(name)
            if name is None:
                needs_review = True
                continue
            if (len(candidates) > 1 and registrant_page_title and
                    _LEGAL_TERMINATOR.search(name) and not _complete_legal_name(name)):
                # A complete legal name followed by free text can be two
                # entities or a trade name in one physical cell.
                needs_review = True
                continue
            if "%" in name or re.search(r"\(\s*[0-9]{1,3}\s*\)$", name):
                # Unresolved ownership percentages and numbered footnotes are
                # not part of a verified legal name; retain the exhibit for review.
                needs_review = True
                continue
            marker = _REGISTRANT.search(name)
            if marker:
                root = _issuer_name_key(metadata.get("issuerName"))
                if not root or _issuer_name_key(name[:marker.start()]) != root:
                    needs_review = True
                continue  # Matching registrant is self; unknown/mismatch is quarantined.
            issuer_name = metadata.get("issuerName")
            if isinstance(issuer_name, str) and _norm(name).casefold() == _norm(issuer_name).casefold():
                continue  # Exact stated registrant only; no punctuation/legal-form aliases.
            if root_first_title and _issuer_name_key(name) == root:
                continue  # Title-bound registrant; do not emit a self relationship.
            entries.append((block_index, name, jurisdiction))
        # Matching block counts alone are not proof: a wrapped partial name
        # must not become a separate company. Reject the entire physical row.
        if any(";" in name or (len(_LEGAL_TERMINATOR.findall(name)) > 1 and
               not (len(names) == 1 and (
                   _jurisdiction_qualified_legal_name(name, jurisdiction, metadata.get("issuerName")) or
                   country_table is not None and len(_LEGAL_TERMINATOR.findall(name)) == 2 and
                   _COMPOUND_LEGAL_END.fullmatch(name))))
               or (len(names) > 1 and not _complete_legal_name(name)) for _, name, jurisdiction in entries):
            needs_review = True
            continue
        if any(len(name) > 300 or len(jurisdiction) > 160 or ";" in jurisdiction
               or re.search(r"\b(?:d/b/a|doing business as|formerly known as|f/k/a)\b", name, re.I)
               for _, name, jurisdiction in entries):
            needs_review = True
            continue
        for block_index, name, jurisdiction in entries:
            source_row = {"index": row_index, "text": text}
            if len(candidates) > 1:
                source_row["tableIndex"] = table_index
            if len(names) > 1:
                source_row["blockIndex"] = block_index
            rows.append({"name": name, "jurisdiction": jurisdiction, "ownershipPct": None,
                         "directOwnership": "unspecified", "sourceRow": source_row})
            if len(rows) > _MAX_ROWS:
                result["rows"] = rows[:_MAX_ROWS]
                result["reviewReason"] = "row-limit"
                return result
    result["rows"] = rows
    result["status"] = "parsed" if rows and not needs_review else "needs-review"
    if result["status"] == "needs-review":
        result["reviewReason"] = "ambiguous-row-binding" if needs_review else "no-eligible-subsidiary-rows"
    return result


def _flat_page_text(nodes):
    return _norm(" ".join(str(node) for node in nodes
                          if isinstance(node, NavigableString) and not isinstance(node, Comment)
                          and not node.find_parent(["head", "style", "script"]))).replace("\u200b", "").strip()


def _omission_note(text):
    """Closed completeness limitations, never permission to omit physical rows."""
    day = r"[A-Za-z]+ [0-9]{1,2}, [0-9]{4}"
    return bool(re.fullmatch(
        r"(?:Pursuant to Item 601\(b\)\(21\) of Regulation S-K, we have omitted some "
        r"subsidiaries that, considered in the aggregate as a single subsidiary, would not "
        r"constitute a significant subsidiary as of " + day + r" under Rule 1-02\(w\) of Regulation S-X\."
        r"|The names of certain subsidiaries which, if considered in the aggregate as a single "
        r"subsidiary, would not constitute a [\u201c\"]?significant subsidiary[\u201d\"]? as defined in "
        r"Regulation S-X, have been omitted\."
        r"|Subsidiaries not included on this list, considered in the aggregate as a single "
        r"subsidiary, would not constitute a significant subsidiary as of " + day + r"\.)",
        text, re.I))


def _bound_flat_pages(soup, metadata, result):
    """Read all physical columns/pages under one explicit issuer title.

    Empty spacing columns and a header split across two physical rows do not
    change a name/jurisdiction pair. Extra data columns, scope text and partial
    rows do. Keep original table/row evidence instead of rewriting the HTML.
    """
    tables = soup.find_all("table")
    root = _issuer_name_key(metadata.get("issuerName"))
    if not root or not tables or any(table.find_parent("table") or table.find("table") for table in tables):
        return None
    prefix = []
    for node in (soup.body or soup).descendants:
        if node is tables[0]:
            break
        prefix.append(node)
    heading = _flat_page_text(prefix)
    note = re.search(r"Pursuant to Item 601\(b\)\(21\).*", heading, re.I)
    if note:
        if not _omission_note(note[0]):
            return None
        heading = heading[:note.start()].strip()
    title = _issuer_name_key(heading) or ""
    title = re.sub(r"^exhibit (?:21|210|211) ", "", title)
    issuer = _issuer_title_pattern(root)
    title_pattern = (r"(?:(?:list of |significant |consolidated )?subsidiaries of " + issuer +
                     r"|" + issuer + r" (?:list of |direct and indirect )?subsidiaries(?: of the registrant)?)")
    if not re.fullmatch(title_pattern + r"(?: as of [a-z]+ [0-9]{1,2} [0-9]{4})?", title):
        return None
    if not _check_exhibit_as_of(soup, result["periodEnd"], result):
        return result
    names, rows, first_signature = set(), [], None
    name_headers = {"name", "name of company", "company", "company name", "subsidiary", "subsidiaries",
                    "name of subsidiary", "name of subsidiaries", "name of corporation",
                    "subsidiary name", "entity name", "legal name"}

    def physical(tr):
        values, width = [], 0
        for cell in tr.find_all(["th", "td"], recursive=False):
            span = str(cell.get("colspan", "1"))
            if (cell.get("rowspan") or not re.fullmatch(r"[1-9][0-9]?", span)
                    or cell.find(["table", "sup", "script", "style", "pre"])):
                return None
            blocks = _cell_blocks(cell, name_cell=False)
            if len(blocks) > 1:
                return None
            value = _norm(cell.get_text(" ", strip=True)).replace("\u200b", "").strip()
            values.append((width, int(span), value))
            width += int(span)
        return width, values

    def header(values):
        filled = [(start, span, value) for start, span, value in values if value]
        if len(filled) != 2:
            return None
        left, right = filled
        if (left[2].casefold() not in name_headers or _header_role(right[2]) != "jurisdiction"
                or len(right[2]) > 120 or re.search(r"[%0-9]", right[2])):
            return None
        return left[:2], right[:2]

    for table_i, table in enumerate(tables):
        trs = table.find_all("tr")
        parsed = [physical(tr) for tr in trs]
        if not parsed or any(value is None for value in parsed):
            return None
        nonempty = [i for i, (_, cells) in enumerate(parsed) if any(v for _, _, v in cells)]
        if not nonempty:
            return None
        hi = nonempty[0]
        header_values = parsed[hi][1]
        signature = header(header_values)
        end_header = hi
        if signature is None and hi + 1 < len(parsed) and parsed[hi][0] == parsed[hi + 1][0]:
            a, b = parsed[hi][1], parsed[hi + 1][1]
            if [(x, w) for x, w, _ in a] == [(x, w) for x, w, _ in b]:
                combined = [(x, w, _norm(v + " " + b[j][2])) for j, (x, w, v) in enumerate(a)]
                signature = header(combined)
                header_values = combined
                end_header = hi + 1
        if signature is None:
            return None  # Unheaded continuations need a separate page-binding proof.
        header_signature = (signature, tuple(value.casefold() for _, _, value in header_values if value))
        if first_signature is None:
            first_signature = header_signature
        if header_signature != first_signature:
            return None
        width = parsed[hi][0]
        for ri in range(end_header + 1, len(trs)):
            actual_width, cells = parsed[ri]
            filled = [(start, span, value) for start, span, value in cells if value]
            if not filled:
                continue
            if actual_width != width or len(filled) != 2 or tuple(c[:2] for c in filled) != signature:
                return None
            name, jurisdiction = filled[0][2], filled[1][2]
            if (not re.search(r"\w", name) or len(name) > 300 or len(jurisdiction) > 160
                    or re.search(r"%|[;*\u2020\u2021]|\([0-9]{1,3}\)", name + " " + jurisdiction)
                    or _OMIT.search(name) or re.fullmatch(r"[A-Z]{3}", jurisdiction)
                    or re.search(r"\b(?:subsidiar(?:y|ies)|ownership|owned|parent|formerly|dba|fka|footnote|total)\b|d/b/a|f/k/a", name, re.I)
                    or _header_role(name) is not None or jurisdiction.casefold() in {"jurisdiction", "country"}
                    or (_LEGAL_TERMINATOR.search(name) and not _complete_legal_name(name))
                    or len(_LEGAL_TERMINATOR.findall(name)) > 1 or name in names):
                return None
            if _issuer_name_key(name) == root:
                continue
            names.add(name)
            rows.append({"name": name, "jurisdiction": jurisdiction, "ownershipPct": None,
                         "directOwnership": "unspecified", "sourceRow": {"index": ri,
                         "tableIndex": table_i, "text": _norm(trs[ri].get_text(" ", strip=True))}})
            if len(rows) > _MAX_ROWS:
                return None
        last = list(table.descendants)[-1]
        gap_nodes = []
        for node in last.next_elements:
            if table_i + 1 < len(tables) and node is tables[table_i + 1]:
                break
            gap_nodes.append(node)
        gap = _flat_page_text(gap_nodes)
        if gap and not (table_i == len(tables) - 1 and _omission_note(gap)):
            return None
    if not rows:
        return None
    return {**result, "rows": rows, "status": "parsed"}


def parse_exhibit(raw_html, metadata):
    result = _parse_exhibit_columns(raw_html, metadata)
    if result["status"] == "parsed" and not result.get("cofilerProof"):
        return result
    raw = raw_html.encode("utf-8") if isinstance(raw_html, str) else raw_html
    try:
        html = raw.decode("utf-8", "strict")
    except UnicodeDecodeError:
        html = raw.decode("latin-1")
    soup = BeautifulSoup(html, "html.parser")
    if result.get("cofilerProof"):
        from api.intelligence.company_structure_sec_sections import parse_cofiler_sections, parse_bound_name_list
        # Existing column formats may already parse, but membership in a joint
        # filing alone does not establish which registrant owns that list.
        prefix = []
        for node in (soup.body or soup).descendants:
            if getattr(node, "name", None) == "table":
                break
            prefix.append(node)
        heading = _issuer_name_key(_flat_page_text(prefix)) or ""
        root = _issuer_name_key(metadata.get("issuerName"))
        marker = r"(?:exhibit (?:21|211) )?"
        title = _issuer_title_pattern(root) if root else r"(?!)"
        bound_title = re.fullmatch(marker + r"(?:" + title + r" subsidiaries(?: of the registrant)?|"
                                  r"(?:list of )?subsidiaries of " + title +
                                  r")(?: as of [a-z]+ [0-9]{1,2} [0-9]{4})?", heading)
        if result["status"] == "parsed" and bound_title:
            return result
        for parser in (parse_cofiler_sections, parse_bound_name_list):
            reviewed = parser(soup, metadata, dict(result))
            if reviewed is not None:
                return reviewed
        if not bound_title:
            return {**result, "status": "needs-review", "rows": [],
                    "reviewReason": "cofiler-parent-title-unbound"}
    if result.get("reviewReason") not in {
            "explicit-name-jurisdiction-header-missing", "multiple-tables-issuer-scope-unbound",
            "ambiguous-row-binding", "partial-table-row-omission", "unreviewed-exhibit-table"}:
        return result
    reviewed = _bound_flat_pages(soup, metadata, dict(result))
    if reviewed is not None:
        if reviewed["status"] == "parsed":
            reviewed.pop("reviewReason", None)
        return reviewed
    from api.intelligence.company_structure_sec_sections import parse_unheaded_continuation
    reviewed = parse_unheaded_continuation(soup, metadata, dict(result))
    if reviewed is not None:
        return reviewed
    return result
