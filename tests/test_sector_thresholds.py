"""
sector_thresholds 회귀 테스트 — Q2 quartile 표 + 5 bucket 매핑 + 미국 임계값 unsafe 가드.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.analyzers import sector_thresholds as st


def test_5_buckets_quartile_loaded():
    """5 카테고리 모두 PER + PBR threshold 박힘."""
    for bucket in st.VALID_BUCKETS:
        per = st.get_per_thresholds(bucket)
        pbr = st.get_pbr_thresholds(bucket)
        assert "Q1" in per and "Q2" in per and "Q3" in per
        assert "Q1" in pbr and "Q2" in pbr and "Q3" in pbr
        assert per["Q1"] < per["Q2"] < per["Q3"], f"{bucket} PER quartile 단조성 위반"
        assert pbr["Q1"] < pbr["Q2"] < pbr["Q3"], f"{bucket} PBR quartile 단조성 위반"


def test_kor_lower_than_us_per_pbr():
    """Q2 핵심 발견 — 한국 중앙값 < S&P500 중앙값 (구조적 디스카운트).
    바이오만 예외 (한국 65 > S&P500 42)."""
    for bucket in ("금융", "지주", "제조", "IT"):
        per = st.get_per_thresholds(bucket)
        pbr = st.get_pbr_thresholds(bucket)
        assert per["Q2"] < per["S&P500_Q2"], f"{bucket} 한국 PER 중앙값이 S&P500 보다 높음 (이론 위반)"
        assert pbr["Q2"] < pbr["S&P500_Q2"], f"{bucket} 한국 PBR 중앙값이 S&P500 보다 높음 (이론 위반)"
    # 바이오는 역방향 (Q2 답 정합)
    bio_per = st.get_per_thresholds("바이오")
    assert bio_per["Q2"] > bio_per["S&P500_Q2"], "바이오 한국 PER 중앙값이 S&P500 보다 낮음 (Q2 분석 모순)"


def test_resolve_sector_bucket_kr_company_type():
    """company_type 한글 → 5 bucket 매핑."""
    assert st.resolve_sector_bucket({"company_type": "은행"}) == "금융"
    assert st.resolve_sector_bucket({"company_type": "반도체"}) == "IT"
    assert st.resolve_sector_bucket({"company_type": "철강"}) == "제조"
    assert st.resolve_sector_bucket({"company_type": "바이오"}) == "바이오"
    assert st.resolve_sector_bucket({"company_type": "게임"}) == "IT"
    assert st.resolve_sector_bucket({"company_type": "조선"}) == "제조"


def test_resolve_sector_bucket_us_yfinance_sector():
    """yfinance 영문 sector → 5 bucket 매핑 (US 종목 대응)."""
    assert st.resolve_sector_bucket({"sector": "Financial Services"}) == "금융"
    assert st.resolve_sector_bucket({"sector": "Technology"}) == "IT"
    assert st.resolve_sector_bucket({"sector": "Healthcare"}) == "바이오"
    assert st.resolve_sector_bucket({"sector": "Industrials"}) == "제조"


def test_resolve_sector_bucket_unknown_falls_back():
    """알 수 없는 섹터 → 빈 문자열 (호출자가 fallback threshold 사용)."""
    assert st.resolve_sector_bucket({}) == ""
    assert st.resolve_sector_bucket({"company_type": "메타버스"}) == ""
    assert st.resolve_sector_bucket({"sector": "Cryptocurrency"}) == ""


def test_fallback_thresholds_for_unknown_bucket():
    """미일치 bucket → 한국 시장 전체 fallback (KOSPI 11배 / PBR 1.1)."""
    per = st.get_per_thresholds("unknown")
    pbr = st.get_pbr_thresholds("")
    assert per["Q2"] == 11.0  # KOSPI 전체 중앙값 fallback
    assert pbr["Q2"] == 0.95  # 한국 시장 fallback


def test_us_threshold_unsafe_warns_high_divergence():
    """금융 PBR 한국 Q2 0.55 vs S&P500 1.8 — unsafe."""
    assert st.is_us_threshold_unsafe("금융", "PBR") is True
    # 바이오 PER 한국 65 vs S&P500 42 — diff 23, unsafe
    assert st.is_us_threshold_unsafe("바이오", "PER") is True
