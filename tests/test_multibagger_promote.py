"""상승 신호 승격 계약 — PREREG_MULTIBAGGER_UPSIDE_FUNNEL_2026_08_22 (PM 지시).

배경: alert>=2 인 78종목이 유니버스 후보(25)·운영풀(38) 어디에도 없었다(교집합 **0**).
신호가 켜져도 구조적으로 매수 후보가 못 되는 상태였고, 그 입구를 연다.

🚨 이 배선의 두 위험을 고정한다:
  ① **얇은 레코드 유입** — 워치 레코드는 7필드, 스캔 레코드는 55필드다. 얇은 것을 넣으면
     하류가 전부 결측으로 채점해 조용히 쓰레기가 된다("채워진 조인이 더 위험" 클래스).
  ② **상한 없는 유입** — 78 전부면 유니버스가 4배가 되어 런타임 예산(60분 타임아웃 이력)을 깬다.

🚨 승격 대상 자체가 위험 구간이라는 사실도 코드가 기억해야 한다 — 2026-08-21 전향 검정에서
상방에 유리한 꼬리(하위 20%)가 90% 손실 확률이 가장 높은 분위였다. 그래서 `promoted_by`
태그를 필수로 고정한다: 성적을 분리 집계할 수 없으면 이 결정을 나중에 평가할 수 없다.
"""
import json

import pytest

from api.intelligence import multibagger_watch as mw


def _row(ticker, alert, fired=("revenue_acceleration",)):
    return {"watch_date": "2026-08-22", "ticker": ticker, "name": f"종목{ticker}",
            "market_cap": 1_000_000_000, "alert_count": alert,
            "signals": {k: {"triggered": k in fired, "score": 80, "reason": "테스트"}
                        for k in ("revenue_acceleration", "operating_leverage",
                                  "category_leader", "hold_pnl_threshold")}}


def _full(ticker):
    return {"ticker": ticker, "name": f"종목{ticker}", "currency": "KRW",
            "market_cap": 1_000_000_000, "price": 1000.0, "per": 10.0,
            "pbr": 1.0, "safety_score": 50, "sector": "Industrials"}


@pytest.fixture
def emit(tmp_path, monkeypatch):
    p = tmp_path / "promote.json"
    monkeypatch.setattr(mw, "_PROMOTE_PATH", str(p))

    def run(rows, stocks):
        mw._emit_promote(rows, stocks)
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return run


# ── 🚨 위험 ① 얇은 레코드 ───────────────────────────────────────

def test_thin_record_is_never_promoted(emit):
    """전체 스캔 레코드가 없으면 **넣지 않는다.** 얇은 대체 금지."""
    rows = [_row("000001", 3), _row("000002", 2)]
    out = emit(rows, [])          # 원본 스톡 0건
    assert out["promoted_n"] == 0, "전체 레코드 없이 승격됐다 — 하류가 결측으로 채점한다"
    assert out["dropped_no_full_record"] == 2
    assert out["candidates"] == []


def test_promoted_record_carries_full_fields(emit):
    rows = [_row("000001", 3)]
    out = emit(rows, [_full("000001")])
    c = out["candidates"][0]
    for f in ("currency", "price", "per", "pbr", "safety_score", "sector"):
        assert f in c, f"승격 레코드에 {f} 가 없다 — 원본 필드를 그대로 실어야 한다"


# ── 🚨 위험 ② 상한 ─────────────────────────────────────────────

def test_cap_is_enforced(emit):
    rows = [_row(f"{i:06d}", 2) for i in range(1, 60)]
    out = emit(rows, [_full(f"{i:06d}") for i in range(1, 60)])
    assert out["promoted_n"] <= mw.PROMOTE_CAP
    assert out["eligible_n"] == 59, "🚨 분모(대상 전체)를 신고해야 상한이 무엇을 잘랐는지 보인다"


def test_higher_alert_wins_under_cap(emit):
    rows = [_row(f"{i:06d}", 2) for i in range(1, 40)] + [_row("999999", 3)]
    out = emit(rows, [_full(f"{i:06d}") for i in range(1, 40)] + [_full("999999")])
    assert out["candidates"][0]["ticker"] == "999999", "alert 높은 종목이 상한에 밀렸다"


# ── 🚨 사후 분리 집계 가능성 ────────────────────────────────────

def test_promoted_by_tag_is_mandatory(emit):
    """태그가 없으면 이 결정의 성적을 영영 분리할 수 없다."""
    out = emit([_row("000001", 3, fired=("revenue_acceleration", "operating_leverage"))],
               [_full("000001")])
    tag = out["candidates"][0].get("promoted_by")
    assert tag, "promoted_by 태그가 사라졌다"
    assert tag["source"] == "multibagger"
    assert tag["alert_count"] == 3
    assert set(tag["fired"]) == {"revenue_acceleration", "operating_leverage"}
    assert tag.get("basis"), "근거 등록문이 기록되지 않았다"


def test_denominator_is_reported(emit):
    """RULE 13 — 승격 수만 보면 무엇을 잘랐는지 모른다."""
    out = emit([_row("000001", 3), _row("000002", 1)], [_full("000001"), _full("000002")])
    for k in ("watch_n", "eligible_n", "cap", "promoted_n", "dropped_no_full_record"):
        assert k in out, f"_meta.{k} 누락"
    assert out["watch_n"] == 2 and out["eligible_n"] == 1, "alert<2 가 대상에 섞였다"


def test_below_threshold_is_not_promoted(emit):
    out = emit([_row("000001", 1)], [_full("000001")])
    assert out["promoted_n"] == 0
