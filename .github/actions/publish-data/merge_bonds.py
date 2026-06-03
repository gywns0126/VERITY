"""
publish-data 단계 inline merge — portfolio.json 의 bonds 섹션을 bonds.json 으로 갱신.

배경 (2026-06-03): bonds 를 공유 portfolio.json 에 쓰면 고빈도 writer(price_pulse 등)와
git rebase(-X theirs) 충돌 시 bonds 변경이 버려짐(race 패배). price_pulse 와 동일하게
bonds 를 별도 파일(data/bonds.json, 단일 writer)로 분리하고, publish 시점에 inline merge
→ 컴포넌트가 보는 portfolio.bonds 가 항상 fresh. bonds.json 미존재/손상 시 silent skip.

사용:
    python3 merge_bonds.py <portfolio.json path> <bonds.json path>
결과: portfolio.json 을 in-place 갱신 (bonds 섹션 전체 override).
"""
from __future__ import annotations

import json
import sys


def main(portfolio_path: str, bonds_path: str) -> int:
    try:
        with open(portfolio_path, "r", encoding="utf-8") as f:
            p = json.load(f)
    except Exception as e:
        print(f"  ✗ portfolio.json 읽기 실패: {e}")
        return 1

    try:
        with open(bonds_path, "r", encoding="utf-8") as f:
            bonds = json.load(f)
    except Exception as e:
        print(f"  ✗ bonds.json 읽기 실패: {e} — merge skip, portfolio 원본 유지")
        return 0

    # bonds.json 이 정상 구조(yield_curves 보유)일 때만 override — 부분/손상 시 원본 유지.
    if not isinstance(bonds, dict) or not bonds.get("yield_curves"):
        print("  ✗ bonds.json 구조 비정상 — merge skip")
        return 0

    p["bonds"] = bonds

    with open(portfolio_path, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False)

    yc = bonds.get("yield_curves", {})
    print(
        f"  ✓ bonds merged: US={len((yc.get('us') or {}).get('curve', []))}만기 "
        f"KR={len((yc.get('kr') or {}).get('curve', []))}만기 "
        f"updated_at={bonds.get('updated_at')}"
    )
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: merge_bonds.py <portfolio.json> <bonds.json>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
