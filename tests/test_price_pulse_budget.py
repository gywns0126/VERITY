"""price_pulse 시간 예산 회귀 테스트 (네트워크 0).

2026-08-15 신설. 취소 58%의 원인이 **타임아웃**이었다는 실측을 고정한다.

실측 근거 (GitHub jobs/timing API — print 타임스탬프 아님):
  · 표본 100건 = cancelled 58 / success 41 / failure 1
  · 취소분 job 시간 309·319·320·322초 — 전부 5분 경계, 12개 step 실행 후 사망(큐 대기 아님)
  · 성공분 step 프로파일 289초 =
      publish 126 · pip 61 · checkout 41 · setup-python 24 · **작업 19** · commit 3 · warm 7
  · 한도 300초 대비 여유 11초 → 조금만 느리면 잘린다
  · billable 0 (public repo = 무제한 무료). 즉 비용이 아니라 절단이 문제였다

🚫 publish(126초) 축소 금지 — publish-data 는 force_orphan: true 로 VERITY-data main 을
   통째 교체한다. 파일 목록을 줄이면 나머지 74개가 삭제되어 공개 데이터 장애가 난다.
   그 사실을 test_publish_is_force_orphan 이 고정한다.
"""
from __future__ import annotations

import os
import re

import pytest
import yaml

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF = os.path.join(_ROOT, ".github", "workflows", "price_pulse.yml")
ACTION = os.path.join(_ROOT, ".github", "actions", "publish-data", "action.yml")

# 실측 상수 — 바뀌면 재측정 후 갱신할 것
MEASURED_RUN_S = 289
MEASURED_WORK_S = 19


def _wf():
    with open(WF, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _job():
    return _wf()["jobs"]["pulse"]


def test_timeout_has_headroom_over_measured_runtime():
    """실측 289초를 timeout 이 넉넉히 덮어야 한다. 5분(300s)은 여유 11초였다."""
    t = _job()["timeout-minutes"]
    assert t * 60 >= MEASURED_RUN_S * 1.5, (
        f"timeout {t}분이 실측 {MEASURED_RUN_S}초 대비 여유 부족 — 58% 절단 재발")
    assert t <= 20, f"timeout {t}분은 과대 — 5분 주기 워크플로가 겹쳐 쌓인다"


def test_checkout_is_shallow():
    """전체 히스토리 clone 이 41초였다. price_pulse 커밋만 13,140건."""
    steps = _job()["steps"]
    co = next(s for s in steps if "checkout" in str(s.get("uses", "")).lower())
    depth = (co.get("with") or {}).get("fetch-depth")
    assert depth is not None, "fetch-depth 미지정 = 전체 히스토리(41초)"
    assert 1 <= int(depth) <= 50, depth


def test_publish_is_force_orphan_so_file_list_must_stay_full():
    """🚫 발행 파일 목록 축소 금지 가드.

    publish-data 는 external_repository 를 force_orphan 으로 교체한다. price_pulse 가
    자기 파일만 발행하도록 바꾸면 VERITY-data 에서 나머지가 삭제된다.
    이 테스트가 깨지면 = 배포 방식이 바뀐 것이니 그때 목록 축소를 재검토하라.
    """
    with open(ACTION, encoding="utf-8") as f:
        src = f.read()
    assert "force_orphan: true" in src, (
        "force_orphan 이 아니게 바뀌었다면 price_pulse 발행 범위 축소를 재검토할 것")
    assert "external_repository: gywns0126/VERITY-data" in src


def test_pulse_workflow_does_not_issue_kis_token():
    """RULE 1 — price_pulse 는 cache_only 소비자다. 발급 경로 0."""
    with open(WF, encoding="utf-8") as f:
        src = f.read()
    assert 'KIS_SHARED_TOKEN: "1"' in src
    # 락 파일 propagation 은 유지 (defense in depth)
    assert "data/.kis_issued_date.txt" in src


def test_concurrency_group_isolated():
    """daily_analysis(verity-data-write) / daily_realtime(verity-realtime) 와 격리 유지."""
    c = _wf()["concurrency"]
    assert c["group"] == "verity-pulse"
    assert c["cancel-in-progress"] is False


def test_work_step_is_tiny_relative_to_overhead():
    """문서화용 — 19초 작업에 오버헤드 93%라는 사실을 코드에 남긴다."""
    with open(WF, encoding="utf-8") as f:
        src = f.read()
    assert re.search(r"오버헤드가?\s*93%", src), (
        "실측 근거 주석이 사라졌다 — 다음 사람이 같은 측정을 반복하게 된다")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
