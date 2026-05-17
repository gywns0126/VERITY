"""KIRS (한국IR협의회) scraper 검증 (2026-05-18, A2.3a).

docs/Q2_LIVE_FETCH_VERIFICATION_20260518.md 정합.
- robots.txt Allow ✓
- PDF URL pattern: w4.kirs.or.kr/download/research/{YYMMDD}_{섹터}_{회사명}({종목코드})_..._{기관}.pdf
- td 5칸 구조: 회사명(코드)/제목/기관|작성자/날짜/PDF
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from api.collectors.ReportScout import (
    _extract_kirs_company_and_ticker,
    fetch_kirs_reports,
    KIRS_PAGES,
)


class TestKirsTickerExtraction:
    """\"질경이(233990)\" → (\"질경이\", \"233990\") 정규식 검증."""

    def test_standard_pattern(self):
        company, ticker = _extract_kirs_company_and_ticker("질경이(233990)")
        assert company == "질경이"
        assert ticker == "233990"

    def test_with_space(self):
        """research22_1 의 \"두산테스나 (131970)\" 형식."""
        company, ticker = _extract_kirs_company_and_ticker("두산테스나 (131970)")
        assert company == "두산테스나"
        assert ticker == "131970"

    def test_no_ticker(self):
        """종목코드 없으면 ticker=None."""
        company, ticker = _extract_kirs_company_and_ticker("미상의회사")
        assert company == "미상의회사"
        assert ticker is None

    def test_empty(self):
        company, ticker = _extract_kirs_company_and_ticker("")
        assert company == ""
        assert ticker is None

    def test_5_digit_not_match(self):
        """6자리 아닌 숫자 = ticker 매칭 안 함."""
        company, ticker = _extract_kirs_company_and_ticker("회사(12345)")
        assert ticker is None


class TestKirsFetcher:
    """fetch_kirs_reports HTML parsing 검증 (mock HTML)."""

    _SAMPLE_OUTSOURCING_HTML = """
    <html><body>
    <table>
        <tr><th>종목</th><th>제목</th><th>기관</th><th>날짜</th><th>PDF</th></tr>
        <tr>
            <td>질경이(233990)</td>
            <td>여성의 일상을 과학으로</td>
            <td>나이스평가정보</td>
            <td>2026-05-14</td>
            <td><a href="https://w4.kirs.or.kr/download/research/260514_test.pdf"><img/></a></td>
        </tr>
        <tr>
            <td>태양3C(052960)</td>
            <td>자동차 전장부품 유통</td>
            <td>서울평가정보(주)</td>
            <td>2026-05-14</td>
            <td><a href="https://w4.kirs.or.kr/download/research/260514_test2.pdf"><img/></a></td>
        </tr>
    </table>
    </body></html>
    """

    _SAMPLE_INSOURCING_HTML = """
    <html><body>
    <table>
        <tr><th>종목</th><th>제목</th><th>작성자</th><th>날짜</th><th>PDF</th></tr>
        <tr>
            <td>두산테스나 (131970)</td>
            <td>보릿고개 딛고 다시 성장</td>
            <td>백종석</td>
            <td>2026-05-15</td>
            <td><a href="https://w4.kirs.or.kr/download/research/260515_test.pdf"><img/></a></td>
        </tr>
    </table>
    </body></html>
    """

    def _mock_response(self, html: str, status_code: int = 200):
        from unittest.mock import MagicMock
        resp = MagicMock()
        resp.status_code = status_code
        resp.text = html
        resp.raise_for_status = MagicMock()
        return resp

    def test_outsourcing_page_parses_two_entries(self):
        with patch("api.collectors.ReportScout._SESSION") as m_session:
            m_session.get.return_value = self._mock_response(self._SAMPLE_OUTSOURCING_HTML)
            result = fetch_kirs_reports("outsourcing", max_pages=1)
            assert len(result) == 2
            r0 = result[0]
            assert r0["source"] == "kirs_outsourcing"
            assert r0["ticker"] == "233990"
            assert r0["company_name"] == "질경이"
            assert r0["firm"] == "나이스평가정보"
            assert r0["author"] is None
            assert r0["date"] == "2026-05-14"
            assert "260514_test.pdf" in r0["pdf_url"]

    def test_insourcing_page_maps_author_not_firm(self):
        with patch("api.collectors.ReportScout._SESSION") as m_session:
            m_session.get.return_value = self._mock_response(self._SAMPLE_INSOURCING_HTML)
            result = fetch_kirs_reports("insourcing", max_pages=1)
            assert len(result) == 1
            r0 = result[0]
            assert r0["source"] == "kirs_insourcing"
            assert r0["firm"] == "KIRS"  # 인소싱은 KIRS 고정
            assert r0["author"] == "백종석"
            assert r0["company_name"] == "두산테스나"
            assert r0["ticker"] == "131970"

    def test_unknown_page_type_returns_empty(self):
        result = fetch_kirs_reports("nonexistent_type", max_pages=1)
        assert result == []

    def test_date_filter_excludes_old_entries(self):
        with patch("api.collectors.ReportScout._SESSION") as m_session:
            m_session.get.return_value = self._mock_response(self._SAMPLE_OUTSOURCING_HTML)
            # bgn_date 가 entry 날짜 이후 → 전부 제외
            result = fetch_kirs_reports(
                "outsourcing", bgn_date="2026-06-01", end_date="2026-06-30", max_pages=1
            )
            assert result == []

    def test_date_filter_includes_in_range(self):
        with patch("api.collectors.ReportScout._SESSION") as m_session:
            m_session.get.return_value = self._mock_response(self._SAMPLE_OUTSOURCING_HTML)
            result = fetch_kirs_reports(
                "outsourcing", bgn_date="2026-05-01", end_date="2026-05-31", max_pages=1
            )
            assert len(result) == 2

    def test_fetch_failure_returns_empty(self):
        with patch("api.collectors.ReportScout._SESSION") as m_session:
            m_session.get.side_effect = Exception("network error")
            result = fetch_kirs_reports("outsourcing", max_pages=1)
            assert result == []

    def test_missing_pdf_yields_none_url(self):
        html_no_pdf = """
        <html><body><table>
            <tr><th>x</th><th>x</th><th>x</th><th>x</th><th>x</th></tr>
            <tr>
                <td>한경(123456)</td><td>제목</td><td>기관</td><td>2026-05-10</td>
                <td>(다운로드 없음)</td>
            </tr>
        </table></body></html>
        """
        with patch("api.collectors.ReportScout._SESSION") as m_session:
            m_session.get.return_value = self._mock_response(html_no_pdf)
            result = fetch_kirs_reports("outsourcing", max_pages=1)
            assert len(result) == 1
            assert result[0]["pdf_url"] is None
            assert result[0]["ticker"] == "123456"

    def test_dedup_same_pdf_url(self):
        """같은 PDF + title + date 조합 = seen 으로 중복 제거."""
        html_dup = """
        <html><body><table>
            <tr><th>x</th><th>x</th><th>x</th><th>x</th><th>x</th></tr>
            <tr><td>A(100000)</td><td>같은제목</td><td>기관A</td><td>2026-05-10</td>
                <td><a href="https://w4.kirs.or.kr/x.pdf"><img/></a></td></tr>
            <tr><td>B(100001)</td><td>같은제목</td><td>기관B</td><td>2026-05-10</td>
                <td><a href="https://w4.kirs.or.kr/x.pdf"><img/></a></td></tr>
        </table></body></html>
        """
        with patch("api.collectors.ReportScout._SESSION") as m_session:
            m_session.get.return_value = self._mock_response(html_dup)
            result = fetch_kirs_reports("outsourcing", max_pages=1)
            assert len(result) == 1  # 두 번째 row dedup


class TestKirsPagesConstant:
    """KIRS_PAGES 상수에 2개 page 박혀있는지."""

    def test_outsourcing_url(self):
        assert "research.html" in KIRS_PAGES["outsourcing"]
        assert "kirs.or.kr" in KIRS_PAGES["outsourcing"]

    def test_insourcing_url(self):
        assert "research22_1.html" in KIRS_PAGES["insourcing"]
