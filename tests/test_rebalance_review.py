# -*- coding: utf-8 -*-
"""드리프트 점검 배선 (2026-08-07).

사고: `quarterly_rebalance` 가 8/2 사전등록·승인 후 **프로덕션 소비자 0곳**이었다.
테스트만 import 했다. 목표비중(중용 3층)은 매일 정상 산출되는데 아무도 쓰지 않았다.

실측 발견 — 이 배선이 없어서 아무도 못 보던 그림:
  FX 헷지 ETF 1종이 총자산 **28.9%**(개별 주식 최대 F&F 9.7% 의 3배).

계약: ① FX 헷지 리저브를 비중에 **반드시 포함**(holdings 배열 밖이라 빼면 29%가 증발)
② 목표비중 조회 실패해도 현재 배분은 남긴다 ③ 표시값 전용·자동 매매 0·brain 미투입
④ 봉인 등급(공개 발행 금지) ⑤ 분기 점검월 표기.
"""
import json

import api.portfolio.rebalance_review as RR


def _pf(holdings=None, fx_krw=None, total=None, cash=0):
    hs = holdings or []
    v = {"holdings": hs, "cash": cash}
    if fx_krw:
        v["fx_hedge_reserve"] = {"ticker": "455030", "name": "KODEX 미국달러SOFR",
                                 "current_krw": fx_krw, "return_pct": -6.49}
    eq = sum((h.get("current_price") or 0) * (h.get("quantity") or 0) for h in hs)
    v["total_asset"] = total if total is not None else eq + (fx_krw or 0) + cash
    return {"vams": v}


def _h(tk, price, qty):
    return {"ticker": tk, "current_price": price, "quantity": qty}


# ── FX 헷지가 그림에서 사라지지 않는다 ───────────────────────────────

def test_fx_hedge_included_in_weights():
    """🚨 핵심 — holdings 배열 밖 필드라 빼면 총액의 29%가 증발한다(실측 사고)."""
    pf = _pf([_h("000001", 1000, 100)], fx_krw=300_000)  # 주식 10만 + 헷지 30만
    w, total, detail = RR.current_weights(pf)
    assert total == 400_000
    assert abs(w["455030"] - 0.75) < 1e-9
    assert detail["fx_hedge"]["krw"] == 300_000


def test_weights_sum_excludes_cash():
    """현금은 재분배 대상이 아니라 잔여 — 비중 합에 넣지 않는다."""
    pf = _pf([_h("000001", 1000, 100)], cash=100_000)
    w, total, _ = RR.current_weights(pf)
    assert total == 200_000
    assert abs(sum(w.values()) - 0.5) < 1e-9


def test_empty_portfolio_safe():
    w, total, _ = RR.current_weights({"vams": {}})
    assert w == {} and total == 0.0


# ── 목표비중 조회 실패해도 현재 배분은 남는다 ────────────────────────

def test_targets_unavailable_still_records_allocation(monkeypatch, tmp_path):
    """조회 실패가 관측 전체를 죽이면, 아무도 못 보던 상태로 되돌아간다."""
    monkeypatch.setattr(RR, "OUT_PATH", str(tmp_path / "o.json"))
    monkeypatch.setattr(RR, "TRAIL_PATH", str(tmp_path / "t.jsonl"))
    monkeypatch.setattr(RR, "_fetch_targets", lambda: ({}, "자격 미설정"))
    d = RR.build(_pf([_h("000001", 1000, 100)], fx_krw=300_000))
    assert d["status"] == "targets_unavailable"
    assert d["total_value_krw"] == 400_000
    assert d["current_weights"]["455030"] == 0.75


def test_ok_path_produces_actions(monkeypatch, tmp_path):
    monkeypatch.setattr(RR, "OUT_PATH", str(tmp_path / "o.json"))
    monkeypatch.setattr(RR, "TRAIL_PATH", str(tmp_path / "t.jsonl"))
    monkeypatch.setattr(RR, "_fetch_targets", lambda: ({"000001": 0.10}, None))
    # 000001 이 50% 인데 목표 10% → 큰 초과 드리프트
    d = RR.build(_pf([_h("000001", 1000, 5000)], fx_krw=5_000_000))
    assert d["status"] == "ok"
    assert any(a["ticker"] == "000001" and a["side"] == "sell" for a in d["actions"])


def test_untargeted_holdings_land_in_review(monkeypatch, tmp_path):
    """FX 헷지·미장은 중용 목표(KR 주식)에 없다 — 수동 검토로 드러나는 것이 정상."""
    monkeypatch.setattr(RR, "OUT_PATH", str(tmp_path / "o.json"))
    monkeypatch.setattr(RR, "TRAIL_PATH", str(tmp_path / "t.jsonl"))
    monkeypatch.setattr(RR, "_fetch_targets", lambda: ({"000001": 0.5}, None))
    d = RR.build(_pf([_h("000001", 1000, 100), _h("GOOGL", 500_000, 1)], fx_krw=300_000))
    kinds = {r["ticker"]: r["kind"] for r in d["review_detail"]}
    assert kinds.get("455030") == "fx_hedge"
    assert kinds.get("GOOGL") == "us"


# ── 등록 계약 ────────────────────────────────────────────────────────

def test_display_only_contract(monkeypatch, tmp_path):
    """🚨 표시값 전용 — 자동 매매 0, brain 미투입(중용 자기참조 차단)."""
    monkeypatch.setattr(RR, "OUT_PATH", str(tmp_path / "o.json"))
    monkeypatch.setattr(RR, "TRAIL_PATH", str(tmp_path / "t.jsonl"))
    monkeypatch.setattr(RR, "_fetch_targets", lambda: ({"000001": 0.5}, None))
    d = RR.build(_pf([_h("000001", 1000, 100)]))
    assert d["auto_trade"] is False and d["brain_used"] is False


def test_brain_score_never_read():
    """docstring 의 '미투입' 언급은 허용 — 실제 **읽기**가 없어야 한다."""
    import inspect
    import re
    src = inspect.getsource(RR)
    assert not re.search(r"""get\(\s*["']brain_score""", src)
    assert not re.search(r"""\[\s*["']brain_score""", src)


def test_sealed_output_not_committed():
    """🚨 목표비중 파생물이라 동일 봉인 등급 — gitignore + 업로드 목록이 유일한 전달 경로."""
    import os
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(repo, ".gitignore"), encoding="utf-8") as f:
        assert "/data/rebalance_review.json" in f.read()
    with open(os.path.join(repo, "scripts/upload_operator_data_to_supabase.py"), encoding="utf-8") as f:
        assert "_operator/rebalance_review.json" in f.read()


def test_wired_into_workflow():
    """8/2 승인 후 5일간 소비자 0 이었던 것이 사고다 — 배선 존재를 고정한다."""
    import os
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(repo, ".github/workflows/moderation_portfolio.yml"), encoding="utf-8") as f:
        assert "api.portfolio.rebalance_review" in f.read()


def test_review_month_flag(monkeypatch, tmp_path):
    monkeypatch.setattr(RR, "OUT_PATH", str(tmp_path / "o.json"))
    monkeypatch.setattr(RR, "TRAIL_PATH", str(tmp_path / "t.jsonl"))
    monkeypatch.setattr(RR, "_fetch_targets", lambda: ({}, "x"))
    d = RR.build(_pf([_h("000001", 1000, 100)]))
    assert d["is_review_month"] == (int(d["as_of"][5:7]) in (1, 4, 7, 10))
    assert json.dumps(d, ensure_ascii=False)
