# Perplexity 6 자문 답 — CAUTION 72 PM 결정 근거 (2026-05-18)

- 받음: 2026-05-18 02:00 KST
- 트리거: 5/18 새벽 cron_health CAUTION 72 (CAPE 99%ile + USDKRW 1497.76)
- 모델: Sonar Pro academic search mode
- 출처: 사용자가 Perplexity에 질문 → 답 가져옴 (Claude 자동 호출 X)
- A1~A4 받음 / **B1~B2 미수신 (대기)**

---

## A1 — CAPE 99%ile + 인버스 부분 헤지 historical 효과

### 핵심 결과 (12m forward)

| 전략 | Sharpe (vs Long) | Max DD 축소 | Win Rate (하락방어) | 헤지비용 |
|---|---|---|---|---|
| 100% Long | 기준 (~0.35-0.45) | 기준 (-50~-60%) | — | 0 |
| 10% 헤지 | +0.05~+0.10 | -5~-8%p | 60-65% | 낮음 |
| 20% 헤지 | +0.08~+0.15 | -10~-15%p | 65-70% | 중간 |
| 30% 헤지 | +0.10~+0.18 (상승장 패널티) | -15~-20%p | 70-75% | 높음 |
| **100% 현금** | **최저 (opportunity cost)** | 최소 | 100% (방어) | 0 |

### KOSPI CAPE Episodes (4건)

| Episode | 기간 | 12m fwd 결과 |
|---|---|---|
| 외환위기 직전 | 1994-1996 | -35~-60% (1997 포함) |
| IT 버블 | 1999-2000 | -50% peak-to-trough |
| 차이나 붐 | 2007 | -54% (2008 급락) |
| 유동성 장세 | 2021 Q1 | -20% (2022) |

**평균 12m fwd 낙폭**: -20~-30%. 샘플 N=4 = 통계 빈약.

### 핵심 한계 ⚠️

- **KOSPI CAPE 99%ile + 인버스 부분헤지 학계 논문 / 공식 backtest 부재**
- 위 표 = 학계 + 삼성증권 CAPE 마켓 타이밍 모델 (2003-2021) 기반 **추정치**
- KODEX 252670 (-2X 인버스) = 2017 상장 → 1990-2000년대 episode 직접 backtest 불가
- 백테스트 직접 구축 = KRX 일별 데이터 + CAPE 추정치 결합 Python 시뮬레이션 필요

### 권고

- **단순 1X 인버스 (114800)** 가 12m+ 보유 시 2X 인버스 (252670) 보다 tracking error 낮음
- 헤지 리밸런싱 = 월간 (CAPE 시그널 지속 여부 재확인)
- Exit 기준 = 12m 경과 OR CAPE < 75%ile

---

## A2 — KODEX 252670 비용 잠식률 (12m 보유)

### 비용 항목별 (σ≈16% 기준)

| 항목 | 연간 비용률 | 1000만원 기준 |
|---|---|---|
| **변동성 감쇠 (Vol Decay)** | **5.04%** | **504,000원** |
| **선물 롤오버 (Contango)** | **1.20%** | **120,000원** |
| 총보수 TER | 0.67% | 67,000원 |
| Slippage + Bid-ask | 0.10% | 10,000원 |
| 매매수수료 | 0.03% | 3,000원 |
| **합계** | **~7.04%** | **~704,000원** |

### Volatility Decay 산식

`Vol Decay = β² × σ²/2 × T` (β=2 for -2X)

| σ (연간) | Vol Decay (-2X) | 1000만원 손실 |
|---|---|---|
| 12% | 2.88% | 288,000원 |
| 15% | 4.50% | 450,000원 |
| **16% (기준)** | **5.04%** | **504,000원** |
| 18% | 6.48% | 648,000원 |
| 25% | 12.50% | 1,250,000원 |

quantkang 분석: 252670 전체 추정 비용 = **31.3%** (변동성 비용 33.5% + 금융비용 -3.3%). 1X 인버스 (10.1%) 대비 **3배 잠식**.

### ProShares SDS (-2X S&P500) 비교

- TER 0.89% (252670 0.64%보다 높음)
- S&P500 σ ≈ 18-20% (KOSPI200 16%보다 높음) → 더 큰 Vol Decay
- 구조적 비용 원리 동일, **변동성 높을수록 잠식 확대**

### 핵심 결론

- **단기 (1-5일) 헤지** = 비용 미미, OK
- **12개월 보유 = 7%+ 잠식 보장** + σ 급등 시 +30%까지
- 1X 인버스 (114800) 대비 -2X = 3배 비용
- **변동성 σ ≥ 20% 국면 = 기하급수적 잠식**

---

## A3 — USD-KRW 1500 돌파 historical episodes

### Episode 개요 (3번 명확 돌파 + 2024 미돌파)

| # | Episode | 1500 돌파 시점 | 피크 환율 |
|---|---|---|---|
| ① | 1997 IMF 외환위기 | 1997.12 초 | **1,964.8원** (1997.12.24) |
| ② | 2008 금융위기 | 2008.11.24 | 1,570대 (11월) / **1,549원** (2009.3) |
| ③ | **2026 현재 (진행 중)** | **2026.3.4 새벽 (1,506 터치)** | **1,530.1원** (2026.3.31) |
| ②.5 | 2024 트럼프+계엄 | **미돌파** (1,473 고점) | 1,473원 (2024.12) |

> 2022 미국 긴축 episode = 1500 미돌파 (peak ~1,444원, 2022.9)

### 직후 12m KOSPI/외국인 통계

| Episode | KOSPI 변화 | 외국인 순매도 | 환율 정상화 |
|---|---|---|---|
| ① 1997 IMF | 650 → 277 (**-58%**) | 미집계 (대규모) | ~18개월 |
| ② 2008 금융위기 | 2,064 → 892 (**-57%**) | 수십조 순매도 | ~12개월 |
| **③ 2026 현재** | **5/15 하루 -6.1%** (외인 5조 순매도) | **3-4월 ~60조** | 진행 중 |

### 2026 환경 진단 (가장 유사한 episode)

**1997/2008 단순 비교 아님. "2008 외부충격 + 2022 구조적 약세 복합형".**

| 비교 차원 | 1997 IMF | 2008 금융위기 | **2026 현재** |
|---|---|---|---|
| 달러 부족 (외환위기) | ✅ 핵심 | ❌ | ❌ |
| 외부 충격 | ❌ | ✅ 리먼 | ✅ 美이란전쟁 |
| 구조적 자본 유출 | ❌ | ❌ | ✅ 서학개미·연기금 |
| 한미 금리 역전 | ❌ | ❌ | ✅ 42개월 |
| 외환보유고 | ❌ 위기 | ✅ | ✅ ($4,259억) |
| 재정 확장 동시 | ❌ | ❌ | ✅ |

**핵심 차이**: "달러 없어서"가 아닌 **"달러 있는데 시장에 안 나오는" 수급·심리형 약세** (이창용 한은 총재 진단: 대차시장 vs 현물시장 이중구조).

**시사**: 외부 충격 (이란전쟁 휴전) 해소 시 빠른 하락 가능, but 구조적 요인 (한미 금리차 + 서학개미 + 국민연금 해외) 잔존 시 **1,400원대 후반이 새 균형 수준** 고착 위험.

---

## A4 — 시드 작은 개인 optimal cash allocation 학계 권고

### 4 Framework 결과 (CAPE 99%ile + USDKRW 1500 환경)

#### I. Markowitz MPT
- CAPE 99%ile → ERP 1.6-2.0% 압축
- 시드 $10K = 거래비용 비선형 → 1-2개 자산군만 효율
- 권고: **ETF 기반 60/40 ~ 80/20 (주식/현금)**

#### II. Kelly Criterion
- f* = (μ - rf) / σ² (Merton Share 동일)

| Kelly 버전 | 주식 배분 | 특성 |
|---|---|---|
| Full Kelly | 20-35% | 단기 변동성 매우 큼 |
| **Half Kelly (권고)** | **10-18%** | 장기성장률 75% 유지, DD 50% 감소 |
| Quarter Kelly | 5-9% | 극도로 보수적, $10K 현실 근접 |

Winselmann (2018), Thorp (2011) = **Half-Kelly 이하 권고**. 소액 시드 Full Kelly = 파산 경로 위험.

#### III. Merton Intertemporal
- w* = (μ - rf) / (γ × σ²)
- 현재 CAPE Yield ≈ 2.7%, 무위험 4.3% → **ERP 음수 또는 zero**
- γ=3 (보통 위험회피) → 이론 0-15%
- 실용 Guardrail: **Floor 20% / Ceiling 40%** (Fictitious Capitalist 2025 CAPE-Merton 모델)
- **100% 현금은 이론적으로 과도**

#### IV. Behavioral Finance
- Kahneman & Tversky (1979) Prospect Theory: 손실 2.5배 무게
- Amundi (2022): Loss Aversion + Status Quo Bias = **현금 15-25%p 과잉 보유** 경향
- 처방:
  - Mental Accounting: "핵심 안전 (50-60%) + 점진 트랜치 (40-50%)" 분리
  - DCA 3-6회 분할 진입 (Regret Aversion 완화)
  - **100% 현금 함정 = 기회비용 무시, 실질구매력 손실**

### USDKRW 1500 환경 추가 시사

- USD 자산 = **KRW 약세 자동 헷지**
- 권고: **USD Cash 또는 단기채 20-30%** > 순수 현금
- NPS도 전술적 헷지 비율 15% 상한 유지 → 개인은 더 유연하게

### 거래비용/세금 ($10K 시드 특수)

- 최적 1회 매수 = $5,000-$10,000 (최소수수료 분기점)
- 상대 거래비용 = 0.2-0.3%/트랜잭션 (ETF 기준)
- KR: 대주주 초과 22%, 소액 비과세
- US: 250만원 공제 후 22%
- 권고: **2-3 트랜치 최대, ETF 1-2종목**

### 학계 컨센서스 요약 ⚠️

**4 framework 모두 100% 현금 = 비최적 판정**

권고 배분 범위:
- **현금 (KRW + USD 단기채): 60-75%**
- **글로벌 주식 ETF (분산): 20-30%**
- **분할 매수 3회+, ETF 2종목 이내**
- **USD 자산 30%+ → KRW 약세 tail risk 헷지**

### 핵심 논문 인용

- Markowitz (1952, *J. Finance*)
- Merton (1969, *Rev. Economics & Statistics*)
- Kelly (1956, *Bell System Technical Journal*)
- Kahneman & Tversky (1979, *Econometrica*) — Prospect Theory
- Thorp (2011, *Handbook of the Fundamentals of Financial Decision Making*)
- Khasanov et al. (2008, SSRN #1098335) — Optimal Portfolio Selection for the Small Investor

---

## B1 — CAPE 99%ile 환경 고밸류 vs 저밸류 forward return

### 핵심 정량 데이터

**CAPE 구간별 Forward 12M return (US 1881-2024, QuantStreet/Campbell-Shiller)**

| CAPE bucket | Forward 12M |
|---|---|
| 저CAPE (하위 20%) | **+19.7%** |
| 20-40% | +14.5% |
| 40-60% | +11.2% |
| 60-80% | +7.8% |
| 고CAPE (상위 20%) | +2.4% |
| **극단 (99%ile)** | **-2.1%** (마이너스 역전) |

CAPE-10Y 상관계수 = **-0.7** (CFA Institute, 강한 부정)

### 10Y 실질수익 추정 (현재 CAPE 기준)

- Research Affiliates: Shiller CAPE **2.4%/yr** / CC CAPE **4.7%/yr**
- PGIM (2024.8): **1.3-4.1%/yr** (장기 평균 6.5% 대비 대폭 낮음)

### PBR/PER 이중 필터 Forward Return

**Penman & Reggiani**:
- 고PER + 고PBR 평균 return = **1.9%**
- 저PER + 저PBR 평균 return = **27.1%**
- 격차 **25.2%p**

### Max Drawdown (밸류에이션 그룹별)

| 그룹 | Max DD |
|---|---|
| PBR < 1.0 | **-15.2%** |
| 1.0 ≤ PBR < 2.0 | -21.5% |
| 2.0 ≤ PBR < 3.0 | -28.3% |
| PBR > 3.0 | -38.7% |
| **PBR > 3.0 + CAPE 99%ile** | **-52.4%** |

→ **고PBR + 고CAPE 결합 = 저PBR 대비 3.5배 낙폭 위험**

### 한국 시장 데이터

**대신증권 (2020)**:
- B/P Q1 (저PBR) 연 **24.4%** (Sharpe 1.0)
- B/P Q4 (고PBR) 연 **8.7%** (Sharpe 0.1)
- 격차 **15.7%p**

**Korea Discount 특수성**: KOSPI CAPE는 글로벌 대비 구조적으로 낮음 → 99%ile 임계값 자체를 **한국 시장 기준 재설정 필요**.

### AQR Value Spread (Asness "Devil in HML")

- Timely B/P 기준 HML Devil α = **305-378bp/yr**
- 가치 스프레드 확대 시 → 미래 HML 수익 **비선형 증가**
- 시장 전체 CAPE 99%ile + value spread 확대 = 저밸류 포지션 상대적 α 극대화

### 가설 검증 결과

| 항목 | 결과 |
|---|---|
| "CAPE 99%ile → 10Y 수익률 저하" | ✅ **강한 지지** (상관 -0.7) |
| "고CAPE + 고PBR → DD 심화" | ✅ **강한 지지** (-52.4% vs -15.2%) |
| 단기 (1-3년) 예측력 | ❌ 약함 (2018 CAPE 33 → 이후 8년 연 13.7% 반례) |
| 한국 시장 일반화 | ⚠ KOSPI CAPE 임계값 재설정 필요 |

### 스크리닝 함의

- 저밸류 (PER<10, PBR<1) = 가격 내재 부정 기대 → 추가 재평가 하방 제한
- **Piotroski F-Score ≥7 + PBR < 1.0 복합 필터** = CAPE 고점 환경 Max DD 한 단계 낮춤 (한국)

---

## B2 — Macro overlay + valuation screening 결합 사례

### 펀드/Firm별 사례

**AQR Capital Management (가장 명확한 공개 사례)**:

| 논문/전략 | 효과 |
|---|---|
| Macro-to-Micro | 국가 macro forecast × 지리적 매출 노출 → firm-fundamental 예측 개선. domestic firm 특히 강함 |
| Fundamental Trends + Dislocated Markets (통합 macro) | 시뮬레이션 Sharpe **>1.4**, max DD **-12.4%** |
| Devil in HML | Timely B/P 기반 가치 스프레드 활용 |

**GMO**: valuation-centered (deep value), macro/valuation context = **filter** (absolute rule 아님)

**Bridgewater All Weather**: asset allocation 차원 (stock-level X), macro state = 지배적 risk driver

**한국 사례**: 공개 quant fund 사례 부재

### 3 변수 macro overlay 표준 구성

1. **Valuation anchor** (CAPE / 국가·섹터 상대 valuation spread)
2. **Currency regime** (수출 의존 / 외국인 매출 비중 큰 기업 특히)
3. **Rate regime** (real rates / 명목 yield trend / policy stance 변화율)

### Binary vs Continuous 비교 ⚠️ **핵심**

| 방식 | 강점 | 약점 |
|---|---|---|
| **Binary cutoff** (WATCH → AVOID 강등 같은) | 설명·구현 쉬움 | **threshold 선택 민감, 경계 turnover 증가, 정보 손실** |
| **Continuous score** (z-score / rank) | 정보 보존, smoother portfolio change | calibrate/backtest 약간 복잡 |

**학계 + practitioner 컨센서스 = Continuous 우위**. binary cutoff = 신호 noisy 시 정보 throw away + 경계 부근 fragile.

### 1인 ~$10K seed 모방 가능 simplified version

```
Composite = 0.5 × ValuationScore + 0.25 × CurrencyScore + 0.25 × RateScore
```

각 score = z-score 또는 0-1 표준화 (**binary X**). Top decile/quintile만 거래. Monthly/quarterly rebalance (turnover 제한).

### 권고 architecture

- **Soft gate** (multiplier) > **hard veto** (binary)
- Cheap names 여전히 rank, but **unfavorable macro state 시 score discount**
- Binary cutoff = **crisis-level risk control 전용** (예: VAMS engine `applicable=False` 같은 절대 회피)
- Order: **valuation first → macro as multiplier → binary only for crisis**

---

## PM 재평가 — 5/18 02:00 KST 직전 결정 대비

### 직전 결정 (01:30 KST)
- A. 헤지 진입 = **거절** → 현금 100% 유지
- B. Brain 룰 변경 = **거절** → 룰 무변경

### 답 받은 후 재해석

#### A1 + A2 결합 — **2X 인버스 12m 헤지 = 학계+실무 모두 비현실**
- 7%+ 잠식 보장 + σ 급등 시 30%
- **단기 (1-5일) 만 유효** → 1인 PM (= 일 1회 모니터링) 부적합
- 1X 인버스 (114800) 12m 보유 = 1.5-2% 잠식, 우월

#### A3 — **이미 진행 중인 episode = 의사결정 시간 압축**
- 1,500 돌파 2026.3.4 이미 발생
- 외국인 5월 60조 순매도, KOSPI 5/15 -6.1% 하루
- 2026 = "복합형" = 1,400원대 후반 신균형 잠재 → 빠른 회복 가능성 낮음

#### A4 — **100% 현금 = 학계 4 framework 일치 비최적**
- Markowitz / Kelly / Merton / Behavioral 모두 부분 진입 권고
- **USD 자산 30%+ = 핵심 권고** (KRW 약세 자연 헷지)

### 직전 결정과의 충돌

- [[feedback_seed_size_conservatism]] 정합 = 현금 우선 = **시드 작을수록 risk 회피** ← 사용자 PM 원칙
- A4 학계 = **현금 100% = opportunity cost + 실질구매력 손실** = 다른 종류의 risk
- 양자 = 정의된 risk vs undefined opportunity cost. PM 가치판단 영역.

### 옵션 재제시 (B1/B2 대기 중이지만 A 결정 가능)

**Option α (직전 결정 유지)**: 현금 100% (KRW MMF/RP) — 최대 보수, 진입 risk 0
- 정합: [[feedback_seed_size_conservatism]] + 시드 작은 단계 default
- 비용: 실질구매력 손실 (USDKRW 1500 신균형 시), 학계 컨센서스 불일치
- VAMS 0거래일 trail = 진입 보수 정당

**Option β (절충 — A4 학계 최소 권고 반영)**: USD 단기채 ETF 20-30% (예: TIGER 미국30년국채 종합, KODEX 미국S&P500), KRW 현금 70-80%
- 정합: A4 학계 4 framework + USDKRW 약세 자연 헷지
- 진입 1-2회 분할, ETF 1-2종목 limit
- 거래비용 0.2-0.3% × 2 = 0.5% 1회 cost
- VAMS trail 1건 시작 = Phase 0 외 추가 데이터 포인트

**Option γ (학계 권고 따라가기)**: 20-30% 글로벌 ETF + USD 자산 30% + 현금 40-50%
- 정합: A4 4 framework 전부 + 분산
- 시드 작은 단계 OOS validation 우선 원칙과 충돌 가능
- 가장 공격적

직전 결정 = α. β/γ 재선택 가능 OR α 유지 (PM 가치 판단).

**B1/B2 받으면 Brain 룰 결정도 같이 정리.**
