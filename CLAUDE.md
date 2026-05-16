# VERITY / ESTATE — Critical Rules (Hardcoded)

이 문서는 **메모리 drift 가 반복된 사고만** 박는 hardcoded 가드입니다. 매 세션 자동 로드. 일반 컨벤션/스타일은 메모리 시스템 사용.

---

## 🚨 RULE 1 — KIS OpenAPI 토큰 = 1일 1토큰. ABSOLUTE.

**한국투자증권 정책: 하루 1개 토큰만 발급. 두 번째 발급 = 계좌 제재 위험.**

- "6시간 갱신" / "8시간" / "12시간" 표기 = **잘못**. 발견 시 즉시 정정 의무.
- 24시간 = "갱신 주기" 가 아니라 **"발급 간격 최소 24시간"**.
- 정상 발급 source = `kis_token_refresh.yml` (KST 23:45 일 1회 force_refresh) + `daily_realtime.yml` (backup)
- **price_pulse / 고빈도 consumer** = `KISBroker(cache_only=True)` 사용 의무. 신규 발급 절대 금지.
- KIS 관련 워크플로 신규 추가 시 = `git add data/.kis_issued_date.txt` step 필수 (lock propagation)
- 사용자 카톡에 KIS 토큰 발급 알림 직송 — **알림 0건이 정상 baseline**. 1건이라도 P0.

상세: `~/.claude/projects/.../memory/project_kis_token_policy.md` + `feedback_kis_one_token_per_day_sentinel.md`

사고 history: 2026-05-03 / 5-12 / 5-13 / 5-16 (5분 폭주 → 사용자 격분). 같은 사고 5번째 = 사용자가 "내가 몇번 말해야 되나" 발화.

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

## 자동화 워크플로 변경 시 검증 의무 (체크리스트)

`.github/workflows/*.yml` 변경 / 추가 시 다음 6축 audit:

1. **env / secret** — 사용 endpoint 명시, 죽은 등록 검증 (memory `feedback_env_registration_with_usage_proof`)
2. **push trigger** — Vercel deploy spam 회귀 검증 (RULE 2)
3. **concurrency group** — 형제 워크플로 + 평균 run 시간 audit (memory `feedback_concurrency_group_lock_audit`)
4. **cron schedule** — gh schedule silent skip vs Vercel cron dispatch chain 정합 (memory `feedback_gh_short_cron_silent_skip`)
5. **KIS 관련** — RULE 1 + `git add data/.kis_issued_date.txt` 누락 검증
6. **pip / requirements** — 의존성 정합

---

## 메모리 우선순위

이 CLAUDE.md = 사고 반복 패턴만 hardcoded. 일반 컨벤션 / 진화 중 룰 / 프로젝트 컨텍스트 = 메모리 (`~/.claude/projects/.../memory/MEMORY.md`) 우선.

메모리 drift 의심 시 ("내가 몇번 말해야 되나" 류 발화) = 즉시 stop + sentinel feedback memory 신설/갱신.
