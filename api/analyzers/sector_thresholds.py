"""
sector_thresholds — 한국 시장 PER/PBR 섹터별 quartile 임계값 헬퍼.

배경 (Perplexity Q2, 2026-05-10):
  한국 PBR 중앙값 1.1 vs S&P500 5.3 (4.8x 구조 차이). 미국 임계값 그대로 쓰면
  한국 90% 종목 false BUY 오탐. **sector_thresholds 의무 적용** — 메모리
  feedback_sector_aware_thresholds 정합.

5 카테고리 (Q2 quartile 출처: KRX·FnGuide·Bloomberg 2024~2025 집계):
  - 금융/은행
  - 지주회사 (yfinance 메타 직접 추출 어려움 — 운영에서 별도 매핑 필요. 현재 fallback)
  - 제조(철강/소재)
  - IT/전기전자
  - 바이오/제약

코리아 디스카운트 + ROE 7~8% 구조적 → Gordon 모형 PBR 자연 낮음 (이론 근거).
"""
from __future__ import annotations

from typing import Dict


# Q2 답 그대로 기록됨 (KRX·FnGuide·Bloomberg 2024~2025 quartile)
_PER_THRESHOLDS: Dict[str, Dict[str, float]] = {
    "금융":      {"Q1": 4.5,  "Q2": 6.2,  "Q3": 8.5,   "S&P500_Q2": 13.5},
    "지주":      {"Q1": 6.0,  "Q2": 8.8,  "Q3": 13.0,  "S&P500_Q2": 14.0},
    "제조":      {"Q1": 7.5,  "Q2": 10.5, "Q3": 15.8,  "S&P500_Q2": 16.0},
    "IT":        {"Q1": 12.0, "Q2": 16.5, "Q3": 24.0,  "S&P500_Q2": 28.0},
    "바이오":    {"Q1": 35.0, "Q2": 65.0, "Q3": 120.0, "S&P500_Q2": 42.0},
}

_PBR_THRESHOLDS: Dict[str, Dict[str, float]] = {
    "금융":      {"Q1": 0.30, "Q2": 0.55, "Q3": 0.80,  "S&P500_Q2": 1.8},
    "지주":      {"Q1": 0.45, "Q2": 0.72, "Q3": 1.05,  "S&P500_Q2": 1.9},
    "제조":      {"Q1": 0.40, "Q2": 0.65, "Q3": 1.10,  "S&P500_Q2": 2.2},
    "IT":        {"Q1": 0.80, "Q2": 1.20, "Q3": 2.10,  "S&P500_Q2": 5.5},
    "바이오":    {"Q1": 1.50, "Q2": 3.20, "Q3": 6.50,  "S&P500_Q2": 6.0},
}

# 부채비율 D/E (debt_ratio) 섹터별 임계 (2026-05-13 권위 검증 완료).
# 출처 (4건 권위 자료 정합):
#   1. **한국은행 2024 기업경영분석** (공식 발표): 전체 법인기업 평균 부채비율 101.9%
#      (https://www.bok.or.kr/portal/bbs/B0000501/view.do?nttId=10091824)
#      → 우리 제조 normal_max=100 정합 (평균 살짝 아래, 보수적)
#   2. **CEOScoreDaily** (4대 금융지주 K-IFRS 연결): 평균 1,176%
#      → 우리 금융 normal_max=1300 정합 (평균 위, 보수)
#      → 금융업 예치금=부채 회계처리로 일반 산업 대비 자연 1000%+
#   3. **newsspace.kr 랭킹**: 1,000%+ = 위험 (효성화학·아시아나항공 등)
#      → 우리 제조 avoid=300 정합 (충분히 위험 진입)
#   4. **12manage / namu.wiki**: 미국 표준 100%, 한국 제조 100~200% 정상
# 메모리 feedback_sector_aware_thresholds + feedback_source_attribution_discipline 정합.
# avoid: 자동 AVOID 임계 / high: 고부채 다운그레이드 / normal_max: 정상 범위 상한.
#
# 2026-05-13 정정: 금융 임계 800/500/200 → 2000/1500/1300.
# 이전 임계는 KB금융지주 1,180% 자동 탈락 시키는 결함 (메모리 정합 X). 1,200% 평균 기반 보수 재산정.
_DEBT_RATIO_THRESHOLDS: Dict[str, Dict[str, float]] = {
    "금융":      {"avoid": 2000.0, "high": 1500.0, "normal_max": 1300.0},
    "지주":      {"avoid": 400.0,  "high": 250.0,  "normal_max": 150.0},
    "제조":      {"avoid": 300.0,  "high": 200.0,  "normal_max": 100.0},
    "IT":        {"avoid": 250.0,  "high": 150.0,  "normal_max": 80.0},
    "바이오":    {"avoid": 200.0,  "high": 100.0,  "normal_max": 60.0},
}

# 알 수 없는 섹터 fallback — 한국 시장 전체 중앙값 (KOSPI 11배, PBR 1.1)
_PER_FALLBACK = {"Q1": 8.0,  "Q2": 11.0, "Q3": 16.0,  "S&P500_Q2": 21.0}
_PBR_FALLBACK = {"Q1": 0.55, "Q2": 0.95, "Q3": 1.50,  "S&P500_Q2": 3.0}
_DEBT_RATIO_FALLBACK = {"avoid": 300.0, "high": 200.0, "normal_max": 100.0}

VALID_BUCKETS = ("금융", "지주", "제조", "IT", "바이오")


# yfinance company_type → 5 bucket 매핑 (stock_data.py 의 _SECTOR_KO + _INDUSTRY_KO_KEYWORDS 기반)
_BUCKET_MAP: Dict[str, str] = {
    # 금융/은행
    "은행": "금융", "보험": "금융", "금융": "금융",
    # 지주: yfinance 직접 라벨 X — 미국 ETF 등 제한 (한국 지주는 별도 매핑 필요)
    # IT/전기전자
    "IT/기술": "IT", "반도체": "IT", "인터넷": "IT", "소프트웨어": "IT",
    "게임": "IT", "통신": "IT", "엔터": "IT", "통신/미디어": "IT",
    "전기/전자": "IT", "배터리": "IT", "EV": "IT", "전기차": "IT",
    "태양광": "IT", "풍력": "IT", "신재생에너지": "IT", "럭셔리": "IT",
    # 제조
    "철강": "제조", "화학": "제조", "소재/화학": "제조", "산업재": "제조",
    "자동차": "제조", "조선": "제조", "방산": "제조", "항공우주": "제조",
    "광업": "제조", "건설": "제조", "포장": "제조", "식품": "제조",
    "에너지": "제조", "석유": "제조", "가스": "제조", "유틸리티": "제조",
    "소비재": "제조", "필수소비재": "제조", "유통": "제조", "리츠": "제조",
    "부동산": "제조",
    # 바이오
    "바이오": "바이오", "제약": "바이오", "헬스케어": "바이오",
}


def resolve_sector_bucket(stock: dict) -> str:
    """stock dict 의 company_type / sector 필드 → 5 bucket 중 하나.

    매핑 미존재 시 빈 문자열 반환 (호출자가 fallback threshold 사용).
    Q2 정합 — 단일 임계 분기 금지 (메모리 feedback_sector_aware_thresholds).
    """
    ct = (stock.get("company_type") or "").strip()
    if ct and ct in _BUCKET_MAP:
        return _BUCKET_MAP[ct]
    # sector field 직접 확인 (yfinance Sector 영문)
    sec = (stock.get("sector") or "").strip()
    if sec:
        # 영문 sector → 5 bucket 직접 매핑
        eng_map = {
            "Financial Services": "금융",
            "Technology": "IT",
            "Communication Services": "IT",
            "Healthcare": "바이오",
            "Industrials": "제조",
            "Basic Materials": "제조",
            "Energy": "제조",
            "Consumer Cyclical": "제조",
            "Consumer Defensive": "제조",
            "Real Estate": "제조",
            "Utilities": "제조",
        }
        if sec in eng_map:
            return eng_map[sec]
    return ""  # fallback — 호출자가 _PER_FALLBACK 사용


def get_per_thresholds(bucket: str) -> Dict[str, float]:
    """섹터별 PER quartile. bucket 미일치 시 한국 시장 전체 fallback."""
    return _PER_THRESHOLDS.get(bucket, _PER_FALLBACK).copy()


def get_pbr_thresholds(bucket: str) -> Dict[str, float]:
    """섹터별 PBR quartile. bucket 미일치 시 한국 시장 전체 fallback."""
    return _PBR_THRESHOLDS.get(bucket, _PBR_FALLBACK).copy()


def get_debt_ratio_thresholds(bucket: str) -> Dict[str, float]:
    """섹터별 부채비율(D/E) 임계. bucket 미일치 시 fallback.

    avoid: 자동 AVOID / high: 고부채 다운그레이드 / normal_max: 정상 범위 상한
    feedback_sector_aware_thresholds 정합 — 금융주 D/E 200~1000% 정상 (단일 임계 분기 금지).
    """
    return _DEBT_RATIO_THRESHOLDS.get(bucket, _DEBT_RATIO_FALLBACK).copy()


def is_financial_excluded(stock: dict) -> bool:
    """재무 건전성 산식(Altman Z / Piotroski F-Score / Lynch TURNAROUND)에서 제외해야 하는 금융업/리츠 판정.

    Perplexity 2026-05-19 Q-fin-5 답변 정합:
      - KSIC 64~66 (은행/보험/금융지주/증권/캐피탈/저축은행) — Altman X4 부채구조 왜곡
      - KSIC 68 (리츠/부동산투자회사) — Piotroski F5 inverse 해석 학술 부재
      - 한국 4대 금융지주 부채비율 ~1176% → 원본 Z 0.1 false distress
      - 대체 평가 = CAMELS / BIS CET1 / NIM 추세 (별 sprint 큐)

    Returns: True = 금융/리츠 (산식 미적용), False = 일반 (산식 적용)
    """
    bucket = resolve_sector_bucket(stock)
    if bucket == "금융":
        return True
    company_type = (stock.get("company_type") or "").strip()
    if company_type in ("은행", "보험", "금융", "증권", "캐피탈", "저축은행", "금융지주", "리츠", "부동산"):
        return True
    sector_eng = (stock.get("sector") or "").strip()
    if sector_eng in ("Financial Services", "Real Estate"):
        return True
    industry = (stock.get("industry") or "").strip()
    if any(kw in industry for kw in ("Bank", "Insurance", "REIT", "Capital Markets", "Holding Companies")):
        return True
    return False


def is_us_threshold_unsafe(bucket: str, metric: str = "PBR") -> bool:
    """미국 임계값(S&P500_Q2) 적용 시 한국 분포에서 false signal 위험 여부.

    Q2 정량 근거:
      - 금융 PBR: 한국 Q3 0.80 vs S&P500 1.8 — 미국 1.0 cut 적용 시 한국 90% false BUY
      - 바이오 PER: 한국 Q2 65 vs S&P500 42 — 미국 기준 적용 시 한국 비싼 종목이 정상 범위
    """
    if metric.upper() == "PBR":
        kor = get_pbr_thresholds(bucket)
        return abs(kor["S&P500_Q2"] - kor["Q2"]) > 0.5  # 0.5x 이상 차이면 unsafe
    if metric.upper() == "PER":
        kor = get_per_thresholds(bucket)
        return abs(kor["S&P500_Q2"] - kor["Q2"]) > 5.0  # 5배 이상 차이면 unsafe
    return False
