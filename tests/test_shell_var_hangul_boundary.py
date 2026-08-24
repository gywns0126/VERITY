# -*- coding: utf-8 -*-
"""셸 변수 뒤에 한글이 바로 붙으면 bash 가 변수명으로 읽는다 (2026-08-24 신설).

## 사고

`scripts/git/rebase_push.sh:120` 이 `$attempt` + `회` 를 중괄호 없이 이어 붙였다.
bash 는 `회` 까지 식별자로 읽어 없는 변수를 찾았고, `set -u` 아래에서

    rebase_push.sh: line 120: attempt<한글>: unbound variable

로 죽었다. 🚨 **그런데 그 자리가 `$( ... )` 서브셸 안이라 push 자체는 성공했다.**
그래서 매 push 마다 경고만 찍힌 채 **2026-08-22 ~ 08-25, 3일간 살아남았다** —
kickoff 미결 ⓔ 에 "push 는 성공, 가드 자체 결함" 으로 올라와 있던 그 건이다.

## 왜 기계로 막나

한국어 메시지를 쓰는 셸 스크립트에서 이 형태는 **자연스럽게 다시 나온다**
(`$n건` · `$cnt개` · `$sec초`). 사람이 매번 중괄호를 기억할 일이 아니다
(RULE 12 — 기억·습관으로는 3일이면 퇴화한다. 실제로 3일 만에 재발한 게 아니라 3일간 안 잡혔다).

## 규약

- 셸에서 `$VAR` 바로 뒤에 한글을 붙이지 않는다. `${VAR}한글` 로 쓴다.
- 주석(`#`)은 제외한다 — 주석에서 이 패턴을 **설명**할 수 있어야 한다.
"""
from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
# `$var` 직후에 한글이 오는 형태. `${var}한글` 은 중괄호가 경계라 걸리지 않는다.
BAD = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*[가-힣]")
TARGET_DIRS = ("scripts", ".github/workflows")
SUFFIXES = (".sh", ".bash", ".yml", ".yaml")


def _files():
    for d in TARGET_DIRS:
        base = _ROOT / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_file() and p.suffix in SUFFIXES:
                yield p


def test_no_unbraced_var_before_hangul():
    hits = []
    for p in _files():
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue                      # 주석은 이 패턴을 설명할 수 있어야 한다
            m = BAD.search(line)
            if m:
                hits.append(f"{p.relative_to(_ROOT)}:{n}  {m.group(0)}")
    assert not hits, (
        "셸 변수 뒤에 한글이 바로 붙었다 — bash 가 한글까지 변수명으로 읽어 "
        "`set -u` 에서 unbound variable 로 죽는다. `${VAR}한글` 로 고칠 것:\n  "
        + "\n  ".join(hits))


def test_scanner_actually_catches_the_original_defect():
    """🚨 스캐너가 실제로 그 형태를 잡는지 — 게이트 자체를 검증한다.

    ([[feedback_green_check_is_not_safety]] — 검산 스크립트 자체 버그가 실제로 있었다)
    """
    assert BAD.search('echo " · 시도 $attempt회"')          # 사고 원문
    assert BAD.search('echo "$n건 처리"')
    assert not BAD.search('echo " · 시도 ${attempt}회"')     # 고친 형태
    assert not BAD.search('echo "$attempt/5"')               # 한글 아님 = 무해
    assert not BAD.search('echo "${n}건"')
