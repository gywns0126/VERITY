# -*- coding: utf-8 -*-
"""Perplexity 호출부 caller 라벨 전수 강제 (2026-08-25).

사고 = 8월 원장 419호출 중 **416이 기본 라벨 'clients_pplx' 하나로 뭉쳐** 소비자 8곳 중
누가 썼는지 원장으로 구분 불가했다. PM 질문("289회?")에 답하려고 **시간대 클러스터로
역추정**해야 했다 — 원장이 있는데 원장이 답을 못 하는 상태.

부수 = 콘솔 289 는 main run 내부 카운트만이라 배치 워크플로 ~130회가 빠진 **부분집계**였다
(표시값≠실체 계열 6번째).

이 테스트는 ① 클라이언트가 caller 를 원장에 전달하는지 ② call_perplexity 호출부 전수가
caller 를 지정했는지(미지정 신규 유입 차단)를 강제한다.
"""
import ast
import glob
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _call_sites():
    """api/ 전체에서 call_perplexity( 호출 노드를 AST 로 전수 수집 (grep 의 리터럴 함정 회피)."""
    out = []
    for path in glob.glob(os.path.join(_ROOT, "api", "**", "*.py"), recursive=True):
        if path.endswith("perplexity_client.py"):
            continue
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
                if name == "call_perplexity":
                    kw = {k.arg for k in node.keywords}
                    out.append((os.path.relpath(path, _ROOT), node.lineno, "caller" in kw))
    return out


def test_client_passes_caller_to_ledger():
    src = open(os.path.join(_ROOT, "api", "clients", "perplexity_client.py"), encoding="utf-8").read()
    assert 'caller: str = "clients_pplx"' in src, "caller 파라미터가 사라졌다"
    assert 'log_perplexity(data, str(payload.get("model") or ""), caller)' in src, (
        "원장에 caller 가 전달되지 않는다 — 라벨이 다시 뭉친다")


def test_every_call_site_declares_caller():
    sites = _call_sites()
    assert len(sites) >= 11, f"호출부가 {len(sites)}곳뿐 — AST 수집이 깨졌는지 확인"
    missing = [(p, ln) for p, ln, has in sites if not has]
    assert not missing, (
        f"caller 미지정 호출부 {len(missing)}건: {missing}\n"
        "→ call_perplexity(..., caller=\"<모듈 이름>\") 로 지정할 것. "
        "기본 라벨로 두면 원장이 또 뭉친다.")


def test_labels_are_distinct_enough():
    """전 호출부가 같은 라벨 하나면 지정의 의미가 없다."""
    labels = set()
    for path in glob.glob(os.path.join(_ROOT, "api", "**", "*.py"), recursive=True):
        if path.endswith("perplexity_client.py"):
            continue
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
                if name == "call_perplexity":
                    for k in node.keywords:
                        if k.arg == "caller" and isinstance(k.value, ast.Constant):
                            labels.add(k.value.value)
    assert len(labels) >= 5, f"라벨 종류 {len(labels)} — 다시 뭉치고 있다: {labels}"
