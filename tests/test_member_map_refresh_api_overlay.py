"""Exact deployed reader integration, synthetic public facts only, no network."""
from copy import deepcopy
import importlib
import io
import json
from pathlib import Path
import sys
import types
import urllib.error

import pytest

PACKAGE = "map_refresh_api_test"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(Path(__file__).resolve().parents[1] / "vercel-api/api/portfolio_core")]
sys.modules[PACKAGE] = package
fetch = importlib.import_module(PACKAGE + ".portfolio_public_fetch")
STAMP = "2026-10-12T12:00:00+00:00"


def state():
    receipt = "20261012000001"
    row = {"id": "DART:" + receipt, "title": "검수용 공개 공시", "label": "DART",
           "date": "2026-10-12", "date_precision": "date", "source_date_field": "rcept_dt",
           "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + receipt,
           "source": "DART", "is_correction": False, "filer": "검수 회사", "observed_at": STAMP}
    return {"status": "success", "error": None, "last_attempt_at": STAMP, "last_success_at": STAMP,
            "requests": 1, "coverage": {"whole_market_coverage": False},
            "health": {"status": "on-time", "age_seconds": 0},
            "screen_delivery_verified": False, "analysis_delivery_verified": False,
            "cursor": {"source": "DART", "through_date": "2026-10-12",
                       "ids": [row["id"]], "checked_at": STAMP},
            "feed": {"items": [{"ticker": "000001", "name": "검수 회사", "latest": "2026-10-12",
                                "disclosures": [row]}],
                     "_meta": {"generated_at": STAMP, "count": 1, "disclosure_count": 1}}}


def baseline(name):
    if name in ("stock_report_public.json", "us_stock_report_public.json"):
        return {"stocks": []}
    if name == "us_disclosure_feed.json":
        return {"items": []}
    if name == "kr_business_overview_public.json":
        return {"rows": []}
    if name == "public_disclosure_feed.json":
        return {"items": [{"ticker": "000002", "name": "기존 회사", "disclosures": []}]}
    if name == "universe_search.json":
        return {"stocks": [{"ticker": "000001", "name": "검수 회사", "market": "KR"},
                           {"ticker": "000002", "name": "기존 회사", "market": "KR"}]}
    if name == "member_map_ai_candidates.json":
        return {"sentinel": "existing-unreviewed-source"}
    return {}


@pytest.fixture(autouse=True)
def reset():
    fetch._reset_cache_for_tests()
    yield
    fetch._reset_cache_for_tests()


def test_checkpoint_facts_reach_existing_projection_without_private_state():
    calls = []
    def reader():
        calls.append(True)
        return {"DART": state()}
    bundle = fetch.fetch_public_sources(_fetcher=baseline, _clock=lambda: 0, _refresh_reader=reader)
    assert calls == [True]
    docs = bundle["documents"]
    assert len(docs["public_disclosure_feed.json"]["items"]) == 2
    assert docs["member_map_ai_candidates.json"] == baseline("member_map_ai_candidates.json")
    helpers = importlib.import_module(PACKAGE + ".portfolio_public_sources")
    projection = helpers.project_public_sources(docs)
    company = next(c for c in projection["companies"] if c["ticker"] == "000001")
    assert company["documents"][0]["title"] == "검수용 공개 공시"
    assert company["documents"][0]["as_of"] == "2026-10-12"
    serialized = json.dumps(bundle)
    assert all(key not in serialized for key in ("cursor", "lease_owner", "last_success_at",
                                                "SUPABASE_SERVICE_ROLE_KEY", "screen_delivery_verified"))
    assert set(bundle["coverage"]) == {"expected", "available", "missing", "status"}


def test_optional_read_failure_retains_last_good_fact_without_new_clock():
    before = fetch.fetch_public_sources(_fetcher=baseline, _clock=lambda: 0,
                                       _refresh_reader=lambda: {"DART": state()})
    def failed():
        raise RuntimeError("never-return-secret-body")
    after = fetch.fetch_public_sources(_fetcher=baseline, _clock=lambda: 61, _refresh_reader=failed)
    assert after == before
    assert "never-return-secret-body" not in json.dumps(after)


@pytest.mark.parametrize("invalid", ["unknown-source", "private-field", "wrong-source-url"])
def test_invalid_checkpoint_keeps_existing_bundle(invalid):
    expected = fetch.fetch_public_sources(_fetcher=baseline, _clock=lambda: 0)
    changed = {"DART": state()}
    if invalid == "unknown-source":
        changed = {"member": state()}
    elif invalid == "private-field":
        changed["DART"]["feed"]["items"][0]["member_id"] = "private"
    else:
        changed["DART"]["feed"]["items"][0]["disclosures"][0]["source_url"] = "https://private.invalid/"
    actual = fetch.fetch_public_sources(_fetcher=baseline, _clock=lambda: 61, _refresh_reader=lambda: changed)
    assert actual == expected
    assert "private.invalid" not in json.dumps(actual)


def test_explicit_source_fixture_never_reads_optional_private_store(monkeypatch):
    monkeypatch.setattr(fetch, "_refresh_overlay", lambda *_: pytest.fail("fixture caused private read"))
    result = fetch.fetch_public_sources(_fetcher=baseline)
    assert result["coverage"]["status"] == "complete"


@pytest.mark.parametrize("mode,extra_hashes", [
    ("unmodified", 0), ("replaced", 1), ("equal-replaced", 1), ("removed", 0),
])
def test_overlay_hash_reuse_preserves_full_rehash_revision(monkeypatch, mode, extra_hashes):
    names = ("universe_search.json", "public_disclosure_feed.json",
             "member_map_auto_evidence.json", "member_map_ai_candidates.json")
    documents = {name: baseline(name) for name in names}
    expected = deepcopy(documents)
    checkpoints = {"DART": state()} if mode == "replaced" else {}
    if mode == "replaced":
        live = importlib.import_module(PACKAGE + ".member_map_live_refresh")
        expected = live.overlay_states(expected, checkpoints)
    elif mode in ("equal-replaced", "removed"):
        def overlay(current, _reader):
            result = current.copy()
            if mode == "removed":
                result.pop("universe_search.json")
            else:
                result["universe_search.json"] = deepcopy(result["universe_search.json"])
            return result
        monkeypatch.setattr(fetch, "_refresh_overlay", overlay)
        if mode == "removed":
            expected.pop("universe_search.json")

    canonical_hash = fetch._document_revision
    hash_calls = []
    def counted_hash(document):
        hash_calls.append(True)
        return canonical_hash(document)
    monkeypatch.setattr(fetch, "_document_revision", counted_hash)
    result = fetch.fetch_public_sources(
        _fetcher=lambda name: documents.get(name), _clock=lambda: 0,
        _refresh_reader=lambda: checkpoints)
    assert len(hash_calls) == len(names) + extra_hashes
    assert result["documents"] == expected
    assert documents == {name: baseline(name) for name in names}
    assert result["revision"] == fetch._bundle_revision(
        {name: canonical_hash(document) for name, document in expected.items()})
    assert result["coverage"] == {
        "expected": len(fetch.PUBLIC_SOURCE_FILES), "available": len(expected),
        "missing": [name for name in fetch.PUBLIC_SOURCE_FILES if name not in expected],
        "status": "partial",
    }


def test_production_cold_and_warm_copy_counts_keep_return_isolation(monkeypatch, capsys):
    downloads, reads, bundle_copies = [], [], []
    original_copy = fetch._copy_public_bundle

    def download(name):
        downloads.append(name)
        return json.loads(json.dumps(baseline(name)))

    def reader():
        reads.append(True)
        return {"DART": state()}

    def counted_copy(value):
        if type(value) is dict and set(value) == {"documents", "coverage", "revision"}:
            bundle_copies.append(True)
        return original_copy(value)

    monkeypatch.setattr(fetch, "_download_source", download)
    monkeypatch.setattr(fetch, "_REFRESH_STORE", types.SimpleNamespace(read_states=reader))
    monkeypatch.setattr(fetch, "_copy_public_bundle", counted_copy)
    # 다운로드·갱신 주입 인자 없이 고정 읽기 경로를 사용합니다. 시계만 고정합니다.
    cold = fetch.fetch_public_sources(_clock=lambda: 0)
    assert bundle_copies == [True]
    assert sorted(downloads) == sorted(fetch.PUBLIC_SOURCE_FILES)
    assert reads == [True]
    assert fetch._CACHE_EXPIRES_AT == fetch.CACHE_TTL_SECONDS
    assert cold == fetch._CACHE_RESULT and cold is not fetch._CACHE_RESULT
    cached_stocks = fetch._CACHE_RESULT["documents"]["universe_search.json"]["stocks"]
    assert cold["documents"]["universe_search.json"]["stocks"] is not cached_stocks
    cold["documents"]["universe_search.json"]["stocks"][0]["name"] = "첫 반환값의 변이"
    cold["coverage"]["missing"].append("반환값에서만 추가된 항목")

    warm = fetch.fetch_public_sources(_clock=lambda: fetch.CACHE_TTL_SECONDS - 0.1)
    assert bundle_copies == [True, True]
    assert len(downloads) == len(fetch.PUBLIC_SOURCE_FILES) and reads == [True]
    assert warm["documents"]["universe_search.json"] == baseline("universe_search.json")
    assert warm["coverage"]["missing"] == []
    warm["documents"]["universe_search.json"]["stocks"].clear()
    assert cached_stocks == baseline("universe_search.json")["stocks"]
    lines = [line for line in capsys.readouterr().err.splitlines()
             if line.startswith("member_map_public_fetch ")]
    assert len(lines) == 2
    assert "cache=miss status=complete available=16" in lines[0]
    assert "cache=hit status=complete available=16" in lines[1]
    assert all("revalidated=0" in line for line in lines)
    assert all("lock_wait_ms=" in line and "copy_ms=" in line and "elapsed_ms=" in line
               for line in lines)
    assert all("검수 회사" not in line and "Bearer" not in line and "http" not in line
               for line in lines)


def test_public_bundle_copy_preserves_shared_aliases_and_nested_isolation():
    shared = {"rows": [{"title": "검수 회사"}]}
    source = {"documents": {"first": shared, "second": shared},
              "coverage": {"missing": []}, "revision": "a" * 64}
    copied = fetch._copy_public_bundle(source)
    assert copied == source and copied is not source
    assert copied["documents"]["first"] is copied["documents"]["second"]
    assert copied["documents"]["first"] is not shared
    copied["documents"]["first"]["rows"][0]["title"] = "변경"
    assert source["documents"]["first"]["rows"][0]["title"] == "검수 회사"


def test_production_failed_news_overlay_separates_live_cache_and_return(monkeypatch):
    news = state()
    news.update(status="partial", requests=None, cursor=None, last_success_at=None,
                health={"status": "unknown", "age_seconds": None},
                feed={"headlines": [{"title": "공개 검수 기사", "source": "Reuters",
                                     "link": "https://www.reuters.com/world/checked-public-news/",
                                     "time": STAMP}]})
    live_states = {"news": news}
    original_copy = fetch.deepcopy
    original_bundle_copy = fetch._copy_public_bundle
    bundle_copies, state_copies = [], []

    def failed_reader():
        raise TimeoutError("합성 갱신 실패")

    def counted_copy(value):
        if value is live_states:
            state_copies.append(True)
        return original_copy(value)

    def counted_bundle_copy(value):
        bundle_copies.append(True)
        return original_bundle_copy(value)

    monkeypatch.setattr(fetch, "_LIVE_STATES", live_states)
    monkeypatch.setattr(fetch, "_REFRESH_STORE", types.SimpleNamespace(read_states=failed_reader))
    monkeypatch.setattr(fetch, "_download_source", lambda name: json.loads(json.dumps(baseline(name))))
    monkeypatch.setattr(fetch, "deepcopy", counted_copy)
    monkeypatch.setattr(fetch, "_copy_public_bundle", counted_bundle_copy)
    cold = fetch.fetch_public_sources(_clock=lambda: 0)
    assert bundle_copies == [True] and state_copies == [True]
    live_row = live_states["news"]["feed"]["headlines"][0]
    cached_row = fetch._CACHE_RESULT["documents"]["portfolio.json"]["headlines"][0]
    returned_row = cold["documents"]["portfolio.json"]["headlines"][0]
    assert cached_row is not live_row and returned_row is not cached_row and returned_row is not live_row
    assert cached_row == returned_row == live_row
    live_row["title"] = "전역 상태의 변이"
    returned_row["title"] = "반환값의 변이"
    warm = fetch.fetch_public_sources(_clock=lambda: 1)
    assert bundle_copies == [True, True] and state_copies == [True]
    assert warm["documents"]["portfolio.json"]["headlines"][0]["title"] == "공개 검수 기사"
    cached_row["title"] = "캐시의 변이"
    assert live_row["title"] == "전역 상태의 변이"
    assert returned_row["title"] == "반환값의 변이"
    assert warm["documents"]["portfolio.json"]["headlines"][0]["title"] == "공개 검수 기사"


def test_fixed_url_304_reuses_only_prior_validated_document_and_hash(monkeypatch, capsys):
    target = "universe_search.json"
    etag = '"' + "a" * 32 + '"'
    calls = []
    revision_calls = []
    original_revision = fetch._document_revision

    class Response(io.BytesIO):
        status = 200
        def __init__(self, url, body, headers):
            super().__init__(body)
            self.url, self.headers = url, headers
        def geturl(self):
            return self.url

    class Opener:
        addheaders = []
        def open(self, request, timeout):
            name = request.full_url.rsplit("/", 1)[-1]
            sent = dict(request.header_items()).get("If-none-match")
            calls.append((name, sent))
            if name == target and sent == etag:
                raise urllib.error.HTTPError(request.full_url, 304, "unchanged",
                                             {"ETag": etag}, io.BytesIO())
            body = json.dumps(baseline(name)).encode()
            return Response(request.full_url, body,
                            {"Content-Length": str(len(body)),
                             "ETag": etag if name == target else "invalid\r\netag"})

    monkeypatch.setattr(fetch.urllib.request, "build_opener", lambda *_: Opener())
    monkeypatch.setattr(fetch, "_REFRESH_STORE", types.SimpleNamespace(read_states=lambda: {}))
    monkeypatch.setattr(fetch, "_document_revision", lambda document: (
        revision_calls.append(True) or original_revision(document)))

    first = fetch.fetch_public_sources(_clock=lambda: 0)
    assert len(revision_calls) == len(fetch.PUBLIC_SOURCE_FILES)
    assert sorted(calls) == sorted((name, None) for name in fetch.PUBLIC_SOURCE_FILES)
    first["documents"][target]["stocks"].clear()

    second = fetch.fetch_public_sources(_clock=lambda: 61)
    assert second["coverage"]["status"] == "complete"
    assert second["revision"] == first["revision"]
    assert second["revision"] == fetch._bundle_revision({
        name: original_revision(document) for name, document in second["documents"].items()})
    assert second["documents"][target] == baseline(target)
    assert len(revision_calls) == 2 * len(fetch.PUBLIC_SOURCE_FILES) - 1
    assert sorted(calls[len(fetch.PUBLIC_SOURCE_FILES):]) == sorted(
        (name, etag if name == target else None) for name in fetch.PUBLIC_SOURCE_FILES)
    assert fetch._VALIDATED_SOURCES[target][2] is not second["documents"][target]
    lines = [line for line in capsys.readouterr().err.splitlines()
             if line.startswith("member_map_public_fetch ")]
    assert len(lines) == 2
    assert "cache=miss" in lines[0] and "revalidated=0" in lines[0]
    assert "cache=miss" in lines[1] and "revalidated=1" in lines[1]
    assert all(etag not in line and "http" not in line for line in lines)


@pytest.mark.parametrize("mode", ["changed", "wrong-304", "missing-304"])
def test_revalidation_never_promotes_unvalidated_or_failed_source(monkeypatch, capsys, mode):
    target = "universe_search.json"
    url = fetch.PUBLIC_SOURCE_URLS[target]
    etag = '"' + "a" * 32 + '"'
    revised_etag = '"' + "b" * 32 + '"'
    phase = [0]

    class Response(io.BytesIO):
        status = 200
        def __init__(self, body, received):
            super().__init__(body)
            self.headers = {"ETag": received, "Content-Length": str(len(body))}
        def geturl(self):
            return url

    class Opener:
        addheaders = []
        def open(self, request, timeout):
            if request.full_url != url:
                raise urllib.error.HTTPError(request.full_url, 404, "missing", {}, io.BytesIO())
            sent = dict(request.header_items()).get("If-none-match")
            if phase[0] and mode != "changed":
                received = revised_etag if mode == "wrong-304" else etag
                if mode == "missing-304":
                    assert sent is None
                raise urllib.error.HTTPError(url, 304, "unchanged",
                                             {"ETag": received}, io.BytesIO())
            document = baseline(target)
            if phase[0]:
                assert sent == etag
                document["stocks"][0]["name"] = "수정된 공개 이름"
            body = json.dumps(document).encode()
            return Response(body, revised_etag if phase[0] else etag)

    monkeypatch.setattr(fetch.urllib.request, "build_opener", lambda *_: Opener())
    monkeypatch.setattr(fetch, "_REFRESH_STORE", types.SimpleNamespace(read_states=lambda: {}))
    if mode == "missing-304":
        phase[0] = 1
        result = fetch.fetch_public_sources(_clock=lambda: 0)
        assert target in result["coverage"]["missing"]
        assert "revalidated=0" in capsys.readouterr().err
        return

    first = fetch.fetch_public_sources(_clock=lambda: 0)
    original = first["revision"]
    phase[0] = 1
    second = fetch.fetch_public_sources(_clock=lambda: 61)
    if mode == "changed":
        assert second["documents"][target]["stocks"][0]["name"] == "수정된 공개 이름"
        assert second["revision"] != original
        assert fetch._VALIDATED_SOURCES[target][1] == revised_etag
    else:
        assert target in second["coverage"]["missing"]
        assert second["revision"] != original
    lines = [line for line in capsys.readouterr().err.splitlines()
             if line.startswith("member_map_public_fetch ")]
    assert len(lines) == 2 and all("revalidated=0" in line for line in lines)


@pytest.mark.parametrize("failure", ["parse", "hash"])
def test_invalid_200_cannot_seed_conditional_reuse(monkeypatch, failure):
    target = "universe_search.json"
    url = fetch.PUBLIC_SOURCE_URLS[target]
    etag = '"' + "a" * 32 + '"'
    sent = []

    class Response(io.BytesIO):
        status = 200
        headers = {"ETag": etag}
        def geturl(self):
            return url

    class Opener:
        addheaders = []
        def open(self, request, timeout):
            if request.full_url != url:
                raise urllib.error.HTTPError(request.full_url, 404, "missing", {}, io.BytesIO())
            sent.append(dict(request.header_items()).get("If-none-match"))
            if failure == "parse":
                return Response(b'{"stocks":[],"stocks":[]}')
            return Response(json.dumps(baseline(target)).encode())

    monkeypatch.setattr(fetch.urllib.request, "build_opener", lambda *_: Opener())
    monkeypatch.setattr(fetch, "_REFRESH_STORE", types.SimpleNamespace(read_states=lambda: {}))
    if failure == "hash":
        monkeypatch.setattr(fetch, "_document_revision", lambda _document: (
            _ for _ in ()).throw(ValueError("synthetic canonical failure")))
    for now in (0, 61):
        result = fetch.fetch_public_sources(_clock=lambda: now)
        assert target in result["coverage"]["missing"]
    assert sent == [None, None]
    assert target not in fetch._VALIDATED_SOURCES
    with pytest.raises(ValueError, match="public source response rejected"):
        fetch._read_public_document("https://not-allowlisted.invalid/file.json", 100,
                                    _with_etag=True)


@pytest.mark.parametrize("etag", ["W/\"weak\"", '"é"', '"a\r\nInjected: yes"',
                                       '"' + "a" * 127 + '"', "bare"])
def test_unsafe_etag_is_never_accepted(etag):
    assert fetch._safe_etag(etag) is None
