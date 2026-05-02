# 운영 검증 진단 — 2026-05-02 22:30 KST

**작성**: 2026-05-02 22:30 KST (회귀 위험 의제 fa3c2d1e 정량 영향 진단)
**참조**: `docs/REGRESSION_RISK_AUDIT_20260502.md` / 의제 ac9d1dc1 / fa3c2d1e / 신규 e8a17b3c
**원칙**: documentation only — 운영 코드 / 운영 데이터 / 메모리 미터치. Phase 0 ATR A/B 비교 baseline 보호

---

## 0. 진단 동기

`docs/REGRESSION_RISK_AUDIT_20260502.md` 의 의제 ac9d1dc1 검증 결과 (verity_brain.py:1631 sector 면제 X) → 정량 영향 진단 필요. 운영 portfolio.json 기준 금융주 도달도 측정.

---

## 1. 1차 진단 (sector 키워드 매칭)

```python
# 명령
financial = [r for r in recs if any(k in (r.get('sector') or '')
              for k in ['금융', '은행', '보험', '증권'])]

# 결과
Total recommendations: 51
Financial sector: 0
```

**해석 미완**: Financial sector 0건 = (a) 회귀 위험 발현 / (b) sector 매칭 실패 (data null) / (c) 우연. 분리 필요.

---

## 2. 2차 진단 (4단계 통합)

### 2-1. Top-level 키 구조 (75 keys)

`portfolio.json` top-level 에 `universe` / `brain_result` 키 부재. `verity_brain` = 2 keys (`macro_override`, `market_brain`) — recs 의 `verity_brain` 필드와 별개 영역.

→ universe / brain 추적은 다른 채널 (예: kis_market / sectors / observability) 통해야 함. **1차 진단의 universe 0/6 결과는 데이터 구조 가정 오류**.

### 2-2. brain_evolution_log

13 items 진입 (T1-06 commit prefix 추적 정상 가동) — 별개 정상 신호.

### 2-3. 한국 대표 금융주 6개 — recs 도달도 + 상세

| ticker | 종목 | recs 진입 | brain_score | grade | red_flags 키 |
|---|---|---|---|---|---|
| 105560 | KB금융 | ✅ | **52** | **AVOID** 🔴 | `auto_avoid` `downgrade` `auto_avoid_detail` `downgrade_detail` `has_critical` `downgrade_count` |
| 055550 | 신한지주 | ✅ | 55 | CAUTION ⚪ | (동일 키 발현) |
| 086790 | 하나금융지주 | ✅ | 55 | CAUTION ⚪ | (동일 키 발현) |
| 316140 | 우리금융 | ❌ | — | — | portfolio 자체 미진입 |
| 139130 | DGB금융 | ❌ | — | — | portfolio 자체 미진입 |
| 029780 | 삼성카드 | ❌ | — | — | portfolio 자체 미진입 |

**recs 키 (sector 부재 확인)**:
```
['ticker', 'ticker_yf', 'name', 'market', 'currency', 'price', 'volume',
 'trading_value', 'market_cap', 'high_52w', 'drop_from_high_pct', 'per',
 'pbr', 'eps', 'div_yield', 'debt_ratio', 'operating_margin',
 'profit_margin', 'revenue_growth', 'roe', ...]
```
→ `sector` / `category` 둘 다 None (51/51 모두).

### 2-4. 우리/DGB/삼성카드 missing 사유

deep search 결과 portfolio.json 전체에서 not found. 코어 화이트리스트 (85종목) 미포함 + Phase 2-A Day 0 비활성 (`UNIVERSE_RAMP_UP_STAGE="0"`) 정합. **회귀 위험과 무관** — Phase 2-A 활성 (5/17+) 후 universe 진입 가능.

---

## 3. Verdict (3 finding 분리)

### Finding 1: 🔴 회귀 위험 **부분 발현 확정** (KB금융 AVOID)

**증거**: KB금융 (105560) brain_score=52 / **grade=AVOID** / red_flags 에 `auto_avoid` 키 발현.

**해석**: verity_brain.py:1631 `if kis_debt > 300: auto_avoid_d.append(...)` 룰이 KB금융 D/E ~300%+ 에 발현 → AVOID 강제 → 추천 BUY/STRONG_BUY 영역 진입 자동 차단.

**범위**: 신한·하나는 grade=CAUTION (45-59 영역) 으로 BUY 영역 미달 — 본 진단으로는 *Hard Floor 직접 발현 여부* 미확정 (CAUTION 자체는 BUY 외 영역). KB금융 1건 = 회귀 위험의 *최소 보장 발현*.

**의제**: fa3c2d1e 우선순위 P0+ 격상 합리화. Phase 0 verdict (5/17+) 후 즉시 정정 sprint 진입.

### Finding 2: 🔴 sector 필드 propagation 결함 (51/51 NULL)

**증거**: recs 51/51 의 sector + category 필드 모두 None.

**해석**: stock_filter / multi_factor / 추천 dict 구성 단계에서 sector 정보 누락. 즉 fa3c2d1e 정정 sprint 가 sector_thresholds 헬퍼를 도입해도 *입력 sector 가 None* → 헬퍼 호출 분기가 default (일반 임계 300%) 로 fallback → 정정 효과 0.

**선행 의존성**: e8a17b3c (sector propagation 정정) 가 fa3c2d1e 보다 *먼저* 진행되어야 함. 그렇지 않으면 fa3c2d1e 의 코드 변경이 silent no-op.

**의제**: e8a17b3c **신규 등록** P0+ (fa3c2d1e 선행).

### Finding 3: ⚪ 우리/DGB/삼성카드 — 회귀 위험과 무관

코어 화이트리스트 미포함. Phase 2-A Day 0 비활성 정합. T1-25 정합 동작 — 회귀 위험과 무관, 별개 의제 X.

---

## 4. 신규 의제 e8a17b3c

| 항목 | 내용 |
|---|---|
| id | **e8a17b3c** (자동 생성) |
| title | sector 필드 propagation 결함 정정 |
| priority | **🔴 P0+** (fa3c2d1e 보다 우선 — silent no-op 방지) |
| depends_on | (선행 X) — 즉시 진행 가능 |
| blocks | fa3c2d1e (sector_thresholds 헬퍼 정정 sprint) |
| target | recs 51/51 의 sector / category 필드 None 정정 |
| 영향 | 운영 코드 — `api/analyzers/stock_filter.py` 또는 `api/analyzers/multi_factor.py` 또는 추천 dict 구성 단계 sector 누락 추적 + 정정 |
| due | Phase 0 verdict (5/17+) 후 진입 — 단일 변수 통제 (결정 21 정합) |

---

## 5. fa3c2d1e 의제 caveat 갱신

`docs/ACTION_QUEUE_PRIORITIZATION_20260502.md` + `docs/DECISION_LOG_MASTER.md` Part C 갱신 완료:
- caveat: "sector 필드 NULL 51/51 — e8a17b3c 선행 의존성"
- 의존성: e8a17b3c 완료 후 fa3c2d1e 진입 (silent no-op 방지)

---

## 6. 다음 진단 시점

| 시점 | 진단 대상 |
|---|---|
| e8a17b3c 정정 후 D+1 | recs sector 필드 채워짐 검증 (51/51 → non-None 비율) |
| fa3c2d1e 정정 후 D+1 | KB금융 AVOID 해제 + 신한·하나 brain_score 재산출 + recs sector 분포 (financial 추천 ≥ 1) |
| Phase 2-A Stage 2 (5/17+) 진입 후 D+1 | 우리/DGB/삼성카드 universe 진입 + brain_score |

---

## 7. 보호 대상 (변경 금지 baseline)

본 진단으로 *변경하지 않을* 항목 명시:
- ✅ Phase 0 ATR A/B 비교 baseline 보호 (5/3~5/16 운영 데이터)
- ✅ portfolio.json 운영 데이터 미터치
- ✅ verity_brain.py / stock_filter.py / multi_factor.py 운영 코드 미터치
- ✅ 메모리 정정 X (본 진단 = 기존 결정 추적 + 신규 의제 등록만)

---

## 8. git 변경 (documentation only)

| 파일 | 변경 |
|---|---|
| `docs/OPS_VERIFICATION_20260502.md` | 신규 |
| `docs/ACTION_QUEUE_PRIORITIZATION_20260502.md` | fa3c2d1e caveat + 신규 e8a17b3c + 변경 추적 |
| `docs/DECISION_LOG_MASTER.md` | Part C fa3c2d1e caveat + e8a17b3c + 운영 코드 sprint 매트릭스 + 변경 추적 |

운영 코드 / 운영 데이터 변경 X.

---

## 9. 3차 진단 — sector propagation root cause (2026-05-02 23:00 KST)

신규 의제 e8a17b3c 작업 범위 정밀화 위해 코드 grep + portfolio.json layer 추적 4단계 진단 추가 실행.

### 9-1. collector 단계 (root cause 확정)

| 파일 | sector 수집 코드 |
|---|---|
| `api/collectors/krx_openapi.py` | ❌ sector 키워드 부재 |
| `api/collectors/dart_fundamentals.py` | ❌ sector 키워드 부재 |
| `api/collectors/universe_builder.py` | ❌ sector 키워드 부재 |
| `api/collectors/stock_data.py:474` | ⚠️ `info.get("sector", "")` 만 — `_resolve_company_type` 함수 내부 한글 업종 라벨 변환에만 사용, dict 에 *저장 X* |
| `api/collectors/us_sector.py:101` | ✅ 존재 (US 전용) |
| `api/collectors/CommodityScout.py:163,315,328,371,377` | ✅ 부착 (commodity 전용) |

→ **KR universe sector 수집기 미구현** = 51/51 NULL 의 root cause 확정.

### 9-2. consumer 단계 (silent degraded mode)

코드는 sector 를 *사용* 하지만 입력 데이터가 비어있어 silent fallback 으로 운영:

| 파일 | 사용 패턴 |
|---|---|
| `api/intelligence/verity_brain.py:87, 1972, 2552` | `stock.get("sector", "") or ""` — Hard Floor 와 무관 영역 (sector 가공만) |
| `api/vams/engine.py:421, 430` | `(candidate_stock.get("sector") or "Unknown").strip()` — **VAMS sector_diversification 한도가 전 종목 "Unknown" 단일 분류로 작동** |
| `api/trade_planner.py:234` | `stock.get("sector") or stock.get("industry")` |
| `api/intelligence/daily_actions.py:61` | `rec.get("sector")` — TodayActionsCard 노출 |
| `api/intelligence/value_hunter.py:303` | `stock.get("sector")` — value hunt 출력 |
| `api/observability/trade_plan_meta_validation.py:159, 266` | meta-validation breakdown |

→ **부수 영향 발견 (Finding 추가)**:
- 🔴 **VAMS sector_diversification 한도 silent gap** (vams/engine.py:421, 430) — 전 종목이 "Unknown" 단일 sector 로 처리 → sector 분산 한도가 *작동하지 않음*. 별개 회귀 위험 신호 (factor_tilt 한도와 무관, 다른 의제)
- 🔴 daily_actions / TodayActionsCard 의 sector 노출도 None → UI 단계 사용자 혼란 가능

### 9-3. portfolio.json 어디에도 sector 데이터 없음

진단 2 결과 — 75 keys 중 sector 보유 list/dict **0건**. 수집 단계 부터 누락 → 모든 downstream silent fallback.

### 9-4. KR/US 분리 finding

- US: `us_sector.py` + `CommodityScout` sector 부착 코드 존재 (별도 채널)
- KR: 수집 채널 자체 부재

→ portfolio 51/51 모두 None 인 것 = 51건 모두 KR 종목 (코어 화이트리스트 85 KR 압도) 또는 KR/US 통합 단계 sector 누락. 별도 검증 의제.

---

## 10. e8a17b3c 작업 범위 정밀화 (3차 진단 후)

### 10-1. 1순위 — KR sector 수집기 신규

```python
# 권장 신규 파일: api/collectors/kr_sector.py
"""KRX 업종코드 → 한글 sector mapping
출처: KRX OpenAPI 업종지수 + KOSPI 21업종 / KOSDAQ 33업종 표준 분류
"""

KOSPI_SECTORS = {
    "010": "음식료품", "020": "섬유의복", ..., "060": "은행", "070": "보험",
    "080": "증권", ...,
}
KOSDAQ_SECTORS = {...}

def fetch_kr_sectors() -> dict[str, str]:
    """ticker → sector mapping. KRX OpenAPI 업종 별 종목 리스트 호출."""
    ...
```

### 10-2. 2순위 — universe_builder + dart_fundamentals 통합

```python
# api/collectors/universe_builder.py 정정
from api.collectors.kr_sector import fetch_kr_sectors
sector_map = fetch_kr_sectors()

for stock in universe:
    stock["sector"] = sector_map.get(stock["ticker"], "Unknown")
```

### 10-3. 3순위 — US/KR 통합 검증

`us_sector.py` 부착 결과가 main pipeline merge 단계에서 살아있는지 검증.

### 10-4. 단위 테스트 신규

```python
# tests/test_kr_sector_propagation.py
def test_kr_financial_sector():
    """KB금융 / 신한 / 하나 = '은행'"""
    sector_map = fetch_kr_sectors()
    assert sector_map.get("105560") == "은행"
    assert sector_map.get("055550") == "은행"

def test_recs_sector_filled():
    """recs 51/51 sector non-null"""
    portfolio = json.load(open("data/portfolio.json"))
    nulls = [r for r in portfolio["recommendations"] if not r.get("sector")]
    assert len(nulls) == 0, f"{len(nulls)}/{len(portfolio['recommendations'])} sector NULL"
```

---

## 11. 부수 발견 — VAMS sector_diversification silent gap

진단 2 의 부수 발견:

**vams/engine.py:421, 430** 의 sector 한도 코드가 sector NULL 입력으로 인해 *전 종목 "Unknown" 단일 분류* → sector 분산 한도가 사실상 작동하지 않음. T1-18 결함 4 (factor tilt 한도) 와 별개 회귀.

**별도 의제 권장 (선택)**:
- id: 별도 등록 권장 (예: VAMS-SECTOR-DIV-FALLBACK)
- title: VAMS sector_diversification silent gap 검증
- 의존성: e8a17b3c 완료 후 (sector 데이터 살아난 뒤 효과 측정)
- priority: P1 (회귀가 *완화 방향* — 한도 미작동 = 더 위험)

본 진단 범위에서는 부수 발견만 기록. 의제 등록은 사용자 결정 (총 의제 수 26 → 27).

---

## 변경 추적

| 일자 | 변경 |
|---|---|
| 2026-05-02 22:30 KST | 초기 작성 — 진단 4단계 결과 + 3 finding 분리 + 신규 의제 e8a17b3c |
| 2026-05-02 23:00 KST | §9 3차 진단 추가 — collector 단계 root cause 확정 (KR sector 수집기 미구현) + §10 e8a17b3c 작업 범위 정밀화 + §11 부수 발견 (VAMS sector_diversification silent gap) |

---

문서 끝.
