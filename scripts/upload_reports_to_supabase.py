#!/usr/bin/env python3
"""
data/reports/verity_<period>_<type>.pdf alias 파일들을
Supabase Storage 의 verity-reports private bucket 으로 업로드.

cron (.github/workflows/reports_v2_cron.yml) 의 PDF 생성 직후 실행.
프론트는 vercel-api `/api/reports?period=&type=` 가 발급하는 signed URL 로 다운로드.

환경변수:
  SUPABASE_URL              필수
  SUPABASE_SERVICE_ROLE_KEY 필수 (RLS 우회 + Storage write)
  REPORTS_DIR               선택 (기본 data/reports)

종료 코드:
  0  성공 (1개 이상 업로드 또는 alias 0개)
  1  부분 실패 (있는 alias 중 일부 실패)
  2  설정 오류 (env 미설정)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

PERIODS = ("daily", "weekly", "monthly", "quarterly", "semi", "annual")
TYPES = ("admin", "public")
BUCKET = "verity-reports"


def main() -> int:
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    reports_dir = Path(os.environ.get("REPORTS_DIR", "data/reports"))

    if not supabase_url or not service_key:
        print("ERROR: SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 미설정", file=sys.stderr)
        return 2

    if not reports_dir.is_dir():
        print(f"WARN: {reports_dir} 가 존재하지 않음 — 업로드 0개")
        return 0

    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/pdf",
        # x-upsert: true → 같은 path 에 덮어쓰기. 매 cron 마다 latest alias 갱신.
        "x-upsert": "true",
        "Cache-Control": "no-store",
    }

    uploaded = 0
    skipped = 0
    failed = 0

    for period in PERIODS:
        for kind in TYPES:
            filename = f"verity_{period}_{kind}.pdf"
            local_path = reports_dir / filename
            if not local_path.is_file():
                skipped += 1
                continue

            url = f"{supabase_url}/storage/v1/object/{BUCKET}/{filename}"
            try:
                with local_path.open("rb") as fp:
                    r = requests.post(url, headers=headers, data=fp.read(), timeout=60)
                if r.status_code in (200, 201):
                    size = local_path.stat().st_size
                    print(f"  ✓ {filename} ({size:,} bytes)")
                    uploaded += 1
                else:
                    print(f"  ✗ {filename} HTTP {r.status_code}: {r.text[:200]}",
                          file=sys.stderr)
                    failed += 1
            except (requests.RequestException, OSError) as e:
                print(f"  ✗ {filename} error: {e}", file=sys.stderr)
                failed += 1

    print(f"\nuploaded={uploaded} skipped={skipped} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
