"""팩터 **내부** 미측정 하위축이 산출물까지 도달하는지 고정한다 (R6).

## 왜 (2026-08-18 신설)

결측 정책이 시스템에 **두 개**인데 하나만 보였다:

| | 위치 | 처리 | 산출물 신고 |
|---|---|---|---|
| 안쪽 | `volatility` · `quality` · `mean_reversion` 하위축 | 빼고 **재정규화** (8/17) | 🚨 **없었다** |
| 바깥 | `fact_score` 컴포넌트 | **중립 50 대입** (2026-05-20) | `missing_components` |

세 모듈이 `unmeasured_axes` 를 만들어 놓고 `multi_factor` 조립 단계에서 버렸다 —
실측(8/18) **소비처 0 · `portfolio.json` 출현 0**. 그래서 4축 중 하나가 절반만 측정된
종목과 전부 측정된 종목이 산출물에서 구분되지 않았다.

재정규화 자체는 정당하다(아핀 고정점 50, Spearman 1.000000). 문제는 **그 사실이 숨는 것**이다.
RULE 12 — 산출물이 자기 입으로 말하게 한다.

🚨 이 테스트는 **점수를 검사하지 않는다.** 전파는 보고 전용이고 점수 영향이 0 이어야 한다.
"""
from __future__ import annotations


def _mf(qf):
    from api.analyzers.multi_factor import compute_multi_factor_score
    return compute_multi_factor_score(60, {}, {}, {}, {}, quant_factors=qf)


def test_unmeasured_subaxes_reach_multi_factor():
    from api.quant.factors.volatility import compute_volatility_score

    # beta·idiosyncratic 미측정 (US 시장지수 수집처 부재 = 라이브 전량 이 상태)
    vol = compute_volatility_score(
        {"volatility_20d": 20, "volatility_60d": 25, "drop_from_high_pct": 10})
    assert vol["unmeasured_axes"], "전제 파손 — volatility 가 미측정 축을 신고하지 않는다"

    out = _mf({"volatility": vol})
    rep = out.get("quant_unmeasured_axes")
    assert isinstance(rep, dict), "quant_unmeasured_axes 가 조립 단계에서 사라졌다"
    assert "volatility" in rep, f"volatility 미측정 축이 전파되지 않았다: {rep}"
    assert set(rep["volatility"]) == set(vol["unmeasured_axes"])


def test_full_measurement_reports_empty():
    from api.quant.factors.volatility import compute_volatility_score

    vol = compute_volatility_score(
        {"volatility_20d": 20, "volatility_60d": 25, "beta": 1.0, "drop_from_high_pct": 10})
    out = _mf({"volatility": vol})
    assert out.get("quant_unmeasured_axes") == {}, "전 축 측정인데 미측정으로 신고됐다"


def test_propagation_is_score_neutral():
    """🚨 보고 전용 — 신고 필드 유무가 점수를 바꾸면 안 된다."""
    from api.quant.factors.volatility import compute_volatility_score

    vol = compute_volatility_score(
        {"volatility_20d": 20, "volatility_60d": 25, "drop_from_high_pct": 10})
    a = _mf({"volatility": vol})
    b = _mf({"volatility": {k: v for k, v in vol.items() if k != "unmeasured_axes"}})
    assert a["multi_score"] == b["multi_score"], (
        f"신고 필드가 점수를 바꿨다: {a['multi_score']} vs {b['multi_score']}")
    assert a["quant_factors"] == b["quant_factors"]


def test_fact_score_surfaces_both_missing_policies():
    """바깥(중립 50)과 안쪽(재정규화) 신고가 **나란히** 실려야 어느 정책인지 보인다."""
    import inspect
    from api.intelligence.factors import fact

    src = inspect.getsource(fact)
    assert '"unmeasured_subaxes"' in src, "fact_score 가 내부 미측정 축을 신고하지 않는다"
    assert '"missing_components"' in src, "전제 파손 — 바깥 신고가 사라졌다"
