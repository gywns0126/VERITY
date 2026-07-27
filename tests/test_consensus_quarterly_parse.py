"""ConsensusScout 분기 컬럼 파싱 — 네이버 기업실적분석 표.

2026-07-28. earnings_surprise.py 헤더가 KR 경로 차단 사유로 든 두 가지가 실측으로 뒤집힘:
  · "ConsensusScout 추정치가 연간(E)-only"  → 분기 (E) 컬럼 존재 (예: 2026.06 (E))
  · "순이익 추정 필드도 부재"                → 당기순이익 행 존재
원인은 소스가 아니라 수집기 필터였다 — _annual_estimate_cells 의 tds[:4] 가 분기 컬럼을 잘라냄.
신규 소스 0 (매 run 이미 받던 동일 페이지). [[feedback_coverage_check_collector_filter_first]] 정합.

fixture = 2026-07-28 실 페이지 스냅샷(000660). 구조 회귀 detect 용.
"""
import os

from bs4 import BeautifulSoup

from api.collectors.ConsensusScout import (
    _parse_financial_estimates,
    _is_estimate_label,
    _parse_period_headers,
    _find_analysis_table,
)

_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "naver_item_main_000660.html")


def _soup():
    with open(_FIXTURE, "r", encoding="utf-8") as f:
        return BeautifulSoup(f.read(), "html.parser")


def test_quarter_columns_parsed():
    out = _parse_financial_estimates(_soup())
    assert out["quarter_period_labels"], "분기 라벨 미검출"
    assert len(out["quarters"]) >= 4
    q = out["quarters"][0]
    assert "sales_bn" in q and "operating_profit_bn" in q and "net_income_bn" in q


def test_quarter_estimate_flagged():
    out = _parse_financial_estimates(_soup())
    ests = [q for q in out["quarters"] if q["is_estimate"]]
    assert ests, "분기 추정((E)) 컬럼 미검출 — KR 서프라이즈 차단 사유의 근거"
    assert all("(E)" in q["period"] for q in ests)
    # 추정 분기에 순이익 추정치가 실제로 들어있어야 함("순이익 추정 부재" 주장 반증)
    assert any(q.get("net_income_bn") is not None for q in ests)


def test_annual_path_unchanged():
    """기존 연간 필드 회귀 0 — 소비처(consensus_score.py) 계약 유지."""
    out = _parse_financial_estimates(_soup())
    assert out["operating_profit_estimate_bn"] is not None
    assert out["operating_profit_prior_year_bn"] is not None
    assert out["sales_estimate_bn"] is not None
    assert len(out["annual_period_labels"]) == 4


def test_annual_quarter_boundary_from_colspan():
    """경계는 그룹 헤더 colspan 으로 — 컬럼 수 하드코딩 아님.

    라벨 문자열은 겹칠 수 있다(연간 '2025.12'=FY2025, 분기 '2025.12'=Q4). 정상 도메인 동작이라
    disjoint 를 요구하지 않고, 경계 위치와 연간 라벨이 전부 12월 결산인지로 검증한다.
    """
    ann, qtr = _parse_period_headers(_find_analysis_table(_soup()))
    assert len(ann) == 4
    assert len(qtr) >= 4
    # 연간 = 결산월 반복(12월), 분기 = 03/06/09/12 가 섞임
    assert all(a.split()[0].endswith(".12") for a in ann), ann
    assert len({q.split()[0][-2:] for q in qtr}) > 1, qtr


def test_is_estimate_label():
    assert _is_estimate_label("2026.06 (E)")
    assert _is_estimate_label("2026.12 (E)")
    assert not _is_estimate_label("2026.03")
    assert not _is_estimate_label("")


def test_missing_table_returns_empty_keys():
    """표 부재 시에도 키 유지 — 소비처 KeyError 방지."""
    out = _parse_financial_estimates(BeautifulSoup("<html></html>", "html.parser"))
    assert out["quarters"] == []
    assert out["quarter_estimate_labels"] == []
    assert out["operating_profit_estimate_bn"] is None


def test_blank_quarters_excluded():
    """값이 전부 비어있는 기간은 제외 — 빈 칸을 실측 0 으로 오인 금지."""
    out = _parse_financial_estimates(_soup())
    for q in out["quarters"]:
        assert any(q.get(k) is not None
                   for k in ("sales_bn", "operating_profit_bn", "net_income_bn"))
