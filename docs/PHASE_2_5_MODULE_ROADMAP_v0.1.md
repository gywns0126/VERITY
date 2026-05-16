# Phase 2 — 1인 기관급 5 모듈 로드맵 v0.1

**박힘**: 2026-05-17 (Perplexity Q2 / Q4 / Q5 / Q6 학계 자문 적용).

`project_institutional_5module_roadmap` 정합. 8월~다음 해 1월 순차 박기. Over-engineering 함정 회피 = "이해 가능한 최소 복잡도" 원칙.

## 0. 핵심 설계 원칙 (Perplexity Q5 학계 자문)

**"1인 운용 적정 = 새벽 2시에 버그 고칠 수 있는 복잡도"**. 1,000만원 portfolio 의 진짜 가치 = 학습 자산. AUM 아님.

5 모듈 간 데이터 계약 (API 스펙) = Phase 2 시작 전 1페이지 문서화 의무 (가장 중요한 선행 작업).

---

## 모듈 1 (8월): Factor v0 — IC / IR / 분해

### 사전 prereq (TG-1, 65 거래일 PRODUCTION 게이트)
- wide_scan 5,500 PRODUCTION 진입 후 진입

### Perplexity Q2 학계 자문 적용
- **방법론**: Cross-sectional IC (Spearman) — Fama-MacBeth 는 Phase 3 이후
- **IC 측정**: Spearman Rank (Pearson 은 KOSPI 급등락 outlier 왜곡 X)
- **IC 분포 정합** (한국 시장 통상):
  - IC < 0.02 = 무신호 (노이즈)
  - IC 0.03~0.05 = 실용 하한
  - IC 0.05~0.10 = 실무 양호 ✅
  - IC > 0.10 = 우수 신호 (Brain v5 복합 같은 종합 신호)
  - IC > 0.15 = 매우 드묾, 과적합 의심
- **ICIR 임계** (= IC / σ(IC)):
  - ICIR < 0.2 → weight 강제 floor 30%
  - ICIR 0.2~0.3 → 경계, 다음 사이클 모니터
  - ICIR ≥ 0.3 → 정상 운용 게이트 ✅
  - ICIR ≥ 0.5 → 가중치 증가 정당화
  - ICIR ≥ 1.0 → 매우 강 (과적합 점검)
- **65 거래일 게이트**: 1차 방향성 게이트만. ICIR ≥ 0.3 = 잠정 통과. 부정 결과 (ICIR < 0.2) = 신뢰. **비대칭 게이팅**

### 측정 타임라인
| 시점 | 목적 | n |
|---|---|---|
| 65 거래일 (8월) | 1차 방향성 게이트 | 65 |
| 130 거래일 (11월) | 2차 강도 검증 | 130 (2 regime) |
| 260 거래일 (2027 8월) | 완전 검증 | 260 (full cycle) |

---

## 모듈 2 (9월): Stress v0 — Historical VaR (10Y)

### Perplexity Q5 학계 자문
**Historical Simulation (10Y lookback) = 1인 운용 표준**. Monte Carlo / CVaR 는 over-engineering.

| 방법 | 1인 적합 |
|---|---|
| Historical 10Y | ✅ 최적 |
| Monte Carlo | ⚠️ 과잉 (분포 가정이 결과 지배) |
| CVaR (ES) | △ 가능 (small sample 꼬리 오차) |

**한국 특화 lookback** = 반드시 2008 + 2020 + 2022 세 tail event 포함.

```python
historical_var_95 = sorted_returns.iloc[124]  # 10Y = 2,500 거래일, 5% 분위수
```

---

## 모듈 3 (10월): Regime v0 — Rolling Z-Score Rule

### Perplexity Q5 학계 자문
**HMM = over-engineering** (Baum-Welch EM → 1~2개월 regime 사후 인식). Random Forest = sample 과적합 KOSDAQ 소수 class BEAR 무시.

**권장 = 2-factor Rolling Rule**:
```python
spy_momentum = returns_20d.mean() / returns_20d.std()  # rolling Z
vix_level    = current_vix or vkospi

if spy_momentum > 0.5 and vix_level < 20:
    regime = "BULL"
elif spy_momentum < -0.5 or vix_level > 30:
    regime = "BEAR"
else:
    regime = "NEUTRAL"
```

---

## 모듈 4 (11월): Portfolio v0 — HRP

### Perplexity Q5 학계 자문
**HRP (Hierarchical Risk Parity) > ERC >> Black-Litterman** (12 종목 기준).

| 방법 | 12 종목 적합 |
|---|---|
| HRP | ✅ 권장 (공분산 역행렬 X, 섹터 클러스터 자동) |
| ERC (Equal-Risk Contribution) | △ 상관관계 무시 |
| Black-Litterman | ❌ view 확신도 (τ × Ω) 임의 설정 |

HRP 구현 5분:
```
1. 거리행렬 = sqrt((1 - corr) / 2)
2. linkage (ward) → dendrogram
3. quasi-diag 재정렬 → 역분산 bisect
```

Capital 3-Tier (P2-2) 와 통합 — tier 별 HRP 별 운영.

---

## 모듈 5 (12 ~ 1월): Attribution v0 — Brinson-Fachler

### Perplexity Q5 학계 자문
**Brinson-Fachler (1985) = 1인 운용 표준**. Carino / Geometric = 기관 multi-period linking 필요.

```python
allocation  = (w_p - w_b) * (r_b_sector - r_b_total)
selection   = w_b * (r_p_sector - r_b_sector)
interaction = (w_p - w_b) * (r_p_sector - r_b_sector)
active_return = allocation + selection + interaction
```

**Interaction effect = 설계상 잔차** — 무시하거나 Selection 흡수 (실무 표준). 공식 오류 X.

1인 분기 단위 분석 = 단순 산술 합산 ±0.5%p 오차 허용.

---

## 모듈별 Over-Engineering 함정 (Perplexity Q5)

| 모듈 | 함정 | 회피 |
|---|---|---|
| Stress | "정밀도 환상" (Monte Carlo 95% VaR 정확도 ₩42→₩43만원 집착) | Historical 단순 신뢰 기반 |
| Regime | "사후 레이블 함정" (HMM 과거 완벽 / 실시간 lag 2-4주) | Rolling rule lag 동일하지만 즉시 이해 가능 |
| Portfolio | "최적화 저주" (BL view 0.02 조정으로 Sharpe 0.01 ↑) | HRP equal-weight 차이 <0.05, 종목 선택 100배 중요 |
| Attribution | "Interaction Effect 공황" (allocation + selection ≠ active 발견 시 오류 오해) | 잔차 무시 / Selection 흡수 표준 |
| 공통 | "모듈 분리 실패" (9월 Stress ↔ 10월 Regime API 불일치) | Phase 2 시작 전 데이터 계약 1페이지 문서화 |

---

## 의존성 그래프

```
TG-1 (8월 말, wide_scan 65 거래일 PRODUCTION)
    ↓
모듈 1 (Factor v0, 8월) ─→ Phase 2 시작
    ↓ IC adjustments 활성
모듈 2 (Stress v0, 9월) ─→ MDD 시나리오 정량
    ↓ stress scenarios
모듈 3 (Regime v0, 10월) ─→ regime-aware 분기
    ↓ regime tagging
모듈 4 (Portfolio v0, 11월) + Capital 3-Tier (P2-2)
    ↓ HRP weights × tier 분리
모듈 5 (Attribution v0, 12~1월) ─→ 수익 분해 + factor IC 정합
    ↓
2027~ 운영 누적 → Calmar / MDD 측정 가능
2028 vision: Calmar 1.0+ / MDD <20% / Anti-fragile
```

---

## Cross-link

- [[project_institutional_5module_roadmap]] (5 모듈 일정 원전)
- [[project_phase_2b_wide_scan]] (TG-1 prereq)
- [[project_capital_3tier_mode]] (모듈 4 Portfolio 통합)
- [[project_golden_goose_vision]] (2028 vision)
- `docs/PHILOSOPHY_TIER_ROUTING_v0.md` (3-Tier SSOT)
- `docs/MASTER_RULE_DRIFT_AUDIT_v0.1.md` (Phase B audit)
