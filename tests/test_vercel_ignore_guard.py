"""🚨 RULE 2 회귀 가드 — vercel-api/vercel.json 의 ignoreCommand 를 지킨다.

배경 (실사고 chain):
  2026-05-13  Vercel(Compute infra) 직접 메일 — 일 ~400 deploy 폭주로 차단 위협. ignoreCommand 도입.
  2026-07-06  46da2c1f2 — 창을 N=50 으로 확립 (봇 커밋이 vercel-api 커밋을 밀어내 '창 밖 skip' 발생하던 문제).
  2026-07-08  7b3da3de0 — 'perf(stock): 종목별 슬라이스 API' 가 vercel.json 을 낡은 base 에서 편집하며
              ignoreCommand 를 N=1 + fail-closed 로 **조용히 되돌림**. 배포와 무관한 커밋이 가드를 덮음.
  2026-07-10  624791d92 — "봇커밋 87개로 ignoreCommand 창 밖 skip 재발(3차)" → 수동 redeploy bump 필요.
  2026-07-13  복원 + 본 테스트 신설.

이 테스트가 지키는 불변식 2개:
  (1) 창이 충분히 넓다 (N>=50) — 봇 커밋이 vercel-api 커밋을 창 밖으로 밀어내지 못하게.
  (2) fail-open — 히스토리를 확보 못 하면 SKIP 이 아니라 BUILD.
      (SKIP 은 '진짜 API 변경이 조용히 배포되지 않음' = 더 나쁜 실패. 배포 1건 추가 << 배포 누락.)

가드를 바꾸려면 memory `project_vercel_deploy_spam_ticket_2026_05_13` 재독 후 이 테스트도 함께 갱신할 것.
"""
import json
import os
import re

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VERCEL_JSON = os.path.join(_ROOT, "vercel-api", "vercel.json")


@pytest.fixture(scope="module")
def ignore_cmd() -> str:
    with open(_VERCEL_JSON, encoding="utf-8") as f:
        doc = json.load(f)
    cmd = doc.get("ignoreCommand")
    assert cmd, "vercel.json 에 ignoreCommand 가 없음 — RULE 2 가드 소실 (배포 폭주 재발)"
    return cmd


def test_guard_scopes_to_vercel_api(ignore_cmd: str):
    """가드가 vercel-api/ 경로만 보고 판단해야 함 (데이터 커밋에 반응 금지)."""
    assert "-- vercel-api/" in ignore_cmd, "경로 스코프(-- vercel-api/) 소실"


def test_guard_window_is_wide_enough(ignore_cmd: str):
    """창 N >= 50. 1커밋 창은 봇 커밋에 밀려 진짜 변경을 놓침 (7/08 회귀 → 7/10 skip 재발 3차)."""
    m = re.search(r"N=(\d+)", ignore_cmd)
    assert m, (
        "창 크기(N=..)가 없음 — HEAD^ 단일 커밋 창으로 회귀한 것으로 보임. "
        "봇 커밋이 vercel-api 커밋을 창 밖으로 밀어내 배포가 조용히 누락됨."
    )
    n = int(m.group(1))
    assert n >= 50, f"창이 너무 좁음 (N={n} < 50) — 창 밖 skip 재발 위험"


def test_guard_is_fail_open_on_missing_history(ignore_cmd: str):
    """히스토리 확보 실패 시 BUILD(exit 1). SKIP(exit 0) 은 배포 누락 = 더 나쁜 실패."""
    assert "|| exit 1" in ignore_cmd, "fail-open(exit 1) 분기 소실 — 히스토리 부족 시 조용히 SKIP 될 위험"


def test_guard_has_no_double_quotes(ignore_cmd: str):
    """🚨 ignoreCommand 에 이중따옴표를 넣지 말 것.

    실사고 2026-07-13: 가드를 '개선'하며 `git cat-file -e "HEAD~$N^{commit}"` 처럼 이중따옴표를
    넣었다가 **프로덕션 배포 전부 FAIL** (f33f90457 / ded9c8a3d). Vercel 이 ignoreCommand 를
    셸에 넘길 때의 인용 처리와 충돌. 검증된 형태는 이중따옴표 0개.
    """
    assert '"' not in ignore_cmd, (
        "ignoreCommand 에 이중따옴표가 있음 — 2026-07-13 배포 전면 FAIL 사고. 따옴표 없이 작성할 것."
    )


def test_guard_does_not_network(ignore_cmd: str):
    """🚨 ignoreCommand 안에서 네트워크 git 명령(fetch/clone/pull) 금지.

    실사고 2026-07-13: `git fetch --deepen=60` 을 넣었다가 배포 FAIL. 빌드 컨테이너에서 자격증명이
    없으면 fetch 가 프롬프트를 기다리며 hang → ignore 스텝 타임아웃 → 배포 실패.
    로컬 히스토리만으로 판정할 것 (없으면 fail-open).
    """
    for bad in ("git fetch", "git clone", "git pull"):
        assert bad not in ignore_cmd, f"ignoreCommand 에 네트워크 명령({bad}) — hang → 배포 FAIL 위험"


def test_vercel_json_has_no_unknown_top_level_keys():
    """🚨 vercel.json 은 스키마 밖 최상위 키를 넣으면 **배포가 통째로 FAIL** 한다.

    실사고 2026-07-13: 가드 복원 PR 이 회귀 경고용으로 `_ignoreCommand_note` 키를 추가 →
    프로덕션 배포가 config 검증 단계에서 즉시 실패(dpl_5gaCLRPMigoz…). 라이브는 직전 배포가
    서빙 중이라 무사했으나 main 이 배포 불가 상태가 됨.
    → vercel.json 에 주석·메모를 넣지 말 것. 설명은 vercel-api/IGNORE_COMMAND.md 에.
    """
    with open(_VERCEL_JSON, encoding="utf-8") as f:
        doc = json.load(f)
    # Vercel 이 허용하는 최상위 키만 (현재 사용 중인 것 + 표준 스펙 일부)
    allowed = {
        "$schema", "cleanUrls", "ignoreCommand", "functions", "crons", "rewrites", "redirects",
        "headers", "regions", "trailingSlash", "framework", "buildCommand", "installCommand",
        "outputDirectory", "devCommand", "public", "github", "images",
    }
    unknown = sorted(k for k in doc if k not in allowed)
    assert not unknown, (
        f"vercel.json 스키마 밖 최상위 키: {unknown} — Vercel 이 거부해 **배포 전체가 FAIL** 함. "
        "설명·경고는 vercel-api/IGNORE_COMMAND.md 에 둘 것 (2026-07-13 실사고)."
    )


def test_guard_doc_exists():
    """회귀 이력·불변식 문서가 vercel.json 옆에 존재해야 함 (7/08 회귀 재발 방지)."""
    doc_path = os.path.join(_ROOT, "vercel-api", "IGNORE_COMMAND.md")
    assert os.path.isfile(doc_path), "vercel-api/IGNORE_COMMAND.md 소실 — 다음 편집자가 회귀 이력을 못 봄"
    with open(doc_path, encoding="utf-8") as f:
        body = f.read()
    assert "RULE 2" in body and "N=50" in body, "IGNORE_COMMAND.md 에 RULE 2 / N=50 불변식 설명이 없음"
