# ATR W2/W3 Wiring Result — 2026-05-21

**전제 게이트** (`ATR_W2_W3_WIRING_PLAN_v0.1` §1): Phase 0 verdict=ok ✅ / Phase 1.5.1 = cell A winner(2.5 유지) ✅ / 단일변수 통제(multiplier·ATR 산출법 변경 X) ✅.
**결과**: ✅ W2 = 이미 사실상 완료(dead code 정리). W3 = schema 기보유 + 라이브 인자 2종 wire, dart_failure_rate 보류(producer 부재).

---

## W2 — KR fetch 경로 (계획서 전제 stale 확인)

계획서(5/12)는 `api/utils/parallel_fetcher.py` 가 **라이브 KR fetch 경로**라 가정하고 "→ `stock_data.get_all_stock_data` hook 으로 swap" 을 명령. **2026-05-21 조사 결과 전제가 stale**:

| 항목 | 실태 |
|---|---|
| 라이브 hook | `get_all_stock_data` (collectors/stock_data.py:603) = stock_filter/wide_scan 등 **이미 모든 곳에서 사용**. per-ticker `get_stock_data()` = yfinance(`safe_yf_call`) |
| `parallel_fetcher.py` | non-test importer **0건** = dead code. `fetch_kr_ohlcv_parallel` = pykrx(yfinance와 다른 소스) |
| 경로 위치 | 계획서 `api/utils/` → 실제 `api/collectors/` (5/12 후 이동) |
| 검증 필드 `kr_fetch_path` | 코드에 **존재한 적 없음** |

→ **W2 swap 은 이미 사실상 완료**(라이브=get_all_stock_data, parallel_fetcher 고아). 계획서의 기계적 절차(parallel_fetcher 시절 7일 baseline → swap → 7일 모니터 → parallel_fetcher rollback) 전부 moot.

**PM 결정 (2026-05-21)**: W2 종결 처리 + dead code 제거.
- `git rm api/collectors/parallel_fetcher.py` + `tests/test_parallel_fetcher.py`
- dangling ref 감사([[feedback_mass_removal_dangling_ref_audit]]): 함수 4종(fetch_kr_ohlcv_parallel/fetch_us_price_batch/fetch_us_fundamentals_parallel/_kr_fetch_one_ohlcv) + 모듈경로 외부 참조 **0건** 확인 후 제거.

---

## W3 — runtime_load_log 인자 통합

계획서 §3.2 4 인자: yfinance_fail_rate / dart_fail_rate / kr_first_call_ms / rate_limit_violations.

**발견**: `runtime_load_log` schema(ramp_up_monitor.log_runtime_load)는 **4 필드를 이미 전부 보유**. 갭은 W1 hook(`_log_w1_runtime`)이 라이브 `_metrics` 에서 일부만 전달한 것.

| 인자 | 전(前) | 후(後, 이번 wire) |
|---|---|---|
| yfinance_failure_rate | ✅ 전달 중 | 유지 |
| rate_limit_violations | default 0 | **wire** ← `_metrics["yf_rate_limited"]` (yfinance_safe wrapper 누적, 실데이터) |
| kr_first_call_duration_ms | default 0 | **wire** ← get_all_stock_data 첫 KR fetch latency 측정 (cold call 대표값, 실데이터) |
| dart_failure_rate | default 0 | **보류** — producer 부재 (코드 어디서도 dart 실패 미추적). default 0 강제 = 의미없는 로깅([[feedback_spec_iteration_retract_rule]]) → DART 실패 producer 신설 후 wire (follow-up) |

**변경 파일**:
- `api/collectors/stock_data.py` — get_all_stock_data 에 kr_first_call_ms 측정 + `_metrics` 노출.
- `api/analyzers/stock_filter.py` — `_log_w1_runtime` 가 rate_limit_violations·kr_first_call_ms 전달 + stderr trace 노출([[feedback_data_collection_verification_mandatory]]).
- `tests/test_ramp_up_monitor.py` — TestW3Wiring (인자 row 전달 검증).

**비변경 영역 준수** (계획서 §4): ATR 산출법/multiplier/profile 손절/VAMS individual stop/trade_planner/Brain v5 **일체 무변경**. wiring = 관측성 로깅 직교 차원만.

---

## PASS 게이트 — 운영 누적 후 검증

wiring 은 commit 완료. 게이트 수치는 **다음 full cron(평일 16:07 KST) 누적 후** 검증 (코드가 아니라 데이터):

| Stage | 게이트 (계획서 §3) | 검증 시점 |
|---|---|---|
| W2 | parallel_fetcher 호출 site 0 / atr_14d_method=wilder 100% | 즉시(0건 확인) / cron 후 |
| W3 | rate_limit_violations·kr_first_call_ms row 채워짐 (dart 제외 3/4) / Phase 1.1 손절 분포 무변경 | 다음 full cron 후 runtime_load_log.jsonl 측정 |

## 후속 분기 (§6)

| 트랙 | trigger |
|---|---|
| dart_failure_rate producer 신설 → W3 4/4 완성 | DART 실패 추적 sprint (별도) |
| 인자 의미 평가 (손절/진입/excursion 상관 → Brain v5 stage_filter 흡수 검토) | runtime_load_log N 누적 후 ([[feedback_spec_iteration_retract_rule]] 정합) |

상세 메모리: [[project_atr_phase0_migration]] 결정 21(wiring 격리), [[project_phase_2b_wide_scan]], [[project_next_session_kickoff]].
