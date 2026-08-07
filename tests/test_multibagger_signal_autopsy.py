# -*- coding: utf-8 -*-
"""텐배거 5신호 중 2종 사인 조사 결과 고정 (2026-08-06).

29,271 관측(2026-06-09~08-06) 내내 0회 발동한 두 신호의 사인:

  · industry_s_curve   = **미구현 스텁**. 기존 복구 계획("sector_trends 보강 후 활성")은
    전제가 틀렸다 — sector_trends 는 섹터 주가 등락률(1m/3m/6m)이고 Rogers S-curve 는
    산업 매출 5년 CAGR 를 요구한다. 대체 불가.
  · hold_pnl_threshold = **소비자 오류**. Lynch "꽃을 뽑지 마라"는 보유 포지션 규칙인데
    유일한 호출자가 미보유 유니버스 스캔이다. hold_days 0/29,271.

부수 결함: trail 이 {triggered, score} 만 저장해 죽은 신호와 정상 미발동이 구분되지
않았다 → reason 영속화.

🚨 이 테스트는 **신호를 살리지 않는다**. 사인을 고정해 조용히 잊히지 않게 한다.
   2026-09 active gate 전 PM 결정 필요(수집 착수 / 소비자 이전 / 폐기 / 게이트 연기).
"""
import json

from api.analyzers.multi_bagger_signals import (
    detect_hold_pnl_threshold,
    detect_industry_s_curve,
    evaluate_multi_bagger_signals,
)
from api.intelligence.multibagger_watch import build_watch


def test_industry_s_curve_is_unimplemented_stub():
    """구현되면 이 테스트가 깨진다 — 그때 사유 문구와 함께 갱신할 것."""
    r = detect_industry_s_curve({"ticker": "000001", "sector": "IT"}, {"sector_trends": {}})
    assert r["triggered"] is False
    assert "미구현" in r["reason"]


def test_industry_s_curve_stays_false_even_with_sector_trends():
    """🚨 sector_trends 를 줘도 발동하지 않는다 — 그게 대체 데이터가 아니라는 뜻."""
    pf = {"sector_trends": {"1m": {"top3_sectors": [{"name": "IT", "avg_change_pct": 9.9}]},
                            "6m": {"top3_sectors": [{"name": "IT", "avg_change_pct": 40.0}]}}}
    assert detect_industry_s_curve({"ticker": "000001", "sector": "IT"}, pf)["triggered"] is False


def test_hold_pnl_inapplicable_without_holding_context():
    """유니버스 스캔 레코드에는 hold_days 가 없다 — 구조상 발동 불가."""
    r = detect_hold_pnl_threshold({"ticker": "000001", "market_cap": 5e11})
    assert r["triggered"] is False
    assert "적용 불가" in r["reason"]


def test_hold_pnl_fires_when_given_holding_context():
    """규칙 자체는 살아 있다 — 보유 맥락만 주면 발동한다(소비자 이전 시 근거)."""
    r = detect_hold_pnl_threshold({"ticker": "000001", "hold_days": 200, "return_pct": 60.0})
    assert r["triggered"] is True


def test_hold_pnl_thresholds_unchanged():
    """임계(180일/+50%) 무변경 — 본 조사는 사인만 기록한다."""
    assert detect_hold_pnl_threshold({"hold_days": 179, "return_pct": 60.0})["triggered"] is False
    assert detect_hold_pnl_threshold({"hold_days": 200, "return_pct": 49.9})["triggered"] is False


def test_alert_count_excludes_dead_signals():
    """죽은 2종은 alert_count 를 부풀리지 않는다 — 5신호 라벨이지만 실효 3종."""
    out = evaluate_multi_bagger_signals({"ticker": "000001"}, {"recommendations": []})
    assert out["industry_s_curve"]["triggered"] is False
    assert out["hold_pnl_threshold"]["triggered"] is False
    assert out["alert_count"] == sum(
        1 for k in ("revenue_acceleration", "operating_leverage", "category_leader",
                    "industry_s_curve", "hold_pnl_threshold") if out[k]["triggered"])


def test_watch_row_persists_reason(monkeypatch):
    """🚨 사유가 trail 에 남아야 죽은 신호를 소스 안 읽고도 안다."""
    stock = {"ticker": "000001", "name": "테스트", "market_cap": 5e11,
             "sector": "IT", "currency": "KRW", "revenue_growth": 40.0}
    rows = build_watch([stock], as_of="2026-08-06")
    if not rows:                       # 신호 0 이면 focused list 에서 제외됨
        return
    sig = rows[0]["signals"]["industry_s_curve"]
    assert "reason" in sig and sig["reason"]
    assert json.dumps(rows[0], ensure_ascii=False)   # 직렬화 가능


# ── 소비자 이전: 보유 종목 축 (PM 승인 2026-08-06) ───────────────────

from api.intelligence.multibagger_watch import build_holding_flowers, run_watch  # noqa: E402


def _pf(holdings):
    return {"vams": {"holdings": holdings}}


def test_holding_axis_evaluates_hold_pnl():
    """소비자 이전 — 보유 종목에서 hold_pnl 이 실제로 평가된다."""
    rows = build_holding_flowers(
        _pf([{"ticker": "000001", "name": "T", "buy_date": "2025-01-01", "return_pct": 80.0}]),
        as_of="2026-08-07")
    sig = rows[0]["signals"]["hold_pnl_threshold"]
    assert rows[0]["source"] == "holding"
    assert sig["triggered"] is True and rows[0]["alert_count"] == 1


def test_holding_axis_not_yet_is_not_broken():
    """🚨 임계 미달은 '미충족' 이지 '적용 불가' 가 아니다 — 둘을 섞으면 사인 추적이 죽는다."""
    rows = build_holding_flowers(
        _pf([{"ticker": "000001", "buy_date": "2026-08-01", "return_pct": 5.0}]),
        as_of="2026-08-07")
    r = rows[0]["signals"]["hold_pnl_threshold"]
    assert r["triggered"] is False
    assert "미충족" in r["reason"] and "적용 불가" not in r["reason"]
    assert rows[0]["hold_days"] == 6


def test_zero_hold_days_is_a_value_not_missing():
    """🚨 당일 매수(0일)·수익률 0.0% 이 falsy 라 None 으로 무너지던 결함.

    실측 2026-08-07: 당일 매수 F&F 가 '적용 불가'로 기록됐다. 결측(모름)과 0(실측값)은 다르다.
    """
    rows = build_holding_flowers(
        _pf([{"ticker": "383220", "buy_date": "2026-08-07", "return_pct": 0.0}]),
        as_of="2026-08-07")
    r = rows[0]["signals"]["hold_pnl_threshold"]
    assert rows[0]["hold_days"] == 0
    assert "적용 불가" not in r["reason"] and "미충족" in r["reason"]


def test_unparseable_buy_date_holds_judgement():
    rows = build_holding_flowers(
        _pf([{"ticker": "000001", "buy_date": None, "return_pct": 60.0}]), as_of="2026-08-07")
    r = rows[0]["signals"]["hold_pnl_threshold"]
    assert rows[0]["hold_days"] is None
    assert "판정 보류" in r["reason"]


def test_holding_axis_only_evaluates_hold_pnl():
    """나머지 4신호는 평가하지 않는다 — 보유 레코드에 펀더멘털이 없어 전부 결손이 된다."""
    rows = build_holding_flowers(
        _pf([{"ticker": "000001", "buy_date": "2026-01-01", "return_pct": 10.0}]),
        as_of="2026-08-07")
    assert set(rows[0]["signals"]) == {"hold_pnl_threshold"}


def test_holding_axis_failure_does_not_kill_universe(monkeypatch, tmp_path):
    """보유 축이 죽어도 유니버스 축은 기록된다(관측이 funnel 을 죽이지 않는다)."""
    import api.intelligence.multibagger_watch as MW
    monkeypatch.setattr(MW, "build_holding_flowers",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    stock = {"ticker": "000001", "name": "T", "market_cap": 5e11,
             "sector": "IT", "currency": "KRW", "revenue_growth": 40.0}
    n = run_watch([stock], path=str(tmp_path / "w.jsonl"))
    assert n >= 0                      # 예외가 전파되지 않는다


def test_holding_rows_marked_for_split_analysis():
    rows = build_holding_flowers(
        _pf([{"ticker": "000001", "buy_date": "2026-01-01", "return_pct": 10.0}]),
        as_of="2026-08-07")
    assert rows[0]["source"] == "holding"


def test_two_axes_write_to_separate_files(tmp_path, monkeypatch):
    """🚨 유니버스와 보유는 스키마가 다르다 — 한 파일에 섞으면 소비자가 깨진다.

    실측: 처음 한 파일에 합쳤더니 기존 end-to-end 테스트가 즉시 KeyError('market_cap').
    """
    import api.intelligence.multibagger_watch as MW
    monkeypatch.setattr(MW, "build_holding_flowers", lambda *a, **k: [
        {"watch_date": "2026-08-07", "source": "holding", "ticker": "000002"}])
    uni, hold = tmp_path / "u.jsonl", tmp_path / "h.jsonl"
    stock = {"ticker": "000001", "name": "T", "market_cap": 5e11,
             "sector": "IT", "currency": "KRW", "revenue_growth": 40.0}
    MW.run_watch([stock], path=str(uni), hold_path=str(hold))
    assert hold.exists()
    for line in hold.read_text(encoding="utf-8").splitlines():
        assert json.loads(line)["source"] == "holding"
    if uni.exists():
        for line in uni.read_text(encoding="utf-8").splitlines():
            assert "market_cap" in json.loads(line)      # 유니버스 스키마 보존


def test_workflow_git_adds_new_trail():
    """RULE 4 — specific git add 패턴이라 신 파일 줄이 없으면 silent 손실."""
    import os
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(repo, ".github/workflows/universe_scan.yml"), encoding="utf-8") as f:
        yml = f.read()
    assert "git add data/metadata/multibagger_holdings.jsonl" in yml
