"""멀티배거 선별 리스트 계약 — PM 지시 2026-08-22 ("따로 리스트로 만들어줘").

🚨 이 리스트의 존재 이유 = **분리 집계**. 멀티배거로 들어온 종목이 일반 후보와 섞이면
이 결정(상승 신호 승격)의 성적을 영영 못 가린다. 사전등록이 `promoted_by` 태그를 필수로
건 이유이고, 이 빌더가 그 태그를 실제로 쓴다.

고정 대상: ① 태그 없는 종목이 섞이지 않는가 ② 세 갈래(채점/대기/상한밀림)가 분리되는가
③ 분모가 신고되는가 ④ 미채점을 0 으로 채우지 않는가(결측 ≠ 실측).
"""
import json

import pytest

from api.builders import multibagger_picks_builder as pb


@pytest.fixture
def build(tmp_path, monkeypatch):
    def run(watch_rows, promoted_tickers=(), scored=()):
        w = tmp_path / "watch.jsonl"
        w.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in watch_rows),
                     encoding="utf-8")
        p = tmp_path / "promote.json"
        p.write_text(json.dumps({"candidates": [{"ticker": t} for t in promoted_tickers],
                                 "as_of": "x", "cap": 20, "dropped_no_full_record": 0}),
                     encoding="utf-8")
        f = tmp_path / "portfolio.json"
        f.write_text(json.dumps({"recommendations": list(scored)}), encoding="utf-8")
        monkeypatch.setattr(pb, "WATCH", str(w))
        monkeypatch.setattr(pb, "PROMOTE", str(p))
        monkeypatch.setattr(pb, "PORTFOLIO", str(f))
        return pb.build()
    return run


def _w(t, alert, fired=("revenue_acceleration",)):
    return {"watch_date": "2026-08-22", "ticker": t, "name": f"종목{t}",
            "market_cap": 1e9, "sector": "Industrials", "lynch_class": "FAST_GROWER",
            "alert_count": alert,
            "signals": {k: {"triggered": k in fired} for k in
                        ("revenue_acceleration", "operating_leverage", "category_leader")}}


def _scored(t, score, grade, tagged=True):
    r = {"ticker": t, "name": f"종목{t}", "price": 1000,
         "verity_brain": {"brain_score": score, "grade": grade}}
    if tagged:
        r["promoted_by"] = {"source": "multibagger", "alert_count": 3}
    return r


# ── 🚨 분리 집계의 핵심 ──────────────────────────────────────────

def test_untagged_stock_is_not_counted_as_ours(build):
    """태그 없는 종목이 우연히 같은 티커여도 **우리 성적이 아니다.**"""
    out = build([_w("000001", 3)], promoted_tickers=["000001"],
                scored=[_scored("000001", 70, "BUY", tagged=False)])
    assert out["_meta"]["scored_n"] == 0, "태그 없는 종목이 채점분으로 잡혔다"
    assert out["_meta"]["waiting_n"] == 1


def test_three_buckets_are_separated(build):
    """섞으면 '몇 개가 살아남았나' 를 못 센다."""
    out = build([_w("000001", 3), _w("000002", 2), _w("000003", 2)],
                promoted_tickers=["000001", "000002"],
                scored=[_scored("000001", 62, "BUY")])
    m = out["_meta"]
    assert m["scored_n"] == 1 and m["waiting_n"] == 1 and m["capped_out_n"] == 1
    assert {x["ticker"] for x in out["scored"]} == {"000001"}
    assert {x["ticker"] for x in out["promoted"]} == {"000002"}
    assert {x["ticker"] for x in out["watching"]} == {"000003"}


def test_denominator_is_reported(build):
    """RULE 13 — 목록만 보면 전수처럼 읽힌다."""
    out = build([_w("000001", 3), _w("000002", 1)])
    m = out["_meta"]
    for k in ("watch_n", "eligible_n", "promoted_n", "scored_n", "waiting_n", "capped_out_n"):
        assert k in m, f"_meta.{k} 누락"
    assert m["watch_n"] == 2 and m["eligible_n"] == 1, "alert<2 가 대상에 섞였다"


def test_unscored_is_none_not_zero(build):
    """🚨 결측과 실측은 다르다 — 미채점을 0 으로 채우면 '나쁜 점수' 로 읽힌다."""
    out = build([_w("000001", 3)], promoted_tickers=["000001"])
    r = out["promoted"][0]
    assert r["brain_score"] is None and r["grade"] is None


def test_grade_distribution_is_reported(build):
    out = build([_w("000001", 3), _w("000002", 2)],
                promoted_tickers=["000001", "000002"],
                scored=[_scored("000001", 62, "BUY"), _scored("000002", 50, "WATCH")])
    assert out["_meta"]["grade_dist"] == {"BUY": 1, "WATCH": 1}


def test_decision_use_is_false(build):
    """관측이지 매수 지시가 아니다 — 화면이 그대로 신고해야 한다."""
    out = build([_w("000001", 3)])
    assert out["_meta"]["decision_use"] is False


def test_fired_signals_are_carried(build):
    out = build([_w("000001", 3, fired=("revenue_acceleration", "category_leader"))])
    assert set(out["watching"][0]["fired"]) == {"revenue_acceleration", "category_leader"}


def test_missing_inputs_do_not_crash(build, tmp_path, monkeypatch):
    """워치가 없으면(신호 미산출) 빈 리스트를 내고 죽지 않는다."""
    monkeypatch.setattr(pb, "WATCH", str(tmp_path / "nope.jsonl"))
    monkeypatch.setattr(pb, "PROMOTE", str(tmp_path / "nope.json"))
    monkeypatch.setattr(pb, "PORTFOLIO", str(tmp_path / "nope.json"))
    out = pb.build()
    assert out["_meta"]["watch_n"] == 0 and out["scored"] == []
