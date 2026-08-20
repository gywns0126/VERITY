"""폐기된 게이트가 사용자 노출 문자열에 다시 새어드는 것을 막는다.

## 왜 (2026-08-18 신설)

`docs/VALIDATION_METHODOLOGY.md` §7-1 (PM 결정 2026-08-15)이 **N=252 IC 게이트(2027-05)를
폐기**했다. 폐기 사유가 그 게이트의 출력 형태 자체였다 —

> *"실제 출력이 언제나 '더 모아라' 였다. 검정력을 따지지 않은 채 표본만 요구하는 것은
> 무책임하다. 기다림은 결론이 아니다."*

그런데 2026-08-18 감사에서 **발행 산출물 56건 전부**가 여전히 그 게이트를 인용하고 있었다:
`"가설 — 자체 산식 N<252 IC 게이트(2027-05) 미검증"`.
`validation_summary._gate_status` 는 한술 더 떠 **폐기된 목표를 향한 진척률(%)** 을
계산해 보여주고 있었다.

🚨 **죽은 전제가 코드에 남아 매 발행마다 복제되는 형태** — RULE 12 가 경고한 그것이다.
문구만 고치면 다음 세션이 되살린다. 그래서 기계로 막는다.

## 범위

**사용자에게 나가는 문자열만** 검사한다 — 주석·docstring 은 이력 설명이라 허용한다
(오히려 "왜 폐기됐나" 를 남겨야 한다). 즉 이 테스트가 잡는 것은
"발행물·오퍼레이터 출력에 죽은 날짜가 실리는 것" 이다.

framer-components 는 RULE 11(3소스 동기화) 대상이라 여기서 자동 수정하지 않는다 —
별도 절차로만 손댄다. 그 사실을 아래 `KNOWN_PENDING` 에 남긴다.
"""
from __future__ import annotations

import ast
import os
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parent.parent

# 폐기된 전제를 가리키는 표현. 날짜가 핵심이다 — "N<252" 는 표본 서술로 쓰일 수 있으나
# "2027" 목표 시점은 폐기된 게이트에서만 나온다.
RETIRED_MARKERS = ("2027-05", "2027 게이트", "검증 후(2027)", "held(2027)", "N≥252", "N<252")

# 검사 대상 = 사용자 노출 산출물을 만드는 경로
SCAN_DIRS = ("api/builders", "api/intelligence", "api/observability", "api/reports")

# RULE 11 대상이라 이 테스트가 건드리지 않는다. 별도 3소스 절차 필요.
KNOWN_PENDING = (
    "framer-components/public-probe/PublicGlassboxTab.tsx",
    "operator-web/",          # 프런트 — 별도 배포 절차
    "vercel-api/",            # RULE 2 — deploy trigger 주의
)


def _string_literals(path: pathlib.Path):
    """AST 로 **문자열 리터럴만** 수집. 주석·docstring 은 제외한다."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            d = ast.get_docstring(node, clean=False)
            if d:
                docstrings.add(d)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in docstrings:
                continue
            yield node.lineno, node.value


def test_no_retired_gate_in_user_facing_strings():
    """🚨 발행·출력 문자열에 폐기된 게이트가 없어야 한다."""
    hits = []
    for d in SCAN_DIRS:
        base = _ROOT / d
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            for lineno, val in _string_literals(path):
                for marker in RETIRED_MARKERS:
                    if marker in val:
                        hits.append(f"{path.relative_to(_ROOT)}:{lineno} — {marker!r} in {val[:70]!r}")
    assert not hits, (
        "폐기된 N=252/2027-05 게이트가 사용자 노출 문자열에 있다 "
        "(docs/VALIDATION_METHODOLOGY.md §7-1 로 폐기됨).\n"
        "주석·docstring 에는 이력으로 남겨도 되지만 출력에는 안 된다.\n  "
        + "\n  ".join(hits))


def test_gate_status_reports_no_progress_percentage():
    """🚨 폐기된 목표를 향한 '진척률' 을 만들지 않는다 — 폐기 사유가 정확히 그것이었다."""
    from api.observability import validation_summary as vs

    for n in (0.0, 10.0, 130.0, 251.0, 400.0):
        out = vs._gate_status(n, None)
        assert "진척" not in out, f"n_eff={n} 에서 진척률이 되살아났다: {out}"
        assert "252" not in out and "2027" not in out, f"폐기 게이트 인용: {out}"


def test_display_verdict_note_is_current():
    from api.intelligence import display_verdict as dv

    assert "2027" not in dv._VALIDATION_NOTE and "252" not in dv._VALIDATION_NOTE
    assert "가설" in dv._VALIDATION_NOTE, "가설 표기 자체는 유지해야 한다 (RULE 7)"


def test_known_pending_surfaces_are_recorded():
    """RULE 11/2 대상이라 미처리인 표면을 **명시적으로** 남긴다.

    조용히 빠뜨리는 것과 알고 남기는 것은 다르다 (RULE 13 — 잔여는 개수+이름으로).
    """
    assert len(KNOWN_PENDING) >= 3
    assert any("framer" in p for p in KNOWN_PENDING)


# ── 2026-08-20 확장: 워크플로 주석 ─────────────────────────────────────────
# 위 테스트는 "주석·docstring 에는 이력으로 남겨도 된다" 를 전제로 문자열만 본다. 맞는 전제다.
# 그런데 2026-08-20 에 그 틈으로 다른 형태가 발견됐다 — `.github/workflows/daily_analysis_full.yml`
# 주석 3곳이 폐기된 게이트를 **이력이 아니라 그 step 이 존재하는 현재 근거로** 인용하고 있었다:
#     "엔진 미사용 신호 forward IC trail 누적(N≥252 2027 검증용)"
#     "N=252 IC 게이트(2027-05) 읽기 준비"
# 이건 사용자 노출은 아니지만 **다음 세션이 읽고 그대로 믿는 자리**다(RULE 12 ③).
# 마커 유무만으로는 이력과 살아있는 인용을 못 가른다 → **부고(訃告) 동반 여부**로 가른다.
WF_DIR = ".github/workflows"
OBITUARY = ("폐기", "종전", "§7-1", "7-1 ", "retired")
OBITUARY_RADIUS = 3   # 같은 줄 ± 3줄 안에 부고가 있으면 이력 인용으로 인정


def test_workflow_comments_cite_retired_gate_only_with_obituary():
    """🚨 워크플로 주석이 폐기 게이트를 인용하려면 폐기 사실을 같이 적어야 한다."""
    hits = []
    base = _ROOT / WF_DIR
    for path in sorted(base.glob("*.yml")) if base.exists() else []:
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if not any(m in line for m in RETIRED_MARKERS):
                continue
            lo, hi = max(0, i - OBITUARY_RADIUS), min(len(lines), i + OBITUARY_RADIUS + 1)
            near = "\n".join(lines[lo:hi])
            if not any(o in near for o in OBITUARY):
                hits.append(f"{path.relative_to(_ROOT)}:{i + 1} — {line.strip()[:90]}")
    assert not hits, (
        "워크플로 주석이 폐기된 N=252/2027-05 게이트를 **살아있는 근거처럼** 인용한다 "
        "(§7-1, PM 2026-08-15 폐기).\n"
        "이력으로 남기려면 같은 자리에 폐기 사실을 함께 적을 것 — 다음 세션이 그대로 믿는다.\n  "
        + "\n  ".join(hits))
