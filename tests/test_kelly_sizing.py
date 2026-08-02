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
    """현 exit_log 규모(n=78, λ≈0.31) → brain 90 도 중립 근처 (사전등록 'N<252 거의 중립')."""
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
