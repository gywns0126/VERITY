# MarketHorizon V0 Plan (2026-05-06)

**목적**: "남이 코스피/시장 어디까지 가냐" 물을 때 답할 수 있는 단독 컴포넌트.
*분포 + 가정 노출* 정직 패턴 (단정 X). horizon 1M/3M/6M/12M.

## 위치
- `home` 페이지 첫 자리 (VerityChat 위 또는 옆)
- *항상 기본 질문* — 진입 시 즉시 답

## 백엔드 — `api/intelligence/market_horizon.py`

### V0 입력 (이미 portfolio.json 박힘)
| 필드 | 출처 |
|---|---|
| `yield_spread_2y_10y` | macro.us_10y - us_2y |
| `yield_spread_3m_10y` | bonds.yield_curves.us.spread_3m_10y |
| `cape` | macro.fred.cape.value (Shiller) |
| `ism_pmi` | macro.fred.ism_pmi.value |
| `hy_oas` | bonds.credit_spreads.us_hy_oas |
| `vix` | macro.vix |

### V0 산출 (4 핵심)

**1. Probit 침체확률** (Estrella-Mishkin 1996, 단일 변수)
```
P(recession in 12M) = Φ(-0.546 - 0.690 × spread_3m_10y)
```
- spread = -1.0 → ~71%
- spread =  0.0 → ~29%
- spread = +2.0 → ~3%
- *self-attribution*: 미국 1968 이후 7번 / 6번 hit (1971 false positive 1번)

**2. CAPE percentile** (1881- 분포 위치)
- 90+ percentile → 역사적 버블 (1929, 2000, 2021)
- 70-90 → 과열
- 30-70 → 평상
- 30- → 저평가

**3. Cycle stage** (rule-based 분류)
| stage | 조건 |
|---|---|
| early bull | CAPE < 50%ile + spread > 1.5 + PMI > 50 |
| mid bull | CAPE 50-75%ile + spread 0.5-1.5 + PMI > 50 |
| late bull | CAPE > 75%ile + spread 0-0.5 + PMI 45-55 |
| euphoria | CAPE > 90%ile + spread < 0 + HY OAS < 3% |
| bear | spread < 0 + PMI < 45 + HY OAS > 5% |

**4. Horizon median return** (regime 기반 historical lookup)
- 1M / 3M / 6M / 12M S&P 500 return *given current regime*
- median / 25-75 percentile / 5-95 percentile
- V0 lookup table = *S&P 500 1928-2024 historical regime별 forward return 분포*

### V0 산출 → portfolio.json
```json
"market_horizon": {
  "verdict": "late mid bull, 12M 침체확률 32%",
  "recession_prob_12m": 0.32,
  "cape_percentile": 87,
  "cape_value": 32.5,
  "cycle_stage": "late_bull",
  "horizons": {
    "1m":  { "median": 0.012, "p25": -0.02, "p75": 0.04, "p5": -0.07, "p95": 0.08 },
    "3m":  { "median": 0.025, "p25": -0.05, "p75": 0.08, "p5": -0.13, "p95": 0.16 },
    "6m":  { "median": 0.045, "p25": -0.08, "p75": 0.13, "p5": -0.21, "p95": 0.28 },
    "12m": { "median": 0.072, "p25": -0.10, "p75": 0.18, "p5": -0.30, "p95": 0.40 }
  },
  "signals": [
    { "name": "yield_spread_3m_10y", "value": 0.15, "lead_months": [6, 18], "direction": "neutral" },
    { "name": "cape", "value": 32.5, "percentile": 87, "direction": "warn" },
    { "name": "pmi", "value": 49.2, "direction": "warn" },
    { "name": "hy_oas", "value": 3.4, "direction": "neutral" }
  ],
  "model_meta": {
    "probit": { "source": "Estrella-Mishkin 1996", "hit_rate": "6/7 since 1968", "false_positive": "1971" },
    "horizon_returns": { "source": "S&P 500 1928-2024 regime lookup", "version": "v0" }
  },
  "as_of": "2026-05-06T20:30:00+09:00"
}
```

## Frontend — `framer-components/pages/home/MarketHorizon.tsx`

### Compact (평소, 1 row)
```
SYSTEM: late mid bull · 12M 침체 32% · CAPE 87%ile · 12M median +7%
```

### Expanded (tap)
1. **Cycle dot** — 5단계 점 (early/mid/late/euph/bear) 위에 현재 위치 표시
2. **Horizon grid** (4 horizon × 분포)
   - 각 horizon: median ± 25-75 박스 + 5-95 wisker (mini box-plot)
3. **Signal stack** (4 signal)
   - 각 row: name · value · 방향 화살표 · lead time
4. **Self-attribution**
   - probit hit rate 명시 (`6/7 since 1968`)
   - regime lookup version

## V1 (운영 후)
- LEI (FRED USSLIND) 추가
- AAII / COT positioning
- 5변수 거리 nearest-N analog matching (단순 lookup → 동적 매칭)
- HMM regime model (V2)

## 메모리 박음
`project_market_horizon` — V0 = probit + CAPE percentile + regime lookup

## 운영 검증
- 매일 산출 → portfolio.json 박힘
- 1주 후 사용자 평가: 답 만들 때 실제로 쓰는지
- 1달 후 self-attribution: probit signal 이 실제 시장과 어떻게 갈렸는지
