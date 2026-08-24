# -*- coding: utf-8 -*-
"""executor_contract — 산출물에 실린 숫자가 **집행에 쓰이는지** 신고하게 한다.

2026-08-25 신설. 하루에 같은 계열 결함을 **넷** 잡았고 원인이 하나였다 —
표시값이 집행값인 척한다.

```
market_cap 0        표시 0 이 "모른다"인지 "작다"인지 구분 안 됨   → 하류가 숫자로 정렬
decision_basis      체결은 verity_brain, 기록은 multi_factor      → 감사 흔적이 체결과 불일치
reasoning 축        점수를 만들지 않은 축으로 종목을 설명(38/38)   → PM 이 읽는 근거가 무관 축
position_guide      표시 3%, 집행 기준선 20.6%                    → 사이징을 3% 로 잘못 답함
```

넷 다 개별로 고쳤다. 그런데 **인스턴스만 고치면 클래스가 남는다**
([[feedback_green_check_is_not_safety]]). 다섯 번째는 다른 이름으로 온다.

이 모듈이 강제하는 것은 하나다: **집행에 쓰일 법한 숫자를 싣는 블록은 자기가 집행자인지
아닌지 말해야 한다.** 말하지 않으면 다음 세션이 표시값을 규칙으로 읽는다.

`tests/test_executor_contract.py` 가 회귀와 신규 유입을 둘 다 막는다.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

# 🚨 "집행에 쓰일 법한" 키 — 이 이름을 달고 있으면 하류가 규칙으로 읽을 가능성이 크다.
#    2026-08-25 실측 4건에서 귀납했다. 늘리는 것은 자유, 줄이려면 사유를 남길 것.
EXECUTION_ISH_KEYS: frozenset = frozenset({
    "recommended_pct", "max_pct", "position_pct", "target_pct",
    "stop_loss_pct", "trailing_stop_pct", "max_per_stock",
    "threshold", "cutoff", "min_safety", "weight", "weights",
})

# 신고에 쓰는 키 — 셋 중 하나라도 있으면 "말했다" 로 본다.
DECLARATION_KEYS: frozenset = frozenset({"is_executor", "executor", "executed_by"})


def declare_advisory(executor: str, scope: str) -> Dict[str, Any]:
    """이 블록은 **집행자가 아니다** 라고 산출물에 적는다.

    Args:
        executor: 실제로 집행하는 곳 (예: "vams.execute_buy (profile.max_per_stock 기반)")
        scope: 이 값이 무엇인지 (예: "참고 상한 — 헌법 max_position_pct[grade]")

    🚨 `executor` 는 **모듈·함수까지** 적는다. "VAMS" 같은 뭉뚱그린 표기는 다음 세션이
       못 찾는다 — 못 찾으면 결국 표시값을 쓴다.
    """
    if not executor or "." not in executor:
        raise ValueError(f"executor 는 모듈.함수 까지 적어야 한다: {executor!r}")
    return {"is_executor": False, "executor": executor, "scope": scope}


def declare_executed(executor: str, chain: Dict[str, Any]) -> Dict[str, Any]:
    """이 블록이 **실제로 집행한 값**이라고 적고, 어떻게 나왔는지 체인을 남긴다."""
    if not executor or "." not in executor:
        raise ValueError(f"executor 는 모듈.함수 까지 적어야 한다: {executor!r}")
    return {"is_executor": True, "executor": executor, **chain}


def _declares(block: Dict[str, Any]) -> bool:
    return bool(DECLARATION_KEYS & set(block))


def scan_undeclared(obj: Any, path: str = "") -> List[Tuple[str, List[str]]]:
    """집행 관련 키를 싣고도 신고하지 않은 블록을 찾는다.

    Returns: [(경로, 걸린 키들)] — 신고 없는 것만.

    🚨 이건 **탐지이지 판정이 아니다.** 정당하게 신고 없이 살아도 되는 블록이 있다
       (예: 순수 설정 파일). 그래서 테스트는 이 목록의 **증가**만 막는다(래칫).
    """
    out: List[Tuple[str, List[str]]] = []
    if isinstance(obj, dict):
        hits = sorted(EXECUTION_ISH_KEYS & set(obj))
        if hits and not _declares(obj):
            out.append((path or "/", hits))
        for k, v in obj.items():
            out.extend(scan_undeclared(v, f"{path}/{k}"))
    elif isinstance(obj, list):
        # 리스트 원소는 경로를 인덱스로 벌리지 않는다 — 종목 3천 개면 경로가 폭발한다.
        # 대신 첫 원소만 대표로 본다(같은 스키마 가정).
        if obj:
            out.extend(scan_undeclared(obj[0], f"{path}[]"))
    return out


def summarize(paths: Iterable[Tuple[str, List[str]]]) -> str:
    rows = list(paths)
    if not rows:
        return "신고 없는 집행 관련 블록 0"
    body = "\n".join(f"  {p}  ← {', '.join(k)}" for p, k in rows[:20])
    more = f"\n  … 외 {len(rows) - 20}건" if len(rows) > 20 else ""
    return f"신고 없는 집행 관련 블록 {len(rows)}건\n{body}{more}"
