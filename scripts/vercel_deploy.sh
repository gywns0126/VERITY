#!/usr/bin/env bash
# Vercel 수동 배포 — CLI 직접 (Hook 우회).
# 선행: dashboard Settings → Build and Deployment → Root Directory 비어 있어야 함.
# 사용: bash scripts/vercel_deploy.sh
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"
rm -rf .vercel vercel-api/.vercel

export VERCEL_ORG_ID="team_8E84APoZieKhinFDdc64R1Qh"
export VERCEL_PROJECT_ID="prj_0HzEuMfn7HlqOgpfRxsy4roV5thZ"

# 자동 push (있으면)
BRANCH="$(git branch --show-current)"
if [ -n "$(git log "@{u}..HEAD" 2>/dev/null || echo unset)" ]; then
  echo "▶ Pushing local commits..."
  git push origin "$BRANCH" 2>&1 | tail -3
fi

echo "▶ Deploying vercel-api/ to production..."
exec npx vercel@latest --cwd vercel-api --prod --yes
