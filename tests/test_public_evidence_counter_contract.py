"""Cross-runtime counter contract using synthetic public evidence only."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess

import pytest

from api.intelligence.portfolio_evidence import PortfolioEvidenceError, _validate_artifact


ROOT = Path(__file__).resolve().parents[1]
STAMP = "2026-11-06T01:38:44Z"
DOCUMENT = {
    "ticker": "101010", "rcept_no": "20260323000001",
    "report_nm": "사업보고서", "rcept_dt": "20260323",
    "snippets": [{"anchor": "매출처", "char_start": 0, "char_end": 30,
                  "snippet": "첫달산업은 미지별테크에 부품을 공급합니다."}],
}
NODE_SETUP = """
const fs = require('node:fs');
const crypto = require('node:crypto');
const api = require('./scripts/member-map/build-public-source-filter.cjs');
const options = JSON.parse(fs.readFileSync(0, 'utf8'));
options.inputMetadata = Object.fromEntries(['universe','chainSnippets','groupStructure'].map(key => {
  const raw = Buffer.from(JSON.stringify(options[key]));
  return [key, {bytes: raw.length, sha256: crypto.createHash('sha256').update(raw).digest('hex')}];
}));
"""


def _options(documents):
    return {
        "generatedAt": STAMP,
        "universe": {"stocks": [
            {"ticker": "101010", "market": "KR", "name": "첫달산업"},
            {"ticker": "202020", "market": "KR", "name": "미지별테크"},
        ]},
        "chainSnippets": {"updated_at": STAMP, "documents": documents},
        "groupStructure": {"updated_at": STAMP, "structures": {}},
    }


def _node(options, body):
    result = subprocess.run(["node", "-e", NODE_SETUP + body], cwd=ROOT,
                            input=json.dumps(options), text=True,
                            capture_output=True, timeout=20, check=True)
    return json.loads(result.stdout)


@pytest.mark.parametrize("case,events,rejections", [
    ("single", 1, {}),
    ("same-receipt-distinct", 2, {}),
    ("same-excerpt", 1, {"duplicate_excerpt_event": 1}),
    ("unknown-empty", 0, {}),
    ("unknown-excerpt", 0, {"unknown_document_issuer": 1}),
])
def test_js_catalog_is_accepted_by_python_consumer(case, events, rejections):
    documents = [deepcopy(DOCUMENT)]
    if case.startswith("same-"):
        documents.append(deepcopy(DOCUMENT))
        if case == "same-receipt-distinct":
            documents[1]["snippets"][0].update(
                char_start=40, char_end=75,
                snippet="첫달산업은 미지별테크에 장비도 공급합니다.")
    if case.startswith("unknown-"):
        documents[0]["ticker"] = "999999"
        if case == "unknown-empty":
            documents[0]["snippets"] = []
    artifact = _node(_options(documents),
                     "process.stdout.write(JSON.stringify(api.buildPublicCatalog(options)));")
    _validate_artifact(artifact)
    assert len(artifact["events"]) == events
    assert artifact["rejectionReasons"] == rejections
    assert sum(rejections.values()) == (
        artifact["denominators"]["excerptsRejected"]
        + artifact["denominators"]["relationsRejected"])
    for event in artifact["events"].values():
        assert event["sourceDate"] == "2026-03-23"
    for source in artifact["sources"].values():
        assert source["sourceDate"] == "2026-03-23"
    assert artifact["artifactTimestamps"]["chainSnippetsUpdatedAt"] == STAMP


def test_bad_counter_blocks_replacement_of_last_good_bytes(tmp_path):
    destination = tmp_path / "catalog.json"
    original = b"last-good-byte-sentinel\n"
    destination.write_bytes(original)
    options = _options([deepcopy(DOCUMENT)])
    options["output"] = str(destination)
    result = _node(options, """
const prior = api.buildPublicCatalog(options);
prior.rejectionReasons.document_only_reason = 1;
prior.contract_facts = [];
options.priorCaptures = prior;
let rejected = false;
try { api.writePublicCatalog(options); }
catch { rejected = true; }
process.stdout.write(JSON.stringify({rejected, prior}));
""")
    assert result["rejected"]
    assert destination.read_bytes() == original
    with pytest.raises(PortfolioEvidenceError):
        _validate_artifact(result["prior"])


@pytest.mark.parametrize("invalid", [-1, 0.5, "1", 1])
def test_producer_rejects_invalid_counter_before_delivery(invalid):
    options = _options([deepcopy(DOCUMENT)])
    options["invalid"] = invalid
    assert _node(options, """
const catalog = api.buildPublicCatalog(options);
catalog.rejectionReasons.extra = options.invalid;
let rejected = false;
try { api.validatePublicCatalog(catalog); }
catch { rejected = true; }
process.stdout.write(JSON.stringify(rejected));
""") is True
