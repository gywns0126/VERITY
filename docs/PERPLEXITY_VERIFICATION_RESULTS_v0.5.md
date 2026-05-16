# PERPLEXITY VERIFICATION RESULTS v0.5

검증: 2026-05-16 (사용자 Perplexity MED-D 호출 — 최종 묶음)
이전: v0.4 (MED-C) / v0.3 (MED-B) / v0.2 (MED-A) / v0.1 (HIGH 5)

---

## MED-D. VAMS 운영 임계 3건

### D-1. VAMS 통과 승률 55% → ✅ **최소 진입 임계 정합** + Expectancy 동반 의무

**Perplexity 핵심**:
- Van Tharp SQN (System Quality Number): `Expectancy / σ` ≥ 1.6 + R-multiple 분포
- Jonathan Kinlay: **60% 권장**, 55%는 낮은 편 (연속 손실 10회 내성 우려)
- Quantopian/AQR: OOS Sharpe ≥ 0.5~1.0, 승률 < Sharpe 우선
- Renaissance/Two Sigma: "소폭이라도 양의 Expectancy 지속"

**임계 권장**:
| 임계 | 의미 |
|---|---|
| 55% | 최소 진입 임계 (false positive 위험, 95% CI 필요) |
| **60%** | 실무 권장 (연속 손실 내성) |
| 65% | 고확신 (저회전·펀더멘탈) |

**핵심 발견**: 55% 단독 부족. **Wide Scan Brain v5 처럼 종목 多 멀티팩터** 는 55% gate + **Expectancy ≥ 1.2R 이중 임계** 권장.

**조치 (즉시 박힘)**:
- `VAMS_PASS_WIN_RATE = 0.55` 유지
- **신규 `VAMS_MIN_EXPECTANCY_R = 1.2`** (Van Tharp Expectancy formula)
- 실제 vams validation logic 적용은 vams 모듈 변경 필요 (별 큐)

---

### D-2. Max Factor Tilt 60% → ⚠️ **60→50 정정**

**Perplexity 핵심**:
| 기관 | 단일 자산/팩터 상한 |
|---|---|
| Markowitz MVO | 15-25% (개별 자산) |
| Norway GPFG | 종목 10% + Tracking Error ±1.5% |
| Yale Endowment | 30-40% (자산군) |
| Black-Litterman | View 강도 비례, 극단 해 방지 (~40%) |
| **CalPERS** | **단일 팩터 50% 상한 (내부 가이드)** |

**한국 시장 특수성**:
- KOSPI/KOSDAQ IT·배터리·바이오 시총 50%+ 집중
- 단일 팩터 = 사실상 섹터 집중 베팅
- 60% = 한국에서 과도 (비선형 리스크 급등)

**권장**: 40-50% 상한. CalPERS 50% 채택 (한국 보수 적용), GICS 2+ 섹터 분산 시 55% 예외.

**조치 (즉시 박힘)**: `VAMS_MAX_FACTOR_TILT_PCT = 60.0 → 50.0`

---

### D-3. Cohen 역발상 VCI ≥ 20 + fact ≥ 60 → ✅ **합리적 + 외국인 가중치 권장**

**Perplexity 핵심**:
- Steve Cohen 1987 블랙 먼데이 = 재량적 판단, 정량 임계 미공개
- AAII 공포탐욕지수 극단 ±20 = 학계 정합
- **학술 실증**: VCI ≥ ±20 + fact ≥ 60 이중 게이트 → 차후 6M 초과수익 **중위값 +8~15%**

**임계 비교**:
| VCI | σ 환산 | 빈도 | 정확도 |
|---|---|---|---|
| ±20 (현재) | ~1σ | 연 3-6회 | 중간 |
| ±25 | 1.5σ | 낮음 | ↑ |
| ±30 | 2σ | 2018/2020/2022 극소수 | ↑↑ |

**핵심**: ±20 + fact ≥ 60 = **합리적 설계** (학술 실증 정합).

**한국 보강 권장**: 외국인 순매도 ≥ 5 거래일 → VCI 가중치 ×1.3

**조치 (큐잉)**: 외국인 가중치 코드 변경 (vci 모듈) — 5/30 due

---

## 즉시 박힘 정리 (D-1 신설 + D-2 정정)

| | 변경 | 출처 |
|---|---|---|
| D-1 | `VAMS_MIN_EXPECTANCY_R = 1.2` 신설 (config) | Van Tharp Expectancy formula |
| D-2 | `VAMS_MAX_FACTOR_TILT_PCT 60 → 50` | CalPERS 50% / Black-Litterman 40% / 한국 섹터 집중 정합 |

## 큐잉 (2건)

- **D-1 후속**: vams validation logic 에 `expectancy_r` 계산 + 55% gate 와 AND 조건 — 5/30 (claude)
- **D-3 후속**: VCI 가중치 — 외국인 순매도 ≥ 5 거래일 시 ×1.3 — 5/30 (claude)

---

## 출처

- D-1: `vantharpinstitute.com/SQN` / `jonathankinlay.com/systematic-strategies`
- D-2: `web.stanford.edu/~boyd/papers/markowitz.pdf` / `nbim.no/government-pension-fund-global` /
       `people.duke.edu/~charvey/Black-Litterman`
- D-3: `verifiedinvesting.com/Steve-Cohen-SAC` / `cmcmarkets.com/market-sentiment-analysis` /
       `academic.oup.com/rfs` / `arxiv.org/html/2601.07131v1` (한국 외국인 수급)

---

## MED 4 묶음 전체 완료 (A + B + C + D)

| 묶음 | 검증 항목 | 즉시 박힘 | 큐잉 |
|---|---|---|---|
| MED-A | 3 (fact:sentiment / VCI / 등급) | 2 (mispricing_z + AVOID 25) | 1 (regime 동적) |
| MED-B | 4 (Ackman PBR / EV / ROE / 시총) | 1 (v2 재설계 통째) | 1 (US sec data) |
| MED-C | 2 (매출 가속 / 영업 레버리지) | 2 (2Q 연속 + OPM 필터) | 1 (컨센서스 서프라이즈) |
| MED-D | 3 (승률 / Factor Tilt / Cohen) | 2 (Expectancy + Tilt 60→50) | 2 (vams expectancy + 외국인 가중치) |
| **총** | **12** | **7** | **5** |

## 종합 학습

| 검증 결과 | 항목 수 |
|---|---|
| ✅ 검증 통과 (변경 없음) | 4 (VCI ±15/±25, 등급 75/60/45, 매출 ≥15%, Cohen ≥20+fact≥60) |
| ⚠️ 부분 적합 (보강 필요) | 5 (fact:sentiment / 매출 2Q / DOL 2.5 / 승률 + Expectancy / VCI 외국인) |
| ❌ 부적합 (재설계 필요) | 3 (Ackman PBR/EV/시총 v1 → v2 / AVOID 30 → 25 / Factor Tilt 60 → 50) |

**자체 정량 룰 12건 중 4건만 그대로 통과 (33%)** — Perplexity 검증의 가치 입증.
