#!/usr/bin/env bash
# operator_ask 코어 동기화 — api/intelligence/{ticker_facts,operator_ask}.py (SSOT)
#                            → vercel-api/api/operator_core/ (배포 번들)
#
# 배경 (sync_chat_hybrid.sh 와 동일 사유):
#   Vercel Serverless 함수는 project root(vercel-api/) 밖 파일을 번들링하지 않는다.
#   repo 루트 api/ 를 import 할 수 없으므로 vercel-api 안에 실제 복제를 유지한다.
#
# 사용:
#   ./scripts/sync_operator_ask.sh           # SSOT → vercel-api 복제
#   ./scripts/sync_operator_ask.sh --check   # 차이만 출력 (CI 용, 차이 나면 exit 1)
#
# 규칙:
#   SSOT 는 항상 api/intelligence/ (repo root). 소비자 2곳:
#     · 오퍼레이터 CLI (터미널 대화 — 내가 직접 실행)
#     · vercel-api/api/operator_ask.py (오퍼레이터 사이트 alphanest-psi.vercel.app)
#   🚨 vercel-api/api/operator_core/ 를 직접 수정하지 말 것 — 다음 sync 에서 덮어써진다.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="${REPO_ROOT}/api/intelligence"
DST="${REPO_ROOT}/vercel-api/api/operator_core"
FILES=(ticker_facts.py operator_ask.py)

if [ "${1:-}" = "--check" ]; then
  rc=0
  for f in "${FILES[@]}"; do
    if ! diff -q "${SRC_DIR}/${f}" "${DST}/${f}" > /dev/null 2>&1; then
      echo "operator_ask out of sync: ${f} — run scripts/sync_operator_ask.sh" >&2
      rc=1
    fi
  done
  [ "$rc" = "0" ] && echo "operator_ask in sync"
  exit "$rc"
fi

mkdir -p "$DST"
touch "${DST}/__init__.py"
for f in "${FILES[@]}"; do
  cp "${SRC_DIR}/${f}" "${DST}/${f}"
done
echo "✓ operator_ask synced: ${SRC_DIR}/{$(IFS=,; echo "${FILES[*]}")} → ${DST}/"
