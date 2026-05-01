#!/usr/bin/env python3
"""
staged_apply — Phase 0 staged_updates 강제기. apply 시점 룰 위반 차단.

룰 (5/17 review 시점에 본인 미래 본인 보호):
  1. tier 명시 필수 (HIGH | MEDIUM | LOW). 저장된 tier 와 매치되어야 함 (downgrade 차단).
  2. 모든 의존 assumption 이 valid 여야 함 (refresh_assumptions.py 통과).
  3. hard dep item 은 이미 applied 되어 있어야 함.
  4. 24h cooldown 사이 (마지막 MEDIUM/HIGH apply 시각 기준).
  5. HIGH 는 별도 --high-tier-confirm 플래그 필수.
  6. soft dep flag_for_review 떴으면 --soft-dep-acknowledged 필수.
  7. 강제 입력 플래그: --tier-evidence, --assumption-recheck-passed, --decision-log-rationale-still-valid.

dry-run 가능. apply 결과는 decision_log.jsonl 의 applied_at 갱신.

사용:
  python3 scripts/staged_apply.py --list
  python3 scripts/staged_apply.py --item learning_001 \\
    --risk-tier HIGH --high-tier-confirm \\
    --tier-evidence "brain_score 가중치 변경" \\
    --assumption-recheck-passed \\
    --decision-log-rationale-still-valid

추가 첫 항목 (수동 입력):
  python3 scripts/staged_apply.py --add \\
    --id learning_001 --title "..." --tier MEDIUM \\
    --depends-on-assumptions A1,A2 --rationale "..."
"""
from __future__ import annotations

import argparse
import json
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
_DECISION_LOG_PATH = _FRAMEWORK_DIR / "decision_log.jsonl"
_ASSUMPTIONS_PATH = _FRAMEWORK_DIR / "assumptions.yaml"

COOLDOWN_HOURS = 24


def _load_log() -> List[Dict[str, Any]]:
    if not _DECISION_LOG_PATH.exists():
        return []
    rows = []
    for ln in _DECISION_LOG_PATH.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            rows.append(json.loads(ln))
        except Exception:
            continue
    return rows


def _save_log(rows: List[Dict[str, Any]]) -> None:
    out = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n"
    _DECISION_LOG_PATH.write_text(out, encoding="utf-8")


def _load_assumptions() -> Dict[str, Any]:
    if not _ASSUMPTIONS_PATH.exists():
        return {}
    with open(_ASSUMPTIONS_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _now_iso() -> str:
    return datetime.now(KST).isoformat()


def _items(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in rows if not r.get("_meta_only")]


def cmd_list(args, rows: List[Dict[str, Any]]) -> int:
    items = _items(rows)
    if not items:
        print("(빈 큐)")
        return 0
    print(f"{'ID':22s} {'tier':6s} {'state':18s} {'applied':25s} title")
    print("-" * 100)
    for it in items:
        state = []
        if it.get("applied_at"):
            state.append("applied")
        if it.get("strikethrough"):
            state.append("X-out")
        if it.get("flag_for_review"):
            state.append("flag")
        if not state:
            state.append("alive")
        print(
            f"{it.get('id',''):22s} {it.get('tier','-'):6s} "
            f"{','.join(state):18s} {(it.get('applied_at') or '-'):25s} "
            f"{(it.get('title') or '')[:50]}"
        )
    return 0


def cmd_add(args, rows: List[Dict[str, Any]]) -> int:
    """새 staged item 추가 — write-time triage 룰 적용 시작점."""
    if not args.id:
        sys.exit("--id 필수")
    if not args.title:
        sys.exit("--title 필수")
    if args.tier not in ("HIGH", "MEDIUM", "LOW"):
        sys.exit("--tier 는 HIGH | MEDIUM | LOW")

    items = _items(rows)
    if any(it.get("id") == args.id for it in items):
        sys.exit(f"id {args.id} 이미 존재")

    deps_a = [a.strip() for a in (args.depends_on_assumptions or "").split(",") if a.strip()]

    # depends_on_items 파싱: "learning_005:hard,learning_007:soft"
    deps_i: List[Dict[str, str]] = []
    if args.depends_on_items:
        for tok in args.depends_on_items.split(","):
            tok = tok.strip()
            if not tok:
                continue
            if ":" in tok:
                dep_id, dep_type = tok.split(":", 1)
                dep_type = dep_type.strip().lower()
            else:
                dep_id, dep_type = tok, "hard"
            if dep_type not in ("hard", "soft"):
                sys.exit(f"dep type 은 hard | soft (item: {tok})")
            if dep_type == "soft" and not args.soft_justification:
                sys.exit(f"soft dep ({dep_id}) 시 --soft-justification 필수")
            entry = {"id": dep_id.strip(), "type": dep_type}
            if dep_type == "soft":
                entry["justification"] = args.soft_justification
            deps_i.append(entry)

    item = {
        "id": args.id,
        "added_at": _now_iso(),
        "title": args.title,
        "tier": args.tier,
        "depends_on_assumptions": deps_a,
        "depends_on_items": deps_i,
        "rationale": args.rationale or "",
        "applied_at": None,
        "strikethrough": False,
        "strikethrough_reason": None,
    }
    rows.append(item)
    _save_log(rows)
    print(f"✓ 추가됨: {args.id} ({args.tier})")
    return 0


def _last_apply_ts(items: List[Dict[str, Any]], tiers: List[str]) -> Optional[datetime]:
    latest: Optional[datetime] = None
    for it in items:
        if it.get("tier") not in tiers:
            continue
        ts = it.get("applied_at")
        if not ts:
            continue
        try:
            d = datetime.fromisoformat(ts)
            if d.tzinfo is None:
                d = d.replace(tzinfo=KST)
            if latest is None or d > latest:
                latest = d
        except Exception:
            continue
    return latest


def cmd_apply(args, rows: List[Dict[str, Any]]) -> int:
    if not args.item:
        sys.exit("--item 필수 (id)")
    items = _items(rows)
    target = next((it for it in items if it.get("id") == args.item), None)
    if not target:
        sys.exit(f"id {args.item} 없음")

    # ── 강제기 룰 ──
    errors: List[str] = []

    # 1. 이미 applied
    if target.get("applied_at"):
        errors.append(f"이미 applied: {target.get('applied_at')}")

    # 2. strikethrough
    if target.get("strikethrough"):
        errors.append(f"strikethrough: {target.get('strikethrough_reason')}")

    # 3. tier 매치
    stored_tier = target.get("tier")
    if args.risk_tier != stored_tier:
        errors.append(f"tier mismatch — stored={stored_tier}, supplied={args.risk_tier} (downgrade 차단)")

    # 4. 강제 플래그
    if not args.tier_evidence:
        errors.append("--tier-evidence 필수")
    if not args.assumption_recheck_passed:
        errors.append("--assumption-recheck-passed 필수 (refresh_assumptions.py 먼저 실행했는지 확인)")
    if not args.decision_log_rationale_still_valid:
        errors.append("--decision-log-rationale-still-valid 필수")

    # 5. HIGH tier
    if stored_tier == "HIGH" and not args.high_tier_confirm:
        errors.append("HIGH tier — --high-tier-confirm 필수")

    # 6. soft dep flag
    if target.get("flag_for_review") and not args.soft_dep_acknowledged:
        errors.append(f"flag_for_review: {target.get('flag_for_review_reason')} — --soft-dep-acknowledged 필수")

    # 7. assumption registry 재검증
    registry = _load_assumptions()
    invalid_assumptions = {
        aid for aid, p in registry.items()
        if not aid.startswith("_") and isinstance(p, dict) and p.get("status") == "invalid"
    }
    deps_a = set(target.get("depends_on_assumptions") or [])
    broken = deps_a & invalid_assumptions
    if broken:
        errors.append(f"invalid assumption 의존: {sorted(broken)} — refresh_assumptions.py 다시 실행 후 cascade 확인")

    # 8. hard dep applied 확인
    items_by_id = {it.get("id"): it for it in items}
    for d in target.get("depends_on_items") or []:
        if not isinstance(d, dict):
            continue
        if (d.get("type") or "hard").lower() != "hard":
            continue
        dep_item = items_by_id.get(d.get("id"))
        if not dep_item:
            errors.append(f"hard dep {d.get('id')} 항목 없음")
            continue
        if not dep_item.get("applied_at"):
            errors.append(f"hard dep {d.get('id')} 미적용 — 그것 먼저")

    # 9. cooldown — MEDIUM 또는 HIGH 일 때만 적용
    if stored_tier in ("MEDIUM", "HIGH"):
        last = _last_apply_ts(items, ["MEDIUM", "HIGH"])
        if last:
            elapsed = datetime.now(KST) - last
            if elapsed < timedelta(hours=COOLDOWN_HOURS):
                rem = timedelta(hours=COOLDOWN_HOURS) - elapsed
                errors.append(f"cooldown 미충족 — 마지막 MEDIUM/HIGH apply 후 {elapsed} 경과 (필요 {COOLDOWN_HOURS}h, 잔여 {rem})")

    if errors:
        print("✗ apply 거부 — 위반 사항:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(f"[DRY RUN] {args.item} apply 가능. 실 적용 시 --dry-run 빼고 재실행.")
        return 0

    target["applied_at"] = _now_iso()
    target["apply_metadata"] = {
        "tier_evidence": args.tier_evidence,
        "by_operator_at": _now_iso(),
    }
    _save_log(rows)
    print(f"✓ applied: {args.item} ({stored_tier}) at {target['applied_at']}")
    print("→ staged/post_phase_0 → main 머지 다음 단계 (수동 git merge).")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="staged_updates apply 강제기")
    sub = p.add_mutually_exclusive_group(required=True)
    sub.add_argument("--list", action="store_true", help="현재 큐 상태")
    sub.add_argument("--add", action="store_true", help="새 staged item 추가 (write-time)")
    sub.add_argument("--item", default=None, help="apply 할 item id")

    # add 용
    p.add_argument("--id", default=None)
    p.add_argument("--title", default=None)
    p.add_argument("--tier", default=None, choices=[None, "HIGH", "MEDIUM", "LOW"])
    p.add_argument("--depends-on-assumptions", default="", help="comma-separated A1,A2")
    p.add_argument("--depends-on-items", default="", help="comma-separated id:hard|soft")
    p.add_argument("--soft-justification", default=None)
    p.add_argument("--rationale", default="")

    # apply 용
    p.add_argument("--risk-tier", default=None, choices=[None, "HIGH", "MEDIUM", "LOW"])
    p.add_argument("--tier-evidence", default=None)
    p.add_argument("--assumption-recheck-passed", action="store_true")
    p.add_argument("--decision-log-rationale-still-valid", action="store_true")
    p.add_argument("--high-tier-confirm", action="store_true")
    p.add_argument("--soft-dep-acknowledged", action="store_true")
    p.add_argument("--dry-run", action="store_true")

    args = p.parse_args()

    rows = _load_log()
    if args.list:
        return cmd_list(args, rows)
    if args.add:
        return cmd_add(args, rows)
    return cmd_apply(args, rows)


if __name__ == "__main__":
    sys.exit(main())
