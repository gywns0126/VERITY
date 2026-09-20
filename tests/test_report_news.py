"""Issuer, time, URL and news-source failures must stay visible."""
import io
import sys
from pathlib import Path
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vercel-api' / 'api'))
from report_news import related_news
import stock_news

NOW = datetime(2026, 9, 20, 4, tzinfo=timezone.utc)
STOCK = {'name': 'Caterpillar Inc.', 'name_ko': '캐터필러'}


def article(title='Caterpillar reports earnings', **fields):
    return {'title': title, 'source': 'Example News', 'url': 'https://example.test/article',
            'datetime': '2026.09.20 03:00', **fields}


def news(items, stock=STOCK, ticker='CAT'):
    return related_news(ticker, stock, lambda _: {'items': items, 'fetched_at': NOW.isoformat()}, NOW)


def test_issuer_boundary_publisher_suffix_and_no_bare_ticker_match():
    d, _ = news([article(), article('CAT lovers like this'), article('Other business news - Caterpillar', source='Caterpillar')])
    assert d['shown'] == 1
    d, _ = news([article('삼성전자서비스 실적'), article('삼성전자는 실적 발표')], {'name': '삼성전자'}, '005930')
    assert d['shown'] == 1 and d['items'][0]['title'] == '삼성전자는 실적 발표'


def test_old_future_missing_time_and_unsafe_link_are_not_recent_news():
    d, _ = news([article(datetime='2026.09.12 03:00'), article(datetime='2026.09.20 05:00'),
                  article(datetime=''), article(url='javascript:alert(1)'), article(source='')])
    assert d['status'] == 'empty' and d['shown'] == 0


def test_reading_priority_then_time_and_exact_duplicate_removal():
    rows = [article('Caterpillar launches a product', url='https://example.test/product'),
            article('Caterpillar earnings', datetime='2026.09.19 03:00', url='https://example.test/earnings'),
            article('Caterpillar trading halt', datetime='2026.09.18 03:00', url='https://example.test/halt'),
            article('Caterpillar earnings', datetime='2026.09.19 02:00', url='https://other.test/earnings')]
    d, c = news(rows)
    assert [r['category'] for r in d['items']] == ['거래·상장·법적 사건', '실적·전망', '기타 관련 보도']
    assert d['duplicates'] == 1 and d['matched'] == 4 and d['eligible'] == 3
    assert d['items'][-1]['recent_24h'] and not d['items'][0]['recent_24h']
    assert '확정이 아닙니다' in d['note'] and c['status'] == '수신'


def test_source_failure_is_not_an_empty_success_and_does_not_leak_message():
    def fail(_):
        raise TimeoutError('private failure detail')
    d, c = related_news('CAT', STOCK, fail, NOW)
    assert d['status'] == 'unavailable' and c['status'] == '조회 실패'
    assert c['reason'] == 'TimeoutError' and 'private failure' not in str((d, c))


def test_rss_strict_mode_reports_failure_without_changing_existing_consumers(monkeypatch):
    monkeypatch.setattr(stock_news.requests, 'get', lambda *a, **k: SimpleNamespace(ok=False))
    assert stock_news._fetch_google_news('Caterpillar') == []
    with pytest.raises(RuntimeError):
        stock_news._fetch_google_news('Caterpillar', strict=True)


def test_news_headline_time_and_clickable_url_survive_pdf_and_prompt():
    pytest.importorskip('typst')
    from pypdf import PdfReader
    from report_evidence import build_report, analysis_prompt
    from fact_report import _render
    def fetch(name):
        if name == 'us_stock_report_public.json':
            return {'stocks': {'CAT': STOCK}}
        if name.startswith('report-news/'):
            return {'items': [article()], 'fetched_at': NOW.isoformat()}
        return {}
    d = build_report('CAT', fetch, NOW)
    pdf = PdfReader(io.BytesIO(_render(d)))
    text = '\n'.join(p.extract_text() for p in pdf.pages)
    links = [str(a.get_object().get('/A', {}).get('/URI', '')) for p in pdf.pages for a in p.get('/Annots', [])]
    assert 'Caterpillar reports earnings' in text and '09.20 12:00 KST' in text
    assert 'https://example.test/article' in links and 'https://example.test/article' in analysis_prompt(d)
    assert next(c for c in d['coverage'] if c['id'] == 'NW')['status'] == '수신'
