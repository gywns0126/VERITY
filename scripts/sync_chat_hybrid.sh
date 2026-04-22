#!/usr/bin/env bash
# chat_hybrid 패키지 동기화 — api/chat_hybrid/ (SSOT) → vercel-api/api/chat_hybrid/ (배포 번들)
#
# 배경:
#   Vercel Serverless 함수가 project root (vercel-api/) 밖의 파일을 안정적으로
#   번들링하지 못해 api.chat_hybrid 모듈이 import 되지 않는 문제가 있었다.
#   그래서 vercel-api/api/chat_hybrid/ 에 실제 복제를 유지한다.
#
# 사용:
#   ./scripts/sync_chat_hybrid.sh           # SSOT → vercel-api 로 동기화
#   ./scripts/sync_chat_hybrid.sh --check   # diff 만 출력 (CI 용)
#
# 규칙:
#   SSOT 는 항상 api/chat_hybrid/ (repo root).
#   vercel-api/api/chat_hybrid/ 를 직접 수정하지 말 것.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${REPO_ROOT}/api/chat_hybrid/"
DST="${REPO_ROOT}/vercel-api/api/chat_hybrid/"

if [ "${1:-}" = "--check" ]; then
  # CI 용 — 차이 나면 1 반환
  if ! diff -qr --exclude='__pycache__' "$SRC" "$DST" > /dev/null 2>&1; then
    echo "chat_hybrid out of sync — run scripts/sync_chat_hybrid.sh" >&2
    diff -qr --exclude='__pycache__' "$SRC" "$DST" || true
    exit 1
  fi
  echo "chat_hybrid in sync"
  exit 0
fi

mkdir -p "$DST"
rsync -a --delete --exclude='__pycache__' "$SRC" "$DST"
echo "✓ chat_hybrid synced: $SRC → $DST"
