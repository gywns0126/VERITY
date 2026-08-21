#!/usr/bin/env bash
# 세션 전용 인덱스로 **내 파일만** 커밋한다. 공유 인덱스를 건드리지 않는다.
#
# 왜 (2026-08-21 사고 2건, 같은 뿌리 반대 방향):
#   ① 내 `rebase --autostash` 가 타 세션 파일 36개를 stash 에 담아 충돌을 남겼다
#   ② 내가 `git add` 로 올린 파일 2개가 타 세션 커밋에 통째로 딸려 들어갔다
#   근본 원인 = **여러 세션 + 크론이 하나의 인덱스를 공유**한다는 것.
#   가드(P4·rebase_push.sh)는 ①만 막는다. ②는 인덱스를 나눠야 막힌다.
#
# 왜 worktree 가 아닌가:
#   worktree 는 `data/` 를 origin 판으로 갖는다. 내 작업은 크론이 방금 쓴 **라이브
#   data/** 와 gitignore 된 로컬 레이크를 읽어야 해서 격리된 트리에서는 성립하지 않는다.
#   격리해야 하는 것은 트리가 아니라 **인덱스**다 — `GIT_INDEX_FILE` 로 충분하다.
#
# 동작:
#   HEAD 로 시드한 임시 인덱스에 **지정 경로만** 올려 커밋한다. 결과 트리는
#   `HEAD + 지정 경로` 이고, 그 외 더티 파일은 구조적으로 들어갈 수 없다.
#   🚨 커밋 직전에 "HEAD 대비 달라진 경로 == 지정 경로" 를 assert 한다.
#
# 사용:
#   bash scripts/git/commit_mine.sh -m "메시지" -- 경로1 경로2 ...
#   bash scripts/git/commit_mine.sh --git-dir .git-private -m "..." -- docs/X.md
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"

GITDIR=""; MSG=""; PATHS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --git-dir) GITDIR="$2"; shift 2 ;;
        -m) MSG="$2"; shift 2 ;;
        --) shift; PATHS=("$@"); break ;;
        *) echo "알 수 없는 인자: $1" >&2; exit 2 ;;
    esac
done
[ -z "$MSG" ] && { echo "-m <메시지> 필요" >&2; exit 2; }
[ ${#PATHS[@]} -eq 0 ] && { echo "-- 뒤에 경로 필요" >&2; exit 2; }

G=(git)
[ -n "$GITDIR" ] && G=(git --git-dir="$GITDIR" --work-tree=.)

fail() { echo "🚨 중단: $*" >&2; [ -n "${IDX:-}" ] && rm -f "$IDX"; exit 1; }

# ── 1. 충돌 마커 (전수) ────────────────────────────────────
mk="$(grep -rl '^<<<<<<< ' data api scripts operator-web/app vercel-api/api .github framer-components tests 2>/dev/null | grep -v /node_modules/ || true)"
[ -n "$mk" ] && fail "충돌 마커가 있다 — 먼저 해소:
$mk"

# ── 2. 경로 존재·글롭 금지 (RULE 1 8/9 사고 클래스) ────────
for p in "${PATHS[@]}"; do
    case "$p" in *[\*\?\[]*) fail "글롭 금지 — 파일별로 명시: $p" ;; esac
    [ -e "$p" ] || fail "경로 없음: $p"
done

# ── 3. 세션 전용 인덱스 ────────────────────────────────────
IDX="$(mktemp -t verity_idx.XXXXXX)"
export GIT_INDEX_FILE="$IDX"
"${G[@]}" read-tree HEAD || fail "read-tree 실패"
for p in "${PATHS[@]}"; do
    "${G[@]}" add -- "$p" || fail "add 실패: $p"     # 경로 1개씩 (원자 실패 회피)
done

# ── 4. 🚨 assert — HEAD 대비 달라진 경로가 **지정 경로뿐**인가 ──
changed="$("${G[@]}" diff --cached --name-only HEAD | sort)"
want="$(printf '%s\n' "${PATHS[@]}" | sed 's#^\./##' | sort)"
if [ -z "$changed" ]; then
    unset GIT_INDEX_FILE; rm -f "$IDX"
    echo "변경 없음 — 커밋하지 않음"; exit 0
fi
extra="$(comm -23 <(echo "$changed") <(echo "$want"))"
[ -n "$extra" ] && fail "지정하지 않은 경로가 커밋에 들어간다 (공유 인덱스 오염 신호):
$extra"

echo "커밋 대상 $(echo "$changed" | wc -l | tr -d ' ')건:"
echo "$changed" | sed 's/^/  /'

# ── 5. 커밋 ────────────────────────────────────────────────
"${G[@]}" commit -q -m "$MSG" || fail "commit 실패"
unset GIT_INDEX_FILE
rm -f "$IDX"

# ── 6. 공유 인덱스 동기화 — 내 파일이 타 세션 status 에 유령으로 남지 않게 ──
"${G[@]}" reset -q -- "${PATHS[@]}" 2>/dev/null || true

echo "✅ $("${G[@]}" log --oneline -1)"
echo "   🚨 공유 인덱스 무접촉 — 스테이징 잔여 $("${G[@]}" diff --cached --name-only | wc -l | tr -d ' ')건(내 것 0)"
