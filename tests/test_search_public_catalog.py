"""공개 검색 보충 목록만 합성 자료로 검사하며 실제 네트워크를 차단한다."""
from copy import deepcopy
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import sys
import threading
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock
from urllib.parse import urlencode

import pytest

ROOT = Path(__file__).resolve().parents[1]
IPO = {"ticker": "386380", "name": "스카이랩스", "market": "KR"}
KR = [
    {"ticker": "005930", "name": "삼성전자", "market": "KOSPI", "yf": "005930.KS"},
    {"ticker": "069500", "name": "KODEX 200", "market": "KOSPI", "etf": True},
]
US = [{"ticker": "SKY", "name": "Skyline", "name_kr": "스카이라인", "market": "NYSE"},
      {"ticker": "SPY", "name": "SPDR", "market": "NYSE ARCA", "etf": True}]


@pytest.fixture
def search(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("실제 네트워크 호출 금지")
    monkeypatch.setattr(socket.socket, "connect", denied)
    spec = importlib.util.spec_from_file_location("search_catalog_test", ROOT / "vercel-api/api/search.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._cache, module._us_cache = deepcopy(KR), deepcopy(US)
    clock = [100.0]
    monkeypatch.setattr(module, "monotonic", lambda: clock[0])
    reader = Mock(return_value={"stocks": [deepcopy(IPO)]})
    storage = ModuleType("api.portfolio_core.member_map_refresh_store")
    storage.read_public_catalog = reader
    monkeypatch.setitem(sys.modules, storage.__name__, storage)
    # Temporary candidates may reuse installed source dependencies; CI defaults to this repo.
    dependency_root = Path(os.environ.get("MEMBER_MAP_TEST_DEPENDENCY_ROOT", ROOT))
    public_spec = importlib.util.spec_from_file_location(
        "api.portfolio_core.portfolio_public_sources",
        dependency_root / "vercel-api/api/portfolio_core/portfolio_public_sources.py")
    public = importlib.util.module_from_spec(public_spec)
    public_spec.loader.exec_module(public)
    monkeypatch.setitem(sys.modules, public_spec.name, public)
    return module, reader, clock


def query(module, q, market="all", limit=12):
    headers = {}
    request = SimpleNamespace(path="/api/search?" + urlencode(dict(q=q, market=market, limit=limit)),
                              wfile=io.BytesIO(), send_response=lambda code: None,
                              send_header=lambda k, v: headers.update({k: v}), end_headers=lambda: None)
    module.handler.do_GET(request)
    return json.loads(request.wfile.getvalue()), headers


def test_new_ipo_and_cdn_expiry(search):
    module, reader, _ = search
    result, headers = query(module, "386380")
    assert result == [IPO]
    assert query(module, "스카이랩스", "kr")[0] == [IPO]
    assert headers["Cache-Control"] == "s-maxage=300, stale-while-revalidate=300"
    reader.assert_called_once_with()


def test_existing_identity_us_etf_and_order_are_preserved(search):
    module, reader, _ = search
    reader.return_value = {"stocks": [IPO, {"ticker": "005930", "name": "다른 이름", "market": "KR"}]}
    assert query(module, "005930")[0] == [KR[0]]
    assert query(module, "KODEX")[0] == [KR[1]]
    assert query(module, "SPY")[0] == [US[1]]
    assert query(module, "스카이")[0] == [US[0], IPO]
    assert query(module, "스카이", limit=1)[0] == [US[0]]
    assert (module._cache, module._us_cache) == (KR, US)


def test_us_and_empty_queries_do_not_fetch_catalog(search):
    module, reader, _ = search
    assert query(module, "sky", "us")[0] == [US[0]]
    assert query(module, "")[0] == []
    reader.assert_not_called()


@pytest.mark.parametrize("bad", [
    {"ticker": "38638K"}, {"ticker": 386380}, {"ticker": "386380 "},
    {"market": "US"}, {"market": ["KR"]}, {"name": ""}, {"name": None},
    {"name": " 스카이랩스"}, {"name": "스카이\n랩스"}, {"name": "<비공개>"},
    {"name": "가" * 161}, {"private_note": "비공개 메모"}, {"user_id": "비공개 식별자"},
])
def test_bad_or_extra_fields_never_enter_response(search, bad):
    module, reader, _ = search
    reader.return_value = {"stocks": [{**IPO, **bad}]}
    assert query(module, "386380")[0] == []
    assert "비공개" not in json.dumps(module._catalog_rows, ensure_ascii=False)


def test_duplicates_conflicts_and_private_duplicate_exclude_whole_ticker(search):
    module, reader, _ = search
    assert module._public_kr_rows({"stocks": [IPO, deepcopy(IPO)]}) == [IPO]
    for other in ({**IPO, "name": "이름 충돌"}, {**IPO, "market": "KOSDAQ"},
                  {**IPO, "private_note": "비공개"}):
        with pytest.raises(ValueError, match="empty-public-search-catalog"):
            module._public_kr_rows({"stocks": [IPO, other, IPO]})
        with pytest.raises(ValueError, match="empty-public-search-catalog"):
            module._public_kr_rows({"stocks": [other, IPO]})
    assert module._public_kr_rows({"stocks": {"386380": IPO}}) == [IPO]
    with pytest.raises(ValueError, match="empty-public-search-catalog"):
        module._public_kr_rows({"stocks": {"000001": IPO}})


@pytest.mark.parametrize("rows", [[], {}, [None, {"ticker": "386380"}],
                                 [{**IPO, "name": "<거부>"}],
                                 [IPO, {**IPO, "name": "충돌"}]])
def test_zero_valid_rows_retain_last_good_and_backoff(search, rows):
    module, reader, clock = search
    assert query(module, "386380")[0] == [IPO]
    reader.return_value = {"stocks": rows}
    clock[0] = 400
    assert query(module, "386380")[0] == [IPO]
    clock[0] = 699
    assert query(module, "386380")[0] == [IPO]
    assert reader.call_count == 2


@pytest.mark.parametrize("name", ["sk-proj-synthetic-not-a-real-key", "Bearer synthetic",
                                 "abcdefghij.abcdefghij.abcdefghij", "member_id synthetic",
                                 "스카이랩스 "])
def test_shared_sensitive_name_validator_rejects_without_reflection(search, name):
    module, reader, _ = search
    reader.return_value = {"stocks": [IPO, {"ticker": "123456", "market": "KR", "name": name}]}
    assert query(module, "123456")[0] == []
    assert query(module, "386380")[0] == [IPO]
    assert module._catalog_rows == [IPO]


def test_cache_expiry_success_and_projection_does_not_alias_source(search):
    module, reader, clock = search
    assert query(module, "386380")[0] == [IPO]
    reader.return_value["stocks"][0]["name"] = "갱신된 이름"
    clock[0] = 399.9
    assert query(module, "386380")[0] == [IPO]
    assert reader.call_count == 1
    clock[0] = 400
    assert query(module, "386380")[0][0]["name"] == "갱신된 이름"
    assert reader.call_count == 2


@pytest.mark.parametrize("failure", [TimeoutError("비공개 원문"), ValueError("비공개 원문"), {"stocks": None}])
def test_failure_keeps_last_good_and_backs_off(search, failure):
    module, reader, clock = search
    assert query(module, "386380")[0] == [IPO]
    if isinstance(failure, Exception):
        reader.side_effect = failure
    else:
        reader.return_value = failure
    clock[0] = 400
    assert query(module, "386380")[0] == [IPO]
    clock[0] = 699.9
    assert query(module, "386380")[0] == [IPO]
    assert reader.call_count == 2
    assert "비공개" not in json.dumps(module._catalog_rows, ensure_ascii=False)


def test_cold_failure_backs_off_and_does_not_break_baseline(search):
    module, reader, clock = search
    reader.side_effect = TimeoutError()
    assert query(module, "005930")[0] == [KR[0]]
    assert query(module, "386380")[0] == []
    assert reader.call_count == 1
    reader.side_effect = None
    clock[0] = 400
    assert query(module, "386380")[0] == [IPO]


def test_late_reader_result_cannot_replace_last_good(search):
    module, reader, clock = search
    assert query(module, "386380")[0] == [IPO]
    clock[0] = 400
    def late():
        clock[0] += 3.01
        return {"stocks": [{**IPO, "name": "늦은 결과"}]}
    reader.side_effect = late
    assert query(module, "386380")[0] == [IPO]
    assert module._catalog_retry_at == pytest.approx(703.01)


def test_concurrent_refresh_does_not_duplicate_download_or_block_cached_read(search):
    module, reader, clock = search
    assert query(module, "386380")[0] == [IPO]
    clock[0] = 400
    entered, release = threading.Event(), threading.Event()
    def pending():
        entered.set()
        assert release.wait(2)
        return {"stocks": [IPO]}
    reader.side_effect = pending
    thread = threading.Thread(target=module._public_catalog)
    thread.start()
    try:
        assert entered.wait(1)
        assert query(module, "386380")[0] == [IPO]
        assert reader.call_count == 2
    finally:
        release.set()
        thread.join(2)
    assert not thread.is_alive()
