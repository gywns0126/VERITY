"""합성 공개자료와 가짜 REST 응답만 사용하는 저장소 경계 검사."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import threading
from types import ModuleType

import pytest

from api.collectors import member_map_listing_delta as delta
from api.collectors import member_map_refresh_store as storage
from api.collectors.member_map_live_refresh import apply_result, overlay_states

NOW = "2026-10-12T01:00:00+00:00"
OWNER = "12345678-1234-4234-8234-123456789012"
CATALOG = {"stocks": [{"ticker": "123456", "market": "KR", "name": "합성 회사"}]}
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("supabase_refresh_runner", ROOT / "scripts/member-map/run-live-refresh.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def rejected(*args, **kwargs):
        pytest.fail("실제 네트워크 호출은 허용하지 않습니다")
    monkeypatch.setattr(storage.requests.sessions.Session, "request", rejected)
    monkeypatch.setattr(delta.requests, "get", rejected)


def page(*, number=1, count=1, total=1, size=100):
    rows = [{"rcept_no": f"20261012{i:06d}", "rcept_dt": "20261012", "stock_code": "123456",
             "report_nm": "합성 공시", "flr_nm": "합성 제출인"} for i in range(number, number + count)]
    return json.dumps({"status": "000", "page_no": number, "page_count": size,
                       "total_count": total, "total_page": (total + size - 1) // size, "list": rows}).encode()


def state():
    result = delta.collect_dart_delta({"123456": "합성 회사"}, {"items": []}, None, NOW, "synthetic-key",
                                     transport=lambda *args, **kwargs: page())
    return apply_result("DART", {}, result, NOW)


class Response:
    status_code = 200
    headers = {}
    def __init__(self, value, url):
        self.raw = value if isinstance(value, bytes) else json.dumps(value).encode()
        self.url = url
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def iter_content(self, chunk_size):
        yield self.raw


def fake_session(monkeypatch, value, *, status=200, headers=None, wrong_url=False):
    calls = []
    class Session:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def request(self, method, url, **kwargs):
            calls.append((method, url, kwargs, self.trust_env))
            response = Response(value, url + "/wrong" if wrong_url else url)
            response.status_code, response.headers = status, headers or {}
            return response
    monkeypatch.setattr(storage.requests, "Session", Session)
    return calls


def claim_response(*, previous=None, status="claimed"):
    return {"status": status, "source": "DART", "generation": 1, "revision": 0, "feed_revision": 0,
            "state": previous or {}, "lease_until": "2026-10-12T01:05:00+00:00", "request_day": "2026-10-12",
            "requests_reserved": 10, "request_budget": 10}


def test_catalog_fixed_keyless_get_and_rpc_fixed_private_post(monkeypatch):
    calls = fake_session(monkeypatch, CATALOG)
    assert storage.read_public_catalog() == CATALOG
    method, url, options, trust_env = calls[0]
    assert method == "GET" and url == storage.CATALOG_URL
    assert "Authorization" not in options["headers"] and "apikey" not in options["headers"]
    assert options["timeout"] == 3 and options["allow_redirects"] is False and not trust_env
    calls = fake_session(monkeypatch, claim_response())
    store = storage.RefreshStore("synthetic-role")
    assert store.claim("DART", OWNER)["request_budget"] == 10
    method, url, options, trust_env = calls[0]
    assert method == "POST" and url == storage.PROJECT_URL + "/rest/v1/rpc/member_map_refresh_claim"
    assert json.loads(options["data"])["p_request_budget"] == 10
    assert options["headers"]["Authorization"] == "Bearer synthetic-role"
    with pytest.raises(storage.RefreshStoreError):
        store._rpc("member_map_state", {})
    assert len(calls) == 1


@pytest.mark.parametrize("body,status,headers,wrong_url", [
    (b'{"status":"busy","status":"claimed"}', 200, {}, False),
    (b'{"value":NaN}', 200, {}, False),
    (b'key=synthetic-role', 401, {}, False),
    ({"status": "busy"}, 302, {}, False),
    ({"status": "busy"}, 200, {}, True),
    ({"status": "busy"}, 200, {"Content-Length": str(storage.RESPONSE_MAX_BYTES + 1)}, False),
])
def test_transport_rejects_without_retry_or_error_body(monkeypatch, body, status, headers, wrong_url):
    calls = fake_session(monkeypatch, body, status=status, headers=headers, wrong_url=wrong_url)
    with pytest.raises(storage.RefreshStoreError) as error:
        storage.RefreshStore("synthetic-role").claim("DART", OWNER)
    assert "synthetic-role" not in str(error.value) and "key=" not in str(error.value)
    assert len(calls) == 1


def test_actual_stream_limit_and_timeout(monkeypatch):
    fake_session(monkeypatch, b"x" * 10)
    with pytest.raises(storage.RefreshStoreError):
        storage._request_json("GET", storage.CATALOG_URL, headers={}, limit=9)
    stamps = iter((0, 4))
    monkeypatch.setattr(storage.time, "monotonic", lambda: next(stamps))
    with pytest.raises(storage.RefreshStoreError):
        storage._request_json("GET", storage.CATALOG_URL, headers={}, limit=20)


def test_read_exact_three_rows_aggregate_bound_and_deep_copy(monkeypatch):
    original = state()
    observed = []
    def read(method, url, **kwargs):
        observed.append((method, url, kwargs))
        if "select=source,revision,feed_revision" in url:
            return [{"source": "DART", "revision": 1, "feed_revision": 1},
                    {"source": "SEC", "revision": 0, "feed_revision": 0}, {"source": "news", "revision": 0, "feed_revision": 0}]
        return [{"source": "DART", "state": original, "revision": 1, "feed_revision": 1},
                {"source": "SEC", "state": {}, "revision": 0, "feed_revision": 0},
                {"source": "news", "state": {}, "revision": 0, "feed_revision": 0}]
    monkeypatch.setattr(storage, "_request_json", read)
    states = storage.RefreshStore("synthetic-role").read_states()
    method, url, options = observed[0]
    assert method == "GET" and url.endswith("?select=source,revision,feed_revision&source=in.(DART,SEC,news)&limit=3")
    assert options["limit"] == storage.ENVELOPE_MAX_BYTES
    assert observed[1][2]["limit"] == 12 * 1024 * 1024 + storage.ENVELOPE_MAX_BYTES
    assert observed[0][2]["deadline"] == observed[1][2]["deadline"]
    states["DART"]["feed"]["items"][0]["name"] = "다른 합성 회사"
    assert original["feed"]["items"][0]["name"] == "합성 회사"


@pytest.mark.parametrize("rows", [
    [{"source": "member", "state": {}, "revision": 0}],
    [{"source": "DART", "state": {}, "revision": 0, "lease_owner": OWNER}],
    [{"source": "DART", "state": {}, "revision": False}],
    [{"source": "DART", "state": {}, "revision": 0}] * 2,
    [{"source": "DART", "state": {}, "revision": 0}] * 4,
])
def test_read_rejects_wrong_rows(monkeypatch, rows):
    monkeypatch.setattr(storage, "_request_json", lambda *args, **kwargs: rows)
    with pytest.raises(storage.RefreshStoreError):
        storage.RefreshStore("synthetic-role").read_states()


@pytest.mark.parametrize("mutation", [
    lambda s: s.update(member_id="private"),
    lambda s: s.update(error="key=private"),
    lambda s: s["feed"].update(raw_body="private"),
    lambda s: s["feed"]["items"][0].update(account_id="private"),
    lambda s: s["feed"]["items"][0].update(ticker="wrong"),
    lambda s: s["feed"]["items"][0].update(ticker="１２３４５６"),
    lambda s: s["feed"]["items"][0].update(latest="2027-01-01"),
    lambda s: s["feed"]["items"][0]["disclosures"][0].update(source_url="https://dart.fss.or.kr.evil.test/x"),
    lambda s: s["feed"]["items"][0]["disclosures"][0].update(date="2026-02-30"),
    lambda s: s["feed"]["items"][0]["disclosures"][0].update(date_precision="timestamp"),
    lambda s: s["feed"]["items"][0]["disclosures"][0].update(title="DART_API_KEY private"),
    lambda s: s["feed"]["_meta"].update(source_collection={"checked_groups": 8}),
    lambda s: s["cursor"].update(owner_id="private"),
    lambda s: s["coverage"].update(whole_market_coverage=True),
    lambda s: s["health"].update(age_seconds=False),
])
def test_nested_private_identity_date_and_false_freshness_rejected(mutation):
    current = state()
    mutation(current)
    with pytest.raises(storage.RefreshStoreError):
        storage.validate_state("DART", current)


def test_state_size_and_config_rejected(monkeypatch):
    monkeypatch.setattr(storage, "STATE_MAX_BYTES", 10)
    with pytest.raises(storage.RefreshStoreError):
        storage.validate_state("DART", state())
    for key, url in (("", storage.PROJECT_URL), ("synthetic\nkey", storage.PROJECT_URL),
                     ("synthetic-role", "https://other.supabase.co")):
        with pytest.raises(storage.RefreshStoreError):
            storage.RefreshStore(key, project_url=url)


@pytest.mark.parametrize("denial", [{"status": "busy"}, {"status": "quota-blocked"},
    {"status": "budget-exhausted"}, {"status": "not-due", "retry_after_seconds": 120}])
def test_claim_denials_are_fixed(monkeypatch, denial):
    monkeypatch.setattr(storage, "_request_json", lambda *args, **kwargs: denial)
    assert storage.RefreshStore("synthetic-role").claim("DART", OWNER) == denial


def test_renew_and_save_exact_contract_no_retry_on_conflict(monkeypatch):
    replies = iter(({"status": "renewed", "source": "DART", "generation": 1, "revision": 0,
                     "lease_until": "2026-10-12T01:05:00+00:00"},
                    {"status": "saved", "source": "DART", "generation": 1, "revision": 1,
                     "feed_revision": 1, "updated_at": NOW}, {"status": "revision-conflict"}))
    calls = []
    def rpc(method, url, **kwargs):
        calls.append(json.loads(kwargs["body"]))
        return next(replies)
    monkeypatch.setattr(storage, "_request_json", rpc)
    store = storage.RefreshStore("synthetic-role")
    store.renew("DART", OWNER, 1)
    assert store.save("DART", OWNER, 1, 0, state())["revision"] == 1
    with pytest.raises(storage.RefreshStoreError, match="refresh-save-conflict"):
        store.save("DART", OWNER, 1, 0, state())
    assert len(calls) == 3 and calls[-1]["p_expected_revision"] == 0


class MemoryStore:
    def __init__(self, previous=None, denial=None, renew_failure=False, ambiguous_save=False):
        self.state = deepcopy(previous or {})
        self.denial, self.renew_failure, self.ambiguous_save = denial, renew_failure, ambiguous_save
        self.events, self.reserved, self.revision = [], 0, 0
    def read_states(self):
        return {"DART": deepcopy(self.state)}
    def claim(self, source, owner):
        self.events.append("claim")
        if self.denial:
            return {"status": self.denial}
        self.reserved += 10
        return {**claim_response(previous=self.state), "revision": self.revision}
    def renew(self, *args):
        self.events.append("renew")
        if self.renew_failure:
            raise storage.RefreshStoreError("refresh-lease-lost")
    def save(self, source, owner, generation, expected_revision, current):
        self.events.append("save")
        self.state = storage.validate_state(source, current)
        self.revision += 1
        if self.ambiguous_save:
            raise storage.RefreshStoreError("refresh-transport-failure")
        return {"revision": self.revision}


def test_runtime_reserves_before_provider_and_restart_120_second_cadence():
    store, calls = MemoryStore(), []
    def provider(endpoint, **kwargs):
        assert store.events[-1] == "renew" and store.reserved == 10
        assert endpoint == delta.DART_LIST
        calls.append(endpoint)
        return page()
    assert runner.supabase_cycle(store, CATALOG, "synthetic-key", OWNER, NOW, transport=provider)["status"] == "success"
    assert store.state["cursor"]["through_date"] == "2026-10-12"
    assert runner.supabase_cycle(store, CATALOG, "synthetic-key", OWNER, "2026-10-12T01:01:59+00:00", transport=provider)["status"] == "not-due"
    assert len(calls) == 1 and store.reserved == 10


@pytest.mark.parametrize("denial", ["already-claimed", "busy", "quota-blocked", "budget-exhausted", "not-due"])
def test_runtime_denials_never_start_second_provider_batch(denial):
    store = MemoryStore(denial=denial)
    assert runner.supabase_cycle(store, CATALOG, "synthetic-key", OWNER, NOW,
        transport=lambda *args, **kwargs: pytest.fail("거절 후 수집 금지"))["status"] == denial
    assert store.events == ["claim"]


def test_runtime_lease_loss_stops_provider_and_preserves_state():
    prior = state()
    store = MemoryStore(previous=prior, renew_failure=True)
    result = runner.supabase_cycle(store, CATALOG, "synthetic-key", OWNER, "2026-10-12T01:02:00+00:00",
                                 transport=lambda *args, **kwargs: pytest.fail("만료 lease 호출 금지"))
    assert result == {"status": "lease-lost", "requests": 0}
    assert store.state == prior and "save" not in store.events and store.reserved == 10


def test_runtime_020_preserves_prior_and_delivers_only_block_code():
    prior = state()
    store = MemoryStore(previous=prior)
    result = runner.supabase_cycle(store, CATALOG, "synthetic-key", OWNER, "2026-10-12T01:02:00+00:00",
        transport=lambda *args, **kwargs: b'{"status":"020","message":"key=private"}')
    assert result["error"] == "dart-quota-exceeded" and store.state["status"] == "error"
    for field in ("feed", "cursor", "last_success_at"):
        assert store.state[field] == prior[field]
    assert "private" not in json.dumps(store.state) and store.reserved == 10


def test_ambiguous_save_restart_retains_committed_state_without_second_collection():
    store = MemoryStore(ambiguous_save=True)
    with pytest.raises(storage.RefreshStoreError):
        runner.supabase_cycle(store, CATALOG, "synthetic-key", OWNER, NOW, transport=lambda *args, **kwargs: page())
    assert runner.supabase_cycle(store, CATALOG, "synthetic-key", OWNER, NOW,
        transport=lambda *args, **kwargs: pytest.fail("불명확 저장 후 중복 수집 금지"))["status"] == "not-due"
    assert store.reserved == 10 and store.state["last_success_at"] == NOW


def test_supabase_cli_dry_run_no_credentials_and_sqlite_required_options(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["runner", "--backend", "supabase", "--duration-seconds", "86400"])
    monkeypatch.setattr(storage.RefreshStore, "from_environment", lambda: pytest.fail("dry-run 키 조회 금지"))
    runner.main()
    printed = json.loads(capsys.readouterr().out)
    assert printed["network_requests"] == 0 and printed["disabled_sources"] == ["SEC", "news"]
    monkeypatch.setattr(sys, "argv", ["runner"])
    with pytest.raises(SystemExit) as error:
        runner.main()
    assert error.value.code == 2
    monkeypatch.setattr(sys, "argv", ["runner", "--backend", "supabase", "--sources", "SEC"])
    with pytest.raises(SystemExit) as error:
        runner.main()
    assert error.value.code == 2


def test_runtime_exact_120_second_boundary_and_fresh_reservation():
    store = MemoryStore()
    runner.supabase_cycle(store, CATALOG, "synthetic-key", OWNER, NOW, transport=lambda *args, **kwargs: page())
    outcome = runner.supabase_cycle(store, CATALOG, "synthetic-key", OWNER, "2026-10-12T01:02:00+00:00",
                                   transport=lambda *args, **kwargs: page())
    assert outcome["status"] == "success" and store.reserved == 20 and store.revision == 2
    assert store.state["last_success_at"] == "2026-10-12T01:02:00+00:00"


def test_runtime_maximum_ten_pages_no_refund_and_partial_retention():
    prior = state()
    store, calls = MemoryStore(previous=prior), []
    def provider(endpoint, **kwargs):
        number = int(kwargs["params"]["page_no"])
        calls.append(number)
        rows = [{"rcept_no": f"20261012{i:06d}", "rcept_dt": "20261012", "stock_code": "123456",
                 "report_nm": "합성 공시", "flr_nm": "합성 제출인"} for i in range((number-1)*100+1, number*100+1)]
        return json.dumps({"status": "000", "page_no": number, "page_count": 100,
                           "total_count": 1100, "total_page": 11, "list": rows}).encode()
    outcome = runner.supabase_cycle(store, CATALOG, "synthetic-key", OWNER, "2026-10-12T01:02:00+00:00", transport=provider)
    assert calls == list(range(1, 11)) and store.reserved == 10
    assert outcome["error"] == "page_limit" and outcome["requests"] == 10
    assert store.state["cursor"] == prior["cursor"] and store.state["last_success_at"] == prior["last_success_at"]
    assert len(store.state["feed"]["items"][0]["disclosures"]) == 8


def test_runtime_provider_timeout_keeps_last_good_without_refund():
    prior = state()
    store = MemoryStore(previous=prior)
    def provider(*args, **kwargs):
        raise TimeoutError("private upstream detail")
    outcome = runner.supabase_cycle(store, CATALOG, "synthetic-key", OWNER, "2026-10-12T01:02:00+00:00", transport=provider)
    assert outcome["requests"] == 1 and store.reserved == 10
    assert "private" not in json.dumps(outcome)
    for key in ("feed", "cursor", "last_success_at"):
        assert store.state[key] == prior[key]


def test_runtime_loop_cadence_no_provider_after_duration(monkeypatch, capsys):
    clock, starts = [0.0], []
    monkeypatch.setattr(runner.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(runner.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0]+seconds))
    monkeypatch.setattr(storage.RefreshStore, "from_environment", lambda **_: object())
    monkeypatch.setenv("DART_API_KEY", "synthetic-key")
    def cycle(*args):
        starts.append(clock[0]); clock[0] += 20
        return {"status": "success", "requests": 1}
    monkeypatch.setattr(runner, "supabase_cycle", cycle)
    runner.run_supabase(CATALOG, 240)
    assert starts == [0, 120] and clock[0] == 240
    assert all(json.loads(line)["disabled_sources"] == ["SEC", "news"] for line in capsys.readouterr().out.splitlines())


def test_memory_overlay_reuses_existing_merge_without_touching_ai_or_price():
    current = storage.validate_state("DART", state())
    docs = {"public_disclosure_feed.json": {"items": [{"ticker": "654321", "name": "기존 합성 회사", "disclosures": []}]},
            "member_map_ai_candidates.json": {"sentinel": "keep"}, "portfolio.json": {"price": "keep"}}
    merged = overlay_states(docs, {"DART": current})
    assert {row["ticker"] for row in merged["public_disclosure_feed.json"]["items"]} == {"123456", "654321"}
    assert merged["member_map_ai_candidates.json"] is docs["member_map_ai_candidates.json"]
    assert merged["portfolio.json"] is docs["portfolio.json"]
    assert len(docs["public_disclosure_feed.json"]["items"]) == 1


def test_package_neutral_copy_imports_no_collector_observability_or_environment(monkeypatch):
    package = ModuleType("refresh_api_fixture")
    package.__path__ = []
    monkeypatch.setitem(sys.modules, package.__name__, package)
    source_spec = importlib.util.spec_from_file_location(package.__name__ + ".portfolio_public_sources",
        ROOT / "vercel-api/api/portfolio_core/portfolio_public_sources.py")
    sources = importlib.util.module_from_spec(source_spec)
    monkeypatch.setitem(sys.modules, source_spec.name, sources)
    source_spec.loader.exec_module(sources)
    store_spec = importlib.util.spec_from_file_location(package.__name__ + ".member_map_refresh_store", Path(storage.__file__))
    copied = importlib.util.module_from_spec(store_spec)
    def rejected(*args, **kwargs):
        pytest.fail("복제 모듈 import에서 환경값을 조회하면 안 됩니다")
    monkeypatch.setattr(storage.os, "getenv", rejected)
    store_spec.loader.exec_module(copied)
    assert copied._public_helpers() is sources
    assert copied.validate_state("DART", state()) == state()


def cached_rest(monkeypatch):
    """동일 table의 head/body/3RPC 응답만 만드는 합성 저장소."""
    ledger = {"DART": {"state": state(), "revision": 1, "feed_revision": 1},
              "SEC": {"state": {}, "revision": 0, "feed_revision": 0},
              "news": {"state": {}, "revision": 0, "feed_revision": 0}}
    calls = []
    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if method == "GET":
            selected = url.split("source=in.(")[1].split(")")[0].split(",")
            keys = ("state", "revision", "feed_revision") if "select=source,state," in url else ("revision", "feed_revision")
            return [{"source": source, **{key: deepcopy(ledger[source][key]) for key in keys}} for source in selected]
        payload = json.loads(kwargs["body"])
        row, source = ledger[payload["p_source"]], payload["p_source"]
        if url.endswith("member_map_refresh_claim"):
            return {**claim_response(), "source": source, "revision": row["revision"], "feed_revision": row["feed_revision"],
                    "state": None if payload["p_known_revision"] == row["revision"] else deepcopy(row["state"])}
        if url.endswith("member_map_refresh_save"):
            assert payload["p_expected_revision"] == row["revision"]
            row["feed_revision"] += int(row["state"].get("feed") != payload["p_state"].get("feed"))
            row["state"], row["revision"] = deepcopy(payload["p_state"]), row["revision"] + 1
            return {"status": "saved", "source": source, "generation": payload["p_generation"],
                    "revision": row["revision"], "feed_revision": row["feed_revision"], "updated_at": NOW}
        return {"status": "renewed", "source": source, "generation": payload["p_generation"],
                "revision": row["revision"], "lease_until": "2026-10-12T01:05:00+00:00"}
    monkeypatch.setattr(storage, "_request_json", request)
    return ledger, calls, request


def test_cross_worker_same_feed_metadata_does_not_advance_cached_state_revision(monkeypatch):
    ledger, calls, _ = cached_rest(monkeypatch)
    store = storage.RefreshStore("synthetic-role")
    original = store.read_states()["DART"]
    later = "2026-10-12T01:02:00+00:00"
    refreshed = apply_result("DART", original, {"status": "success", "complete": True, "records": [],
        "cursor": {**original["cursor"], "checked_at": later}, "requests": 1, "error": None, "coverage": {}}, later)
    assert refreshed["feed"] == original["feed"]
    ledger["DART"].update(state=refreshed, revision=2)
    before = len(calls)
    assert store.read_states()["DART"] == original
    assert len(calls) == before + 1 and store._state_revisions["DART"] == 1
    claimed = store.claim("DART", OWNER)
    assert json.loads(calls[-1][2]["body"])["p_known_revision"] == 1
    assert claimed["revision"] == 2 and claimed["state"]["last_success_at"] == later
    failed = apply_result("DART", claimed["state"], {"status": "error", "complete": False, "requests": 1,
        "error": "transport_failure", "coverage": {}}, "2026-10-12T01:04:00+00:00")
    saved = store.save("DART", OWNER, 1, 2, failed)
    assert saved["revision"] == 3 and saved["feed_revision"] == 1
    assert store._state_revisions["DART"] == 3 and store._states["DART"]["last_success_at"] == later


def test_warm_null_claim_reuses_only_exact_cached_full_state_and_compact_save(monkeypatch):
    ledger, calls, _ = cached_rest(monkeypatch)
    store = storage.RefreshStore("synthetic-role")
    original = store.read_states()["DART"]
    assert store.claim("DART", OWNER)["state"] == original
    assert json.loads(calls[-1][2]["body"])["p_known_revision"] == 1
    failed = apply_result("DART", original, {"status": "error", "complete": False, "requests": 1,
        "error": "transport_failure", "coverage": {}}, "2026-10-12T01:02:00+00:00")
    saved = store.save("DART", OWNER, 1, 1, failed)
    assert "state" not in saved and set(saved) == {"status", "source", "generation", "revision", "feed_revision", "updated_at"}
    assert store.claim("DART", OWNER)["state"] == failed
    assert json.loads(calls[-1][2]["body"])["p_known_revision"] == 2
    assert ledger["DART"]["feed_revision"] == 1
    monkeypatch.setattr(storage, "_request_json", lambda *args, **kwargs: {**claim_response(), "state": None})
    with pytest.raises(storage.RefreshStoreError):
        storage.RefreshStore("synthetic-role").claim("DART", OWNER)


def test_changed_feed_reads_only_changed_source_and_keeps_other_sources(monkeypatch):
    ledger, calls, _ = cached_rest(monkeypatch)
    store = storage.RefreshStore("synthetic-role")
    before = store.read_states()
    result = delta.collect_dart_delta({"123456": "합성 회사"}, before["DART"]["feed"], before["DART"]["cursor"],
        "2026-10-12T01:02:00+00:00", "synthetic-key", transport=lambda *args, **kwargs: page(number=2))
    changed = apply_result("DART", before["DART"], result, "2026-10-12T01:02:00+00:00")
    ledger["DART"].update(state=changed, revision=2, feed_revision=2)
    assert store.read_states()["DART"] == changed
    assert "source=in.(DART)&limit=3" in calls[-1][1]
    assert calls[-1][2]["limit"] == storage.STATE_MAX_BYTES + storage.ENVELOPE_MAX_BYTES
    assert store._states["SEC"] == before["SEC"] and store._states["news"] == before["news"]


def test_unknown_save_forces_body_reread_without_caching_unacknowledged_submission(monkeypatch):
    ledger, calls, request = cached_rest(monkeypatch)
    store = storage.RefreshStore("synthetic-role")
    original = store.read_states()["DART"]
    failed = apply_result("DART", original, {"status": "error", "complete": False, "requests": 1,
        "error": "transport_failure", "coverage": {}}, "2026-10-12T01:02:00+00:00")
    def ambiguous(method, url, **kwargs):
        result = request(method, url, **kwargs)
        if url.endswith("member_map_refresh_save"):
            raise storage.RefreshStoreError("refresh-transport-failure")
        return result
    monkeypatch.setattr(storage, "_request_json", ambiguous)
    with pytest.raises(storage.RefreshStoreError):
        store.save("DART", OWNER, 1, 1, failed)
    assert store._states["DART"] == original and store._state_revisions["DART"] == 1
    assert store.read_states()["DART"] == failed
    assert "source=in.(DART)&limit=3" in calls[-1][1]
    assert store._state_revisions["DART"] == 2 and not store._uncertain_sources


def test_head_body_revision_race_and_failed_lookup_do_not_mutate_cache(monkeypatch):
    ledger, _, request = cached_rest(monkeypatch)
    store = storage.RefreshStore("synthetic-role")
    original = store.read_states()
    ledger["DART"].update(revision=2, feed_revision=2)
    def race(method, url, **kwargs):
        if "select=source,state," in url:
            ledger["DART"]["revision"] += 1
        return request(method, url, **kwargs)
    monkeypatch.setattr(storage, "_request_json", race)
    with pytest.raises(storage.RefreshStoreError):
        store.read_states()
    assert store._states == original and store._state_revisions["DART"] == 1


def test_reader_deadline_covers_head_body_and_validation(monkeypatch):
    _, _, request = cached_rest(monkeypatch)
    store = storage.RefreshStore("synthetic-role")
    clock, deadlines = [0.0], []
    def timed(method, url, **kwargs):
        deadlines.append(kwargs["deadline"])
        clock[0] += 2
        return request(method, url, **kwargs)
    monkeypatch.setattr(storage.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(storage, "_request_json", timed)
    with pytest.raises(storage.RefreshStoreError, match="refresh-read-timeout"):
        store.read_states()
    assert deadlines == [3, 3] and store._states == {}


def test_late_read_result_cannot_commit_and_does_not_spawn_repeated_workers(monkeypatch):
    _, _, request = cached_rest(monkeypatch)
    monkeypatch.setattr(storage, "RPC_TIMEOUT_SECONDS", 0.03)
    store = storage.RefreshStore("synthetic-role")
    entered, release = threading.Event(), threading.Event()
    def blocked(method, url, **kwargs):
        entered.set(); release.wait(1)
        return request(method, url, **kwargs)
    monkeypatch.setattr(storage, "_request_json", blocked)
    with pytest.raises(storage.RefreshStoreError, match="refresh-read-timeout"):
        store.read_states()
    assert entered.is_set()
    with pytest.raises(storage.RefreshStoreError, match="refresh-read-busy"):
        store.read_states()
    release.set()
    assert store._read_inflight.wait(1) and store._states == {} and store._state_revisions == {}


def test_midnight_bootstrap_reads_yesterday_today_then_only_boundary_day():
    store, windows = MemoryStore(), []
    def provider(endpoint, **kwargs):
        windows.append((kwargs["params"]["bgn_de"], kwargs["params"]["end_de"]))
        return page() if len(windows) == 1 else b'{"status":"013"}'
    first = runner.supabase_cycle(store, CATALOG, "synthetic-key", OWNER, "2026-10-12T15:00:30+00:00", transport=provider)
    assert first["status"] == "success" and store.state["feed"]["items"][0]["disclosures"][0]["date"] == "2026-10-12"
    assert store.state["cursor"]["through_date"] == "2026-10-13"
    runner.supabase_cycle(store, CATALOG, "synthetic-key", OWNER, "2026-10-12T15:02:30+00:00", transport=provider)
    assert windows == [("20261012", "20261013"), ("20261013", "20261013")]
    assert store.reserved == 20
