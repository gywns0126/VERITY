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
    # === 진짜 jsonl entry 박는 path (5/27 매핑 박힘) ===
    # api/main.py post_main_dart_drain (5/26 fix f7dd1c1c) — 모든 cron 박을 때 박힘
    ("quick", "post_main_dart_drain"): {"min": 1, "max": 500, "hint": "daily_analysis/realtime quick cron post_main (매일 박혀야)"},
    ("full", "post_main_dart_drain"): {"min": 0, "max": 3, "hint": "daily_analysis_full 평일 KST 16:07 post_main (월요일 0건 자연)"},
    ("full_us", "post_main_dart_drain"): {"min": 0, "max": 2, "hint": "daily_analysis_full 화~금 KST 06:30 post_main"},
    ("periodic_weekly", "post_main_dart_drain"): {"min": 0, "max": 1, "hint": "토 KST 09:07 주간"},
    ("periodic_monthly", "post_main_dart_drain"): {"min": 0, "max": 1, "hint": "매월 1일 KST 09:07"},
    ("periodic_quarterly", "post_main_dart_drain"): {"min": 0, "max": 1, "hint": "분기 1일"},
    ("periodic_semi", "post_main_dart_drain"): {"min": 0, "max": 1, "hint": "반기 1일"},
    ("periodic_annual", "post_main_dart_drain"): {"min": 0, "max": 1, "hint": "연간 1/4"},
    # universe_scan_builder._log_w1_runtime — pipeline drain (scope=all)
    ("universe_scan", "all"): {"min": 0, "max": 2, "hint": "universe_scan 평일 KST 15:30 (5/27 fix 후 박힘 시작, 주말 0건)"},
}

# 옛 entry whitelist — 5/12+ 박힘 X 박은 path. mismatch alert 회피.
# 박은 path 의 entry 박힘 시 false positive 아닌 진짜 회귀 = unknown_pattern alert 박힘.
# 5/12 이전 옛 entry (mode="" + scope=all/us, mode="full"/"full_us" + scope=all/us) 는
# yesterday window 박힘 0 이라 audit 자체 무관 (window 밖 자동 제외).

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

    return {
        "audit_at": _now_kst().isoformat(),
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


def _today_window() -> Tuple[datetime, datetime]:
    """오늘 KST 00:00 ~ 24:00 (dry-run verify 용)"""
    now = _now_kst()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return today_start, today_start + timedelta(days=1)


def main() -> int:
    # --window today/yesterday 옵션 박음 (default = yesterday, cron 운영)
    window_arg = "yesterday"
    for a in sys.argv[1:]:
        if a == "--window=today" or a == "today":
            window_arg = "today"
    if window_arg == "today":
        start, end = _today_window()
    else:
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
