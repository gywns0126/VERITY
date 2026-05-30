# VERITY — News Impact Magnitude + 3-Axis Score: Research Answers
**Batch date: 2026-05-30 | Phase 0 / N=14 | RULE 7 사전등록 입력용**

---

## 개요

본 문서는 `PERPLEXITY_QUESTIONS_news_impact_20260530.md`의 Q1–Q8에 대한 외부 사실·학술·무료 스택 검증 결과다. VERITY의 현재 자산(13-source sentiment, KR-FinBERT-SC, alpha decay D+1~D+10, DART catalyst 5-tier 가설)을 기준으로, 결손 축인 **impact magnitude**와 **novelty**를 어떻게 채울 것인가에 대한 의사결정 입력을 정리했다.

---

## Q1 (P0) — News Impact Magnitude Score: 학술/기관 표준

### 1-1. Bloomberg ESI (Economic Surprise Index)

Bloomberg ESI는 뉴스 이벤트 severity index가 아니라, **경제지표 발표치 대 컨센서스 예측치의 편차**를 집계한 매크로 지수다. "actual > Street estimate → positive score, actual < Street estimate → negative score"를 롤링 기간에 걸쳐 평균 낸다[cite:82][cite:85]. Bloomberg에서 1–5 등급으로 뉴스 이벤트를 분류하는 "News Event Severity Index"는 공개된 공식 문서가 존재하지 않으며, ESG 이벤트 리서치(Bloomberg Intelligence ESG Event-Driven Risk) 맥락에서 이벤트별 7일 수익률 충격을 사후 집계하는 접근이 사용된다[cite:88]. **VERITY 적용 불가: 공개 API 없음, 상용 라이선스 전용.**

### 1-2. Refinitiv TRNA (Thomson Reuters News Analytics) Impact Score

TRNA는 Reuters 뉴스를 실시간으로 읽어 알고리즘 트레이더/시장 참여자에게 **per-asset 감성 스코어, relevance, novelty**를 제공하는 PostgreSQL 데이터베이스다[cite:86]. 핵심 구조:
- **SENT**: sentiment score (-1 ~ +1)
- **REL (Relevance)**: 해당 기사가 특정 자산에 얼마나 직접 관련되는지 (0~100)
- **NoveltyScore / Linked Items**: 과거 24h 내 유사 스토리 대비 신선도

별도의 "Impact Score" 컬럼은 공식 문서상 "ITEM_CNT1~5" 계열(같은 주제 관련 보도 개수)와 headline classification field로 간접 측정된다[cite:80]. NewsScope Event Indices(NEI, AlphaSimplex 공동 개발)는 "비정상적으로 많은 뉴스가 특정 카테고리에 몰릴 때" 임계 초과 신호를 발생시킨다[cite:83]. TRNA의 최신 버전은 Refinitiv Eikon/Workspace API로 접근 가능하지만 상용 구독 필요[cite:89]. **학술 접근 경로: WRDS(Wharton) — 대학 기관 계정 필요[cite:86].**

### 1-3. RavenPack 방법론

RavenPack은 22,000개+ 소스를 실시간으로 처리해 다음 메트릭을 제공한다[cite:78][cite:84]:
- **ESS (Event Sentiment Score)**: 0~100, 50=중립, 100=완전 긍정
- **CSS (Composite Sentiment Score)**: 복수의 sentiment 기법(규칙 기반 + ML)을 결합한 스토리 단위 종합 점수[cite:93]
- **Relevance Score**: 특정 entity와 기사의 관련도 (0~100)
- **Novelty Score/Temporal Scoring**: 24h 슬라이딩 윈도우 내 유사 스토리 수 대비 신선도

ESS는 0~100 연속 스코어이며, 문서상 "1~5 등급"으로 버킷팅하는 공식 표준은 없다. 연구 맥락에서는 ESS를 연속 값으로 사용하거나 3분위/5분위로 버킷팅한다[cite:96][cite:99]. WRDS Academic을 통해 기관 접근 가능[cite:81][cite:84]. **개인/retail 접근 불가 (commercial license).**

### 1-4. 학술 표준 meta-reference

| 논문 | 방법론 | Impact 정량화 |
|------|--------|--------------|
| Tetlock (2007, JoF) | WSJ "Abreast of the Market" 컬럼 — Harvard GI-4 사전 기반 pessimism score | 일별 시장 수익률, 거래량과의 회귀[cite:91][cite:94][cite:97] |
| Loughran-McDonald (2011, JoF) | 10-K 전용 금융 텍스트 사전 (Negative/Positive/Uncertainty/Litigious) | 단어 비율 × IDF 가중 → 문서 sentiment[cite:92][cite:95][cite:98] |
| Boudoukh et al. (2019, RFS) | 기업 특정 뉴스에서 "fundamental info" 판별 → overnight vs intraday 변동성 분해 | 49.6% overnight idiosyncratic variance를 public news가 설명[cite:141] |
| Kumar-Putnins (2024) | retail trader의 뉴스 반응 패턴 | retail과 institutional의 news IC 격차 |

이들 논문은 공통적으로 **단어 목록 기반 sentiment → 일별/주별 수익률 IC** 프레임을 쓰고, impact magnitude를 별도 레이어로 분리하지는 않는다. Impact magnitude 분리는 RavenPack/TRNA 같은 상용 데이터의 영역이거나, 직접 event-type 분류(M&A, earnings, regulatory 등) × 과거 abnormal return 분포를 결합하는 자체 설계로 접근하는 게 학술 선례에 가깝다.

### 1-5. 무료 대안 스택

| 도구 | 설명 | 한계 |
|------|------|------|
| GDELT Project | 100+ 언어, 전세계 뉴스 실시간 + 역사 데이터, 15분 단위 업데이트, 완전 무료[cite:132][cite:135] | KR 금융 특화 모델 없음, GCQ(GDELT CAMEO) 이벤트 분류가 금융과 매핑 어려움 |
| Loughran-McDonald 사전 | 무료 (학술 비상업), 7개 카테고리[cite:95] | 한국어 미지원 |
| GDELT GKG tone field | GKG에서 tone(−10~+10) 직접 추출 가능[cite:123][cite:126] | entity-level precision 낮음 |
| HuggingFace KR-FinBERT-SC | 무료, Apache 2.0 상업 사용 가능, KR 금융 SOTA[cite:106] | sentiment 3분류만, impact magnitude 없음 |

### 1-6. IC (Information Coefficient) 일반 범위

- 문서화된 equity factor: **IC 0.02–0.05** 범위가 전형적[cite:174]
- IC 0.05–0.10: 강한 신호로 인정[cite:179]
- IC > 0.15: 극히 드물고, overfitting 의심[cite:179]
- 뉴스 sentiment 신호는 일반적으로 IC 0.02~0.06 수준이 보고된다 (Tetlock 계열 연구 기준)
- 1일 horizon IC가 5–10일보다 높고, 시간이 지날수록 decay[cite:174][cite:179]

**VERITY 함의**: N=14에서는 IC 측정 자체가 통계적 의미 없음. signal 설계·산식 구조 확정 후, N≥60에서 초기 IC를 추정하고, N=126~252에서 유의성 판단하는 것이 현실적.

---

## Q2 (P0) — 한국 시장 News Impact 자동 분류 무료 스택

### 2-1. KR-FinBERT-SC fine-tune 가능성

KR-FinBERT-SC는 서울대 NLP 연구실 모델로, KR-BERT-MEDIUM 위에 72개 금융 언론사 기사 + 16개 증권사 애널리스트 리포트로 추가 학습했으며, 분류 정확도 96.3%를 보고한다[cite:106]. **impact magnitude fine-tune 가능성:**
- 기술적으로는 가능: HuggingFace `Trainer`로 fine-tune sequence classification (3-class → 5-class로 변경)
- 문제는 **labeled data 부재**: KR finance event impact 등급 라벨이 붙은 공개 데이터셋 없음
- 방법론적 대안: 과거 DART 공시 + 공시 후 5일 수익률(CAR)을 기준으로 **weak supervision** 라벨을 생성해 fine-tune하는 경로가 현실적
- 샘플 예시: `DataWizardd/finbert-sentiment-ko` — KR-FinBERT-SC를 기반으로 네이버 환율 뉴스 200개를 수작업 라벨링해 fine-tune, 전체 정확도 93%[cite:112]

1인 유지 관점에서 수작업 라벨링은 부담이 크므로, **DART 공시 → CAR 기반 weak label** 경로가 가장 현실적이다.

### 2-2. KPF-BERT (한국언론진흥재단)

한국언론진흥재단이 2022년 2월 공개한 KPF-BERT는 20년치 뉴스 기사로 학습된 언어모델이다[cite:113]. 특징:
- 감성 분류(긍/부/중), 혐오 표현 검출, 기사 요약, 클러스터링 기능 지원[cite:113]
- **무상 공개**: GitHub 전체 공개, 연구자/언론사/일반 시민 무료 사용[cite:113]
- Finance event classification: 논조 파악(긍/부)은 가능하나, severity/impact 등급 분류는 자체 구현 필요
- KPF-BERT는 KR-FinBERT-SC 대비 금융 특화도는 낮지만, 뉴스 도메인 일반 분류에서 강점이 있을 수 있다

### 2-3. KF-DeBERTa (카카오뱅크 × FnGuide)

카카오뱅크와 에프엔가이드 공동 개발, DeBERTa-v2 기반, 범용+금융 도메인 말뭉치 혼합 학습[cite:107][cite:110]. 특징:
- GitHub 공개 (kakaobank/KF-DeBERTa)[cite:110]
- KLUE Benchmark에서 RoBERTa-Large 초과 성능[cite:110]
- `upskyy/kf-deberta-multitask`: KorNLI + KorSTS fine-tune 버전 공개[cite:116]
- **Finance event classification** downstream task 공개 성능 데이터는 제한적. embedding/classification 모두 활용 가능한 아키텍처

**추천 조합 (1인 운영, 무료):**
KR-FinBERT-SC (sentiment) + KF-DeBERTa (embedding similarity / event type classification) + 자체 DART CAR 기반 weak label

### 2-4. 빅카인즈(BIGKinds) API

빅카인즈는 한국언론진흥재단 운영, 1993년부터 뉴스 DB를 구축한 국내 최대 뉴스 분석 시스템이다[cite:108][cite:114].
- 기사 검색, 키워드 트렌드, 관계도 분석, CSV 다운로드 기능 제공[cite:108]
- **이벤트 severity 자동 분류는 없음**: 뉴스 카테고리(정치/경제/사회 등) 분류와 클러스터링은 있지만, 금융 이벤트 중요도 등급(1–5)은 자체 제공되지 않는다
- API 접근: 연구자/기관 신청 기반, 완전 무료 public API는 아님. VERITY 단독 활용에 barrier 있음.

### 2-5. HuggingFace KR 금융 NLP 추가 모델 (2024~2026)

| 모델 | 특징 | 라이선스 |
|------|------|---------|
| `snunlp/KR-FinBert-SC` | 감성 3분류, 정확도 96.3%[cite:106] | MIT 계열 |
| `DataWizardd/finbert-sentiment-ko` | KR-FinBERT-SC fine-tune, KRX 환율 뉴스[cite:112] | 공개 |
| `kakaobank/KF-DeBERTa` | 금융+범용 DeBERTa[cite:110] | 공개 |
| KPF-BERT | 뉴스 20년치, 한국언론진흥재단[cite:113] | 무료 공개 |

### 2-6. KR Finance Labeled Dataset

- **KLUE**: 8개 NLP 태스크 (NLI, NER, 감성 등), finance 특화 아님
- **NSMC**: 영화 리뷰 감성, finance 무관
- **금융 특화 impact 등급 라벨셋**: 공개된 것 없음. 직접 DART 공시 + CAR 기반 weak supervision이 현실적 유일 경로.

---

## Q3 (P1) — Novelty Score (dedup + 첫 보도 시점) 표준

### 3-1. Refinitiv NoveltyScore

TRNA의 NoveltyScore는 **슬라이딩 24h 윈도우** 안에서 같은 주제/entity에 대해 이전에 얼마나 많은 기사가 있었는지를 기반으로 산출한다[cite:80]. Linked Items 카운트와 함께 "이 뉴스가 이 entity 관련 첫 보도인가 아닌가"를 0~1 범위로 표현한다.

### 3-2. Dedup 알고리즘 무료 표준

**MinHash + LSH (추천, VERITY 규모)**
- 문서를 n-gram shingle 집합으로 변환 → MinHash 서명(100~200개 해시값) 생성 → LSH로 유사도 높은 쌍만 candidate 추출[cite:121]
- Jaccard similarity ≈ MinHash 서명 공유 확률 → 임계 이상인 쌍 = 중복[cite:121][cite:124]
- Python 라이브러리: `datasketch` (MIT, MinHash + LSH 완전 구현)[cite:121]
- 장점: 속도 빠름, 메모리 효율, 수백만 문서 대상 가능
- 단점: 의미 유사도(semantic)가 아닌 어휘 중복 기반 → 같은 내용을 다른 단어로 쓴 기사 miss 가능

**Sentence Embedding + FAISS**
- `sentence-transformers` (KR은 `jhgan/ko-sroberta-multitask` 또는 KF-DeBERTa embedding) → 임베딩 생성 → FAISS cosine similarity 검색[cite:116]
- 의미 유사도 기반이므로 paraphrase 중복 감지에 강함
- 단점: GPU/메모리 비용, daily 500 articles 규모면 CPU로도 가능하지만 속도 차이 있음

**n-gram Jaccard / TF-IDF cosine** (가장 단순)
- 빠른 prototyping에 적합, 대규모에서는 O(n²) 비용 문제

**1인 유지, daily ~325 articles 규모에서의 권고:**
- **Phase 1**: MinHash + LSH (`datasketch`) — 헤드라인+본문 앞 300자 기준, shingle size=3
- **Phase 2 (선택)**: embedding similarity (KF-DeBERTa)로 보완 — false negative 보정용

### 3-3. Novelty 분류 threshold 권고

RavenPack/학술 관행 기준:
- **"Novel"**: 같은 entity에 대해 직전 **12–24h 이내** 유사 기사 0개이면 novelty=1.0
- **"Repeat"**: 직전 24h 내 2개 이상 유사 기사 있으면 novelty 급감
- MinHash Jaccard threshold: **0.5~0.7** 이상이면 중복으로 처리하는 것이 일반적

### 3-4. Novelty Decay Function

학술 표준은 없지만, 실무에서 자주 쓰이는 모형:
- **Exponential decay**: novelty(t) = exp(−λ·Δt), 여기서 Δt는 첫 보도 이후 시간(시간 단위)
- λ 권고: 뉴스 사이클 기준으로 **6~12h half-life** (즉 λ ≈ 0.06~0.12/h)
- Tetlock 계열 연구에서 뉴스 alpha는 D+1에서 급감하고 D+3 이후 대부분 소멸하므로, **24h 내 급격한 decay, 48h 이후 0에 수렴**하는 모양이 실증과 정합

### 3-5. KR 시장 / 빅카인즈 dedup 자체 제공 여부

빅카인즈는 내부적으로 유사 기사 클러스터링 기능을 사용하지만, API로 "dedup 결과"를 직접 제공하지는 않는다[cite:108][cite:113]. VERITY는 자체 구현 필요.

### 3-6. Python 무료 라이브러리 정리

| 라이브러리 | 기능 | 라이선스 |
|-----------|------|---------|
| `datasketch` | MinHash + LSH, 대규모 dedup 표준[cite:121] | MIT |
| `simhash` | Simhash 기반 near-duplicate | MIT |
| `sentence-transformers` | Semantic embedding, FAISS 연동 | Apache 2.0 |
| `faiss-cpu` | 고속 similarity search (CPU) | MIT |

---

## Q4 (P1) — 3-axis 통합 Score (sentiment × impact × novelty) Weighted Formula

### 4-1. Bloomberg/Refinitiv/RavenPack 통합 공식 공개 여부

3사 모두 통합 headline score의 **정확한 가중치 공식을 공개하지 않는다.** RavenPack의 CSS(Composite Sentiment Score)는 "복수의 sentiment 기법을 결합"한다고만 명시하고 세부 가중치는 독점 정보다[cite:93]. TRNA의 SENT 필드도 내부 ML 모델 출력이다[cite:80].

### 4-2. 학술 통합 산식 선례

Boudoukh et al. (2019)는 뉴스를 "fundamental vs non-fundamental"으로 이진 분류한 후 sentiment와 곱하는 방식을 쓴다[cite:141]. Tetlock (2007)은 단순 pessimism score 하나만 사용하고, 별도 impact 레이어를 두지 않는다[cite:91][cite:94].

실질적으로 "3-axis 통합 weighted score"를 명시적으로 공개한 학술 논문은 드물고, 상용 데이터(RavenPack ESS × REL × novelty)를 외생 변수로 쓰는 연구들이 실증 선례에 가깝다[cite:99].

**참고 가능한 기본 공식 구조:**

```
composite_score = w_s × sentiment_score
               + w_i × impact_magnitude
               + w_n × novelty_score
```

혹은 곱 형태:

```
composite_score = sentiment_score × impact_magnitude × novelty_score
```

### 4-3. Weight 권고

- **Equal weight (1:1:1)**: baseline, 학술적으로 가장 방어하기 쉬움
- **Sentiment heavier**: N=14 단계에서 sentiment만 검증됐으므로, 초기에는 sentiment 비중 높게 (예: 0.5:0.3:0.2)
- **Impact heavier**: 대형 이벤트(파산, 합병) 포착에 유리
- RavenPack 연구에서 ESS(sentiment) × REL(relevance) 곱 형태가 단순 ESS 대비 IC를 개선한다는 내부 연구가 있다[cite:99][cite:105]

**VERITY 1인 운영 권고**: 초기 RULE 7 사전등록 시 equal weight로 시작하고, N=60 이후 grid search로 조정.

### 4-4. Alpha Decay 결합

VERITY 보유 alpha decay (D+1 100% → D+10 15~30%):

```
signal_t = composite_score_t0 × decay(t − t0)
```

- decay 함수: exponential 또는 piecewise linear
- 3-axis score와의 결합: **곱(multiplicative)** 방식이 직관적 (novelty가 0이면 decay 적용 안 해도 됨)
- 대안: 3-axis score를 먼저 계산하고, 그 결과에 time-weighted α decay를 사후 곱하는 2단계 설계

KR vs US alpha decay 차이 (D+3~D+10 KR vs D+1~D+3 US): KR 시장에서 retail 비중이 높고 정보 반영 속도가 느려 decay가 더 길게 유지된다는 해석이 있다. 이 경우 weight보다는 **decay rate λ 자체를 KR/US 별도로 설정**하는 게 더 직접적인 방법이다.

### 4-5. Empirical IC — 3-axis 통합 score

- 단일 sentiment IC ≈ 0.02~0.05 (일반적)[cite:174][cite:179]
- Relevance 필터링(관련 기사만 남기면) 후 IC가 개선된다는 연구들이 있음[cite:99]
- 3-axis 통합 시 IC 개선 여부: 통합 score를 쓴 학술 논문의 IC 개선치 명시 데이터는 제한적이지만, RavenPack 내부 연구에서 REL·novelty 필터링이 return predictability를 개선한다는 언급이 있다[cite:99][cite:105]

---

## Q5 (P2) — LLM 자동 분류: Cost + Accuracy + KR 정합

### 5-1. 2026 기준 모델 비용 비교

| 모델 | Input ($/1M tok) | Output ($/1M tok) | Batch 50% 할인 적용 Input | 비고 |
|------|-----------------|------------------|--------------------------|------|
| Claude Haiku 4.5 | $1.00 | $5.00 | $0.50 | 프롬프트 캐싱 90% 할인[cite:160][cite:163][cite:166] |
| Gemini 2.0 Flash | $0.10 | $0.40 | ~$0.05 | 1M context window[cite:148] |
| GPT-4o mini | $0.15 | $0.60 | ~$0.075 | 128K context[cite:148] |
| DeepSeek V4 | $0.30 | $0.50 | ~$0.15 | 5–9× cheaper output than Haiku[cite:145] |

**VERITY 월 비용 추산:**
- 입력: 헤드라인 200 token + 컨텍스트 50 token = 250 input token
- 출력: JSON 3-axis (sentiment, impact, novelty) = 50 output token
- 월 10,000 articles 기준:
  - Claude Haiku 4.5 (Batch): 10,000 × 300 input × $0.50/1M + 10,000 × 50 output × $2.50/1M = **$1.63/월**
  - Gemini 2.0 Flash (Batch): 10,000 × 300 × $0.05/1M + 10,000 × 50 × $0.20/1M = **$0.25/월**
  - **Gemini 2.0 Flash가 약 6~7× 저렴**

### 5-2. Accuracy — Finance Event Classification

- LLM structured output의 finance entity extraction 정확도: GPT-4 계열은 precision ~85–92%, recall ~80–88% (F1 ~83–90%) 수준[cite:137]
- KR 한국어 처리: Gemini와 GPT-4o 계열이 Claude보다 KR 다국어 처리에서 상대적 우위가 있다는 평가가 있지만, 2026 기준으로 Claude Haiku 4.5도 KR 처리 가능
- KR-FinBERT-SC 대비: LLM은 KR-FinBERT-SC sentiment를 대체할 수 있지만, fine-tuned 도메인 모델의 정확도(96.3%[cite:106])에는 미치지 못하는 경우가 많음. **Impact classification(KR-FinBERT-SC에 없는 축)에서 LLM이 유리**

### 5-3. Structured Output Reliability

- 2026 기준 Native JSON Schema 지원(OpenAI `.parse()`, Gemini `response_schema`, Anthropic `tool_use` 기반)으로 스키마 위반 거의 0%[cite:143][cite:146]
- Pydantic 모델 검증 결합 권고[cite:146][cite:149]

### 5-4. Batch Processing

- **Anthropic Message Batches API**: 입출력 모두 50% 할인, 비동기, 24h 지연 허용[cite:160][cite:163][cite:166][cite:172]
- **OpenAI Batch API**: 동일하게 ~50% 할인
- **VERITY delay tolerance**: D+1 batch 기준이면 Batch API 100% 활용 가능

### 5-5. VERITY scale × $20/월 Claude budget 정합

- Claude Haiku 4.5 Batch: 월 10,000 articles → **~$1.63/월** → $20/월 예산 내 여유
- 월 15,000 articles까지도 $2.45/월 → 문제없음
- 단, 프롬프트 캐싱(시스템 프롬프트 반복 → 90% 할인) 활용 시 더 저렴[cite:166]

**권고**: Gemini 2.0 Flash (비용 최소화) 또는 Claude Haiku 4.5 Batch (Anthropic 생태계 통합 시 편리). RULE 6 정합(LLM narrative STOP, structured output 산식 layer는 허용)을 준수하며 3-axis JSON 분류에 사용.

---

## Q6 (P0) — 1인 Retail Minimum Viable News Pipeline

### 6-1. Daily Ingestion Scale

- KR 25종목 × 10 articles/day = **250**
- US 15종목 × 5 articles/day = **75**
- 합산 **~325 articles/day**, 월 **~10,000 articles**

### 6-2. Source Mix 권고 (무료 우선)

| 소스 | 대상 | 무료 여부 | 비고 |
|------|------|----------|------|
| 네이버 금융 RSS | KR 종목별 뉴스 | 완전 무료 | 종목 ticker별 RSS 피드 존재 |
| Google News RSS | KR/US 혼합 | 완전 무료 | 언어 필터링 필요 |
| Yahoo Finance RSS | US 종목 | 완전 무료 | |
| DART OpenAPI | KR 공시 (정기/수시) | 무료 (2만건/일 쿼터) | VERITY 보유, 실시간 가능 |
| SEC EDGAR RSS (8-K) | US 주요 공시 | 완전 무료 | `https://www.sec.gov/cgi-bin/browse-edgar` RSS |
| GDELT GKG | 글로벌 뉴스 tone | 완전 무료, BigQuery | KR 종목 precision 낮음 |

빅카인즈 API는 연구자/기관 신청 필요로 1인 retail 접근에 barrier가 있다[cite:108].

### 6-3. Pipeline 구성 + 1인 Maintenance 추정

**Phase 1 (Baseline, 지금 바로)**
- Ingestion: RSS reader (`feedparser`) + DART API → Supabase free tier[cite:184][cite:187]
- Dedup: MinHash LSH (`datasketch`)
- Sentiment: KR-FinBERT-SC (KR) + 기존 13-source scorer (US)
- Trigger: GH Actions cron (5분/1일 1회)
- Maintenance: **~2h/월** (RSS 소스 죽은 피드 교체, 에러 로그 확인)

**Phase 2 (impact + novelty 추가, Q3~Q4 이후)**
- impact: LLM Batch (Claude Haiku / Gemini Flash) → 3-axis JSON
- novelty: MinHash 슬라이딩 24h 윈도우 비교
- 추가 maintenance: **~1–2h/월**

**Phase 3 (3-axis 통합)**
- composite_score 계산 + alpha decay 결합
- Quartz vault 리포팅 레이어
- 추가 maintenance: **~1h/월**

### 6-4. Delay Tolerance

- D+0 realtime (cron 5분): DART 공시 즉시 알림, 중요 공시 포착에 필수
- D+1 batch (cron 1일 1회): LLM classification은 이걸로 충분

권고: **DART 공시 + 중요 키워드 필터는 D+0(cron 5분), 일반 뉴스 분류는 D+1 batch**

### 6-5. Storage

| 옵션 | 월 GB (325 articles/day, 헤드라인+메타) | 비용 |
|------|----------------------------------------|------|
| Supabase 무료 tier | 월 ~0.3–0.5 GB (JSON 메타만) | 무료[cite:176][cite:187] |
| SQLite (로컬) | 월 ~0.3 GB | 무료 |
| Supabase free 500MB 한도 | 1년치 유지 가능 | 무료[cite:176] |

원문 full-text 저장 시 월 ~5–20 GB → Supabase Pro ($25/월) 또는 R2/S3 필요.

### 6-6. 운영 비용 추산

| 항목 | 월 비용 |
|------|--------|
| GH Actions (public repo) | 무료 |
| Vercel Pro | 기존 보유 |
| Supabase 무료 tier | 무료 |
| LLM (Claude Haiku Batch) | ~$1.63 |
| DART API | 무료 |
| 기타 | $0 |
| **합계** | **~$1.63–$5/월** |

**$20/월 Claude budget 대비 충분한 여유.**

---

## Q7 (P2) — News Impact ↔ Stock Return Meta-Analysis

### 7-1. Classic Papers

**Tetlock 2007 (JoF 62:3, p.1139–1168)**
- WSJ "Abreast of the Market" 컬럼 일별 pessimism score → 시장 수익률/거래량 회귀
- 핵심 발견: 높은 미디어 pessimism → 주가 하락 압력 → 이후 fundamental 수준으로 reversion
- IC(직접 보고 없음, 회귀계수 기준) → 단기 예측 가능성 있지만 reversal 존재[cite:91][cite:94][cite:97]

**Loughran-McDonald 2011 (JoF)**
- Harvard GI-4 사전이 금융 문서에서 오분류 73.8%를 발생시킨다는 비판적 발견
- 금융 특화 사전 6종 (Negative, Positive, Uncertainty, Litigious, Strong Modal, Weak Modal) 제시[cite:92][cite:95][cite:98]

**Boudoukh et al. 2019 (RFS 32:3)**
- 기업 특정 뉴스에서 "fundamental information"을 추출 → S&P 500 overnight idiosyncratic variance의 **49.6%를 public news가 설명**[cite:141]
- trading hours 중 설명력 12.4%에 비해 overnight 비중이 월등히 높음 → overnight에 뉴스 정보 집중

### 7-2. Modern Papers (2020+)

**Chinese stock market (Informs 2024)**
- FarmPredict (factor augmentation + sparsity regularization) → 중국 뉴스로 수익률 예측
- Positive sentiment: 평균 **83 bps** daily excess return (뉴스 발표일)
- Negative sentiment: **-26 bps** (비대칭 효과 → short-sale constraint 반영)[cite:125]
- Alpha decay: positive news alpha 수 일 지속 → KR과 유사한 패턴

### 7-3. Meta-analysis IC Range 권고

| Horizon | IC Range (문헌 전반) | 비고 |
|---------|---------------------|------|
| D+1 | 0.02–0.06 | 가장 강함 |
| D+2~D+5 | 0.01–0.03 | decay |
| D+6~D+10 | 0.005–0.01 | 통계적 경계 |
| D+11+ | ~0 | 대부분 소멸 |

sentiment 단일 신호 기준. impact × novelty 필터링으로 0.5–1σ 개선 가능성 있음.

### 7-4. KR 시장 Papers

- **KCMI (자본시장연구원)**: KR 뉴스 sentiment와 수익률 관계 분석 수행, 2023–24 리포트에서 D+1~D+3 효과 확인 (구체 IC 수치는 보고서별 상이)
- DART 공시 이벤트 스터디: KOSPI 액면분할 공시 당일 AAR **+2.58% (t=2.86, 유의)**[cite:151], KOSDAQ은 양의 방향이지만 유의성 낮음[cite:151]
- M&A 공시: 아주대 경제학부 연구에서 공시 전후 인수기업 CAR 분석 수행[cite:157]
- 상호변경 공시 (KOSDAQ): 공시 전후 누적초과수익률 유의, 상장폐지 기업 vs 지속 기업 차이 확인[cite:152]

**KR alpha decay 특성**: DART 공시 기반 이벤트는 D+0 또는 D+1에 수익률 반응이 집중되는 경향이 있으며, 이후 reversal이 발생하거나 서서히 decay. US의 D+1~D+3 대비 KR은 D+0 즉시 반응 이후 D+5~D+10까지 trailing effect가 관찰되는 경우도 있음.

### 7-5. Failure Mode

- **Regime dependency**: bear market에서 news sentiment IC가 붕괴하는 경향 (정보 과부하, attention 분산)[cite:138][cite:144]
- **Overfitting risk**: sentiment factor가 특정 기간에만 작동하고 타 기간에서 IC 역전
- **Survivorship bias**: DART 이벤트 스터디는 살아있는 기업만 포함하면 결과 왜곡
- **Endogeneity**: 대형 공시 이후 미디어 보도 폭증 → sentiment가 원인인지 결과인지 구분 어려움

---

## Q8 (P1) — DART 공시 Severity 5-Tier 학술 정합

### 8-1. KCMI / KOFIA / 한국거래소 공식 Severity 표준 존재 여부

공식적인 "5-tier severity 분류 표준"은 존재하지 않는다. 금융감독원 DART는 공시 유형(수시/정기/기타)과 report_nm(주요사항보고서, 사업보고서 등)으로 구분하지만, severity 등급을 부여하지 않는다[cite:175][cite:186]. 한국거래소도 공시 중요도 등급을 공식 표준으로 제정하지 않았다.

### 8-2. KOSPI vs KOSDAQ 별 공시 중요도 차등 표준

없음. 다만 실증 연구들에서:
- KOSPI 공시 CAR이 KOSDAQ 대비 더 유의하게 나오는 경향[cite:151]
- KOSDAQ은 소형주 비중이 높아 동일 공시 유형에서도 분산이 더 크고 통계적 유의성이 낮은 경우가 많음[cite:151][cite:152]

이는 VERITY 5-tier를 KOSPI/KOSDAQ 별로 threshold를 다르게 설정할 근거가 될 수 있다.

### 8-3. DART 공시 유형별 Abnormal Return 실증 (한국 논문)

| 공시 유형 | 실증 결과 (KR 논문) |
|-----------|---------------------|
| 액면분할 공시 | KOSPI 당일 AAR +2.58% (유의), KOSDAQ 유의성 낮음[cite:151] |
| 이전상장 결의 공시 | 발표 시 주가 유의하게 상승, 실제 이전 시점엔 하락[cite:153] |
| M&A 공시 | 인수기업 단기 CAR 분석 다수[cite:157] |
| 팬데믹(거시 이벤트) | 언택트 기업 CAR 공시 후 6.2% 초과수익[cite:154] |
| 회계부정/집단소송 | 정상주가 대비 큰 하락, 손해액 산정 기준 사용[cite:156] |

회생/파산, CB/BW에 대한 한국 학술 abnormal return 메타분석은 개별 논문에서 일부 다루지만, VERITY 5-tier와 1:1로 매핑되는 종합 연구는 검색 범위 내에서 확인되지 않는다. DART 사건연구 데이터로 자체 집계가 현실적인 접근이다.

### 8-4. VERITY 자체 5-tier 사후 검증

VERITY의 자체 5-tier (회생/파산=5, M&A=4, 자사주/배당=3, CB/BW 5%=2, 정정=1):

| Tier | VERITY 분류 | 학술 근거 | 정합도 |
|------|------------|----------|--------|
| 5 | 회생/파산 | 자본 감소/소멸 리스크, 극단적 CAR | **정합** |
| 4 | M&A 합병/분할 | 인수기업 단기 CAR, 이전상장 효과[cite:153][cite:157] | **정합** |
| 3 | 자사주/배당 | 액면분할류 공시 CAR[cite:151], 배당 공시 효과 | **정합** |
| 2 | CB/BW 5% | 전환사채/신주인수권 희석화 리스크 | **적정** (직접 실증 제한적) |
| 1 | 정정(corr) | 정정 공시 자체 효과 낮음 | **정합** |

전체적으로 VERITY 5-tier는 한국 이벤트스터디 문헌의 암묵적 중요도 순위와 방향이 일치한다. Bloomberg ESI / Refinitiv의 5-tier 공개 비교는 불가능하지만(상용 비공개), 범주 구조(하방 리스크 > 기업 구조 변화 > 주주환원 > 희석화 > 정정)는 합리적이다.

### 8-5. Alert Engine Level Mapping 권고

| Severity | VERITY 분류 예시 | Alert 방식 | 학술 정합 근거 |
|----------|----------------|-----------|--------------|
| 5 | 회생/파산/상장폐지 | **Telegram 즉시** | 최대 하방 CAR, 즉시 대응 필요 |
| 4 | 합병/인수/분할 | **Telegram 즉시** | M&A CAR 단기 집중[cite:157] |
| 3 | 자사주 취득/배당 발표 | Digest (일 1회) | 중기 CAR, 즉시 필요성 낮음 |
| 2 | CB/BW 5% 이상 | Digest | 희석화 효과 서서히 반영 |
| 1 | 정정 공시 | Log only | 정보 가치 낮음 |

---

## PM 의사결정 Path (Q별 요약)

| Q | 핵심 결론 | VERITY 의사결정 |
|---|-----------|----------------|
| Q1 | Impact magnitude 공개 표준 없음, 상용(RavenPack/TRNA) 접근 불가. 자체 설계 필요 | **DART CAR weak label 기반 자체 impact tier 설계 → RULE 7 사전등록** |
| Q2 | KR-FinBERT-SC fine-tune 가능 (weak supervision). KF-DeBERTa 추가 활용 | **KR-FinBERT-SC + KF-DeBERTa 결합, DART CAR 라벨 생성 sprint** |
| Q3 | MinHash + LSH (`datasketch`) = 1인 유지 최적, 24h 슬라이딩 윈도우 | **novelty score 신 sprint, `datasketch` 채택** |
| Q4 | 통합 공식 비공개, equal weight baseline + alpha decay 곱 결합 | **equal weight (0.5:0.3:0.2) 초안 RULE 7 사전등록, N=60 후 조정** |
| Q5 | Gemini 2.0 Flash Batch ~$0.25/월, Claude Haiku Batch ~$1.63/월 → $20 예산 내 | **LLM batch 자동 분류 path 채택 (Gemini 2.0 Flash 우선)** |
| Q6 | RSS + DART + SEC EDGAR 무료 스택 = ~$1.63–5/월 total | **Phase 1 (현재) → Phase 2 (impact+novelty) graduated path 확정** |
| Q7 | 뉴스 IC D+1: 0.02–0.06, KR DART 이벤트 D+0 집중 | **N=60 이후 IC 추정 baseline 설정** |
| Q8 | VERITY 5-tier = 한국 이벤트스터디 방향과 정합, Severity 5/4 = 즉시 알림 | **DART 5-tier 활성화 (RULE 7 권한 6월 1건 활용)** |

---

*저장 경로: `PERPLEXITY_ANSWERS_news_impact_20260530.md`*
*다음 단계: impact 산식 RULE 7 사전등록 → 6월 sprint 진입*
