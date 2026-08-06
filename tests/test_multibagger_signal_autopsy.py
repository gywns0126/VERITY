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
