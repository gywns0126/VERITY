# UNIVERSE FUNNEL REFORM v0.1

작성: 2026-05-12 / 적용 게이트: 5/17 sprint (ATR verdict 후) / 사용자 결정 = "지금 박아" (PRODUCTION 데이터 0일이라 손실 없음)

근거 자료: `터미널 보충 학습 자료. /터미널 학습 자료 3.pdf` (Perplexity-fetched 2026-05-12, Greenblatt/Fama-French/AQR/GMO + Grinold-Kahn + 미래에셋/KIF 한국 실무 + Evans-Archer/Statman/Yoon 종목수 + Sloan/Piotroski IC decay)

---

## 1. 현행 (As-Is) 문제 진단

```
현행: 5,000 → 1,000 → 300 → 100 → 25 (KR10 + US15)
축소율:        20%      30%     33%    25%
```

| # | 결함 | 근거 |
|---|---|---|
| 1 | **5,000 input 의 임의성** | Greenblatt 3,500 / Fama 9,000 / AQR 1,000-3,000 / GMO 수천 / KR 실무 800-1,000. 5,000 = 어디서도 안 쓰는 숫자. *count* 가 아닌 *criteria* 로 정의해야 함 |
| 2 | **1,000 → 300 (30%)** | top quintile-of-quintile = 표준 cut 아님. 학계 cut convention = quintile(20%) / decile(10%) / vigintile(5%) 계층. 30% 는 어느 layer 도 아닌 임의값 |
| 3 | **최종 25 종목 vs Tier 1 자본 ~1,000만원** | Quantil(EUROSTOXX 50) + Kelly + KR KOSDAQ 왕복 2-4% 거래비용 → 1,000만원에서 5-12 종목이 학계 컨센서스. 20+ = 명백 과도분산 |
| 4 | **KR10:US15 split 근거 0** | Tier 1 에서 미장 보유는 환차익+22% 단일세 + 왕복 2% → cost-prohibitive. 학계 backing 없는 split |
| 5 | **KR factor half-life 동아시아 디스카운트 미반영** | 글로벌 대비 30-60% 짧음 (Value half-life ~0 한국). 현 funnel 은 글로벌 표준 cut 사용 |
| 6 | **Hard exclusion 의 funnel 내 처리** | 관리/SPAC/우선주/유동성절벽 = Stage 0 에서 끝내야 하는데 funnel 단계가 흡수 → noise + compute 낭비 |

---

## 2. 개편안 (To-Be)

```
[Stage 0] Tradable Universe (criteria, fixed count 없음)
[Stage 1] Hard Exclusion (관리/SPAC/우선주/유동성절벽/금융/신규)
[Stage 2] Coarse Filter (Top Quintile, sector-relative composite)
[Stage 3] Medium Filter (Top Decile of remaining)
[Stage 4] Fine Filter (Brain v5 full)
[Stage 5] Conviction Portfolio (Tier-aware sizing)
```

### Stage 0 — Tradable Universe (criteria-based)

**원칙: 숫자 X, 기준 O.** KRX 신규 상장·폐지에 자연 변동 흡수.

- KR: KOSPI 전체 + KOSDAQ 전체 (KONEX 제외)
- US: tradable from KRX 계좌, ADV ≥ $5M (또는 시총 ≥ $500M)
- 결과: ~5,200-5,800 (raw, 변동)

### Stage 1 — Hard Exclusion (절대 제거)

KR 실무 표준 (미래에셋/MK 리서치 정합):

| 카테고리 | 기준 |
|---|---|
| 관리종목 / 투자주의 / 매매정지 / 상장폐지위험 | KRX 지정 D+1 즉시 제거 |
| 자본잠식률 ≥ 50% / 감사의견 비적정 | 동일 카테고리 |
| SPAC | 합병 완료 후 6개월 재편입 검토 |
| 우선주 | 보통주 only (별도 스프레드 전략은 별 universe) |
| 신규 상장 < 12개월 | 1년치 재무 시계열 부재 |
| 금융업 (은행/보험/증권/카드) | P/B·ROE·레버리지 팩터 해석 왜곡 |
| 유동성 절벽 | 시총 < 100억원 OR 일평균 거래대금 < 1억원 |
| 외국 기업 국내 상장 | 세제/공시 기준 상이 |

**결과: ~1,500-1,800** (KR ~900 + US ~700, 한국 실무 표준 수렴 구간)

### Stage 2 — Coarse Filter (Top Quintile, sector-relative)

**Grinold-Kahn 정합**: Stage 1 universe filter = quintile (20%) 이 BR-IC 최적 균형 (MSCI Minimum Vol / Quality / Value 표준).

복합 z-score (sector-neutral):
- Value: B/P, EV/EBITDA, E/P — sector 내 rolling 3y z-score (한국 2009- 가치프리미엄 소멸 정합, `reference_learning_materials_folder` Q1)
- Quality: Piotroski F-Score ≥ 4 + GP/A + ROE
- Momentum: 12-1M return — top 30% (한국 short half-life)
- Accruals: Sloan, 하위 30-40% (낮은 발생액 = 고품질)

복합 합산 → top quintile 잔류.

**결과: ~300-360** (~20% of 1,500-1,800)

### Stage 3 — Medium Filter (Top Decile of remaining)

**Asness et al. (2013) AQR 정합**: composite 단계는 decile (10%) 로 수렴. 여러 팩터 결합 후 IC noise 상쇄 → tighter cut 정당화.

- Brain v5 quick scoring (기존 quick path 유지)
- Sector neutralization (KR 섹터 집중 보정, 윤영섭 2001-2008 51-53종목 한국 시장 implicit)
- Altman Z safety floor (2.99+ 우선)
- Commodity exposure 60%+ 종목은 별도 버킷 (`reference_learning_materials_folder` Q3 commodity 매핑)

**결과: ~30-36** (top 10% of 300)

### Stage 4 — Fine Filter (Brain v5 full)

- Brain v5 full scoring
- MarketHorizon V2.3 KCMI Quality of New Issues check (분기 60%/13건 임계, `project_market_horizon` 백링크)
- 사이클 단계별 보정 (Speculation Extreme = defensive bias)

**결과: ~15-20** (final candidate basket)

### Stage 5 — Conviction Portfolio (Tier-aware sizing)

**자본 Tier 별 동적**:

| Tier | 자본 | 권장 종목수 | KR:US | 근거 |
|---|---|---|---|---|
| Tier 1 | ≤ 1억 (현재) | **6-8** | KR 6 + US 0-2 | Quantil + Kelly + KR 거래비용 |
| Tier 2 | 1-10억 | 15-25 | KR 12 + US 8-13 | Greenblatt 모델 실행 구간 |
| Tier 3 | 10-100억 | 30-50 | KR 20 + US 15-25 | KR optimal 51-53 근접 |
| Tier 4 | 100억+ | 50-120 | KR 40+ + US 30+ | Lynch 광범위 분산 강제 |

**Tier 1 (현재) 핵심**: 6-8 종목, half-Kelly sizing. 단일 종목 비중 ≤ 20% (소형주 유동성 위험 제어).

**미장 진입 조건** (Tier 1):
- 종목당 배분액 ≥ 100만원 (왕복 거래비용 2% × 50배)
- 명확한 정보 우위 (Brain v5 score 75+)
- 환차익 비과세 250만원 buffer 내 운영

---

## 3. 축소율 비교

```
현행:  5,000 → 1,000 → 300 → 100 → 25
        (20%)  (30%) (33%) (25%) → top 0.5%

개편: ~5,500 → ~1,650 → ~330 → ~33 → ~18 → 7 (Tier 1)
       hard cut (30%)  quintile  decile  Brain  conviction
                (20%)   (10%)    (~55%)  (Tier)
       → 최종 top 0.12% (Tier 1)
```

축소율 패턴: criteria → 20% → 10% → fine → Tier (Greenblatt 패턴 + AQR composite + Tier-aware Kelly 정합)

---

## 4. KR factor 동아시아 디스카운트 보정

학습 자료 3 의 핵심 발견: KR factor half-life 가 글로벌 대비 30-60% 짧음.

**조치**:
- 리밸런싱 주기: Stage 2-4 = 월 1회 (글로벌 표준의 2/3, AQR 분기 → 월)
- Momentum factor: top 30% (글로벌 20%) — KR 노이즈 보정
- Value factor: sector 내 rolling 3y z-score (절대 PBR 컷 폐기, 한국 2009- 가치프리미엄 소멸)
- Quality factor: Piotroski F≥4 유지 (KR-안정 영역)

---

## 5. 마이그레이션 (PRODUCTION 데이터 0일 — 손실 없음)

**현 상태**: Phase 2-B SHADOW 활성 5/11~ (1일치 데이터만 누적). PRODUCTION 게이트 65 거래일 (8월 말) 시계는 어차피 다시 시작.

**5/17 sprint 진입 시점에 박을 변경 사항**:

1. **Stage 0 criteria-based** 변경 — `api/builders/universe_scan_builder.py:OUTPUT_PATH` 가 universe_candidates 생성하는 로직 재작성. 5,000 hardcode 제거.
2. **Stage 1 Hard Exclusion** 별도 단계 분리 — `api/filters/hard_exclusion.py` (신규). KRX 관리종목 일일 동기화 collector + 자본잠식률 + 거래대금 floor.
3. **Stage 2 Coarse Filter quintile** — 현 `wide_scan` v0_heuristic 의 20% 정합 확인 (이미 22% 라 거의 정합), sector-neutral z-score 산식 정착.
4. **Stage 3 Medium top decile** — 신규 단계. 300 → 30. 기존 1,000 → 300 → 100 의 *중간* 두 단계를 *압축*.
5. **Stage 4 Fine** — Brain v5 full + KCMI cycle check.
6. **Stage 5 Tier-aware** — `api/portfolio/conviction_selector.py` 가 Tier 자본 읽어 동적 K (6-8 / 15-25 / 30-50). 현재 25 hardcode 제거.

**기존 자산 재사용**:
- Phase 2-B 7차원 + sector_thresholds → Stage 2 의 composite 산식
- Phase 2-C/2-D 가속 빌드 (5/15/5/20) → Stage 3/4 의 정착
- conviction_selector (5/22 가속 빌드) → Stage 5 의 Tier-aware 강화

**관찰 트랙**:
- Stage 1 hard exclusion 비율 → 한 달 누적 후 미래에셋 분석 1,986개 / KR 실무 800-1,000 컨센서스 정합 확인
- 단계별 IC + ICIR 측정 (Phase 2-B SHADOW 패턴 확장)
- 65 거래일 PRODUCTION 게이트 = 새로 시작 (8/17 ~ 11/15 KST)

---

## 6. 책임 분리 (frontend vs backend)

`feedback_simple_front_monster_back` 정합:

- **Backend (Stage 0~4)** = 월가 0.00000001% 정교. funnel 학계 표준 + KR 디스카운트 + Brain v5 + KCMI cycle.
- **Frontend (Stage 5)** = 심플. 사용자에게 보이는 건 conviction basket 18 + Tier 권장 N (6-8 for Tier 1). 그 위의 funnel 5단계는 admin/dev 카드 만.

---

## 7. 미해결 (5/17 sprint 진입 전 결정 필요)

1. **KR/US split 의 자본 Tier 별 정확 산식** — Tier 1 = KR 6 + US 0-2 도 보수적인지, 0:6 만 두는지. **사용자 결정 필요**
2. **Stage 0 US ADV 컷** — $5M 인지 $10M 인지. US universe 크기 영향. 백테스트로 결정
3. **리밸런싱 주기 KR 월 1회** — 거래비용 vs IC decay 균형. 백테스트로 검증
4. **Stage 1 Hard Exclusion 의 신규 12개월 룰** — KR 신규상장 multi-bagger (예: 카카오뱅크 2021) 기회 손실 우려. 6개월 절충 검토

---

## 8. 메모리 정합

- `project_stock_filter_v0_enhancement` — 5단계 funnel 9원칙 → 이 plan 으로 *재정의*. 기존 25 hardcode 등 변경 필요
- `project_phase_2b_wide_scan` — 가속 빌드 일정 유지. Stage 2/3/4 가 기존 2-B/2-C/2-D 의 *내용 보강*
- `project_funnel_5stage_sprint` — 5/17 sprint 의 시작점 = 이 plan
- `project_capital_evolution_path` — 6 tier × 7축 정합. Tier 1 = 6-8 종목으로 명시
- `feedback_source_attribution_discipline` — 모든 cut/임계값에 학계/실무 출처 명시 (이 doc 의 표 형식)
- `reference_learning_materials_folder` — 학습 자료 3.pdf 가 이 plan 의 단일 외부 근거
