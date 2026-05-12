# ATR Phase 1.5.1 명령서 v0.1

ATR Phase 0 verdict=**ok** 직후 진입 백테스트 검증 명령서 (2026-05-12 박음).

## 1. 사전 조건 (Gate)

다음 셋 다 충족 시에만 진입:

1. **Phase 0 verdict = ok**: `data/metadata/phase_0_results.json` 의 `verdict == "ok"`
   (= 14일 윈도우 avg_diff_pct < 15%, project_atr_phase0_migration 매트릭스)
2. **secret 활성화**: `ATR_14D_METHOD=wilder_ema_14` 가 운영 cron 환경에 반영됨 (5/3 활성화 큐 9f48284a)
3. **W2/W3 wiring 미진행** (project_atr_phase0_migration 결정 21 — Phase 1.5.1 까지는 W2/W3 격리 유지)

verdict ≠ ok 시:
- monitoring → Phase 1.5.1 진입 X. ATR 모니터 7일 연장 후 재판정
- fail → 즉시 `scripts/rollback_atr_to_sma.sh` 실행 + Phase 1.5.1 보류
- monitoring_escape → 정상 시장 7일 후 재판정 (rollback 보류)

## 2. 목적

ATR(14)×2.5 의 한국 시장 적합성 정량 검증. project_atr_dynamic_stop 5/2 풀스캔 v2 finding 이
"large tier stop_loss_rate 75.6%" 로 🔴 신호 — Phase 1.1 ATR 거리 너무 tight 가능성.
verdict=ok 통과해도 운영 코드 변경 전 4-cell 비교로 정량 결정.

## 3. 두 단계 (P0 격상)

### 3.1 운영 영향 사전 검증 (Step A)

```
입력:
    - data/vams/holdings_*.json (운영 holding stop_loss 트리거 이력)
    - data/metadata/atr_migration_log.jsonl (5/3~5/16 14일)
산출:
    - data/analysis/atr_phase_1_5_1_step_a_<YYYY-MM-DD>.json
        actual_stop_hit_rate          # 운영 holding 의 실측 stop trigger 비율
        backtest_75pct_baseline       # 5/2 풀스캔 v2 baseline
        delta_pct                     # 운영 vs 백테스트 차이
        sample_size_holdings          # 통계 신뢰성 사이즈
```

**판정**:
- 운영 실측 stop_hit_rate ≥ 60% → 백테스트 finding 재확인. Step B 진입 (P0).
- < 60% → 백테스트가 과대평가. Step B 진입 (P1, 우선순위 낮음).
- sample 사이즈 < 10 holdings → "통계 부족" + 운영 누적 후 재실행.

### 3.2 4-cell 비교 백테스트 (Step B)

| cell | lookback | multiplier | 비고 |
|---|---|---|---|
| A | 14 | 2.5 | 현 운영 (Phase 1.1 기준선) |
| B | 14 | 3.0 | tighter window + LeBeau multiplier |
| C | 22 | 2.5 | LeBeau window + 현 multiplier |
| D | 22 | 3.0 | LeBeau Chandelier Exit 원전 |

```
스크립트 (신규):
    scripts/atr_4cell_backtest.py
        --baseline    data/analysis/5r_feasibility_full_v2_20260502.json
        --hard-floor  (적용)
        --metric      stop_loss_rate / 5r_hit_unique_tickers / max_excursion / profit_factor
        --out         data/analysis/atr_4cell_<YYYY-MM-DD>.json

산출 schema:
    {
      "cells": {
        "A": {"stop_loss_rate": 0.756, "5r_hit_unique": N, "max_excursion": {...}, "profit_factor": F},
        "B": {...}, "C": {...}, "D": {...}
      },
      "winner_per_metric": {"stop_loss_rate": "C", ...},
      "recommended_cell": "C|D|A|B (산식 정합 결정)",
      "delta_vs_A": {...}
    }
```

**평가 정공법** (메트릭별 비중 사전 박음 — 사후 가중치 변경 금지):
- 50% stop_loss_rate (낮을수록 ↑) — Phase 1.1 운영 위험 직접 지표
- 25% profit_factor (높을수록 ↑) — 손실 대비 이익 비율
- 15% 5r_hit_unique_tickers (높을수록 ↑) — 큰 익절 기회
- 10% max_excursion p50 — 평균 손실 magnitude

추가: **VIX 정상 구간 (≤25) 분리 통계 의무** — 시장 정상 시 적합성과 변동 시 적합성 분리.

## 4. PASS 게이트 (Phase 1.5.1 → 다음 sprint)

다음 조건 모두 충족 시 "ATR multiplier 재검토 sprint" 진입:

1. Step A actual_stop_hit_rate vs 백테스트 baseline `|delta| < 10pp` (운영=백테스트 정합)
2. Step B recommended_cell 가 cell A (현 운영) 와 다름
3. recommended_cell stop_loss_rate < 60% (한국 시장 적합 임계 — project_atr_dynamic_stop 5/2 결정)
4. recommended_cell profit_factor ≥ A 대비 +0.1 (실효 개선)

조건 미충족 시:
- Step A 미정합 (운영 ≠ 백테스트) → 백테스트 산식 audit + 데이터 품질 검증 sprint
- A 가 winner → ATR multiplier 변경 보류, W2/W3 wiring 진입 (Phase 1.1 유지)

## 5. 진행 산출물

각 단계 commit 의무 (project_gh_pages_disabled 정합 — 빌더 산출물 main commit):
- `data/analysis/atr_phase_1_5_1_step_a_<date>.json`
- `data/analysis/atr_4cell_<date>.json`
- `docs/ATR_PHASE_1_5_1_RESULT_<date>.md` (Markdown 요약 — recommended_cell + 후속 sprint 결정)

commit prefix: `📊 atr:` (verity 도메인, analysis 영역).

## 6. 후속 분기

| 결과 | 다음 |
|---|---|
| PASS (cell B/C/D winner) | ATR multiplier 재검토 sprint — 운영 코드 변경 (별도 명령서) |
| PASS but A winner | W2/W3 wiring 진입 (ATR_W2_W3_WIRING_PLAN_v0.1) |
| FAIL (Step A 미정합) | 백테스트 산식 audit sprint |
| 통계 부족 | 운영 14d 추가 후 재실행 |

## 7. 비변경 영역 (Step 2 범위 분리)

- 운영 코드 (api/vams/, trade_planner.py) **터치 X**
- portfolio.json schema **변경 X**
- env (ATR_STOP_MULTIPLIER, FALLBACK_STOP_PCT) **변경 X**
- 본 명령서 = **분석/검증 산출물만**. 운영 변경은 결과 후 별도 sprint.

## 8. 큐잉 (실행 직전 user_action)

verdict=ok 확정 후 user_action_queue 박는 작업:
- `scripts/atr_4cell_backtest.py` 신설 + 실행
- runtime_load_log.jsonl 누적 검증 (Step A 입력)
- 5R 풀스캔 hard_floor baseline 재확보 (5/2 산출물 stale 시)
