# Tier 2 PM Decision Queue — 2026-05-18

**Purpose** — Tier 1 fix 13 commit 박힌 후 (BRAIN_SCORE_AUDIT_20260518.md / COMPONENT_FALLBACK_AUDIT § 7), 다음 단계 = Tier 2 산식/임계 조정. **모두 PM 사전 승인 의무** (CLAUDE.md RULE 7 — 1회만, 곡선 맞추기 금지). 본 doc = PM 결정 준비 자료 (코드 변경 X).

**Scope** — N=25 운영 풀, 5/18 trigger #3 결과 측정 후 PM 결정.

---

## §1 — Tier 1 효과 측정 baseline (trigger #2 결과)

| metric | baseline 5/16 | dev 5/18 trigger #2 | 회복 |
|---|---|---|---|
| brain_score min/med/max/mean | 28/37/46/39 | 33/40/49/40.84 | +5/+3/+3/+1.84 |
| grade WATCH/CAUTION/AVOID | 4/17/4 | 8/13/4 | +4/-4/0 |
| BUY / STRONG_BUY | 0/0 | **0/0** | **0** |
| external_risk fill | 0/25 | **10/25** | A7 작동 ✓ |
| volatility_20d fill | ?/25 | **25/25** | A5+yfinance 작동 ✓ |
| sec_financials | 10/25 | 10/25 (회귀, trigger #3 fix) | — |

**결정적 fact**: Tier 1 fix 9 commits 적용 후 **여전히 BUY 0건**. BUY 임계 60 까지 max 49 = 11점 거리.

---

## §2 — Tier 2 옵션 정의

### C (DEAD factor 가중치 0 — disable)

**현 상태**: 4 factor (multi_factor / prediction / timing / consensus) IC negative.
- 처리: 0.3× demote (factor_decay.py:271) 만 — anti-signal score 자체는 30% 영향 유지
- 베테랑 진단: DEAD → disable 권장 (factor_decay.py:383 alert 만 발생, 실제 disable 미실행)

**Fix proposal**:
- 옵션 a: 가중치 0 강제 (disable, 단일 변수 통제)
- 옵션 b: score flip (1 - x/100) × 100 — anti-signal 반전 시그널 활용
- 옵션 c: 0.0× × multiplier (0.3 → 0.0)

**효과 시뮬**: fact_score 평균 +3 (39→42), brain_score max +3 (49→52)
**Risk**: anti-signal 일시 회복 가능성 0 차단 (IC 가 positive 회복 시 재진입 의무)
**1회 권한 가치**: ⭐⭐⭐ (중간 — 시그널 quality ↑, score 도약 +3 작음)

### D (bonus trigger 임계 완화)

**현 상태**: vci / candle / gs / inst 4 bonus 모두 0/25 trigger.
- vci_bonus (verity_brain.py:2913): `vci_val > 25 and fs >= 60` → fs >= 60 도달 불가 = 영구 X
- candle / gs / inst 도 비슷한 strict 임계

**Fix proposal**:
- 옵션 a: vci_bonus `fs >= 60` → `fs >= 50` 완화 (낮은 1단계)
- 옵션 b: bonus 임계 자체 재 calibration (현 max 45 기반 → 40~50 trigger 가능)
- 옵션 c: 단순 임계 변경 X, bonus 산식 자체 재설계 (다음 sprint)

**효과 시뮬**: 1-2 bonus trigger 시 brain_score +3-5
**Risk**: 곡선 맞추기 (확증편향) — 현 data 에 맞게 임계 조정 = overfitting
**1회 권한 가치**: ⭐⭐ (낮음 — 임계 의존, sample N=25 작음)

### E (grade 임계 재 calibration)

**현 상태**: 75 / 60 / 45 / 30 (STRONG_BUY / BUY / WATCH / CAUTION 경계).
- 현 운영 풀 max 49 → BUY 60 영구 X = 임계 자체가 data 와 mismatch.

**Fix proposal**:
- 옵션 a: 60 → 50 (BUY 임계 1단계 완화)
- 옵션 b: 60 → 45 (현 max 기반)
- 옵션 c: percentile 기반 (top 10% = BUY, top 30% = WATCH 등 동적)

**효과 시뮬**:
- 옵션 a (60→50): BUY 0건 → 4건 (현 dev max 49 시점 cluster 4)
- 옵션 b (60→45): BUY 0건 → ~15건 (대량 발화, 부적합)
- 옵션 c: 통계적 robust 단 사용자 frame "고정 임계" 와 충돌

**Risk**: **곡선 맞추기 가장 강함** ([[feedback_no_premature_completion_claims]] / RULE 7). 단순 임계 조정 = sample N=25 빈약 baseline.
**1회 권한 가치**: ⭐ (낮음 — overfit risk 최대, 단 BUY 0건 영구는 site 가치 0)

---

## §3 — Engineer 추천 + PM 결정 의제

**Engineer 추천 진행 순서** (사용자 결정 의무):

1. **C 진입** (옵션 a — 0 disable) — anti-signal 제거, 단일 변수 통제, audit 정합
2. **trigger 후 측정** (C 효과만)
3. **D / E 보류** — sample N≥30 거래일 누적 후 재평가 (~6월 중순)

**또는 보류 권장**:
- 1회 임계 조정 권한 = 보존 (E 적용 시점 = N≥60 거래일 = 8월 이후)
- 현 baseline (dev max 49) = Tier 1 fix 만으로 +3 추가 회복 trigger #3 후 측정 가능
- BUY 0건 frame = site 자체 명시 (옵션 H) → 사용자 frame 정합

### CLAUDE.md RULE 7 정합 의무

- 1회 사용 시 commit message 에 PM 승인 기록 박음
- 단일 변수 통제 (C / D / E 동시 X)
- 곡선 맞추기 cross-check — N≥30 baseline 후 재평가

### Site 노출 의무 (RULE 7)

C/D/E 진입 시 site UI:
- "(가설 N=25)" 명시
- 임계 조정 trail 명시 ("60 → 50 (5/18 1회 권한 사용)")
- hit rate + expectancy + sample size + CI 병기

---

## §4 — 의제 보류 권장 (Engineer view)

**진입 권장 X 이유**:
1. Tier 1 fix 9 commits 효과 일부만 propagate (trigger #3 결과 측정 필요)
2. external_risk 10/25 + vol_20d 25/25 회복 = brain_score 도약 가능 (trigger #3 측정 후 확인)
3. Phase 0 trail (14일) + VAMS reset 후 0 거래일 = 임계 조정 권한 보존 가치 ↑
4. 사용자 frame ("자본 = 부산물 / 목표 X") 정합 = BUY 0건 자체 신호 (시장 약세 정합)

**진입 권장 시점**:
- N≥30 거래일 누적 (~6월 중순) 후 E 단독 진입 (단 1회 권한 보존 시점까지)
- 또는 Phase 1 (8월) 진입 직전 — Tier 2 5 module 도래 시점

---

## §5 — Cross-link

- [[project_brain_score_funnel_audit]] (Tier 1 진단)
- docs/BRAIN_SCORE_AUDIT_20260518.md §7 PM 결정 의제
- docs/COMPONENT_FALLBACK_AUDIT_20260518.md §3 Tier 2 적용 trigger
- CLAUDE.md RULE 7 (1회 권한 + 단일 변수 + 곡선 맞추기 금지)
- [[feedback_no_premature_completion_claims]] / [[feedback_praise_calibration]]

---

**End of Tier 2 PM decision queue. 본 doc = PM 결정 준비, 코드 변경 X.**
