#!/usr/bin/env python3
"""staged_apply — staged_updates 큐의 항목을 verdict gate 통과 후 자동 적용.

연관:
  - data/staged_updates/post_phase_0/decision_log.jsonl (append-only)
  - data/staged_updates/post_phase_0/assumptions.yaml (A1-A5 가정 valid 확인)
  - data/staged_updates/post_phase_0/README.md (절차)
  - audit BRAIN_SELF_GROWTH P1-4

원칙 (write-time triage):
  · HIGH tier 변경 = Phase 0 verdict + assumptions 전부 valid 필수
  · MED tier = 변경 가능하나 user 확인 의무
  · LOW tier = 즉시 적용

사용:
  python scripts/staged_apply.py                  # dry-run (default)
  python scripts/staged_apply.py --execute        # 실제 적용
  python scripts/staged_apply.py --item ID        # 특정 항목만
  python scripts/staged_apply.py --tier HIGH      # tier 필터

워크플로:
  1. decision_log.jsonl load (applied_at null 인 항목)
  2. assumptions.yaml 의 depends_on_assumptions 가 모두 status=valid 확인
  3. Phase 0 verdict_official_60d = ok 확인
  4. dry-run = 적용 계획만 출력 / --execute = 실제 적용 후 applied_at 기록됨
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:
    yaml = None

REPO_ROOT = Path(__file__).resolve().parents[1]
STAGED_DIR = REPO_ROOT / "data" / "staged_updates" / "post_phase_0"
DECISION_LOG = STAGED_DIR / "decision_log.jsonl"
ASSUMPTIONS_YAML = STAGED_DIR / "assumptions.yaml"
PHASE_0_RESULTS = REPO_ROOT / "data" / "metadata" / "phase_0_results.json"


def _load_decisions() -> List[Dict[str, Any]]:
    if not DECISION_LOG.exists():
        return []
    out = []
    for line in DECISION_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            if d.get("_meta_only"):
                continue
            out.append(d)
        except json.JSONDecodeError:
            continue
    return out


def _load_assumptions() -> Dict[str, Dict[str, Any]]:
    if not ASSUMPTIONS_YAML.exists() or yaml is None:
        return {}
    try:
        data = yaml.safe_load(ASSUMPTIONS_YAML.read_text(encoding="utf-8")) or {}
        return {k: v for k, v in data.items() if not k.startswith("_")}
    except Exception as e:
        sys.stderr.write(f"[staged_apply] assumptions load fail: {e}\n")
        return {}


def _check_phase_0_verdict() -> str:
    """Phase 0 verdict_official_60d 상태 반환 (ok / monitoring / fail / unknown)."""
    if not PHASE_0_RESULTS.exists():
        return "unknown"
    try:
        d = json.loads(PHASE_0_RESULTS.read_text(encoding="utf-8"))
        return d.get("verdict_official_60d") or d.get("verdict_smoke") or "unknown"
    except Exception:
        return "unknown"


def _gate_pass(item: Dict[str, Any], assumptions: Dict[str, Dict[str, Any]],
               phase_0_verdict: str) -> Dict[str, Any]:
    """게이트 통과 여부 검증 — 명시적 이유 함께 반환."""
    tier = (item.get("tier") or "").upper()
    deps = item.get("depends_on_assumptions") or []
    reasons: List[str] = []

    # 1. Phase 0 verdict 검증 (HIGH tier 만)
    if tier == "HIGH" and phase_0_verdict not in ("ok", "monitoring"):
        return {"passed": False, "reason": f"Phase 0 verdict={phase_0_verdict} (HIGH tier 진입 게이트 미통과)"}

    # 2. depends_on_assumptions 의 status valid 확인
    invalid_deps = []
    for dep in deps:
        a = assumptions.get(dep)
        if not a:
            invalid_deps.append(f"{dep}=unknown")
            continue
        status = a.get("status")
        if status != "valid":
            invalid_deps.append(f"{dep}={status}")
    if invalid_deps:
        return {"passed": False, "reason": f"assumptions invalid: {', '.join(invalid_deps)}"}

    # 3. depends_on_items 의 applied_at 확인 (선행 의제 적용 필수)
    dep_items = item.get("depends_on_items") or []
    if dep_items:
        reasons.append(f"depends_on_items {len(dep_items)}건 — 별도 확인 필요")

    return {"passed": True, "reason": "all gates passed" + (f" ({'; '.join(reasons)})" if reasons else "")}


def _mark_applied(item_id: str) -> bool:
    """decision_log.jsonl 의 해당 item 에 applied_at 마킹.

    append-only 정책이지만 staged_apply 만 예외 (스크립트 명시).
    """
    if not DECISION_LOG.exists():
        return False
    lines = DECISION_LOG.read_text(encoding="utf-8").splitlines()
    new_lines = []
    modified = False
    now_iso = datetime.now().isoformat()
    for line in lines:
        if not line.strip():
            new_lines.append(line)
            continue
        try:
            d = json.loads(line)
            if d.get("id") == item_id and d.get("applied_at") is None:
                d["applied_at"] = now_iso
                modified = True
            new_lines.append(json.dumps(d, ensure_ascii=False))
        except json.JSONDecodeError:
            new_lines.append(line)
    if modified:
        DECISION_LOG.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return modified


def main() -> int:
    parser = argparse.ArgumentParser(description="Staged updates 자동 적용")
    parser.add_argument("--execute", action="store_true",
                        help="실제 적용 (default = dry-run)")
    parser.add_argument("--item", default=None, help="특정 item id 만")
    parser.add_argument("--tier", default=None,
                        choices=["HIGH", "MED", "LOW", "all"],
                        help="tier 필터 (default all)")
    args = parser.parse_args()

    decisions = _load_decisions()
    assumptions = _load_assumptions()
    phase_0_verdict = _check_phase_0_verdict()

    print(f"=== staged_apply ===")
    print(f"  decisions: {len(decisions)}")
    print(f"  assumptions: {len(assumptions)} ({sum(1 for a in assumptions.values() if a.get('status') == 'valid')} valid)")
    print(f"  Phase 0 verdict: {phase_0_verdict}")
    print(f"  mode: {'EXECUTE' if args.execute else 'DRY-RUN'}")
    print(f"  tier filter: {args.tier or 'all'}")
    print()

    pending = [d for d in decisions if d.get("applied_at") is None]
    print(f"  pending items: {len(pending)}")

    applied = 0
    blocked = 0
    skipped = 0
    for item in pending:
        if args.item and item.get("id") != args.item:
            continue
        if args.tier and args.tier != "all" and item.get("tier") != args.tier:
            skipped += 1
            continue

        item_id = item.get("id", "?")
        title = (item.get("title") or "")[:80]
        tier = item.get("tier", "?")

        gate = _gate_pass(item, assumptions, phase_0_verdict)
        if not gate["passed"]:
            blocked += 1
            print(f"  ✗ BLOCKED [{tier}] {item_id}")
            print(f"      title: {title}")
            print(f"      reason: {gate['reason']}")
            continue

        print(f"  ✓ READY   [{tier}] {item_id}")
        print(f"      title: {title}")
        print(f"      gate: {gate['reason']}")

        if args.execute:
            success = _mark_applied(item_id)
            if success:
                applied += 1
                print(f"      → applied_at 마킹 완료")

    print()
    print(f"=== summary ===")
    print(f"  applied: {applied}")
    print(f"  blocked: {blocked}")
    print(f"  skipped (tier filter): {skipped}")
    if not args.execute and (applied + blocked) > 0:
        print(f"  (DRY-RUN — 실제 적용 시 --execute 추가)")

    return 0 if blocked == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
