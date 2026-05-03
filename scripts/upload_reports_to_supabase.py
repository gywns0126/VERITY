#!/usr/bin/env python3
"""
data/reports/ 의 PDF 들을 Supabase Storage `verity-reports` private bucket 에 업로드.

업로드 대상 두 갈래:
  1) latest alias  — verity_<period>_<type>.pdf
                     → bucket 루트 verity_<period>_<type>.pdf
                     매 cron 마다 덮어쓰기. 프론트의 "오늘 리포트" 다운로드.
  2) dated archive — verity_<period>_<type>_<YYYYMMDD>_<HHMM>.pdf
                     → archive/<period>/<type>/<YYYY-MM-DD>.pdf
                     일자별 1개 (같은 날 여러 run 은 마지막이 덮어씀).
                     프론트의 "이전 리포트 보기" 모달.

cron (.github/workflows/reports_v2_cron.yml) 의 PDF 생성 직후 실행.
프론트는 vercel-api `/api/reports?period=&type=[&date=|&action=list]` 로 접근.

환경변수:
  SUPABASE_URL              필수
  SUPABASE_SERVICE_ROLE_KEY 필수 (RLS 우회 + Storage write)
  REPORTS_DIR               선택 (기본 data/reports)

종료 코드:
  0  성공 (1개 이상 업로드 또는 0개)
  1  부분 실패
  2  설정 오류 (env 미설정)
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import requests

PERIODS = ("daily", "weekly", "monthly", "quarterly", "semi", "annual")
TYPES = ("admin", "public")
BUCKET = "verity-reports"

# verity_<period>_<type>_<YYYYMMDD>_<HHMM>.pdf 패턴 — group(1)=YYYYMMDD, group(2)=HHMM
_DATED_RE = re.compile(r"^verity_([a-z]+)_([a-z]+)_(\d{8})_(\d{4})\.pdf$")


def _put(supabase_url: str, headers: dict, path: str, body: bytes) -> tuple[int, str]:
    url = f"{supabase_url}/storage/v1/object/{BUCKET}/{path}"
    r = requests.post(url, headers=headers, data=body, timeout=60)
    return r.status_code, r.text[:200] if r.text else ""


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
        # x-upsert: true → 같은 path 덮어쓰기.
        "x-upsert": "true",
        "Cache-Control": "no-store",
    }

    uploaded = 0
    skipped = 0
    failed = 0

    # ── 1) latest alias 업로드 ─────────────────────────────────
    print("[alias]")
    for period in PERIODS:
        for kind in TYPES:
            filename = f"verity_{period}_{kind}.pdf"
            local_path = reports_dir / filename
            if not local_path.is_file():
                skipped += 1
                continue
            try:
                body = local_path.read_bytes()
                code, txt = _put(supabase_url, headers, filename, body)
                if code in (200, 201):
                    print(f"  ✓ {filename} ({len(body):,} bytes)")
                    uploaded += 1
                else:
                    print(f"  ✗ {filename} HTTP {code}: {txt}", file=sys.stderr)
                    failed += 1
            except (requests.RequestException, OSError) as e:
                print(f"  ✗ {filename} error: {e}", file=sys.stderr)
                failed += 1

    # ── 2) dated archive 업로드 ────────────────────────────────
    # 같은 (period, kind, YYYY-MM-DD) 안에 여러 run 이 있으면 HHMM 가장 큰 것만.
    print("\n[archive]")
    grouped: dict[tuple[str, str, str], tuple[str, Path]] = {}
    for p in reports_dir.iterdir():
        if not p.is_file():
            continue
        m = _DATED_RE.match(p.name)
        if not m:
            continue
        period, kind, ymd, hm = m.group(1), m.group(2), m.group(3), m.group(4)
        if period not in PERIODS or kind not in TYPES:
            continue
        ymd_iso = f"{ymd[0:4]}-{ymd[4:6]}-{ymd[6:8]}"
        key = (period, kind, ymd_iso)
        prev = grouped.get(key)
        if prev is None or hm > prev[0]:
            grouped[key] = (hm, p)

    for (period, kind, ymd_iso), (_hm, src) in sorted(grouped.items()):
        archive_path = f"archive/{period}/{kind}/{ymd_iso}.pdf"
        try:
            body = src.read_bytes()
            code, txt = _put(supabase_url, headers, archive_path, body)
            if code in (200, 201):
                print(f"  ✓ {archive_path} ← {src.name} ({len(body):,} bytes)")
                uploaded += 1
            else:
                print(f"  ✗ {archive_path} HTTP {code}: {txt}", file=sys.stderr)
                failed += 1
        except (requests.RequestException, OSError) as e:
            print(f"  ✗ {archive_path} error: {e}", file=sys.stderr)
            failed += 1

    print(f"\nuploaded={uploaded} skipped={skipped} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
