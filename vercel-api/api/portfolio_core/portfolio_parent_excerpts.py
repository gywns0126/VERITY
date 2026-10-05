"""Closed, text-only parent rows from retained public filing excerpts.

No identity resolution, dates, current ownership, or economic events are inferred.
Offsets refer to the supplied text, not to the original filing's HTML/XML.
"""

import re


_LINES = re.compile(r"[^\r\n]+")
_INTRO = re.compile(
    r"(?:(?:\([0-9]{1,2}\)|[가-하]\.|[0-9]{1,2}\.|-)[ \t]*)?"
    r"(?P<as_of>(?:보고기간(?:종료일|말)|보고서[ \t]*작성기준일|"
    r"당(?:기|분기|반기)말)[ \t]*현재|현재)[ \t]*"
    r"(?:당사|회사|연결회사|연결기업)의[ \t]*"
    r"(?:주요[ \t]*)?특수관계(?:자의?[ \t]*현황|에[ \t]*있는[ \t]*회사의[ \t]*내역)"
    r"(?:은[ \t]*다음과[ \t]*같습니다\.)?"
)
_NAME_BODY = r"[A-Za-z0-9가-힣][A-Za-z0-9가-힣 .·\-]{0,119}?"
_COMPANY = re.compile(
    rf"(?:(?:㈜|\(주\)|주식회사)[ \t]*{_NAME_BODY}|"
    rf"{_NAME_BODY}[ \t]*(?:㈜|\(주\)|주식회사))(?:\(주[0-9]{{1,2}}\))?"
)
_HEADERS = {"구분", "특수관계구분", "특수관계자구분"}
_NEXT_ROLES = {
    "종속기업", "종속회사", "관계기업", "관계회사", "공동기업", "공동회사",
    "기타특수관계자", "기타의특수관계자", "관계기업및공동기업",
}


def extract_related_party_parent_rows(text: str) -> list[dict]:
    """Return exact quoted, reported-parent rows; unsupported layouts yield [].

    Only an immediately adjacent issuer/period introduction followed by a
    two-column header, one corporate-name cell and a distinct next role is read.
    Legal markers and footnotes stay verbatim for the caller's identity gate.
    A missing issuer subject is not supplied from the surrounding document.
    """
    if not isinstance(text, str) or len(text) > 30_000:
        return []
    if any(ord(char) < 32 and char not in "\r\n\t" for char in text):
        return []
    cells = []
    for match in _LINES.finditer(text):
        raw = match.group()
        value = raw.strip()
        if value:
            start = match.start() + len(raw) - len(raw.lstrip())
            cells.append((value, start, start + len(value)))

    rows = []
    for i in range(1, len(cells) - 4):
        # No colspan/period columns or intervening prose may be skipped.
        if "".join(cells[i][0].split()) not in _HEADERS:
            continue
        if "".join(cells[i + 1][0].split()) not in {"회사명", "특수관계자명칭"}:
            continue
        if cells[i + 2][0] != "지배기업":
            continue
        intro = _INTRO.fullmatch(cells[i - 1][0])
        raw_name = cells[i + 3][0]
        next_role = "".join(cells[i + 4][0].split())
        if not intro or not _COMPANY.fullmatch(raw_name) or next_role not in _NEXT_ROLES:
            continue
        if any(word in raw_name.split() for word in ("및", "외", "등", "또는", "와", "과", "and")):
            continue
        if sum(raw_name.count(marker) for marker in ("㈜", "(주)", "주식회사")) != 1:
            continue

        # A second parent row in the same two-column run is not a sole parent.
        j = i + 4
        multiple_parents = False
        while j < len(cells):
            role = "".join(cells[j][0].split())
            if role == "지배기업":
                multiple_parents = True
                break
            if role not in _NEXT_ROLES or j + 1 >= len(cells):
                break
            j += 2
        if multiple_parents:
            continue
        start, end = cells[i - 1][1], cells[i + 4][2]
        quote = text[start:end]
        if len(quote) > 600:
            continue
        rows.append({
            "role": "reported-parent", "raw_name": raw_name,
            "quote": quote, "char_start": start, "char_end": end,
            "as_of_phrase": intro.group("as_of"),
        })
    # Do not choose between conflicting parent tables or resolve name variants.
    return rows if len({row["raw_name"] for row in rows}) <= 1 else []
