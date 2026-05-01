#!/usr/bin/env python3
"""
operator_deadman — 본인(operator) 무활동 감지 → 자동매매 정지 / 시스템 maintenance 전환.

배경:
  Deadman switch 가 데이터 소스 장애만 잡고 정작 본인(직업군인 — 훈련/파견 가능성)
  무활동 시나리오는 안 잡고 있었음. 본인이 7~14일 응답 못 하면 시스템이 그 사이
  자동매매를 계속 돌리고, 시장이 망가지면 자본 직격.

3중 AND 신호 (false positive 방지):
  1. days_since_last_git_commit          (git log -1 --format=%ct)
  2. days_since_last_telegram_response   (data/.last_user_telegram_ts, telegram_bot 가 기록)
  3. days_since_last_user_action_queue   (Supabase user_action_queue.completed_at max)

각각이 자동화 가능 (예약 commit / bot poll 등) 하므로 셋 다 AND 여야 진짜 본인 부재.

2단계 escalation:
  - 7일 (warning_pause): data/.auto_trade_paused 생성 → auto_trader 정지
  - 14일 (maintenance) : data/.system_maintenance_mode 생성 → 추후 config.py 가
                          이 플래그 보고 VERITY_MODE staging 으로 다운그레이드

회복:
  - 셋 중 하나라도 < 7일 으로 떨어지면 두 플래그 모두 제거 (idempotent)

산출물:
  - data/metadata/operator_deadman_log.jsonl (append, state change 시 텔레그램 알림)

사용:
  python3 scripts/operator_deadman.py            # 평가 + 액션
  python3 scripts/operator_deadman.py --dry-run  # 평가만, 플래그/알림 없음
  python3 scripts/operator_deadman.py --warn-days 7 --maint-days 14
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import requests

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))

from api.config import DATA_DIR  # noqa: E402

KST = timezone(timedelta(hours=9))

_KILLSWITCH_PATH = os.path.join(DATA_DIR, ".auto_trade_paused")
_MAINTENANCE_PATH = os.path.join(DATA_DIR, ".system_maintenance_mode")
_TG_TS_PATH = os.path.join(DATA_DIR, ".last_user_telegram_ts")
_LOG_PATH = os.path.join(DATA_DIR, "metadata", "operator_deadman_log.jsonl")


def _load_dotenv() -> None:
    env_path = os.path.join(os.path.dirname(_HERE), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


def _now() -> datetime:
    return datetime.now(KST)


def _days_since(ts: Optional[datetime], now: datetime) -> Optional[float]:
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=KST)
    return (now - ts).total_seconds() / 86400.0


_BOT_EMAIL_PATTERNS = ("bot@ansim.ai", "github-actions", "noreply@github.com")
# 본인 email 화이트리스트 (env 로 override 가능 — OPERATOR_GIT_EMAIL).
_DEFAULT_OPERATOR_EMAIL = "gywns0126@gmail.com"


def _git_last_commit_ts() -> Optional[datetime]:
    """본인(=operator) email 의 commit 만 탐지. 봇 email 은 deadman log 자동 commit 이라 제외.

    같은 'AI Stock Bot' 이름이라도 bot@ansim.ai 는 GH Actions, gywns0126@gmail.com 은 본인.
    """
    operator_email = os.environ.get("OPERATOR_GIT_EMAIL", _DEFAULT_OPERATOR_EMAIL).lower()
    try:
        repo_root = os.path.dirname(_HERE)
        out = subprocess.check_output(
            ["git", "log", "-500", "--format=%ct|%ae", "--no-merges"],
            cwd=repo_root,
            stderr=subprocess.DEVNULL,
            timeout=10,
        ).decode().strip()
        if not out:
            return None
        for line in out.split("\n"):
            parts = line.split("|", 1)
            if len(parts) != 2:
                continue
            ts, email = parts
            email_l = email.strip().lower()
            if any(pat in email_l for pat in _BOT_EMAIL_PATTERNS):
                continue
            if email_l != operator_email:
                continue
            return datetime.fromtimestamp(int(ts), tz=KST)
        return None
    except Exception:
        return None


def _telegram_last_user_ts() -> Optional[datetime]:
    if not os.path.exists(_TG_TS_PATH):
        return None
    try:
        with open(_TG_TS_PATH, "r") as f:
            raw = f.read().strip()
        ts = datetime.fromisoformat(raw)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=KST)
        return ts
    except Exception:
        return None


def _user_action_queue_last_response() -> Optional[datetime]:
    """user_action_queue.completed_at MAX (status=done|skipped) — 사용자 직접 처리 흔적."""
    supa_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    supa_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not supa_url or not supa_key:
        return None
    try:
        r = requests.get(
            f"{supa_url}/rest/v1/user_action_queue",
            headers={"apikey": supa_key, "Authorization": f"Bearer {supa_key}"},
            params={
                "select": "completed_at",
                "status": "in.(done,skipped)",
                "completed_at": "not.is.null",
                "order": "completed_at.desc",
                "limit": "1",
            },
            timeout=10,
        )
        if r.status_code != 200:
            return None
        rows = r.json()
        if not rows:
            return None
        ts_raw = rows[0].get("completed_at")
        if not ts_raw:
            return None
        ts_raw = ts_raw.replace("Z", "+00:00")
        ts = datetime.fromisoformat(ts_raw)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(KST)
    except Exception:
        return None


def _trigger_state(
    days_git: Optional[float],
    days_tg: Optional[float],
    days_uaq: Optional[float],
    warn_days: float,
    maint_days: float,
) -> str:
    """AND 셋 다 임계 초과여야 trigger. None 신호는 '미측정' 으로 보고 보수적으로 ok 유지하지 않음 —
    None 이면 그 신호를 무시하고 측정 가능한 신호들끼리 AND."""
    measured = [d for d in (days_git, days_tg, days_uaq) if d is not None]
    if not measured:
        return "ok"  # 다 측정 불가면 판단 보류 (false positive 방지)
    if all(d >= maint_days for d in measured):
        return "maintenance"
    if all(d >= warn_days for d in measured):
        return "warning_pause"
    return "ok"


def _last_log_state() -> Optional[str]:
    if not os.path.exists(_LOG_PATH):
        return None
    try:
        with open(_LOG_PATH, "r", encoding="utf-8") as f:
            lines = [line for line in f if line.strip()]
        if not lines:
            return None
        last = json.loads(lines[-1])
        return last.get("trigger")
    except Exception:
        return None


def _append_log(entry: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
    with open(_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _send_telegram(msg: str) -> None:
    """알림 전송 — 실패해도 silent (deadman 스크립트 자체가 죽으면 안 됨)."""
    try:
        from api.notifications.telegram import send_message  # type: ignore
        send_message(msg)
    except Exception as e:
        print(f"[deadman] 텔레그램 알림 실패: {e}", file=sys.stderr)


def _apply_pause(active: bool) -> None:
    if active:
        if not os.path.exists(_KILLSWITCH_PATH):
            with open(_KILLSWITCH_PATH, "w") as f:
                f.write(f"operator_deadman triggered at {_now().isoformat()}\n")
    else:
        if os.path.exists(_KILLSWITCH_PATH):
            try:
                with open(_KILLSWITCH_PATH, "r") as f:
                    content = f.read()
                if "operator_deadman" in content:
                    os.remove(_KILLSWITCH_PATH)
            except Exception:
                pass


def _apply_maintenance(active: bool) -> None:
    if active:
        if not os.path.exists(_MAINTENANCE_PATH):
            with open(_MAINTENANCE_PATH, "w") as f:
                f.write(f"operator_deadman maintenance at {_now().isoformat()}\n")
    else:
        if os.path.exists(_MAINTENANCE_PATH):
            os.remove(_MAINTENANCE_PATH)


def main() -> int:
    p = argparse.ArgumentParser(description="Operator deadman switch")
    p.add_argument("--warn-days", type=float, default=7.0, help="warning_pause 임계 (default 7)")
    p.add_argument("--maint-days", type=float, default=14.0, help="maintenance 임계 (default 14)")
    p.add_argument("--dry-run", action="store_true", help="평가만, 플래그/알림 미적용")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    _load_dotenv()
    now = _now()

    git_ts = _git_last_commit_ts()
    tg_ts = _telegram_last_user_ts()
    uaq_ts = _user_action_queue_last_response()

    days_git = _days_since(git_ts, now)
    days_tg = _days_since(tg_ts, now)
    days_uaq = _days_since(uaq_ts, now)

    state = _trigger_state(days_git, days_tg, days_uaq, args.warn_days, args.maint_days)
    prev_state = _last_log_state()
    state_change = state != prev_state

    entry = {
        "ts": now.isoformat(),
        "days_git": round(days_git, 2) if days_git is not None else None,
        "days_telegram": round(days_tg, 2) if days_tg is not None else None,
        "days_uaq": round(days_uaq, 2) if days_uaq is not None else None,
        "warn_days": args.warn_days,
        "maint_days": args.maint_days,
        "trigger": state,
        "prev_trigger": prev_state,
        "state_change": state_change,
        "auto_trade_paused": state in ("warning_pause", "maintenance"),
        "maintenance": state == "maintenance",
        "false_positive": None,  # 사용자가 수동으로 채우는 audit 필드
    }

    if args.verbose or args.dry_run:
        print(json.dumps(entry, ensure_ascii=False, indent=2))

    if args.dry_run:
        return 0

    pause_active = state in ("warning_pause", "maintenance")
    maint_active = state == "maintenance"
    _apply_pause(pause_active)
    _apply_maintenance(maint_active)
    _append_log(entry)

    if state_change:
        if state == "warning_pause":
            _send_telegram(
                "🚨 <b>Operator Deadman — 자동매매 정지</b>\n\n"
                f"git: {entry['days_git']}d / tg: {entry['days_telegram']}d / uaq: {entry['days_uaq']}d\n"
                f"3 신호 모두 ≥ {args.warn_days}d. .auto_trade_paused 활성화.\n"
                "응답하시면 다음 cron 에서 자동 해제됩니다."
            )
        elif state == "maintenance":
            _send_telegram(
                "🛑 <b>Operator Deadman — Maintenance Mode</b>\n\n"
                f"git: {entry['days_git']}d / tg: {entry['days_telegram']}d / uaq: {entry['days_uaq']}d\n"
                f"3 신호 모두 ≥ {args.maint_days}d. .system_maintenance_mode 활성화.\n"
                "config.py 가 이 플래그 감지 시 VERITY_MODE → staging 으로 다운그레이드."
            )
        elif state == "ok" and prev_state in ("warning_pause", "maintenance"):
            _send_telegram(
                "✅ <b>Operator Deadman — 해제</b>\n\n"
                f"신호 회복 감지. .auto_trade_paused / .system_maintenance_mode 제거됨.\n"
                f"git: {entry['days_git']}d / tg: {entry['days_telegram']}d / uaq: {entry['days_uaq']}d"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
