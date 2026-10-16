"""Private source-cache preservation and public producer/hash boundaries."""
import copy
import hashlib
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from api.utils import dart_private_evidence as private
from api.utils.dart_pre_attach import attach_dart_to_stocks


@pytest.fixture(autouse=True)
def private_cache(monkeypatch):
    original_loader = private.load_private_snapshot
    original_loader.cache_clear()
    monkeypatch.delenv("DART_PRIVATE_EVIDENCE", raising=False)
    yield
    original_loader.cache_clear()


def _rows():
    public = {"005930": {"roe": 12.0, "source": "DART", "report_date": "2025",
                          "reprt_code": "11011", "fs_div": "CFS"}}
    full = copy.deepcopy(public)
    full["005930"]["_source_evidence"] = {"roe": {"value": 12.0, "source": "DART",
        "ticker": "005930", "definition": "annual_net_income_over_closing_equity", "inputs": []}}
    return public, {"fundamentals": full}


def test_full_row_match_restores_only_metadata_without_mutating_inputs():
    public, full = _rows(); before = copy.deepcopy(public)
    merged, count = private.merge_source_evidence(public, full)
    assert count == 1 and public == before
    proof = merged["005930"].pop("_source_evidence")
    assert merged == before and proof == full["fundamentals"]["005930"]["_source_evidence"]


@pytest.mark.parametrize("change", [
    {"report_date": "2024"}, {"fs_div": "OFS"}, {"reprt_code": "11012"},
    {"unmatched_extra_field": 1}, {"roe": True}, {"roe": float("nan")},
    {"roe": 12},
])
def test_equal_looking_scalar_is_insufficient_if_any_public_field_differs(change):
    public, full = _rows();full["fundamentals"]["005930"].update(change)
    merged, count = private.merge_source_evidence(public, full)
    assert count == 0 and merged == public


def test_missing_unit_in_restored_proof_is_not_invented():
    public, full = _rows();merged, _ = private.merge_source_evidence(public, full)
    proof=merged["005930"]["_source_evidence"]["roe"]
    assert "unit" not in proof and proof["inputs"] == []


def test_fixed_private_object_memo_allows_only_one_get(monkeypatch):
    import requests
    public, full = _rows();calls=[]
    monkeypatch.setenv("DART_PRIVATE_EVIDENCE", "1")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "SECRET-NEVER-LOG")
    class Response:
        status_code=200
        def json(self):return full
    def get(url, **kwargs):calls.append((url,kwargs));return Response()
    monkeypatch.setattr(requests,"get",get)
    assert private.restore_source_evidence(public)[1] == 1
    assert private.restore_source_evidence(public)[1] == 1
    assert len(calls)==1
    assert calls[0][0].endswith('/verity-reports/_operator/dart_fundamentals_kr.json')
    assert calls[0][1]['allow_redirects'] is False


def test_disabled_or_wrong_bucket_makes_no_request(monkeypatch):
    import requests
    monkeypatch.setattr(requests,"get",lambda *a,**k:pytest.fail("unauthorized read"))
    assert private.load_private_snapshot() is None
    private.load_private_snapshot.cache_clear()
    monkeypatch.setenv("DART_PRIVATE_EVIDENCE", "1")
    monkeypatch.setenv("OPERATOR_BUCKET", "other")
    assert private.load_private_snapshot() is None


def test_private_read_failure_keeps_unknown_without_logging_secret(monkeypatch,capsys):
    import requests
    monkeypatch.setenv("DART_PRIVATE_EVIDENCE","1")
    monkeypatch.setenv("SUPABASE_URL","https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY","SECRET-NEVER-LOG")
    def fail(*args,**kwargs):raise ValueError("SECRET-NEVER-LOG private-body")
    monkeypatch.setattr(requests,"get",fail)
    public,_=_rows();assert private.restore_source_evidence(public)==(public,0)
    assert "SECRET" not in capsys.readouterr().out


def test_pre_attach_restores_in_memory_and_never_changes_cached_file(monkeypatch,tmp_path):
    public,full=_rows();path=tmp_path/'dart.json'
    path.write_text(json.dumps({'collected_at':datetime.now(timezone.utc).isoformat(),'fundamentals':public}))
    before=path.read_bytes();monkeypatch.setattr(private,'load_private_snapshot',lambda:full)
    stock={'ticker':'005930','currency':'KRW','roe':0}
    attach_dart_to_stocks([stock],path=path)
    assert stock['roe']==12.0
    assert stock['fundamental_source_evidence']['roe']==full['fundamentals']['005930']['_source_evidence']['roe']
    assert path.read_bytes()==before


def test_us_only_attach_never_requests_private_dart_metadata(monkeypatch,tmp_path):
    public,_=_rows();path=tmp_path/'dart.json'
    path.write_text(json.dumps({'collected_at':datetime.now(timezone.utc).isoformat(),'fundamentals':public}))
    monkeypatch.setattr(private,'load_private_snapshot',lambda:pytest.fail("US-only read unnecessary"))
    attach_dart_to_stocks([{'ticker':'ABC','currency':'USD'}],path=path)


def test_batch_restore_preserves_scalar_and_snapshot_envelope(monkeypatch,tmp_path):
    public,full=_rows();path=tmp_path/'dart.json';document={'collected_at':'original','diagnostics':{'keep':True},'fundamentals':public}
    path.write_text(json.dumps(document));monkeypatch.setattr(private,'load_private_snapshot',lambda:full)
    assert private.restore_batch_cache(path)==1
    restored=json.loads(path.read_text());restored['fundamentals']['005930'].pop('_source_evidence')
    assert restored==document


def test_candidate_builder_omits_metadata_before_identity_and_loader_hash(monkeypatch,tmp_path):
    from api.builders import universe_scan_builder as builder
    from api.utils import universe_candidates as loader
    from scripts.ci.private_analysis_files import PRIVATE_ANALYSIS_KEYS
    now=datetime(2026,10,15,17,0,tzinfo=timezone(timedelta(hours=9)))
    records=[{'ticker':'005930','currency':'KRW','roe':0,'fundamental_source_evidence':{'x':1}},
             {'ticker':'ABC','currency':'USD','sec_financials':{'revenue':0,'_source_evidence':{'x':1}}}]
    original=copy.deepcopy(records)
    monkeypatch.setattr('api.analyzers.stock_filter.run_filter_pipeline_with_ramp_up',lambda **kw:records)
    monkeypatch.setattr(builder,'_load_existing',lambda:{})
    monkeypatch.setattr(builder,'merge_promoted',lambda values:(values,0,{}))
    monkeypatch.setattr(builder,'_now_kst',lambda:now)
    monkeypatch.setenv('GITHUB_RUN_ID','999');monkeypatch.setenv('GITHUB_RUN_ATTEMPT','1');monkeypatch.setenv('VERITY_MODE','prod')
    result=builder.build();assert records==original
    text=json.dumps(result,sort_keys=True)
    assert all('"'+key+'"' not in text for key in PRIVATE_ANALYSIS_KEYS)
    assert result['scan_id']=='gh:999:1'
    path=tmp_path/'scan.json';path.write_text(text);before=path.read_bytes()
    monkeypatch.setattr(loader,'SNAPSHOT_PATH',str(path));monkeypatch.setattr(loader,'_now_kst',lambda:now)
    monkeypatch.setattr('api.utils.dart_pre_attach.attach_dart_to_stocks',lambda *a,**k:{})
    monkeypatch.setenv('UNIVERSE_EXPECTED_SCAN_ID','gh:999:1');loader.reset_cache()
    loaded=loader.load_universe_candidates()
    assert loaded['_load_provenance']['snapshot_sha256']==hashlib.sha256(before).hexdigest()
    assert path.read_bytes()==before


@pytest.mark.parametrize('fail_phase',['upload','strip'])
def test_private_preservation_or_strip_failure_prevents_public_commit(tmp_path,fail_phase):
    import yaml
    root=Path(__file__).resolve().parents[1]
    workflow=yaml.safe_load((root/'.github/workflows/dart_batch.yml').read_text())
    steps=workflow['jobs']['batch']['steps']
    preserve=next(s for s in steps if s['name']=='Preserve private DART evidence before public Git')
    commit=next(s for s in steps if s['name']=='Commit data/dart_fundamentals_kr.json')
    assert steps.index(preserve)<steps.index(commit) and commit['if']=='success()'
    assert '--only dart_fundamentals_kr' in preserve['run']
    script=tmp_path/'commands.sh'
    script.write_text("""python() {
      if [[ "$1" == scripts/upload_operator_data_to_supabase.py ]]; then
        echo upload
        [[ "$FAIL_PHASE" != upload ]]
      else
        echo strip
        [[ "$FAIL_PHASE" != strip ]]
      fi
    }
"""+preserve['run']+'\necho commit-allowed\n')
    import os
    result=subprocess.run(['bash','-e',str(script)],env={**os.environ,'FAIL_PHASE':fail_phase},capture_output=True,text=True)
    assert result.returncode!=0 and 'commit-allowed' not in result.stdout
    if fail_phase=='upload':assert 'strip' not in result.stdout
