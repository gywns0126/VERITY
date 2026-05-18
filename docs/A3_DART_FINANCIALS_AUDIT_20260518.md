# A3 DART Financials Audit — 2026-05-18

**Purpose** — `BRAIN_SCORE_AUDIT_20260518.md` §6 root cause #1 ("data fallback dominance") 의 `dart_financials 0/25` (KR 10 100% fallback) 정밀 진단. A3 = `COMPONENT_FALLBACK_AUDIT_20260518.md` §3 audit doc 권장 fix #3. 코드 변경 X, PM 결정 의제 큐잉만.

**Scope** — N=25 portfolio.json (5/15 18:32 KST universe scan, 5/16 13:01 last brain). KR=10 / US=15.

**결론 (선요약)** — `dart_financials` 입력 path **3종 동시 결함**:
1. main.py:2705 STEP 5.7 DartScout 호출 fail (5/16 토요일 full run 에서도 0/10 = audit doc baseline)
2. `data/dart_fundamentals_kr.json` (dart_batch 주 1회 산출, 1867 종목, 5/18 01:06 KST mtime) **10/10 매칭** but **필드 mismatch** (verity_brain.py:102 요구 `income_statement.gross_profit_margin / revenue_growth_yoy / cashflow.free_cashflow` ↔ 산출물 `per/pbr/roe/debt_ratio/op_margin`)
3. `kis_financial_ratio` 7/10 KR fallback path (verity_brain.py:113 `if kfr.get("source") == "kis":`) 가 dart 출처 비채택 (3/10 KR 부재 종목)

---

## §1 — main.py STEP 5.7 DartScout 호출 진단 (가설)

### 코드 위치
- `main.py:2705` `if effective_mode == "full":` (weekend 제한 없음, 평일 full 도 시도)
- `main.py:2728~2759` DartScout `safe_collect(scout, ticker_yf, ...)` → `stock["dart_financials"]` attach
- `safe_collect` default `{}` + timeout 90s

### baseline 정량
- audit doc baseline = **5/16 토요일 13:01 last brain analysis** (= 평일 full + 주말 full 모두 통과한 시점)
- `dart_financials 0/10 KR` = STEP 5.7 호출 자체는 발동했지만 모든 KR 종목 fail
  - 가능 1: DART OpenAPI rate limit / timeout (90s × 10 = 15분, 단일 종목 critical_error 가능)
  - 가능 2: `safe_collect` 가 error / critical_error 반환 (line 2736 `if dart_data and not dart_data.get("error") and not dart_data.get("critical_error"):` 조건)
  - 가능 3: DART OpenAPI 인증 fail (DART_API_KEY env 부재 또는 만료)

### 정밀 trace 의제 (다음 sprint)
- `gh run view <last_full_run_id> --log` 로 `[5.7]` 출력 + `safe_collect` 결과 검증
- DART_API_KEY env 존재성 확인
- `safe_collect` error 종류 분포 (timeout / critical_error / 빈 결과 비율)

---

## §2 — dart_fundamentals_kr.json 매칭 + 필드 mismatch

### 정량
- `data/dart_fundamentals_kr.json` 산출물 (dart_batch.yml 매주 일요일 22:00 KST cron)
- 구조: `{collected_at, fundamentals, diagnostics, schema_version}`
- `fundamentals` = 1867 ticker6 → `{per, pbr, roe, debt_ratio, op_margin, report_date, source}` dict
- 5/18 01:06 KST mtime (5/17 일요일 22:00 cron 직후 commit)

### portfolio KR 10 종목 매칭
| ticker6 | name | per | pbr | roe | debt_ratio | op_margin |
|---|---|---|---|---|---|---|
| 214150 | 클래시스 | None | None | None | None | None |
| 035900 | JYP Ent. | None | None | None | None | None |
| 214450 | 파마리서치 | None | None | None | None | None |
| 041510 | 에스엠 | None | None | None | None | None |
| 100840 | SNT에너지 | 10.1 | None | 25.15 | 0.89 | 23.16 |
| 035420 | NAVER | 13.53 | None | None | 5.32 | 16.71 |
| 200670 | 휴메딕스 | None | None | None | None | None |
| 175330 | JB금융지주 | 5.66 | None | 12.29 | None | 43.49 |
| 000240 | 한국앤컴퍼니 | 5.58 | None | 7.52 | 2.07 | 21.68 |
| 098070 | 한텍 | None | None | None | None | None |

**매칭 10/10**, **부분 채움 5/10** (100840 / 035420 / 175330 / 000240 + 1), **전체 None 5/10** (214150 / 035900 / 214450 / 041510 / 200670 / 098070).

### 필드 mismatch 분석

`verity_brain.py:101-108` (`_compute_moat_score` 의 Hohn 가격결정력 axis):
```python
dart = stock.get("dart_financials") or {}
inc = dart.get("income_statement") or {}
gpm = inc.get("gross_profit_margin")
rev_growth = inc.get("revenue_growth_yoy")
if gpm is None:
    kfr = stock.get("kis_financial_ratio") or {}
    if kfr.get("source") == "kis":
        gpm = kfr.get("gross_margin")
```

`verity_brain.py:1762-1764` (red_flag FCF):
```python
dart = stock.get("dart_financials", {})
cf = dart.get("cashflow", {})
fcf = cf.get("free_cashflow")
```

**요구 필드 vs 산출물 필드**:
| 요구 필드 | 산출물 필드 | 매핑 가능 |
|---|---|---|
| `dart_financials.income_statement.gross_profit_margin` | `fundamentals[t].op_margin` (영업이익률, 다름) | ❌ (계산 분모 다름) |
| `dart_financials.income_statement.revenue_growth_yoy` | 부재 | ❌ |
| `dart_financials.cashflow.free_cashflow` | 부재 | ❌ |

→ `dart_fundamentals_kr.json` 산출물의 ratio 필드 (per/pbr/roe/debt_ratio/op_margin) 는 verity_brain 직접 사용 X.

단 `kis_financial_ratio` source 가 `pbr/debt_ratio/gross_margin` 활용 (verity_brain.py:113 fallback path) — **dart 출처를 kis source 로 가장하면 fallback 활용 가능** (옵션 b).

---

## §3 — 3 옵션 비교 + PM 결정 의제

### 옵션 a — 진단 only (현 doc 박음, 코드 X)
- scope: docs/A3_DART_FINANCIALS_AUDIT_20260518.md 산출 (본 doc) + 다음 sprint 의제 큐잉
- 변경: 코드 0, RULE 7 적용 X
- 효과: brain_score 영향 0, audit cycle 영속화
- 시간: ~30분 (현 doc + 메모리 갱신)
- 추천 시점: 16:07 KST daily_full run trace 확보 후 옵션 b/c 결정

### 옵션 b — fallback path 산식 변경 (PM 승인 의무, RULE 7)
- scope: verity_brain.py:113 `if kfr.get("source") == "kis":` 조건 완화 + dart_fundamentals_kr 산출물을 stock['kis_financial_ratio'] 로 attach (또는 별 source 신설)
- 변경: 산식 변경 = RULE 7 적용 + PM 사전 승인 + 단일 변수 통제 + 곡선 맞추기 risk
- 효과: KR 5/10 부분 채움 종목 moat_quality fallback 활용 (op_margin → gross_margin 근사, 정확도 risk)
- 시간: ~1h (verity_brain.py + main.py attach + 테스트)
- risk: op_margin ≠ gross_margin 정확도 차이 (영업이익률 vs 매출총이익률)

### 옵션 c — 새 collector 신설 (별 sprint)
- scope: DART OpenAPI 직접 income_statement fetch (`fnlttSinglAcntAll.json` API) → `dart_financials.income_statement` + `cashflow` 박음
- 변경: 새 collector + main.py STEP 5.7 대체 또는 보강
- 효과: dart_financials 정공법 회복 (필드 mismatch 해소)
- 시간: ~2-3h (DART API 호출 + parser + cache + DART 20K/day 한도 검증)
- risk: 기존 STEP 5.7 DartScout 와 중복, 한도 부담

---

## §4 — Engineer 추천 진행 순서

1. **A1 commit 후 16:07 KST daily_full 실행 trace 수집** — DartScout safe_collect 결과 (error 종류 분포)
2. **trace 결과 기반 옵션 b/c 결정** — DartScout fail 종류가 transient (timeout 등) 면 retry/timeout 조정 sufficient (옵션 a 후속), permanent (auth fail 등) 면 옵션 c 필수
3. **dart_fundamentals_kr 활용** 은 보조 path 로 보존 — 1867 종목 wide_scan 단계 활용 (Phase 2-B step e)

---

## §5 — PM 결정 의제 (RULE 7 의무)

| # | scope | RULE 7 | 진입 권장 시점 |
|---|---|---|---|
| A3.a | 본 doc 산출 (코드 X) | X | 즉시 (이번 commit) |
| A3.b | fallback path 산식 변경 | **PM 승인 + 1회** | 16:07 후 trace 확보 후 |
| A3.c | 새 collector 신설 | X (data pipeline only) | 다음 sprint (별 2-3h) |

---

## §6 — Cross-link

- [[project_brain_score_funnel_audit]] — 본 doc = 4중 root cause #1 정밀 진단
- [[feedback_data_collection_verification_mandatory]] — 옵션 b/c 적용 시 try/finally + logged=True 의무
- [[project_dart_api_2026_constraints]] — 옵션 c 적용 시 20K/day 한도 검증
- [[feedback_workflow_yml_audit_mandatory]] — 옵션 c 가 cron 추가 시 6축 audit 의무
- `docs/BRAIN_SCORE_AUDIT_20260518.md` §3 (component breakdown)
- `docs/COMPONENT_FALLBACK_AUDIT_20260518.md` §3 (A3 권장 fix)

---

**End of A3 audit. 코드 변경 0. PM 결정 대기 — 16:07 trace 확보 후 옵션 b/c 결정.**
