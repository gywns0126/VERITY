import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('context', ROOT / 'api/intelligence/operator_context.py')
ctx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ctx)


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'repo'
        self.runtime = Path(self.tmp.name) / 'runtime'
        self.write('api/intelligence/ticker_facts.py', "CORE_FILES=[('prices.json','price')]\nSCAN_FILES=[]\nLOCAL_FILES=[('data/facts.json','facts',True)]\nPRIVATE_FILES=[('_operator/private.json','private')]\n")
        self.write('scripts/upload_operator_data_to_supabase.py', 'UPLOADS=[]\n')
        self.write('data/prices.json', json.dumps({'as_of': '2026-09-07T12:00:00+00:00', 'stocks': {'EXAMPLE': {'price': 0}}}))
        self.write('data/facts.json', json.dumps({'EXAMPLE': list(range(100))}))

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)

    def test_repeat_has_no_changes_and_same_snapshot(self):
        a = ctx.snapshot(self.root, self.runtime)
        b = ctx.snapshot(self.root, self.runtime)
        self.assertEqual(a['snapshot_id'], b['snapshot_id'])
        self.assertEqual(b['changes'], [])
        self.assertEqual(sum(b['coverage'].values()), b['total'])

    def test_missing_and_not_requested_are_distinct(self):
        snap = ctx.snapshot(self.root, self.runtime)
        states = {r['id']: r['status'] for r in snap['entries']}
        self.assertEqual(states['source:PRIVATE_FILES:_operator/private.json'], 'not_requested')
        self.assertEqual(states['registry:data/metadata/model_registry.json'], 'missing')

    def test_full_array_can_be_retrieved_without_trim(self):
        snap = ctx.snapshot(self.root, self.runtime)
        row = next(r for r in snap['entries'] if r['path'] == 'data/facts.json')
        result = ctx.get_evidence(self.root, snap, row['id'], row['content_version'], '/EXAMPLE', 80, 20)
        self.assertEqual(result['data'], list(range(80, 100)))
        self.assertEqual(result['total'], 100)
        self.assertIsNone(result['next_offset'])

    def test_changed_evidence_is_rejected(self):
        snap = ctx.snapshot(self.root, self.runtime)
        row = next(r for r in snap['entries'] if r['path'] == 'data/facts.json')
        self.write('data/facts.json', '{}')
        with self.assertRaisesRegex(ValueError, 'source_changed'):
            ctx.get_evidence(self.root, snap, row['id'], row['content_version'])

    def test_deletion_correction_and_new_source_are_visible(self):
        ctx.snapshot(self.root, self.runtime)
        (self.root / 'data/facts.json').unlink()
        self.write('data/prices.json', '{"corrected": true}')
        self.write('api/quant/new_formula.py', 'answer=1')
        snap = ctx.snapshot(self.root, self.runtime)
        changed = {r['id']: r for r in snap['changes']}
        self.assertEqual(changed['source:LOCAL_FILES:data/facts.json']['after']['status'], 'missing')
        self.assertIn('source:CORE_FILES:prices.json', changed)
        self.assertEqual(changed['code:api/quant/new_formula.py']['kind'], 'added')

    def test_freshness_expires_without_content_change(self):
        key = 'source:CORE_FILES:prices.json'
        now = datetime(2026, 9, 7, 13, tzinfo=timezone.utc)
        ctx.snapshot(self.root, self.runtime, {key: 2}, now)
        snap = ctx.snapshot(self.root, self.runtime, {key: 2}, now + timedelta(hours=3))
        changed = next(r for r in snap['changes'] if r['id'] == key)
        self.assertEqual(changed['fields'], ['freshness'])
        self.assertEqual(changed['after']['freshness'], 'stale')

    def test_generated_time_is_not_observation_time(self):
        self.assertIsNone(ctx.source_time({'_meta': {'generated_at': ctx.stamp()}}))

    def test_review_cas_and_input_version(self):
        snap = ctx.snapshot(self.root, self.runtime)
        review = dict(reviewed_at=ctx.stamp(), snapshot_id=snap['snapshot_id'], summary='keep',
                      evidence_ids=[], coverage={'reviewed': 0}, invalidators=['changed facts'])
        result = ctx.save_review(self.runtime, None, review)
        self.assertFalse(result['orders_authorized'])
        with self.assertRaisesRegex(ValueError, 'review_version_conflict'):
            ctx.save_review(self.runtime, None, review)
        self.write('data/facts.json', '{"new":1}')
        ctx.snapshot(self.root, self.runtime)
        with self.assertRaisesRegex(ValueError, 'snapshot_version_conflict'):
            ctx.save_review(self.runtime, result['version'], review)

    def test_symlink_outside_workspace_is_rejected(self):
        outside = Path(self.tmp.name) / 'outside.json'
        outside.write_text('{"private":1}')
        (self.root / 'data/facts.json').unlink()
        (self.root / 'data/facts.json').symlink_to(outside)
        snap = ctx.snapshot(self.root, self.runtime)
        row = next(r for r in snap['entries'] if r['path'] == 'data/facts.json')
        self.assertEqual(row['status'], 'error')

    def test_failed_capture_preserves_previous_raw_source(self):
        facts = self.root / 'api/intelligence/ticker_facts.py'
        facts.write_text(facts.read_text() + '\nBLOB="https://example.test"\ndef _fetch_json(url): return None\n')
        cache = self.root / '.cache/operator_context' / (ctx.hashlib.sha256(b'prices.json').hexdigest() + '.json')
        ctx.atomic_json(cache, {'previous': True})
        with self.assertRaisesRegex(ValueError, 'previous_evidence_preserved'):
            ctx.capture(self.root, 'source:CORE_FILES:prices.json')
        self.assertEqual(ctx.read_json(cache), {'previous': True})

    def test_review_rejects_invalid_cash_and_overallocated_percentages(self):
        snap = ctx.snapshot(self.root, self.runtime)
        review = dict(reviewed_at=ctx.stamp(), snapshot_id=snap['snapshot_id'], summary='proposal',
                      evidence_ids=[], coverage={}, invalidators=[])
        for value in (-1, True, float('inf')):
            with self.assertRaises(ValueError):
                ctx.save_review(self.runtime, None, dict(review, target_cash_krw=value))
        with self.assertRaisesRegex(ValueError, 'percentages_exceed'):
            ctx.save_review(self.runtime, None, dict(review, target_rows=[
                dict(ticker='FIRST', target_krw=1, target_pct=60),
                dict(ticker='SECOND', target_krw=1, target_pct=60)]))


if __name__ == '__main__':
    unittest.main()
