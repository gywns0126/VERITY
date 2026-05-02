# LANDEX 검증 메트릭 — 5/12 결정 RUNBOOK

**작성**: 2026-05-02
**결정 일자**: 2026-05-12
**관련 문서**: `docs/ESTATE_VALIDATION_METRICS.md`
**결정 영역**: ESTATE LANDEX 메타-검증 단독 IC 임계 → 다중 메트릭 5개 전환 여부

---

## 1. 사전 점검 (D3 작업)

| 항목 | 상태 | 위치 |
|---|---|---|
| 메트릭 사양 문서 | ✅ 작성 (D3-1) | `docs/ESTATE_VALIDATION_METRICS.md` |
| Silent 측정 인프라 | ✅ 추가 (D3-2) | `scripts/landex_meta_validation.py` 의 `_compute_silent_metrics()` |
| Silent jsonl 기록 경로 | ✅ 정의 | `data/metadata/landex_meta_validation.jsonl` |
| 단위 테스트 | ✅ 5 cases (D3-4) | `tests/test_landex_silent_metrics.py` |
| Mock dry-run | ✅ 검증 완료 | `python3 scripts/landex_meta_validation.py --dry-run-silent` |

---

## 2. 5/5 ~ 5/12 일정

| 일자 | 이벤트 | 비고 |
|---|---|---|
| **2026-05-05 (화)** | 첫 cron 자동 실행 (.github/workflows/landex_meta_validation.yml) | jsonl row 1 누적. 본인 직접 점검 (action_log) |
| 2026-05-08 (금) | (수동 실행 가능) `python3 scripts/landex_meta_validation.py 2026-04` | 데이터 추가 누적. 필수 X |
| **2026-05-12 (화)** | 두 번째 cron (또는 수동). jsonl row 4+ 누적 (5/5, 5/8, 5/12) | 분석 트리거 |

> ⚠ cron 스케줄 = 매주 화요일 03:00 KST (project_estate_backtest_methodology). 4주 누적 = 5/5, 5/12, 5/19, 5/26 가 정확.
> 5/12 시점은 **2 row** 만 누적 가능 = 표본 부족. 본 RUNBOOK 의 *4주 4 row* 가정은 5/26 까지 연장 필요. 5/12 = **중간 점검**, 5/26 = 정식 verdict.

### 2-1. 일정 정정

| 시점 | row 누적 | 의미 |
|---|---|---|
| 5/5 | 1 | 첫 측정 (인프라 작동 확인) |
| 5/12 | 2 | 중간 점검 — verdict 보류, 메트릭 분포만 관찰 |
| 5/19 | 3 | 임시 verdict 산출 가능 |
| **5/26** | **4** | **정식 verdict 산출** (4주 누적 = 사용자 명세) |

→ 본 RUNBOOK 은 **5/26 verdict 운영용**. 5/12 는 mid-checkpoint.

---

## 3. 분석 스크립트 호출 인터페이스 (계약)

`scripts/analyze_landex_validation_stability.py` 의 *입출력 계약* 만 본 RUNBOOK 에서 약속한다. 내부 구현·임계·markdown 형식은 5/26 별도 명세로 결정.

> ⚠ **5/26 별도 명세 caveat**: 본 절의 임계 판정 로직(variance < mean × 0.3 등)·내부 함수 구조·markdown 리포트 형식은 **본 RUNBOOK 에서 약속하지 않음**. 5/12 mid-checkpoint 데이터 분포를 본 후 5/26 직전 별도 명세로 확정. CLI 인자·입력 소스·출력 JSON 스키마·exit code 규약 4가지만 본 RUNBOOK 에서 *불변 계약* 으로 고정.

### 3-1. CLI 인자 (계약)

```bash
python3 scripts/analyze_landex_validation_stability.py \
    --window-start YYYY-MM-DD \
    --window-end   YYYY-MM-DD \
    --output       PATH
```

3 인자 모두 필수. 추가 옵션은 5/26 명세에서 자유.

| 호출 시점 | 명령 |
|---|---|
| 5/12 mid-checkpoint | `--window-start 2026-05-05 --window-end 2026-05-12 --output data/analysis/landex_validation_stability_20260512.json` |
| **5/26 정식 verdict** | `--window-start 2026-05-05 --window-end 2026-05-26 --output data/analysis/landex_validation_stability_20260526.json` |

### 3-2. 입력 데이터 소스 (계약)

| 항목 | 값 |
|---|---|
| 입력 파일 | `data/metadata/landex_meta_validation.jsonl` (D3-2 에서 cron 마다 append) |
| 입력 row 형식 | D3-2 `_compute_silent_metrics()` 출력 schema (timestamp / horizon_weeks / n_districts / metrics{...} / thresholds_evaluated{...} / current_operational_verdict) |
| 윈도우 필터 | `record["timestamp"][:10]` ∈ [window_start, window_end] (포함) |
| n=0 처리 | exit code 3 (fail) + verdict_reasoning 에 "no_records_in_window" 명시 |

### 3-3. 출력 JSON 스키마 (계약)

```json
{
  "window_start": "2026-05-05",
  "window_end":   "2026-05-26",
  "n_cron_records": 4,
  "metric_stability": {
    "spearman_rank_ic":   {"mean": 0.0, "variance": 0.0, "stable": true},
    "rmse":               {"mean": 0.0, "variance": 0.0, "stable": true},
    "direction_accuracy": {"mean": 0.0, "variance": 0.0, "stable": true},
    "quintile_spread_pct":{"mean": 0.0, "variance": 0.0, "stable": true}
  },
  "p0_pass_rate_4_of_4": 0.0,
  "p0_pass_rate_3_of_4": 0.0,
  "verdict": "ok",
  "verdict_reasoning": "..."
}
```

| 키 | 타입 | 의무 |
|---|---|---|
| `window_start`, `window_end` | string (YYYY-MM-DD) | ✅ |
| `n_cron_records` | int | ✅ — 윈도우 내 jsonl row 수 |
| `metric_stability.<metric>.mean` | float | ✅ |
| `metric_stability.<metric>.variance` | float | ✅ |
| `metric_stability.<metric>.stable` | bool | ✅ — 안정성 판정 결과 (임계 자체는 5/26 명세) |
| `p0_pass_rate_4_of_4` | float (0.0~1.0) | ✅ — n_cron_records 중 4중 4 통과 비율 |
| `p0_pass_rate_3_of_4` | float (0.0~1.0) | ✅ — n_cron_records 중 4중 3 통과 비율 |
| `verdict` | string ∈ `{ok, partial, unstable, fail}` | ✅ — §4 매트릭스 라벨 |
| `verdict_reasoning` | string | ✅ — verdict 산출 근거 한 줄 (사람 읽기) |

추가 키 (예: `markdown_report`, `top_anomalies`, `recommendation`) 는 5/26 명세 자유. 위 의무 키는 본 RUNBOOK 에서 불변.

### 3-4. Exit code 규약 (계약)

| code | verdict | 의미 |
|---|---|---|
| **0** | `ok` | 모두 안정 + 4중 3 통과 → 다중 평가 체계 정식 코드화 진입 |
| **1** | `partial` | 1~2개 불안정 또는 통과 변동 → 임계 재조정 후 진입 |
| **2** | `unstable` | 3+개 불안정 → D 산식 재검토 필요 |
| **3** | `fail` | 4중 3 미달 또는 데이터 부재 → 모델 자체 부적합 |

cron / shell 호출 측에서 `$?` 로 분기 가능. 기타 exit code (예: 사용 오류 130 등) 는 표준 따름.

---

---

## 4. 5/26 정식 판정 매트릭스

| 5개 메트릭 4주 누적 패턴 | verdict | 6월 액션 |
|---|---|---|
| 모두 안정 (variance < mean × 0.3) + 4중 3 통과 | **ok** | 다중 평가 체계 정식 코드화 + IC 단독 임계 폐기 |
| 일부 불안정 (1~2개 variance ≥ 0.3 or 통과 변동) | **partial** | 불안정 메트릭 교체 또는 임계 재조정 후 진입 |
| 다수 불안정 (3+개) | **unstable** | D 산식 v1.2 자체 재검토 (산식 안정성 판정 = 5/5 별도 트랙과 통합) |
| 4중 3 미달 (P0 한번도 통과 안 됨) | **fail** | 모델 자체 부적합 — Brain 룰 재구성 검토 |

### 4-1. 안정성 정의

`stability_ratio = sqrt(variance) / |mean|` < **0.3** = 안정.

예: Spearman IC mean=0.12 / std=0.03 → ratio=0.25 = 안정 ✅
    Direction Accuracy mean=0.60 / std=0.10 → ratio=0.17 = 안정 ✅
    Quintile Spread mean=0.5 / std=0.4 → ratio=0.80 = 불안정 ❌

### 4-2. 통과 정의 (메트릭별, ESTATE_VALIDATION_METRICS.md §2 참조)

| 메트릭 | 임계 |
|---|---|
| Spearman Rank IC | ≥ 0.10 AND p < 0.10 |
| RMSE | ≤ market_volatility × 0.5 |
| Direction Accuracy | ≥ 0.60 |
| Quintile Spread | ≥ 1.0 %p |

→ 4중 **3개 이상 통과** = pass.

---

## 5. 롤백 조건

다중 메트릭 도입 (= 5/26 verdict=ok 후) 직후 첫 4주 동안:

- 운영 verdict 분포가 **기존 (IC 단독) 대비 75% 이상 다르게 나오면**
  → **한 단계 보수적 임계로 재조정**: P0 4중 3 → **P0 4중 4 통과 요구**

### 5-1. "75% 다름" 정의
```
mismatch_rate = (
    sum(1 for r in 4_weekly_runs
        if multi_verdict(r) != single_ic_verdict(r))
) / 4
```
mismatch_rate > 0.75 → 롤백 트리거.

### 5-2. 롤백 후 재모니터링
- 4중 4 임계로 4주 추가 모니터링
- 또 mismatch > 0.75 면 **다중 메트릭 도입 자체 폐기** + 단독 IC 유지 + Phase 2 별도 명세

---

## 6. 운영 무영향 보장 (5/12 mid-checkpoint 까지)

D3-2 silent 측정은 다음을 *변경하지 않음*:

- 기존 `landex_meta_validation.py` 의 verdict 산출 (`_compute_verdict()`)
- `estate_system_health.json` 의 `meta_validation` 섹션 갱신 로직
- `.github/workflows/landex_meta_validation.yml` cron return 값
- Telegram/Slack 알림 (현재 미연동, 그대로)

추가만:
- `data/metadata/landex_meta_validation.jsonl` append (각 cron 1 row)
- 알림 / 임계 / 게이팅 트리거 X

---

## 7. 변경 추적

| 날짜 | 변경 |
|---|---|
| 2026-05-02 | 초기 작성 (D3 사전 준비) |
| 2026-05-12 | (예정) mid-checkpoint 분석 결과 보강 |
| 2026-05-26 | (예정) 정식 verdict + 운영 전환 결정 |
