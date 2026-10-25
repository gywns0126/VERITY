"""Protocol metadata normalization must not relax source/result validation."""
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.utils import mini_codex_reader as cli
from scripts import mini_document_readers as worker


def _execute(tmp_path, events, *, value='{"global":[],"kr":[]}'):
    def executor(args, **kwargs):
        target = Path(args[args.index("--output-last-message") + 1])
        target.write_text(json.dumps({"result_json": value}))
        return SimpleNamespace(returncode=0, stdout=events, stderr="")
    return cli.read_json_with_codex("public", cli=Path("/cli"), model="gpt-6.1-sol",
                                    runtime=tmp_path, identity="fixed", search=True, executor=executor)


def test_identical_protocol_metadata_is_unambiguous_and_counted(tmp_path):
    value, receipt = _execute(tmp_path,
        '{"type":"item.completed","item":{"type":"web_search","status":"completed","status":"completed"}}\n'
        '{"type":"turn.completed"}\n')
    assert value == {"global": [], "kr": []}
    assert receipt["protocol_identical_duplicate_keys"] == 1
    assert receipt["item_types"] == ["web_search"]


@pytest.mark.parametrize("events", [
    '{"type":"turn.failed","type":"turn.completed"}\n',
    '{"type":"item.completed","item":{"type":"mcp_tool_call","type":"web_search"}}\n{"type":"turn.completed"}\n',
    '{"type":"item.completed","item":{"type":"code_execution"}}\n{"type":"turn.completed"}\n',
])
def test_conflicting_protocol_and_unapproved_tools_fail_closed(tmp_path, events):
    with pytest.raises(ValueError):
        _execute(tmp_path, events)
    receipt = cli.strict_json(next(tmp_path.rglob("receipt.json")).read_bytes())
    assert receipt["status"] == "uncertain"


def test_source_and_result_duplicate_keys_remain_strict(tmp_path):
    with pytest.raises(ValueError, match="duplicate_json_key"):
        cli.strict_json('{"a":1,"a":1}')
    with pytest.raises(ValueError, match="duplicate_json_key"):
        _execute(tmp_path, '{"type":"turn.completed"}\n', value='{"global":[],"global":[],"kr":[]}')


def test_opaque_search_metadata_is_not_used_as_source_or_control_evidence(tmp_path):
    value, receipt = _execute(tmp_path,
        '{"type":"item.completed","item":{"type":"web_search","action":{"query":"first","query":"second"}}}\n'
        '{"type":"turn.completed"}\n')
    assert value == {"global": [], "kr": []}
    assert receipt["protocol_unused_metadata_duplicate_keys"] == 1
    assert receipt["item_types"] == ["web_search"]


def test_old_completed_error_receipt_cannot_be_reused(tmp_path):
    _, receipt = _execute(tmp_path, '{"type":"turn.completed"}\n')
    path = next(tmp_path.rglob("receipt.json"))
    receipt["item_types"] = ["agent_message", "error"]
    cli.atomic_json(path, receipt)
    with pytest.raises(ValueError, match="saved_receipt_requires_review"):
        _execute(tmp_path, '{"type":"turn.completed"}\n')


def test_primary_day_month_year_date_is_supported_without_fabrication():
    quote = "23 October 2026. An official consumer survey reported unchanged expectations."
    value = {region: [{"text": "소비자 기대가 전월과 같았다.", "source_date": "2026-10-23",
                      "source_url": "https://www.ecb.europa.eu/official-release", "source_quote": quote}]
             for region in ("global", "kr")}
    assert worker.verify_macro_facts(value, now=datetime(2026, 10, 26, tzinfo=timezone.utc),
                                     reader=lambda _: quote).keys() == value.keys()


def test_dynamic_trailing_view_counter_is_not_treated_as_a_macro_fact():
    quote = "공식 감독규정 개정안의 규정변경예고를 실시합니다. 2026-10-23"
    value = {region: [{"text": "감독규정 개정안의 규정변경예고를 실시했다.", "source_date": "2026-10-23",
                      "source_url": "https://www.fsc.go.kr/official-release", "source_quote": quote + " 조회수 : 12158"}]
             for region in ("global", "kr")}
    args = dict(now=datetime(2026, 10, 26, tzinfo=timezone.utc), reader=lambda _: quote + " 조회수 : 12213")
    result = worker.verify_macro_facts(value, **args)
    assert result["kr"][0]["source_quote"] == quote
    value["kr"][0]["text"] = "조회수는 12158건이었다."
    with pytest.raises(ValueError, match="unsupported_macro_number"):
        worker.verify_macro_facts(value, **args)


def test_contradictory_model_paraphrase_never_becomes_verified_content():
    quote = "October 23, 2026. The Committee decided to maintain the target range unchanged."
    value = {region: [{"text": "연준은 금리 인하를 결정했다.", "source_date": "2026-10-23",
                      "source_url": "https://www.federalreserve.gov/official-release", "source_quote": quote}]
             for region in ("global", "kr")}
    verified = worker.verify_macro_facts(value, now=datetime(2026, 10, 26, tzinfo=timezone.utc),
                                        reader=lambda _: quote)
    output = worker.macro_bundle(verified, model="gpt-6.1-sol", generated_at="2026-10-26T00:00:00+00:00")
    assert verified["global"][0]["text"] == quote
    assert "인하" not in json.dumps(output, ensure_ascii=False)
