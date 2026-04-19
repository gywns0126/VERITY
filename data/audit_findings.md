# VERITY Brain — Audit Findings

## U-shape 알파 발견 (2026-04-19)

- 30종목 5년 8,130행 검증 결과 (`scripts/historical_replay.py`)
- 등급별 forward 30d 수익률:
  - **STRONG_BUY (+3.96%) ≈ CAUTION (+3.94%)** >> **BUY (+1.67%)** ≈ WATCH (+1.92%)
- **양 극단에 알파, 중간에 없음**
  - STRONG_BUY = deep oversold mean-reversion (RSI 18, momentum -11%, vol 17%)
  - CAUTION = high-vol momentum continuation (RSI 64, momentum +17%, **vol 50%**)
- **선형 등급 시스템으로 U-shape 표현 불가**
- **단조성 metric 은 이 universe 에서 무의미**

### 컴포넌트별 등급 분포 (참고)

| component | STRONG_BUY | BUY | WATCH | CAUTION |
|---|---|---|---|---|
| momentum_3m | -11.45 | -0.46 | 5.54 | 16.68 |
| momentum_1m | -9.18 | -2.47 | 2.65 | 10.22 |
| rsi_14 | 18.13 | 42.79 | 58.68 | 63.84 |
| price_to_ma200_pct | -12.91 | 0.94 | 7.78 | 20.98 |
| volatility_20d_ann | 17.23 | 20.30 | 27.53 | 49.63 |
| **fwd_30d_avg %** | **+3.96** | **+1.67** | **+1.92** | **+3.94** |

모든 6 컴포넌트가 등급별로 단조 증가하지만 수익률은 U자형. 선형 IC 측정으로는 U-shape 알파 포착 불가.

---

## §9 보류 사유

- **30 S&P 대형주 post-COVID bias**
  - 2020-01 ~ 2026-04 = post-COVID 강세장 + AI bubble (TSLA/NVDA/META 폭등)
  - high-vol = high-return 이라는 IC +0.10 도 universe 특성에 종속
- **universe 확장 후 재검증 필요**
  - 소형주 / 페니주 (진짜 AVOID 후보 포함)
  - 2008 금융위기 / 2018 무역전쟁 / 2011 유럽위기 등 다른 regime 포함
  - 한국 코스닥 (yfinance coverage 부실 → DART 직접 연결 필요)
- **§9-C (Sharpe 단조성) 장기 로드맵으로 이전**
  - 현 mean return 기준 단조성 → risk-adjusted (Sharpe) 단조성으로 전환
  - BUY = "최고 수익률" → "risk-adjusted 안전 매수"로 의미 재정의
  - CAUTION = "회피" → "고변동 momentum — 추격 위험" 으로 의미 재정의
  - 새 등급 `MOMENTUM_RIDE` 도입 후보 (CAUTION 의 high-vol 부분 분리)

---

## 현재 유효한 검증 결과

- **regime detection: 3/3 PASS** (유지)
  - COVID 크래시 (2020-02~03): STRONG_BUY 0% (평시 0.7%)
  - 2022 인플레: brain_score 평균 2021(55.94) → 2022(54.17) 하락
  - SVB (2023-03): 금융주 68.44 → 62.47
- **AVOID semantic 해소 (§8)**
  - AVOID n: 198 → 0 (대형주에서 fact-only AVOID 차단)
  - has_critical / macro_override 위기 cap 에만 한정
- **inflation_2022 PASS (V3 + regime gate)**
  - VIX > 30 일자에 mean-reversion bonus 비활성 → 거시 신호와 충돌 방지

---

## 작업 우선순위 (다음 세션)

1. **universe 확장 backfill** — 소형주 + 다양한 regime 포함 → 진짜 IC 재측정
2. **DART 연결** — 한국 fundamental 시계열 backfill (현재 DART 미사용)
3. **§9-C Sharpe 단조성** — universe 확장 후 라벨 의미 재정의 검토
4. **brain_history.py 90일 누적 대기** — production 데이터 prospective 검증 (이미 설치됨)

작성: 2026-04-19
관련 커밋: `29f2ec3` (V3 mean-reversion 재설계), `596c801` (§8 AVOID 재정의)
