# 마스터 룰 Silent Drift Audit Phase B v0.1

**박힘**: 2026-05-17 새벽 (P2-4 sprint partial).

`feedback_master_rule_drift_audit` Phase B 정합. 9권 마스터 룰 이식 후 원전 vs 코드 silent drift 검증 의무.

## 1. 박는 목적

- 9권 (Lynch / Ackman / Hohn / Druckenmiller / TCI / Rokos / Nison 등) 의 룰 이식 시 임계값 / 분류 / 산출식이 원전에서 silent drift 발생할 위험 차단.
- **3층 매핑 구조** (메모리 정합):
  1. **원전 정의** (책·페이지·원문 인용, 시대·시장 컨텍스트 메타)
  2. **한국 캘리브레이션** (조정 산출식 + 근거)
  3. **분기 재검토** (시간 가변성 — 섹터 cyclicality / 매크로 변화 추적)

## 2. 9권 source list

| # | Source | 핵심 룰 영역 | VERITY 이식 위치 |
|---|---|---|---|
| 1 | Peter Lynch — *One Up On Wall Street* | 6 분류 (Fast / Slow / Cyclical / Stalwart / Asset Play / Turnaround) | `api/intelligence/lynch_classifier.py` (추정) |
| 2 | Peter Lynch — *Beating the Street* | PEG ≤ 1, 1/3 매도, multi-bagger | `verity_constitution.json` thresholds |
| 3 | Peter Lynch Playbook | 산업·소비자 본인 안다 영역 | rule 기반 검색 |
| 4 | Bill Ackman — *Great Investment* | 5 기준 (free cash flow / strong competitive position / limited downside / proven mgmt / low leverage) | `api/intelligence/ackman_detector.py` |
| 5 | (9781118505212) Behavioral Investing | bias 회피 | brain_score penalty |
| 6 | Chris Hohn — TCI (The Children's Investment) | activist + 4 stage frameworks | activist detector |
| 7 | Stanley Druckenmiller — 2020 essays | 매크로 cycle / liquidity / Fed | `api/intelligence/macro_override.py` |
| 8 | Rokos — RCM TCFD | risk management framework | risk filter |
| 9 | 2026 Annual IR templates | corporate reporting standards | reporting 정합 |

**메인 학습 자료**: `배리티 브레인 학습 도서/배리티_브레인_투자_바이블.pdf` (사용자 정리 통합본 13p)

## 3. 첫 룰 mapping example — Lynch Fast Grower

### 3.1 원전 정의
- **Source**: Peter Lynch, *One Up On Wall Street* (1989), Chapter 8 "Stalwarts, Slow Growers and Other Categories"
- **원문 인용**: "Fast Growers are aggressive new enterprises that grow at 20 to 25 percent a year. ... a small, aggressive new enterprise that grows at 20 to 25 percent a year"
- **시대 컨텍스트**: 1980s 미국 nominal GNP 성장률 7~8%
- **분류 기준**: 매출 또는 EPS 연간 20~25% 절대값

### 3.2 한국 캘리브레이션
- **VERITY 임계**: 15% (코드)
- **조정 근거**: 한국 명목 GDP × 3 ≈ 10~11% 와 원전 20% 사이 엄격 운영 선택
- **한국 시장 특수성**: 71% Slow Grower 오분류 → Lynch 통계 분류 (매출 CV > 0.15) 한국 KOSPI F1 0.67 부진
- **대체 시그널**: 영업이익률 std (한국 시클리컬 마진 진폭)

### 3.3 분기 재검토 트리거
- **다음 review**: 2026-06 백테스트 (메모리 정합)
- **시간 가변성**: 반도체가 mild → high beta 변모 (LSEG 2024). 정적 임계 위험
- **재검토 신호**: KOSPI 매출 분포 4분기 후 변화 ≥ ±2σ

### 3.4 코드 위치
- 추정: `api/intelligence/lynch_classifier.py` 또는 `verity_constitution.json` thresholds
- audit 검증: 위 임계 (15%) 가 코드와 일치하는지 별 grep 검증 + 코드 주석 원전 인용 박힘 의무

## 4. 두 번째 룰 mapping — Ackman activist target (v2)

### 4.1 원전 정의
- **Source**: Bill Ackman, *Great Investment* (Pershing Square Capital Mgmt)
- **5 기준**: (1) free cash flow strong (2) competitive position strong (3) limited downside (4) proven management (5) low leverage
- **시대 컨텍스트**: 미국 large-cap activist 1990s~. EV/EBITDA 5~10× target 평균
- **목적**: undervalued large-cap activist 진입 후보 detect

### 4.2 한국 캘리브레이션
- **VERITY 임계**: `veteran_triggers.detect_ackman_activist_target` v2 (Perplexity MED-B 재설계)
- **시총 컷**: US $5B / KR 5000억 (대형주 한정 — activist 가능 규모)
- **5 기준 정합**: PS 패턴 + capital allocation efficiency + free cash flow yield + competitive moat + management proven
- **코드 위치**: `api/intelligence/veteran_triggers.py:160~190` (detect_ackman_activist_target)

### 4.3 분기 재검토 트리거
- **한국 KOSPI 대형주 분포**: 미국 대비 더 좁음 (5000억 vs $5B = ~6배 작음). activist 후보 5% 가능
- **재검토 신호**: ASA / FactSet activist campaign DB 한국 사례 분기별 추적
- **다음 review**: 2026-06 백테스트 (Lynch 와 동시)

---

## 5. 세 번째 룰 mapping — Druckenmiller Conviction

### 5.1 원전 정의
- **Source**: Stanley Druckenmiller (Duquesne Capital), 2020 essays + 강연 transcript
- **원칙**: "확신 있을 때 집중 베팅" — 평소 분산, 확신 시 over-position
- **Conviction Score (CS) 공식**: 매크로 cycle + sector rotation + sentiment + technical 통합

### 5.2 한국 캘리브레이션
- **VERITY 임계**: `veteran_triggers.detect_druckenmiller_conviction`
- **CS 산출**: VERITY brain v5 매크로 override + sector rotation + momentum 통합
- **trigger 임계**: CS ≥ X (코드 grep 후 확정)

### 5.3 분기 재검토 트리거
- **시간 가변성**: 매크로 cycle 변화 (Fed pivot, 한국 금리 변동) 따라 CS 가중치 조정 필요
- **다음 review**: 2026-06 백테스트

---

## 6. 네 번째 룰 mapping — Hohn TCI Capital Allocation

### 6.1 원전 정의
- **Source**: Chris Hohn (TCI — The Children's Investment Fund)
- **원칙**: capital allocation 부실 = activist 진입 6번째 요소. "free cash flow 좋은데 buyback 없거나 acquisition 잘못된 회사"

### 6.2 한국 캘리브레이션
- **VERITY 임계**: `veteran_triggers.detect_hohn_capital_allocation_inefficiency`
- **trigger**: FCF yield + 자사주매입 부족 + 비효율 M&A history

### 6.3 분기 재검토 트리거
- **한국 시장 특수성**: 자사주매입 의무 (5% rule) — 미국 대비 capital allocation 룰 다름
- **다음 review**: 2026-06

---

## 7. 다섯 번째 룰 mapping — Nison Candle Psychology

### 7.1 원전 정의
- **Source**: Steve Nison, *Japanese Candlestick Charting Techniques* (1991), Ch 10 "Rule of Multiple Techniques"
- **원문 인용**: "Patterns are stronger when confirmed by other technical evidence — multiple techniques agreement"
- **시대 컨텍스트**: 1700s 일본 쌀 거래 → 1991 미국 도입. NYSE 주식 일봉 패턴
- **분류 기준**: bullish / bearish 캔들 패턴 카운트 × 확인 (volume / trend / support)

### 7.2 한국 캘리브레이션
- **VERITY 임계**: `verity_brain._compute_candle_psychology_score`
- **boost 범위**: -4 ~ +4 (timing 팩터 보정)
- **산식**: `candle_base = min(bullish_count × 1.5, 4)` (또는 bearish 음수)
- **한국 시장 특수성**: KOSPI/KOSDAQ 갭 시초가 빈번 (장 시작 5-min 룰 ≠ 일본 쌀 종가 룰) → 시초가 갭 제외 후 일봉 패턴 적용

### 7.3 분기 재검토 트리거
- **bonus 발동 빈도**: 운영 누적 0건 (project_brain_score_funnel_audit) — strict 룰 의심
- **다음 review**: 임계 완화 또는 산식 재검토 (2026-06 백테스트)
- **코드 위치**: api/intelligence/verity_brain.py:_compute_candle_psychology_score

---

## 8. 여섯 번째 룰 mapping — Rokos TCFD (큐잉)

### 8.1 원전 정의
- **Source**: Chris Rokos (RCM Capital), TCFD (Task Force on Climate-related Financial Disclosures) 기반 risk management framework
- **원문 인용**: 책 파일명 `RCM_TCFD` 박혀있음 (메모리 project_brain_kb_learning)
- **목적**: 매크로 + 기후 + 거시 위험 통합 risk framework

### 8.2 VERITY 적용 status — 미박힘 (큐잉)
- **코드 grep 결과**: api/ 내 `Rokos / TCFD` 직접 함수 X
- **흡수 가능 영역**: `api/intelligence/macro_override.py` 또는 risk filter
- **별 sprint**: 원전 정독 + 흡수 위치 결정 + 산식 박기 (~4h)
- **8월 진입 전 큐**: Phase 2 Module 2 (Stress) 와 결합 가능 — Rokos macro risk framework 가 stress scenarios 의 input source

### 8.3 분기 재검토 트리거
- **다음 review**: 별 sprint 진입 후 박기
- **우선순위**: P3 (Phase 2 Module 2 prep)

---

## 9. 진행 status

- ✅ Phase A (이식) 완료
- 🚧 **Phase B (audit) 진행 중** — 5 룰 mapping 박힘 (Lynch / Ackman / Druckenmiller / Hohn / Nison)
- ⏳ Rokos mapping — 별 sprint (Phase 2 Module 2 Stress 결합)
- ⏳ 6월 백테스트 동시 수행 — 5 룰 임계 분포 효과 측정

---

## 8. 진행 status

- ✅ Phase A (이식) 완료 (2026-04-28 ~ 5/16)
- 🚧 **Phase B (audit) 진행 중** — 본 docs 4 룰 mapping 박힘 (Lynch / Ackman / Druckenmiller / Hohn)
- ⏳ Rokos / Nison mapping — code grep 후 추가
- ⏳ 6월 백테스트 동시 수행 — 4 룰 임계 분포 효과 측정 + 한국 캘리브레이션 효과 입증

## 5. Drift 분류 (즉시 vs 백테스트)

| 분류 | 처리 |
|---|---|
| **사실 분류 drift** (예: 삼성=Cyclical vs Slow) | 백테스트 불필요. 즉시 수정. 5소스 cross-check (원전 + 3 LLM + 코드 audit) |
| **임계값 drift** (예: Fast 12% vs 15%) | 6월 백테스트. 분포 효과 측정 |
| **데이터 의존 drift** (예: Asset Play 다중 조건) | 데이터 확장 (DART/추가 source) 후 |

## 6. 다음 sprint (Phase B 완성)

| Step | 작업 | 시간 |
|---|---|---|
| 1 | Ackman 5 기준 mapping | 1h |
| 2 | Druckenmiller 매크로 cycle mapping | 1h |
| 3 | Hohn TCI activist framework mapping | 1h |
| 4 | Rokos TCFD risk framework mapping | 1h |
| 5 | Nison candle 패턴 mapping | 1h |
| 6 | 9 룰 × 코드 grep audit (실측 vs 본 docs) | 2h |
| 7 | 6월 백테스트 분포 측정 sprint | 별 sprint |

**총 ~7-8h Phase B 완성 sprint** (3-4 세션 분산 권장).

## 7. 분기 재검토 cron

- **6월 1일**, **9월 1일**, **12월 1일** 자동 audit cron 큐잉 (별 task)
- 자동 검증: 본 docs 의 3층 mapping vs 코드 실측 일치 확인
- 불일치 시 telegram alert → 수동 Phase B 재진입

## 8. Cross-link

- [[feedback_master_rule_drift_audit]] — 본 docs 원전 룰
- [[project_brain_kb_learning]] — Phase A 이식 status
- [[feedback_source_attribution_discipline]] — 출처 명시 의무
- [[project_multi_bagger_watch]] — Lynch 1/3 매도 룰 ref
- [[project_brain_v5_self_attribution]] — Brain v5 자체 결정 vs 9권 이식 구분
