"""Strict parser for filing-bound, explicitly titled subsidiary sections.

This parser emits only rows from the exact requested parent section. Other
sections are fully checked for scope and row completeness before any rows are
returned. It does not create ownership edges or infer corporate-name aliases.
"""

import re
import unicodedata
from datetime import datetime

from bs4 import Comment, NavigableString, Tag


_EXHIBIT_TITLE = re.compile(r"exhibit\s+21(?:\.1)?", re.IGNORECASE)
_SECTION_PREFIX = re.compile(r"^(?:list\s+of\s+)?subsidiaries\s+of\s+(.+)$", re.IGNORECASE)
_DATE_SUFFIX = re.compile(r"^(.*?)\s+as\s+of\s+([A-Za-z]+\s+\d{1,2},\s*\d{4})$", re.IGNORECASE)
_BOUND_LIST_TITLE = re.compile(r"^subsidiaries\s+of(?:\s+(.+))?$", re.IGNORECASE)
_LEGAL_ENTITY_ENDING = re.compile(
    r"\b(?:incorporated|inc\.?|company|co\.?|corporation|corp\.?|"
    r"limited|ltd\.?|llc|l\.l\.c\.?|lp|l\.p\.)$", re.IGNORECASE
)
_DECORATIVE_RULE = re.compile(r"^_{8,}$")
_NAME_ANNOTATION = re.compile(
    r"\b(?:wholly\s+owned|owned\s+by|subsidiary\s+of|parent\s+company|"
    r"branch|br\.?\s*&\s*sup\.?|organized\s+under|incorporated\s+in)\b",
    re.IGNORECASE,
)
_MULTIPLE_ENTITIES = re.compile(r"\s+(?:and|&|/)\s+(?=[A-Z])")
_ENTITY_TERMINATOR = re.compile(r"\b(?:incorporated|inc|corporation|corp|limited|ltd|llc|lp|l\.p|l\.l\.c)(?=\.?(?:\s|,|$))", re.I)
_OMISSION_NOTE = re.compile(
    r"^omits\s+names\s+of\s+subsidiaries\s+that\s+as\s+of\s+"
    r"([A-Za-z]+\s+\d{1,2},\s*\d{4})\s+were\s+not,\s+in\s+the\s+"
    r"aggregate,\s*[\"“]?significant\s+subsidiaries\.?[\"”]?\.?$",
    re.IGNORECASE,
)


def _text(value):
    value = unicodedata.normalize("NFKC", str(value))
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Cf")
    return " ".join(value.split())


def _issuer_key(value):
    """Normalize typography only; legal suffix words remain significant."""
    value = _text(value).casefold()
    return value.replace(",", "").replace(".", "")


def _as_date(value):
    try:
        return datetime.strptime(_text(value), "%B %d, %Y").date().isoformat()
    except (TypeError, ValueError):
        return None


def _section_title(value):
    match = _SECTION_PREFIX.fullmatch(_text(value))
    if not match:
        return None
    parent = _text(match.group(1))
    date_match = _DATE_SUFFIX.fullmatch(parent)
    stated_date = None
    if date_match:
        parent = _text(date_match.group(1))
        stated_date = _as_date(date_match.group(2))
        if stated_date is None:
            return {"invalid": True}
    if not parent or "%" in parent:
        return {"invalid": True}
    return {"parent": parent, "statedDate": stated_date, "title": _text(value)}


def _visible_events(soup):
    root = soup.body or soup
    events = []
    for node in root.descendants:
        if isinstance(node, Comment):
            continue
        if isinstance(node, Tag) and node.name == "table":
            if node.find_parent("table") is None:
                events.append(("table", node))
            continue
        if not isinstance(node, NavigableString):
            continue
        if node.find_parent(["head", "script", "style", "table"]):
            continue
        value = _text(node)
        if value:
            events.append(("text", value))
    return events


def _table_has_expected_header(table):
    for row in table.find_all("tr"):
        values = [_text(cell.get_text(" ", strip=True)).casefold()
                  for cell in row.find_all(["th", "td"], recursive=False)]
        values = [value for value in values if value]
        if values == ["subsidiary", "jurisdiction"]:
            return True
    return False


def _single_legal_name(name):
    terms = list(_ENTITY_TERMINATOR.finditer(name))
    companies = list(re.finditer(r"\bcompany\b", name, re.I))
    if len(terms) > 1 or len(companies) > 1:
        return False
    if terms and name[terms[0].end():].strip(" .,"):
        return False
    if companies:
        tail = name[companies[0].end():].strip(" ,")
        if tail and not re.fullmatch(r"(?:Inc(?:orporated)?|LLC|L\.L\.C|Ltd|Limited)\.?", tail, re.I):
            return False
    return True


def _parse_table(table):
    if table.find("table") or table.find_parent("table"):
        return None, "nested-table"
    rows = table.find_all("tr", recursive=False)
    if not rows:
        return None, "empty-table"

    header_seen = False
    header_positions = None
    data = []
    for row_index, row in enumerate(rows):
        cells = row.find_all(["th", "td"], recursive=False)
        if not cells:
            return None, "row-without-cells"
        if any(cell.has_attr("rowspan") or cell.has_attr("colspan") for cell in cells):
            return None, "spanned-cells"
        if any(_text(cell.get_text(" ", strip=True)) and (
               cell.find(["br", "sup", "script", "style", "pre"]) or
               len(cell.find_all(["p", "div"])) > 1) for cell in cells):
            return None, "multiple-cell-blocks"
        if any(_text(node) for node in row.find_all(string=True, recursive=False)):
            return None, "unbound-row-text"
        cells_with_text = [(position, _text(cell.get_text(" ", strip=True)))
                           for position, cell in enumerate(cells)]
        nonempty = [(position, value) for position, value in cells_with_text if value]
        positions = [position for position, _ in nonempty]
        values = [value for _, value in nonempty]
        folded = [value.casefold() for value in values]
        if folded == ["subsidiary", "jurisdiction"]:
            if header_seen or data:
                return None, "duplicate-or-late-header"
            header_seen = True
            header_positions = positions
            continue
        if not header_seen:
            if values:
                return None, "missing-section-header"
            continue
        if len(values) != 2:
            return None, "partial-row"
        if positions != header_positions:
            return None, "column-position-mismatch"
        name, jurisdiction = values
        if (not name or not jurisdiction or "%" in name or "%" in jurisdiction or
                len(name) > 300 or len(jurisdiction) > 120 or
                not _single_legal_name(name)):
            return None, "unsafe-or-incomplete-row"
        if any(name.casefold() == prior[0].casefold() for prior in data):
            return None, "duplicate-row"
        source_text = _text(row.get_text(" ", strip=True))
        data.append((name, jurisdiction, source_text, row_index))
        if len(data) > 1000:
            return None, "row-limit"
    if not header_seen:
        return None, "missing-section-header"
    if not data:
        return None, "empty-section"
    return data, None


def _review(result, reason, sections=None):
    updated = dict(result or {})
    updated["status"] = "needs-review"
    updated["rows"] = []
    updated["reviewReason"] = reason
    if sections is not None:
        updated["reviewedSections"] = sections
    return updated


def _cofiler_proof_matches(metadata):
    proof = metadata.get("cofilerProof")
    index_raw = metadata.get("cofilerIndexRaw")
    if not isinstance(proof, dict) or not index_raw:
        return False
    if proof.get("requestedCik") != metadata.get("cik"):
        return False
    if proof.get("accession") != metadata.get("accession"):
        return False
    if _issuer_key(proof.get("issuerName", "")) != _issuer_key(metadata.get("issuerName", "")):
        return False
    if proof.get("exhibitUrl") != metadata.get("url"):
        return False
    return True


def _bound_title_issuer_matches(title_issuer, metadata_issuer):
    """Allow only the requested terminal Co/Company equivalence."""
    title = _text(title_issuer).casefold()
    metadata_name = _text(metadata_issuer).casefold()
    if _issuer_key(title_issuer) == _issuer_key(metadata_issuer):
        return True
    title_match = re.fullmatch(r"(.*?)\s+(?:co\.?|company)", title)
    metadata_match = re.fullmatch(r"(.*?)\s+(?:co\.?|company)", metadata_name)
    if not title_match or not metadata_match:
        return False
    return title_match.group(1) == metadata_match.group(1)


def _flat_leaf_blocks(soup):
    """Collect visible independent paragraph/div/list-item blocks losslessly."""
    root = soup.body or soup
    if root.find("table"):
        return None
    blocks = []
    covered_nodes = set()
    for element in root.find_all(["p", "div", "li"]):
        if element.find(["p", "div", "li"]):
            continue
        if element.find(["a", "br", "sup", "img", "svg", "iframe", "object"]):
            # A <br> is accepted only when it carries no visible text, as in
            # the SEC source's empty spacing blocks.
            if (element.find(["a", "sup", "img", "svg", "iframe", "object"])
                    or element.find("br") and _text(element.get_text(" ", strip=True))):
                return None
        for node in element.descendants:
            if isinstance(node, NavigableString) and not isinstance(node, Comment):
                if _text(node):
                    covered_nodes.add(node)
        value = _text(element.get_text(" ", strip=True))
        if value:
            blocks.append((element, value))

    for node in root.descendants:
        if not isinstance(node, NavigableString) or isinstance(node, Comment):
            continue
        if node.find_parent(["head", "script", "style"]):
            continue
        if _text(node) and node not in covered_nodes:
            return None
    return blocks


def parse_bound_name_list(soup, metadata, result):
    """Parse a fully bound, jurisdiction-free legal-name list or hold it.

    The issuer is taken from the exhibit title and must match filing metadata,
    allowing only terminal ``Co``/``Company`` equivalence. No ownership,
    jurisdiction, or parent-child edge is inferred from the list.
    """
    events = _visible_events(soup)
    has_title_cue = any(
        kind == "text" and (
            value.casefold() == "subsidiaries of" or
            _BOUND_LIST_TITLE.fullmatch(value)
        ) for kind, value in events
    )
    if not has_title_cue:
        return None

    blocks = _flat_leaf_blocks(soup)
    if blocks is None:
        return _review(result, "bound-list-unrecognized-scope")
    values = [value for _, value in blocks]
    title_positions = [index for index, value in enumerate(values)
                       if _BOUND_LIST_TITLE.fullmatch(value) and
                       value.casefold() != "subsidiaries of" and
                       not (index > 0 and values[index - 1].casefold() == "subsidiaries of")]
    split_title_positions = [index for index, value in enumerate(values)
                             if value.casefold() == "subsidiaries of"]
    if not isinstance(metadata, dict) or not _cofiler_proof_matches(metadata):
        return _review(result, "cofiler-proof-mismatch")
    if len(title_positions) + len(split_title_positions) != 1:
        return _review(result, "bound-list-title-scope-invalid")

    title_index = title_positions[0] if title_positions else split_title_positions[0]
    if values[title_index].casefold() == "subsidiaries of":
        if title_index + 1 >= len(values):
            return _review(result, "bound-list-title-incomplete")
        issuer_title = values[title_index + 1]
        data_start = title_index + 2
    else:
        match = _BOUND_LIST_TITLE.fullmatch(values[title_index])
        issuer_title = match.group(1)
        data_start = title_index + 1

    stated_date = None
    date_match = _DATE_SUFFIX.fullmatch(issuer_title or "")
    if date_match:
        issuer_title = _text(date_match.group(1))
        stated_date = _as_date(date_match.group(2))
        if stated_date is None or stated_date != metadata.get("periodEnd"):
            return _review(result, "bound-list-date-mismatch")

    if not _bound_title_issuer_matches(issuer_title or "", metadata.get("issuerName", "")):
        return _review(result, "bound-list-issuer-mismatch")

    # Only an exhibit marker may precede the issuer title. The source uses an
    # underscore-only visual rule after the final row; no other scope text is
    # treated as decoration.
    for value in values[:title_index]:
        if not _EXHIBIT_TITLE.fullmatch(value):
            return _review(result, "bound-list-unrecognized-prefix")

    remaining = values[data_start:]
    if remaining and _DECORATIVE_RULE.fullmatch(remaining[-1]):
        remaining = remaining[:-1]
    if any(_DECORATIVE_RULE.fullmatch(value) for value in remaining):
        return _review(result, "bound-list-unrecognized-scope")

    rows = []
    seen = set()
    for row_index, name in enumerate(remaining, start=1):
        if (len(name) > 300 or "%" in name or "(" in name or ")" in name or
                ";" in name or "\n" in name or "/" in name or
                _NAME_ANNOTATION.search(name) or _MULTIPLE_ENTITIES.search(name) or
                not _single_legal_name(name) or
                _bound_title_issuer_matches(name, metadata.get("issuerName", "")) or
                not _LEGAL_ENTITY_ENDING.search(name)):
            return _review(result, "bound-list-non-name-block")
        key = name.casefold()
        if key in seen:
            return _review(result, "bound-list-duplicate-name")
        seen.add(key)
        source_index = data_start + row_index - 1
        rows.append({
            "name": name,
            "jurisdiction": None,
            "ownershipPct": None,
            "directOwnership": "unspecified",
            "parentTitle": values[title_index] if title_positions else
                           "Subsidiaries of " + values[title_index + 1],
            "parentName": issuer_title,
            "sourceRow": {"index": source_index, "text": name},
        })
        if len(rows) > 1000:
            return _review(result, "row-limit")
    if not rows:
        return _review(result, "bound-list-empty")

    updated = dict(result or {})
    updated["rows"] = rows
    updated["status"] = "parsed"
    updated.pop("reviewReason", None)
    updated["reviewedSections"] = [{
        "parentTitle": rows[0]["parentTitle"],
        "parentName": issuer_title,
        "rowCount": len(rows),
    }]
    return updated


def parse_cofiler_sections(soup, metadata, result):
    """Return None for another layout, else a parsed or needs-review result.

    ``metadata`` is expected to carry the already-verified co-filer index proof
    and raw index. Only exact parent-title matches are returned as rows.
    """
    tables = soup.find_all("table")
    if not tables:
        return None

    events = _visible_events(soup)
    has_section_cue = any(
        kind == "text" and _SECTION_PREFIX.match(_text(value))
        for kind, value in events
    )
    has_expected_header = any(_table_has_expected_header(table) for table in tables)
    if not has_section_cue and not has_expected_header:
        return None

    if not isinstance(metadata, dict) or not _cofiler_proof_matches(metadata):
        return _review(result, "cofiler-proof-mismatch")

    period_end = metadata.get("periodEnd")
    parsed_sections = []
    pending_title = None
    title_count = 0
    footnote_seen = False
    expected_table_index = 0

    for kind, value in events:
        if kind == "text":
            if _EXHIBIT_TITLE.fullmatch(value) and not parsed_sections and pending_title is None and title_count == 0:
                continue
            title = _section_title(value)
            if title is not None:
                if title.get("invalid") or pending_title is not None or footnote_seen:
                    return _review(result, "section-title-scope-invalid", parsed_sections)
                if title.get("statedDate") and title["statedDate"] != period_end:
                    return _review(result, "section-date-mismatch", parsed_sections)
                pending_title = title
                title_count += 1
                continue
            note = _OMISSION_NOTE.fullmatch(value)
            if note:
                note_date = _as_date(note.group(1))
                if (pending_title is not None or footnote_seen or note_date is None or
                        note_date != period_end):
                    return _review(result, "after-text-or-date-mismatch", parsed_sections)
                footnote_seen = True
                continue
            return _review(result, "unrecognized-scope-text", parsed_sections)

        if footnote_seen or pending_title is None:
            reason = "unreviewed-table" if title_count else "missing-section-header"
            return _review(result, reason, parsed_sections)
        data, error = _parse_table(value)
        if error:
            return _review(result, error, parsed_sections)
        parsed_sections.append({
            "tableIndex": expected_table_index,
            "parentTitle": pending_title["title"],
            "parentName": pending_title["parent"],
            "rows": data,
        })
        expected_table_index += 1
        pending_title = None

    if pending_title is not None:
        return _review(result, "section-without-table", parsed_sections)
    if len(parsed_sections) != len(tables):
        return _review(result, "unreviewed-table", parsed_sections)

    requested_parent = _issuer_key(metadata.get("issuerName", ""))
    matches = [section for section in parsed_sections
               if _issuer_key(section["parentName"]) == requested_parent]
    if len(matches) != 1:
        return _review(result, "issuer-scope-unbound", [
            {"tableIndex": section["tableIndex"], "parentTitle": section["parentTitle"],
             "parentName": section["parentName"], "rowCount": len(section["rows"])}
            for section in parsed_sections
        ])

    target = matches[0]
    rows = [{
        "name": name,
        "jurisdiction": jurisdiction,
        "ownershipPct": None,
        "directOwnership": "unspecified",
        "parentTitle": target["parentTitle"],
        "parentName": target["parentName"],
        "sourceRow": {"tableIndex": target["tableIndex"], "index": row_index,
                      "text": source_text},
    } for name, jurisdiction, source_text, row_index in target["rows"]]
    updated = dict(result or {})
    updated["rows"] = rows
    updated["status"] = "parsed"
    updated.pop("reviewReason", None)
    updated["reviewedSections"] = [
        {"tableIndex": section["tableIndex"], "parentTitle": section["parentTitle"],
         "parentName": section["parentName"], "rowCount": len(section["rows"])}
        for section in parsed_sections
    ]
    return updated


def parse_unheaded_continuation(soup, metadata, result):
    """Bind unheaded physical table pages to one exact issuer/header pair.

    Return ``None`` outside this narrow layout. Once its issuer-title/two-page
    shape is recognized, every visible event and physical row must be covered;
    any ambiguity holds the whole exhibit with zero rows.
    """
    from api.intelligence import company_structure_sec as columns

    events = _visible_events(soup)
    tables = [value for kind, value in events if kind == "table"]
    if len(tables) < 2 or len(tables) != len(soup.find_all("table")):
        return None
    visible = [(kind, value) for kind, value in events]
    if len(visible) < 4 or visible[0][0] != "text" or visible[1][0] != "text":
        return None
    if not _EXHIBIT_TITLE.fullmatch(visible[0][1]):
        return None
    title = _section_title(visible[1][1])
    if title is None:
        return None
    if title.get("invalid") or not isinstance(metadata, dict):
        return _review(result, "unheaded-continuation-title-invalid")
    if (soup.body or soup).find(["img", "svg", "iframe", "object", "input", "select", "textarea"]):
        return _review(result, "unheaded-continuation-unbound-media")
    root = columns._issuer_name_key(metadata.get("issuerName"))
    parent = columns._issuer_name_key(title["parent"])
    if not root or not parent or root != parent:
        return _review(result, "unheaded-continuation-issuer-mismatch")
    period = result.get("periodEnd")
    if not period or title["statedDate"] and title["statedDate"] != period:
        return _review(result, "unheaded-continuation-date-mismatch")
    date_result = dict(result)
    if not columns._check_exhibit_as_of(soup, period, date_result):
        return _review(date_result, date_result["reviewReason"])
    if any(kind != "table" for kind, _ in visible[2:]):
        return _review(result, "unheaded-continuation-unbound-text")
    if any(table.find("table") or table.find_parent("table") for table in tables):
        return _review(result, "unheaded-continuation-nested-table")

    name_headers = {"name", "name of company", "company", "company name", "subsidiary",
                    "subsidiaries", "name of subsidiary", "name of subsidiary or organization",
                    "name of subsidiaries", "name of corporation", "subsidiary name",
                    "entity name", "legal name"}
    header_text = None
    signature = None
    width = None
    rows = []
    names = set()

    for table_index, table in enumerate(tables):
        trs = table.find_all("tr")
        if not trs:
            return _review(result, "unheaded-continuation-empty-table")
        if any(cell.find_parent("tr") not in trs for cell in table.find_all(["td", "th"])):
            return _review(result, "unheaded-continuation-orphan-cell")
        # Captions, stray table text, and cells outside physical rows are not
        # silently discarded by BeautifulSoup's row enumeration.
        if any(_text(node) for node in table.find_all(string=True)
               if not isinstance(node, Comment) and
               not node.find_parent(["td", "th"])):
            return _review(result, "unheaded-continuation-unbound-table-text")
        nonblank_seen = False
        for row_index, tr in enumerate(trs):
            cells = tr.find_all(["th", "td"], recursive=False)
            if not cells or any(_text(node) for node in tr.find_all(string=True, recursive=False)):
                return _review(result, "unheaded-continuation-unbound-row")
            physical = []
            position = 0
            for cell in cells:
                span = str(cell.get("colspan", "1"))
                if (cell.get("rowspan") or not re.fullmatch(r"[1-9][0-9]?", span)
                        or cell.find(["table", "sup", "script", "style", "pre"])
                        or (cell.find("br") and (table_index != 0 or nonblank_seen))
                        or len(cell.find_all(["p", "div"])) > 1):
                    return _review(result, "unheaded-continuation-cell-shape")
                value = _text(cell.get_text(" ", strip=True))
                physical.append((position, int(span), value))
                position += int(span)
            filled = [item for item in physical if item[2]]
            if not filled:
                continue
            if len(filled) != 2:
                return _review(result, "unheaded-continuation-partial-row")
            coordinates = tuple(item[:2] for item in filled)
            values = tuple(item[2] for item in filled)
            if table_index == 0 and not nonblank_seen:
                if (values[0].casefold() not in name_headers or
                        columns._header_role(values[1]) != "jurisdiction" or
                        len(values[1]) > 120 or re.search(r"[%0-9]", values[1]) or
                        re.search(r"\b(?:parent|owner|ownership|percent|dba|trade)\b", values[1], re.I)):
                    return _review(result, "unheaded-continuation-header-invalid")
                header_text, signature, width = values, coordinates, position
                nonblank_seen = True
                continue
            if table_index > 0 and not nonblank_seen and values == header_text:
                if coordinates != signature or position != width:
                    return _review(result, "unheaded-continuation-header-shape")
                nonblank_seen = True
                continue
            nonblank_seen = True
            if values == header_text or columns._header_role(values[0]) is not None:
                return _review(result, "unheaded-continuation-header-change")
            if position != width or coordinates != signature:
                return _review(result, "unheaded-continuation-column-change")
            name, jurisdiction = values
            if (len(name) > 300 or len(jurisdiction) > 160 or
                    not re.search(r"\w", name) or
                    re.search(r"%|[;*\u2020\u2021]|\([0-9]{1,3}\)", name + " " + jurisdiction) or
                    columns._OMIT.search(name) or
                    re.search(r"\b(?:subsidiar(?:y|ies)|ownership|owned|parent|formerly|dba|fka|footnote|total|vie)\b|d/b/a|f/k/a", name, re.I) or
                    re.fullmatch(r"[A-Z]{3}", jurisdiction) or
                    jurisdiction.casefold() in {"jurisdiction", "country"} or
                    (columns._LEGAL_TERMINATOR.search(name) and
                     not columns._complete_legal_name(name)) or
                    len(columns._LEGAL_TERMINATOR.findall(name)) > 1 or
                    columns._issuer_name_key(name) == root or name.casefold() in names):
                return _review(result, "unheaded-continuation-unsafe-row")
            names.add(name.casefold())
            rows.append({"name": name, "jurisdiction": jurisdiction,
                         "ownershipPct": None, "directOwnership": "unspecified",
                         "sourceRow": {"index": row_index, "tableIndex": table_index,
                                       "text": _text(tr.get_text(" ", strip=True))}})
            if len(rows) > 1000:
                return _review(result, "row-limit")
        if not nonblank_seen:
            return _review(result, "unheaded-continuation-empty-table")
    if not rows or not any(row["sourceRow"]["tableIndex"] > 0 for row in rows):
        return _review(result, "unheaded-continuation-empty-page")
    updated = dict(result)
    updated.update(status="parsed", rows=rows)
    updated.pop("reviewReason", None)
    return updated
