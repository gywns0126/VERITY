"""Bounded issuer headlines through the existing RSS search adapter; no AI.

Priority is a disclosed reading order, not a price-impact score. A headline is
not primary-source verification and never earns a confirmed emergency badge.
"""
from datetime import datetime, timedelta, timezone
import re
from urllib.parse import quote, urlparse, parse_qsl, urlencode, urlunparse

if __package__:
    from .stock_news import _name_in_title, _company_headline, _ISSUER_ALIASES
else:
    from stock_news import _name_in_title, _company_headline, _ISSUER_ALIASES

KST = timezone(timedelta(hours=9))
WINDOW_DAYS = 7
LIMIT = 5
_TYPES = [
    ('거래·상장·법적 사건', r'거래\s*정지|상장\s*폐지|파산|회생|trading\s+halt|delist|bankrupt|insolvenc'),
    ('실적·전망', r'실적|매출|영업이익|영업손실|가이던스|earnings|revenue|profit|guidance'),
    ('계약·자금·규제', r'계약|수주|인수|합병|증자|규제|제재|소송|contract|acqui[rs]|merger|financing|regulat|sanction|lawsuit'),
]


def _names(ticker, stock):
    names = []
    for value in [stock.get('name_ko'), stock.get('name'), *_ISSUER_ALIASES.get(ticker, ())]:
        if not isinstance(value, str):
            continue
        name = value.strip()
        # Legal suffix removal only; never shorten to a group name or first word.
        name = re.sub(r'(?:,?\s+(?:Inc\.?|Corp\.?|Corporation|Limited|Ltd\.?|PLC))+$', '', name, flags=re.I).strip()
        if name and name != ticker and name.casefold() not in {n.casefold() for n in names}:
            names.append(name)
    return names


def _article_url(value):
    try:
        u = urlparse(value or '')
        if u.scheme != 'https' or not u.hostname or u.username or u.password or u.path in ('', '/'):
            return ''
        query = [(k, v) for k, v in parse_qsl(u.query) if not k.lower().startswith('utm_')]
        return urlunparse(u._replace(fragment='', query=urlencode(query)))
    except (ValueError, TypeError):
        return ''


def related_news(ticker, stock, fetch, now):
    names = _names(ticker, stock)
    result = {'items': [], 'window_days': WINDOW_DAYS, 'shown': 0, 'matched': 0,
              'received': 0, 'duplicates': 0, 'eligible': 0, 'fetched_at': '', 'status': 'unavailable',
              'window_start': (now - timedelta(days=WINDOW_DAYS)).astimezone(KST).strftime('%Y-%m-%d %H:%M KST'),
              'window_end': now.astimezone(KST).strftime('%Y-%m-%d %H:%M KST'),
              'note': '제목에 회사명이 명시된 최근 7일 기사입니다. 거래·상장·법적 사건 → 실적·전망 → 계약·자금·규제 → 기타 순이며, 같은 분류는 최신순입니다. 제목 분류는 긴급성·중요도·사실 확인의 확정이 아닙니다.'}
    coverage = {'id': 'NW', 'label': '최근 관련 뉴스', 'file': 'Google News RSS', 'status': '해당 종목 자료 미수신',
                'published': '미수신', 'artifact_url': '', 'source': 'Google News RSS · 발행 매체 제목·링크', 'reason': ''}
    if not names:
        coverage['reason'] = '확인된 회사명 미수신'
        return result, coverage
    query = ' OR '.join('"' + n.replace('"', '') + '"' for n in names) + ' when:7d'
    market = 'KR' if ticker.isdigit() else 'US'
    locale = '&hl=ko&gl=KR&ceid=KR:ko' if market == 'KR' else '&hl=en-US&gl=US&ceid=US:en'
    coverage['artifact_url'] = 'https://news.google.com/rss/search?q=' + quote(query) + locale
    try:
        doc = fetch('report-news/' + market + '/' + quote(query, safe=''))
        if not isinstance(doc, dict) or not isinstance(doc.get('items'), list):
            raise ValueError('invalid_news_shape')
        raw = doc['items']
        result['fetched_at'] = str(doc.get('fetched_at') or '')
        coverage['published'] = '조회 ' + (result['fetched_at'] or now.isoformat())
    except Exception as exc:
        coverage.update(status='조회 실패', reason=type(exc).__name__)
        result['note'] = '뉴스를 조회하지 못했습니다. 관련 사건이 없다는 뜻이 아닙니다.'
        return result, coverage
    result['received'] = len(raw)
    rows = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get('title') or '').strip()
        source = str(item.get('source') or '').strip()
        headline = _company_headline(title, source)
        if not any(_name_in_title(n, headline) for n in names):
            continue
        link = _article_url(item.get('url'))
        try:
            # Existing RSS adapter explicitly returns UTC-naive minute strings.
            published = datetime.strptime(item.get('datetime', ''), '%Y.%m.%d %H:%M').replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
        if not link or not source or not (now - timedelta(days=WINDOW_DAYS) <= published <= now):
            continue
        priority, category = next(((i, label) for i, (label, pattern) in enumerate(_TYPES)
                                   if re.search(pattern, headline, re.I)), (len(_TYPES), '기타 관련 보도'))
        rows.append({'title': title, 'source': source, 'url': link, 'category': category,
                     'published_at': published.isoformat(), 'display_time': published.astimezone(KST).strftime('%m.%d %H:%M KST'),
                     'recent_24h': now - published <= timedelta(hours=24), 'priority': priority,
                     'link_label': '기사 열기 · Google 뉴스' if urlparse(link).hostname == 'news.google.com' else '기사 원문 열기',
                     'verification': '기사 본문·사건 미검증'})
    result['matched'] = len(rows)
    seen_urls, seen_titles = set(), set()
    # Same full headline or URL only; do not merge different facts on a shared topic.
    for row in sorted(rows, key=lambda r: (r['priority'], -datetime.fromisoformat(r['published_at']).timestamp())):
        title_key = re.sub(r'\W', '', _company_headline(row['title'], row['source'])).casefold()
        key = (row['published_at'][:10], title_key)
        if row['url'] in seen_urls or key in seen_titles:
            result['duplicates'] += 1
            continue
        seen_urls.add(row['url']); seen_titles.add(key)
        result['items'].append(row)
    result['eligible'] = len(result['items'])
    result['items'] = result['items'][:LIMIT]
    result['shown'] = len(result['items'])
    result['status'] = 'available' if result['shown'] else 'empty'
    coverage['status'] = '수신' if result['shown'] else '해당 종목 자료 미수신'
    coverage['reason'] = f"검색 수신 {len(raw)}건 · 기간·회사명·링크 조건 일치 {len(rows)}건 · 중복 {result['duplicates']}건 · 표시 {result['shown']}/{result['eligible']}건"
    if not result['shown']:
        result['note'] = '최근 7일·회사명·발행 시각·링크 조건을 충족한 기사를 확보하지 못했습니다. 사건이 없다는 뜻은 아닙니다.'
    return result, coverage
