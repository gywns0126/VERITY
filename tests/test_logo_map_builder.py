import collections
import hashlib
import io
import json

import pytest
from PIL import Image

from api.builders import logo_map_builder as builder


def _url(ticker):
    return f"https://static.toss.im/png-icons/securities/icn-sec-fill-{ticker}.png"


def _sample_inputs():
    logos = {}
    stocks = []
    for market, prefix, count in (("KR", "KR", 4), ("ETF", "ETF", 4), ("US", "US", 4), ("OTHER", "X", 8)):
        for i in range(count):
            ticker = f"{prefix}{i:03d}"
            logos[ticker] = _url(ticker)
            stocks.append({"ticker": ticker, "market": market})
    return {"logos": logos}, {"stocks": stocks}


def test_stratified_sample_is_deterministic_and_host_bounded():
    doc, universe = _sample_inputs()
    first = builder._stratified_logo_sample(doc, universe)
    second = builder._stratified_logo_sample(doc, universe)
    assert first == second
    assert len(first) == len({row["ticker"] for row in first}) == 16
    assert collections.Counter(row["group"] for row in first) == {"KR": 4, "ETF": 4, "US": 4, "random": 4}
    assert all(builder._is_toss_logo_url(row["url"]) for row in first)
    assert not builder._is_toss_logo_url("https://evil.example/png-icons/securities/icn-sec-fill-X.png")
    assert not builder._is_toss_logo_url("https://static.toss.im.evil.example/png-icons/securities/icn-sec-fill-X.png")


def test_verify_receipt_does_not_rewrite_map_and_caps_body(monkeypatch, tmp_path):
    doc, universe = _sample_inputs()
    map_path = tmp_path / "logo_map.json"
    universe_path = tmp_path / "universe_search.json"
    original = json.dumps(doc, separators=(",", ":")).encode()
    map_path.write_bytes(original)
    universe_path.write_text(json.dumps(universe))
    monkeypatch.setattr(builder, "OUT_PATH", str(map_path))
    monkeypatch.setattr(builder, "UNIVERSE_SEARCH", str(universe_path))

    image = Image.new("RGB", (3, 3))
    image.putdata([(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255), (0, 0, 0), (10, 20, 30), (40, 50, 60), (70, 80, 90), (100, 110, 120)])
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    payload = buf.getvalue()
    read_limits = []

    class Response:
        headers = {"content-type": "image/png"}
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def getcode(self): return 200
        def geturl(self): return "https://static.toss.im/png-icons/securities/icn-sec-fill-OK.png"
        def read(self, limit):
            read_limits.append(limit)
            return payload[:limit]

    monkeypatch.setattr(builder, "_open_toss_url", lambda request, timeout: Response())
    receipt_path = tmp_path / "receipt.json"
    assert builder.verify_existing_toss_urls(str(receipt_path)) == 0

    receipt = json.loads(receipt_path.read_text())
    assert map_path.read_bytes() == original
    assert receipt["map_sha256"] == hashlib.sha256(original).hexdigest()
    assert receipt["selected"] == receipt["checked"] == receipt["passed"] == 16
    assert receipt["total"] == len(doc["logos"])
    assert set(read_limits) == {builder._VERIFY_MAX_BODY + 1}
    encoded_receipt = receipt_path.read_text()
    assert "KR000" not in encoded_receipt and "static.toss.im/png-icons" not in encoded_receipt


def _result(sample, *, blocked=False, block_code=403, ok=False):
    return {
        "group": sample["group"], "url_sha256": hashlib.sha256(sample["url"].encode()).hexdigest(),
        "host": builder._TOSS_HOST, "http_status": block_code if blocked else (200 if ok else None),
        "content_type": "image/png" if ok else "", "bytes_read": 100 if ok else 0,
        "body_truncated": False, "width": 2 if ok else None, "height": 2 if ok else None,
        "sha256": "f" * 64 if ok else "", "decoded": ok, "blank": False if ok else None,
        "query_ok": ok, "source_quality_bad": False, "ok": ok,
        "failure": "http_status" if blocked else ("" if ok else "timeout"),
        "elapsed_ms": 1.0, "stop_required": blocked,
    }


@pytest.mark.parametrize("blocked_code", [403, 429])
def test_403_or_429_stops_later_batches_and_same_map_is_not_retried(monkeypatch, tmp_path, blocked_code):
    doc, universe = _sample_inputs()
    map_path = tmp_path / "logo_map.json"
    universe_path = tmp_path / "universe_search.json"
    original = json.dumps(doc).encode()
    map_path.write_bytes(original)
    universe_path.write_text(json.dumps(universe))
    monkeypatch.setattr(builder, "OUT_PATH", str(map_path))
    monkeypatch.setattr(builder, "UNIVERSE_SEARCH", str(universe_path))
    selected = builder._stratified_logo_sample(doc, universe)
    calls = []
    blocked_tickers = {selected[0]["ticker"]}

    def check(sample):
        calls.append(sample["ticker"])
        return _result(sample, blocked=sample["ticker"] in blocked_tickers, block_code=blocked_code, ok=sample["ticker"] not in blocked_tickers)

    monkeypatch.setattr(builder, "_check_toss_logo", check)
    receipt_path = tmp_path / "receipt.json"
    assert builder.verify_existing_toss_urls(str(receipt_path)) == 1
    receipt = json.loads(receipt_path.read_text())
    assert receipt["status"] == "source_blocked"
    assert receipt["source_blocked"] is True and receipt["all_records_revalidated"] is False
    assert receipt["selected"] == 16 and receipt["checked"] == 2
    assert len(calls) == 2
    assert map_path.read_bytes() == original

    calls.clear()
    assert builder.verify_existing_toss_urls(str(receipt_path)) == 1
    assert calls == []


def test_zero_success_and_time_budget_are_receipted_without_map_write(monkeypatch, tmp_path):
    doc, universe = _sample_inputs()
    map_path = tmp_path / "logo_map.json"
    universe_path = tmp_path / "universe_search.json"
    original = json.dumps(doc).encode()
    map_path.write_bytes(original)
    universe_path.write_text(json.dumps(universe))
    monkeypatch.setattr(builder, "OUT_PATH", str(map_path))
    monkeypatch.setattr(builder, "UNIVERSE_SEARCH", str(universe_path))
    monkeypatch.setattr(builder, "_check_toss_logo", lambda sample: _result(sample))

    zero_receipt = tmp_path / "zero.json"
    assert builder.verify_existing_toss_urls(str(zero_receipt)) == 1
    zero = json.loads(zero_receipt.read_text())
    assert zero["status"] == "source_or_quality_error"
    assert zero["selected"] == zero["checked"] == 16 and zero["passed"] == 0
    assert zero["source_quality_bad"] == 0 and zero["source_quality_unverified"] == 16
    assert zero["all_records_revalidated"] is False
    zero_projection_path = tmp_path / "zero-projection.json"
    zero_projection_path.write_text(json.dumps(_receipt(original, total=20, selected=16, checked=16, passed=0, blocked=False)))
    zero_projection = builder.validate_logo_map_source_receipt(
        str(zero_projection_path), str(map_path), expected_total=20,
        now=builder.datetime.fromisoformat("2026-10-21T15:40:00+00:00"))
    assert "completed_at" not in zero_projection
    assert zero_projection["all_records_revalidated"] is False
    assert map_path.read_bytes() == original

    calls = []
    monkeypatch.setattr(builder, "_check_toss_logo", lambda sample: calls.append(sample) or _result(sample, ok=True))
    partial_receipt = tmp_path / "partial.json"
    assert builder.verify_existing_toss_urls(str(partial_receipt), max_seconds=0) == 1
    partial = json.loads(partial_receipt.read_text())
    assert partial["selected"] == 16 and partial["checked"] == 0
    assert partial["status"] == "partial" and partial["all_records_revalidated"] is False
    assert calls == [] and map_path.read_bytes() == original


def test_unapproved_host_is_rejected_without_network(monkeypatch):
    calls = []
    monkeypatch.setattr(builder, "_open_toss_url", lambda *args, **kwargs: calls.append(args))
    result = builder._check_toss_logo({"group": "test", "url": "https://example.invalid/logo.png"})
    assert result["failure"] == "unapproved_host_or_path"
    assert result["stop_required"] is False
    assert calls == []


def test_response_redirect_to_unapproved_host_is_rejected(monkeypatch):
    class Response:
        headers = {"content-type": "image/png"}
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def getcode(self): return 200
        def geturl(self): return "https://example.invalid/redirected.png"
        def read(self, limit): raise AssertionError("redirect response body must not be read")

    monkeypatch.setattr(builder, "_open_toss_url", lambda *args, **kwargs: Response())
    result = builder._check_toss_logo({"group": "test", "url": _url("OK")})
    assert result["failure"] == "unapproved_redirect_target"
    assert result["query_ok"] is False and result["ok"] is False


def test_zero_fetch_normal_run_preserves_map_and_freshness_metadata(monkeypatch, tmp_path):
    map_path = tmp_path / "logo_map.json"
    universe_path = tmp_path / "universe_search.json"
    report_path = tmp_path / "stock_report_public.json"
    domains_path = tmp_path / "kr_corp_domains.json"
    doc = {
        "_meta": {"generated_at": "old", "source": "existing", "logo_source": "non_toss"},
        "logos": {"000001": "ticker/000001.KS", "ETF1": "domain/example.org", "AAPL": "ticker/AAPL"},
        "colors": {"000001": "#123456"}, "shapes": {"000001": 1.2}, "style": {"padS": 8},
        "_tried": {},
    }
    original = json.dumps(doc, separators=(",", ":")).encode()
    map_path.write_bytes(original)
    universe = {"stocks": [
        {"ticker": "000001", "market": "KR", "name": "Example"},
        {"ticker": "ETF1", "market": "ETF", "name": "Unknown brand"},
        {"ticker": "AAPL", "market": "US", "name": "Example"},
    ]}
    universe_path.write_text(json.dumps(universe))
    report_path.write_text(json.dumps({"stocks": [{"ticker": "000001", "market": "KOSPI"}]}))
    domains_path.write_text(json.dumps({"domains": {}}))
    monkeypatch.setattr(builder, "OUT_PATH", str(map_path))
    monkeypatch.setattr(builder, "UNIVERSE_SEARCH", str(universe_path))
    monkeypatch.setattr(builder, "KR_REPORT", str(report_path))
    monkeypatch.setattr(builder, "KR_DOMAINS", str(domains_path))
    monkeypatch.setattr(builder, "_cid", lambda: "offline-test")
    monkeypatch.delenv("LOGO_MAP_VERIFY_EXISTING", raising=False)
    monkeypatch.delenv("LOGO_FALLBACK_BACKFILL", raising=False)
    monkeypatch.delenv("LOGO_COLOR_BACKFILL", raising=False)

    assert builder.main() == 0
    assert map_path.read_bytes() == original


def test_incremental_write_preserves_existing_color_style_metadata(monkeypatch, tmp_path):
    map_path = tmp_path / "logo_map.json"
    universe_path = tmp_path / "universe_search.json"
    report_path = tmp_path / "stock_report_public.json"
    domains_path = tmp_path / "kr_corp_domains.json"
    original_doc = {
        "_meta": {"generated_at": "old", "logo_source": "existing"},
        "logos": {"OLD001": "ticker/OLD001.KS"},
        "colors": {"OLD001": "#123456"}, "shapes": {"OLD001": 1.2}, "style": {"padS": 8},
        "_tried": {},
    }
    map_path.write_text(json.dumps(original_doc))
    universe_path.write_text(json.dumps({"stocks": [{"ticker": "000001", "market": "KR", "name": "Example"}]}))
    report_path.write_text(json.dumps({"stocks": [{"ticker": "000001", "market": "KOSPI"}]}))
    domains_path.write_text(json.dumps({"domains": {}}))
    monkeypatch.setattr(builder, "OUT_PATH", str(map_path))
    monkeypatch.setattr(builder, "UNIVERSE_SEARCH", str(universe_path))
    monkeypatch.setattr(builder, "KR_REPORT", str(report_path))
    monkeypatch.setattr(builder, "KR_DOMAINS", str(domains_path))
    monkeypatch.setattr(builder, "_cid", lambda: "offline-test")
    monkeypatch.setattr(builder, "_resolve_kr", lambda *args: "ticker/000001.KS")
    monkeypatch.delenv("LOGO_MAP_VERIFY_EXISTING", raising=False)
    monkeypatch.delenv("LOGO_FALLBACK_BACKFILL", raising=False)
    monkeypatch.delenv("LOGO_COLOR_BACKFILL", raising=False)

    assert builder.main() == 0
    updated = json.loads(map_path.read_text())
    assert updated["logos"]["000001"] == "ticker/000001.KS"
    for field in ("colors", "shapes", "style"):
        assert updated[field] == original_doc[field]


def _receipt(map_bytes, *, total=20, selected=16, checked=12, passed=10, blocked=True, checked_at="2026-10-21T15:31:37+00:00"):
    failed = checked - passed
    results = []
    for index in range(checked):
        ok = index < passed
        code = 200 if ok else (403 if blocked else None)
        results.append({"group": "test", "host": "static.toss.im", "http_status": code,
                        "content_type": "image/png" if ok else "",
                        "ok": ok, "decoded": ok, "blank": not ok if code == 200 else None,
                        "stop_required": code in (403, 429), "source_quality_bad": False})
    return {
        "checked_at": checked_at, "map_sha256": hashlib.sha256(map_bytes).hexdigest(),
        "source_host": "static.toss.im", "selected": selected, "checked": checked,
        "passed": passed, "failed": failed, "total": total, "results": results,
        "source_blocked": blocked,
        "status": "source_blocked" if blocked else ("partial" if checked < selected else ("sampled" if passed == selected else "source_or_quality_error")),
        "source_quality_bad": 0,
    }


def test_receipt_validator_projects_actual_partial_block_without_full_freshness(tmp_path):
    map_path = tmp_path / "logo_map.json"
    doc, _ = _sample_inputs()
    map_path.write_text(json.dumps(doc))
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(_receipt(map_path.read_bytes())))
    checked_at = builder.datetime.fromisoformat("2026-10-21T15:40:00+00:00")

    result = builder.validate_logo_map_source_receipt(
        str(receipt_path), str(map_path), now=checked_at)
    assert result["clock_kind"] == "bounded_logo_url_query"
    assert result["bound_query_incomplete"] is True
    assert result["scope_counts"] == {"selected": 16, "attempted": 12, "passed": 10, "failed": 2, "unattempted": 4, "total": 20}
    assert result["status"] == "source_blocked"
    assert result["quality_reason"] == "source_access_stop"
    assert result["all_records_revalidated"] is False
    assert "completed_at" not in result


def test_receipt_validator_rejects_future_naive_wrong_hash_and_status(tmp_path):
    map_path = tmp_path / "logo_map.json"
    doc, _ = _sample_inputs()
    map_path.write_text(json.dumps(doc))
    receipt_path = tmp_path / "receipt.json"
    now = builder.datetime.fromisoformat("2026-10-21T15:40:00+00:00")

    receipt = _receipt(map_path.read_bytes(), checked_at="2026-10-21T15:41:00+00:00")
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="future"):
        builder.validate_logo_map_source_receipt(str(receipt_path), str(map_path), expected_total=20, now=now)

    receipt = _receipt(map_path.read_bytes(), checked_at="2026-10-21T15:30:00")
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="timezone"):
        builder.validate_logo_map_source_receipt(str(receipt_path), str(map_path), expected_total=20, now=now)

    receipt = _receipt(map_path.read_bytes())
    receipt["status"] = "sampled"
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="status"):
        builder.validate_logo_map_source_receipt(str(receipt_path), str(map_path), expected_total=20, now=now)

    receipt = _receipt(map_path.read_bytes())
    receipt["map_sha256"] = "0" * 64
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="hash"):
        builder.validate_logo_map_source_receipt(str(receipt_path), str(map_path), expected_total=20, now=now)


def test_blocked_legacy_receipt_freezes_retries_unless_explicit_resume(monkeypatch, tmp_path):
    doc, universe = _sample_inputs()
    map_path = tmp_path / "logo_map.json"
    universe_path = tmp_path / "universe_search.json"
    map_bytes = json.dumps(doc).encode()
    map_path.write_bytes(map_bytes)
    universe_path.write_text(json.dumps(universe))
    legacy_path = tmp_path / "legacy.json"
    legacy_path.write_text(json.dumps({"map_sha256": hashlib.sha256(map_bytes).hexdigest(),
                                       "stopped_on_403_or_429": True}))
    monkeypatch.setattr(builder, "OUT_PATH", str(map_path))
    monkeypatch.setattr(builder, "UNIVERSE_SEARCH", str(universe_path))
    monkeypatch.setattr(builder, "_VERIFY_LEGACY_RECEIPT", str(legacy_path))
    calls = []
    monkeypatch.setattr(builder, "_check_toss_logo", lambda sample: calls.append(sample) or _result(sample, ok=True))

    assert builder.verify_existing_toss_urls(str(tmp_path / "current.json")) == 1
    assert calls == []
    assert builder.verify_existing_toss_urls(str(tmp_path / "resumed.json"), resume=True) == 0
    assert len(calls) == 16


def test_normal_builder_does_not_migrate_temporary_toss_source(monkeypatch, tmp_path):
    map_path = tmp_path / "logo_map.json"
    original = json.dumps({"_meta": {"logo_source": "toss_temp"}, "logos": {"T1": _url("T1")}}, separators=(",", ":")).encode()
    map_path.write_bytes(original)
    monkeypatch.setattr(builder, "OUT_PATH", str(map_path))
    monkeypatch.setattr(builder, "_cid", lambda: (_ for _ in ()).throw(AssertionError("must not read or call Brandfetch")))
    monkeypatch.delenv("LOGO_MAP_VERIFY_EXISTING", raising=False)
    assert builder.main() == 0
    assert map_path.read_bytes() == original
