"""Offline historical-byte backfill: no collection, provider, or publication."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import socket
import sys
import urllib.request

import pytest

from tests.test_annual_capture_delivery import fixture as public_catalog_fixture
from tests.test_portfolio_contract_facts import _body, _parse, RECEIPT


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "same_sha_capture", ROOT / "scripts/member-map/capture-contract-facts.py")
capture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(capture)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("financial backfill cannot collect or publish")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(urllib.request, "build_opener", forbidden)
    monkeypatch.setattr(capture, "load_public_sources", forbidden)
    monkeypatch.setattr(capture, "apply_local", forbidden)


@pytest.fixture(scope="module")
def base():
    return public_catalog_fixture()


def case(tmp_path, base):
    financial = ('<tr><td>2. 계약내역</td><td>계약금액(원)</td><td>1,000</td></tr>'
                 '<tr><td>최근매출액(원)</td><td>10,000</td></tr>'
                 '<tr><td>매출액대비(%)</td><td>10.0</td></tr>')
    note = '최근매출액은 2025년도 연결재무제표 기준임.'
    raw = _body(financial_rows=financial).decode('euc-kr').replace(
        '</table><script>', '<tr><td>10. 기타 투자판단에 참고할 사항</td></tr>'
        f'<tr><td>{note}</td></tr></table><script>').encode('euc-kr')
    parsed = _parse(raw)
    retained = deepcopy(parsed)
    for key in ('financial_terms', 'financial_notes', 'revenue_basis'):
        retained['contract'].pop(key, None)
    # A source-title receipt must survive even though viewer parsing has no feed.
    retained['filing']['source_title'] = '[기재정정]단일판매ㆍ공급계약체결'
    artifact = deepcopy(base)
    artifact['contract_facts'] = [retained]
    directory = tmp_path / 'raw'
    directory.mkdir()
    (directory / (RECEIPT + '.viewer.html')).write_bytes(raw)
    return artifact, parsed, directory


def test_same_sha_adds_only_absent_fields_preserving_observation_and_all_other_artifact(base, tmp_path):
    artifact, parsed, directory = case(tmp_path, base)
    before = deepcopy(artifact)
    enriched, proof = capture.backfill_same_sha_financial(artifact, [directory])
    assert proof['input'] == proof['counts']['updated'] == 1
    expected = deepcopy(before)
    for key in ('financial_terms', 'financial_notes', 'revenue_basis'):
        expected['contract_facts'][0]['contract'][key] = parsed['contract'][key]
    assert enriched == expected and artifact == before
    assert enriched['contract_facts'][0]['source'] == before['contract_facts'][0]['source']
    assert proof['public_gets'] == proof['ai_calls'] == 0 and proof['applied'] is False
    assert proof['rows'][0]['added_fields'] == [
        'financial_terms.amount', 'financial_terms.recent_revenue',
        'financial_terms.revenue_ratio', 'financial_notes', 'revenue_basis']
    again, replay = capture.backfill_same_sha_financial(enriched, [directory])
    assert again == enriched and replay['counts']['unchanged'] == 1


def test_partial_financial_terms_are_extended_without_replacement(base, tmp_path):
    artifact, parsed, directory = case(tmp_path, base)
    amount = deepcopy(parsed['contract']['financial_terms']['amount'])
    artifact['contract_facts'][0]['contract']['financial_terms'] = {'amount': amount}
    enriched, proof = capture.backfill_same_sha_financial(artifact, [directory])
    assert proof['counts']['updated'] == 1
    assert enriched['contract_facts'][0]['contract']['financial_terms'] == parsed['contract']['financial_terms']
    assert 'financial_terms.amount' not in proof['rows'][0]['added_fields']


@pytest.mark.parametrize('change,status', [
    ('missing', 'missing-source'), ('changed-sha', 'changed-source'),
    ('changed-size', 'changed-source'), ('symlink', 'unsafe-source'),
    ('period-conflict', 'conflict'), ('amount-conflict', 'conflict'),
    ('notes-conflict', 'conflict'), ('issuer-conflict', 'source-parser-rejected'),
    ('filing-conflict', 'source-parser-rejected'),
])
def test_missing_changed_or_conflicting_source_never_replaces_retained_fact(base, tmp_path, change, status):
    artifact, parsed, directory = case(tmp_path, base)
    path = directory / (RECEIPT + '.viewer.html')
    fact = artifact['contract_facts'][0]
    if change == 'missing':
        path.unlink()
    elif change == 'changed-sha':
        raw = path.read_bytes()
        path.write_bytes(b'X' + raw[1:])
    elif change == 'changed-size':
        path.write_bytes(path.read_bytes() + b' ')
    elif change == 'symlink':
        target = tmp_path / 'other.html'
        path.rename(target)
        path.symlink_to(target)
    elif change == 'period-conflict':
        fact['contract']['period']['end']['value'] = '2051-12-31'
    elif change == 'amount-conflict':
        fact['contract']['financial_terms'] = deepcopy(parsed['contract']['financial_terms'])
        fact['contract']['financial_terms']['amount']['value'] = '999'
    elif change == 'notes-conflict':
        fact['contract']['financial_notes'] = deepcopy(parsed['contract']['financial_notes'])
        fact['contract']['financial_notes']['value'] = '다른 기존 주석입니다.'
    elif change == 'issuer-conflict':
        fact['issuer']['name'] = '다른발행사'
    elif change == 'filing-conflict':
        fact['filing']['filed_on'] = '2026-09-29'
    before = deepcopy(artifact)
    result, proof = capture.backfill_same_sha_financial(artifact, [directory])
    assert result == artifact == before
    assert proof['counts'][status] == 1 and proof['counts']['updated'] == 0


def test_duplicate_receipt_and_unbounded_cache_list_rejected(base, tmp_path):
    artifact, _, directory = case(tmp_path, base)
    with pytest.raises(ValueError, match='cache-directory'):
        capture.backfill_same_sha_financial(artifact, [directory] * 9)
    artifact['contract_facts'].append(deepcopy(artifact['contract_facts'][0]))
    with pytest.raises(ValueError, match='duplicate-contract-receipt'):
        capture.backfill_same_sha_financial(artifact, [directory])


def test_cli_is_usable_without_catalog_feed_and_preserves_source_bytes(base, tmp_path, monkeypatch, capsys):
    artifact, _, directory = case(tmp_path, base)
    source = tmp_path / 'source'
    source.mkdir()
    path = source / 'member_map_auto_evidence.json'
    path.write_text(json.dumps(artifact, ensure_ascii=False))
    before = path.read_bytes()
    output = tmp_path / 'review'
    args = ['capture-contract-facts.py', '--source-dir', str(source), '--output-dir', str(output),
            '--backfill-financial-from', str(directory)]
    monkeypatch.setattr(sys, 'argv', args)
    capture.main()
    summary = json.loads(capsys.readouterr().out)
    assert summary['counts']['updated'] == 1 and summary['applied'] is False
    assert path.read_bytes() == before
    assert json.loads((output / 'financial-backfill-proof.json').read_text())['rows'][0]['receipt_no'] == RECEIPT
    with pytest.raises(SystemExit):
        capture.main()  # Existing output is never overwritten.
    assert path.read_bytes() == before


@pytest.mark.parametrize('option', ['--fetch-public', '--apply-local', '--reparse'])
def test_offline_cli_refuses_capture_or_apply_options(tmp_path, monkeypatch, option):
    monkeypatch.setattr(sys, 'argv', ['capture-contract-facts.py', '--source-dir', str(tmp_path),
        '--output-dir', str(tmp_path / 'out'), '--backfill-financial-from', str(tmp_path), option])
    with pytest.raises(SystemExit):
        capture.main()
    assert not (tmp_path / 'out').exists()
