# operator-web — Vercel ignoreCommand (RULE 2, 약화 금지)

이 앱은 **별 Vercel 프로젝트** (Root Directory = `operator-web`). `vercel.json` 의 `ignoreCommand` =
**vercel-api 와 동일 계열 배포 폭주 가드**. 2026-05-13 Vercel Shohei 직접 메일(일 ~400 deploy 폭주로
차단 위협) 사고 클래스. 신규 프로젝트라 첫날부터 넣는다.

## 동작 (exit 0 = SKIP 배포, exit 1 = BUILD)
```
cd ..                              # Root=operator-web → repo 루트로 (1단계 = cd .. 1회)
B=${VERCEL_GIT_PREVIOUS_SHA:-}      # Vercel 이 제공한 직전 배포 SHA 우선
직전 SHA를 확인할 수 없을 때만 HEAD~50 폴백
git diff --quiet $B HEAD -- operator-web/  → 변경 없으면 SKIP / 있으면 BUILD
```

## 불변식 (변경 시 회귀)
- 경로 스코프 `-- operator-web/` (봇 데이터 커밋에 반응 금지)
- 직전 배포 SHA 우선, N=50은 SHA를 확인할 수 없을 때만 쓰는 폴백
- fail-open `|| exit 1` (자격증명 없는 빌드컨테이너에서 배포 누락보다 중복이 안전)
- **이중따옴표 0** (2026-07-13 프로덕션 배포 전면 FAIL 사고 — JSON 문자열 안 `'` 만)
- **`git fetch`/`clone`/`pull`·네트워크·프롬프트 유발 명령 절대 금지** (인증프롬프트 hang → 타임아웃 FAIL, #123→#124 롤백 사고)
- `cd ..` 횟수 = Root Directory 깊이(=1). 틀리면 엉뚱한 루트 보고 항상 SKIP(조용한 실패)

상세 근거: 메모리 project_vercel_deploy_spam_ticket_2026_05_13 · feedback_vercel_deploy_probe_after_push.
