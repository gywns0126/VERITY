"""Exercise the real shared publish boundary with all external commands stubbed."""
from pathlib import Path
import os
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CalendarPublishBoundaryTests(unittest.TestCase):
    def boundary(self):
        action = (ROOT / '.github/actions/publish-data/action.yml').read_text()
        marker = '    - name: Reconcile reviewed report cells before both public writes\n'
        block = action.split(marker, 1)[1].split('\n    - name:', 1)[0]
        self.assertNotIn('continue-on-error', block)
        self.assertLess(action.index(marker), action.index('    - name: Deploy to VERITY-data'))
        self.assertLess(action.index(marker), action.index('    - name: Dual-write to Vercel Blob'))
        script = textwrap.dedent(block.split('      run: |\n', 1)[1])
        return script.replace('${{ github.workspace }}', str(ROOT))

    def run_boundary(self, failure='', report_exists=True):
        stub = '''
node() {
  printf '%s\\n' "$*" >> "$CALL_LOG"
  case "$1" in
    *publish_earnings_calendar.cjs) [ "$FAIL_CALENDAR" != "calendar" ] ;;
    *) return 0 ;;
  esac
}
'''
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / '_public_dist').mkdir()
            if report_exists:
                (path / '_public_dist/stock_report_public.json').write_text('{"stocks":[]}')
            result = subprocess.run(['bash', '-e', '-c', stub + self.boundary()
                                     + '\nprintf "public-write-reached\\n" >> "$CALL_LOG"\n'],
                                    cwd=path, capture_output=True, text=True, timeout=10,
                                    env=dict(os.environ, CALL_LOG=str(path / 'calls'),
                                             FAIL_CALENDAR=failure))
            calls = (path / 'calls').read_text().splitlines() if (path / 'calls').exists() else []
        return result, calls

    def test_calendar_validation_precedes_both_targets(self):
        result, calls = self.run_boundary()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('publish_report_financials.cjs --staged-public', calls[1])
        self.assertIn('publish_earnings_calendar.cjs --staged-public', calls[2])
        self.assertEqual(calls[-1], 'public-write-reached')

    def test_calendar_failure_stops_before_any_public_write(self):
        result, calls = self.run_boundary('calendar')
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any('publish_earnings_calendar.cjs' in x for x in calls))
        self.assertNotIn('public-write-reached', calls)

    def test_missing_report_stops_before_source_or_public_operations(self):
        result, calls = self.run_boundary(report_exists=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
