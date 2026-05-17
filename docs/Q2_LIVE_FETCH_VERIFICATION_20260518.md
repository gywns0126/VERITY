# Q2 — Top 2 source 실호출 검증 (2026-05-18)

**Purpose** — [[feedback_real_call_over_llm_consensus]] 정합. Q2 자문 결과의 Top 3 source 추천을 시스템 룰 박기 전 실호출 1회씩 검증. R-ONE 케이스 학습 — LLM 답변은 baseline 가설, 실호출 1회가 우선.

**Scope** — KIRS (kirs.or.kr) + 한경컨센서스 (consensus.hankyung.com) robots.txt + 메인 페이지 1회 fetch.

**결론 (선요약)** — 자문 검증 결과 **부분 falsification**:
- ✅ **KIRS 적합** — robots.txt Allow + PDF 직링크 + 종목코드 검색 지원 + 응답 0.33s
- ❌ **한경컨센서스 차단** — `robots.txt: Disallow: /` 전체 차단. 자문의 "robots.txt 관대" 가 false. **자동화 scraping 불가**.
- ⏳ 미래에셋 = 미검증 (다음 phase)

---

## §1 — KIRS (kirs.or.kr) 실호출 결과

### robots.txt

```
User-agent: Yeti
Disallow: /css
Disallow: /image
Disallow: /js
Disallow: /okcert
Disallow: /uploadimg
Disallow: /batch
Allow: /
```

- **Yeti (네이버 검색봇) 만 정적 리소스 제한**. 다른 봇 (일반 crawler) 명시적 제한 없음.
- research/ 경로 = Allow ✓
- HTTP 200, response time 0.33s

### research.html 페이지 구조 (아웃소싱 보고서 list)

**검색 form**:
```html
<option value="code">종목명</option>
<option value="code2">종목코드</option>
```
→ **6자리 종목코드 직접 검색 지원** ✓

**PDF URL pattern** (실측 8건):
```
https://w4.kirs.or.kr/download/research/{YYMMDD}_{섹터}_{회사명}({종목코드})_{설명}_{발간기관}.pdf
```

실제 entries (5/7~5/14, 8건):
- `260514_소비재_질경이(233990)_..._NICE평가정보.pdf`
- `260514_산업재_태양3C(052960)_..._서울평가정보(주).pdf`
- `260514_경기관련소비재_미쥬(351020)_..._서울평가정보(주).pdf`
- `260507_커뮤니케이션 서비스_한빛소프트(047080)_..._NICE평가정보.pdf`
- `260507_IT_인티큐브(070590)_..._NICE평가정보.pdf`
- `260430_IT_슈피겐코리아(192440)_..._서울평가정보(주).pdf`
- `260430_산업재_엑사이엔씨(054940)_..._NICE평가정보.pdf`
- (8번째 truncated)

**관측**:
- 종목코드 () 안에 6자리 박힘 → regex 추출 100% 가능
- 발간기관 = NICE평가정보 / 서울평가정보(주) (외부 위탁 = "아웃소싱")
- 섹터 분류 박힘 (소비재 / 산업재 / IT / 커뮤니케이션 등)
- **주간 평균 ~5건 발간** (1주일 5/7~5/14 8건 → 월 평균 ~32건 추정)
- 한글 파일명 → URL encoding 필요

### 메뉴 구조 (5종 발견)

| 페이지 | URL | 비고 |
|---|---|---|
| 리서치 보고서 (인소싱) | `/research/research22_1.html` | **자체 발간** — 대형주 가능성 ↑ |
| 리서치 보고서 (아웃소싱) | `/research/research.html` | NICE/서울평가 위탁, 코스닥 중심 |
| 밸류업 보고서 | `/research/valueup.html` | 정부 밸류업 program 연계 |
| Research Report (영문) | `/research/research_eng.html` | 외국인 IR 용 |
| **AI 기업분석 보고서** | `/research/ai_report.html` | **신규** — AI 자동 생성, 커버리지 ↑ 가능 |
| 기업분석 (~2022.5) | `/research/tech2020_1.html` | 보관 |
| 산업분석 (~2022.5) | `/research/tech2020_2.html` | 보관 |

→ **인소싱 + AI 보고서** 2개 추가 page 도 ReportScout 보강 시 같이 박을 가치 있음.

### 운영 풀 25 종목 매칭 추정

운영 풀 KR 10 종목 (NAVER / JB금융지주 / 한국앤컴퍼니 / 클래시스 / JYP / 파마리서치 / 에스엠 / 휴메딕스 / SNT에너지 / 한텍):

- 코스피 대형 (NAVER 035420 / JB금융 175330) = 인소싱 (research22_1) 또는 자체 발간 source 우선
- 코스닥 중형 (클래시스 214150 / 파마리서치 214450 / 에스엠 041510 / 휴메딕스 200670) = 인소싱 + 아웃소싱 둘 다 cover 가능
- 코스닥 소형 (한텍 ?) = 아웃소싱 main

→ 정확 매칭률은 실 fetch 시점 검증 의무 (별 의제).

### 자동화 신호

- HTTP 200 / response time 0.33s / robots Allow ✓
- 직링크 패턴 안정 (변경 위험 낮음)
- captcha / 로그인 / WAF 흔적 없음
- rate limit 미관측 (다회 호출 검증 별 의제)
- Engineer 작업 estimate: **ReportScout 보강 ~3h** (3 page scraper + PDF download + Gemini Flash 요약)

---

## §2 — 한경컨센서스 (consensus.hankyung.com) 실호출 결과

### robots.txt

```
User-Agent : *
Disallow : /
```

→ **전체 봇 전체 경로 차단**. 자문 답변 "robots.txt 관대" 와 **정면 충돌**. HTTP 200 으로 robots.txt 자체는 응답하지만 explicit Disallow.

### 함의

- 자동화 scraping = **robots.txt 명시 위반**. 운영 cron 박을 시 IP block / 법적 risk
- [[project_vercel_deploy_spam_ticket_2026_05_13]] 학습 — 인프라/외부 service ToS 위반 = P0 risk
- 자문 = Sonar Pro 가 "관대" 라고 답변했으나 실호출 검증 결과 false

### 대안

- 사용자가 수동 다운로드 → 본 시스템에 manual ingest (운영 자동화 X)
- 또는 한경컨센서스 API/data partnership 별도 협의 (PM 비즈니스 의제)
- **자동화 source 후보에서 제외**

---

## §3 — 자문 결과 검증 점수

| Source | 자문 추천 | 실호출 결과 | 검증 결과 |
|---|---|---|---|
| ① 한국IR협의회 (KIRS) | 자동화 5/5, 무료, 소형주 | ✅ robots Allow + PDF 패턴 + 종목코드 검색 + 200/0.33s | **TRUE — 자문 정확** |
| ② 한경컨센서스 | 자동화 4/5, robots 관대 | ❌ `Disallow: /` 전체 차단 | **FALSE — 자문 falsify** |
| ③ 미래에셋증권 | 자동화 3/5, attachmentId pattern | ⏳ 미검증 | 보류 |

**검증 점수**: 2개 중 1개 정확 (50%). [[feedback_real_call_over_llm_consensus]] R-ONE 케이스 학습 재확인 — **외부 사실 자문은 baseline 가설일 뿐, 시스템 룰 박기 전 1회 실호출 필수**.

---

## §4 — Engineer 후속 작업 의제

### Tier 1 (코드 only, KIRS 활성)

| # | action | scope |
|---|---|---|
| **A2.3a** | **KIRS scraper 신설** — research.html (아웃소싱) + research22_1.html (인소싱) + ai_report.html (AI) 3 page collector | data pipeline 신설 |
| A2.3b | PDF download + 한글 파일명 URL encode 처리 | utility |
| A2.3c | report_summarizer.py 연동 — KIRS PDF → Gemini Flash 요약 → analyst_report_summary attach | 기존 pipeline 확장 |
| A2.3d | rate limit 검증 (5건 연속 fetch 후 응답 시간 변화 측정) | 검증 의무 |

### 보류

| # | action | 사유 |
|---|---|---|
| 한경 | scraper 신설 보류 | robots.txt explicit Disallow |
| 미래에셋 | attachmentId pattern crawler | A2.3 PASS 후 별도 검증 (A2.4 큐잉) |
| FnGuide API | 별도 PM 예산 의제 | 유료 ($수십 만/년 추정) |

### 보강된 fix 후보 (`COMPONENT_FALLBACK_AUDIT_20260518.md` §3 update)

- **A2 (analyst_report_summary)** = ReportScout (네이버 단일) + **KIRS 신규 3 page** 병행 collector
- 예상 효과: KR 10 종목 중 5~8 종목 hit (자문 §3 의 코스피/코스닥 분포 가정)
- Tier 2 (PM 승인) = 미래에셋 + 한국투자증권 + 키움증권 등 회원사 source 별도 audit (회원가입 자동화 부담 ↑)

---

## §5 — 변경 추적

| 일자 | 변경 |
|---|---|
| 2026-05-18 | Q2 실호출 검증 (본 doc) — KIRS PASS, 한경 FAIL, 미래에셋 보류 |

### 관련 메모리

- [[reference_learning_materials_folder]] (Q2 query/answer 인덱스)
- [[feedback_real_call_over_llm_consensus]] — 본 검증 = 정합 (자문 50% falsify)
- [[project_brain_score_funnel_audit]] (A-task 의 A2 구체화)
- [[feedback_perplexity_collaboration]] — 외부 사실 영역 정합
- [[feedback_workflow_yml_audit_mandatory]] — A2.3 cron 추가 시 6축 audit 의무

### Source data (재현)

```bash
# KIRS robots.txt
curl -s "https://kirs.or.kr/robots.txt"
# 한경컨센서스 robots.txt
curl -s "https://consensus.hankyung.com/robots.txt"
# KIRS research page (PDF URL pattern 추출)
curl -s -A "Mozilla/5.0" -L "https://kirs.or.kr/research/research.html" | \
  grep -oE 'https://w4\.kirs\.or\.kr/download/research/[^"]+\.pdf' | head -10
```

---

**End of verification. KIRS = 시스템 룰 박을 만큼 검증 완료. 한경 = 보류 (robots 위반 risk). PM 결정 — A2.3 (KIRS scraper) 진행 여부.**

---

## §6 — A2.3 박힘 후 실호출 결과 (2026-05-18 23:xx 추가)

`api/collectors/ReportScout.py` 박힘 (+ `tests/test_kirs_scraper.py` 15 tests PASS, 전체 1149 tests PASS):

### Rate limit + 추출 통계 (5 page 연속)

- outsourcing 5 page = 10 entries / 1.62s (avg 0.32s/page, degradation 없음)
- insourcing 5 page = 10 entries / 1.39s (avg 0.28s/page)
- ticker 추출: **20/20 (100%)**
- PDF URL 추출: **20/20 (100%)**
- 한글 PDF 다운로드 1건 검증: 1.27MB / 0.66s OK

### **회귀 신호 — 운영 풀 KR 10 매칭 = 0/10** ★

운영 풀 KR ticker = {214150, 035900, 214450, 041510, 100840, 035420, 200670, 175330, 000240, 098070} (KOSPI 대형 + 코스닥 중형)
KIRS 추출 ticker (20건) = {233990, 052960, 351020, 047080, 070590, 192440, 054940, 131970, 252990, ...} (코스닥 소형주 위주)

→ **매칭 0/10**. Q2 자문 §3 finding 정합 — KIRS = 코스닥 소형주 강점 + 운영 풀 (베타 N=25) = 대형/중형 위주 분포 cascade.

### 회수 의제 (COMPONENT_FALLBACK_AUDIT §3 A2 예상 효과 정정)

- 박혔던 "예상 효과: KR 10 종목 중 5~8 hit" = **false** (실호출 검증 결과)
- KIRS 진가 = **Phase 2-B universe (5,000) 확장 후 코스닥 미커버 62% 보강**. 현 N=25 운영 풀 fact_score 회복 효과 = **0건**
- 즉시 의제:
  - A2.3 = 인프라 박힘 (자산), Phase 2-B 진입 시 효과 본격화 — 보존
  - 현 N=25 풀 보강은 별 source 필요 — 미래에셋 (A2.4) / 한투 / 키움 등 회원사 source (자동화 부담 ↑) PM 의제
  - 또는 KIRS 자체가 인소싱 (대형주 보강) 늘 가능성 검증 (research22_1 더 깊이 lookback)
