"""Issuer-announced KR earnings IR dates. DART reads only; no model or broker.

The listing window is bounded and reported, never described as all future events.
Only explicit quarterly/annual earnings presentations qualify. Generic IR and
monthly sales notices do not. A newer ambiguous correction suppresses old dates.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import urlencode

from bs4 import BeautifulSoup
import requests

from api.utils.earnings_calendar_selection import select_calendar, merge_calendar

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'data/kr_earnings_calendar.json'
KST = timezone(timedelta(hours=9))
PARSER_VERSION = 1


def parse_notice(html, filing, url, observed_at):
    """Parse the final notice table, not correction before/after or filing date."""
    soup = BeautifulSoup(html, 'html.parser')
    rows = [[c.get_text(' ', strip=True) for c in tr.find_all(['td', 'th'], recursive=False)]
            for tr in soup.find_all('tr')]
    # Last matching field is the current full-form table after correction summary.
    def field(marker):
        found = [r for r in rows if r and marker in re.sub(r'\s+', '', r[0])]
        return found[-1] if found else []
    title = str(filing.get('report_nm') or '')
    purpose = ' '.join(field('개최목적')[1:])
    explanation = ' '.join(field('주요설명회내용')[1:])
    evidence = re.sub(r'\s+', '', purpose + ' ' + explanation)
    result = {
        'ticker': filing.get('stock_code'), 'receipt': filing.get('rcept_no'),
        'filed': filing.get('rcept_dt'), 'report_name': title,
        'source': 'DART issuer IR notice', 'url': url,
        'observed_at': observed_at, 'purpose': purpose,
        'body_sha256': hashlib.sha256(html.encode()).hexdigest(),
        'parser_version': PARSER_VERSION,
    }
    if re.search(r'취소|철회', title + purpose):
        return dict(result, status='cancelled')
    is_earnings = (re.search(r'분기|반기|연간|결산|사업연도', evidence)
                   and re.search(r'(?:경영|영업|재무)?실적', evidence)
                   and '실적발표' in evidence)
    if not is_earnings:
        return dict(result, status='review_required' if '정정' in title else 'not_earnings')
    when = field('일시및장소') or field('일시')
    days = re.findall(r'\b(20\d{2})[-./년]\s*(\d{1,2})[-./월]\s*(\d{1,2})', ' '.join(when))
    if len(days) != 1:
        return dict(result, status='review_required', reason='single_event_date_not_found')
    try:
        day = date(*(int(x) for x in days[0])).isoformat()
    except ValueError:
        return dict(result, status='review_required', reason='invalid_date')
    result.update(status='confirmed', date=day, is_estimated=False,
                  event='실적발표 (회사 공시)', kind='실적',
                  basis='DART 기업설명회 개최 공시 · ' + purpose)
    clock = re.search(r'\b([01]\d|2[0-3]):([0-5]\d)\b', ' '.join(when))
    if clock:
        result['time_kst'] = clock.group(0)
    return result


def fetch_notice(filing, session, observed_at):
    receipt = str(filing.get('rcept_no') or '')
    if not re.fullmatch(r'\d{14}', receipt):
        raise ValueError('invalid_receipt')
    r = session.get('https://dart.fss.or.kr/dsaf001/main.do',
                    params={'rcpNo': receipt}, timeout=25)
    r.raise_for_status()
    r.encoding = 'utf-8'
    matches = re.findall(r'viewDoc\("(\d+)",\s*"(\d+)",\s*"(\d+)",\s*"(\d+)",\s*"(\d+)",\s*"([A-Za-z0-9_.]+)"', r.text)
    match = next((m for m in matches if m[0] == receipt), None)
    if not match:
        raise ValueError('viewer_link_not_found')
    params = dict(zip(('rcpNo', 'dcmNo', 'eleId', 'offset', 'length', 'dtd'), match))
    url = 'https://dart.fss.or.kr/report/viewer.do?' + urlencode(params)
    r = session.get(url, timeout=25)
    r.raise_for_status()
    # DART exchange HTML documents declare EUC-KR, unlike the UTF-8 viewer shell.
    charset = re.search(br'charset\s*=\s*["\x27]?([\w-]+)', r.content[:4096], re.I)
    r.encoding = charset.group(1).decode() if charset else 'euc-kr'
    return parse_notice(r.text, filing, url, observed_at)


def list_notices(api_key, session, today, days=45, corp_code=None):
    if not api_key:
        raise ValueError('DART_API_KEY_missing')
    if not 1 <= days <= 90:
        raise ValueError('listing_days_out_of_bounds')
    params = {'crtfc_key': api_key, 'bgn_de': (today - timedelta(days=days)).strftime('%Y%m%d'),
              'end_de': today.strftime('%Y%m%d'), 'pblntf_ty': 'I',
              'page_count': '100', 'sort': 'date', 'sort_mth': 'desc'}
    if corp_code:
        params['corp_code'] = corp_code
    found, total, pages = [], 0, 1
    for page in range(1, 101):
        r = session.get('https://opendart.fss.or.kr/api/list.json',
                        params=dict(params, page_no=str(page)), timeout=25)
        r.raise_for_status()
        d = r.json()
        if d.get('status') == '013' and page == 1:
            return [], 0, 1
        if d.get('status') != '000':
            raise ValueError('DART_listing_status_' + str(d.get('status')))
        pages = int(d.get('total_page') or 1)
        if pages > 100:
            raise ValueError('listing_page_budget_exceeded')
        batch = d.get('list') or []
        total += len(batch)
        found.extend(x for x in batch if re.fullmatch(r'\d{6}', str(x.get('stock_code') or ''))
                     and '기업설명회' in str(x.get('report_nm') or ''))
        if page >= pages:
            return found, total, pages
        time.sleep(.15)
    raise ValueError('incomplete_listing')


def collect(api_key, previous=None, *, today=None, days=45, corp_code=None, session=None,
            max_notices=500, max_seconds=600):
    started = time.monotonic()
    today = today or datetime.now(KST).date()
    session = session or requests.Session()
    observed = datetime.now(KST).isoformat()
    filings, listing_count, pages = list_notices(api_key, session, today, days, corp_code)
    previous = previous or {}
    records = {r['receipt']: r for r in previous.get('records', [])
               if r.get('receipt') and str(r.get('filed') or '') >= (today-timedelta(days=180)).strftime('%Y%m%d')}
    errors, attempted, reused, deferred = [], 0, 0, 0
    for f in filings:
        rid = f['rcept_no']
        cached = records.get(rid)
        if cached and cached.get('parser_version') == PARSER_VERSION and cached.get('status') != 'review_required':
            reused += 1
            continue
        if attempted >= max_notices or time.monotonic() - started >= max_seconds:
            deferred += 1
            errors.append({'receipt': rid, 'error_type': 'budget_deferred'})
            records[rid] = {'receipt': rid, 'ticker': f.get('stock_code'),
                            'filed': f.get('rcept_dt'), 'report_name': f.get('report_nm'),
                            'status': 'review_required', 'observed_at': observed,
                            'reason': 'budget_deferred'}
            continue
        attempted += 1
        try:
            records[rid] = fetch_notice(f, session, observed)
        except (requests.RequestException, ValueError) as e:
            # No URL/exception text: request exceptions can contain the API key.
            errors.append({'receipt': rid, 'error_type': type(e).__name__})
            records[rid] = {'receipt': rid, 'ticker': f.get('stock_code'),
                            'filed': f.get('rcept_dt'), 'report_name': f.get('report_nm'),
                            'status': 'review_required', 'observed_at': observed}
        time.sleep(.15)
    return {'_meta': {'checked_at': observed, 'window_start': (today-timedelta(days=days)).isoformat(),
                     'window_end': today.isoformat(), 'listing_count': listing_count,
                     'listing_pages': pages, 'ir_candidates': len(filings),
                     'notices_attempted': attempted, 'notices_reused': reused,
                     'notices_deferred': deferred, 'max_notices': max_notices,
                     'max_seconds': max_seconds,
                     'errors': errors, 'scope': 'corp' if corp_code else 'listed_market',
                     'source': 'DART list.json I + original issuer IR notice'},
            'records': sorted(records.values(), key=lambda r: r['receipt'])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default=str(OUTPUT))
    parser.add_argument('--days', type=int, default=45)
    args = parser.parse_args()
    path = Path(args.output)
    previous = json.loads(path.read_text()) if path.exists() else {}
    try:
        doc = collect(os.environ.get('DART_API_KEY', ''), previous, days=args.days)
    except (requests.RequestException, ValueError) as e:
        print('[kr_earnings_calendar] failed:', type(e).__name__)
        return 1  # preserve old artifact and its original timestamp
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as f:
        json.dump(doc, f, ensure_ascii=False)
        tmp = f.name
    os.replace(tmp, path)
    print('[kr_earnings_calendar]', doc['_meta'])
    return 2 if doc['_meta']['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
