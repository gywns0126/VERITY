# Cross-Link Simplify Retract (2026-05-04)

**Spec ID**: VERITY-CROSSLINK-THRESHOLDS-V1.5-simplified
**상위 spec**: V1.4 + V1.4.1 PATCH (docs/cross_link/ 보관)
**유형**: 운영 데이터 0건 상태에서의 dead layer 정리 (over-engineering 회수)

---

## 변경 요지

v1.0 → v1.4.1 까지 6 iteration 누적 spec 중 운영 12주 동안 동작 영향 0인 layer 4종 삭제.

| 삭제 layer | 사유 |
|---|---|
| **§9-2 TIER1 강등** | 결함 R — 통계적 정상 noise(13.5%) × 30 pair 평균 4.05건 + σ=2.55 → 임계 5건은 41% cycle 발동 cry-wolf |
| **§9-2 TIER2 강등** | KI-18 — §5 instant_hold(silent_pass 누적 3건) 와 임계 동일이라 항상 §5 가 먼저 발동 = dead code |
| **§10 rate limit (TIER3 일일 3건)** | TIER3 1건 = 즉시 hold 라 2건째 발생 시점엔 brain 이미 정지 = dead. 거기에 한도 초과 시 강등 회귀(False) 룰은 운영상 위험 |
| **§17 ROLLING_STABLE 5번째 phase** | enabled_tiers 영향 0, 표시만 — cosmetic |

---

## 유지된 valid layer

- §1 source: backtest_stats.json 직접 (verification_report stale 함정 회피)
- §2 snapshot-pair 모델 (rolling 아님)
- §3 verdict 3-tier (ready / manual_review / hold)
- §4 evaluator plugin 패턴 (1차 sub-factor `brain_distribution_normal`)
- §5 instant_hold: silent_pass 누적 3건 → hold (T-14 verdict 기반, self-healing 차단)
- §6 baseline 90일 mean + floor 0.45 + cold-start 0.5
- §7 σ = binomial SE on cumulative_trades
- §8 Gate A (cumulative_trades ≥ 20)
- §9-1 alert_tier (yellow/orange/red) — dashboard only, verdict 영향 X
- **§9-2 escalation: TIER3 1건 → hold** (§5 보다 strict 한 유일 분기, 유지)
- §15 unit 0~1 비율
- §17 phase 4종: INSUFFICIENT_DATA / TIER3_DISABLED / FULLY_ACTIVE / STALE_UNKNOWN
- phase 비가역성 (snapshot_n 변동 reverse 차단)

---

## 코드 영향

| 파일 | 변경 |
|---|---|
| `api/observability/cross_link_layer.py` | `_today_tier3_count` / `_phase_with_rolling_stable` 함수 삭제. `_evaluate_noise_floor_escalation` TIER3 만 남기고 단순화. rate_limit 분기 + ROLLING_STABLE phase 분기 + `NOISE_FLOOR_TIER1/TIER2` 상수 삭제. `_PHASE_RANK` 4 phase 로 축소. spec_version 갱신 |
| `tests/test_cross_link_layer.py` | T1 schema 검증에서 `rate_limit_status` 키 폐기 |
| `tests/test_cross_link_layer_p1.py` | `SCENARIOS` 12 → 9 (scenario_8/9/11 삭제) |
| `tests/mock/cross_link/scenario_8_*.json` | **삭제** (TIER1 dashboard 검증) |
| `tests/mock/cross_link/scenario_9_*.json` | **삭제** (KI-18 dead code 검증) |
| `tests/mock/cross_link/scenario_11_*.json` | **삭제** (TIER1 4건 below 의미 약함) |

테스트 결과: 15/15 PASS (P0 5건 + P1 9건 + summary 1건).

---

## 향후 재도입 검토

운영 12주 누적 후 (~2026-08-04) 재평가:

- TIER1/TIER2 강등 임계: 운영 데이터로 정상 noise 분포 재산출 → 임계 정합한 값 재도출
- rate_limit: TIER3 1건 hold 후에도 추가 TIER3 누적 발견 시 시스템 자체 이상 시그널 layer 로 재정의
- ROLLING_STABLE: rolling vs cumulative 구분이 의미 있는 시점 (Gate B 통과 후 30 cycle) 검증

검토 시점은 `user_action_queue` 에 등록.

---

## 관련 문서

- `VERITY_CROSS_LINK_SPEC_v1.4.md` — 전 본문
- `VERITY_CROSS_LINK_SPEC_v1.4.1_PATCH.md` — 결함 R/S/T/U 정정
- `CMD_VERITY_S1_5_NOISE_FLOOR_RETRACTION.md` — Sprint 1.5 명령서 (본 simplify 의 모태)
- `CMD_VERITY_CRON_BACKTEST_HISTORY.md` — KI-9 cron (별도 작업)
- `CMD_VERITY_S1_P2_WIRE.md` — 운영 통합 (별도 작업)
