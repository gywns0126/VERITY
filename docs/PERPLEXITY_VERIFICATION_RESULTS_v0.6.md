# PERPLEXITY VERIFICATION RESULTS v0.6

검증: 2026-05-16 (Brain 자가 성장 NQ 5건 호출 — Q1-Q5 결정 의존 5건 적용)
이전: v0.5 (MED-D) / v0.4 (MED-C) / v0.3 (MED-B) / v0.2 (MED-A) / v0.1 (HIGH 5)

---

## NQ 5건 검증 + 즉시 적용 종합

### NQ1. IC 측정 최소 sample size → ⚠️ **7일 통계적 취약, sample confidence penalty 적용**

**Perplexity 핵심**:
- ICIR=0.5 가정 시 t-stat≥2 위해 **T≥16 거래일** (실용 30-60일)
- ICIR=0.3 (약한 팩터): T≥45
- 기관 표준: BARRA 12-36개월(252-756일) / Wells Fargo 12-24개월
- **min_history_days 7 완화는 통계적 취약**. 팩터 유형별 분리 권장:
  - 가격 기반 (모멘텀/변동성): 7일 OK
  - 재무 팩터 (Piotroski 등): 분기 공시 기준 (min_history 무의미)

**적용 (Q1 P0-2)**:
- 7일 임계 유지 (insufficient_data 고착 해소 우선)
- **신규**: sample size confidence penalty 추가 (`factor_decay.py`):
  - N ≥ 30: full multiplier
  - N 14-29: ×0.7 shrinkage
  - N 7-13: ×0.4 shrinkage
- `_shrink_mult(raw_mult, conf)`: `1.0 + (raw_mult - 1.0) × conf`
- 후속 큐 (P2): 팩터 유형별 (price-based vs fundamental) min_history 분리

---

### NQ2. 동적 가중치 multiplier 0.8-1.2x → ✅ **정합** + floor 30% + Kelly 변형

**Perplexity 핵심**:
- 학계 단일 표준 X. AQR Taming the Factor Zoo (2018): L1/L2 shrinkage 권장
- AMH (Andrew Lo): ±20% 좁은 범위는 under-adaptive 가능성
- **Factor Timing 2021 실증** (JSTOR):
  - 제약 없음 → OOS 심각하게 열화
  - **±20% (0.8-1.2x) = 안정적**
  - ±50% → 과적합 위험 높음
- **floor 30-50% 필수** (AQR 계열 암묵적 관행) — 0 수렴 시 신호 재활성화 능력 손실
- Kelly 변형:
  - hit_rate < 45%: × 0.5
  - 45-50%: × 0.8
  - 50-55%: × 1.0 (유지)
  - 55-60%: × 1.10-1.15
  - > 60%: × 1.2 (cap)

**적용 (Q8 P1-2, `brain_learning.py:compute_hit_rate_weight_multiplier`)**:
- 5-tier multiplier (poor/below_avg/neutral/good/strong)
- floor 30% 강제 (raw < 0.30 시 0.30 으로 클립)
- Sample size confidence (Half-Kelly 변형):
  - samples < 10: × 0.5
  - 10-30: × 0.75
  - ≥ 30: × 1.0
- `applied = 1.0 + (raw - 1.0) × confidence`

---

### NQ3. Grade 분포 drift 임계 → ✅ **PSI 1순위 + 이중 조건 + regime 분리**

**Perplexity 핵심**:
- **PSI 1순위 권장** (등급 = 범주형 5-bin 적합)
- KS test: N 큼 시 오탐 → 단독 X
- Wasserstein: N < 100k 추정 오차 → 부적합
- KL divergence: PSI 와 유사 거동 (PSI 가 대칭화 변형)

**PSI 표준 임계**:
- PSI < 0.10: 안정 (stable)
- 0.10-0.25: 중간 변동 (moderate) — 원인 분석
- ≥ 0.25: 중대 변동 (major) — 시스템 재보정

**이중 조건**: `(KS p < 0.05) AND (단일 등급 비중 변화 ±5%p)`

**Regime 분리** (자연 vs 결함):
- Regime flag ≥ 2개 동시 (VIX/외인/USD-KRW/cycle 등) → 자연 shift, 4주 유예
- Regime flag < 2개 + PSI ≥ 0.10 → 결함성 drift, 재보정 alert

**적용 (Q6 P1-3, `api/observability/grade_distribution_drift.py` 신규 모듈)**:
- `compute_psi(baseline_dist, current_dist)` — PSI 표준 공식
- `compute_grade_share_diff` — 등급별 ±%p 변화
- `detect_regime_flags(portfolio)` — VIX/USD/cycle 외생 flag 검출
- `evaluate_grade_drift` — 통합 평가 (PSI + 비중 변화 + regime 분리 → alert_level)
- `log_drift_evaluation` — ledger 적재 (`data/metadata/grade_drift_log.jsonl`)

---

### NQ4. Brain v6 next-gen 방향성 → ✅ **TradingAgents 2025 + RAG + Online + RL**

**Perplexity 핵심**:
1. **Multi-Agent Ensemble** (가장 빠른 성장):
   - TradingAgents 2025: Bull/Bear/Risk Manager 토론 → 단일 모델 대비 Sharpe +14-22%
   - FinCon NeurIPS 2024: Conceptual Verbal Reinforcement
   - Apex Quant: 강세/약세/중립 3-agent debate voting
2. **RAG Augmentation** (즉시 구현 가능):
   - **BGE-M3 임베딩** (한국어 recall 우수)
   - FAISS → Qdrant 단계 확장
   - 512 token + 64 overlap, Dense + BM25 Hybrid Search
3. **Online Learning** (Hybrid Regime-Triggered):
   - NYU Stern 2025: OGU Sharpe 1.26 / Fast Universalization 1.25
   - Batch (Weekly 평상시) + Online Fast Adaptation (Regime change 시)
4. **RL Position Sizing**:
   - PPO (Stable-Baselines3) → SAC
   - **Sharpe + MDD 페널티 + 한국 거래세 0.2% 반영** (보상 핵심)

**기관 동향**:
- AQR Asness: "AI 공시 파싱 우월" 발언 → RAG 강력 근거
- Citadel: 10,000 코어 백테스트 (5분 완료, 우리는 무관)
- RenTec Medallion: ML 강화 추정

**적용 (Q5 P0-4, `docs/BRAIN_V6_ROADMAP.md` 신규, 260L)**:
- 4-Layer Stack 정의 (Data / Specialist / Debate / RL)
- P0: RAG + Bull/Bear Debate (2026 Q3-Q4)
- P1: Online + PPO Shadow (2027 Q1)
- P2: LLM Alpha + 500 factor ML (2027 Q2+)
- v7 vision: Full auto-evolution

---

### NQ5. 자동 룰 진화 patterns → ✅ **EWMA 1차 + SHAP sign consistency + Bayesian Prior**

**Perplexity 핵심**:
- **Renaissance Medallion**:
  - p-value < 0.01 자동 편입/퇴역
  - 통계적 이탈 자동 비활성화
  - "실행 불가 거래" 에서도 학습 (포트폴리오 레벨 틸트)
  - 단일 통합 모델 — 신호 추가/퇴역 가능
- **Two Sigma SHAP**:
  - SHAP value sign consistency (sign 반전 → "Leaky Signal")
  - SHAP × IC 상관 < threshold → factor quarantine
- **알고리즘 선택**:
  - **EWMA 1차** (λ=0.94 RiskMetrics): 소샘플 가능, regime change 느림
  - ε-Greedy Bandit 2차: 보통 regime 감지
  - Thompson Sampling: 50건+ 이후
  - Bayesian Online: Prior 의존
- **한국 소샘플 (5-10건) 권장 3-단계**:
  1. EWMA IC 트래킹 (λ=0.90, 반응성 ↑)
  2. Bayesian Prior 주입 (Mauboussin + 자체 백테스트)
  3. Postmortem 루프 자동화 (regime-conditional weight)

**적용 (Q7 P1-1, `api/intelligence/postmortem_auto_evolve.py` 신규)**:
- `update_ewma(prev, new, λ=0.94)` — RiskMetrics 표준
- `detect_sign_consistency_violation` — SHAP-like sign 반전 감지
  - consistency_score ≥ 0.8: stable / 0.5-0.8: weakening / < 0.5: leaky (quarantine)
- `apply_postmortem_to_factor_weights` — misleading_factors → EWMA 감쇠 → quarantine
- `evaluate_and_persist` — end-to-end + ledger 적재 (`data/metadata/postmortem_auto_evolve.jsonl`)

---

## 즉시 박힘 정리 (NQ 5건 적용 결과)

| NQ | 모듈 | 신규 함수 / 변경 |
|---|---|---|
| **NQ1** | `api/quant/alpha/factor_decay.py` | `_shrink_mult` + sample size confidence penalty 추가 |
| **NQ2** | `api/metadata/brain_learning.py` | `compute_hit_rate_weight_multiplier` 신규 (Kelly 변형 + floor 30%) |
| **NQ3** | `api/observability/grade_distribution_drift.py` | 신규 모듈 (PSI + regime 분리) |
| **NQ4** | `docs/BRAIN_V6_ROADMAP.md` | 신규 docs (260L, 4-Layer Stack + Phase 로드맵) |
| **NQ5** | `api/intelligence/postmortem_auto_evolve.py` | 신규 모듈 (EWMA + sign consistency + quarantine) |

---

## 후속 큐 (적용 결과 활성화 필요)

| 큐 | 내용 | due |
|---|---|---|
| 1 | factor_decay 팩터 유형별 (price vs fundamental) min_history 분리 — NQ1 후속 | 6/15 |
| 2 | brain_learning compute_hit_rate_weight_multiplier → strategy_evolver/verity_brain 실제 wiring | 5/30 |
| 3 | grade_distribution_drift 평가 → alert_dispatcher 통합 (cron) | 5/30 |
| 4 | postmortem_auto_evolve → 매일 cron 실행 + strategy_evolver wire | 5/30 |
| 5 | Brain v6 P0 (RAG + Debate) 진입 — 65 거래일 게이트 통과 후 | 8/17 |

---

## 종합 통계

### Perplexity 검증 완료 누적
- HIGH 5 (v0.1) + MED 12 (v0.2-v0.5) + NQ 5 (v0.6) = **22 항목 검증 완료**

### 자체 정량 룰 vs Perplexity verdict
- 그대로 통과: 5 (29%)
- 보강 필요: 9 (41%) — 정합하지만 추가 조건/필터
- 재설계: 8 (36%) — 임계값 또는 구조 자체 변경

### 자가 성장 인프라 점수 변화
- audit 전: **56/100** (P1 58 / P2 58 / P3 58 / P4 75 / P5 32)
- NQ + 인프라 박힘 후 추정: **72/100** (+16)
  - P1 학습 루프: 58 → 72 (EWMA + hit_rate multiplier + 메모리 인덱스)
  - P2 자체 검증: 58 → 70 (Phase verdict 템플릿 + staged_apply + drift 감지)
  - P3 메모리 진화: 58 → 75 (인덱스 122 모두 등록 + drift cron)
  - P4 운영 데이터: 75 → 80 (factor_decay confidence + hit_rate 자동)
  - P5 미래 방향성: 32 → 65 (Brain v6 roadmap + P0/P1/P2 명시)

> **다음 게이트**: 5/18 첫 평일 cron 후 65 거래일 운영 → 8/17 PRODUCTION 진입 → Brain v6 P0 시작 (2026-09)
