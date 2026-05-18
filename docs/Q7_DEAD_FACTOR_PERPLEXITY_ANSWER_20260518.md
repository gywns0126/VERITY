# Q7 답변 — DEAD Factor 처리 Best Practice (Perplexity, 2026-05-18)

**Source**: Perplexity Sonar Pro (사용자 paste, 2026-05-18). 학술 + 실무 reference 풍부.

## Executive Summary

2026년 학술·실무 컨센서스:
1. **Disable (w=0) = 표준** (Grinold-Kahn FLAM + AQR + Barra IC-IR weighting 모두 지지)
2. **Demote 0.3× = 임시** (6개월 이내 초기만 정당화). 현재 0.3× = **부적합**
3. **Flip = 조건부** (ICIR 절대값 > 0.5 + 경제적 논리 검증 시만)
4. **IC-IR weighting = 가장 권장 systematic 접근법** (Brain v6 정공법)

---

## 3 옵션 비교 (Q7 답 정합)

| 기준 | Demote (0.3×) | **Disable (w=0)** | Flip (anti-signal) |
|------|---|---|---|
| 정보 손실 | 70% | 100% | 0% (재활용) |
| Composite 오염 | 부분 잔존 | **없음** | 없음 (방향 수정) |
| Turnover 충격 | 낮음 | 높음 (급격) | 낮음 (점진) |
| 적합 IC 범위 | -0.02 ~ -0.05 | **< -0.05 (지속)** | < -0.05 (안정적 음수) |
| 학술 지지도 | 낮음 | **높음** | 중간 (조건부) |
| 2026 실무 관행 | 임시 조치 | **기본 처리** | 전문 quant firm |

= **현재 4 factor (multi_factor / prediction / timing / consensus) 모두 IC < -0.05 지속** = Demote 0.3× 부적합 + Disable 정공법

---

## 현재 4 factor 처리 권장 (Perplexity 답)

| Factor | 1차 권장 | 조건 / 별 audit |
|---|---|---|
| **multi_factor** | **Disable → 재설계** | IC negative 원인 분석 먼저 (복합 score 설계 오류 의심) |
| **prediction** | **Flip 검토** | ICIR 절대값 > 0.5 확인 후 (ML/통계 anti-signal 가능) |
| **timing** | **Disable (이 기간)** | regime 변화 시 복원 |
| **consensus** | **Flip 또는 Disable** | contrarian 논리 검증 후 |

---

## 단기 실행 계획 (Perplexity 답, Q3 2026)

1. **즉시** (=오늘 sprint 박을 수 있는 영역): 4 factor disable (w=0) → composite score impact 측정
2. **1개월 후**: prediction/consensus flip 버전 생성 → shadow mode 운용
3. **3개월 후**: flip 버전 IC 실측 → 진짜 anti-signal 확인
4. **6개월 후**: IC recovery 또는 flip 확정 시 graduated weight 복원

---

## Weight Reset 정책 (Perplexity 답)

### Rolling Window Confirmation
- IC ≥ +0.03 × 1개월: 0.1× probe (모니터링)
- IC ≥ +0.03 × 3개월 연속: 0.3× → 0.5× (부분 복원)
- IC ≥ +0.05 × 6개월 연속: 1.0× (완전 복원)

### EWMA 대안 (autonomous)
- `IC_EWMA = λ × IC_now + (1-λ) × IC_EWMA_prev`
- 권장 λ = 0.04~0.06 (12~25개월 half-life)
- 자동 ramp-up = false recovery 회피

### Cooldown Period
- IC negative 지속 기간의 50%
- 예: IC negative 12개월 → cooldown 6개월
- 재진입 시 2회 이상 IC negative = 구조적 재검토 (feature re-engineering)

---

## 학술 / 실무 reference (Q7 답)

### 학술
- **Grinold-Kahn FLAM**: IR = IC × √BR. IC < 0 = IR 감소 = disable 정당
- **SSRN 2023**: "Fundamental Law of Active Management under Fundamental Factor Model"
- **arXiv 2025**: "IC negative signal = inverse relationship, contrarian strategies"
- **Bailey & Lopez de Prado 2012**: PSR / 후속 DSR
- **Kakushadze & Yu 2016 (arXiv)**: "How to Combine a Billion Alphas" — IC negative alpha = 음수 weight 자동 (long-only constraint 하 0 clip)

### 실무
- **AQR 2024**: "Can Machines Build Better Stock Portfolios?" — IC negative signal = optimizer 자동 낮은 weight
- **Bridgewater Pure Alpha**: factor 상관관계 구조 우선, IC negative라도 diversification 기여 시 유지
- **WorldQuant**: IC < -0.05 안정적 = flip하여 contrarian alpha 재등록
- **Barra CNE5/CNE6 (MSCI)**: IC-IR weighting 표준, IR < 0 = 자연 0 수렴

---

## Engineer Engineer 분석 (Q7 답 → VERITY 적용)

### 현재 운영 풀 (N=25, 14 거래일)
- multi_factor IC -0.158 / ICIR -0.779 = 구조적 음수 (12개월 미만 단 단순 noise 아님)
- prediction IC -0.094 / ICIR -0.397 = 음수 + ICIR 절대값 0.4 (flip 검토 임계 근접)
- timing IC -0.167 / ICIR -0.755 = 구조적 음수
- consensus IC -0.143 / ICIR -0.627 = 음수 + ICIR 절대값 0.6 (flip 정당)

### Tier 2 C 옵션 확정 (PM 결정 의무)

**옵션 a (Engineer 추천)**: multi_factor + timing **disable (w=0)** + prediction + consensus **flip audit 별 sprint**
- 학술 정합 (Disable = 표준)
- 단일 변수 통제 (multi/timing 만 = 2 factor, prediction/consensus 별 sprint = 단계적)
- Q7 답 정합 ("Disable → 재설계" / "Disable (이 기간)")

**옵션 b**: 4 factor 모두 disable
- 가장 단순
- 학술 정합 (모두 IC < -0.05 지속)
- 단 prediction/consensus 의 anti-signal 가치 손실

**옵션 c**: IC-IR weighting 전환 (Brain v6 정공법)
- 가장 long-term 정합
- 산식 자체 변경 = 큰 sprint
- 다음 sprint 또는 Brain v6 큐잉

### Engineer 추천 진행 순서

1. **즉시** (이번 sprint): multi_factor / timing disable (단일 변수 통제, 2 factor)
2. **다음 sprint**: prediction / consensus flip audit (ICIR 절대값 확인 + 경제적 논리 검증)
3. **Brain v6**: IC-IR weighting 전환 (Q7 답 best practice)

### Weight Reset 정책 (자기 산식 정합)

- 매주 IC 측정 (현재 7d / 14d / 30d window)
- IC ≥ +0.03 × 3개월 연속 → 단계적 복원 (0.1× → 0.3× → 0.5× → 1.0×)
- weight_history.jsonl 영속화 (자기 trail)

---

## Cross-link

- `docs/TIER2_PM_DECISION_QUEUE_20260518.md` (Q7 답 반영 C 옵션 확정 의무)
- `docs/BRAIN_SCORE_AUDIT_20260518.md` § 4 (factor_decay.py:271 0.3× → 0 disable)
- `[[project_brain_v5_self_attribution]]` (7:3 가중치 + IC-IR weighting 전환 의제)
- `[[project_brain_v6_design_2026_05_17]]` (Brain v6 sprint: alphalens-reloaded + IC-IR weighting)
- `[[feedback_perplexity_collaboration]]` (외부 자문 정합)

---

**End of Q7 답 정리. Q9 (grade 임계) / Q11 (minimum N) 답 받음 wait.**
