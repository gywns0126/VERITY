"""공개 컴포넌트의 **로드 판정 필드**가 발행본에 실제로 있는지 검사한다 (2026-08-19).

## 왜

`PublicGlassboxTab` 이 `if (d && d.gate)` 로 로드를 판정했다. 백엔드가 표본수 게이트
폐기 정합으로 `gate` 를 **null** 로 보내기 시작하자(§7-1) 이 조건이 항상 거짓이 되어,
데이터가 정상 도착했는데도 화면에 **"검증 데이터를 불러오지 못했어요"** 가 떴다.

🚨 **로드 판정을 폐기 예정 필드에 걸어둔 것**이 결함이다. 백엔드에서 필드를 지우는 것은
정당한 변경인데, 프런트가 그 필드로 "데이터가 왔는지" 를 판정하면 정상 데이터가 실패로 둔갑한다.

같은 날 같은 뿌리를 두 번 더 봤다 — 컴포넌트 폴백 `Number(gate.target_n) || 252` 가
폐기된 목표를 0% 진행률로 되살린 것, `alert_dispatcher` 가 비핵심 소스에 🔴 를 낸 것.
공통 = **한쪽에서 지운 것을 다른 쪽이 여전히 전제한다.**

이 테스트는 계약을 고정한다 — 로드 판정에 쓰는 필드는 발행본에 반드시 존재해야 한다.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PP = _ROOT / "framer-components" / "public-probe"

# (컴포넌트, 발행 산출물, 로드 판정 필드)
LOAD_GATES = [
    ("PublicGlassboxTab.tsx", "validation_summary.json", "signals"),
    ("PublicBondRegime.tsx", "bonds.json", "yield_curves"),
]


@pytest.mark.parametrize("comp,artifact,field", LOAD_GATES)
def test_load_gate_field_exists_in_artifact(comp, artifact, field):
    """로드 판정 필드가 로컬 발행본에 존재하는지 (라이브 조회 없이 계약만 검사)."""
    p = _ROOT / "data" / artifact
    if not p.exists():
        pytest.skip(f"{artifact} 부재 — 데이터 없는 환경")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert field in d, f"{comp} 의 로드 판정 필드 '{field}' 가 {artifact} 에 없다"
    v = d[field]
    assert v is not None and v != [] and v != {}, (
        f"{comp} 로드 판정이 falsy 값에 걸린다: {artifact}.{field} = {v!r}\n"
        "→ 데이터가 정상 도착해도 '불러오지 못했어요' 가 뜬다")


def test_glassbox_does_not_gate_on_retired_field():
    """🚨 `gate` 는 §7-1 로 폐기됐다 — 로드 판정에 다시 쓰면 실패한다."""
    src = (_PP / "PublicGlassboxTab.tsx").read_text(encoding="utf-8")
    body = "\n".join(l for l in src.split("\n") if not l.strip().startswith("//"))
    assert not re.search(r"if\s*\(\s*d\s*&&\s*d\.gate\s*\)", body), (
        "로드 판정이 폐기된 `gate` 필드로 되돌아갔다 (2026-08-19 사고)")
    assert re.search(r"d\s*&&\s*Array\.isArray\(\s*d\.signals\s*\)", body), (
        "로드 판정이 `signals` 기준이 아니다")


def test_no_component_gates_on_stripped_publish_fields():
    """🚨 발행에서 제거한 필드로 로드를 판정하는 컴포넌트가 없어야 한다.

    2026-08-19 에 발행본에서 뺀 것 = 애널리스트 컨센서스 3키(PM 결정) ·
    trail_integrity 진척 필드(§7-1 폐기).
    """
    STRIPPED = ("consensus", "analyst_consensus", "analyst_report_summary",
                "pct_to_gate", "gate_n", "remaining_days")
    hits = []
    for p in sorted(_PP.glob("*.tsx")):
        body = "\n".join(l for l in p.read_text(encoding="utf-8").split("\n")
                         if not l.strip().startswith("//"))
        for f in STRIPPED:
            if re.search(rf"if\s*\(\s*(?:alive\s*&&\s*)?d\s*&&\s*d\.{f}\b", body):
                hits.append(f"{p.name} — d.{f}")
    assert not hits, "발행에서 제거된 필드로 로드를 판정한다:\n  " + "\n  ".join(hits)
