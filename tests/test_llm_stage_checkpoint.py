"""LLM 단계 진입 전 체크포인트 저장 회귀 테스트.

🚨 고정하려는 사고 (2026-08-15 실측):

  `full` run 이 런타임 예산을 소진하고 워치독 SIGTERM 으로 죽었는데, 핸들러 로그가 매번
  `_latest_portfolio_ref None — save 스킵 (early SIGTERM)` 이었다(실패 run 31781495244 ·
  31842720344 두 건 모두). 핸들러는 "partial portfolio 저장 시도" 를 광고하는데 실제로는
  한 번도 저장하지 않았다.

  근인 = `main()` 안의 `save_portfolio()` 호출 3곳이 전부 비켜 있었다.
    · `if should_abort:` 조기중단 경로
    · `if mode in ("realtime","realtime_us")` realtime 전용
    · 나머지 하나는 STEP 6(Gemini)보다 **뒤**
  즉 full 모드는 LLM 단계에 닿을 때까지 디스크에 아무것도 안 썼고, 거기서 잘리면
  유니버스 스캔(약 33분) + 병합(약 51분) + 채점이 통째로 사라졌다. 꼬리만 잃는 게 아니었다.

계약 둘:
  ① `main()` 안에서 체크포인트 저장이 STEP 6(LLM) 마커보다 **앞선다**
  ② `save_portfolio()` 는 원본 저장 성패와 무관하게 모듈 전역 ref 를 세팅한다
     — 이게 SIGTERM 핸들러의 partial 저장이 작동하기 위한 유일한 조건이다
"""
from __future__ import annotations

import ast
import os

import pytest

_MAIN_PY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api", "main.py"
)


def _llm_stage_lineno(tree, src_lines) -> int:
    """STEP 6(LLM) 진입 라인. 주석 마커로 잡되 없으면 실패시켜 기준점 소실을 드러낸다."""
    for i, l in enumerate(src_lines, 1):
        if "STEP 6: full 전용" in l:
            return i
    raise AssertionError("STEP 6(LLM) 마커 소실 — 이 테스트의 기준점이 사라졌다")


def _unconditional_save_linenos(fn: ast.FunctionDef) -> list:
    """`main()` 안에서 **조건 분기 밖**의 save_portfolio(portfolio) 호출 라인들.

    try/except 로 감싼 것은 허용한다(저장 실패가 run 전체를 죽이면 안 되므로 오히려 정상).
    if/for/while 안에 있으면 모드·상태에 따라 안 탈 수 있으므로 제외한다 — 그게 이번 사고다.
    """
    found = []

    def walk(nodes):
        for n in nodes:
            if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call):
                f = n.value.func
                if isinstance(f, ast.Name) and f.id == "save_portfolio":
                    found.append(n.lineno)
            elif isinstance(n, ast.Try):
                walk(n.body)  # try 본문은 무조건 실행 경로
            # if / for / while / with(조건부 컨텍스트) 는 파고들지 않는다
    walk(fn.body)
    return found


def _main_fn():
    src = open(_MAIN_PY, encoding="utf-8").read()
    tree = ast.parse(src)
    fn = next(
        (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main"), None
    )
    assert fn is not None, "main() 을 못 찾았다"
    return fn, tree, src.splitlines()


def test_checkpoint_save_precedes_llm_stage():
    """① 조건 밖 save_portfolio 가 STEP 6(LLM)보다 앞서야 한다."""
    fn, tree, lines = _main_fn()
    llm_at = _llm_stage_lineno(tree, lines)
    saves = _unconditional_save_linenos(fn)

    before = [ln for ln in saves if ln < llm_at]
    assert before, (
        f"LLM 단계(라인 {llm_at}) 이전에 조건 밖 save_portfolio 가 없다 "
        f"(발견된 조건 밖 저장: {saves}). 예산 소진으로 잘리면 그때까지의 분석분이 통째로 "
        "사라지고, SIGTERM 핸들러의 partial 저장도 ref 가 None 이라 스킵된다."
    )


def test_checkpoint_is_not_hidden_in_a_branch():
    """조건 블록 안에만 있으면 안 된다 — 그게 이번 사고의 형태다.

    사고 당시 main() 의 save_portfolio 는 `if should_abort:` 와
    `if mode in ("realtime","realtime_us")` 안에만 있었고, 조건 밖 첫 저장은 STEP 6 뒤였다.
    """
    fn, tree, lines = _main_fn()
    llm_at = _llm_stage_lineno(tree, lines)
    assert any(ln < llm_at for ln in _unconditional_save_linenos(fn))


def test_save_portfolio_sets_module_ref(monkeypatch):
    """② ref 세팅이 SIGTERM partial 저장의 유일한 조건 — 원본 저장이 실패해도 세팅된다."""
    api_main = pytest.importorskip("api.main")

    monkeypatch.setattr(api_main, "_latest_portfolio_ref", None, raising=False)

    def boom(_p):
        raise OSError("disk full")

    monkeypatch.setattr(api_main, "_orig_save_portfolio", boom, raising=False)

    doc = {"vams": {"total_asset": 1}, "recommendations": []}
    try:
        api_main.save_portfolio(doc)
    except Exception:
        pass  # 원본 저장 실패는 여기서 관심사가 아니다

    assert api_main._latest_portfolio_ref is doc, (
        "원본 저장이 실패하면 ref 도 안 잡히는 구조라면, 디스크가 문제일 때 "
        "SIGTERM partial 저장까지 동시에 죽는다"
    )
