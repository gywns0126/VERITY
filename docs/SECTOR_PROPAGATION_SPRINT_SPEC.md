# Sector Propagation Sprint 명세 (의제 e8a17b3c + b9d4f72a + fa3c2d1e 통합)

**작성**: 2026-05-03 01:00 KST (Round 4 작업 7)
**의제 id**: e8a17b3c (P0+ root cause) + b9d4f72a (P1 검증) + fa3c2d1e (P0 Hard Floor 정정)
**예상 시간**: ~3시간 (5 step)
**참조**: `docs/SILENT_ERRORS_20260502.md` Error 2/3/4 / `docs/OPS_VERIFICATION_20260502.md` §9-12 / `docs/REGRESSION_RISK_AUDIT_20260502.md`

---

## 0. Sprint 목표

sector 데이터 layer 정정 (KR sector 수집기 신규) → VAMS sector_diversification 한도 작동 → Hard Floor sector 분기 정정 (금융주 회귀 차단). 3 의제 통합 sprint — 의존성 순서 고정.

---

## 1. 진입 조건 (선행 의존성)

### 1-1. 의무 (선행 의제)

| 우선 | 의제 | 이유 |
|---|---|---|
| **1** | Phase 0 verdict (5/17) 통과 | 단일 변수 통제 (결정 21) |
| **2** | **c5e8f9a2 hotfix sprint 완료** | VAMS sector_diversification 정정 효과 측정 baseline (holdings avg_price + total_value 정확) |

### 1-2. 선택 (보강용)

- Phase 1.1 4-cell 백테스트 결과 (Step 5 sector 분기 임계 산출 보강용)

### 1-3. 미정정 시 영향

c5e8f9a2 미정정 상태에서 본 sprint 진입 시:
- VAMS sector_diversification 정정 효과 *측정 불가* (holdings 분포 변화 baseline 부재)
- holdings 분포 변화 측정 불가 (avg_price=0 → return_pct 부정확)
- 검증 매트릭스 D+1 항목 작동 X (정정 전/후 비교 의미 X)

→ **c5e8f9a2 완료 의무**.

---

## 2. 작업 단계 (순차)

### Step 1 — KR sector 수집기 신규 (45분)

**파일**: `api/collectors/kr_sector.py` (신규)

**작업**:
- KOSPI 21업종 / KOSDAQ 33업종 mapping (KRX OpenAPI 업종지수 + 한국 표준 산업분류)
- DART 1순위 / KRX OpenAPI 2순위 / 자체 mapping fallback
- 캐시 24시간 (`data/cache/kr_sector_map.json`, sector 변경 거의 X)
- 단위 테스트 12 cases:
  - 금융주 (KB/신한/하나) = "은행"
  - 증권주 (미래에셋증권 037620) = "증권"
  - 보험주 (DB손보 005830) = "보험"
  - 자동차 (현대차 005380) = "자동차"
  - 반도체 (SK하이닉스 000660) = "반도체"
  - cache hit/miss
  - DART API 실패 시 KRX fallback
  - 모두 실패 시 자체 mapping fallback
  - 신규 ticker (mapping 부재) = "Unknown" + 알림
  - 캐시 24시간 만료 후 재 fetch
  - rate limit 가드
  - 한글 sector 라벨 표준화

### Step 2 — universe_builder + dart_fundamentals sector 부착 (30분)

**파일**:
- `api/collectors/universe_builder.py` 정정
- `api/collectors/dart_fundamentals.py` 정정

**작업**:
```python
# universe_builder.py 정정
from api.collectors.kr_sector import fetch_kr_sectors
sector_map = fetch_kr_sectors()

for stock in universe:
    stock["sector"] = sector_map.get(stock["ticker"], "Unknown")
```

backward compat: 기존 컬럼 보존 (sector 추가만, 다른 필드 변경 X).

**단위 테스트 8 cases**:
- universe build 후 sector 필드 non-null 비율 ≥ 95% (Unknown < 5%)
- 코어 화이트리스트 85 모두 sector 부착
- DART fundamentals 결과 sector 누락 시 KR sector 보강
- KR sector 수집 실패 시 graceful fallback (Unknown)

### Step 3 — stock_data._resolve_company_type 정정 (20분)

**파일**: `api/collectors/stock_data.py:474`

**작업**:
- yfinance `info.get("sector")` 를 dict 에 *저장* (US 종목)
- 기존 한글 라벨 변환 보존
- 단위 테스트 5 cases:
  - US 종목 sector 부착 (예: AAPL = "Technology")
  - KR 종목 sector 부착 (kr_sector 우선, yfinance fallback)
  - sector 한글 라벨 변환 정상
  - 빈 sector 처리 (Unknown)
  - industry fallback

### Step 4 — VAMS sector "Unknown" fallback 정정 (30분)

**파일**: `api/vams/engine.py:421, 430` (의제 b9d4f72a)

**작업**:
- sector NULL 시 "Unknown" → 종목 sector 의무 fetch (universe_builder 결과 사용)
- sector 한도 검증 활성 (현재 silent gap 정정)
- holdings sector 부착 영속화

**단위 테스트 10 cases**:
- 5종목 분산 시 sector 한도 trigger 발동 X
- 7종목 같은 sector 시 trigger 발동 ✅
- sector NULL holding 시 graceful (legacy 호환)
- sector 한도 35% 정확 산출
- new buy 시 한도 초과 시 차단
- 한도 초과 X 시 매수 통과
- factor_tilt 한도 (60%, T1-18) 와 독립 작동
- exit 시 sector 비중 재산출
- portfolio.json holdings sector 영속화 검증
- multiple sector 분포 정확 산출

### Step 5 — Hard Floor sector 분기 (의제 fa3c2d1e, 60분)

**파일**:
- `api/intelligence/verity_brain.py:1631` (auto_avoid 부채 300%)
- `verity_brain.py:1633` (downgrade 부채 200%)
- `lynch_classifier.py` TURNAROUND 부채 < 300%
- `api/utils/sector_thresholds.py` (신규 헬퍼)

**작업** (`docs/REGRESSION_RISK_AUDIT_20260502.md` §3 정합):

```python
# api/utils/sector_thresholds.py (신규)

FINANCIAL_SECTORS = {"financial", "bank", "insurance", "securities",
                     "은행", "보험", "증권", "금융"}
HEAVY_DEBT_SECTORS = {"construction", "aviation_shipping",
                      "건설", "항공", "해운"}

def get_debt_thresholds(sector: str) -> dict:
    """sector 별 부채비율 임계 (auto_avoid / downgrade).
    
    출처: feedback_sector_aware_thresholds 정책 + tests/test_dilution.py:215 정합.
    """
    s = (sector or "").lower()
    if any(f in s for f in FINANCIAL_SECTORS):
        return {"auto_avoid": 700, "downgrade": 500}
    if any(h in s for h in HEAVY_DEBT_SECTORS):
        return {"auto_avoid": 500, "downgrade": 350}
    return {"auto_avoid": 300, "downgrade": 200}  # 일반 (기존 동작 보존)
```

```python
# verity_brain.py:1631 정정
from api.utils.sector_thresholds import get_debt_thresholds
sector = stock.get("sector", "")
thresholds = get_debt_thresholds(sector)
if kis_debt > thresholds["auto_avoid"]:
    auto_avoid_d.append(_make_flag(
        f"부채비율 {kis_debt:.0f}% [{sector}] (KIS 기준, 임계 {thresholds['auto_avoid']}%)"
    ))
elif kis_debt > thresholds["downgrade"]:
    downgrade_d.append(_make_flag(
        f"고부채 {kis_debt:.0f}% [{sector}]"
    ))
```

**단위 테스트 15 cases** (`tests/test_brain_hard_floor_sector.py` 신규):
- 일반 제조업 D/E 350% → auto_avoid 발동 (기존 동작 보존)
- 일반 제조업 D/E 250% → downgrade 발동
- **금융주 D/E 350% → auto_avoid X** (회귀 차단 핵심 case)
- 금융주 D/E 750% → auto_avoid 발동 ✅
- 금융주 D/E 600% → downgrade 발동
- 건설 D/E 400% → downgrade 발동 (350% 임계)
- 건설 D/E 600% → auto_avoid 발동 (500% 임계)
- 항공/해운 D/E 동일 패턴
- sector NULL → 일반 임계 (기존 동작 보존)
- KB금융 (105560) 실측 D/E 350% case → AVOID 해제 검증
- 신한지주 (055550) 동일
- 하나금융지주 (086790) 동일
- TURNAROUND 부채 < 300% (lynch_classifier) sector 분기 동일
- sector_thresholds 헬퍼 단위 테스트 (FINANCIAL/HEAVY_DEBT/일반)
- thresholds 미적용 시 silent fallback (호환성)

---

## 3. 검증 매트릭스 (D+0 ~ D+30)

### 3-1. D+0 (즉시)

- [ ] Step 1 단위 테스트 12/12 통과
- [ ] Step 2 단위 테스트 8/8 통과
- [ ] Step 3 단위 테스트 5/5 통과
- [ ] Step 4 단위 테스트 10/10 통과
- [ ] Step 5 단위 테스트 15/15 통과
- [ ] **총 50/50 통과**

### 3-2. D+1 (운영 cron 결과)

- [ ] **D+0 baseline**: 정정 전 holdings sector 분포 = "Unknown" 100% (`holdings_utilization_baseline.jsonl` 5/2 entry)
- [ ] **D+1 비교**: 정정 후 holdings sector 분포 = 다양 (KB금융=은행 / 삼성전자=반도체 / 등)
- [ ] recs 51건 sector 필드 non-null 비율 ≥ 95% (e8a17b3c 정정 효과)
- [ ] KB금융 (105560) red_flags 변화 (auto_avoid 발현 X 검증) — fa3c2d1e 정정 효과
- [ ] 금융주 추천 0 → 5~10건 (sector 면제 적용 후)

### 3-3. D+7 (1주 운영)

- [ ] VAMS sector 한도 trigger 발동 횟수 측정 (정상 +20% 이내)
- [ ] 추천 list 의 sector 분포 안정 (HHI index < 0.3)
- [ ] holdings sector 다양화 시작 (Unknown 100% → < 30%)

### 3-4. D+30 (1개월 운영)

- [ ] portfolio sector 분산도 측정 (HHI index 안정)
- [ ] 운영 alpha 비교 (정정 전 30일 vs 정정 후 30일)
- [ ] 금융주 alpha 정량 측정 (회귀 차단 효과)

---

## 4. 롤백 조건

- sector 수집 실패율 > 30% (kr_sector.py 가동 후 1주)
- VAMS holdings 분산 한도 trigger 폭주 (정상 +20% 이내 임계 위반)
- 금융주 추천 갑작스런 0건 (Hard Floor 정정 효과 미발현 신호)
- 50 단위 테스트 중 1개라도 fail
- portfolio.json 산출 실패 (다음 cron)

**롤백 절차**:
1. `git revert <sprint-commits>` (5 step 모두)
2. `cp data/portfolio.json.pre_sector_sprint data/portfolio.json` (backup 보존 의무)
3. 별도 진단 의제 등록 (예: `e8a17b3c-fail` — Step 1~5 중 fail step 식별)

---

## 5. 운영 영향

**예상 (긍정)**:
- 추천 list 개편 (sector 분산 강제) — KOSPI 200 sector 분포 정합
- 금융주 추천 5~10건 진입 가능 (회귀 차단)
- VAMS sector 한도 정상 작동 → 단일 sector 베팅 차단
- daily_actions / TodayActionsCard sector 노출 정상화

**위험**:
- 일부 종목 sector 한도 초과로 신규 진입 불가 (T1-18 결함 4 정상 발현)
- 금융주 추천 급증 시 사용자 confirm 게이트 필요 (PM 검토 의무)
- KR sector 수집 API rate limit 가드 (DART 1만/일 한도)

**완화**:
- backup 보존 (`portfolio.json.pre_sector_sprint`)
- D+1 / D+7 / D+30 검증 매트릭스 단계별 ✅ 의무
- 5/17 진입 시 PM 1주 모니터링 의무 (sprint 진입 후 1주는 daily check)

---

## 6. 후속 의제 진입 (Step 4-3 D+30 완료 후)

| 후속 의제 | 의존성 해제 |
|---|---|
| 작업 8 (PHASE_1_1_RECONSIDERATION) sector 차등 분석 | sector 데이터 정상화 → 4-cell × sector 분해 가능 |
| capital_evolution_monitor Trigger 2 (시장 임팩트) | sector 분포 정확 → 시장 임팩트 sector 별 산출 |
| ESTATE landex 통합 (해당 시) | KR sector 표준 — ESTATE 부동산 sector 매핑 정합 |

---

## 7. 학습 사례 cross-ref

본 sprint = `feedback_sector_aware_thresholds` 정책의 *6주 후 운영 발현 정정* 사례.

- 정책 정립 (4/29 T1-08 마스터 룰 drift audit) → silent gap 발견 (5/2 SOURCE_AUDIT P1c) → 정량 진단 (5/2 OPS_VERIFICATION) → 본 sprint 정정 (5/17+)
- 메타 원칙: **정책 정립 후 *영역별 적용 검증* 의무** (dilute() 만 적용, Hard Floor + VAMS 미적용 = silent gap)

→ `feedback_source_attribution_discipline` 학습 사례 7번째 후보 (sprint 완료 후 추가 검토).

---

## 8. 변경 추적

| 일자 | 변경 |
|---|---|
| 2026-05-03 01:00 KST | 초기 작성 — 5 step + 50 단위 테스트 + D+0/D+1/D+7/D+30 검증 매트릭스 + 학습 사례 cross-ref |

---

문서 끝.
