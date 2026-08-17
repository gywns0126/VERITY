"""VAMS 국면 맥락 회귀 테스트 — 기록 의무이되 **판정에는 절대 안 들어간다**.

## 이 파일이 지키는 것

PM 승인(2026-08-18): VAMS 게이트 판정문에 국면을 **병기**한다. 기준 변경이 아니다.

주식도 국면 의존이 실측된다(200d MA 위 Sharpe 1.83 vs 아래 −1.03, t=+2.58). 그런데
게이트를 국면 조건부로 바꾸는 것은 **지표 선택이 사전등록 대상**이라 보류했다 —
후보 3개를 이미 봤고(200d MA t=+2.58 / 20일 t=+5.11 / 60일 t=+2.47), 급조하면
크립토의 200d MA 를 그대로 옮겨 잘못된 안심을 만든다. 실제로 그 지표는 KR 에서
2026-06~08 창을 오판한 전력이 있다.

🚨 **그래서 가장 중요한 성질은 "판정에 안 들어간다" 이다.** advisory 가 슬그머니
게이트로 승격하면 사전등록을 우회한 산식 변경이 된다(RULE 7 위반).

상세 = `docs/KR_REGIME_WATCH_ASSESSMENT_2026_08_18.md`
"""
from __future__ import annotations

import inspect

from api.vams import regime_context


# ══════════════ ① 판정 침투 차단 (가장 중요) ══════════════

def test_context_has_no_pass_or_verdict_keys():
    """🚨 pass/verdict 키를 만들지 않는다 — 게이트에 잘못 꽂으면 즉시 깨지도록."""
    r = regime_context.describe()
    for forbidden in ("pass", "verdict", "eligible", "score", "grade"):
        assert forbidden not in r, (
            f"'{forbidden}' 키가 있다 — advisory 가 판정으로 승격할 통로가 된다")


def test_context_self_declares_advisory():
    r = regime_context.describe()
    assert r.get("advisory_only") is True
    assert "not_a_gate" in r or "error" in r


def test_gate_does_not_read_regime_into_verdict():
    """🚨 validation 이 국면 값을 pass 계산에 쓰지 않는가 (소스 검사)."""
    from api.vams import validation

    src = inspect.getsource(validation)
    assert '"regime_context": _regime_context_safe()' in src, "국면 맥락이 산출물에 없다"
    # regime_context 결과가 pass/verdict 계산에 흘러들지 않는지 — 변수로 받지 않는다
    assert "regime_ctx =" not in src and "rc =" not in src, (
        "국면 값을 변수로 받으면 판정에 섞일 통로가 생긴다 — 산출물에만 넣을 것")


def test_gate_survives_context_failure():
    """국면 산출이 실패해도 게이트가 죽지 않는다."""
    from api.vams import validation

    src = inspect.getsource(validation._regime_context_safe)
    assert "except Exception" in src, "국면 조회 실패가 게이트 전체를 죽인다"


# ══════════════ ② 맥락 값 자체 ══════════════

def test_window_slicing_works():
    """창을 나눠 재면 다른 값이 나온다 — 2026-08-18 에 이 분해로 초판 오류를 잡았다."""
    down = regime_context.describe(20260618, 20260730)
    up = regime_context.describe(20260731, 20260813)
    if "error" in down or "error" in up:
        return          # 데이터 미보유 환경에서는 통과
    assert down["market_return_pct"] < 0 < up["market_return_pct"], (
        "6/18~7/30 하락 · 7/31~8/13 반등 구조가 재현되지 않는다")
    assert down["momentum_weak_ratio"] > up["momentum_weak_ratio"]


def test_note_carries_ma200_caveat():
    """🚨 200d MA 오판 전력을 항상 같이 적는다 — 숫자만 보면 잘못 믿는다."""
    r = regime_context.describe()
    if "error" in r:
        return
    assert "오판" in r["note"], "200d MA 한계 경고가 빠지면 잘못된 안심을 만든다"


def test_empty_window_reports_error_not_zero():
    """🚨 관측 0일을 '시장 0%' 로 내지 않는다 — 판정 불가는 에러로."""
    r = regime_context.describe(19000101, 19000102)
    assert "error" in r and "market_return_pct" not in r
