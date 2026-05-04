# VERITY Cross-Link Layer Spec v1.4.1 PATCH

**Spec ID**: VERITY-CROSSLINK-THRESHOLDS-V1.4.1-20260504
**작성일**: 2026-05-04
**상위 spec**: V1.4 (DRAFT, 2026-05-04)
**유형**: PATCH (전문 재발행 X, 변경분만)
**목적**: 사용자 검토 보고 (2026-05-04) 발견 결함 R/S/T/U 4건 정정 + 결함 V/W/X/Y 명령서 patch list 박음

---

## 변경 사항 한눈에

| # | 결함 | 정정 위치 | 정정 내용 |
|---|---|---|---|
| R | TIER1=5 cry-wolf (41% cycle 강등) | §9-2 + §3-2 | **TIER1 강등 비활성** (옵션 A 채택). dashboard only. |
| S | §7-1 % 표기 오류 + 단방향/양방향 모호 | §7-1 + §9-2 | % 정정 + 단방향 명시 |
| T | rolling 60일 안정 시점 누락 | §17 + §9-2 | "60일+ ROLLING_STABLE" phase 추가 |
| U | §9-2 Tier별 read 함수 미구현 | §16 + §9-2 | `_rolling_tier_counts()` 인터페이스 명시 |

명령서 patch list (별도 작업):

| # | 결함 | 영향 명령서 | 정정 |
|---|---|---|---|
| V | §17 phase 비가역성 부재 | Sprint 1.5 | `cross_link_phase_state.json` 영속화 추가 |
| W | §14 v1.5 진입 시점 명시 | spec §14 | "v1.5 진입 = max(원래 12주, Sprint 1.5 종료 + 12주)" 명시 |
| X | §11 Telegram 핸들러 의존성 | P2 wire | `api/notifications/telegram_bot.py` 신규 핸들러 작업 항목 추가 |
| Y | §0-3 추정 위험 표 누락 | spec §0-3 | 5번째 행 추가 — "§9-2 임계값의 통계 정합성" |

---

## §3-2 정정 (결함 R)

### 변경 전 (v1.4)

| 강등 trigger | 강등 결과 |
|---|---|
| §5 instant_hold | hold |
| §9-2 TIER1 누적 ≥ 5건 | manual_review |
| §9-2 TIER2 누적 ≥ 3건 | manual_review |
| §9-2 TIER3 누적 ≥ 1건 | hold |

### 변경 후 (v1.4.1)

| 강등 trigger | 강등 결과 | 비고 |
|---|---|---|
| §5 instant_hold | hold | 그대로 |
| ~~§9-2 TIER1 누적 ≥ 5건~~ | ~~manual_review~~ | **삭제 (결함 R 정정, dashboard only)** |
| §9-2 TIER2 누적 ≥ 3건 | manual_review | 그대로 |
| §9-2 TIER3 누적 ≥ 1건 | hold | 그대로 |

**TIER1 운영 의미 변경**: §9-1 dashboard yellow 강조 임계 only. verdict 영향 X. NOISE_FLOOR_TIER1=5 상수는 dashboard 강조 트리거로 재정의 (코드 상수값 변경 X).

---

## §7-1 정정 (결함 S)

### 변경 전 (v1.4)

| Tier | k | 통계 의미 |
|---|---|---|
| TIER0 (silent) | < 1 | baseline ± 1σ 이내 = 정상 noise |
| TIER1 | 1 ≤ k < 2 | ± 1~2σ = 약한 outlier (32% 사건) |
| TIER2 | 2 ≤ k < 3 | ± 2~3σ = 중간 outlier (5% 사건) |
| TIER3 | k ≥ 3 | ± 3σ 이상 = extreme outlier (0.27% 미만) |

### 변경 후 (v1.4.1)

| Tier | k | 양방향 % | **단방향 %** | 비고 |
|---|---|---|---|---|
| TIER0 (silent) | < 1 | 68% | 34% | baseline ± 1σ 이내 = 정상 noise |
| TIER1 | 1 ≤ k < 2 | 27% | **13.5%** | 약한 outlier (양쪽 합산 27%, 단방향 13.5%) |
| TIER2 | 2 ≤ k < 3 | 4.3% | **2.15%** | 중간 outlier |
| TIER3 | k ≥ 3 | 0.27% | **0.135%** | extreme outlier |

**§9-2 임계 산출 근거 명시**: §9-2 누적 임계는 **단방향 silent_pass** 만 기준. cry_wolf (반대 방향)는 §12 비대칭 처리 path를 따름.

---

## §9-2 정정 (결함 R + S + T + U)

### 변경 후 (v1.4.1)

**산출**: rolling 30 pair 내 Tier별 **silent_pass** violation count 누적 (단방향).

**source**: `data/metadata/cross_link_violations.jsonl` (Sprint 1.5 신설).

**산출 함수 인터페이스 (결함 U 정정)**:

```python
def _rolling_tier_counts(
    jsonl_path: Path,
    window_days: int = 30,
) -> Dict[str, int]:
    """§9-2 누적 산출. silent_pass 만 (단방향).
    
    Returns:
        {"TIER1": int, "TIER2": int, "TIER3": int}
    """
```

**임계** (결함 R 정정):

| Tier | 누적 임계 | 강등 결과 | 비고 |
|---|---|---|---|
| TIER1 | **N/A (강등 비활성)** | — | dashboard only (NOISE_FLOOR_TIER1=5는 §9-1 yellow 강조 임계로 재정의) |
| TIER2 | ≥ 3건 / 30 pair | manual_review | 단방향 2.15% × 30 pair = 평균 0.65건 → 3건 누적 = 통계적 의미 |
| TIER3 | ≥ 1건 | hold | 단방향 0.135% = 0.27% 미만 사건 = 1건도 우연 X |

**활성 시점 + rolling 안정 시점 명시 (결함 T 정정)**:
- **활성 시점**: Gate B (snapshot-pair ≥ 30) 통과 후
- **rolling 안정 시점**: 활성 후 30 cycle 경과 후 (= drop-out 발생 시점)
- 활성 ~ rolling 안정 사이 30 cycle = cumulative 동작 (drop-out 0)
- rolling 안정 후 = 정상 30 pair rolling drop-out

운영 의미: §9-2 임계 검증의 통계적 정합성 보장 시점은 활성 + 30 cycle 후. §17 phase에 ROLLING_STABLE 추가.

---

## §16-1 정정 (결함 U)

### 변경 후 (v1.4.1)

`cross_link_violations.jsonl` schema 명시:

```json
{
  "cycle_id": "cycle_42",
  "timestamp": "2026-05-04T09:00:00Z",
  "violations": [
    {
      "evaluator": "brain_distribution_normal",
      "evaluation": "TIER2",       // ← Tier 분리 영속화 (필수)
      "direction": "silent_pass",  // ← 단방향/양방향 분리 (§9-2 정합)
      "value": 0.43,
      "baseline": 0.55,
      "sigma": 0.091
    }
  ],
  "alert_tier": "orange",
  "verdict": "manual_review",
  "escalation_result": {...} | null
}
```

**핵심 필드**:
- `violations[].evaluation`: TIER1/TIER2/TIER3 분리 영속화 (read 시점 Tier 분리 카운트 가능)
- `violations[].direction`: silent_pass / cry_wolf 분리 영속화 (§9-2 단방향 산출 정합)

신설 결정: **Sprint 1.5에서 신설** (기존 P0/P1에 영속화 없음 — 사용자 검토 결함 U 명시).

---

## §17 정정 (결함 T + V)

### 변경 후 (v1.4.1) — Phase 5 추가

| Phase | 시점 | 활성 layer | 비활성 layer |
|---|---|---|---|
| **0~30일 INSUFFICIENT_DATA** | Gate A/B 미통과 | §9-1 dashboard only | §9-2 / TIER3 / §11 Telegram (대부분) |
| **30~50일 TIER3_DISABLED** | Gate A/B 통과 시작 | §9-1 + §9-2 (TIER2만, TIER1 강등 비활성) | TIER3 / cold-start baseline |
| **50일+ FULLY_ACTIVE** | snapshot_n ≥ 50 | §9-1 + §9-2 (TIER2/TIER3) + §11 | — |
| **60일+ ROLLING_STABLE** (신설) | §9-2 활성 + 30 cycle | rolling drop-out 정상 동작 | — |
| **90일+ HISTORICAL** | history 누적 90일 | §9-1 + §9-2 + §11 + historical σ baseline | cold-start / effective_n 주입 |

**Phase 비가역성 명시 (결함 V 정정 — Sprint 1.5에서 처리)**:
- snapshot_n cycle 변동으로 phase reverse 위험
- 해결: `data/metadata/cross_link_phase_state.json` 영속화 (max historical phase 기준 idempotent 진행)
- Sprint 1.5 명령서 §"phase 비가역성" 항목 추가 작업

---

## §14 정정 (결함 W)

### 변경 후 (v1.4.1)

**v1.5 진입 시점**:

```
v1.5 진입 = max(원래 12주, Sprint 1.5 종료 + 12주)
        ≈ 14~15주 후
```

이유: Sprint 1.5 retraction이 §9 분기 4 재구현 = 본격 평가 cycle reset. mid-review 6주 / 본격 12주 모두 Sprint 1.5 종료 시점 기준 재산출.

---

## §0-3 정정 (결함 Y)

### 변경 후 (v1.4.1) — 5번째 행 추가

| 위험 | 영향 § | 발견 시 처리 |
|---|---|---|
| §5 결함 L = T-14 verdict | §5 | v1.5 §5 재작성 |
| §9 noise floor 5/3/1의 운영 의미 | §9 | v1.5 §9 patch |
| §12 처리 정책 비대칭 형태 | §12 | v1.5 §12 patch |
| §11 v1.3 PM trigger 표 | §11 | v1.5 §11 통합 |
| **§9-2 임계값의 통계 정합성** (신규) | **§9-2** | **mid-review 6주 발동 빈도 실측 → 임계값 재조정 검토** |

---

## 명령서 patch list (별도 작업, 본 patch 진입 후)

### Sprint 1.5 명령서 patch

| 항목 | 정정 |
|---|---|
| §2-2 `_evaluate_noise_floor_escalation()` | TIER1 분기 삭제 (강등 비활성) |
| §2-4 `cross_link_violations.jsonl` schema | direction 필드 추가 (silent_pass/cry_wolf 분리) |
| §2-5 `_rolling_tier_counts()` 신규 | §9-2 산출 함수 별도 박음 |
| §2-7 phase 비가역성 (신규) | `cross_link_phase_state.json` 영속화 작업 추가 |
| §3-2 신규 mock 시나리오 | scenario_8 (TIER1 누적 ≥5) 삭제 또는 dashboard only 검증으로 변경 |

### P2 wire 명령서 patch

| 항목 | 정정 |
|---|---|
| §2-3 Telegram dispatcher | `api/notifications/telegram_bot.py` 신규 핸들러 의존성 명시 |
| §3-1 Mock | TIER1 강등 시나리오 제거 |

### KI-9 cron 명령서 patch

| 항목 | 정정 |
|---|---|
| 변경 없음 | history 누적 cron은 §9-2 변경과 독립 |

---

## 절대 하지 말 것 (v1.4.1)

1. **NOISE_FLOOR 상수값 변경 X** — TIER1=5 / TIER2=3 / TIER3=1 그대로 유지. TIER1만 운영 의미 재정의 (verdict→dashboard).
2. **v1.4 본문 전면 재발행 X** — 본 patch는 변경분만. v1.4 + v1.4.1 합쳐서 source of truth.
3. **mid-review 6주 전 임계값 재조정 X** — 운영 데이터 누적 후 결정. 월가 정신 정합.
4. **결함 R~Y 8건 외 spec 추가 변경 X** — patch 범위 한정.

---

## 진입 OK

본 v1.4.1 patch 발행 + 명령서 3건 patch 완료 후 Claude Code 전달.

**전달 순서 (v1.4 동일 유지)**:
1. Sprint 1.5 retraction (patch 통합) + KI-9 cron 병행
2. 둘 다 종료 PASS 후 P2 wire (patch 통합)

**운영 진입 후 검증**:
- mid-review 6주: TIER2/TIER3 발동 빈도 실측 + TIER1 dashboard 변동 빈도 실측
- 본격 12주: NOISE_FLOOR 임계값 재조정 (TIER1 강등 재활성화 검토 포함)

---

**END of v1.4.1 PATCH.**
