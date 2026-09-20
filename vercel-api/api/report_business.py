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


def reviewed_overview(ticker, cik, now):
    """Reviewed translations are separate from filing excerpts and expire visibly.

Ticker AND SEC entity must match; an unavailable SEC identity never borrows a
well-known company's profile. This registry does not claim universe coverage.
"""
    import json
    from datetime import date
    from pathlib import Path
    profiles = json.loads((Path(__file__).parent / '_content' / 'report_company_profiles.json').read_text())
    entry = profiles.get(ticker)
    if not entry or str(cik).lstrip('0') != entry['cik']:
        return None
    age = (now.date() - date.fromisoformat(entry['reviewed_at'])).days
    if not 0 <= age <= 180:
        return None
    return {**entry, 'label': f"공식 기업 소개를 검수한 한국어 요약 · 확인 {entry['reviewed_at']}",
            'source': {'text': '기업 소개 원문', 'url': entry['source_url']}}


def company_explanation(document, filing, cik, current):
    """Quote only explicitly dated aggregate historical results within MD&A.

Conservative selection: no segment, regional, forecast or undated paragraphs.
Only complete paragraphs are retained, including any offsetting explanation.
"""
    topics = [('가격', r'price realization|selling prices?|가격'),
              ('물량', r'sales volume|volumes? sold|판매량|물량'),
              ('제품 구성', r'product mix|sales mix|제품 구성'),
              ('비용', r'(?:manufacturing|operating|production|tariff|restructuring) costs?|비용|원가')]
    result = {'excerpts': [], 'source': None, 'topics': [{'label': label, 'refs': []} for label, _ in topics],
              'note': '현재 실적 기간과 맞는 회사 설명 문단 미확보. 영향이 없다는 뜻은 아닙니다.'}
    if not current or not isinstance(document, str) or filing.get('report_date') != current['end']:
        return result
    accession, name = str(filing.get('accession') or ''), str(filing.get('primary_document') or '')
    if not str(cik).isdigit() or not re.fullmatch(r'\d{10}-\d{2}-\d{6}', accession) or not re.fullmatch(r'[\w.-]+\.html?', name):
        return result
    # The quoted filing must be the same document as the current financial row.
    if current.get('accession') != accession:
        return result
    clean = re.sub(r'(?is)<(script|style|ix:header)\b[^>]*>.*?</\1>', ' ', document)
    clean = re.sub(r'(?i)</(?:p|div|tr|h[1-6])>', '\n', clean)
    paragraphs = [re.sub(r'\s+', ' ', p).strip() for p in html.unescape(re.sub(r'<[^>]+>', ' ', clean)).splitlines() if p.strip()]
    anchors = [i for i, p in enumerate(paragraphs) if len(p) < 160 and re.search(r'item\s*2\.?\s*management.s discussion', p, re.I)]
    if not anchors:
        return result
    # Table-of-contents hits precede the actual Item 2; use its final heading.
    body = paragraphs[anchors[-1]+1:]
    from datetime import date
    end = date.fromisoformat(current['end'])
    month = end.strftime('%B')
    date_pattern = rf'{month}\s+{end.day},?\s+{end.year}'
    kind = current['period_kind']
    if kind == 'quarter':
        period_pattern = rf'(?:three months ended\s+{date_pattern})'
        ordinal = {3: 'first', 6: 'second', 9: 'third', 12: 'fourth'}.get(end.month)
        if ordinal and current['start'] == f'{end.year}-{end.month-2:02d}-01':
            period_pattern += rf'|{ordinal}[ -]quarter(?:\s+of)?\s+{end.year}'
    elif kind == 'annual':
        period_pattern = rf'(?:year|twelve months) ended\s+{date_pattern}'
    else:
        count = {6: 'six', 9: 'nine'}.get(end.month)
        if not count or current['start'] != f'{end.year}-01-01':
            return result
        period_pattern = rf'{count} months ended\s+{date_pattern}'
    seen_metrics = set()
    for paragraph in body:
        if re.match(r'Item\s*[3-9]\b', paragraph, re.I):
            break
        metric = re.match(r'^(?:Total |Consolidated )?(sales and revenues|revenues?|net sales|operating profit|operating income|net income)\b', paragraph, re.I)
        reported = re.split(r'\bcompared\b', paragraph, maxsplit=1, flags=re.I)[0]
        if not metric or len(paragraph) > 1600 or not re.search(period_pattern, reported, re.I):
            continue
        if re.search(r'\b(expect|anticipate|forecast|may|could|would|will)\b', paragraph, re.I):
            continue
        cause = re.search(r'\b(?:due to|driven by|reflect(?:s|ed|ing)?|result(?:ed|ing) from)\b', paragraph, re.I)
        if not cause:
            continue
        group = '영업손익' if metric[1].lower().startswith('operating') else '순이익' if metric[1].lower() == 'net income' else '매출'
        if group in seen_metrics:
            continue
        seen_metrics.add(group)
        ref = f'M{len(result["excerpts"])+1}'
        result['excerpts'].append({'id': ref, 'metric': group, 'quote': paragraph,
                                   'period': current['start'] + ' ~ ' + current['end']})
        for topic, (_, pattern) in zip(result['topics'], topics):
            if re.search(pattern, paragraph[cause.start():], re.I):
                topic['refs'].append(ref)
    if result['excerpts']:
        result.update(source={'text': '회사 설명 원문', 'url': f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{name}"},
                      note='회사 공시의 영문 문단을 그대로 발췌했습니다. 해당 기간의 회사 설명이며 독립적으로 입증한 원인이 아닙니다. 항목 미발췌는 영향 없음과 다릅니다.')
    return result
