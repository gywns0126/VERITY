#!/usr/bin/env python3
"""
refresh_assumptions — Phase 0 staged_updates 가정 registry 재검 + cascade strikethrough.

흐름:
  1. assumptions.yaml 로드
  2. 각 assumption 의 check 실행 → status / current_value 갱신
  3. 갱신된 assumptions.yaml 쓰기
  4. decision_log.jsonl 의 각 item 에 대해:
     - depends_on_assumptions 중 invalid 가 있으면 strikethrough=true
     - depends_on_items[].type=hard 인 dep 가 strikethrough 면 cascade strikethrough
     - depends_on_items[].type=soft 인 dep 가 strikethrough 면 flag_for_review (strikethrough X)
  5. 결과 요약 출력

사용:
  python3 scripts/refresh_assumptions.py
  python3 scripts/refresh_assumptions.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml  # type: ignore
except ImportError:
    sys.exit("PyYAML 필요: pip install pyyaml")

KST = timezone(timedelta(hours=9))

_ROOT = Path(__file__).resolve().parent.parent
_FRAMEWORK_DIR = _ROOT / "data/staged_updates/post_phase_0"
_ASSUMPTIONS_PATH = _FRAMEWORK_DIR / "assumptions.yaml"
_DECISION_LOG_PATH = _FRAMEWORK_DIR / "decision_log.jsonl"


def _load_portfolio() -> Dict[str, Any]:
    p = _ROOT / "data" / "portfolio.json"
    if not p.exists():
        return {}
    try:
        text = p.read_text(encoding="utf-8")
        text = text.replace("NaN", "null").replace("Infinity", "null").replace("-Infinity", "null")
        return json.loads(text)
    except Exception:
        return {}


def _load_phase_0_results() -> Dict[str, Any]:
    p = _ROOT / "data/metadata/phase_0_results.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _last_deadman_trigger() -> Optional[str]:
    p = _ROOT / "data/metadata/operator_deadman_log.jsonl"
    if not p.exists():
        return None
    try:
        lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
        for ln in reversed(lines):
            try:
                obj = json.loads(ln)
            except Exception:
                continue
            if obj.get("_meta_only"):
                continue
            return obj.get("trigger")
        return None
    except Exception:
        return None


def _atr_migration_log_count() -> int:
    p = _ROOT / "data/metadata/atr_migration_log.jsonl"
    if not p.exists():
        return 0
    try:
        return sum(1 for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip())
    except Exception:
        return 0


# ── assumption check 함수 ──
# 각 함수는 (current_value, status) 튜플 반환. status: valid | invalid | unknown

def _check_A1(_assumption: Dict[str, Any]) -> tuple:
    p = _load_portfolio()
    vix = (((p.get("macro") or {}).get("vix") or {}).get("value"))
    if not isinstance(vix, (int, float)):
        return None, "unknown"
    threshold = float(_assumption.get("threshold", 25.0))
    return float(vix), "valid" if vix < threshold else "invalid"


def _check_A2(_assumption: Dict[str, Any]) -> tuple:
    r = _load_phase_0_results()
    verdict = r.get("verdict_smoke")
    allowed = _assumption.get("allowed_values") or []
    if verdict in (None, "insufficient_data"):
        return verdict, "unknown"
    return verdict, "valid" if verdict in allowed else "invalid"


def _check_A3(_assumption: Dict[str, Any]) -> tuple:
    p = _load_portfolio()
    us10 = (((p.get("macro") or {}).get("us_10y") or {}).get("value"))
    if not isinstance(us10, (int, float)):
        return None, "unknown"
    threshold = float(_assumption.get("threshold", 4.5))
    return float(us10), "valid" if us10 < threshold else "invalid"


def _check_A4(_assumption: Dict[str, Any]) -> tuple:
    trigger = _last_deadman_trigger()
    if trigger is None:
        return None, "unknown"
    forbidden = _assumption.get("forbidden_values") or []
    return trigger, "invalid" if trigger in forbidden else "valid"


def _check_A5(_assumption: Dict[str, Any]) -> tuple:
    n = _atr_migration_log_count()
    return n, "valid" if n > 0 else "unknown"


_CHECKS = {
    "A1": _check_A1,
    "A2": _check_A2,
    "A3": _check_A3,
    "A4": _check_A4,
    "A5": _check_A5,
}


def _refresh_assumptions(dry_run: bool = False) -> Dict[str, Dict[str, Any]]:
    if not _ASSUMPTIONS_PATH.exists():
        sys.exit(f"assumptions.yaml 없음: {_ASSUMPTIONS_PATH}")
    with open(_ASSUMPTIONS_PATH, "r", encoding="utf-8") as f:
        registry = yaml.safe_load(f) or {}

    now_iso = datetime.now(KST).isoformat()
    for aid, payload in list(registry.items()):
        if aid.startswith("_"):
            continue
        check = _CHECKS.get(aid)
        if not check:
            continue
        try:
            current, status = check(payload)
        except Exception as e:
            current, status = None, "unknown"
            payload["last_check_error"] = str(e)[:200]
        payload["current_value"] = current
        payload["status"] = status
        payload["last_checked_at"] = now_iso

    if not dry_run:
        with open(_ASSUMPTIONS_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(registry, f, sort_keys=False, allow_unicode=True)

    return registry


def _load_decision_log() -> List[Dict[str, Any]]:
    if not _DECISION_LOG_PATH.exists():
        return []
    rows = []
    for ln in _DECISION_LOG_PATH.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            obj = json.loads(ln)
        except Exception:
            continue
        if obj.get("_meta_only"):
            rows.append(obj)
            continue
        rows.append(obj)
    return rows


def _write_decision_log(rows: List[Dict[str, Any]], dry_run: bool = False) -> None:
    if dry_run:
        return
    out_lines = []
    for r in rows:
        out_lines.append(json.dumps(r, ensure_ascii=False))
    _DECISION_LOG_PATH.write_text("\n".join(out_lines) + "\n", encoding="utf-8")


def _cascade(rows: List[Dict[str, Any]], registry: Dict[str, Any]) -> Dict[str, int]:
    """assumption invalidate → item strikethrough. hard cascade / soft flag."""
    invalid_assumptions = {
        aid for aid, p in registry.items()
        if not aid.startswith("_") and isinstance(p, dict) and p.get("status") == "invalid"
    }

    items = [r for r in rows if not r.get("_meta_only")]
    items_by_id = {it.get("id"): it for it in items if it.get("id")}

    stats = {"assumption_strikethrough": 0, "hard_cascade": 0, "soft_flag": 0}

    # 1) assumption 직접 의존 strikethrough
    for it in items:
        if it.get("applied_at"):
            continue  # 이미 apply 된 항목은 건드리지 않음
        deps_a = set(it.get("depends_on_assumptions") or [])
        broken = deps_a & invalid_assumptions
        if broken:
            it["strikethrough"] = True
            it["strikethrough_reason"] = f"assumption invalidated: {sorted(broken)}"
            stats["assumption_strikethrough"] += 1

    # 2) item 의존 cascade (hard) / flag (soft) — fixpoint 까지 반복
    changed = True
    while changed:
        changed = False
        for it in items:
            if it.get("applied_at"):
                continue
            if it.get("strikethrough"):
                continue
            deps_i = it.get("depends_on_items") or []
            hard_invalid = []
            soft_invalid = []
            for d in deps_i:
                if not isinstance(d, dict):
                    continue
                dep_id = d.get("id")
                dep_type = (d.get("type") or "hard").lower()
                dep_item = items_by_id.get(dep_id)
                if dep_item and dep_item.get("strikethrough"):
                    if dep_type == "soft":
                        soft_invalid.append(dep_id)
                    else:
                        hard_invalid.append(dep_id)
            if hard_invalid:
                it["strikethrough"] = True
                it["strikethrough_reason"] = f"hard cascade from: {hard_invalid}"
                stats["hard_cascade"] += 1
                changed = True
            elif soft_invalid:
                if not it.get("flag_for_review"):
                    it["flag_for_review"] = True
                    it["flag_for_review_reason"] = f"soft dep invalidated: {soft_invalid}"
                    stats["soft_flag"] += 1

    return stats


def main() -> int:
    p = argparse.ArgumentParser(description="Refresh staged_updates assumption registry + cascade strikethrough.")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    registry = _refresh_assumptions(dry_run=args.dry_run)
    rows = _load_decision_log()
    stats = _cascade(rows, registry)
    if not args.dry_run:
        _write_decision_log(rows)

    # 요약 출력
    total = sum(1 for r in rows if not r.get("_meta_only"))
    applied = sum(1 for r in rows if r.get("applied_at"))
    strikethrough = sum(1 for r in rows if r.get("strikethrough"))
    flagged = sum(1 for r in rows if r.get("flag_for_review") and not r.get("strikethrough"))
    alive = total - applied - strikethrough

    print(f"=== Assumption Registry ===")
    for aid, payload in registry.items():
        if aid.startswith("_") or not isinstance(payload, dict):
            continue
        sym = {"valid": "✓", "invalid": "✗", "unknown": "?"}.get(payload.get("status"), "?")
        cv = payload.get("current_value")
        print(f"  {sym} {aid} {payload.get('description', '')} → {payload.get('status')} (current: {cv})")

    print(f"\n=== Decision Log ===")
    print(f"  total items     : {total}")
    print(f"  applied         : {applied}")
    print(f"  strikethrough   : {strikethrough}  (assumption: {stats['assumption_strikethrough']}, cascade: {stats['hard_cascade']})")
    print(f"  flag_for_review : {flagged}  (soft dep: {stats['soft_flag']})")
    print(f"  alive           : {alive}")

    if args.dry_run:
        print("\n[DRY RUN — 아무것도 안 씀]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
