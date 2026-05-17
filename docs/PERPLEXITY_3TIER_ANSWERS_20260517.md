# Perplexity Sonar Pro Answers — VAMS 3-Tier 모드 검증

**Query source**: `docs/PERPLEXITY_3TIER_BATCH_v0.md` (v1, 10 query batch)
**호출일**: 2026-05-17
**Perplexity 모드**: Sonar Pro / Deep Research
**비용**: ~$0.20-0.40 추정

---

## Critical 요약 (PM 결정 trigger)

Perplexity 답의 가장 중요한 5 conclusion:

1. **시드 1000만 원에서 3-Tier 비효율** — 공격 Tier 100만 원 / 종목당 20만 원 = 수수료+슬리피지가 알파 잠식. **단일 Tier 80% 또는 80/15/5 권장**, 1억 진입 후 60/30/10 점진 이동
2. **시그널 미검증(38일) 상태 3-Tier 도입 = curve-fit 위험 3배 증폭** — 단일 Tier 운영 + Brain v5 OOS N≥100 거래 검증 후 점진 (Phase 1 → 2 → 3)
3. **공격 Tier 해외 비중 0% 권장** — 한국 1년 미만 33% 세금 함정. 공격 Tier = 국내 비과세 100% 활용
4. **Tier 간 심리 오염 = LTCM 패턴** — 1인 PM 은 Tier 분리 심리 장치 없음. **공격 Tier 별도 계좌 물리 분리** 권장
5. **Q10 critical flaw 5건** = 현 설계 회귀 anchor. 그대로 진입 시 1년 후 후회 risk

→ **사용자 PM 결정**: [[project_capital_3tier_mode]] 의 "5/17 후 진입" anchor 재검토 필요.

---

## Q1 — 자본 분배 비율 (60/30/10) 학계 권위

### 7 Frameworks 비율 비교표

| Framework | 출처 | 보수 % | 중간 % | 공격 % | 핵심 산식 |
|-----------|------|--------|--------|--------|----------|
| Yale Endowment | Swensen 2009 *Pioneering Portfolio Management* | ~55% (채권+절대수익) | ~25% (글로벌주식) | ~20% (PE+VC) | 개인 simple: 채30+REIT20=50보수 / 미주30=중간 / 해외20=공격 |
| Markowitz MVO | Markowitz 1952 *JoF* "Portfolio Selection" | 효율선 좌 60% | 중간점 30% | 우 10% | `σ_port 증분/σ_공격` ≤ 한계효용 |
| Fractional Kelly | Kelly 1956 + Thorp 1962 | N/A (sizing 공식) | N/A | **¼ Kelly** = full kelly의 25% | `f* = (bp-q)/b`; 1인 PM = ¼ Kelly → 단일 포지션 max 5~8% |
| Risk Parity | Dalio 1996 + Qian 2005 | ~40% (저변동 + 레버) | ~35% | ~25% | risk contribution = 1/3 균등; 저변동 Tier 레버리지 |
| All-Weather 4Q | Dalio *Principles* 2017 | 55% (채권+명목채) | 30% (주식) | 15% (금+원자재) | 4분면→3Tier: 성장↑=공격 / 성장↓=보수 / 인플레↑=중간 |
| Permanent Portfolio | Harry Browne 1981 | 50% (현금+장기채) | 25% (주식) | 25% (금) | 25×4 → 3Tier 재매핑 |
| Coffeehouse/Lazy | Bogle / Bernstein 2002 *Four Pillars* | 40% (채권+MMF) | 40% (광역지수) | 20% (섹터/스몰캡) | 단순성 극대화, 리밸런스 연 1회 |

### 한국 1인 PM (1000만~1억) 권고

**70/20/10** — 단, VAMS 시뮬 단계에서는 **80/15/5** 운영 후 신호 검증 누적 시 60/30/10 점진 이동.

이유:
- 시드 1000만 → 공격 100만 → 종목당 20만 = 단주 매매 비효율
- Brain v5 38일 시그널 = N<30 신호 → 통계 불충분, Kelly 원리상 공격 사이즈 축소
- 전역 전 = 시뮬 검증 + 리스크 근육 강화 기간, 보수 70% 심리 안전망

### 비율별 최적/위험 조건표

| 비율 | 최적 조건 | 위험 조건 |
|------|----------|----------|
| 40/40/20 | 시드 5억+, 트랙레코드 3년+, 상승 레짐 | 1인 PM 베타, 하락장 |
| 50/30/20 | 검증된 시그널, 시드 1억+, 경험 2년+ | 공격 20% Kelly 위반 |
| **60/30/10** | VERITY 목표 (검증 완료 정상 운영) | 시드<5000만, 시그널 N<100 |
| **70/20/10** | 전역 전 시뮬→실거래 초기 (권장) | 강세장 진입 시 기회비용 |
| **80/15/5** | 베타 38일차 현재, MDD 테스트 | 자본 성장 속도 ↓ |

### ⚠ 반증

60/30/10 자살행위 case:
- 2008/2022 레짐 전환: 공격 Tier -50% → 전체 -5% 단독이지만, 공격 심리 붕괴 → 중간/보수 강제 청산
- 시드 <500만: 공격 50만 = 수수료+슬리피지가 알파 잠식
- 베타 38일 PM 경력: 데이터 부족 → 공격 신호 curve-fit 가능성 50%+
- 심리 비대칭: 공격 -30% 목격 → 보수 매도 충동 → 전체 시스템 붕괴

---

## Q2 — Tier 별 룰 차별 18-Cell 표

| 항목 | 보수 (60%) | 중간 (30%) | 공격 (10%) |
|------|-----------|-----------|-----------|
| **(a) 포지션 max %** | **5%** | **10%** | **20%** |
| Kelly 근거 | ¼ Kelly × 안전버퍼 = ~5%, 종목 20개 분산 | ½ Kelly = ~10%, 종목 10개 | Full Kelly 보정 ~20%, 종목 5개 |
| 🇰🇷 조정 | KOSDAQ 소형주: 일평균 거래량 1% 이하 cap 추가 | KOSPI 대형주 5% 완화 가능 | KOSDAQ 거래량 하위 20% 제외 |
| **(b) ATR 손절 multiplier** | **ATR×3.0~3.5** | **ATR×2.5 (현 VERITY)** | **ATR×1.5~2.0** |
| 학계 | Wilder 1978; Van Tharp 1999: 넓은 stop = 낮은 사이즈 | Van Tharp 표준 2.5× | Jegadeesh-Titman 1993 momentum 표준 |
| 🇰🇷 조정 | KOSPI 변동성 ×1.2 → 실효 ATR×3.6 | 변동성 조정 ATR×3.0 | KOSDAQ 고변동성 → ATR×2.5 상향 |
| **(c) R-multiple 익절** | **60/30/10** | **50/30/20 (현)** | **30/30/40** |
| 학계 | Van Tharp: 조기 익절 = 심리 안정 | 표준 R-multiple ladder | O'Neil CANSLIM: 트레일링 최대화 |
| 🇰🇷 조정 | 해외 1R 익절 = 33% 세금 → 세후 감소 | 동일 | 공격 트레일 40% = 1년+ hold → 22% 유리 |
| **(d) 종목 수** | **15~20** | **10~12** | **5~8** |
| 학계 | Statman 1987 *JFQ*: 비체계적 95% 제거 = 30종목, 한계효과 15~20 급감 | Evans & Archer 1968 | Buffett 집중투자 best ideas |
| **(e) 회전율 (yr)** | **≤0.5 (b&h)** | **1.0~1.5** | **2.0~3.0** |
| 학계 | Fama-French 장기 보유 = factor premium | Jegadeesh-Titman 12M 모멘텀 | O'Neil CANSLIM 연 3~4회 |
| 🇰🇷 세제 | **해외 1년 미만 33%** → 1년+ hold 의무 | 1년 hold 22% 절세 | **공격 KR 단타 비과세 활용** (국내 집중) |
| **(f) 종목 선정** | **Quality** Piotroski F≥8 / Altman Z>3 / ROE>15% / 부채<100% / 배당>2% | **Value+Quality** F-F HML + Piotroski F≥6 / PBR<1.5 / EV/EBIT<15 | **Growth+Momentum** CANSLIM / EPS 가속 +25%+ / 52w 신고가 |
| 학계 | Piotroski 2000 *JAR*; Altman 1968 *JoF* | Asness et al. 2019 AQR "Quality Minus Junk" | Jegadeesh-Titman 1993; O'Neil CANSLIM |
| 🇰🇷 조정 | **금융주 PBR/ROE 다름** → 섹터어웨어 제외; KOSDAQ ROE 20%+ | KOSPI200 Value 팩터 유효성 하락(2015~) → Quality 비중↑ | **KOSDAQ 성장주 = 공격 중심**; 52w 신고가 한국 실증 (자본시장연구원 2019) |

---

## Q3 — Hybrid 구조 실무 사례 + 학계

### 실무 사례

| 펀드 | 구조 | 시그널 공유 | 룰 차별 |
|------|------|------------|--------|
| Bridgewater Pure Alpha + All Weather | 분리: Pure Alpha=시장중립 / AW=Risk Parity | 매크로 리서치 공유 | Pure Alpha 15% / AW 15% (다른 sizing) |
| AQR Multi-Strategy | Style Sleeve (V/M/Q/Carry) | 공통 factor signal | sleeve별 target vol (Value 8% / Mom 12%) |
| Two Sigma Compass | Quant umbrella sub-strategy | ML 시그널 공유 | 각 sub risk budget 독립 |
| Yale 내부 | 6 sub-asset class 외부 운용 + 내부 매크로 | CIO 매크로 공유 | 각 클래스 target + ±5% band |
| 미래에셋 멀티에셋 | 국내/해외/대체 3 Tier sleeve | 매크로 탑다운 | Risk budget 기반 sleeve VaR |

### 학계 논문

| 논문 | 저자/연도 | 결론 |
|------|----------|------|
| "Optimal Portfolio Construction for Long-Horizon Investors" | Campbell & Viceira 2002 | Multi-bucket > 단일 (지평선 다른 자금 분리 효율) |
| "The Bucket Approach to Retirement" | Kitces & Pfau 2014 *J of FP* | 3-bucket 심리 안정 +15%, 실질수익 차이 미미 |
| "Multi-strategy Funds" | CAIA 2019 | 상관관계 낮은 sub-strategy 조합 시 Sharpe 0.2~0.4↑ |

### 38일 베타 단계 권고

**단일 Tier 검증 후 점진 전환이 우월**.
- 38일 시그널 페어 = 추정 15~25회 → 통계 불충분 (최소 50~100 거래 필요)
- 3-Tier 동시 → 노이즈 증폭: attribution 혼재 → 진단 불가
- 권고 순서: **보수 단독 3개월 → 중간 추가 3개월 → 공격 추가 3개월**

### ⚠ 반증 (실패 사례)

- **LTCM 1998**: risk Tier 분리했으나 공격 블로우업 → 보수 강제 청산 → 전체 붕괴. **Tier 간 margin call 연결 절대 불가**
- **Amaranth 2006**: Multi-strategy hedge → energy 공격 -65% → 펀드 청산. 공격 hard circuit-breaker 부재 치명

---

## Q4 — Tier 간 재배분 Trigger 5종

| Trigger | 권고 | 임계 | Unwind 룰 | 학계 |
|---------|------|------|----------|------|
| 시간 기반 | **분기 1회** | 목표비율 ±3% 시만 실행 | 수수료+세금 ROI 계산 | Bernstein 2001 *Intelligent Asset Allocator* |
| 편차 기반 | **±5% drift** 시 | 60/30/10 → 65/25/10 → rebalance | 초과→부족 Tier, 세금 최소 경로 | Markowitz 재균형 분기내 ±5% |
| 레짐 기반 | VIX>30 → 공격→보수 일시이동 | VIX 30 (Pedersen AQR) | VIX<25 회복 후 재이동 (급속 복귀 X) | Pedersen 2009 "Risk On/Off" |
| Drawdown 기반 | 공격 MDD>-25% → 50% 축소 | -25% = Calmar 1.0 경계 | -25% 복구 시 재진입 (자동 코드) | Van Tharp 1999 |
| 시그널 Quality 기반 | Brain hit rate<55% (rolling 20거래) → 보수 80% 상향 | 55% = break-even Kelly | hit>60% 3개월 → 정상화 | Kelly 1956: `f*>0` 조건 |

### 거래 비용 break-even

- 수수료 0.015% × 2 = 0.03% 편도
- 국내 rebalance: ROI break-even = 드리프트 수익개선 > 0.03% (분기 ±5% 대부분 충족)
- 해외 1년 미만 rebalance: 33% 세금 + 0.03% → break-even ↑ → **해외 Tier = 연 1회 또는 1년 hold 원칙**

### ⚠ 반증

rebalance 가 alpha 죽이는 경우: Yale 2009 금융위기 후 의도적 지연. 강세장 초입 섣부른 공격→보수 = 모멘텀 프리미엄 포기. Bridgewater 도 레짐 전환 확인 전 조기 X.

---

## Q5 — 시드별 3-Tier Break-even

### 공식

```
Break-even 시드 = (수수료율 × 2 × 종목수) / 기대 초과수익률 (Tier 차별 알파)
```

### 사이즈별 분석

| 시드 | 3-Tier | 공격 Tier | 종목당 | 실효 수수료 | 3-Tier ROI |
|------|--------|----------|--------|------------|----------|
| **1000만** | 600/300/100만 | 100만 / 5종목 = **20만/종목** | 삼전 7만 = 2~3주 / 수수료 0.13% | ❌ **비권고**: 단일 Tier 80%+ |
| **1억** | 6000/3000/1000만 | 1000만 / 5종목 = **200만/종목** | 수수료 <0.05% | ✅ **2-Tier (70/30) 또는 3-Tier 가능** |
| **10억** | 6/3/1억 | 1억 / 8종목 = **1250만/종목** | 코스닥 중소형 유동성 임팩트 risk | ✅ **3-Tier 표준** (공격 = KOSPI200 중형주 한정) |

### 시드별 권고 Tier 수

- 1000만 = **1 Tier** (보수 집중)
- 5000만 = **2 Tier** (보수/중간)
- 1억+ = **3 Tier 진입 적합**
- 10억+ = 3 Tier + 내부 슬리브 세분화

### ⚠ 반증

Buffett 초기 시드 소액 = 집중 1 Tier 로 자본 성장 극대화 후 분산. 1000만에서 3-Tier = 분산 비용만 지불, 분산 효과 X.

---

## Q6 — Tier 별 KPI Dashboard

### 3 Tier × KPI 표

| KPI | 보수 (60%) | 중간 (30%) | 공격 (10%) | 보고 빈도 |
|-----|-----------|-----------|-----------|---------|
| 주요 1 | **Sortino** ≥1.5 | **Sharpe** ≥1.0 | **Calmar** ≥1.0 | 월간 |
| 주요 2 | Max DD <10% | Max DD <20% | Max DD <30% | 월간 |
| 주요 3 | Alpha vs KOSPI200+KTB 50:50 | **IR** ≥0.5 vs KOSPI TR | **멀티배거 Hit Rate** (>3R) ≥20% | 분기 |
| 주요 4 | 회전율 <0.5 | 회전율 1.0~1.5 | **Omega** ≥1.5 (Shadwick-Keating 2002) | 분기 |
| 주요 5 | **Treynor** (β 조정) | β 0.7~1.0 | **절대수익률** (벤치마크 무관) | 분기 |

### 한국 벤치마크

| Tier | 무위험 | 벤치마크 | 비고 |
|------|--------|---------|------|
| 보수 | **국고채 10y ~3.5%** | KOSPI200 + KTB 50:50 | 금투세 폐지 후 변경 없음 |
| 중간 | 동일 | **KOSPI TR** | 배당 재투자 포함 |
| 공격 | 동일 | **KOSDAQ150** (KR) / Russell 2000 (US) | KR 공격=KOSDAQ, US 공격=R2K |

### ⚠ KPI 왜곡 사례

- 공격 Tier 에 Sharpe → 변동성 큰 멀티배거 패널티 → 자동 배제. **공격 Sharpe 최적화 = 멀티배거 완전 차단**
- 보수 Tier 에 절대수익 → 국채 대비 무의미 과도한 리스크 추구

---

## Q7 — 1인 PM Blow-up 7 패턴

| # | 패턴 | 사례 | 방어 룰 |
|---|------|------|--------|
| (a) Kelly Full | Niederhoffer 1997: 아시아 위기 단일 이벤트 → 계좌 전멸 | ¼ Kelly hard cap 코드화, override 불가 |
| (b) FOMO/복수거래 | Damodaran 행동재무: 손실 만회 충동 → 평단 낮추기 → 추가 손실 | 손절 후 동일 종목 **48시간 재진입 금지** 코드 |
| (c) 레버리지 | Livermore: 마진 call → 1929 전재산 / 한국 신용 2020-03 | 레버리지 = 공격 Tier 도 **0%** (미장 마진 포함) |
| (d) 더블다운 | LTCM 1998 -45% 추가 → 청산 | MDD -25% → 포지션 **자동 50% 축소** |
| (e) Overfitting | Knight Capital 2012: 45분 만에 $440M 손실 | 공격 시그널 = OOS **N≥100 검증** 후 투입 |
| (f) 레짐 전환 | 2022 금리 인상: ARK -75% | VIX>30 → 공격 자동 50% 현금화 |
| (g) 세제 함정 | 한국 개인 2021: 미장 단타 → 종합소득세+33% 이중 타격 | 해외 공격 = 1년 hold; 1년 미만 실현 시 **사전 세후 수익 계산 의무** |

---

## Q8 — 한국 세제 정밀 반영

### KR/US 비중 권고

| Tier | KR | US | 세제 근거 |
|------|-----|-----|----------|
| 보수 (60%) | **70~80%** | 20~30% (1년+ hold) | 국내 비과세 최대 / 해외 장기 22% |
| 중간 (30%) | **50~60%** | 40~50% (1년+ 목표) | V+Q 팩터 양쪽 유효 / 해외 1년 절세 |
| 공격 (10%) | **80~90%** | 10~20% (극히 선별) | **국내 단타 비과세** / 해외 33% → 실효 급감 |

### R-multiple 익절 세후

- 해외 1R 익절 (+5%) × (1-0.33) = **+3.35%**
- 트레일링 (+5R = +25%) × (1-0.22) = **+19.5%**
- → **트레일링 6배 세후 우월**. 해외 1R 조기 익절 = 세후 비효율

### 손실 이월공제 불가

- 같은 해 다른 해외 익절로 손익 상계 불가
- 방어: 해외 공격 = 동일 과세연도 손익 페어링 (손실 정리 전 익절 먼저 → 순익 최소화)
- 실질: **공격 Tier 해외 비중 최소화** (국내 비과세 집중)

### 대주주 50억 anchor

현 1000만 vs 50억 = 500배. 도달 시 국내 매매차익 과세 전환 → 전체 Tier 재설계.

---

## Q9 — 시뮬→실거래 Protocol

| 단계 | 기간 | 검증 KPI | 통과 기준 |
|------|------|---------|---------|
| Phase 0 (현재) | ~38일 | 시그널 hit rate / MDD / ATR 작동 | 거래 N≥30 (통계 최소) |
| Phase 1 | +65 거래일 (8월말) | Sharpe ≥0.8 (시뮬), MDD <15%, hit ≥55% | 3 KPI 동시 충족 |
| Phase 2 (소액 실거래) | 3개월 | 보수 1% 시드 실거래 | Paper vs Live P&L 격차 <30% (1% = 10만) |
| Phase 3 (보수 본격) | 전역 후 3개월 | 보수 30% 시드, Sharpe ≥1.0 | MDD <10% (보수) |
| Phase 4 (중간 추가) | 전역 후 +6개월 | 전체 Sharpe ≥0.8, IR ≥0.4 | 2 Tier 안정 |
| Phase 5 (3-Tier 완성) | 전역 후 +12개월 | Calmar ≥0.8, MDD <20% | 2028 목표 경로 확인 |

**Paper vs 실거래 격차**: 학계 평균 -20~-40% alpha decay. KIS API 자동화 → -15~-25% 경감 가능. (algotrading 커뮤니티 실증)

### ⚠ 반증

시뮬이 나쁜 습관 형성 — 심리 없는 시뮬 검증된 "참을성" 이 실거래 작동 X. 소액 실거래 병행이 pure paper 보다 우월.

---

## Q10 — Critical Flaw 5건 (설계 재검토 Anchor)

### Flaw 1: 시그널 미검증(38일) 상태 3-Tier 조기 도입

Brain v5 OOS 미검증 → 3-Tier 분할 = curve-fit 시그널 3배 증폭. 보수/공격 동일 신호 → 시그널 curve-fit 시 3 Tier 동시 실패.
**대안**: 시그널 검증 완료까지 **1 Tier 운용**, 3-Tier 설계만 유지.

### Flaw 2: 1000만 시드 공격 100만의 경제적 무의미

100만 / 5종목 = 20만/종목 → 삼전 2~3주 → 포지션 사이징 정밀도 제로. 수수료+슬리피지가 알파 잠식.
**대안**: 실 시드 1억 전환 전까지 3-Tier 설계만 유지, **단일 보수 Tier 실 운용**.

### Flaw 3: Tier 간 심리 오염 (Cross-Tier Contamination)

공격 -30% 목격 → 보수까지 손절 충동. 1인 PM = Tier 분리 심리 장치 X. LTCM 패턴 (공격 붕괴 → 전체 청산 trigger).
**대안**: 공격 Tier = **별도 증권 계좌 물리 분리**, 보수 계좌와 화면 분리.

### Flaw 4: 한국 세제 vs 공격 Tier 회전율 치명 비정합

공격 회전율 2~3/yr + 해외 비중 → 33% 단기양도세. 연 +30% 도 세후 +20%. **공격 Calmar 1.0+ 달성 사실상 불가**.
**대안**: 공격 Tier = **국내 100%** (비과세). 해외 공격 = 중간 Tier 의 1년 hold 포지션으로만.

### Flaw 5: 황금알 거위 목표 vs 공격 Tier 설계 모순

Calmar 1.0+ / MDD <20% Anti-fragile 목표인데, 공격 Tier MDD 30% 허용. 수학적으로는 10%×30% = 3% 기여 무해. **1인 PM 심리 MDD = 최악 포지션 기준**으로 느낌. 공격 단일 -50% = 시스템 전체 신뢰 붕괴.
**대안**: 공격 Tier 도 단일 종목 **max loss -20% hard stop** 코드화 (ATR 손절 + 이중 안전장치).

---

## 사용자 액션 체크리스트 (Perplexity 권고)

1. **비율 결정**: 현 1000만 → **80/15/5 또는 단일 Tier 80%** → 실 시드 1억 전환 후 60/30/10 점진
2. **공격 Tier 국내 집중**: 해외 공격 = 0%, 국내 비과세 극대화
3. **물리적 계좌 분리**: 공격 Tier = 별도 KIS 계좌 (심리 오염 방지)
4. **시그널 N≥100 게이트**: Phase 1 완료 후 중간 추가, Phase 2 이후 공격 추가
5. **Q10 Flaw 1~5 = 설계 재검토 anchor** → [[project_capital_3tier_mode]] 메모리 갱신
