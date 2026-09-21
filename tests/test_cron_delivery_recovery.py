"""Regression checks for failed heartbeat delivery and repeated infra alerts."""
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import action_queue as queue
from scripts import infra_status_monitor as infra
from scripts import local_lake_heartbeat as heartbeat


@pytest.mark.parametrize('published, expected', [(True, 0), (False, 1)])
def test_heartbeat_exit_tracks_delivery(tmp_path, monkeypatch, published, expected):
    out = tmp_path / 'nested' / 'health.json'
    monkeypatch.setattr(heartbeat, 'OUT', str(out))
    monkeypatch.setattr(heartbeat, 'build', lambda: {'artifacts': []})
    monkeypatch.setattr(heartbeat, '_publish_to_main', lambda: published)
    monkeypatch.setattr(heartbeat.sys, 'argv', ['heartbeat', '--publish'])
    assert heartbeat.main() == expected
    assert json.loads(out.read_text()) == {'artifacts': []}


def _publisher(tmp_path, monkeypatch, responses):
    out = tmp_path / 'health.json'
    out.write_text('{}')
    monkeypatch.setattr(heartbeat, 'OUT', str(out))
    monkeypatch.setattr(heartbeat.shutil, 'which', lambda _: '/usr/bin/gh')
    monkeypatch.setattr(heartbeat.time, 'sleep', lambda _: None)
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return SimpleNamespace(returncode=result[0], stdout=result[1], stderr='')
    monkeypatch.setattr(heartbeat.subprocess, 'run', run)
    return calls


def test_failed_sha_lookup_never_sends_put(tmp_path, monkeypatch):
    calls = _publisher(tmp_path, monkeypatch, [(1, '')] * 3)
    assert not heartbeat._publish_to_main()
    assert len(calls) == 3
    assert all('--method' not in args for args in calls)


def test_retry_refreshes_sha_after_write_conflict(tmp_path, monkeypatch):
    calls = _publisher(tmp_path, monkeypatch, [(0, 'a' * 40), (1, ''), (0, 'b' * 40), (0, '{}')])
    assert heartbeat._publish_to_main()
    assert 'sha=' + 'a' * 40 in calls[1]
    assert 'sha=' + 'b' * 40 in calls[3]
    assert 'branch=main' in calls[3]


def test_timeout_retries_are_bounded(tmp_path, monkeypatch):
    calls = _publisher(tmp_path, monkeypatch, [subprocess.TimeoutExpired('gh', 30)] * 3)
    assert not heartbeat._publish_to_main()
    assert len(calls) == 3


def test_missing_event_artifact_stays_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(heartbeat, 'TRACKED', [('event_study', str(tmp_path / 'absent'), 'json:_meta.generated_at')])
    assert heartbeat.build()['artifacts'][0]['status'] == 'missing'


def _args(refresh=True):
    return SimpleNamespace(title='[infra] LLM Budget ALERT', category='monitoring', priority='p0',
                           actor='user', detail='current evidence', commit=None, component=None,
                           snippet=None, due=None, refresh_pending=refresh)


def _response(status, text='', rows=None):
    return SimpleNamespace(status_code=status, text=text, json=lambda: rows)


def test_repeated_alert_updates_only_matching_pending(monkeypatch):
    monkeypatch.setattr(queue, '_check_env', lambda: None)
    monkeypatch.setattr(queue.requests, 'post', lambda *a, **kw: _response(409, '23505 uniq_uaq_pending_title'))
    patched = []
    def patch(*a, **kw):
        patched.append(kw)
        return _response(200, rows=[{'id': 'existing'}])
    monkeypatch.setattr(queue.requests, 'patch', patch)
    assert queue.cmd_add(_args()) == 0
    assert patched[0]['params'] == {'title': 'eq.[infra] LLM Budget ALERT', 'category': 'eq.monitoring', 'status': 'eq.pending'}
    assert patched[0]['json']['detail'] == 'current evidence'


@pytest.mark.parametrize('refresh, message', [(False, '23505 uniq_uaq_pending_title'), (True, 'other conflict')])
def test_other_conflicts_are_not_hidden(monkeypatch, refresh, message):
    monkeypatch.setattr(queue, '_check_env', lambda: None)
    monkeypatch.setattr(queue.requests, 'post', lambda *a, **kw: _response(409, message))
    monkeypatch.setattr(queue.requests, 'patch', lambda *a, **kw: pytest.fail('unexpected patch'))
    with pytest.raises(SystemExit, match='insert 실패'):
        queue.cmd_add(_args(refresh))


def test_concurrent_alert_resolution_is_not_reported_as_update(monkeypatch):
    monkeypatch.setattr(queue, '_check_env', lambda: None)
    monkeypatch.setattr(queue.requests, 'post', lambda *a, **kw: _response(409, '23505 uniq_uaq_pending_title'))
    monkeypatch.setattr(queue.requests, 'patch', lambda *a, **kw: _response(200, rows=[]))
    with pytest.raises(SystemExit, match='pending 갱신 대상 없음'):
        queue.cmd_add(_args())


def test_alert_keeps_failure_exit_and_writes_snapshot(tmp_path, monkeypatch):
    names = ['check_kis', 'check_vercel_deploy_spam', 'check_github_actions_billing',
             'check_external_repos', 'check_dart', 'check_supabase', 'check_llm_budget']
    for name in names:
        monkeypatch.setattr(infra, name, lambda: {'provider': 'test', 'status': 'ALERT', 'detail': 'evidence'})
    monkeypatch.setattr(infra, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(infra, 'OUTPUT_PATH', tmp_path / 'infra.json')
    queued = []
    monkeypatch.setattr(infra, '_push_action_queue', lambda **kw: queued.append(kw))
    assert infra.main() == 1
    assert json.loads((tmp_path / 'infra.json').read_text())['summary']['alert'] == 7
    assert len(queued) == 7
