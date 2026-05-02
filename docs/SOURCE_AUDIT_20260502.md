# 시스템 전체 출처 무결성 Audit — Step 1 P0

**작성**: 2026-05-02
**목적**: D2/D4 정정 외 silent drift 잔여 발견. 2027 Q1 Bagger Stage Manager 진입 전 baseline.
**참조 메모리**: `feedback_source_attribution_discipline` (audit 원칙)
**범위**: P0 4영역 (D2/D4 정정 완료 6항목은 Skip 1줄 확인)
**주의**: documentation only — 코드 / 운영 변경 X. 정정은 Step 2 (별도 confirm 후).

---

## 0. Skip 처리 (D2/D4 정정 완료, 1줄 확인)

| 영역 | 정정 메모리 | 상태 |
|---|---|---|
| 신호 1 (분기 매출 가속) | `project_multi_bagger_watch` line 19 | ✅ Mauboussin & Rappaport *Expectations Investing* (2001) 단일 출처 정정 완료 |
| 신호 2 (Operating leverage) | `project_multi_bagger_watch` line 20 | ✅ Mauboussin *More Than You Know* (firm-level) 단일 출처 정정 완료 |
| 신호 4 (Rogers S-curve) | `project_multi_bagger_watch` line 22 | ✅ Rogers *Diffusion of Innovations* (1962) 단일 출처 정정 완료 |
| 신호 5 (Lynch 매도 자제) | `project_multi_bagger_watch` line 23 | ✅ Lynch *One Up* (1989) 정성 원칙 + "180d/+50% 정량 임계는 자체 설정" 명시 완료 |
| Phase 1.1 ATR×2.5 표현 | `project_atr_dynamic_stop` line 23 | ✅ "월가 표준" → "단기/한국 자체 채택 변형" 정정 완료. **풀스캔 v2 정량 보강 대기 (§5)** |
| Phase 1.2 R-multiple 표현 | `project_r_multiple_exit` description | ✅ Raschke/LeBeau "표준" 표현 정정 완료 |

---

## 1. P0a — Brain v5 신호 3 (Lynch category killers)

### 데이터 소스 grep 결과
| 소스 | 결과 |
|---|---|
| 메모리 | `project_multi_bagger_watch.md` line 21: "Lynch *One Up on Wall Street* Ch.7 (category killers)" |
| 코드 (api/intelligence/) | `verity_brain.py:181, 191` — 키워드 매칭만 (`"점유율", "1위", "market share", "dominant"`). **정량 임계 부재** |
| 코드 주석 | category killers 출처 명시 X. `lynch_classifier.py:32` 의 Ch.7 인용은 **Cyclical 분류** (자동차/철강/화학/항공) — category killers 와 무관 |
| Config (constitution) | category_killer / market_share 임계 없음 |

### 4 점검
1. **출처 명시**: 메모리 ✅ / 코드 주석 ❌ / 정량 임계 X
2. **원전 진위**: Lynch *One Up* Ch.7 = "I've Got It, I've Got It—What Is It?" (6분류 = Slow/Stalwart/Fast/Cyclical/Turnaround/Asset Play). **category killers 용어는 별도 챕터 (Ch.10 *Earnings, Earnings, Earnings* 또는 Ch.13 부근 추정)** — Ch.7 인용 자체가 부정확
3. **시스템 적합성**: 신호 3 메모리 정의 = "산업 점유율 1위 + 직전 4분기 격차 확대" / 코드 구현 = 키워드 매칭 → **정의-구현 불일치**
4. **자체 결정 명시**: ❌

### Verdict: 🔴
- **사유**: (a) Ch.7 인용이 다른 챕터 가능성 + (b) 코드 구현이 메모리 정의와 단순 키워드 매칭으로 대체 + (c) "직전 4분기 격차 확대" 정량 룰 미구현
- **Step 2 정정**: 메모리에 (1) Ch.7 → 정확 챕터 재확인 또는 "Lynch 정성 영감 + 자체 정량 룰" 라벨링 (2) 코드 구현이 메모리 정의 미반영 = **별도 의제 큐잉** (운영 코드 수정 필요)

---

## 2. P0b — Brain v5 가중치 (fact 0.7 / sentiment 0.3)

### 데이터 소스 grep 결과
| 소스 | 결과 |
|---|---|
| 메모리 | `project_sprint_11_veteran_response.md` 의 `BRAIN_FACT_WEIGHT_OVERRIDE / BRAIN_SENTIMENT_WEIGHT_OVERRIDE` 언급 (베테랑 권고 0.85/0.15 점진 시험) — *현 default 0.7/0.3 의 출처 X* |
| 코드 default | `verity_brain.py:2389`: `default = bw.get("default", {"fact": 0.70, "sentiment": 0.30})` |
| 코드 주석 | `verity_brain.py:10-11` 헤더: `Fact Score (객관 + Moat + Graham + CANSLIM) × 0.7 + Sentiment Score (심리 + 동적 크립토 가중치) × 0.3` — 비율 명시되었으나 **출처 부재** |
| Config | `verity_constitution.json` `brain_weights`: `{}` (빈 dict) — 코드 default 사용 |
| 환경변수 override | `BRAIN_FACT_WEIGHT_OVERRIDE` / `BRAIN_SENTIMENT_WEIGHT_OVERRIDE` (베테랑 권고 0.85/0.15 시험용) |

### 4 점검
1. **출처 명시**: 헤더 docstring 에 출처 = "Hedge Fund Masters Report / Quant & Smart Money Trading Report / 30권 투자 고전" — **모호 (구체 챕터/페이지 없음)**. 7:3 비율 자체 출처 부재
2. **원전 진위**: 어느 학계/펀드 표준이 fact/sentiment 7:3 비율을 명시하는지 추적 불가
3. **시스템 적합성**: fact/sentiment split 자체는 multi-factor 모델 표준이나 7:3 가중치는 자의적 가능성 큼
4. **자체 결정 명시**: ❌ (헤더 docstring 이 마치 "30권 통합" 출처 인 것처럼 표기되어 있음)

### Verdict: ❓
- **사유**: 자체 결정 가능성 압도적 + 명시 X
- **Step 2 정정**: 메모리 신규 추가 = "brain_weights 7:3 = 자체 결정. OOS 백테스트 필요". 헤더 docstring 정정 의제 큐잉 (코드 수정 = 별도)
- **검증 의제 큐잉**: brain_weights_cv.py 결과 누적 후 7:3 vs 6:4 vs 8:2 정량 비교

---

## 3. P0c — Brain v5 등급 임계 (75/60/45/30)

### 데이터 소스 grep 결과
| 소스 | 결과 |
|---|---|
| 메모리 | 임계값 산출 근거 메모리 부재 |
| 코드 | `verity_brain.py:2252-2259` `_score_to_grade()` — `decision_tree.grades` lookup |
| Config | `verity_constitution.json` `decision_tree.grades`: `{STRONG_BUY: {min:75}, BUY:60, WATCH:45, CAUTION:30, AVOID:0}` |
| Config description | description / source / reference 키 없음 |
| 코드 주석 | `_score_to_grade` 정의에 출처 주석 X |

### 4 점검
1. **출처 명시**: ❌ (코드/메모리/문서/config 어디에도 출처 명시 X)
2. **원전 진위**: 75/60/45/30 등간격 15점 + 0~75 5단계 = **자체 설계 압도적**
3. **시스템 적합성**: 5단계 (vs 4단계/3단계) 선택 근거 X. 등간격 15점 산출 근거 X
4. **자체 결정 명시**: ❌ (constitution.json 에 description 키 자체 없음)

### Verdict: ❓
- **사유**: 자체 결정 + 명시 X (가장 명확한 ❓ 사례)
- **Step 2 정정**: constitution.json 에 description/source 필드 추가 의제 + 메모리 신규 = "등급 임계 75/60/45/30 = 자체 결정 (등간격 15점, 5단계)"
- **검증 의제 큐잉**: 운영 누적 데이터로 4단계/3단계 분포 비교 백테스트 (Phase 2-D 안정 후)

---

## 4. P0d — VCI / GS / Candle / 13F bonus

### 4-1. VCI bonus
| 소스 | 값 / 출처 |
|---|---|
| 코드 | `verity_brain.py:2443-2447` — `vci_bonus = 5 (positive) / -10 (negative)` |
| Config | `vci.thresholds`: `strong_contrarian_buy 25 / mild 15 / aligned 15 / mild_sell -15 / strong_sell -25` |
| 코드 주석 | 헤더 line 13 = "VCI v2.0 Bonus (Cohen 역발상 체크리스트)" |
| 출처 | "Cohen Checklist" (Steven Cohen / SAC Capital) — 모호 인용. 25/15/-15/-25 임계 자체 출처 X |

**Verdict**: ❓ — Cohen 영감 인정 + 25/15/-15/-25 임계는 자체 설정 (명시 필요). +5/-10 비대칭 보너스 (positive 약함, negative 강함) 비대칭 근거 X

### 4-2. GS bonus (group structure / 지분구조)
| 소스 | 값 / 출처 |
|---|---|
| 코드 | `verity_brain.py:2210` `_compute_group_structure_bonus` — top 주주 ≥30% → +2 등 |
| 코드 주석 | "지분구조(대주주 집중도, NAV 할인) → Brain Score 보너스" — **출처 부재** |
| 출처 | 한국 대주주 집중도 / NAV discount 보너스 = 자체 설계 |

**Verdict**: ❓ — 자체 설계 + 명시 X. NAV discount 컨셉 = 일반적 (Greenblatt *You Can Be a Stock Market Genius* 한국 적용 추정 가능, 단 직접 출처 X)

### 4-3. Candle bonus (Nison)
| 소스 | 값 / 출처 |
|---|---|
| 코드 주석 | 헤더 line 14 = "Candle Psychology Bonus (Nison Rule of Multiple Techniques)" |
| 출처 | Steve Nison *Japanese Candlestick Charting Techniques* — 명시 ✅ |
| 임계값 | `_compute_candle_psychology_score` 내부 산식 별도. 점수 범위 미점검 (시간 절약) |

**Verdict**: ⚠️ — Nison 출처 명시 ✅ / 임계값 산출 (개별 패턴별 가점) 출처 별도 검증 필요. 의제 큐잉

### 4-4. 13F bonus (institutional smart money)
| 소스 | 값 / 출처 |
|---|---|
| 코드 | `verity_brain.py:2459-2476` — `inst_bonus = 3 (iscore≥70) / 1 (iscore≥60), USD 종목만` |
| 코드 주석 | line 2458 = "V6: 13F 기관 스마트머니 보너스 (US 종목만, 분기 수집 후 존재 시)" |
| 출처 | SEC 13F (분기 institutional ownership) — 출처 명확. 단 *iscore ≥70 → +3, ≥60 → +1* 임계 산출 X |

**Verdict**: ⚠️ — SEC 13F 데이터 출처 명확 / 임계 70/60 산출 근거 X + **한국 종목 미적용 (코드 line 2460 `currency == "USD"`)**. 한국 적용성 자체 의제 큐잉

---

## 5. Phase 1.1 ATR×2.5 정량 verdict (풀스캔 v2 도착 후 보강 — 2026-05-02 16:46)

### 5-1. 데이터 출처
`data/analysis/5r_feasibility_full_v2_20260502.json` — universe 1,826 (hard_floor 적용 후) / 1,791 처리 / 715,732 weekly entry / R-cap=50

### 5-2. 시총 tier 별 stop_loss_rate

| tier | stop_loss_rate | 임계 (KRW) |
|---|---|---|
| **large** (≥ 1조) | **75.6%** | ≥ 1,000,000,000,000 |
| mid (≥ 1천억) | 77.8% | ≥ 100,000,000,000 |
| small (< 1천억) | 78.9% | < 100,000,000,000 |

### 5-3. 보조 지표
- ATR%/price 분포: p25=3.73% / p50=4.57% / p75=5.44% / p90=7.21%
- avg days to 5R hit: **80일 (~3.8개월)**
- universe 전체 stop_loss_rate: 77.12%
- 5R hit rate (entry 단위): 17.51%

### 5-4. Verdict: 🔴

**사유**: large tier stop_loss_rate **75.6%** > 60% — **ATR×2.5 한국 시장 부적합 강한 신호**.
- 모든 tier (large/mid/small) 가 75~79% 동일 수준 — tier 무관 ATR×2.5 가 한국 변동성 대비 tight
- avg ATR/price = 4.57% × 2.5 = 1R distance = 11.4% (한국 종목 일반 변동성에 너무 좁음)
- 1년 보유 윈도우에서 75%가 손절 hit = whipsaw 위험 정량 확인

### 5-5. 정정 액션 (Step 2 통합)

**메모리 2차 정정** (정정 이력 명시):
- `project_atr_dynamic_stop.md` 의 큐잉 의제 섹션 보강
- 형식: `[D2-1 1차 정정 2026-05-02]` (출처 표현) + `[Phase 1.3 v2 2차 정정 2026-05-02]` (정량 finding)
- 4-cell 백테스트 의제 = 큐잉 → **우선순위 P0** 격상
- 풀스캔 v2 결과 = 본 의제의 정량 baseline

**Step 2 진입 권고 항목 +1건**: P0e Phase 1.1 ATR×2.5 (🔴) — 메모리 2차 정정

### 5-6. 추가 finding (D5 보강)

**🟢 결정 23 텐버거 카운트 자체 검증됨**:
- 가정 114 (30년 Perplexity 인용) vs 실측 **128 (10년 풀스캔)** → Δ +12.3% / verdict=**consistent**
- 결정 23 의 114 인용 자체 무효화 안 됨 (미국 Bessembinder ≠ 한국, 단 한국 카운트는 정합 영역)
- 단 lookback 차이 (10년 < 30년) 인데 더 많이 나옴 = **survivorship bias 잔존** (5/12 별도 audit 의제)

**🟢 Bessembinder 패턴 한국 적용 확인**:
- median -4.36% (US -2%) 음수 일치 ✅
- skewness 10.89 ≥ 3 강한 우편향 ✅
- top 4% wealth share 51.35% (US 100%) — **한국은 분산형** (성공 종목 분포 더 넓음)
- 함의: 결정 23 Stage 5 (30x+) 표본은 한국에서도 매우 희귀 (20-bagger 44개 / 30-bagger 미산출)

---

## 6. 통계 — Step 1 P0 (풀스캔 v2 보강 후 갱신)

### Verdict 카운트

| Verdict | 항목 수 | 항목 |
|---|---|---|
| ✅ 통과 | **0** | (Skip 6건은 별도 — D2/D4 정정 완료) |
| ⚠️ 검증 의제 큐잉 | **2** | Candle bonus 임계 / 13F bonus 한국 적용성 |
| 🔴 정정 + 자체 결정 + 검증 | **2** | 신호 3 (Ch.7 인용 + 구현 불일치) / **Phase 1.1 ATR×2.5 (large stop_loss 75.6%)** |
| ❓ 자체 결정 라벨링 추가 | **4** | Brain 가중치 7:3 / 등급 임계 75-60-45-30 / VCI 임계 / GS bonus |
| 🟢 자체 검증 (보너스 finding) | **2** | 결정 23 텐버거 (consistent) / Bessembinder 한국 패턴 일치 |

**총 8 신규 audit + 6 Skip 확인 = 14 항목 (모두 verdict 산출 완료)**

### 즉시 정정 필요 (🔴 + ❓): **6건** (5 → 6)

1. 신호 3 출처/구현 정정 (P0a, 🔴) — `project_multi_bagger_watch` 라벨링 + 의제 큐잉
2. Brain 가중치 7:3 자체 결정 라벨링 (P0b, ❓)
3. 등급 임계 75/60/45/30 자체 결정 라벨링 (P0c, ❓)
4. VCI 임계 25/15/-15/-25 자체 결정 라벨링 (P0d-1, ❓)
5. GS bonus 자체 설계 라벨링 (P0d-2, ❓)
6. **Phase 1.1 ATR×2.5 메모리 2차 정정 (P0e, 🔴)** — `project_atr_dynamic_stop` 큐잉 의제 우선순위 P0 격상 + 정량 finding

### 검증 의제 큐잉 (⚠️ + 🔴): **5건** (4 → 5)

1. 신호 3 코드 구현 정정 (운영 코드 수정 — `verity_brain.py:181, 191`) (P0a)
2. Brain 가중치 OOS 백테스트 (brain_weights_cv 누적 후) (P0b)
3. Candle bonus 개별 패턴 임계 출처 검증 (P0d-3)
4. 13F bonus 한국 종목 적용성 검토 (P0d-4)
5. **Phase 1.1 4-cell 백테스트 우선순위 P0 격상** (P0e) — 5/17 verdict=ok 후 즉시 진행 의제

---

## 7. Step 2 (정정 단계) 진입 권고 항목 (풀스캔 v2 보강 후 갱신)

**메모리 정정 6건** (Step 2 즉시 진행 가능, 운영 코드 미터치):
1. P0a 신호 3 — `project_multi_bagger_watch` line 21: Ch.7 표시 정정 + 코드 구현 불일치 명시 + 의제 큐잉
2. P0b Brain 가중치 7:3 — 신규 메모리 또는 `project_sprint_11_veteran_response` 보강: "7:3 = 자체 결정, OOS 검증 의제"
3. P0c 등급 임계 — 신규 메모리: "75/60/45/30 등간격 15점 5단계 = 자체 결정"
4. P0d-1 VCI 임계 — 신규 메모리: "25/15/-15/-25 = Cohen 영감 + 자체 임계"
5. P0d-2 GS bonus — 신규 메모리: "지분구조 보너스 = 자체 설계 (NAV discount 컨셉 일반적, 직접 출처 X)"
6. **P0e Phase 1.1 ATR×2.5 — `project_atr_dynamic_stop` 큐잉 의제 섹션에 2차 정정 추가**:
   - `[D2-1 1차 정정 2026-05-02]` (출처 표현 정정)
   - `[Phase 1.3 v2 2차 정정 2026-05-02]` (정량 finding: large 75.6% / mid 77.8% / small 78.9%)
   - 4-cell 백테스트 의제 우선순위 P0 격상 (5/17 verdict=ok 후 즉시)

**의제 큐잉 5건** (action_queue 등록 권장):
1. 신호 3 코드 구현 정정 (운영 코드 수정 — `verity_brain.py:181, 191` 키워드 매칭 → 정량 룰)
2. Brain 가중치 7:3 OOS 백테스트 (`brain_weights_cv.py` 누적 후)
3. Candle bonus 개별 패턴 임계 출처 검증
4. 13F bonus 한국 종목 적용성 검토 (KRX 기관 데이터 가용성 점검)
5. **Phase 1.1 4-cell 백테스트 P0** — 5/17 verdict=ok 후 즉시 진행 (기존 의제 우선순위 P0 격상)

**🟢 보너스 finding 메모리 보강 권장** (정정 X, 검증 결과 누적):
- `project_multi_bagger_watch` 결정 23 검증 출처 섹션에 "한국 텐버거 카운트 = 5R 풀스캔 v2 128개 (10년) → 가정 114 (30년) 정합" 추가
- 단 survivorship bias 잔존 영향은 별도 분석 의제

---

## 8. P1 Audit (Step 3) — VAMS / Lynch 6분류 / Macro override

### 8-1. P1a — VAMS 프로필 임계

**대상**: `api/config.py:203-244` `VAMS_PROFILES` (aggressive / moderate / safe)

| 프로필 | stop | trail | hold_d | max_picks | per_stock | min_safety |
|---|---|---|---|---|---|---|
| aggressive | -8% | 5% | 21 | 10 | 3,000,000 | 45 |
| **moderate (default)** | -5% | 3% | 14 | 7 | 2,000,000 | 55 |
| safe | -3% | 2% | 10 | 3 | 1,500,000 | 70 |

**관련 상수**: `VAMS_INITIAL_CASH = 10,000,000` / `VAMS_COMMISSION_RATE = 0.00015` / `VAMS_SELL_TAX_KR_STOCK = 0.0018` / `VAMS_SPREAD_SLIPPAGE_BPS = 5`

#### 4 점검
1. **출처 명시**: 코드 주석 `# config.py의 VAMS_PROFILES 중 활성 프로필` 만. **임계 산출 근거 / 학계 인용 X**
2. **원전 진위**: 외부 출처 부재 — 자체 결정
3. **시스템 적합성**: 한국 retail 1인 1,000만원 자본 가정. 종목당 150~300만원 = 1~3% 비중 (분산형). 단 *자본 규모 변경 시 비례 변환 명시 X* — 1억 운영 시 종목당 비중 하락 (15~30만원 효과 없음), 비례 스케일링 수동
4. **자체 결정 명시**: ❌

#### Verdict: ❓
- **사유**: 자체 설계 + 명시 X (Brain 가중치와 동일 패턴)
- **정정**: `project_brain_v5_self_attribution` 의 패턴으로 **신규 메모리 또는 기존 보강** 으로 자체 결정 라벨링 + 자본 규모 비례 변환 가이드
- **검증 의제 큐잉**: VAMS 운영 데이터 누적 후 (3개월+) 프로필별 alpha 비교

---

### 8-2. P1b — Lynch 6분류 임계

**대상**: `api/intelligence/lynch_classifier.py:22-30` 한국 KOSPI/KOSDAQ 기준

| 임계 | 값 | 출처 (코드 주석 — 헤더 + 인라인) |
|---|---|---|
| FAST_GROWER 매출 ≥ | 15.0% | "한국 명목 GDP × 3 ≈ 10~11% 사이 운영 선택 — 6월 백테스트 시 12% 비교" |
| FAST_GROWER 시총 ≤ | 5조 | "소·중형 선호" (출처 X) |
| STALWART 매출 5~15% | 5.0~15.0 | (출처 X) |
| STALWART 시총 ≥ | 1조 | "대형" (출처 X) |
| ASSET_PLAY PBR ≤ | 0.8 | "한국 저PBR 구조 반영" (출처 X) |
| TURNAROUND 부채 ≤ | 300% | "생존 가능" (출처 X) |
| CYCLICAL 키워드 | 11개 | Lynch *One Up* Ch.7 인용 (자동차/철강/화학/항공) + 한국 추가 (반도체/조선/건설/해운/정유/비철금속/시멘트). **Ch.7 인용 — P0a 와 동일 의문 (Ch.7 = 6분류 챕터, Cyclical 직접 언급은 다른 챕터 가능)** |
| 우선순위 | Turnaround → Cyclical → Fast → Stalwart → Asset → Slow | "반등기 매출 급증 → Fast 오분류 방지" (자체 설계) |

**헤더 docstring 출처 명시 ✅ (P0c 등급 임계 대비 강함)**:
- "한국 GDP 2026 전망 1.9% 실질 / 명목 ~3.5% (KDI/IMF/OECD)" — 매크로 출처 명시
- "Lynch 원전 Fast Grower = 20~25% 절대값 (1989 미국 명목 GNP ≈ 7~8% → 약 3× GNP)" — Lynch 원전 인용 + *조정 산출식 명시*
- "GDP × 10 은 2차 요약본 오류" — Phase B 정정 흔적 (`feedback_master_rule_drift_audit` 와 정합)

#### 4 점검
1. **출처 명시**: 헤더 docstring ✅ (FAST_GROWER 만) / 다른 임계 (5조 / 1조 / 0.8 / 300%) 출처 ❌
2. **원전 진위**: Lynch 원전 = 20~25% 명시 정확 ✅. 단 "한국 명목 GDP × 3 ≈ 10~11% vs 절대값 20% 사이 운영 선택" = 자체 캘리브레이션 (정직 명시 ✅). CYCLICAL Ch.7 인용 = **P0a 와 동일 의문 — 별도 챕터 가능성**
3. **시스템 적합성**: 한국 시장 캘리브레이션 명시 ✅ + KDI/IMF/OECD 매크로 출처 ✅ — 가장 잘 된 사례
4. **자체 결정 명시**: 부분 ⚠ — Fast Grower 만 정직 명시 / 다른 임계 (5조 / 1조 / 0.8 / 300%) = ❓

#### Verdict: ⚠️ + ❓ (혼재)
- **FAST_GROWER 임계 = ✅** (헤더 docstring 우수)
- **다른 임계 (5조 / 1조 / 0.8 / 300%) = ❓** (자체 결정 명시 미흡)
- **CYCLICAL_KEYWORDS Ch.7 인용 = ⚠** (P0a 와 동일 의문, 챕터 재검증)

**정정**:
- `feedback_master_rule_drift_audit` 의 임계값 drift 정정 패턴 적용 → lynch_classifier 헤더에 다른 임계 (5조/1조/0.8/300%) 산출 근거 보강 의제 큐잉
- CYCLICAL 챕터 재검증 (P0a 와 동일 의제로 묶음)

---

### 8-3. P1c — Macro override 임계

**대상**: `api/intelligence/verity_brain.py:2011-` `detect_macro_override` + `api/config.py:123` + `verity_constitution.json` `panic_stages`

| 임계 | 값 | 출처 |
|---|---|---|
| MACRO_DGS10_DEFENSE_PCT | 4.5% | `api/config.py:123` env override 가능 / **출처 X** |
| VIX panic_stage | denial[20-30] / fear[30-40] / panic[40-80] / despair[25-40] | `verity_constitution.json` panic_stages — "Soros 반사성 + Cohen 1987" 영감 명시 ✅ |
| 부채비율 Hard Floor | > 300% | `verity_brain.py:1631` (출처 X — Sprint 11 의 `feedback_sector_aware_thresholds` 와 충돌 가능 — *금융주 D/E 200~1000% 정상* 임에도 Hard Floor 300% 적용 시 금융주 자동 탈락 위험) |
| PEG Hard Floor | > 3.0 | `verity_brain.py:1652` "배리티 브레인 투자 바이블 ⑥, Lynch 절대 매도" — 출처 ✅ (단 Lynch 원전 PEG > 2 / 본 시스템 3.0 = 자체 보수화 명시 X) |
| 유동비율 KR Hard Floor | < 50% | `verity_brain.py:1637` "배리티 브레인 투자 바이블 ⑥" — 출처 ✅ |
| FCF / 공매도 / 기타 | (코드 grep 결과 부분 발견) | 출처 분산 |

**헤더 출처 (verity_constitution.json macro_override.description)**:
"V4 — Soros 4단계 + Bridgewater 4분면 통합" — 영감 출처 ✅ / 정량 임계 직접 인용 X

#### 4 점검
1. **출처 명시**: panic_stages = "Soros + Cohen 1987" ✅ / DGS10 4.5% = ❌ / 부채 300% = ❌ (sector_aware 와 충돌 가능) / PEG 3.0 = ✅ ("브레인 바이블 ⑥") / 유동비율 50% = ✅
2. **원전 진위**:
   - Soros *Alchemy of Finance* 반사성 4단계 = 정성 원칙 (정량 vix_range 직접 인용 X — 자체 캘리브레이션)
   - Cohen 1987 = SAC Capital 역발상 — vix_range 직접 인용 X
   - PEG 3.0 — Lynch 원전 PEG > 2 / 본 시스템 3.0 = 자체 보수화 (명시 필요)
3. **시스템 적합성**:
   - DGS10 = 미국 10년 국채 → 한국 시장 영향 channel 명시 X (간접 — 글로벌 valuation 압력)
   - **부채비율 300% Hard Floor + sector_aware (금융주 D/E 정상 200~1000%) 충돌**: 우선순위/면제 룰 명시 X = 🔴 잠재 회귀 위험
4. **자체 결정 명시**: 부분 — panic_stages / PEG / 유동비율 ✅ / DGS10 / 부채 300% ❌

#### Verdict: 🔴 + ❓ (혼재 + 회귀 위험)
- **DGS10 4.5% = ❓** (자체 결정 명시 X)
- **부채 300% Hard Floor + sector_aware 충돌 = 🔴** (sector_aware 가 Hard Floor 우회 면제 명시되었는지 코드 검증 필요 — 미명시 시 금융주 자동 탈락 회귀 위험 — 별도 의제로 큐잉)
- **PEG 3.0 = ❓** (Lynch 원전 2.0 vs 본 시스템 3.0 보수화 근거 명시 필요)
- **panic_stages vix_range = ✅** (Soros + Cohen 영감 + 자체 캘리브레이션 명시 정합)

**정정 + 검증 의제**:
- `project_brain_v5_self_attribution` 에 P1c 매크로 임계 영역 추가 (DGS10 / 부채 / PEG)
- **부채 300% Hard Floor ↔ sector_aware 면제 룰 검증 의제 = P0 우선순위** (회귀 위험)

---

### 8-4. P1 통계

| Verdict | 카운트 | 항목 |
|---|---|---|
| ✅ 통과 | **2** | Lynch FAST_GROWER 임계 / panic_stages vix_range |
| ⚠️ 검증 의제 큐잉 | **1** | Lynch CYCLICAL_KEYWORDS Ch.7 인용 (P0a 와 묶음) |
| 🔴 정정 + 회귀 위험 | **1** | 부채 300% Hard Floor ↔ sector_aware 충돌 |
| ❓ 자체 결정 라벨링 | **5** | VAMS 프로필 / Lynch 임계 (5조/1조/0.8/300%) / DGS10 4.5% / PEG 3.0 보수화 / VAMS 자본 규모 비례 변환 |

**총 9 항목 (P1) — Step 1 P0 14 항목 + P1 9 항목 = 23 항목**

---

## 9. 통합 통계 (P0 + P1, 2026-05-02 최종)

| Verdict | P0 | P1 | 총 |
|---|---|---|---|
| ✅ Skip 정정 완료 | 6 | - | 6 |
| ✅ 통과 | 0 | 2 | **2** |
| 🟢 보너스 검증 | 2 | 0 | **2** |
| ⚠️ 의제 큐잉 | 2 | 1 | **3** |
| 🔴 정정 + 의제 | 2 | 1 | **3** |
| ❓ 라벨링 | 4 | 5 | **9** |

**즉시 정정 (🔴 + ❓)**: 12건 (P0 6 + P1 6)
**검증 의제 큐잉 (⚠️ + 🔴)**: 6건 (P0 5 + P1 1)

---

## 10. 진행 상태

- [x] Step 1 P0 audit + Step 2 정정 (메모리 6 + 의제 8) 완료
- [x] Step 3 P1 audit + 보강 정정 진행
- [ ] 통합 작업 3건 (PRIORITIZATION / MEMORY_CHANGE / DECISION_LOG)
- [ ] 최종 보고

---

## 변경 추적

| 날짜 | 변경 |
|---|---|
| 2026-05-02 (1차) | 초기 작성 (Step 1 P0) — Phase 1.1 v2 보강 대기 placeholder |
| 2026-05-02 (2차) | 풀스캔 v2 도착 → §5 정량 verdict 🔴 + §6 통계 갱신 + §7 항목 5→6/4→5 + 🟢 보너스 finding 추가 |
| 2026-05-02 (3차) | Step 3 P1 audit (VAMS / Lynch / Macro) 추가. 9 항목 신규 verdict + 통합 통계 §9 |

---

## 변경 추적

| 날짜 | 변경 |
|---|---|
| 2026-05-02 (1차) | 초기 작성 (Step 1 P0) — Phase 1.1 v2 보강 대기 placeholder |
| 2026-05-02 (2차) | 풀스캔 v2 도착 → §5 정량 verdict 🔴 + §6 통계 갱신 + §7 항목 5→6/4→5 + 🟢 보너스 finding 추가 |
