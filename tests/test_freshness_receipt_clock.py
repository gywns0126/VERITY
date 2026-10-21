"""Receipt-bound streams cannot inherit clocks from rebuilt retained data."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from api.builders import freshness_board_builder as board
from scripts import freshness_shadow_monitor as monitor

NOW = datetime(2026, 10, 22, 1, tzinfo=timezone(timedelta(hours=9)))


def configure(tmp_path, monkeypatch, proof):
    manifest = tmp_path / 'freshness_sla.json'
    manifest.write_text(json.dumps({'streams': [{
        'id': 'dividends_kr', 'file': 'input.json', 'criticality': 'P2',
        'receipt_clock': True, 'missing_ts_status': 'unmeasurable',
        'measurement_reason': 'source_query_receipt_missing',
        'schedule': 'always', 'max_age_minutes': 90,
    }]}))
    (tmp_path / 'input.json').write_text(json.dumps({
        'generated_at': NOW.isoformat(),
        '_meta': {'source_as_of': NOW.isoformat()},
        '005930': [{'ex_date': '2027-12-31'}],
    }))
    for mod in (board, monitor):
        monkeypatch.setattr(mod, 'DATA_DIR', str(tmp_path))
        monkeypatch.setattr(mod, 'MANIFEST', str(manifest))
        monkeypatch.setattr(mod, 'now_kst', lambda: NOW)
    monkeypatch.setattr(monitor, 'collection_receipt', lambda *args: proof)
    def forbidden(*args):
        raise AssertionError('workflow completion is not a receipt clock')
    monkeypatch.setattr(monitor, 'producer_evidence', forbidden)


@pytest.mark.parametrize('proof', [None, {'status': 'invalid_receipt'},
                                   {'status': 'bound_query_incomplete'}])
def test_missing_or_failed_receipt_cannot_use_embedded_or_job_clock(tmp_path, monkeypatch, proof):
    configure(tmp_path, monkeypatch, proof)
    observed = monitor.build_observations()['rows'][0]
    assert observed['status'] == 'unmeasurable'
    assert observed['would_alarm'] is True
    assert 'last_ts' not in observed
    public = board.build_board()
    assert public['streams'] == []
    assert public['summary']['p2']['unmeasured'] == 1


@pytest.mark.parametrize('age,stale', [(5, False), (91, True)])
def test_bound_chunk_uses_its_clock_and_preserves_partial_scope(tmp_path, monkeypatch, age, stale):
    counts = {'selected': 2, 'attempted': 2, 'successful': 2, 'total': 2635}
    proof = {'status': 'bound_query_complete', 'clock_kind': 'source_query_attempt',
             'completed_at': (NOW - timedelta(minutes=age)).isoformat(),
             'asset_binding': 'verified_sha256', 'source_freshness_verified': False,
             'all_records_revalidated': False, 'scope_counts': counts}
    configure(tmp_path, monkeypatch, proof)
    observed = monitor.build_observations()['rows'][0]
    assert observed['age_eff_min'] == age
    assert observed['would_alarm'] is stale
    public = board.build_board()['streams'][0]
    assert public['status'] == ('stale' if stale else 'fresh')
    assert public['clock_kind'] == 'source_query_attempt'
    assert public['all_records_revalidated'] is False
    assert public['scope_counts'] == counts


def test_logo_access_stop_remains_actionable_without_claiming_freshness(tmp_path, monkeypatch):
    proof = {'status': 'bound_query_incomplete', 'clock_kind': 'bounded_logo_url_query',
             'asset_binding': 'verified_sha256', 'quality_reason': 'source_access_stop',
             'source_freshness_verified': False, 'all_records_revalidated': False,
             'scope_counts': {'selected': 16, 'attempted': 12, 'passed': 10,
                              'failed': 2, 'unattempted': 4, 'total': 9361}}
    configure(tmp_path, monkeypatch, proof)
    manifest = tmp_path / 'freshness_sla.json'
    doc = json.loads(manifest.read_text())
    doc['streams'][0]['id'] = 'logo_map'
    manifest.write_text(json.dumps(doc))
    observed = monitor.build_observations()['rows'][0]
    assert observed['would_alarm'] is True
    assert observed['quality_reason'] == 'source_access_stop'
    public = board.build_board()
    assert public['streams'] == []
    assert public['_skipped'][0]['measurement_reason'] == 'source_access_stop'
    assert public['_producer_evidence']['logo_map']['scope_counts']['unattempted'] == 4
    assert public['summary']['p2']['fresh'] == 0
