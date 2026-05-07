# ESTATE Brain Backtest 50년+ Plan (2026-05-08)

**Goal**: V0 backtest (R-ONE 2012~ = 13년) 한계 돌파. 한국 부동산 30-50년 (가능 시 60년) 시계열로 cycle_analog plan v0.2 정합 *직접* 검증.

**Why now**: V0 = 2022 Rate-Shock 만 직접 검증 가능. 1997 IMF / 2008 GFC = plan v0.2 외부 reference (Perplexity 답변) 만 — 자체 검증 0. 30-50년 시계열 확보 = 3 cycle 모두 직접 + 추가 사이클 발굴 가능.

---

## 1. 데이터 source 후보

| Source | 시작연도 | 단위 | 권역 분리 | API | 비용 | 권장 우선순위 |
|---|---|---|---|---|---|---|
| **BIS Real Estate Price Statistics** | **1975** | 분기 | 전국 only | csv direct | 무료 | ★★★★★ (50년 backbone) |
| **KB부동산 통계 (KB데이터허브)** | **1986** | 월 | 서울/수도권/광역시/시·군 | UI 만 / 기관 API 유료 | 부분 무료 | ★★★★ (40년, 권역 분리) |
| **한국감정원 / R-ONE** | 2012 | 주 | 25구 | 무료 (이미 박힘) | 무료 | ★★★ (V0 보유) |
| 통계청 KOSIS 주택보급률·지가 | 1965~ 부분 | 분기 | 시·도 | 무료 | 무료 | ★★ (보조 변수) |
| 한국은행 ECOS 거시 | 1965~ | 월 | 전국 | 무료 (이미 박힘) | 무료 | ★★ (금리·CPI 보강) |

**추천 stack**:
- **Backbone** = BIS 1975~ 분기 (50년, 전국 단일)
- **권역 보강** = KB 1986~ 월 (40년, 서울/수도권/광역 분리)
- **단지·구 보강** = R-ONE 2012~ 주 (13년, 25구) — V0 보유
- **거시 변수** = ECOS / KOSIS (금리·CPI·인구·소득)

---

## 2. 검증 가능 cycle (60년 lookback)

| 시점 | 사이클명 | trigger | plan v0.2 매핑 | 데이터 가용 |
|---|---|---|---|---|
| 1979-1981 | 2차 오일쇼크 | 인플레·금리 | (plan 외) | BIS X (1975 분기 시작) |
| 1989-1991 | 1기 신도시 충격 | 200만호 공급 | (plan 외 — Korean specific) | KB ✓ / BIS ✓ |
| **1997-2001** | **IMF Shock** | 환율·금리 25% | **Shock-Recovery** | KB ✓ / BIS ✓ |
| 2003-2004 | 카드대란 | 가계신용 | (plan 외) | KB ✓ / BIS ✓ |
| **2008-2017** | **GFC** | 가계부채+공급과잉 | **Debt-Deflation Drag** | KB ✓ / BIS ✓ / R-ONE △ |
| 2014-2017 | 부동산 회복 | 저금리·LTV 완화 | (recovery half) | 모두 ✓ |
| 2017-2019 | 8.2대책·9.13대책 | 정책 규제 | (regulatory shock) | 모두 ✓ |
| 2020-2021 | COVID 부양 | 유동성 | (catalyst) | 모두 ✓ |
| **2022~** | **Rate-Shock** | 0.5→3.5% | **Rate-Shock Rebound** | 모두 ✓ |

**plan v0.2 3 cycle 직접 검증 가능 (BIS or KB)**: 1997 / 2008 / 2022 — 즉 **plan 가설 100% 자체 검증** 진입 path.

**추가 cycle 발굴**: 1989 신도시 / 2003 카드대란 / 2014 회복 / 2017 규제 / 2020 COVID = plan v0.2 *bonus*. 한국 부동산 사이클이 plan 의 3 패턴으로 *충분한가* 검증.

---

## 3. 산식 확장 spec

V0 backtest core (`api/intelligence/estate_brain_backtest.py`) 는 *시계열 길이 무관* 함수. 즉 **core 변경 X**, builder 만 신규.

### 신규 builder
- `api/builders/estate_brain_backtest_50y_builder.py` (또는 V1 통합)
- 입력: BIS csv + KB API + R-ONE (cross-source merge)
- 출력: `data/estate_brain_backtest_50y.json`

### 산식 확장
- **Cycle classifier**: 시계열 → drop>X% & duration>Y개월 자동 감지 → 사이클 list (plan 의 3 패턴 외 발굴)
- **Cross-cycle IC**: cycle 별 estate_brain weighted_score 가 forward return 예측력 일관 (cross-cycle robustness)
- **Regime-aware**: 1989 / 1997 / 2008 / 2022 별로 *어떤 신호가 작동* 하는지 (4중 신호 별 hit rate by cycle)

### 핵심 산출 (사용자 가치 측면)
- **plan v0.2 정합 점수**: 3 cycle drop_pct 정합 % (within ±5%)
- **bonus cycle 발견**: 추가 N 사이클 발굴 + 자동 patten classify
- **신호 robustness**: 미분양 신호 / 전세가율 신호 / PIR 신호 의 cross-cycle hit rate
- **권역 분리** (KB 만): 핵심지(서울 강남) vs 비핵심지 cycle 별 timing 차

---

## 4. 사용자 결정 필요 항목 (내일 진입 전)

### A. 시작연도 결정
- [ ] **1975 (50년, BIS backbone)** ← 추천
- [ ] 1986 (40년, KB 만)
- [ ] 1965 (60년, KOSIS 부분 + 보조 source 합성)

### B. 시계열 단위
- [ ] **분기 (BIS, 4 obs/year × 50 = 200 points)** ← BIS 정합
- [ ] 월 (KB, 12 × 40 = 480 points) — 더 dense, KB API 가능 시
- [ ] 둘 다 (BIS + KB cross-validation)

### C. 권역 분리 깊이
- [ ] **전국 단일** (BIS 만, 가장 단순)
- [ ] **서울 vs 수도권 vs 광역시** (KB 권역) ← 추천 (plan §3 핵심지 검증 가능)
- [ ] 25구 (R-ONE, 2012~ 한정)

### D. forward return horizon
- [ ] **12M (52w / 4Q)** ← V0 정합
- [ ] 24M (cycle 중반)
- [ ] 60M (cycle 전체)
- [ ] 모두 (multi-horizon 비교)

### E. cycle 자동 감지 vs hardcoded
- [ ] **plan 3 cycle hardcoded + 자동 감지 추가** ← 추천
- [ ] plan 3 cycle 만 검증 (단순)
- [ ] 자동 감지 only (open-ended 발굴)

---

## 5. Perplexity 검증 필요 (외부 사실, memory `feedback_perplexity_collaboration` 정합)

내일 진입 전 사용자 Perplexity 호출 권장:

**호출 1 — BIS 데이터 access**
> "BIS Real Estate Price Statistics 한국 데이터: csv 직접 다운로드 URL, 시작연도, 분기/월 단위, 명목/실질 분리 여부. 2026 현재 가능한 권역 분리 (전국 only or sub-regions)."

**호출 2 — KB부동산 통계 무료 access**
> "KB국민은행 KB부동산 통계 (월간 매매·전세 가격지수, 1986~) 무료 API 또는 csv download. 권역 분리 (서울/수도권/광역시/시·군). 기관 유료 vs 개인 무료 한계."

**호출 3 — 한국 부동산 사이클 발굴**
> "1965-2026 한국 부동산 가격 사이클 (drop > 10%, duration > 1년) 학술 논문 또는 한국감정원·KB·한국은행 보고서. plan v0.2 의 1997/2008/2022 외 추가 사이클 (1989 신도시, 2003 카드대란 등) drop_pct 와 duration 실측."

---

## 6. 진입 후 예상 commit (내일)

| Step | commit prefix | 추정 lines |
|---|---|---|
| BIS 어댑터 (csv fetch + parse) | `[verity-estate]` | 150 |
| KB 어댑터 (가능 시) | `[verity-estate]` | 150 |
| 50y builder (cross-source) | `[verity-estate]` | 250 |
| Cycle classifier 산식 (자동 감지) | `[verity-estate]` | 100 |
| Workflow 업데이트 (월 1회 cron) | `[verity-estate]` | 30 |
| 단위 테스트 + smoke run | `[verity-estate]` | 200 |
| **합계** | | **~880 lines** |

V0 backtest sprint (959 lines) 와 비슷한 규모. 1 세션 완료 가능 (사용자 결정 5 항목 + Perplexity 3 호출 박힌 후).

---

## 7. 위험·한계

- **BIS 데이터 권역 X**: 한국 BIS = 전국 단일 (서울 vs 지방 분리 X). 권역은 KB 의존.
- **KB API 무료 미공식**: 기관 유료 API 일 가능성. 무료 = UI download 만 → 수동 csv 적재 path.
- **1989 / 2003 사이클 = plan 외**: 발굴 시 *plan v0.2 부족* 진단 → V2 plan 추가 필요.
- **인플레 보정**: 50년 시계열 = 명목 / 실질 분리 필수 (CPI 보정). BIS 는 둘 다 제공.
- **거시 환경 차이**: 1997 vs 2022 = 금리 환경 / 경제 구조 / 인구 trend 다름. *직접 비교* 보다 *패턴 정합* 검증.

---

**진입 준비 완료** — 사용자 결정 5 항목 + Perplexity 3 호출 → 내일 새 세션 진입.
