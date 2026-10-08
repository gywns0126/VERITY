"""Compact annual source rows survive existing refresh and atomic apply paths."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

from api.intelligence.portfolio_annual_customer_tables import capture_annual_customer_tables
from tests.test_portfolio_annual_customer_tables import _synthetic_xml, _zip

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    # Build a public fixture through the shipped builder, not a local-only test helper.
    script = """
const {buildPublicCatalog}=require('./scripts/member-map/build-public-source-filter.cjs');
const meta={bytes:1,sha256:'a'.repeat(64)};
console.log(JSON.stringify(buildPublicCatalog({generatedAt:'2026-10-08T00:00:00Z',
  universe:{_meta:{count:1,generated_at:'2026-10-08T00:00:00Z'},stocks:[{ticker:'027040',market:'KR',name:'서울전자통신'}]},
  chainSnippets:{updated_at:'2026-10-08T00:00:00Z',documents:[]},
  groupStructure:{updated_at:'2026-10-08T00:00:00Z',count:0,structures:{}},
  inputMetadata:{universe:meta,chainSnippets:meta,groupStructure:meta}})));
"""
    result = subprocess.run(['node', '-e', script], cwd=ROOT, check=True,
                            text=True, capture_output=True, timeout=30)
    return json.loads(result.stdout)


def compact():
    return capture_annual_customer_tables(
        _zip(_synthetic_xml(table="""<TABLE>
<TR><TH>회사</TH><TH>사업부문</TH><TH>주요제품</TH><TH>주요고객</TH></TR>
<TR><TD>서울전자통신</TD><TD>전원</TD><TD>부품</TD><TD>LG전자</TD></TR>
</TABLE>""")), receipt_no="20260320001349", issuer_id="KR:027040",
        issuer_name="서울전자통신", corp_code="00130587", filed_on="2026-03-20",
        fiscal_year="2025", report_name="사업보고서 (2025.12)")


def module(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'scripts/member-map' / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_annual_delivery_validator_rejects_duplicate_unknown_and_private_fields():
    validator = module('validate-capture-delivery')
    row = compact()
    assert validator.validate({'annual_customer_tables': [row]}) == {'annual_customer_tables': 1}
    with pytest.raises(ValueError):
        validator.validate({'annual_customer_tables': [row, row]})
    for key, value in [('local_path', '/Users/operator/private.json'), ('relations', [])]:
        bad = deepcopy(row)
        bad[key] = value
        with pytest.raises(ValueError):
            validator.validate({'annual_customer_tables': [bad]})


def test_atomic_annual_apply_preserves_prior_source_and_refuses_history_loss(tmp_path):
    capture = module('capture-contract-facts')
    source, output = tmp_path / 'source', tmp_path / 'out'
    source.mkdir(); output.mkdir()
    baseline = fixture()
    target = source / 'member_map_auto_evidence.json'
    target.write_text(json.dumps(baseline))
    previous = target.read_bytes()
    enriched = deepcopy(baseline)
    enriched['annual_customer_tables'] = [compact()]
    assert capture.apply_local(source, baseline, enriched, output)['applied'] is True
    assert json.loads(target.read_bytes()) == enriched
    assert (output / 'member_map_auto_evidence.before-apply.json').read_bytes() == previous
    with pytest.raises(ValueError, match='history-loss'):
        capture.apply_local(source, enriched, baseline, output)
    assert json.loads(target.read_bytes()) == enriched


def test_daily_public_builder_keeps_compact_source_unchanged():
    script = """
const fs = require('node:fs');
const assert = require('node:assert/strict');
const {buildPublicCatalog,mergePriorCaptures,validateDeliveryCatalog} = require('./scripts/member-map/build-public-source-filter.cjs');
const row = JSON.parse(fs.readFileSync(0,'utf8'));
const meta = {bytes:1,sha256:'a'.repeat(64)};
const base = buildPublicCatalog({generatedAt:'2026-10-08T00:00:00Z',
  universe:{_meta:{count:1,generated_at:'2026-10-08T00:00:00Z'},stocks:[{ticker:'027040',market:'KR',name:'서울전자통신'}]},
  chainSnippets:{updated_at:'2026-10-08T00:00:00Z',documents:[]},
  groupStructure:{updated_at:'2026-10-08T00:00:00Z',count:0,structures:{}},
  inputMetadata:{universe:meta,chainSnippets:meta,groupStructure:meta}});
const prior = {...base,annual_customer_tables:[row]};
validateDeliveryCatalog(prior);
const merged = mergePriorCaptures({...base,generatedAt:'2026-10-09T00:00:00Z'},prior);
assert.deepEqual(merged.annual_customer_tables,[row]);
assert.equal(merged.generatedAt,'2026-10-09T00:00:00Z');
assert.deepEqual(merged.relations,base.relations);
console.log('retained');
"""
    result = subprocess.run(['node', '-e', script], cwd=ROOT, input=json.dumps(compact()),
                            text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'retained'
