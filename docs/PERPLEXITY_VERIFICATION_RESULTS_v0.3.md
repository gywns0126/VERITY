# PERPLEXITY VERIFICATION RESULTS v0.3

검증: 2026-05-16 (사용자 Perplexity MED-B 후속 호출, v0.2 후속)
연관: `docs/PERPLEXITY_VERIFICATION_BACKLOG_v0.1.md` MED-B
이전: `docs/PERPLEXITY_VERIFICATION_RESULTS_v0.2.md` (MED-A)

---

## MED-B. Pershing Square Activist 진입 4 임계

### Verdict: 4 임계 중 1.5개만 부분 적합 ❌

Pershing Square가 **공개 정량 임계를 명시한 적이 없음**. 17 사례 (McD/Wendy's/Target/JCP/Chipotle/Hilton/Lowe's/ADP/Air Products/Burger King 등) 역산 결과 우리 임계 대부분 부적합.

### B-1. PBR < 1.5 → ❌ **부적합**

**Perplexity 사례 분포**:
| 사례 | 진입 시 PBR |
|---|---|
| McDonald's 2005 | 3.5-5× |
| Wendy's 2005 | 1.2-1.8× |
| Target 2007 | 2.0-2.5× |
| JCPenney 2010 | 0.6-0.8× (실패) |
| Chipotle 2016 | **7-9×** |
| Hilton 2016 | 4-6× |
| Lowe's 2018 | 6-8× |
| Air Products 2024 | 3-4× |

**핵심**: 0.6× ~ 9× 극히 넓은 분포. PS 진입 = "PBR 절댓값"이 아닌 **자산 재평가 gap** (브랜드/프랜차이즈 자산이 장부가 미반영).

### B-2. EV/EBITDA < 8 → ❌ **부적합**

| 사례 | 진입 EV/EBITDA |
|---|---|
| McDonald's 2005 | 8-10× |
| Wendy's 2008 | 7-9× |
| Burger King 2012 | 8-10× |
| ADP 2017 | **18-20×** |
| Chipotle 2016 | 15-25× |
| Hilton 2016 | 11-13× |
| Lowe's 2018 | 9-11× |
| Air Products 2024 | 12-15× |

**핵심**: 평균 10-14×, ADP 18×, Chipotle 25×. 진입 시 < 8 은 Wendy's/JCP 정도. PS 기준 = **정상화 EBITDA 기준 할인폭** (재구조화 후 도달 가능한 정상 EBITDA 대비 현 EV/EBITDA gap).

### B-3. ROE < 8% + GPM > 30% → ⚠️ **부분 적합**

**Perplexity 핵심**: Pershing Square 실질 분석법 = "잠재 ROE vs 실현 ROE gap"

| 사례 | 진입 시 ROE | 잠재 ROE | gap |
|---|---|---|---|
| McDonald's | 12% | 25-30% | **+15-18%p** |
| Wendy's | 5-8% | 15-20% | +10-12%p |
| ADP 2017 | 18% | 30%+ | +12%p |
| Lowe's 2018 | 28% | 45%+ | +17%p |
| JCPenney | 4% | 12% | +8%p (실패) |

**핵심 기준**: 절대 ROE 임계가 아닌 **peer median 대비 gap ≥ 10%p**. GPM > 30% 는 해자 확인 보조 필터.

### B-4. 시총 KR 1000억 / US $500M → ⚠️ **부분 적합**

**Perplexity 분포**:
| Activist | 평균 타깃 시총 |
|---|---|
| **Pershing Square** | $5-30B+ (메가캡) |
| Elliott Management | $3-20B |
| Carl Icahn | ~$2.5B 평균 |
| Starboard Value | ~$3.9B 평균 |
| 일반 activist | $100M-$500M 가장 빈번 |

**한국 활동주의**:
| 사례 | 타깃 | 시총 |
|---|---|---|
| KCGI | 한진칼 | 1.6조 |
| Align Partners | 은행주 7사 | 5조-30조 |
| Align Partners | SM엔터테인먼트 | 1.5-2조 |

**핵심**: PS는 메가캡 $5B+ 선호. KR Align Partners 평균 5000억-2조. **US $500M / KR 1000억은 일반 activist 하한이지 PS 패턴 아님**.

---

## v2 재설계 (즉시 박힘)

### `detect_ackman_activist_target` v2 (PS 패턴 정합)

```python
# 1. 메가캡 게이트 (필요조건) — US $5B+ / KR 5000억+
# 2. peer 대비 ROE gap ≥ 10%p (핵심 — Pershing 잠재 vs 실현 gap)
#    + 절대 ROE 게이트 제거
# 3. GPM > 30% = 해자 확인 필터 (보조)
# 4. 부채비율 < 200% (PS 진입 부담 적음 — 유지)
# 5. PBR/EV-EBITDA 단순 임계 제거 → peer median 대비 -20% 할인폭 (보조)
# 6. SEC 13F Pershing Square holding = 강한 확정 신호 (+25)
```

### 검증 결과 (실 portfolio 25 종목)
- US 4 종목: `sec_financials.market_cap` 미수집 → "평가 불가" (별 데이터 결함)
- KR 4 종목 (클래시스/JYP/파마리서치/에스엠): 메가캡 게이트 통과 + 부채 균형, 모두 score ~60-65 (peer ROE gap 데이터 부족으로 약함)
- 이전 v1 에서 NAVER 발화했던 거 (PBR 1.00) → v2 에서는 메가캡+부채만으로 score 60 (peer gap 데이터 보강 후 더 엄격)

### 정량 적용 변화
| 임계 | v1 (2026-05-16 오전) | v2 (Perplexity 검증 후) |
|---|---|---|
| PBR | < 1.5 (필수) | peer median 대비 -20% (보조) |
| EV/EBITDA | < 8 (필수) | (제거) |
| ROE | < 8% + GPM > 30% | peer median 대비 gap ≥ 10%p (핵심) |
| 시총 | KR 1000억 / US $500M | **KR 5000억 / US $5B (메가캡 게이트)** |
| GPM > 30% | (조합) | 단독 해자 확인 (보조) |
| 부채 < 200% | 유지 | 유지 |
| Pershing 13F | +25 | 유지 |

---

## 후속 큐잉

- **US 데이터 결함**: `sec_financials.market_cap` 다수 미수집 → ackman v2 평가 불가
  → 별 audit 큐 (p3 향후)
- **sector propagation 결함**: peer ROE/PBR 계산 불가 (sector=None 다수)
  → 이미 알려진 결함 (multi_bagger category_leader 와 동일)

---

## 출처

- 17 PS 사례 분석: `valley.town/space/bhj5674` / `10xebitda.com/Pershing-Square-McDonalds-Presentation` / `levelheadedinvesting.com`
- 미국 활동주의 분포: `corpgov.law.harvard.edu/2019/the-road-ahead-for-shareholder-activism`
- 한국 활동주의: `mk.co.kr/news/business/8581876` (KCGI) / `mk.co.kr/en/stock/10919712` (Align)
- Wendy's 2008 deck: `10xebitda.com/Pershing-Square-Wendys-Presentation-May-2008.pdf`

---

## MED-C/D — 답 대기 중

(사용자 추가 Perplexity 호출 결과 받는 대로 v0.4 박힘)
