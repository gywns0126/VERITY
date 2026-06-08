"""multibagger_watch 테스트 — KR 소형주 텐버거 후보 WATCH (로깅 전용).

2026-06-09. 재사용(classify_lynch_kr + multi_bagger_signals) 배선 + 필터/로깅 검증.
"""
import json
import tempfile

from api.intelligence import multibagger_watch as MW


def _stock(ticker, mc, currency="KRW", **kw):
    base = {"ticker": ticker, "name": f"N{ticker}", "market_cap": mc, "currency": currency,
            "sector": kw.get("sector", "IT"), "revenue_growth": kw.get("rev", 5.0),
            "operating_margin": kw.get("opm", 10.0), "per": kw.get("per", 12.0),
            "pbr": kw.get("pbr", 1.2), "debt_ratio": kw.get("debt", 50.0)}
    base.update(kw)
    return base


def test_smallcap_filter_excludes_us_and_largecap():
    assert MW._is_kr_smallcap(_stock("A", 5e11)) is True              # KR 5000억 < 1조
    assert MW._is_kr_smallcap(_stock("B", 5e12)) is False             # KR 5조 (대형)
    assert MW._is_kr_smallcap(_stock("C", 5e11, currency="USD")) is False  # US 제외
    assert MW._is_kr_smallcap({"ticker": "D"}) is False               # market_cap 결손


def test_build_watch_focuses_fast_grower_or_signal():
    stocks = [
        _stock("FAST", 3e11, rev=25.0),   # Fast Grower (매출 25% ≥ 15) → watch 포함
        _stock("SLOW", 3e11, rev=1.0, pbr=2.0),  # 저성장·무신호 → 제외 가능
        _stock("BIG", 5e12, rev=30.0),    # 대형 → 제외 (소형 아님)
        _stock("USX", 3e11, rev=30.0, currency="USD"),  # US → 제외
    ]
    recs = MW.build_watch(stocks, as_of="2026-06-09")
    tickers = {r["ticker"] for r in recs}
    assert "FAST" in tickers          # Fast Grower 포함
    assert "BIG" not in tickers       # 대형 제외
    assert "USX" not in tickers       # US 제외
    # 레코드 구조
    fast = next(r for r in recs if r["ticker"] == "FAST")
    assert fast["lynch_class"] == "FAST_GROWER"
    assert fast["spec_version"] == "watch.v0"
    assert "signals" in fast and "alert_count" in fast


def test_log_watch_appends_jsonl():
    tmp = tempfile.mktemp(suffix=".jsonl")
    recs = [{"watch_date": "2026-06-09", "ticker": "T1", "lynch_class": "FAST_GROWER"}]
    n = MW.log_watch(recs, path=tmp)
    assert n == 1
    rows = [json.loads(l) for l in open(tmp, encoding="utf-8") if l.strip()]
    assert rows[0]["ticker"] == "T1"


def test_log_watch_empty_noop():
    tmp = tempfile.mktemp(suffix=".jsonl")
    assert MW.log_watch([], path=tmp) == 0


def test_run_watch_end_to_end():
    tmp = tempfile.mktemp(suffix=".jsonl")
    stocks = [_stock("FAST", 3e11, rev=25.0), _stock("BIG", 9e12, rev=30.0)]
    n = MW.run_watch(stocks, path=tmp)
    assert n >= 1  # 최소 FAST 1건
    rows = [json.loads(l) for l in open(tmp, encoding="utf-8") if l.strip()]
    assert all(r["spec_version"] == "watch.v0" for r in rows)
    assert all(float(r["market_cap"]) < MW.SMALLCAP_MAX_KRW for r in rows)  # 전부 소형주
