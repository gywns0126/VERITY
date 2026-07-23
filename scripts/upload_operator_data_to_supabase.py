#!/usr/bin/env python3
"""VERITY↔AlphaNest 분리 Stage 1 (2026-07-23): 오퍼레이터 full 데이터를 private Supabase Storage 업로드.

공개 blob(sanitize 예정)과 별도로, full portfolio.json (+ 향후 오퍼레이터 파일) 을 verity-reports
private bucket 에 올려 /api/admin(authed, ?type=portfolio_full) 이 서빙. 발행 파이프라인
(daily_analysis_full)에서 portfolio.json 확정 후 실행. SUPABASE_SERVICE_ROLE_KEY 필요(이미 등록).

패턴 = scripts/upload_reports_to_supabase.py 정합(POST storage/v1/object + x-upsert). JSON parse
검증 후 업로드(깨진 발행 방지, [[feedback_published_json_parse_verify]]).
"""
from __future__ import annotations

import json
import os
import sys

import requests

BUCKET = os.environ.get("OPERATOR_BUCKET", "verity-reports")

# (로컬 소스, bucket 내 경로, content-type).
# 2026-07-23 분리 Stage 3 후속: 오퍼레이터 전용 파일(public-probe 소비 0)을 private bucket 으로.
# 공개 발행 제거(action.yml)와 짝 — authed /api/admin?type=<name> 라우트로 서빙.
UPLOADS = [
    ("data/portfolio.json", "_operator/portfolio_full.json", "application/json"),
    ("data/history.json", "_operator/history.json", "application/json"),
    ("data/system_health_snapshot.json", "_operator/system_health_snapshot.json", "application/json"),
    ("data/brain_kb_usage.json", "_operator/brain_kb_usage.json", "application/json"),
    ("data/admin_todos.json", "_operator/admin_todos.json", "application/json"),
]


def main() -> int:
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not supabase_url or not key:
        print("ERROR: SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 미설정 — 업로드 불가", file=sys.stderr)
        return 2

    ok = 0
    for src, dest, ctype in UPLOADS:
        if not os.path.isfile(src):
            print(f"WARN: {src} 부재 — skip")
            continue
        with open(src, "rb") as f:
            body = f.read()
        # JSON parse 검증 — 깨진 파일 업로드 차단(오퍼레이터 콘솔 파손 방지)
        if ctype == "application/json":
            try:
                json.loads(body)
            except ValueError as e:
                print(f"ERROR: {src} JSON parse 실패 — skip: {e}", file=sys.stderr)
                continue
        try:
            r = requests.post(
                f"{supabase_url}/storage/v1/object/{BUCKET}/{dest}",
                headers={
                    "apikey": key,
                    "Authorization": f"Bearer {key}",
                    "Content-Type": ctype,
                    "x-upsert": "true",       # 같은 path 덮어쓰기
                    "Cache-Control": "no-store",
                },
                data=body,
                timeout=60,
            )
        except requests.RequestException as e:
            print(f"  ✗ {src} → 요청 실패: {e}", file=sys.stderr)
            continue
        if r.status_code in (200, 201):
            print(f"  ✓ {src} → {BUCKET}/{dest} ({len(body):,} bytes)")
            ok += 1
        else:
            print(f"  ✗ {src} → {r.status_code} {r.text[:150]}", file=sys.stderr)

    print(f"operator upload: {ok}/{len(UPLOADS)}")
    # 부분 실패도 발행 파이프라인 중단 X (fallback = 공개 blob) — 단 stderr 로 명시.
    return 0


if __name__ == "__main__":
    sys.exit(main())
