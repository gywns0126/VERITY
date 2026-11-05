from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.utils import mini_codex_reader as cli
from scripts import mini_document_readers as worker


def test_cli_drops_provider_keys_and_keeps_saved_login_home():
    assert cli.cli_environment({"HOME": "/saved", "PATH": "/bin", "OPENAI_API_KEY": "sentinel",
        "CODEX_API_KEY": "sentinel", "GEMINI_API_KEY": "sentinel"}) == {"HOME": "/saved", "PATH": "/bin"}
    cmd = cli.command(Path("/cli"), Path("/job"), model="gpt-6.1-sol", search=False)
    assert "mcp_servers={}" in cmd and "--search" not in cmd
    assert "read-only" in cmd and "--output-schema" in cmd
    assert all(name in cmd for name in ("shell_tool", "unified_exec", "apps", "hooks", "multi_agent"))
    disabled = [cmd[i + 1] for i, value in enumerate(cmd) if value == "--disable"]
    enabled = [cmd[i + 1] for i, value in enumerate(cmd) if value == "--enable"]
    assert enabled == ["code_mode_host"] and "code_mode_host" not in disabled
    assert all(name in disabled for name in ("shell_tool", "apps", "multi_agent", "plugins"))
    assert 'web_search="disabled"' in cmd


def test_single_invocation_result_reused_and_no_raw_events_saved(tmp_path):
    calls = []
    def executor(args, **kwargs):
        calls.append(args)
        target = Path(args[args.index("--output-last-message") + 1])
        target.write_text(json.dumps({"result_json": '{"facilities": []}'}))
        return SimpleNamespace(returncode=0, stdout='{"type":"turn.completed"}\n', stderr="")
    options = dict(cli=Path("/cli"), model="gpt-6.1-sol", runtime=tmp_path, identity="source-fixed", executor=executor)
    first, receipt = cli.read_json_with_codex("public filing", **options)
    second, reused = cli.read_json_with_codex("public filing", **options)
    assert first == second == {"facilities": []}
    assert len(calls) == 1 and receipt["google_calls"] == 0 and reused["reused"]
    assert not list(tmp_path.rglob("events*"))


def test_uncertain_invocation_is_not_retried(tmp_path):
    calls = []
    def executor(*args, **kwargs):
        calls.append(1)
        return SimpleNamespace(returncode=1, stdout="", stderr="usage limit")
    options = dict(cli=Path("/cli"), model="gpt-6.1-sol", runtime=tmp_path, identity="fixed", executor=executor)
    with pytest.raises(ValueError, match="codex_nonzero"):
        cli.read_json_with_codex("public", **options)
    with pytest.raises(ValueError, match="previous_request_requires_review"):
        cli.read_json_with_codex("public", **options)
    assert len(calls) == 1


@pytest.mark.parametrize("raw", ['{"a":1,"a":2}', '{"a":NaN}'])
def test_strict_result_rejects_ambiguous_json(raw):
    with pytest.raises(ValueError):
        cli.strict_json(raw)


def facts():
    fact = {"text": "Policy rate is 4.00 percent.", "source_date": "2026-10-23",
            "source_url": "https://www.bok.or.kr/official-release",
            "source_quote": "October 23, 2026. The policy rate is 4.00 percent and this is an official statement."}
    return {"kr": [fact], "global": [dict(fact, source_url="https://www.federalreserve.gov/release")]}


def test_macro_requires_actual_primary_quote_and_numeric_support():
    now = datetime(2026, 10, 25, tzinfo=timezone.utc)
    good = facts()
    verified = worker.verify_macro_facts(good, now=now, reader=lambda _: good["kr"][0]["source_quote"])
    result = worker.macro_bundle(verified, model="gpt-6.1-sol", generated_at="2026-10-25T00:00:00+00:00")
    assert result["source_verification"] == "2/2" and result["google_calls"] == 0
    assert result["sources"]["codex_kr"]["source_as_of"] == "2026-10-23"
    with pytest.raises(ValueError, match="quote_not_in"):
        worker.verify_macro_facts(good, now=now, reader=lambda _: "Different text")
    good["kr"][0]["text"] = "Rate is 8.00 percent."
    with pytest.raises(ValueError, match="unsupported_macro_number"):
        worker.verify_macro_facts(good, now=now, reader=lambda _: good["kr"][0]["source_quote"])


def test_macro_date_cannot_be_fabricated_for_an_old_quote():
    old = facts()
    for region in old:
        old[region][0]["source_quote"] = "The policy rate is 4.00 percent and this is an old undated statement."
    with pytest.raises(ValueError, match="macro_date_not_in_same"):
        worker.verify_macro_facts(old, now=datetime(2026, 10, 25, tzinfo=timezone.utc),
                                  reader=lambda _: old["kr"][0]["source_quote"])


@pytest.mark.parametrize("url", ["http://www.bok.or.kr/a", "https://www.bok.or.kr.evil.test/a",
    "https://user:password@www.bok.or.kr/a", "https://127.0.0.1/a", "https://www.bok.or.kr:8443/a"])
def test_macro_source_cannot_escape_official_allowlist(url):
    with pytest.raises(ValueError):
        worker._official_url(url)


def test_macro_retired_cloud_reader_cannot_force_generation(tmp_path, monkeypatch):
    from api.intelligence import macro_synthesis as macro
    monkeypatch.setattr(macro, "OUT_PATH", str(tmp_path / "out.json"))
    monkeypatch.setattr(macro, "CACHE_PATH", str(tmp_path / "cache.json"))
    monkeypatch.setenv("GEMINI_API_KEY", "must-not-be-used")
    assert macro.synthesize_macro(force=True)["status"] == "pending_mini_producer"
    original = {"producer": "mac-mini-codex", "contract": "macro-facts-v1", "source_verification": "2/2",
                "generated_at": "2026-10-23T01:00:00+00:00", "sources": {}}
    (tmp_path / "out.json").write_text(json.dumps(original))
    assert macro.synthesize_macro(force=True)["generated_at"] == original["generated_at"]


def test_owner_dispatch_rechecks_public_source_and_preserves_generation(tmp_path):
    day = datetime.now(worker.KST).strftime("%Y-%m-%d")
    source = f"{day}. The policy rate is 4.00 percent in this official release."
    original = facts()
    for region in original:
        original[region][0].update(source_date=day, source_quote=source)
    verified = worker.verify_macro_facts(original, reader=lambda _: source)
    generated = worker.stamp()
    doc = worker.macro_bundle(verified, model="gpt-6.1-sol", generated_at=generated)
    doc["verified_at"] = generated
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"action": "mini_macro_facts", "client_payload": {"document": doc}}))
    env = {"GITHUB_EVENT_NAME": "repository_dispatch", "GITHUB_ACTOR": "owner", "GITHUB_REPOSITORY_OWNER": "owner"}
    checks = []
    def reader(url):
        checks.append(url)
        return source
    result = worker.receive_dispatch(event, root=tmp_path, reader=reader, environ=env)
    assert result["source_verification"] == "2/2" and len(checks) == 2
    saved = cli.strict_json((tmp_path / "data/macro_synthesis.json").read_bytes())
    assert saved["generated_at"] == generated and saved["google_calls"] == 0
    with pytest.raises(ValueError, match="actor_not_owner"):
        worker.receive_dispatch(event, root=tmp_path, reader=reader, environ=dict(env, GITHUB_ACTOR="other"))
    with pytest.raises(ValueError, match="quote_not_in_primary_source"):
        worker.receive_dispatch(event, root=tmp_path, reader=lambda _: "not the source", environ=env)
    doc["generated_at"] = "2020-01-01T00:00:00Z"
    event.write_text(json.dumps({"action": "mini_macro_facts", "client_payload": {"document": doc}}))
    with pytest.raises(ValueError, match="generation_clock"):
        worker.receive_dispatch(event, root=tmp_path, reader=reader, environ=env)


@pytest.mark.parametrize("ticker,currency", [("005930", "KRW"), ("005930.KS", "KRW"), ("AAPL", "USD")])
def test_manual_filing_identity_routes_correctly_without_advancing_rotation(tmp_path, monkeypatch, ticker, currency):
    def source(row):
        assert row["currency"] == currency
        raise ValueError("source_pending")
    monkeypatch.setattr(worker, "filing_input", source)
    args = SimpleNamespace(ticker=ticker, runtime=tmp_path, max_filings=1)
    result = worker.run_filings(args)
    assert result["results"][0]["reason"] == "source_pending"
    assert not (tmp_path / "filing-rotation.json").exists()


def test_cli_item_error_cannot_be_mistaken_for_completed_result(tmp_path):
    def executor(args, **kwargs):
        target = Path(args[args.index("--output-last-message") + 1])
        target.write_text(json.dumps({"result_json": '{"global": [], "kr": []}'}))
        return SimpleNamespace(returncode=0, stdout='{"type":"item.completed","item":{"type":"error","message":"tool unavailable"}}\n{"type":"turn.completed"}\n', stderr="")
    with pytest.raises(ValueError, match="codex_reader_item_error"):
        cli.read_json_with_codex("public", cli=Path("/cli"), model="gpt-6.1-sol", runtime=tmp_path,
                                identity="failed-tool", search=True, executor=executor)
    receipt = cli.strict_json(next(tmp_path.rglob("receipt.json")).read_bytes())
    assert receipt["status"] == "uncertain" and receipt["diagnostics"] == ["reader_item_error"]


def filing_refresh_executor(rows=None, mapping=None):
    rows = rows if rows is not None else [{"ticker": "005930", "name": "Public KR", "currency": "KRW", "account_route": "must-not-reach-reader"},
                                          {"ticker": "AAPL", "name": "Public US", "currency": "USD"}]
    mapping = mapping if mapping is not None else {"005930": "00126380", "0009K0": "01234567"}
    bodies = {"recommendations.json": json.dumps(rows).encode(), "mapping.json": json.dumps(mapping).encode()}
    calls = []
    def executor(command, **options):
        calls.append(command)
        assert options == {"capture_output": True, "timeout": 30}
        relative = command[2].split("/contents/", 1)[1]
        assert relative in ("data/recommendations.json?ref=main", "data/mapping.json?ref=main")
        return SimpleNamespace(returncode=0, stdout=bodies[relative.split("?", 1)[0].split("/")[-1]], stderr=b"")
    return executor, calls, bodies


def test_filing_source_refresh_validates_both_before_atomic_replace(tmp_path):
    executor, calls, bodies = filing_refresh_executor()
    (tmp_path / "data").mkdir(exist_ok=True)
    for filename in bodies:
        (tmp_path / "data" / filename).write_bytes(b"old source")
    rows, receipt = worker.refresh_filing_sources(root=tmp_path, executor=executor)
    assert len(calls) == 2 and receipt["validated"] == "2/2"
    assert receipt["candidates"] == 2 and receipt["mapping_entries"] == 2
    assert rows == [{"ticker": "005930", "name": "Public KR", "currency": "KRW", "corp_code": "00126380"},
                    {"ticker": "AAPL", "name": "Public US", "currency": "USD"}]
    for filename, body in bodies.items():
        assert cli.strict_json((tmp_path / "data" / filename).read_bytes()) == cli.strict_json(body)
    assert "account_route" not in str(rows) and "must-not-reach-reader" not in str(receipt)


@pytest.mark.parametrize("problem", ["request", "json", "mapping", "candidate", "size"])
def test_filing_refresh_failure_preserves_both_previous_files(tmp_path, problem):
    executor, calls, bodies = filing_refresh_executor()
    (tmp_path / "data").mkdir(exist_ok=True)
    for filename in bodies:
        (tmp_path / "data" / filename).write_bytes(b"previous")
    if problem == "json":
        bodies["mapping.json"] = b'{"a":1,"a":2}'
    elif problem == "mapping":
        bodies["mapping.json"] = b'{"005930":"invalid"}'
    elif problem == "candidate":
        bodies["recommendations.json"] = b'[{"ticker":"bad","name":"Name","currency":"KRW"}]'
    elif problem == "size":
        bodies["mapping.json"] = b" " * 1_048_577
    def request(command, **options):
        if problem == "request" and "mapping.json" in command[2]:
            return SimpleNamespace(returncode=1, stdout=b"", stderr=b"private auth diagnostic")
        return executor(command, **options)
    with pytest.raises(ValueError):
        worker.refresh_filing_sources(root=tmp_path, executor=request)
    assert len(calls) <= 2
    assert all((tmp_path / "data" / name).read_bytes() == b"previous" for name in bodies)


def test_refreshed_identities_drive_bounded_filing_rotation(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "refresh_filing_sources", lambda **_: ([
        {"ticker": "NEW", "name": "New public source", "currency": "USD"}], {"validated": "2/2"}))
    seen = []
    def source(row):
        seen.append(row["ticker"])
        raise ValueError("source_pending")
    monkeypatch.setattr(worker, "filing_input", source)
    result = worker.run_filings(SimpleNamespace(ticker=None, runtime=tmp_path, max_filings=3))
    assert seen == ["NEW"] and result["processed"] == result["total_candidates"] == 1
    assert result["source_refresh"]["validated"] == "2/2"


def test_failed_input_refresh_stops_filings_but_all_phase_continues_macro(tmp_path, monkeypatch):
    def failed(**_):
        raise ValueError("filing_source_refresh_unavailable")
    monkeypatch.setattr(worker, "refresh_filing_sources", failed)
    monkeypatch.setattr(worker, "filing_input", lambda _: pytest.fail("stale input used"))
    calls = []
    monkeypatch.setattr(worker, "run_macro", lambda _: calls.append("macro") or {"google_calls": 0})
    monkeypatch.setattr(worker.socket, "gethostname", lambda: "test-macmini")
    monkeypatch.setattr(worker.sys, "platform", "darwin")
    monkeypatch.setattr(worker.sys, "argv", ["worker", "--runtime", str(tmp_path), "--cli", "/cli"])
    assert worker.main() == 1 and calls == ["macro"]
    result = cli.strict_json((tmp_path / "latest.json").read_bytes())
    assert result["status"] == "partial" and result["filings"]["processed"] == 0
    assert result["filings"]["total_candidates"] is None
    assert result["filings"]["results"][0]["reason"] == "filing_source_refresh_unavailable"
    assert not (tmp_path / "filing-rotation.json").exists()


@pytest.mark.parametrize("domestic", [False, True])
def test_refreshed_filing_uses_same_exact_cache_as_existing_consumer(tmp_path, monkeypatch, domestic):
    from api.utils import filing_extraction_cache as cache
    if domestic:
        from api.analyzers.facilities_parser import build_business_facilities_prompt as build, validate_business_facilities_data as validate, parse_business_facilities as consume
        extractor, ticker, currency = "dart-facilities-v1", "005930", "KRW"
        source = {"source_id": "source:dart:20260318001234", "as_of": "2026-03-18", "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260318001234"}
    else:
        from api.analyzers.properties_parser import build_10k_properties_prompt as build, validate_10k_properties_data as validate, parse_10k_properties as consume
        extractor, ticker, currency = "sec-properties-v1", "AAPL", "USD"
        source = {"source_id": "source:sec:0000320193-25-000079", "as_of": "2025-10-31", "url": "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl.htm"}
    raw = "Public filing words. " * 40
    cache_root = tmp_path / "data/filing_extraction_cache"
    original_read, original_write, original_path = cache.cache_read, cache.cache_write, cache.filing_cache_path
    monkeypatch.setattr(cache, "cache_read", lambda **kw: original_read(cache_root=cache_root, **kw))
    monkeypatch.setattr(cache, "cache_write", lambda **kw: original_write(cache_root=cache_root, **kw))
    def cache_path(*a, **kw):
        kw["cache_root"] = cache_root
        return original_path(*a, **kw)
    monkeypatch.setattr(cache, "filing_cache_path", cache_path)
    monkeypatch.setattr(worker, "ROOT", tmp_path)
    monkeypatch.setattr(worker, "refresh_filing_sources", lambda **_: ([
        {"ticker": ticker, "name": "Public name", "currency": currency}], {"validated": "2/2"}))
    monkeypatch.setattr(worker, "filing_input", lambda _: (extractor, raw, source, build, validate))
    calls = []
    def model(prompt, **_):
        calls.append(prompt)
        return {"summary_ko": "Public source result"}, {"completed_at": "2026-10-26T00:00:00+00:00", "reused": False}
    monkeypatch.setattr(worker, "read_json_with_codex", model)
    args = SimpleNamespace(ticker=None, runtime=tmp_path, max_filings=1, cli=Path("/cli"), model="gpt-6.1-sol", publish=False)
    first, second = worker.run_filings(args), worker.run_filings(args)
    assert first["results"][0]["status"] == "ready" and second["results"][0]["status"] == "cache_hit"
    assert len(calls) == 1
    actual = consume("Public name", ticker, raw, source_id=source["source_id"], as_of=source["as_of"], source_url=source["url"], cache_root=cache_root)
    assert actual["summary_ko"] == "Public source result" and "error" not in actual


def test_krw_letter_prefixed_identity_never_enters_sec_collector(monkeypatch):
    from api.collectors import DartScout as dart
    calls = []
    def public_source(corp):
        calls.append(corp)
        return {"raw_text": "Public DART words", "rcept_no": "20260318001234", "rcept_dt": "20260318"}
    monkeypatch.setattr(dart, "fetch_business_facilities_raw", public_source)
    extractor, _, source, _, _ = worker.filing_input(
        {"ticker": "ABCDEF", "name": "Public KR", "currency": "KRW", "corp_code": "00126380"})
    assert calls == ["00126380"] and extractor == "dart-facilities-v1"
    assert source["source_id"] == "source:dart:20260318001234"


def kr_feed(*, url="https://www.bok.or.kr/portal/bbs/B0000501/view.do?nttId=123&menuNo=201264",
            published="Thu, 05 Nov 2026 08:00:00 +0900", count=1):
    from xml.sax.saxutils import escape
    item = f"<item><title>국제수지</title><link>{escape(url)}</link><pubDate>{published}</pubDate></item>"
    return ("<rss><channel>" + item * count + "</channel></rss>").encode()


KR_SOURCE = ("한국은행 보도자료 등록일 2026.11.05 키워드 국제수지 담당부서 국제수지팀(02-759-4570) "
             "첨부파일 BOP.hwp 다운로드 BOP.pdf 다운로드 뷰어 "
             "□ 2026년 9월 경상수지는 614.6억달러 흑자를 기록 □ 자세한 내용은 붙임 참조 목록 관련자료")
KR_NOW = datetime(2026, 11, 5, 12, tzinfo=worker.KST)


def test_korean_fact_uses_rss_for_discovery_and_exact_primary_html_for_evidence():
    reads = []
    fact = worker.korean_macro_fact(now=KR_NOW, feed_reader=lambda _: kr_feed(),
        reader=lambda url: reads.append(url) or KR_SOURCE)
    assert len(reads) == 1 and fact["source_date"] == "2026-11-05"
    assert fact["text"] == fact["source_quote"] and fact["source_quote"] in KR_SOURCE
    assert "614.6억달러" in fact["source_quote"] and "목록" not in fact["source_quote"]
    verified = worker.verify_macro_facts({"kr": [fact], "global": [fact]}, now=KR_NOW, reader=lambda _: KR_SOURCE)
    assert verified["kr"][0]["verification"] == "primary_quote_exact_match"


@pytest.mark.parametrize("problem", ["stale", "future", "undated", "date_mismatch", "pdf_only", "no_fact", "outside_quote", "entity", "foreign_host"])
def test_korean_fact_never_fills_missing_primary_evidence(problem):
    feed, source = kr_feed(), KR_SOURCE
    if problem == "stale":
        feed = kr_feed(published="Sun, 01 Nov 2026 08:00:00 +0900")
    elif problem == "future":
        feed = kr_feed(published="Fri, 06 Nov 2026 08:00:00 +0900")
    elif problem == "undated":
        source = source.replace("등록일 2026.11.05", "등록일 없음")
    elif problem == "date_mismatch":
        source = source.replace("등록일 2026.11.05", "등록일 2026.11.04")
    elif problem == "pdf_only":
        source = "등록일 2026.11.05 첨부파일 통계.pdf 다운로드 자세한 내용은 붙임 참조 목록"
    elif problem == "no_fact":
        source = "등록일 2026.11.05 담당부서 02-759-4000 첨부파일 총재.hwp 다운로드 출국 예정입니다 목록"
    elif problem == "outside_quote":
        source = "등록일 2026.11.05 " + "메타데이터 " * 100 + "□ 경상수지는 614.6억달러 흑자를 기록 목록"
    elif problem == "entity":
        feed = b'<!DOCTYPE rss [<!ENTITY x "bad">]><rss><channel/></rss>'
    elif problem == "foreign_host":
        feed = kr_feed(url="https://www.bok.or.kr.evil.test/portal/bbs/B0000501/view.do")
    with pytest.raises(ValueError, match="kr_primary_source_unavailable"):
        worker.korean_macro_fact(now=KR_NOW, feed_reader=lambda _: feed, reader=lambda _: source)


def test_korean_source_candidates_are_bounded_and_same_url_is_not_retried():
    reads = []
    with pytest.raises(ValueError, match="kr_primary_source_unavailable"):
        worker.korean_macro_fact(now=KR_NOW, feed_reader=lambda _: kr_feed(count=100),
            reader=lambda url: reads.append(url) or "no primary release")
    assert len(reads) == 1


def test_model_cannot_drop_korean_fact_collected_before_its_single_invocation(tmp_path, monkeypatch):
    fact = worker.korean_macro_fact(now=KR_NOW, feed_reader=lambda _: kr_feed(), reader=lambda _: KR_SOURCE)
    today = KR_NOW.date().isoformat()
    quote = f"{today}. The policy rate is 4.00 percent in this official release."
    global_fact = dict(text=quote, source_quote=quote, source_date=today,
                       source_url="https://www.federalreserve.gov/release")
    # Use the real count/quote/date validator with an injected primary reader.
    original_verify = worker.verify_macro_facts
    calls = []
    monkeypatch.setattr(worker, "ROOT", tmp_path)
    monkeypatch.setattr(worker, "korean_macro_fact", lambda: fact)
    monkeypatch.setattr(worker, "verify_macro_facts", lambda value: original_verify(value, now=KR_NOW,
        reader=lambda url: KR_SOURCE if "bok.or.kr" in url else quote))
    def model(prompt, **options):
        calls.append(options)
        assert "exactly one array: global" in prompt
        return {"global": [global_fact]}, {"completed_at": today + "T00:00:00+00:00", "reused": False}
    monkeypatch.setattr(worker, "read_json_with_codex", model)
    result = worker.run_macro(SimpleNamespace(cli=Path("/cli"), model="gpt-6.1-sol", runtime=tmp_path, publish=False))
    saved = cli.strict_json((tmp_path / "data/macro_synthesis.json").read_bytes())
    assert result["source_verification"] == "2/2" and len(calls) == 1
    assert saved["sources"]["codex_kr"]["facts"][0]["source_quote"] == fact["source_quote"]
    assert saved["sources"]["codex_kr"]["provider"] == "official-rss"
    assert saved["sources"]["codex_kr"]["model"] is None
    assert calls[0]["identity"].startswith("macro-facts-v1:protocol-v5:")


def test_unavailable_korean_source_stops_before_model_and_preserves_previous_artifact(tmp_path, monkeypatch):
    path = tmp_path / "data/macro_synthesis.json"
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(b"previous accepted artifact")
    monkeypatch.setattr(worker, "ROOT", tmp_path)
    monkeypatch.setattr(worker, "read_json_with_codex", lambda *a, **k: pytest.fail("model must not run"))
    def unavailable():
        raise ValueError("kr_primary_source_unavailable")
    monkeypatch.setattr(worker, "korean_macro_fact", unavailable)
    with pytest.raises(ValueError, match="kr_primary_source_unavailable"):
        worker.run_macro(SimpleNamespace())
    assert path.read_bytes() == b"previous accepted artifact"


def test_empty_region_is_still_rejected_by_existing_delivery_validator():
    with pytest.raises(ValueError, match="macro_fact_count"):
        worker.verify_macro_facts({"global": [], "kr": []})


def test_owner_receiver_preserves_direct_korean_provenance_and_rechecks_quote(tmp_path):
    day = datetime.now(worker.KST).strftime("%Y-%m-%d")
    quote = f"{day}. Official interest rates are unchanged at 4.00 percent."
    kr_url = "https://www.bok.or.kr/portal/bbs/B0000501/view.do?nttId=123"
    values = {region: [dict(text=quote, source_quote=quote, source_date=day,
        source_url=kr_url if region == "kr" else "https://www.federalreserve.gov/release")]
        for region in ("global", "kr")}
    verified = worker.verify_macro_facts(values, reader=lambda _: quote)
    generated = worker.stamp()
    doc = worker.macro_bundle(verified, model="gpt-6.1-sol", generated_at=generated, kr_direct=True)
    doc["verified_at"] = generated
    path = tmp_path / "event.json"
    path.write_text(json.dumps({"action": "mini_macro_facts", "client_payload": {"document": doc}}))
    env = {"GITHUB_EVENT_NAME": "repository_dispatch", "GITHUB_ACTOR": "owner", "GITHUB_REPOSITORY_OWNER": "owner"}
    calls = []
    worker.receive_dispatch(path, root=tmp_path, reader=lambda url: calls.append(url) or quote, environ=env)
    saved = cli.strict_json((tmp_path / "data/macro_synthesis.json").read_bytes())
    assert len(calls) == 2 and saved["generated_at"] == generated
    assert saved["sources"]["codex_kr"]["provider"] == "official-rss"
    assert saved["sources"]["codex_kr"]["model"] is None
    before = (tmp_path / "data/macro_synthesis.json").read_bytes()
    with pytest.raises(ValueError, match="macro_quote_not_in_primary_source"):
        worker.receive_dispatch(path, root=tmp_path, reader=lambda _: "changed primary text", environ=env)
    assert (tmp_path / "data/macro_synthesis.json").read_bytes() == before
    doc["sources"]["codex_kr"]["facts"][0]["source_url"] = "https://www.federalreserve.gov/release"
    path.write_text(json.dumps({"action": "mini_macro_facts", "client_payload": {"document": doc}}))
    with pytest.raises(ValueError, match="macro_dispatch_kr_source"):
        worker.receive_dispatch(path, root=tmp_path, reader=lambda _: quote, environ=env)


def test_kr_feed_failure_can_use_another_official_release_without_model_retry():
    feeds = []
    def feed(url):
        feeds.append(url)
        if url == worker.KR_RELEASE_FEEDS[0]:
            raise OSError("unavailable")
        return kr_feed()
    fact = worker.korean_macro_fact(now=KR_NOW, feed_reader=feed, reader=lambda _: KR_SOURCE)
    assert len(feeds) == 2 and fact["source_quote"] in KR_SOURCE
