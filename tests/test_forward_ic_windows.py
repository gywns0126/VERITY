"""장기 forward IC 윈도(63/126, fundamental 분기) 로깅 — exact_horizon + backward-compat 가드.

2026-06-09 (537f4442 follow-up). 7일 일간 IC 가 분기 reporting-lag fundamental 에 부적합 →
63/126 forward 윈도 추가. 핵심 불변식:
  1. exact_horizon=True 는 정확히 forward_days 후 스냅샷만 사용 (라벨오염 방지).
  2. history < forward_days 면 sample 0 (저장 게이트가 빈 entry 차단).
  3. factor_decay(None) 은 단기윈도(≤30)만 — 장기윈도가 기존 decay 분석 오염 금지.
"""
from api.quant.alpha.alpha_scanner import compute_factor_ic
import api.quant.alpha.factor_decay as fd


def _mk_snaps(n: int, n_stocks: int = 6):
    snaps = []
    for d in range(n):
        snaps.append({
            "_date": f"2026-01-{d + 1:02d}",
            "recommendations": [
                {"ticker": f"T{k}", "price": 100 + d + k,
                 "multi_factor": {"factor_breakdown": {"fundamental": k}}}
                for k in range(n_stocks)
            ],
        })
    return snaps


def test_exact_horizon_uses_only_full_horizon_pairs():
    # 10 스냅샷, forward=3 → full horizon = i 0..6 (7개), truncated tail(i=7,8) 제외
    snaps = _mk_snaps(10)
    exact = compute_factor_ic(snaps, "fundamental", forward_days=3, exact_horizon=True)
    trunc = compute_factor_ic(snaps, "fundamental", forward_days=3, exact_horizon=False)
    assert exact["sample_count"] == 7
    assert trunc["sample_count"] == 9  # truncated tail 포함 (기존 동작)


def test_exact_horizon_insufficient_history_yields_zero():
    # history(10) < forward_days(63) → exact 는 sample 0 (라벨오염 0)
    snaps = _mk_snaps(10)
    r = compute_factor_ic(snaps, "fundamental", forward_days=63, exact_horizon=True)
    # 빈 ic_series 경로는 sample_count 키가 없을 수 있음 (.get 로 0 처리 — save 게이트와 동일)
    assert r.get("sample_count", 0) == 0
    # non-exact 는 truncate 해 garbage 를 만든다 (이 fix 가 막는 대상)
    rb = compute_factor_ic(snaps, "fundamental", forward_days=63, exact_horizon=False)
    assert rb.get("sample_count", 0) > 0


def test_factor_decay_none_excludes_long_windows(monkeypatch):
    orig = fd._load_ic_history
    base = orig()
    if not base:
        return  # history 없으면 skip (CI 환경)
    long_entry = dict(base[-1])
    long_entry["forward_days"] = 63

    monkeypatch.setattr(fd, "_load_ic_history", lambda: base + [long_entry] * 20)
    none_days = fd.analyze_factor_decay().get("history_days")
    f63_days = fd.analyze_factor_decay(forward_days=63).get("history_days")
    # None = 단기(≤30)만 → 주입한 63d 20개 제외
    assert none_days == len([h for h in base if h.get("forward_days", 7) <= 30])
    assert f63_days == 20
