"""내부 컨텍스트 — 서버리스(로컬 data 부재) 상황에서 원격 경유가 실제로 동작하는지.

2026-07-30: Vercel 함수에는 data/ 가 없다(vercel-api/data 는 2개 파일뿐). 그래서 내부 블록이
비어 챗이 공개 컨텍스트로만 답했다. 원격 폴백을 넣었으니 그 경로를 회귀 테스트로 고정한다.
"""
from __future__ import annotations

import api.chat_hybrid.search.internal_context as ic


def test_local_path_resolves_to_repo_data():
    """SSOT 위치에서는 repo 의 data/ 를 찾아야 한다(고정 깊이 dirname 금지 회귀)."""
    d = ic._find_data_dir()
    assert d is not None and d.endswith("data")


def test_remote_base_defaults_to_bridge():
    """env 미설정이면 공개 브리지가 기본값 — Vercel 에서 내부 블록이 비지 않게."""
    assert ic._REMOTE_BASE.startswith("https://")
    assert ic._REMOTE_BASE.endswith("/data")


def test_private_first_when_no_token():
    """PAT 없으면 private 경로는 시도조차 하지 않는다(빈 토큰으로 GitHub 두드리지 않기)."""
    if not ic._PRIV_PAT:
        assert ic._load_private("us_analyst_consensus.json") is None


def test_build_is_fail_open_without_data(monkeypatch):
    """로컬 data 도 없고 원격도 막히면 예외 없이 빈 결과 — 챗을 죽이지 않는다."""
    monkeypatch.setattr(ic, "_DATA", None)
    monkeypatch.setattr(ic, "_REMOTE_BASE", "")
    monkeypatch.setattr(ic, "_PRIV_PAT", "")
    r = ic.build_internal_context(["TSLA"])
    assert r["ok"] is False and r["text"] == "" and r["chars"] == 0


def test_build_labels_hypothesis_when_data_present():
    """RULE 7 — 자기 산식이 실릴 때 '가설' 표기가 함께 가야 한다."""
    r = ic.build_internal_context([])
    if r["ok"]:
        assert "가설" in r["text"]
