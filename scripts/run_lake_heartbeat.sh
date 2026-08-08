#!/bin/bash
# ──────────────────────────────────────────────────────────────────
# 로컬 레이크 하트비트 — launchd wrapper (일 1회). 2026-08-08 신설.
# 정본 설치 위치: ~/VERITY_data_lake/run_lake_heartbeat.sh
#   (레포 사본은 복구용. plist 는 레이크 경로를 가리킨다.)
# ──────────────────────────────────────────────────────────────────
# 🚨 왜 /bin/bash 래퍼인가 — plist 가 /usr/bin/python3 로 Desktop 아래 스크립트를 직접 실행하면
#   TCC 가 막는다("Operation not permitted", 2026-08-08 실측). 기존 com.verity.krflow 가
#   /bin/bash + 레이크 경로 래퍼로 도는 것과 같은 이유다. 이 패턴을 그대로 따른다.
#
# 🚨 왜 ~/VERITY_main 인가 — Desktop 작업 레포는 작업 브랜치라 data/ 가 origin/main 보다
#   뒤처져 있다. 거기서 하트비트를 돌리면 data/event_study.json 의 옛 사본을 읽고
#   "event_study 38일 stale" 같은 거짓 경보를 낸다(2026-08-08 실제 발생: 보드는 927h stale,
#   실제 origin/main 산출물은 8/07 21:10). 관측기는 origin/main 워크트리에서 돌아야 한다
#   — [[feedback_audit_agents_target_origin_main]] 과 동일 교훈.
# ──────────────────────────────────────────────────────────────────
set -uo pipefail
# gh(homebrew) 필요 — 하트비트가 gh api 로 main 에 직접 발행한다.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

REPO="$HOME/VERITY_main"
LOG="$HOME/VERITY_data_lake/lake_heartbeat.log"

echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') lake heartbeat 시작 ===" >> "$LOG"

if [ ! -d "$REPO" ]; then
    echo "[ERR] origin/main 워크트리 없음: $REPO" >> "$LOG"
    exit 1
fi
cd "$REPO" || { echo "[ERR] cd 실패: $REPO" >> "$LOG"; exit 1; }

# 관측 대상(data/event_study.json)이 최신 main 사본이도록 먼저 당긴다. 실패해도 계속 —
# 하트비트 자체(로컬 레이크 mtime)는 여전히 유효하다.
git fetch origin main --quiet >> "$LOG" 2>&1 || echo "[WARN] fetch 실패" >> "$LOG"
git checkout -q origin/main -- data/event_study.json >> "$LOG" 2>&1 || \
    echo "[WARN] event_study 체크아웃 실패 — 기존 사본으로 판정" >> "$LOG"

# 🚨 --publish 필수 — 없으면 로컬 파일만 갱신되고 main 에는 옛 스냅샷이 남는다.
#   CI cron_health 는 main 사본을 읽으므로, 발행하지 않으면 관측이 늙은 채로 방치된다.
/usr/bin/python3 scripts/local_lake_heartbeat.py --publish >> "$LOG" 2>&1
rc=$?
echo "=== exit=$rc @ $(date '+%H:%M:%S') ===" >> "$LOG"
exit $rc
