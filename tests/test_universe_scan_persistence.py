"""Offline Git regression tests; no scan, credentials, market APIs, or LLM calls."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('persist', ROOT / 'scripts/ci/persist_universe_scan.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.remote = self.root / 'remote.git'
        self.producer = self.root / 'producer'
        self.writer = self.root / 'writer'
        self.run_git(self.root, 'init', '--bare', str(self.remote))
        self.run_git(self.root, 'clone', str(self.remote), str(self.producer))
        self.configure(self.producer)
        self.run_git(self.producer, 'checkout', '-b', 'main')
        self.write(self.producer, 'data/universe_candidates.json', '{"collected_at":"old"}\n')
        self.write(self.producer, 'data/metadata/analysis_rotation_state.json', '{"cursor":1}\n')
        self.health_base = '{\n"scan":0,\n"a":0,\n"b":0,\n"c":0,\n"d":0,\n"macro":0\n}\n'
        self.write(self.producer, 'data/metadata/data_pipeline_health.json', self.health_base)
        self.write(self.producer, 'data/stock_history/2026-Q4.jsonl', '{"base":1}\n')
        self.write(self.producer, module.RUNTIME_LOG_PATH, '{"base":1}\n')
        self.write(self.producer, 'byproduct.json', 'base\n')
        self.commit(self.producer, 'base')
        self.run_git(self.producer, 'push', '-u', 'origin', 'main')
        self.run_git(self.root, 'clone', '-b', 'main', str(self.remote), str(self.writer))
        self.configure(self.writer)
        self.write(self.producer, 'data/universe_candidates.json', '{"collected_at":"new"}\n')
        self.write(self.producer, 'data/metadata/analysis_rotation_state.json', '{"cursor":2}\n')
        self.write(self.producer, 'data/metadata/data_pipeline_health.json', '{"status":"scan"}\n')
        self.write(self.producer, 'data/stock_history/2026-Q4.jsonl', '{"base":1}\n{"scan":2}\n')
        self.write(self.producer, module.RUNTIME_LOG_PATH, '{"base":1}\n{"scan":2}\n')
        self.commit(self.producer, 'scan')
        self.source = self.run_git(self.producer, 'rev-parse', 'HEAD')

    def run_git(self, repo, *args):
        return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.PIPE, text=True).strip()

    def configure(self, repo):
        self.run_git(repo, 'config', 'user.name', 'test')
        self.run_git(repo, 'config', 'user.email', 'test@example.invalid')

    def write(self, repo, path, text):
        f = repo / path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)

    def commit(self, repo, message):
        self.run_git(repo, 'add', '.')
        self.run_git(repo, 'commit', '-m', message)

    def push_writer(self, path='byproduct.json', text='remote\n'):
        self.write(self.writer, path, text)
        self.commit(self.writer, 'concurrent writer')
        self.run_git(self.writer, 'push', 'origin', 'main')

    def remote_text(self, path):
        return self.run_git(self.remote, 'show', f'main:{path}')

    def assert_producer_preserved(self):
        self.assertEqual(self.source, self.run_git(self.producer, 'rev-parse', 'HEAD'))
        self.assertEqual('', self.run_git(self.producer, 'stash', 'list'))
        self.assertEqual('', self.run_git(self.producer, 'diff', '--name-only', '--diff-filter=U'))

    def test_dirty_autostash_conflict_isolated(self):
        self.write(self.producer, 'byproduct.json', 'local dirty\n')
        self.write(self.producer, 'untracked.txt', 'keep\n')
        self.push_writer()
        module.persist(self.producer, 'main', retry_delay=0)
        self.assertEqual('remote', self.remote_text('byproduct.json'))
        self.assertEqual('local dirty\n', (self.producer / 'byproduct.json').read_text())
        self.assertEqual('keep\n', (self.producer / 'untracked.txt').read_text())
        self.assertEqual('{"status":"scan"}\n', (self.producer / 'data/metadata/data_pipeline_health.json').read_text())
        self.assertIn('new', self.remote_text('data/universe_candidates.json'))
        self.assertIn('2', self.remote_text('data/metadata/analysis_rotation_state.json'))
        self.assertIn('scan', self.remote_text('data/stock_history/2026-Q4.jsonl'))
        self.assert_producer_preserved()

    def test_new_remote_generation_rejected(self):
        self.push_writer('data/universe_candidates.json', '{"collected_at":"newest"}\n')
        with self.assertRaisesRegex(RuntimeError, 'generation changed'):
            module.persist(self.producer, 'main', retry_delay=0)
        self.assertIn('newest', self.remote_text('data/universe_candidates.json'))
        self.assert_producer_preserved()

    def test_conflicting_history_fails_without_losing_either_copy(self):
        self.push_writer('data/stock_history/2026-Q4.jsonl', '{"base":1}\n{"other":3}\n')
        with self.assertRaisesRegex(RuntimeError, 'Conflicting scan outputs'):
            module.persist(self.producer, 'main', retry_delay=0)
        self.assertIn('other', self.remote_text('data/stock_history/2026-Q4.jsonl'))
        self.assertIn('scan', (self.producer / 'data/stock_history/2026-Q4.jsonl').read_text())
        self.assert_producer_preserved()

    def test_push_race_retries_from_new_remote(self):
        original = module.git
        raced = False
        def race(repo, *args, **kwargs):
            nonlocal raced
            if args[0] == 'push' and not raced:
                raced = True
                self.push_writer()
            return original(repo, *args, **kwargs)
        with patch.object(module, 'git', side_effect=race):
            module.persist(self.producer, 'main', retry_delay=0)
        self.assertTrue(raced)
        self.assertEqual('remote', self.remote_text('byproduct.json'))
        self.assertIn('new', self.remote_text('data/universe_candidates.json'))
        self.assert_producer_preserved()

    def test_new_generation_arriving_at_push_is_preserved(self):
        original = module.git
        raced = False
        def race(repo, *args, **kwargs):
            nonlocal raced
            if args[0] == 'push' and not raced:
                raced = True
                self.push_writer('data/universe_candidates.json', '{"collected_at":"newest"}\n')
            return original(repo, *args, **kwargs)
        with patch.object(module, 'git', side_effect=race):
            with self.assertRaisesRegex(RuntimeError, 'generation changed'):
                module.persist(self.producer, 'main', retry_delay=0)
        self.assertIn('newest', self.remote_text('data/universe_candidates.json'))
        self.assertIn('new', (self.producer / 'data/universe_candidates.json').read_text())
        self.assert_producer_preserved()

    def test_already_pushed_is_idempotent(self):
        module.persist(self.producer, 'main', retry_delay=0)
        before = self.run_git(self.remote, 'rev-parse', 'main')
        module.persist(self.producer, 'main', retry_delay=0)
        self.assertEqual(before, self.run_git(self.remote, 'rev-parse', 'main'))

    def test_rebased_persistence_retry_is_idempotent(self):
        self.push_writer()
        module.persist(self.producer, 'main', retry_delay=0)
        before = self.run_git(self.remote, 'rev-parse', 'main')
        module.persist(self.producer, 'main', retry_delay=0)
        self.assertEqual(before, self.run_git(self.remote, 'rev-parse', 'main'))
        self.assert_producer_preserved()

    def test_nonoverlapping_snapshot_fields_do_not_merge_generations(self):
        # Git could merge these disjoint fields; snapshot ownership must block it.
        self.write(self.producer, 'data/metadata/analysis_rotation_state.json', '{"local": 1}\n')
        self.run_git(self.producer, 'add', '.')
        self.run_git(self.producer, 'commit', '--amend', '--no-edit')
        self.source = self.run_git(self.producer, 'rev-parse', 'HEAD')
        self.push_writer('data/metadata/analysis_rotation_state.json', '{"remote": 2}\n')
        with self.assertRaisesRegex(RuntimeError, 'generation changed'):
            module.persist(self.producer, 'main', retry_delay=0)
        self.assertIn('remote', self.remote_text('data/metadata/analysis_rotation_state.json'))
        self.assert_producer_preserved()

    def test_shared_health_conflict_keeps_remote_and_persists_scan(self):
        self.write(self.producer, 'byproduct.json', 'local dirty\n')
        self.write(self.producer, 'untracked.txt', 'keep\n')
        self.push_writer('data/metadata/data_pipeline_health.json', '{"status":"macro-newer"}\n')
        module.persist(self.producer, 'main', retry_delay=0)
        self.assertEqual('{"status":"macro-newer"}', self.remote_text('data/metadata/data_pipeline_health.json'))
        self.assertIn('new', self.remote_text('data/universe_candidates.json'))
        self.assertEqual('local dirty\n', (self.producer / 'byproduct.json').read_text())
        self.assertEqual('keep\n', (self.producer / 'untracked.txt').read_text())
        self.assert_producer_preserved()

    def test_uncontested_scan_health_is_still_persisted(self):
        module.persist(self.producer, 'main', retry_delay=0)
        self.assertEqual('{"status":"scan"}', self.remote_text('data/metadata/data_pipeline_health.json'))

    def test_shared_health_nonconflicting_merge_still_keeps_exact_remote(self):
        # Disjoint key edits could merge cleanly; do not retain a hybrid status.
        self.write(self.producer, 'data/metadata/data_pipeline_health.json', self.health_base.replace('"scan":0', '"scan":2'))
        self.run_git(self.producer, 'add', '.')
        self.run_git(self.producer, 'commit', '--amend', '--no-edit')
        self.source = self.run_git(self.producer, 'rev-parse', 'HEAD')
        remote = self.health_base.replace('"macro":0', '"macro":3')
        self.push_writer('data/metadata/data_pipeline_health.json', remote)
        original, applied_codes = module.git, []
        def record_apply(repo, *args, **kwargs):
            result = original(repo, *args, **kwargs)
            if 'cherry-pick' in args and '--no-commit' in args:
                applied_codes.append(result.returncode)
            return result
        with patch.object(module, 'git', side_effect=record_apply):
            module.persist(self.producer, 'main', retry_delay=0)
        self.assertEqual([0], applied_codes)  # The dangerous hybrid would merge cleanly.
        self.assertEqual(remote.strip(), self.remote_text('data/metadata/data_pipeline_health.json'))
        self.assertIn('new', self.remote_text('data/universe_candidates.json'))
        self.assert_producer_preserved()

    def test_shared_health_deletion_is_not_resurrected(self):
        self.run_git(self.writer, 'rm', 'data/metadata/data_pipeline_health.json')
        self.commit(self.writer, 'remove shared diagnostic')
        self.run_git(self.writer, 'push', 'origin', 'main')
        module.persist(self.producer, 'main', retry_delay=0)
        self.assertNotIn('data/metadata/data_pipeline_health.json', self.run_git(self.remote, 'ls-tree', '-r', '--name-only', 'main'))
        self.assertIn('new', self.remote_text('data/universe_candidates.json'))
        self.assert_producer_preserved()

    def test_shared_health_push_race_keeps_latest_remote_exactly(self):
        original = module.git
        raced = False
        def race(repo, *args, **kwargs):
            nonlocal raced
            if args[0] == 'push' and not raced:
                raced = True
                self.push_writer('data/metadata/data_pipeline_health.json', '{"status":"macro-race"}\n')
            return original(repo, *args, **kwargs)
        with patch.object(module, 'git', side_effect=race):
            module.persist(self.producer, 'main', retry_delay=0)
        self.assertTrue(raced)
        self.assertEqual('{"status":"macro-race"}', self.remote_text('data/metadata/data_pipeline_health.json'))
        self.assertIn('new', self.remote_text('data/universe_candidates.json'))
        self.assert_producer_preserved()

    def test_core_conflict_with_shared_health_still_fails_closed(self):
        self.write(self.writer, 'data/metadata/data_pipeline_health.json', '{"status":"macro"}\n')
        self.push_writer('data/universe_candidates.json', '{"collected_at":"newest"}\n')
        before = self.run_git(self.remote, 'rev-parse', 'main')
        with self.assertRaisesRegex(RuntimeError, 'generation changed'):
            module.persist(self.producer, 'main', retry_delay=0)
        self.assertEqual(before, self.run_git(self.remote, 'rev-parse', 'main'))
        self.assert_producer_preserved()

    def test_runtime_and_health_collision_preserves_both_writers(self):
        self.write(self.producer, 'byproduct.json', 'local dirty\n')
        self.write(self.producer, 'untracked.txt', 'keep\n')
        self.write(self.writer, 'data/metadata/data_pipeline_health.json', '{"status":"macro"}\n')
        self.push_writer(module.RUNTIME_LOG_PATH, '{"base":1}\n{"remote":3}\n')
        module.persist(self.producer, 'main', retry_delay=0)
        self.assertEqual('{"status":"macro"}', self.remote_text('data/metadata/data_pipeline_health.json'))
        self.assertEqual('{"base":1}\n{"remote":3}\n{"scan":2}', self.remote_text(module.RUNTIME_LOG_PATH))
        before = self.run_git(self.remote, 'rev-parse', 'main')
        module.persist(self.producer, 'main', retry_delay=0)
        self.assertEqual(before, self.run_git(self.remote, 'rev-parse', 'main'))
        self.assertEqual('local dirty\n', (self.producer / 'byproduct.json').read_text())
        self.assertEqual('keep\n', (self.producer / 'untracked.txt').read_text())
        self.assertIn('new', self.remote_text('data/universe_candidates.json'))
        self.assert_producer_preserved()

    def test_runtime_rewrite_rejected(self):
        self.push_writer(module.RUNTIME_LOG_PATH, '{"remote":3}\n')
        before = self.run_git(self.remote, 'rev-parse', 'main')
        with self.assertRaisesRegex(RuntimeError, 'Remote runtime log.*append-only'):
            module.persist(self.producer, 'main', retry_delay=0)
        self.assertEqual(before, self.run_git(self.remote, 'rev-parse', 'main'))
        self.assert_producer_preserved()

    def test_prepared_runtime_rewrite_and_partial_row_rejected(self):
        for content in ('{"scan":2}\n', '{"base":1}\n{"partial":'):
            self.write(self.producer, module.RUNTIME_LOG_PATH, content)
            self.run_git(self.producer, 'add', module.RUNTIME_LOG_PATH)
            self.run_git(self.producer, 'commit', '--amend', '--no-edit')
            self.source = self.run_git(self.producer, 'rev-parse', 'HEAD')
            with self.assertRaisesRegex(RuntimeError, 'Prepared runtime log.*append-only'):
                module.persist(self.producer, 'main', retry_delay=0)
            self.assert_producer_preserved()

    def test_runtime_push_race_preserves_remote_rows(self):
        original, raced = module.git, False
        def race(repo, *args, **kwargs):
            nonlocal raced
            if args[0] == 'push' and not raced:
                raced = True
                self.write(self.writer, 'data/metadata/data_pipeline_health.json', '{"status":"macro-race"}\n')
                self.push_writer(module.RUNTIME_LOG_PATH, '{"base":1}\n{"race":4}\n')
            return original(repo, *args, **kwargs)
        with patch.object(module, 'git', side_effect=race):
            module.persist(self.producer, 'main', retry_delay=0)
        self.assertTrue(raced)
        self.assertEqual('{"base":1}\n{"race":4}\n{"scan":2}', self.remote_text(module.RUNTIME_LOG_PATH))
        self.assertEqual('{"status":"macro-race"}', self.remote_text('data/metadata/data_pipeline_health.json'))
        self.assert_producer_preserved()

    def test_runtime_duplicate_rows_preserve_multiplicity(self):
        self.write(self.producer, module.RUNTIME_LOG_PATH, '{"base":1}\n{"scan":2}\n{"scan":2}\n')
        self.run_git(self.producer, 'add', module.RUNTIME_LOG_PATH)
        self.run_git(self.producer, 'commit', '--amend', '--no-edit')
        self.source = self.run_git(self.producer, 'rev-parse', 'HEAD')
        self.push_writer(module.RUNTIME_LOG_PATH, '{"base":1}\n{"scan":2}\n')
        module.persist(self.producer, 'main', retry_delay=0)
        self.assertEqual(2, self.remote_text(module.RUNTIME_LOG_PATH).count('{"scan":2}'))
        self.assert_producer_preserved()

    def test_failed_push_exhausts_without_touching_source(self):
        hook = self.remote / 'hooks/pre-receive'
        hook.write_text('#!/bin/sh\nexit 1\n')
        hook.chmod(0o755)
        with self.assertRaisesRegex(RuntimeError, 'retries exhausted'):
            module.persist(self.producer, 'main', attempts=2, retry_delay=0)
        self.assertIn('old', self.remote_text('data/universe_candidates.json'))
        self.assert_producer_preserved()


if __name__ == '__main__':
    unittest.main()
