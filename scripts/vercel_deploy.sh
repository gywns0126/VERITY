#!/usr/bin/env bash
# Vercel 수동 배포 — webhook 우회. vercel-api/ 만 업로드.
# 사용: bash scripts/vercel_deploy.sh
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

# stale link 모두 정리 (root + vercel-api 양쪽)
rm -rf .vercel vercel-api/.vercel

export VERCEL_ORG_ID="team_8E84APoZieKhinFDdc64R1Qh"
export VERCEL_PROJECT_ID="prj_0HzEuMfn7HlqOgpfRxsy4roV5thZ"

echo "▶ Deploying vercel-api/ to project=$VERCEL_PROJECT_ID"
exec npx vercel@latest --cwd vercel-api --prod --yes
