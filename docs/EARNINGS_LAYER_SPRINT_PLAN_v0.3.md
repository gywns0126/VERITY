# VERITY 미장 강화 Sprint 1 — Earnings Layer (v0.3.1)

**작성:** 2026-05-04
**대상:** Claude Code
**버전 history:** v0.1 (Claude 베테랑 페르소나 초안) → v0.2 (Claude Code self-review) → v0.3 (코드베이스 실측 정합) → **v0.3.1 (Perplexity 외부 fact-check 3건 반영)**
**다음 정정:** v1.0 — P-1 시스템 관찰 결과 반영 + 5/16 verdict 후 진입 확정 시
**전제:** ESTATE 작업은 본 sprint chain 동안 후순위, 각 sprint verdict 시점에 우선순위 재평가

---

## 0. 핵심 변경 사항

### 0-A. v0.3 → v0.3.1 (Perplexity fact-check 반영, 2026-05-04)

| # | 항목 | v0.3 | v0.3.1 |
|---|---|---|---|
| 1 | PEAD IC 출처 | "B&T 1989/1990" 인용 | **B&T 원전은 IC 미제시 — L/S 스프레드만. IC 0.04~0.08은 후속 연구 컨센서스로 재인용** |
| 2 | actual EPS source | yfinance 확장 / SEC EDGAR / Polygon / Alpha Vantage 후보 | **SEC EDGAR XBRL 권고 확정 (무료, PIT timestamp). Polygon/AV는 PIT 부재로 부적합** |
| 3 | Surprise 기대모형 | consensus 가정 | **Random Walk 기대모형 (전분기 EPS = 기대치) — B&T 1989 원전 방법론. consensus PIT historical 무료 source 부재 (IBES/Bloomberg만)** |
| 4 | revision_score backtest 부재 근거 | "historical 깊이 부족" | **무료 source 자체 부재 (Polygon/AV PIT snapshot 없음). 근본 원인 명시** |
| 5 | 잔차 IC 0.5 임계 | "자체 결정" | **학계 표준 부재 확정 + 실무 관행 0.2~0.3보다 느슨 명시 + Sprint 2 FF5 추가 시 0.3 재조정 검토** |

### 0-B. v0.2 → v0.3 (코드베이스 실측 정합, 2026-05-04)

| # | 항목 | v0.2 (가정) | v0.3 (코드 실측) |
|---|---|---|---|
| 1 | 메모리 인용 | "메모리 #20/12/3/4/KI-4/룰 #8-x" | **모두 hallucination 확정 — 본문 인용 제거, 룰 자체로 풀어 기술** |
| 2 | Earnings 데이터 source | Finnhub free tier | **yfinance (실재) — actual EPS / consensus / SUE는 추가 source 필요** |
| 3 | fact_score 범위 | 0.0 ~ 1.0 | **0 ~ 100 정수** (`api/intelligence/verity_brain.py:_compute_fact_score`) |
| 4 | fact_score sub-score 수 | 6개 가정 | **13개** (verity_constitution.json `fact_score.weights`) |
| 5 | fact_score 시그니처 | `(ticker, current_date)` | **`(stock, portfolio, macro_override)`** |
| 6 | 가중치 동결 정합성 | "v1 동결" 단순 | **V6 IC/ICIR 피드백 자동 조정 이미 박힘 — base weight 동결 vs 자동 multiplier 적용 구분 필요** |
| 7 | Shadow mode 코드 | trial = v1 그대로 (측정 불가) | **trial = v1 base + w_earnings × earnings_score** 단일 path |
| 8 | 5/16 verdict 정의 | placeholder | **= ATR Phase 0 (SMA→Wilder EMA) 효과 측정 + 운영 안정성 판정 종료 시점** |
| 9 | Sprint 일정 | 1만 8주, 2/3 각 4주 | **각 sprint 6~8주 보수, 총 5~6개월** |
| 10 | revision_score backtest | scope 포함 | **scope 제외, live forward IC only (5/4 prep 시작 → 6월 중순 40일치 확보)** |
| 11 | IC 합격선 | 0.03 | **0.04 (후속 연구 컨센서스 baseline 0.04~0.08의 약 50% 보수, 본 sprint 자체 결정)** |
| 12 | Rebalance | daily 가정 | **weekly 고정** |
| 13 | Momentum collinearity | 없음 | **잔차 IC 검증 추가 (잔차 IC ≥ raw IC × 0.5, 본 sprint 자체 결정 — 직교성 학문 표준 부재)** |
| 14 | sparse vs always-on | 미명시 | **P-1에서 결정 의무** |
| 15 | 가중치 출처 | 막연 | **0.4/0.3/0.3 = Brain v0 self-decision, fact_score v2 재산출 sprint(9월 말)에서 backtest 기반 재산출** |
| 16 | survivorship/timezone | risk 언급 | **정직 인정 섹션 분리 (§12)** |

---

## 1. Sprint 1 목표

미장 영역의 **earnings cycle layer 부재**를 해소한다. 자체 평가(self-assessment) 5/10 → 7.5/10. 점수 자체는 prep §2-2에서 KR vs US fact_score 분포 비교로 검증 큐잉.

미장 alpha의 robust 단일 source인 PEAD + Earnings Surprise + Estimate Revision을 fact_score sub-score로 통합. 매 분기 4회 alpha window 시스템적으로 포착.

### 1-1. In-scope

- PEAD strategy (post-earnings drift 14d~60d window)
- Earnings Surprise (event ±5d, SUE 표준화)
- Estimate Revision (live forward only — historical backtest 불가)
- 통합 `earnings_score` sub-score
- fact_score **trial path**에 추가 (shadow mode, v1 base 가중치 영향 0)
- backtest IC / ICIR + Momentum collinearity 잔차 IC

### 1-2. Out-of-scope

- FF5 factor (Sprint 2)
- 미장 regime split (Sprint 3)
- fact_score v2 가중치 재산출 (별도 sprint, 9월 말)
- Earnings call transcript NLP (장기)
- Guidance change 추적 (장기)

### 1-3. 산출물

| # | 산출물 | 위치 (예상, P-1에서 정정 가능) |
|---|---|---|
| 1 | `earnings_layer.py` — score 계산 모듈 | `api/factors/earnings_layer.py` (또는 `api/intelligence/earnings_layer.py`) |
| 2 | `earnings_data_fetcher.py` — actual EPS / consensus 수집 (yfinance + 보강 source) | `api/collectors/earnings_data_fetcher.py` |
| 3 | `eps_estimate_snapshot.py` — daily snapshot collector (prep §2-1) | `api/collectors/eps_estimate_snapshot.py` |
| 4 | `data/metadata/earnings_history.jsonl` — invalidate flag 지원 | jsonl |
| 5 | `data/metadata/eps_estimates.jsonl` — invalidate flag 지원 | jsonl |
| 6 | `verity_brain.py` 수정 — earnings_score trial path 추가 | 기존 파일 수정 |
| 7 | `test_earnings_layer.py` | `tests/factors/` |
| 8 | `BACKTEST_REPORT_earnings_v1.md` — IC/ICIR + collinearity | `docs/backtest/` |

---

## 2. Prep Phase (5/4 ~ 5/16)

**Critical:** prep는 코드 변경 0, fact_score 영향 0, 데이터·문서·관찰만. Phase 0 단일 변수 통제 위반 회피.

### 2-1. revision_score용 자체 EPS estimate snapshot 누적 (즉시 시작)

revision_score는 historical 시계열 못 잡으니 **누적 빨리 시작 = alpha**. 5/4 시작 → 5/16에 12일치, 6월 중순 backtest 시점에 약 40일치 확보.

작업 명세:
- `api/collectors/eps_estimate_snapshot.py` 신규
- 매일 1회 yfinance 또는 추가 source로 EPS estimate fetch
- `data/metadata/eps_estimates.jsonl` append, line 단위 invalidate flag 지원
- cron 또는 GitHub Actions 등록
- **fact_score 호출 0** — 데이터 수집 only

### 2-2. KR vs US fact_score 분포 비교 (self-assessment 5/10 검증)

- `data/holdings/` 또는 `data/analysis/` 기존 운영 결과에서 KR / US 종목별 fact_score sub-score 분포 추출
- 13 sub-score 각각 KR vs US mean/std/IC 격차 측정
- "earnings cycle axis가 미장에서 진짜 1순위 약점인가" 정량 답
- 결과에 따라 Sprint 1 우선순위 재평가 가능

### 2-3. P-1 시스템 관찰 5건 실측 (§3)

코드 변경 0, 측정만. 5/16 verdict와 독립.

### 2-4. Universe 정의 + survivorship 정책

- 현재 미장 universe 실측 (S&P 500 / 자체 universe)
- delisted ticker 처리:
  - **옵션 A:** current universe만 (survivorship bias 인정 + report inscription)
  - **옵션 B:** historical constituent (가능 source 별도 조사)

### 2-5. PEAD/Surprise 학문 reference 출처 audit

§14 reference 1차 검증 — 인용 정확성, baseline IC 출처 명확화.

### 2-6. Prep phase 산출물

5/16 verdict 시점 보유:
- 12일치 EPS snapshot
- KR vs US sub-score 분포 비교 보고서
- P-1 5건 결과
- universe + survivorship 정책안
- reference audit 결과
- v1.0 진입 ready 명령서 골격

---

## 3. P-1 시스템 관찰 (Claude Code 실측 의무)

v0.3은 다음 5건을 가정 기반으로 작성. Claude Code는 prep 내 5건 실측 후 보고. 가정 1건이라도 어긋나면 즉시 멈춤 + v1.0 정정.

### P-1.1. Earnings 데이터 source quota 실측

- **현재 코드는 yfinance 사용** (`api/collectors/earnings_calendar.py`). next_earnings 일자만 수집. actual EPS / consensus EPS / SUE 계산용 데이터 없음
- **외부 fact-check (Perplexity 2026-05-04) 결과:**
  - **Polygon free tier:** estimate revision 미제공 + 2년 히스토리만 → 본 sprint backtest 불가
  - **Alpha Vantage:** EPS estimate 일부 제공하나 PIT (Point-in-Time) snapshot 없음 → lookahead bias 필연
  - **SEC EDGAR XBRL (무료):** 실제 EPS 발표치 + 제출일 timestamp 제공. consensus 추정치는 **없음**
  - **FMP (Financial Modeling Prep) free 250 req/day:** 컨센서스 제공하나 PIT 보장 X
  - **Refinitiv IBES / Bloomberg:** 완전한 PIT 컨센서스 historical은 사실상 이쪽만. 수천 달러/월
- **권고 source 조합 (Sprint 1 무료 가능):**
  - **PEAD/Surprise: SEC EDGAR XBRL + Random Walk 기대모형** (전분기 EPS = 기대치)
    - Bernard & Thomas (1989) **원전 방법론과 동일** — 당시도 컨센서스 없이 RW 기대모형 사용
    - SUE = (actual_eps - prev_quarter_eps) / std(historical_surprises) 계산 가능
  - **Revision: PIT 데이터 부재 → backtest 진짜로 불가능** (소스 자체 부재가 근본 원인). live forward only 결정 강화
- 다음 결정 필요:
  - yfinance + SEC EDGAR XBRL hybrid 채택 vs FMP free 추가 채택
  - SEC EDGAR XBRL fetcher 자체 구축 비용 추정
- yfinance rate limit (분단위 throttling 알려짐) 측정
- **결과 보고:** "actual EPS source 결정 (EDGAR XBRL 권고) + Random Walk 기대모형 채택 가/부 + 분단위 호출 한계 + universe N 종목 daily fetch 비용"

### P-1.2. fact_score 13 sub-score 통합 방식 결정

- 실제 fact_score sub-score 13개 (verity_constitution.json `fact_score.weights`):
  - multi_factor (0.1876), consensus (0.1279), prediction (0.0853), backtest (0.0682), timing (0.0597), commodity_margin (0.0341), export_trade (0.0682), moat_quality (0.0853), graham_value (0.0682), canslim_growth (0.0682), analyst_report (0.0784), dart_health (0.049), perplexity_risk (0.02)
- earnings_score 통합 방식 결정:
  - **(a) 신규 14번째 sub-score 추가** (trial path만, base 가중치 영향 0)
  - **(b) 기존 multi_factor 또는 backtest 카테고리 sub-component로 박기**
- **earnings_score sparse vs always-on 결정:**
  - sparse: event window 외 score=0.5 중립 (가중 합산 시 영향 0)
  - always-on: 모든 시점 0.0~1.0 활성 (revision_score 통해 보강)
- **결과 보고:** "통합 방식 (a)/(b) 권고 + sparse/always-on 권고 + 근거"

### P-1.3. V6 IC 피드백 자동 조정과 v1 base 가중치 정합

- `_compute_fact_score`는 V6 IC/ICIR 피드백으로 가중치를 자동 조정 (`_load_ic_adjustments()`, `_IC_TO_WEIGHT_KEY`)
- "v1 가중치 동결"이 의미하는 것:
  - **(α) base weight (constitution.json) 동결, IC multiplier 적용은 허용**
  - **(β) IC multiplier도 본 sprint 동안 동결**
  - **(γ) earnings_score 추가 시 IC 자동 조정 hook에 등록 안 함 (trial path만)**
- **결과 보고:** "현재 V6 운영 모드 + earnings_score 추가 시 (α)/(β)/(γ) 권고"

### P-1.4. backtest_archive schema + factor_decay.py 인터페이스 실측

- `api/quant/alpha/factor_decay.py` 인터페이스 (입력 형태, IC 측정 공식)
- 기존 backtest_archive schema (PEAD strategy 결과 통합 vs 분리)
- **결과 보고:** "factor_decay.py 재사용 가능 여부 + PEAD 결과 누적 위치 권고"

### P-1.5. 미장 universe 실측 + REGIME 변수 구조

- 미장 universe 정의 위치 (S&P 500 / 자체)
- REGIME 변수 country-aware인지 (`scripts/historical_replay.py`, `api/config.py`, `api/analyzers/macro_adjustments.py`, `api/analyzers/yieldcurveanalyzer.py` 검토)
- Sprint 3 미장 regime 진입 시 정합성 영향 평가
- **결과 보고:** "미장 universe 정의 + REGIME 분리 권고"

---

## 4. P0 — Earnings Layer 설계

### 4-1. earnings_score 정의

`earnings_score`는 **0~100 정수** (fact_score와 동일 스케일). 3 sub-score 가중 평균:

```
earnings_score = w1 * pead_score + w2 * surprise_score + w3 * revision_score

초기 가중치 (Brain v0 self-decision, backtest 미실시 추정):
w1 = 0.4 (PEAD)
w2 = 0.3 (Surprise)
w3 = 0.3 (Revision)
```

**Critical:** 위 가중치 출처는 **본 sprint 자체 결정**, 학문 baseline 가중 비례 추정. fact_score v2 가중치 재산출 sprint(9월 말)에서 backtest 결과 기반으로 재산출.

각 sub-score는 0~100 정수.

### 4-2. PEAD score

```python
def calc_pead_score(ticker: str, current_date: date) -> int:
    """
    Post-Earnings-Announcement Drift score (0~100).

    SUE (Standardized Unexpected Earnings) 분위 기반.
    최근 earnings 발표 후 14d ~ 60d window에서 활성.

    - 100: SUE 최상위 분위 + drift window 진입 직후 (14d)
    -  50: SUE 중립 OR drift window 외 (sparse)
    -   0: SUE 최하위 분위
    """
    # 1. 최근 earnings event 조회 (earnings_history.jsonl)
    # 2. 발표 후 경과일 d 계산
    # 3. drift window 14 ≤ d ≤ 60 외이면 return 50 (중립)
    # 4. SUE = (actual_eps - consensus_eps) / std(historical_surprises)
    # 5. SUE 분위 5등분 → score 매핑 (Q5=100, Q3=50, Q1=0)
    # 6. drift window decay: 14d 100% → 60d 0% 선형 감쇠 (score 50 방향으로 회귀)
```

### 4-3. Earnings Surprise score

```python
def calc_surprise_score(ticker: str, current_date: date) -> int:
    """
    Earnings Surprise score (event ±5d window, 0~100).
    window 외: 50 (중립).
    """
    # 1. 최근 earnings event 조회
    # 2. |오늘 - 발표일| > 5d이면 return 50
    # 3. SUE 계산 → 분위 매핑 (Q5=100, Q3=50, Q1=0)
```

PEAD vs Surprise 시간축 mutually exclusive — Surprise는 ±5d immediate, PEAD는 14d~60d post-event.

### 4-4. Estimate Revision score (live forward only)

```python
def calc_revision_score(ticker: str, current_date: date) -> int:
    """
    Estimate Revision score (leading indicator, 0~100).
    Live forward only — historical backtest 불가.
    자체 누적 eps_estimates.jsonl 사용.
    """
    # 1. eps_estimates.jsonl에서 최근 30일 snapshot 조회
    # 2. invalidate=true line 제외
    # 3. estimate 변화율 = (latest - earliest) / earliest
    # 4. 변화율 → score 매핑 (sigmoid 또는 분위)
    #    +5% 이상: 100, 0%: 50, -5% 이하: 0
```

revision_score는 **backtest scope 제외**. 5/4 prep 시작 → 6월 중순 40일치로 live forward IC만 측정.

### 4-5. earnings_data_fetcher.py 설계

P-1.1 결과에 따라 최종 결정. 권고안 (Perplexity fact-check 반영):

| 데이터 | source 권고 | 빈도 | 위치 |
|---|---|---|---|
| earnings calendar (next_earnings 일자) | yfinance (기존 `earnings_calendar.py` 재사용) | 1x/day | `data/metadata/earnings_calendar.jsonl` |
| actual EPS (PEAD/Surprise용) | **SEC EDGAR XBRL 자체 fetcher** (무료, PIT timestamp 제공) | 1x/day | `data/metadata/earnings_history.jsonl` |
| Surprise 기대치 산출 | **Random Walk 기대모형** (전분기 EPS = 기대치, B&T 1989 원전 방법론) | — | 코드 내 산출 |
| EPS estimate snapshot (revision용) | yfinance + 자체 누적 (prep §2-1 시작) | 1x/day | `data/metadata/eps_estimates.jsonl` |

모든 jsonl은 line 단위 `invalidate` flag 지원 (§10).

**Critical:** consensus 추정치 PIT historical은 무료 source 부재 (Refinitiv IBES / Bloomberg만 가능, 수천 달러/월). 따라서:
- PEAD/Surprise는 RW 기대모형으로 대체 → Sprint 1 무료 진입 가능
- Revision은 historical backtest 불가, 자체 누적으로 live forward only

---

## 5. P0 — fact_score 통합 (Shadow Mode)

### 5-1. earnings_score plug-in 지점

P-1.2 결과에 따라 통합 방식 (a) 신규 14번째 sub-score / (b) 기존 카테고리 sub-component 결정.

**가정안 (a) 시 의사 코드:**

```python
def _compute_fact_score(stock, portfolio=None, macro_override=None):
    const = _load_constitution()
    w_raw = (const.get("fact_score") or {}).get("weights") or {}
    w = dict(w_raw)
    # ... (V6 IC 자동 조정, regime-aware 등 기존 로직 그대로)

    # 기존 13 sub-score 계산
    sub_scores = {
        "multi_factor": ...,
        "consensus": ...,
        # ... 13개 그대로
    }
    fact_score_v1 = sum(sub_scores[k] * w[k] for k in sub_scores)
    # → 0~100 범위 정수

    # === Shadow mode: earnings_score trial path ===
    earnings_score = calc_earnings_score(stock["ticker"], current_date)  # 0~100
    w_earnings_trial = const.get("fact_score_trial", {}).get("w_earnings", 0.05)
    # base 가중치 합 1.0 유지 + earnings 별도 확장 (trial 영역에서만)
    fact_score_trial = fact_score_v1 + w_earnings_trial * earnings_score
    # → trial path는 0~105 범위 (운영 path 영향 0)

    return {
        "fact_score": fact_score_v1,           # 운영 path (V6 자동 조정 그대로)
        "fact_score_trial": fact_score_trial,  # 측정용 (Sprint 1 검증)
        "sub_scores": sub_scores,
        "earnings_breakdown": {
            "earnings_score": earnings_score,
            "pead": ...,
            "surprise": ...,
            "revision": ...,
        }
    }
```

**Critical:**
- 운영 path `fact_score_v1`는 기존 V6 IC 자동 조정 그대로. earnings_score는 IC 자동 조정 hook 등록 X (P-1.3 (γ) 권고).
- trial path `fact_score_trial`에서만 earnings_score 적용. 두 path 병렬 운영하며 Sprint 1 V1 backtest로 IC/ICIR 비교.
- `w_earnings_trial` 초기값 0.05 — 본 sprint 자체 결정. v2 재산출 sprint에서 정정.

### 5-2. v1 운영 영향 격리 보장

- 운영 시그널·alert·UI는 모두 `fact_score`만 참조 (변경 X)
- `fact_score_trial`은 backtest report + admin dashboard에만 노출 (운영 결정 영향 0)
- earnings_score 호출 실패 시 try/except 격리 → trial path만 영향, v1 무관

---

## 6. P0 — Backtest 설계

### 6-1. Backtest scope

| 항목 | 값 | 출처 |
|---|---|---|
| 기간 | 2021-01 ~ 2026-04 (5년) | yfinance 무료 historical 한계 추정 — P-1에서 정확 측정. SEC EDGAR XBRL은 더 깊은 historical 가능 (10년+), 가능하면 10년(2016~) 적용 |
| Universe | P-1.4 결정 (S&P 500 가정) | survivorship 정책 §2-4 결과 적용 |
| Frequency | **Weekly rebalance** | PEAD drift window 14d~60d 정합 + transaction cost 누적 회피 |
| Benchmark | S&P 500 등가중 | |
| Surprise 기대모형 | **Random Walk** (전분기 EPS = 기대치) | B&T 1989 원전 방법론. consensus PIT 부재 시 표준 대체 |

### 6-2. Backtest scope 제한

| Sub-score | Backtest | Live forward only |
|---|---|---|
| pead_score | ✅ | |
| surprise_score | ✅ | |
| **revision_score** | **❌** | **✅** |

revision_score historical 시계열 부재 → backtest 제외, prep §2-1 자체 누적 → 6월 중순부터 live forward IC.

### 6-3. 측정 지표

- **IC:** earnings_score vs forward 14d return Spearman
- **ICIR:** mean(IC) / std(IC)
- **Quintile spread:** 최상위 - 최하위 분위 forward return
- **Decay:** 시간 축 IC 감쇠
- **By regime:** bull / bear / range (Sprint 3 박힌 후 재측정 가능)

### 6-4. Momentum collinearity 검증

PEAD는 학문적으로 momentum sub-component로 분류되기도 함. fact_score 13 sub-score 중 **canslim_growth (0.0682)**, **timing (0.0597)** 등이 momentum 성격 일부 포함 — 직교성 검증 필수.

검증 절차:
1. 상관계수: earnings_score vs canslim_growth / timing / multi_factor 각각 Pearson + Spearman
2. **잔차 IC:**
   - 위 3 sub-score를 explanatory variable로 회귀 → earnings_score residual
   - residual의 IC 측정
   - **잔차 IC ≥ raw IC × 0.5** (본 sprint 자체 결정 — 직교성 학문 표준 부재, 절반 이상이면 직교성 인정)
3. **Incremental Sharpe:**
   - 기존 13 sub-score만으로 구성한 portfolio Sharpe
   - earnings_score 추가 portfolio Sharpe
   - 차이 > 0이어야 추가 alpha 인정

**임계 0.5의 한계 인지 (Perplexity fact-check 반영):**
- 학계 단일 표준 부재 확정. 실무 관행은 분산: AQR/Barra류 0.3, 일부 펀드 Pearson r 0.2, VIF<5 등
- 본 sprint 0.5는 실무 관행보다 **느슨한 편**. 현재 13 sub-score + earnings = 14개에선 허용
- **Sprint 2 FF5 추가 (16+ factor) 시 0.3으로 재조정 검토** — 팩터 수 증가 시 암묵적 중복 누적 risk
- v2 가중치 재산출 sprint(10월 말~)에서 임계 자체 재평가

### 6-5. 합격 기준 (Sprint 1 V1 통과 = §7-1 게이트와 동일)

| 지표 | 합격 임계 | 근거 |
|---|---|---|
| IC mean | ≥ 0.04 | **후속 연구 컨센서스 baseline 0.04~0.08의 약 50% 보수** (B&T 원전은 IC 미제시, L/S 스프레드만 — Perplexity audit 결과). 본 sprint 자체 결정 |
| ICIR | ≥ 0.5 | 단일 factor 표준 |
| Quintile spread (annualized) | ≥ 2% | 학문 PEAD 4~8%의 절반 보수 |
| 잔차 IC (collinearity 후) | ≥ raw IC × 0.5 | 본 sprint 자체 결정 |
| Incremental Sharpe | > 0 | 기존 13 sub-score 대비 추가 alpha |

5개 지표 모두 통과해야 Sprint 1 → Sprint 2 게이트 통과. 1개라도 실패 시 정정 cycle.

---

## 7. Sprint 결합 — fact_score 진화 path

```
fact_score v1 (현재, 13 sub-score, base 가중치 동결 + V6 IC 자동 조정)
  ↓
+earnings_score (Sprint 1, 5/16~7월) — 본 명령서, trial path
  ↓
+FF5 profitability/investment (Sprint 2, 7~9월)
  ↓
+US regime split (Sprint 3, 9~10월)
  ↓
fact_score v2 가중치 재산출 sprint (10월 말 ~ 11월) — 별도 명령서
```

### 7-1. Sprint 진입 게이트

| 게이트 | 조건 |
|---|---|
| Sprint 1 → 2 | §6-5 합격 기준 5개 모두 통과 + V4 cron 무사고 1주일 |
| Sprint 2 → 3 | FF5 직교성 검증 통과 + V4 cron 무사고 1주일 |
| → v2 재산출 sprint | 3 sprint 모두 V4 통과 + 운영 데이터 누적 ≥ 8주 |

게이트 미통과 = 다음 sprint 진입 금지, 정정 cycle 우선.

### 7-2. 일정 추정 (각 sprint 6~8주 보수)

| Sprint | 기간 | 종료 |
|---|---|---|
| Prep | 5/4 ~ 5/16 (12일) | 5/16 verdict |
| Sprint 1 (Earnings) | 5/16 ~ 7월 중순 (~8주) | V4 cron 무사고 1주일 |
| Sprint 2 (FF5) | 7월 중순 ~ 9월 초 (~6주) | FF5 직교성 + V4 cron |
| Sprint 3 (미장 regime) | 9월 초 ~ 10월 중순 (~6주) | yield curve + credit spread |
| v2 가중치 sprint | 10월 말 ~ 11월 중순 (~3주) | 재산출 |

**총 5~6개월 sprint chain.** v0.2의 비대칭 일정(1=8주, 2/3=4주)을 일관 6~8주로 정정 — 후속 sprint도 P-1·V1·V4 cycle 동일 부하.

### 7-3. 5/16 verdict 정의

`project_atr_phase0_migration` 결정 20에 따라:
**ATR Phase 0 (SMA → Wilder EMA(14)) 효과 측정 + 운영 안정성 판정 종료 시점 = 5/16.**

verdict 통과 조건:
- ATR Phase 0 secret deployment(5/3 시작) 운영 14일 무사고
- SMA vs Wilder EMA stop-loss 효과 측정 결과 부정 효과 없음
- W2/W3 wiring 격리 진입 가능 판정

verdict 통과 시 본 sprint chain Sprint 1 진입.

---

## 8. Lifecycle 단계

| 단계 | 내용 | 통과 조건 |
|---|---|---|
| **Prep** | 5/4 ~ 5/16, 데이터 누적 + P-1 + universe + reference audit | 5/16 verdict |
| **P-1** | 시스템 관찰 5건 (prep 중) | PM 보고 + v1.0 정정 결정 |
| **P0** | Contract 확정 (v1.0) | PM 승인 |
| **P1** | Mock 구현 (더미 데이터) | unit test 통과 |
| **P2** | Wire (실데이터 연동) | integration test 통과 |
| **P3** | Harden (quota + error handling + retry + invalidate flag) | edge case 통과 |
| **V1** | Backtest (collinearity 포함) | §6-5 5개 지표 모두 통과 |
| **V2** | fact_score trial path 통합 | v1 운영 영향 0 확인 |
| **V3** | Trial 운영 (1주일 shadow) | hit rate cycle 정상 |
| **V4** | cron 통합 + 무사고 1주일 운영 | Sprint 2 게이트 |

---

## 9. Claude Code 멈춤 정책

다음 트리거 발생 시 즉시 멈춤 + PM 보고:

- **[A] 강제 멈춤:** 코드 + 테스트 단위 종료 시 (P0 → P1 → P2 등 단계 전환)
- **[B] 자발 멈춤:** 패턴 차용 작업 (기존 factor 함수 차용)
- **[C] 즉시 멈춤 트리거:**
  1. requirements.txt 변경 발생
  2. 명령서 외 신규 파일 생성
  3. 기존 패턴 위반 의심
  4. **P-1 5건 중 1건이라도 가정과 어긋남**
  5. LLM 모델 변경
  6. 1시간 이상 단일 작업 지속

---

## 10. 롤백 정책

### 10-1. V4 cron 실패 시 격리

| 실패 유형 | 격리 메커니즘 | v1 영향 |
|---|---|---|
| 데이터 source API timeout | retry + fallback (다음 cron 재시도) | 0 |
| jsonl write 실패 | 해당 line `invalidate=true` flag | 0 |
| earnings_score 계산 NaN/Exception | try/except → trial path만 fallback (50 중립값) | 0 |
| backtest IC 합격선 미달 | trial path 동결 + 정정 cycle | 0 |

### 10-2. jsonl invalidate flag 메커니즘

```jsonl
{"date":"2026-05-04","ticker":"AAPL","eps_estimate":1.45,"snapshot_ts":"2026-05-04T10:00:00Z","invalidate":false}
{"date":"2026-05-05","ticker":"AAPL","eps_estimate":1.50,"snapshot_ts":"2026-05-05T10:00:00Z","invalidate":true,"invalidate_reason":"source returned cached data, snapshot_ts mismatch"}
```

- 데이터 오염 발견 시 line 단위 flag
- score 계산 시 `invalidate=false` line만 사용
- 파일 삭제 X (audit trail 유지)

### 10-3. earnings layer 전체 비활성화 fallback

`fact_score_trial` 산출 try/except 격리. earnings_score 호출 실패 시:
- `fact_score_trial = fact_score_v1` (영향 0)
- log warning + admin alert

운영 path `fact_score`는 어떤 경우에도 영향 0.

---

## 11. P-1 보고 양식

```
## P-1 시스템 관찰 결과

### 결정사항 표
| 항목 | 가정 (v0.3) | 실측 결과 | 정정 필요 |
|---|---|---|---|
| earnings 데이터 source | yfinance + 추가 source 가능 | (a)/(b)/(c) 권고 | Y/N |
| fact_score 통합 방식 | sub-score (a) 또는 (b) | 권고 | Y/N |
| sparse vs always-on | 미결정 | 권고 | Y/N |
| V6 IC 자동 조정 정합 | (γ) hook 미등록 | (α)/(β)/(γ) 권고 | Y/N |
| factor_decay.py 재사용 | 가능 | 가능/불가 | Y/N |
| 미장 universe | S&P 500 | 실측 | Y/N |
| REGIME 분리 | country-aware | 실측 | Y/N |

### Prep phase 산출물
- EPS estimate snapshot 누적: X일치
- KR vs US sub-score 분포: ...
- universe 정의: ...
- survivorship 정책: ...
- reference audit 결과: ...

### 다음 Step 진입 OK 요청
v1.0 정정 후 P0 → P1 진입 가능?
```

---

## 12. 알려진 risk + 정직 인정

### 12-1. 데이터 risk

- **yfinance rate limit + actual EPS / consensus EPS 부재** — P-1.1에서 결정. 권고 source: SEC EDGAR XBRL (무료, PIT timestamp). 추가 source 필요 시 cost·license 검토
- **Consensus 추정치 PIT historical 무료 source 부재 (Perplexity audit 확정)** — Refinitiv IBES / Bloomberg만 완전 PIT. 본 sprint는 RW 기대모형으로 대체
- **Estimate revision historical 깊이 부재 = 근본적 source 부재** — Polygon/AV는 PIT snapshot 없음, 무료 source 자체가 존재 안 함. revision_score backtest scope 제외 결정의 근본 근거 (단순 "깊이 부족"이 아니라 "source 부재")

### 12-2. 운영 risk

- **Earnings event timezone** — UTC 기준 source vs KST cron 정합. earnings_history.jsonl 시점 UTC + market_session 필드(BMO/AMC/RTH) 필수
- **Pre-market(BMO) / After-hours(AMC) 발표** — 미장 earnings 90%+ 가 BMO/AMC. price align 시 AMC는 다음 거래일 open price reference. 시점 처리 부정확 시 IC 측정 왜곡

### 12-3. Backtest risk (정직 인정)

- **Survivorship bias** — current universe 5년 backtest 시 delisted 누락. §2-4에서 정책 결정 + report inscription 의무
- **Look-ahead bias** — analyst estimate snapshot timestamp 정확성. revision_score backtest 제외 결정의 추가 근거
- **Selection bias** — earnings 발표 종목만 universe에 들어오면 selection bias. universe는 발표와 독립적으로 정의 (예: backtest start 시점 S&P 500)

### 12-4. 합격 임계 출처 정직 인정 (Perplexity audit 반영)

- IC ≥ 0.04: **본 sprint 자체 결정**
  - 출처: 후속 연구 컨센서스 baseline 0.04~0.08의 약 50% 보수
  - **B&T 1989/1990 원전은 IC 제시 안 함** (당시 L/S 스프레드만 측정). IC 수치는 후속 SUE 팩터 재산출 결과
- 잔차 IC ≥ raw IC × 0.5: **본 sprint 자체 결정** (직교성 학계 단일 표준 부재 확인. 실무 관행 0.2~0.3보다 느슨, Sprint 2 FF5 추가 시 0.3 재조정 검토)
- w_earnings_trial 0.05: **본 sprint 자체 결정** (v2 재산출 sprint에서 정정)
- w1/w2/w3 = 0.4/0.3/0.3: **Brain v0 self-decision** (PEAD 학문 robust 가중 비례 추정)

위 4개 모두 v2 가중치 재산출 sprint에서 backtest 결과 기반 재산출.

---

## 13. 버전 관리 + GitHub commit prefix

| 버전 | 시점 | 내용 |
|---|---|---|
| v0.1 | 2026-05-04 | Claude 베테랑 페르소나 초안 |
| v0.2 | 2026-05-04 | Claude Code review 7정정 + sprint 결합 + 롤백 |
| v0.3 | 2026-05-04 | 코드베이스 실측 정합 (메모리 #N hallucination 제거, fact_score 13 sub-score, yfinance source, V6 IC 정합 등) |
| **v0.3.1** | **2026-05-04** | **Perplexity 외부 fact-check 3건 반영 (PEAD IC B&T 오귀속 정정, EDGAR XBRL+RW 권고, 잔차 IC 0.5 한계 명시)** |
| v1.0 | 5/16 verdict 후 | P-1 결과 반영 + 진입 확정 |
| v1.1+ | sprint 진행 중 | 정정 cycle |

GitHub commit prefix:
- `[verity-earnings-plan]` — 명령서 자체 변경
- `[verity-earnings-prep]` — prep phase (snapshot collector, KR vs US 분포 비교 등)
- `[verity-earnings-impl]` — Sprint 1 구현
- `[verity-earnings-backtest]` — backtest 코드 + 결과
- `[verity-earnings-cron]` — V4 cron 통합

---

## 14. 학문 reference (Perplexity audit 2026-05-04 1차 검증 완료)

### 14-1. 1차 출처 (학문 검증)

- Ball, R., & Brown, P. (1968). "An empirical evaluation of accounting income numbers." *Journal of Accounting Research*, 6(2), 159-178. — PEAD 최초 발견
- Bernard, V. L., & Thomas, J. K. (1989). "Post-earnings-announcement drift: Delayed price response or risk premium?" *Journal of Accounting Research*, 27, 1-36. — **L/S 스프레드 60일 누적 약 4.2% (IC 미제시)**, Random Walk 기대모형 채택
- Bernard, V. L., & Thomas, J. K. (1990). "Evidence that stock prices do not fully reflect the implications of current earnings for future earnings." *Journal of Accounting and Economics*, 13(4), 305-340. — 4분기 누적 추가 drift, **연환산 약 18~25%** 수준
- Chan, L. K., Jegadeesh, N., & Lakonishok, J. (1996). "Momentum strategies." *Journal of Finance*, 51(5), 1681-1713. — collinearity 검증 reference

### 14-2. IC 수치 출처 정정 (Perplexity audit)

**Critical:** "PEAD IC 0.05~0.08"은 B&T 원전이 아님.
- B&T 1989/1990은 **L/S 스프레드 + 누적수익률**로 측정, IC 미제시
- IC 0.04~0.08 수치는 **후속 학계/실무에서 SUE 팩터를 IC로 재산출한 결과**
- 실무 퀀트 컨센서스 (FE Training 등): IC 0.05+ "강한 시그널", 0.15+ 오버피팅 의심

본 명령서 IC 합격선 0.04는 후속 연구 컨센서스 baseline의 약 50% 보수 — **B&T 원전 인용은 방법론 (RW 기대모형, SUE)에 한정, IC 수치는 후속 연구로 인용**.

### 14-3. 직교성 임계 출처 (Perplexity audit)

학계 단일 표준 부재 확인. 실무 분산:
- AQR/Barra류: 팩터 간 IC 상관 < 0.3
- 일부 펀드: Pearson r < 0.2
- 회귀 기반: VIF < 5

본 명령서 잔차 IC × 0.5 임계는 **자체 설정**. 학계 표준 인용 X.

---

## 15. v0.3 → v1.0 정정 예상 영역

P-1 결과 + prep 산출물에 따라 정정 가능 영역:

1. earnings_data_fetcher.py source 결정 + quota 전략
2. fact_score 통합 방식 (a)/(b) 결정 + sparse/always-on 결정
3. V6 IC 자동 조정 정합 (α)/(β)/(γ) 결정
4. backtest_archive 통합 vs 분리
5. 미장 universe + survivorship 정책 확정
6. REGIME country-aware 구조
7. 학문 reference audit 결과 반영
8. 5/10 self-assessment 점수 KR vs US 분포 비교 결과 반영

---

**END OF v0.3**

PM 승인 시 → Prep phase 진입 (5/4 ~ 5/16). 5/16 verdict 시점 v1.0 정정 후 Sprint 1 본격 진입.
