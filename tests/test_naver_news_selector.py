"""네이버 뉴스 셀렉터 회귀 가드 — 2026-08-20.

사고: 네이버가 검색 결과를 `sds-comps-*` 컴포넌트로 갈아타면서 `a.news_tit` 가 0건이
됐고, regex fallback 도 `"link"` 가 0건이라 `zip()` 이 빈 결과를 냈다. 두 경로가 동시에
죽었는데 말미의 `except Exception: return []` 가 조용히 삼켜서 **아무 신호도 없었다.**

실측(git 전수 131 일자): 마지막 정상 **2026-04-10**(KR 30/30 · headline_count 15),
**2026-04-11 이후 121일 검사 전부 0건** → **132일간 KR 뉴스 감성이 상수 50**.

이 테스트가 지키는 것:
  ① 신·구 마크업 **양쪽** 파싱 (네이버가 되돌려도 살아 있어야 한다)
  ② 🚨 0건일 때 **조용하지 않을 것** — FETCH_DIAG 증가 + stderr 경고
     ([[feedback_cluster_silent_defect]] "건수 0 + 성공 종료 = 결함")

네트워크를 타지 않는다 — requests.get 을 대체해 픽스처를 먹인다.
"""
import sys

import pytest

from api.collectors import news_sentiment as ns

NEW_MARKUP = """
<html><body>
  <div class="sds-comps-base-layout">
    <a href="https://example.com/news/1">
      <span class="sds-comps-text sds-comps-text-type-headline1">삼성전자 3분기 영업이익 급등 전망</span>
    </a>
    <a href="https://example.com/news/2">
      <span class="sds-comps-text sds-comps-text-type-headline1">코스피 약세에 외국인매도 지속</span>
    </a>
  </div>
</body></html>
"""

OLD_MARKUP = """
<html><body>
  <a class="news_tit" href="https://example.com/old/1" title="현대차 대규모수주 계약 체결"></a>
</body></html>
"""

EMPTY_MARKUP = "<html><body><div>결과 없음</div></body></html>"


class _Resp:
    status_code = 200

    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


@pytest.fixture(autouse=True)
def _reset_diag():
    before = dict(ns.FETCH_DIAG)
    ns.FETCH_DIAG.update({"ok": 0, "empty": 0, "errors": 0,
                          "last_error": None, "last_empty_query": None})
    yield
    ns.FETCH_DIAG.update(before)


def _patch(monkeypatch, html):
    monkeypatch.setattr(ns.requests, "get", lambda *a, **k: _Resp(html))


def test_new_sds_markup_is_parsed(monkeypatch):
    """🚨 2026-04-11 이후 132일을 날린 그 마크업."""
    _patch(monkeypatch, NEW_MARKUP)
    out = ns.fetch_news_with_links("삼성전자 주가", count=10)
    assert len(out) == 2, f"신 마크업 파싱 실패 — {out}"
    assert out[0]["title"] == "삼성전자 3분기 영업이익 급등 전망"
    assert out[0]["url"].startswith("https://"), "링크를 못 뽑으면 top_headline_links 가 빈다"


def test_old_markup_still_works(monkeypatch):
    """네이버가 구 마크업으로 되돌려도 살아 있어야 한다 — 한쪽만 남기면 같은 사고가 반복된다."""
    _patch(monkeypatch, OLD_MARKUP)
    out = ns.fetch_news_with_links("현대차 주가", count=10)
    assert len(out) == 1 and out[0]["url"] == "https://example.com/old/1"


def test_empty_result_is_not_silent(monkeypatch, capsys):
    """🚨 이 테스트가 이 파일의 존재 이유다.

    HTTP 200 인데 0건이면 '뉴스가 없다' 가 아니라 **파서가 죽은 것**이다.
    132일을 놓친 이유가 정확히 이 신호의 부재였다.
    """
    _patch(monkeypatch, EMPTY_MARKUP)
    out = ns.fetch_news_with_links("아무거나", count=10)
    assert out == []
    assert ns.FETCH_DIAG["empty"] == 1, "0건인데 FETCH_DIAG 가 안 움직였다"
    assert ns.FETCH_DIAG["last_empty_query"] == "아무거나"
    err = capsys.readouterr().err
    assert "0건" in err and "셀렉터" in err, f"stderr 경고가 없다 — {err!r}"


def test_exception_is_not_silent(monkeypatch, capsys):
    def _boom(*a, **k):
        raise ns.requests.RequestException("연결 실패")
    monkeypatch.setattr(ns.requests, "get", _boom)
    out = ns.fetch_news_with_links("아무거나")
    assert out == []
    assert ns.FETCH_DIAG["errors"] == 1
    assert ns.FETCH_DIAG["last_error"] and "연결 실패" in ns.FETCH_DIAG["last_error"]
    assert "수집 실패" in capsys.readouterr().err


def test_success_increments_ok(monkeypatch):
    _patch(monkeypatch, NEW_MARKUP)
    ns.fetch_news_with_links("삼성전자 주가")
    assert ns.FETCH_DIAG["ok"] == 1 and ns.FETCH_DIAG["empty"] == 0


def test_parsed_headlines_reach_the_score(monkeypatch):
    """파싱만 되고 점수에 도달하지 않으면 의미가 없다 (조인 성공 ≠ 출력 도달)."""
    _patch(monkeypatch, NEW_MARKUP)
    res = ns.get_stock_sentiment("삼성전자", market="KOSPI", ticker="005930")
    assert res["headline_count"] > 0, "헤드라인이 점수 산출까지 안 갔다"
    assert res["positive"] + res["negative"] + res["neutral"] == res["headline_count"]
