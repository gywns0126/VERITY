# Perplexity Q batch — news impact magnitude + 3-axis score 의제 (2026-05-30)

## Context

VERITY (1인 retail, 4/1 시작, N=14, Phase 0) — 현재 news sentiment 1축 만 보유 (13-source + KR-FinBERT-SC + alpha decay D+1~D+10). 사용자 발화 (5/30): "엡손 기름 재고량 바닥 경고 같은 호재/악재 외 내용상 중요도 등급 의제". 사이트 성장 단계 진입 (vault Quartz 64 entry publish, methodology.verity-terminal.com).

본 batch 의도 = **외부 사실 / 학술 / 무료 stack 검증** ([[feedback_perplexity_collaboration]] 정합). 답변 후 PM 결정 → 산식 RULE 7 사전등록 → 사프린트 진입.

VERITY 기존 자산:
- 13-source sentiment ([[project_sentiment_13source_design]])
- KR-FinBERT-SC (KR 감성 SOTA)
- alpha decay (D+1 100% → D+10 15-30%)
- DART catalyst severity 5-tier (사전등록 5/23 A4 자문, 활성 X)
- detected_risk_keywords (7 keyword narrow filter)
- 자체 산식 = 가설 (RULE 7 정합, N<100 통계 무의미)

목표 산식 (impact magnitude + 3-axis):
- sentiment (호재/악재) — 보유
- impact magnitude (1-5 등급) — 결손
- novelty (신선도 / 첫 보도) — 결손

---

## Q1 (P0) — news impact magnitude score 학술 / 기관 표준

배경: VERITY 는 현재 sentiment (positive/negative/neutral) 1축 만 보유. "엡손 기름 재고 바닥" 같은 supply chain risk = mid-high impact 있어도 단순 negative sentiment 로만 분류. impact magnitude (1-5) 신 layer 추가 의제 발생.

질문:
1. Bloomberg Event Severity Index (ESI) 정의 + 산출 방법론 (1-5 등급 기준 + 입력 변수). 공식 docs / academic reference 있는가?
2. Refinitiv (Thomson Reuters) News Analytics — TRNA Impact Score 산출 방법론 + scale. 학술 백테스트 사례.
3. RavenPack / Accern 같은 commercial news analytics 의 impact / relevance score 산출 방법론.
4. **학술 paper meta-analysis**: Tetlock 2007 (Giving Content to Investor Sentiment), Loughran-McDonald 2011 (10-K dictionary), Kumar-Putnins 2024 retail news 같은 표준 reference 의 impact 정량화 방법론.
5. 무료 대안 — Bloomberg / Refinitiv 사용 불가 시 retail/academic 가능 무료 stack (HuggingFace model, GDELT, public dataset).
6. impact score 의 IC (Information Coefficient) 일반 range — 학술 paper 보고 보고된 평균 / 권고 임계.

VERITY 현 자산 / 정합도:
- 13-source sentiment 있음 (KR-FinBERT-SC continuous score)
- DART catalyst 5-tier (자체 산식, 학술 정합 검증 의제)
- N=14 = 산식 평가 통계 무의미

---

## Q2 (P0) — 한국 시장 news impact 자동 분류 무료 stack

배경: VERITY = KR 비중 ~40% (25종목 KR 10 + US 15). KR 한국어 NLP = 별 layer 의제. KR-FinBERT-SC = 감성 (pos/neg/neutral) SOTA but impact magnitude 분류 capability 없음.

질문:
1. KR-FinBERT-SC 의 impact 분류 fine-tune 가능성 — labeled data 무료 / 학술 dataset 존재?
2. **KPF-BERT** (한국언론진흥재단) / **KF-DeBERTa** (KAIST) — finance event classification 정합도, downstream task 성능.
3. **빅카인즈** (BIGKinds) 메타데이터 — 이벤트 카테고리 + severity 분류 자동 제공하는가? API 접근 + 비용.
4. **KOFIA / 한국거래소** 공시 severity 표준 분류 존재? — DART catalyst 자체 5-tier (5/23 A4 자문) 정합도 사후 검증.
5. **한국 finance NLP 오픈소스** — HuggingFace `snunlp/KR-FinBERT-SC` 외 추가 모델 (지난 12개월 출시). 라이선스 + Apache 2.0 정합.
6. **labeled dataset 무료** — KLUE / NSMC 외 finance 특화 KR labeled (event severity / impact 등급).

VERITY 운영 환경:
- daily ingestion = 100~500 articles (KR + US 합산)
- 자동 분류 정합 의제 (수동 라벨링 1인 운영 불가)

---

## Q3 (P1) — novelty score (dedup + 첫 보도 시점) 표준

배경: news pipeline 에서 같은 사건 다중 보도 (1차 통신사 → 2차 매체 → 3차 SNS). impact magnitude 정합 측정 위해 novelty / dedup layer 의제.

질문:
1. Refinitiv NoveltyScore / Linked Items 산출 방법론 (sliding window + similarity threshold).
2. **dedup 알고리즘 무료 표준**:
   - LSH (Locality-Sensitive Hashing) / MinHash
   - sentence embedding similarity (`sentence-transformers` / FAISS)
   - n-gram Jaccard / TF-IDF cosine
3. threshold 권고 — 첫 보도 후 N분 / N시간 = "novel" 분류.
4. novelty decay function — 첫 보도 = 100, 시간 흐름 의 decay rate 학술 권고.
5. KR 시장 적용 사례 — 빅카인즈 dedup 자체 제공 / 자체 구현 필요?
6. 무료 라이브러리 — Python ecosystem (datasketch, simhash, sentence-transformers).

VERITY scale:
- daily 100~500 articles
- 1인 maintenance = LSH / embedding 중 어느 path 정합?

---

## Q4 (P1) — 3-axis 통합 score (sentiment × impact × novelty) weighted formula

배경: 3-axis 있을 (정정 = 보유 시) 통합 score 산출 = stock signal 의 의제. 단순 곱 vs 가중 합 + alpha decay 결합 path.

질문:
1. Bloomberg / Refinitiv / RavenPack 의 통합 headline score 공식 (3-axis weighted formula 공개).
2. 학술 paper (Tetlock 2008, Boudoukh 2019, Kumar-Putnins 2024) headline score 통합 산식.
3. weight 권고 — (1, 1, 1) equal vs sentiment heavier vs impact heavier.
4. alpha decay 결합 — VERITY 보유 D+1~D+10 decay 의 3-axis score 와 곱 vs 시간 의존 weight.
5. **empirical IC** — 3-axis 통합 score 의 IC range (학술 paper 보고).
6. KR 시장 정합 — 한국 alpha decay (D+3~D+10) 가 미국 (D+1~D+3) 의 차이 가 통합 score 의 weight 차등 정당화 의 영향.

VERITY 자산:
- alpha decay 학습 자료 보유 ([[reference_learning_materials_folder]] 8개 토픽 #7 KR 뉴스 감성 D+1 100% → D+10 15-30%)

---

## Q5 (P2) — LLM 자동 분류 cost + accuracy + KR 정합

배경: 자체 NLP 산식 vs LLM 호출 (Claude Haiku / Gemini Flash / GPT-4o-mini) trade-off. RULE 6 정합 = LLM narrative 신규 컴포넌트 STOP but LLM 자동 분류 (structured output) 는 산식 layer 활용 가능 의제.

질문:
1. **cost 비교** ($/1000 articles, 2026 기준):
   - Claude Haiku 4.5 / Gemini 2.0 Flash / GPT-4o-mini
   - input 의 headline 200 token + output 의 JSON 3-axis 50 token = 평균 비용
2. **accuracy** — KR/EN finance event classification, human annotation 와 비교 (precision/recall/F1).
3. **KR 한국어 처리** — 어느 LLM 의 KR 정합도 우수 (KR-FinBERT-SC baseline 과 비교).
4. **structured output** — function calling / JSON mode 의 reliability + cost overhead.
5. **batch processing** — Anthropic Message Batches / OpenAI Batch API 의 50% 할인 적용 가능성 + delay tolerance.
6. **VERITY scale 추정** — daily 100~500 articles × 30 days = 월 3,000~15,000 articles. 월 비용 추정 ($/월).

VERITY 의 Claude budget = $20/월 ([[project_claude_budget_guard]]).

---

## Q6 (P0) — 1인 retail minimum viable news pipeline

배경: VERITY = 1인 사이드, 직업군인 (4/1 시작, 2개월). news pipeline 운영 cost / maintenance / scalability trade-off 의제.

질문:
1. **daily ingestion scale**:
   - KR 25종목 × 10 articles/day = 250
   - US 15종목 × 5 articles/day = 75
   - 합산 ~325 articles/day = 월 ~10,000
2. **source mix 권고** (무료 우선):
   - RSS (네이버 금융 RSS / Google News RSS / Yahoo Finance / SeekingAlpha)
   - 한국 빅카인즈 API
   - SEC EDGAR 8-K filing
3. **dedup + classification + storage** = 1인 maintenance 시간 추정 (h/월).
4. **delay tolerance** — D+0 realtime (cron 5분) vs D+1 batch (cron 1일 1회).
5. **storage** — JSON / SQLite / Postgres trade-off, 월 GB.
6. **운영 비용** — LLM call cost + storage + (선택) 유료 API ($/월).
7. **graduated path** — Phase 1 (baseline) → Phase 2 (impact + novelty) → Phase 3 (3-axis 통합).

VERITY 운영 환경:
- GH Actions PUBLIC repo (무제한 minutes)
- Vercel Pro
- Supabase 무료 tier
- 1인 maintenance ~5h/주
- Claude budget $20/월

---

## Q7 (P2) — news impact ↔ stock return meta-analysis paper

배경: news impact score 적용 의 정합도 검증 학술 reference. KR 시장 특화 paper 추적.

질문:
1. **classic paper**:
   - Tetlock 2007 (Giving Content to Investor Sentiment, WSJ news)
   - Tetlock 2010 (Liquidity and Limits to Arbitrage)
   - Loughran-McDonald 2011 (Liability of Foreignness, 10-K dictionary)
2. **modern paper (2020+)**:
   - Boudoukh 2019 (Information, Trading, and Volatility)
   - Kumar-Putnins 2024 (Retail Trader News Response)
   - NLP + transformer 기반 news IC 측정
3. **meta-analysis** — news impact ↔ next-day / 5-day / 30-day return 의 IC range expected.
4. **KR 시장 paper**:
   - KCMI (자본시장연구원) 의 한국 news impact 실증
   - 한국증권학회지 paper
   - 양철원 (가치프리미엄) / KCMI 2023-24 (이미 보유 [[reference_learning_materials_folder]])
5. **alpha decay** — news impact alpha decay 학술 권고 (KR D+1~D+10 vs US D+1~D+3).
6. **failure mode** — impact score 의 잘못된 trade signal 의 사례 (over-fit / 시장 regime 의존).

---

## Q8 (P1) — DART 공시 severity 5-tier 학술 정합

배경: VERITY 5/23 A4 자문 의 DART catalyst severity 5-tier 사전등록 (회생/파산/M&A/배당/CB/corr 5단계). 학술 정합 사후 검증 의제.

질문:
1. **KCMI / KOFIA / 한국거래소** 의 공식 severity 표준 분류 존재?
2. **KSE (KOSPI) vs KOSDAQ** 별 공시 중요도 차등 표준 있는가?
3. **corporate disclosure abnormal return event study** — 한국 paper (회생/파산/M&A/배당/CB 별 abnormal return 통계).
4. **DART severity tier 학술 권고**:
   - 5-tier vs 3-tier vs continuous score (어느 path 정합도 우수?)
   - Bloomberg ESI / Refinitiv 5-tier 정합도
5. **VERITY 자체 5-tier 사후 검증** — 회생/파산 (severity 5) / M&A 합병 분할 (4) / 자사주 배당 (3) / CB BW 5% (2) / corr (1) 분류 = 한국 시장 실증 정합?
6. **alert_engine level mapping** — severity 5/4 = telegram 즉시 / 3/2 = digest / 1 = log only 권고.

VERITY 자산:
- DART API 통합 의 운영 중
- detected_risk_keywords 7 keyword narrow filter 있음 (false alarm baseline)
- DART catalyst 5-tier = 사전등록 만, 활성 X

---

## 답변 후 의사결정 path

| Q 답변 | VERITY 의사결정 |
|---|---|
| Q1+Q4 학술 정합 강함 | impact 산식 RULE 7 사전등록 진입 |
| Q2 KR-FinBERT-SC fine-tune 가능 | 자체 산식 + KR-FinBERT 결합 path |
| Q3 dedup 무료 라이브러리 정합 | novelty score 신 sprint |
| Q5 LLM cost 합리적 | LLM batch 자동 분류 path |
| Q6 minimum viable pipeline 확정 | 1인 maintenance 의제 정합 |
| Q7 KR 시장 IC 의 range 정합 | 산식 효과 측정 baseline |
| Q8 DART 5-tier 사후 정합 | 활성화 (RULE 7 권한 6월 1건 활용) |

답변 받은 후 본 docs 같은 위치 에 `PERPLEXITY_ANSWERS_news_impact_20260530.md` 저장 + 메모리 인덱스 갱신 + PM 결정 trail commit.

## 사용자 Perplexity paste 가이드

1. Perplexity Pro 또는 Free 접근
2. 모델 = Sonar Pro 또는 GPT-4o (학술 reference 우선 권고)
3. 본 8 Q 의 한 번에 paste — Perplexity 의 batch 답변 정합
4. 답변 받은 후 `터미널 보충 학습 자료. /Q1_news_impact_answer_20260530.md` 저장 (사용자 reference 폴더 표준)
5. 메모리 [[reference_learning_materials_folder]] 인덱스 갱신 알림

본 batch 의 후속 = PM 결정 / 산식 RULE 7 사전등록 / 6월 sprint 진입.
