# Audit Sprint #3 — 코드 품질 sweep

**일자**: 2026-05-12
**범위**: dead code / dangling ref / security / 에러 경로 / magic number drift
**결과**: 매우 깨끗. 실 결함 2건만.

---

## 결함 요약

| # | Risk | Axis | File:Line | Drift | Fix |
|---|---|---|---|---|---|
| 1 | MED | 4 (에러 경로) | `api/main.py:2193~2194` | `h["current_price"] / h["buy_price"]` 직접 인덱싱 (KeyError 잠재 — realtime mode) | 5/17 queue |
| 2 | LOW | 4 (에러 경로) | `api/intelligence/verity_brain.py:113` | `gpm > 40` — gpm 타입 보증 부재 (default value 없음) | 5/17 queue |

**총 2건** (MED 1, LOW 1)

---

## 검사 5축 결과

| Axis | 상태 |
|---|---|
| 1. Dead code | 검사함, 결함 0. `parallel_fetcher.py` 정상 가동 (Phase 2-A 신규). Star import 없음 |
| 2. Dangling reference | 검사함, 결함 0. ATR/r_multiple 마이그레이션 caller 정합 |
| 3. Security (OWASP) | 검사함, 결함 0. `brain_evolution.py:53` subprocess 인자 hardcoded list. env 처리 `.get()` 안전. XSS/SQLi 없음 |
| 4. 에러 경로 | **결함 2건** (위 표) |
| 5. Magic number drift | 검사함, 결함 0. FILTER 상수 (`KR_TOP_N=10`/`US_TOP_N=15`) 메모리 정합. `parallel_fetcher` 임계값 ValueError 차단 정합 |

---

## False positive (agent 보고 후 검증으로 정정)

Agent가 `brain_evolution.py:53` subprocess 를 HIGH로 보고했으나, caller trace 결과 hardcoded args 만 사용 → 실 위험 0. 본 docs에서 결함 list 제외.

---

## Fix 분류

### 5/17 sprint queue
- **MED 1**: `api/main.py:2193~2194` `.get()` + default 패턴으로 안전화
- **LOW 2**: `verity_brain.py:113` gpm float() 변환 보장 또는 default

### 권장
시스템 코드 품질은 42일차 단독 운영치고 매우 깨끗. dead code / dangling ref / security 모두 결함 0. 메모리 룰들이 코드 작성 단계에서 잘 흡수된 결과로 판단.

---

## 다음 갈래 (마지막)

Axis #4 + #6 — 컴포넌트 overlap + Frontend/UX (펜타그램 일관성).
