#!/usr/bin/env python3
"""재구축 불가 관측 trail 오프사이트 백업 (전용 GitHub private repo: VERITY-trail-backup).

대상 = 로컬 레이크에만 존재하고 재구축 불가한 시계열:
  - smallcap_corner_prediction_trail.jsonl (성장 파일, ~8MB/run, repo 밖 비커밋)
  - kr_flow_observations.parquet (네이버 직접 로깅, 과거 backfill 불가)

설계 (무료 조건 영구 충족, 2026-06-26 검증):
  GitHub 일반 git = 50MiB 경고 / 100MiB 하드 차단. 성장 파일 단일 커밋 = ~10 run 후 차단.
  → prediction_trail 을 created_at 의 ISO-주 단위 date-shard 로 분할. 각 shard 는 몇 run 분(<8MB),
    지난 주 shard = immutable (원본 append-only + 결정적 순서 → byte 동일 → git 재저장/재push 0),
    현재 주 shard 만 변동. 100MiB 한도 영구 회피 + LFS 불필요 + 무료 영구.
  parquet = 0.12MB 라 통째 미러.

멱등: 매 실행이 전체 trail 을 주별 재분할 → 지난 주는 변화 없음(commit skip). 안전 재실행 가능.
"""
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

LAKE = os.path.expanduser("~/VERITY_data_lake")
TRAIL = os.path.join(LAKE, "smallcap_corner_prediction_trail.jsonl")
PARQUET = os.path.join(LAKE, "kr_flow_observations.parquet")

REPO_URL = "https://github.com/gywns0126/VERITY-trail-backup.git"
WORK = os.path.expanduser("~/VERITY_trail_backup")

WARN_MIB = 50      # GitHub 경고선
ABORT_MIB = 95     # 100MiB 하드 차단 직전 — push 거부 방지

def _log(m): print(f"[offsite-trail] {m}", flush=True)

def _git(*args) -> int:
    return subprocess.call(["git", "-C", WORK, *args])

def _git_out(*args) -> str:
    return subprocess.run(["git", "-C", WORK, *args], capture_output=True, text=True).stdout.strip()


def _ensure_clone() -> None:
    if os.path.isdir(os.path.join(WORK, ".git")):
        if _git("pull", "--ff-only", "-q") != 0:
            _log("pull 실패 — 계속 (신규 repo 빈 상태일 수 있음)")
        return
    _log(f"clone → {WORK}")
    if subprocess.call(["git", "clone", "-q", REPO_URL, WORK]) != 0:
        # 빈 repo 면 clone 이 빈 디렉토리 — init 후 remote 연결
        os.makedirs(WORK, exist_ok=True)
        _git("init", "-q")
        _git("remote", "add", "origin", REPO_URL)


def _iso_week_key(created_at: str) -> str:
    d = str(created_at)[:10]
    try:
        dt = datetime.strptime(d, "%Y-%m-%d")
        y, w, _ = dt.isocalendar()
        return f"{y}-W{w:02d}"
    except ValueError:
        return "_unknown"


def _shard_trail() -> int:
    """trail 을 ISO-주 shard 로 재분할 write (결정적 순서 = 원본 append 순서). 변경 shard 수 반환."""
    if not os.path.exists(TRAIL):
        _log(f"trail 부재 {TRAIL} — skip")
        return 0
    buckets: dict[str, list[str]] = {}
    with open(TRAIL, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            try:
                ca = json.loads(line).get("created_at", "")
            except json.JSONDecodeError:
                ca = ""
            buckets.setdefault(_iso_week_key(ca), []).append(line)

    out_dir = os.path.join(WORK, "trail")
    os.makedirs(out_dir, exist_ok=True)
    for key, lines in sorted(buckets.items()):
        dest = os.path.join(out_dir, f"prediction_trail_{key}.jsonl")
        content = "\n".join(lines) + "\n"
        # 기존과 동일하면 write 생략 (mtime 안정 → git 무변화)
        if os.path.exists(dest):
            with open(dest, encoding="utf-8") as ex:
                if ex.read() == content:
                    continue
        with open(dest, "w", encoding="utf-8") as w:
            w.write(content)
    return len(buckets)


def _mirror_parquet() -> None:
    if not os.path.exists(PARQUET):
        _log(f"parquet 부재 {PARQUET} — skip")
        return
    fdir = os.path.join(WORK, "flow")
    os.makedirs(fdir, exist_ok=True)
    shutil.copy2(PARQUET, os.path.join(fdir, "kr_flow_observations.parquet"))


def _write_readme(shard_n: int) -> None:
    readme = os.path.join(WORK, "README.md")
    body = (
        "# VERITY-trail-backup\n\n"
        "재구축 불가 관측 trail 오프사이트 백업 (private). 디스크 고장 보험.\n\n"
        "- `trail/prediction_trail_<ISO주>.jsonl` — smallcap 코너 예측 trail, created_at ISO-주 shard.\n"
        "  복원 = ISO-주 오름차순으로 모든 shard concat.\n"
        "- `flow/kr_flow_observations.parquet` — KR flow 관측 (최신 통째 미러).\n\n"
        f"shard 수: {shard_n}. 갱신 = 로컬 weekly 잡 (`backup_irreplaceable.sh` 동승).\n"
        "무료 조건: 일반 git (LFS 미사용). shard <50MiB 유지로 100MiB 차단 영구 회피.\n"
    )
    with open(readme, "w", encoding="utf-8") as w:
        w.write(body)


def _size_guard() -> bool:
    """repo 내 어떤 파일이든 ABORT_MIB 초과 시 False (push 거부 방지). WARN 시 경고만."""
    ok = True
    for root, _dirs, files in os.walk(WORK):
        if ".git" in root:
            continue
        for fn in files:
            mib = os.path.getsize(os.path.join(root, fn)) / 1024 / 1024
            if mib >= ABORT_MIB:
                _log(f"🚨 ABORT: {fn} {mib:.1f}MiB ≥ {ABORT_MIB} — 100MiB 차단 임박. 일-단위 shard 전환 필요.")
                ok = False
            elif mib >= WARN_MIB:
                _log(f"⚠️  {fn} {mib:.1f}MiB ≥ {WARN_MIB} 경고선 — 곧 shard 세분 검토.")
    return ok


def main() -> int:
    push = "--no-push" not in sys.argv
    _ensure_clone()
    shard_n = _shard_trail()
    _mirror_parquet()
    _write_readme(shard_n)

    if not _size_guard():
        _log("size guard 실패 — commit/push 중단")
        return 1

    _git("add", "-A")
    if _git("diff", "--cached", "--quiet") == 0:
        _log("변경 없음 — commit skip")
        return 0
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    _git("commit", "-q", "-m", f"backup(trail): 오프사이트 동기화 {stamp} (shard={shard_n})")
    if push:
        if _git("push", "-q", "-u", "origin", "HEAD:main") != 0:
            _log("push 실패")
            return 1
        _log(f"오프사이트 push 완료 (shard={shard_n})")
    else:
        _log("commit 완료 (--no-push)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
