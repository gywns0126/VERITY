#!/usr/bin/env bash
# Manual production deployment of the already-linked API project.
# Usage: bash scripts/vercel_deploy.sh
set -euo pipefail

TASK_VERCEL_REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TASK_VERCEL_APP_DIR="$TASK_VERCEL_REPO_ROOT/vercel-api"
TASK_VERCEL_LINK="$TASK_VERCEL_APP_DIR/.vercel/project.json"
if [[ ! -f "$TASK_VERCEL_LINK" ]]; then
  echo "Missing vercel-api/.vercel/project.json; link the intended project first." >&2
  exit 1
fi
TASK_VERCEL_PROJECT_ID="$(python3 - "$TASK_VERCEL_LINK" <<'PYLINK'
import json, sys
with open(sys.argv[1]) as f:
    link = json.load(f)
if link.get("projectName") != "verity-api" or not link.get("projectId") or not link.get("orgId"):
    raise SystemExit("Expected the existing verity-api project link; refusing deployment.")
print(link["projectId"])
PYLINK
)"
TASK_VERCEL_CLI="${VERCEL_CLI:-}"
if [[ -z "$TASK_VERCEL_CLI" ]]; then
  TASK_VERCEL_CLI="$(command -v vercel || true)"
fi
if [[ -z "$TASK_VERCEL_CLI" && -x "$HOME/.npm-global/bin/vercel" ]]; then
  TASK_VERCEL_CLI="$HOME/.npm-global/bin/vercel"
fi
if [[ -z "$TASK_VERCEL_CLI" && -x "$TASK_VERCEL_APP_DIR/node_modules/.bin/vercel" ]]; then
  TASK_VERCEL_CLI="$TASK_VERCEL_APP_DIR/node_modules/.bin/vercel"
fi
if [[ -z "$TASK_VERCEL_CLI" || ! -x "$TASK_VERCEL_CLI" ]]; then
  echo "No installed Vercel CLI found; refusing an automatic download." >&2
  exit 1
fi
"$TASK_VERCEL_CLI" --version
TASK_VERCEL_INSPECT="$("$TASK_VERCEL_CLI" --cwd "$TASK_VERCEL_APP_DIR" project inspect --non-interactive 2>&1)"
printf '%s\n' "$TASK_VERCEL_INSPECT"
if [[ "$TASK_VERCEL_INSPECT" != *"$TASK_VERCEL_PROJECT_ID"* ]]; then
  echo "Resolved project differs from the local link; refusing deployment." >&2
  exit 1
fi
exec "$TASK_VERCEL_CLI" deploy --cwd "$TASK_VERCEL_APP_DIR" --prod --yes
