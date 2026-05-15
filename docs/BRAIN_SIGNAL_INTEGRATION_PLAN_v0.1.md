# BRAIN SIGNAL INTEGRATION PLAN v0.1

작성: 2026-05-15 (사용자 발견 — "사이트 연동하는 모든 정보가 Brain 고려요소")
적용 게이트: Phase A 즉시 / Phase B 5/17 ATR verdict 후 / Phase C 8/17 PRODUCTION 게이트 후

---

## 배경

전수 audit 결과 (`api/intelligence/verity_brain.py` 51개 잠재 시그널 중):
- **19 시그널 (37%)** = Brain 결정에 반영 (가중치/게이트/Cohen check)
- **32 시그널 (63%)** = 데이터 수집되지만 Brain 반영 **0%**

사용자 정의: "내가 사이트에 연동하는 모든 정보 = Brain 종목 선정 고려요소". 현 상태 격차 63%.

연관 메모리:
- `feedback_brain_synthesizer_role` — Brain = 종합 판단자, 보조 신호와 동급 비교 X
- `project_brain_score_funnel_audit` — BUY 0건 / brain_score max 50점 = 입력 다양성 부족이 원인 후보
- `project_market_horizon` — V2.1 박혀있는데 Brain 미연결 (가장 큰 단일 결함)

---

## 1. 미반영 32 시그널 전수표

### 1-A. 매크로 미반영 (15)

| 시그널 | 경로 | 의미 | 예상 영향도 |
|---|---|---|---|
| **usd_krw** | `macro.usd_krw` | 원/달러 환율 | ★★★★★ KR 수출주 fact 핵심 |
| usd_jpy | `macro.usd_jpy` | 엔/달러 | ★★ 한일 무역·BOJ 정책 |
| eur_usd | `macro.eur_usd` | 유로/달러 | ★ |
| **wti_oil** | `macro.wti_oil` | WTI 원유 | ★★★★ 정유·화학·항공·운송 |
| **gold** | `macro.gold` | 금 | ★★★★ flight to safety |
| silver | `macro.silver` | 은 | ★★ |
| copper | `macro.copper` | 구리 (Dr. Copper) | ★★★ 글로벌 경기 선행 |
| us_2y | `macro.us_2y` | 미 2년 국채 | ★★★ 단기 금리 절대 레벨 |
| **nasdaq** | `macro.nasdaq` | 나스닥 | ★★★ 미장 동조화 |
| dji | `macro.dji` | 다우 | ★ |
| nikkei | `macro.nikkei` | 니케이 | ★★ 한일 동조 |
| sse | `macro.sse` | 상해종합 | ★★★ 한중 동조·중국 모멘텀 |
| dax | `macro.dax` | 독일 DAX | ★ |
| **hy_spread** | `macro.hy_spread` | High Yield spread | ★★★★★ 신용 위기 1차 신호 |
| breakeven_inflation_10y | `macro.breakeven_inflation_10y` | 10년 기대 인플레 | ★★★ 금리 + 인플레 압력 |
| **fed_balance_sheet** | `macro.fed_balance_sheet` | Fed B/S | ★★★ QE/QT |
| capital_flow | `macro.capital_flow` | 자본 흐름 | ★★ |
| micro_signals | `macro.micro_signals` | 마이크로 시그널 묶음 | ★★ |
| cross_asset_corr | `macro.cross_asset_corr` | 자산 상관도 | ★★ regime 진단 |

### 1-B. 포트폴리오 미반영 (16)

| 시그널 | 경로 | 의미 | 예상 영향도 |
|---|---|---|---|
| **market_horizon** | `portfolio.market_horizon` | V2.1 CAPE+11signal+8analog | ★★★★★ 통째로 wire 안 됨 |
| **value_hunt** | `portfolio.value_hunt` | 자체 저평가 발굴 모듈 | ★★★★★ 별 분석 — Fact 미통합 |
| **geopolitical_hotspots** | `portfolio.geopolitical_hotspots` | 지정학 위기 | ★★★★ 매크로 override 후보 |
| **global_events** | `portfolio.global_events` | 글로벌 이벤트 캘린더 | ★★★★ 단기 변동성 |
| **bloomberg_google_headlines** | `portfolio.bloomberg_google_headlines` | 매크로 헤드라인 | ★★★★ 매크로 sentiment |
| **us_headlines / headlines** | `portfolio.us_headlines / headlines` | KR/US 시장 헤드라인 | ★★★ 매크로 sentiment |
| **lynch_kr_distribution** | `portfolio.lynch_kr_distribution` | Lynch KR 분포 | ★★★ Fact Lynch sub 보강 |
| **sector_rotation / sector_trends** | `portfolio.sector_rotation` | 섹터 흐름 | ★★★ Brain 섹터 가중 |
| stat_arb | `portfolio.stat_arb` | 통계 차익 | ★★★ |
| alt_data | `portfolio.alt_data` | 얼터너티브 데이터 | ★★ |
| bond_analysis | `portfolio.bond_analysis` | 채권 분석 | ★★ |
| commodity_impact | `portfolio.commodity_impact` | 원자재 영향 | ★★ (현재 empty) |
| kis_overseas_market | `portfolio.kis_overseas_market` | KIS 해외 시장 | ★ |
| krx_openapi | `portfolio.krx_openapi` | KRX 공식 API | ★★ |

---

## 2. Phase A — 즉시 박힘 (2026-05-15 commit)

**매크로 override 게이트 4개 신설** (`api/intelligence/verity_brain.py:detect_macro_override`)

| 게이트 | 조건 | mode | max_grade | 임계값 출처 |
|---|---|---|---|---|
| FX shock | `\|usd_krw.change_pct\| ≥ 1.5%` | fx_shock | WATCH | KR 환변동성 ±0.5% 평균 (BOK 보고서) → 3σ |
| Oil shock | `\|wti.change_pct\| ≥ 5%` | oil_shock | WATCH | EIA 평균 ±2% 일변동 → 정치/공급 충격 |
| Credit stress | `hy_spread ≥ 4.5%p` (severe ≥ 6%p) | credit_stress / credit_stress_severe | WATCH / AVOID | FRED BAMLH0A0HYM2 평균 4-5%, 6%+ = 2008/2020 패턴 |
| Flight to safety | `gold.change_pct ≥ +3%` | flight_to_safety | BUY | 일변동 통상 ±1% → 3% = 패닉/지정학 |

**검증**:
- 임계값은 합리적 기본값 — 65 거래일 운영 (8/17~11/15) 후 fine-tune 큐
- Perplexity fact-check 후속 큐잉 (각 임계값 학계/실무 출처 명시화)

---

## 3. Phase B — 5/17 ATR verdict 후 sprint (Sentiment 8 sub-component 확장)

목표: `_compute_sentiment_score` 7 component → **13 component** 로 확장.

### 3-A. 신규 sentiment sub-component 6개

| sub-component | source | 변환식 | 가중치 (조정) |
|---|---|---|---|
| `fx_sentiment` | `macro.usd_krw.change_pct` | 변동률 → 50±점수 | 5% |
| `commodity_sentiment` | wti/gold/copper composite | 종합 → 점수 | 5% |
| `global_index_decoupling` | nasdaq vs kospi 5d corr | 1 - corr → 점수 | 4% |
| `geopolitical_score` | `geopolitical_hotspots` severity 합산 | 점수 | 3% |
| `macro_headlines` | bloomberg + KR/US 헤드라인 NLP | 점수 | 3% |
| `market_horizon_link` | `market_horizon.verdict` mapping | euphoria→낮음 / panic→높음 (역설) | 5% |

기존 7 sub-component 가중치 조정 (합 100% 유지):
```
news_sentiment    25% → 20%
x_sentiment       18% → 15%
market_mood       18% → 15%
consensus_opinion 12% → 10%
crypto_macro       8% →  8%
market_fear_greed 10% →  8%
social_sentiment   9% →  7%
[신규 6개]              25%
```

### 3-B. 신규 매크로 override 게이트 5개

| 게이트 | 조건 | mode | max_grade |
|---|---|---|---|
| copper crash | `copper.change_pct ≤ -5%` | dr_copper_recession | WATCH |
| global decoupling | `nasdaq.change_pct - kospi.change_pct ≤ -3%` | kr_decoupling | BUY |
| Fed BS 급변 | `fed_balance_sheet 7d ±3%` | fed_qt_shock | WATCH |
| US 2Y 급등 | `us_2y.change_pct ≥ +0.3%p` (일) | rate_shock | WATCH |
| Inflation breakeven | `breakeven_10y > 3.0%` | inflation_breakeven | WATCH |

### 3-C. market_horizon 통합

`market_horizon.verdict` (euphoria/normal/correction/panic) 을:
1. `_detect_bubble_signals` 의 group E 로 추가 (severity +1~2)
2. `detect_macro_override` 의 cycle_stage 게이트로 추가 (panic/correction 시 cap)
3. Sentiment 의 `market_horizon_link` 로 wire (점수)

---

## 4. Phase C — 8/17 PRODUCTION 게이트 통과 후 (Fact Score 확장)

### 4-A. value_hunt 통합

`portfolio.value_hunt.value_candidates` 를 종목별 `multi_factor` 와 합산:
- 종목이 value_hunt 후보면 fact_score +5~10점
- gate_reason 통과 종목은 추가 보너스

### 4-B. lynch_kr_distribution 통합

`portfolio.lynch_kr_distribution` 의 KR 시장 Lynch 분위수 기준으로:
- 현 종목의 Lynch score 가 KR 분포 상위 X% 인지 판정
- `_compute_lynch_kr_score` 에 분포-상대치 보너스

### 4-C. sector_rotation / sector_trends fact 가중

`portfolio.sector_rotation` 에서 종목의 sector 가 favored / unfavored 면:
- favored 종목 fact_score +3
- unfavored 종목 fact_score -3
- `sector_rotation_check` (이미 매크로 override 에 wire) 와 별개 — fact 레벨 가중

---

## 5. 검증 트랙

각 Phase 완료 시:
1. **A/B test**: 변경 전/후 종목 등급 분포 비교 (BUY/STRONG_BUY 분포 변화)
2. **65 거래일 PRODUCTION 게이트**: 8/17~11/15 누적 결과로 excess_accuracy 변화 측정
3. **`brain_learning.jsonl` 14d/30d hit rate trend**: Phase 적용 전후 비교
4. **메타 분석 source 다양성**: findings_aux 의 5→11 항목 확장 후 IC ranking

성공 기준:
- Phase A: 매크로 위기 시 적절히 WATCH/AVOID 캡 발동 (false positive < 10%)
- Phase B: sentiment_score 평균 분산 증가 (현 표준편차 < 5점 → 8점+ 목표)
- Phase C: STRONG_BUY 등급 비율 0% → 5%+ (memory `project_brain_score_funnel_audit` 결함 해소)

---

## 6. 비반영 결정 (의도된 미통합)

다음 시그널은 Brain 통합 보류:
- **alerts** = 알림 시스템 — Brain 결정 input 아님
- **kis_overseas_market** = US 시장 raw — 이미 macro.sp500/nasdaq 으로 대체
- **commodity_impact** = 현재 empty — 데이터 채워지면 Phase B 검토
- **ai_leaderboard / cross_verification / claude_*** = 메타-검증 layer — Brain 보조 아니라 감시자
- **trade_plan_evolution_signals** = 운영 시그널 — Brain 종목 선정과 직교

---

## 7. 메모리 정합

- 임계값 출처 단일 명시 (feedback_source_attribution_discipline)
- 변경 후 brain_evolution_log 자동 commit (feedback_brain_evolution_admin_sync)
- 가중치 변경은 백테스트 통과 필수 (feedback_continuous_evolution)
- Phase B/C 전 staged_updates 강제 (project_phase_0_staged_framework)

---

## 8. 후속 박힘 예정 (v0.2 트리거)

- 65 거래일 운영 데이터 누적 후 임계값 fine-tune 결과 반영
- Brain v6 (`project_brain_v5_self_attribution` 후속) 가중치 재배분
- meta_findings_aux 가 13 항목으로 확장된 후 IC ranking 재산정
- ESTATE Brain 의 매크로 통합 패턴과 정합 (memory `project_estate_tier3_macro_bridge`)
