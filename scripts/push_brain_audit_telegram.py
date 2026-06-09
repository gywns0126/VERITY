"""brain_audit 마지막 entry 텔레그램 push.

2026-05-18 추가됨 — 사용자 자리 비움 시 핸드폰 알림 정공법.
daily_analysis_full.yml step 호출. brain_audit.jsonl tail 1 → 요약 → send_message.

quiet hours / dedupe = api/notifications/telegram.send_message 가 자동 정합.
bypass_quiet=False (default) → 23:00~07:00 KST suppress. 16:07/06:30 cron 통과.
"""
from __future__ import annotations

import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

AUDIT_PATH = os.path.join(_REPO_ROOT, "data", "metadata", "brain_audit.jsonl")


def main() -> int:
    if not os.path.isfile(AUDIT_PATH):
        sys.stderr.write(f"[telegram] brain_audit.jsonl 부재 — skip\n")
        return 0

    try:
        with open(AUDIT_PATH, "r", encoding="utf-8") as f:
            lines = [ln for ln in f.readlines() if ln.strip()]
        if not lines:
            sys.stderr.write(f"[telegram] brain_audit.jsonl 빈 — skip\n")
            return 0
        e = json.loads(lines[-1])
    except (OSError, json.JSONDecodeError) as ex:
        sys.stderr.write(f"[telegram] brain_audit.jsonl read fail: {ex}\n")
        return 0

    try:
        from api.notifications.telegram import send_message
    except Exception as ex:
        sys.stderr.write(f"[telegram] send_message import fail: {ex}\n")
        return 0

    bs = e.get("brain_score") or {}
    g = e.get("grade") or {}
    fill = e.get("component_fill") or {}
    qd_keys = list((e.get("quadrant") or {}).keys())
    w_keys = list((e.get("brain_weights") or {}).keys())

    def _fill(k: str) -> str:
        return (fill.get(k) or {}).get("total", "?")

    msg = (
        f"📊 <b>brain_audit @ {(e.get('ts_kst') or '?')[:16]}</b>\n"
        f"N={e.get('n_total')} | "
        f"score={bs.get('min')}~{bs.get('median')}~{bs.get('max')} (μ={bs.get('mean')})\n"
        f"BUY={g.get('BUY', 0)} STRONG_BUY={g.get('STRONG_BUY', 0)} "
        f"WATCH={g.get('WATCH', 0)} CAUTION={g.get('CAUTION', 0)} "
        f"AVOID={g.get('AVOID', 0)}\n"
        f"dart_biz={_fill('dart_business_analysis')} "
        f"ext_risk={_fill('external_risk')} "
        f"vol20d={_fill('volatility_20d')} "
        f"commodity={_fill('commodity_margin')}\n"
        f"sec_fin={_fill('sec_financials')} "
        f"analyst={_fill('analyst_report_summary')} "
        f"dart_fin={_fill('dart_financials')}\n"
        f"quad={qd_keys[0] if qd_keys else '?'} "
        f"w={w_keys[0] if w_keys else '?'}"
    )
    try:
        send_message(msg, bypass_quiet=False)
        print(f"[telegram] brain_audit push sent ({len(msg)} chars)")
    except Exception as ex:
        sys.stderr.write(f"[telegram] send_message fail: {ex}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
