"""Bounded, contiguous SEC filing excerpts. No generated paraphrase or table inference.

Uses the segment-description anchors already used by us_filing_probe. This small
public adapter preserves document URL/date instead of importing operator code.
"""
import html
import re


def filing_business(document, filing, cik):
    accession = str(filing.get("accession") or "")
    name = str(filing.get("primary_document") or "")
    if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession) or not re.fullmatch(r"[\w.-]+\.html?", name):
        return {}
    if not str(cik).isdigit() or not isinstance(document, str):
        return {}
    clean = re.sub(r"(?is)<(script|style|ix:header)\b[^>]*>.*?</\1>", " ", document)
    clean = re.sub(r"(?i)</(?:p|div|tr|h[1-6])>", "\n", clean)
    clean = html.unescape(re.sub(r"<[^>]+>", " ", clean))
    clean = re.sub(r"[^\S\n]+", " ", clean)
    paragraphs = [re.sub(r"\s+", " ", p).strip() for p in clean.splitlines()]
    # Prefer descriptions over accounting policy or a flattened numerical table.
    hits = [i for i, p in enumerate(paragraphs) if re.search(
        r"description of segments|(?:we|company|corporation) (?:have|has|operate|operates).*?reportable segments|"
        r"(?:principal|primary) (?:business|products)|(?:our|company.s) business consists", p, re.I)]
    for i in hits:
        selected = "\n\n".join(p for p in paragraphs[i:i+12] if p)
        if len(selected) < 100:
            continue
        excerpt = selected[:2600]
        # Explicitly an excerpt. It is not a complete segment list or mix estimate.
        return {"text": excerpt, "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{name}",
                "fiscal_year": str(filing.get("report_date") or "")[:4], "report": filing.get("form", "SEC 공시") + " 사업·부문 설명 (영문 원문)",
                "filed_at": filing.get("filing_date", ""), "truncated": True,
                "selection": "사업·부문 설명 제목 또는 문장 이후 연속 발췌 · 부문별 비중으로 환산하지 않음"}
    return {}
