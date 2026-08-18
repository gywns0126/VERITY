"""V7 fractional Kelly 단위테스트 — PREREG_KELLY_FIX_2026_08_02 (PM 승인 2026-08-02).

옛 V6 결함(실측): brain 50~90 전 구간 0.5× 동일(edge 무차별) + brain 40 ≈0 절벽.
본 테스트 = 사전등록 요건 그대로: (1) 미검증(λ=0) = 중립 1.0× (2) 검증 시 brain 단조
(3) 절벽 없음 (4) clip 범위 (5) 중립 기준점 (6) 현 표본(n=78) 구간 = 거의 중립.
stats 주입으로 파일 IO 없이 순수 함수 검증.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.vams.engine import (  # noqa: E402
    KELLY_MULT_MAX,
    KELLY_MULT_MIN,
    _apply_fractional_kelly,
)

BASE = 1_000_000.0
BRAINS = (30, 40, 50, 57, 60, 65, 80, 90)


def test_unvalidated_is_neutral():
    """λ=0 (n=0) → 전 brain 에서 mult=1.0 (미검증 점수가 사이징 지배 못 함 — RULE 7 #2)."""
    for bs in BRAINS:
        assert _apply_fractional_kelly(BASE, bs, stats=(0, 1.2)) == BASE


def test_monotone_and_not_degenerate_when_validated():
    """λ=1 (n=252) → brain 에 단조 증가 + 상수 아님 (옛 degeneracy 제거 확인)."""
    outs = [_apply_fractional_kelly(BASE, bs, stats=(252, 1.2)) for bs in BRAINS]
    assert all(b >= a for a, b in zip(outs, outs[1:])), outs
    assert len({round(o) for o in outs}) > 1, "flat = degenerate 재발"


def test_no_cliff_at_low_brain():
    """brain 40 이 0 으로 추락하지 않고 (옛 float epsilon 절벽), 50 과 연속."""
    a = _apply_fractional_kelly(BASE, 40, stats=(252, 1.2))
    c = _apply_fractional_kelly(BASE, 50, stats=(252, 1.2))
    assert a >= BASE * KELLY_MULT_MIN
    assert abs(a - c) / BASE < 0.25


def test_clip_bounds():
    """극단 입력에서도 mult ∈ [0.6, 1.2] (D3)."""
    lo = _apply_fractional_kelly(BASE, 0, stats=(252, 5.0))
    hi = _apply_fractional_kelly(BASE, 100, stats=(252, 5.0))
    assert lo >= BASE * KELLY_MULT_MIN - 1e-6
    assert hi <= BASE * KELLY_MULT_MAX + 1e-6


def test_neutral_reference_brain60():
    """중립 기준점 brain 60 → mult=1.0."""
    assert abs(_apply_fractional_kelly(BASE, 60, stats=(252, 1.2)) - BASE) < 1e-6


def test_current_sample_size_stays_gentle():
    """현 exit_log 규모(n=78, λ≈0.31) → brain 90 도 중립 근처 (사전등록 '미검증 거의 중립')."""
    out = _apply_fractional_kelly(BASE, 90, stats=(78, 1.2))
    assert 1.0 <= out / BASE < 1.05


def test_invalid_brain_returns_neutral():
    assert _apply_fractional_kelly(BASE, None, stats=(252, 1.2)) == BASE  # type: ignore[arg-type]


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                fails += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if fails else 0)


def test_kelly_n_comes_from_ledger_not_raw_exit_log(tmp_path, monkeypatch):
    """🚨 n 은 정본 원장(trade_ledger)에서 와야 한다 — raw exit_log 는 유령 매도를 담는다.

    2026-08-18 실측: `exit_log.jsonl` 82행 중 **59행이 유령**(dev-mode 사이클 잔재,
    7/20 감사 P0). 같은 종목·같은 날 같은 고점으로 8행이 찍힌 경우까지 있었다.
    그대로 세면 λ = n/252 가 0.091 → 0.325 로 부풀어, **미검증 brain 점수에 실제
    실적의 3.5배 사이징 권한**을 준다. 방향이 안전한 쪽이 아니라 위험한 쪽이다.

    이 테스트는 "유령이 n 을 부풀리지 않는다" 만 고정한다 — 산식은 건드리지 않는다.
    """
    from api.vams import engine as E

    # 실제 청산 1건 + 같은 (종목,날짜) 유령 5건
    history = [
        {"date": "2026-06-01", "type": "BUY", "ticker": "000001", "quantity": 10, "price": 1000},
        {"date": "2026-06-10", "type": "SELL", "ticker": "000001", "quantity": 10,
         "price": 900, "pnl": -1000},
    ] + [{"date": "2026-06-10", "type": "SELL", "ticker": "000001", "quantity": 10,
          "price": 900, "pnl": -1000} for _ in range(5)]

    monkeypatch.setattr(E, "load_history", lambda: history)
    monkeypatch.setattr(E, "_kelly_window_start", lambda: "2026-05-17")
    monkeypatch.setattr(E, "DATA_DIR", str(tmp_path))   # exit_log 부재 → b=default

    n, b = E._kelly_realized_stats()
    assert n == 1, f"유령 5건이 n 에 섞였다: n={n} (정본 1건이어야 한다)"
    assert b == E.KELLY_B_DEFAULT


def test_kelly_lambda_denominator_is_a_scale_not_a_retired_gate():
    """252 는 여기서 **스케일 분모**다 — 폐기된 IC 게이트(§7-1)와 동작이 다르다.

    값 변경 = RULE 7 쿼터 소모라 재등록 대상. 이 테스트는 값이 조용히 바뀌는 것을 막는다.
    """
    from api.vams import engine as E

    assert E.KELLY_LAMBDA_N_FULL == 252, "분모 변경은 재등록 대상 (PREREG_KELLY_FIX_2026_08_02)"
    # 게이트가 아니라 연속 스케일 — 도달 전에도 0 이 아니라 비례해서 작동한다
    base = 1_000_000
    lo = E._apply_fractional_kelly(base, 90, stats=(20, 1.2))
    hi = E._apply_fractional_kelly(base, 90, stats=(200, 1.2))
    assert base < lo < hi, "n 증가에 따라 점증해야 한다(게이트식 계단 아님)"


def test_kelly_stats_cache_invalidates_on_ledger_change(tmp_path, monkeypatch):
    """🚨 캐시는 원장이 바뀌면 반드시 풀려야 한다 — 안 풀리면 매도 후에도 옛 n 을 쓴다.

    캐시를 넣은 이유 = 정본 전환으로 이 함수가 portfolio.json(3.5MB)까지 읽게 됐고,
    호출부가 `execute_buy` 라 매수 후보마다 돈다 (실측 193.5ms/회 → 후보 5,000이면 967초).
    속도를 얻자고 신선도를 잃으면 안 되므로 mtime 키로 무효화한다.
    """
    from api.vams import engine as E

    hist = [{"date": "2026-06-01", "type": "BUY", "ticker": "000001", "quantity": 10, "price": 1000},
            {"date": "2026-06-10", "type": "SELL", "ticker": "000001", "quantity": 10,
             "price": 900, "pnl": -1000}]
    state = {"h": hist}
    monkeypatch.setattr(E, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(E, "load_history", lambda: state["h"])
    monkeypatch.setattr(E, "_kelly_window_start", lambda: "2026-05-17")
    E._KELLY_CACHE["key"] = None                      # 테스트 격리
    (tmp_path / "history.json").write_text("{}", encoding="utf-8")

    assert E._kelly_realized_stats()[0] == 1

    # 청산 1건 추가 + mtime 갱신 → 캐시가 풀려 2가 나와야 한다
    state["h"] = hist + [
        {"date": "2026-06-11", "type": "BUY", "ticker": "000002", "quantity": 5, "price": 2000},
        {"date": "2026-06-12", "type": "SELL", "ticker": "000002", "quantity": 5,
         "price": 2200, "pnl": 1000}]
    (tmp_path / "history.json").write_text('{"x":1}', encoding="utf-8")

    assert E._kelly_realized_stats()[0] == 2, "원장이 바뀌었는데 캐시가 옛 n 을 내놓았다"
