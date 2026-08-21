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
MARK_PATHS=(data api scripts operator-web/app vercel-api/api .github framer-components tests)

scan_markers() {
    grep -rl '^<<<<<<< ' "${MARK_PATHS[@]}" 2>/dev/null | grep -v '/node_modules/' || true
}

fail() { echo "🚨 중단: $*" >&2; exit 1; }

# ── 사전 조건 ──────────────────────────────────────────────
pre_markers="$(scan_markers)"
[ -n "$pre_markers" ] && fail "이미 충돌 마커가 있다 — 먼저 해소할 것:
$pre_markers"

pre_stash="$(git stash list | wc -l | tr -d ' ')"
ahead="$(git rev-list --count "origin/$BRANCH..HEAD" 2>/dev/null || echo 0)"
[ "$ahead" = "0" ] && { echo "푸시할 커밋 없음 — 종료"; exit 0; }
echo "미푸시 커밋 $ahead 건 · 기존 stash $pre_stash 건"

# ── fetch + rebase ────────────────────────────────────────
git fetch -q origin "$BRANCH" || fail "fetch 실패"
git rebase --autostash "origin/$BRANCH"
rc=$?

# 🚨 핵심 — exit 0 을 믿지 않는다. 실제 상태를 본다.
post_stash="$(git stash list | wc -l | tr -d ' ')"
post_markers="$(scan_markers)"

if [ -n "$post_markers" ]; then
    fail "autostash pop 충돌 — 마커가 남았다. **push 하지 않았다**:
$post_markers

복구:
  1) 각 파일의 양쪽을 대조 (보통 origin 판이 더 최신인 크론 산출물)
  2) git checkout origin/$BRANCH -- <경로>   ← 삭제 아님, 복원
  3) git stash show --name-only stash@{0} 으로 잔여 확인 후 drop
  4) 이 스크립트 재실행"
fi
if [ "$post_stash" != "$pre_stash" ]; then
    fail "stash 잔여수가 $pre_stash → $post_stash 로 변했다 = pop 미완. **push 하지 않았다**.
  git stash list / git stash show --name-only stash@{0} 확인 후 해소하고 재실행."
fi
[ $rc -ne 0 ] && fail "rebase 실패 (rc=$rc) — push 하지 않았다"

# ── push ──────────────────────────────────────────────────
git push -q origin "$BRANCH" || fail "push 실패"
echo "✅ push 완료 · $(git log --oneline -1)"
echo "   충돌 마커 0 · stash $post_stash 건(변동 없음)"
