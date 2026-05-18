# Perplexity 질문 stack — 2026-05-18 sprint 중 박힘

**Purpose** — 5/18 sprint 진행 중 출처/공식 정합 검증 필요한 외부 사실 의문 정리. PM (사용자) 가 답 받아옴 → Engineer 가 fix 진행.

[[feedback_perplexity_collaboration]] 정합 — 외부 사실/통계/법규 = Perplexity, 시스템/코드 = Claude.

---

## Q1 — Yahoo Finance anti-bot 2026 best practice (yfinance lib)

**배경**: 5/18 trigger #1 (run 26011919102) workflow log — yfinance HTTP 404 매번 30+ 종목. local 정상 / GitHub Actions runner 만 fail. curl_cffi (chrome impersonate) session 박아서 우회 시도. 단 trigger #2 log 도 다른 호출처 (technical / parallel_fetcher / earnings 등) 일부 여전 404 가능.

**질문**:
1. 2026 시점 yfinance Yahoo Finance anti-bot 회피 best practice — curl_cffi (chrome impersonate) 외 다른 path?
2. Yahoo 가 GitHub Actions IP block 정책 변경 가능성 — IP rotation / residential proxy 필요?
3. yfinance lib 의 fallback library (pure HTTP without yfinance, 또는 alternative API)?
4. yfinance Ticker.info / .history / .dividends / .calendar / .options 각 endpoint 별 anti-bot 강도 차이?

**예상 비용**: Sonar Pro $0.10
**우선순위**: HIGH (오늘 sprint 의 root cause)

---

## Q2 — SEC EDGAR API endpoint changelog (data.sec.gov vs www.sec.gov)

**배경**: 5/18 trigger #1 — SEC `data.sec.gov/files/company_tickers.json` = 404. `www.sec.gov/files/company_tickers.json` = 200 OK. 단 `submissions/CIK*.json` 은 www = 404, data = 403 (auth) → data 그대로 사용 의무. 정확 endpoint 매핑 모호.

**질문**:
1. SEC EDGAR API 의 공식 endpoint 매핑 (2026 시점):
   - `/files/company_tickers.json` — www vs data 중 정공법?
   - `/submissions/CIK{cik}.json` — www vs data 중 정공법?
   - `/api/xbrl/companyfacts/CIK{cik}.json` — www vs data?
2. data.sec.gov sub-domain 의 deprecated 시점 또는 일부 endpoint 만 옮김?
3. SEC EDGAR rate limit (10 req/sec) 외 IP-based throttling 정책 (GitHub Actions IP block?)?
4. SEC EDGAR User-Agent 명시 의무 (현재 "VERITY/1.0 (gywns0126@gmail.com)") — 형식 정합?

**예상 비용**: Sonar $0.05
**우선순위**: HIGH (SEC fix 정확성 검증)

---

## Q3 — pykrx KRX OpenAPI 결함 대안 (get_index_ohlcv_by_date / get_otc_treasury_yields_by_date)

**배경**: 5/18 trigger log — pykrx error 다수:
```
Error occurred in get_index_ohlcv_by_date: Expecting value: line 1 column 1 (char 0)
Error occurred in get_otc_treasury_yields_by_date: '국고채권(01년)' ~ '국고채권(30년)'
```
= pykrx 의 KRX OpenAPI 응답 parser 결함 가능 (KRX 가 응답 format 변경).

**질문**:
1. 2026 시점 pykrx 최신 release 및 알려진 회귀 — KRX OpenAPI format 변경에 대응됐는지?
2. pykrx 대안 (KR 주식/지수/채권 데이터 fetch) — 무료 / 안정성 / 갱신 활성 비교:
   - KRX OpenAPI 직접 호출 (인증 키 필요?)
   - DART OpenAPI (재무 외 가격 X)
   - 한국투자증권 KIS OpenAPI (현재 사용 — 1일 1토큰 정책)
   - 야후 파이낸스 한국 지수 (^KS11 / ^KQ11) — yfinance 의존
   - 키움 / 미래에셋 비공식 API?
3. KRX 채권 데이터 (`국고채권(01년) ~ (30년) 수익률`) 무료 fetch source?

**예상 비용**: Sonar Pro $0.10
**우선순위**: MEDIUM (실제 brain v5 영향 작음, 보고서 PDF 가 채권 데이터 사용)

---

## Q4 — Gemini Flash 2.0 vs Claude Haiku 4.5 vs OpenAI GPT-5 Nano 비교 (DART 사업보고서 AI 분석)

**배경**: 5/18 audit doc Q3 (COMPONENT_FALLBACK_AUDIT) 박힘. 현재 DART 사업보고서 AI 분석 = Gemini 호출 ($0.05/종목). 비용/성능 비교 필요.

**질문**:
1. 2026 시점 KR 텍스트 (한글 사업보고서 ~10MB PDF) 분석 LLM 비용/품질 비교:
   - Gemini Flash 2.0 (현재) — 한글 처리 정확도?
   - Claude Haiku 4.5 — 한글 정확도 + 비용
   - OpenAI GPT-5 Nano — 한글 정확도 + 비용
   - Mistral / DeepSeek 등 open-source — self-hosted 가능 시 비용 ↓?
2. 가장 cost-effective 옵션 (token/$/quality 종합)?
3. Anthropic Files API (file upload) 활용 시 KR PDF 처리 안정성?

**예상 비용**: Sonar Pro $0.10
**우선순위**: LOW (현재 Gemini 안정 작동, 비용 최적화 다음 sprint)

---

## Q5 — KR 증권사 리포트 PDF 공개 source (KIRS scraper 보강)

**배경**: 5/18 새벽 sprint KIRS scraper (commit fdeea8da) 박힘. 단 운영 풀 N=25 매칭 0/10 (audit doc § 3 정합). 다른 KR 증권사 리포트 source 통합 필요.

**질문**:
1. 2026 시점 한국 증권사 리포트 PDF 공개 source 종합:
   - KIRS (한국투자증권 리서치) — 현재 사용
   - 네이버 금융 증권 리포트 — 활성?
   - 와이즈리포트 — 무료 API?
   - 매경/한경 컨센서스 — 자동화 가능 (robots-allowed)?
   - 키움/미래에셋/삼성/NH/한화/하나/신한 — 자체 site scrape 가능?
   - 한경컨센서스 — 5/18 audit 시 robots.txt `Disallow: /` 확인 → 자동화 폐기 결론 정합?
2. 무료 API 또는 robots-allowed scrape source 우선 list
3. PDF 다운로드 후 AI 요약 cost 추정 (종목당 $0.05~0.10)

**예상 비용**: Sonar Pro $0.10
**우선순위**: MEDIUM (Phase 2-B 진입 시 본격화, 현 풀 N=25 영향 0)

---

## Q6 — GitHub Actions schedule cron silent miss 정책 (2026)

**배경**: 5/18 진단 — universe_scan.yml cron `30 6 * * 1-5` UTC (KST 15:30 평일). 마지막 schedule run = 5/15 09:31 UTC. 5/16~17 = 주말 (정상 skip). **5/18 (월요일) 정기 schedule run 0건 = silent miss**. 같은 concurrency group (verity-data-write) 의 daily_analysis_full 도 16:07 KST 정기 cron 안 돔 (manual trigger only).

**질문**:
1. 2026 시점 GitHub Actions schedule cron silent miss 정책:
   - public repo 60일 inactivity 후 cron 자동 비활성 정책 적용 여부 (Actions 사용량 있으면 reset?)
   - high-load 시 schedule miss 빈도 (특정 분 / 특정 시간대 우선 fail?)
   - SLA 또는 best-effort 명시?
2. concurrency group cascade miss 패턴:
   - 같은 group 의 여러 cron 충돌 시 schedule cron 도래 시 큐에 진입 못 하면 silent skip?
   - workflow_dispatch (manual) 와 schedule 우선순위 차이?
3. silent miss 회피 best practice:
   - Vercel Cron + repository_dispatch 활용?
   - 여러 cron 시각 분산 (예: 30 6, 32 6, 34 6)?
   - 외부 cron service (cron-job.org / EasyCron) trigger?
4. GitHub Actions schedule cron 신뢰성 monitoring (도래 vs miss 통계 자체 진단)?

**예상 비용**: Sonar $0.05
**우선순위**: HIGH (5/18 발견 = 5000~5500 wide_scan 7일 stale + daily_analysis_full 정기 cron 도 같은 결함)

---

## 비용 정리

| Q | 비용 | 우선순위 | 답 받은 후 적용 영역 |
|---|---|---|---|
| Q1 | $0.10 | HIGH | yfinance fix 정확성 (오늘 sprint 핵심) |
| Q2 | $0.05 | HIGH | SEC fix 정확성 (오늘 sprint 핵심) |
| Q3 | $0.10 | MEDIUM | pykrx 대안 (다음 sprint) |
| Q4 | $0.10 | LOW | LLM cost 최적화 (다음 sprint) |
| Q5 | $0.10 | MEDIUM | KIRS scraper 보강 (Phase 2-B) |
| **Q6** | **$0.05** | **HIGH** | **GitHub Actions cron silent miss (5/18 발견)** |
| **총** | **$0.50** | — | — |

[[feedback_perplexity_collaboration]] 비용 cap: 단일 query ≤ $0.10 자율 / batch ≥ $0.50 PM 사전 — $0.50 = PM 사전 의제 (batch 임계 정확).

---

**End of Perplexity question stack — PM 답 받아오면 Engineer fix 진행.**
