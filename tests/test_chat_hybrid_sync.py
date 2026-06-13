"""chat_hybrid 이중 사본 동기화 가드.

api/chat_hybrid/ 와 vercel-api/api/chat_hybrid/ 는 동일 모듈의 배포용 사본이다
(Vercel 빌드가 vercel-api/ 내부 파일만 포함하므로 사본 자체는 구조상 필요).
동기화 강제 장치가 없어 한쪽만 수정되면 silent drift — chat grounding guard
(feedback_chat_price_grounding_guard) 회귀로 직결되므로 push 마다 diff 를 검증한다.

2026-06-13 신설. 신설 당일 실제 분기 1건(brain_client.py 주석) 발견·정정 이력.
"""

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CANONICAL = ROOT / "api" / "chat_hybrid"
DEPLOY_COPY = ROOT / "vercel-api" / "api" / "chat_hybrid"

SKIP_PARTS = {"__pycache__", ".pytest_cache"}


def _rel_files(base: pathlib.Path) -> set:
    return {
        p.relative_to(base)
        for p in base.rglob("*")
        if p.is_file() and not (set(p.parts) & SKIP_PARTS)
    }


def test_file_sets_match():
    """양쪽 디렉토리의 파일 목록이 동일해야 한다 (한쪽에만 추가/삭제 = drift)."""
    canonical = _rel_files(CANONICAL)
    deploy = _rel_files(DEPLOY_COPY)
    only_canonical = sorted(str(p) for p in canonical - deploy)
    only_deploy = sorted(str(p) for p in deploy - canonical)
    assert not only_canonical and not only_deploy, (
        "chat_hybrid 사본 파일 목록 불일치 — 양쪽에 동일하게 반영 필요.\n"
        f"api/ 에만 존재: {only_canonical}\n"
        f"vercel-api/ 에만 존재: {only_deploy}"
    )


@pytest.mark.parametrize(
    "rel", sorted(_rel_files(CANONICAL), key=str), ids=str
)
def test_file_contents_identical(rel):
    """파일 내용이 byte 단위로 동일해야 한다. 수정 시 양쪽 모두 반영할 것."""
    counterpart = DEPLOY_COPY / rel
    if not counterpart.exists():
        pytest.skip("목록 불일치는 test_file_sets_match 가 보고")
    assert (CANONICAL / rel).read_bytes() == counterpart.read_bytes(), (
        f"chat_hybrid 사본 내용 분기: {rel}\n"
        f"api/chat_hybrid/{rel} 와 vercel-api/api/chat_hybrid/{rel} 를 "
        "동일하게 동기화 후 커밋할 것."
    )
