# 5/18 Sprint Summary — 2026-05-18 KST 12:08 ~ 19:35

**Goal** (PM /goal 시점 13:30 KST 박힘): "오늘(5/18) 예정되어 있던 모든 작업 끝내자. 중간중간 궁금한거 있으면 퍼플렉시티 질문 정리해둬. 내가 답 받아올테니."

---

## 1. Sprint chain (16 commit + 4 doc + 1 메모리)

### Commit chain

| commit | scope | 영향 |
|---|---|---|
| `f28cdcf5` | A1 v1 (weekend 제한 제거) + A3 audit doc | dart_business_analysis 평일 진입 |
| `763d510c` | brain_audit hook v1 | daily_full 마다 jsonl 측정 |
| `51988f03` | A5 backtester vol | quant_volatility 회복 backbone |
| `3bb142e8` | A4 silent skip 보강 + A6 v1 zfill 버그 fix | trace enabling + US ticker 매칭 |
| `cd37ec77` | telegram push step | 사용자 핸드폰 자동 알림 |
| `60fd52b7` | **SEC EDGAR endpoint** + yfinance backtester | sec_financials 5 US 회복 + vol fetch |
| `04f30868` | A1 v2 (`_dt` import) | A1 v1 NameError hotfix |
| `619aab0e` | **yfinance 14 file 일괄** wrapper | 모든 yfinance 호출 anti-bot 우회 |
| `9639ec13` | brain_audit v2 (dev.json) | staging mode dual measure |
| `33a90d96` | A6 v2 (run_commodity_scout zfill) | US ticker by_ticker 매칭 |
| `ab5e3b49` | A7 attach drop US | external_risk/dart/comm/vol/anal 보존 |
| `4afbd2e0` | A7 attach drop v2 KR | KR 정합 |
| `ec0ba7ca` | Perplexity 질문 5건 doc | PM 답 받음 의제 |
| `9a204a34` | Tier 2 PM Decision Queue doc | C/D/E 결정 준비 |
| `09b92ec8` | Perplexity Q6 추가 | cron silent miss |

### 신 doc (4)
- `docs/A3_DART_FINANCIALS_AUDIT_20260518.md` (dart_financials 3 옵션)
- `docs/A4_A6_FIX_AUDIT_20260518.md` (A4 silent skip + A6 zfill)
- `docs/PERPLEXITY_QUESTIONS_20260518.md` (Q1~Q6, $0.50)
- `docs/TIER2_PM_DECISION_QUEUE_20260518.md` (C/D/E)

### 신 메모리 (2)
- `feedback_no_wait_mode_default` (wait 모드 default 금지)
- `project_5_18_sprint_lessons` (3 patterns: staging dual measure / realtime prev_merge / 변수 사용처 검증)

### 신 script (1)
- `scripts/push_brain_audit_telegram.py` (brain_audit jsonl → telegram)

---

## 2. Trigger 3회 측정

| trigger | run id | 시작 | 결과 |
|---|---|---|---|
| #1 | 26011919102 | 12:29 KST | A1 v1 NameError fail. 진단만 가치 |
| #2 | 26026493421 | 18:57 KST | **vol_20d 25/25 ✓ external_risk 10/25 ✓ brain max 49 (+3)** |
| #3 | 26027394324 | 19:18 KST | 모든 fix 적용, 결과 wait |

### universe_scan manual (5000~5500 wide_scan)
- run 26028132497 (19:33 KST 박힘, trigger #3 큐잉 후 진행). ~35분 추정.

### Trigger #3 측정 의제 (자동 push 도착 + Engineer chat 보고)
- prod portfolio.json: 5/16 13:01 baseline (staging mode = 안 박힘)
- **dev portfolio.dev.json**:
  - brain_score min/med/max/mean
  - grade BUY/STRONG_BUY/WATCH/CAUTION/AVOID
  - dart_business_analysis fill (A1 v2 효과 — 0/25 → KR 10?)
  - external_risk fill (A7 효과 — top 10 attach)
  - volatility_20d fill (A5 + yfinance 효과 — 25/25?)
  - commodity_margin fill (A6 v2 효과 — by_ticker 정상 시)
  - sec_financials fill (15/25 회복 유지)

---

## 3. 외부 API 회귀 발견 + fix

### SEC EDGAR endpoint 이전
- `data.sec.gov/files/company_tickers.json` = **404** (5/18 발견)
- `www.sec.gov/files/company_tickers.json` = **200 OK** ✓
- `data.sec.gov/submissions/CIK*.json` = 정상 (그대로 사용)
- fix: api/collectors/sec_edgar.py:18 `_WWW_BASE` 분리

### yfinance Yahoo anti-bot
- local sanity OK / GitHub Actions runner 만 404 매번
- fix: curl_cffi (chrome impersonate) session inject
- 14 file 일괄 (technical/parallel_fetcher/earnings/dividend/group/momentum/eps/dart_fundamentals/crypto/sector/cboe/fund_flow/cross_asset_corr/pair_scanner)

### pykrx 결함 (Q3 큐잉)
- `Error occurred in get_index_ohlcv_by_date / get_otc_treasury_yields_by_date` 다수
- 진단만 + Perplexity Q3 (pykrx 대안)

---

## 4. 측정 결과 patterns

### staging mode dual measure 박힘
- 옛 brain_audit script = portfolio.json 만 measure → staging trigger 결과 항상 baseline 그대로
- 신 v2 = portfolio.json + portfolio.dev.json 분리 measure, jsonl source 명시
- 결과 진단 정확성 ↑

### realtime cron prev_match merge field 결함 발견 + fix
- full mode 산출 (external_risk / dart_business / commodity / vol / analyst) 가 quick/realtime cron 도래 시 drop
- _us_fields (US) + KR merge expand 박음
- 다음 realtime cron 1 cycle 후 보존 검증 의무

### A1 fix v1 `_dt` import 누락
- Engineer 단일 line 제거 시 변수 사용처 검증 의무 (lessons #3)
- A1 v2 hotfix 박음

---

## 5. PM 결정 큐 (Tier 2 / 다음 sprint)

### Tier 2 (1회 권한, RULE 7)
- **C** (DEAD factor 가중치 0) ⭐⭐⭐ Engineer 추천 = 보류
- **D** (bonus trigger 임계 완화) ⭐⭐
- **E** (grade 임계 재 calibration) ⭐ overfit risk 최대
- Engineer 추천: **보류** — 1회 권한 보존, N≥30 거래일 후 (~6월 중순) 재평가

### Perplexity 답 받음 후 fix 진행
- Q1 yfinance anti-bot 2026 → curl_cffi 정확성 검증
- Q2 SEC EDGAR endpoint changelog → www 정합 검증
- Q6 GitHub Actions cron silent miss → wide_scan 정기 cron 회복 path

### 다음 sprint 큐잉
- A3 옵션 b/c (dart_financials 산식 / 새 collector)
- A4 본격 fix (silent skip trace 식별 후)
- A6 by_ticker 빈 root cause (run_commodity_scout fail 진단)
- 5000 wide_scan cron miss fix
- 옛 stash 정리 (8건 잔류)

---

## 6. 사용자 frame 정합

- "내가 가는 길은 의심 안 해. 하면할수록 답이 보임" — 정합 (16 commit 추가 trail)
- "넘어진다는 것은 일어서는 방법 학습" — A1 v1 buggy 패턴 학습 → v2 hotfix
- "되면 돈벌고, 안되면 스펙용 포트폴리오" — downside hedged 유지
- 사용자 격분 "wait 모드 / 거짓말" → [[feedback_no_wait_mode_default]] hardcoded 학습

---

**End of 5/18 sprint summary. trigger #3 + universe_scan 결과 wait. 자동 push 도착 후 다음 결정.**
