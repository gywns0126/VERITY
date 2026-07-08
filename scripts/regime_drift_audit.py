#!/usr/bin/env python3
"""레짐 드리프트 감사 — 하드코딩된 시장값 임계가 현 시장 레짐에서 stale(포화/사멸)한지 점검.

배경(2026-07-08): Deadman's Switch 의 KOSPI sanity 상한이 5000 으로 하드코딩돼 있었는데
실 KOSPI 는 ~8000(2026 강세) → 정상값을 오탐해 분석 오중단. 같은 계열로 USD/KRW 1400 앵커
(currency_penalty·macro 진단·safe_picks)가 원화 ~1500대 레짐에서 밴드가 한쪽으로 붙어(포화/사멸)
산식·신호를 조용히 편향. 이런 stale 를 "사고 나기 전에" 정기 포착하는 가드.

동작: data/macro_snapshot.json 의 현재 시장값을 REGISTRY 의 하드코딩 임계와 대조 →
  · BREACH   = 실값이 sanity 상/하한 밖 (KOSPI 5000 오탐 계열 — 즉시 재상향 대상)
  · NEAR_CAP = 실값이 상한 85%+ 근접 (곧 BREACH — 선제 상향 권고)
  · SATURATED= 페널티/스코어 밴드가 cap 에 붙음 (차등 소실 — 재캘리 권고)
  · STUCK    = 경고/긍정 밴드 한쪽이 상시 발화 또는 영구 사멸 (신호 무의미)
  · OK       = 실값이 밴드 안에서 정상 discriminate

산출: stdout 표 + data/metadata/regime_drift_audit.jsonl append.
관측-only — 항상 exit 0 (self_assets exit1 캐스케이드 학습). 알람은 cron_health 가 jsonl 소비.

주기: 주1 (레짐은 천천히 이동). 신 하드코딩 임계 추가 시 REGISTRY 에 등록.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone, timedelta

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MACRO_PATH = os.path.join(_ROOT, "data", "macro_snapshot.json")
OUT_PATH = os.path.join(_ROOT, "data", "metadata", "regime_drift_audit.jsonl")
KST = timezone(timedelta(hours=9))


def _now_kst() -> datetime:
    return datetime.now(timezone.utc).astimezone(KST)


# 하드코딩된 시장값 임계 등록부 (이번 감사 curated). 신 임계 추가 시 여기 등록.
#   live      = data/macro_snapshot.json macro.<field> 대조 필드
#   band      = (lo, hi) sanity 경계 (BREACH/NEAR_CAP 판정)
#   penalty_band = (start, cap) 스코어 페널티 램프 (SATURATED 판정)
#   warn_above / pos_below = 신호 밴드 (STUCK 판정)
#   suitable_below = 추천 적합 임계 (STUCK 판정)
REGISTRY = [
    {"name": "health.deadman.kospi", "file": "api/health.py", "live": "kospi", "band": (1000, 15000),
     "note": "Deadman sanity. 실 KOSPI 상한 근접 시 재상향 (5000→15000 2026-07-08 정정 이력)."},
    {"name": "health.deadman.kosdaq", "file": "api/health.py", "live": "kosdaq", "band": (300, 6000)},
    {"name": "health.deadman.usd_krw", "file": "api/health.py", "live": "usd_krw", "band": (900, 2200)},
    {"name": "health.deadman.vix", "file": "api/health.py", "live": "vix", "band": (5, 120)},
    {"name": "brain.currency_penalty", "file": "api/intelligence/verity_brain.py", "live": "usd_krw",
     "penalty_band": (1450, 1750), "note": "KR 사이징 페널티 램프. live>=cap → 균일 포화(차등 소실)."},
    {"name": "macro_data.usd_krw_diag", "file": "api/collectors/macro_data.py", "live": "usd_krw",
     "warn_above": 1550, "pos_below": 1450, "note": "원화약세 경고 / 원화강세 긍정 신호 밴드."},
    {"name": "safe_picks.tbill_suitable", "file": "api/analyzers/safe_picks.py", "live": "usd_krw",
     "suitable_below": 1500, "note": "US T-Bill 적합 임계."},
]


def _live_value(macro: dict, field: str):
    """macro.<field>.value. nan/None 이면 sparkline 마지막값 fallback."""
    d = macro.get(field) or {}
    v = d.get("value")
    if v is None or (isinstance(v, float) and math.isnan(v)):
        sp = d.get("sparkline") or []
        v = sp[-1] if sp else None
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _evaluate(entry: dict, macro: dict) -> dict:
    v = _live_value(macro, entry["live"])
    row = {"name": entry["name"], "file": entry["file"], "live_field": entry["live"], "live": v}
    if v is None:
        row["status"] = "no_live"
        row["detail"] = "현재 시장값 없음 (nan + sparkline 부재)"
        return row

    flags = []
    if "band" in entry:
        lo, hi = entry["band"]
        if v > hi or v < lo:
            flags.append(f"BREACH: {v:g} 가 sanity {lo}~{hi} 밖 — 즉시 재조정")
        elif v >= lo + (hi - lo) * 0.85:
            flags.append(f"NEAR_CAP: {v:g} 가 상한 {hi} 85%+ 근접 — 선제 상향 권고")
    if "penalty_band" in entry:
        start, cap = entry["penalty_band"]
        if v >= cap:
            flags.append(f"SATURATED: {v:g} >= cap {cap} — 페널티 균일 포화(차등 소실), 재캘리")
        elif v < start:
            flags.append(f"INACTIVE: {v:g} < start {start} — 페널티 미발동(정상 가능)")
    if "warn_above" in entry and "pos_below" in entry:
        wa, pb = entry["warn_above"], entry["pos_below"]
        # 두 밴드 사이(중립대)면 정상. 한쪽이 현재 레짐에서 도달 불가면 STUCK.
        if v > wa:
            flags.append(f"WARN_ON: {v:g} > {wa} — 경고 발화 중 (실약세면 정상)")
        elif v < pb:
            flags.append(f"POS_ON: {v:g} < {pb} — 긍정 발화 중")
    if "suitable_below" in entry:
        sb = entry["suitable_below"]
        if v >= sb:
            flags.append(f"UNSUITABLE: {v:g} >= {sb} — 현재 부적합 판정 중")

    row["status"] = "flag" if any(f.split(":")[0] in ("BREACH", "NEAR_CAP", "SATURATED") for f in flags) else "ok"
    row["flags"] = flags
    if entry.get("note"):
        row["note"] = entry["note"]
    return row


def main() -> int:
    try:
        with open(MACRO_PATH, encoding="utf-8") as f:
            snap = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[regime_drift] macro_snapshot 로드 실패: {e}")
        return 0  # 관측-only, 게이팅 안 함
    macro = snap.get("macro") or {}

    rows = [_evaluate(e, macro) for e in REGISTRY]
    flagged = [r for r in rows if r["status"] == "flag"]

    print(f"[regime_drift] 감사 {len(rows)}건 | 플래그 {len(flagged)}건 | macro as_of {snap.get('collected_at')}")
    for r in rows:
        mark = "🔴" if r["status"] == "flag" else ("⚪" if r["status"] == "no_live" else "🟢")
        live = f"{r['live']:g}" if isinstance(r.get("live"), (int, float)) else "—"
        print(f"  {mark} {r['name']:32s} live({r['live_field']})={live:>8s}")
        for fl in r.get("flags", []):
            print(f"       · {fl}")

    entry = {
        "ts_kst": _now_kst().isoformat(timespec="seconds"),
        "macro_as_of": snap.get("collected_at"),
        "checked": len(rows),
        "flagged": len(flagged),
        "flagged_names": [r["name"] for r in flagged],
        "rows": rows,
    }
    try:
        os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
        with open(OUT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as e:
        print(f"[regime_drift] jsonl append 실패: {e}")

    return 0  # 항상 0 — 관측-only, 알람은 cron_health 소비


if __name__ == "__main__":
    raise SystemExit(main())
