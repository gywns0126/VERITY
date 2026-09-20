"""Reviewed Korean references bound to the exact filing URL and source text.

No runtime translation service. New or amended text stays explicitly untranslated;
financial facts and the original quotation remain authoritative.
"""
import hashlib
import json
import re
from datetime import date
from functools import lru_cache
from pathlib import Path


def translation_key(ticker, source_url, original):
    normalized = re.sub(r'\s+', ' ', original).strip()
    return hashlib.sha256(f'{ticker}\n{source_url}\n{normalized}'.encode()).hexdigest()


@lru_cache(maxsize=1)
def _translations():
    return json.loads((Path(__file__).parent / '_content' / 'report_translations_ko.json').read_text())


def korean_reference(ticker, source_url, original, now):
    key = translation_key(ticker, source_url, original)
    entry = _translations().get(key)
    if not entry or entry['ticker'] != ticker or entry['source_url'] != source_url:
        return None
    if translation_key(ticker, source_url, entry['original']) != key:
        return None
    if date.fromisoformat(entry['reviewed_at']) > now.date():
        return None
    return {'text': entry['text_ko'], 'summary': entry.get('summary_ko', ''),
            'label': '한국어 참고 번역 · 비공식 · 원문 대조 ' + entry['reviewed_at'],
            'source_url': source_url, 'source_fingerprint': key}


def attach_translations(ticker, profile, company, now, kr=False):
    """Only translate the actual displayed excerpts, never whole-filings by proxy."""
    profile['translation'] = None
    coverage = {'translated': 0, 'total': 0}
    if kr:
        return coverage
    items = [(q, 'quote', company['source']) for q in company['excerpts']]
    if profile['available']:
        items.insert(0, (profile, 'text', profile['source']))
    for item, field, source in items:
        coverage['total'] += 1
        item['translation'] = korean_reference(ticker, source['url'], item[field], now)
        if item['translation']:
            coverage['translated'] += 1
    return coverage
