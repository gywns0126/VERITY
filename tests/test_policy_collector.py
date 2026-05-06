"""
test_policy_collector.py — v2 검증 (data.go.kr 정공법)

T7  테스트 통과 위해 산출 함수 로직 변경 X. fixture 변경은 OK.
T13 fixture (data_go_kr_press_release_sample.xml) = 실제 API 응답 캡처본 — 위변조 금지
T14 최소 케이스: 정상 / 빈응답 / 5xx / resultCode!=0 / minister filter / lookback
T15 timeout=15s + retry=0 검증
"""
import os
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
import requests as requests_lib

from api.collectors.policy_collector import (
    API_BASE,
    DEFAULT_LOOKBACK_HOURS,
    DEFAULT_MINISTER_FILTER,
    collect_policies,
)


FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "fixtures", "data_go_kr_press_release_sample.xml"
)


@pytest.fixture
def fixture_xml() -> str:
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return f.read()


# ───────────────────────────── 1. 정상 응답 ─────────────────────────────

def test_normal_response_parses_fixture(fixture_xml):
    """T13 fixture 의 NewsItem 들이 minister_filter=None + 충분한 lookback 시 정상 파싱."""
    # fixture 캡처 시점(2026-05-06) 보다 충분히 미래 + 큰 lookback (단 API 제약 72h 가드 제거)
    # _xml_text 주입 시는 lookback 가드 우회 — 더 큰 윈도우 가능 (테스트 친화)
    now = datetime(2026, 5, 6, 23, 0, 0, tzinfo=timezone.utc)
    out = collect_policies(
        lookback_hours=24 * 30,  # 30일
        minister_filter=None,
        now=now,
        _xml_text=fixture_xml,
    )

    assert len(out) > 0, "fixture 의 NewsItem 들이 일부라도 통과해야 함"

    expected_keys = {"id", "title", "source_url", "source_name", "published_at", "raw_text"}
    for p in out:
        assert set(p.keys()) == expected_keys
        assert p["title"]                    # 빈 문자열 X
        assert p["source_name"]              # MinisterCode 비어있지 않음
        assert p["published_at"]             # ISO 8601
        assert p["id"]                       # NewsItemId

        # source_url 은 korea.kr 원문 (있을 때만)
        if p["source_url"]:
            assert p["source_url"].startswith("http")

        # DataContents HTML 클린업 검증 (BeautifulSoup get_text)
        rt = p["raw_text"].lower()
        assert "<a " not in rt
        assert "<br" not in rt
        assert "<div" not in rt
        assert "<table" not in rt
        assert "<span" not in rt


# ───────────────────────────── 2. minister_filter ─────────────────────────────

def test_minister_filter_default_molit(fixture_xml):
    """default minister_filter='국토교통부' — v1 dept_molit 정합."""
    assert DEFAULT_MINISTER_FILTER == "국토교통부"

    now = datetime(2026, 5, 6, 23, 0, 0, tzinfo=timezone.utc)
    out = collect_policies(
        lookback_hours=24 * 30,
        now=now,
        _xml_text=fixture_xml,  # default minister_filter
    )

    # 모든 결과가 국토교통부 only
    for p in out:
        assert p["source_name"] == "국토교통부"


def test_minister_filter_none_returns_all(fixture_xml):
    """minister_filter=None 시 전체 부처 통과 — 다양한 MinisterCode 가 나와야 함."""
    now = datetime(2026, 5, 6, 23, 0, 0, tzinfo=timezone.utc)
    out = collect_policies(
        lookback_hours=24 * 30,
        minister_filter=None,
        now=now,
        _xml_text=fixture_xml,
    )

    ministers = {p["source_name"] for p in out}
    assert len(ministers) >= 2, "전체 응답엔 다양한 부처가 있어야 함"


# ───────────────────────────── 3. 빈 응답 ─────────────────────────────

def test_empty_body_returns_empty_list():
    """body 의 NewsItem 0건 → 빈 배열 (T1 — fabricate X)."""
    empty_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<response><header><resultCode>0</resultCode><resultMsg>NORMAL_SERVICE</resultMsg>'
        '</header><body></body></response>'
    )
    out = collect_policies(_xml_text=empty_xml)
    assert out == []


def test_missing_body_returns_empty_and_logs(caplog):
    """<body> 자체가 없는 깨진 응답 → 빈 배열 + 에러 로그 (T9)."""
    no_body_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<response><header><resultCode>0</resultCode></header></response>'
    )
    with caplog.at_level("ERROR", logger="api.collectors.policy_collector"):
        out = collect_policies(_xml_text=no_body_xml)
    assert out == []
    assert any("missing <body>" in r.message for r in caplog.records)


def test_result_code_non_zero_returns_empty_and_logs(caplog):
    """resultCode != 0 (예: 98 THREE_DAYS_OVER_ERROR) → 빈 배열 + 로그."""
    err_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<response><header><resultCode>98</resultCode>'
        '<resultMsg>THREE_DAYS_OVER_ERROR</resultMsg></header><body></body></response>'
    )
    with caplog.at_level("ERROR", logger="api.collectors.policy_collector"):
        out = collect_policies(_xml_text=err_xml)
    assert out == []
    assert any("resultCode=98" in r.message for r in caplog.records)


# ───────────────────────────── 4. 네트워크/HTTP 실패 ─────────────────────────────

def test_5xx_returns_empty_and_logs(caplog, monkeypatch):
    """T9, T15 — 503 응답 시 빈 배열 + 명시적 로그. retry 없음."""
    monkeypatch.setenv("PUBLIC_DATA_API_KEY", "test_key")
    mock_res = Mock()
    mock_res.status_code = 503
    mock_res.text = ""
    with patch(
        "api.collectors.policy_collector.requests.get",
        return_value=mock_res,
    ) as mg:
        with caplog.at_level("ERROR", logger="api.collectors.policy_collector"):
            out = collect_policies()

    assert out == []
    assert mg.call_count == 1  # retry 0회 (T15)
    _args, kwargs = mg.call_args
    assert kwargs["timeout"] == 15
    assert any("503" in r.message for r in caplog.records)


def test_request_exception_returns_empty_and_logs(caplog, monkeypatch):
    """네트워크 단절 (ConnectionError) → 빈 배열 + 로그."""
    monkeypatch.setenv("PUBLIC_DATA_API_KEY", "test_key")
    with patch(
        "api.collectors.policy_collector.requests.get",
        side_effect=requests_lib.ConnectionError("boom"),
    ):
        with caplog.at_level("ERROR", logger="api.collectors.policy_collector"):
            out = collect_policies()
    assert out == []
    assert any("HTTP error" in r.message for r in caplog.records)


def test_missing_api_key_returns_empty_and_logs(caplog, monkeypatch):
    """PUBLIC_DATA_API_KEY 없으면 fetch 자체 skip + 명시적 logged=True 에러."""
    monkeypatch.delenv("PUBLIC_DATA_API_KEY", raising=False)
    with caplog.at_level("ERROR", logger="api.collectors.policy_collector"):
        out = collect_policies()
    assert out == []
    assert any("PUBLIC_DATA_API_KEY missing" in r.message for r in caplog.records)


# ───────────────────────────── 5. 깨진 XML ─────────────────────────────

def test_malformed_xml_returns_empty_and_logs(caplog, monkeypatch):
    """200 응답이지만 XML 파싱 실패 → 빈 배열 + 로그 (T1, T9)."""
    monkeypatch.setenv("PUBLIC_DATA_API_KEY", "test_key")
    mock_res = Mock()
    mock_res.status_code = 200
    mock_res.text = "<response><header><resultCode>0"  # 닫히지 않음
    with patch(
        "api.collectors.policy_collector.requests.get",
        return_value=mock_res,
    ):
        with caplog.at_level("ERROR", logger="api.collectors.policy_collector"):
            out = collect_policies()
    assert out == []
    assert any("XML parse error" in r.message for r in caplog.records)


# ───────────────────────────── 6. T11 / T15 / params 검증 ─────────────────────────────

def test_params_and_timeout_and_default_endpoint(monkeypatch):
    """T11 (default endpoint = data.go.kr 1371000), T15 (timeout=15)."""
    monkeypatch.setenv("PUBLIC_DATA_API_KEY", "test_key_xyz")
    mock_res = Mock()
    mock_res.status_code = 200
    mock_res.text = (
        '<?xml version="1.0"?><response>'
        '<header><resultCode>0</resultCode></header><body></body></response>'
    )
    with patch(
        "api.collectors.policy_collector.requests.get",
        return_value=mock_res,
    ) as mg:
        collect_policies(timeout_sec=15)

    args, kwargs = mg.call_args
    assert args[0] == API_BASE
    assert "apis.data.go.kr/1371000/pressReleaseService/pressReleaseList" in API_BASE
    assert kwargs["timeout"] == 15
    p = kwargs["params"]
    assert p["serviceKey"] == "test_key_xyz"
    assert "startDate" in p and "endDate" in p
    assert p["pageNo"] == 1


# ───────────────────────────── 7. lookback 필터 + 가드 ─────────────────────────────

def test_lookback_default_72(fixture_xml):
    """default lookback=72h (P2 결정 2 + API 3-day 제약 정합)."""
    assert DEFAULT_LOOKBACK_HOURS == 72


def test_lookback_72_filters_old_items(fixture_xml):
    """lookback 윈도우 외 항목은 제외 (T1 — fabricate X 검증)."""
    # fixture 캡처가 5/3~5/6 인데 5/8 시점 lookback=1h → 0건이어야 함
    now_far = datetime(2026, 5, 8, 23, 0, 0, tzinfo=timezone.utc)
    out_far = collect_policies(
        lookback_hours=1,
        minister_filter=None,
        now=now_far,
        _xml_text=fixture_xml,
    )
    assert out_far == []


def test_lookback_over_72_caps_with_warning(caplog, monkeypatch):
    """API 제약 가드 — lookback>72 호출 시 72 로 cap + 명시 로그."""
    monkeypatch.setenv("PUBLIC_DATA_API_KEY", "test_key")
    mock_res = Mock()
    mock_res.status_code = 200
    mock_res.text = (
        '<?xml version="1.0"?><response>'
        '<header><resultCode>0</resultCode></header><body></body></response>'
    )
    with patch(
        "api.collectors.policy_collector.requests.get",
        return_value=mock_res,
    ):
        with caplog.at_level("ERROR", logger="api.collectors.policy_collector"):
            collect_policies(lookback_hours=168)  # 7d
    assert any("> 72 violates API 3-day limit" in r.message for r in caplog.records)
