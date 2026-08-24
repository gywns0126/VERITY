# -*- coding: utf-8 -*-
"""표시값이 집행값인 척하는 것을 클래스로 막는다 (2026-08-25 신설).

2026-08-24~25 하루에 같은 계열 결함 **넷**을 잡았고 원인이 하나였다.

```
market_cap 0     표시 0 이 "모른다"인지 "작다"인지 구분 안 됨
decision_basis   체결은 verity_brain, 기록은 multi_factor
reasoning 축     점수를 만들지 않은 축으로 종목을 설명 (38/38)
position_guide   표시 3%, 집행 기준선 20.6% → 사이징을 3% 로 잘못 답함
```

🚨 **인스턴스만 고치면 클래스가 남는다.** 다섯 번째는 다른 이름으로 온다 —
실제로 이 스캐너를 처음 돌리자마자 `trade_plan.position_pct` 가 나왔다.
"""
import json
import os

import pytest

from api.observability.executor_contract import (
    DECLARATION_KEYS,
    EXECUTION_ISH_KEYS,
    declare_advisory,
    declare_executed,
    scan_undeclared,
    summarize,
)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 🚨 래칫 상한 — 2026-08-25 실측 기준선.
#   현재 10건. 다음 universe_scan 이 돌면 position_guide 가 신고를 달고 나와 **9 로 내려간다**.
#   알려진 다음 표적 = `trade_plan.position_pct`(집행 아님, entry_zone·position_pct 모두 참고값).
#   🚨 **이 숫자를 올려서 통과시키지 말 것.** 올리는 순간 클래스 가드가 죽는다.
#   내려가는 방향으로만 갱신한다.
MAX_UNDECLARED = 10


def _sample_record():
    p = os.path.join(_ROOT, "data", "recommendations.json")
    if not os.path.exists(p):
        pytest.skip("recommendations.json 없음 — 로컬 산출물 미생성")
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    rows = d if isinstance(d, list) else (d.get("stocks") or d.get("recommendations") or [])
    rows = [r for r in rows if isinstance(r, dict)]
    if not rows:
        pytest.skip("레코드 0건")
    return rows[0]


def test_declare_advisory_requires_module_level_executor():
    """'VAMS' 같은 뭉뚱그린 표기는 다음 세션이 못 찾는다 — 못 찾으면 표시값을 쓴다."""
    d = declare_advisory("vams.execute_buy (profile.max_per_stock 기반)", "참고 상한")
    assert d["is_executor"] is False
    assert "." in d["executor"]
    with pytest.raises(ValueError):
        declare_advisory("VAMS", "참고 상한")
    with pytest.raises(ValueError):
        declare_executed("엔진", {"base": 1})


def test_scanner_catches_undeclared_and_ignores_declared():
    bad = {"recommended_pct": 3, "max_pct": 3}
    good = {"recommended_pct": 3, "max_pct": 3,
            **declare_advisory("vams.execute_buy", "참고 상한")}
    assert scan_undeclared(bad) == [("/", ["max_pct", "recommended_pct"])]
    assert scan_undeclared(good) == []


def test_declaration_keys_are_what_the_fixes_actually_emit():
    """실제 수정본이 쓰는 키와 계약이 어긋나면 가드가 헛돈다."""
    assert "is_executor" in DECLARATION_KEYS
    assert "executor" in DECLARATION_KEYS
    for k in ("recommended_pct", "max_pct", "position_pct"):
        assert k in EXECUTION_ISH_KEYS


def test_undeclared_blocks_do_not_increase():
    """🚨 래칫 — 신고 없는 집행 관련 블록이 늘면 실패한다.

    줄어드는 것은 자유. 늘리려면 이 상수를 올려야 하고, 그건 가드를 끄는 것이다.
    """
    found = scan_undeclared(_sample_record(), "/recommendations[]")
    assert len(found) <= MAX_UNDECLARED, (
        f"신고 없는 집행 관련 블록이 {len(found)}건으로 늘었다 (상한 {MAX_UNDECLARED}).\n"
        f"{summarize(found)}\n"
        "→ 새 블록에 executor_contract.declare_advisory / declare_executed 를 붙일 것. "
        "상한을 올려서 통과시키지 말 것."
    )


def test_fact_score_reports_runtime_weights():
    """헌법 정적표로는 38중 33만 재현된다 — 실가중을 산출물이 신고해야 재현 가능하다."""
    import inspect
    from api.intelligence.factors import fact
    src = inspect.getsource(fact)
    assert "weights_effective" in src, "fact_score 런타임 가중 신고가 사라졌다"
