"""A cached translation must never drift to another issuer, filing or paragraph."""
from copy import deepcopy
from datetime import datetime
import io
import json
from pathlib import Path
import sys

import pytest

API = Path(__file__).resolve().parents[1] / 'vercel-api' / 'api'
sys.path.insert(0, str(API))
from report_translation import attach_translations, korean_reference, translation_key
from report_evidence import analysis_prompt, build_report

ENTRIES = json.loads((API / '_content' / 'report_translations_ko.json').read_text())
NOW = datetime(2026, 9, 20)


@pytest.mark.parametrize('key,entry', ENTRIES.items())
def test_reviewed_text_is_bound_to_issuer_document_and_content(key, entry):
    ticker, url, text = (entry[k] for k in ('ticker', 'source_url', 'original'))
    assert translation_key(ticker, url, text) == key
    translated = korean_reference(ticker, url, text, NOW)
    assert translated['text'] == entry['text_ko']
    assert '비공식' in translated['label']
    assert korean_reference('DIFFERENT', url, text, NOW) is None
    assert korean_reference(ticker, url.replace('000046', '000047'), text, NOW) is None
    assert korean_reference(ticker, url, text.replace('2026', '2027') + ' changed', NOW) is None
    assert korean_reference(ticker, url, text, datetime(2026, 9, 19)) is None
    assert korean_reference(ticker, url, text.replace(' ', '\n '), NOW) == translated


def test_missing_translation_preserves_original_and_denominator():
    entry = next(iter(ENTRIES.values()))
    profile = {'available': True, 'text': entry['original'], 'source': {'url': entry['source_url']}}
    company = {'source': profile['source'], 'excerpts': [{'quote': 'A new unmatched company statement.'}]}
    original = deepcopy(company['excerpts'][0])
    coverage = attach_translations('CAT', profile, company, NOW)
    assert coverage == {'translated': 1, 'total': 2}
    assert company['excerpts'][0] == {**original, 'translation': None}
    assert attach_translations('005930', profile, company, NOW, kr=True) == {'translated': 0, 'total': 0}


def test_translation_and_original_survive_pdf_and_prompt():
    pytest.importorskip('typst')
    PdfReader = pytest.importorskip('pypdf').PdfReader
    from fact_report import _render
    ticker = 'CAT'
    data = build_report(ticker, lambda name: {'stocks': {ticker: {'ticker': ticker}}}
                        if name == 'us_stock_report_public.json' else {}, NOW)
    entry = list(ENTRIES.values())[1]
    quote = {'id': 'M1', 'metric': '매출', 'period': '2026-04-01 ~ 2026-06-30', 'quote': entry['original']}
    data['reading']['company']['excerpts'] = [quote, {**quote, 'id': 'M2', 'quote': 'Untranslated new filing.'}]
    data['reading']['company']['source'] = {'text': '공시 원문', 'url': entry['source_url']}
    data['translation_coverage'] = attach_translations(ticker, data['business_profile'], data['reading']['company'], NOW)
    payload = analysis_prompt(data)
    assert entry['original'] in payload and entry['text_ko'] in payload
    reader = PdfReader(io.BytesIO(_render(data)))
    text = '\n'.join(page.extract_text() for page in reader.pages)
    assert '205억 4,300만 달러' in text and '$20.543 billion' in text
    assert text.index('205억 4,300만 달러') < text.index('$20.543 billion')
    assert '한국어 번역 미준비' in text and 'Untranslated new filing.' in text
    assert '1/2개' in text
    links = [str(a.get_object().get('/A', {}).get('/URI', '')) for page in reader.pages for a in page.get('/Annots', [])]
    assert entry['source_url'] in links
