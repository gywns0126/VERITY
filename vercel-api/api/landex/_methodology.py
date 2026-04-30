"""LANDEX 방법론 SSOT (Single Source of Truth).

V/D/S/C/R 5대 지표 가중치, 정규화 규칙, 등급 매핑, Hysteresis, Confidence Score 정의.
모든 백엔드 라우트와 프론트가 /api/landex/methodology 통해 이 정보를 받아 사용.

변경 시 version 필드 bump + 모든 사용처 재검증 필수.
"""
from typing import Dict, List, Tuple, Optional

VERSION = "1.2"
LAST_UPDATED = "2026-04-30"
# v1.2 changelog (2026-04-30):
#   - balanced preset 가중치 조정: V 0.30→0.32, D 0.20→0.15, S 0.15→0.18
#     이유: D 산식 v1.1 (26주/±2.0cap) 후에도 outlier 8구 (강동·마포·송파 등)는
#     시점 시프트로 10~26점 변동 — D 영향력 25% 감소 + V/S 보강으로 안정화
#   - d_high_volatility 플래그 추가 (raw_payload) — 26주 시계열 변동률 std > 0.3%p
#     백테스트 합성 시 high-volatility 구의 D 점수는 confidence 낮음 표시
#
# v1.1 changelog (2026-04-30):
#   - D (Development) 가속도 산식 윈도우 12주 → 26주 + cap ±0.5%p → ±2.0%p
#     이유: 메타-검증 결과 12주/±0.5cap 산식이 시점 1주 시프트에 30점 변동 — 합성 부적합
#     4배 robust 화 (0.05%p 차이 = 5점 → 1.25점)
#   - V momentum penalty 시계열 슬라이스 명시 — D 와 윈도우 분리 (V 는 항상 최근 12주)

# ── 5대 지표 정의 ──
FACTORS: Dict[str, dict] = {
    "V": {
        "name": "Value",
        "name_ko": "가치",
        "weight": 0.30,
        "metrics": ["price_to_avg_ratio", "official_price_gap"],
        "description": "지역·동급 평균 대비 저평가 정도",
        "inverted": False,
    },
    "D": {
        "name": "Development",
        "name_ko": "개발 호재",
        "weight": 0.20,
        "metrics": ["transit_exp_index", "urban_plan_score"],
        "description": "교통망 확충 및 용도지역 변경 가능성",
        "inverted": False,
    },
    "S": {
        "name": "Supply",
        "name_ko": "수급·심리",
        "weight": 0.15,
        "metrics": ["inventory_stock", "absorption_rate", "sentiment_index"],
        "description": "미분양·입주 물량·시장 심리 종합",
        "inverted": False,
    },
    "C": {
        "name": "Convenience",
        "name_ko": "입지 인프라",
        "weight": 0.20,
        "metrics": ["subway_proximity", "workplace_accessibility", "school_district"],
        "description": "직주근접 + 학군 + 인프라 접근성",
        "inverted": False,
    },
    "R": {
        "name": "Risk",
        "name_ko": "리스크",
        "weight": 0.15,
        "metrics": ["jeonse_ratio", "interest_rate_sensitivity", "ltv_pressure"],
        "description": "깡통전세·금리 민감도·대출 규제 부담",
        "inverted": True,  # 낮을수록 좋음 → 100 - score
    },
}

# 가중치 합계 검증 (런타임)
assert abs(sum(f["weight"] for f in FACTORS.values()) - 1.0) < 1e-6, "factor weights must sum to 1.0"

# ── 가중치 프리셋 (사용자 성향별 + 시장국면별) ──
WEIGHT_PRESETS: Dict[str, Dict[str, float]] = {
    # 사용자 성향별 (정적)
    # balanced v1.2 (2026-04-30): D 0.20→0.15 (시점 민감도 보정), V/S 보강
    "balanced":  {"V": 0.32, "D": 0.15, "S": 0.18, "C": 0.20, "R": 0.15},
    "growth":    {"V": 0.15, "D": 0.30, "S": 0.20, "C": 0.20, "R": 0.15},  # 공격형
    "value":     {"V": 0.40, "D": 0.10, "S": 0.10, "C": 0.20, "R": 0.20},  # 방어형
    # 시장국면별 (Perplexity·Gemini 합의 — 거시 환경 따라 동적 전환)
    "tightening":          {"V": 0.25, "D": 0.15, "S": 0.15, "C": 0.20, "R": 0.25},  # 금리 긴축기 — DSR·전세가율 중심
    "redevelopment_boom":  {"V": 0.20, "D": 0.30, "S": 0.10, "C": 0.20, "R": 0.20},  # 재개발 붐 — 종상향·GTX 호재
    "supply_shock":        {"V": 0.25, "D": 0.15, "S": 0.25, "C": 0.20, "R": 0.15},  # 입주 폭탄 — 공급 과잉 리스크
}

# ── 현재 권고 시장국면 (수동 갱신, 자동 MRS 는 v1.5) ──
# 2026-04: TIGHTENING (다주택자 만기연장 불허 4/17 시행 + 한은 동결 4/10 + 주담대 4.32% 고점)
CURRENT_REGIME = {
    "preset": "tightening",
    "since": "2026-04",
    "rationale": (
        "다주택자 만기연장 원칙 불허 (2026-04-17 시행) + 가계대출 증가율 1.5% 목표 + "
        "한은 기준금리 2.50% 동결(2026-04-10) + 주담대 4.32%(2년 3개월 최고) + "
        "4월부터 고액 주담대 +0.25%p 가산금리. R축 25% 상향 시나리오 작동."
    ),
    "review_date": "2026-05-28",  # 신임 총재 첫 금통위
}

# ── 정규화 규칙 ──
NORMALIZATION = {
    "method": "minmax",
    "outlier_clip_pct": 0.05,   # 상하위 5% Cut-off
    "low_liquidity_threshold": 5,  # 거래 5건 미만 단지·면적은 low_liquidity 플래그
}

# ── 이상치 필터링 (3-Layer) ──
OUTLIER_FILTERS = {
    "rule_based": {
        "exclude_trade_types": ["직거래", "증여", "상속"],  # 국토부 거래유형
        "require_registration": True,  # 등기일자 필수
    },
    "statistical": {
        "hard_cut_pct": 0.30,        # 단지·면적 평균 대비 ±30%
        "iqr_multiplier": 1.5,       # IQR × 1.5 (둘 중 더 보수적)
    },
    "distribution": {
        "min_trades_for_median": 5,  # 5건 미만은 평균값 신뢰도 낮음 표시
        "default_aggregation": "median",  # robust
    },
}

# ── 시계열 / 집계 ──
AGGREGATION = {
    "unit": "gu",  # 구 단위 (v1). 동/단지는 v1.5
    "time_window_months": 6,  # 기본 6개월 rolling
    "extended_window_months": 12,  # 거래 5건 미만 시 확장
    "price_basis": "pyeong",  # 평당가(₩/3.3m²) — 한국 관행
    "real_terms": False,  # 명목가 v1 (실질가는 v2 옵션)
}

# ── 등급 체계: 내부 10단계 ↔ UI 5단계 ──
TIER_10: List[dict] = [
    {"code": "S+",  "min": 95, "max": 100, "status": "Perfect Alpha",   "action": "시장을 압도하는 절대적 기회 (강력 매수)"},
    {"code": "S",   "min": 90, "max": 94,  "status": "Prestige",        "action": "핵심 입지 및 고성장성 확정 지역"},
    {"code": "A+",  "min": 80, "max": 89,  "status": "Prime Growth",    "action": "합리적 가격의 고성장주 성격 단지"},
    {"code": "A",   "min": 70, "max": 79,  "status": "Stable Value",    "action": "탄탄한 인프라 기반의 안정적 투자처"},
    {"code": "B+",  "min": 60, "max": 69,  "status": "Neutral Plus",    "action": "평균 이상의 입지나 단기 호재 대기 중"},
    {"code": "B",   "min": 50, "max": 59,  "status": "Market Average",  "action": "시장 수익률을 따라가는 표준 단지"},
    {"code": "C+",  "min": 40, "max": 49,  "status": "Observation",     "action": "특정 리스크 해소 시 반등 가능"},
    {"code": "C",   "min": 30, "max": 39,  "status": "Underperform",    "action": "펀더멘털 대비 가격 다소 높음 (보수적)"},
    {"code": "D",   "min": 15, "max": 29,  "status": "Alert",           "action": "가격 하락 압력 또는 입지 노후화 심각"},
    {"code": "F",   "min": 0,  "max": 14,  "status": "Exit / Avoid",    "action": "자본 잠식 우려 및 유동성 함정 위험"},
]

# 10단계 → 5단계 UI 매핑 (Tag.tsx의 grade enum과 정합)
TIER_10_TO_5: Dict[str, str] = {
    "S+": "HOT",  "S":  "HOT",
    "A+": "WARM", "A":  "WARM",
    "B+": "NEUT", "B":  "NEUT",
    "C+": "COOL", "C":  "COOL",
    "D":  "AVOID","F":  "AVOID",
}

# Hysteresis (이력 현상) — 등급 경계 깜빡임 방지
HYSTERESIS = {
    "buffer_pct": 2.0,  # ±2점 버퍼 (89.4점에서 A+ 진입은 90, A 강등은 88)
}

# ── DigestPublishPanel 체크리스트 9종 ──
PUBLISH_CHECKLIST = [
    # Data Integrity
    {"id": "recency",      "category": "data",  "label": "Recency Check",     "description": "실거래가·매물 데이터가 최근 72시간 이내"},
    {"id": "outlier",      "category": "data",  "label": "Outlier Filter",     "description": "평균가 대비 ±30% 이상 이상치 제거"},
    {"id": "source",       "category": "data",  "label": "Source Validation",  "description": "V/D/S/C/R 결측치 2개 이상 미발생"},
    # Logical Consistency
    {"id": "divergence",   "category": "logic", "label": "Bull/Bear Cross-check", "description": "LANDEX↑ + 거래량↓ 또는 GEI Stage 4 다이버전스 경고 포함"},
    {"id": "weight",       "category": "logic", "label": "Weighted Alignment", "description": "특정 가중치가 60% 이상 지배하지 않음"},
    {"id": "sentiment",    "category": "logic", "label": "Sentiment Sync",     "description": "정량 점수와 뉴스/소셜 감성 방향성 일치"},
    # UX & Legal
    {"id": "actionable",   "category": "ux",    "label": "Actionable Insight", "description": "매수/보유/관망 결론 명확"},
    {"id": "disclosure",   "category": "ux",    "label": "Risk Disclosure",    "description": "투자 참고용 + 본인 책임 면책 문구"},
    {"id": "comparison",   "category": "ux",    "label": "Comparison Context", "description": "인근 단지·구 평균 비교 차트 포함"},
]

CONFIDENCE = {
    "publish_threshold": 80.0,  # 80점 이상이어야 발행 가능
    "divergence_penalty": 15.0,  # LANDEX-GEI 다이버전스 발생 시 감점
}


def get_methodology_dict() -> dict:
    """API 응답용 직렬화."""
    return {
        "version": VERSION,
        "last_updated": LAST_UPDATED,
        "factors": FACTORS,
        "weight_presets": WEIGHT_PRESETS,
        "current_regime": CURRENT_REGIME,
        "normalization": NORMALIZATION,
        "outlier_filters": OUTLIER_FILTERS,
        "aggregation": AGGREGATION,
        "tier_10": TIER_10,
        "tier_10_to_5": TIER_10_TO_5,
        "hysteresis": HYSTERESIS,
        "publish_checklist": PUBLISH_CHECKLIST,
        "confidence": CONFIDENCE,
    }
