#!/usr/bin/env python3
"""
data/reports/ 의 timestamped PDF (verity_<period>_<type>_YYYYMMDD_HHMM.pdf) 중
가장 최근 본을 alias 이름(verity_<period>_<type>.pdf) 으로 복사한다.

사용 케이스 (2026-05-03):
  cron 의 alias 생성 단계가 과거에 실행됐지만 alias 파일이 누락된 상태.
  Storage 업로드 스크립트는 alias 파일을 읽으므로, 이 스크립트로 alias 를
  복원한 뒤 upload_reports_to_supabase.py 를 돌리면 stale 이지만 즉시
  다운로드 가능한 상태가 된다.

옵션:
  --dry-run   복사할 파일만 출력
  --reports-dir 경로 (기본 data/reports)

종료 코드:
  0  성공 (1개 이상 복사 또는 0개)
  2  reports 디렉터리 없음
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

PERIODS = ("daily", "weekly", "monthly", "quarterly", "semi", "annual")
TYPES = ("admin", "public")

# verity_<period>_<type>_<8digits>_<4digits>.pdf
_TIMESTAMP_RE = re.compile(r"_(\d{8})_(\d{4})\.pdf$")


def latest_for(reports_dir: Path, period: str, kind: str) -> Path | None:
    prefix = f"verity_{period}_{kind}_"
    candidates: list[tuple[str, Path]] = []
    for p in reports_dir.iterdir():
        if not p.is_file() or not p.name.startswith(prefix):
            continue
        m = _TIMESTAMP_RE.search(p.name)
        if not m:
            continue
        # YYYYMMDD + HHMM 사전식 정렬 = 시간순
        candidates.append((m.group(1) + m.group(2), p))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reports-dir", default="data/reports")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    reports_dir = Path(args.reports_dir)
    if not reports_dir.is_dir():
        print(f"ERROR: {reports_dir} 가 존재하지 않음", file=sys.stderr)
        return 2

    copied = 0
    skipped = 0
    for period in PERIODS:
        for kind in TYPES:
            src = latest_for(reports_dir, period, kind)
            alias = reports_dir / f"verity_{period}_{kind}.pdf"
            if src is None:
                print(f"  ─ verity_{period}_{kind}: timestamped 파일 없음")
                skipped += 1
                continue
            if args.dry_run:
                print(f"  [dry] {src.name} → {alias.name}")
                copied += 1
                continue
            shutil.copy2(src, alias)
            size = alias.stat().st_size
            print(f"  ✓ {src.name} → {alias.name} ({size:,} bytes)")
            copied += 1

    print(f"\ncopied={copied} skipped={skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
