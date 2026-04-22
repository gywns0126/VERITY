"""
One-off 백필: data/history.json 의 기존 BUY/SELL 엔트리에 asset_class 필드 추가.

목적:
  compute_adjusted_return 이 asset_class 누락 시 'KR_STOCK'(0.18%) 로 가정 → 실제 ETF/US
  종목이 있었다면 과다 과세. 이를 ticker 포맷·이름 기반으로 분류해 소급 교정한다.

사용:
  python3 scripts/backfill_history_asset_class.py            # dry-run (기본)
  python3 scripts/backfill_history_asset_class.py --apply    # 실제 저장 (.bak 백업)

안전장치:
  - dry-run 이 기본. --apply 명시해야만 덮어쓴다.
  - 쓰기 전 원본을 history.json.bak 로 복사.
  - 이미 asset_class 가 있는 엔트리는 건너뜀 (idempotent).
  - DIVIDEND 같은 추가 type 은 건드리지 않음 (BUY/SELL 만 대상).
"""
import argparse
import json
import os
import shutil
import sys
from collections import Counter

# api/ 를 임포트 경로에 추가
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))

from api.config import HISTORY_PATH  # noqa: E402
from api.vams.engine import classify_asset  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill asset_class into history.json")
    ap.add_argument("--apply", action="store_true", help="실제 저장 (기본: dry-run)")
    ap.add_argument("--path", default=HISTORY_PATH, help="history.json 경로 (기본: data/history.json)")
    args = ap.parse_args()

    path = args.path
    if not os.path.exists(path):
        print(f"[오류] {path} 없음")
        return 1

    with open(path, "r", encoding="utf-8") as f:
        history = json.load(f)
    if not isinstance(history, list):
        print(f"[오류] {path} 은 리스트 형식이어야 함 (현재: {type(history).__name__})")
        return 1

    targets = []
    skipped_already = 0
    skipped_type = 0
    for i, entry in enumerate(history):
        if not isinstance(entry, dict):
            continue
        t = entry.get("type")
        if t not in ("BUY", "SELL"):
            skipped_type += 1
            continue
        if entry.get("asset_class"):
            skipped_already += 1
            continue
        ac = classify_asset(entry)
        targets.append((i, entry, ac))

    counter = Counter(ac for _, _, ac in targets)

    print(f"총 {len(history)}건 중 백필 대상: {len(targets)}건")
    print(f"  (skip) 이미 asset_class 있음: {skipped_already}건")
    print(f"  (skip) BUY/SELL 외 타입     : {skipped_type}건")
    print()
    print("분류 결과:")
    for ac, n in counter.most_common():
        print(f"  {ac:10s} {n}건")
    print()
    print("샘플(최대 8건):")
    for i, entry, ac in targets[:8]:
        t = entry.get("type")
        tk = entry.get("ticker")
        nm = entry.get("name")
        curr = entry.get("currency", "—")
        print(f"  [{i}] {t} {tk!s:10s} {str(nm)[:20]:20s} currency={curr!s:5s} → {ac}")

    if not args.apply:
        print()
        print("(dry-run 종료) --apply 추가하면 실제 저장.")
        return 0

    if not targets:
        print("\n백필할 대상 없음. 파일 변경 안 함.")
        return 0

    backup_path = path + ".bak"
    shutil.copy2(path, backup_path)
    for i, entry, ac in targets:
        history[i]["asset_class"] = ac

    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2, allow_nan=False)
    os.replace(tmp_path, path)

    print()
    print(f"[완료] {len(targets)}건 백필 적용. 백업: {backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
