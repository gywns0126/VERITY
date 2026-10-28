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


def _bok_primary(monkeypatch, *, body="소비자 조사 지수는 100.0으로 전월과 같았다.", counter="3124"):
    page = (f'<dl><dt class="sr-only">등록일</dt><dd class="date">2026.10.27</dd>'
            f'<dt class="sr-only">조회수</dt><dd class="hits">{counter}</dd></dl>'
            f'<p>{body}</p>')
    class Response:
        headers = SimpleNamespace(get_content_charset=lambda: "utf-8")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, limit):
            return page.encode()
    monkeypatch.setattr(worker.urllib.request, "build_opener",
                        lambda *_: SimpleNamespace(open=lambda *a, **kw: Response()))
    return worker.read_official_text("https://www.bok.or.kr/official-release")


def test_bok_view_metadata_between_date_and_body_cannot_break_exact_quote(monkeypatch):
    source = _bok_primary(monkeypatch)
    quote = "2026.10.27 조회수 1960 소비자 조사 지수는 100.0으로 전월과 같았다."
    value = {region: [{"text": quote, "source_quote": quote, "source_date": "2026-10-27",
                      "source_url": "https://www.bok.or.kr/official-release"}]
             for region in ("global", "kr")}
    args = dict(now=datetime(2026, 10, 28, tzinfo=timezone.utc), reader=lambda _: source)
    verified = worker.verify_macro_facts(value, **args)
    delivered = "2026.10.27 소비자 조사 지수는 100.0으로 전월과 같았다."
    assert source == "등록일 " + delivered
    assert verified["kr"][0]["source_quote"] == delivered
    # Owner-side re-verification must accept the already sanitized producer quote.
    for region in value:
        value[region][0].update(text=delivered, source_quote=delivered)
    assert worker.verify_macro_facts(value, **args)["kr"][0]["text"] == delivered
    value["kr"][0]["text"] = "조회수는 1960건이었다."
    with pytest.raises(ValueError, match="unsupported_macro_number"):
        worker.verify_macro_facts(value, **args)


@pytest.mark.parametrize("change", [
    lambda q: q.replace("100.0", "101.0"),
    lambda q: q.replace("전월과 같았다", "전월보다 낮았다"),
    lambda q: q.replace("2026.10.27", "2026.10.28"),
])
def test_bok_counter_exception_never_hides_fact_or_date_change(monkeypatch, change):
    source = _bok_primary(monkeypatch)
    quote = change("2026.10.27 조회수 1960 소비자 조사 지수는 100.0으로 전월과 같았다.")
    value = {region: [{"text": quote, "source_quote": quote, "source_date": "2026-10-27",
                      "source_url": "https://www.bok.or.kr/official-release"}]
             for region in ("global", "kr")}
    with pytest.raises(ValueError, match="macro_quote_not_in_primary_source"):
        worker.verify_macro_facts(value, now=datetime(2026, 10, 28, tzinfo=timezone.utc),
                                  reader=lambda _: source)


def test_bok_article_prose_is_not_mistaken_for_view_metadata(monkeypatch):
    body = "조회수 1960 증가로 조사 지수가 변동하지 않았다는 공식 발표문이다."
    source = _bok_primary(monkeypatch, body=body)
    assert body in source and "3124" not in source
    quote = "2026.10.27 " + body
    value = {region: [{"text": quote, "source_quote": quote, "source_date": "2026-10-27",
                      "source_url": "https://www.bok.or.kr/official-release"}]
             for region in ("global", "kr")}
    with pytest.raises(ValueError, match="macro_quote_not_in_primary_source"):
        worker.verify_macro_facts(value, now=datetime(2026, 10, 28, tzinfo=timezone.utc),
                                  reader=lambda _: source)


@pytest.mark.parametrize("fields", [0, 2])
def test_bok_counter_omission_requires_one_actual_primary_metadata_field(fields):
    quote = "2026.10.27 조회수 1960 소비자 조사 지수는 100.0으로 전월과 같았다."
    source = worker.OfficialText("2026.10.27 소비자 조사 지수는 100.0으로 전월과 같았다.",
                                 bok_view_fields=fields)
    value = {region: [{"text": quote, "source_quote": quote, "source_date": "2026-10-27",
                      "source_url": "https://www.bok.or.kr/official-release"}]
             for region in ("global", "kr")}
    with pytest.raises(ValueError, match="macro_quote_not_in_primary_source"):
        worker.verify_macro_facts(value, now=datetime(2026, 10, 28, tzinfo=timezone.utc),
                                  reader=lambda _: source)


def test_bok_multiple_counter_fields_are_not_silently_removed(monkeypatch):
    source = _bok_primary(monkeypatch)
    quote = "2026.10.27 조회수 1960 조회수 1961 소비자 조사 지수는 100.0으로 전월과 같았다."
    value = {region: [{"text": quote, "source_quote": quote, "source_date": "2026-10-27",
                      "source_url": "https://www.bok.or.kr/official-release"}]
             for region in ("global", "kr")}
    with pytest.raises(ValueError, match="macro_quote_not_in_primary_source"):
        worker.verify_macro_facts(value, now=datetime(2026, 10, 28, tzinfo=timezone.utc),
                                  reader=lambda _: source)


def test_macro_prompt_names_the_enforced_hosts_without_new_attempt_identity(tmp_path, monkeypatch):
    def model(prompt, **options):
        assert all(host in prompt for host in worker.OFFICIAL_HOSTS)
        assert options["identity"].startswith("macro-facts-v1:protocol-v4:")
        raise ValueError("model_not_invoked")
    monkeypatch.setattr(worker, "read_json_with_codex", model)
    with pytest.raises(ValueError, match="model_not_invoked"):
        worker.run_macro(SimpleNamespace(cli=Path("/cli"), model="gpt-6.1-sol", runtime=tmp_path))


def test_prompt_alignment_does_not_add_the_previous_rejected_government_host():
    url = "https://m.korea.kr/official-release"
    with pytest.raises(ValueError, match="unapproved_macro_source"):
        worker._official_url(url)
    with pytest.raises(ValueError, match="unapproved_macro_source"):
        worker.OfficialRedirect().redirect_request(None, None, 302, "redirect", {}, url)
