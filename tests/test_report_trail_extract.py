"""PDF trail 실 노출 회귀 test — text extract 검증.

배경 (2026-05-27):
  commit 2d63b2e2 "fix(reports): 자기 trail 노출 강화" 가 helper 함수
  `_methodology_narrative` + `_stock_detail_block` 를 풍부하게 만들었으나,
  v2 entry (`generate_daily_admin_pdf_v2` / `generate_weekly_admin_pdf`) 에서
  호출 자체가 0건이라 운영 PDF 에 박힘 0. test 가 helper 직접 호출만
  검증했기에 미감지.

  본 test = 실 PDF 생성 후 pypdf text extract → expected keyword 박힘
  여부 검증. helper 함수 호출 자체가 빠지면 즉시 fail.

회귀 가드:
  - daily_admin v2 chapter 10 methodology + chapter 4 종목 detail 박힘
  - weekly_admin chapter 7 methodology 박힘
"""
from __future__ import annotations

import os
import pytest


def _minimal_portfolio():
    """최소 portfolio fixture — 1 KR + 1 US 종목, AVOID grade.

    _stock_detail_block 박힘 분기 (Brain v5 / Lynch / commodity_margin /
    kis_financial_ratio) 와 _methodology_narrative 박힘 검증.
    """
    return {
        "updated_at": "2026-05-27T12:00:00+09:00",
        "macro": {
            "market_mood": {"score": 50, "label": "중립"},
            "vix": {"value": 16.0, "source": "yfinance"},
            "usd_krw": {"value": 1500.0, "change_pct": 0.0},
            "fred_dgs10": {"value": 4.5, "source": "FRED"},
            "sp500_change_pct": {"value": 0.1},
            "wti": {"value": 90.0},
            "gold_price": {"value": 4500.0},
            "kr_base_rate": {"value": 2.5},
        },
        "vams": {
            "total_value_krw": 10_000_000,
            "cash_krw": 10_000_000,
            "return_pct": 0.0,
            "holdings": [],
        },
        "verity_brain": {
            "market_brain": {"avg_brain_score": 45},
        },
        "sectors": [],
        "recommendations": [
            {
                "ticker": "005930",
                "name": "삼성전자",
                "market": "KOSPI",
                "sector": "반도체",
                "price": 80000,
                "market_cap": 500_000_000_000_000,
                "per": 12.5,
                "pbr": 1.5,
                "recommendation": "AVOID",
                "verity_brain": {
                    "brain_score": 35,
                    "grade": "AVOID",
                    "grade_label": "회피",
                    "fact_score": {"score": 60, "components": {}},
                    "sentiment_score": {"score": 48, "components": {}},
                    "vci": {"vci": 5, "label": "neutral"},
                    "red_flags": {},
                    "data_coverage": 0.8,
                    "reasoning": "테스트 종목 요약",
                },
                "lynch_kr": {
                    "class": "STALWART",
                    "label": "안정 성장주",
                    "summary": "대형 안정주 분류",
                    "reasons": ["시총 대형", "EPS 안정"],
                },
                "commodity_margin": {
                    "primary": {
                        "commodity_ticker": "DRAM",
                        "correlation_60d": 0.45,
                        "commodity_20d_pct": 2.5,
                        "stock_20d_pct": 1.8,
                        "spread_regime": "neutral",
                    }
                },
                "kis_financial_ratio": {
                    "roe": 8.5,
                    "roa": 5.2,
                    "debt_ratio": 35.0,
                    "operating_margin": 12.0,
                },
            }
        ],
    }


@pytest.fixture
def portfolio():
    return _minimal_portfolio()


def _extract_text(pdf_path: str) -> str:
    import pdfplumber
    full = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            full += (page.extract_text() or "") + "\n"
    return full


def test_daily_admin_v2_methodology_chapter_rendered(portfolio, tmp_path, monkeypatch):
    """daily_admin v2 PDF 에 methodology chapter (B1~B6 + V1~V5 + KIS) 박힘."""
    monkeypatch.chdir(tmp_path)
    from api.reports.daily_admin_pdf import generate_daily_admin_pdf_v2
    path = generate_daily_admin_pdf_v2(portfolio)
    assert os.path.exists(path), f"PDF 생성 실패: {path}"

    text = _extract_text(path)

    # methodology chapter title
    assert "분석 산식 · 자체 검증" in text, "chapter 10 title 미박힘"
    # B1 가중치 7:3
    assert "fact 0.70 / sentiment 0.30" in text, "B1 가중치 미박힘"
    # B2 등급 임계
    assert "STRONG_BUY" in text and "BUY" in text, "B2 등급 임계 미박힘"
    # B3 VCI 임계
    assert "strong_contrarian_buy" in text, "B3 VCI 임계 미박힘"
    # B6 macro multiplier
    assert "Macro size multiplier" in text, "B6 macro multiplier 미박힘"
    # V1 ATR 2.5
    assert "ATR(14)" in text and "2.5" in text, "V1 ATR 임계 미박힘"
    # V4 EWMA
    assert "EWMA" in text, "V4 EWMA 미박힘"
    # V5 IC-DEAD
    assert "IC-DEAD" in text, "V5 IC-DEAD freeze 미박힘"
    # KIS 정책
    assert "OpenAPI 토큰은 일 1회" in text, "KIS 1일 1토큰 정책 미박힘"
    # 가설 명시
    assert "365일 운영 trail" in text, "가설 표기 미박힘"


def test_daily_admin_v2_stock_detail_block_rendered(portfolio, tmp_path, monkeypatch):
    """daily_admin v2 chapter 4 종목 detail block (Brain v5 / Lynch / 원자재 / KIS) 박힘."""
    monkeypatch.chdir(tmp_path)
    from api.reports.daily_admin_pdf import generate_daily_admin_pdf_v2
    path = generate_daily_admin_pdf_v2(portfolio)
    text = _extract_text(path)

    # AVOID/WATCH 종목 (삼성전자) 의 detail block 박혀야 — 4-C 분기
    assert "Brain v5 산출:" in text, "stock_detail_block Brain v5 prefix 미박힘"
    assert "(가중 7:3)" in text, "stock_detail_block 가중 7:3 미박힘"
    assert "Lynch 분류:" in text, "stock_detail_block Lynch 분류 미박힘"
    assert "STALWART" in text or "안정 성장주" in text, "Lynch 라벨 미박힘"
    assert "원자재 마진:" in text, "stock_detail_block 원자재 마진 미박힘"
    assert "KIS 재무비율:" in text or "ROE" in text, "stock_detail_block KIS 재무 미박힘"


def test_weekly_admin_methodology_chapter_rendered(portfolio, tmp_path, monkeypatch):
    """weekly_admin v2 chapter 7 methodology 박힘."""
    monkeypatch.chdir(tmp_path)
    from api.reports.weekly_admin_pdf import generate_weekly_admin_pdf

    # weekly = analysis dict 필요 — minimal stub
    analysis = {
        "period": "weekly",
        "kpi_summary": {},
        "narrative": "test stub",
        "performance": {},
        "strategy_review": {},
        "macro_review": {},
        "scenarios": [],
    }
    path = generate_weekly_admin_pdf(analysis, portfolio)
    assert os.path.exists(path)
    text = _extract_text(path)

    assert "분석 산식 · 자체 검증" in text, "weekly chapter 7 title 미박힘"
    assert "fact 0.70 / sentiment 0.30" in text, "weekly B1 가중치 미박힘"
    assert "OpenAPI 토큰은 일 1회" in text, "weekly KIS 정책 미박힘"
