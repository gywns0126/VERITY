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
    # 2026-08-04 후보 편입/이탈 diff(오퍼레이터 전용) — private+authed 만.
    ("data/candidates_diff.json", "_operator/candidates_diff.json", "application/json"),
    # 거시 사실 번들(오퍼레이터 전용) — 전망·추천 없이 출처와 기준일만 제공.
    ("data/macro_synthesis.json", "_operator/macro_synthesis.json", "application/json"),
    ("data/verification_report.json", "_operator/verification_report.json", "application/json"),
    # 중용 목표비중 — 태생부터 봉인(gitignore, 공개 발행 금지). private bucket + authed 만.
    ("data/moderation_portfolio.json", "_operator/moderation_portfolio.json", "application/json"),
    # 2026-08-21 멀티배거 워치(오퍼레이터 전용) — 종목 신호라 공개 발행 금지(유사투자자문 회피).
    #   🚨 생산물이 "로깅 전용 — 결정 0" 을 자기신고하므로 UI 도 관측으로만 표시한다.
    ("data/multibagger_watch.json", "_operator/multibagger_watch.json", "application/json"),
    # 2026-08-22 멀티배거 선별 리스트(PM 지시) — 승격→채점 결과를 일반 후보와 분리.
    #   🚨 이 결정의 성적을 나중에 분리 집계하려면 리스트가 남아야 한다.
    ("data/multibagger_picks.json", "_operator/multibagger_picks.json", "application/json"),
    # 2026-08-07 드리프트 점검 — 목표비중 파생물이라 동일 봉인 등급.
    #   🚨 gitignore 라 git add 로는 전달 불가 — 이 목록이 유일한 전달 경로다(RULE 4 등가).
    ("data/rebalance_review.json", "_operator/rebalance_review.json", "application/json"),
]


def main() -> int:
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not supabase_url or not key:
        print("ERROR: SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 미설정 — 업로드 불가", file=sys.stderr)
        return 2

    # --only <substr>: 특정 파일만 업로드 (전용 워크플로가 타 오퍼레이터 파일을 stale 로 덮는 사고 방지).
    only = None
    if "--only" in sys.argv:
        i = sys.argv.index("--only")
        if i + 1 < len(sys.argv):
            only = sys.argv[i + 1]

    uploads = [u for u in UPLOADS if (only is None or only in u[0] or only in u[1])]
    ok = 0
    for src, dest, ctype in uploads:
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

    print(f"operator upload: {ok}/{len(uploads)}")
    # 부분 실패도 발행 파이프라인 중단 X (fallback = 공개 blob) — 단 stderr 로 명시.
    return 0


if __name__ == "__main__":
    sys.exit(main())
