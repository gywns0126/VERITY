"""Offline preservation checks for the isolated scheduled event-study job."""
import importlib.util
from copy import deepcopy
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    'lake_rebuild', Path(__file__).resolve().parents[1] / 'scripts/rebuild_local_lake_artifacts.py')
lake = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lake)


def issuer(value=1):
    return {'name': 'fixture', 'events': [{'type': 'historical', 'count': 3, 'truncated': 2,
                                          'occurrences': [{'date': '2020-01-01', 'ret_1d': value}]}]}


def study(stocks, generated='old'):
    return {'_meta': {'stock_count': len(stocks),
                      'kr_count': sum(ticker.isdigit() for ticker in stocks),
                      'us_count': sum(not ticker.isdigit() for ticker in stocks),
                      'occurrence_count': sum(len(g['occurrences']) for s in stocks.values() for g in s['events']),
                      'generated_at': generated, 'us_price_source': 'CI receipt',
                      'windows': {'ret_1d': 1}}, 'stocks': stocks}


@pytest.fixture
def job(monkeypatch, tmp_path):
    root = tmp_path / 'job'
    repo = root / 'repo'
    monkeypatch.setattr(lake, 'JOB', root)
    monkeypatch.setattr(lake, 'REPO', repo)
    doc = study({'005930': issuer(), 'US': issuer()}, generated='original')
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


def test_historical_issuer_payload_and_original_receipt_are_preserved():
    old = study({'005930': issuer(), 'CURRENT': issuer(), 'MISSING': issuer(2)})
    before = deepcopy(old)
    current = study({'005930': issuer(3), 'CURRENT': issuer(4)}, generated='new')
    merged = lake.preserve_historical_issuers(old, current)
    lake.validate(old, merged)
    assert old == before
    assert merged['stocks']['MISSING'] == old['stocks']['MISSING']
    assert merged['stocks']['MISSING'] is not old['stocks']['MISSING']
    assert merged['stocks']['CURRENT'] != old['stocks']['CURRENT']
    assert merged['_meta']['stock_count'] == 3
    assert merged['_meta']['kr_count'] == 1 and merged['_meta']['us_count'] == 2
    assert merged['_meta']['occurrence_count'] == 3
    assert merged['_meta']['generated_at'] == 'new'
    receipt = merged['_meta']['carried_forward_issuers']['MISSING']
    assert receipt['previous_generated_at'] == 'old'
    assert receipt['previous_us_price_source'] == 'CI receipt'
    assert len(receipt['payload_sha256']) == 64
    assert merged['_meta']['carried_forward_issuer_count'] == 1


def test_repeated_carry_keeps_receipts_stable_and_recovery_removes_flags():
    old = study({'005930': issuer(), 'CURRENT': issuer(), 'MISSING': issuer(2)})
    fresh = study({'005930': issuer(), 'CURRENT': issuer()}, generated='first')
    first = lake.preserve_historical_issuers(old, fresh)
    repeat = lake.preserve_historical_issuers(
        first, study({'005930': issuer(), 'CURRENT': issuer()}, generated='second'))
    assert lake.content(first) == lake.content(repeat)
    recovered = lake.preserve_historical_issuers(
        repeat, study({'005930': issuer(), 'CURRENT': issuer(), 'MISSING': issuer(9)}, generated='third'))
    assert recovered['stocks']['MISSING'] == issuer(9)
    assert 'carried_forward_issuers' not in recovered['_meta']
    assert 'carried_forward_issuer_count' not in recovered['_meta']


@pytest.mark.parametrize('remaining', [{}, {'005930': issuer()}, {'US': issuer()}])
def test_carry_cannot_hide_empty_or_missing_fresh_market(remaining):
    old = study({'005930': issuer(), 'US': issuer()})
    current = study(remaining)
    with pytest.raises(ValueError):
        lake.preserve_historical_issuers(old, current)
    assert current['stocks'] == remaining


def test_count_or_receipt_corruption_does_not_get_relabelled_as_fresh():
    old = study({'005930': issuer(), 'US': issuer(), 'MISSING': issuer()})
    current = study({'005930': issuer(), 'US': issuer()}, generated='new')
    current['_meta']['us_count'] = 2
    with pytest.raises(ValueError, match='count mismatch'):
        lake.preserve_historical_issuers(old, current)
    current = study({'005930': issuer(), 'US': issuer()}, generated='new')
    old['_meta']['carried_forward_issuers'] = {'MISSING': {'payload_sha256': 'invalid'}}
    with pytest.raises(ValueError, match='receipt does not match'):
        lake.preserve_historical_issuers(old, current)


def test_original_loss_guard_still_rejects_an_unmerged_payload():
    old = study({'005930': issuer(), 'US': issuer(), 'MISSING': issuer()})
    with pytest.raises(ValueError, match='Refusing loss of 1'):
        lake.validate(old, study({'005930': issuer(), 'US': issuer()}))


def test_runner_writes_preserved_payload_before_its_single_file_commit(monkeypatch, job):
    repo, _, command, create_repo = job
    create_repo()
    old = study({'005930': issuer(), 'US': issuer(), 'MISSING': issuer(2)})
    (repo / lake.OUTPUT).write_text(json.dumps(old))
    staged, committed = [False], []
    def rebuilt(*args, **kwargs):
        if args[1:] == ('-m', 'api.builders.event_study_builder'):
            (repo / lake.OUTPUT).write_text(json.dumps(
                study({'005930': issuer(3), 'US': issuer()}, generated='new')))
            return ''
        if args[:3] == ('git', 'diff', '--name-only'):
            return lake.OUTPUT
        if args[:4] == ('git', 'diff', '--cached', '--name-only'):
            return lake.OUTPUT if staged[0] else ''
        if args[:2] == ('git', 'add'):
            assert args == ('git', 'add', '--', lake.OUTPUT)
            staged[0] = True
            return ''
        if args[:3] == ('git', 'config', '--get'):
            return 'existing-identity'
        if args[:2] == ('git', 'commit'):
            committed.append(json.loads((repo / lake.OUTPUT).read_text()))
            return ''
        return command(*args, **kwargs)
    monkeypatch.setattr(lake, 'command', rebuilt)
    monkeypatch.setattr(lake, 'network', rebuilt)
    assert lake.rebuild() == 0
    assert len(committed) == 1
    assert committed[0]['stocks']['MISSING'] == old['stocks']['MISSING']
    assert committed[0]['stocks']['005930'] == issuer(3)
    lake.validate(old, committed[0])


def test_kr_issuer_loss_still_fails_closed_before_us_carry():
    old = study({'005930': issuer(), '000660': issuer(), 'US': issuer(), 'MISSING': issuer()})
    current = study({'005930': issuer(), 'US': issuer()}, generated='new')
    before = deepcopy(current)
    with pytest.raises(ValueError, match='Refusing unverified KR issuer loss'):
        lake.preserve_historical_issuers(old, current)
    assert current == before
