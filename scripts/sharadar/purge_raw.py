"""
purge_raw.py — Sharadar raw CSV purge 도구 (CoMOM 파이프라인 §5). 🚨 DESTRUCTIVE, 게이트.

2026-06-14 신설. 라이선스(Personal Use): derived 는 우리 소유로 보존, **raw 는 구독 취소 30일 내
purge 의무**(affidavit 가능). 본 도구 = 그 의무 이행용. 단, purge 트리거 = *구독 취소 시점*이지
지금이 아님 → **기본 dry-run**, 실삭제는 --confirm 명시 + derived 보존 검증 통과 시에만.

안전 설계 (되돌릴 수 없는 삭제):
  1) 기본 = dry-run (무엇이 삭제될지 + derived 보존 상태만 출력).
  2) --confirm 줘도, 필수 derived 산출물(materialized 테이블 + parquet) 전부 존재해야 삭제 진행.
     하나라도 없으면 거부(raw 만이 유일 소스인 상태에서 삭제 차단).
  3) 삭제 직전 affidavit 용 manifest(보존 derived 목록 + 크기 + 시각) 기록.

🚨 raw 뷰(SEP/SF1/DAILY 등)는 raw CSV 를 참조 → purge 후 뷰 쿼리는 실패하나, materialized
derived 테이블(BASE TABLE)은 영속(독립). 재빌드 필요 시 = 재구독/재다운로드.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List

DB_PATH_DEFAULT = os.path.expanduser("~/VERITY_data_lake/sharadar.duckdb")
RAW_DIR_DEFAULT = os.path.expanduser("~/Desktop/나스닥")
LAKE_DIR = os.path.expanduser("~/VERITY_data_lake")
MANIFEST_PATH = os.path.join(LAKE_DIR, "purge_manifest.json")

# 필수 derived: 이것들이 전부 있어야 raw 삭제 허용 (raw 가 유일 소스인 상태 차단)
REQUIRED_TABLES = ["universe_common", "sp500_membership", "comom_factor_monthly"]
OPTIONAL_TABLES = ["comom_13f_crosscheck"]
REQUIRED_PARQUETS = [
    os.path.join(LAKE_DIR, "comom_factor_monthly.parquet"),
    os.path.join(LAKE_DIR, "ff3_weekly.parquet"),
]


def _table_info(db_path: str) -> Dict[str, str]:
    """{table_name: table_type} (BASE TABLE vs VIEW)."""
    import duckdb
    con = duckdb.connect(db_path, read_only=True)
    try:
        return {r[0]: r[1] for r in con.execute(
            "SELECT table_name, table_type FROM information_schema.tables"
        ).fetchall()}
    finally:
        con.close()


def verify_derived(db_path: str) -> Dict[str, object]:
    """derived 보존 상태 검증. 모든 필수 테이블=BASE TABLE + 필수 parquet 존재해야 ok."""
    info = _table_info(db_path)
    tbl_ok = {t: (info.get(t) == "BASE TABLE") for t in REQUIRED_TABLES}
    opt = {t: (info.get(t) == "BASE TABLE") for t in OPTIONAL_TABLES}
    pq_ok = {p: os.path.exists(p) for p in REQUIRED_PARQUETS}
    ok = all(tbl_ok.values()) and all(pq_ok.values())
    return {"ok": ok, "tables": tbl_ok, "optional_tables": opt, "parquets": pq_ok}


def scan_raw(raw_dir: str) -> List[Dict[str, object]]:
    files = sorted(glob.glob(os.path.join(raw_dir, "SHARADAR_*.csv")))
    return [{"path": f, "bytes": os.path.getsize(f)} for f in files]


def purge(db_path: str = DB_PATH_DEFAULT, raw_dir: str = RAW_DIR_DEFAULT,
          confirm: bool = False) -> Dict[str, object]:
    ver = verify_derived(db_path)
    raw = scan_raw(raw_dir)
    total_gb = sum(r["bytes"] for r in raw) / 1e9
    out: Dict[str, object] = {
        "derived_verified": ver, "raw_files": len(raw), "raw_total_gb": round(total_gb, 2),
        "confirm": confirm, "deleted": [], "action": "dry-run",
    }
    if not confirm:
        out["note"] = "dry-run — 실삭제하려면 --confirm. (구독 취소 시점에만 실행 권장)"
        return out
    if not ver["ok"]:
        out["action"] = "거부(derived 미보존)"
        out["note"] = "필수 derived 산출물 누락 → raw 가 유일 소스. 삭제 차단. build_comom 먼저 실행."
        return out

    # affidavit manifest 기록 후 삭제
    manifest = {
        "purged_at_utc": datetime.now(timezone.utc).isoformat(),
        "license": "Sharadar Personal Use — derived retained, raw purged per cancellation obligation",
        "derived_verified": ver,
        "raw_purged": [{"path": os.path.basename(r["path"]), "bytes": r["bytes"]} for r in raw],
        "raw_total_gb": round(total_gb, 2),
    }
    os.makedirs(LAKE_DIR, exist_ok=True)
    with open(MANIFEST_PATH, "w") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)

    deleted = []
    for r in raw:
        try:
            os.remove(r["path"])
            deleted.append(os.path.basename(r["path"]))
        except OSError as e:
            out.setdefault("errors", []).append(f"{r['path']}: {e}")
    out["deleted"] = deleted
    out["action"] = f"삭제완료 {len(deleted)}/{len(raw)} 파일 ({total_gb:.1f}GB)"
    out["manifest"] = MANIFEST_PATH
    return out


def _print(res: Dict[str, object]) -> None:
    ver = res["derived_verified"]
    print("[purge_raw] Sharadar raw purge (§5) — 🚨 DESTRUCTIVE, 기본 dry-run")
    print(f"  derived 보존 검증: {'✅ OK' if ver['ok'] else '❌ 미보존'}")
    for t, ok in ver["tables"].items():
        print(f"    table {t}: {'✅' if ok else '❌ 누락'}")
    for t, ok in ver["optional_tables"].items():
        print(f"    table {t} (opt): {'✅' if ok else '— 없음'}")
    for p, ok in ver["parquets"].items():
        print(f"    parquet {os.path.basename(p)}: {'✅' if ok else '❌ 누락'}")
    print(f"  raw: {res['raw_files']}개 파일, {res['raw_total_gb']}GB")
    print(f"  결과: {res['action']}")
    if res.get("note"):
        print(f"  → {res['note']}")
    if res.get("deleted"):
        print(f"  삭제 manifest: {res.get('manifest')}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-path", default=DB_PATH_DEFAULT)
    ap.add_argument("--raw-dir", default=RAW_DIR_DEFAULT)
    ap.add_argument("--confirm", action="store_true", help="🚨 실삭제 (구독 취소 시점에만)")
    args = ap.parse_args()
    try:
        _print(purge(args.db_path, args.raw_dir, confirm=args.confirm))
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[purge_raw] 실패: {type(e).__name__}: {e}\n")
        raise
