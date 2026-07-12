# 🚨 RULE 2 — `vercel.json` 의 `ignoreCommand` 를 지킬 것

> ⚠️ **`vercel.json` 에 주석·커스텀 키를 넣지 말 것.**
> Vercel 은 `vercel.json` 스키마 밖의 최상위 키를 **거부**한다. 2026-07-13 에 `_ignoreCommand_note`
> 키를 넣었다가 프로덕션 배포가 config 검증 단계에서 즉시 FAIL 했다. 경고문은 **이 파일**에 둔다.

## 왜 이 가드가 있나

| 시점 | 사건 |
|---|---|
| 2026-05-13 | Vercel(Compute infra) 직접 메일 — 일 ~400 deploy 폭주, 차단 위협. `ignoreCommand` 도입 |
| 2026-07-06 `46da2c1f2` | 창을 **N=50** 으로 확립 — 봇 커밋이 `vercel-api` 커밋을 창 밖으로 밀어내던 문제 해결 |
| 2026-07-08 `7b3da3de0` | `perf(stock): 종목별 슬라이스 API` 가 **낡은 base 에서 편집** 하며 가드를 N=1 + fail-closed 로 **조용히 되돌림** |
| 2026-07-10 `624791d92` | *"봇커밋 87개로 ignoreCommand 창 밖 skip 재발(3차)"* → 수동 redeploy bump 필요 |
| 2026-07-13 | 복원 (N=50 + fail-open + `cat-file -e` + `--deepen`) + CI 회귀 가드 신설 |

## 불변식 (CI 가 강제 — `tests/test_vercel_ignore_guard.py`)

1. **경로 스코프** — `-- vercel-api/` 만 보고 판단. 데이터 커밋에 반응 금지.
2. **창 N ≥ 50** — 1커밋 창이면 봇 커밋이 `vercel-api` 커밋을 밀어내 **진짜 변경이 조용히 미배포**.
3. **fail-open** — 히스토리를 확보 못 하면 `exit 1`(BUILD). `exit 0`(SKIP) 은 배포 누락 = 더 나쁜 실패.
   **배포 1건 추가 ≪ 배포 누락.**
4. **`cat-file -e` 로 객체 존재 검증** — `git rev-parse` 성공 ≠ 객체 존재(참조 해석만 함).
5. **`git fetch --deepen` 선행** — Vercel 은 얕은 클론을 하므로, 창을 계산하려면 히스토리를 먼저 파야 함.

## 변경하려면

1. memory `project_vercel_deploy_spam_ticket_2026_05_13` 재독.
2. `tests/test_vercel_ignore_guard.py` 를 함께 갱신 (안 하면 CI 가 막음).
3. 머지 후 **Vercel 배포 상태를 반드시 확인** — `vercel.json` 은 잘못 건드리면 배포가 통째로 죽는다.
