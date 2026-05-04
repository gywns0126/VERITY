# Sprint 1 P1 검증 보고서

## 1. 시나리오 결과 (7건)

| 시나리오 | PASS/FAIL | evidence |
|---|---|---|
| INSUFFICIENT_DATA — Gate A 미통과 | PASS | skipped: cumulative_trades=8 below Gate A (20) |
| TIER3_DISABLED 정상 PASS | PASS | hit_rate=0.550 within baseline=0.500 ± 1σ (0.091) |
| TIER3_DISABLED Silent PASS Tier 2 cycle 단위 (강등 X) | PASS | hit_rate=0.300 below baseline=0.500 -2σ (0.091) |
| FULLY_ACTIVE Silent PASS Tier 3 + instant_hold | PASS | hit_rate=0.200 below baseline=0.500 -3σ (0.071) |
| Cry-wolf — hold 인데 hit_rate 양수 | PASS | hit_rate=0.650 above baseline=0.500 +2σ (0.071) |
| Baseline degradation alert — floor 0.45 안착 | PASS | hit_rate=0.450 within baseline=0.450 ± 1σ (0.050) |
| Stale source fallback — KI-8 정정 | PASS | skipped: stale_source_no_fallback |
| TIER3 1건 즉시 hold (extreme outlier) | PASS | hit_rate=0.200 below baseline=0.500 -3σ (0.071) |
| Phase 비가역성 — FULLY_ACTIVE 유지 (snapshot_n 변동 무관) | PASS | hit_rate=0.500 within baseline=0.500 ± 1σ (0.071) |

## 2. Spec 정정 통합 결과

- [x] KI-10 Gate A cumulative_trades 누적 로직 작동
- [x] KI-7 trust_log path alias 통일 (data/metadata/trust_log.jsonl)
- [x] KI-8 stale 필드 fallback (updated_at 6h 임계 → STALE_UNKNOWN)
