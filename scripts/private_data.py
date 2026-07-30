#!/usr/bin/env python3
"""민감 데이터 private repo 동기화 — public repo 에서 운용 데이터를 뺀다.

배경 (2026-07-30 발견):
  메인 repo 가 PUBLIC 인데 `data/` 의 운용 산출물이 전부 git 추적 중이었다. 실측:
    raw.githubusercontent.com/gywns0126/VERITY/main/data/us_analyst_consensus.json → 200
  즉 **발행 영구 금지로 확정한 컨센서스(PM 7/10)와 VAMS 운용 실적이 이미 공개**였다.
  blob allowlist 에서만 빼고 repo 는 그대로였던 것.

  repo 를 public 으로 두는 결정 자체는 유효하다 — GitHub Actions 무료 무제한 CI 때문이고
  private 전환 시 월 ~$286 이다([[project_hybrid_repo_privacy_2026_05_31]]).
  **코드는 공개해도 되지만 운용 데이터까지 공개할 이유는 없다.** 그래서 데이터만 분리한다.

방식:
  · public repo 는 해당 파일을 .gitignore 로 추적 해제 (디스크에는 그대로 둔다 — 상대경로 무결)
  · 생산 워크플로: 산출 직후 `push` 로 private repo(VERITY-private)에 올린다
  · 소비 워크플로/서버: 잡 시작 시 `pull` 로 내려받아 디스크에 복원한다
  · 토큰 = PRIVATE_DATA_PAT (VERITY-private contents:write). 없으면 **조용히 skip** —
    토큰 미설정이 파이프라인을 죽이면 안 된다(fail-open). 대신 종료 코드로 구분 가능.

사용:
    python scripts/private_data.py push data/us_analyst_consensus.json
    python scripts/private_data.py pull data/us_analyst_consensus.json
    python scripts/private_data.py pull --all          # MANIFEST 전량

🚨 이 스크립트는 **파일 내용을 로그에 찍지 않는다**. 민감 데이터를 CI 로그로 흘리면 분리 의미가 없다.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from typing import List, Optional

REPO = os.environ.get("PRIVATE_DATA_REPO", "gywns0126/VERITY-private")
BRANCH = os.environ.get("PRIVATE_DATA_BRANCH", "main")
TOKEN = (
    os.environ.get("PRIVATE_DATA_PAT")
    or os.environ.get("VERITY_PRIVATE_PAT")
    or ""
)
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://api.github.com"

# 분리 대상 — 결합이 얕은 순. 하나씩 검증하며 넓힌다(한 번에 옮기면 파이프라인이 통째로 흔들린다).
MANIFEST: List[str] = [
    "data/us_analyst_consensus.json",   # 코드 2곳·워크플로 1개 — 발행 영구 금지 자산
    "data/factor_ic_history.json",      # 코드 5곳·워크플로 0개
    "data/recommendations.json",        # 코드 15곳·워크플로 2개
    "data/portfolio.json",              # 코드 36곳·워크플로 5개 — 가장 깊다, 마지막
]


def _req(method: str, path: str, body: Optional[dict] = None):
    url = API + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Authorization", "Bearer " + TOKEN)
    r.add_header("Accept", "application/vnd.github+json")
    r.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data is not None:
        r.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read() or b"{}")


def _sha(rel: str) -> Optional[str]:
    """private repo 상 기존 파일 sha (없으면 None)."""
    try:
        d = _req("GET", f"/repos/{REPO}/contents/{rel}?ref={BRANCH}")
        return d.get("sha")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def push(rel: str) -> bool:
    local = os.path.join(_ROOT, rel)
    if not os.path.exists(local):
        print(f"[private_data] skip(로컬 없음) {rel}", file=sys.stderr)
        return False
    with open(local, "rb") as f:
        raw = f.read()
    body = {
        "message": f"data: {os.path.basename(rel)} 동기화",
        "content": base64.b64encode(raw).decode(),
        "branch": BRANCH,
    }
    sha = _sha(rel)
    if sha:
        body["sha"] = sha
    _req("PUT", f"/repos/{REPO}/contents/{rel}", body)
    print(f"[private_data] push OK {rel} ({len(raw):,} bytes)", file=sys.stderr)
    return True


def pull(rel: str) -> bool:
    try:
        d = _req("GET", f"/repos/{REPO}/contents/{rel}?ref={BRANCH}")
    except urllib.error.HTTPError as e:
        print(f"[private_data] pull 실패 {rel} — HTTP {e.code}", file=sys.stderr)
        return False
    content = d.get("content") or ""
    if not content and d.get("download_url"):
        # 1MB 초과 파일은 content 가 비어 온다 → download_url 사용
        r = urllib.request.Request(d["download_url"])
        r.add_header("Authorization", "Bearer " + TOKEN)
        with urllib.request.urlopen(r, timeout=60) as resp:
            raw = resp.read()
    else:
        raw = base64.b64decode(content)
    local = os.path.join(_ROOT, rel)
    os.makedirs(os.path.dirname(local), exist_ok=True)
    tmp = local + ".tmp"
    with open(tmp, "wb") as f:
        f.write(raw)
    os.replace(tmp, local)
    print(f"[private_data] pull OK {rel} ({len(raw):,} bytes)", file=sys.stderr)
    return True


def main(argv: List[str]) -> int:
    if len(argv) < 2 or argv[1] not in ("push", "pull"):
        print(__doc__, file=sys.stderr)
        return 2
    mode = argv[1]
    targets = argv[2:]
    if not targets or targets == ["--all"]:
        targets = list(MANIFEST)

    if not TOKEN:
        # fail-open — 토큰 없는 환경(로컬 개발·포크 CI)에서 파이프라인을 죽이지 않는다.
        print("[private_data] PRIVATE_DATA_PAT 없음 — skip", file=sys.stderr)
        return 0

    ok = 0
    for rel in targets:
        try:
            if (push(rel) if mode == "push" else pull(rel)):
                ok += 1
        except Exception as e:  # noqa: BLE001 — 개별 실패 격리
            print(f"[private_data] {mode} 예외 {rel}: {type(e).__name__}", file=sys.stderr)
    print(f"[private_data] {mode} {ok}/{len(targets)} 완료", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
