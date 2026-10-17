"""No network or production writes: provider estimates and stale pattern bounds."""
import ast
import datetime
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
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


class CalendarCheckpointPushTests(unittest.TestCase):
    """Execute the actual two workflow shell steps with Git/network fully mocked."""
    STEPS = ('Preserve only official calendar checkpoint',
             'Apply the same calendar fields to public fallback')

    def run_step(self, name, mode):
        workflow = (Path(__file__).resolve().parents[1] /
                    '.github/workflows/daily_analysis_full.yml').read_text()
        job = workflow.split('\n  calendar_only:\n', 1)[1]
        block = job.split('      - name: ' + name + '\n', 1)[1].split('\n      - ', 1)[0]
        script = textwrap.dedent(block.split('        run: |\n', 1)[1])
        # Functions shadow commands only inside this child shell; no real Git or Node.
        stub = r'''
push_count=0
git() {
  printf '%s\n' "$*" >> "$GIT_LOG"
  if [ "$1" = "-C" ]; then shift 2; fi
  case "$1" in
    diff)
      if [ "$2" = "--name-only" ]; then return 0; fi
      return 1 ;;
    pull)
      if [ "$TEST_MODE" = "conflict" ]; then return 1; fi
      return 0 ;;
    push)
      push_count=$((push_count + 1))
      if [ "$TEST_MODE" = "always_fail" ]; then return 1; fi
      if [ "$push_count" -eq 1 ]; then return 1; fi
      return 0 ;;
    *) return 0 ;;
  esac
}
node() { return 0; }
sleep() { return 0; }
'''
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'data').mkdir()
            (root / 'data/kr_earnings_calendar.json').write_text('{}')
            result = subprocess.run(['bash', '-c', stub + '\n' + script], cwd=tmp,
                                    env=dict(os.environ, GIT_LOG=str(root / 'git.log'), TEST_MODE=mode),
                                    text=True, capture_output=True, timeout=10)
            commands = (root / 'git.log').read_text().splitlines()
        normalized = [line.removeprefix('-C _report_published ') for line in commands]
        self.assertFalse(any('--force' in line or ' -X ' in line or
                             'rebase --abort' in line for line in normalized))
        return result, normalized

    def test_first_push_race_rebases_then_succeeds(self):
        for name in self.STEPS:
            with self.subTest(step=name):
                result, commands = self.run_step(name, 'first_race')
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                self.assertEqual(commands.count('pull --rebase --autostash origin main'), 2)
                self.assertEqual(commands.count('push origin HEAD:main'), 2)

    def test_five_failed_pushes_fail_closed(self):
        for name in self.STEPS:
            with self.subTest(step=name):
                result, commands = self.run_step(name, 'always_fail')
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(commands.count('pull --rebase --autostash origin main'), 5)
                self.assertEqual(commands.count('push origin HEAD:main'), 5)
                self.assertIn('failed after 5 attempts', result.stdout)

    def test_rebase_conflict_stops_before_push(self):
        for name in self.STEPS:
            with self.subTest(step=name):
                result, commands = self.run_step(name, 'conflict')
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(commands.count('pull --rebase --autostash origin main'), 1)
                self.assertEqual(commands.count('push origin HEAD:main'), 0)
                self.assertIn('manual conflict review required', result.stdout)


if __name__ == '__main__':
    unittest.main()
