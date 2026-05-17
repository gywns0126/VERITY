# Source Tier Spec — VERITY 2026-05-18

**Purpose** — 베테랑 진단 (2026-05-18) 권고 정합: **"많다 vs 적다" 프레임 폐기, "위계 + pruning 룰" 으로 재정의**. 현 시스템 모든 source 의 Tier 1/2/3 분류 + 충돌 처리 룰 + SPOF 식별. 8월 게이트 (PRODUCTION 진입) 전 인프라 자산 확정.

**Scope** — 3 layer:
1. **Layer A**: External data source (collector level, ~30종)
2. **Layer B**: fact_score 14 components (verity_brain.py:_compute_fact_score)
3. **Layer C**: sentiment_score 7 source (verity_brain.py:_compute_sentiment_score)

**원칙** ([[feedback_no_premature_completion_claims]] 정합):
- 본 spec = **인벤토리 + Tier 분류 + 룰 spec only**. 코드 변경 X (별 sprint).
- Source 신규 add / 제거 = 본 spec 갱신 의무 (drift 방지).
- 8월 게이트 후 IC 측정 결과로 Tier 재분류 (continuous adjustment).

---

## §0 — Tier 정의

| Tier | 정의 | 행동 룰 |
|---|---|---|
| **Tier 1 (Primary)** | 이게 죽으면 시스템 마비. 모든 의사결정의 기준점 | SPOF mitigation 의무 (fallback 또는 mode degradation) |
| **Tier 2 (Secondary)** | Primary 보완 / 교차검증. Primary 다운 시 fallback | 충돌 시 Tier 1 우선, 없을 시 weight 50% 감산 |
| **Tier 3 (Specialized)** | 특정 분석에만 사용 (지역 / 섹터 / 기간) | 항상 호출 X, 목적 명확하면 정당 |

---

## §1 — Layer A: External Data Source (collector level)

### Tier 1 (Primary, SPOF mitigation 의무)

| Source | 영역 | SPOF mitigation 현 상태 | 비고 |
|---|---|---|---|
| **KIS** | KR 시세 + 미국주식 (cache) | ⚠️ 1일 1토큰 = 강한 SPOF. 결정 22 (2026-09) 대체 broker 조사 큐잉 (LS/한투/대신/키움 등) | CLAUDE.md RULE 1 |
| **DART** | KR 공시 / 사업보고서 | ⚠️ 단독, KR 공시 대체 X. 20K/day 한도 | [[project_dart_api_2026_constraints]] |
| **FRED** | US 매크로 (CPI/실업/recession prob) | ✓ multpl.com (CAPE) + ECOS (KR rate) 부분 보완 | F1+F2 5/18 박힘 (cdabc548) |
| **Vercel** | API 인프라 + frontend serve | ✓ 옵션 B 박힘 5/17 (VERITY-data 별 repo) — [[project_vercel_gh_pages_chronic]] | 5/13 Shohei 메일 = SPOF risk 인지 |
| **Supabase** | DB (profiles / user_action_queue / reports Storage) | ⚠️ 단독, RLS 자체 회귀 사고 1회 ([[feedback_supabase_rls_no_self_subquery]]) | private fallback X |
| **R-ONE** | KR 부동산 매매지수 / 미분양 | ⚠️ 단독, KOSIS 우회 검토 ([[project_rone_api_spec]]) | 13y 시계열 핵심 |
| **GitHub Actions** | cron 인프라 (워크플로 ~40종) | ⚠️ 단독. 5분 미만 cron silent skip 사고 ([[feedback_gh_short_cron_silent_skip]]) | Vercel Cron + 양분 (이중) |

### Tier 2 (Secondary, fallback)

| Source | 영역 | Primary 와 관계 |
|---|---|---|
| **yfinance** | US 시세 fallback | KIS 미국 cache 보완 |
| **pykrx** | KR OHLCV + 거래소 calendar | KIS rate limit 시 fallback. 5/17 박힘 (31a666d7) |
| **KRX OpenAPI** | KR 시세 별 source | pykrx 와 중복 — 미사용 영역 점검 의제 |
| **Finnhub** | US 컨센서스 / 내부자 + 13F | analyst_report / institutional bonus 입력 |
| **SEC EDGAR** | US 사업보고서 (10-K/10-Q) | sec_financials moat 입력 |
| **ECOS (한국은행)** | KR 매크로 (정책금리 / 국채) | FRED Korea series 와 cross-check |
| **multpl.com** | Shiller CAPE 스크래핑 | FRED 미공개 보완 (5/7 박힘) |
| **vWorld** | KR 지오코더 (estate) | R-ONE 보완 |

### Tier 3 (Specialized)

| Source | 영역 | 호출 빈도 |
|---|---|---|
| **KIRS** | 코스닥 소형주 리포트 (research + research22_1) | 매 full mode (5/18 박힘 3b2a15b0) |
| **네이버 리서치** | 종합 증권사 리포트 | 매 full mode |
| **빅카인즈** | KR 뉴스 sentiment | sentiment_score 입력 |
| **Perplexity Sonar Pro** | 외부 리스크 scan + equity brief | 주 1회 (US15) + 매 full top-10 (A7) |
| **Gemini Flash** | DART 사업보고서 AI 분석 | 주말 full only |
| **CBOE** | 옵션 데이터 | 별 분석 (cboe_options_collector.py) |
| **CFTC COT** | 선물 포지션 | commodity 분석 |
| **NewsAPI** | 영문 헤드라인 | sentiment / events |
| **alt_data** | 위성 / Google Trends 등 | 별 신호 |
| **BIS** | 50y 가계부채 | estate backtest (1회성) |
| **KOSIS** | KR 통계청 | estate / 인구 |
| **multpl CAPE** | (Tier 2 보완) | |

### Tier 폐기 (deprecated, 2026-05-18)

| Source | 이유 |
|---|---|
| **한경컨센서스** | robots.txt `Disallow: /` 전체 차단 (5/18 verify) — 자동화 폐기, manual ingest 만 |
| **gh-pages** | Vercel 옵션 B 박힘 후 임시 hybrid (5/17 후 cleanup 의제, 5/18 ~ Framer 재paste 까지 유지) |

---

## §2 — Layer B: fact_score 14 components

현 가중치 (verity_constitution.json) + 본 spec Tier 분류:

| Component | weight | Tier | 근거 | SPOF / 결함 |
|---|---|---|---|---|
| **multi_factor** | 0.1876 | T1 | 7 부분합 종합 (quant + fundamental + technical) | IC=-0.158 DEAD (5/18 audit) → 0.3× demote, anti-signal flip 의제 |
| **consensus** | 0.1279 | T1 | 컨센서스 EPS/TP (Finnhub + FnGuide) | IC=-0.143 WEAKENING |
| **prediction** | 0.0853 | T2 | AI up_probability | IC=-0.094 DEAD |
| **moat_quality** | 0.0853 | T1 | Hohn + Greenblatt 가치 | KR dart_financials 0/10 입력 부재 (audit §3 A4) |
| **analyst_report** | 0.0784 | T2 | report_summarizer (네이버 + KIRS) | 1/25 hit (5/18 audit) — KIRS 5/18 박힘 |
| **backtest** | 0.0682 | T2 | yfinance 시뮬 | 변수 정합 |
| **export_trade** | 0.0682 | T3 | 수출입 / Finnhub 내부자 | US-only 영역 |
| **graham_value** | 0.0682 | T1 | Graham 가치 산식 (regime bear weighting) | dart 의존 |
| **canslim_growth** | 0.0682 | T1 | CANSLIM 성장 산식 (regime bull weighting) | 28% fallback |
| **timing** | 0.0597 | T2 | 진입 타이밍 sub-score | IC=-0.167 DEAD |
| **dart_health** | 0.049 | T3 | Gemini DART 사업보고서 AI 분석 | 100% fallback (audit §3 A1, weekend full only) |
| **commodity_margin** | 0.0341 | T3 | 원자재 마진 안전 | 100% fallback (audit §3 A6, attach 미작동) |
| **equity_brief_verdict** | 0.03 | T3 | Perplexity Sonar Pro 미장 brief | US15 only, KR 50 neutral |
| **perplexity_risk** | 0.02 | T3 | Perplexity 외부 리스크 | 100% fallback (audit §3 A7, A7 5/18 박힘) |

### 추가 (가중치 X, 보너스/패널티)
- alpha_combined (sub-score 보너스, IC scale 0.5~1.3)
- quant_factors {momentum / quality / volatility / mean_reversion} — verity_brain.py:957 분기
- technical_mean_reversion / kr_fundamental_mean_reversion (Brain Audit §7/§11, IC backfill 검증)
- kis_analysis (KIS 데이터 보너스)
- governance (자사주 + 대주주, treasury_stock)

### Tier 분류 근거 (1차 cut)

- **T1 (5 components)**: weight ≥ 0.07 + 단일 source 결함 시 brain_score 큰 변동. multi_factor / consensus / moat_quality / graham_value / canslim_growth
- **T2 (4 components)**: weight 0.05~0.08, fallback 가능. prediction / analyst_report / backtest / timing
- **T3 (5 components)**: weight ≤ 0.05 + specialized. dart_health / commodity_margin / equity_brief_verdict / perplexity_risk / export_trade

---

## §3 — Layer C: sentiment_score 13 source (5/16 ce36c470 정합, 2026-05-18 정정)

현 가중치 (verity_constitution.json sentiment_score.weights, hard-wire 합 1.000) + Tier 분류:

| Source | weight | Tier | 입력 source | SPOF |
|---|---|---|---|---|
| **news_sentiment** | 0.175 | T1 | 네이버 / 빅카인즈 / NewsAPI 종합 | 단일 영역 dead 시 17.5% 신호 dead |
| **x_sentiment** | 0.125 | T2 | **네이버 검색 + Google News RSS 2차 보도 proxy** (X API 무관, x_sentiment.py:1-7 정합) | X API 무관 → ToS 안전. naming drift 주의 |
| **market_mood** | 0.125 | T1 | KOSPI 종합 mood (자체 산식) | 자체 산식, 안정 |
| **consensus_opinion** | 0.100 | T2 | 증권사 리포트 컨센서스 | analyst_report 와 중복 ([[Layer B]] 와 cross) |
| **social_sentiment** | 0.085 | T2 | 종합 social (네이버 카페 / 디시 / 종토방 등) | 자체 집계, Reddit 미사용 (ToS 안전) |
| **crypto_macro** | 0.065 | T3 | 암호화폐 + 매크로 spillover | risk-on/off proxy |
| **market_fear_greed** | 0.065 | T2 | CNN Fear & Greed Index | 외부 단일 source |
| **geopolitical_score** | 0.060 | T2 | 지정학 risk (신규 5/16) | 한국 지정학 민감도 ↑ |
| **fx_sentiment** | 0.050 | T3 | FX 변동성 / 환율 sentiment (신규 5/16) | institutional 채널 |
| **macro_headlines** | 0.050 | T2 | 매크로 헤드라인 (신규 5/16) | FRED + news 교차 |
| **commodity_sentiment** | 0.040 | T3 | 원자재 + 산업 sentiment (신규 5/16) | KR 정유/철강/화학 cross |
| **global_index_decoupling** | 0.040 | T3 | 글로벌 지수 디커플링 (신규 5/16) | 국가별 spread proxy |
| **market_horizon_link** | 0.020 | T3 | market_horizon 연동 (신규 5/16) | self-reference 회피용 낮음 |
| **합** | **1.000** | | hard-wire (post-hoc normalize 금지) | [[project_sentiment_13source_design]] 정합 |
| **retail (x + social)** | **21%** | | < cap 22% (정상 dead, meme trigger Phase 2 TODO) | AIMM 연구 정합 |

### 위계 평가 (베테랑 진단 정합 + 5/18 정정)

- 가중치 0.175 vs 0.020 = 8.75배 차이 (자문 paste 3배 차이는 outdated 7-source baseline)
- **T1 2개** (news_sentiment 0.175 + market_mood 0.125 = 0.30) 가 결정 main
- **T2 5개** (x_sentiment / consensus / social / fear_greed / geopolitical / macro = 0.485) 보강
- **T3 5개** (crypto / fx / commodity / gid / horizon = 0.215) 특화 신호
- **충돌 룰 부재** = 8월 게이트 전 박을 의제 (§4 참조)

### 5/18 정정 trail (Engineer)

- 자문 paste 인용 "x_sentiment 0.18 가중치" = **5/16 13-source 변경 전 outdated baseline** (commit ce36c470). 현재 0.125 (~30% 하향됨).
- x_sentiment 의 실제 구현 = **2차 보도 proxy** (네이버/Google News RSS, X API 무관, x_sentiment.py:1-7) — ToS 안전, scraping risk X. Perplexity 권고 "X API 유료화 risk" 이미 mitigated.
- 자문 "T1" 분류 권고 → 본 spec **T2 강등** (proxy 신호 품질 + x API 무관 함의). news_sentiment / market_mood 만 T1 유지.
- Social_sentiment 의 Reddit 사용 X 명시 (ToS 안전).

---

## §4 — 충돌 처리 룰 (spec, 코드 변경 X)

베테랑 권고 "충돌 처리 룰 박기" 정합:

### 룰 1: Tier 우선순위
```
Tier 1 vs Tier 1: 최신 timestamp 우선 (둘 다 valid 시 평균)
Tier 1 vs Tier 2/3: Tier 1 우선
Tier 2 vs Tier 3: Tier 2 우선
Tier 3 단독 신호: weight 50% 감산
```

### 룰 2: Source 결함 시
```
Tier 1 결함 (data=None / API 5xx):
  - fallback Tier 2 사용 (가중치 보존)
  - fallback 부재 시 = mode degradation (full → light → quick)

Tier 2 결함:
  - silent skip, weight 재분배 (F1+F2 normalize 패턴 정합)

Tier 3 결함:
  - silent skip, no propagation
```

### 룰 3: Cross-layer 충돌 (Layer A ↔ B ↔ C)

```
fact_score (Layer B) 와 sentiment_score (Layer C) 충돌:
  - brain_weights 의 quadrant-aware fact/sent 비율 적용 (현 분면 dependent)
  - 5/18 F1+F2 후 (0.65, 0.35) 범위, 정합

Layer A (collector) 결함이 Layer B/C 모두 영향:
  - 예: KIS 다운 → multi_factor + technical_mean_reversion + kis_analysis 동시 dead
  - 처리: SPOF mitigation 우선 (KIS fallback broker 의제)
```

### 룰 4: 신호 신선도 (timestamp)

```
Tier 1 데이터 stale > 4h: weight 50% 감산 + alert
Tier 2 데이터 stale > 24h: weight 30% 감산
Tier 3 데이터 stale > 7d: silent skip (가중치 = 0)
```

→ **본 룰 모두 spec only**, 코드 박음은 별 sprint (회귀 risk, RULE 7 정합 — 단일 변수 통제 + PM 승인)

---

## §5 — SPOF 식별 (8월 게이트 전 mitigation 의무)

베테랑 권고 "SPOF 식별" 정합:

| SPOF | 영향 | 현 mitigation | 8월 전 의제 |
|---|---|---|---|
| **KIS 1일 1토큰** | 시세 + 미국 cache 마비 | CLAUDE.md RULE 1 (cache_only mode) | 결정 22 (9월) 대체 broker 조사 — 보류 가능, but Tier 1 SPOF 강함 |
| **Vercel API** | frontend + API 마비 | ✓ 옵션 B 박힘 (5/17, 별 repo VERITY-data) | gh-pages cleanup (Framer 재paste 후) |
| **DART 단독** | KR 공시 layer 마비 | 단독 (대체 source 부재) | mitigation 어려움 — KIS 사업보고서 보강 검토 |
| **Supabase 단독** | DB 마비 (profiles + queue + reports) | 단독 | private mode degradation 검토 (read-only fallback) |
| **GitHub Actions** | cron 마비 (40+ 워크플로) | Vercel Cron 일부 dispatch (양분) | Railway / 자체 cron 일부 이전 의제 |
| **R-ONE 단독** | estate 마비 | 단독 (KOSIS 우회 가능, 차이 큼) | manual ingest fallback |
| **PERPLEXITY_API_KEY** | A7 + equity brief 마비 | 단독 | 단일 vendor lock-in, 8월 후 IC 측정 후 가중치 결정 |
| **FRED 단독** | 매크로 분면 산정 마비 (F1+F2 후 강화) | ECOS Korea series + multpl CAPE 일부 보완 | F1+F2 의존도 ↑ → fallback 강화 의제 |

### 우선순위 (8월 전 처리 권장)

1. **Supabase fallback** = mitigation 부재 (P1)
2. **GitHub Actions 의존도** = Vercel Cron 양분 진행 중 (P2)
3. **KIS 대체 broker** = 결정 22 (9월) 일정 정합 (P2)
4. **DART 보강** = mitigation 어려움 = 보류 (P3)

---

## §6 — 8월 게이트 후 pruning sprint 의제

베테랑 권고 "Pruning sprint 1회 필수" 정합 + Engineer 보강 (continuous down-weight 우선):

### 진입 조건
- 65 거래일 (Phase 0 + reset 후) 누적 = **2026-08-17 ~ 2026-11-15**
- IC 측정 가능 sample (N ≥ 30, [[Perplexity NQ1]] 정합)
- PSR/DSR 적용은 N ≥ 365 후 (2027-05)

### 권장 방식 (Engineer 보강)

**Option A (베테랑 권고)**: prune 박음 (13 → 7 source)
- 정보 손실 risk
- false negative (제거 후 시장 변화 시 다시 add 비용)

**Option B (Engineer 보강)**: continuous down-weight 강화
- IC adjustment 메커니즘 강화 (`factor_decay.py:_STATUS_MULT`)
- DEAD floor 강화 (0.3 → 0.0 강제 검토)
- prune 대신 weight = 0 (코드 보존, runtime degrade)
- baseline 회복 시 자동 부활

**권장**: Option B 우선, A 는 Option B 후 효과 없을 시 마지막 수단

### 진입 의제 (5/17 commit 이미 박혀있음 — [[project_phase_2b_wide_scan]] PRODUCTION 게이트 8/10 정합)

---

## §7 — 본 spec 의 사용 패턴

### Source 신규 add 시

```
1. 본 spec 의 [§1 Layer A] / [§2 Layer B] / [§3 Layer C] 에 entry 추가
2. Tier 1/2/3 명시 + 근거 1-2줄
3. 충돌 룰 (§4) 정합 검증
4. SPOF risk 평가 (§5)
5. 코드 박음 (별 sprint, PM 승인 의무 if 산식 변경)
```

예: 5/18 KIRS scraper 박음 = 본 spec 에 Tier 3 (specialized: 코스닥 소형주) 명시 박힘 ✓

### Source 제거 / 폐기 시

```
1. 본 spec 의 deprecated section (§1 마지막) 에 entry 추가 + 이유
2. 코드 호출 보존 vs 제거 결정 (graceful fallback 추천)
3. 의존 component (Layer B/C) audit
```

예: 5/18 한경컨센서스 deprecated = robots.txt `Disallow: /` ([[Q2_LIVE_FETCH_VERIFICATION_20260518.md]])

### IC 측정 후 Tier 재분류 (8월 후)

```
1. 65 거래일 IC 측정 결과 검토 (factor_decay.py)
2. T1 component 중 IC < 0.03 → T2 강등 검토
3. T3 component 중 IC > 0.10 → T2 승격 검토
4. PM 사전 승인 (RULE 7 정합 — 임계 조정 1회)
```

---

## §8 — 베테랑 진단 핵심 답 정합

베테랑 (2026-05-18) 의 진짜 핵심:

> **"많다 vs 적다" 프레임이 잘못된 거야. "Primary 명확하냐 + 위계 박혔냐 + Pruning 룰 있냐" 가 진짜 질문이야.**

본 spec 진단 결과:
- ✅ **Primary 명확함** (Layer A: KIS / DART / R-ONE / FRED. Layer B: 5 T1 components. Layer C: 3 T1 sources)
- ✅ **위계 박힘** (본 spec §1~§3, 코드 정합은 별 sprint)
- ✅ **충돌 룰 박힘** (본 spec §4, 코드 정합은 별 sprint)
- ✅ **SPOF 식별** (본 spec §5, mitigation 우선순위 박힘)
- ⏳ **Pruning 룰** (8월 후 IC 측정 결과 후 진입, 본 spec §6 의제 박힘)

→ **현 다중 source 구조 = 베타 단계 정상**. 본 spec 박힘으로 인프라 자산 완성. 8월 게이트 진입 가능.

---

## §9 — 변경 추적

| 일자 | 변경 |
|---|---|
| 2026-05-18 | 초기 spec 박음 (3 layer + Tier 분류 + 충돌 룰 spec + SPOF + pruning 의제) |

### 관련 메모리 / 문서

- 베테랑 진단 본문: `터미널 보충 학습 자료. /베테랑_source_tier_pruning_권고_20260518.md` (의제 박을 시)
- [[project_brain_score_funnel_audit]] (5/18 audit 정합)
- docs/COMPONENT_FALLBACK_AUDIT_20260518.md (Layer B 결함 진단)
- docs/Q2_LIVE_FETCH_VERIFICATION_20260518.md (Layer A KIRS / 한경 검증)
- [[project_kis_token_policy]] (Layer A T1 KIS SPOF, CLAUDE.md RULE 1)
- [[project_sentiment_13source_design]] (Layer C 설계, 본 spec 으로 Tier 박힘)
- [[project_phase_2b_wide_scan]] (8월 PRODUCTION 게이트 8/10)
- [[project_brain_v5_self_attribution]] (Layer B 가중치 자체 결정)
- [[feedback_data_collection_verification_mandatory]] (신규 source add 시 검증 의무)

---

**End of spec. 인벤토리 + Tier 분류 + 충돌 룰 + SPOF + pruning 의제 박힘. 코드 변경 0건 (별 sprint, RULE 7 정합). 8월 게이트 진입 자산.**
