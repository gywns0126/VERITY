# Quadrant Regression Audit — 2026-05-18

**Purpose** — Brain Score Audit (`BRAIN_SCORE_AUDIT_20260518.md`) §6 root cause 4 "quadrant diversity 0" 별도 audit. F-task. 25/25 종목 모두 `growth_down_inflation_down` 단일 강제 = 회귀인지 vs 의도된 상태인지 정량 판별.

**Scope** — `detect_economic_quadrant` (verity_brain.py:1998) 입력 데이터 trace + portfolio.macro 실측값 cross-check + constitution brain_weights 매핑 의도 검증.

**결론 (선요약)** — **회귀 결함 확정**. 함수가 찾는 키 (`fred.gdp_growth`, `fred.cpi_yoy`, `fred.ism_pmi`, `fred.pce_yoy`) 가 portfolio.macro.fred 에 전혀 없음. 데이터는 다른 키 (`fred.core_cpi.yoy_pct`, `fred.unemployment_rate.pct`, `fred.us_recession_smoothed_prob.pct`) 에 정상 채워짐. **단순 key naming mismatch + fallback 영구 trip → growth_down_inflation_down 영구 강제**.

---

## §1 — 산식 trace

`detect_economic_quadrant` (verity_brain.py:1998-2048)

```python
gdp_growth = fred.get("gdp_growth", {}).get("value")     # ← MISSING
cpi_yoy    = fred.get("cpi_yoy",    {}).get("value")     # ← MISSING

if gdp_growth is None:                                    # 항상 True
    pmi = fred.get("ism_pmi", {}).get("value")           # ← MISSING
    if pmi is not None:
        gdp_growth = float(pmi) - 50
    else:
        mood = macro.get("market_mood", {}).get("score", 50)
        gdp_growth = (mood - 50) * 0.06                  # ← fallback trip → -0.6

if cpi_yoy is None:                                       # 항상 True
    pce = fred.get("pce_yoy", {}).get("value")           # ← MISSING
    if pce is not None:
        cpi_yoy = float(pce)
    else:
        cpi_yoy = 2.5                                     # ← 영구 하드코드

growth_up    = gdp_growth > 1.5     # -0.6 > 1.5 → False (mood ≤ 75 시 항상)
inflation_up = cpi_yoy > 3.0        # 2.5 > 3.0 → False (영구)
# → growth_down_inflation_down 영구 강제
```

### 4 입력 키 portfolio 존재 검증

| 함수가 찾는 키 | portfolio.macro.fred 존재? |
|---|---|
| `fred.gdp_growth.value` | **MISSING** |
| `fred.cpi_yoy.value` | **MISSING** |
| `fred.ism_pmi.value` | **MISSING** |
| `fred.pce_yoy.value` | **MISSING** |

→ 4/4 다 부재. fallback chain 끝까지 트립 → **mood proxy (-0.6) + 2.5 하드코드 강제**.

### 실측 trip 값 (portfolio.json 5/17 14:21)

```json
{
  "quadrant": "growth_down_inflation_down",
  "gdp_growth": -0.6,            // (40-50)*0.06 = -0.6, mood=40 비관
  "cpi_yoy": 2.5,                // 하드코드 default
  "favored": ["국채","금","배당주"],
  "unfavored": ["원자재","경기민감주"],
  "crypto_bias": "risk_off"
}
```

---

## §2 — 진짜 매크로 데이터 (있지만 안 읽힘)

portfolio.macro.fred 실제 내용:

| key | structure | value | proxy 가능? |
|---|---|---|---|
| `fred.core_cpi` | `{index, date, yoy_pct: 2.99}` | yoy_pct = **2.99** (2026-04) | **cpi_yoy proxy 가능** |
| `fred.unemployment_rate` | `{pct, date, mom_change_pp, yoy_change_pp, series_id}` | pct = 4.3 (2026-04) | growth proxy (역수) |
| `fred.us_recession_smoothed_prob` | `{pct, date, mom_change_pp, series_id}` | pct = 1.82 (2026-03) | growth proxy (역수) |
| `fred.consumer_sentiment` | `{value, date, mom_change, series_id}` | value = 53.3 (2026-03) | mood proxy 비교 |
| `fred.dgs10` | `{value, ...}` | 4.47 | duration risk |
| `fred.cape` | `{value, ...}` | 41.66 | valuation extremes |
| `fred.breakeven_inflation_10y` | `{value: None}` | **수집 미작동** | (T10YIE FRED OK 인데 portfolio 미연동) |
| `fred.ism_pmi` | **부재** | — | NAPMI series 자체 수집 X |

→ **CPI/실업/경기침체 확률 데이터 모두 있음**. ism_pmi 만 수집기 자체 부재 (FRED 의 NAPMI deprecated 이슈 추정).

### fred_health 작동 검증 (data/metadata/fred_health.jsonl, 5/17 06:01 last run)

5 series 모두 status=ok:
- UNRATE / UMCSENT / BAMLH0A0HYM2 (HY spread) / T10YIE (breakeven) / WALCL (Fed BS)

→ FRED 수집 자체는 정상. **portfolio.macro.fred 로 propagate 되는 단계에서 일부 key 누락** (T10YIE → breakeven_inflation_10y.value 빈 채로 박힘).

---

## §3 — collector / brain 사이 disconnect

`api/collectors/macro_data.py:317`:

```python
cpi_yoy = (fred.get("core_cpi") or {}).get("yoy_pct")  # 2.99 정상 수집
if cpi_yoy is not None:
    if float(cpi_yoy) >= 4.5:
        ...  # macro_diagnosis 텍스트 생성용으로만 사용
```

→ collector 는 `cpi_yoy` 를 **로컬 변수** 로 계산해서 macro_diagnosis 메시지에만 쓰고, **portfolio.macro.fred.cpi_yoy.value = 2.99 같은 구조로 저장하지 않음**.

→ brain 의 `detect_economic_quadrant` 는 `fred.cpi_yoy.value` 만 찾음. **collector → brain 사이 fred 구조 약속 불일치**.

### 다른 reader 동일 회귀

- `api/intelligence/market_horizon.py:782` — `_safe_get(macro, "fred", "ism_pmi", "value")` 동일 회귀 (영구 None → fallback)
- `api/notifications/telegram_bot.py:633` — `auto_q.get('gdp_growth')` / `auto_q.get('cpi_yoy')` 텔레그램 메시지에 가짜 -0.6 / 2.5 출력 중

→ **quadrant 가짜 값이 텔레그램 알림까지 propagate** = `[[feedback_no_premature_completion_claims]]` 정합 위반 (자기 산식이 가짜 매크로 기반).

---

## §4 — regime_diagnostics vs quadrant 모순

`portfolio.regime_diagnostics`:
- `trailing_score + leading_score × 1.5 / 2.5 = regime_avg ≈ 0.64` (bull)
- source: `strategy_evolver._classify_regime` (별도 산식)

`portfolio.verity_brain.market_brain.economic_quadrant`:
- `growth_down_inflation_down` (bear-ish, risk_off)
- source: `detect_economic_quadrant` (위 회귀 fallback)

→ **두 시스템이 서로 다른 매크로 source**. fact_score 의 regime_weighting (verity_brain.py:843-856) 은 `bull_canslim_dominant` 모드 활성 (regime_avg > 0.3 임계). 동시에 brain_weights 는 `growth_down → 0.8/0.2` 적용. 두 산식이 정반대 시그널 동시 호출.

---

## §5 — 분면 분류 매크로 신호 mapping (constitution 의도)

`data/verity_constitution.json` decision_tree.brain_weights:

| quadrant | fact | sentiment | 의도 |
|---|---|---|---|
| growth_up_inflation_down | 0.65 | 0.35 | 호황·디스인플레 = sentiment 비중 ↑ (risk-on 감정 추적) |
| growth_up_inflation_up | 0.70 | 0.30 | 인플레+성장 = 균형 (default) |
| **growth_down_inflation_down** | **0.80** | **0.20** | **수축기 = fact 비중 ↑** |
| growth_down_inflation_up | 0.85 | 0.15 | 스태그플레이션 = fact 최대 |
| default | 0.70 | 0.30 | 분면 미확정 시 |

→ constitution 의도는 **분면별 차등** (0.65 ~ 0.85). 현 회귀 결과 모든 종목이 단일 분면 강제 → **다섯 분면 design 무효화 / sentiment 비중 영구 0.2**.

### sentiment 비중 0.35 vs 0.20 영향 시뮬 (현 데이터)

가정: 진짜 분면이 growth_up_inflation_down 이면 weight (0.65, 0.35) 적용:
- TMO 예: fact 37 / sent 49
- 현 (0.8, 0.2): 37×0.8 + 49×0.2 = 29.6 + 9.8 = **39.4** ✓ (실측 34, red_flag -5)
- 새 (0.65, 0.35): 37×0.65 + 49×0.35 = 24.0 + 17.2 = **41.2** (+1.8)
- → 분면 변경 효과: 종목별 ±1~3점 변동. BUY 60 임계 도달 여전히 어려움.

**but** 분면 정상화 + 종목별 quadrant 차등 + sector unfavored 매칭이 살아나면 분류 회복. brain_score 절대값 보다 **상대 ranking 개선** 효과가 더 큼.

---

## §6 — 회귀 vs 의도 판정

**회귀 확정**. 근거:

1. `fred.cpi_yoy.value` ← 함수가 찾는 키. portfolio 에 없음. 같은 데이터가 `fred.core_cpi.yoy_pct` 에 정상 채워짐 (2.99). collector 가 둘 다 채워야 하는데 한쪽만 채움.
2. `fred.gdp_growth.value` ← 함수가 찾는 키. portfolio 에 없음. proxy 후보 (`us_recession_smoothed_prob.pct` 1.82) 채워짐. collector 가 GDP proxy 변환 안 함.
3. `fred.ism_pmi.value` ← FRED NAPMI/MANPMI 수집기 자체 부재. portfolio 에 키 없음.
4. fallback chain 마지막 `cpi_yoy = 2.5` 하드코드 → 영구 trip.
5. mood proxy `(40-50)*0.06 = -0.6` → mood ≤ 75 인 경우 영구 trip.

**의도된 상태가 아님** — constitution 의 5 분면 차등 설계가 단일 분면 강제로 무효화. brain_audit §1 의 weight diversity 0 직접 cause.

---

## §7 — fix 후보 (Engineer 분석, PM 결정 의무)

| # | action | scope | RULE 7 적용 | 권장 |
|---|---|---|---|---|
| **F1** | collector fix: `core_cpi.yoy_pct` → `fred.cpi_yoy.value` 동시 채우기 | 데이터 mapping, 산식 X | OK (코드 fix) | **추천** |
| F2 | collector fix: `us_recession_smoothed_prob.pct` 또는 `unemployment_rate.yoy_change_pp` → gdp_growth proxy 박기 | proxy 산식 정의 | PM 승인 의무 (산식) | 보류 |
| F3 | `detect_economic_quadrant` 입력 키 mapping fix (`fred.core_cpi.yoy_pct` 직접 읽기) | brain 산식 변경 | PM 승인 의무 | 대안 |
| F4 | 분면 분류 임계 변경 (cpi_yoy > 3.0 → > 2.5 Fed target) | 임계 조정 | RULE 7 **1회만 + 사전 승인** | 금지 (now) |
| F5 | 매크로 데이터 미확정 시 default 분면 (0.7/0.3) 사용 fallback 변경 | 산식 변경 | PM 승인 의무 | 대안 |
| F6 | NAPMI / ISMPMI series FRED 수집기 추가 | 데이터 pipeline 신설 | OK (수집기) | 보류 (NAPMI deprecated 추정) |

### 권장 진행 (PM 결정 의무)

1. **F1 먼저** = 가장 안전. collector 가 같은 데이터를 두 키 (core_cpi.yoy_pct + cpi_yoy.value) 에 동시 채움. 산식 변경 X. brain 자동 회복.
2. **F3 대신 또는 동시** = brain 함수 입력 키 매핑 변경 (core_cpi 직접 읽기). collector 변경 없이 fix 가능. 단 산식 변경이라 PM 승인.
3. F2/F4/F5 = baseline 회복 후 재측정. 1 회 임계 조정 권한 = F4 에 보존.
4. F6 = ISMPMI series 사용 가능성 별도 조사 (FRED docs 검증 후 결정).

### F1 적용 후 예상 효과

- portfolio.macro.fred.cpi_yoy.value = 2.99 → inflation_up = False (2.99 < 3.0, 간발의 차)
- gdp_growth 는 여전히 mood proxy (-0.6) → growth_up = False
- → **여전히 growth_down_inflation_down 강제** (cpi 만 fix 해서는 분면 안 바뀜)

**F1 + F2 (또는 F3) 둘 다 적용해야 분면 회귀 회복 가능**. F2 는 us_recession_smoothed_prob 같은 proxy 산식 정의 필요 → PM 승인 의무.

---

## §8 — 다음 세션 의제

본 audit = F-task closure. brain_audit §7 PM 결정 의제 (A/B/C/D/E/F) 중 F 만 진행.

remaining:
- A (5 component data pipeline fix): 코드 fix only, RULE 7 적용 X → 다음 sprint 진입 가능
- B/C/D/E (산식/임계 변경): F1/F2 적용 후 baseline 재측정 → 1 회 조정 권한 보존

H (UI 명시) = 즉시 박을 옵션 유지.

---

## §9 — 변경 추적

| 일자 | 변경 |
|---|---|
| 2026-05-18 | F-task audit (본 doc) — quadrant 회귀 확정, fix 후보 6개 제시 |

### 관련 메모리

- [[project_brain_score_funnel_audit]] (2026-05-18 갱신, 본 audit = 4중 root cause 중 #4 의 별도 trace)
- [[project_brain_v5_self_attribution]] — brain_weights 가중치 자체 결정 명시
- [[project_fred_silent_skip_audit]] — FRED silent skip 패턴 (본 회귀와 다른 layer)
- [[feedback_data_collection_verification_mandatory]] — F1 적용 시 try/finally + logged=True 검증 의무
- [[feedback_no_premature_completion_claims]] — 가짜 매크로 → 텔레그램 propagate = 정합 위반

### Source data (재현)

```bash
python3 -c "
import json
p = json.load(open('data/portfolio.json'))
fred = p['macro']['fred']
print('cpi_yoy proxy:', fred['core_cpi']['yoy_pct'])  # 2.99
print('quadrant input:', fred.get('cpi_yoy'))         # None
print('quadrant output:', p['verity_brain']['market_brain']['economic_quadrant']['quadrant'])
"
```

---

**End of F-audit. 코드 변경 / 임계 조정 없음. PM 결정 대기.**
