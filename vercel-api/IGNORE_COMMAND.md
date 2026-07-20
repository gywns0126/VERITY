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

## 🚨 2026-07-13 — 가드를 '개선'하려다 배포를 전부 죽인 사고

복원 PR(#92/#93)이 가드를 손보면서 **프로덕션 배포 전부 FAIL** (`f33f90457`, `ded9c8a3d`).
라이브는 직전 배포가 서빙 중이라 무사했으나 main 이 배포 불가 상태였다. 원인 2개 — **둘 다 하지 말 것**:

1. **`vercel.json` 에 커스텀 키 추가** (`_ignoreCommand_note`) → Vercel 이 스키마 밖 최상위 키를 거부 → config 검증 FAIL.
   → 설명·경고는 **이 파일**에. `vercel.json` 은 주석 불가.
2. **`ignoreCommand` 에 이중따옴표 + `git fetch --deepen` 추가** → 배포 FAIL.
   - 이중따옴표: Vercel 이 명령을 셸에 넘길 때의 인용 처리와 충돌.
   - `git fetch`: 빌드 컨테이너에 자격증명이 없으면 프롬프트를 기다리며 **hang** → ignore 스텝 타임아웃 → 배포 실패.

**결론: 검증된 형태(아래)에서 벗어나지 말 것. 손대면 반드시 배포 결과를 확인할 것.**

```
bash -c 'cd .. || exit 0; N=50; git rev-parse HEAD~$N >/dev/null 2>&1 || N=1; git rev-parse HEAD~$N >/dev/null 2>&1 || exit 1; git diff --quiet HEAD~$N HEAD -- vercel-api/ && exit 0; exit 1'
```

## 불변식 (CI 가 강제 — `tests/test_vercel_ignore_guard.py`)

1. **경로 스코프** — `-- vercel-api/` 만 보고 판단. 데이터 커밋에 반응 금지.
2. **창 N ≥ 50** — 1커밋 창이면 봇 커밋이 `vercel-api` 커밋을 밀어내 **진짜 변경이 조용히 미배포**.
3. **fail-open** — 히스토리를 확보 못 하면 `exit 1`(BUILD). `exit 0`(SKIP) 은 배포 누락 = 더 나쁜 실패.
   **배포 1건 추가 ≪ 배포 누락.**
4. **이중따옴표 0개** — 2026-07-13 사고.
5. **네트워크 git 명령(`fetch`/`clone`/`pull`) 금지** — hang → 배포 FAIL. 로컬 히스토리만으로 판정.
6. **`vercel.json` 스키마 밖 최상위 키 0개** — 2026-07-13 사고.

## 변경하려면

1. memory `project_vercel_deploy_spam_ticket_2026_05_13` 재독.
2. `tests/test_vercel_ignore_guard.py` 를 함께 갱신 (안 하면 CI 가 막음).
3. **머지 후 Vercel 배포 상태를 반드시 확인** — `vercel.json` 은 잘못 건드리면 배포가 통째로 죽는다.
   `gh api repos/gywns0126/VERITY/deployments?per_page=5` → `deployments/<id>/statuses`
