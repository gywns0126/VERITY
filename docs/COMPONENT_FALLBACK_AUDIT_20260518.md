# 5 Component Fallback Audit — 2026-05-18

**Purpose** — Brain Score Audit (`BRAIN_SCORE_AUDIT_20260518.md`) §3 root cause "5 components 100% fallback 50" 의 별도 audit. A-task. 6 component (commodity_margin / dart_health / perplexity_risk / quant_volatility / analyst_report / moat_quality) 각 collector / propagate / trigger 결함 정량 진단.

**Scope** — `data/portfolio.json` recommendations N=25 (5/15 18:32 KST universe scan, 5/16 13:01 last brain analysis).

**결론 (선요약)** — **5 component 모두 raw input field 자체가 부재** (collector 산출물 없음). 단순 산식 결함 아니고 pipeline 결함. 4종 trigger 결함 (full 모드 제한 + weekend 제한 + CIRCULAR dependency) + 1종 데이터 수집 결함 + 1종 KR/US 비대칭. **`perplexity_risk` 의 CIRCULAR DEPENDENCY 가 가장 중요한 발견**.

---

## §1 — raw input field 존재 (N=25)

| component | raw input field | KR (10) | US (15) | 전체 |
|---|---|---|---|---|
| commodity_margin | `stock.commodity_margin` | — | — | **0/25** |
| dart_health | `stock.dart_business_analysis.business_health_score` | 0/10 | n/a | **0/25** |
| perplexity_risk | `stock.external_risk.risk_level` | 0/10 | 0/15 | **0/25** |
| quant_volatility | `volatility_20d / volatility_60d / beta` | 0/10 | 0/15 | **0/25** |
| analyst_report | `stock.analyst_report_summary.analyst_sentiment_score` | 0/10 | 1/15 (TMO) | **1/25** |
| moat_quality | `sec_financials` (US) / `dart_financials` (KR) | 0/10 | 10/15 (5 미수집) | KR 0%, US 67% |

---

## §2 — 결함 분류

### A. `commodity_margin` — collector 안 돌음

- `_commodity_to_score` (verity_brain.py:1149-1155): `cm.get("primary").get("margin_safety_score")` 부재 시 50 반환
- main.py:3073 `cm = stock.get("commodity_margin") or {}` — 단순 reader, attach 위치 별도
- **결함**: universe_scan 단계 또는 main analysis pipeline 어디서도 `stock["commodity_margin"]` 박는 collector 호출 흔적 없음
- Cache: `data/commodity_sector_map_cache.json` (5/16 13:36 갱신) 존재하나 stock-level attach 와 disconnect

### B. `dart_health` — weekend full 모드 only + 28일 stale

- main.py:3206 트리거 조건: `if effective_mode == "full" and _is_weekend:`
  - **주말 (토/일) + full 모드** 에만 실행
  - 5/17 (일) 14:21 = VAMS reset (full 모드 아닐 가능성), 5/16 (토) 13:01 = main analysis (full 모드여야 함)
- `data/dart_analysis_cache.json` mtime 2026-04-20 06:13 → **28일 stale**
- `data/dart_kr_cache/` mtime 2026-04-19 17:46 → **29일 stale**
- main.py:3209 `_get_cc` 호출 → corp_code 부재 시 skip. KR 10 종목 모두 `business_health_score=None` = corp_code 미해석 또는 weekend full 안 돌음

### C. `perplexity_risk` — **CIRCULAR DEPENDENCY** ★ 핵심 ★

main.py:3370-3392:

```python
if effective_mode == "full" and PERPLEXITY_API_KEY:
    buy_candidates = [
        s for s in candidates
        if s.get("verity_brain", {}).get("grade") in ("BUY", "STRONG_BUY")
    ]
    if buy_candidates:
        ...
        for stock in buy_candidates[:10]:
            ...
            stock["external_risk"] = risk
```

→ **BUY/STRONG_BUY 종목만 Perplexity scan**. 현 운영 BUY 0건 → buy_candidates 빈 list → scan 안 돌음 → external_risk 부재 → perplexity_risk = 50 fallback → fact_score 변동 X → brain_score 안 오름 → BUY 임계 60 도달 못 함 → **영구 loop**.

**`data/perplexity_scan_cache.json` 자체 부재** = 한 번도 안 돌았거나 캐시 미사용. 강한 회귀 시그널.

이 loop 가 풀리지 않으면 다른 fix 박아도 BUY 부활 불가.

### D. `quant_volatility` — 입력 데이터 부재

- main.py:2611-2614 `qf["volatility"] = compute_volatility_score(stock, universe_stats=vol_stats)`
- `compute_volatility_score` (api/quant/factors/volatility.py:24) 입력:
  - `stock.volatility_20d`, `stock.volatility_60d`, `stock.beta`, `stock.technical.volatility_20d`, `stock.price_history`
- **25 종목 전부 위 4개 필드 0/25**. `price_history` 도 없으면 모두 50 default fallback.
- universe_scan_builder 가 volatility_20d / beta 박는 collector 호출 안 함 (FRED 또는 yfinance 의 일별 수익률 stddev 산출 단계 부재)

### E. `analyst_report` — full 모드 only + ticker mapping 1/25

- main.py:3169 트리거: `if effective_mode == "full":`
- `data/analyst_reports.json` mtime 2026-04-20 → **28일 stale**
- `data/analyst_pdf_summaries.json` 부재
- main.py:3191 `t6 = str(t).split(".")[0].zfill(6)` — 6자리 ticker 매칭 (KR 위주)
- TMO (US ticker) 만 1건 박힘 — US ticker mapping 우연 hit 또는 별경로
- KR 10 종목 0건 = full 모드 + report_summarizer 모두 실패

### F. `moat_quality` — KR 입력 전체 부재, US 67%

- `_compute_moat_score` (verity_brain.py:75) 입력:
  - US: `sec_financials.gross_margin / revenue_growth / pbr / roe / debt_ratio` + `dart_business_analysis.moat_indicators`
  - KR: `dart_financials.income_statement` + `kis_financial_ratio` fallback
- 운영 풀: **sec_financials 10/15 US 종목** (TMO/SOFI/QCOM 등 부분 채워짐), **dart_financials 0/10 KR**, kis_financial_ratio 7/10 KR
- US 5/15 누락 종목 = sec_filing 수집 회귀 의심
- KR 0% = dart_financials collector 자체 안 돌음 (sb 마찬가지로 weekend full only 추정)

---

## §3 — 종합 fix 후보 (PM 결정 의무)

### Tier 1: 코드 only (RULE 7 X) — Engineer 박을 수 있음

| # | action | scope | priority |
|---|---|---|---|
| A1 | `[5.88]` dart_business_analysis weekend 제한 해제 (매일 full 모드) + cache 활용 | trigger 완화, 산식 X | high |
| A2 | `[5.87]` analyst_report_summary 매일 trigger + ticker mapping (US ticker 포함) audit | trigger 완화, 산식 X | high |
| A3 | dart_financials KR collector 추가 호출 (또는 dart_batch.yml 의 dart_fundamentals_kr.json 활용 propagate) | data pipeline | high |
| A4 | sec_financials 누락 5 US 종목 audit (수집기 에러 trace) | data pipeline | medium |
| A5 | volatility_20d / volatility_60d / beta 산출 collector 추가 (yfinance 일별 수익률 stddev) | data pipeline 신설 | medium |
| A6 | commodity_margin attach 위치 audit + 누락 collector 호출 추가 | data pipeline | medium |

### Tier 2: 산식/임계 변경 (RULE 7 적용 — PM 사전 승인 의무)

| # | action | scope | priority |
|---|---|---|---|
| **A7** ★ | **perplexity_risk 트리거 조건 변경**: `BUY/STRONG_BUY` → 상위 N 종목 (예: top 10 by brain_score) | **CIRCULAR 해소** | **critical** |
| A8 | quant_volatility 입력 부재 시 default 50 대신 universe median 사용 | 산식 변경 | low |

### A7 권장 산식 (PM 결정 의무, 1회 한정)

옵션 a: `buy_candidates = sorted(candidates, key=brain_score, reverse=True)[:10]` (상위 10)
옵션 b: `buy_candidates = [s for s in candidates if grade in ("BUY", "STRONG_BUY", "WATCH")]` (WATCH 포함)
옵션 c: `buy_candidates = [s for s in candidates if brain_score >= 45]` (절대 임계)

권장: **옵션 a (상위 N)** — 자기 산식 (BUY 임계 도달 불가능 cycle 회피 + 정량 cap)

---

## §4 — 퍼플 자문 query 식별

[[feedback_perplexity_collaboration]] 정합 — 외부 사실/통계/source 확인 필요 영역:

| Q# | 질문 | 비용 추정 | 우선순위 |
|---|---|---|---|
| Q1 | FRED 의 NAPMI / MANEMP 대체 monthly GDP nowcast series (RECPROUSM156N proxy 보강용). NY Fed Weekly Economic Index (WEI) 또는 Atlanta Fed GDPNow 가 FRED 등록 됐는지. | $0.05 (Sonar) | low (F2 검증) |
| Q2 | 한국 증권사 리포트 PDF 공개 source 종합 (네이버 외 와이즈리포트 / 매경 / 키움 / 미래에셋 등). 무료 API 또는 robots-allowed scrape 가능한 source 우선. | $0.10 (Sonar Pro) | high (A2 보강) |
| Q3 | 한국 상장사 사업보고서 (DART) AI 분석 비용 효율화 — Gemini Flash 2.0 vs OpenAI GPT-5 Nano vs Claude Haiku 4.5 비교. 정량 metric (token/$). | $0.10 (Sonar Pro) | medium (A1 보강) |
| Q4 | Perplexity Sonar API rate limit 및 batch best practice (현 운영: BUY-only 종목 1-by-1 호출 = 비효율). top-N 자동화 시 비용/throttle 가이드. | $0.05 (Sonar) | medium (A7 보강) |
| Q5 | KR 종목 historical price → volatility_20d / volatility_60d / beta 산출에 yfinance vs KRX OpenAPI vs pykrx 정확도/속도 비교. | $0.05 (Sonar) | low (A5 보강) |

**총 비용 추정**: $0.35 (5 query, 1회).

[[project_perplexity_collaboration]] 정합 — 위 query 들은 외부 사실 검증 영역이라 Claude 시스템 코드 영역 침범 X.

---

## §5 — 진행 권장 순서 (Engineer 추천, PM 결정 의무)

1. **A7 먼저 (CIRCULAR 해소)** — PM 승인 후 1회. 다른 모든 fix 의 enabling 조건.
2. **A1 + A2 묶음** — weekend / full 모드 제한 해제 + ticker mapping. dart_business_analysis 와 analyst_report_summary 동시 회복.
3. **A3 + A4 데이터 pipeline 보강** — dart_financials KR + sec_financials US 누락 audit.
4. **Perplexity Q2/Q4 자문** — A2/A7 보강용 외부 사실 확인.
5. A5 / A6 / A8 = baseline 회복 후 재측정 → 1회 임계 조정 권한 보존 (RULE 7).

### A1-A7 fix 후 예상 효과 (시뮬)

- 5 component data fill 평균 65 도달 시: fact_score +5 ≈ 50
- DEAD 4 factor 처리 (별도 의제 C) 추가 시: fact +3 ≈ 53
- bonus 1-2개 trigger (별도 의제 D) 시: raw +3-5
- **F1+F2 분면 (0.65, 0.35) 가중 시**: brain_score ≈ 53 × 0.65 + 50 × 0.35 + 4 = 56
- → **여전히 BUY 60 임계 도달 어려움**. E (grade 임계 calibration) 1회 권한 필요 가능성 높음.

---

## §6 — 변경 추적

| 일자 | 변경 |
|---|---|
| 2026-05-18 | A-task audit (본 doc) — 5 component fallback root cause + 8 fix 후보 + 5 퍼플 query |

### 관련 메모리

- [[project_brain_score_funnel_audit]] (4중 root cause 의 #1 = 본 audit 깊이 박음)
- [[feedback_data_collection_verification_mandatory]] — A1~A6 적용 시 try/finally + logged=True 의무
- [[feedback_perplexity_collaboration]] — §4 query 적용 시 정합
- [[project_perplexity_equity_brief]] — Q2 와 시너지 가능 (KR 증권사 리포트 + 미장 brief)
- [[feedback_workflow_yml_audit_mandatory]] — A1/A2/A3 cron 추가 시 6축 audit 의무
- [[project_dart_api_2026_constraints]] — A3 적용 시 DART 20K/day 한도 검증

### Source data (재현)

```bash
python3 -c "
import json
p = json.load(open('data/portfolio.json'))
recs = p.get('recommendations', [])
for f in ('commodity_margin', 'dart_business_analysis', 'external_risk', 'analyst_report_summary'):
    n = sum(1 for s in recs if s.get(f))
    print(f'{f}: {n}/25')
"
```

---

**End of A-audit. 코드 변경 / 임계 조정 없음. PM 결정 대기 — A7 (CIRCULAR 해소) 최우선.**
