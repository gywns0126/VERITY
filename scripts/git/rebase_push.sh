#!/usr/bin/env bash
# 안전한 rebase + push — 공유 작업트리(크론·타 세션 상시 더티)에서 쓰는 유일한 경로.
#
# 왜 이 스크립트가 필요한가 (2026-08-21 실사고):
#   `git rebase --autostash origin/main && git push` 를 썼는데, autostash 가 작업트리
#   **36파일**(크론 산출물 + 타 세션 편집분)을 담았고 pop 에서 data/price_pulse.json 이
#   충돌해 마커가 남았다. 🚨 **rebase 는 pop 충돌에도 exit 0** 이라 `&&` 가 그대로
#   통과했고, push 성공만 보고 넘어가 오염이 작업트리에 남았다.
#   ([[feedback_autostash_conflict_exits_zero]] 가 경고한 바로 그 형태)
#
# 이 스크립트가 promise 가 아니라 **기계**인 이유:
#   rebase 직후 stash 잔여수·충돌 마커를 assert 하고, 어긋나면 push 하지 않고 죽는다.
#   주의력에 의존하지 않는다 (RULE 12 — 기억·습관으로는 3일이면 퇴화한다).
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"

BRANCH="${1:-main}"
# 🚨 2026-08-22 적대적 검증에서 발견 — 초판은 docs·server·supabase·private·루트 파일을
#   통째로 빼먹었다. docs/ 는 사전등록을 매일 쓰는 곳이고 private repo 로 가는 경로라
#   거기 마커가 남으면 검사에 안 걸린 채 커밋된다. 존재하는 디렉토리만 추린다.
MARK_DIRS=(data api scripts docs operator-web/app vercel-api/api .github framer-components
           tests server supabase private)
MARK_PATHS=()
for _d in "${MARK_DIRS[@]}"; do [ -d "$_d" ] && MARK_PATHS+=("$_d"); done
# 루트 레벨 텍스트 파일(CLAUDE.md 등)도 포함 — 디렉토리 스캔이 놓치는 자리
for _f in ./*.md ./*.json ./*.yml ./*.yaml; do [ -f "$_f" ] && MARK_PATHS+=("$_f"); done

scan_markers() {
    grep -rl '^<<<<<<< ' "${MARK_PATHS[@]}" 2>/dev/null | grep -v '/node_modules/' || true
}

fail() { echo "🚨 중단: $*" >&2; exit 1; }

# ── 사전 조건 ──────────────────────────────────────────────
pre_markers="$(scan_markers)"
[ -n "$pre_markers" ] && fail "이미 충돌 마커가 있다 — 먼저 해소할 것:
$pre_markers"

pre_stash="$(git stash list | wc -l | tr -d ' ')"
# 🚨 재시도 루프 (2026-08-22 추가) — fetch 와 push 사이에 타 세션이 push 하면
#   non-fast-forward 로 거부된다. 실제로 발생했다. 이 저장소 워크플로들도 같은 이유로
#   5회 재시도한다(universe_scan.yml 선례). 조용히 성공한 척하지 않고, 매 시도마다
#   stash·마커 검증을 다시 통과해야 push 한다.
for attempt in 1 2 3 4 5; do
[ "$attempt" -gt 1 ] && echo "🔁 재시도 $attempt/5 (타 세션 push 레이스)"

# 🚨 fetch 를 **먼저** 한다 (2026-08-22 자가 발견 결함).
#   초판은 fetch 전에 ahead 를 세서 **낡은 origin/BRANCH ref** 로 판단했다.
#   타 세션이 그 사이 push 했으면 "푸시할 커밋 없음" 으로 잘못 빠져나간다.
git fetch -q origin "$BRANCH" || fail "fetch 실패"
ahead="$(git rev-list --count "origin/$BRANCH..HEAD" 2>/dev/null || echo 0)"
[ "$ahead" = "0" ] && { echo "푸시할 커밋 없음 — 종료"; exit 0; }
echo "미푸시 커밋 $ahead 건 · 기존 stash $pre_stash 건"

# ── rebase ────────────────────────────────────────────────
git rebase --autostash "origin/$BRANCH"
rc=$?

# 🚨 핵심 — exit 0 을 믿지 않는다. 실제 상태를 본다.
post_stash="$(git stash list | wc -l | tr -d ' ')"
post_markers="$(scan_markers)"

if [ -n "$post_markers" ]; then
    # 🚨 자동 해소는 **파이프라인 산출물(data/)로 한정**한다 (2026-08-22 — 3연속 발생 후 추가).
    #   크론이 rebase 중에도 계속 data/ 를 쓰므로 이 충돌은 사고가 아니라 상시 상태다.
    #   그 파일들은 재생성되고 origin 판이 커밋된 정본이라 origin 으로 되돌리는 것이 안전하다.
    #   🚨 코드·문서(data/ 밖)는 자동 해소하지 않는다 — 그건 진짜 충돌이고 사람이 봐야 한다.
    auto=""; manual=""
    while IFS= read -r f; do
        case "$f" in data/*) auto="$auto $f" ;; *) manual="$manual $f" ;; esac
    done <<< "$post_markers"
    if [ -n "$manual" ]; then
        fail "data/ 밖 충돌 — 자동 해소하지 않는다. **push 하지 않았다**:$manual"
    fi
    for f in $auto; do
        git checkout "origin/$BRANCH" -- "$f" 2>/dev/null || fail "복원 실패: $f"
    done
    echo "🔧 파이프라인 산출물 자동 해소(origin 판 복원):$auto"
    post_markers="$(scan_markers)"
fi
if [ -n "$post_markers" ]; then
    fail "자동 해소 후에도 마커가 남았다. **push 하지 않았다**:
$post_markers

복구:
  1) 각 파일의 양쪽을 대조 (보통 origin 판이 더 최신인 크론 산출물)
  2) git checkout origin/$BRANCH -- <경로>   ← 삭제 아님, 복원
  3) git stash show --name-only stash@{0} 으로 잔여 확인 후 drop
  4) 이 스크립트 재실행"
fi
if [ "$post_stash" != "$pre_stash" ]; then
    # 자동 해소했다면 남은 stash 가 data/ 전용인지 확인 후 정리
    if [ -n "${auto:-}" ] && [ -z "$(git stash show --name-only stash@{0} 2>/dev/null | grep -v "^data/")" ]; then
        git stash drop >/dev/null 2>&1 && echo "🔧 잔여 autostash 정리(전부 data/)"
        post_stash="$(git stash list | wc -l | tr -d ' ')"
    fi
fi
if [ "$post_stash" != "$pre_stash" ]; then
    fail "stash 잔여수가 $pre_stash → $post_stash 로 변했다 = pop 미완. **push 하지 않았다**.
  git stash list / git stash show --name-only stash@{0} 확인 후 해소하고 재실행."
fi
[ $rc -ne 0 ] && fail "rebase 실패 (rc=$rc) — push 하지 않았다"

# ── push ──────────────────────────────────────────────────
if git push -q origin "$BRANCH" 2>/dev/null; then
    echo "✅ push 완료 · $(git log --oneline -1)"
    echo "   충돌 마커 0 · stash $post_stash 건(변동 없음)$([ "$attempt" -gt 1 ] && echo " · 시도 $attempt회")"
    exit 0
fi
echo "   push 거부(원격 선행) — 재fetch 후 다시 시도"
sleep 2
done
fail "5회 재시도 후에도 push 실패 — 원격이 계속 앞선다. 수동 확인 필요."
