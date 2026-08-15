#!/usr/bin/env python3
"""중복 트리거 가드 — 같은 슬롯에 이미 성공한 run 이 있으면 생략을 지시한다.

🚨 왜 (2026-08-15 실측)
  daily_analysis_full 은 트리거가 둘이다 — GH `schedule` + Vercel `repository_dispatch`.
  후자는 "GH schedule silent miss 회피" fallback(2026-05-18)인데, GH 가 정상 발화하면
  **둘 다 돈다**. fallback 에 "본편이 이미 돌았나" 확인이 없었다.

  GitHub API 표본 60건 / 20일 → 중복 쌍 **16건**.
    예) 08-14T21:30 dispatch(실패 110분) + 21:49 schedule(성공 146분) = 슬롯 하나에 256분.
        두 번째는 concurrency 큐에서 96분 대기 후 시작했다.
  universe_scan 도 같은 구조로 4건(양쪽 성공 = 순수 낭비) — 후속 과제.

🚨 설계 원칙 두 가지
  ① **선행이 '성공'했을 때만 생략한다.** 중복이 우연히 재시도 역할을 했다 — 08-14 는
     dispatch 가 실패하고 schedule 이 성공해 그날 산출물을 건졌다. 조건을 "선행이 존재하면
     생략" 으로 넓히면 그 구제가 사라진다. 실패·취소·진행중은 전부 실행이다.
  ② **fail-open.** 조회 실패·자기 run 미발견·판단 불가 = 무조건 실행. 슬롯을 비우는 것이
     이 fallback 이 애초에 막으려던 사고이므로, 의심스러우면 도는 쪽이 맞다.

입력  : stdin = GitHub Actions runs API 응답 JSON
환경  : SELF=현재 run id · WINDOW_MIN=중복 판정 창(분, 기본 120)
출력  : 마지막 줄에 `run=0`(생략) 또는 `run=1`(실행). 종료코드는 항상 0.

창 크기: 관측 중복 간격 18.9~88.8분. 정규 슬롯 간격은 13.7h 이상이라 120분은 안전하다.

🚫 워크플로 YAML 에 인라인으로 되돌리지 말 것 — 블록 스칼라 들여쓰기가 깨져 워크플로가
   통째로 무효가 된다(2026-08-15 작성 중 실측). 파일로 두면 테스트도 이 파일을 직접 돌린다.
"""
from __future__ import annotations

import datetime
import json
import os
import sys


def _dt(s: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))


def decide(payload: dict, self_id: int, window_min: float) -> tuple[bool, str]:
    """(실행할지, 사유). 예외는 호출자가 fail-open 으로 처리한다."""
    runs = payload.get("workflow_runs") or []
    me = next((r for r in runs if r.get("id") == self_id), None)
    if me is None:
        return True, "자기 run 미발견 — fail-open 실행"

    anchor = _dt(me["created_at"])
    for r in runs:
        if r.get("id") == self_id:
            continue
        # 결론이 'success' 인 것만 — 실패·취소·진행중은 재시도 여지를 남긴다.
        if r.get("conclusion") != "success":
            continue
        try:
            gap = (anchor - _dt(r["created_at"])).total_seconds() / 60
        except Exception:  # noqa: BLE001
            continue
        # gap<0 = 자기보다 나중 run. 그걸로 생략하지 않는다.
        if 0 <= gap <= window_min:
            return False, (
                "선행 성공분 발견 (run %s, %.1f분 전, %s) — 중복 실행 생략"
                % (r.get("id"), gap, r.get("event"))
            )
    return True, "창 %.0f분 내 선행 성공분 없음 — 실행" % window_min


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        self_id = int(os.environ["SELF"])
        window = float(os.environ.get("WINDOW_MIN", "120") or "120")
        should_run, reason = decide(payload, self_id, window)
    except Exception as e:  # noqa: BLE001
        print("가드 판정 실패(%s) — fail-open 실행" % e)
        print("run=1")
        return 0
    print(reason)
    print("run=1" if should_run else "run=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
