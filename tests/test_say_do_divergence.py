"""say_do_divergence 관측 로거 — 부호/괴리/dedupe 로직 검증 (네트워크 없이 mock)."""
import json

from api.observability import say_do_divergence as sd


def test_opinion_sign():
    assert sd._opinion_sign("매수") == 1
    assert sd._opinion_sign("강력매수") == 1
    assert sd._opinion_sign("매도") == -1
    assert sd._opinion_sign("비중축소") == -1
    assert sd._opinion_sign("중립") == 0
    assert sd._opinion_sign("보유") == 0
    assert sd._opinion_sign(None) == 0


def test_say_sign_combines():
    assert sd._say_sign({"report_sign": 1, "consensus_sign": 1}) == 1
    assert sd._say_sign({"report_sign": -1, "consensus_sign": -1}) == -1
    # 상충 = 0
    assert sd._say_sign({"report_sign": 1, "consensus_sign": -1}) == 0
    # 결손 = 0
    assert sd._say_sign({}) == 0
    assert sd._say_sign({"report_sign": 1}) == 1


def test_do_signal_sum_and_sign():
    panel = [
        {"date": "2026-06-10", "foreign_net": -100, "inst_net": -50},
        {"date": "2026-06-11", "foreign_net": -200, "inst_net": 10},
    ]
    do = sd._do_signal(panel, lookback=5)
    assert do["foreign_net_sum"] == -300
    assert do["inst_net_sum"] == -40
    assert do["smart_net_sum"] == -340
    assert do["do_sign"] == -1
    assert do["days"] == 2


def test_do_signal_empty():
    do = sd._do_signal([], lookback=5)
    assert do["do_sign"] == 0
    assert do["days"] == 0
    assert do["smart_net_sum"] is None


def test_do_signal_lookback_truncates():
    panel = [{"date": f"2026-06-{d:02d}", "foreign_net": 1, "inst_net": 0} for d in range(1, 11)]
    do = sd._do_signal(panel, lookback=3)
    assert do["days"] == 3
    assert do["foreign_net_sum"] == 3  # 마지막 3일만


def test_divergence_say_bull_do_sell(tmp_path, monkeypatch):
    # 말=강세(매수), 행동=순매도 → divergence True
    monkeypatch.setattr(sd, "REPORT_PATH", str(tmp_path / "rep.json"))
    monkeypatch.setattr(sd, "CONSENSUS_PATH", str(tmp_path / "cons.json"))
    (tmp_path / "rep.json").write_text(json.dumps({
        "summaries": {"005930": {"signal_direction": "bullish", "dominant_opinion": "매수",
                                  "analyst_sentiment_score": 80}}
    }), encoding="utf-8")
    (tmp_path / "cons.json").write_text(json.dumps({
        "stocks": [{"ticker": "005930", "investment_opinion": "매수", "upside_pct": 30}]
    }), encoding="utf-8")

    def fake_fetch(code, sess=None):
        return [{"date": "2026-06-11", "foreign_net": -500, "inst_net": -300}]

    out = str(tmp_path / "saydo.jsonl")
    res = sd.run_say_do_observation(delay=0, lookback=5, path=out, _fetch=fake_fetch)
    assert res["logged"] is True
    assert res["divergences"] == 1
    rec = json.loads(open(out, encoding="utf-8").read().splitlines()[0])
    per = rec["per_ticker"]["005930"]
    assert per["say_sign"] == 1 and per["do_sign"] == -1 and per["divergence"] is True


def test_no_divergence_when_aligned(tmp_path, monkeypatch):
    # 말=강세, 행동=순매수 → 정합(divergence False)
    monkeypatch.setattr(sd, "REPORT_PATH", str(tmp_path / "rep.json"))
    monkeypatch.setattr(sd, "CONSENSUS_PATH", str(tmp_path / "cons.json"))
    (tmp_path / "rep.json").write_text(json.dumps({
        "summaries": {"005930": {"signal_direction": "bullish"}}
    }), encoding="utf-8")
    (tmp_path / "cons.json").write_text(json.dumps({"stocks": []}), encoding="utf-8")

    def fake_fetch(code, sess=None):
        return [{"date": "2026-06-11", "foreign_net": 500, "inst_net": 300}]

    out = str(tmp_path / "saydo.jsonl")
    res = sd.run_say_do_observation(delay=0, path=out, _fetch=fake_fetch)
    assert res["divergences"] == 0
    per = json.loads(open(out, encoding="utf-8").read().splitlines()[0])["per_ticker"]["005930"]
    assert per["divergence"] is False


def test_us_ticker_excluded(tmp_path, monkeypatch):
    # 알파벳 ticker(US)는 say 신호에서 제외
    monkeypatch.setattr(sd, "REPORT_PATH", str(tmp_path / "rep.json"))
    monkeypatch.setattr(sd, "CONSENSUS_PATH", str(tmp_path / "cons.json"))
    (tmp_path / "rep.json").write_text(json.dumps({
        "summaries": {"AAPL": {"signal_direction": "bullish"}, "005930": {"signal_direction": "bearish"}}
    }), encoding="utf-8")
    (tmp_path / "cons.json").write_text(json.dumps({"stocks": []}), encoding="utf-8")
    say = sd._say_signals()
    assert "AAPL" not in say
    assert "005930" in say


def test_date_dedupe(tmp_path, monkeypatch):
    monkeypatch.setattr(sd, "REPORT_PATH", str(tmp_path / "rep.json"))
    monkeypatch.setattr(sd, "CONSENSUS_PATH", str(tmp_path / "cons.json"))
    (tmp_path / "rep.json").write_text(json.dumps({
        "summaries": {"005930": {"signal_direction": "bullish"}}
    }), encoding="utf-8")
    (tmp_path / "cons.json").write_text(json.dumps({"stocks": []}), encoding="utf-8")

    def fake_fetch(code, sess=None):
        return [{"date": "2026-06-11", "foreign_net": 1, "inst_net": 1}]

    out = str(tmp_path / "saydo.jsonl")
    sd.run_say_do_observation(delay=0, path=out, _fetch=fake_fetch)
    sd.run_say_do_observation(delay=0, path=out, _fetch=fake_fetch)  # 같은 날 두 번
    lines = [l for l in open(out, encoding="utf-8").read().splitlines() if l.strip()]
    assert len(lines) == 1  # date dedupe — 1줄만
