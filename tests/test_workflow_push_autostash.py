# -*- coding: utf-8 -*-
"""워크플로 push 블록의 `git pull --rebase` 는 전부 `--autostash` 를 달아야 한다.

왜 (실측 사고 2건, 같은 클래스):
  · 2026-08-13/14 `reports_v2_cron` — 좁은 add 로 남은 unstaged 파일 때문에
    `git pull --rebase` 가 "You have unstaged changes" 로 거부, 재시도 8회 전부 같은 이유로 실패.
  · 2026-08-16 `dart_quarterly_backfill` — 백필이 **100% 완주**(64,386/64,386, 89건 append)하고
    커밋까지 됐는데 같은 이유로 push 5회 실패 → 그날 수집분이 통째로 유실.

🚨 핵심: 이건 경합이 아니라 **작업트리 오염**이다. 경합은 재시도로 풀리지만 오염은 결정론적이라
   몇 번을 재시도해도 같은 자리에서 같은 이유로 실패한다. 재시도 횟수를 늘리는 방향의 수정은
   전부 헛되고, 로그에는 "N회 push 실패" 만 남아 경합처럼 보인다.

8/13 사고 후 수정은 `reports_v2_cron` **한 파일에만** 적용됐다 (broad add + 사전 stash).
2026-08-17 전수 집계에서 같은 결함이 나머지 **21개 파일**에 남아 있었고, 그중 2개는
RULE 1 영역(`kis_token_refresh` 락 전파 · `daily_realtime` 백업 발급원)이었다.
= 인스턴스만 고치고 클래스를 안 고친 형태. 이 테스트가 클래스를 고정한다.

🚨 분모 함정 (RULE 13 실측): 최초 점검을 **파일 단위**(`grep -l`)로 해서 "autostash 있음" 으로
   분류된 파일 안의 **두 번째 push 블록 4건**을 놓쳤다. 그래서 이 테스트는 파일이 아니라
   **발생(occurrence) 단위**로 센다.
"""
from __future__ import annotations

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF_DIR = os.path.join(ROOT, ".github", "workflows")

PULL_RE = re.compile(r"git\s+pull\s+--rebase")
OK_RE = re.compile(r"git\s+pull\s+--rebase\s+--autostash")


def _occurrences():
    """(파일, 줄번호, 줄) 전수. 주석 줄은 서술이므로 제외."""
    out = []
    for fn in sorted(os.listdir(WF_DIR)):
        if not fn.endswith((".yml", ".yaml")):
            continue
        with open(os.path.join(WF_DIR, fn), encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                if line.lstrip().startswith("#"):
                    continue
                if PULL_RE.search(line):
                    out.append((fn, i, line.rstrip()))
    return out


def test_every_pull_rebase_has_autostash():
    occ = _occurrences()
    assert occ, "워크플로에서 git pull --rebase 를 하나도 못 찾음 — 탐지 정규식 자체를 의심할 것"
    bad = [(f, i, l.strip()) for f, i, l in occ if not OK_RE.search(l)]
    assert not bad, (
        f"--autostash 누락 {len(bad)}/{len(occ)}건 — 작업트리가 더러우면 결정론적으로 실패하고 "
        "재시도로는 절대 안 풀린다 (2026-08-16 dart_quarterly_backfill 완주분 유실):\n  "
        + "\n  ".join(f"{f}:{i}  {l}" for f, i, l in bad))


def test_denominator_is_reported():
    """분모 자기신고 — 발생 수가 줄면 탐지 범위가 조용히 좁아진 것이다 (RULE 13)."""
    occ = _occurrences()
    files = {f for f, _, _ in occ}
    # 2026-08-17 기준 실측: 발생 68 · 파일 64. 파일 단위로 세면 4건을 놓친다.
    assert len(occ) >= len(files), "발생 수 < 파일 수 = 집계 오류"
    assert len(occ) >= 60, (
        f"push 블록 발생 {len(occ)}건 — 8/17 실측 68건 대비 급감. 워크플로가 줄었거나 "
        "탐지 정규식이 놓치고 있다. 둘 중 무엇인지 확인 전에는 통과시키지 않는다.")
