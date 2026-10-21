"""Offline preservation checks for the isolated scheduled event-study job."""
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    'lake_rebuild', Path(__file__).resolve().parents[1] / 'scripts/rebuild_local_lake_artifacts.py')
lake = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lake)


@pytest.fixture
def job(monkeypatch, tmp_path):
    root = tmp_path / 'job'
    repo = root / 'repo'
    monkeypatch.setattr(lake, 'JOB', root)
    monkeypatch.setattr(lake, 'REPO', repo)
    doc = {'_meta': {'stock_count': 2, 'kr_count': 1, 'us_count': 1,
                     'generated_at': 'original'}, 'stocks': {'kr': {}, 'us': {}}}
    calls = []
    def create_repo():
        (repo / '.git').mkdir(parents=True)
        (repo / 'data').mkdir()
        (repo / lake.OUTPUT).write_text(json.dumps(doc))
    def command(*args, **kwargs):
        calls.append(args)
        if args[:4] == ('git', 'remote', 'get-url', 'origin'):
            return lake.REMOTE
        if args[:3] == ('git', 'rev-list', '--count'):
            return '0'
        if args[:2] == ('git', 'clone'):
            create_repo()
        return ''
    monkeypatch.setattr(lake, 'command', command)
    monkeypatch.setattr(lake, 'network', command)
    return repo, calls, command, create_repo


def test_fresh_clone_retains_ancestry_and_unchanged_content(job):
    repo, calls, _, _ = job
    assert lake.rebuild() == 0
    assert any(args[:2] == ('git', 'clone') for args in calls)
    assert any(args[:3] == ('git', 'fetch', 'origin') for args in calls)
    assert not any(any(str(arg).startswith('--depth') for arg in args) for args in calls)
    assert not any(args[:2] in {('git', 'push'), ('git', 'commit'), ('git', 'reset')}
                   for args in calls)
    assert json.loads((repo / lake.OUTPUT).read_text())['_meta']['generated_at'] == 'original'


def test_dirty_existing_clone_is_preserved_without_fetch_or_restore(monkeypatch, job):
    repo, calls, command, create_repo = job
    create_repo()
    path = repo / 'local-change.txt'
    path.write_text('preserve')
    def dirty(*args, **kwargs):
        if args[:3] == ('git', 'status', '--porcelain'):
            return ' M local-change.txt'
        return command(*args, **kwargs)
    monkeypatch.setattr(lake, 'command', dirty)
    with pytest.raises(RuntimeError, match='Pending local changes preserved'):
        lake.rebuild()
    assert path.read_text() == 'preserve'
    assert not any(args[:2] in {('git', 'fetch'), ('git', 'restore'), ('git', 'reset')}
                   for args in calls)


def test_unpublished_commit_still_stops_before_checkout(monkeypatch, job):
    _, calls, command, create_repo = job
    create_repo()
    def ahead(*args, **kwargs):
        if args[:3] == ('git', 'rev-list', '--count'):
            return '1'
        return command(*args, **kwargs)
    monkeypatch.setattr(lake, 'command', ahead)
    with pytest.raises(RuntimeError, match='Unpublished commit preserved'):
        lake.rebuild()
    assert not any(args[:2] in {('git', 'checkout'), ('git', 'reset'), ('git', 'push')}
                   for args in calls)
