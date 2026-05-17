# ATR Phase 1.5.1 Result — 2026-05-17 (Step A + Step B audit)

**날짜**: 2026-05-17 14:35 KST
**전제**: ATR Phase 0 verdict OK 확정 (avg_diff_pct 8.4% < 15%, 14:12 KST scripts/analyze_atr_migration.py)
**결과**: 🚨 **Phase 1.5.1 진입 게이트 불충족 — 인프라 보강 sprint 선행 필수**

---

## 요약 결정 trigger

| 항목 | 결과 | PASS 게이트 |
|---|---|---|
| Step A — actual_stop_hit_rate | **N/A (데이터 부재)** | ❌ |
| Step B — 4-cell 비교 | **cell A 만 유효, cell B/C/D 무효** | ❌ |
| 종합 verdict | **FAIL (Step A 미정합 + Step B fabrication)** | 진입 보류 |

→ 명령서 후속 분기: **"백테스트 산식 audit sprint"** 또는 **운영 인프라 보강 sprint** 진입.

---

## Step A — 운영 영향 사전 검증

### Input audit

- `data/vams/holdings_*.json` = 별 jsonl 파일 부재
- `data/vams/archive_pre_5_17/portfolio_full_snapshot.json` 에서 추출:
  - holdings (open): 0
  - simulation_stats: total_trades=13, win_count=9, loss_count=4
  - best_trade: 삼성전자 +538,841 / worst_trade: LG화학 -72,550
- `data/metadata/atr_migration_log.jsonl` = 3,229 row (Phase 0 sample, sample 산식 base 다름)

### 산출 부재 사유

VAMS 가 **trade history 별도 jsonl 안 박음**. summary stats 만 영속화 → **exit_reason 분해 불가**:
- 13 trade pair 중 4 loss 가 stop_loss trigger 인지 사용자 수동 매도인지 분리 X
- actual_stop_hit_rate 산식 불가능

### 산출 결과

```json
{
  "sample_size_holdings": 13,
  "actual_stop_hit_rate": null,
  "backtest_75pct_baseline": 0.756,
  "delta_pct": null,
  "_error": "exit_reason logging 인프라 부재 (VAMS jsonl 미박힘)",
  "_recommendation": "운영 14d 추가 + VAMS exit_reason logging 신설 후 재실행"
}
```

### 판정 ([[project_atr_phase0_migration]] 명령서 정합)

> sample 사이즈 < 10 holdings → "통계 부족" + 운영 누적 후 재실행.

sample 13 > 10 이지만 **exit_reason 분해 불가 = 사실상 통계 부재**. 명령서 "통계 부족" 카테고리로 처리.

---

## Step B — 4-cell 비교 (5/16 박힌 결과 audit)

### Input audit

- `data/analysis/atr_4cell_sweep_20260516_131435.json` (sweep summary)
- `data/analysis/atr_cell_14x2.5_20260516_131241.json` (cell A)
- `data/analysis/atr_cell_14x3.0_20260516_131339.json` (cell B)
- cell C/D (period=22) = not_supported (`compute_atr_14d` 가 14 고정, Phase 1.3 prerequisite)

### 🚨 사고 발견 — cell B silent fabrication

**증거**:

| 파일 | params.atr_multiplier | stop_loss_rate | 5r_hit_rate | total_stop_loss |
|---|---|---|---|---|
| atr_cell_14x**2.5**_*.json | **2.5** | 0.7101 | 0.233 | 15,948 |
| atr_cell_14x**3.0**_*.json | **2.5** ← 잘못 | 0.7101 ← 동일 | 0.233 ← 동일 | 15,948 ← 동일 |

→ cell B (14×3.0) 의 params + metrics 모두 cell A 와 동일. **실제로는 14×2.5 가 실행됨**.

### ROOT CAUSE

`scripts/analyze_5r_sample_feasibility.py:62`:
```python
ATR_MULTIPLIER = 2.5   # Phase 1.1 ATR_STOP_MULTIPLIER 와 동일값
```

→ **모듈 상수 하드코드. ATR_STOP_MULTIPLIER env 안 읽음.**

`scripts/run_atr_4cell_sweep.py:87-89` 가 env 박지만:
```python
env_override = {"ATR_STOP_MULTIPLIER": str(mult)}
env = dict(os.environ); env.update(env_override)
```

→ subprocess 에 env 전달되지만, analyze_5r 가 env 무시 → cell B sweep 결과 = cell A 와 동일 (silent fabrication).

### 결과

- cell A (14×2.5, 현 운영) = 유효: stop_loss_rate 71.01% / 5r_hit 23.3% / 22,460 entries
- cell B (14×3.0) = **무효 (fabrication, 재실행 필수)**
- cell C (22×2.5) = not_supported (Phase 1.3 prerequisite)
- cell D (22×3.0) = not_supported (Phase 1.3 prerequisite)

→ **4-cell 비교 불가**. cell A 단독 결과만 = 신호 X.

---

## PASS 게이트 점검 ([[project_atr_phase0_migration]] 명령서)

| 조건 | 충족 |
|---|---|
| 1. Step A actual_stop_hit_rate vs 백테스트 baseline `|delta| < 10pp` | ❌ Step A 데이터 부재 |
| 2. Step B recommended_cell ≠ cell A | ❌ Step B fabrication, 비교 불가 |
| 3. recommended_cell stop_loss_rate < 60% | ❌ N/A |
| 4. recommended_cell profit_factor ≥ A 대비 +0.1 | ❌ N/A |

→ **4/4 조건 모두 불충족. Phase 1.5.1 진입 보류.**

---

## 후속 sprint plan (사용자 PM 결정 영역)

### Option A: 인프라 보강 sprint (추천)

직렬 sprint, ATR 트랙 continuation:

1. **VAMS exit_reason logging 신설** (Step A 인프라):
   - api/vams/ 코드 수정 — sell trade 시 exit_reason (stop_loss / r_multiple_1r / r_multiple_2r / trailing / manual) 명시
   - data/vams/holdings_history.jsonl 신설 (closed trade 영속화)
   - 운영 14d 누적 후 Step A 재실행

2. **analyze_5r ATR_STOP_MULTIPLIER env 읽기 fix** (Step B 인프라):
   - scripts/analyze_5r_sample_feasibility.py:62 의 모듈 상수 → env 우선 분기
   - sweep 재실행 (cell A vs B 진짜 비교)
   - cell C/D = compute_atr_n 헬퍼 확장 (Phase 1.3 prerequisite) — 별 sprint

3. **재실행 후 Phase 1.5.1 verdict** (3개월 추정):
   - 운영 14d × Step A 통계 누적
   - cell A vs B 진짜 비교
   - PASS 게이트 재점검

### Option B: ATR 트랙 보류 + 다른 트랙 진입

[[user_profile]] 단일 트랙 집중. ATR 트랙 인프라 보강 부담 크면 다른 트랙으로:

- funnel 5단계 sprint (4-6시간)
- earnings layer sprint (Finnhub free tier IC)
- brain_score_funnel F+G audit
- fred_silent_skip sprint
- Brain v6 design 작업

### Option C: Phase 1.5.1 명령서 자체 회귀

명령서 v0.1 박힌 5/12 시점 = exit_reason 인프라 / sweep wiring 검증 부재. 명령서 자체 v0.2 로 회귀 (인프라 prerequisite 명시):

- v0.2 명령서: Step A 진입 전 VAMS exit_reason 인프라 의무, Step B 진입 전 sweep env wiring 검증 의무
- 명령서 정합 검증 sprint = 5/12 이후 박힌 sprint 명령서 다수 audit

---

## 사고 학습 (PM trail 자산화)

이번 발견 = **검증 운영 누적의 핵심 신뢰성 사고**:

1. **sweep 메타데이터 거짓말** — atr_cell_14x3.0_*.json 의 params 와 metrics 가 14×2.5 실행 결과인데 파일명만 14x3.0
2. **subprocess env 격리 비검증** — sweep 스크립트가 env 박고 끝, 실제 적용 검증 안 함
3. **모듈 상수 vs env 정합 부재** — analyze_5r 가 ATR_STOP_MULTIPLIER 명시 무시

→ [[feedback_data_collection_verification_mandatory]] 정합 결함. 향후 sweep / backtest 스크립트는 **첫 row 의 params 가 의도된 input 과 정합 의무 검증** 박아야.

→ [[project_brain_learning_loop_repair]] 5/3 학습 루프 4결함 수리 패턴 — 이번도 같은 카테고리 (silent skip + fabricated metrics).

---

## 추천 결정

**Option A (인프라 보강)** — ATR 트랙 continuation 정합 + 단일 변수 통제 정합 + 사고 학습 영속화 정합.

다만:
- 운영 14d 누적 필요 → 즉시 5/18 진입은 (1) sweep wiring fix 만 가능 (1-2시간), (2) VAMS exit_reason logging 신설 (2-3시간) + 운영 누적 14d 대기
- 인프라 보강 진행 동안 ATR 트랙 = **잠시 정지**. Phase 1.5.1 verdict 까지 ~3-4주 (운영 누적 14d + analysis + verdict)

또는 **Option A + B 직렬** (인프라 보강 + 다른 트랙 운영 동안 누적):
- 5/18: sweep wiring fix (1-2시간) + VAMS exit_reason logging 신설 (2-3시간) — 4-5시간 sprint
- 5/19~6/2: 운영 14d 누적 (자동, 사용자 신경 X)
- 6/2 후: Phase 1.5.1 재실행 + verdict
- 그 사이 5/18~6/2 사용자 트랙 = 별 sprint (funnel / earnings / brain v6 등)

→ **단일 트랙 집중 [[user_profile]] 살짝 위반 X** — 인프라는 자동 누적 (휘발 X), 사용자 트랙은 다른 sprint 1개. 정합.
