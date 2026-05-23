# Perplexity 답변 정리 — 2026-05-24

> **출처**: `docs/PERPLEXITY_QUESTIONS_20260524.md` 의 Q2 (cash cross) + Q5 (USD/KRW σ) 답변.
> **활용**: RULE 7 사전 등록 input. 답변 기반 산식 박기 *전* 백테스트 / 검증 의무 표기.
> **사용자 응답 status**: Q2 / Q5 답변 박힘. Q1 (KR ETF Z-Score) / Q3 (themes pulse) / Q4 (sector_trends 명세) = 답변 대기.

---

## Q2 — 자금 흐름 cross-validation (F sprint input)

### 핵심 결론
- **단순 합산 < 가중평균 < Bayesian aggregation** 정합도 순.
- **한국 시장 특유**: 외인 · 기관 · 프로그램 매매의 정보비대칭 + 역할 차이 → *source weighting 의무*.
- 합의도 (agreement ratio) + 강도 (weighted score) **결합 산식** 이 majority vote / weighted score 단독보다 우월.

### 산식 4 유형
| 유형 | 산식 | 특성 |
|---|---|---|
| 단순 합산 | `S_t = Σ z_i,t` | z-score 표준화 후 합. baseline |
| 가중평균 | `S_t = Σ w_i × z_i,t`, `Σ w_i = 1` | IC / t-stat / hit rate / turnover 효율 기반 weight |
| Majority vote | `S_t = sign(Σ sign(z_i,t))` | 방향성 합의 강, 크기 정보 손실 |
| Bayesian aggregation | `P(r_{t+h}>0 \| x_{1:t}) ∝ P(r_{t+h}>0) × Π P(x_i,t \| r_{t+h})^w_i` | 신호별 likelihood 결합. expert judgement 또는 다중 source 결합 *가장 자연* |

### 실무 권고 순서
1. **Granger causality** 로 *선행 정보 있는 source 만 남김* → predictive filtering
2. **Cointegration** = 장기 균형 검증용 (filtering 후 보조)
3. **IC 기반 weight** 결정 (순서: 예측력 검증 → 가중치 결정 분리)

→ *예측력 검증 + 가중치 결정 분리 구조* 가 가장 안전.

### 한국 시장 source 신뢰도 (Perplexity 정리)
| source | 역할 | weight 권고 |
|---|---|---|
| 외인 net buy | KOSPI 대형주 / 지수 방향성 직접 반응 | 가장 큼 |
| 기관 net buy | 연기금 = 정보성 높음, 금융투자/보험 = 분리 의무 | 중간 (분리 후) |
| 프로그램 매매 | 차익 거래 성격 → 단기 변동성 확대와 함께 해석 | 방향성 X, **regime filter / vol 보정 변수** |
| CFTC COT | 미국 자산 / 글로벌 risk-on/off 간접 | 보조 신호만 |
| ETF flows | 국내 ETF = 단기 **역추세** 성격 관찰 (한국 연구) | *반전 / 과열 지표* (추세 신호 X) |

기본 weight 출발점: **`w_foreign > w_institution > w_program`**.  
기관은 *연기금 / 금융투자 / 보험* 분리가 문헌 친화적.

### Agreement ratio + 강도 결합 산식 (**핵심 권고**)

```
AR_t = (1/N_t) × Σ 1(sign(s_1j) = sign(s_2j) = sign(s_3j))

S_t = AR_t × Σ w_i × z_i,t
```

| threshold | 의미 |
|---|---|
| AR ≥ 0.67 | 1차 유효 |
| AR ≥ 0.80 | 강한 합의 |

### 예측력 검증 (IC / ICIR / Decay)

```
IC_h = corr(S_t, r_{t+h})
ICIR = mean(IC_h) / std(IC_h)
Decay(h) = IC_h / IC_1
```

**horizon 별 일반 경향**:
- forward 5d = 가장 강함
- forward 20d = 절반 수준
- forward 60d = regime 의존 (확인용)

### Regime 의존성
| regime | 우월 source / 산식 |
|---|---|
| Bull | 외인 신호 + ETF flow |
| Bear | 기관 / 연기금 + 프로그램 매매 위험회피 신호 |
| Sideway | 합의도 + majority vote 효율 ↑ |
| Crisis | **Bayesian aggregation** 가장 안정. 단순 sum = 과적합 |

→ **고정 모델 X. 레짐별 weight set 분리** 정공법.

### 검증 표본 요구 (VERITY 백테스트 의무)
- 최소 2~5년, 권장 5~10년
- KOSPI / KOSDAQ 분리
- forward 5d / 20d / 60d
- bull / bear / sideway 레짐 분리
- z-score 표준화 + lagged signal
- 성과 = IC / hit rate / turnover-adjusted IR / decay curve

### **VERITY 의 현재 trail (49d) 으로는 N 부족** — 실제 산식 박기 *전*:
1. KRX / 예탁결제원 / CFTC / ETF flow 원자료 백테스트
2. KOSPI / KOSDAQ × 5d/20d/60d × 4 regime 의 IC 표 산출
3. weight + AR threshold 사전 등록 commit
4. F sprint (CashFlowRadar cross verdict) 진입

---

## Q5 — USD/KRW σ 동적 windows (b8e1b18d 후속)

### 최종 판정 (Perplexity)
| 용도 | 판정 |
|---|---|
| 정규분포 기준 이벤트 필터 | **P (통과)** |
| 실제 FX tail risk 캡처 | **F (불합격)** |

### 산식 4 유형 비교
| 유형 | 특성 |
|---|---|
| **EWMA (λ=0.94, RiskMetrics)** | 최근 데이터 가중치 큼. 단순 이동평균보다 추정오차 작거나 비슷 |
| **GARCH(1,1)** | 평균회귀 반영. 충격 후 서서히 안정되는 시계열 정합. 레짐 전환 잘 설명 |
| Realized variance (intraday) | 가장 우월. intraday 데이터 있을 시 우선 |
| 90일 rolling std | fallback / 장기 기준선 only |

### 권고 산식 (계층 구조)
```
σ_basic   = EWMA(λ=0.94)              ← 기본
σ_corr    = GARCH(1,1)                ← 보정
σ_realized = realized_variance        ← intraday 있을 시 우선
σ_fallback = 90d rolling std          ← floor / ceiling 참고만

σ_final = max(σ_floor, min(σ_EWMA, σ_GARCH))    ← 보수적 결합
```

### Fat-tail 보정
- USD/KRW excess kurtosis = 4-6 (fat-tail 강함)
- 정규분포 ±3σ = 0.27% **이론**, 실제 빈도 **1% 내외 또는 더 큼**
- 3σ 단독 = 희귀 이벤트로 사용 가능, but "거의 안 일어남" 해석 *틀림*

### **Quantile threshold 병행** (핵심 권고)
| quantile | 의미 |
|---|---|
| 1% | 강한 경보 |
| 5% | 주의 |
| 95% | 상단 압력 탐지 |
| 99% | 극단 스트레스 |

대칭 σ + 분위수 기준 *동시 사용*. 환율 = 하방/상방 비대칭 의무.

### 0.30% floor 판정
- **P (보수적 operational floor 로 합리)**
- 하지만 학술적 최적값 일반화 근거 *약함*
- **soft floor 권고** (hard floor X)

### 49일 부족 case (현재 VERITY 시점)
정공법 4 단계:
1. 49일 rolling std 우선 계산
2. EWMA 로 최근 49일 보강
3. 장기 priors + GARCH shrinkage 가능 시
4. 90일 수준 = floor / ceiling 만 참고

→ 실무 권고: `σ_final = max(σ_floor, min(σ_EWMA, σ_GARCH))`

### 한국 FX 시장 특유
- 2008 금융위기 / 2022 금리충격 = σ 점프 큼
- BIS / 국내 연구 = 구조적 취약성 / 대외자산 환리스크 / NDF-현물 연계 지적
- σ = 단순 통계 X, **조건부 지표** (한미 금리 spread / 달러 유동성 / NDF 프리미엄 동반)

→ 90일 = *장기 평균 기준선*, 일일 판단 = EWMA / GARCH 이중 구조.

---

## VERITY 적용 단계 (사전 등록 input)

### F sprint (CashFlowRadar cross verdict) — 진입 *전 의무*

| 단계 | 작업 | 의무 |
|---|---|---|
| 1 | KRX / 예탁결제원 / CFTC / ETF flow 원자료 fetch | backend 신설 |
| 2 | KOSPI / KOSDAQ × 5d/20d/60d × 4 regime IC 백테스트 | 산식 검증 (Q2 답변에 수치 없음, 직접 산출) |
| 3 | weight + AR threshold 사전 등록 commit | RULE 7 |
| 4 | CashFlowRadar UI = `S_t = AR × Σ w_i × z_i,t` 노출 | frontend |
| 5 | Brain 산식 통합 (선택) — fact_score 보너스 + sentiment cross | 별도 PM 결정 |

**현재 단계**: 1 (원자료 fetch) 도 미박힘. 큰 sprint. *별도 의제 큐잉*.

### σ sprint (USD/KRW σ EWMA 보강) — 진입 가능 단계

| 단계 | 작업 | 의무 |
|---|---|---|
| 1 | EWMA(λ=0.94) σ 산식 박음 (factors/_common 또는 verity_brain) | 산식 신설 = RULE 7 사전 등록 |
| 2 | GARCH(1,1) 보정 — `arch` 라이브러리 의존성 | backend (requirements.txt) |
| 3 | quantile threshold (1/5/95/99%) 박음 (3σ 와 병행) | 산식 추가 = RULE 7 |
| 4 | 49일 trail case fallback 로직 박음 — `max(σ_floor, min(σ_EWMA, σ_GARCH))` | 이미 검증 (Perplexity 정합) |
| 5 | verity_brain fx_shock msg 동적 method 명시 — "EWMA σ" / "GARCH σ" / "90일 σ" | b8e1b18d 후속 |

**현재 단계**: 1 (EWMA 산식) 박을 수 있음. RULE 7 사전 등록 commit 후 진입.

---

## RULE 7 사전 등록 (메모리 정합)

`feedback_methodology_pre_registration` + `project_brain_v5_self_attribution` 정합 — 자기 산식 변경 = 1회만, PM 승인 의무, commit 에 WHY/DATA/EXPECTED 박음.

### 사전 등록 commit 박을 산식 (Q5 기반)

```
산식 이름: USD/KRW σ 동적 추정 (EWMA + Quantile)
산식:
   σ_EWMA(t) = sqrt(λ × σ²(t-1) + (1-λ) × r²(t))
   λ = 0.94 (RiskMetrics 표준)
   
   σ_GARCH(1,1)(t) = ω + α × r²(t-1) + β × σ²(t-1)
   (arch 라이브러리, MLE fit)
   
   σ_final = max(σ_floor, min(σ_EWMA, σ_GARCH))
   σ_floor = 0.30% (soft floor, 보수적 operational)
   
   threshold 4 단계:
   - 3σ_final (이벤트 필터)
   - Q1 (강한 경보)
   - Q5 (주의)
   - Q95/Q99 (상단/극단 스트레스)
   
WHY: USD/KRW excess kurtosis 4-6 (fat-tail), 90d rolling std 단독 = 
     정규분포 가정 ±3σ 0.27% 이론과 실제 빈도 1%+ mismatch.
     RiskMetrics EWMA + GARCH(1,1) 학술 정합 (Perplexity Q5 정리).

DATA: 검증 의무 — USD/KRW 일별 5~10년 (FRED DEXKOUS), 
      2008 / 2022 stress event 분리 검증.
      VERITY 현재 trail = 49d → 백테스트 input 부족 → 시점:
        * EWMA 산식 박음 + verity_brain msg 동적 method 박음 (즉시 가능)
        * GARCH 추가 = 백테스트 후 (별도 sprint)

EXPECTED: 49d 시점 EWMA σ ≈ 0.40~0.60% 추정 (현재 fix b8e1b18d 의 
         sigma_dyn 동일 path), msg label = "EWMA σ" 명시. 
         3σ threshold + Q1/Q5/Q95/Q99 병행 → 사용자 PM 보수적 해석.
         자연 회복 시 (180d+) GARCH 보정 자동 활성.
```

---

## 다음 commit 후보

### Pre-register commits (RULE 7)
1. `pre-register(brain): USD/KRW σ EWMA 산식 사전 등록 — Q5 정합` (Q5)
2. `pre-register(brain): 자금 흐름 cross-validation 산식 사전 등록 — Q2 정합` (Q2) → 단 백테스트 *전* 까지는 *틀만* 박음

### Implementation commits (사전 등록 후)
1. EWMA σ 산식 박음 + verity_brain msg method 명시 (Q5 산식 1 단계)
2. CashFlowRadar AR × Σ w_i × z_i,t UI 박음 (Q2 산식 1 단계, 백테스트 의무 명시 caption)

---

---

## Q3 — themes_pulse 빌더 방법론 (G sprint input)

### 핵심 결론
- 주 1회 자동 cron + Sonar Pro + 컨콜 텍스트 + 정량화 산식 결합 = 표준 패턴 (Bridgewater / AQR / Two Sigma 흉내)
- 8 매크로 카테고리 × {positive/negative/neutral} × {high/mid/low} 정량화
- LLM hallucination 방어 = *다중 source 합의도* + *SEC/원본 cross-check rule* + *숫자/날짜 hallucination 금지 시스템 prompt*

### 산식 구조

**direction 매핑**: positive=+1 / neutral=0 / negative=-1
**conviction weight**: high=1.0 / mid=0.6 / low=0.3

**단일 source theme_score**:
```
theme_score_{s,c} = d_{s,c} × w_{s,c}      (범위 -1 ~ +1)
```

**멀티 source 합성 (4 소스: GS/MS/JPM/BLK)**:
```
aggregate_score_c = Σ α_s × d_{s,c} × w_{s,c}  /  Σ α_s
```
α_s = source 신뢰도 (초기 1.0 동일 가중)

**합의도 (consensus)** — hallucination 방어 + ambiguous filter:
```
consensus_c = |average(d_{s,c})|
```
- 4 source 중 3 positive + 1 neutral → avg=0.75, consensus=0.75
- 2 positive + 2 negative → avg=0, consensus=0 (불확실)
- **consensus < 0.3 → theme_score 강제 0 (불확실 카테고리 폐기)**

### Sonar Pro prompt 구조 (3-shot fixed)

**시스템 prompt** (고정 prefix):
> You are a macro strategist. Read the input text (weekly outlook).
> Map all views into exactly these 8 categories: growth, inflation, rates, fx, commodities, credit, geopolitics, policy.
> For each category, assign:
>   - direction: positive, negative, or neutral
>   - conviction: high, mid, or low
>   - rationale: 1–2 sentence justification copied and lightly compressed from the text.
> Do not invent numbers, dates, or policy names.
> Only extract what is explicitly stated in the input text.
> If unsure, mark the category as neutral and conviction as low.
> Output pure JSON only.

**3-shot** = 답변 박힘 (BlackRock weekly / 한국 리서치 / mixed nuance 예시).

### Industry themes (US15 컨콜)

대상: **Mag 7 + 8 섹터 리더 = 15 종목** (AAPL/MSFT/GOOGL/AMZN/META/NVDA/TSLA + 8).
파이프라인:
1. SEC 10-Q/8-K + earnings call transcript fetch (Investing.com / Nasdaq IR)
2. 전처리 (Forward-Looking Statements 제거, Q&A vs prepared remarks 분리)
3. TF-IDF + bigram/trigram + LDA/NMF (10 토픽)
4. Sonar Pro theme labeling (회사당 3-5개 핵심 themes, importance high/mid/low)
5. keyword dict 저장 (label → normalized token, importance weight)

**산업 theme_score**: 해당 industry 내 US15 종목 평균/중앙값.

### 비용 효율
- 월–화: GS/MS/JPM/BLK weekly outlook fetch + themes 추출
- 금–토: 그 주 발표 US15 earnings call 처리 (없으면 skip)
- monthly aggregate = 4-5 주 평균
- rolling 3개월 이동평균 (노이즈 제거)
- SHA-256 hash 기반 캐시 (재처리 skip)
- Sonar Pro 호출 = 2-3k tokens / chunk (비용 최적)

### 실패 사례 + 회피
1. **mixed signal 강제 분류** → ambiguous = neutral/mid + duality rationale
2. **숫자 hallucination** → `quoted_number: true/false` 필드, false 시 discard
3. **buzzword 과대 해석** → "topic must be material to guidance" 명시
4. **카테고리 오분류** → 8 카테고리 정의 prompt 박음

### 검증
- macro themes → toy portfolio (All Weather 변형) tilt → 3/6/12m forward 비교
- industry themes → AI / cloud / 반도체 ETF 1m/3m/6m alpha 측정
- t-test / bootstrap 으로 *theme presence → performance uplift* 유의성

### **G sprint 구현 단계 (큰 backend sprint, 사전 등록 의무)**

| 단계 | 작업 |
|---|---|
| 1 | `api/builders/macro_themes_pulse_builder.py` 신설 (Perplexity Sonar Pro + 4 IB outlook fetch) |
| 2 | `api/builders/industry_themes_pulse_builder.py` 신설 (US15 컨콜 fetch + LDA) |
| 3 | cron 신설 — 월요일 06:00 + 화요일 06:00 KST (RULE 4 / RULE 1 audit 의무) |
| 4 | output = `data/macro_themes_pulse.json` + `data/industry_themes_pulse.json` |
| 5 | macro_industry_align.py 호출 wire (main.py) — portfolio.json 에 attach |
| 6 | SectorMap UI 직결 (favored / disfavored sector 노출) |

**비용 추정**: Sonar Pro 4 호출/주 × 4 IB outlook + 15 호출/분기 × 4 quarter US15 = 약 $5-10/월.

---

## Q4 — sector_trends builder 정상 동작 명세 (acb2c12c / 193e64c4 검증)

### 핵심 결론
- **현재 VERITY fix (insufficient_trail flag + trail_warning) = 정답에 가까움** (acb2c12c / 193e64c4 정합 확인)
- 라벨 (1m/3m/6m/1y) vs 실제 trail 길이 *분리* = Bloomberg / LSEG point-in-time history 관행 정합
- 49일 누적 + 90일 요청 = "3개월 통계 X, 49일 추적 구간 부분표본 통계" 취급

### 옵션 평가
| 옵션 | 평가 |
|---|---|
| (a) sliding window — most recent N days | 항상 값 만들지만 라벨 ≠ 실제 = 해석 오류 |
| (b) anchored window — N days ago to today | trail 부족 시 동일 왜곡 |
| **(c) skip + insufficient_trail flag (현재 VERITY 선택)** | **가장 보수적 + 재현성 ↑** ✅ |

### Confidence threshold 표준

| ratio | 처리 |
|---|---|
| N / requested ≥ 0.7 | 정상 또는 amber 경고 |
| 0.5 ≤ N / requested < 0.7 | 계산 허용 + warning 강하게 표시 |
| N / requested < 0.5 | 통계 미생성 또는 insufficient_trail flag만 반환 |

VERITY 현재 = 0.7 cutoff. amber band (0.5~0.7) 미박힘 → **추가 sprint 권고**.

### Misleading 회피 패턴
1. **기간별 표본 수 다른데 동일 막대 비교** → coverage ratio 노출 의무
2. **1m/3m/6m/1y 모두 같은 데이터셋 다른 라벨** → effective lookback days 명시
3. **절대 수익률만 노출** → 동일 기간 benchmark 대비 excess return 또는 z-score 병행

### Caller (Gemini / UI) 가 PM 에게 알려야 할 정보
- `requested period`
- `actual trailing days`
- `coverage ratio = actual / requested`
- `quality label`: OK / amber / insufficient
- 계산 방식: sliding / anchored / skip
- 해석 제한: "3m/6m/1y는 추정치, full-window 아님"
- Gemini prompt: "Do not compare labels as equal horizons when coverage differs"

### Backfill vs simulation
- **Backfill** = "데이터 복원" 용도 (survivorship bias / 데이터 리비전 risk)
- **Simulation** = "what-if" 탐색 용도 (성과평가/랭킹엔 부적합)
- *섞으면 misleading 큼* → 분리 의무

### **추가 fix sprint (Q4 정합 보강)**

| 단계 | 작업 |
|---|---|
| 1 | `compute_sector_trend_summary` 결과에 `coverage_ratio` + `quality_label` (OK/amber/insufficient) 박음 |
| 2 | `generate_periodic_analysis` 동일 추가 |
| 3 | 0.5 hard floor 적용 (0.5 미만 = insufficient_trail flag만 반환, 통계 미생성) |
| 4 | Gemini prompt template 에 "Do not compare labels as equal horizons" 박음 (별도 sprint) |

→ acb2c12c / 193e64c4 의 *완성* sprint.

---

## 출처

- 답변 출처: Perplexity Sonar Pro (사용자 박음 2026-05-24, 5 질문 모두)
- 답변 핵심 인용: 
  - Q2: nber.org / sites.stat.columbia.edu / koreascience.kr / s-space.snu.ac.kr / sciencedirect / chosun / aeaweb
  - Q3: blackrock.com / file.alphasquare.co / bbn.kiwoom / blog.naver / kr.investing / kind.krx / linkedin.com (Bridgewater) / ssga (All Weather)
  - Q4: wu.ac (Bloomberg) / cdn.refinitiv (LSEG) / erawa.com (statistical guidelines) / youtube
  - Q5: eia.feaa.ugal / joongang.co / kcmi.re / kif.re / kbam.co / youtube (fat-tail)
- 다음 단계: 사전 등록 commit + EWMA / Quantile / Cross verdict / Q4 정합 / G sprint 진입

## 메모리 정합

- `feedback_perplexity_collaboration` — 외부 사실/통계/법규 = Perplexity 핸드오프 (적용 완료)
- `feedback_methodology_pre_registration` — 산식 변경 사전 등록 의무
- `feedback_pm_decision_trail_in_commit` — PM 결정 commit = WHY/DATA/EXPECTED 3요소
- `feedback_source_attribution_discipline` — 신호/룰/임계 단일 명확 출처 + 자체 신호 명시
- `feedback_no_premature_completion_claims` — Q2 / Q5 사전 등록 = *틀만*, 산식 박을 단계는 백테스트 후
