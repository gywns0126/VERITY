"""
test_policy_collector.py — P2 Step 1.2 검증

T7  테스트 통과 위해 산출 함수 로직 변경 X. fixture 변경은 OK.
T13 fixture (molit_rss_sample.xml) 는 실제 응답 캡처본 — 위변조 금지
T14 최소 3 케이스: 정상 / 빈응답 / 5xx (이 파일은 7 케이스로 보강)
T15 timeout=10s + retry=0 검증
"""
import os
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
import requests as requests_lib

from api.collectors.policy_collector import (
    DEFAULT_FEED_URL,
    USER_AGENT,
    collect_policies,
)


FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "fixtures", "molit_rss_sample.xml"
)


@pytest.fixture
def fixture_xml() -> str:
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return f.read()


# ───────────────────────────── 1. 정상 응답 ─────────────────────────────

def test_normal_response_parses_fixture(fixture_xml):
    """T13 fixture 50건이 lookback 충분 시 모두 정상 파싱된다."""
    # fixture 캡처 시점(2026-05-02) 보다 충분히 미래 + 매우 긴 lookback
    now = datetime(2027, 1, 1, tzinfo=timezone.utc)
    out = collect_policies(
        lookback_hours=24 * 365 * 2,  # 2년
        now=now,
        _xml_text=fixture_xml,
    )

    assert len(out) == 50, "fixture 의 50개 item 모두 통과해야 함"

    expected_keys = {"id", "title", "source_url", "source_name", "published_at", "raw_text"}
    for p in out:
        # 필드 존재 + 필드만 노출 (private _published_dt 누출 X)
        assert set(p.keys()) == expected_keys

        assert p["source_name"] == "국토교통부"
        assert p["title"]                    # 빈 문자열 X
        assert p["source_url"].startswith("http")
        assert p["published_at"]             # ISO 8601 문자열
        assert p["id"]                       # guid or sha1 해시

        # description HTML 클린업 검증 (BeautifulSoup get_text)
        rt = p["raw_text"].lower()
        assert "<a " not in rt
        assert "<br" not in rt
        assert "<img" not in rt
        assert "<div" not in rt


# ───────────────────────────── 2. 빈 응답 ─────────────────────────────

def test_empty_channel_returns_empty_list():
    """item 0건 응답 → 빈 배열 (T1 — 가짜 fabricate X)."""
    empty_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0"><channel><title>empty</title></channel></rss>'
    )
    out = collect_policies(_xml_text=empty_xml)
    assert out == []


def test_missing_channel_returns_empty_and_logs(caplog):
    """<channel> 자체가 없는 깨진 RSS → 빈 배열 + 에러 로그 (T9)."""
    no_channel_xml = '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"></rss>'
    with caplog.at_level("ERROR", logger="api.collectors.policy_collector"):
        out = collect_policies(_xml_text=no_channel_xml)
    assert out == []
    assert any("missing <channel>" in r.message for r in caplog.records)


# ───────────────────────────── 3. 5xx 에러 ─────────────────────────────

def test_5xx_returns_empty_and_logs(caplog):
    """T9, T15 — 503 응답 시 빈 배열 + 명시적 로그. retry 없음."""
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
    # retry 0회 — 단 한 번만 호출됨 (T15)
    assert mg.call_count == 1
    # T12 — User-Agent 가 실제로 전달됐는지
    _args, kwargs = mg.call_args
    assert kwargs["headers"]["User-Agent"] == USER_AGENT
    assert kwargs["timeout"] == 10
    # T9 — 명시적 에러 로그
    assert any("503" in r.message for r in caplog.records)


def test_request_exception_returns_empty_and_logs(caplog):
    """네트워크 단절 (ConnectionError) → 빈 배열 + 로그."""
    with patch(
        "api.collectors.policy_collector.requests.get",
        side_effect=requests_lib.ConnectionError("boom"),
    ):
        with caplog.at_level("ERROR", logger="api.collectors.policy_collector"):
            out = collect_policies()
    assert out == []
    assert any("HTTP error" in r.message for r in caplog.records)


# ───────────────────────────── 4. 깨진 XML ─────────────────────────────

def test_malformed_xml_returns_empty_and_logs(caplog):
    """200 응답이지만 XML 파싱 실패 → 빈 배열 + 로그 (T1, T9)."""
    mock_res = Mock()
    mock_res.status_code = 200
    mock_res.text = "<rss><channel><item><title>broken"  # 닫히지 않음
    with patch(
        "api.collectors.policy_collector.requests.get",
        return_value=mock_res,
    ):
        with caplog.at_level("ERROR", logger="api.collectors.policy_collector"):
            out = collect_policies()
    assert out == []
    assert any("XML parse error" in r.message for r in caplog.records)


# ───────────────────────────── 5. T12 / T15 검증 ─────────────────────────────

def test_user_agent_and_timeout_and_default_url():
    """T12 (User-Agent), T15 (timeout=10), T11 (default URL korea.kr) 확인."""
    mock_res = Mock()
    mock_res.status_code = 200
    mock_res.text = '<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>'
    with patch(
        "api.collectors.policy_collector.requests.get",
        return_value=mock_res,
    ) as mg:
        collect_policies(timeout_sec=10)

    args, kwargs = mg.call_args
    assert args[0] == DEFAULT_FEED_URL == "https://www.korea.kr/rss/dept_molit.xml"
    assert kwargs["timeout"] == 10
    assert kwargs["headers"]["User-Agent"] == USER_AGENT


# ───────────────────────────── 6. lookback 필터 ─────────────────────────────

def test_lookback_default_72_and_filters_old_items(fixture_xml):
    """결정 2 (2026-05-02): DEFAULT_LOOKBACK_HOURS = 72.
    + lookback 윈도우 외 항목은 제외."""
    from api.collectors.policy_collector import DEFAULT_LOOKBACK_HOURS

    assert DEFAULT_LOOKBACK_HOURS == 72, "default lookback 은 72h (P2 결정 2)"

    # default lookback 으로 호출 시 명시 lookback=72 와 동일 결과
    now = datetime(2026, 5, 2, 14, 0, 0, tzinfo=timezone.utc)
    out_default = collect_policies(now=now, _xml_text=fixture_xml)
    out_72 = collect_policies(lookback_hours=72, now=now, _xml_text=fixture_xml)
    assert len(out_default) == len(out_72)

    # 윈도우 외 (now=fixture+30일, lookback=1h) → 0건 (T1 — fabricate X 검증)
    now_far = datetime(2026, 6, 1, tzinfo=timezone.utc)
    out_far = collect_policies(lookback_hours=1, now=now_far, _xml_text=fixture_xml)
    assert out_far == []
