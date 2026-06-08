"""factor_decay 팩터 유형별 min_history (52c8222b, 2026-06-08 Perplexity NQ1)."""
from api.quant.alpha import factor_decay as fd


def test_min_samples_by_type():
    assert fd._min_samples_for("fundamental") == 21
    assert fd._min_samples_for("quality") == 21
    assert fd._min_samples_for("safety_score") == 21
    assert fd._min_samples_for("consensus") == 21
    assert fd._min_samples_for("momentum") == 5
    assert fd._min_samples_for("mean_reversion") == 5
    assert fd._min_samples_for("technical") == 5
    assert fd._min_samples_for("unknown_xyz") == 5  # 기본=price(미freeze)


def _hist(n, factors):
    return [{"forward_days": 7, "factors": {f: {"ic_mean": 0.02, "icir": 0.4} for f in factors}}
            for _ in range(n)]


def test_fundamental_insufficient_below_21(monkeypatch):
    # 10 obs: price(momentum)=분류됨, fundamental=INSUFFICIENT (21 미달, 조기 분류 차단)
    monkeypatch.setattr(fd, "_load_ic_history", lambda: _hist(10, ["momentum", "fundamental"]))
    r = fd.analyze_factor_decay(min_history_days=7)
    assert r["status"] == "ok"
    assert r["factors"]["fundamental"]["status"] == "INSUFFICIENT"
    assert r["factors"]["fundamental"]["factor_type"] == "fundamental"
    assert r["factors"]["momentum"]["status"] != "INSUFFICIENT"  # price 는 5만 넘으면 분류


def test_fundamental_classified_above_21(monkeypatch):
    monkeypatch.setattr(fd, "_load_ic_history", lambda: _hist(25, ["fundamental"]))
    r = fd.analyze_factor_decay(min_history_days=7)
    assert r["factors"]["fundamental"]["status"] != "INSUFFICIENT"
