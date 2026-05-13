# 거래 비용 모델 — 구현 명세서 (보류 상태, 2026-04-28)

**상태**: 명세 작성 완료 / 구현 보류
**작성**: 2026-04-28
**선결 조건**: Phase A 룰 이식 운영 검증 + Lynch 분류 분포 안정화 후 착수
**예상 스프린트**: 2주 (Week 1 코어 + Week 2 UI / 회귀)

## 검수 결과 요약 (2026-04-28)

VERITY VAMS 가 이 명세의 **약 80% 를 이미 구현 중**:
- ✅ KR/US 매도 세율 분기 (`VAMS_SELL_TAX_KR_STOCK / KR_ETF / US_STOCK / US_ETF`)
- ✅ 위탁수수료 (`VAMS_COMMISSION_RATE`)
- ✅ Almgren-Chriss 제곱근 슬리피지 (`api/vams/engine.py::_estimate_slippage`)
- ✅ 배당세 (`VAMS_DIVIDEND_TAX_RATE`)
- ✅ ValidationPanel.tsx 의 cost breakdown UI (gross vs net 분리)

**진짜 미구현 (실제 작업 4건)**:
1. 시간대 가중치 (장 시작/마감 1.5~2배)
2. alpha-to-cost gate (매수 신호 사전 비용 비교)
3. 거래 회전율 (turnover) 측정 + 200%+ 경고
4. 환전 비용 (KIS 0.5~1% 단방향) — US 종목

따라서 본 명세의 "처음부터 구축" 가정은 부정확. **2주 스프린트 → 4~5일 보강** 으로 단축 가능.

## 명세서 본문 — Perplexity 협업 결과 보존

(이하는 사용자가 Perplexity 와 협업해 작성한 원본 명세서. 구현 시점에 본 검수 결과와 합쳐 4~5일 스프린트로 진행)

### 1. 모듈 구조

```
api/quant/
├── cost_model.py          # NEW: 비용 산출 코어
├── liquidity_cache.py     # NEW: 종목별 ADV/spread 캐시
└── factors/

api/vams/
├── engine.py              # MOD: cost_model 통합 (이미 80% 구현)
├── execution.py           # NEW: 실효 체결가 계산
└── alpha_gate.py          # NEW: alpha-to-cost 게이트
```

### 2. 핵심 로직

**3-tier participation rate 슬리피지** (Almgren-Chriss 단순화):
- < 0.5% ADV: 0.5 × spread
- 0.5~2%: 1.0 × spread + 5bps
- 2~5%: 1.5 × spread + 15bps
- > 5%: 거래 거부

**시간대 가중치**:
- 장 시작 30분: 1.8×
- 장 마감 30분: 1.5×
- 점심 (KR 11:30~13:00): 1.3×
- 그 외: 1.0×

**alpha-to-cost gate**:
- expected_alpha = brain_implied_return × confidence
- threshold: alpha ≥ round_trip_cost × 2.0
- 근거: Grinold·Kahn *Active Portfolio Management* 2판 16장

### 3. 한국 시장 비용 표 (2026-04 기준)

| 항목 | KOSPI | KOSDAQ | KR ETF | US |
|---|---|---|---|---|
| 위탁수수료 | 0.015% | 0.015% | 0.015% | $0 (Robinhood) |
| 유관기관 | 0.0036% | 0.0036% | 0.0036% | — |
| 매도 거래세 | 0.18% | 0.18% | 면제 | SEC 0.0028% |
| 환전 (KR→US) | — | — | — | 50bps 단방향 |

### 4. 하이브리드 30일 병기 (UI)

VAMSProfilePanel 듀얼 카드:
- 신규 비용 반영 수익률 (정확)
- 기존 표시 (비용 미반영, 참고용) — Day 0~30
- Day 31+: 신규만 유지, legacy 는 archive

공지 카피: "성능 저하가 아니라 현실 반영"

### 5. 위험 요소

- 위험 1: STRONG_BUY net 수익률이 BUY 와 비슷하면 → 보유기간 늘림 / 임계 강화
- 위험 2: 단기 모멘텀 (1~3일 보유) 모두 차단 → 가짜 알파였을 가능성, 차단 정상
- 위험 3: 사용자 일부 "수익률 낮아짐" 이탈 → 정직성이 장기 신뢰

## 착수 결정 시 검증 질문 (Perplexity)

1. 한국 거래세 0.18% 의 향후 변경 로드맵 (2025 0.20% → 2027 0.15% 등)?
2. Almgren-Chriss α 한국 시장 실증 추정값 (학술/운용사 보고서)?
3. alpha-to-cost ratio 2.0× 임계의 학술 표준 (Grinold·Kahn 외 다른 권장값)?

## 다음 액션 (구현 착수 시)

1. 본 명세 + 검수 결과 합치기 (이미 80% 구현 인지)
2. 4~5일 스프린트 (2주 → 단축):
   - Day 1: 시간대 가중치 추가
   - Day 2: 회전율 측정 + AdminDashboard 경고
   - Day 3: alpha-to-cost gate
   - Day 4: 환전 비용 (US)
   - Day 5: 30일 spread 캐시 + 백테스트 재실행

---

**현재 보류 사유**: Phase A 룰 이식 (regime_weight / PEG / Hard Floor / Lynch 분류) 의 운영 영향이 먼저 검증되어야 함. 거래 비용 모델까지 동시 변경 시 충격 누적 + 원인 분리 어려움.

---

# Part II — After-Tax Alpha & Replacement Hurdle (2026-05-12 추가)

근거: `터미널 보충 학습 자료. /터미널 학습 자료 4.pdf` (Perplexity tax-aware portfolio construction)
연관: `UNIVERSE_FUNNEL_REFORM_PLAN_v0.2.md §7` (세후 alpha hurdle layer)
영문 표준 산식 + 한국 거주자 (Tier 1, 비대주주) 로컬화.

## 1. Tax Alpha 정의

Natixis / Neuberger Berman 표준:

\[\text{Tax Alpha} = \alpha_{\text{after-tax}} - \alpha_{\text{pre-tax}}\]

분해:
\[\text{Tax Alpha} = \text{TLH 혜택} + \text{차익 이연 (deferral)} + \text{능동 운용 alpha}\]

AQR (2023) 핵심 발견: **세후 alpha 의 주된 원천은 TLH 가 아닌 *gain deferral*** — 미실현 이익 보유의 복리 효과. ← `project_multi_bagger_watch` 결정 22 ("꽃 뽑지 마라") 와 정합. 정성 원칙이 *세후 alpha 측면* 으로도 정당화됨.

## 2. 기본 세후 보유기간 수익률

CFA Level III 표준 (analystprep):

\[r_{\text{AT}} = r_{\text{PT}} \times (1 - t_{\text{eff}})\]

## 3. 실효 세율 (Effective Tax Rate)

표준 형식 (warakirri):

\[t_{\text{eff}} = w_{\text{ST}} \cdot t_{\text{ST}} + w_{\text{LT}} \cdot t_{\text{LT}}\]

여기서 \(w_{\text{ST}}, w_{\text{LT}}\) = 연간 회전율에서 ST/LT 매도 비율.

### 한국 거주자 (Tier 1, 대주주 50억 미만) 로컬화

미국 거주자의 ST 40.8% / LT 23.8% 와 다름:

| 시장 | 보유기간 | 세율 | 추가 |
|---|---|---|---|
| KR (보통주, 비대주주) | 무관 | **0%** | 비과세 |
| KR ETF | 무관 | 15.4% | 배당소득세 분류 |
| US (해외주식) | 무관 | **22%** | 250만 공제 후, 단일세율 (학습자료 2) |

→ **Tier 1 VERITY 의 t_eff 산정**:

\[t_{\text{eff, KR stock}} = 0\%\]
\[t_{\text{eff, US stock}} = 22\% \times \frac{\max(0, \text{gain} - 2.5\text{M})}{\text{gain}}\]

연 미실현 이익이 250만 초과할 때부터 22% 적용. 250만 미만이면 0%.

연 수익 산정 시 (예: 종목당 평균 50만 수익 × 5종목 청산 = 250만): 공제 안 넘으므로 t_eff = 0. 6종목 청산 (300만 수익): t_eff = 22% × 50/300 = 3.67%. **공제는 portfolio 전체에 1회 적용**, 종목 단위 X.

## 4. Post-Liquidation Return (미실현 이익 포함)

진정한 세후 수익률 (analystprep):

\[r_{\text{AT,liq}} = r_{\text{AT}} - \frac{G_{\text{embedded}} \times t_{\text{LT}}}{V_{\text{portfolio}}}\]

\(G_{\text{embedded}}\): 포지션 내재 미실현 이익.

**진입 hurdle 의 세후 환산**: 신규 종목 기대수익이 기존 포지션의 *세후 청산 비용* 을 상회해야 교체 정당화. Tier 1 KR-only 인 경우 청산 세금 0 → 청산 비용 = 거래비용만. US 포지션 정리 시 청산 세금 발생 → hurdle 상승.

## 5. 표준 세후 교체 Hurdle (intelliflo)

\[\alpha_{\text{new, PT}} > \alpha_{\text{existing, PT}} + \frac{t_{\text{ST}} G_{\text{ST}} + t_{\text{LT}} G_{\text{LT}}}{V_{\text{portfolio}}} \div T_{\text{horizon}}\]

\(T_{\text{horizon}}\) 단기일수록 hurdle 상승. KR 비과세라 \(t_{\text{ST}} = t_{\text{LT}} = 0\) → 추가 hurdle = 0 (거래비용만). US 는 22% 곱해진 항이 살아남음.

## 6. AQR 실증 — 비선형 세후 전환 효율

| 세전 alpha | 세후 alpha (US 거주자) | 전환률 |
|---|---|---|
| +2% | +1.7~1.9% | 85~95% |
| +5% | +4.3~4.6% | 86~92% |

**상위 alpha 일수록 세후 전환률 ↑** — 비선형. 한국 거주자 적용 시 KR 영역은 100% (비과세) 라 비선형 효과 발생 안 함, US 영역만 적용.

## 7. Tax-Efficiency Ratio (TER)

\[\text{TER} = \frac{r_{\text{AT}}}{r_{\text{PT}}}\]

업계 베이스라인:
- 패시브 인덱스: 0.85~0.95
- 고회전 액티브: 0.55~0.70

### VERITY Tier 1 (KR 6 + US 2) 예상 TER

\[\text{TER}_{\text{Tier 1}} \approx 0.75 \times 1.0 + 0.25 \times 0.78 = 0.945\]

(KR 75% 가중 비과세 × US 25% 가중 t_eff≈22% 가정)

→ **패시브 인덱스 상단 수준의 세금 효율**. KR-bias 구조의 정량적 정당화.

## 8. Realized vs Unrealized 처리 원칙

| 항목 | 처리 | 세후 효과 |
|---|---|---|
| Realized 단기 손실 | 즉시 세금 상쇄 → 재투자 | 즉각 tax alpha (한국은 같은 해 손익통산만, 이월공제 X) |
| Realized 장기 이익 | KR=0% / US=22% 발생 | Alpha 마찰 직접 |
| **Unrealized 이익 보유** | 이연 → 복리 | **최강 세후 alpha 원천 (AQR 2023)** |
| Unrealized 손실 | 조기 실현 (단, 한국 wash-sale 없음 — US 거주자만 적용) | 같은 해 이익과 통산 |

## 9. Greenblatt Magic Formula Tax-Aware 변형

Joel Greenblatt *The Little Book That Beats the Market* 공식 룰 (Korean resident 적용은 *US 종목 한정*):

| 상황 | 표준 처리 | 한국 거주자 변형 |
|---|---|---|
| 이익 종목 | 리밸런싱 기준일 *1-2일 후* 매도 → LTCG (1년+1일) | **US 종목만 적용**. 한국 보통주는 보유기간 무관 |
| 손실 종목 | 기준일 *1-2일 전* 매도 → ST 손실 → 같은 해 ST 이익 상쇄 | US 종목: 같은 해 이익과 손익통산. KR 은 비과세라 N/A |
| 신규 매수 | 12개월 분산 (월 2-3종목) → 보유기간 분산 | **그대로 적용 가능** (Tier 1, 8 종목 정합) |

→ 5/17 sprint 진입 시 `api/portfolio/conviction_selector.py` 의 *진입 timing* 룰 에 통합.

## 10. Wash-Sale Rule 적용 여부

- **미국 거주자**: 30일 대체 유사자산 보유 의무
- **한국 거주자**: wash-sale 규정 *없음* (한국 세법). US 종목 거래 시에도 *한국 거주자 신고* 에 적용 X.
- **함의**: TLH 운영 자유도 ↑. 한국 거주자는 같은 해 손익통산 + 30일 룰 부담 0.
- 단, US broker (예: Interactive Brokers) 보고에는 wash-sale 표시 가능 (미국 IRS form). 한국 신고에는 무관.

## 11. Tax-Aware Long/Short Beta-One (2026 트렌드, 큐잉)

AQR / Quantinno 주도, 2026 급성장. 세전 alpha 클수록 TLH 비선형 효과.

**VERITY 적용 가능성**:
- Tier 1: Long-only 라 N/A
- Tier 3+ (10억+): 검토 가능. 단 한국 거주자는 US 공매도 접근성·세제 복잡 — 별 sprint 필요.

큐잉만, 박지 않음.

## 12. 구현 액션 (5/17 sprint 진입 시점)

```
api/quant/cost_model.py (확장)
  + after_tax_return(r_pt, market, holding_pd, position_value, ytd_deduction_remaining)
  + post_liquidation_return(r_at, embedded_gain, t_lt)
  + replacement_hurdle(new_pos, existing_pos, t_horizon)
  + tax_efficiency_ratio(portfolio)

api/portfolio/conviction_selector.py
  → score 산출 후 after-tax 변환 layer
  → US 진입 hurdle: KR ≥ 75 와 *세후 동일 비교* (단순 +5%p 대신 정밀 산식)
  → Greenblatt 12개월 분산 매수 enforce

api/vams/engine.py
  → 청산 시 post-liquidation 비용 표시
  → 250만 공제 portfolio level 추적
  → 같은 해 손익통산 자동 매칭
```

## 13. v0.2 Plan §7 와 정합

`UNIVERSE_FUNNEL_REFORM_PLAN_v0.2.md §7` 의 단순 +5%p 허들 → 본 문서 §5 정밀 산식으로 *대체*. v0.3 박는 시점에 둘 다 통합 예정 (베타 테스트 구역 추가 Perplexity 답변 도착 후 한 번에).
