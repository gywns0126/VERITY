# ATR W2/W3 Wiring 명령서 v0.1

ATR Phase 0 verdict=ok + Phase 1.5.1 결정 후 진입 격리 wiring (2026-05-12 박음).

## 1. 사전 조건 (Gate)

다음 셋 다 충족 시에만 진입:

1. **Phase 0 verdict = ok** (project_atr_phase0_migration)
2. **Phase 1.5.1 결과**: ATR multiplier 재검토 sprint 결정 종료 (다음 분기 중 하나):
   - cell A winner → 현 ATR(14)×2.5 유지 + 본 wiring 진입
   - cell B/C/D winner → 운영 코드 multiplier 변경 sprint 먼저 완료 후 본 wiring 진입
3. **단일 변수 통제 — 동시 변경 금지**:
   - W2 wiring 진행 중 ATR multiplier 변경 X
   - ATR multiplier sprint 와 wiring 동시 X (둘 다 손절 거리 분포 변경 → 회귀 격리 불가)

## 2. 배경 (project_atr_phase0_migration 결정 21 정합)

5/2 진단:
- **W1** ✅ 5/2 완료 (commit 7fc184b, runtime_load_log.jsonl row 검증)
- **W2** 미진행 — parallel_fetcher → `stock_data.get_all_stock_data` 경로 교체
- **W3** 미진행 — W1+W2 인자 통합 (yfinance/DART fail_rate, kr_first_call_ms, rate_limit_violations)

5/16 전 절대 진행 금지 이유:
- W2 = KR fetch 경로 변경. ATR 마이그레이션 = 손절 산출법 변경 (SMA→Wilder).
- 두 변경 동시 발생 시 5/16 verdict avg_diff_pct 차이가 "산출법" 인지 "fetch 결과" 인지 분리 불가.

## 3. 격리 wiring 순서 (3 stage)

### Stage W2 — KR fetch 경로 교체

```
변경:
    api/utils/parallel_fetcher.py  →  api/data/stock_data.get_all_stock_data hook

격리 보호:
    - ATR_STOP_MULTIPLIER 변경 X (현 운영 값 유지)
    - FALLBACK_STOP_PCT 변경 X
    - profile fixed (-8/-5/-3) 변경 X
    - 단 fetch 경로 하나만 swap

산출물:
    - runtime_load_log.jsonl 의 kr_fetch_path = "stock_data_hook" 으로 전환 검증
    - parallel_fetcher 호출 site 0 건 확인 (dead code 격리)

운영 검증 기간:
    - 7 영업일 운영 누적
    - 매일 runtime_load_log.jsonl 행 수 / fail_rate / first_call_ms 측정
    - 비교 baseline = W2 전 7일치 (parallel_fetcher 시절) — 사전 캡처 의무
```

**Stage W2 PASS 게이트** (7일 후 측정):

| 지표 | 임계 | 사유 |
|---|---|---|
| fail_rate (KR fetch) | baseline ±20% 이내 | fetch 안정성 보존 |
| first_call_ms p50 | baseline ±30% 이내 | 응답속도 회귀 가드 |
| stale row 누락 | 0 건 | data integrity 정합 |
| ATR atr_14d_method 분포 | wilder_ema_14 = 100% | Phase 0 결과 보존 |

미충족 시:
- 정공법: 회귀 원인 식별 + W2 patch (단일 변수 통제 — patch 도 fetch 경로 영역만)
- rollback: `git revert <W2 commit>` 후 parallel_fetcher 복귀

### Stage W3 — 인자 통합

```
변경:
    runtime_load_log.jsonl row 에 W1+W2 인자 통합:
        - yfinance_fail_rate (W1 → W3)
        - dart_fail_rate (W1 → W3)
        - kr_first_call_ms (W2 → W3, stock_data hook 측정)
        - rate_limit_violations (W2 → W3, hook 내 counter)

격리:
    - W2 PASS 게이트 통과 후만 진입 (W2 의 fail_rate/workers 인자가 의미 있어야 통합)
    - ATR 관련 일체 변경 X

산출물:
    - runtime_load_log.jsonl schema v2 (W1+W2+W3 통합 필드)
    - W3 schema 변경 commit 전 schema migration 가드 (없는 필드 → null 정합)
```

**Stage W3 PASS 게이트** (7일 후):

| 지표 | 임계 | 사유 |
|---|---|---|
| 4 인자 (yf/dart/kr_call/rate_lim) all 채워짐 | 100% row | 누락 0건 |
| 인자 분포 정상 (outlier <5%) | — | 통합 산식 다음 sprint 입력 신뢰성 |
| Phase 1.1 손절 동작 무변경 | individual stop_loss 분포 unchanged | wiring 회귀 격리 |

### Stage 통합 분석 — 인자 의미 평가

W3 PASS 후 별도 sprint 의제 (큐잉):
- 4 인자가 손절 결과 / 진입 결과 / max_excursion 과의 상관 측정
- 의미 있는 인자만 Brain v5 의 stage_filter 입력으로 흡수
- 의미 없는 인자 = 로깅만 + retract 검토 ([[feedback_spec_iteration_retract_rule]] 정합)

## 4. 비변경 영역 (단일 변수 통제 — wiring 영역 외 절대 X)

본 명령서 진행 중 다음 영역 **변경 절대 금지**:

- ATR 산출법 (SMA / Wilder EMA(14) / lookback 14)
- ATR multiplier (현 운영 값)
- Profile 손절 (-8/-5/-3)
- VAMS holding individual stop 영속화 로직
- trade_planner.py stop_loss 산출식
- Brain v5 가중치 / 등급 임계

위 영역 변경이 필요하면 **wiring 보류 + 별도 sprint**.

## 5. 진행 산출물

| Stage | 산출물 | commit prefix |
|---|---|---|
| W2 baseline 캡처 | `data/metadata/runtime_load_log_w2_baseline.jsonl` | `📋 atr: W2 baseline` |
| W2 swap | `api/utils/parallel_fetcher.py` 제거 + hook 호출 | `🔧 atr: W2 wiring` |
| W2 7일 측정 | `docs/ATR_W2_RESULT_<date>.md` | `📊 atr: W2 result` |
| W3 schema | `runtime_load_log.jsonl` 필드 4종 추가 | `🔧 atr: W3 wiring` |
| W3 7일 측정 | `docs/ATR_W3_RESULT_<date>.md` | `📊 atr: W3 result` |

## 6. 후속 분기

| 결과 | 다음 |
|---|---|
| W2 + W3 모두 PASS | 인자 의미 평가 sprint (Brain v5 흡수 검토) |
| W2 FAIL | W2 patch sprint 또는 rollback. W3 보류 |
| W3 FAIL (schema migration 사고) | W3 rollback. W2 단독 운영 유지 |
| 인자 의미 없음 | runtime_load_log schema retract (필드 제거) |

## 7. 위험 가드

- **commit 시간대**: Phase 0 verdict commit 직후 동일 날 W2 commit 금지 (24h 격리)
- **모니터링 cadence**: W2 swap 후 첫 24h 는 시간당 runtime_load_log 행 수 점검
- **롤백 트리거**: KR fetch fail_rate >40% / 1h 지속 시 즉시 W2 revert
- **사용자 액션 큐잉**: W2 swap commit 직후 `data.go.kr ratelimit 측정` user_action

## 8. 관련 메모리

- [[project_atr_phase0_migration]] 결정 21 — wiring 격리 정책 원전
- [[project_atr_dynamic_stop]] — Phase 1.1 ATR 손절 (보존 영역)
- [[feedback_decision_logging_separation]] — wiring = 로깅 풍부 직교 차원
- [[feedback_spec_iteration_retract_rule]] — 인자 의미 없으면 retract
