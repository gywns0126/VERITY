"""
purge_raw.py — Sharadar 컴플라이언스 purge (CoMOM 파이프라인 §5). 🚨 DESTRUCTIVE, 게이트.

2026-06-14 신설(raw만), 2026-06-15 재작성(파생 포함). 🚨 1차 약관 검증(2026-06-15):
종료 시 30일 내 **"all copies of the Services Data, AND all data sets derived from the Services Data,
and all software"** 삭제 + affidavit. → 삭제 대상 = raw + Sharadar-파생 모두.

🚨 trigger = 구독 *접근 종료(기간 만료)* 시점이지 지금이 아님 → **기본 dry-run**, 실삭제는 --confirm.
구독: ~2026-06-14 시작 = 접근 ~2026-07-14, 삭제 데드라인 ~2026-08-13.

삭제 대상:
  - raw: ~/Desktop/나스닥/SHARADAR_*.csv (~14GB, Services Data)
  - Sharadar 파생: features/*.parquet + comom_*.parquet + sharadar.duckdb (derived data sets)
보존(삭제 X):
  - ff3_weekly.parquet — Kenneth French 무료 데이터(Services Data 아님)
  - 코드(scripts/*.py) + 방법론 doc + CoMOM 고수준 결과/통계 = 합법 보존 자산(재구독 시 전량 재생성)

안전: 기본 dry-run. --confirm 시 affidavit manifest(삭제 목록+시각) 기록 후 삭제.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List

RAW_DIR_DEFAULT = os.path.expanduser("~/Desktop/나스닥")
LAKE_DIR = os.path.expanduser("~/VERITY_data_lake")
MANIFEST_PATH = os.path.join(LAKE_DIR, "purge_affidavit.json")

# Sharadar 파생 산출물 (삭제 대상). ff3_weekly.parquet = 무료 FF3 → 제외.
DERIVED_TARGETS = [
    os.path.join(LAKE_DIR, "comom_factor_monthly.parquet"),
    os.path.join(LAKE_DIR, "comom_13f_crosscheck.parquet"),
    os.path.join(LAKE_DIR, "comom_monthly.parquet"),
    os.path.join(LAKE_DIR, "sharadar.duckdb"),
]
DERIVED_GLOBS = [os.path.join(LAKE_DIR, "features", "*.parquet")]
KEEP_NOTE = "보존: ff3_weekly.parquet(무료 FF3) + scripts/*.py + docs/comom_methodology_v1 + 결과통계"


def _scan(paths_or_globs: List[str], is_glob: bool = False) -> List[Dict[str, object]]:
    files: List[str] = []
    if is_glob:
        for g in paths_or_globs:
            files.extend(glob.glob(g))
    else:
        files = [p for p in paths_or_globs if os.path.exists(p)]
    return [{"path": f, "bytes": os.path.getsize(f)} for f in sorted(set(files))]


def collect(raw_dir: str) -> Dict[str, List[Dict[str, object]]]:
    raw = _scan([os.path.join(raw_dir, "SHARADAR_*.csv")], is_glob=True)
    derived = _scan(DERIVED_TARGETS) + _scan(DERIVED_GLOBS, is_glob=True)
    return {"raw": raw, "derived": derived}


def purge(raw_dir: str = RAW_DIR_DEFAULT, confirm: bool = False) -> Dict[str, object]:
    groups = collect(raw_dir)
    raw_gb = sum(r["bytes"] for r in groups["raw"]) / 1e9
    der_mb = sum(r["bytes"] for r in groups["derived"]) / 1e6
    out: Dict[str, object] = {
        "raw_files": len(groups["raw"]), "raw_gb": round(raw_gb, 2),
        "derived_files": len(groups["derived"]), "derived_mb": round(der_mb, 1),
        "confirm": confirm, "deleted": [], "action": "dry-run", "keep": KEEP_NOTE,
    }
    if not confirm:
        out["note"] = "dry-run — 실삭제하려면 --confirm. (접근 종료~2026-07-14 후, 데드라인 ~2026-08-13)"
        return out

    # 합법 보존 자산 sanity (재생성 경로 유지 확인)
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    keepable_ok = os.path.exists(os.path.join(repo, "scripts", "sharadar", "build_comom.py"))
    if not keepable_ok:
        out["action"] = "거부(코드 부재)"
        out["note"] = "재생성 코드(build_comom.py) 미확인 → 삭제 중단."
        return out

    manifest = {
        "purged_at_utc": datetime.now(timezone.utc).isoformat(),
        "license": "Sharadar — Services Data + derived data sets deleted within 30d of termination",
        "raw_deleted": [{"name": os.path.basename(r["path"]), "bytes": r["bytes"]} for r in groups["raw"]],
        "derived_deleted": [{"name": os.path.basename(r["path"]), "bytes": r["bytes"]} for r in groups["derived"]],
        "raw_gb": round(raw_gb, 2), "derived_mb": round(der_mb, 1),
        "retained": KEEP_NOTE,
    }
    os.makedirs(LAKE_DIR, exist_ok=True)
    with open(MANIFEST_PATH, "w") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)

    deleted = []
    for grp in ("raw", "derived"):
        for r in groups[grp]:
            try:
                os.remove(r["path"])
                deleted.append(os.path.basename(r["path"]))
            except OSError as e:
                out.setdefault("errors", []).append(f"{r['path']}: {e}")
    out["deleted"] = deleted
    out["action"] = f"삭제완료 {len(deleted)}개 (raw {raw_gb:.1f}GB + 파생 {der_mb:.0f}MB)"
    out["manifest"] = MANIFEST_PATH
    return out


def _print(res: Dict[str, object]) -> None:
    print("[purge_raw] Sharadar 컴플라이언스 purge (§5) — 🚨 DESTRUCTIVE, 기본 dry-run")
    print(f"  raw(Services Data): {res['raw_files']}개 {res['raw_gb']}GB")
    print(f"  파생(derived data sets): {res['derived_files']}개 {res['derived_mb']}MB")
    print(f"  {res['keep']}")
    print(f"  결과: {res['action']}")
    if res.get("note"):
        print(f"  → {res['note']}")
    if res.get("deleted"):
        print(f"  affidavit manifest: {res.get('manifest')}")
    if res.get("errors"):
        print(f"  ⚠️ 오류: {res['errors']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", default=RAW_DIR_DEFAULT)
    ap.add_argument("--confirm", action="store_true", help="🚨 실삭제 (접근 종료 후, 데드라인 전)")
    args = ap.parse_args()
    try:
        _print(purge(args.raw_dir, confirm=args.confirm))
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[purge_raw] 실패: {type(e).__name__}: {e}\n")
        raise
