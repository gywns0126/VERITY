"""실행 진척 등록부 — 런타임 예산이 끊길 때 "무엇이 얼마나 안 됐나" 를 신고한다.

🚨 왜 필요한가 (2026-08-13 신설).

  full run 이 자체 예산 110분을 소진해 SIGTERM 으로 종료됐다(run 31745952833). 죽은 지점은
  Gemini 배치 **16/50** 이었고 상위 50종목 중 34개가 AI 종합 없이 남았다. 그런데 그 뒤 발행
  단계는 정상 완료했기 때문에(blob 1,331건 0 실패) `data_health` 는 **green** 으로 찍혔다.
  즉 **결손이 초록불 뒤에 숨는다.** 없는 것보다 나쁜 상태다
  ([[feedback_silent_total_failure_guard]] · [[feedback_render_stage_silent_field_drop]] 정합).

  예산을 늘리는 것은 별개 판단이고, 늘려도 언젠가 다시 걸린다. 그때도 안 보이는 게 진짜 문제라
  **먼저 보이게** 만든다. 이 모듈은 판정도 수정도 하지 않는다 — 신고만 한다.

사용법 (긴 루프를 도는 단계에서 한 줄):

    from api.observability import run_progress
    for i, item in enumerate(items):
        run_progress.set_stage("gemini_batch", i + 1, len(items), "종목")

끊길 때는 `api/main.py` 의 SIGTERM 핸들러가 `format_shortfall()` 을 알림에 싣고
`append_cutoff_row()` 로 장부에 남긴다.

🚨 장부 경로는 `data/metadata/` 아래다 — 해당 워크플로가 `git add data/`(broad) 를 쓰므로
   RULE 4(신 logging 파일 추가 시 workflow git add 정합) 는 자동 충족. 경로를 `data/` 밖으로
   옮기면 커밋에서 조용히 빠진다.
"""
from __future__ import annotations

import json
import os
import threading
from collections import OrderedDict
from typing import Any, Dict, Optional

_LOCK = threading.Lock()
_STAGES: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
_CUTOFF: Dict[str, Any] = {"reason": None}

# 기본 장부 경로 — 테스트는 인자로 갈아끼운다.
DEFAULT_LOG_PATH = os.path.join("data", "metadata", "runtime_cutoff.jsonl")


def reset() -> None:
    """테스트/재진입용. 전역 상태 초기화."""
    with _LOCK:
        _STAGES.clear()
        _CUTOFF["reason"] = None


def set_stage(name: str, done: int, total: int, unit: str = "건") -> None:
    """단계 진척 갱신. 같은 이름으로 계속 덮어쓴다(마지막 값 = 현재 진척).

    total 이 0 이하이면 진척 비율을 못 내므로 기록만 남긴다.
    """
    if not name:
        return
    with _LOCK:
        _STAGES[name] = {
            "done": int(done),
            "total": int(total),
            "unit": unit or "건",
        }


def mark_cutoff(reason: str) -> None:
    """끊긴 사유를 못박는다. 먼저 기록된 사유가 이긴다.

    watchdog(예산 소진)이 SIGTERM 을 보내기 **전에** 호출하므로, 핸들러에서 사유가 비어 있으면
    외부 취소(GH Actions concurrency cancel 등)로 구분된다. 둘을 섞으면 예산 문제 빈도를
    잘못 세게 된다.
    """
    with _LOCK:
        if _CUTOFF["reason"] is None:
            _CUTOFF["reason"] = reason


def snapshot() -> Dict[str, Any]:
    with _LOCK:
        return {
            "reason": _CUTOFF["reason"] or "external_sigterm",
            "stages": {k: dict(v) for k, v in _STAGES.items()},
        }


def _shortfall_items(snap: Optional[Dict[str, Any]] = None):
    snap = snap or snapshot()
    out = []
    for name, st in (snap.get("stages") or {}).items():
        total, done = int(st.get("total", 0)), int(st.get("done", 0))
        if total > 0 and done < total:
            out.append((name, done, total, total - done, st.get("unit", "건")))
    return out


def format_shortfall(snap: Optional[Dict[str, Any]] = None) -> str:
    """사람이 읽을 신고문. 결손이 없으면 그렇다고 말한다 — 빈 문자열로 삼키지 않는다."""
    snap = snap or snapshot()
    items = _shortfall_items(snap)
    reason_ko = {
        "runtime_budget": "런타임 예산 소진",
        "external_sigterm": "외부 종료(취소 등)",
    }.get(snap.get("reason"), str(snap.get("reason")))

    if not (snap.get("stages") or {}):
        return f"{reason_ko} · 진척 등록 단계 없음(어디서 끊겼는지 미상)"
    if not items:
        return f"{reason_ko} · 등록된 단계는 전부 완료 — 미처리 0"

    lines = [f"{reason_ko} · 미처리 {len(items)}개 단계"]
    for name, done, total, left, unit in items:
        pct = round(done / total * 100)
        lines.append(f"· {name} {done}/{total}{unit} ({pct}%) — 미처리 {left}{unit}")
    return "\n".join(lines)


def append_cutoff_row(path: str = DEFAULT_LOG_PATH, extra: Optional[Dict[str, Any]] = None) -> bool:
    """장부 1행 append. 신호 핸들러에서 불리므로 절대 예외를 밖으로 내보내지 않는다.

    반환값 = 기록 성공 여부. 실패해도 종료 흐름을 막지 않는다.
    """
    try:
        snap = snapshot()
        row: Dict[str, Any] = {
            "reason": snap["reason"],
            "stages": snap["stages"],
            "shortfall": [
                {"stage": n, "done": d, "total": t, "missing": m, "unit": u}
                for n, d, t, m, u in _shortfall_items(snap)
            ],
        }
        if extra:
            row.update(extra)
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False
