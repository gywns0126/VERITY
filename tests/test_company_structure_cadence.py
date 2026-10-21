"""Corporate source scheduling reuses the existing clock without sending requests."""
import importlib.util
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def dispatcher():
    spec = importlib.util.spec_from_file_location('structure_cadence', ROOT / 'vercel-api/api/cron/dispatch_pulse.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_one_daily_existing_clock_slot_for_the_full_week():
    module = dispatcher()
    start = datetime(2026, 10, 18, tzinfo=timezone.utc)
    slots = []
    for minute in range(7 * 1440):
        now = start + timedelta(minutes=minute)
        if now.minute % 5 and now.minute != 7:
            continue
        for raw in module._resolve_events(now):
            name, payload = module._split_event(raw)
            if name == 'ownership_backfill':
                assert (now.hour, now.minute) == (19, 40)
                assert payload == {'schedule_slot': now.isoformat()}
                slots.append(payload['schedule_slot'])
    assert len(slots) == len(set(slots)) == 7


@pytest.mark.parametrize('minute', [40, 41, 42, 43, 44])
def test_delayed_delivery_keeps_original_due_time(minute):
    module = dispatcher()
    now = datetime(2026, 10, 21, 19, minute, tzinfo=timezone.utc)
    events = [module._split_event(e) for e in module._resolve_events(now)]
    assert ('ownership_backfill', {'schedule_slot': '2026-10-21T19:40:00+00:00'}) in events


def test_workflow_entry_and_existing_collector_lock_are_consistent():
    doc = yaml.safe_load((ROOT / '.github/workflows/ownership_backfill.yml').read_text())
    triggers = doc.get('on', doc.get(True))
    assert triggers['repository_dispatch']['types'] == ['ownership_backfill']
    assert 'workflow_dispatch' in triggers
    assert doc['permissions']['actions'] == 'read'
    assert doc['jobs']['backfill']['concurrency'] == {'group': 'verity-ownership-backfill', 'cancel-in-progress': False}
    assert 'concurrency' not in doc


@pytest.mark.parametrize('event,created,slot', [
    ('workflow_dispatch', '2026-10-21T18:00:00Z', None),
    ('repository_dispatch', '2026-10-21T19:41:00Z', '2026-10-21T19:40:00+00:00'),
    ('schedule', '2026-10-21T22:30:00Z', None),
])
@pytest.mark.parametrize('prior,expected', [([], True), ([{'id': 99, 'conclusion': 'failure'}], False),
                                         ([{'id': 99, 'conclusion': 'cancelled'}], False),
                                         ([{'id': 101, 'status': 'queued'}], True)])
def test_actual_guard_reserves_failed_and_cancelled_attempts_for_the_kst_day(event, created, slot, prior, expected):
    doc = yaml.safe_load((ROOT / '.github/workflows/ownership_backfill.yml').read_text())
    script = doc['jobs']['cadence']['steps'][0]['with']['script']
    context = {'repo': {'owner': 'test', 'repo': 'test'}, 'eventName': event, 'runId': 100,
               'payload': {'repository': {'default_branch': 'main'}, 'client_payload': {'schedule_slot': slot}}}
    current_attempt = 1
    harness = f'''
    const context={json.dumps(context)};
    const core={{setOutput:(k,v)=>{{if(k==='run')process.stdout.write(v);}},info:()=>{{}}}};
    const github={{rest:{{actions:{{getWorkflowRun:async()=>({{data:{{created_at:{json.dumps(created)},run_attempt:{current_attempt}}}}}),listWorkflowRuns:{{}}}}}},
      paginate:async(_,args)=>{{
        if(args.workflow_id!=='ownership_backfill.yml'||args.branch!=='main'||args.created!=='>=2026-10-21T15:00:00.000Z')throw Error('Wrong day boundary');
        return {json.dumps(prior + [{'id': 100}])};
      }}}};
    (async()=>{{{script}}})().catch(()=>process.exit(1));
    '''
    result = subprocess.run(['node', '-e', harness], capture_output=True, text=True, check=True)
    assert result.stdout == str(expected).lower()


@pytest.mark.parametrize(('attempt', 'expected', 'fails'), [
    (2, 'false', False),
    (0, '', True),
    (-1, '', True),
    (1.5, '', True),
])
def test_same_run_rerun_consumes_daily_slot_and_invalid_attempt_fails_closed(attempt, expected, fails):
    doc = yaml.safe_load((ROOT / '.github/workflows/ownership_backfill.yml').read_text())
    script = doc['jobs']['cadence']['steps'][0]['with']['script']
    context = {'repo': {'owner': 'test', 'repo': 'test'}, 'eventName': 'workflow_dispatch', 'runId': 100,
               'payload': {'repository': {'default_branch': 'main'}, 'client_payload': {}}}
    harness = f'''
    const context={json.dumps(context)};
    const core={{setOutput:(k,v)=>{{if(k==='run')process.stdout.write(v);}},info:()=>{{}}}};
    const github={{rest:{{actions:{{getWorkflowRun:async()=>({{data:{{created_at:"2026-10-21T18:00:00Z",run_attempt:{attempt}}}}}),listWorkflowRuns:{{}}}}}},
      paginate:async()=>[]}};
    (async()=>{{{script}}})().catch(()=>process.exit(1));
    '''
    result = subprocess.run(['node', '-e', harness], capture_output=True, text=True, check=False)
    assert (result.returncode != 0) is fails
    assert result.stdout == expected

