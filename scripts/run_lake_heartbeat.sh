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
# event_study는 격리된 재생성 잡의 산출물을 읽는다. 공유 VERITY_main에 fetch/checkout
# 하지 않는다. 이 wrapper와 local_lake_heartbeat.py를 레이크에 함께 설치한다.
# ──────────────────────────────────────────────────────────────────
set -uo pipefail
# gh(homebrew) 필요 — 하트비트가 gh api 로 main 에 직접 발행한다.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

LAKE="$HOME/VERITY_data_lake"
LOG="$LAKE/lake_heartbeat.log"
export VERITY_HEARTBEAT_OUTPUT="$LAKE/local_lake_health.json"
export VERITY_EVENT_STUDY_PATH="$LAKE/event_study_job/repo/data/event_study.json"

echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') lake heartbeat 시작 ===" >> "$LOG"

if [ ! -f "$LAKE/local_lake_heartbeat.py" ]; then
    echo "[ERR] heartbeat 독립 실행 파일 미설치" >> "$LOG"
    exit 1
fi

# 🚨 --publish 필수 — 없으면 로컬 파일만 갱신되고 main 에는 옛 스냅샷이 남는다.
#   CI cron_health 는 main 사본을 읽으므로, 발행하지 않으면 관측이 늙은 채로 방치된다.
/usr/bin/python3 "$LAKE/local_lake_heartbeat.py" --publish >> "$LOG" 2>&1
rc=$?
echo "=== exit=$rc @ $(date '+%H:%M:%S') ===" >> "$LOG"
exit $rc
