"""
수동 Rollback — constitution 이전 스냅샷으로 되돌림.

사용:
  python3 scripts/rollback_strategy.py --list       # 버전 히스토리만 조회
  python3 scripts/rollback_strategy.py --dry-run    # 어디로 돌아갈지 미리보기
  python3 scripts/rollback_strategy.py              # 실제 rollback 실행

strategy_evolver.rollback_strategy() 를 CLI 로 노출.
직전 apply_proposal 의 pre_change_snapshot 을 찾아 constitution 복원.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_registry() -> dict:
    fp = ROOT / "data" / "strategy_registry.json"
    if not fp.exists():
        return {}
    return json.loads(fp.read_text(encoding="utf-8"))


def _print_history(registry: dict) -> None:
    versions = registry.get("versions", [])
    current = registry.get("current_version", 1)
    print(f"current_version: {current}")
    print(f"versions 총 {len(versions)}개, history {len(registry.get('history', []))}개")
    print()
    if not versions:
        print("(apply 이력 없음 — rollback 불가)")
        return
    print(f"{'ver':>4}  {'applied_at':<22}  {'by':<10}  reason")
    print("─" * 80)
    for v in versions:
        ver = v.get("version", "?")
        applied = str(v.get("applied_at", ""))[:19]
        by = str(v.get("proposed_by", ""))[:10]
        reason = str(v.get("reason", v.get("change_summary", "")))[:40]
        has_snap = "✓" if v.get("pre_change_snapshot") else " "
        marker = " ← CURRENT" if ver == current else ""
        print(f"{ver:>4}  {applied:<22}  {by:<10}  [{has_snap}] {reason}{marker}")
    print()
    print("[✓] = pre_change_snapshot 보유 (rollback 가능)")


def main() -> int:
    ap = argparse.ArgumentParser(description="Brain V2 constitution rollback")
    ap.add_argument("--list", action="store_true", help="버전 히스토리 출력만 하고 종료")
    ap.add_argument("--dry-run", action="store_true",
                    help="어느 스냅샷으로 복원할지 미리보기 (실제 변경 X)")
    args = ap.parse_args()

    registry = _load_registry()
    _print_history(registry)

    if args.list:
        return 0

    versions = registry.get("versions", [])
    if not versions:
        print("⚠ rollback 불가 — apply 이력 없음")
        return 1

    target = None
    for v in reversed(versions):
        if v.get("pre_change_snapshot"):
            target = v
            break

    if not target:
        print("⚠ rollback 불가 — pre_change_snapshot 보유 버전 없음 (구 registry)")
        return 1

    print(f"복원 대상: v{target['version']} 직전 스냅샷")
    snap = target.get("pre_change_snapshot", {})
    fw = snap.get("fact_score_weights") or {}
    sw = snap.get("sentiment_score_weights") or {}
    gt = snap.get("grade_thresholds") or {}
    print(f"  fact weights ({len(fw)} keys): {list(fw.keys())[:6]}...")
    print(f"  sent weights ({len(sw)} keys): {list(sw.keys())[:6]}...")
    print(f"  grade thresholds: {gt}")

    if args.dry_run:
        print()
        print("(dry-run: 실제 변경 없음)")
        return 0

    # 실제 실행
    from api.intelligence.strategy_evolver import rollback_strategy  # noqa: E402
    confirm = input("\n정말 rollback 하시겠습니까? [y/N] ").strip().lower()
    if confirm != "y":
        print("취소됨.")
        return 0

    new_ver = rollback_strategy()
    if new_ver is None:
        print("⚠ rollback 실패")
        return 1
    print(f"✓ rollback 완료 — new_version: v{new_ver}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
