"""Automatic cadence, quota and duplicate guards; no external dispatches."""
import importlib.util
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ('cockpit_aggregate', 'cron_health_monitor', 'dart_kr_fin_backfill')


def dispatcher():
    spec = importlib.util.spec_from_file_location(
        'cadence_dispatch', ROOT / 'vercel-api/api/cron/dispatch_pulse.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def workflow(name):
    return yaml.safe_load((ROOT / f'.github/workflows/{name}.yml').read_text())


def test_full_week_cadence_and_daily_quota_boundary():
    module = dispatcher()
    start = datetime(2026, 10, 18, tzinfo=timezone.utc)
    counts = dict.fromkeys(TARGETS, 0)
    unique_cockpit_slots = set()
    for minute in range(7 * 1440):
        now = start + timedelta(minutes=minute)
        # Existing Vercel clock: every five minutes, plus the quick :07 slot.
        if now.minute % 5 and now.minute != 7:
            continue
        for item in module._resolve_events(now):
            event, payload = module._split_event(item)
            if event not in counts:
                continue
            counts[event] += 1
            slot = datetime.fromisoformat(payload['schedule_slot'])
            if event == 'dart_kr_fin_backfill':
                assert (now.hour, now.minute) == (20, 30)
                assert slot == now.replace(hour=15, minute=0)
                assert 'quota_cap' not in payload
            else:
                assert slot == now.replace(minute=now.minute - now.minute % 5)
                if event == 'cockpit_aggregate':
                    unique_cockpit_slots.add(slot)
    assert counts == dict(zip(TARGETS, (7 * 312, 7 * 24, 7)))
    assert len(unique_cockpit_slots) == 7 * 288  # :07 reuses :05, guarded in workflow.


@pytest.mark.parametrize('name', TARGETS)
def test_single_clock_manual_entry_and_serialized_guard(name):
    doc = workflow(name)
    triggers = doc.get('on', doc.get(True))
    assert 'schedule' not in triggers
    assert triggers['repository_dispatch']['types'] == [name]
    assert 'workflow_dispatch' in triggers
    assert doc['permissions']['actions'] == 'read'
    assert doc['concurrency']['cancel-in-progress'] is False
    assert doc['jobs']['cadence']['if'] == "github.event_name == 'repository_dispatch'"
    job = next(v for k, v in doc['jobs'].items() if k != 'cadence')
    assert job['needs'] == 'cadence'
    assert "needs.cadence.result == 'skipped'" in job['if']
    assert "needs.cadence.outputs.run == 'true'" in job['if']


@pytest.mark.parametrize('name', TARGETS)
@pytest.mark.parametrize('prior,expected', [([], True), ([{'id': 99}], False),
                                          ([{'id': 99, 'conclusion': 'failure'}], False),
                                          ([{'id': 101, 'status': 'queued'}], True)])
def test_guard_executes_real_workflow_script(name, prior, expected):
    script = workflow(name)['jobs']['cadence']['steps'][0]['with']['script']
    context = {'repo': {'owner': 'test', 'repo': 'test'}, 'runId': 100,
               'payload': {'client_payload': {'schedule_slot': '2026-10-18T15:00:00+00:00'},
                           'repository': {'default_branch': 'main'}}}
    harness = f"""
      const context = {json.dumps(context)};
      const core = {{setOutput: (key,value) => process.stdout.write(value), info: () => {{}}}};
      const github = {{rest: {{actions: {{listWorkflowRuns: {{}}}}}},
        paginate: async (_, args) => {{
          if (args.workflow_id !== '{name}.yml' || args.branch !== 'main' ||
              args.created !== '>=2026-10-18T15:00:00+00:00') throw Error('Bad query');
          return {json.dumps(prior + [{'id': 100}])};
        }} }};
      (async () => {{ {script} }})().catch(() => process.exit(1));
    """
    result = subprocess.run(['node', '-e', harness], text=True, capture_output=True, check=True)
    assert result.stdout == str(expected).lower()


def test_automatic_dart_cap_and_existing_runtime_limits():
    doc = workflow('dart_kr_fin_backfill')
    job = doc['jobs']['fin-backfill']
    collect = next(step for step in job['steps'] if step.get('id') == 'bf')
    assert collect['env']['QUOTA_CAP'] == "${{ github.event.inputs.quota_cap || '3000' }}"
    assert '"${args[@]}"' in collect['run']
    assert 'SELECTED_TICKERS' in collect['env']
    assert job['timeout-minutes'] == 70
    assert collect['timeout-minutes'] == 55
    config = json.loads((ROOT / 'vercel-api/vercel.json').read_text())
    assert config['functions']['api/cron/dispatch_pulse.py']['maxDuration'] == 90


@pytest.mark.parametrize('minute', [10, 11, 12, 13, 14])
def test_delayed_health_uses_the_same_scheduled_slot(minute):
    events = [dispatcher()._split_event(e) for e in dispatcher()._resolve_events(
        datetime(2026, 10, 18, 12, minute, tzinfo=timezone.utc))]
    assert ('cron_health_monitor', {'schedule_slot': '2026-10-18T12:10:00+00:00'}) in events
    assert ('cockpit_aggregate', {'schedule_slot': '2026-10-18T12:10:00+00:00'}) in events


@pytest.mark.parametrize('minute', [30, 31, 32, 33, 34])
def test_delayed_annual_uses_the_same_kst_day(minute):
    module = dispatcher()
    events = [module._split_event(e) for e in module._resolve_events(
        datetime(2026, 10, 18, 20, minute, tzinfo=timezone.utc))]
    assert ('dart_kr_fin_backfill', {'schedule_slot': '2026-10-18T15:00:00+00:00'}) in events


def test_bounded_serial_network_time_fits_configured_duration():
    module = dispatcher()
    start = datetime(2026, 10, 18, tzinfo=timezone.utc)
    worst = 0
    for minute in range(7 * 1440):
        now = start + timedelta(minutes=minute)
        events = [module._split_event(e)[0] for e in module._resolve_events(now)]
        # _dispatch timeout=8; backup lookup timeout=6; quick busy lookup=6.
        upper = 8 * len(events) + (6 if 'daily_analysis_quick' in events else 0)
        upper += 14 * len(module._resolve_backup_events(now))
        worst = max(worst, upper)
    config = json.loads((ROOT / 'vercel-api/vercel.json').read_text())
    assert 10 < worst < config['functions']['api/cron/dispatch_pulse.py']['maxDuration']


@pytest.mark.parametrize('authorized,status', [(False, 401), (True, 200)])
def test_handler_auth_and_actual_dispatch_payloads(monkeypatch, authorized, status):
    module = dispatcher()
    class Clock(datetime):
        @staticmethod
        def now(tz):
            return datetime(2026, 10, 18, 12, 10, tzinfo=tz)
    monkeypatch.setattr(module, 'datetime', Clock)
    monkeypatch.setattr(module, 'CRON_SECRET', 'test-only')
    calls = []
    monkeypatch.setattr(module, '_dispatch', lambda event, payload:
                        (calls.append((event, payload)) or (204, 'dispatched')))
    request = object.__new__(module.handler)
    request.headers = {'Authorization': 'Bearer test-only' if authorized else ''}
    request.wfile = io.BytesIO()
    responses = []
    request.send_response = responses.append
    request.send_header = lambda *args: None
    request.end_headers = lambda: None
    request.do_GET()
    assert responses == [status]
    if authorized:
        assert calls == [(name, {'schedule_slot': '2026-10-18T12:10:00+00:00'})
                         for name in TARGETS[:2]]
    else:
        assert calls == []


@pytest.mark.parametrize('name', TARGETS)
def test_guard_api_error_stops_before_collector(name):
    script = workflow(name)['jobs']['cadence']['steps'][0]['with']['script']
    harness = """
      const context = {repo: {}, runId: 100, payload: {
        client_payload: {schedule_slot: '2026-10-18T15:00:00Z'},
        repository: {default_branch: 'main'}}};
      const github = {rest: {actions: {}}, paginate: async () => {throw Error('API unavailable')}};
      const core = {setOutput: () => process.stdout.write('UNSAFE'), info: () => {}};
    """ + f"(async () => {{ {script} }})().catch(() => process.exit(1));"
    result = subprocess.run(['node', '-e', harness], text=True, capture_output=True)
    assert result.returncode == 1
    assert result.stdout == ''
