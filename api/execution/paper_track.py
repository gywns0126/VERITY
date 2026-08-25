# -*- coding: utf-8 -*-
"""paper_track — 자동매매 사전등록(PREREG_AUTO_EXECUTION_GATE_2026_08_03) 규칙의 가상 집행.

목적 (PM 2026-08-03 "페이퍼 트랙 ㄱㄱ"):
  VAMS 가 쌓는 trail 은 VAMS 자체 로직의 것 — 9월부터 실탄을 굴릴 규칙(aligned BUY 체계)의
  트랙레코드는 N=0 이었다. 이 모듈이 등록 규칙 E·S·X 를 **문자 그대로** 가상 1,000만원으로
  매 run 집행해, 8월 말 VAMS 게이트 판정 시점에 "실전 전략 자체의 예비 N" 이 함께 도착하게 한다.

원칙:
  · VAMS 상태 불간섭 (별도 장부·별도 상태 — Phase 0 trail 순수성 유지)
  · 등록 규칙에서 벗어나는 모든 간이화 = flags 로 정직 기록 (재등록 시 정제 입력)
  · 산식·임계 무변경. 실패가 파이프라인을 중단시키지 않는다.

등록 규칙 대응 (v0 간이화 명시):
  E1 신호        = display_verdict.final == "BUY" and aligned == True (KR 6자리만)
  E2 익일 집행    = 오늘 신호 → pending 주문 → **다음 run 의 가격으로 체결** (±2% 밴드 밖 = 취소).
                   진짜 익일 시가가 아니라 다음 run 시점 가격 — flag "e2_next_run_fill"
  E3 유동성      = 1개월 평균 거래량 × 현재가 ≥ 10억 — 20일 평균 거래대금의 근사, flag "e3_1m_proxy"
  E4 오염 제외    = name 오염(콤마)·red_flag critical·브레인 미채점
  E5 일 2건      = brain_score 상위 2건만
  S  사이징      = 종목당 min(position_guide, 3%) × 자본. 총노출 상한 = 중용 exposure
                   (private 조회 실패 시 그날 신규 진입 중단 — S1 종속성 준수, flag)
  X1 CAUTION 이하 강등 → 익일(다음 run) 청산 / X2 AVOID → 당일 즉시 / X3 종가 −10% → 익일 /
  X4 레코드 이탈 3거래일 → 청산
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

_KST = timezone(timedelta(hours=9))
INITIAL_CAPITAL = 10_000_000  # PM 2026-08-03 "가상매매 하게 1천만원"
STOP_PCT = 0.10               # 등록 X3
FILL_BAND = 0.02              # 등록 E2 ±2%
MIN_TRADING_VALUE = 1_000_000_000  # 등록 E3 10억
MAX_DAILY_ENTRIES = 2         # 등록 E5
PER_STOCK_CAP = 0.03          # 등록 S2 (position_guide 와 이중 상한)
MISSING_DAYS_EXIT = 3         # 등록 X4


def _now() -> datetime:
    return datetime.now(_KST)


def _load(path: str, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _append_ledger(path: str, event: Dict[str, Any]) -> None:
    event["ts"] = _now().isoformat(timespec="seconds")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _fetch_moderation_exposure() -> Optional[float]:
    """중용 layer3 exposure — private bucket 조회 (등록 S1 종속). 실패 = None (진입 중단)."""
    url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not key:
        return None
    try:
        req = urllib.request.Request(
            f"{url}/storage/v1/object/verity-reports/_operator/moderation_portfolio.json",
            headers={"apikey": key, "Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=15) as r:
            doc = json.loads(r.read().decode("utf-8", "replace"))
        exp = ((doc.get("layer3") or {}).get("exposure"))
        return float(exp) if exp is not None else None
    except Exception:
        return None


def _is_kr(r: Dict[str, Any]) -> bool:
    tk = str(r.get("ticker") or "")
    return len(tk) == 6 and tk.isdigit()


def _price(r: Optional[Dict[str, Any]]) -> Optional[float]:
    if not r:
        return None
    p = r.get("current_price")
    try:
        p = float(p)
        return p if p > 0 else None
    except (TypeError, ValueError):
        return None


def _live_quotes(tickers: List[str]) -> Dict[str, float]:
    """KR 티커 실시간 현재가 일괄 조회 (KIS cache_only — 토큰 신규 발급 0, RULE 1 정합).

    PM 승인 2026-08-26 "매매시 실시간 참고" — 체결가 충실도 배선. 🚨 원칙:
    **판정 입력(E/S/X 등록 규칙)은 run 스냅샷 그대로, 체결가만 실시간.**
    실패·토큰 부재 시 = 빈 dict → 호출부가 스냅샷 폴백 + fill_source 자기신고
    (체결 방식 변경은 측정 창 경계를 만들므로 체결 단위로 전후 분리 가능해야 한다).
    """
    out: Dict[str, float] = {}
    if not tickers:
        return out
    try:
        from api.trading.kis_broker import KISBroker
        b = KISBroker(cache_only=True)
        if not b.is_configured():
            return out
        for tk in dict.fromkeys(tickers):
            try:
                q = b.get_current_price(tk)
                p = float(q.get("stck_prpr") or 0)
                if p > 0:
                    out[tk] = p
            except Exception:
                continue
    except Exception:
        return out
    return out


def run_paper_track(analyzed: List[Dict[str, Any]], data_dir: str) -> Dict[str, Any]:
    """등록 규칙 가상 집행 1사이클. 반환 = portfolio["exec_paper"] 요약 (오퍼레이터 전용)."""
    state_path = os.path.join(data_dir, "exec_paper_state.json")
    ledger_path = os.path.join(data_dir, "exec_paper_trail.jsonl")
    today = _now().strftime("%Y-%m-%d")

    state = _load(state_path, None) or {
        "version": "v0", "initialized": today, "cash": float(INITIAL_CAPITAL),
        "positions": {}, "pending": [], "last_date": None, "trades": 0, "realized_pnl": 0.0,
    }
    flags: List[str] = ["e2_next_run_fill", "e3_1m_proxy", "fill_live_quote_20260826"]

    kr = [r for r in analyzed if _is_kr(r)]
    by_tk = {str(r.get("ticker")): r for r in kr}
    gate_live = any(isinstance(r.get("display_verdict"), dict) for r in kr)

    if state.get("last_date") == today:
        return _summary(state, by_tk, ["already_ran_today"] )
    if not gate_live:
        _append_ledger(ledger_path, {"type": "skip", "reason": "display_verdict_absent", "date": today})
        return _summary(state, by_tk, ["gate_not_live"])

    # ── 1) pending 체결 (E2: 이전 run 신호 → 이번 run 가격, ±2% 밴드) ──
    # 체결가 = 실시간 조회 우선(PM 8/26), 실패 시 run 스냅샷 폴백 — fill_source 자기신고.
    live_px = _live_quotes(
        [od["ticker"] for od in state.get("pending", [])]
        + list(state.get("positions", {}).keys())
    )
    still_pending: List[Dict[str, Any]] = []
    for od in state.get("pending", []):
        r = by_tk.get(od["ticker"])
        _pl = live_px.get(od["ticker"])
        px = _pl if _pl is not None else _price(r)
        fill_src = "live_quote" if _pl is not None else "run_snapshot"
        if px is None:
            od["missing_fills"] = od.get("missing_fills", 0) + 1
            if od["missing_fills"] <= 2:
                still_pending.append(od)
            else:
                _append_ledger(ledger_path, {"type": "cancel", "ticker": od["ticker"],
                                             "reason": "price_unavailable", "order": od})
            continue
        if od["side"] == "buy":
            band = abs(px / od["ref_price"] - 1.0) if od.get("ref_price") else 0.0
            if band > FILL_BAND:
                _append_ledger(ledger_path, {"type": "cancel", "ticker": od["ticker"],
                                             "reason": f"e2_band_{band:.3f}", "order": od})
                continue
            qty = int(od["alloc_krw"] // px)
            if qty <= 0 or state["cash"] < qty * px:
                _append_ledger(ledger_path, {"type": "cancel", "ticker": od["ticker"],
                                             "reason": "insufficient_alloc", "order": od})
                continue
            state["cash"] -= qty * px
            state["positions"][od["ticker"]] = {
                "qty": qty, "buy_price": px, "buy_date": today, "missing_days": 0,
                "signal_snapshot": od.get("signal_snapshot"), "fill_source": fill_src,
            }
            state["trades"] += 1
            _append_ledger(ledger_path, {"type": "fill_buy", "ticker": od["ticker"], "price": px,
                                         "qty": qty, "krw": qty * px, "fill_source": fill_src,
                                         "order": od})
        else:  # sell
            pos = state["positions"].pop(od["ticker"], None)
            if pos:
                proceeds = pos["qty"] * px
                pnl = (px - pos["buy_price"]) * pos["qty"]
                state["cash"] += proceeds
                state["realized_pnl"] += pnl
                state["trades"] += 1
                _append_ledger(ledger_path, {"type": "fill_sell", "ticker": od["ticker"], "price": px,
                                             "qty": pos["qty"], "pnl": round(pnl),
                                             "fill_source": fill_src, "reason": od.get("reason")})
    state["pending"] = still_pending

    # ── 2) 보유 청산 판정 (X 규칙) ──
    for tk, pos in list(state["positions"].items()):
        r = by_tk.get(tk)
        if r is None:  # X4 관측 사각
            pos["missing_days"] = pos.get("missing_days", 0) + 1
            if pos["missing_days"] >= MISSING_DAYS_EXIT:
                state["pending"].append({"side": "sell", "ticker": tk, "reason": "x4_coverage_lost",
                                         "created": today})
                _append_ledger(ledger_path, {"type": "exit_signal", "ticker": tk, "rule": "X4"})
            continue
        pos["missing_days"] = 0
        # 🚨 판정(X1~X3)은 run 스냅샷 가격 — 등록 규칙의 판정 입력을 바꾸지 않는다.
        #    실시간은 X2 즉시 청산의 **체결가**에만 쓴다 (fill_source 자기신고).
        px = _price(r)
        badge = str(r.get("recommendation") or "")
        if badge == "AVOID" and px:  # X2 즉시
            _fl = live_px.get(tk)
            fill_px = _fl if _fl is not None else px
            _fsrc = "live_quote" if _fl is not None else "run_snapshot"
            proceeds = pos["qty"] * fill_px
            pnl = (fill_px - pos["buy_price"]) * pos["qty"]
            state["cash"] += proceeds
            state["realized_pnl"] += pnl
            state["trades"] += 1
            state["positions"].pop(tk)
            _append_ledger(ledger_path, {"type": "fill_sell", "ticker": tk, "price": fill_px,
                                         "qty": pos["qty"], "pnl": round(pnl),
                                         "fill_source": _fsrc, "reason": "x2_avoid_immediate"})
            continue
        queued = any(o["ticker"] == tk and o["side"] == "sell" for o in state["pending"])
        if not queued and badge in ("CAUTION",):  # X1 익일
            state["pending"].append({"side": "sell", "ticker": tk, "reason": "x1_badge_demote", "created": today})
            _append_ledger(ledger_path, {"type": "exit_signal", "ticker": tk, "rule": "X1", "badge": badge})
        elif not queued and px and px <= pos["buy_price"] * (1 - STOP_PCT):  # X3 익일
            state["pending"].append({"side": "sell", "ticker": tk, "reason": "x3_hard_stop", "created": today})
            _append_ledger(ledger_path, {"type": "exit_signal", "ticker": tk, "rule": "X3",
                                         "price": px, "buy_price": pos["buy_price"]})

    # ── 3) 신규 진입 (E 규칙 → S 사이징 → pending) ──
    equity = state["cash"] + sum(
        (p["qty"] * (_price(by_tk.get(t)) or p["buy_price"])) for t, p in state["positions"].items())
    exposure = _fetch_moderation_exposure()
    candidates = []
    for r in kr:
        dv = r.get("display_verdict") or {}
        tk = str(r.get("ticker"))
        if dv.get("final") != "BUY" or not dv.get("aligned"):
            continue
        if tk in state["positions"] or any(o["ticker"] == tk for o in state["pending"]):
            continue
        if "," in str(r.get("name") or ""):  # E4 오염
            _append_ledger(ledger_path, {"type": "skip", "ticker": tk, "reason": "e4_name_pollution"})
            continue
        rf = ((r.get("verity_brain") or {}).get("red_flags") or {})
        if rf.get("has_critical"):
            _append_ledger(ledger_path, {"type": "skip", "ticker": tk, "reason": "e4_red_flag_critical"})
            continue
        px = _price(r)
        avg_vol = ((r.get("trends") or {}).get("1m") or {}).get("avg_volume")
        if not px or not avg_vol or avg_vol * px < MIN_TRADING_VALUE:  # E3
            _append_ledger(ledger_path, {"type": "skip", "ticker": tk, "reason": "e3_liquidity"})
            continue
        candidates.append(r)

    candidates.sort(key=lambda r: ((r.get("verity_brain") or {}).get("brain_score") or 0), reverse=True)
    entered = 0
    if candidates and exposure is None:
        flags.append("s1_moderation_unavailable_entries_halted")
        for r in candidates[:MAX_DAILY_ENTRIES]:
            _append_ledger(ledger_path, {"type": "skip", "ticker": r.get("ticker"),
                                         "reason": "s1_moderation_unavailable"})
    else:
        held_value = equity - state["cash"]
        exposure_cap_krw = equity * float(exposure or 0)
        for r in candidates[:MAX_DAILY_ENTRIES]:
            tk = str(r.get("ticker"))
            guide = (((r.get("verity_brain") or {}).get("position_guide") or {}).get("recommended_pct") or 3)
            alloc = equity * min(PER_STOCK_CAP, float(guide) / 100.0)
            if held_value + alloc > exposure_cap_krw:
                alloc = max(0.0, exposure_cap_krw - held_value)
                flags.append("s1_exposure_scaled")
            if alloc < 10_000:
                _append_ledger(ledger_path, {"type": "skip", "ticker": tk, "reason": "s1_exposure_cap_full"})
                continue
            px = _price(r)
            od = {"side": "buy", "ticker": tk, "created": today, "ref_price": px, "alloc_krw": round(alloc),
                  "signal_snapshot": {"brain": ((r.get("verity_brain") or {}).get("brain_score")),
                                      "gates": (r.get("display_verdict") or {}).get("gates"),
                                      "exposure": exposure}}
            state["pending"].append(od)
            held_value += alloc
            entered += 1
            _append_ledger(ledger_path, {"type": "entry_signal", "ticker": tk, "rule": "E1_aligned_buy",
                                         "order": od})

    state["last_date"] = today
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    return _summary(state, by_tk, flags, entered)


def _summary(state, by_tk, flags, entered: int = 0) -> Dict[str, Any]:
    equity = state["cash"] + sum(
        (p["qty"] * (_price(by_tk.get(t)) or p["buy_price"])) for t, p in state["positions"].items())
    return {
        "as_of": _now().isoformat(timespec="seconds"),
        "version": "v0 (PREREG_AUTO_EXECUTION_GATE_2026_08_03)",
        "initial_capital": INITIAL_CAPITAL,
        "equity": round(equity),
        "cash": round(state["cash"]),
        "return_pct": round((equity / INITIAL_CAPITAL - 1) * 100, 3),
        "positions": {t: {"qty": p["qty"], "buy_price": p["buy_price"], "buy_date": p["buy_date"]}
                      for t, p in state["positions"].items()},
        "pending": len(state.get("pending", [])),
        "trades_total": state.get("trades", 0),
        "realized_pnl": round(state.get("realized_pnl", 0.0)),
        "entered_today": entered,
        "flags": sorted(set(flags)),
        "_note": "등록 규칙 가상 집행 — VAMS 와 분리 · 오퍼레이터 전용 · 실주문 0",
    }
