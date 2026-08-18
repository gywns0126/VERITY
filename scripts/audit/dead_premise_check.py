#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""폐기된 전제가 새 문서·코드에 다시 인용되는 것을 막는다 (2026-08-17 신설).

## 왜

kickoff 에 **죽은 전제 (인용 금지)** 섹션이 있고 그 첫 줄이 "N≥252 게이트(2027-05) 폐기" 인데,
🚨 나는 같은 날 그 전제를 **사전등록 문서 2건에 써넣었다** ("N≥252 이후 재검토").
PM 지적으로 잡혔다 — 자동 검사가 없었기 때문이다.

기존 `knowledge_surface_check` 는 kickoff 에 **섹션이 존재하는지**만 본다. 목록은 있는데
**인용 여부를 강제하지 않는다.** 그래서 목록이 장식이 됐다.

🚨 잔존 실측(2026-08-17): 코드 **9파일 15건**이 아직 `N≥252` 를 인용 중이다. 다음 세션이
그중 아무거나 읽으면 죽은 전제를 살아있는 것으로 쓴다 — 내가 오늘 그랬듯이.
RULE 12 가 경고하는 형태다: "기억·습관·체크리스트로는 안 막힌다."

## 방식

kickoff 의 죽은 전제 목록에서 **금지 토큰을 기계로 추출**하고, 지정 경로에서 그 토큰이
"살아있는 조건"처럼 쓰인 곳을 찾는다. 폐기를 **설명하는** 문장(폐기·죽은 전제·인용 금지·
superseded 가 같은 줄에 있음)은 통과시킨다 — 그건 올바른 언급이다.

기본은 **신규분만** 검사한다(`--since`). 기존 15건을 전부 고치는 것은 별건이고,
그걸 이유로 이 가드를 미루면 또 3일 만에 퇴화한다.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KICKOFF = os.path.expanduser(
    "~/.claude/projects/-Users-macbookpro-Desktop--------/memory/project_next_session_kickoff.md")

# 같은 줄에 이 중 하나가 있으면 "폐기를 설명하는 문장" 이므로 통과
_OK_CONTEXT = ("폐기", "죽은 전제", "인용 금지", "superseded", "SUPERSEDED",
               "틀림", "틀렸", "대체", "무효")


def dead_tokens() -> list[str]:
    """kickoff '죽은 전제' 섹션에서 금지 토큰 추출.

    목록 항목의 **굵게 표시된 첫 구절**을 토큰으로 본다 — 그게 그 전제의 이름이다.
    """
    try:
        lines = open(KICKOFF, encoding="utf-8").read().split("\n")
    except OSError:
        return []
    out, inside = [], False
    for ln in lines:
        if ln.startswith("## ") and "죽은 전제" in ln:
            inside = True
            continue
        if inside and ln.startswith("## "):
            break
        if not inside or not ln.strip().startswith("-"):
            continue
        for m in re.finditer(r"\*\*(.+?)\*\*", ln):
            t = m.group(1).strip()
            # "N≥252 게이트(2027-05) 폐기" → 핵심 토큰 "N≥252"
            core = re.split(r"[ (（—·]", t)[0].strip()
            # 🚨 일반어를 금지어로 뽑으면 오탐이 쏟아지고(첫 시행 72건: "구조적으로"·"arXiv"),
            #   오탐이 많은 가드는 무시당한다. 그래서 **식별자 형태만** 받는다 —
            #   숫자·비교기호·언더스코어를 포함한 토큰(N≥252, GATE_X, 2027-05 …).
            #   자연어 구절로 된 죽은 전제는 기계로 못 잡으므로 사람이 문장으로 남긴다.
            if not re.search(r"[0-9≥≤<>_]", core):
                continue
            core = core.strip('"“”\'')
            if len(core) >= 3 and core not in out:
                out.append(core)
    return out


def scan(paths: list[str], tokens: list[str]) -> list[tuple]:
    hits = []
    for p in paths:
        ap = os.path.join(ROOT, p) if not os.path.isabs(p) else p
        if not os.path.isfile(ap):
            continue
        try:
            for i, ln in enumerate(open(ap, encoding="utf-8"), 1):
                for t in tokens:
                    if t in ln and not any(k in ln for k in _OK_CONTEXT):
                        hits.append((p, i, t, ln.strip()[:100]))
        except (OSError, UnicodeDecodeError):
            continue
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None,
                    help="이 git ref 이후 변경된 파일만 검사 (신규분 게이트)")
    ap.add_argument("--all", action="store_true", help="추적 파일 전수 (잔존 집계용)")
    a = ap.parse_args()

    tokens = dead_tokens()
    if not tokens:
        print("죽은 전제 토큰 0 — kickoff 섹션 파싱 실패 의심", file=sys.stderr)
        return 0                      # fail-open: 가드 자체 오류가 작업을 막지 않는다
    print(f"금지 토큰 {len(tokens)}: {tokens}")

    if a.all:
        files = subprocess.run(["git", "-C", ROOT, "ls-files", "docs", "api", "scripts"],
                               capture_output=True, text=True).stdout.split()
    else:
        base = a.since or "HEAD~1"
        files = subprocess.run(["git", "-C", ROOT, "diff", "--name-only", base],
                               capture_output=True, text=True).stdout.split()
    files = [f for f in files if f.endswith((".md", ".py"))]
    hits = scan(files, tokens)
    print(f"검사 대상 {len(files)}파일 · 위반 {len(hits)}건")
    for p, i, t, ln in hits[:20]:
        print(f"  🚨 {p}:{i}  [{t}]  {ln}")
    if hits:
        print("\n폐기된 전제를 살아있는 조건처럼 인용했다. 폐기 사실을 명시하거나 문장을 지울 것.")
        print("(폐기를 **설명하는** 문장은 통과한다 — 같은 줄에 '폐기·죽은 전제·인용 금지' 포함)")
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
