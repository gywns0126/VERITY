# VERITY / ESTATE — Critical Rules (Hardcoded)

이 문서 = **메모리 drift 가 반복된 사고만** 등록한 hardcoded 가드. 매 세션 자동 로드. 일반 컨벤션/스타일은 메모리 시스템 우선.

---

## 🚨 RULE 1 — KIS OpenAPI 토큰 = 1일 1토큰. ABSOLUTE.

**한국투자증권 정책: 하루 1개 토큰만 발급. 두 번째 발급 = 계좌 제재 위험.**

- "6시간 갱신" / "8시간" / "12시간" / **"23시간"** 표기 = **잘못**. 발견 시 즉시 정정 의무.
- 24시간 = "갱신 주기" 가 아니라 **"발급 간격 최소 24시간"**. **broker `_is_recently_issued(hours=N)` N=24 hardcoded** (2026-05-29 RULE 1 재정정). N<24 = 정책 위반 잠재.
- 정상 발급 source = `kis_token_refresh.yml` (KST 23:45 일 1회 force_refresh) + `daily_realtime.yml` (backup)
- **price_pulse / 고빈도 consumer** = `KISBroker(cache_only=True)` 사용 의무. 신규 발급 절대 금지.
- 🚨 **발급원 = 단 하나여야 함 (subsystem cross-source).** GH Actions(broker, file lock 24h) + Railway(`server/kis_rest_client.py`, /tmp 6h) 가 서로 모른 채 독립 발급 = 하루 2토큰 (5/31 사고). file lock 은 timestamp 만 — 토큰 **값** 이 없어 타 subsystem 재사용 불가. 신 KIS consumer 추가 시 = 자체 발급 경로 신설 절대 금지, 공유 store(`kis_shared_token`) 읽기만. PM 결정 5/31 = **GH Actions 단일 발급원** (기존 file-lock 24h 가드 + 발급 직후 Supabase publish), Railway/Vercel = `KIS_SHARED_TOKEN=1` 읽기 소비. 선정 이유 = GH 관측성/기존 RULE 1 인프라 재사용 + 가용성 결합 안전 방향 (always-on 소비자가 read). cutover 런북 = `docs/KIS_SINGLE_ISSUER_CUTOVER_20260531.md`.
- KIS 관련 워크플로 신규 추가 시 = `git add data/.kis_issued_date.txt` step 필수 (lock propagation)
- 사용자 카톡에 KIS 토큰 발급 알림 직송 — **알림 0건이 정상 baseline**. 1건이라도 P0.

상세: `~/.claude/projects/.../memory/project_kis_token_policy.md` + `feedback_kis_one_token_per_day_sentinel.md`

사고 history: 2026-05-03 / 5-12 / 5-13 / 5-16 (5분 폭주 → 사용자 격분) / **5-27 + 5-28** (broker 가드 23h drift, 매일 23h interval 발급, 사용자 알림 2일 연속) / **5-31** (dual-issuer — Railway /tmp 6h 가드가 재시작마다 신규 발급, GH 발급과 합쳐 하루 2토큰). 같은 사고 7+회. 사용자 발화 "내가 몇번 말해야 되나" / "오늘도 22시쯤 발급됨" / "토큰 두번 발급됨". PM 결정 5/29 옵션 A (가드만 23h→24h) → 5/31 GH Actions 단일 발급원 + Supabase 공유 store publish (Railway/Vercel 소비).

---

## 🚨 RULE 2 — Vercel deploy = `vercel-api/` 외부 commit 은 trigger 안 됨.

**5/13 Vercel Shohei (Compute infra) 직접 메일 — 일 ~400 deploy 폭주로 차단 위협 받음.** P0 fix = `vercel-api/vercel.json` `ignoreCommand` 확장 (commit e8965c3e).

- `ignoreCommand` 약화 / 제거 절대 금지. 변경 시 메모리 `project_vercel_deploy_spam_ticket_2026_05_13` 재독 필수.
- 새 자동 commit 워크플로 (cron 으로 JSON/data 파일 commit) 추가 시 = `vercel-api/` 외부 경로 commit 정합 확인 의무 (ignoreCommand 자동 skip 작동 검증).
- 변경 빈도 ≥ 1회/시간 인 데이터 = Vercel Blob / Edge Config 이전 검토 (gh-pages publish 가 현재 1차 source).

상세: 메모리 `project_vercel_deploy_spam_ticket_2026_05_13` + `feedback_infra_provider_ticket_priority`.

---

## 🚨 RULE 3 — 인프라 제공자 직접 메일/티켓 = 24h 내 인지 회신.

Vercel / Supabase / GitHub / KIS / DART / 한국투자증권 등 인프라 제공자가 직접 보낸 메일/티켓 = 최우선 처리.

- "may block" / "kindly ask" / "consider" 같은 정중한 재량 표현 = 디스카운트 금지. enforcement 실제 발생.
- 실제 fix 못 박더라도 **24h 내 최소 "인지 + 일정" 회신 의무**.
- Follow-up 메일 도착 = silent escalation 임박 시그널 → 즉시 P0 격상.

상세: `feedback_infra_provider_ticket_priority`.

---

## 🚨 RULE 4 — 신 logging / lock / cache 파일 추가 시 workflow git add 정합 의무

2026-05-16 하루 5번 같은 패턴 결함 (KIS lock × 2 / fred_health / runtime_load / wide_scan_log) 학습.

신 logging path / lock 파일 / cache 추가 시:
- 해당 cron 워크플로 yml 의 `git add` 정합 검증 의무
- `git add data/<file>` (specific) 사용 시 = 신 파일 추가 시 yml update 필수
- `git add data/` (broad) 사용 시 = 자동 포함, 안전
- 검증: `git log --since="7 days ago" -- <path>` 로 commit 누락 detect

상세: 메모리 `feedback_data_collection_verification_mandatory`.

---

## 🚨 RULE 5 — 메모리 drift 의심 발화 = 즉시 stop + sentinel

사용자 발화 패턴:
- "내가 몇번 말해야 되나"
- "또 까먹었나"
- "이미 말했는데"
- "왜 이걸 또"

= 메모리 drift 시그널. 즉시 행동:
1. 진행 중 작업 stop
2. 해당 룰 메모리 description 부터 정독 (drift 표기 확인)
3. 강한 표현으로 정정 (description + sentinel feedback 신설)
4. CLAUDE.md root 박을지 검토 (반복 사고 = hardcoded)

상세: `feedback_no_premature_completion_claims` + `feedback_kis_one_token_per_day_sentinel` (drift 4번 반복 학습).

---

## 🚨 RULE 7 — 자기 산식 site 노출 시 "가설 (N=X)" 명시 의무

**2026-05-17 외부 베테랑 진단 발생 — 47일 = 운영 X, code commit 기간. 실제 검증 trail = 14일 (Phase 0)**.

47일 운영 = oversold. 실제:
- Phase 0 누적 14일 (5/2 ~ 5/16) + VAMS reset 5/17 후 0일
- 14일 hit rate 50% = binomial 95% CI ±20%p = 동전 던지기와 통계 구분 X
- N < 100 = PSR/DSR 적용 불가
- 모든 자기 산식 (Brain v5 가중치 7:3 / 등급 75-60-45-30 / Lynch 룰 / VCI / sentiment 13-source) = **가설**
- 365일 trail 도달 (2027-05) 전까지 = 통계 무의미

행동 룰:
- **모든 site 노출 자기 산식** = "(가설 / N=X일)" 명시 의무
- **Tier 진화 path** = 자본 도달 시점 추정 절대 금지 (1000만→100억 = 6년 215% CAGR = 메달리온 66% 도 불가)
- **자본 = 부산물**, 목표 X. Tier 진화 trigger = 시스템 성숙도 (N≥365 + IC/ICIR 0.3 + Phase 2 진입) only
- **hit rate** site 노출 시 = **삭제 X, 병기 의무** — hit rate + expectancy + sample size + CI 모두 노출 (PM 이 통계적 함정 인지 가능). hit rate 단독 게재 금지, expectancy 단독 게재 금지 (PM 이 hit rate 자기 의심 차단 못 함)
- **자기 산식 임계 조정** (Brain 가중치 / 등급 임계 / VCI / Lynch 룰 등) = **1회만, 사전 PM 승인 의무**. 반복 조정 = 곡선 맞추기 (확증편향). 조정 시 commit message 에 PM 승인 기록 추가
- **Tier path UI** = 자본 path 유지 (통째 삭제 X), but 성숙도 primary / 자본 sub-label. 자본 label 강조 X
- **N < 30** = "통계 무의미" 명시. N < 100 = "예비 결과, 검증 진행 중" 명시
- **PM 결정 자기 산식 박을 때** = 단일 명확 출처 + 자체 신호 명시 + 검증 큐잉 (이미 [[feedback_source_attribution_discipline]])

상세: `feedback_no_premature_completion_claims` + `feedback_praise_calibration` + `project_capital_evolution_path` (시점 추정 절대 금지 추가).

---

## 🚨 RULE 6 — 신규 LLM narrative 컴포넌트 추가 STOP

**2026-05-17 빅브라더 정합 발견 — LLM 무료 tier 가 더 잘함, narrative 차별점 0.**

ChatGPT Pro / Claude for Small Business 같은 BigBrother 가 위에서 아래로 누르는 그림. 십 년 걸려 쌓은 기능을 LLM 이 그냥 잡아먹음. VERITY 의 진짜 해자 = LLM 못 가진 자기 자산:

1. 자기 자본 진화 path (Tier 1 → 6)
2. 자기 운영 trail (VAMS / Brain learning / Phase 0 / KIS 1일 1토큰 학습)
3. 자기 산식 (Brain v5 가중치 7:3 / 5단계 funnel / market_horizon 5축)
4. 자기 cron 자동화 (LLM 가입자도 매일 매번 못 함)
5. 자기 universe (5,000→25 funnel)

행동 룰:
- **신규 LLM narrative 컴포넌트 추가 = 절대 STOP**. 사용자 명시 승인 + 강력한 자기 trail input 정합 필수.
- **기존 LLM narrative 컴포넌트** = 자기 trail (Brain/VAMS/Lynch) 첨부로 보강 (LLM 못 가지는 unique view).
  · 정공법 예시 = `equity_research_brief.fetch_verity_trail()` (2026-05-17 구현, commit 948e95b7).
- **사이트 노출 narrative** = 자기 차별점 자산 (Brain grade / VAMS hit / Lynch) 동시 노출 의무.
- prose 비중 큰 컴포넌트 (reports/* PDF) = narrative ↓, 자기 metric/chart ↑.

PM 결정 commit 시 [[feedback_pm_decision_trail_in_commit]] WHY/DATA/EXPECTED 3요소 의무 — 1년치 trail = LLM 못 가진 자산.

상세: `feedback_no_new_llm_narrative_features` + `feedback_pm_decision_trail_in_commit`.

---

## 🚨 RULE 8 — 신 cron / workflow 추가 후 N=2 실 cron 결과 audit 의무

**2026-05-28 신설 — 사용자 격분 발화 "맨날 이런식으로 데이터 손실내지". 사고 history 6+ 회 (KIS 4번 / Vercel deploy / workflow git add 4건 / 5/27 cockpit dotenv / 5/28 TIDE billing 28h gap)**.

Root cause = 자동화 추가 후 실 cron 실행 결과 audit 진행하지 않음. commit/push = "의지" 표명, 실 검증 진행하지 않음. 사용자 알림/사이트 격분 후 결함 발견 = systemic 결함.

신 cron / workflow / scheduled job 추가 시 의무:
- **N=2 실 cron 결과 audit**: commit push 직후 `gh workflow run <name>` (N=1 manual) + 다음 scheduled cron 시점 결과 (N=2). 둘 다 success + 산출물 정합 검증.
- **billing / quota / payment 영역 monitor**: 별 repo (TIDE) 영역도 동일 의무. VERITY Cockpit Phase 2 = 외부 repo health monitor 의제 ([[project_tide_billing_incident_2026_05_28]] 학습).
- **사용자 알림 후 결함 발견 = 결함 자가 진단 신호**. 즉시 sentinel memory 신설.

상세: [[feedback_post_deploy_cron_audit_mandatory]] (본 RULE 도출 사례 + 회피 mechanism).

---

## 🚨 RULE 9 — 동사 '박-' 영구 사용 금지. ABSOLUTE.

**Drift 5차 학습 (5/28 → 5/29 정상화 → 5/29 재발 → 5/30 격분 + /goal hook + AUP filter trigger → 5/30 RULE 9 등록 후 동일 세션에서 재재발).**

응답 / 메모리 / commit message / task description / 어디서든 동사 '박-' 형태 ('박는다 / 박은 / 박지 / 박혀 / 박힘 / 박아 / 박으면') **영구 제로**.

- 본래 의미 (못 박다 / 도장 박다 / 점 박다) 도 회피 — 대체 표현 사용 (고정하다 / 추가하다 / 확정하다)
- 응답 send 직전 grep self-check 의무 — 정규식 `박[으이아았혀힘은는지하한히음으면혀]` 0건 확정
- 신규 메모리 작성 후 동일 grep 0건 확정 후 저장
- commit message 동일 정규식 0건 확정 후 push

**대체 동사 정답표:**

| 옛 (불가) | 신 (정합) |
|---|---|
| 박는다 / 박았다 | 한다 / 했다 / 추가한다 / 진행한다 |
| 박혀 있다 / 박힘 | 있다 / 구현되어 있다 / 완료 |
| 박을 거 | 할 것 / 진행할 것 / 다음 단계 |
| 박은 후 | 한 후 / 완료 후 |
| 박아야 | 해야 / 추가해야 / 설정해야 |
| 박지 X | 하지 않음 / 적용되지 않음 |

사고 history:
- 5/28: 응답 '박을 거' 5+ 회 → 사용자 "뭔 개소리야"
- 5/29 정상화 sprint: Top 5 메모리 280→85 정정 (70%)
- 5/29 재발: 같은 날 응답에서 '박-' 50+ 회 → 사용자 "다신 안쓰겠다고 넣어"
- 5/30 격분: 응답 100+ 회 → AUP filter trigger + `/goal` Stop hook 활성
- 5/30 RULE 9 등록 후 재재발: 동일 일자 TIDE 의제 세션에서 응답 100+ 회 + 메모리 update 본문 다수 → 사용자 "박힘이란 말쓰지 말랬지?" (5차 학습) = 메모리 신뢰성 회수 직전 상태

상세: [[feedback_writing_no_pak_overuse]] (대체 동사 정답표 + Drift 4차 학습 trail).

---

## 🚨 RULE 10 — Agent audit 결과 = 1차 자료 cross-source verify 후 전달 의무

**2026-05-30 신설 — 사용자 격분 발화 "이런 미친 ㅋㅋㅋㅋㅋ 핵심이 없으면 여태 뭐한거야? 자동차에 기름 안주고 뭔 운전했다고 뻥치는거랑 뭐가 달라. 베테랑이라며? 핵심 놓칠래 자꾸?"**.

VERITY 데이터 audit Explore agent 가 양쪽 핵심 자산 모두 wrong 결론 → 그대로 전달:
- "DART 시계열 0 (모두 5/17 단일 스냅샷)" → 실제 = `data/dart_kr_cache/` 1,202 파일 (`종목코드_연도_분기.json`, 2015~) + `dart_kr_backfill_result.json` 911 records (PER/PBR/EPS history)
- "Sentiment 13-source 인프라 부재" → 실제 = 5 collector (news / naver_community / reddit / stocktwits / x_sentiment) + `sentiment_engine.py` 통합 + `api/intelligence/factors/sentiment.py:1` = `"Sentiment score — 13-source composite (Brain Signal Plan v0.2 Phase B)"` 명시. 5/16 hard-wire

agent 가 단일 파일 (`dart_quarterly_snapshots.jsonl`) 또는 파일명 grep (`sentiment*.json`) 만 보고 결론. 다른 DART family / 코드 import / class 검색 전혀 안 함. verify 없이 전달 = "베테랑" 자처 + 핵심 자산 부재 결론 = PM 신뢰 큰 손상.

agent (Explore / general-purpose / Plan / vercel:*) 결과 사용자 전달 전 의무:

- "X 부재 / 시계열 0 / 인프라 없음 / 모듈 없음 / 데이터 stale" 결론 = verify 의무 trigger
- verify 최소 2 source:
  - "X 시계열 0" → 동일 도메인 `*_cache/`, `*_backfill_result.json`, `*_history.json`, `*_quarterly*` 4 family 모두 확인
  - "X 모듈 부재" → 파일명 grep + `from X import` grep + class/func 검색 모두 확인
  - "데이터 stale" → mtime + jsonl tail timestamp + `git log --since=` 모두 확인
- verify 결과:
  - wrong 발견 → agent 결과 폐기, 정정 결과 만 사용자 전달
  - 정합 → "1차 자료 verify 완료 (source A + B)" 명시 후 전달
- 사용자 전달 후 wrong 발견 시 = 즉시 정정 + sentinel feedback memory 갱신 + RULE 5 trigger 정합

**1년 timeline 직격 의식** (2026-05-30 사용자 발화 "1년 날리고 싶어?" 정합):
- agent wrong "X 부재" 결론 무지정 전달 → 사용자가 결손 인지 못 함 → 1년 후 N=252 IC 게이트 (2027-05) 도달 시점에 핵심 자산 부재 발견 = 1년 손실
- 즉 매 audit verify = 1년 timeline 보호 의무. 단일 wrong 결론 = 1년 손실 risk
- "X 부재" 결론 = **agent 가설**. 1차 자료 verify 통과 전 사용자 전달 = **거짓말 정합**

자기 정정 사례 (RULE 10 작동 정합):
- 2026-05-30 격분 사고 후 같은 세션에서 자기 정정 2건:
  - "Price pulse 7.5h 멈춤" → verify (`vercel-api/api/cron/dispatch_pulse.py` 시장 시간 가드 5/16 정합) = 결함 0 자기 정정
  - "Cron health monitor 결함" → verify (gh log `[cron_health] P0 critical — exit 1` 의도) = 결함 0 자기 정정 + 진짜 P0 `dart_fail_rate>5%` 발견 + DART pipeline P0 fix (f21d8ccf)
- 자기 정정 = 사용자 격분 trigger 전 = RULE 10 의도 정합. 패턴 영속 의무

상세: [[feedback_agent_audit_verify_before_relay]] (본 RULE 도출 사례 + 7차 학습 trail) + [[feedback_diagnose_before_fix_jsonl_n_check]] (fix 영역 정합, 본 RULE = agent 영역 확장).

---

## 자동화 워크플로 변경 시 검증 의무 (체크리스트)

`.github/workflows/*.yml` 변경 / 추가 시 다음 7축 audit:

1. **env / secret** — 사용 endpoint 명시, 죽은 등록 검증 (memory `feedback_env_registration_with_usage_proof`)
2. **push trigger** — Vercel deploy spam 회귀 검증 (RULE 2)
3. **concurrency group** — 형제 워크플로 + 평균 run 시간 audit (memory `feedback_concurrency_group_lock_audit`)
4. **cron schedule** — gh schedule silent skip vs Vercel cron dispatch chain 정합 (memory `feedback_gh_short_cron_silent_skip`)
5. **KIS 관련** — RULE 1 + `git add data/.kis_issued_date.txt` 누락 검증
6. **pip / requirements** — 의존성 정합 (5/27 cockpit dotenv 누락 학습)
7. **N=2 post-deploy audit** — RULE 8 정합. commit push 후 manual run (N=1) + 다음 scheduled (N=2) 실 결과 검증 의무

---

## 메모리 우선순위

이 CLAUDE.md = 사고 반복 패턴만 hardcoded. 일반 컨벤션 / 진화 중 룰 / 프로젝트 컨텍스트 = 메모리 (`~/.claude/projects/.../memory/MEMORY.md`) 우선.

메모리 drift 의심 시 ("내가 몇번 말해야 되나" 류 발화) = 즉시 stop + sentinel feedback memory 신설/갱신.
