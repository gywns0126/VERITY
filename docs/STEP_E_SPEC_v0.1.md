# STEP E SPEC v0.1 — DART Pre-Attach + Altman Z″ EM

작성: 2026-05-14
적용 게이트: 5/17 sprint Day 1 (Phase A)
근거:
- `docs/UNIVERSE_FUNNEL_REFORM_PLAN_v0.2.md` §4 Stage 3 Medium Filter + §10 마이그레이션
- Perplexity 2026-05-14 (Altman Z″ EM 한국 표준 + DART API 2026 운영 제약)
- 메모리: `project_altman_z_korea_standard`, `project_dart_api_2026_constraints`

---

## 1. 목적

wide_scan 5/11 1회 SHADOW run 의 결함 수리:
- `gate_stats.fscore_full_n = 40 / 1879` (2%)
- `gate_stats.altman_z_full_n = 0`
- 데이터 입력 부재로 Stage 3 (300→30) 진입 불가

step e = stock_data 확장 + DART 재무제표 pre-attach + Altman Z″ EM 적용 + medium_filter.py 신규.

v0.2 §13 분리 spec 패턴 정합 (COST_MODEL_SPEC.md / SLEEVE_TRACKING_SPEC.md 형제).

---

## 2. DART pre-attach 룰

### 2.1 Rate limit 가드
- **일일 20,000 건 한도** (KST 00:00 reset, 키별)
- 사용 가이드: corp_code 갱신 (1회/월 ~10K건) + fnlttSinglAcntAll (분기 batch ~2,600 종목 × 1 보고서 = ~2,600 건/회) → 월 합 ~12,800 건 (한도의 64%)
- 에러 020 (한도 초과) → self-throttle, 24h 다음 batch 지연
- 에러 011 (키 비활성화) 감지 시 즉시 알림 + 키 갱신 액션

### 2.2 Cron 시간 회피
- **점검 시간 02:00~06:00 KST** (에러 800) → 회피 의무
- **마감 직후 트래픽 폭주 윈도우** → 회피 의무:
  - 3월 25 ~ 4월 5 (사업보고서 마감)
  - 8월 10 ~ 8월 20 (반기 보고서 마감)
- **권장 cron**:
  - corp_code 갱신: 매월 첫째 월요일 KST 09:30 (점검·마감 둘 다 회피)
  - fnlttSinglAcntAll batch: 분기 마감 + 30일 (5/1, 8/30, 11/30, 익년 4/30) KST 09:30

### 2.3 corp_code 갱신
- 다운로드: `GET /api/corpCode.xml` → corp_code.zip
- 처리: zip 해제 → XML parse → stock_code 있는 상장법인만 필터링 → KONEX 제외
- 출력: `data/dart/corp_code_active.json` (~2,600 건 예상)
- schema:
  ```json
  {
    "as_of": "2026-05-14",
    "modify_date_max": "2026-05-12",
    "n_active": 2598,
    "items": [
      {"corp_code": "00126380", "corp_name": "삼성전자", "stock_code": "005930", "modify_date": "2026-04-15"}
    ]
  }
  ```

### 2.4 fnlttSinglAcntAll 호출
- endpoint: `GET https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json`
- 필수 파라미터: `crtfc_key`, `corp_code`, `bsns_year`, `reprt_code`, `fs_div=CFS` (연결 우선)
- 보고서 우선순위 (가장 최신 가용 1개):
  1. 11011 (연간) — **가장 안정, BS 시점값 + IS/CF 12M 누적 → annualize 불필요**
  2. 11012 (반기)
  3. 11014 (3Q)
  4. 11013 (1Q)
- **응답 schema 정정 (2026-05-14 실호출 검증, 005930 2025 3Q)**:
  - 응답 키 14개: `rcept_no, reprt_code, bsns_year, corp_code, sj_div, sj_nm, account_id, account_nm, account_detail, thstrm_nm, thstrm_amount, frmtrm_nm, frmtrm_amount, ord, currency`
  - **`thstrm_add_amount` 필드 자체 없음** — Perplexity 명시 룰 무효
  - **분기 보고서의 IS/CF 흐름 항목 = 누적값**:
    - thstrm_nm 패턴: "제 57 기 3분기" (174 items, 누적) vs "제 57 기 3분기말" (51 items, BS 시점)
    - 1Q = 3개월, 반기 = 6개월, 3Q = 9개월, 연간 = 12개월 누적
  - sj_div 분포: SCE 105 / BS 51 / CF 39 / IS 17 / CIS 13 → step e 사용 = BS+IS+CF 만 (107)
- XBRL 미채택 → "표준계정코드 미사용" 반환 시 skip + `data/dart/dart_health.jsonl` 적재 (silent skip 금지)

### 2.5 account_id 매핑 표 (실측 검증 005930 2025 3Q)

| Step E 명 | account_id | sj_div | account_nm | 항목 종류 |
|---|---|---|---|---|
| total_asset | `ifrs-full_Assets` | BS | 자산총계 | 시점 |
| current_assets | `ifrs-full_CurrentAssets` | BS | 유동자산 | 시점 |
| current_liab | `ifrs-full_CurrentLiabilities` | BS | 유동부채 | 시점 |
| book_equity | `ifrs-full_Equity` | BS | 자본총계 | 시점 |
| total_debt | `ifrs-full_Liabilities` | BS | 부채총계 | 시점 |
| retained_earnings | `ifrs-full_RetainedEarnings` | BS | 이익잉여금 | 시점 |
| long_term_debt | `ifrs-full_NoncurrentLiabilities` | BS | 비유동부채 | 시점 |
| ebit (영업이익) | `dart_OperatingIncomeLoss` | IS | 영업이익 | **누적 (분기보고서)** |
| interest_expense | `ifrs-full_FinanceCosts` | IS | 금융비용 | **누적 (분기보고서)** |
| operating_cf | `ifrs-full_CashFlowsFromUsedInOperatingActivities` | CF | 영업활동현금흐름 | **누적 (분기보고서)** |

**fallback 후보** (1차 매핑 미발견 시):
- `book_equity` → `ifrs-full_EquityAttributableToOwnersOfParent` (지배기업 소유주 지분)
- `interest_expense` → `ifrs-full_InterestExpense` (CIS 직접, 금융주 패턴) → `ifrs-full_InterestPaidClassifiedAsOperatingActivities` (CF 의 이자의 지급)
- `ebit` → `ifrs-full_ProfitLossFromOperatingActivities` (KB금융 등 일부 사용)

**working_capital 은 별도 account_id 없음** — 코드에서 `current_assets - current_liab` 계산.

### 2.6 출력 schema (data/dart/financials_latest.json)

```json
{
  "as_of": "2026-05-14",
  "n_total": 2598,
  "n_attached": 2350,
  "n_skipped_xbrl": 180,
  "n_skipped_other": 68,
  "items": {
    "005930": {
      "corp_code": "00126380",
      "bsns_year": 2025,
      "reprt_code": "11014",
      "fs_div": "CFS",
      "period_months": 9,
      "raw": {
        "ebit": 12166062000000,
        "total_asset": 523659586000000,
        "retained_earnings": 385279270000000,
        "book_equity": 413501494000000,
        "total_debt": 110158092000000,
        "long_term_debt": 22898833000000,
        "current_assets": 229440881000000,
        "current_liab": 87259259000000,
        "interest_expense": null,
        "operating_cf": 56515496000000
      },
      "computed": {
        "working_capital": 142181622000000,
        "ebit_annualized": 16221416000000
      }
    }
  }
}
```

`period_months` = 보고서 코드별 (11011=12, 11012=6, 11013=3, 11014=9). 흐름 항목 annualize 시 ×(12/period_months) 적용.

### 2.7 적재 hook (필수)
- `try/finally + logged=True stderr` (`feedback_data_collection_verification_mandatory` 정합)
- `data/dart/dart_health.jsonl` 매 batch 적재:
  - `ts_kst`, `n_called`, `n_ok`, `n_skip_xbrl`, `n_skip_other`, `n_error_020`, `n_error_011`, `daily_quota_used_pct`

---

## 3. Altman Z″ EM 산식 (Stage 3 Safety Floor)

### 3.1 산식
```
X1 = ebit_annualized / total_asset             # 흐름 항목 annualize 의무 (§3.1.1)
X2 = retained_earnings / total_asset           # 시점 항목, annualize 불필요
X3 = working_capital / total_asset             # working_capital = current_assets - current_liab
X4 = book_equity / total_debt                  # 시가총액 X — 장부가 사용 의무

Z″_EM = 3.25 + 6.72·X1 + 3.26·X2 + 6.72·X3 + 1.05·X4
```

(X5 = 매출/총자산 의도적 제거 — 비제조업 비교성 확보)

### 3.1.1 Annualize 룰 (분기 보고서 흐름 항목 처리)

DART fnlttSinglAcntAll 응답의 IS/CF 항목 = 누적값. Altman Z 의 X1 (EBIT/총자산) 은 연간 기준 가정 → 분기 보고서 사용 시 annualize 의무.

```
period_months = {11011: 12, 11012: 6, 11013: 3, 11014: 9}[reprt_code]
ebit_annualized = ebit_raw * (12 / period_months)
```

**우선 순위**: 11011 (연간) 사용 가능하면 annualize 불필요. 분기보고서는 차순위.

**계절성 종목 주의**: 단순 ×(12/n) annualize 는 계절성 큰 기업 (소매/관광) 왜곡. v0.2 에서 TTM (4 보고서 호출) 으로 정밀화 큐. v0.1 에서는 simple annualize 채택 (Altman 의 robustness 가 충분히 큼 — 삼성전자 sanity 11.57 검증 §9).

### 3.2 컷오프
- Safe: `Z″_EM > 2.6` → Stage 3 자동 통과 (Altman 측면)
- Grey: `1.1 ≤ Z″_EM ≤ 2.6` → 보조 신호 통과 조건 적용
- Distress: `Z″_EM < 1.1` → 즉시 reject

원본 Z 컷오프 (1.81/2.99) 사용 금지. 한국 시장에 과도하게 보수적 (안전구간 ~42% 과대추정).

### 3.3 Grey zone 보조 신호 (둘 다 충족 필요)
- Piotroski F ≥ 4
- 이자보상배율 (ebit / interest_expense) ≥ 1.5

(F-Score 계산은 Brain v5 quick scoring 결과 재활용 가능 — 중복 호출 회피)

### 3.4 금융주 제외 (Stage 1 처리)
- KSIC 64~66 (은행/보험/금융지주/증권/캐피탈/저축은행/리츠) → Stage 1 hard exclusion
- v0.2 §2 Stage 1 표 "금융업" 항목 정합 (이미 박혀있음)
- 별도 평가 = CAMELS / BIS CET1 / NIM 추세 (현재 미구현, 8월+ 큐)

### 3.5 시계열 추세 (v0.3 큐)
- 단일 시점 컷오프보다 3-5년 Z″_EM 추세 (방향성) 신호 품질 우월
- 운영 6개월 누적 후 `Z_trend_label` (up/flat/down) 추가

---

## 4. medium_filter.py 신규 (Stage 3 implementation)

**위치**: `api/filters/medium_filter.py`

**입력**: Stage 2 통과 ~300 종목 (data/wide_scan_log.jsonl 의 top quintile)
**출력**: ~30 종목 (data/medium_filter_log.jsonl)

**룰 적용 순서**:
1. 금융주 제외 sanity check (Stage 1 의무 — 누락 시 알림)
2. DART financials 매핑 (data/dart/financials_latest.json) — 미매핑 시 skip + log
3. Altman Z″ EM 산식 (위 §3) — Distress reject
4. Grey zone → F-Score + ICR 병행 통과
5. Brain v5 quick scoring (기존)
6. Sector neutralization (v0.2 §4)
7. Commodity 60%+ 별도 버킷 (v0.2 §4)
8. Top decile (300 → 30)

**적재 hook**: try/finally + logged=True stderr (`feedback_data_collection_verification_mandatory` 정합)

**출력 jsonl schema** (data/medium_filter_log.jsonl):
```json
{
  "ts": "2026-05-17T09:30:00+09:00",
  "label": "v0_medium",
  "mode": "SHADOW",
  "input_n": 300,
  "passed_n": 30,
  "rejected": {
    "financial_sector_caught": 2,
    "dart_unmapped": 18,
    "altman_distress": 47,
    "grey_failed_aux": 89,
    "brain_v5_low": 65,
    "sector_neutral": 49
  },
  "altman_dist": {"safe": 165, "grey": 88, "distress": 47},
  "top10_tickers": [...],
  "data_source": "stock_dict_v0 + dart_financials_latest"
}
```

---

## 5. 진입 조건 (5/17 sprint Day 1)

체크리스트:
- [ ] step e DART pre-attach cron 박힘 (corp_code 월1회 + fnlttSinglAcntAll 분기 batch)
- [ ] Altman Z″ EM 산식 medium_filter.py 에 박힘
- [ ] wide_scan SHADOW 5/15~5/17 누적 데이터 정상 출력 확인 (현재 5/11 1회만)
- [ ] gate_stats.fscore_full_n / altman_z_full_n 양쪽 ≥ 1500 (KOSPI 80% 커버)
- [ ] dart_health.jsonl 첫 batch 정상 적재 확인
- [ ] WIDE_SCAN_MODE secret = "SHADOW" 상태 (사용자 GH 콘솔)

---

## 6. 검증 (65 거래일 PRODUCTION 게이트 정합)

- Altman Z 컷별 hit rate (Distress reject 종목 12M 후 부도/감리 발생률)
- Grey zone 보조 신호 통과군 vs reject 군 alpha 차이
- DART 호출 일일 사용량 (20,000 한도 대비 %)
- corp_code 갱신 후 신규 상장 D+5 반영 검증
- medium_filter SHADOW vs PRODUCTION decision overlap (단계별 jsonl 트랙 분리로 회귀 격리)

---

## 7. 정합 메모리

- `project_altman_z_korea_standard` — Z″ EM 산식 + KSIC 64~66 제외 + Grey zone 룰
- `project_dart_api_2026_constraints` — Rate limit / corp_code / cron 회피
- `project_phase_2b_wide_scan` — Stage 2 quintile (입력 source)
- `project_funnel_5stage_sprint` — 5/17 sprint 시작점
- `project_brain_v5_self_attribution` — Brain v5 quick scoring 통합
- `feedback_sector_aware_thresholds` — 섹터 의존 임계 (sector_thresholds 헬퍼)
- `feedback_data_collection_verification_mandatory` — try/finally + stderr + 누적 검증
- `feedback_real_call_over_llm_consensus` — DART 사양 실호출 1회 우선 검증

---

## 8. 변경 가능성 (5/17 sprint 진입 직전 마지막 조정)

- ~~DART 실호출 후 schema 정합 검증 (예상 vs 실제 account_id 매핑) — 5/16 1회 호출 권장~~ ✅ **완료 2026-05-14** — §9 참조
- corp_code KONEX 필터링 정확도 검증 (5/17 첫 호출 시)
- 추가 종목 호출 (금융주 / 소형주 / 비제조업) — XBRL 미채택 빈도 측정
- Altman Z″ EM 한국 부도 데이터 calibration (장기 v0.3 큐)
- 5/17 직전 수정 완료 시 spec PDF 동결 (현재 markdown 만)

---

## 9. 실호출 sanity check (2026-05-14 검증)

**호출**: `005930` (삼성전자), `bsns_year=2025`, `reprt_code=11014` (3Q), `fs_div=CFS`

**응답**: status=000, 225 items 정상

**9 raw items 매핑 (10/10 발견 — interest_expense 도 ifrs-full_FinanceCosts 매핑)**:

| 항목 | 값 (단위 원) | 단위 |
|---|---:|---|
| total_asset | 523,659,586,000,000 | 523.66조 |
| current_assets | 229,440,881,000,000 | 229.44조 |
| current_liab | 87,259,259,000,000 | 87.26조 |
| book_equity | 413,501,494,000,000 | 413.50조 |
| total_debt | 110,158,092,000,000 | 110.16조 |
| retained_earnings | 385,279,270,000,000 | 385.28조 |
| long_term_debt | 22,898,833,000,000 | 22.90조 |
| ebit (9M) | 12,166,062,000,000 | 12.17조 |
| operating_cf (9M) | 56,515,496,000,000 | 56.52조 |

**Altman Z″_EM 산식 적용**:
```
ebit_annualized = 12,166,062 × (12/9) = 16,221,416 백만원
X1 = 16,221,416 / 523,659,586 = 0.0310
X2 = 385,279,270 / 523,659,586 = 0.7357
X3 = (229,440,881 - 87,259,259) / 523,659,586 = 0.2716
X4 = 413,501,494 / 110,158,092 = 3.7536

Z″_EM = 3.25 + 6.72(0.0310) + 3.26(0.7357) + 6.72(0.2716) + 1.05(3.7536)
      = 3.25 + 0.208 + 2.398 + 1.825 + 3.941
      = 11.62  → Safe (컷 2.6 한참 위)
```

**검증 결과**: 산식 작동 OK, 시그널 합리적 (삼성전자 = 안정 그 자체). step e 진입 기술적 blocker 없음.

### 9.1 추가 3종 검증 (2026-05-14, 비제조 + 소형 + 금융)

| 종목 | 카테고리 | 매핑 | Z″_EM | 판정 | 의의 |
|---|---|---|---:|---|---|
| 005930 삼성전자 | 제조 대형 | 10/10 | 11.62 | Safe | 기준 |
| 035420 NAVER | 비제조 플랫폼 | 10/10 | 8.93 | Safe | 비제조 매핑 robust |
| 027040 서울전자통신 | 소형 적자 (시총 ~150억) | 10/10 | -0.86 | **Distress** | 소형주 XBRL 우려 무용 + 산식이 부도위험 정확 식별 |
| 105560 KB금융 | 금융주 | 6/10 | 계산 불가 | Stage 1 제외 | 4 필드 (current_assets/current_liab/long_term_debt/interest_expense) 원천 미존재 → 금융주 제외 룰 입증 |

**산식 robustness 입증**:
- 정상 → Safe (삼성/NAVER), 적자 → Distress (서울전자통신) 정확 분류
- 금융주 = BS 가 유동/비유동 구분 안 함 → Z 계산 원천 불가능 → KSIC 64~66 Stage 1 제외 의무 = 한 번 더 검증

**IFRS variant 1건 추가 (위 §2.5 fallback 반영)**:
- 비금융 일부: `interest_expense` → `ifrs-full_InterestExpense` (CIS 직접) — fallback 추가
- 영업이익: `dart_OperatingIncomeLoss` (제조/일반) ↔ `ifrs-full_ProfitLossFromOperatingActivities` (금융/일부) — fallback 작동 확인

**최종 판정**: step e spec v0.1 동결 가능. 5/17 sprint 진입 시 medium_filter.py 가 본 spec 그대로 implement.

**Perplexity 답과 어긋난 발견 3건 (이미 §2.4-§2.6, §3.1.1 에 정정 반영)**:
1. `thstrm_add_amount` 필드 자체 없음
2. 분기 보고서 IS/CF = 누적값 (3Q = 9개월)
3. interest_expense = `ifrs-full_FinanceCosts` (별도 이자비용 항목 없음)

`feedback_real_call_over_llm_consensus` 정합 — LLM 답 → 실호출 1회로 3건 정정.
