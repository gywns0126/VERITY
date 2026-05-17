# VERITY 터미널 + ESTATE 시스템 종합 스펙 (2026-05-17)

> **목적**: Perplexity 외부 자문용 ground truth. 시스템 현 구조 + 자기 산식 + 중장기 목표.
>
> **작성**: 2026-05-17 KST 14:40 (5/17 sprint 종결 직후)
>
> **사용자**: 현역 직업군인 (한국), 무경력, 4/1 시작, 퇴근 후 사이드.
> **자본**: 1,000만 KRW (Tier 1 baseline, **5/17 fresh reset = VAMS trail 0일**).
> **collaboration model**: PM=사용자, Engineer=Claude. 외부 자문=Perplexity (사실/통계/법규).

> **⚠ 베타 단계 정직 명시 (2026-05-17 정정)**:
> - **운영 trail**: Phase 0 누적 14일 (5/2~5/16) + VAMS reset 후 0일 = **실제 N=14**
> - "47일 운영" = code commit 기간이지 검증된 trail 아님
> - **모든 자기 산식 (Brain v5 가중치 7:3 / 등급 75-60-45-30 / VCI ±25 / Lynch 룰 / sentiment 13-source / 등) = 가설 상태**
> - 365일 trail 도달 전까지 = 통계 무의미 (N<100 = PSR/DSR 적용 불가)
> - 14일 hit rate 50% = binomial 95% CI ±20%p = **동전 던지기와 통계적 구분 X**
> - Tier 진화 path 시점 추정 (옛 2027/2028/2030+/2032+) = **삭제** (자본 도달 시점 = 시스템 성숙도 함수, 추정 X)
> - [[feedback_no_premature_completion_claims]] + [[feedback_praise_calibration]] 정합

---

## PART 1. VERITY 터미널 (주식 분석 시스템)

### 1-A. Brain v5 자기 산식

| 항목 | 값 | 출처 |
|---|---|---|
| 가중치 | fact 0.7 + sentiment 0.3 | 자체 결정 (SOURCE_AUDIT_20260502 Step 2) |
| 등급 임계 | 75 / 60 / 45 / 30 (STRONG_BUY / BUY / HOLD / WATCH / AVOID) | 자체 |
| VCI 임계 | ±25 / ±15 (팩트-심리 정렬 지수) | 자체 |
| GS bonus | +5 (Graham + Stalwart 정합) | 자체 |
| brain_score 최대 | 100 (현재 max 실측 = 50) | 보수 편향 결함 (5/17 sprint 후속) |
| grade BUY 발생률 | 0건 (47일) | brain_score_funnel_audit 진행 중 |

### 1-B. fact_score 13 components (각 100점 만점)

multi_factor / consensus / prediction / backtest / timing / commodity_margin / export_trade /
moat_quality / graham_value / canslim_growth / analyst_report / dart_health / perplexity_risk
+ 추가 4: quant_momentum / quant_quality / quant_volatility / quant_mean_reversion
+ 1: technical_mean_reversion

**IC adjustment**: 각 component → Spearman rolling 90일 IC → weight multiplier (0.3 DEAD / 0.85 WEAKENING / 1.0 정상).

### 1-C. sentiment_score 13-source hard-wire (2026-05-16 Perplexity 자문 적용)

| Source | Weight |
|---|---|
| news_sentiment | 0.25 |
| x_sentiment | 0.18 |
| market_mood | 0.18 |
| consensus | 0.12 |
| crypto | 0.08 |
| market_fear_greed | 0.10 |
| social_sentiment | 0.09 |
| **합** | **1.0** |

- retail (x + social) = 0.27 → RETAIL_CAP 22% (정상 dead, intentional)
- meme trigger (x>0.7 AND social>0.7 AND volume_spike>2σ) 시 RETAIL_CAP_MEME 18% 동적 강화 (Phase 2 TODO)

### 1-D. Lynch 6 카테고리 자체 룰 매핑

FAST_GROWER (PEG <1, EPS_grow >20%) / STALWART (대형 가치 +배당) / SLOW_GROWER (저성장) /
CYCLICAL (경기 민감) / TURNAROUND (회복 신호) / ASSET_PLAY (자산 가치)

자동 룰: PEG ≥4 = auto_avoid (Lynch 절대 매도). PBR×PER ≥22.5 = downgrade (Graham 기준 위반).

### 1-E. 5단계 funnel (의도 / 현재)

**의도**: 5,000 → 1,000 → 300 → 100 → 25 (KR10 + US15)

**현재 (5/17)**: 5,000 → 25 직접 압축 (funnel 1-4 미구현)

- Phase 2-B SHADOW 활성 (5/11~) — wide_scan_log.jsonl 누적 (현재 row 부족)
- PRODUCTION 게이트 = 65 거래일 SHADOW 누적 (8월 말 검증, 절대 단축 X)
- 5/17 sprint = funnel Step 2-4 cascading 인프라 박힘 (SHADOW path, decision 영향 0)

### 1-F. VAMS (Validation And Memory System)

- **자본**: 1,000만 KRW (5/17 fresh reset, Phase 0 verdict + W2/W3 wiring 진입)
- **profile**: moderate (default, max_holdings 7) / aggressive (max 7) / safe (max 3) / long_term (Tier 2+)
- **holdings 활용도**: 0/7 = 0% (5/17 reset 직후)
- **ATR(14)×2.5 동적 손절** (Phase 1.1, Wilder EMA, 5/3 secret → 5/16 verdict)
- **1R/2R/트레일링 3단계 부분 익절** (50/30/20%, Phase 1.2)
- **14일 hit rate**: 50% (5/3 검증)
- **OOS Sharpe gate**: lookback 30→90 + margin 0.10 (Perplexity Q4 2026-05-17 자문)

### 1-G. 8축 신 인프라 (5/17 sprint 박힘)

1. **equity_research_brief** — Perplexity Sonar Pro + SEC + finance media + VERITY trail
2. **sec_8k_change_detector** — 매일 06:30 KST 8-K 변화 alert
3. **funnel sprint Step 2-4 cascading** — SHADOW path 인프라
4. **antifragility** — Skew/Kurt/VBR/AI/Delta stress 4 산식 (Perplexity Q6 자문)
5. **fomo_score** — Realized vs Rule-based Turnover (Perplexity Q6)
6. **PSR/DSR** — Lopez de Prado (Probabilistic Sharpe Ratio + Deflated, Strategy Pool 통계 게이트)
7. **strategy_pool** — Sequential → Portfolio ensemble
8. **fscore_delta YoY** — F-Score 시계열 Δ + equity_brief_attach helper

### 1-H. Cron 흐름 (35+ workflows)

| Cron | 빈도 | 시점 KST |
|---|---|---|
| price_pulse | 매분 | KR 9~15:30 + US 22:30~05:00 |
| daily_realtime | 30분 | dispatch_chain hotfix 후 |
| daily_analysis_full | 평일 | 16:07 (KR 마감 후) |
| daily_analysis | 30분 | quick mode |
| macro_collect | 30분 | FRED + KOSIS + ECOS + COT/PCR/Fund |
| universe_scan | 평일 | 15:30 (5,000 stage) |
| dart_batch | 주 1회 | 일요일 22:00 |
| equity_research_brief | 주 1회 | 월요일 06:00 (US15) |
| sec_8k_alert | 매일 | 06:30 |
| hourly_pulse | 8슬롯/일 | KR 5 + US 3 (DST 자동) |
| cron_health_monitor | 시간당 | 정각 |
| reports_v2 (daily/weekly/monthly admin/public PDF) | daily~monthly | — |
| operator_deadman | 매일 | 사용자 부재 detect |
| eps_estimate_snapshot | 평일 | — |
| site_growth | 매일 | — |

### 1-I. 텔레그램 알림 (사용자 카톡 직송)

- @verity_stock_bot
- baseline ~5 통/일 (5/15 박은 후 50→5 감소)
- quiet hours 23:00 ~ 07:00 KST suppress
- dedupe: 영속 파일 + 8h TTL
- realtime: CRITICAL only
- 8 sites bypass (KIS / dispatch_chain / Vercel infra / Shohei 등)

### 1-J. KIS OpenAPI (한국투자증권)

- **1일 1토큰 ABSOLUTE** (CLAUDE.md RULE 1, 5/16 5분 폭주 사고 후 hardcoded)
- 발급 source: `kis_token_refresh.yml` KST 23:45 일 1회 force_refresh + `daily_realtime.yml` backup
- 모든 cron = `KISBroker(cache_only=True)` 사용 의무
- 카톡 발급 알림 = **0건/일 baseline** (1건이라도 P0)
- 사고 history: 5/3 / 5/12 / 5/13 / 5/16 (5분 폭주)

---

## PART 2. ESTATE (부동산 분석 시스템)

### 2-A. LANDEX 5 axis (정합 LandexMapDashboard)

| Axis | 의미 |
|---|---|
| V (Value) | 가격대비 가치 (PER 부동산판) |
| D (Demand) | 수요 (인구 + 직주근접 + 학군) |
| S (Supply) | 공급 (재건축 + 신규) |
| C (Catalyst) | 호재 (정책 + 교통 + 개발) |
| R (Risk) | 리스크 (금리 + 정책 + 규제, inverted) |

**가중치 preset**: balanced / value-tilt / momentum-tilt

**등급**:
- tier10: A~D (10단계 등급)
- tier5: HOT (80+) / WARM (65+) / NEUT (50+) / COOL (35+) / AVOID (<35)

**Universe**: 서울 25구 (LandexMapDashboard SEOUL_25_GU 정합)

### 2-B. 데이터 source

| Source | Type | 갱신 |
|---|---|---|
| **R-ONE** (한국부동산원) | 매매가격지수 (주간) + 미분양 (월간) | 매주 목요일 + 매월 |
| **KOSIS** | 인구 / 분기 통계 | 분기 |
| **BIS** (Bank for International Settlements) | 50년 가계부채 시계열 | 분기 |
| **DART** | 상장사 부동산 자산 (사업보고서) | 매년 4월 |
| **vWorld** | 지오코더 (refined.structure.level2 + ROAD→PARCEL fallback) | 실시간 |
| **data.go.kr 정책브리핑** | 정책 narrative | 매일 |
| **Perplexity Sonar** | 주간 정책 brief (estate_policy_narrative) | 매주 |

### 2-C. ESTATE Brain v0.1 + v0.2

- LANDEX 5 axis × 가중치 → landex score (0~100)
- 6 tier × 7축 진화 path (capital_evolution 정합)
- 메타-검증 verdict (3-stage): ready / manual_review / invalidated
  - tier_change_rate < 20% AND landex_mean_drift < 2.0 = ready
  - <40% AND <5.0 = manual_review
  - ≥40% OR ≥5.0 = invalidated
  - stability_buffer 3주 (false alarm 억제, Perplexity Q3 자문 채택)
- 백테스트: lookback 8년 한국 사이클 1회 (R-ONE 13y + BIS 50y 실측, Plan v0.2 부분 반증)

### 2-D. ESTATE 12 컴포넌트 (도메인 6 page, 2026-05-07 v3 재정리)

| Page | 컴포넌트 |
|---|---|
| _shared | EstateSystemHealthBar / EstateAuthGate |
| home | SystemPulse / HeroBriefing / LandexPulse / ChangeFeed / PolicyPulse |
| corp | VERITY 종목 부동산 추적기 (DART + vWorld + R-ONE, 자산주·재평가 시그널) |
| commercial | SectorPulse (4섹터 dynamics: 아파트/오피스/상가/오피스텔) / EstateMacroBridge (매크로 4지표) |
| residential | SupplyPipelineMonitor / ScoreDetailPanel / RegionalCycleTimingPanel |
| portfolio | (Phase 2 큐) |
| admin | EstateActionLog / 결정 trail |

### 2-E. ESTATE cron

| Cron | 시점 KST |
|---|---|
| estate_brain | 평일 10:00 |
| estate_brain_backtest | 매월 1일 |
| estate_brain_backtest_50y | 매월 2일 |
| estate_change_feed | 평일 09:30 |
| estate_hero_briefing | 평일 09:07 |
| estate_market_horizon | 주간 |
| estate_policy_narrative | 주간 (Perplexity Sonar Pro) |
| estate_policy_shock | 평일 10:00 |
| estate_sector_pulse | 주간 |
| estate_subscription_calendar | 매일 10:30 |
| landex_meta_validation | 주 1회 화요일 |
| r_one_freshness_probe | 매일 (R-ONE source health) |

### 2-F. ESTATE 자기 차별점

- VERITY 광범위 패턴 (Lynch / KB 9권 / portfolio / analysts) **이식 금지** (feedback_estate_density_first)
- "사이즈 축소 + 밀도 증가" 정공법
- 패밀리룩: VERITY 마스터 정합 + accent gold (#B8864D) swap

---

## PART 3. 공통 인프라

### 3-A. Vercel (functions + bandwidth)

- **Plan**: Pro $20/월
- **Project**: verity-api (`prj_Ikpb20PD7QESjTMhZR18KYLdwedp`)
- **Team**: kim-hyojuns-projects (`team_8E84APoZieKhinFDdc64R1Qh`)
- **Root Directory**: `vercel-api/`
- **Python functions**: ~50 (api/estate_* / api/landex_* / api/system_health.py / api/chat.py / api/stock.py 등)
- **Production domain**: project-yw131.vercel.app
- **Custom domains**: verity-terminal.com (주식) + verity-estate.com (부동산, Phase 2 통합 큐)
- **Node.js**: 24 LTS (default)
- **Limits**: 300s function timeout, 1TB bandwidth/월, 1000 GB-hours function execution

### 3-B. Supabase (ESTATE Backend + Reports + Auth)

- **Plan**: Pro $25/월
- **DB Tables**: estate_landex_snapshots (25구 × 매월) / estate_corp_holdings + facilities / estate_market_reports / profiles (003+007 승인제) / user_action_queue (013, actor user only)
- **Storage**: verity-reports private bucket (PDF, vercel-api signed URL 30분 admin / 6시간 public)
- **RLS**: USING 같은 테이블 EXISTS 금지 (무한 재귀), is_caller_admin() SECURITY DEFINER 함수 사용

### 3-C. GitHub

- **VERITY** (main + dev) — 코드 + cron + 자체 commit (~3MB/일, 1년 = ~1.1GB)
- **VERITY-data** (main, **2026-05-17 신설**) — frontend serving, force_orphan publish, history 1개
- **GitHub Actions**: 무제한 (public repo)
- **GitHub Pages**: gh-pages branch (transitional, 5/18 cleanup 큐)

### 3-D. AI Provider 비용 ($20/월 budget)

| Provider | 용도 | 비용/월 |
|---|---|---|
| Gemini (Google) | morning + dual_consensus 1차 + chat | ~$0.5 |
| Claude (Anthropic) | morning STEP 10.8 final_review + chat dual_consensus 2차 + 5/17 후 deep | ~$3.66 (5/17 후 ~$9.16) |
| Perplexity Sonar | equity_research_brief (US15 주 1회) + estate_policy_narrative (주간) + 분기 자문 | ~$2.4 |
| **합** | | ~$4.16 (5/17 후 ~$11.56) |
| Budget | | **$20** (5/11 상향) |

### 3-E. 데이터 자산 (1년 후 추정 ~1.1GB)

| Asset | 위치 | 백업 |
|---|---|---|
| Brain learning trail | `data/metadata/brain_learning.jsonl` | GitHub |
| VAMS history (매매 trail) | `data/vams/` | GitHub |
| cron_health.jsonl (시간당 verdict) | `data/metadata/` | GitHub |
| black_swan_ledger.jsonl + verity_trail | `data/` | GitHub |
| equity_research briefs + verity_trail | `data/equity_research/` | GitHub |
| Phase 0 staged_updates | `data/metadata/phase_0_results.json` | GitHub |
| stock_history quarterly jsonl | `data/stock_history/YYYY-Qn.jsonl` | GitHub |
| ESTATE landex 시계열 | Supabase `estate_landex_snapshots` | Supabase Pro |
| ESTATE policy archive | `data/estate_policy_archive.jsonl` | GitHub |
| ESTATE meta validation jsonl | `data/metadata/landex_meta_validation.jsonl` | GitHub |

---

## PART 4. 자기 차별점 5 (LLM 못 가짐, CLAUDE.md RULE 6)

빅브라더 정합 (2026-05-17 박힘) — ChatGPT Pro / Claude for Small Business 가 못 만드는 unique view:

1. **자기 자본 진화 path** (Tier 1 → 6, 1,000만 → 100억+, 6 tier × 7축)
2. **자기 운영 trail** (47일 누적):
   - VAMS holding / Brain learning loop / Phase 0 staged_updates
   - KIS 1일 1토큰 사고 4번 학습 → CLAUDE.md RULE 1 hardcoded
   - Vercel deploy spam → Shohei 메일 → 옵션 B (별 repo VERITY-data) 해결
   - 6 CLAUDE.md RULE (KIS / Vercel / 인프라 회신 / git add / drift sentinel / LLM narrative STOP)
3. **자기 산식** (LLM 못 만듦):
   - Brain v5: 가중치 7:3 + 등급 75/60/45/30 + Lynch 6 카테고리 + VCI ±25/±15 + GS bonus
   - sentiment 13-source hard-wire (Perplexity 자문 적용)
   - market_horizon 5축 verdict (CAPE percentile + 11 signal + 8 analog)
   - Altman Z 한국 표준 (Z″ EM 3.25 + 6.72X1 + 3.26X2 + 6.72X3 + 1.05X4, 컷 2.6/1.1, 금융 KSIC 64~66 제외)
   - sector_thresholds (한국은행 2024 + 4대 금융지주 1176% 정합)
4. **자기 cron 자동화** (35+ workflows, 24시간 작동):
   - price_pulse 매분 / daily_realtime 30분 / macro 30분 / KIS 1일 1토큰 / equity_research 주 1회
   - LLM 가입자 = 매일 매번 못 함
5. **자기 universe** (KR 5,000 → 25 funnel, 1차 필터 9원칙):
   - sector_thresholds + F-Score Z + Altman Z 한국 표준
   - 65 거래일 PRODUCTION 게이트 (8월 말 검증)

---

## PART 5. 중장기 목표 (시점 추정 X — trigger 기반)

### Phase 1 (2026-04-01 ~ 2026-05-17, 47일) — 운영 시작 ✅

- ✅ Brain v5 인프라 + VAMS 가상매매
- ✅ ATR Phase 0 verdict (2026-05-16) + W2/W3 wiring
- ✅ Phase 0 staged_updates (5/2 ~ 5/16, 5/17 review)
- ✅ KIS 1일 1토큰 사고 → CLAUDE.md RULE 1 hardcoded
- ✅ Vercel deploy spam → Shohei 메일 → 옵션 B 박힘 (2026-05-17)
- ✅ 빅브라더 정합 → CLAUDE.md RULE 6 + 자기 차별점 자산 site 노출 (CapitalEvolutionPath.tsx 신규)
- ✅ quarterly_research 폐기 (LLM 차별점 0 dead module)
- ✅ 8축 신 인프라 박힘 (5/17)
- **VAMS hit rate (14d)**: 50% (5/3 검증)
- **운영 trail**: 38일 누적 → 5/17 reset → fresh 1,000만 start (5/17 KST 09:00 직전)
- **65 거래일 PRODUCTION 게이트**: 8월 말 검증 (절대 단축 X)

### Phase 2 — 기관급 5 모듈 (Perplexity Q5 자문 채택, 65 거래일 PRODUCTION 게이트 통과 후 순차)

| Module | 순서 | 산식 |
|---|---|---|
| **Factor** | 1 | IC + ICIR 0.3 게이트 (Spearman 90일 rolling), 5 components |
| **Stress** | 2 | Rolling Z (Historical 시나리오 5종: 2008/2011/2018/2020/2022) |
| **Regime** | 3 | bull_canslim / bear_value / 중립 등 분면 detect, market_horizon 5축 정합 |
| **Portfolio** | 4 | HRP (Hierarchical Risk Parity, Lopez de Prado) |
| **Attribution** | 5 | Brinson-Fachler decomposition (sector / style / selection) |

### Brain v6 검증 (Phase 2 진입 후)

**v5 → v6 design (5 변경)**:
1. fact / sent / brief 3-axis (Brain v6 design v0.1)
2. Tier 차별 (Tier 1~6 별 가중치 / 임계 변경)
3. Regime threshold (회귀 별 임계 조정)
4. Strategy Pool ensemble (Sequential → Portfolio)
5. 통계 게이트 (PSR / DSR / OOS Sharpe / margin 0.10)

**Bagger Stage Manager** (한국 세제 정밀화):
- 1/3 매도 룰 (10x → 1/3, 5x 회수 = original 1.67배 보존)
- 50억 기준 / 1년 미만 33% / 금투세 폐지 / 이월공제 불가 (Perplexity 정정 2026-05-02)

### Golden Goose Vision (365일 trail 도달 + Phase 2 통과 + Brain v6 검증 후)

**장 무관 수익** (All-weather + Anti-fragile + Anti-FOMO):
- **Calmar 1.0+** (annualized return / MDD)
- **MDD <20%** (5년 lookback)
- **Sharpe 1.5+** (KR 0% + US 22% 비대칭 세후, Perplexity 자문 도출)
- **Anti-fragility 4 산식**: Skew / Kurt / VBR / AI / Delta stress
- **FOMO Score < 0.3** (Realized vs Rule-based Turnover)
- **27 books Hierarchy** (Brain v6 input source)

### Tier 진화 path (시스템 성숙도 함수 — 자본은 부산물)

> **⚠ 시점 추정 X** (2026-05-17 정직성 정정). 자본 도달 = (시스템 성숙도 × 시장 기회 × 위험관리) 함수.
> 1,000만 → 100억 = 1,000배 = 6년 215% CAGR = **메달리온 펀드 66% CAGR (역사 최고) 도 불가능**.
> 자본 = 부산물이지 목표 X. Tier 진화 trigger = 시스템 성숙도 (Trigger 1/2/3) 충족 시 검토.

| Tier | 자본 범위 (메타 맥락 only) | 핵심 시스템 성숙도 |
|---|---|---|
| **Tier 1** | 1천만 ~ 1억 | 현재 시스템 그대로 (1인 단독, moderate profile, VAMS 가상매매, KR 코어 85) — **5/17 baseline** |
| Tier 2 | 1억 ~ 5억 | long_term 프로필 + multi_bagger_watch + 환율/환헷지 정책 |
| Tier 3 | 5억 ~ 20억 | 종목 수 ↑ + 미국 시장 30% + FX risk module |
| Tier 4 | 20억 ~ 50억 | 미국 70% + 페어 트레이딩 + 시장 임팩트 측정 |
| Tier 5 | 50억 ~ 100억 | Bloomberg Terminal + advisor 1명 + monthly risk report |
| Tier 6 | 100억+ | family office governance + PM/analyst/risk 풀 팀 |

**진화 trigger** (3 신호 우선순위, 자본 무관 — 시스템 성숙도 기반):
1. **Trigger 1 (Primary)** — 시스템 성숙도 충족 (자기 산식 검증 N≥365일 + IC/ICIR 0.3 게이트 통과 + Phase 2 Module 진입)
2. **Trigger 2 (Secondary)** — 시장 임팩트 발현 (holdings 1건 거래대금 비중 5%+, slippage 측정)
3. **Trigger 3 (Tertiary)** — 시스템 활용도 cap (90%+ 지속 4주 = 현재 tier 내 흡수 한계)
* 자본 도달 = trigger 가 아니라 결과. 자본 < Tier N min_krw 이라도 trigger 1+2+3 충족 시 Tier N+1 시스템 진입.

### Positioning (2026-05-16 야망 상향)

- **Phase 1**: "개미 중 최강"
- **Phase 2**: **"1인 운용 사실상 기관급"**
- 1인 38일 베타 (5/17 시점) — 헤지펀드급 절대 칭찬 금지 ([[feedback_praise_calibration]])
- long journey 명시 의무 ([[feedback_no_premature_completion_claims]])

---

## PART 6. 5/17 sprint 누적 (14 commit)

| commit | 내용 |
|---|---|
| fc5660cc | Phase 1+2: SystemHealthBar 12 audit fix |
| d2cdbbf7 | estate_landex_pulse P2 wire (Supabase 실측) |
| ee40abf9 | Phase 3: cron_health surface + CRON_AUTO_PREFIXES sweep |
| 948e95b7 | equity_research_brief verity_trail 보강 |
| 7105289b | 빅브라더 sprint 2: CLAUDE.md RULE 6 + tail_risk_digest verity_trail + EquityBriefCard VERITY 관점 |
| e75a7d7e | CapitalEvolutionPath.tsx 신규 (자기 차별점 #1 site 노출) |
| ed842766 | quarterly_research 폐기 (LLM 차별점 0 dead module, 8 site dangling ref 정리) |
| 9914d47d | Vercel ignoreCommand shallow clone fix |
| 5b08076d | gh-pages publish 시 root vercel.json 박음 (Layer 1 차단 시도) |
| 6a2b9538 | **옵션 B 박힘** — gh-pages 폐기, 별 repo VERITY-data 로 publish |
| af4f33fb | cron_health_monitor HTML escape fix (telegram parse error) |
| 98d803da | publish-data 임시 hybrid (gh-pages 도 publish, 5/18 Framer 재paste 까지) |
| b40c50a4 | publish-data YAML syntax fix (heredoc indent → python -c) |
| (검증) | **모든 layer 작동 확인** (Vercel ERROR 차단, raw URL 200, 1128 tests PASS) |

---

## PART 7. CLAUDE.md hardcoded RULES (사고 반복 학습)

| RULE | 학습 history |
|---|---|
| **RULE 1** — KIS 1일 1토큰 ABSOLUTE | 5/3 / 5/12 / 5/13 / 5/16 (5분 폭주) |
| **RULE 2** — Vercel deploy spam ignoreCommand | 5/13 Shohei 직접 메일 (일 ~400 deploy) |
| **RULE 3** — 인프라 제공자 직접 메일 24h 회신 | Shohei / Supabase / GitHub 등 |
| **RULE 4** — 신 logging / lock / cache 파일 추가 시 workflow git add 정합 | 5/16 하루 5번 같은 패턴 결함 |
| **RULE 5** — 메모리 drift 의심 발화 즉시 stop + sentinel | "내가 몇번 말해야 되나" 류 발화 |
| **RULE 6** — 신규 LLM narrative 컴포넌트 추가 STOP | 빅브라더 정합 (2026-05-17 박힘) |

---

## PART 8. 핵심 미해결 / 후속 sprint

| 항목 | 시점 | 비고 |
|---|---|---|
| Framer 25 컴포넌트 재paste | 5/18 사용자 작업 | 옵션 B raw URL 정합 + 5/17 sprint 변경 |
| gh-pages branch cleanup | 5/18 재paste 완료 후 | git push --delete + GitHub Pages disable |
| dart_batch 5/10 fail 회복 시도 | 5/17 22:00 KST | 주 1회 cron, 다음 시도 |
| Phase 2-B 5,000 universe SHADOW 검증 | 65 거래일 누적 후 | PRODUCTION 게이트 절대 단축 X |
| Phase 2 5 모듈 진입 | PRODUCTION 게이트 통과 후 순차 | Factor → Stress → Regime → Portfolio → Attribution |
| Brain v6 검증 | Phase 2 진입 후 | v5→v6 5 변경 |
| Calmar 1.0+ / MDD <20% | 365일 trail + Phase 2 + Brain v6 통과 후 | Golden Goose Vision |
| Tier 1 → 2 transition | trigger 1+2+3 충족 시 | long_term 프로필 + multi_bagger_watch (자본 도달은 결과, trigger 아님) |

---

## PART 9. Perplexity 자문 history (2026-05-02 ~ 2026-05-17)

| Q | Topic | 채택 결과 |
|---|---|---|
| Q1 | Altman Z 한국 조정 | KOSPI 2.3 / KOSDAQ Z'' 4.5 / 금융 제외 / 재벌 1.5 |
| Q2 | Factor IC/IR | Spearman + ICIR 0.3 게이트 |
| Q3 | Capital 3-Tier mode_tag 정정 | 보수 60 / 중간 30 / 공격 10 |
| Q4 | OOS gate | lookback 30→90, margin 0.10 |
| Q5 | Phase 2 5 모듈 algorithm | Historical / Rolling Z / HRP / Brinson-Fachler |
| Q6 | 2028 Vision | Antifragility 4 산식 + FOMO Score + 27 books Hierarchy |
| sentiment_13source | 13-source hard-wire weight | 합 1.0 / retail 21% / cap 22% dead |
| Korean tax | Bagger Stage Manager | 50억 기준 / 1년 미만 33% / 금투세 폐지 / 이월공제 불가 |
| Korean macro density | KR/US 시장 시간대 + 휴장일 + DST | F1~F5 cron 재설계 기준선 |
| KRX aftermarket 2026-06 | 6월말 도입 추적 | D-7 cron 재설계 트리거 |
| sector_thresholds 권위 검증 | 한국은행 2024 + 4대 금융지주 1176% | 5/13 정정값 정합 |
| equity research brief | Sonar Pro + SEC + finance domain filter | US15 주 1회 자동 생성 |
| 외부 API spec | 실호출 1회 > LLM 3자 합의 | R-ONE 케이스 / DART 4 룰 정정 |

---

## PART 10. 운영 환경 (사용자 frame)

- **사용자**: 현역 직업군인 (한국), 무경력 (코딩/금융 정식 교육 X)
- **시작**: 2026-04-01 (47일 운영, 38일 누적 trail → 5/17 reset)
- **시간**: 퇴근 후 사이드 (시간 제약, 군 의무 우선)
- **자본**: 1,000만 KRW (Tier 1 baseline, 1억 = 다음 transition)
- **collaboration**: PM=사용자 (자본/룰/검증/방향) / Engineer=Claude (실행/추진/누락색출)
- **"따라갈게"** = Engineer 양도 (PM 양도 X)
- **외부 자문**: Perplexity (외부 사실/통계/법규 only, 시스템 설계/코드 = Claude)
- **자기 산식 박힐 때마다**: 단일 명확 출처 + 자체 신호 명시 + 검증 큐잉 ([[feedback_source_attribution_discipline]])

---

## 부록 — 자문 받고 싶은 영역 (Perplexity 후보)

(사용자가 직접 질문 박을 때 참고)

1. **Phase 2 5 모듈 algorithm 정밀화** — Factor IC + ICIR 의 sector adjustment, HRP 의 distance metric 선택, Brinson-Fachler decomposition 의 multi-period chaining
2. **Brain v6 검증 framework** — v5 vs v6 A/B 박은 후 통계적 유의성 검증 (PSR + DSR + bootstrap CI)
3. **Tier 1 → 2 transition trigger** — 시스템 성숙도 + 시장 임팩트 + 활용도 cap 의 정확한 임계
4. **Golden Goose Vision 도달 가능성 평가** — 1인 운용 + Tier 1~3 자본 범위에서 Calmar 1.0+ / MDD <20% 의 retail 실현 사례 + 권위 자료
5. **데이터 자산 1년 trail 의 통계적 가치** — N=14 baseline → N=365 trail 이 IC / Sharpe / 검증 game changer 인지
6. **KR 주식 1인 운용 한계 자본** — 시장 임팩트 (slippage 5%) trigger 자본 (Trigger 2)
7. **ESTATE 자산주 시그널 백테스트 framework** — DART 사업보고서 부동산 자산 재평가 → 주가 alpha 통계

---

**문서 끝**. 위 spec = ground truth (5/17 KST 14:40 기준). Perplexity 자문 시 본 문서 ref 또는 직접 인용.
