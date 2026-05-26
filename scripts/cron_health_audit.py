#!/usr/bin/env python3
"""cron_health_audit — 매일 runtime_load_log.jsonl entry 분포 자동 검증.

박힌 cron 별 expected pattern vs actual. mismatch 시 telegram alert + jsonl 박음.
[[feedback_data_collection_verification_mandatory]] 의 "N run 누적 검증 3중" 자동화.

운영:
  - cron_health_audit.yml = 매일 KST 06:00 (UTC 21:00 전일)
  - window = 어제 KST 00:00 ~ 24:00
  - 결과 = data/metadata/cron_health_audit.jsonl append
  - mismatch → telegram alert (PM 자리비움 시 핸드폰)

drift 시 EXPECTED_PATTERNS dict manual update 의무.
신규 cron yml 박을 때 expected entry 추가 박을 것.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple

KST = timezone(timedelta(hours=9))

LOG_PATH = Path("data/metadata/runtime_load_log.jsonl")
AUDIT_PATH = Path("data/metadata/cron_health_audit.jsonl")

# expected pattern — drift 박을 때 manual update 의무.
# key = (mode, market_scope), value = {min, max, hint}
# min=0 → 미박힘 OK. min>0 → 어제 entry 미박힘 = missing alert.
EXPECTED_PATTERNS: Dict[Tuple[str, str], Dict] = {
    # daily_analysis_full (KST 16:00 평일, full mode) — scope=all 박힘
    ("full", "all"): {"min": 0, "max": 3, "hint": "daily_analysis_full KST 16:00 평일 (5/10 universe_scan 분리 후 drain 박힘 X — 5/27 fix 후 박힐 예정)"},
    ("full", "post_main_dart_drain"): {"min": 0, "max": 3, "hint": "full post_main DART drain (5/26 fix f7dd1c1c, 5/27 cron 박혀야)"},
    # daily_analysis_full (KST 06:30 화~금, full_us mode) — scope=us 박힘
    ("full_us", "us"): {"min": 0, "max": 2, "hint": "daily_analysis_full 화~금 KST 06:30 (full_us)"},
    ("full_us", "post_main_dart_drain"): {"min": 0, "max": 2, "hint": "full_us post_main"},
    # quick mode (daily_analysis + daily_realtime 다수) — scope=all 박힘
    ("quick", "all"): {"min": 1, "max": 200, "hint": "daily_analysis / realtime quick cron"},
    ("quick", "us"): {"min": 0, "max": 100, "hint": "daily_analysis_us quick"},
    ("quick", "post_main_dart_drain"): {"min": 1, "max": 200, "hint": "quick post_main"},
    # universe_scan (KST 15:30 평일, 5/27 fix 후 mode=universe_scan)
    ("universe_scan", "all"): {"min": 0, "max": 2, "hint": "universe_scan 평일 KST 15:30 (5/27 fix 후 박힘 시작)"},
    # periodic 류 (월간/분기/반기/연간) — 박힐 때만 1 entry, 다른 날은 0
    ("periodic_weekly", "all"): {"min": 0, "max": 1, "hint": "토요일 KST 09:00 주간"},
    ("periodic_monthly", "all"): {"min": 0, "max": 1, "hint": "매월 1일 KST 09:00"},
    ("periodic_quarterly", "all"): {"min": 0, "max": 1, "hint": "분기 1일 KST 10:01"},
    ("periodic_semi", "all"): {"min": 0, "max": 1, "hint": "반기 1일 KST 10:01"},
    ("periodic_annual", "all"): {"min": 0, "max": 1, "hint": "연간 1/4 KST 10:01"},
}

ALWAYS_ALERT_MODES = {
    "unknown": "ANALYSIS_MODE env 박힘 X — cron yml step env 확인 의무 (5/27 universe_scan 학습)",
    "": "ANALYSIS_MODE env 빈 문자열 박힘 — 옛 코드 default 또는 propagate 결함",
}


def _now_kst() -> datetime:
    return datetime.now(tz=KST)


def _yesterday_window() -> Tuple[datetime, datetime]:
    """어제 KST 00:00 ~ 24:00"""
    now = _now_kst()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    return yesterday_start, today_start


def _load_window_entries(start: datetime, end: datetime) -> List[Dict]:
    """run_id 기준 window 안 entry 추출. run_id = ISO 8601 박혀있음 가정."""
    if not LOG_PATH.exists():
        return []
    out = []
    with LOG_PATH.open() as f:
        for line in f:
            try:
                d = json.loads(line)
                run_id = d.get("run_id", "")
                if not run_id:
                    continue
                try:
                    ts = datetime.fromisoformat(run_id)
                except ValueError:
                    continue
                # tz-naive 박혀있으면 KST 박힘 가정
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=KST)
                if start <= ts < end:
                    out.append(d)
            except Exception:
                continue
    return out


def _audit(entries: List[Dict]) -> Dict:
    """expected vs actual 비교."""
    actual: Counter = Counter()
    for e in entries:
        mode = e.get("mode", "?")
        scope = (e.get("extra") or {}).get("market_scope", "?")
        actual[(mode, scope)] += 1

    mismatches: List[Dict] = []

    # 1) actual 박힌 거 검증
    for (mode, scope), n in actual.items():
        # always-alert mode (unknown 류)
        if mode in ALWAYS_ALERT_MODES:
            mismatches.append({
                "type": "always_alert_mode",
                "mode": mode,
                "scope": scope,
                "count": n,
                "hint": ALWAYS_ALERT_MODES[mode],
            })
            continue
        key = (mode, scope)
        if key not in EXPECTED_PATTERNS:
            mismatches.append({
                "type": "unknown_pattern",
                "mode": mode,
                "scope": scope,
                "count": n,
                "hint": "expected pattern 미정 — EXPECTED_PATTERNS dict 에 manual whitelist 박을 것",
            })
            continue
        spec = EXPECTED_PATTERNS[key]
        if n < spec["min"] or n > spec["max"]:
            mismatches.append({
                "type": "count_mismatch",
                "mode": mode,
                "scope": scope,
                "count": n,
                "expected_min": spec["min"],
                "expected_max": spec["max"],
                "hint": spec["hint"],
            })

    # 2) expected 박혀야 하는데 actual 0 (missing)
    for key, spec in EXPECTED_PATTERNS.items():
        if spec["min"] > 0 and actual.get(key, 0) == 0:
            mismatches.append({
                "type": "missing",
                "mode": key[0],
                "scope": key[1],
                "count": 0,
                "expected_min": spec["min"],
                "hint": spec["hint"],
            })

    win_start, win_end = _yesterday_window()
    return {
        "audit_at": _now_kst().isoformat(),
        "window_start": win_start.isoformat(),
        "window_end": win_end.isoformat(),
        "total_entries": len(entries),
        "mode_scope_counts": {f"{m}|{s}": n for (m, s), n in actual.items()},
        "mismatches": mismatches,
        "mismatch_count": len(mismatches),
    }


def _alert(audit: Dict) -> None:
    """Telegram alert — mismatch 박혀있으면 push."""
    if audit["mismatch_count"] == 0:
        return
    try:
        from api.notifications.telegram import send_message
    except Exception as e:
        print(f"telegram import fail: {e}", file=sys.stderr)
        return
    lines = [
        f"<b>Cron Health Audit — {audit['mismatch_count']} mismatch</b>",
        f"window: {audit['window_start'][:10]} (KST)",
        f"total entries: {audit['total_entries']}",
        "",
    ]
    for m in audit["mismatches"][:10]:
        lines.append(
            f"⚠ <code>{m['type']}</code> mode={m['mode']} scope={m['scope']} n={m['count']}"
        )
        if "expected_min" in m:
            lines.append(f"  expected: [{m['expected_min']}~{m.get('expected_max', '∞')}]")
        lines.append(f"  {m['hint']}")
    if len(audit["mismatches"]) > 10:
        lines.append(f"... +{len(audit['mismatches']) - 10} more (자세한 건 data/metadata/cron_health_audit.jsonl)")
    try:
        send_message("\n".join(lines))
    except Exception as e:
        print(f"telegram send fail: {e}", file=sys.stderr)


def main() -> int:
    start, end = _yesterday_window()
    entries = _load_window_entries(start, end)
    audit = _audit(entries)
    print(json.dumps(audit, ensure_ascii=False, indent=2))

    # jsonl append
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_PATH.open("a") as f:
        f.write(json.dumps(audit, ensure_ascii=False) + "\n")

    # alert
    _alert(audit)

    # exit 0 — mismatch 박혀있어도 workflow success 박음 (alert 만 의미).
    # critical fail 박을 거 = cron_health_audit 자체 fail (jsonl IO / parse 에러).
    return 0


if __name__ == "__main__":
    sys.exit(main())
