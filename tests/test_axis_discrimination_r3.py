"""R3 — 축 변별 소멸 감시가 실제로 두 방향을 다 잡는지 고정한다.

§7-C 최초안 "고유값 ≤ 2" 는 두 가지가 문제였다:
  · 실측 고유값이 28/17/26/23 이라 2 까지 떨어지려면 완전 상수화 이후 = 걸릴 때 이미 늦다
  · 🚨 고유값 임계는 **N 에 의존**한다. 풀이 56 → 10 으로 줄면 정상 운영이 오탐된다

그래서 N 무관한 최빈값 점유율을 병행한다. 실측(N=56) 최빈 점유 최악 23.2% → 임계 50%
까지 여유 26.8%p.
"""
from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "audit"))
import axis_discrimination as AD


def _pf(values_by_axis):
    n = max(len(v) for v in values_by_axis.values())
    recs = []
    for i in range(n):
        comp = {a: v[i] for a, v in values_by_axis.items() if i < len(v)}
        recs.append({"verity_brain": {"fact_score": {"components": comp}}})
    return {"recommendations": recs}


def _healthy(n=56):
    return {a: [float(30 + (i * 7 + j * 3) % 60) for i in range(n)]
            for j, a in enumerate(AD.AXES)}


def test_healthy_pool_passes():
    r = AD.audit(_pf(_healthy()))
    assert r["severity"] == "OK", f"정상 분포가 발동했다: {r['fired']}"


def test_live_pool_passes():
    """🚨 라이브 산출물로도 통과해야 한다 — 임계가 현재 운영을 오탐하면 못 쓴다."""
    import json, pathlib
    p = pathlib.Path(AD._ROOT) / "data" / "portfolio.json"
    if not p.exists():
        return
    r = AD.audit(json.loads(p.read_text(encoding="utf-8")))
    assert r["severity"] == "OK", f"라이브 운영 풀이 오탐됐다: {r['fired']}"


def test_constant_axis_fires_by_unique():
    v = _healthy()
    v["quant_volatility"] = [50.0] * 56          # 완전 상수
    r = AD.audit(_pf(v))
    assert r["severity"] == "FAIL"
    assert any("quant_volatility" in f and "고유값" in f for f in r["fired"])


def test_modal_dominance_fires_even_with_many_unique():
    """🚨 고유값이 충분해도 한 값이 과반이면 변별하지 않는 것이다.

    고유값 임계 단독으로는 이 형태를 절대 못 잡는다 — 그래서 두 기준을 둔다.
    """
    v = _healthy()
    v["graham_value"] = [50.0] * 40 + [float(60 + i) for i in range(16)]  # 고유값 17, 최빈 71%
    r = AD.audit(_pf(v))
    assert r["severity"] == "FAIL"
    fired = " ".join(r["fired"])
    assert "graham_value" in fired and "최빈" in fired
    row = next(x for x in r["rows"] if x["axis"] == "graham_value")
    assert row["unique"] > AD.MIN_UNIQUE, "고유값만 봤다면 통과했을 케이스여야 의미가 있다"


def test_small_sample_is_held_not_failed():
    """표본이 적으면 무엇이든 상수처럼 보인다 — 판정을 보류한다(오탐 방지)."""
    v = {a: [50.0] * 5 for a in AD.AXES}
    r = AD.audit(_pf(v))
    assert r["severity"] == "OK"
    assert all("보류" in x["verdict"] for x in r["rows"])
