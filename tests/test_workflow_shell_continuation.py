# -*- coding: utf-8 -*-
"""워크플로 셸 이어쓰기 파손 가드 (2026-08-16).

사고: 532f3460b(8/06) 가 `git add data/metadata/llm_cost.jsonl` 을 13개 워크플로에
일괄 삽입했는데, `us_smart_money_13f.yml` 에서는 그 자리가 `\\` 이어쓰기 한가운데였다.

    git add A.json B.json \\
    git add data/metadata/llm_cost.jsonl 2>/dev/null || true   ← 삽입된 줄
      data/cusip_ticker_map.json data/13f_quarter_cache.json ...

셸은 1+2행을 한 줄로 붙여 `git add A B git add C` 로 읽어 pathspec 불일치로 실패하고
(`|| true` 가 삼킨다), 3행은 **독립 명령**이 되어 JSON 파일을 실행하려다
exit 126(Permission denied) 으로 step 을 죽인다.

왜 아무도 못 잡았나 — 이 형태가 **문법상 정상**이기 때문이다. `bash -n` 을 78개
워크플로 전 run 블록에 돌려도 0건이다(파일 경로를 명령으로 부르는 건 유효한 문장).
git add 다중경로 훅 가드도 통과한다. 즉 문법·훅 어느 쪽으로도 탐지 경로가 없었고,
8/06 파손 → 8/15 첫 실행 실패까지 무신호였다. 산출물은 7/30~8/01 에 동결됐다.

계약: 워크플로 run 블록에서 `\\` 로 끝나는 줄 다음에 새 명령이 오면 안 된다.
"""
import glob
import os
import re

import yaml

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_WF = os.path.join(_ROOT, ".github", "workflows")

# 이어쓰기 다음 줄이 이 중 하나로 시작하면 = 앞줄 인자가 아니라 새 명령이다.
_COMMAND_START = re.compile(
    r"^\s*(git|python|python3|pip|echo|cd|curl|gh|jq|npm|node|bash|sh|mkdir|rm|cp|mv|ls|cat)\b"
)


def _run_blocks():
    """(파일명, step 이름, run 문자열) 전량."""
    for path in sorted(glob.glob(os.path.join(_WF, "*.yml"))):
        with open(path, encoding="utf-8") as f:
            doc = yaml.safe_load(f)
        if not isinstance(doc, dict):
            continue
        for job_name, job in (doc.get("jobs") or {}).items():
            for i, step in enumerate(job.get("steps") or []):
                run = step.get("run")
                if isinstance(run, str):
                    label = step.get("name") or f"{job_name}[{i}]"
                    yield os.path.basename(path), label, run


def test_no_command_after_line_continuation():
    """`\\` 다음 줄이 새 명령이면 앞줄 add/명령이 통째로 오작동한다."""
    broken = []
    for fname, label, run in _run_blocks():
        lines = run.splitlines()
        for n in range(len(lines) - 1):
            cur, nxt = lines[n], lines[n + 1]
            if not cur.rstrip().endswith("\\"):
                continue
            # 주석 줄은 셸이 이어쓰기 인자로 먹으므로 이것도 파손이다.
            if _COMMAND_START.match(nxt) or nxt.lstrip().startswith("#"):
                broken.append(f"{fname} · {label} · {n + 1}행: {cur.strip()[:60]!r} → {nxt.strip()[:60]!r}")
    assert not broken, "이어쓰기 파손 — `\\` 다음 줄이 새 명령/주석이다:\n  " + "\n  ".join(broken)


def test_no_bare_data_path_as_command():
    """data/ 로 시작하는 줄이 **명령 자리**에 있으면 파일을 실행하려는 것 (exit 126).

    앞줄이 `\\` 로 끝나면 그 줄은 인자 이어쓰기라 정상이다 — 여러 워크플로가
    긴 경로 목록을 그렇게 쓴다. 판정은 "앞줄이 이어쓰기가 아닌데 data/ 로 시작"뿐이다.
    """
    offenders = []
    for fname, label, run in _run_blocks():
        prev = ""
        for n, line in enumerate(run.splitlines(), 1):
            s = line.strip()
            if s.startswith("data/") and not prev.rstrip().endswith("\\"):
                offenders.append(f"{fname} · {label} · {n}행: {s[:70]!r}")
            prev = line
    assert not offenders, "파일 경로가 명령 자리에 있다 (exit 126 유발):\n  " + "\n  ".join(offenders)
