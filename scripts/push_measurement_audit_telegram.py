#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""측정 감사 결과를 텔레그램으로 — **신규 발생일 때만**.

2026-08-06 신설. 사고: `measurement_audit` 가 통화 혼재 3건을 **매일** 신고하고 있었는데
워크플로 로그에 한 줄 찍고 끝이라 아무도(엔지니어 포함) 읽지 않았다. 8/6 에야 PM 질문
("자동 크론 만들었잖아? 아직도 3%야?")으로 파다가 발견했다.

교훈 = 매일 FAIL 인 경보는 경보가 아니다. 두 겹으로 막는다:
  ① measurement_audit 의 baseline — 알려진 미해결분은 KNOWN 으로 내린다
  ② 이 스크립트 — status FAIL(=baseline 초과=신규) 일 때만 발송. KNOWN/OK 는 침묵

🚨 **알림 0건이 정상 baseline.** 1건이라도 오면 그날 새로 생긴 것이다.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.config import DATA_DIR  # noqa: E402


def _previous_failing(current_as_of: str) -> list[str]:
    """trail 의 직전 실행 failing 집합. 현재 실행 행은 as_of 로 제외한다."""
    trail = os.path.join(DATA_DIR, "metadata", "measurement_audit_trail.jsonl")
    try:
        with open(trail, encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
    except (OSError, json.JSONDecodeError):
        return []
    for row in reversed(rows):
        if str(row.get("as_of")) == str(current_as_of):
            continue
        value = row.get("failing")
        if isinstance(value, list):
            return sorted(str(x) for x in value)
        # 구 trail 은 failing 집합이 없어 동일 여부를 증명할 수 없다. 한 번은 발송하고
        # 신 포맷이 쌓인 다음 실행부터 상태 전이로 판정한다.
        if row.get("status") == "FAIL":
            return []
        return []
    return []


def main() -> int:
    path = os.path.join(DATA_DIR, "measurement_audit.json")
    try:
        with open(path, encoding="utf-8") as f:
            audit = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[measurement_audit_push] 읽기 실패: {e}", file=sys.stderr)
        return 0                                  # 알림 실패가 파이프라인을 죽이지 않는다

    status = audit.get("status")
    failing = audit.get("failing") or []
    if status != "FAIL" or not failing:
        print(f"[measurement_audit_push] status={status} — 신규 없음, 발송 안 함")
        return 0

    previous = _previous_failing(str(audit.get("as_of") or ""))
    if sorted(str(x) for x in failing) == previous:
        print(f"[measurement_audit_push] FAIL 지속 상태 — 재발송 안 함: {sorted(failing)}")
        return 0

    checks = audit.get("checks") or {}
    lines = [f"<b>🚨 측정 감사 신규 검출</b> ({len(failing)}종)", ""]
    for name in failing:
        c = checks.get(name) or {}
        tag = "재발" if c.get("status") == "REGRESSION" else "신규"
        detail = str(c.get("detail") or c.get("skipped") or "")[:200]
        lines.append(f"• <b>{name}</b> [{tag}]")
        lines.append(f"  {detail}")
        base = c.get("baseline")
        if base:
            lines.append(f"  알려진 기준: {base}")
        lines.append("")
    lines.append("알려진 미해결분(KNOWN)은 발송하지 않는다 — 이 알림은 <b>새로 생긴 것</b>만.")
    if audit.get("known_unresolved"):
        lines.append(f"참고 KNOWN: {', '.join(audit['known_unresolved'])}")

    from api.notifications.telegram import send_message
    ok = send_message("\n".join(lines))
    print(f"[measurement_audit_push] 발송={'성공' if ok else '실패/미설정'} · 대상 {failing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
