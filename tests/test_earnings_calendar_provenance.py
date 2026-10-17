"""No network or production writes: provider estimates and stale pattern bounds."""
import ast
import datetime
from pathlib import Path
import unittest
from unittest.mock import patch

from api.builders import stock_report_public_builder as builder
from api.collectors import earnings_calendar as collector


class EarningsCalendarProvenanceTests(unittest.TestCase):
    def test_provider_is_estimated_and_timestamped(self):
        value = collector._estimated_date('2026-10-30', 'calendar')
        self.assertTrue(value['is_estimated'])
        self.assertEqual(value['provider'], 'Yahoo Finance')
        self.assertIsNotNone(datetime.datetime.fromisoformat(value['observed_at']).tzinfo)

    def test_legacy_provider_date_is_not_promoted_to_confirmed(self):
        with patch.object(builder, '_now_kst', return_value=datetime.datetime(2026, 10, 18)):
            row = builder.build_rich({'ticker': '000270', 'earnings': {
                'next_earnings': '2026-10-23', 'source': 'calendar'}}, {})['calendar'][0]
        self.assertTrue(row['is_estimated'])
        self.assertIn('미확정', row['event'])
        self.assertIn('Yahoo', row['basis'])
        self.assertEqual(row['source'], 'calendar')
        self.assertNotIn('observed_at', row)

    def test_valid_observation_is_preserved(self):
        with patch.object(builder, '_now_kst', return_value=datetime.datetime(2026, 10, 18)):
            row = builder._earnings_calendar_from_rec({'earnings': {
                'next_earnings': '2026-10-30', 'source': 'earnings_dates',
                'observed_at': '2026-10-17T13:00:00+09:00'}})[0]
        self.assertEqual(row['observed_at'], '2026-10-17T13:00:00+09:00')

    def test_past_and_invalid_provider_dates_are_omitted(self):
        with patch.object(builder, '_now_kst', return_value=datetime.datetime(2026, 10, 18)):
            for value in ['2026-09-29', '2026-02-30', 'garbage', None]:
                self.assertEqual(builder._earnings_calendar_from_rec({'earnings': {
                    'next_earnings': value}}), [])

    def test_exhausted_pattern_is_not_returned_as_next_event(self):
        # Execute the actual nested helper without running the publishing main().
        tree = ast.parse(Path(builder.__file__).read_text())
        node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                    and n.name == '_kr_earnings_window')
        namespace = {}
        exec(compile(ast.Module(body=[node], type_ignores=[]), builder.__file__, 'exec'), namespace)
        old = [{'filed': day, 'form': '잠정실적'}
               for day in ['2020-01-01', '2020-04-01', '2020-07-01']]
        self.assertIsNone(namespace['_kr_earnings_window'](old))
        today = datetime.date.today()
        fresh = [{'filed': (today - datetime.timedelta(days=days)).isoformat(), 'form': '잠정실적'}
                 for days in [190, 100, 10]]
        result = namespace['_kr_earnings_window'](fresh)
        self.assertTrue(result['is_estimated'])
        self.assertIn('미대조', result['basis'])


if __name__ == '__main__':
    unittest.main()
