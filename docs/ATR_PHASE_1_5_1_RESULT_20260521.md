# ATR Phase 1.5.1 Result — 2026-05-21 (Step A + Step B 종결)

**날짜**: 2026-05-21 KST
**전제**: Phase 0 verdict_official_60d = **ok** (avg_diff_pct 8.4% < 15%, `data/metadata/phase_0_results.json`)
**결과**: ✅ **Phase 1.5.1 검증 종결 — ATR(14)×2.5 동결 확정. 운영 임계 변경 없음. forward = W2/W3 wiring + 라이브 N 누적.**

> 이 문서는 `ATR_PHASE_1_5_1_RESULT_20260517.md` (FAIL — Step A 데이터 부재 + Step B fabrication) 를 **supersede** 한다. 그 FAIL 의 두 블로커(인프라)는 PR #38/#39/#40 으로 해소됨.

---

## 요약 결정 trigger

| 항목 | 결과 | PASS 게이트(§4) |
|---|---|---|
| 게이트 — Phase 0 verdict | ok (8.4%) | ✅ |
| Step A — actual_stop_hit_rate | **N=0 (5/17 reset 후 매도 0건)** = 통계 부족 | ⏸ 누적 대기 |
| Step B — 4-cell 비교 (env fix 후 유효) | **cell A(2.5) winner, 어느 cell 도 손절<60% 미달** | ❌ multiplier 변경 게이트 불충족 |
| 종합 verdict | **A 유지 (2.5 동결). W2/W3 wiring 분기.** | — |

---

## 전제 — 5/17 FAIL 두 블로커 해소

| 블로커 (5/17) | fix |
|---|---|
| Step A: VAMS 가 exit_reason 별도 jsonl 안 박음 → actual_stop_hit_rate 산출 불가 | PR #38 — `api/vams/engine.py:799 _append_exit_log()` (execute_sell 시 exit_reason append-only jsonl) |
| Step B: `analyze_5r` ATR_MULTIPLIER 모듈 하드코드 → 모든 cell 14×2.5 실행(fabrication) | PR #38 — config.py `ATR_STOP_MULTIPLIER` env wiring. PR #39 — sweep summary 추출(metrics nested) fix. PR #40 — KRX_API_KEY 주입(stratified-100 유니버스) + degrade sentinel |

---

## Step A — 운영 영향 사전 검증

- 입력: `data/vams/exit_log.jsonl` (PR #38 신설) + `data/vams/holdings`
- 현 상태: **5/17 09:00 KST VAMS reset (1000만 fresh) 후 매도 0건 → exit_log 미생성, open holdings 0**.
- 산출: `actual_stop_hit_rate = N/A (sample_size_holdings = 0)`.
- 판정: 명령서 §3.1 "sample < 10 holdings → 통계 부족 + 운영 누적 후 재실행". **인프라는 이제 active** (engine.py:876 execute_sell → `_append_exit_log`) → 매도 발생 시마다 자동 누적.

---

## Step B — 4-cell 비교 백테스트 (sweep, env fix 후 유효)

**소스**: `data/analysis/atr_4cell_sweep_20260521_132132.json` (workflow_dispatch `atr_4cell_sweep.yml`, run 26228215004).
**유니버스**: `stratified_dry_run_100__system_universe_20260520` (KRX OpenAPI 정상, whitelist degrade 아님), 97/96 종목, 2020~2025, 22,206 entries, seed=42.
**범위 한계**: cell C/D (period 22) = `not_supported` (compute_atr_14d 14 고정 — Phase 1.3 prerequisite). → period 14 multiplier 2.5 vs 3.0 만 비교.

| 지표 (weight §3.2) | A: 14×2.5 (운영) | B: 14×3.0 | 방향 | winner |
|---|---|---|---|---|
| stop_loss_rate (50%, ↓) | 71.31% | 68.06% | B 낮음 (−3.25%p) | B |
| 5r_hit_unique (15%, ↑) | 97 | 96 | A 많음 | A |
| max_excursion p50 (10%) | 7.186 R | 6.927 R | A 높음 | A |
| profit_factor (25%) | sweep 미산출 (analyze_5r 출력 외) | — | — | — |
| (참고) 5R 평균 도달일 | 84.2일 | 98.6일 | A 빠름 (−14.4일) | A |
| (참고) 시간만료 보유(max_days) | 1,219 | 1,993 | A 적음 (자본효율) | A |
| (참고) stop_loss large tier | 69.18% | 65.76% | B 낮음 | B |

**해석**: B(3.0)는 손절률만 우위(−3.25%p)이나, 회피된 손절이 승자로 전환되지 않고 **죽은돈(max_days +774)** 으로 흐름 + 5R 도달 오히려 −53건/14일 지연. **순효과 ≈ 무승부 + 자본효율 손해** = "성격 교환(whipsaw↓ vs 자본효율↓)" 일 뿐 실효 개선 아님.

---

## PASS 게이트(§4) 적용 — "multiplier 재검토 sprint" 진입 조건

| # | 조건 | 결과 |
|---|---|---|
| 1 | Step A \|delta\| < 10pp (운영=백테스트 정합) | ❌ Step A N=0 = 통계 부족 |
| 2 | recommended_cell ≠ A | ❌ A winner |
| 3 | recommended_cell stop_loss_rate < 60% (한국 적합 임계) | ❌ A 71.31% / B 68.06% **둘 다 >60%** |
| 4 | recommended_cell profit_factor ≥ A +0.1 | ❌ 실효 개선 없음 |

→ **게이트 4/4 불충족.** 명령서 §6 분기 = **"PASS but A winner → W2/W3 wiring 진입 (Phase 1.1 유지)"**.

### finding (5/2 🔴 verdict 재프레임)
5/2 풀스캔 v2 가 large tier 손절 75.6% → "ATR×2.5 한국 부적합" 🔴 했으나, sweep 결과 **multiplier 를 3.0 으로 넓혀도 손절률이 안 고쳐짐**(large 69→66% 여전히 >60%). → **높은 손절률 = multiplier 레버로 못 고치는 한국시장/주간진입(weekly ISO) 방법론의 성질**. tighter/wider stop 의 문제가 아님.

---

## 통계 honesty (RULE 7)

- Step B = **6년 백테스트** (22,206 entries, but 동일 종목·중첩 윈도우 → 독립 표본 아님). **운영 라이브 ATR N ≈ 0** (5/17 reset). → **예비 결과, 검증 진행 중**. 백테스트 방향성 신호일 뿐 검증된 엣지 아님.
- hit rate 단독 판단 금지 — 위 표 hit/손절/보유/도달일수/excursion 동시 병기.
- 임계 조정은 RULE 7 1회 권한 + N<50 이론 고정([[feedback_threshold_calibration_overfit_guard]]). 무승부에 권한 낭비 X → 동결.

## PM 결정 (2026-05-21, 사용자 동의)

**ATR_STOP_MULTIPLIER 2.5 동결.** 운영 코드/env 변경 없음 (명령서 §7 비변경 영역 준수).

---

## 후속 분기 (§6)

| 트랙 | 내용 | trigger |
|---|---|---|
| **W2/W3 wiring** | `ATR_W2_W3_WIRING_PLAN_v0.1` (Phase 1.1 유지하 parallel_fetcher wiring) | 다음 sprint (PM 결정) |
| **라이브 N 누적** | exit_log.jsonl 자동 append → actual_stop_hit_rate 산출 가능해짐 | 매도 발생 시 자동 |
| **임계 재결정** | 2.5 vs 대안 multiplier 재평가 | 라이브 ATR N≥50 + walk-forward 1회 (RULE 7 1회 권한 보존) |
| **period 22 (cell C/D)** | compute_atr_n 헬퍼 확장 후 진입 | Phase 1.3 prerequisite |

상세 메모리: [[project_atr_dynamic_stop]] "4-cell sweep 결과" 섹션, [[project_next_session_kickoff]].
