# 학습 철학 × 자본 3-Tier Routing 매트릭스 v0

**작성**: 2026-05-09
**관련 메모리**: `project_capital_3tier_mode`, `project_brain_kb_learning`, `project_market_horizon` V2.3
**진입 게이트**: 5/17 ATR Phase 0 verdict 후 capital_3tier sprint 진입 시 SSOT

## 배경

`data/brain_knowledge_base.json` v2.1 = 29권 books + 23 frameworks 박힘. `verity_brain` v5 가 이 모두를 *평균/가중* 으로 단일 brain_score 계산 → 자기모순 발생 (예: Marks "거시 회피" vs market_horizon 거시 layer / Buffett 장기 보유 vs O'Neil 단기 모멘텀).

**해법**: tier 별 routing. 9개 → 3 tier × 코히런트 thesis 로 분배. 충돌이 *기능* 으로 바뀜.

## V0 Routing 매트릭스

### 보수 60% — Buffett·Graham value · 장기 보유 · 거시 회피

| 항목 | source |
|---|---|
| Graham Intelligent Investor | value_investing.graham_intelligent_investor |
| Buffett Essays | value_investing.buffett_essays |
| Bogle Common Sense (index) | value_investing.bogle_common_sense |
| Defensive screen | frameworks.graham_defensive_screen |
| Intelligent investor signals | frameworks.intelligent_investor_signals |
| Buffett management score | frameworks.buffett_management_score |
| Mackay 군중심리 회피 | risk_psychology.mackay_madness_crowds |
| Lefevre 투자 절제 (간접 인용) | risk_psychology.lefevre_reminiscences (방어용) |

**핵심 신호**: 안전마진·부채비율·ROE 5y·dividend·moat·earnings 일관성
**Marks 정신 정합**: Risk First (1번) + 일관성 (2번) + 거시 회피 (5번)
**보유 기간**: 3-12개월+
**평균 종목 수**: 5-8

### 중간 30% — Lynch GARP · Phil Fisher · balanced

| 항목 | source |
|---|---|
| Lynch One Up | value_investing.lynch_one_up |
| Fisher Uncommon Profits | value_investing.fisher_uncommon_profits |
| Antonacci Dual Momentum | trend_momentum.antonacci_dual_momentum |
| Lynch PEG filter | frameworks.lynch_peg_filter |
| Dual momentum rule | frameworks.dual_momentum_rule |
| Chan strategy selection | frameworks.chan_strategy_selection |
| Aronson statistical gate | frameworks.aronson_statistical_gate |
| Schwager Market Wizards (전략 mix) | risk_psychology.schwager_market_wizards |
| Schwager New Market Wizards | risk_psychology.schwager_new_market_wizards |

**핵심 신호**: PEG·earnings 일관성·moat·6-12M 모멘텀 (long-term)
**Marks 정신 정합**: 사이클 위치 *적정* 활용 (3번 시장 비효율)
**보유 기간**: 1-6개월
**평균 종목 수**: 4-6

### 위험 10% — CANSLIM 모멘텀 · 컨트레리언 · 단기

| 항목 | source |
|---|---|
| Livermore Operator | trend_momentum.livermore_operator |
| Covel Turtle Trader | trend_momentum.covel_turtle_trader |
| O'Neil CANSLIM | trend_momentum.oneil_canslim |
| Carter Mastering Trade | trend_momentum.carter_mastering_trade |
| Murphy Technical Analysis | technical_candle.murphy_technical_analysis |
| Nison Candlestick Psychology | technical_candle.nison_candlestick_psychology |
| Livermore probing | frameworks.livermore_probing |
| Turtle breakout system | frameworks.turtle_breakout_system |
| Sperandeo trend reversal | frameworks.sperandeo_trend_reversal |
| TTM squeeze | frameworks.ttm_squeeze |
| Trout position sizing | frameworks.trout_position_sizing |
| Nison candle scoring | frameworks.nison_candle_scoring |
| Murphy technical foundations | frameworks.murphy_technical_foundations |
| **Marks 신규 딜 품질 — starved** (V2.3) | market_horizon signals.new_listing_quality |

**핵심 신호**: breakout·sector rotation·VCP·candle pattern·52W high·MA cross·Marks starved (강세장 1단계)
**Marks 정신 정합**: 강세장 1단계 contrarian 매수 + 3단계 회피 (사이클 적극 활용)
**보유 기간**: 2주-2개월
**평균 종목 수**: 1-3

### Cross-tier (모든 tier 공통 input — 꼬리위험 / 체제 / 메타)

| 항목 | source | 적용 |
|---|---|---|
| Taleb Fooled by Randomness | risk_psychology.taleb_fooled_by_randomness | 모든 tier 의 risk awareness |
| Lewis Big Short | risk_psychology.lewis_big_short | tail event 모니터링 |
| Lowenstein When Genius Failed | risk_psychology.lowenstein_when_genius_failed | leverage / 과신 방어 |
| Douglas Trading in Zone | risk_psychology.douglas_trading_in_zone | 매매 심리 (모든 tier) |
| Douglas Disciplined Trader | risk_psychology.douglas_disciplined_trader | 동일 |
| Elder Trading for Living | risk_psychology.elder_trading_for_living | risk management 공통 |
| Malkiel Random Walk | quantitative.malkiel_random_walk | 효율 시장 가설 (humility) |
| Shiller Irrational Exuberance | quantitative.shiller_irrational_exuberance | CAPE → market_horizon 직접 입력 |
| Natenberg Options Volatility | quantitative.natenberg_options_volatility | VIX/PCR 해석 (메타) |
| LTCM warning signals | frameworks.ltcm_warning_signals | risk monitoring (cross) |
| Big short tail risk | frameworks.big_short_tail_risk | tail event detection |
| CAPE macro strategy | frameworks.cape_macro_strategy | market_horizon 코어 |
| VARITY brain signal system | frameworks.varity_brain_signal_system | 메타 (Brain v5) |
| Core knowledge keywords | frameworks.core_knowledge_keywords | 메타 |
| Trader success factors | frameworks.trader_success_factors | 메타 (전 tier) |
| Aronson statistical gate | frameworks.aronson_statistical_gate | 백테스트 검증 (cross) |
| Natenberg options model | frameworks.natenberg_options_model | sentiment 해석 |

**적용 방식**: 신호 자체는 모든 tier 의 brain score 에 합류. 다만 **tier 별 가중치 차별** — 보수 tier 는 tail risk 신호에 + 가중, 위험 tier 는 momentum quality 신호에 + 가중.

## 충돌 해소 매트릭스

| 충돌 | V0 (현재) | V1 (3-tier 후) |
|---|---|---|
| Marks 거시 회피 vs market_horizon 거시 활용 | 평균 가중 | 보수=거시 비중조절만 / 위험=거시 적극 / 중간=절충 |
| Buffett 장기 vs O'Neil 단기 | 평균 가중 | 보수=Buffett 룰 / 위험=O'Neil 룰 (각 tier 자기 룰만) |
| Lynch GARP vs CANSLIM 모멘텀 | 평균 가중 | 중간=Lynch / 위험=CANSLIM |
| Taleb 꼬리위험 vs 단기 모멘텀 | Brain v5 가 weight 7:3 | 모든 tier risk gate (cross-tier) — 위험 tier 도 손절 강제 |

## 미박 / 큐잉 항목

- **Marks 9 정신** — 1순위 (신규 딜 품질) 만 V2.3 박힘. 나머지 8개 (humility, 비대칭, 진자 등) → 정신적 룰이라 코드 안 됨, docs/HOWARD_MARKS_NOTES.md 보관 검토 X (오늘 사용자 "코드 이식 X" 결정)
- **추가 도서 후보** (40 도달 위해) — Klarman Margin of Safety, Marks Most Important Thing, Pabrai Dhandho, Bridgewater Principles 등. 이식 시 본 매트릭스 v1 갱신
- **routing 적용 코드** — 5/17 capital_3tier sprint 진입 시 verity_brain v5 → v6 (tier 별 sub-score) 마이그레이션. brain_score 단일 → {conservative_score, balanced_score, aggressive_score} 3-trail.

## 다음 단계 (5/17 sprint 박을 때)

### Backend (괴물)

1. `verity_brain.py` v6 — tier 별 sub-score 계산 함수 분리 (compute_brain_score_conservative / _balanced / _aggressive)
2. 신호별 tier weight 매트릭스 박음 (`data/brain_tier_weights.json` SSOT)
3. portfolio.recommendations[].verity_brain 에 3-trail score 박음 (현재 단일 brain_score → 3 sub-score 추가)
4. 백테스트 tier 별 IC + Sharpe 분리 → 어느 철학이 어느 시장 환경에서 통하는지 명확화
5. AdminDashboard tier 별 브레인 스코어 카드

### Frontend (심플 — `feedback_simple_front_monster_back` 정합)

**원칙**: 3 모드 UI 만들지 않음. 27 컴포넌트가 81개로 안 부풀어야 함. 단일 UI + tier-aware 컴포넌트 + focus 토글 1개.

대부분 컴포넌트 tier 무관 그대로 유지 (StockHeatMap·MarketHorizon·BlackSwan·뉴스·신호 — 모든 tier 공통 input). 영향 받는 컴포넌트 3 + 신규 1:

1. **Recommendations** — 픽마다 tier 뱃지 (`보수`/`중간`/`위험`) 표시. `mode_tag` 필드로 색·라벨만 분기.
2. **VAMS holdings** — `mode_tag` 그룹화 / 정렬. 3tier 메모리에 이미 schema 박힘.
3. **Brain score 표시** — 단일 점수 → 3-trail (`conservative_score / balanced_score / aggressive_score`). StockDashboard sub-component 변경.
4. **Focus 토글 (신규)** — 상단 nav에 "현재 보는 tier" 토글 (전체/보수/중간/위험). 선택 시 다른 tier 컴포넌트 opacity 0.4 흐림 처리. 심리적 규율 ("10% 빠졌다고 보수 tier 매도 충동" 방지) 용. 페이지 카피 X, CSS 1 layer.

**복붙 대상 (5/17 sprint)**: framer-components/pages/_shared/RecommendationCard.tsx, VAMSProfilePanel.tsx, StockDashboard.tsx, **신규** FocusToggle.tsx
