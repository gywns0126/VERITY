# PERPLEXITY VERIFICATION RESULTS v0.4

검증: 2026-05-16 (사용자 Perplexity MED-C 후속 호출)
이전: v0.3 (MED-B) / v0.2 (MED-A) / v0.1 (HIGH 5)

---

## MED-C. Multi-bagger Mauboussin 2 임계

### C-1. 매출 성장 가속 ≥ 15% YoY → ✅ **검증 + 2분기 연속 보강**

**Perplexity 핵심**:
- Mauboussin *Expectations Investing* (2021 2판) — **Threshold Margin** 개념 (가치 중립이 되는 최소 마진 역산)
- *More Than You Know* — Base Rates 기반 지속 성장 가능 기업 비중 분석
- "기대치 대비 서프라이즈" 가 본질 (절대 임계 X)

**임계 비교**:
| 임계 | 근거 | 한계 |
|---|---|---|
| **15% YoY** | Base Rate 분석에서 15%+ 지속 성장 비중 급감 → 희소성 프리미엄 | 사이클 업종 노이즈 |
| 20% YoY | Lynch "Fast Growers" 기준선 + PEG 활용 | 소형주 한정 |
| 25% YoY | Minervini SEPA 매출 가속 신호 | 진입 시 이미 고평가 |

**한국 KOSPI/KOSDAQ 30년 텐배거 128종목 진입 시점 분포**:
| 매출 YoY 구간 | 텐배거 비중 | 멀티배거 발화 확률 |
|---|---|---|
| <10% | 22% | ~10% |
| 10-15% | 28% | ~18% |
| **15-20%** | **25%** | **~35%** |
| 20-25% | 14% | ~50% |
| >25% | 11% | ~62% |

**핵심**: 15-25% 구간이 텐배거 진입 50% 집중. ≥ 15% 임계 정합 ✅.

**보강 필수** (Perplexity 권장): **2분기 연속 가속 확인** (단일 분기 스파이크 = 기저효과 노이즈).

**조치 (즉시 박힘)**: `detect_revenue_acceleration` 보강
- 15% 임계 유지
- `quarterly_revenue` history 있으면 2Q 연속 가속 검증
  - 연속 가속 → +10 점 보너스
  - 단일 스파이크 → -5 페널티
- 데이터 미수집 시 "평가 불가" 명시 (silent skip 회피)

### C-2. 영업 레버리지 DOL > 3x → ⚠️ **2.5x 권장 + OPM 절대값 ≥ 5% 필터 필수**

**Perplexity 핵심**:
- Mauboussin DOL = % ΔEBIT / % ΔSales (Morgan Stanley 2006 리포트)
- Mauboussin 본인 = **DOL 절대 임계 미제시** (섹터 내 상대 비교 도구로 권장)

**임계별 발화 빈도**:
| DOL | 의미 | Multi-bagger 연관 |
|---|---|---|
| **2.5x** | 매출 10% → 이익 25% | **Threshold Margin 시작점** |
| 3.0x | 매출 10% → 이익 30% | 발화 빈도 최고, 서프라이즈 임계 |
| 4.0x+ | 슈퍼사이클 / 구조 전환 | 단기 폭발적, 지속성 낮음 |

**한국 슈퍼사이클 3대 사례**:
| 사례 | 매출 YoY | OP YoY | DOL | OPM | 판정 |
|---|---|---|---|---|---|
| **삼성전자 2017** | +18.7% | +83.6% | **4.5x** | (반도체 부문 OPM 30%+) | ✅ |
| **SK하이닉스 2017** | +75.0% | +315.2% | **4.2x** | **45.6%** | ✅ 교과서적 |
| **LGES 2021** | +42.1% | +220.8% | **5.3x** | **4.3%** | ⚠️ **기저효과 왜곡** |

**LGES 사례 교훈**: DOL 5.3x 였지만 OPM 절대값 4.3% (리콜 비용 제외) → 절대 이익 작은데 비율 큰 게 노이즈. 다음 해 (2022) DOL 1.3x 로 급락 = 레버리지 효과 소진.

**조치 (즉시 박힘)**: `detect_operating_leverage` 정정
- 임계 **3x → 2.5x** (Perplexity 권장)
- **OPM ≥ 5% 필터 (필수)** — 미달 시 `triggered = False` 강제
- OPM 5%+ 보너스 / 5% 미달 페널티

**검증 시뮬레이션**:
- LGES 2021 (DOL 5.2x + OPM 4.3%) → `triggered=False` ✅ (필터 작동)
- SK하이닉스 2017 (DOL 4.2x + OPM 45.6%) → `triggered=True` ✅
- 경계 (DOL 2.5 + OPM 5.0%) → `triggered=True` ✅

---

## 추가 발견 — Mauboussin 본질

**"성장 자체"가 아니라 "시장이 아직 가격에 반영하지 못한 성장"**.

매출 +25%라도 컨센서스 +30% 면 부정적 기대 수정 → 주가 하락.
매출 +15%도 컨센서스 +5% 였으면 강력한 주가 촉매.

**향후 큐잉** (Phase C): 컨센서스 추정치 (eps_estimates / consensus 데이터) 와 실적 비교 시그널 추가.

---

## 즉시 박힘 정리 (C-1 + C-2)

| | 변경 | 출처 |
|---|---|---|
| C-1 | `detect_revenue_acceleration` 2Q 연속 가속 보강 | Mauboussin Base Rate + 한국 30Y 텐배거 분포 |
| C-2 | `detect_operating_leverage` 3x → 2.5x + OPM ≥ 5% 필터 | Mauboussin Morgan Stanley 2006 + 한국 슈퍼사이클 3대 사례 |

## 큐잉

- **C-3 (신규)**: 컨센서스 vs 실적 서프라이즈 시그널 (Mauboussin 본질 — 기대치 대비) — 5/30 due
- 데이터 의존: `quarterly_revenue` history KR/US 양쪽 수집 (이미 큐잉됨)

---

## 출처

- C-1: `perpustakaan.usni.ac.id/Expectations-Investing` / `mjbaldbard.files.wordpress.com/Mauboussin-Base-Rates`
- C-2: `krishakansara.wordpress.com/Operating-Leverage-Mauboussin` /
       삼성전자 2017: `mk.co.kr/news/economy/8453359` /
       SK하이닉스 2017: `news.skhynix.co.kr/2018-business-performance` /
       LGES 2021: `inside.lgensol.com/2022/02`

---

## MED-D — 답 대기 중

VAMS 운영 3건 (통과 승률 55% / Factor 60% / Cohen ≥20) 답 받으면 v0.5 박힘.
