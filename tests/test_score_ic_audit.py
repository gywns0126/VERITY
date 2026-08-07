# -*- coding: utf-8 -*-
"""점수 IC 감사 — 겹침 함정 통제 (2026-08-07).

사고: 첫 실행에서 60일 지평 IC 0.150 · t=5.02 가 나왔다. 그대로 보고했으면
"강한 신호"라고 말했을 것이다. **틀렸다.**

매일 스냅샷을 찍고 h일 forward 수익률을 재면 연속된 날의 구간이 거의 완전히 겹친다.
관측이 독립이 아닌데 독립처럼 t 를 계산하면 t 가 부풀어 없는 유의성이 생긴다.
비겹침 표본으로 다시 재니 t=5.02 → N=1 로 판정 불가, 20일은 t=2.19 → −0.07 이 됐다.

계약: ① 단면 IC(날짜가 관측 단위) — 종목 반복이 N 을 부풀리지 않는다
② naive 와 비겹침을 **함께** 내고 판정은 비겹침으로 ③ look-ahead 차단
④ 다중검정 기준 명시 ⑤ 관측 전용 — 이 산출로 임계·가중치를 만지지 않는다.
"""
import api.observability.score_ic_audit as S


def test_spearman_basic():
    assert round(S._spearman([1, 2, 3, 4], [1, 2, 3, 4]), 6) == 1.0
    assert round(S._spearman([1, 2, 3, 4], [4, 3, 2, 1]), 6) == -1.0


def test_spearman_needs_variation():
    assert S._spearman([1, 1, 1], [1, 2, 3]) is None      # 분산 0
    assert S._spearman([1, 2], [1, 2]) is None            # n<3


def test_forward_return_math():
    bars = [[20260601 + i, 0, 0, 0, 100 + i * 10, 0] for i in range(6)]
    assert round(S._fwd(bars, "2026-06-01", 3), 4) == 30.0


def test_forward_none_when_horizon_not_elapsed():
    """구간이 안 지났으면 None — 외삽 금지(있는 봉으로 때우면 미래 정보가 샌다)."""
    bars = [[20260601, 0, 0, 0, 100, 0], [20260602, 0, 0, 0, 110, 0]]
    assert S._fwd(bars, "2026-06-01", 20) is None


def test_nonoverlap_sampling_thins_by_horizon():
    """🚨 핵심 — h일 지평이면 h일 간격으로 솎아야 구간이 안 겹친다."""
    vals = [0.1] * 60
    s = S._summ(vals, horizon=20)
    assert s["n_days"] == 60
    assert s["nonoverlap"]["n"] == 3          # 60 // 20


def test_naive_t_is_inflated_vs_nonoverlap():
    """겹침을 무시하면 t 가 부풀어 오른다 — 실측 60일 t 5.02 → 판정 불가."""
    import random
    random.seed(7)
    vals = [random.gauss(0.05, 0.2) for _ in range(90)]
    s = S._summ(vals, horizon=20)
    assert s["nonoverlap"]["n"] < s["n_days"]
    # 같은 평균인데 표본이 줄어 t 절대값이 작아진다
    assert abs(s["nonoverlap"]["t_stat"] or 0) < abs(s["t_stat_naive"] or 0)


def test_judgement_field_points_to_nonoverlap():
    s = S._summ([0.1, -0.05, 0.2, 0.0, 0.15] * 6, horizon=5)
    assert "nonoverlap" in s["_note"]


def test_thin_sample_returns_no_verdict():
    s = S._summ([0.1, 0.2], horizon=5)
    assert s["mean"] is None and s.get("verdict") == "표본 부족"


def test_audit_is_observation_only():
    """🚨 RULE 7 — 이 모듈은 어떤 점수·임계도 바꾸지 않는다."""
    import inspect
    src = inspect.getsource(S)
    assert "brain_input" in src
    assert "관측 전용" in (S.__doc__ or "")
    # 쓰기는 자기 산출물 하나뿐
    assert src.count("os.replace(") == 1
