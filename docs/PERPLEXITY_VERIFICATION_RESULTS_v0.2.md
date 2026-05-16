# PERPLEXITY VERIFICATION RESULTS v0.2

검증: 2026-05-16 (사용자 Perplexity MED 묶음 호출, v0.1 후속)
연관: `docs/PERPLEXITY_VERIFICATION_BACKLOG_v0.1.md` MED-A/B/C/D
이전: `docs/PERPLEXITY_VERIFICATION_RESULTS_v0.1.md` (HIGH 5)

---

## MED-A. Brain 가중치 / 등급 임계 3건

### A-1. Brain v5 fact:sentiment 7:3 비율

**Verdict**: ⚠️ **학계 단일 표준 X. 동적 권장**

**Perplexity 핵심**:
| 학파/기관 | 감성 처리 | 비중 |
|---|---|---|
| Fama-French 5F | 감성 제외 | 0% |
| Carhart 4F + Sentiment | 모멘텀 = 감성 대리 | 10-20% |
| Andrew Lo AMH | regime 동적 | 동적 |
| AQR Multi-Factor | Momentum 내포 | 15-25% |
| Probability.nl 실증 | 독립 팩터 추가 시 IR 0.43 | 20-30% 효과 |

**한국 시장 특수성** (외국인 거래 비중 급증):
- KOSDAQ 외국인 비중 13% → **27% (2026)**
- KOSPI 외국인 지분율 37%+ (5년 9개월 최고)
- 외국인 수급 = 감성 팩터 핵심 (USD/KRW r=0.37)
- 고감성 regime 에서 고베타 팩터 수익 역전

**권장 설계**:
| 시장 | 기본 비율 | regime 전환 시 |
|---|---|---|
| KOSPI 대형주 | 7:3 | VIX↑/외인 순매도/USD/KRW↑ → 8:2 방어 |
| KOSDAQ 소형주 | **6:4** (감성↑) | regime 전환 시 7:3 |

**조치**: 🟡 큐잉 — regime 분기 동적 가중치 (verity_brain 확장 큰 작업)

---

### A-2. VCI ±15 / ±25 임계

**Verdict**: ✅ **±1σ/±2σ 정합. fact-sentiment gap (mispricing) 추가 권장**

**Perplexity 핵심**:
- **VCI ±15 / ±25 = ±1σ / ±2σ 정합** (AAII Sentiment Survey 실증)
- AAII 1987~ 실증:
  - Bullish > +2σ → 6개월 후 **-0.7%**
  - Bullish < -2σ → 6개월 후 **+14.0%** (정합률 100%)
  - Bearish > +3σ → 6개월 후 **+25.8%** (정합률 100%)
- Templeton/Marks/Druckenmiller 모두 **정량 임계 명시 X** (정성 원칙만)
- Baker-Wurgler 2006 = "high vs low" 이분법, ±1σ/±2σ 명시 X

**핵심 발견**: 단순 |VCI| 절댓값보다 **mispricing_z = (fact_z - sentiment_z)** 가 사이클 국면 노이즈 회피에 우월 (Baker-Wurgler 계열 정합).

**조치**: 🟢 **즉시 박음** — `_compute_vci` 에 `mispricing_z + mispricing_signal` 추가
- mispricing_z = base_vci / 15 (z-score)
- signal: extreme_undervalued (≥+2σ) / mild_undervalued (≥+1σ) / fair_value / mild_overvalued / extreme_overvalued

---

### A-3. 등급 75-60-45-30 (STRONG_BUY/BUY/WATCH/CAUTION/AVOID)

**Verdict**: ⚠️ **정합하지만 AVOID 폭 30p 과도 (보수 편향) → 25 권장**

**Perplexity 핵심**:
- I/B/E/S 학계 표준 = 서수 매핑 (Strong Buy=1...Strong Sell=5)
- 자연 quintile (80/60/40/20) vs Brain 현행 (75/60/45/30):

| 등급 | NQ 폭 | Brain 폭 | 차이 |
|---|---|---|---|
| STRONG_BUY | 20p | 25p | +5p (확대) |
| BUY | 20p | 15p | -5p |
| WATCH | 20p | 15p | -5p |
| CAUTION | 20p | 15p | -5p |
| **AVOID** | 20p | **30p** | **+10p** (NQ × 1.5) |

**I/B/E/S 실증 분포 (2010-2020 Nature 연구)**:
- Strong Buy 27.5% / Buy 20.3% / **Hold 41.0%** / Sell 3.8% / Strong Sell 1.3%
- → Sell-bias 회피 (애널리스트), Hold 과대 밀집

**핵심 발견**: AVOID 폭 30p 는 보수 편향. STRONG_BUY 확대 (+5p) 보다 AVOID 확대 (+10p) 가 2배 큼. 한국 소형주 커버리지 사각지대 우려.

**분포 보정 추천안 (Perplexity)**:
| 등급 | 추천 임계 |
|---|---|
| STRONG_BUY | ≥72 |
| BUY | 55-72 |
| WATCH | 38-55 |
| CAUTION | 25-38 |
| AVOID | <25 |

**조치**: 🟢 **즉시 박음** — 보수적 적용 (Perplexity 25 권장 채택, 다른 임계 유지)
- CAUTION min_brain_score: **30 → 25** (AVOID 폭 30p → 25p 축소)
- 다른 등급 (STRONG_BUY 75 / BUY 60 / WATCH 45) 유지

---

## MED-B/C/D — 답 대기 중

(사용자 추가 Perplexity 호출 후속 결과 받는 대로 v0.3 박힘)

---

## 즉시 박힘 정리 (A-2 + A-3)

| | 변경 | 출처 |
|---|---|---|
| **A-2** | `_compute_vci` 에 mispricing_z + mispricing_signal 추가 | Baker-Wurgler 2006 / AAII ±1σ/±2σ |
| **A-3** | `verity_constitution.json` CAUTION 30 → **25** | I/B/E/S Nature 2024 + Perplexity 분포 보정 |

## 큐잉 (A-1)

- **regime 동적 fact:sentiment 가중치** (5/30 due, claude p2)
  - KOSPI 7:3 / KOSDAQ 6:4 분기
  - VIX↑/외인↓/USD/KRW↑ regime → 8:2 자동 방어
  - Andrew Lo AMH 원칙 정합

## 출처

- A-1: `velog.io/Fama-French` / `probability.nl/SentimentFactors` / `pulse.mk.co` / `academic.oup.com/rfs`
- A-2: `greenbackd.com/AAII` / `pages.stern.nyu.edu/wurgler` / `acfr.aut.ac.nz/Han-Investor-Sentiment`
- A-3: `nature.com/articles/s41599-023-02527-8` / `anderson.ucla.edu/trueman_ratings`
