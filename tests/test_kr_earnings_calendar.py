"""Official IR dates: exact event fields, corrections, cancellation and provenance."""
from datetime import date
import ast
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from api.collectors.kr_earnings_calendar import parse_notice, select_calendar, list_notices, collect, merge_calendar


def html(purpose='2026년 3분기 경영실적 발표', day='2026-10-30'):
    return (f'<table><tr><td>1. 일시 및 장소</td><td>일시</td><td>{day}</td><td>--:--</td></tr>'
            f'<tr><td>3. 개최목적</td><td>{purpose}</td></tr>'
            '<tr><td>7. 결정일자</td><td>2026-10-14</td></tr>'
            '<tr><td>8. IR 자료</td><td>게재일시</td><td>2026-10-29</td></tr></table>')


def parsed(body=None, receipt='20261014800271', title='기업설명회(IR)개최(안내공시)'):
    return parse_notice(body or html(), {'stock_code': '000270', 'rcept_no': receipt,
                        'rcept_dt': '20261014', 'report_nm': title},
                        'https://dart.fss.or.kr/report/viewer.do?rcpNo=' + receipt,
                        '2026-10-18T00:00:00+09:00')


class OfficialEarningsTests(unittest.TestCase):
    def test_event_date_not_filing_or_materials(self):
        row = parsed()
        self.assertEqual(row['date'], '2026-10-30')
        self.assertFalse(row['is_estimated'])
        self.assertEqual(row['receipt'], '20261014800271')
        self.assertEqual(row['status'], 'confirmed')

    def test_generic_ir_and_monthly_sales_excluded(self):
        for purpose in ['회사소개 및 경영현황 설명', '2026년 9월 판매실적 발표',
                        '기관투자자 NDR 및 3분기 실적 설명']:
            self.assertEqual(parsed(html(purpose))['status'], 'not_earnings')

    def test_ambiguous_or_invalid_dates_not_confirmed(self):
        for day in ['2026-10-30 ~ 2026-11-02', '미정', '2026-02-30']:
            self.assertEqual(parsed(html(day=day))['status'], 'review_required')

    def test_final_corrected_table_wins(self):
        row = parsed(html(day='2026-10-23') + html(), title='[기재정정]기업설명회(IR)개최')
        self.assertEqual(row['date'], '2026-10-30')

    def test_latest_correction_overrides_old(self):
        old = parsed(html(day='2026-10-23'))
        new = parsed(receipt='20261015800271', title='[기재정정]기업설명회(IR)개최')
        doc = {'_meta': {'checked_at': '2026-10-18T00:00:00+09:00'}, 'records': [old, new]}
        self.assertEqual(select_calendar(doc, '000270', date(2026, 10, 18))[0]['date'], '2026-10-30')

    def test_cancellation_or_unknown_new_notice_suppresses_old(self):
        old = parsed()
        for status in ['cancelled', 'review_required']:
            new = dict(old, receipt='20261015800271', status=status)
            doc = {'_meta': {'checked_at': '2026-10-18T00:00:00+09:00'}, 'records': [old, new]}
            self.assertEqual(select_calendar(doc, '000270', date(2026, 10, 18)), [])
        self.assertEqual(parsed(title='기업설명회(IR)개최 취소')['status'], 'cancelled')

    def test_old_observation_not_relabelled_current(self):
        doc = {'_meta': {'checked_at': '2026-10-10T00:00:00+09:00'}, 'records': [parsed()]}
        self.assertEqual(select_calendar(doc, '000270', date(2026, 10, 18)), [])
        self.assertIsNone(select_calendar({}, '000270', date(2026, 10, 18)))
        self.assertIsNone(select_calendar(doc, '005930', date(2026, 10, 18)))

    def test_non_earnings_calendar_is_preserved(self):
        dividend = {'kind': '배당', 'event': '배당 기준일', 'date': '2026-12-31'}
        old = {'kind': '실적', 'event': '실적발표', 'date': '2026-10-23'}
        self.assertEqual(merge_calendar([dividend, old], []), [dividend])
        self.assertEqual(merge_calendar([dividend, old], [parsed()]), [dividend, parsed()])

    def test_budget_deferral_is_explicit_and_suppresses_old_date(self):
        filing = {'stock_code': '000270', 'rcept_no': '20261015800271',
                  'rcept_dt': '20261015', 'report_nm': '[정정]기업설명회'}
        with patch('api.collectors.kr_earnings_calendar.list_notices',
                   return_value=([filing], 1, 1)):
            doc = collect('test', {'records': [parsed()]}, today=date(2026,10,18), max_notices=0)
        self.assertEqual(doc['_meta']['notices_deferred'], 1)
        self.assertEqual(doc['_meta']['errors'][0]['error_type'], 'budget_deferred')
        self.assertEqual(select_calendar(doc, '000270', date(2026,10,18)), [])

    def test_listing_pagination_and_no_data_distinct_from_failure(self):
        session = Mock()
        a, b = Mock(), Mock()
        a.json.return_value = {'status': '000', 'total_page': 2, 'list': []}
        filing = {'stock_code': '000270', 'report_nm': '기업설명회(IR)개최'}
        b.json.return_value = {'status': '000', 'total_page': 2, 'list': [filing]}
        session.get.side_effect = [a, b]
        rows, count, pages = list_notices('test', session, date(2026, 10, 18))
        self.assertEqual((rows, count, pages), ([filing], 1, 2))
        session.get.side_effect = None
        session.get.return_value.json.return_value = {'status': '020'}
        with self.assertRaises(ValueError):
            list_notices('test', session, date(2026, 10, 18))

    def test_actual_builder_override_block(self):
        from api.builders import stock_report_public_builder as builder
        tree = ast.parse(Path(builder.__file__).read_text())
        loop = next(n for n in ast.walk(tree) if isinstance(n, ast.For)
                    and any(isinstance(x, ast.Assign) and any(isinstance(t, ast.Name)
                    and t.id == 'official' for t in x.targets) for x in n.body))
        start = next(i for i, n in enumerate(loop.body) if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == 'official' for t in n.targets))
        code = compile(ast.Module(body=loop.body[start:start+2], type_ignores=[]), builder.__file__, 'exec')
        for status, expected in [('confirmed', '2026-10-30'), ('cancelled', None)]:
            record = dict(parsed(), status=status)
            from api.collectors.kr_earnings_calendar import merge_calendar
            scope = {'_official_calendar': select_calendar, '_merge_calendar': merge_calendar,
                     'official_earnings': {'_meta': {'checked_at': '2026-10-18T00:00:00+09:00'},
                                           'records': [record]},
                     'tk': '000270', 's': {'calendar': [{'event': '실적발표', 'date': '2026-10-23'}]},
                     'n_cal': 0, '_now_kst': Mock(return_value=Mock(date=lambda: date(2026,10,18)))}
            exec(code, scope)
            if expected:
                self.assertEqual(scope['s']['calendar'][0]['date'], expected)
                self.assertEqual(scope['s']['calendar'][0]['receipt'], record['receipt'])
            else:
                self.assertEqual(scope['s']['calendar'], [])


if __name__ == '__main__':
    unittest.main()
