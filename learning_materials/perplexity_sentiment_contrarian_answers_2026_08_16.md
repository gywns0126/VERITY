# Perplexity 답변 — 투자자 심리·역발상 4문 (2026-08-16)

질문 = 2026-08-16 채팅 전달 4문 (심리 역발상 학술·실무 지표·뉴스 편향·게이트 설계).
PM 웹 질의 후 원문 전달. **아래 본문 = 전달 원문 그대로 (무수정 보존).**
채택 기록 = `docs/PREREG_SENTIMENT_GATE_2026_08_16.md` (설계 등록).

핵심 채택 6:
1. 비대칭 확정 — 고심리 = buy-restraint (naked short 금지). 공매도 제약 메커니즘 (Baker-Wurgler)
2. 🚨 감쇠 경고 — Tetlock/García 계수는 후속 연구에서 감쇠 보고. 원전 bp 복사 금지, forward 검증 필수
3. 지평 분리 — 뉴스/검색 1~5일 · survey 1~6개월 · issuance 수개월~년. 혼용 = horizon mismatch
4. 게이트 형태 = g_t 곱셈 오버레이 + rolling percentile 5/95 + 지속성 필터 + 히스테리시스(95진입/80해제)
5. 검정 = 20~30년 이력 · event cluster · regime 분해 · 시도 전수 기록 · median/hit/worst 병기
6. 뉴스 탈편향 = source fixed-effect 잔차 (8단계 절차) — sentiment_engine 개선 후보로 별도 등록

---

투자자 심리는 평균적인 정상 구간에서는 약한 신호지만, **극단 구간에서는 기대수익·변동성·시장참여자의 포지셔닝을 보완적으로 설명하는 역발상 신호**가 될 수 있습니다. 다만 심리 지표만으로 시장을 숏하거나 바닥을 단정하는 방식은 근거가 약하며, 실무에서는 대개 종목 선별이 아니라 **gross exposure·신규 매수 속도·헤지 비중을 조절하는 gate**로 씁니다.

## Q1. 학술 원전의 증거

### Baker–Wurgler: 심리는 특히 투기적 종목에 작동

Baker & Wurgler의 2006년 연구는 투자자 심리가 높은 시기 뒤에는 작고, 젊고, 변동성이 크고, 무수익·무배당이며, 성장 기대가 크거나 distressed한—즉 가치평가가 주관적이고 차익거래가 어려운—종목군의 이후 수익률이 상대적으로 낮아진다고 보였습니다. 반대로 저심리 시기 뒤에는 이 종목군의 이후 수익률이 상대적으로 높았습니다. [ideas.repec]

그들의 composite sentiment index는 다음 6개 proxy에서 공통 성분을 PCA로 추출합니다.

| 구성요소 | 고심리와의 방향 | 해석 |
|---|---:|---|
| Closed-end fund discount | 낮을수록 고심리 | 개인투자자 낙관·할인 축소 |
| NYSE share turnover | 높을수록 고심리 | 투기적 거래 참여 |
| IPO 수 | 높을수록 고심리 | 신규 위험자산 수요 |
| IPO first-day return | 높을수록 고심리 | IPO 과열 |
| Equity share in new issues | 높을수록 고심리 | 기업의 equity financing 선호 |
| Dividend premium | 높을수록 고심리 | 안전·배당주 대비 성장·투기주의 선호 |

이 6개 구성은 원전의 Baker–Wurgler sentiment index 정의와 일치합니다. [academic.oup]

### 비대칭의 경제적 해석

질문의 "고심리 이후 저수익이 저심리 이후 고수익보다 더 강한가"에 대해선, **Baker–Wurgler의 핵심은 대칭적 시장 타이밍 규칙보다 고심리 국면의 과대평가와 그 후의 낮은 횡단면 수익**입니다. 고심리 때는 낙관적 투자자가 speculative stock을 밀어 올리고, 비관적 투자자는 공매도 제약·차입비용·idiosyncratic risk 때문에 이를 충분히 바로잡지 못합니다. 따라서 과대평가가 누적·지속되다가 중기적으로 실현수익률 부진으로 해소될 수 있습니다. [ideas.repec]

저심리에서의 저평가도 가능하지만, "싼 종목을 사기"는 제한이 덜한 반면 "비싼 종목을 공매도하기"는 제약이 크므로, 과대평가 쪽의 왜곡과 이후 correction이 더 뚜렷할 수 있습니다. 이는 원전의 arbitrage-asymmetry와 일치하는 해석이지만, 모든 시기·모든 지표에서 통계적으로 고심리 효과가 반드시 더 크다는 보편 법칙은 아닙니다.

### De Bondt–Thaler: 장기 과잉반응의 반전

De Bondt & Thaler(1985)는 과거 3년간 극단적 loser 종목 35개와 winner 종목 35개를 구성한 뒤, 이후 36개월을 추적했습니다. loser portfolio는 시장 대비 누적 초과수익률 19.6%, winner portfolio는 약 -5.0%였고, winner–loser spread는 약 24.6%였습니다. 표본은 16개의 비중첩 3년 formation period였습니다. [tradicted]

- **형태:** 종목 횡단면 장기 reversal
- **예측 지평:** formation 후 약 3년
- **심리 연결:** 최근 과거 성과에 대한 과도한 외삽과 기대의 과잉반응
- **주의점:** 후속 연구에서는 size, value, seasonality, risk adjustment, data-snooping 논쟁이 있어 이를 순수한 "심리 효과"로만 해석하면 안 됩니다.

### Tetlock: 미디어 비관은 단기 가격압력 후 반전

Tetlock(2007)은 Wall Street Journal의 *Abreast of the Market* 칼럼에서 부정 단어 비중을 이용해 media pessimism을 구성했습니다. 높은 비관은 다음 날 시장 가격 하락압력을 예측하지만, 그 효과는 그 주말까지 거의 반전됐습니다. 1표준편차 높은 비관은 다음 날 Dow 수익률 약 -8.1bp와 연결됐고, 이후 단기 반전이 나타났습니다. [onlinelibrary.wiley]

- **형태:** 일별 market-level short-horizon reversal
- **예측 지평:** 다음날 충격, 약 1주 이내 반전
- **해석:** 뉴스 비관이 fundamental information만 반영한다면 반전이 약해야 합니다. 반전은 liquidity/noise trader 기반 일시적 가격압력 해석과 더 부합합니다.
- **유의점:** 낮은 시장수익률이 높은 media pessimism을 유발하는 역인과도 존재합니다. Tetlock도 이를 보고하므로, 단순 contemporaneous correlation을 예측력으로 착각하면 안 됩니다. [business.columbia]

### García: 침체기에서 더 강한 뉴스 감성 효과

García(2013)는 1905–2005년의 *New York Times* 일별 기사 텍스트를 바탕으로 뉴스 비관을 측정했고, 뉴스 감성의 수익률 예측력은 특히 recession에서 집중된다고 보였습니다. 경기침체기에 pessimism factor가 1표준편차 변하면 DJIA의 조건부 일평균 수익률이 약 12bp 변했지만, expansion에서는 약 3.5bp였습니다. [leeds-faculty.colorado]

- **형태:** market-level 일별 예측
- **지평:** 주로 단기·일별
- **핵심:** 심리 충격은 불확실성·불안이 큰 recession에서 더 크게 가격에 반영되고 반전/예측 관계도 강해질 수 있음
- **실무 함의:** 동일한 sentiment z-score라도 low-vol expansion과 recession/high-stress 환경에서 동일한 exposure rule을 적용하면 안 됩니다.

### Da–Engelberg–Gao: FEARS의 단기 반전

Da, Engelberg & Gao의 FEARS는 Google 검색량에서 "recession", "unemployment", "bankruptcy" 같은 가계의 금융·경제 우려 검색을 집계한 일별 sentiment index입니다. FEARS 상승은 당일 시장수익률 하락과 동행하지만, 이후 **약 2거래일 동안 수익률 상승**, 즉 단기 반전을 예측했습니다. 변동성의 일시적 증가와 주식형 펀드에서 채권형 펀드로의 자금 이동도 관련되어 있습니다. [nber]

| 연구 | 신호 | 핵심 효과 | 주된 지평 |
|---|---|---|---|
| Baker–Wurgler 2006/2007 | composite sentiment | 고심리 후 speculative·hard-to-arbitrage 종목 저수익 | 수개월~수년 횡단면 |
| De Bondt–Thaler 1985 | 과거 winner/loser | 장기 loser 반전·winner 부진 | 36개월 |
| Tetlock 2007 | WSJ media pessimism | 비관 후 가격압력, 이후 반전 | 1일~1주 |
| García 2013 | NYT 뉴스 감성 | recession에서 일별 예측력 강화 | 1일 중심 |
| Da–Engelberg–Gao 2015 | FEARS 검색지수 | 공포 급등 후 2일 내 반전 | 1~2일 |

### 발표 후 감쇠 여부

효과가 "사라졌다"고 단정할 수는 없지만, **원전이 사용한 텍스트·시장구조·정보 유통 환경에서의 추정치를 현재 그대로 기대하면 안 됩니다.** 최근 연구는 Tetlock과 García의 news-sentiment 관계가 시간이 지나며 감쇠했다고 보고하며, 원 데이터를 다시 분석해 이 변화가 현대 표본에서의 약한 결과와 양립한다고 설명합니다. [sciencedirect]

실무적으로는 다음처럼 해석하는 편이 안전합니다.

- 장기 sentiment factor는 구조적 가설이 있어도 rolling OOS IC·ICIR로 계속 재검증
- 뉴스 기반 초단기 signal은 source·언어·시차·모델 변경에 매우 민감하므로 fresh forward validation 필수
- 2000년대 신문 텍스트 논문에서 얻은 bp 크기를 2026년 웹·SNS·LLM 뉴스 흐름에 그대로 복사하지 않기
- high sentiment의 "신규 위험자산 매수 억제"에는 활용 가능하지만, 단독 naked short signal로 확대 해석하지 않기

## Q2. 실무 지표와 실패 구간

### 지표별 현실적 사용법

아래 임계치는 **보편적 매매 규칙이 아니라 조사·경계 수준**입니다. 지표의 장기 평균과 분산은 조사방법, 투자자 구성, 옵션시장 구조 변화에 따라 달라지므로, 고정 절대값보다 5~10년 rolling percentile/z-score가 더 낫습니다.

| 지표 | 흔한 역발상 극단 | 문서화된 활용 | 주요 한계 |
|---|---|---|---|
| AAII bull–bear spread | 대략 하위 5~10% 또는 -20~-30pt 이하: fear; 상위 5~10% 또는 +30pt 이상: greed | 개인투자자 survey 기반 contrarian context | survey 응답 표본·짧은 주기·극단 지속 가능 |
| Investors Intelligence | bulls 60% 이상 또는 bull/bear ratio 약 2 이상: 과열; bulls 35% 이하·bears 40~45% 이상 또는 ratio 0.6 이하: 공포 | newsletter writer sentiment를 professional-adviser positioning proxy로 사용 | 실제 포지션이 아닌 의견 survey |
| Equity put/call ratio | 자체 history 기준 상위 5~10%: fear; 하위 5~10%: greed | 옵션 hedge/speculation 수요의 보조 proxy | dealer hedging·0DTE·기관 hedge 수요가 signal을 왜곡 |
| VIX | rolling percentile 상위 90~95%: panic; 하위 5~10%: complacency | volatility regime·hedge cost·position sizing 보조 | VIX는 fear 자체보다 option-implied variance; 고VIX가 장기 지속 가능 |
| CNN Fear & Greed | 20 이하: extreme fear, 80 이상: extreme greed | 여러 market internals를 한 화면에서 확인하는 regime dashboard | proprietary composite, 역사·구성 변경·중복 신호 |
| BofA Sell Side Indicator | 15년 rolling mean 대비 약 -1σ: buy; +1σ: sell | sell-side strategist의 recommended equity allocation을 contrarian proxy로 사용 | 월간·느린 지표, sell-side 의견과 실제 risk-taking 차이 |

AAII에서 1987–2023년 표본의 bull–bear spread가 -31pt 이하인 매우 비관 구간은 평균적으로 이후 6개월 5.5%, 1년 10.5% 수익률과 연결됐고, +34pt 초과의 매우 낙관 구간은 이후 6개월 -0.2%, 1년 -2.2%였습니다. 다만 극단 낙관 구간은 전체의 약 1.5%로 event 수가 매우 적습니다. [signaturebank]

AAII의 실무적 공개 설명도 survey를 단독 timing tool이 아니라 historical averages/extremes와 함께 읽는 contrarian context로 제시합니다. Investors Intelligence에서는 bull/bear ratio 약 2.0 이상을 낙관 극단, 0.6 이하를 비관 극단으로 보는 관행이 알려져 있습니다. [aaii]

BofA Sell Side Indicator는 sell-side strategist의 미국 주식 권고 비중을 기반으로 하며, 15년 rolling 평균의 ±1 표준편차를 buy/sell threshold로 사용해 왔습니다. 2012년에 50 아래로 떨어진 뒤 buy signal이 발생했고, 이후 12개월 S&P 500은 약 18% 상승했다는 사례가 있습니다. [businessinsider]

### "지표가 맞았던 사례"와 "너무 일찍 맞은 사례"를 구분

| 구간 | 극단 심리 | 결과 | 교훈 |
|---|---|---|---|
| 1999년 기술주 버블 | survey·IPO·valuation·옵션 낙관이 장기간 과열 | 과열 신호가 나와도 시장은 추가 상승 가능 | 고심리는 즉시 숏 신호가 아니라 risk budget 축소 신호 |
| 2008년 금융위기 | fear·VIX·put demand 급등 | 공포가 강해도 바닥 전까지 손실 확대 가능 | "fear=buy"가 아니라 drawdown/추세/유동성 조건 필요 |
| 2020년 3월 | AAII bear, VIX, put demand 등 panic | 이후 강한 반등 | 극단 공포는 기대수익 개선의 후보지만 execution·volatility budget이 핵심 |
| 2020–2021년 | 저금리·유동성·retail participation 속 고심리 지속 | 성장주·meme·SPAC 과열이 장기간 지속 후 2022년 조정 | 극단은 시간결정이 아니라 취약성 상태를 알려줌 |
| 2022년 | survey pessimism·strategist allocation 하락 | 이후 반등 구간 존재 | slow-moving survey는 scale-in/hedge reduction에는 유용, 단기 entry timing에는 제한적 |

따라서 1999, 2020–2021처럼 심리 극단이 1년 이상 유지될 수 있는 환경에서 "극단이면 즉시 반대로 베팅"하면 carry와 trend에 크게 질 수 있습니다. 특히 VIX·put/call은 hedging demand와 option supply/demand 구조도 반영하므로, 투자자의 단순 방향 예측으로 읽으면 안 됩니다.

### 기관식 보완책

- **Persistence filter:** 한 번의 extreme 대신 2~4주 연속 extreme, 또는 5일/20일 평균이 threshold를 통과해야 gate 발동
- **Trend filter:** fear에서 매수 노출을 늘리더라도 시장이 장기 이동평균을 회복하거나 breadth가 개선될 때만 실행
- **Volatility filter:** VIX 급등 직후 full-size 진입 대신 변동성 목표 비중으로 나누어 진입
- **Valuation·liquidity filter:** sentiment가 높아도 valuation, credit spread, funding condition, earnings revision이 동반 악화되는지 확인
- **No naked short:** extreme greed에서는 새 long을 억제·gross를 줄이고 hedge를 늘리는 방식이 일반적으로 더 견고
- **Composite confirmation:** survey, options, flows, breadth, volatility 중 최소 2~3개가 같은 방향일 때만 강한 gate

## Q3. 뉴스 부정 편향과 탈편향

뉴스의 부정 편향은 공급자만의 문제라기보다 **수요와 상호작용하는 구조**입니다. Soroka·Trussler 계열 연구는 사람들이 명시적으로는 덜 부정적인 뉴스를 선호한다고 말해도, 실제 선택에서는 negative·strategic frame을 더 자주 선택한다는 결과를 보였습니다. [cpsa-acsp]

대규모 온라인 실험에서도 평균 길이의 headline에서 negative word가 하나 추가될 때 click-through rate가 약 2.3% 높아졌고, positive word는 소비율을 낮추는 방향이었습니다. 이 결과는 약 2만 2,743명의 randomized trials, 약 10만 5천 개 headline variation, 약 5.7백만 clicks와 3.7억 impressions의 데이터를 활용했습니다. [ideas.repec]

### 소스별 baseline을 제거하는 방법

금융 뉴스 sentiment를 raw negative-word 비율로 쓰면, 상시적으로 비관적 문체인 source가 "더 나쁜 시장신호"처럼 오인됩니다. 따라서 종목·뉴스 소스·시간을 함께 보정해야 합니다.

가장 단순한 source fixed-effect 방식: Sentiment_{a,t} = α_source(a) + γ_topic(a) + δ_time(t) + ε_{a,t}
여기서 실제 signal은 raw score가 아니라 잔차 ε — 해당 source·topic·기간에 비해 **비정상적으로 부정적 또는 긍정적인 부분**입니다.

실무 절차 8단계:
1. 기사 단위로 model score를 [-1,1] 혹은 negative/neutral/positive 확률로 저장
2. source별 rolling 180~365일 평균·표준편차를 계산
3. raw score 대신 source-normalized z-score 사용
4. outlet fixed effect, 언어, 기사 길이, topic, author, weekday, market-volatility regime을 회귀 보정
5. 동일 뉴스의 재인쇄·syndication을 deduplicate
6. 발표시각·수집시각·시장 사용 가능시각을 분리해 PIT 보장
7. aggregate signal에서는 기사 수가 많은 source가 압도하지 않도록 source equal-weight 또는 capped weight 적용
8. source별 OOS IC를 따로 보아, 특정 매체 baseline 변화나 model drift를 탐지

이는 factor model의 industry-neutralization과 같은 논리입니다. "부정 점수가 높다"가 아니라, **평소 그 source가 쓰는 문체 대비 얼마나 비정상적으로 부정적인가**를 봐야 합니다.

### 긍정 뉴스의 과소반응과 PEAD

긍정 earnings surprise 뒤에 수주~수개월 상승 drift가 이어지는 PEAD는 가장 잘 알려진 underreaction 현상 중 하나입니다. 가격은 positive news에 즉시 전부 반응하지 않고, 이후에도 상승하는 경향을 보입니다. [pages.stern.nyu]

최근 text 기반 연구에서는 earnings call text에서 만든 unexpected positive content signal의 후속 수익률 drift가 전통적 숫자 기반 PEAD보다 더 크다고 보고했습니다. 2010–2019 표본에서 quintile portfolio의 top-minus-bottom 누적 차이는 발표 후 1분기 시점 2.87% 대 1.54%, 4분기 시점 8.01% 대 4.63%였습니다. [cambridge]

한국 시장에서도 긍정·부정 earnings surprise 이후 drift가 최대 약 12개월 이어질 수 있고, positive surprise 종목이 negative surprise 종목보다 월 1% 이상 높은 수익률을 보인다는 보고가 있습니다. 따라서 "뉴스가 대체로 부정적이니 반대로 긍정만 찾자"가 아니라, **긍정 news surprise가 시장 가격에 충분히 반영되지 않았는지**를 기업별·event-time으로 검정하는 것이 더 적절합니다. [sciencedirect]

### 의도적 낙관 논거 탐색의 효과

"부정 일색 뉴스에서 의도적으로 optimistic case를 작성하면 투자성과가 좋아진다"는 직접적인 장기 실험 증거는 제한적입니다. 이를 알파 생성 규칙으로 주장하기보다는, **확증편향을 줄이는 decision hygiene**로 보는 편이 정확합니다.

실무에서 더 방어 가능한 절차:
- Bear case와 bull case를 같은 evidence standard로 작성
- 각 주장에 대해 supporting evidence와 disconfirming evidence를 최소 하나씩 기록
- base/bull/bear scenario의 확률·valuation·catalyst를 명시
- 사전 정의한 monitoring KPI와 kill criterion으로 thesis를 업데이트
- "긍정적 주장"의 설득력이 아니라 OOS 예측력·실현 결과로 점수화

이 과정은 심리적으로 편향된 뉴스 소비를 상쇄할 수 있지만, 그것 자체가 초과수익을 보장한다는 뜻은 아닙니다.

## Q4. 심리 극단 exposure gate 설계

심리 gate는 종목별 alpha에 합산하는 것이 아니라, portfolio-level risk control로 구현:
w_final = g_t × w_stock_selection
g_t 는 sentiment·trend·volatility·liquidity conditions에 따른 gross exposure multiplier. 동일한 market sentiment 값은 같은 날짜 모든 종목에 공통이므로 cross-sectional rank 자체를 바꾸지 않지만, 전체 gross/net exposure·hedge ratio·신규 매수 허용 여부는 바꿀 수 있습니다.

### 극단 정의

| 방식 | 장점 | 단점 | 권장 |
|---|---|---|---|
| Rolling percentile | 비정규분포·regime shift에 비교적 강함 | 장기 history가 필요, window choice 민감 | 기본 선택 |
| Rolling z-score | 직관적이고 여러 지표 결합이 쉬움 | heavy tail·평균 변화에 취약 | percentile과 병행 |
| Absolute threshold | 설명이 쉽고 운영 간단 | 구조 변화에 취약 | 검증된 단일 survey에 한정 |

권장 초기 설정:
- rolling 10년 또는 가능한 전체 history의 **5th/95th percentile**: 강한 extreme
- 10th/90th percentile: watch zone
- z-score 기준 |z|≥1.5 경계, |z|≥2.0 강한 extreme
- 극단 이벤트가 너무 적다면 10/90 percentile로 넓히되, 결과를 "moderate extreme"로 구분
- 신호 방향은 항상 사전 등록: high greed → risk reduction 후보, high fear → selective risk addition 후보

### 지속성 요구

| 설계 | 예시 |
|---|---|
| 연속 확인 | 3주 연속 AAII spread가 상위/하위 10% |
| 이동평균 | 5일 또는 20일 average sentiment가 threshold 통과 |
| 누적 압력 | 10일 중 7일 이상 extreme zone |
| 다중 지표 확인 | survey + options + volatility + flow 중 2개 이상 extreme |
| 진입·해제 hysteresis | 95th percentile에서 risk-off 진입, 80th percentile 아래에서만 해제 |

hysteresis가 중요합니다. 그렇지 않으면 threshold 근처에서 매일 exposure를 켰다 껐다 하며 turnover와 whipsaw가 커집니다.

### 비대칭 행동: 과열에서는 억제, 공포에서는 허용

| 상태 | 권장 기본 행동 | 이유 |
|---|---|---|
| Extreme greed | 신규 long 억제, gross 축소, 기존 수익 포지션 rebalancing, hedge 검토 | 고심리는 즉시 하락보다 valuation·crowding·left-tail 취약성을 의미하는 경우가 많음 |
| Neutral | 기본 alpha portfolio 운용 | sentiment 단독의 정보가 약함 |
| Extreme fear | 강제 역매수보다 정상적 alpha 진입 허용, 금지됐던 buy를 단계적으로 복원 | fear는 종종 높은 미래 기대수익과 연결되지만, 하락 추세·liquidity stress가 계속될 수 있음 |
| Panic + trend breakdown | risk budget 유지·축소, 분할 진입 | "싼데 더 싸질" tail risk와 deleveraging 위험 |

이 비대칭은 공매도 제약과 단기 price pressure의 비대칭성에 부합합니다. Baker–Wurgler의 high-sentiment speculative-stock 저수익 결과도 이런 "buy restraint" 해석에는 더 잘 맞습니다. [ideas.repec]

### 적정 지평

| 지표 유형 | 합리적 평가 지평 |
|---|---|
| 뉴스·검색량 기반 shock | 1~5거래일, 길어도 1~2주 |
| option positioning·VIX shock | 수일~수주 |
| AAII·Investors Intelligence survey | 1~6개월 |
| sell-side allocation·issuance/IPO sentiment | 수개월~1년 이상 |
| Baker–Wurgler류 structural sentiment | 중기 횡단면, 수개월~수년 |

FEARS의 반전은 약 2일, Tetlock 뉴스 비관의 반전은 통상 1주 내 — 이들을 월간 market timing signal로 쓰는 것은 horizon mismatch. 반대로 sell-side allocation이나 IPO/issuance 기반 지표는 일별 entry trigger가 아니라 느린 risk-regime signal.

### 드문 extreme event의 검정

심리 extreme은 의도적으로 드문 사건이라 표본이 작습니다. 30년 주별 자료도 약 1,560개인데 5% tail은 약 78개 observation이며, 연속 extreme을 요구하면 독립 event 수는 더 작아집니다.

1. **최소 20~30년 history** 확보. survey·options·VIX·macro regime 포함, 여러 crisis와 bull market
2. threshold crossing이 아니라 **event cluster**로 묶기 — 연속 extreme 주는 하나의 event, 첫 발생일 또는 worst percentile date가 event date
3. 각 event에서 +1, +5, +20, +60, +120, +252 거래일 forward return 사전 정의
4. raw return뿐 아니라 benchmark-adjusted, volatility-adjusted, maximum adverse excursion, drawdown 병기
5. overlapping forward return에는 non-overlapping blocks, HAC, block bootstrap 병행
6. recession/expansion, 인플레, credit stress, trend, volatility regime별 결과 + event 수 병기
7. threshold·holding·filter를 여러 개 시험했다면 모든 시도 기록, final holdout 또는 live forward 재검증
8. 평균만 보지 말고 median, hit rate, worst decile, tail loss 병기 — fear event 뒤 평균이 높아도 path risk가 클 수 있음

핵심은 "extreme fear 뒤 평균적으로 반등했다"를 곧바로 매수 규칙으로 바꾸지 않는 것. 표본 수·regime dependency·진입 이후 drawdown·실행비용까지 통과한 경우에만, 전체 전략의 **작은 exposure overlay**로 승격.
