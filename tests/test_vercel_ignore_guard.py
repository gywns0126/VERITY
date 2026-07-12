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
    # 객체 존재를 rev-parse 가 아니라 cat-file -e 로 검증해야 정확 (rev-parse 는 참조 해석만 하므로
    # 얕은 클론에서 부모 SHA 가 '있는데 객체는 없는' 상태를 통과시킬 수 있음).
    assert "cat-file -e" in ignore_cmd, (
        "객체 존재 검증이 rev-parse 로 되어 있음 — rev-parse 성공 != 객체 존재. cat-file -e 사용 필요"
    )
    assert "|| exit 1" in ignore_cmd, "fail-open(exit 1) 분기 소실 — 히스토리 부족 시 조용히 SKIP 될 위험"
    # 마지막 판단은 '변경 없음 → SKIP'
    assert ignore_cmd.rstrip().rstrip("'").endswith("exit 0"), "정상 경로(변경 없음)의 종료가 exit 0(SKIP) 이 아님"


def test_guard_deepens_shallow_clone(ignore_cmd: str):
    """Vercel 은 얕은 클론을 함 — 창을 계산하려면 먼저 히스토리를 깊게 파야 함."""
    assert "--deepen" in ignore_cmd, (
        "git fetch --deepen 이 없음 — 얕은 클론에서 N=50 창을 계산할 수 없어 매번 fail-open(빌드)로 떨어짐"
    )


def test_guard_note_present():
    """변경자가 회귀 이력을 보게 하는 인라인 경고 주석 (7/08 사고 재발 방지)."""
    with open(_VERCEL_JSON, encoding="utf-8") as f:
        doc = json.load(f)
    note = doc.get("_ignoreCommand_note", "")
    assert "RULE 2" in note, "_ignoreCommand_note 경고 소실 — 다음 편집자가 회귀 이력을 못 봄"
