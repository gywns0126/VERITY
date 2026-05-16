# PERPLEXITY VERIFICATION RESULTS v0.1

검증: 2026-05-16 (사용자 Perplexity HIGH 5건 일괄 호출)
연관: `docs/PERPLEXITY_VERIFICATION_BACKLOG_v0.1.md` Q1~Q5

---

## Q1. Wide Scan PRODUCTION 65 거래일 게이트

### Verdict: ⚠️ **부족 — 권장 120~252 거래일**

**Perplexity 발견**:
- 65 거래일 = **최소 통과 기준 하한** (Fast-alpha HFT형 전략용)
- Brain-style 펀더멘털 종합 점수 시스템에는 **부족**
  - 분기 실적 시즌 최소 2 cycle = 약 120-130 거래일
  - 권장: 252 거래일 (분기 4회 + 연간 이벤트 완전 커버)
- ICIR ≥ 0.5 통계적 유의 (t-stat ≥ 2) → 약 320 거래일 필요
- ICIR = 1.0 기준만 65~90 거래일 진입 가능

**기관 기준**:
- BARRA: 최소 36개월 월간 = 756 거래일 (팩터 모델 표준)
- AQR: OOS 강화 + 단일 regime 의존 회피
- WorldQuant: Sharpe ≥ 1.0 + 1~2년 백테스트

**한국 시장 특수성**: 외국인 수급 이벤트 + DART 공시 패턴이 서구와 다름 → 최소 2년 IS + 1년 OOS 권장.

### 조치
- **현재 65 거래일** → **권장 120 거래일 (절충)** 또는 252 거래일 (이상)
- 운영 영향 큼 (8월 말 → 11월 말로 6주 이동) — 사용자 결정 필요
- `memory project_phase_2b_wide_scan` + `api/config.py` 동시 정정 필요

### 출처
- ICIR 통계: `dl.acm.org` `sciencedirect.com`
- AQR OOS 원칙: `aqr.com/practice-papers`
- 실무 표준: `goatfundedtrader.com`

---

## Q2. Hohn (TCI) 환원율 < 1% 임계

### Verdict: ❌ **단독 임계 부적절 — 복합 조건 필요**

**Perplexity 사례 분포** (TCI 진입 시점 환원율 추정):

| 캠페인 | 연도 | 환원율 | 비고 |
|---|---|---|---|
| J-Power | 2007-08 | **~1% 이하** | TCI 임계 정합 (저환원 + 저ROE 1.86~3.05%) |
| ABN AMRO | 2006-07 | ~4% | 환원율 정상 |
| Coal India | 2014 | ~4-5% | 환원율 정상 |
| Aena | 2018 | ~2-3% | 중간 |
| Royal Mail | 2017 | ~4-5% | 환원율 정상 |
| Volkswagen | 2022 | ~5-7% | 환원율 높음 |

**핵심 발견**: TCI는 환원율 절댓값 보다 **구조적 조건 복합 진단**:
1. **ROE 저위** (vs WACC) — J-Power ROE 1.86~3.05% (동종 평균 미달)
2. **배당성향 < 업종 중위 × 0.5** (피어 대비 상대 payout)
3. **FCF yield > 5%** (현금 창출력 검증)
4. **교차주주 / 방어적 지배구조** (한국 = 지주사 할인 구조)
5. **잠재 ROE vs 실현 ROE gap** (활동주의 개선 여지)

**TCI 본인 발언**: 정량 임계 미공개. 정성 기준 = "독과점·고진입장벽 + 5종목 70-80% 집중"

### 조치 (큐잉 — 복합 재설계)
- 현재 `detect_hohn_capital_allocation_inefficiency` = 환원율 < 1% / < 3% 단일 임계
- → 복합 조건 detector 재설계:
  ```
  필요조건 (AND):
    · FCF yield > 5% (능력 있음)
    · 배당성향 < 업종 중위 × 0.5 (피어 비효율)
  보너스 OR:
    · ROE < WACC 추정치 (자본 파괴)
    · 교차주주 + 지주사 할인 (한국 특수)
  ```
- 1주 작업 분량 → user_action_queue 등록

### 출처
- TCI 캠페인 사례: `institutionalinvestor.com` `massivemoats.substack.com`
- J-Power 환원율: `jpower.co.jp/english/news_release/news080107-2.pdf`
- Hohn 정성 기준: `thetechnocratictyranny.com/PDFS/Harvard_Report_Hedge_fund_HBS.pdf`

---

## Q3. Druckenmiller VCI |val| < 15 conviction 정합

### Verdict: ✅ **정합 = 필요조건 (충분조건 X). CS 공식 + Catalyst 박기**

**Perplexity 핵심**: Druckenmiller 명시적 숫자 임계 X. 그러나 구조적 정량 추출 가능:

**1. 그의 정량 발언**:
| 출처 | 발언 | 내재 임계 |
|---|---|---|
| Sohn 2022 | "Sizing is 70-80% of the equation" | 포지션 결정 비중 ≥ 70% |
| Norges Bank 2024 | "NAV 25% 채권 숏 — 완전 확신 X" | 중간 확신 = 25% NAV |
| GBP 1992 | 첫 진입 20-25% → 소로스 후 200% 레버리지 | 일방적 확신 = 펀드 2배 |

**2. 3-레이어 동시 정렬 조건**:
- **펀더멘털** (경제 구조 분석)
- **기술적 확인** (가격 구조, 시장 반응)
- **촉매** (정책 결정자 발언, 중앙은행 행동)
- → 셋 중 하나 없으면 "Invest then Investigate" 모드 (작은 포지션만)

**3. Conviction Score (CS) 공식 권장**:
```
CS = 0.45 × Fact + 0.35 × (100 - |VCI|) + 0.20 × CatalystFlag

CS ≥ 75 → Full conviction (포트폴리오 15-25%)
55-75 → 중간 확신 (5-15%, NAV 25% 수준)
35-55 → Invest-then-Investigate (1-5% 감시 포지션)
< 35 → 관망
```

**4. Soros vs Druckenmiller**:
- Druckenmiller = 정합 (|VCI|<15) + 전환점 catalyst = 최대 사이즈
- Soros = contrarian (VCI≥25) + Fact≥60 = 최대 사이즈

### 조치 (✅ 즉시 박힘)
- `veteran_triggers.py:detect_druckenmiller_conviction`:
  - Brain ≥ 75 단일 게이트 → **CS 공식 (Fact + VCI 정합 + Catalyst) 종합**
  - 3-레이어 정렬 명시 (펀더멘털·기술·촉매)
  - CS 임계 4단계 (75/55/35) 매핑

### 출처
- Sohn/Norges Bank 인터뷰: `linkedin.com` `lilys.ai/ko/notes/378589`
- Invest then Investigate 원칙: `tradebytrade.substack.com`

---

## Q4. 카테고리 리더 5%p 매출 격차 임계 (P0a)

### Verdict: ⚠️ **5%p 부족. 한국 실증 = 10%p + 매출 배율 2×**

**Perplexity 핵심**:

**1. Lynch 원전 (P0a 정정 재확인)**:
- "category leader" 점유율 격차 정량 임계 **명시 X** (메모리 P0a 의제 정확)
- Lynch fast grower 실질 정량:
  - **EPS/이익 성장률 20~50% p.a.** (sweet spot 25%)
  - **PEG ≤ 1.0** (이상적), ≤ 0.5 = 극단적 저평가
  - 시총 > $1B 시 P/E < 40 추가 요건

**2. Mauboussin CAP**:
- 점유율 격차 X — **ROIC 스프레드 (ROIC - WACC) 지속 기간** 측정
- MICAP 역산: 현재 주가 → 내재 CAP 도출
- 대부분 기업 CAP 범위 = 5~20년

**3. 한국 실증 사례**:
| 사례 | 시기 | 점유율 격차 | 매출 배율 | Multi-bagger 발화 |
|---|---|---|---|---|
| NAVER vs Daum | 2010-15 | 압도 (70%+) | 2-3× | ✅ |
| SK하이닉스 vs Micron (DRAM) | 2017-18 | 5-8%p | - | ✅ |
| SK하이닉스 vs Micron (HBM) | 2025 | **14-17%p** | - | ✅ |
| LG엔솔 vs CATL | 2024 | 9-11%p | **2.8×** | ⚠️ (LG는 점유율 -11.3%p 열위) |

**4. 권장 임계 (한국 귀납)**:
- 점유율 격차 **≥ 10%p** (5%p 부족)
- 매출 배율 **≥ 2×** (절대 격차 검증)
- 동시 충족 → multi-bagger 발화점

### 조치 (✅ 즉시 박힘)
- `multi_bagger_signals.py:detect_category_leader`:
  - 5%p 임계 → **10%p (한국 실증)**
  - 매출 배율 2× 추가 게이트
  - is_top + is_widening AND 모두 충족 (기존) + 매출 배율 ≥ 2 추가

### 출처
- Lynch fast grower 임계: `en.globes.co.il` `svencarlin.com`
- Mauboussin CAP: `pages.stern.nyu.edu/~adamodar/pdfiles/eqnotes/cap.pdf`
- 한국 사례: `v.daum.net` `opinionnews.co.kr` `g-enews.com`

---

## Q5. ATR × 2.5 + R-multiple 50/30/20%

### Verdict: ✅ **ATR × 2.5 균형점 검증. period 21 + 트레일링 단계 조임 권장**

**Perplexity 핵심**:

**1. ATR multiplier 원전**:
| 출처 | 권장 배수 | 근거 |
|---|---|---|
| Wilder 1978 | 변동성 측정 (배수 미특정) | ATR 원전 |
| Chuck LeBeau Chandelier | **3.0x** (period=22) | 추세추종 트레일 |
| Van Tharp | **2.0-3.0x** | 1R 정의 |
| Mark Minervini SEPA | **1.5-2.5x** (일간) | VCP 초기 tight |
| 실무 컨센서스 | **2.5-3.5x** | Chandelier 실전 |

**2. KOSPI/KOSDAQ 1년 보유 권장**:
- KOSDAQ 소형주 ATR = 미국 1.4-1.8× (변동성 높음)
- **2.5x = 1년 균형점 (KOSPI 대형 + KOSDAQ 중소형)** ✅
- 2.0x = KOSDAQ 노이즈 청산 위험
- 3.0x = MDD 관리 우선
- **ATR period 14 → 21 권장** (1년 보유 단기 노이즈 필터)

**3. R-multiple 50/30/20% 배분**:
- ✅ **검증 정합** — Linda Raschke "Split right down the middle"
- Van Tharp R-multiple 분포 최적화 ✓
- +1R 50% 청산 = 손익분기 확보 → 시스템 기댓값 안정화
- +2R 30% 청산 = 우측 꼬리 실현
- +트레일 20% = "홈런 타율" 비선형 기여

**4. 트레일링 ATR 단계 조임** (현 미구현):
```
진입 ~ +1R: ATR × 2.5 (초기 유지)
+1R: 본전 보호 (스톱 → 진입가)
+2R: 최고가 - ATR × 2.0
+3R: 최고가 - ATR × 1.5 (Chandelier 좁힘)
```

### 조치 (큐잉)
- ✅ ATR × 2.5 유지 (검증)
- ✅ R-multiple 50/30/20% 유지 (검증)
- 🟡 `ATR_MIN_PERIOD = 20` → `ATR_PERIOD = 21` 검토 (KOSDAQ 소형 noise filter)
- 🟡 트레일링 단계 조임 (ATR × 3 → 2 → 1.5) 구현 — `r_multiple_exit.py` 확장 큐잉
- 5/22 ATR 4-cell sweep 정식 실행 결과와 종합

### 출처
- Wilder/LeBeau/Tharp: `brunch.co.kr` `chartschool.stockcharts.com` `pnlledger.com`
- Linda Raschke: `tradersmastermind.com` `tradergav.com`
- 트레일링 ATR: `luxalgo.com` `vectoralpha.dev`

---

## 종합 정리

| Q | Verdict | 조치 |
|---|---|---|
| Q1 | ⚠️ 65 부족 → 120 권장 | 🟡 사용자 결정 (운영 영향 큼) |
| Q2 | ❌ 환원율 단독 부적절 | 🟡 큐잉 (복합 재설계 1주) |
| Q3 | ✅ 정합 = 필요조건, CS+Catalyst | 🟢 즉시 박음 |
| Q4 | ⚠️ 5%p 부족 → 10%p + 2× | 🟢 즉시 박음 |
| Q5 | ✅ 2.5x + 50/30/20 검증 | 🟡 트레일링 단계 조임 큐잉 |

### 즉시 박힘 (Q3 + Q4)
1. `detect_druckenmiller_conviction` — Brain 단일 게이트 → CS 공식 + Catalyst flag
2. `detect_category_leader` — 5%p → 10%p + 매출 배율 2×

### 큐잉 (3건)
- Q1 65 → 120 거래일 결정 (사용자, p1)
- Q2 Hohn 복합 재설계 (claude, p2, 5/30)
- Q5 트레일링 ATR 단계 조임 (claude, p2, 5/30)

### 출처 출판
- Lynch 원전 직접 인용 (Globes / SvenCarlin)
- Mauboussin Stern NYU PDF
- Hohn HBS 케이스 (Harvard Tech Tyranny PDF)
- Druckenmiller 인터뷰 종합 (LinkedIn / Lilys)
- ATR/R-multiple 학계 종합 (StockCharts / Tradersmastermind)
