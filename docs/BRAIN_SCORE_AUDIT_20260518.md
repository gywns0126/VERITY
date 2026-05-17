# Brain Score Funnel Audit — 2026-05-18

**Purpose** — 베테랑 진단 우선순위 1 의제. 47일 BUY 0건 / brain_score max 50점 결함 root cause 정량 진단. 임계 조정 안 함 (CLAUDE.md RULE 7), PM 검수용 데이터만.

**Scope** — `data/portfolio.json` recommendations N=25 (universe 5/15 18:32 KST scan, ramp_up_stage 5000, 10 KR + 15 US). 5/16 P0-1 fix (`verity_brain.py:930-941` IC+regime weight normalize) 작동 검증 포함.

**Source files (verified existence + line numbers)**:
- `api/intelligence/verity_brain.py` 3578 lines
  - `_compute_fact_score` line 803 (14+ components)
  - `_load_ic_adjustments` line 551
  - `_IC_TO_WEIGHT_KEY` line 572 (multi_factor / consensus / prediction / timing)
  - P0-1 weight normalize fix line 930-941 (5/16)
  - brain_score 산출 line 2949: `raw = fs * w_fact + ss * w_sent + vci_bonus + gs_bonus + candle_bonus + inst_bonus - red_flag_penalty`
  - `score_breakdown` attach line 3045
- `api/quant/alpha/factor_decay.py`
  - `_classify_decay` line 182
  - `compute_ic_weight_adjustments` line 243
  - `_STATUS_MULT` line 265 (HEALTHY 1.0 / WEAKENING 0.85 / DECAYING 0.6 / DEAD 0.3 / INSUFFICIENT_ICIR 0.3)

---

## §1 — brain_score 분포 baseline

| metric | 값 |
|---|---|
| N | 25 |
| min | 28 |
| median | 37 |
| max | **46** |
| mean | 39.0 |

### 임계별 분포

| 임계 | grade | 건수 |
|---|---|---|
| ≥75 | STRONG_BUY | **0** |
| 60~74 | BUY | **0** |
| 45~59 | WATCH | 4 |
| 30~44 | CAUTION | 20 |
| <30 | AVOID | 1 |

### grade 분포 (red_flag 강등 + AVOID 재정의 적용 후)

| grade | 건수 |
|---|---|
| WATCH | 4 |
| CAUTION | 17 |
| AVOID | 4 |

**Memory 대비**: 5/5 진단 max=50 → **5/18 max=46** (개선 X, 오히려 4점 ↓). 5/16 P0-1 fix (weight normalize) 가 brain_score 분포에 의미 있는 영향 못 줌.

---

## §2 — 산식 trace 검증

```
brain_score = clip(raw, 0, 100)
raw = fs * w_fact + ss * w_sent + vci_bonus + gs_bonus + candle_bonus + inst_bonus - red_flag_penalty
```

### 가중치 (`brain_weights`)

| (fact, sent) | 종목 수 | quadrant |
|---|---|---|
| (0.8, 0.2) | **25 (전체)** | growth_down_inflation_down |

→ **메모리 7:3 → 실제 운영 8:2**. quadrant 단일 분면 (growth_down_inflation_down) 박혀서 fact dominant. 분면 diversity 0.

### 평균 contribution (N=25)

| 항목 | mean | max | trigger 빈도 |
|---|---|---|---|
| fact_contribution | 31.74 | 36.0 | 25/25 (100%) |
| sentiment_contribution | 10.01 | 10.4 | 25/25 (100%) |
| vci_bonus | 0.00 | 0 | **0/25 (0%)** |
| candle_bonus | 0.00 | 0 | **0/25 (0%)** |
| gs_bonus | 0.00 | 0 | **0/25 (0%)** |
| inst_bonus | 0.00 | 0 | **0/25 (0%)** |
| red_flag (penalty) | -2.80 | -10.0 | 13/25 (52%) |
| quadrant_unfavored (penalty) | 0.00 | 0 | 0/25 (0%) |

→ **이론 최대 (현 데이터 quality)** = 36 + 10.4 + 0 + 0 + 0 + 0 - 0 = **46.4** ✓ 실측 max 46 와 정합.
→ **BUY 임계 60 까지 거리 14점**, **STRONG_BUY 75 까지 29점**. 보너스 trigger 없이는 절대 불가.

---

## §3 — fact_score 14+ component breakdown

### fact_score 분포

| metric | 값 |
|---|---|
| min | 35 |
| median | 40 |
| max | **45** |
| mean | 39.7 |

### Component 별 (50.0 fallback 비율 포함)

| component | n | min | median | max | mean | fallback_50 |
|---|---|---|---|---|---|---|
| **commodity_margin** | 25 | 50.0 | 50.0 | 50.0 | 50.0 | **25/25 (100%)** |
| **dart_health** | 25 | 50.0 | 50.0 | 50.0 | 50.0 | **25/25 (100%)** |
| **perplexity_risk** | 25 | 50.0 | 50.0 | 50.0 | 50.0 | **25/25 (100%)** |
| **quant_volatility** | 25 | 50.0 | 50.0 | 50.0 | 50.0 | **25/25 (100%)** |
| analyst_report | 25 | 50.0 | 50.0 | 91.0 | 51.6 | 24/25 (96%) |
| moat_quality | 25 | 50.0 | 50.0 | 55.0 | 50.8 | 21/25 (84%) |
| consensus | 25 | 47.0 | 50.0 | 90.0 | 58.5 | 15/25 (60%) |
| export_trade | 25 | 35.0 | 50.0 | 58.0 | 52.3 | 11/25 (44%) |
| canslim_growth | 25 | 45.0 | 50.0 | 60.0 | 51.5 | 7/25 (28%) |
| multi_factor | 25 | 43.0 | 53.0 | 60.0 | 52.3 | 3/25 (12%) |
| backtest | 25 | 22.4 | 48.8 | 74.3 | 49.9 | 0/25 (0%) |
| graham_value | 25 | 24.0 | 62.0 | 97.0 | 61.8 | 0/25 (0%) |
| prediction | 25 | 13.9 | 59.1 | 84.3 | 58.4 | 0/25 (0%) |
| technical_mean_reversion | 25 | 7.6 | 57.2 | 80.5 | 54.1 | 0/25 (0%) |
| timing | 25 | 39.0 | 60.0 | 80.0 | 57.9 | 1/25 (4%) |
| quant_momentum | 25 | 19.0 | 49.0 | 80.0 | 45.1 | 1/25 (4%) |
| quant_quality | 25 | 28.0 | 56.0 | 70.0 | 55.0 | 2/25 (8%) |
| quant_mean_reversion | 25 | 30.0 | 45.0 | 65.0 | 46.4 | 1/25 (4%) |
| kr_fundamental_mean_reversion | 10 | 0.0 | 0.0 | 39.8 | 8.7 | 0/10 (0%) |

### 정량 진단

- **5 components 100% fallback 50** = data 수집 미작동 또는 운영 풀 미적용. 가중치 합 100% 중 이 component 비중이 fact_score 평균을 50 근처로 끌어내림.
- **dart_health 100% fallback**: KR 종목 10건 있는데도 dart_business_analysis 결과 미포함. DART KR 백필 수집 결함 강한 의심.
- **perplexity_risk 100% fallback**: external_risk_level 스캔 결과 미연동 (Perplexity scan 호출 후 portfolio 까지 propagate 안 됨).
- **quant_volatility 100% fallback**: alpha_combined.quant_factors.volatility 가 항상 default 50.
- **commodity_margin 100% fallback**: commodity_margin 수집 0건 또는 mapping 결함.
- **analyst_report 96% fallback**: 25 종목 중 1건만 analyst summary 박힘 (TMO 91점, 나머지 24건 50 default).
- **moat_quality 84% fallback**: \_compute_moat_score 가 84% 케이스에서 데이터 부족으로 50 반환.

---

## §4 — IC adjustment 검증

### 5/16 last run (factor_ic_history.json N=30 entries, primary 7d window)

| factor | IC | ICIR | status | multiplier | 적용 결과 |
|---|---|---|---|---|---|
| **multi_factor** | **-0.158** | -0.779 | **DEAD** | 0.3× | original 0.1876 → adjusted 0.0563 |
| **prediction** | **-0.094** | -0.397 | **DEAD** | 0.3× | original 0.0853 → adjusted 0.0256 |
| **timing** | **-0.167** | -0.755 | **DEAD** | 0.3× | original 0.0597 → adjusted 0.0179 |
| **consensus** | **-0.143** | -0.627 | WEAKENING | 0.85× | original 0.1279 → adjusted 0.1087 |
| momentum | +0.236 | +0.918 | HEALTHY | 1.0× | (alpha sub-factor) |
| quality | +0.006 | +0.056 | NEUTRAL | 1.0× | (alpha sub-factor) |

### 결정적 진단

**DEAD 4 factor 가 모두 NEGATIVE IC = anti-signal**. 현재 처리:
- 가중치 0.3× 로 demote ✓ (`factor_decay.py:271`)
- ❌ **그러나 score 값 자체는 flip 안 함**. component 점수 50~70 사이여도 30% 의 anti-signal 영향 그대로 brain_score 에 가산.
- ❌ 베테랑 진단 권장 "DEAD → disable" (`factor_decay.py:383-386` alert 만 발생, 실제 disable 미실행).

WEAKENING consensus 도 IC = **-0.143** (음수). 분류 기준 (`_classify_decay` line 202-204) 은 `ic_recent < -0.02` → DEAD 인데 consensus 는 WEAKENING 으로 분류됨. 분류 로직 자체 audit 필요 (slope/ic_all/ic_recent 조합 조건 흐름 검토).

### 5/16 P0-1 weight normalize 작동 확인 (verity_brain.py:937-940)

```
w_sum = sum(w.values())
if w_sum > 0 and abs(w_sum - 1.0) > 0.01:
    for k in list(w.keys()):
        w[k] = w[k] / w_sum
```

- normalize 자체는 정상 작동 (TMO 예시 raw 합 ≈ 0.7, normalize 후 합 1.0).
- 그러나 normalize 가 **alpha 있는 factor 로 비중 재분배** 의도였는데, alpha 있는 factor 들 점수 자체도 fallback 50 비중이 높아 **재분배 효과 무효화**.

### 신규 회귀 관찰: regime weighting

- 25 종목 모두 `regime_avg = 0.64` → bull regime 분류 → `bull_canslim_dominant` 모드.
- canslim_growth weight 0.0341 → **0.1023** (1.5×), graham_value weight 0.0682 → **0.0341** (0.5×).
- 그러나 canslim_growth 자체가 28% fallback + mean 51.5 = 변별력 낮음.
- bull regime 가정이 quadrant `growth_down_inflation_down` 과 충돌 (성장 down 이면 bull 아님). regime classification source 검증 필요.

---

## §5 — bonus 산식 trigger 실패 진단

### vci_bonus (verity_brain.py:2913-2917)

```
if vci_val > 25 and fs >= 60:  → +5
elif vci_val < -25 and fs < 50: → -10
```

- TMO 예: vci = -12 (ALIGNED), fs = 37 → 조건 불충족.
- 25 종목 vci 분포 검증 필요 — fact_score 가 60 이상 도달 못 하면 positive bonus 영구 X.

### candle_bonus, gs_bonus, inst_bonus

- 25 종목 모두 0. `_compute_candle_psychology_score`, `_compute_group_structure_bonus`, 13F institutional 모두 trigger 임계 너무 strict 이거나 data fetch 안 됨.

### red_flag_penalty hit 52% (13/25)

- 메모리 5/7 = 56%, 현재 = 52%. 비슷한 비율. 부분적으로 작동 중.
- TMO 예: PEG 4.0 / PBR×PER 77.8 → red_flag, penalty -5.

---

## §6 — 종합 root cause (4중 중첩)

1. **Data fallback dominance** — 5 components 100% fallback + 4 components 28~96% fallback. fact_score 평균 ~40, max 45 cap.
2. **DEAD factor anti-signal 미처리** — multi_factor / prediction / timing / consensus 4개 모두 IC negative 인데 score 값 flip 안 됨. 0.3× demote 만으로는 anti-signal 영향 제거 불가.
3. **Bonus pipeline 전체 무효** — vci/candle/gs/inst 4종 보너스가 25/25 종목 모두 trigger X. 모든 트리거 임계가 fact_score≥60 같은 도달 불가능한 조건에 묶임.
4. **Quadrant diversity 0** — 25 종목 모두 `growth_down_inflation_down` 단일 분면, weight 8:2 단일. quadrant 분류 검증 필요 (5/15 18:32 scan 시점의 macro snapshot 단일 → 모든 종목 동일 분면 강제).

### 이론 최대 도달 시뮬레이션 (현 데이터 quality)

- 5 fallback components 데이터 채워서 평균 65 도달 시: fact_score +5 ≈ 45 → 50
- DEAD 4 factor weight 0 (완전 disable): fact 평균 +3 ≈ 53
- bonus 1개라도 trigger (예 +3 candle): raw +3
- → brain_score 약 **53 × 0.8 + 50 × 0.2 + 3 = 55** (보수적 추정).

여전히 BUY 60 임계 도달 못 함. **임계 조정 안 하면 데이터 fix 만으로 BUY 부활 불가**. 임계 조정 시도 시 RULE 7 의무 — 1회 + PM 사전 승인 + 곡선 맞추기 금지.

---

## §7 — PM 결정 의제 (조정 X, 진단만)

Engineer 권장 actions (각각 PM 사전 승인 의무):

| # | action | scope | RULE 7 적용 |
|---|---|---|---|
| A | dart_health / commodity_margin / quant_volatility / perplexity_risk 4 component 데이터 수집 fix | 데이터 pipeline, brain_score 산식 X | OK (코드 fix) |
| B | analyst_report / moat_quality 산출식 검토 (84~96% fallback) | 산출식 변경 = 임계 조정 의제 | PM 승인 의무 |
| C | DEAD factor 가중치 → 0 (disable) 또는 score flip (1−x) | 산식 변경 | PM 승인 의무 + 단일 변수 통제 |
| D | bonus trigger 임계 완화 (vci/candle/gs/inst) | 임계 조정 | PM 승인 의무 + 곡선 맞추기 risk |
| E | grade 임계 75/60/45 자체 재 calibration | 임계 조정 (root) | **PM 승인 의무 + 1회만** |
| F | quadrant 분류 audit (25 종목 단일 분면 회귀 검증) | 산식 + macro snapshot 동시 | 검증 먼저 |

### 진행 권장 순서 (Engineer 추천, PM 결정 의무)

1. **F 먼저** (audit only): quadrant 단일 회귀가 회귀 결함이면 다른 모든 진단 무효.
2. **A 다음** (코드 fix only): 4 component data pipeline 만 — RULE 7 적용 X.
3. **C 검토** (PM 승인 후): DEAD factor 처리 산식. 단일 변수 통제 — 1 factor 씩.
4. **D~E 보류**: 데이터 fix 후 baseline 재측정. 1회 임계 조정 권한 = E 에 한 번만 박을지 보존.

### 즉시 박을 옵션 H (UI 명시, 백엔드 무영향)

site BUY 추천 0건 상태 명시 — "현재 전 운영 풀 max brain_score 46점, BUY 임계 60 미도달. 산식/데이터 audit 진행 중." [[feedback_no_premature_completion_claims]] + RULE 7 "(가설 N=25)" 정합.

---

## §8 — 변경 추적 / 검증 데이터

| 일자 | 변경 |
|---|---|
| 2026-05-05 | 초기 진단 (memory project_brain_score_funnel_audit) — max 50, 51 종목 |
| 2026-05-07 | component 분해 (memory 추가) — fact max 47, sent 55-58 |
| 2026-05-16 | P0-1 fix 박힘 (verity_brain.py:937 weight normalize) |
| 2026-05-18 | 본 audit — N=25, max **46**, fact max 45, sent 48-52, weight 8:2 단일, DEAD 4 factor 음수 IC 재확인 |

### Source data (재현 가능)

```bash
python3 -c "
import json
p = json.load(open('data/portfolio.json'))
recs = p.get('recommendations', [])
print([s.get('verity_brain', {}).get('brain_score') for s in recs])
"
```

`data/component_ic_result.json` (4/19 batch, raw 6 technical 컴포넌트) + `data/factor_ic_history.json` (97 entries, 5/16 last, primary 7d window) cross-reference.

### 관련 메모리

- [[project_brain_score_funnel_audit]] — 5/5+5/7 초기 진단 (10일 stale, 본 audit 으로 갱신 의무)
- [[project_brain_v5_self_attribution]] — 7:3 가중치 / 75-60-45-30 임계 자체 결정 명시 (실제 운영은 8:2 추가)
- [[feedback_data_collection_verification_mandatory]] — 5 component fallback fix 시 try/finally + logged=True 의무
- [[project_external_veteran_diagnosis_2026_05_17]] — 본 audit = 우선순위 1 산출
- CLAUDE.md RULE 7 — 임계 조정 1회 + PM 승인 + 곡선 맞추기 금지

---

**End of audit. 임계 조정 / 코드 변경 없음. PM 결정 대기.**
