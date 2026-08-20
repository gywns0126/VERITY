"""F-c 계약 — 인플레 축은 한국 headline CPI 의 z 부호다.
(PREREG_INFLATION_AXIS_2026_08_20, PM 승인 2026-08-20)

## 배경

종전 축 = **미국 core CPI(CPILFESL) + headline 관행 임계 3.0%**.
Q10(퍼플렉시티)이 세 층위에서 동시에 부정했다 —
① Bridgewater 원전은 지표를 특정하지 않고 핵심이 "기대 대비 서프라이즈"
② 후속 4분면 구현 관행은 headline CPI (core·PCE 를 축으로 쓴 공개 연구 없음)
③ 임계 관행은 절대 수준이 아니라 변화·z-score (절대 3% 사례 미발견)
④ core 는 headline 보다 평균이 낮다(IMF Ball 2023 · ECB 2018) → 과소분류
⑤ 한국 포트폴리오면 한국 CPI 가 관행(한국은행 CPI 2% 타게팅)

실측: 118일 중 임계 초과 **0/80** — inflation_up 계열 2개가 한 번도 안 나왔다.

🚨 여기서 잠그는 것은 "이 형태가 옳다" 가 아니라 **"사전 고정된 형태에서 벗어나지
않는다"** 다. 특히 **창(12M)** 은 스누핑 방지를 위해 테스트가 값을 고정한다.
"""
import pytest

from api.intelligence.verity_brain import detect_economic_quadrant


def _pf(kr_axis=None, gdp=2.45, us_core=2.79):
    fred = {"gdp_growth": {"value": gdp}, "cpi_yoy": {"value": us_core}}
    if kr_axis is not None:
        fred["korea_cpi_axis"] = kr_axis
    return {"macro": {"fred": fred}}


def _axis(up=True, z=1.008, yoy=2.789):
    return {"inflation_up": up, "z": z, "yoy_pct": yoy,
            "form": "rolling_z_sign_only", "window_months": 12}


# ── 창 사전 고정 (스누핑 방지) ────────────────────────────────────────────


def test_z_window_is_pinned_at_12_months():
    """🚨 창을 여러 개 시도해 고르면 그게 White(2000) 데이터 스누핑이다.

    12M 은 El-Ayari(2026 QUANTT)의 외생값이며, 변경은 사전등록 + 사유 명시로만 한다.
    """
    from api.collectors import ecos_macro as E

    assert E.KR_CPI_Z_WINDOW_M == 12, "창 변경 — 사전등록 없이 바꾸면 스누핑"
    assert E.KR_CPI_MIN_MONTHS == 25, "최소 표본(YoY 12 + z창 12 + 현재 1)이 바뀌었다"


def test_indicator_is_korean_headline_not_core():
    """지표 = ECOS 901Y009 총지수(headline). core 로 되돌아가면 잡는다."""
    from api.collectors import ecos_macro as E

    assert E.KR_CPI_STAT == "901Y009"
    assert E.KR_CPI_ITEM == "0", "총지수(headline)가 아닌 항목으로 바뀌었다"


# ── 임계 부활 차단 ────────────────────────────────────────────────────────


def _code_only(fn) -> str:
    """소스에서 주석·docstring 을 걷어낸 **실행 코드만** 반환.

    🚨 이 헬퍼가 필요한 이유 — 폐기한 것을 설명하는 주석에 그 문자열이 그대로 남는다.
    처음 이 테스트를 소스 전체 문자열 매칭으로 썼더니 **주석을 잡고 실패**했다.
    "코드에 없다" 를 검사하려면 코드만 봐야 한다.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(fn).strip())
    for node in ast.walk(tree):
        # docstring 제거
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(
                    getattr(body[0], "value", None), ast.Constant) and isinstance(
                    body[0].value.value, str):
                node.body = body[1:]
    return ast.unparse(tree)          # 주석은 AST 에 없다


def test_absolute_threshold_is_gone():
    """🚨 절대 임계 3.0 과 하드코드 2.5 fallback 이 **실행 코드에서** 사라졌는지.

    둘 다 맞물려 구조적으로 inflation_down 을 주입했다(실측 0/80).
    """
    src = _code_only(detect_economic_quadrant)
    assert "cpi_yoy > 3.0" not in src, "절대 임계 3.0 이 되살아났다"
    assert "cpi_yoy = 2.5" not in src, "하드코드 2.5 fallback 이 되살아났다"
    # pce_yoy fallback 도 같은 계열(값 주입)이므로 함께 막는다
    assert "pce_yoy" not in src, "pce_yoy fallback 이 되살아났다"


def test_sign_only_no_band():
    """F-c 는 밴드가 없다 — z 부호만 본다. 밴드가 생기면 상태가 3개가 되어 구조가 깨진다."""
    import inspect

    from api.collectors import ecos_macro as E
    src = inspect.getsource(E._kr_cpi_inflation_axis)
    assert "z > 0" in src, "부호 판정이 바뀌었다"
    assert "0.4" not in src, "밴드(±0.4)가 생겼다 — 상태 3개가 되면 4분면이 못 받는다"


# ── 결측 = 값 아님 (B1 규율 확장) ─────────────────────────────────────────


def test_missing_kr_cpi_returns_unknown_not_us_fallback():
    """🚨 한국 CPI 결측 시 **미국 core 로 되돌아가지 않는다.**

    그 경로 자체가 0/80 의 원인이었다. 되돌아가면 결함이 재발한다.
    """
    q = detect_economic_quadrant(_pf(kr_axis=None))
    assert q["quadrant"] == "unknown"
    assert q["inflation_source"] == "unknown"
    assert q["cpi_yoy"] is None, "결측인데 숫자가 만들어졌다"
    assert q["favored"] == []
    # 미국 core 는 관측용으로만 남는다
    assert q["us_core_cpi_yoy_observed"] == 2.79


def test_malformed_axis_is_treated_as_missing():
    for bad in ({}, {"inflation_up": None}, {"inflation_up": "yes"}, {"inflation_up": 1}):
        assert detect_economic_quadrant(_pf(kr_axis=bad))["quadrant"] == "unknown"


# ── 정상 경로 + 자기신고 ─────────────────────────────────────────────────


def test_inflation_up_now_reachable():
    """🚨 종전에는 118일 중 0/80 이라 이 분면이 **구조적으로 도달 불가**했다."""
    q = detect_economic_quadrant(_pf(_axis(up=True)))
    assert q["quadrant"] == "growth_up_inflation_up"
    assert q["inflation_source"] == "ecos.901Y009.headline_kr"
    assert q["inflation_form"] == "rolling_z_sign_only"
    assert q["inflation_window_months"] == 12
    assert q["inflation_z"] == 1.008


def test_inflation_down_path():
    q = detect_economic_quadrant(_pf(_axis(up=False, z=-0.8, yoy=1.5)))
    assert q["quadrant"] == "growth_up_inflation_down"
    assert q["cpi_yoy"] == 1.5


def test_us_core_is_reported_but_not_used_for_judgement():
    """🚨 두 값이 다르다는 사실이 산출물에서 보여야 한다(등록문 §6)."""
    # 미국 core 가 3.0 을 넘어도 판정은 한국 축이 정한다
    q = detect_economic_quadrant(_pf(_axis(up=False, z=-0.8), us_core=9.9))
    assert q["quadrant"] == "growth_up_inflation_down", "미국 core 가 판정에 개입했다"
    assert q["us_core_cpi_yoy_observed"] == 9.9


def test_live_ecos_axis_shape():
    """실 ECOS 호출 — 배선이 실제로 작동하는지(자격증명 없으면 skip)."""
    import os

    if not os.environ.get("ECOS_API_KEY"):
        pytest.skip("ECOS_API_KEY 없음")
    from api.collectors.ecos_macro import _kr_cpi_inflation_axis

    r = _kr_cpi_inflation_axis(os.environ["ECOS_API_KEY"])
    if r is None:
        pytest.skip("ECOS 응답 없음 — 네트워크")
    for k in ("yoy_pct", "z", "inflation_up", "date", "window_months", "form"):
        assert k in r, f"{k} 미신고"
    assert r["window_months"] == 12
    assert isinstance(r["inflation_up"], bool)
