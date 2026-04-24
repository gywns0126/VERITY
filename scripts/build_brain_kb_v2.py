#!/usr/bin/env python3
"""
brain_knowledge_base.json v2 빌더 — 17권 리포트 기반 enrich.

배경:
  커서가 정리한 Vol.1/Vol.2 리포트(a36fd53d.pdf, a3901866.pdf) 는 실제 파이프라인에
  전혀 주입되지 않음(`_load_knowledge_base()` 미호출, `_build_knowledge_context()` 하드코딩).
  이 스크립트는 리포트의 핵심 구조(공식·규칙·트리거 조건)를 v1 기반 JSON 에 병합해
  파이프라인이 동적으로 인용할 수 있도록 한다.

보존 원칙:
  - v1 최상위 카테고리 키와 각 책 엔트리의 기존 필드는 **절대 삭제 안 함**
  - enrich 는 `trigger_conditions`, `key_principles` 등 **새 필드 추가** 형태
  - frameworks / trigger_index / report_sources 는 신규 최상위 섹션

Usage:
  python3 scripts/build_brain_kb_v2.py           # build & save
  python3 scripts/build_brain_kb_v2.py --check   # regression check (no write)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
KB_PATH = REPO / "data" / "brain_knowledge_base.json"


# ─────────────────────────────────────────────────────────
# 1. 각 책별 확장 필드 (v1 엔트리 위에 merge)
#    trigger_conditions: 언제 이 책을 Gemini 프롬프트에 인용할지
#    key_principles: 3~7개 짧은 원칙 (리포트에서 핵심만)
# ─────────────────────────────────────────────────────────

BOOK_ENRICH = {
    "value_investing": {
        "graham_intelligent_investor": {
            "trigger_conditions": {
                "primary": "per > 0 and per <= 15 and pbr < 1.5",
                "secondary": "pb_pe_product <= 22.5 and current_ratio >= 2.0",
                "context": "가치주 스크리닝 / 안전마진 판단 / 방어적 포트폴리오 구성",
            },
            "key_principles": [
                "안전마진(내재가치 대비 33%+ 할인) 확보 시에만 매수",
                "방어적 투자자 7기준: 대형주, 유동비율 2배+, 20년 연속 배당, 10년 흑자, 10년 EPS 33%+ 성장, PER ≤ 15, PBR×PER ≤ 22.5",
                "Mr.Market은 서번트 — 비관 시 매수, 낙관 시 무시. 가이드로 따르지 말 것",
                "채권/주식 25~75% 범위 내 비중 유지. 절대 한 자산 0% 또는 100% 금지",
            ],
        },
        "buffett_essays": {
            "trigger_conditions": {
                "primary": "roe > 15 and debt_ratio < 100",
                "secondary": "operating_margin > 15 and consecutive_profit_years >= 5",
                "context": "경제적 moat 평가 / 장기 보유 후보 / 경영진 평가",
            },
            "key_principles": [
                "4필터: 이해 가능 + 경쟁우위(moat) + 유능·정직한 경영진 + 합리적 가격",
                "Owner Earnings = 순이익 + 감가상각 - 유지CapEx ± 운전자본변동 (실제 주주 귀속 현금)",
                "단기 투표기, 장기 저울 — 장기적으론 내재가치를 추종",
                "ROE > WACC 5년 이상 지속 여부로 경영진 평가",
            ],
        },
        "bogle_common_sense": {
            "trigger_conditions": {
                "primary": "portfolio_allocation_decision",
                "secondary": "cost_sensitivity_analysis or long_horizon_planning",
                "context": "장기 패시브 vs 액티브 판단 / 비용 민감도 / 인덱스 전략",
            },
            "key_principles": [
                "총 수익 = 배당수익률 + 이익성장률 + 밸류에이션변화 - 비용",
                "비용 1%p 차이 → 30년 후 수익 25%+ 차이 (복리 효과)",
                "평균 투자자 수익 = 시장 수익 - 비용 → 비용 최소화 인덱스 장기 우위",
                "시장 타이밍은 대부분 실패 — 연 1회 리밸런싱으로 비용 최소화",
            ],
        },
    },
    "trend_momentum": {
        "livermore_operator": {
            "trigger_conditions": {
                "primary": "volume_spike_ratio >= 2.0 or breakout_new_high",
                "secondary": "drop_from_high_pct > -10 and trend_direction_clear",
                "context": "피봇 포인트 탐지 / 탐색매매 진입 / 추세 확인",
            },
            "key_principles": [
                "최소저항선 원칙: 상승장만 매수 / 하락장만 공매도 / 횡보는 현금",
                "탐색매매 4단계: 20%씩 분할, 상승 확인 후 추가 (역피라미딩 금지)",
                "10% 손실 자동 청산 — 예외 없음",
                "피봇포인트: 거래량 전일 대비 200%+ + 가격 전환 → 반전 신호",
                "정보·팁 무시 — 자신의 분석이 최우선",
            ],
        },
        "oneil_canslim": {
            "trigger_conditions": {
                "primary": "eps_growth_qoq_pct >= 20 and new_high_breakout",
                "secondary": "rs_rating >= 80 and market_direction_up",
                "context": "성장주 신고가 돌파 매수 / 기관 후원 확인 / 상승장 한정",
            },
            "key_principles": [
                "CANSLIM: Current EPS 20~50%+ / Annual 5년 24%+ / New 신고가 / Shares 2500만 이하 / Leader RS 80%+ / Institutional 일부 / Market 상승장",
                "98%가 꺼리는 신고가 매수가 정답 — '너무 높아 보이는 것이 더 간다'",
                "매수 후 8% 하락 시 무조건 손절",
            ],
        },
    },
    "risk_psychology": {
        "taleb_fooled_by_randomness": {
            "trigger_conditions": {
                "primary": "backtest_sample_size < 100 or sharpe_ratio < 1.0",
                "secondary": "this_time_is_different_narrative_detected or recent_winning_streak",
                "context": "전략 검증 / 운 vs 실력 판별 / 블랙스완 리스크 평가",
            },
            "key_principles": [
                "생존자 편향: 성공 샘플만 보면 안 됨 (1000명 동전던지기 → 1명 10년 연속 승리)",
                "샤프 비율 > 1.0 + 최소 100회 거래 샘플 + MDD < 15% 기준 요구",
                "경로 의존성: 손실 포지션 집착 경계. '현재가에 새로 잡겠는가?' 자문",
                "블랙스완: 모델이 예측 못하는 꼬리 리스크 상존. LTCM 사례",
            ],
        },
        "douglas_trading_in_zone": {
            "trigger_conditions": {
                "primary": "any_active_position",
                "secondary": "consecutive_losses >= 3 or consecutive_wins >= 5",
                "context": "심리 규율 / 일관된 실행 / 확률적 사고 유지",
            },
            "key_principles": [
                "5가지 기본 진실: 모든 거래는 loser 가능 / 엣지는 확률우위뿐 / 랜덤 결과-일관 성과 / 현재 순간 집중 / 사전 리스크 정의",
                "Zone 상태: 공포·강박 없이 시스템 실행 — 매 거래를 1000번 중 하나로 인식",
                "카지노 마인드셋: 각 거래 독립, 엣지 일관 적용, 결과에 무감각",
                "연속 손실/수익 후 시스템 변경 금지, 포지션 크기 유지",
            ],
        },
        "douglas_disciplined_trader": {
            "trigger_conditions": {
                "primary": "trader_psychology_check",
                "secondary": "rule_deviation_detected or impulsive_trade_pattern",
                "context": "자기규율 강화 / 심리 함정 탐지 / 시스템 이탈 방지",
            },
            "key_principles": [
                "4가지 심리 함정: 규칙 만들기 거부 / 책임 회피 / 랜덤 보상 중독 / 외부 통제 의존",
                "자기가치감 법칙: 실제 수익 상한 = 자기가치감. 낮으면 자기파괴 패턴",
                "시장은 능동적 선택 없이도 수동적으로 잃을 수 있는 유일한 환경",
            ],
        },
        "mackay_madness_crowds": {
            "trigger_conditions": {
                "primary": "cape > 25 or media_overheating_index_high",
                "secondary": "this_time_different_narrative or cross_sector_same_theme_rally",
                "context": "버블 탐지 / 군중 광기 경고 / 테마 과열 감지",
            },
            "key_principles": [
                "버블 5단계: 씨앗 스토리 → 초기 수익자 → 언론 증폭 → 대중 유입 → 내부자 매도·붕괴",
                "연료는 탐욕+사회적 증거, 방아쇠는 유동성 경색 또는 내부자 대규모 매도",
                "강제 유동성 공급은 일시 지지 후 더 큰 붕괴 (미시시피 버블 교훈)",
            ],
        },
        "elder_trading_for_living": {
            "trigger_conditions": {
                "primary": "any_active_trade",
                "secondary": "position_size_calculation or regime_classification",
                "context": "삼중스크린 진입 / 자금관리 / ADX 레짐 판별",
            },
            "key_principles": [
                "삼중 스크린: 주간 MACD(장기추세) → 일간 Stochastic(중기조정) → 시간/진입",
                "3M 중요도: Mind > Money > Method (대부분 Method 중시하지만 오판)",
                "2% 규칙(단일 거래) + 6% 규칙(월 최대) — 6% 도달시 당월 거래 중단",
                "ADX < 20 비추세(오실레이터) / ADX > 25 강추세(모멘텀) / ADX > 40 과열",
            ],
        },
        "lowenstein_when_genius_failed": {
            "trigger_conditions": {
                "primary": "leverage_ratio >= 15 or concentration_pct > 10",
                "secondary": "liquidity_stress_indicator or correlation_spike or tail_risk_elevated",
                "context": "시스템 리스크 평가 / 레버리지 경고 / 꼬리 리스크",
            },
            "key_principles": [
                "레버리지 15배+ = LTCM 위험 구간 (정상 헤지펀드 5~10배)",
                "위기 시 모든 상관관계 → 1 수렴. 다양한 전략이 같은 방향으로 수렴",
                "과거 데이터에 없던 일이 미래에 일어난다 (러시아 모라토리엄 교훈)",
                "유동성 위기: 모두 동시 탈출 → 가격에 청산 불가 → 악순환",
                "단일 포지션 ≤ 포트폴리오 1~2% 초과 금지",
            ],
        },
        "schwager_new_market_wizards": {
            "trigger_conditions": {
                "primary": "position_sizing_decision",
                "secondary": "consensus_divergence_detected or macro_theme_formation",
                "context": "포지션 사이징 / 변형 인식 / 감정 규율 / 거시 집중 베팅",
            },
            "key_principles": [
                "Sperandeo 추세전환 3단계: 추세선 이탈 → 실패 테스트 → 저점 이탈",
                "Trout 0.5% 규칙: 단일 거래 리스크 ≤ 자본 0.5%, 변동성 반비례 사이징",
                "Druckenmiller: 확신 있을 때 집중 베팅, 아니면 최소 규모",
                "Steinhardt 변형 인식: 컨센서스와 다른 나만의 판단 + 검증 근거 + 촉매 + 타이밍",
                "트레이더 성공 요인: 실수 인정 능력(40%) > 감정규율(35%) > 리스크관리(20%) > 분석(5%)",
            ],
        },
    },
    "quantitative": {
        "chan_algorithmic_trading": {
            "trigger_conditions": {
                "primary": "backtest_or_strategy_selection",
                "secondary": "statistical_arb_opportunity or half_life_calculation",
                "context": "평균회귀 vs 모멘텀 판별 / 페어 트레이딩 / 반감기 계산",
            },
            "key_principles": [
                "ADF t-통계 음수 + Hurst < 0.5 → 평균회귀 / Hurst > 0.5 → 모멘텀",
                "반감기 < 30일 → 평균회귀 전략, 30~90일 → 볼린저 중기",
                "공적분 검정(CADF/Johansen) 성립 시 페어 롱숏",
                "목표 샤프 > 1.0, MDD < 20%, Kelly 절반 레버리지",
            ],
        },
        "shiller_irrational_exuberance": {
            "trigger_conditions": {
                "primary": "cape_level_classification",
                "secondary": "macro_bubble_detection or feedback_loop_signs",
                "context": "거시 밸류에이션 판단 / 버블 국면 감지",
            },
            "key_principles": [
                "CAPE = 실질주가 / 10년 실질 EPS 평균",
                "< 15 저평가 / 15~25 적정 / > 25 고평가 / > 30 역사적 버블",
                "5단계 버블 피드백: 촉발 → 가격상승-열광 루프 → 문화적 증폭 → 앵커링 → 자연 폰지",
                "미디어는 결과의 사후 스토리텔러 (1989 UAL 사례)",
            ],
        },
    },
    "technical_candle": {
        "nison_candlestick_psychology": {
            "trigger_conditions": {
                "primary": "technical_signals_count >= 2 or reversal_candle_detected",
                "secondary": "volume_confirmation or support_resistance_match",
                "context": "반전/지속 패턴 확인 / 거래량 교차 검증",
            },
            "key_principles": [
                "단일 캔들 1점, 2캔들 2점, 3캔들 3점 가중치 시스템",
                "확인 조건(각 +1점): 거래량 증가 / 지지저항선 일치 / 상위 레짐 방향 일치",
                "임계값: ≥ 4 강 신호 / 2~3 보통 / < 2 무시",
                "강세 반전 Top: 망치, 관통형, 아침별, 삼병정 / 약세 Top: 흑운형, 저녁별, 까마귀",
            ],
        },
    },
}


# ─────────────────────────────────────────────────────────
# 2. Frameworks — 리포트의 Python 딕셔너리들 이식
#    코드 적용용 (파이프라인이 조건식·임계값 직접 사용 가능)
# ─────────────────────────────────────────────────────────

FRAMEWORKS = {
    "graham_defensive_screen": {
        "description": "Graham 방어적 투자자 종목 스크리닝 기준 (Vol.2 §1.4)",
        "criteria": {
            "market_cap_min": "large_cap",
            "current_ratio_min": 2.0,
            "dividend_years_min": 20,
            "earnings_consecutive_years": 10,
            "eps_growth_10yr_min_pct": 33,
            "pe_ratio_max": 15,
            "pb_pe_product_max": 22.5,
            "margin_of_safety_min_pct": 33,
        },
    },
    "intelligent_investor_signals": {
        "description": "Graham 내재가치 기반 의사결정 (Vol.2 §1.3)",
        "rules": {
            "BUY": "price < intrinsic_value * 0.67",
            "SELL": "price > intrinsic_value * 1.25",
            "HOLD": "0.67 <= price/intrinsic_value <= 1.25",
            "SPECULATIVE_WARNING": "price > intrinsic_value * 1.5",
        },
    },
    "buffett_management_score": {
        "description": "경영진 평가 (Vol.2 §2.6)",
        "dimensions": {
            "capital_allocation_quality": "0~10",
            "shareholder_communication": "0~10",
            "roe_vs_cost_of_capital": "ROE > WACC for 5+ consecutive years",
            "integrity_red_flags": [
                "excessive_stock_options",
                "misleading_accounting",
                "related_party_transactions",
            ],
        },
    },
    "zone_trading_rules": {
        "description": "Douglas Zone 상태 유지 실행 규칙 (Vol.2 §4.6)",
        "rules": {
            "on_signal": "100% 실행 (의심 금지)",
            "in_position": "모니터링하되 행동하지 않음",
            "stop_loss": "사전 정의 가격에서 자동 실행",
            "take_profit": "시스템 목표에서 실행",
            "after_loss_streak": "시스템 변경 금지, 계속 실행",
            "after_win_streak": "포지션 크기 섣불리 증가 금지",
        },
    },
    "elder_risk_rules": {
        "description": "Elder 자금관리 2%/6% 규칙 (Vol.2 §7.3)",
        "rules": {
            "max_single_trade_risk_pct": 2,
            "max_monthly_loss_pct": 6,
            "stop_trading_trigger": "월 손실 6% 도달 시 그 달 거래 중단",
            "position_size_formula": "risk_amount / abs(entry - stop)",
        },
    },
    "ltcm_warning_signals": {
        "description": "LTCM 붕괴 교훈 기반 시스템 리스크 조기 경보 (Vol.2 §6.3)",
        "signals": [
            "swap_spread > historical_mean * 2",
            "leverage_ratio > 15",
            "single_position_concentration_pct > 10",
            "liquidity_stress_indicator_up",
            "cross_asset_correlation_spike",
            "same_strategy_competitor_liquidation_news",
            "emerging_market_bond_spread_surge",
        ],
        "counting_rules": {
            "SELL": "3개 이상 동시 발동",
            "STRONG_SELL": "4개 이상 동시 발동",
        },
    },
    "trout_position_sizing": {
        "description": "Monroe Trout 극저위험 포지션 사이징 (Vol.2 §3.3)",
        "rules": {
            "single_trade_risk_max_pct": 0.5,
            "volatility_scaling": "inverse — 변동성 높을수록 포지션 축소",
            "no_immediate_profit_response": "진입 후 즉각 수익 없으면 포지션 즉시 축소",
        },
        "priority_order": [
            "1. Capital Preservation",
            "2. Consistent Profitability",
            "3. Superior Returns (1,2 달성 후에만)",
        ],
    },
    "sperandeo_trend_reversal": {
        "description": "Victor Sperandeo 3단계 추세 전환 확인 (Vol.2 §3.2)",
        "stages": [
            "추세선 이탈 (Trend Line Break)",
            "이전 고점의 실패 테스트 (Failed Test of Prior High)",
            "최근 상대적 저점 하향 돌파",
        ],
        "bear_market_condition": "기간 6개월 이상 + 하락폭 15% 이상",
        "intermediate_decline": "15일 이상 지속 하락",
    },
    "livermore_probing": {
        "description": "Livermore 탐색매매 4단계 분할 진입 (Vol.1 §5.2)",
        "steps": [
            {"pct": 20, "when": "initial probe"},
            {"pct": 20, "when": "profit confirmed after step 1"},
            {"pct": 20, "when": "profit confirmed after step 2"},
            {"pct": 40, "when": "normal pullback + recovery confirmed"},
        ],
        "stop_loss_pct": -10,
        "direction_rule": "역피라미딩 금지 — 상승 확인하며 매수",
    },
    "chan_strategy_selection": {
        "description": "Chan 정량전략 선택 의사결정 (Vol.1 §4.7)",
        "rules": {
            "half_life_lt_30d": "평균회귀 전략",
            "half_life_30_90d": "볼린저 밴드 중기 전략",
            "hurst_gt_0_5": "모멘텀 전략",
            "min_sharpe": 1.0,
            "max_mdd_pct": 20,
            "leverage_cap": "Kelly / 2",
        },
        "data_hygiene": [
            "survivorship_bias_remove",
            "look_ahead_bias_remove",
            "strict_train_test_split",
        ],
    },
    "cape_macro_strategy": {
        "description": "Shiller CAPE 거시 레짐 (Vol.1 §3.6)",
        "bands": {
            "< 15": "주식 비중 과중 (강한 매수 신호)",
            "15~25": "중립 — 개별 종목 선택 집중",
            "> 25": "주식 비중 축소, 방어적",
            "> 30": "버블 경고, 포지션 대폭 축소",
        },
        "cross_checks": [
            "주식-채권 크로스 피드백",
            "부동산 지수와 시차 (주식 대비 통상 2년 후행)",
        ],
    },
    "nison_candle_scoring": {
        "description": "Nison 캔들 가중치 점수 시스템 (Vol.1 §7.4)",
        "pattern_base": {
            "single_candle": 1,
            "two_candle": 2,
            "three_candle": 3,
        },
        "confirmations": {
            "volume_increase": 1,
            "support_resistance_match": 1,
            "regime_direction_match": 1,
        },
        "thresholds": {
            "strong_signal": ">= 4",
            "moderate": "2~3",
            "ignore": "< 2",
        },
    },
    "varity_brain_signal_system": {
        "description": "통합 매매 신호 시스템 (Vol.2 §9.2) — 카테고리 교차 검증",
        "STRONG_BUY": {
            "conditions": [
                "graham_margin_of_safety >= 0.33",
                "buffett_moat_score >= 8",
                "elder_triple_screen == BUY",
                "cape < 20",
                "ltcm_warnings == 0",
            ],
            "position_size": "최대 (Elder 2% 규칙 내)",
        },
        "BUY": {
            "conditions": [
                "graham_margin_of_safety >= 0.15",
                "elder_triple_screen == BUY",
                "ltcm_warnings <= 1",
            ],
            "position_size": "중간",
        },
        "HOLD": {
            "conditions": "진입 조건 부분 만족, 강도 부족",
            "action": "현 포지션 유지, 추가 진입 보류",
        },
        "SELL": {
            "conditions": [
                "price > intrinsic_value * 1.25",
                "OR elder_triple_screen == SELL",
                "OR ltcm_warnings >= 3",
            ],
            "action": "포지션 축소 또는 청산",
        },
        "STRONG_SELL": {
            "conditions": [
                "cape > 30",
                "ltcm_warnings >= 4",
                "elder_adx_collapse",
                "graham_margin_of_safety < 0",
            ],
            "action": "전량 청산 + 현금 또는 역방향 포지션",
        },
    },
    "core_knowledge_keywords": {
        "description": "Gemini 프롬프트 보강용 카테고리별 키워드 (Vol.1 §8.4)",
        "buckets": {
            "버블_탐지": ["CAPE", "신시대론", "군중심리", "거래량_이상", "내부자_매도"],
            "평균회귀": ["ADF검정", "허스트지수", "반감기", "볼린저밴드", "공적분"],
            "모멘텀": ["롤수익", "정보지연", "CANSLIM", "신고가돌파", "상대강도"],
            "심리분석": ["생존자편향", "경로의존성", "히스테리", "확증편향", "손실회피"],
            "리스크관리": ["켈리기준", "최대낙폭", "분할진입", "손절가", "포지션사이징"],
            "캔들패턴": ["아침별", "저녁별", "삼병정", "까마귀", "피봇포인트"],
            "타이밍": ["피봇포인트", "거래량확인", "추세전환", "최소저항선"],
        },
    },
    "trader_success_factors": {
        "description": "Sperandeo 38명 훈련 → 5명 성공 실험 (Vol.2 §3.5)",
        "weights": {
            "ability_to_admit_mistakes": 0.40,
            "emotional_discipline": 0.35,
            "risk_management": 0.20,
            "analytical_ability": 0.05,
        },
        "insight": "IQ와 성공 무관. 고IQ가 오히려 더 실패 경향. 핵심은 실수 인정·자아-포지션 분리",
    },
}


# ─────────────────────────────────────────────────────────
# 3. trigger_based_index — 파이프라인이 종목 조건에서 빠르게 책 후보 찾기
# ─────────────────────────────────────────────────────────

TRIGGER_INDEX = {
    "per_lte_15_pbr_lt_1_5": ["graham_intelligent_investor"],
    "eps_growth_qoq_gte_20": ["oneil_canslim"],
    "roe_gt_15": ["buffett_essays"],
    "moat_candidate": ["buffett_essays", "fisher_uncommon_profits"],
    "candle_signals_gte_2": ["nison_candlestick_psychology", "murphy_technical_analysis"],
    "drop_from_high_gt_30": ["nison_candlestick_psychology", "livermore_operator"],
    "per_gt_40": ["shiller_irrational_exuberance", "mackay_madness_crowds"],
    "pbr_gt_5_roe_lt_15": ["shiller_irrational_exuberance", "taleb_fooled_by_randomness"],
    "cape_gt_30": ["shiller_irrational_exuberance", "mackay_madness_crowds", "taleb_fooled_by_randomness"],
    "cape_lt_15": ["graham_intelligent_investor", "bogle_common_sense", "buffett_essays"],
    "leverage_gt_15": ["lowenstein_when_genius_failed"],
    "any_position": ["douglas_trading_in_zone", "elder_trading_for_living"],
    "fallback_universal": ["bogle_common_sense", "douglas_trading_in_zone"],
}


# ─────────────────────────────────────────────────────────
# 4. report_sources — 원본 리포트 출처 추적
# ─────────────────────────────────────────────────────────

REPORT_SOURCES = {
    "vol1_a36fd53d": {
        "title": "배리티 브레인 투자 바이블 Vol.1",
        "books": [
            "mackay_madness_crowds",
            "taleb_fooled_by_randomness",
            "shiller_irrational_exuberance",
            "chan_algorithmic_trading",
            "livermore_operator",
            "schwager_market_wizards",
            "nison_candlestick_psychology",
        ],
        "path_hint": "/Users/macbookpro/Desktop/a36fd53d.pdf (21p)",
        "date": "2026-04-13",
    },
    "vol2_a3901866": {
        "title": "배리티 브레인 학습 자료 Vol.2",
        "books": [
            "graham_intelligent_investor",
            "buffett_essays",
            "schwager_new_market_wizards",
            "douglas_trading_in_zone",
            "douglas_disciplined_trader",
            "lowenstein_when_genius_failed",
            "elder_new_trading_for_living",
            "elder_trading_for_living",
            "bogle_common_sense",
        ],
        "path_hint": "/Users/macbookpro/Desktop/a3901866.pdf (21p)",
        "date": "2026-04-13",
    },
}


def deep_merge(dst: dict, src: dict) -> dict:
    """dict 를 deep merge. src 가 dst 를 덮어씀, list 는 교체."""
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst


def build_v2(v1: dict) -> dict:
    out = dict(v1)
    out["version"] = "2.0"
    out["description"] = (
        "배리티 브레인 지식 베이스 v2 — 17권 리포트 기반 구조화. "
        "v1 키 유지(호환). frameworks·trigger_index·report_sources 신규 섹션."
    )
    out["processed_count"] = 17  # 나머지 13권은 웹서칭 정리 대기

    for cat, books in BOOK_ENRICH.items():
        if cat not in out:
            out[cat] = {}
        for book_id, enrich in books.items():
            existing = dict(out[cat].get(book_id, {}))
            deep_merge(existing, enrich)
            out[cat][book_id] = existing

    out["frameworks"] = FRAMEWORKS
    out["trigger_index"] = TRIGGER_INDEX
    out["report_sources"] = REPORT_SOURCES
    return out


def check_regression(v1: dict, v2: dict) -> None:
    """v1 모든 기존 필드가 v2 에 그대로 남아있는지 확인."""
    for cat in v1:
        if cat in ("version", "description", "created", "sources_count"):
            continue
        assert cat in v2, f"missing top-level category {cat!r}"
        if isinstance(v1[cat], dict):
            for book_id, v1_body in v1[cat].items():
                assert book_id in v2[cat], f"missing book {cat}.{book_id}"
                if isinstance(v1_body, dict):
                    for fld in v1_body:
                        assert fld in v2[cat][book_id], (
                            f"v1 field dropped: {cat}.{book_id}.{fld}"
                        )
    for sect in ("frameworks", "trigger_index", "report_sources"):
        assert sect in v2, f"missing new section {sect!r}"


def main() -> int:
    if not KB_PATH.exists():
        print(f"ERROR: {KB_PATH} not found", file=sys.stderr)
        return 1
    v1 = json.loads(KB_PATH.read_text(encoding="utf-8"))
    v2 = build_v2(v1)
    check_regression(v1, v2)

    if "--check" in sys.argv:
        print("✓ v2 check passed (v1 필드 보존 + 신규 섹션 존재)")
        return 0

    KB_PATH.write_text(
        json.dumps(v2, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    size = KB_PATH.stat().st_size
    print(f"✓ wrote {KB_PATH} ({size:,} bytes)")
    print(f"  version         : {v2['version']}")
    print(f"  processed_count : {v2['processed_count']}")
    print(f"  frameworks      : {len(v2['frameworks'])}")
    print(f"  trigger_index   : {len(v2['trigger_index'])}")
    print(f"  report_sources  : {len(v2['report_sources'])} vols")
    return 0


if __name__ == "__main__":
    sys.exit(main())
