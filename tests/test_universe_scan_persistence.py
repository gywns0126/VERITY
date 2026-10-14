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
        self.write(self.producer, 'data/stock_history/2026-Q4.jsonl', '{"base":1}\n')
        self.write(self.producer, 'byproduct.json', 'base\n')
        self.commit(self.producer, 'base')
        self.run_git(self.producer, 'push', '-u', 'origin', 'main')
        self.run_git(self.root, 'clone', '-b', 'main', str(self.remote), str(self.writer))
        self.configure(self.writer)
        self.write(self.producer, 'data/universe_candidates.json', '{"collected_at":"new"}\n')
        self.write(self.producer, 'data/metadata/analysis_rotation_state.json', '{"cursor":2}\n')
        self.write(self.producer, 'data/stock_history/2026-Q4.jsonl', '{"base":1}\n{"scan":2}\n')
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
        self.write(self.producer, 'data/metadata/data_pipeline_health.json', '{"local": 1}\n')
        self.run_git(self.producer, 'add', '.')
        self.run_git(self.producer, 'commit', '--amend', '--no-edit')
        self.source = self.run_git(self.producer, 'rev-parse', 'HEAD')
        self.push_writer('data/metadata/data_pipeline_health.json', '{"remote": 2}\n')
        with self.assertRaisesRegex(RuntimeError, 'generation changed'):
            module.persist(self.producer, 'main', retry_delay=0)
        self.assertIn('remote', self.remote_text('data/metadata/data_pipeline_health.json'))
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
