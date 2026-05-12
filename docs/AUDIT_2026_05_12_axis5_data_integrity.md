# Audit Sprint #5 — 데이터 무결성 sweep

**일자**: 2026-05-12
**범위**: 데이터 무결성 (staleness / schema drift / 메타 누락 / 수집 검증 / cross-source / 단위)
**산출**: 결함 list + fix 분류
**컨텍스트**: 5/17 ATR verdict + VAMS reset 전 fresh baseline. Axis #2 (운영 결함) 와 일부 중첩이지만 본 sweep는 산출 데이터 자체 품질 집중.

---

## 결함 요약 (8건)

| # | Risk | Axis | Path | 결함 | Fix 분류 |
|---|---|---|---|---|---|
| 1 | **HIGH** | 3 (메타) | `data/macro_snapshot.json` (macro 블록) | 15+ 필드 `source`/`as_of` 누락. `feedback_macro_timestamp_policy` 위반 | 5/17 queue |
| 2 | **HIGH** | 3 (메타) | `data/portfolio.json::macro` | 동일 macro 데이터 중복 저장에도 메타 누락 | 5/17 queue |
| 3 | **HIGH** | 3 (메타) | `data/daily_content/*/macro/meta.json` | `generated_at`만 있고 `collected_at` 누락 (3일치) | 5/17 queue |
| 4 | **HIGH** | 4 (로깅) | `api/collectors/macro_data.py:69,133,147,163,190,204,628` | 7개 bare `except Exception: pass`. logged=True stderr 없음 | 5/17 queue |
| 5 | **HIGH** | 4 (로깅) | `api/collectors/RSSScout.py` | feedparser 예외 logged 누락 | 5/17 queue |
| 6 | MED | 2 (schema) | `data/recommendations.dev.json` | 30 records 중 21개 unique schema (enrichment 분기) | 5/17 queue |
| 7 | MED | 5 (cross-source) | USD/KRW | price_pulse(19:45) vs macro_snapshot(17:30) 차이 1.39원 (2h15m stale) | 관찰 |
| 8 | LOW | 1 (staleness) | `data/recommendations.dev.json` | top-level `updated_at` 메타 누락 | 5/17 queue |

**총 8건** (HIGH 5, MED 2, LOW 1)

---

## 축별 상세

### Axis 1 — 데이터 staleness (LOW 1건)

`data/portfolio.json`, `data/price_pulse.json`, `data/macro_snapshot.json` 모두 당일 갱신 ✓

**[LOW] `data/recommendations.dev.json`**: top-level array 구조라 `updated_at` 메타 없음. 산출 시점 추적 불가.

---

### Axis 2 — Schema drift (MED 1건)

**[MED] `data/recommendations.dev.json`**: 30 records 중 21개 unique schema. enrichment 조건 분기 (DART/KIS/chain_scout/company_news 등 일부 record만 추가). 통합 전 정규화 필요 — optional marker (`_enriched_dart: false`) 명시 패턴.

**검사 OK**:
- `data/portfolio.json::vams.holdings` 통일 ✓
- `data/runs/*.json` 적재 schema 일관성 ✓ (3일 sample)

---

### Axis 3 — 메타 필드 누락 (HIGH 3건)

`feedback_macro_timestamp_policy` 메모리 룰: "매크로 지표는 collected_at + 각자 source/as_of 메타 의무"

**[HIGH] `data/macro_snapshot.json::macro`** — 15+ 매크로 필드 (usd_krw/usd_jpy/eur_usd/wti_oil/gold/silver/copper/vix/us_2y/sp500/nasdaq/dji/nikkei/sse/dax/yield_spread) 모두 `source`/`as_of` 없음. 단 3건(us_10y/hy_spread/breakeven_inflation_10y)만 source 있음 — drift.

**[HIGH] `data/portfolio.json::macro`** — 동일 매크로 데이터 중복 저장, 같은 메타 누락 패턴.

**[HIGH] `data/daily_content/*/macro/meta.json`** — `generated_at`(콘텐츠 생성)만 있고 `collected_at`(원본 수집) 누락. 3일치 (5/6, 5/8, 5/11).

영향: 리포트 노출 시 `macro_as_of_line` 헬퍼 호출 못 함 (`feedback_macro_timestamp_policy` 정합 불가).

---

### Axis 4 — 수집 검증 적재 누락 (HIGH 2건)

`feedback_data_collection_verification_mandatory` 정합 위반.

**[HIGH] `api/collectors/macro_data.py:69, 133, 147, 163, 190, 204, 628`**: 7개 `except Exception` 패턴, 모두 `pass` 또는 fallback return. stderr logged=True 표식 없음.
- `_get_usd_krw()`, `_get_fx()`, `_get_commodity()`, `_get_commodity_with_history()`, `_get_index_change()` 등.
- 비교 패턴: `api/collectors/policy_collector.py`는 `logger.error()` 적재 정합.

**[HIGH] `api/collectors/RSSScout.py`**: feedparser 호출 예외 처리만, logged 적재 X.

영향: 매크로 수집 silent skip 시 portfolio 안 macro 필드가 stale 또는 빈 값으로 표시되어도 운영 모니터링 못 잡음.

**Axis #2 와 차이**: 본 항목은 **정상 path에서 logged 표식**까지 명시 누락 (메모리 룰 정합). Axis #2는 `except: return None` 류 단순 silent skip만.

---

### Axis 5 — Cross-source 일관성 (MED 1건)

**[MED] USD/KRW 시간차**: `price_pulse.json` 1489.97 (19:45:56) vs `macro_snapshot.json` 1488.58 (17:30:39). 2h15m 차이, 1.39원(0.09%) 괴리. stale 범위(>1h) 내. macro_collect.yml 30분 cron 정합 확인 필요.

---

### Axis 6 — 단위 / fingerprint 결함 (결함 0)

오늘 KOSPI 의심 사례 → fact-check 결과 정상 (knowledge cutoff 오류). 본격 단위 검사:
- `api/cron/price_pulse.py:38` `_INDEX_SYMBOLS` 매핑 정합 ✓ (^KS11/^KQ11/^GSPC/^IXIC/^DJI/^VIX/KRW=X)
- KR 종목 단위 원 / US 종목 단위 달러 일관 ✓
- 지수 단위 통일 ✓

`feedback_knowledge_cutoff_verify_first` 메모리 신규 박힘 — 다음 sweep에서 cutoff 의심 재발 시 fact-check 우선.

---

## Fix 분류

### 즉시 (5/13~5/14)
없음. 모두 5/17 sprint queue (운영 영향은 누적, 즉시 위험 없음).

### 5/17 sprint queue (HIGH 5건)
- **3.1** `macro_data.py` 7 except에 `logger.warning()` + stderr logged=True
- **3.2** `RSSScout.py` 동일 패턴 적용
- **3.3** macro_snapshot 각 필드에 `source`/`as_of` 추가 (`policy_collector.py` 패턴 준용)
- **3.4** portfolio.json::macro 동일 (또는 단일 source 통합)
- **3.5** daily_content 메타 정정

### 5/17 sprint queue (MED/LOW)
- **6.1** recommendations.dev.json schema 정규화 (optional marker 패턴)
- **6.2** recommendations.dev 에 `updated_at` 추가
- **5.1** macro_collect cron 정합 검증 (USD/KRW 동기화)

### 관찰
- cross-source 시간차는 정기 cron 동기화로 자연 해결 가능. 운영 1주 후 재측정.

---

## 다음 갈래 (5/14)

Axis #1 시스템 정합성 — 메모리 룰 vs 코드 drift. Phase B (`feedback_master_rule_drift_audit`) 확장. 9권 KB 룰 / 임계값 / 신호식 출처 명시 audit.
