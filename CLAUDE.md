# VERITY / ESTATE — Critical Rules (Hardcoded)

이 문서는 **메모리 drift 가 반복된 사고만** 박는 hardcoded 가드입니다. 매 세션 자동 로드. 일반 컨벤션/스타일은 메모리 시스템 사용.

---

## 🚨 RULE 1 — KIS OpenAPI 토큰 = 1일 1토큰. ABSOLUTE.

**한국투자증권 정책: 하루 1개 토큰만 발급. 두 번째 발급 = 계좌 제재 위험.**

- "6시간 갱신" / "8시간" / "12시간" / **"23시간"** 표기 = **잘못**. 발견 시 즉시 정정 의무.
- 24시간 = "갱신 주기" 가 아니라 **"발급 간격 최소 24시간"**. **broker `_is_recently_issued(hours=N)` N=24 hardcoded** (2026-05-29 RULE 1 재정정). N<24 = 정책 위반 잠재.
- 정상 발급 source = `kis_token_refresh.yml` (KST 23:45 일 1회 force_refresh) + `daily_realtime.yml` (backup)
- **price_pulse / 고빈도 consumer** = `KISBroker(cache_only=True)` 사용 의무. 신규 발급 절대 금지.
- KIS 관련 워크플로 신규 추가 시 = `git add data/.kis_issued_date.txt` step 필수 (lock propagation)
- 사용자 카톡에 KIS 토큰 발급 알림 직송 — **알림 0건이 정상 baseline**. 1건이라도 P0.

상세: `~/.claude/projects/.../memory/project_kis_token_policy.md` + `feedback_kis_one_token_per_day_sentinel.md`

사고 history: 2026-05-03 / 5-12 / 5-13 / 5-16 (5분 폭주 → 사용자 격분) / **5-27 + 5-28** (broker 가드 23h drift, 매일 23h interval 발급, 사용자 알림 2일 연속). 같은 사고 6+회. 사용자 발화 "내가 몇번 말해야 되나" / "오늘도 22시쯤 발급됨". PM 결정 5/29 옵션 A (가드만 23h→24h, cron schedule 변경 보류).

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

**2026-05-17 외부 베테랑 진단 박힘 — 47일 = 운영 X, code commit 기간. 실제 검증 trail = 14일 (Phase 0)**.

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
- **hit rate** site 노출 시 = **삭제 X, 병기 의무** — hit rate + expectancy + sample size + CI 모두 노출 (PM 이 통계적 함정 인지 가능). hit rate 단독 박음 금지, expectancy 단독 박음 금지 (PM 이 hit rate 자기 의심 차단 못 함)
- **자기 산식 임계 조정** (Brain 가중치 / 등급 임계 / VCI / Lynch 룰 등) = **1회만, 사전 PM 승인 의무**. 반복 조정 = 곡선 맞추기 (확증편향). 조정 시 commit message 에 PM 승인 기록 박음
- **Tier path UI** = 자본 path 유지 (통째 삭제 X), but 성숙도 primary / 자본 sub-label. 자본 label 강조 X
- **N < 30** = "통계 무의미" 명시. N < 100 = "예비 결과, 검증 진행 중" 명시
- **PM 결정 자기 산식 박을 때** = 단일 명확 출처 + 자체 신호 명시 + 검증 큐잉 (이미 [[feedback_source_attribution_discipline]])

상세: `feedback_no_premature_completion_claims` + `feedback_praise_calibration` + `project_capital_evolution_path` (시점 추정 절대 금지 추가).

---

## 🚨 RULE 6 — 신규 LLM narrative 컴포넌트 추가 STOP

**2026-05-17 빅브라더 정합 박힘 — LLM 무료 tier 가 더 잘함, narrative 차별점 0.**

ChatGPT Pro / Claude for Small Business 같은 BigBrother 가 위에서 아래로 누르는 그림. 십 년 걸려 쌓은 기능을 LLM 이 그냥 잡아먹음. VERITY 의 진짜 해자 = LLM 못 가진 자기 자산:

1. 자기 자본 진화 path (Tier 1 → 6)
2. 자기 운영 trail (VAMS / Brain learning / Phase 0 / KIS 1일 1토큰 학습)
3. 자기 산식 (Brain v5 가중치 7:3 / 5단계 funnel / market_horizon 5축)
4. 자기 cron 자동화 (LLM 가입자도 매일 매번 못 함)
5. 자기 universe (5,000→25 funnel)

행동 룰:
- **신규 LLM narrative 컴포넌트 추가 = 절대 STOP**. 사용자 명시 승인 + 강력한 자기 trail input 정합 필수.
- **기존 LLM narrative 컴포넌트** = 자기 trail (Brain/VAMS/Lynch) 첨부로 보강 (LLM 못 가지는 unique view).
  · 정공법 예시 = `equity_research_brief.fetch_verity_trail()` (2026-05-17 박힘, commit 948e95b7).
- **사이트 노출 narrative** = 자기 차별점 자산 (Brain grade / VAMS hit / Lynch) 동시 노출 의무.
- prose 비중 큰 컴포넌트 (reports/* PDF) = narrative ↓, 자기 metric/chart ↑.

PM 결정 commit 시 [[feedback_pm_decision_trail_in_commit]] WHY/DATA/EXPECTED 3요소 의무 — 1년치 trail = LLM 못 가진 자산.

상세: `feedback_no_new_llm_narrative_features` + `feedback_pm_decision_trail_in_commit`.

---

## 🚨 RULE 8 — 신 cron / workflow 박은 후 N=2 실 cron 결과 audit 의무

**2026-05-28 박음 — 사용자 격분 발화 "맨날 이런식으로 데이터 손실내지". 박은 사고 history 6+ 회 (KIS 4번 / Vercel deploy / workflow git add 4건 / 5/27 cockpit dotenv / 5/28 TIDE billing 28h gap)**.

박은 root cause = 자동화 박은 후 실 cron 실행 결과 audit 박지 X. commit/push = "박은 의지" 박음, 박은 실 검증 박지 X. 사용자 카톡/사이트 격분 박은 후 박은 발견 = 박은 systemic 결함.

신 cron / workflow / scheduled job 박을 때 박은 의무:
- **N=2 실 cron 박은 결과 audit**: commit push 직후 `gh workflow run <name>` (N=1 manual) + 다음 scheduled cron 박은 시점 박은 결과 (N=2). 박은 둘 다 success + 산출물 박힘 검증.
- **billing / quota / payment 박은 부분 monitor**: 별 repo (TIDE) 박은 부분도 박은 obligated. VERITY Cockpit Phase 2 박은 부분 = 외부 repo health monitor 박은 의제 ([[project_tide_billing_incident_2026_05_28]] 박은 부분 학습).
- **사용자 알림 박은 후 박은 발견 = 결함 박은 자가 진단**. 박은 즉시 sentinel memory 박음.

상세: [[feedback_post_deploy_cron_audit_mandatory]] (본 RULE 도출 사례 + 박은 회피 mechanism).

---

## 자동화 워크플로 변경 시 검증 의무 (체크리스트)

`.github/workflows/*.yml` 변경 / 추가 시 다음 7축 audit:

1. **env / secret** — 사용 endpoint 명시, 죽은 등록 검증 (memory `feedback_env_registration_with_usage_proof`)
2. **push trigger** — Vercel deploy spam 회귀 검증 (RULE 2)
3. **concurrency group** — 형제 워크플로 + 평균 run 시간 audit (memory `feedback_concurrency_group_lock_audit`)
4. **cron schedule** — gh schedule silent skip vs Vercel cron dispatch chain 정합 (memory `feedback_gh_short_cron_silent_skip`)
5. **KIS 관련** — RULE 1 + `git add data/.kis_issued_date.txt` 누락 검증
6. **pip / requirements** — 의존성 정합 (5/27 cockpit dotenv 누락 학습)
7. **N=2 post-deploy audit** — RULE 8 정합. commit push 후 manual run (N=1) + 다음 scheduled (N=2) 박은 실 결과 검증 의무

---

## 메모리 우선순위

이 CLAUDE.md = 사고 반복 패턴만 hardcoded. 일반 컨벤션 / 진화 중 룰 / 프로젝트 컨텍스트 = 메모리 (`~/.claude/projects/.../memory/MEMORY.md`) 우선.

메모리 drift 의심 시 ("내가 몇번 말해야 되나" 류 발화) = 즉시 stop + sentinel feedback memory 신설/갱신.
