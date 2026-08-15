# Perplexity 답변 — IC 검증 방법론 5문 (2026-08-15)

질문 5종 출처 = Brain 전면 검수 세션 (`docs/BRAIN_AUDIT_2026_08_15.md` §1-D).
PM 이 Perplexity 에 질의 후 원문 전달. **아래 본문 = 전달 원문 그대로 (무수정 보존).**

적용 기록 = `docs/BRAIN_AUDIT_2026_08_15.md` §3 (외부 검증) + `docs/VALIDATION_METHODOLOGY.md` §7-3.

핵심 채택 4:
1. k<10 = 통계적 유의 아님 → **exploratory** 분류. 자유도 ≈ k−1 (fwd7 k=6 → 임계 2.571)
2. offset 하나 선택 = 데이터 스누핑 → **전 offset non-overlap 표본** + median/positive-ratio/worst/best 보고
3. 시장 공통 신호 = 선별 점수 밖 (timing/exposure/risk-budget 레이어). 예외 = 노출 상호작용(m_t × z_i)
4. 분기 fundamental 을 일별 IC 로 재면 표본만 인위 증가 → **공시 event-date 또는 월말 snapshot IC**

---

아래의 핵심 결론부터 말하면, **겹치는 장기 horizon IC의 유의성은 "매일 관측치 수"가 아니라 실질적으로 독립적인 time breadth로 판단**해야 하며, 독립 블록 수가 \(k<10\)이면 HAC 기반 t-stat을 주된 증거로 쓰지 않는 것이 보수적 표준입니다. 또한 종목 공통 market-level 신호는 cross-sectional stock-ranking 알파가 아니라 market timing·gross exposure·risk-budget 레이어에 두는 것이 맞습니다.

## Q1. 겹치는 forward-return IC

### 결론

30거래일 forward return을 매일 사용한 IC 시계열은 관측치가 \(T\)개여도 유효 독립 표본은 대략 \(T/30\) 수준입니다. 이때 \(k<10\)이라면, 다음 우선순위를 권합니다.

| 방법 | 용도 | \(k<10\)일 때 판단 |
|---|---|---|
| Non-overlapping block | 가장 투명한 보수적 검정 | **주 검정으로 권장**, 단 검정력 부족을 명시 |
| Newey–West HAC, lag \(=h-1\) | overlap을 포함한 보조 추정 | 참고치로만 제시, 작은 표본 t값 과신 금지 |
| Hansen–Hodrick | 기계적으로 알려진 overlap 구조 | NW보다 기본 선택으로 권하지 않음 |
| Valkanov 계열 long-horizon inference | persistent predictor + horizon이 표본에 비해 긴 회귀 | IC 평균 자체보다 predictive regression 검정에 적합 |

Hansen–Hodrick(HH)은 overlap 구간 안의 자기공분산을 동일 가중치로 더하고, Newey–West(NW)는 Bartlett taper를 적용합니다. NW는 양의 준정부호를 보장하는 HAC라서 실무에서 더 흔히 쓰이지만, 둘 다 표본 길이 대비 horizon이 길면 표준오차를 심하게 낮게 추정할 수 있습니다. 즉 "HAC를 했으니 안전하다"가 아닙니다.

### 실무 표준 제안

30일 horizon이라면 다음을 함께 보고하는 것이 가장 방어적입니다.

1. **주 결과:** 30거래일 간격 non-overlapping IC.
   - 시작 offset을 하나만 임의로 고르지 말고, \(0,\ldots,29\)개 offset의 non-overlapping 표본을 모두 생성합니다.
   - 각 offset별 평균 IC, t-stat, 부호 일관성을 보고합니다.
   - 가장 좋아 보이는 offset을 선택하면 다시 데이터 스누핑이 됩니다.

2. **보조 결과:** 매일 IC에 대해 NW-HAC, lag \(=29\).
   - t-stat은 \(t_{\text{HAC}}=\bar{IC}/SE_{\text{HAC}}(\bar{IC})\).
   - bandwidth를 기계적으로 \(h-1\)에 고정한 결과와, 더 긴 lag 또는 automatic bandwidth의 민감도도 제시합니다.
   - 30일 forward return이라도 signal persistence, 월말효과, 발표일 군집 등이 있으면 29보다 긴 serial dependence가 남을 수 있습니다.

3. **독립 블록 \(k<10\):** "통계적 유의"가 아니라 **exploratory evidence**로 분류합니다.
   - Student-t 임계값을 쓰더라도 자유도는 사실상 \(k-1\)에 가깝습니다.
   - 예를 들어 5년 일별 데이터가 약 1,250일이면, 30일 horizon의 유효 블록 수는 약 41개입니다. 반면 1년 데이터는 약 8개에 불과하므로, HAC t-stat이 2 이상이어도 강한 증거로 취급하기 어렵습니다.
   - 가능하면 검증기간을 늘리거나 horizon을 줄여 independent breadth를 확보하는 편이, HAC tuning보다 더 중요합니다.

Valkanov의 비판은 특히 predictor가 느리게 움직이고 horizon \(K\)가 표본 \(T\)에 비해 무시할 수 없을 때, 통상 OLS t-stat과 long-horizon 회귀 추론이 부적절해질 수 있다는 점입니다. 따라서 macro-like 또는 매우 persistent한 predictor로 장기수익률을 예측하는 회귀라면 HAC만으로 끝내지 말고 Valkanov/IVX류의 long-horizon robust inference, bootstrap, 또는 직접적인 non-overlap 검정을 병행하는 것이 낫습니다.

### 권장 보고 형식

```text
Horizon: 30 trading days
Daily overlapping IC:
  Mean IC = ...
  NW(29) t-stat = ...
  NW(59) t-stat = ...

Non-overlapping validation:
  Number of offsets = 30
  Median offset mean IC = ...
  Positive-offset ratio = ... / 30
  Median t-stat = ...
  Worst / best offset t-stat = ... / ...

Effective independent blocks:
  Approx. T / 30 = ...
  Classification: exploratory / confirmatory
```

***

## Q2. 시장 레벨 신호의 위치

**동일 날짜에 모든 종목에 같은 값인 market-level signal은 같은 날짜의 cross-sectional rank에 기여하지 않는다**는 지적은 정확합니다.

종목 \(i\)의 composite score를

\[
S_{i,t}=a_{i,t}+\beta m_t
\]

라고 하면, \(m_t\)는 모든 종목에 공통입니다. 따라서 임의의 두 종목 \(i,j\)에 대해

\[
S_{i,t}-S_{j,t}=a_{i,t}-a_{j,t}
\]

이므로 순위, quintile membership, long-short constituent는 완전히 동일합니다. Spearman IC도 종목 간 rank만 보기 때문에 \(m_t\)의 직접 기여는 0입니다.

### 권장 아키텍처

| 레이어 | 입력 | 산출물 | 적합한 목적 |
|---|---|---|---|
| Security selection | 종목별 value, quality, momentum, revisions, sentiment | 종목별 alpha 또는 ranking score | 어떤 종목을 살지/팔지 |
| Risk model | beta, sector, size, style, liquidity, volatility | risk forecast, exposure constraints | 원치 않는 위험 통제 |
| Market regime | 공포탐욕, macro mood, FX, commodity, rates, breadth | gross exposure, net exposure, hedge ratio, factor tilt | 얼마나 위험을 가질지 |
| Portfolio construction | alpha, risk, cost, constraints | 최종 portfolio weights | turnover·risk·capacity 통제 |

Grinold–Kahn의 IC는 일반적으로 예측과 실현 alpha의 관계, 즉 **종목 단위의 active forecast skill**로 이해됩니다. 시장 방향을 맞히는 신호는 time-series breadth를 갖는 별도 market-timing 문제이며, cross-sectional breadth와 동일한 IC로 섞으면 측정과 포트폴리오 설계가 혼재됩니다. 시장 타이밍의 IR은 time-series breadth와 cross-sectional breadth를 분리해 해석해야 한다는 연구도 이 구분을 지지합니다.

### 예외: 상호작용을 만들면 종목선별에 들어갈 수 있음

시장 신호 자체가 아니라 **market-conditioned cross-sectional signal**이면 종목별 ranking에 기여할 수 있습니다.

\[
S_{i,t}
=
a_{i,t}
+
\gamma \cdot m_t \cdot z_{i,t}^{\text{beta}}
\]

예를 들어 risk-off regime에서 고베타 종목을 상대적으로 낮추거나, 원화 약세 국면에서 수출주 노출이 큰 종목을 높이는 방식입니다. 이 경우 \(m_t\)는 공통이어도 \(z_{i,t}^{\text{beta}}\) 또는 FX exposure가 종목별로 달라서 순위가 바뀝니다.

다만 이것은 "공포탐욕 지수를 종목 점수에 더한다"가 아니라, **regime-conditioned factor tilt**입니다. BARRA식으로는 common factor return 또는 factor-risk environment와 종목별 exposure의 결합으로 해석하는 편이 자연스럽습니다.

***

## Q3. 횡단면 IC 측정 관행

### IC 정의와 기본 통계

각 날짜 \(t\)에서 유니버스 \(N_t\)개 종목의 signal rank와 다음 기간 수익률 rank의 Spearman 상관을 계산합니다.

\[
IC_t
=
\rho_{\mathrm{Spearman}}
\left(
\operatorname{rank}(x_{i,t}),
\operatorname{rank}(r_{i,t\rightarrow t+h})
\right)
\]

시계열 요약값은 통상 다음을 보고합니다.

\[
ICIR=\frac{\overline{IC}}{\sigma(IC)}
\]

독립 관측이라는 가정에서

\[
t \approx ICIR\sqrt{T}
\]

입니다. 그러나 forward-return overlap이 있으면 이 \(T\)는 일수 \(T\)가 아니라 HAC 또는 block 방식으로 조정된 유효 표본 수여야 합니다. Grinold–Kahn의 IC는 예측정보와 실현 alpha 사이의 상관이라는 개념이고, IC와 breadth를 통해 기대 IR을 연결합니다.

### 유니버스 크기

문헌에 모든 시장에 적용되는 단일 "최소 종목 수" 규칙은 없습니다. 다만 실무적으로 다음처럼 운영하는 편이 낫습니다.

| 유니버스 수 | 해석 |
|---|---|
| 20 미만 | rank IC가 매우 불안정. 정식 일별 IC 검정에는 부적합 |
| 30–50 | 최소 운영선. sector-neutral 또는 size bucket 중립화를 하면 더 불안정할 수 있음 |
| 100 이상 | broad-market factor 연구의 실무적 하한선으로 적절 |
| 300 이상 | KOSPI+KOSDAQ broad universe에서는 상대적으로 안정적 |

중요한 것은 단순 종목 수보다 **유동성 필터 적용 뒤의 \(N_t\), sector별 구성, microcap 비중, 결측치 처리, 매일의 유니버스 변동**을 같이 기록하는 것입니다. 일별 IC에 \(N_t<50\)인 날이 많다면 그 날짜를 제외하는 명시적 rule을 사전에 정하거나, 최소 \(N_t\) 기준을 100 등으로 두는 것이 좋습니다.

### 일별·월별 선택

| 조건 | 권장 IC 빈도 | forward horizon |
|---|---|---|
| 가격·거래량·단기 모멘텀 | 일별 또는 주별 | 1일~20일 |
| 중기 모멘텀·revision | 주별 또는 월별 | 1~3개월 |
| 가치·수익성·재무건전성 | 월별 | 1~12개월 |
| 분기 갱신 fundamental | 공시 event-date 또는 월별 hold | 1~12개월 |

"데이터가 매일 존재한다"와 "경제적으로 새로운 정보가 매일 발생한다"는 다릅니다. 분기 재무제표 기반 factor를 매일 같은 값으로 IC 계산하면 IC 시계열 표본 수만 인위적으로 늘어나고 serial correlation이 강해집니다.

### 분기 fundamental의 권장 방식

분기 갱신 factor는 아래 중 하나를 사용합니다.

- **공시일 기반 event-time IC:** 실제 DART 접수 시각 또는 다음 거래 가능 시점에 factor를 갱신하고, 20/60/120거래일 forward IC를 산출
- **월말 snapshot IC:** 해당 월말에 실제 이용 가능했던 공시만 반영한 factor로 1·3·6·12개월 forward return을 측정
- **월간 rebalance portfolio:** value/quality 등은 월 1회 또는 분기 1회 rebalance하고, IC와 portfolio spread를 함께 검증

Qian–Hua–Sorensen의 목차에도 single-period skill을 IC로 다루고, 이후 portfolio constraints와 IR을 연결하는 구조가 나타납니다. 따라서 IC는 단독 통계가 아니라 turnover, 구현비용, 위험제약 후의 portfolio-level 결과와 연결해서 보는 것이 바람직합니다.

***

## Q4. 한국 시장 팩터 검증

한국 KOSPI+KOSDAQ에서 broad equity factor를 연구한다면, 최소 기준은 **10년**, 선호 기준은 **15년 이상**입니다. 이는 보편적인 법칙이라기보다 한국 시장의 구조 변화, KOSDAQ의 높은 퇴출 위험, 금융위기·코로나·금리 급등·반도체 사이클 등 서로 다른 regime을 포함시키기 위한 실무 기준입니다. 한국 상장·상장폐지 연구도 장기 표본을 사용하며, 예를 들어 KOSPI·KOSDAQ 신규상장 표본을 2001–2012년으로 구성하고 2017년까지 추적한 연구가 있습니다.

### 데이터 및 유니버스 규칙

| 항목 | 권장 처리 |
|---|---|
| 표본 | 매 시점에 실제 상장되어 있고 거래 가능했던 KOSPI+KOSDAQ 전 종목에서 사전 정의한 liquidity filter 적용 |
| 생존편향 | 현재 상장 종목 마스터 금지. 당시 상장·관리·거래정지·상장폐지 종목을 포함한 point-in-time security master 사용 |
| 상장폐지 | 마지막 거래일까지 보유; 상장폐지·정리매매·합병·공개매수 cash-out의 실제 실현수익률 반영 |
| 거래정지 | 매매 불가능 기간에는 신규 편입·리밸런싱 불가로 처리. 이미 보유한 포지션은 재개 또는 청산 가능 시점까지 mark-to-model 하지 말고, 실행 가능 가격 규칙을 명시 |
| 관리종목 | 사전 정의한 유동성·거래가능성 rule에 따라 제외 또는 포함. 단, 제외한다면 해당 정보가 언제 공개되었는지 point-in-time으로 적용 |
| 가격 | 수정주가·현금배당·유상증자·액면분할·감자·권리락 등을 반영한 total-return 계열 사용 |
| 유동성 | 거래대금, 호가 스프레드, ADV, 가격 하한, turnover/capacity filter를 사전 고정 |
| 비용 | 수수료, 세금, bid–ask, market impact, 체결지연을 portfolio 규모별로 반영 |

### DART reporting lag

DART의 법정 제출기한은 분기·반기보고서가 기간 종료 후 45일 이내, 사업보고서가 사업연도 종료 후 90일 이내입니다. 그러나 backtest에서는 "45일 뒤부터 사용 가능"이라고 일괄 처리하는 것보다 **실제 DART 접수 timestamp**를 쓰는 것이 최선입니다.

실무적으로는 다음 hierarchy를 권합니다.

1. 최선: DART 원문 및 XBRL의 실제 접수일시 기준.
2. 차선: 각 기업의 실제 filing date를 historical database에서 확보.
3. 보수적 대안: 분기·반기는 quarter-end +45 calendar days 후 다음 거래일, 연간은 fiscal-year-end +90 calendar days 후 다음 거래일.
4. 수정공시는 최초 공시 당시 알려진 숫자로 시작하고, 정정본은 **정정 접수 이후에만** 반영.

특히 12월 결산 법인의 경우 1분기·반기·3분기 보고서와 사업보고서의 이용 가능 시점이 다르므로, "분기말 기준 재무비율"을 다음 날부터 쓴 backtest는 전형적인 look-ahead bias입니다. 실제 2026년 DART 일정도 결산월별 분기·반기·사업보고서 마감일을 별도로 제시합니다.

### 검증기간 제안

- **최소:** 10년, 가능하면 서로 다른 bull/bear·high/low-rate regime 포함
- **권장:** 15~20년, 단 회계기준·상장규정·데이터 정의 변경 구간은 별도 robustness check
- **최근 holdout:** 마지막 2~3년은 model selection에 사용하지 않는 frozen OOS 기간으로 보존
- **결과 분해:** KOSPI/KOSDAQ, 대형주/중소형주, sector-neutral 여부, liquidity bucket, 상승·하락·고변동성 regime별 보고

한국의 상장폐지 관련 연구들은 KOSPI/KOSDAQ의 퇴출 종목을 별도로 다루고 있으며, KOSDAQ는 성장시장 특성상 상장폐지 위험이 더 높다는 점이 보고됩니다. 따라서 퇴출 종목을 제외한 "현존 종목" 표본은 특히 quality, distress, value, microcap factor를 과대평가할 위험이 큽니다.

***

## Q5. LLM·alternative-data 신호 검증

**완전한 historical backtest가 불가능한 신호에는 학계 전체에서 통일된 '최소 forward 기간' 규정이 있지는 않습니다.** 그러나 퀀트 운용의 실질적 표준은 research pre-registration, immutable point-in-time snapshot, shadow/live forward evaluation, 그리고 변경 통제입니다.

핵심은 "과거에 없던 LLM score를 과거에 만들어 보는 것"이 아니라, **당시의 모델·프롬프트·문서·데이터 접근 가능 시점이 동결된 상태에서 앞으로 생성되는 신호를 평가**하는 것입니다.

### 사전등록 패키지

신호를 production 또는 paper portfolio에 올리기 전 아래를 versioned research charter로 고정하세요.

| 항목 | 반드시 고정할 내용 |
|---|---|
| Hypothesis | 어떤 경제적 메커니즘으로 alpha가 발생하는가 |
| Universe | 거래가능성, 상장기간, 시가총액, ADV, 가격, 관리·거래정지 처리 |
| Signal | 모델 ID, weight hash, tokenizer, prompt template, temperature, retrieval corpus, parsing rules |
| Timestamp | 문서 발행시각, 수집시각, score 생성시각, execution cutoff |
| Portfolio rule | rank cutoff, weighting, sector/beta constraints, rebalance frequency |
| Horizon | 1일·5일·20일·60일 등 primary endpoint와 secondary endpoint |
| Costs | 수수료·세금·slippage·impact·거래 불능 규칙 |
| Statistics | primary metric, IC, long-short spread, HAC/block correction, multiple-testing adjustment |
| Success rule | 최소 mean IC, t-stat, turnover-adjusted spread, maximum drawdown, capacity 기준 |
| Stop rule | 언제 paper test를 중단·폐기·재검토할지 |
| Change rule | model/prompt/data source/portfolio rule 변경 시 기존 trial 종료 후 새 버전으로 재등록 |

### forward 검증 기간

정답은 달력 기간보다 **독립적인 rebalance 관측 수와 market regime**입니다.

| 신호 주기 | 최소 탐색 단계 | 투자 전 권장 |
|---|---|---|
| 일별·주별 신호 | 최소 6개월 | 12개월 이상, 서로 다른 변동성 국면 포함 |
| 월별·분기별 신호 | 최소 12개월 | 24~36개월 또는 충분한 독립 rebalance 수 |
| 20~60일 holding horizon | 최소 6~12개월 | overlap을 감안한 20~30개 이상의 유효 독립 holding cycle 지향 |
| LLM event signal | event 수 기준 병행 | 종목·sector·market regime별 충분한 event coverage 필요 |

이 숫자는 규제나 교과서의 단일 규칙이 아니라 운영상 gate입니다. 특히 30일 holding signal을 6개월만 관찰하면 약 6개의 독립 cycle 수준이라 통계적 승인을 내리기에는 약합니다. 이때는 deploy sizing을 매우 작게 하고, "promising but unconfirmed"로 관리하는 것이 맞습니다.

### 스냅샷 무결성

LLM 신호에는 아래 5개가 사실상 필수입니다.

- 원문 문서의 immutable raw copy와 content hash
- 제공자 publish time, 시스템 ingest time, score generation time
- prompt·model version·tool version·retrieval index version·output JSON의 hash
- 재실행 가능 환경 또는 최소한 container/image·dependency lockfile
- 모든 score 및 주문결정의 append-only audit log

애널리스트 리포트처럼 라이선스·수정·삭제가 가능한 데이터는 특히 "현재 다운로드한 문서"가 아니라 **그 당시 접근 가능했던 원문과 시각**을 입증해야 합니다. LLM 공급자 모델이 무단 또는 자동으로 업데이트되면, 동일 프롬프트라도 과거와 다른 score가 나올 수 있으므로 model-version drift를 별도 리스크로 관리해야 합니다.

### 사후 조정 금지 규칙

- trial 시작 후 prompt, model, feature definition, rank cutoff, universe, horizon, cost model을 변경하지 않습니다.
- 오류 수정은 허용하되, 오류의 발견 시각·영향 범위·수정 전후 결과를 기록하고 기존 trial과 분리합니다.
- 성과가 나쁜 기간을 삭제하거나, favorable event만 골라 재평가하지 않습니다.
- 여러 prompt·모델·cutoff를 시험했다면 **모든 trial 수와 선택 규칙**을 기록합니다.
- 최종 선택은 untouched forward holdout 또는 새 trial에서 재검증합니다.

대규모 전략 탐색에서는 좋은 backtest가 live에서 크게 저하될 수 있습니다. alternative-beta 전략 연구에서는 backtest 대비 live Sharpe가 중앙값 기준 73% 저하됐고, 더 복잡한 전략일수록 저하가 더 컸습니다. Quantopian의 대규모 표본에서도 일반적인 backtest Sharpe는 out-of-sample 성과 예측력이 매우 낮았으며, 최소 6개월 OOS 성과가 있는 전략을 분석 대상으로 사용했습니다.

### 당신의 LLM 주식 분석 플랫폼에 맞춘 운영안

LLM 리포트·공시 요약 점수라면 다음과 같이 설계하는 것이 현실적입니다.

1. 매일 KST 기준 cutoff, 예를 들어 08:30 또는 15:20을 고정합니다.
2. cutoff 이전에 수집·처리 완료된 문서만 signal 생성에 사용합니다.
3. 종목별 score와 근거 문장, 문서 ID, source timestamp, LLM/model/prompt hash를 저장합니다.
4. 다음 거래 세션의 현실적인 체결가로 paper portfolio를 실행합니다.
5. primary endpoint를 예를 들어 20거래일 residual return IC로 하나만 사전 지정합니다.
6. secondary endpoint로 1·5·60일 IC, quintile spread, sector-neutral spread, turnover, 거래비용 후 PnL을 둡니다.
7. 12개월 forward record가 쌓이기 전에는 낮은 risk budget 또는 paper-only로 유지합니다.
8. model 또는 prompt를 바꾸면 V2를 새 전략으로 취급하고 V1의 성과와 합치지 않습니다.

CPCV, purging/embargo, deflated Sharpe, PBO 같은 도구는 historical data가 있는 구성요소의 과적합을 진단하는 데 유용하지만, 과거 시점의 LLM score 자체가 존재하지 않는 경우에는 live-forward log를 대체하지 못합니다. 전략 검정에서 PBO를 정량화하는 CSCV 접근과, overlap leakage를 피하는 purged validation은 보조 검증층으로 두는 것이 적절합니다.

## 구현 원칙

전체 설계는 다음 한 줄로 요약할 수 있습니다.

> **종목 공통 신호는 exposure/risk layer로, 종목별 signal은 cross-sectional alpha layer로, 겹치는 horizon의 통계는 독립 breadth 기준으로, 재현 불가 LLM 신호는 immutable forward experiment로 검증한다.**

이 원칙을 따르면 한국 주식용 멀티팩터·LLM 플랫폼에서 가장 흔한 오류인 look-ahead, survival bias, overlap 과신, rank-neutral market signal 혼입, prompt/model drift에 의한 사후 최적화를 동시에 줄일 수 있습니다.
