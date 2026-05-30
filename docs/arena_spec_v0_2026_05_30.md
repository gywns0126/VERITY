# ARENA Spec v0 — Pre-Sprint 0 A축 (산식 정합 검증)

**작성일:** 2026-05-30 (토, 잠들기 전 2h 사이드)
**작성자:** Engineer (Claude) / PM (User)
**위치:** `verity-terminal/docs/arena_spec_v0_2026_05_30.md` (6/6 ARENA repo init 시 migrate)
**Status:** Pre-Sprint 0 A축 산출물 (사전 등록 path, [[feedback_methodology_pre_registration]] 정합)

---

## 0. 개요

ARENA = 금융경제 정량 시뮬레이터 (게임 HUD X, simple modern 톤). VERITY hub 의 본능 훈련 surface ([[project_solo_economy_terminal_frame_2026_05_30]] 4-site ecosystem 정합).

본 spec = Pre-Sprint 0 A축 (산식 정합 검증) 산출물. 5 산식의 학술 ref ≥ 2 + 수식 + 파라미터 + 가정·한계 + ARENA 적용 spec 사전 등록.

**RULE 정합:**
- **RULE 7** ✓ — 본인 only, 사전 등록 ("가설 N=0" 명시). 외부 노출 시 라벨 의무
- **RULE 6** ✓ — 자기 산식 dogfood, LLM wrap X
- **RULE 9** ✓ — 글쓰기 규율 ([[feedback_writing_no_pak_overuse]])
- [[feedback_formula_coefficient_fact_check]] ✓ — 학술 ref ≥ 2 per 산식

**다음 단계:**
- 6/1 (월) = B축 자산 historical 통계 측정 (KR ETF / 미장 ETF / 코인 / 레버리지 ETF σ/μ/corr, yfinance/pykrx)
- 6/2 (화) = C축 시뮬 sanity check (Monte Carlo vs 실 historical KS test)
- 6/3 (수) = D축 VERITY 연결 spec
- 6/4 (목) = E축 Supabase trail schema
- 6/5 (금) = 5축 산출물 종합 + 사전 등록 commit
- 6/6 (토) = ARENA Sprint 0 진입

---

## 1. GBM (Geometric Brownian Motion)

### 1.1 정의

주가가 lognormal 분포 따른다는 가정 하에 주가 process 모델링하는 stochastic differential equation.

### 1.2 수식

**연속 시간 SDE:**
```
dS_t = μ S_t dt + σ S_t dW_t
```

**Closed-form 해:**
```
S_t = S_0 · exp((μ - σ²/2) t + σ W_t)
```

**이산 1-step (시뮬 사용):**
```
S_{t+Δt} = S_t · exp((μ - σ²/2) Δt + σ √Δt · Z),  Z ~ N(0, 1)
```

### 1.3 파라미터

| 파라미터 | 의미 | ARENA spec |
|---|---|---|
| S_0 | 초기 가격 | 사용자 시뮬 시점 spot |
| μ | drift (연 expected return) | B축 historical 측정 (자산별) |
| σ | volatility (연 std) | B축 historical 측정 (자산별) |
| Δt | time step | 1 거래일 = 1/252 |
| Z | 표준 정규 random | numpy.random.normal |

### 1.4 가정·한계

- 수익률 = lognormal 분포 (실제 fat tail 위반)
- σ = 상수 (실제 stochastic vol)
- 가격 = 양수 (lognormal property ✓)
- 연속 거래 가능 (실제 = discrete + gap)
- jump 무시
- 점프·skew·kurtosis 미반영 → C축 KS test 의무

### 1.5 ARENA 적용

- Sprint 1 시뮬 엔진 base process
- 자산별 (μ, σ) historical estimate (B축 산출물)
- 1 시뮬 turn = 252 step Monte Carlo (1년)
- 코드: numpy / Framer 코드 컴포넌트 ~50 LOC

### 1.6 학술 ref

1. Hull, J. C. (2009). *Options, Futures and Other Derivatives* (7th ed.). Prentice Hall. Ch 13-14.
2. Glasserman, P. (2003). *Monte Carlo Methods in Financial Engineering*. Springer. Ch 3.
3. Haugh, M. (2017). "Monte Carlo Simulation: IEOR E4603." Columbia University lecture notes.

---

## 2. Monte Carlo Simulation

### 2.1 정의

확률 process 다수 시나리오 generation 으로 expected value / 분포 / risk measure 추정하는 numerical method.

### 2.2 수식

**M 시나리오 generation:**
```
{S^(i)_T}_{i=1..M},  S^(i)_T = GBM(S_0, μ, σ, T, Z^(i))
```

**Expected value 추정:**
```
E[f(S_T)] ≈ (1/M) Σ_{i=1..M} f(S^(i)_T)
```

**표준 오차:**
```
SE = std(f(S^(i)_T)) / √M
```

### 2.3 파라미터

| 파라미터 | 의미 | ARENA spec |
|---|---|---|
| M | 시나리오 수 | 10,000 (default) |
| T | horizon | 252 (1년 거래일) |
| variance reduction | antithetic / control variates | optional (Sprint 1.5+) |

### 2.4 가정·한계

- 시나리오 = IID samples (autocorr / vol clustering 위반 시 bias)
- price process 정확성 (GBM 가정 의존)
- M ↑ = 정밀도 ↑ but computation ↑
- rare event 추정 어려움 (M=10K 으로 99% VaR 부정확)

### 2.5 ARENA 적용

- **본인 본능 훈련 모드** = 1 시뮬 turn 당 1 경로 (M=1, ground truth path 표시)
- **결과 평가 모드** = M=1,000 시나리오 generation → "내 결정 vs Monte Carlo expected" cross-tab
- Sprint 1 = M=1 only (실시간 game-like). Sprint 4 결과 화면 = M=1,000 분포 시각화.

### 2.6 학술 ref

1. Glasserman, P. (2003). *Monte Carlo Methods in Financial Engineering*. Springer. Ch 1-2.
2. Boyle, P. (1977). "Options: A Monte Carlo Approach." *Journal of Financial Economics* 4(3): 323-338.
3. Hull (2009) Ch 21.

---

## 3. Kelly Criterion

### 3.1 정의

장기 expected log wealth growth rate 를 maximize 하는 베팅 사이즈 산정 산식.

### 3.2 수식

**Binary bet:**
```
f* = (p · b - q) / b = (p(b+1) - 1) / b
```
- p: 승률, q = 1-p, b: payoff odds (2:1 → b=2)

**Continuous return (자산 시장):**
```
f* = (μ - r_f) / σ²
```
- μ: expected return, r_f: risk-free rate, σ²: variance

**Merton-style (risk aversion 일반화):**
```
f* = (μ - r_f) / (γ σ²)
```
- γ: risk aversion (Kelly γ=1)

**Fractional Kelly:**
```
f_frac = α · f*,  α ∈ (0, 1]
```
- α = 0.5 (half-Kelly) ≈ 75% growth rate + vol 50% 절감 (MacLean-Ziemba-Blazenko 1992)

### 3.3 파라미터

| 파라미터 | 의미 | ARENA spec |
|---|---|---|
| μ | expected return | B축 historical estimate |
| r_f | risk-free rate | KR 3년 국고채 또는 미장 US 10Y |
| σ | volatility | B축 historical estimate |
| α | fractional Kelly | UI selectable (0.25 / 0.5 / 1.0) |

### 3.4 가정·한계

- **IID returns** (실 시장 = 위반 가능)
- **정확한 p / b / μ / σ estimate 의무** — estimation error = catastrophe (Lo 2024)
- **log utility** (실 사용자 utility ≠ log)
- **bankruptcy 가능** (full Kelly + estimation error)
- **단기 volatile** (long-run optimal but short-run 변동 큼)
- KR 양도세 / 금투세 (2024-12 폐지) 미반영 — Phase 2 정밀화

### 3.5 ARENA 적용

- 본인 본능 검증 = "본인 결정 vs full Kelly vs half-Kelly"
- 레버리지 1x~10x range 사용자 selection → Kelly 권장 비교
- Sprint 1 = Kelly 권장 표시만 (overlay, 강제 X)
- Sprint 3 VERITY 연결 시 = "Brain grade + Kelly = position size 권장" (cross-tab)

### 3.6 학술 ref

1. Kelly, J. L. (1956). "A New Interpretation of Information Rate." *Bell System Technical Journal* 35(4): 917-926.
2. Thorp, E. O. (1969). "Optimal Gambling Systems for Favorable Games." *Review of the International Statistical Institute* 37(3): 273-293.
3. MacLean, L. C., Thorp, E. O., & Ziemba, W. T. (2011). *The Kelly Capital Growth Investment Criterion*. World Scientific.
4. MacLean, L. C., Ziemba, W. T., & Blazenko, G. (1992). "Growth Versus Security in Dynamic Investment Analysis." *Management Science* 38(11): 1562-1585.

---

## 4. Sharpe / MDD / Calmar

### 4.1 Sharpe Ratio

**정의:** 위험 조정 수익률. excess return / volatility ratio.

**수식:**
```
Sharpe = (R_p - R_f) / σ_p
```
- R_p: 포트폴리오 평균 return, R_f: risk-free rate, σ_p: 포트폴리오 std

**연 annualization (IID 가정 의무):**
```
Annual Sharpe = Daily Sharpe × √252
```

**가정·한계:**
- normal return 분포 (fat tail = Sharpe 왜곡)
- 시간 invariant (regime change = Sharpe 왜곡)
- R_f 세전·세후 통일 ([[feedback_rf_pretax_consistency]])
- 음수 skew 자산 = Sharpe 과대 추정
- N 작음 = 표준 오차 ↑ → Bailey-Lopez de Prado 2014 PSR / DSR 보정

**ARENA 적용:**
- 시뮬 결과 평가 metric (Sprint 4 결과 화면)
- 본인 결정 vs benchmark Sharpe 비교
- N≥126 (2027 봄~여름) 후 운영 평가 의미 ([[project_minimum_n_milestones_2026_05_18]])

**학술 ref:**
1. Sharpe, W. F. (1966). "Mutual Fund Performance." *Journal of Business* 39(1): 119-138.
2. Sharpe, W. F. (1994). "The Sharpe Ratio." *Journal of Portfolio Management* 21(1): 49-58.
3. Bailey, D. H., & Lopez de Prado, M. (2014). "The Deflated Sharpe Ratio." *Journal of Portfolio Management* 40(5): 94-107.

### 4.2 Maximum Drawdown (MDD)

**정의:** 최고점 대비 최대 누적 손실.

**수식:**
```
MDD = min_t [(V_t - max_{s≤t} V_s) / max_{s≤t} V_s]
```
- V_t: 자본 시계열, t ∈ [0, T]
- magnitude only 표기 ([[feedback_mdd_magnitude_display]] 정합)

**가정·한계:**
- 시계열 continuous (실 = discrete sampling)
- 시간 window 의존 (MDD 가 window 따라 다름)
- 단일 outlier 영향 ↑

**ARENA 적용:**
- 시뮬 결과 자본 곡선 MDD 시각화 (양수 magnitude)
- 자산별 historical MDD baseline (B축)

**학술 ref:**
1. Magdon-Ismail, M., Atiya, A. F., Pratap, A., & Abu-Mostafa, Y. S. (2004). "An Analysis of the Maximum Drawdown Risk Measure." *Risk Magazine*.
2. Cheridito, P., Furrer, C., & Kropp, K. (2008). "Conditional Drawdown-at-Risk." (alternative measure)

### 4.3 Calmar Ratio

**정의:** 연 CAGR / |MDD| ratio.

**수식:**
```
Calmar = CAGR / |MDD|
```
- CAGR = compound annual growth rate
- |MDD| = magnitude (양수)

**가정·한계:**
- MDD window 통일 의무 (보통 3년)
- N 작음 = 신뢰 ↓
- window dependence 큼
- Sharpe 보다 단일 outlier 민감

**ARENA 적용:**
- 시뮬 결과 평가 metric (Sharpe 와 병행)
- 1년 시뮬 Calmar = baseline 부족 (3년+ 권장)
- Sprint 4 결과 화면 보조 metric

**학술 ref:**
1. Young, T. W. (1991). "Calmar Ratio: A Smoother Tool." *Futures Magazine*.
2. Bajaj AMC (2024). "Calmar Ratio: Meaning, Formula, and How It Helps Measure Investment Risk." (modern review)

---

## 5. Black-Scholes (Sprint 1.5 prep)

### 5.1 정의

European 옵션 가격 closed-form formula. risk-neutral measure 활용 PDE 해.

### 5.2 수식

**Call option:**
```
C = S_0 · N(d_1) - K · e^(-rT) · N(d_2)

d_1 = (ln(S_0/K) + (r + σ²/2) T) / (σ √T)
d_2 = d_1 - σ √T
```
- C: 콜옵션 가격, S_0: spot, K: strike, r: risk-free, T: 만기, σ: vol
- N(·): 표준 정규 누적분포

**Put-call parity:**
```
P = C - S_0 + K · e^(-rT)
```

**Greeks (1차):**
- Δ (delta): ∂C/∂S = N(d_1)
- Γ (gamma): ∂²C/∂S² = φ(d_1) / (S σ √T)
- ν (vega): ∂C/∂σ = S √T · φ(d_1)
- Θ (theta): -∂C/∂t
- ρ (rho): ∂C/∂r

### 5.3 파라미터

| 파라미터 | 의미 | ARENA spec |
|---|---|---|
| S_0 | spot | 시뮬 시점 가격 |
| K | strike | 사용자 선택 (ATM ±10%) |
| T | 만기 | 1주 고정 (단순화) |
| r | risk-free | KR 3년 국고채 |
| σ | implied vol | historical vol 사용 (vol surface 무시) |

### 5.4 가정·한계

- **σ = 상수** (vol surface / smile / skew 무시)
- continuous trading
- 무차익 거래
- lognormal 가격 process
- **European only** (American 옵션 X)
- jump 무시
- 거래 비용 X (실 KOSPI200 옵션 거래 비용 ~0.3%)

### 5.5 ARENA 적용 (Sprint 1.5)

- Sprint 1 = 옵션 X (Sprint 1.5 prep)
- 옵션 콜·풋 = Black-Scholes closed-form 가격
- 사용자 옵션 선택 시 가격 자동 계산 (UI 표시)
- vol surface 무시 = 단순화 (자산별 historical vol 1 값)
- Greeks 표시 = Sprint 2+ (Delta / Vega 만)

### 5.6 학술 ref

1. Black, F., & Scholes, M. (1973). "The Pricing of Options and Corporate Liabilities." *Journal of Political Economy* 81(3): 637-654.
2. Merton, R. C. (1973). "Theory of Rational Option Pricing." *Bell Journal of Economics and Management Science* 4(1): 141-183.
3. Hull (2009) Ch 15.

---

## 6. 사전 등록 결정 (Lock)

본 spec 등록 5 산식 = ARENA Sprint 1-1.5 구현 baseline. 산식 변경 시 RULE 7 사전 등록 의무 ([[feedback_methodology_pre_registration]]).

| 산식 | Sprint | Lock 산식 |
|---|---|---|
| GBM | Sprint 1 | Hull-Glasserman base, σ historical (B축) |
| Monte Carlo | Sprint 1 (M=1) / Sprint 4 (M=1000) | Glasserman base |
| Kelly criterion | Sprint 1 (overlay) | full + half (α=0.5 default) |
| Sharpe / MDD / Calmar | Sprint 4 (결과 화면) | 학술 표준 산식 |
| Black-Scholes | Sprint 1.5 (옵션) | 1주 만기 고정, vol surface 무시 |

**산식 변경 trigger 요건 ([[feedback_methodology_pre_registration]] 정합):**
- N≥50 실 시뮬 trail + walk-forward 1회만 ([[feedback_threshold_calibration_overfit_guard]])
- PM 승인 + commit message WHY/DATA/EXPECTED 3요소 ([[feedback_pm_decision_trail_in_commit]])
- 변경 횟수 ≤ 1회/산식 (자유 tweak 금지, [[feedback_methodology_pre_registration]])

---

## 7. 다음 단계

- **6/1 (월)** = B축 자산 historical 통계 (KR ETF / 미장 ETF / 코인 / 레버리지 ETF σ/μ/corr 측정). TIDE N=2 audit 병행.
- **6/2 (화)** = C축 시뮬 sanity check (Monte Carlo vs 실 5년 historical KS test, GBM 가정 자산별 skew/kurtosis 표기)
- **6/3 (수)** = D축 VERITY 연결 spec (`portfolio.json` schema 검증, Brain grade A/B/C/D 정합, Framer fetch CORS path)
- **6/4 (목)** = E축 Supabase trail schema (의사결정 trail 테이블 design, RLS 본인 only, Brain learning consumer 산식)
- **6/5 (금)** = 5축 산출물 종합 + 사전 등록 commit (본 spec v1)
- **6/6 (토)** = ARENA Sprint 0 진입 (Framer canvas + TIDE design token import + Framer password gate)

---

## 부록 A — 관련 메모리

- [[project_arena_kickoff_2026_05_30]] — ARENA kickoff + Sprint 분해
- [[project_solo_economy_terminal_frame_2026_05_30]] — 4-site ecosystem frame
- [[feedback_methodology_pre_registration]] — 사전 등록 path
- [[feedback_formula_coefficient_fact_check]] — 학술 ref ≥ 2 의무
- [[feedback_threshold_calibration_overfit_guard]] — 임계 조정 곡선 맞추기 회피
- [[project_minimum_n_milestones_2026_05_18]] — N=60/126/252/684 마일스톤
- [[feedback_rf_pretax_consistency]] — R_f 세전·세후 통일 의무
- [[feedback_mdd_magnitude_display]] — MDD magnitude only 표기
