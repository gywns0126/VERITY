# Perplexity 답변 — 기관 설계·모델 사고 6문 (2026-08-16)

질문 = `perplexity_institutional_design_questions_2026_08_16.md`. PM 웹 질의 후 원문 전달.
**아래 본문 = 전달 원문 그대로 (무수정 보존).** 채택 기록 = `docs/GOVERNANCE_BENCHMARK_2026_08_16.md`.

---

대표적 사고들이 남긴 공통 교훈은 단순합니다. **모델 오류 자체보다, 오류가 포착·격리·중단되지 못하게 한 운영 통제의 부재가 손실을 키웠습니다.** 1인 운용도 기관의 조직도를 복제할 필요는 없지만, 변경 통제·독립적 시각·불변 로그·자동 중단 장치는 반드시 축소 구현해야 합니다.

## Q1. 사고 사례와 통제

| 사례 | 근인 분류 | 사고의 핵심 | 이후 정착한 통제 | 1인 운용 최소 구현 |
|---|---|---|---|---|
| LTCM, 1998 | 모델·유동성·레버리지·집중 | 정상시기 상관·유동성을 전제로 한 relative-value 포지션에 높은 레버리지가 결합. 러시아 디폴트와 flight-to-quality에서 상관과 유동성이 동시에 붕괴 | 유동성을 독립 risk factor로 취급, stressed correlation, reverse stress test, gross leverage·funding concentration limit, counterparty aggregate exposure 관리 | 매일 gross/net leverage, ADV 대비 포지션일수, worst-case liquidation day를 계산. "상관 1, 스프레드 2~4배, 거래량 50% 감소" 시나리오로 파산/마진콜 여부를 테스트 |
| Quant quake, 2007년 8월 | crowding·유동성·모델 | 유사한 market-neutral/value·momentum 포지션의 동시 unwind가 발생해 통상 상관이 낮던 전략이 함께 손실 | factor exposure aggregation, crowding proxy, deleveraging stress, portfolio-level not strategy-level risk, concentration cap | 개별 팩터가 아니라 포트폴리오 전체의 value/momentum/size/beta/sector exposure를 매일 저장. 비슷한 신호 간 상관, 공통 보유 종목, 공통 short 비중을 모니터링 |
| AXA Rosenberg, 2007–2010 공개·2011 SEC 제재 | 코드·거버넌스·공시·검증 | 위험관리 핵심 구성요소를 사실상 제거한 코드 오류가 발견됐지만 즉시 수정·공시하지 않았고, 고객에는 시장 변동성 탓으로 설명 | 독립 code QC, material model defect escalation, 영향분석, 고객 공시·기록보존, compliance의 실질적 권한 | 모든 factor/risk 코드 변경에 golden dataset regression test. 오류 발견 시 `incident.md`를 즉시 생성하고 영향 기간·대상 계좌·수정 여부를 기록. 이미 외부에 성과를 제시했다면 수정 사실과 영향도 공개 |
| Knight Capital, 2012 | 배포·코드·운영·실시간 위험 | 일부 서버에만 새 코드가 배포되고, 남은 서버의 dormant legacy code가 대량 잘못된 주문을 생성. 주문·체결 대조 및 자본 한도 차단도 부재 | staged/canary deployment, deploy manifest 및 server parity check, pre-trade hard limit, kill switch, incident runbook, change-management 기록 | production 배포는 immutable artifact와 commit hash로만. 서버/컨테이너 version parity를 자동 확인. 주문수·notional·position delta·일 손실 한도를 초과하면 API key/주문 프로세스를 자동 중단 |
| JPMorgan London Whale, 2012 | 모델·스프레드시트·검증·거버넌스 | 새 VaR 모델의 수식·상관/변동성 계산 변경이 충분한 검증 없이 반영되어 VaR가 낮게 측정. manual spreadsheet와 copy-paste도 오류 통로가 됨 | model-change approval, benchmark/parallel run, spreadsheet end-user computing control, formula lock, independent price verification, limit breach escalation | 위험 계산에 수동 Excel을 source of truth로 쓰지 않기. Python/SQL 코드+테스트+versioned input으로 재현. old/new risk model을 최소 20~60 거래일 parallel run하고 차이가 임계치를 넘으면 배포 금지 |
| 데이터 수정·상장폐지 누락형 실패 | 데이터·생존편향·룩어헤드 | 현재 상장 종목만 사용하거나, 수정된 재무 데이터·후행 분류·사후 확정 corporate action을 과거에 사용해 성과를 과대평가 | point-in-time database, delisting return, as-of timestamp, vendor revision history, data QA 및 lineage | 모든 테이블에 `effective_at`, `available_at`, `ingested_at`, `source_version` 저장. historical universe는 날짜별 constituent로 재구성하고 상장폐지·거래정지를 제거하지 않음 |
| 과도한 전략 탐색·백테스트 최적화 | 오버피팅·리서치 거버넌스 | 수많은 feature, period, cutoff, portfolio rule을 시험한 뒤 최고 Sharpe만 선택 | experiment registry, holdout lockbox, PBO/CSCV·CPCV, deflated Sharpe, 사전 정의된 selection rule | 시도한 모든 실험을 자동 기록하고, 최종 holdout 기간은 선택 단계에서 열지 않음. 동일 아이디어의 parameter search 횟수를 기록하고, 변경 후에는 OOS 평가를 새로 시작 |

LTCM 이후에는 레버리지 포트폴리오에서 시장가치·유동성·공통 risk-factor 노출을 함께 봐야 하고, 모델을 stress test와 판단으로 보완해야 한다는 교훈이 강조됐습니다. 2007년 8월 사태는 개별 전략의 과거 상관만으로 충분하지 않으며, **동일 factor trade의 crowded unwind**를 별도 스트레스로 다뤄야 한다는 사례입니다. [bauer.uh]

AXA Rosenberg는 2007년에 유입된 코드 오류가 risk-management 핵심 구성요소를 무력화했고, 2009년 발견 후에도 즉시 고치거나 고객에게 알리지 않은 사안입니다. SEC는 약 2억 1,700만 달러의 고객 보상, 2,500만 달러의 제재금, 독립 컨설턴트 नियुक्त과 compliance 기능 개선을 요구했습니다. [sec]

Knight의 경우 SEC는 불완전한 배포, 주문-체결 대조 부재, 전체 자본노출과 연동되지 않은 위험통제, 코드 배포·테스트·사고대응 절차 미비를 지적했습니다. 이는 "좋은 전략"과 별도로 주문 시스템에 **독립적인 hard risk gate**가 있어야 한다는 강한 선례입니다. [sec]

London Whale에서는 수식 변경과 manual spreadsheet 프로세스가 충분히 검증되지 않아 변동성·상관 추정 오류와 과소 VaR가 발생했습니다. 상원 조사 보고서는 검증되지 않은 spreadsheet 수식이 두 개의 계산 오류를 만들었다고 지적했습니다. [hsgac.senate]

## Q2. 1인 운용 거버넌스 축소판

SR 11-7의 핵심은 부서 수가 아니라 세 기능입니다.

1. **개발의 타당성 검토**: 이론·가정·데이터·구현이 목적에 맞는가
2. **outcomes analysis**: 예측과 실현 결과가 일치하는가
3. **ongoing monitoring**: 데이터·시장·성능 변화 뒤에도 계속 유효한가

연준은 validation을 conceptual soundness, ongoing monitoring, outcomes analysis로 구성하며, backtest는 실제 결과와 모델 예측을 forecast horizon에 맞춰 비교하는 outcomes analysis의 한 형태로 정의합니다. [federalreserve]

### 개발자=검증자 문제의 완화

독립 부서가 없으면 "사람의 독립성"을 완벽하게 만들 수 없습니다. 대신 **시간·코드·데이터·의사결정의 독립성**을 만들어야 합니다.

| 문제 | 경량 대체 통제 |
|---|---|
| 개발자가 자기 전략을 편향되게 검증 | research charter를 먼저 commit하고, 결과 확인 전 hypothesis·universe·endpoint·cost model·kill rule을 고정 |
| 결과를 보고 parameter를 조정 | experiment registry에 run ID, commit hash, data snapshot, parameter, 결과를 append-only로 저장 |
| 과거 결과에 맞춘 반복 수정 | research 기간, validation 기간, final holdout을 물리적으로 분리. holdout은 승격 결정을 내릴 때 한 번만 열기 |
| 코드와 production 불일치 | research와 production이 같은 feature definition package를 import하도록 구성. 계산 로직의 복사·붙여넣기 금지 |
| 독립 challenge 부재 | 월 1회 "red-team review"를 과거의 자신이 아닌 미래의 자신에게 맡김: 최소 7일 cooling-off 후 thesis 반증만을 위해 재검토 |
| 외부 관점 부족 | 분기 1회 신뢰 가능한 퀀트 개발자·회계/리스크 전문가와 60~90분 외부 peer review. 코드 전체가 아니라 assumptions, data timing, execution, risk limits를 검토 |
| 위험 대응이 감정적 | 위험 한도 위반 시 사람이 판단하기 전에 자동으로 신규 주문 차단, 포지션 축소 또는 alert를 발생 |

### 유지해야 할 최소 문서

| 문서 | 핵심 필드 | 갱신 시점 |
|---|---|---|
| Model/strategy inventory | ID, 목적, asset class, owner, tier, 상태, capital, last review, next review | 전략 생성·변경·폐기 |
| Research charter | hypothesis, 경제적 근거, universe, data availability rule, parameter search 범위, OOS plan, 비용·세금, 성공·킬 기준 | research 시작 전 |
| Data contract | vendor, fields, timestamp 의미, revision policy, corporate action, null/outlier 처리, PIT 보장 여부 | 데이터 변경 시 |
| Model card | 수식, feature 정의, code hash, assumptions, limitations, expected decay, exposure, capacity, failure modes | 승인/변경 시 |
| Backtest report | IS/OOS 분리, 시도 횟수, IC·ICIR·PnL, turnover, cost, stress, sensitivity, PBO/CPCV 가능 여부 | 승격 심사 시 |
| Deployment runbook | 배포 절차, rollback, kill switch, 주문 한도, 장애 대응, 연락/알림 | production 변경 시 |
| Daily risk log | NAV, gross/net, sector/factor exposure, leverage, turnover, slippage, stale data, limit breach | 매 거래일 |
| Change log | 무엇을, 왜, 누가, 언제, 영향 범위, 새 version, 재검증 요구 여부 | 모든 변경 |
| Incident/postmortem | 탐지 시각, 원인, 영향, 조치, 재발 방지 test | 모든 material incident |

### 버려도 되는 기관 통제

소규모에서 비용 대비 효익이 낮아 생략 가능한 것은 다음입니다.

- 전담 model validation 부서와 다단계 조직 승인 체계
- 월간 대형 risk committee용 프레젠테이션 제작
- 동일 모델을 여러 언어로 독립 재구현하는 full-scale challenger model
- 복잡한 GRC 시스템, 대형 상용 model-risk 플랫폼
- 저위험 보조 지표마다 연간 완전 재검증 보고서 작성
- 사람이 24시간 상주하는 NOC/SOC식 관제

대신 다음은 버리면 안 됩니다.

- Git 기반 version control 및 protected production branch
- immutable data snapshot 또는 최소한 input hash
- production deploy 전 자동 test
- order-level hard limit과 kill switch
- 변경 승인 기록
- periodic review 및 실제 성과-예측 성과 비교
- 상장폐지·공시시점·데이터 수정 대응을 포함한 PIT 데이터 규칙

과잉 엔지니어링의 기준은 명확합니다. **통제가 막을 수 있는 최대 손실보다 구축·유지비가 크고, 더 단순한 자동 통제로 같은 손실을 막을 수 있다면 생략**합니다. 단, 주문 폭주·데이터 stale·손실 한도·배포 오류처럼 단일 사건이 계좌 생존을 위협하는 영역은 비용 논리로 생략하면 안 됩니다.

## Q3. 팩터 라이브러리 메타데이터

기관형 factor library는 단순히 `factor_name → dataframe`이 아닙니다. "이 값이 어느 시점에, 어떤 코드·데이터·규칙으로 산출됐고, 어디에 쓰이며, 현재도 쓸 수 있는가"를 추적하는 registry입니다.

상용 equity risk model의 문서는 factor별 정의, 입력 구성, 추정 horizon, orthogonalization, industry/country assignment 같은 재현 가능한 방법론을 제공합니다. 예를 들어 Axioma의 스타일 factor 문서는 liquidity, market sensitivity, volatility, momentum, size, value, leverage, growth, profitability의 구체 구성요소를 제시합니다. Barra식 risk model도 common factor component와 security-specific component를 분해해 관리합니다. [cdn2.hubspot]

### 권장 스키마

```yaml
factor_id: quality_roa_v3
display_name: "Profitability: Return on Assets"
status: approved                 # draft | research | approved | watch | deprecated | retired
risk_tier: tier_2
owner: quant-research
backup_owner: null

business_purpose:
  intended_use:
    - cross_sectional_alpha
    - risk_control
  asset_class: KR_equity
  universe_policy_id: kr_liquid_equity_v4
  economic_hypothesis: >
    Higher operating profitability is persistently underpriced,
    conditional on size, sector and accounting availability.
  prohibited_uses:
    - intraday_execution
    - standalone_market_timing

definition:
  formula_version: 3.1.0
  canonical_formula: "TTM operating income / average total assets"
  transform:
    - winsorize: [0.01, 0.99]
    - sector_zscore: true
    - size_neutralize: true
  rebalance_frequency: monthly
  availability_lag_rule: "actual DART filing timestamp + next tradable session"
  missing_value_policy: "unscored; excluded before cross-sectional normalization"

lineage:
  source_systems:
    - dart_xbrl
    - krx_prices
  source_field_ids:
    - dart.operating_income_ttm
    - dart.total_assets
  entity_mapping_version: issuer_master_2026_04
  corporate_action_policy: total_return_v2
  point_in_time_policy: strict_asof
  data_snapshot_id: snapshot_2026_08_16
  raw_data_hash: "sha256:..."
  feature_code_commit: "git:..."
  environment_lock_hash: "sha256:..."

validation:
  last_validated_at: "2026-08-01"
  next_review_due: "2027-08-01"
  validation_scope: full
  validation_owner: external_peer_or_delayed_self_review
  conceptual_soundness: pass
  implementation_test_status: pass
  data_quality_test_status: pass
  known_limitations:
    - accounting comparability across sectors
    - delayed updates and restatements
  benchmark_factor_ids:
    - roa_v2
    - gross_profitability_v1

performance:
  ic_horizon_days: [20, 60, 120]
  ic_mean_rolling_252d: 0.018
  icir_rolling_252d: 0.42
  hac_t_stat_rolling_3y: 2.1
  long_short_spread_net: 0.0
  turnover: 0.0
  cost_adjusted_sharpe: 0.0
  live_vs_backtest_gap: 0.0
  decay_status: watch
  regime_breakdown:
    bull: {}
    bear: {}
    high_vol: {}
    low_vol: {}

risk_and_capacity:
  factor_exposures:
    - size
    - value
    - sector
  correlation_to_live_factors: {}
  estimated_capacity_krw: 0
  median_adv_participation: 0.0
  implementation_shortfall_budget_bps: 0
  crowding_proxy: {}
  liquidity_constraints: {}

governance:
  approval_date: "2026-08-01"
  approver: "owner + peer reviewer"
  change_policy: major_change_requires_new_factor_id
  kill_criteria:
    - "12-month rolling ICIR below 0 for 2 review windows"
    - "live net spread below 0 after costs for defined independent observations"
    - "data lineage/PIT integrity breach unresolved"
    - "capacity estimate falls below allocated capital"
  alerts:
    - stale_input
    - population_shift
    - ic_decay
    - missingness_spike
    - live_slippage_breach
```

### 필수 메타데이터 그룹

| 그룹 | 필수 필드 |
|---|---|
| 식별·책임 | factor ID, 명칭, owner, backup owner, 상태, risk tier |
| 경제적 정의 | 가설, 정확한 수식, 단위, 방향성, transform, neutralization, universe |
| 버전 | semantic version, code commit, environment lock, 승인일, 변경 이유 |
| 데이터 계보 | source, field ID, entity mapping, as-of rule, revision policy, raw snapshot/hash |
| PIT 적합성 | 정보 발생·공개·수집·사용 시각, filing lag, corporate action 처리 |
| 성과 | IC/ICIR 시계열, horizon별 결과, OOS/live 결과, turnover, 비용 후 spread |
| 감쇠 | rolling IC, regime별 성과, drift, 최근 live-backtest gap, watch/decay state |
| 위험 | sector/size/beta/other factor exposure, 상관, crowding, tail behavior |
| 구현 | rebalance, 주문 제약, capacity, ADV participation, estimated slippage |
| 검증 | conceptual review, implementation test, benchmark, sensitivity, last/next review |
| 폐기 | kill criteria, retirement date, downstream dependency, 대체 factor |

현대 feature-store 관점에서도 핵심은 point-in-time correctness, source-to-feature-to-model lineage, 코드 version lineage, dependency-aware deprecation입니다. Databricks의 공개 문서도 feature tables·functions·models 간 lineage, point-in-time joins, code version 추적을 governance 핵심으로 둡니다. [docs.databricks]

## Q4. Backtest → paper → live 승격 게이트

기간이나 표본 수에는 업계 단일 규정이 없습니다. 거래 빈도, holding horizon, 비용 구조, 알파 half-life와 capacity가 다르기 때문입니다. 대신 "**독립 관측 수 + 실제 거래 마찰 + 여러 regime**"을 통과 조건으로 쓰는 것이 표준에 가깝습니다.

### 권장 단계

| 단계 | 목적 | 최소 권고 | 통과 조건 |
|---|---|---|---|
| Research/backtest | 가설의 역사적 타당성 | IS/validation/final holdout 분리, realistic cost·delay, delisting·PIT 검증 | 경제적 가설, OOS 성과, stress·sensitivity, 과도한 parameter search 부재 |
| Shadow/paper | signal 생성·데이터 timing·주문시스템 검증 | 일별/주별 전략은 보통 6~12개월, 월별 전략은 12~24개월 또는 충분한 독립 rebalance | live signal이 research signal과 일치, stale/missing 데이터 없음, 예상 turnover·slippage 범위 충족 |
| Pilot live | 실제 체결·비용·운영 리스크 확인 | 최소 3~6개월 및 실거래가 최소 1개 리밸런싱/변동성 regime을 통과 | 실현 slippage·fill rate·PnL 분포가 ex-ante budget 안, hard-limit breach 없음 |
| Scale-up | capacity와 portfolio fit 확인 | 단계적 증액: 예 0.25x → 0.5x → 1.0x target | live net performance, risk contribution, capacity, crowding과 existing portfolio correlation 통과 |
| Watch/retire | decay·구조 변화 대응 | rolling review | 성과·데이터·실행·capacity kill trigger에 따른 축소 또는 중단 |

### Paper 기간과 독립 관측

paper 기간은 "6개월"보다 다음 계산이 중요합니다.

N_independent ≈ forward observation days / holding horizon days

예를 들어 20거래일 holding 전략을 6개월, 약 126 거래일 paper run하면 독립 holding cycle은 약 6개 수준입니다. signal 및 execution smoke test에는 의미가 있어도, 알파 유의성을 확정하기엔 약합니다. 12개월은 약 12개, 24개월은 약 25개 cycle입니다.

따라서 다음을 권합니다.

- **일별·단기 전략**: 최소 6개월 paper, 권장 12개월; 단 실제 독립 trade/event count와 regime coverage를 병기
- **월별 factor 전략**: 최소 12개월, 권장 24~36개월
- **분기 fundamental 전략**: 12개월은 사실상 4회 rebalance일 수 있으므로 충분하지 않음; 최소 2~3년 또는 더 긴 holdout 필요
- **LLM·alternative data 전략**: 생성 시점·문서 시점·모델 version이 immutable하게 기록된 forward 기간을 별도로 확보

Quantopian의 888개 알고리즘 연구는 최소 6개월 OOS 자료가 있는 전략을 분석했으며, backtest Sharpe는 OOS 성과 예측력이 매우 낮았습니다(R²<0.025). 즉 paper 기간은 단순 의례가 아니라, backtest selection bias를 드러내는 단계입니다. [community.portfolio123]

### Pilot 자본 크기

Pilot capital은 "의미 있는 비용·체결정보가 나오지만, strategy failure가 전체 NAV를 훼손하지 않는 수준"이어야 합니다. 고정 비율보다 위험 예산으로 정하는 것이 좋습니다.

Pilot capital = min(5% target allocation, daily loss budget / stressed daily volatility, capacity의 보수적 하한)

1인 운용의 실무적 시작점은 보통 목표 전략 배분의 **5~10% 이하**, 혹은 전체 계좌의 일일 최대 허용 손실이 0.25~0.50% NAV를 넘지 않도록 잡는 방식입니다. 다만 초저유동성 KOSDAQ, event-driven, high-turnover 전략은 이보다 훨씬 작게 시작해야 합니다.

### 승격·강등·킬 규칙

| 항목 | 예시 사전 규칙 |
|---|---|
| 승격 | paper/live에서 signal 생성 일치율 99% 이상, data freshness breach 0회, realized slippage가 예상 예산의 125% 이하, 독립된 관측 수 충족 |
| 증액 | live net IC 또는 net spread가 사전 기대 범위 내, rolling drawdown 및 factor exposure가 risk budget 이내, capacity 사용률 제한 이내 |
| 강등 | 1~2개 review window에서 live-backtest gap이 통계·경제적으로 material, slippage가 2개월 연속 budget 초과, 데이터 결측 급증 |
| 즉시 중단 | stale/corrupt input, 주문한도 위반, reconciliation 실패, 손실 hard-stop, PIT integrity breach, 예상과 다른 leverage/exposure |
| 폐기 | 사전 정의된 독립 관측 수 후에도 net edge가 0 이하, 설명 불가능한 decay, capacity 붕괴, 가설의 경제적 근거 소멸 |

### 수정하면 시계를 재시작하는가

원칙은 **예, material change면 재시작**입니다.

| 변경 유형 | 새 버전/새 paper clock |
|---|---|
| factor 수식, signal ensemble, 모델 weight, LLM prompt/model, universe, rebalance, execution logic, risk limit, 비용모델의 핵심 가정 변경 | 반드시 재시작 |
| 데이터 vendor 교체, PIT timestamp 정의 변경, corporate action 처리 변경 | 반드시 재시작 또는 최소 parallel revalidation |
| bug fix가 과거 성과·현재 signal·주문을 materially 바꿈 | 재시작 및 기존 결과 restatement |
| logging 개선, dashboard 변경, 성과에 영향 없는 refactor | 재시작 불필요. regression test와 change log면 충분 |
| 긴급 위험 제한 강화 | live는 즉시 적용 가능하되, 성과 평가 version은 분리 |

실무의 lifecycle도 대체로 idea → rigorous backtest → incubation/paper → small live allocation → scale-up → decay/retirement의 형태이며, incubation의 목적은 "실시간 환경에서 백테스트 약속이 유지되는지" 확인하는 것입니다. 실자본 배정 프로세스도 성과 검증·데이터 검증 후 live test allocation을 거쳐 지속 배정을 판단하는 다단계 구조를 사용합니다. [quantmemo]

## Q5. 리서치 노트와 IC 메모

헤지펀드식 single-name 또는 systematic strategy IC memo는 "왜 살 것인가"보다 **무엇이 시장 기대와 다른가, 무엇이 이를 드러낼 것인가, 무엇이 틀렸음을 증명할 것인가**를 문서화해야 합니다.

### 종목 IC 메모 표준 구조

| 섹션 | 필수 내용 |
|---|---|
| Recommendation | Long/short, ticker, 현 가격, target, horizon, requested size, expected return |
| Thesis | 1~3문장 핵심 주장. 기업 설명이 아니라 mispricing의 원인과 해소 경로 |
| Variant perception | 시장 consensus/price가 암묵적으로 전제한 것과 본인의 상이한 관점 |
| Evidence | 재무·산업·채널체크·공시·가격·수급 근거. 사실과 판단을 분리 |
| Catalyst | 실적, 가격, 계약, 규제, 자본배치, event calendar와 예상 시점 |
| Valuation | base/bull/bear, multiple/DCF/asset value, 민감도, target-price bridge |
| Risk | 확률, 영향도, 완화책, leading indicator, tripwire |
| Position sizing | conviction, downside, liquidity, correlation, beta/sector exposure, stop 조건 근거 |
| Kill criteria | thesis를 반증하는 관측 가능한 사건·수치·시간 제한 |
| Monitoring plan | 주간/월간 KPI, 다음 확인일, catalyst 전후의 재평가 기준 |
| Decision log | 최초 승인, 증액/축소/유지/종료의 날짜·근거·결과 |

fundamental long/short workflow에서도 idea sourcing → deep dive → memo → IC discussion → sizing → monitoring의 흐름이 일반적이며, variant perception, catalyst, KPI, risk, disconfirming evidence, "what would prove us wrong" trigger를 명시적으로 추적하는 접근이 제안됩니다. [stackai]

### Kill criteria는 이렇게 쓴다

나쁜 kill criterion:

> "실적이 나쁘면 재검토한다."

좋은 kill criterion:

> "2026년 4분기까지 핵심 제품의 신규 고객 순증이 3개 분기 연속 전년 대비 감소하고, 이는 pricing power가 아니라 수요 훼손에서 기인하며, base-case 매출 성장률 12%가 5% 이하로 하향될 경우 long thesis를 무효화한다."

좋은 기준은 다음 네 요소를 가집니다.

- 관측 가능한 변수
- 수치 또는 명확한 사건
- 판단 시점
- 자동 행동: 유지·축소·중단·재심사

### 시스템 전략 IC 메모 구조

```text
1. Strategy ID / version / owner
2. Economic hypothesis and market microstructure rationale
3. Signal definition and point-in-time data contract
4. Universe, tradability, holding period, rebalance and execution assumptions
5. IS / validation / untouched OOS separation
6. Parameter-search inventory and selection rule
7. IC, ICIR, net spread, turnover, capacity and stress results
8. Factor, sector, beta, liquidity and crowding exposures
9. Known failure regimes and expected decay mechanism
10. Paper/live acceptance criteria
11. Scaling, drawdown, slippage and data-integrity kill rules
12. Version-change policy and next revalidation date
```

López de Prado와 공동저자들의 연구가 지적하듯, 과도한 모델·파라미터 선택은 표본 내에서 좋아 보이지만 실제에서는 열등한 전략을 선택하는 backtest overfitting을 유발합니다. CSCV/PBO 및 purged cross-validation은 이를 정량화·완화하는 보조 수단입니다. [papers.ssrn]

## Q6. 재검증 주기와 트리거

SR 11-7은 "모든 모델을 무조건 연 1회 full validation"하라고 정하는 규정보다, 모델의 **materiality·complexity·uncertainty**에 비례한 검증 강도와 ongoing monitoring을 요구하는 프레임워크입니다. 모델 output과 현실 outcome을 비교하고, 제품·노출·데이터·시장 조건 변화 속에서도 목적에 맞게 작동하는지 모니터링해야 합니다. [federalreserve]

### 권장 tier별 주기

| Tier | 예시 | 정기 full review | monitoring |
|---|---|---|---|
| Tier 1 | 주문·execution, leverage/risk limit, portfolio optimizer, live capital 핵심 alpha | 최소 연 1회 | 일별 또는 매 리밸런싱 |
| Tier 2 | 승인된 factor, 중간 규모 signal, risk overlay | 12~18개월 | 주별·월별 |
| Tier 3 | 보조 feature, research-only factor, 낮은 영향 모델 | 18~24개월 | 월별·분기별 |
| Tier 4 | retired model, 실험적 dashboard, non-decision analytics | event-driven | 사용 시점 또는 분기 점검 |

소규모 운용에서는 tier를 3개로 단순화해도 충분합니다.

- **Critical**: 돈을 직접 움직이거나 손실 제한을 결정
- **Active**: 포트폴리오 signal에 기여하지만 단독 생존위협은 아님
- **Research/retired**: 운용 의사결정에 직접 사용하지 않음

### 트리거 기반 재검증

정기 검토를 기다리지 말고 다음이 발생하면 review를 시작해야 합니다.

| 트리거 | 최소 조치 |
|---|---|
| rolling IC/ICIR 또는 net PnL이 사전 범위를 이탈 | targeted performance review, 필요 시 allocation 축소 |
| live slippage가 예산을 지속 초과 | execution·liquidity·capacity 재검증 |
| universe 구성·ADV·missingness·factor distribution 변화 | data drift review |
| vendor·API·DART parser·entity mapping 변경 | lineage 및 PIT regression test |
| 모델/prompt/feature/version 변경 | materiality assessment, 대부분 parallel run 또는 full revalidation |
| 시장 구조 변화 | tick size, short-sale rule, 거래시간, 세금, index methodology 변화 등은 regime review |
| 스트레스 손실·limit breach | 즉시 incident review와 reverse stress update |
| backtest와 live signal 불일치 | data snapshot·code hash·execution timing audit |
| crowding 또는 capacity 지표 급변 | participation cap, scaling review, liquidation stress 재계산 |

### Full vs targeted review

| 검토 유형 | 언제 쓰는가 | 범위 |
|---|---|---|
| Full revalidation | 수식·모델·데이터 vendor·universe·execution logic 변경, material performance failure, 모델 용도 변경 | conceptual soundness, code replication, data/PIT, full backtest, OOS, stress, capacity, documentation, approval |
| Targeted review | 단일 data field 변경, 특정 drift, slippage 악화, one-off incident | 해당 component, 영향 분석, regression test, 제한적 historical/live comparison |
| Ongoing monitoring | 정상 운영 | 성능·drift·exposure·data freshness·execution·limit dashboard |
| Emergency review | data corruption, order malfunction, hard loss/limit breach | 신규 주문 중지, reconciliation, root cause, rollback, incident record |

### 1인 운용용 경량 cadence

- **매 거래일**: data freshness, source row count, missingness, gross/net, factor exposure, open orders, realized vs expected slippage, loss limits
- **매주**: signal distribution, turnover, universe 변화, top positions, execution anomalies
- **매월**: live IC/ICIR 또는 strategy-level net PnL, factor attribution, model-version audit, capacity·crowding 점검
- **매분기**: strategy/model card 재검토, kill criteria 점검, change log review, external peer challenge
- **매년**: Critical 전략 full revalidation, stress scenario update, disaster-recovery/kill-switch drill
- **언제든**: trigger 발생 시 즉시 targeted 또는 full review

가장 중요한 원칙은 "검토했다"가 아니라, **검토 결과가 전략의 자본배분·배포 권한·운용 중단에 실제 영향을 줄 수 있어야 한다**는 점입니다. SR 11-7의 validation도 단순 문서심사가 아니라 conceptual soundness, outcomes analysis, ongoing monitoring을 결합해 모델의 신뢰성·한계·목적 적합성을 평가하는 체계입니다. [federalreserve]
