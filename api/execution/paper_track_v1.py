# -*- coding: utf-8 -*-
"""현행 Brain 순위형 전향 가상 운용 v1.

산식·가중치는 그대로 두고 실행층만 순위형으로 바꾼다. 현재 분석 KR 후보 안에서
WATCH 이상·유동성·중대 위험·정수 1주 조건을 통과한 상위 최대 10개를 20개의 서로 다른 가격
스냅샷마다 다시 고른다. 비용과 코스피 비교를 포함하지만 실주문 경로는 없다.
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Callable, Dict, List, Optional

from api.execution import paper_track as base


def _equity_value(state: Dict[str, Any], by_tk: Dict[str, Dict[str, Any]]) -> float:
    return float(state.get("cash") or 0) + sum(
        float(p.get("qty") or 0) * (base._price(by_tk.get(t)) or float(p.get("buy_price") or 0))
        for t, p in (state.get("positions") or {}).items()
    )


def _sell_position(state: Dict[str, Any], ledger_path: str, ticker: str, price: float,
                   today: str, fill_source: str, reason: str,
                   market_clock_state: str) -> None:
    pos = (state.get("positions") or {}).pop(ticker, None)
    if not pos:
        return
    qty = int(pos.get("qty") or 0)
    gross = qty * price
    cost = gross * base.ONE_WAY_COST_RATE
    proceeds = gross - cost
    entry_cost = float(pos.get("entry_cost_krw") or (qty * float(pos.get("buy_price") or 0)))
    pnl = proceeds - entry_cost
    state["cash"] = float(state.get("cash") or 0) + proceeds
    state["realized_pnl"] = float(state.get("realized_pnl") or 0) + pnl
    state["cost_paid"] = float(state.get("cost_paid") or 0) + cost
    state["trades"] = int(state.get("trades") or 0) + 1
    base._append_ledger(ledger_path, {
        "type": "fill_sell", "ticker": ticker, "price": price, "qty": qty,
        "gross_krw": round(gross), "cost_krw": round(cost, 2), "pnl": round(pnl),
        "fill_source": fill_source, "reason": reason, "date": today,
        "market_clock_state": market_clock_state,
    })


def _record_equity(state: Dict[str, Any], by_tk: Dict[str, Dict[str, Any]],
                   today: str, benchmark: Optional[Dict[str, Any]], new_session: bool) -> None:
    if benchmark:
        state["benchmark_latest"] = benchmark
        if not state.get("benchmark_start"):
            state["benchmark_start"] = benchmark
    if not new_session:
        return
    row: Dict[str, Any] = {
        "date": today,
        "equity": round(_equity_value(state, by_tk), 2),
        "positions_n": len(state.get("positions") or {}),
        "trades_total": int(state.get("trades") or 0),
        "cost_paid": round(float(state.get("cost_paid") or 0), 2),
    }
    if benchmark:
        row["benchmark_date"] = benchmark["date"]
        row["benchmark_close"] = benchmark["close"]
    curve = list(state.get("equity_curve") or [])
    curve.append(row)
    state["equity_curve"] = curve[-500:]


def _save(path: str, state: Dict[str, Any]) -> None:
    directory = os.path.dirname(path) or "."
    fd, temp_path = tempfile.mkstemp(prefix=".exec-paper-", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def _summary(state: Dict[str, Any], by_tk: Dict[str, Dict[str, Any]],
             flags: List[str], now_fn: Callable[[], Any], entered: int = 0) -> Dict[str, Any]:
    equity = _equity_value(state, by_tk)
    strategy_return = (equity / base.INITIAL_CAPITAL - 1) * 100
    b0 = state.get("benchmark_start") or {}
    b1 = state.get("benchmark_latest") or {}
    benchmark_return = None
    try:
        benchmark_return = (float(b1["close"]) / float(b0["close"]) - 1) * 100
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        pass
    target_snaps = state.get("target_snapshots") or {}
    targets = [target_snaps.get(tk) or {"ticker": tk} for tk in state.get("target_tickers", [])]
    denominator = state.get("last_denominator") or {}
    halted = "v0_nonempty_migration_halted" in flags
    status = "HALTED" if halted else ("RUNNING" if targets else "WAITING_FOR_ELIGIBLE_TARGETS")
    sessions_since = int(state.get("sessions_since_rebalance") or 0)
    return {
        "as_of": now_fn().isoformat(timespec="seconds"),
        "status": status,
        "version": state.get("version") or base.TRACK_VERSION,
        "formula_version": state.get("formula_version") or base.FORMULA_VERSION,
        "capital_mode": "paper_only",
        "real_orders": 0,
        "initial_capital": base.INITIAL_CAPITAL,
        "equity": round(equity),
        "cash": round(float(state.get("cash") or 0)),
        "return_pct": round(strategy_return, 3),
        "benchmark": {
            "name": "KOSPI",
            "start_date": b0.get("date"),
            "as_of": b1.get("date"),
            "return_pct": round(benchmark_return, 3) if benchmark_return is not None else None,
            "excess_pct": round(strategy_return - benchmark_return, 3)
            if benchmark_return is not None else None,
            "source": b1.get("source"),
            "freshness": b1.get("freshness"),
        },
        "positions": {
            t: {
                "qty": p.get("qty"), "buy_price": p.get("buy_price"),
                "buy_date": p.get("buy_date"), "name": (target_snaps.get(t) or {}).get("name"),
            }
            for t, p in (state.get("positions") or {}).items()
        },
        "targets": targets,
        "target_holdings": len(targets),
        "target_capacity": base.TARGET_HOLDINGS,
        "target_exposure_pct": round(float(state.get("target_exposure") or 0) * 100, 2),
        "actual_exposure_pct": round((equity - float(state.get("cash") or 0)) / equity * 100, 2)
        if equity > 0 else None,
        "pending": len(state.get("pending") or []),
        "trades_total": int(state.get("trades") or 0),
        "realized_pnl": round(float(state.get("realized_pnl") or 0)),
        "cost_paid": round(float(state.get("cost_paid") or 0), 2),
        "entered_today": entered,
        "market_sessions": int(state.get("market_sessions") or 0),
        "rebalance": {
            "interval_sessions": base.REBALANCE_SESSIONS,
            "sessions_since": sessions_since,
            "sessions_remaining": max(0, base.REBALANCE_SESSIONS - sessions_since),
            "last_date": state.get("last_rebalance_date"),
        },
        "denominator": denominator,
        "price_snapshot": state.get("price_snapshot") or {},
        "flags": sorted(set(flags)),
        "_meta": {
            "score_system": {
                "name": "current Brain rank",
                "axes": ["fact_70", "sentiment_30", "vci", "risk_adjustments"],
                "is_operational": True,
                "capital_mode": "paper_only",
                "note": "현재 분석 KR 후보 안의 순위. 전체 KR 상장사 순위가 아니다.",
            },
            "min_detectable": base._detectability(list(state.get("equity_curve") or [])),
            "evidence_class": "forward_execution",
            "historical_alpha_claim": False,
            "selection_note": "N10·20세션은 과거 6개 후보를 본 뒤 고른 실행 기본값이며 새 검증 근거로 쓰지 않는다.",
            "whole_share_only": True,
        },
        "_note": "현행식 전향 가상 운용 · 비용 반영 · VAMS 분리 · 오퍼레이터 전용 · 실주문 0",
    }


def run_paper_track_v1(
    analyzed: List[Dict[str, Any]],
    data_dir: str,
    *,
    now_fn: Callable[[], Any],
    live_quotes_fn: Callable[[List[str]], Dict[str, float]],
    exposure_fn: Callable[[], Optional[float]],
    source_as_of: Optional[str] = None,
) -> Dict[str, Any]:
    state_path = os.path.join(data_dir, "exec_paper_state.json")
    ledger_path = os.path.join(data_dir, "exec_paper_trail.jsonl")
    run_now = now_fn()
    today = run_now.strftime("%Y-%m-%d")

    state, migration = base._migrate_state(base._load(state_path, None), today)
    flags: List[str] = [
        "e2_next_run_fill", "e3_1m_proxy", "fill_live_quote_20260826",
        "candidate_pool_rank_not_full_kr_universe",
    ]
    if migration:
        flags.append(migration)
        base._append_ledger(ledger_path, {
            "type": "epoch_start", "date": today, "version": state.get("version"),
            "formula_version": state.get("formula_version"), "migration": migration,
            "capital_mode": "paper_only", "real_orders": 0,
        })

    kr = [r for r in analyzed if base._is_kr(r)]
    by_tk = {str(r.get("ticker")): r for r in kr}
    gate_live = any(isinstance(r.get("display_verdict"), dict) for r in kr)
    benchmark = base._kospi_snapshot(data_dir)
    market_clock_state = base._kr_clock_state(run_now)
    price_snapshot = {
        "source": "portfolio.recommendations.current_price",
        "as_of": source_as_of,
        "market_clock_state": market_clock_state,
        "holiday_calendar": "not_connected",
    }

    if migration == "v0_nonempty_migration_halted":
        flags.append("manual_epoch_decision_required")
        return _summary(state, by_tk, flags, now_fn)
    if state.get("last_date") == today and migration is None:
        prior_flags = list(state.get("last_flags") or [])
        return _summary(state, by_tk, prior_flags + ["already_ran_today"], now_fn)
    if not gate_live:
        base._append_ledger(ledger_path, {"type": "skip", "reason": "display_verdict_absent", "date": today})
        state["last_date"] = today
        state["last_flags"] = ["gate_not_live"]
        _save(state_path, state)
        return _summary(state, by_tk, ["gate_not_live"], now_fn)

    exposure = base._valid_exposure(exposure_fn())
    if exposure is None:
        exposure = base.FALLBACK_EXPOSURE
        flags.append("paper_exposure_fallback_50pct")
    state["target_exposure"] = exposure
    state["price_snapshot"] = price_snapshot

    fingerprint = base._market_fingerprint(kr)
    new_session = bool(fingerprint and fingerprint != state.get("last_price_fingerprint"))
    if new_session:
        state["market_sessions"] = int(state.get("market_sessions") or 0) + 1
        if state.get("last_rebalance_date"):
            state["sessions_since_rebalance"] = int(state.get("sessions_since_rebalance") or 0) + 1
        state["last_price_fingerprint"] = fingerprint

    signal_eligible, rejected = base._rank_eligible(kr)
    signal_rank = {str(r.get("ticker") or ""): i + 1 for i, r in enumerate(signal_eligible)}
    ranked, slot_budget, execution = base._select_executable_targets(
        signal_eligible, _equity_value(state, by_tk), exposure)
    eligible_n = execution["execution_eligible_n"]
    if execution["one_share_above_slot_n"]:
        rejected["one_share_above_slot"] = execution["one_share_above_slot_n"]
    denominator = {
        "kr_candidate_n": len(kr),
        "eligible_n": eligible_n,
        "signal_eligible_n": execution["signal_eligible_n"],
        "selected_n": min(len(ranked), base.TARGET_HOLDINGS),
        "target_capacity_n": base.TARGET_HOLDINGS,
        "slot_budget_krw": round(slot_budget),
        "whole_share_only": True,
        "not_selected_by_rank_n": execution["not_selected_by_rank_n"],
        "rejected": rejected,
    }
    state["last_denominator"] = denominator

    rebalance_due = bool(ranked) and (
        not state.get("target_tickers")
        or (new_session and int(state.get("sessions_since_rebalance") or 0) >= base.REBALANCE_SESSIONS)
    )
    if rebalance_due:
        target_tickers = [str(r.get("ticker")) for r in ranked]
        snapshots = {
            tk: base._target_snapshot(
                r, i + 1, len(kr), eligible_n,
                signal_rank=signal_rank.get(tk),
                signal_eligible_n=execution["signal_eligible_n"],
                price_as_of=source_as_of,
                market_clock_state=market_clock_state,
            )
            for i, (tk, r) in enumerate(zip(target_tickers, ranked))
        }
        old_targets = list(state.get("target_tickers") or [])
        state["target_tickers"] = target_tickers
        state["target_snapshots"] = snapshots
        state["last_rebalance_date"] = today
        state["selection_slot_krw"] = round(slot_budget)
        state["sessions_since_rebalance"] = 0
        state["pending"] = [
            od for od in (state.get("pending") or [])
            if od.get("side") != "buy" or od.get("ticker") in target_tickers
        ]
        base._append_ledger(ledger_path, {
            "type": "rebalance_target", "date": today, "old_targets": old_targets,
            "targets": target_tickers, "denominator": denominator,
            "formula_version": base.FORMULA_VERSION,
            "price_snapshot": price_snapshot,
        })

    # 이전 run 주문 체결
    live_px = live_quotes_fn(
        [str(od.get("ticker") or "") for od in state.get("pending", [])]
        + list((state.get("positions") or {}).keys())
    )
    still_pending: List[Dict[str, Any]] = []
    target_set = set(state.get("target_tickers") or [])
    for od in state.get("pending", []):
        tk = str(od.get("ticker") or "")
        r = by_tk.get(tk)
        if od.get("side") == "buy":
            if tk not in target_set:
                base._append_ledger(ledger_path, {"type": "cancel", "ticker": tk,
                                                  "reason": "left_rank_target", "order": od})
                continue
            if r is None:
                base._append_ledger(ledger_path, {"type": "cancel", "ticker": tk,
                                                  "reason": "entry_signal_missing", "order": od})
                continue
            entry_reason = base._candidate_reason(r)
            if entry_reason is not None:
                base._append_ledger(ledger_path, {"type": "cancel", "ticker": tk,
                                                  "reason": f"entry_condition_{entry_reason}", "order": od})
                continue
        live = live_px.get(tk)
        px = live if live is not None else base._price(r)
        fill_source = "live_quote" if live is not None else "run_snapshot"
        if px is None:
            od["missing_fills"] = int(od.get("missing_fills") or 0) + 1
            if od["missing_fills"] <= 2:
                still_pending.append(od)
            else:
                base._append_ledger(ledger_path, {"type": "cancel", "ticker": tk,
                                                  "reason": "price_unavailable", "order": od})
            continue
        if od.get("side") == "buy":
            ref = float(od.get("ref_price") or 0)
            band = abs(px / ref - 1.0) if ref > 0 else 0.0
            if band > base.FILL_BAND:
                base._append_ledger(ledger_path, {"type": "cancel", "ticker": tk,
                                                  "reason": f"e2_band_{band:.3f}", "order": od})
                continue
            qty = int(float(od.get("alloc_krw") or 0) // (px * (1 + base.ONE_WAY_COST_RATE)))
            gross = qty * px
            cost = gross * base.ONE_WAY_COST_RATE
            total = gross + cost
            if qty <= 0 or float(state.get("cash") or 0) < total:
                base._append_ledger(ledger_path, {"type": "cancel", "ticker": tk,
                                                  "reason": "insufficient_alloc", "order": od})
                continue
            state["cash"] = float(state.get("cash") or 0) - total
            state["cost_paid"] = float(state.get("cost_paid") or 0) + cost
            state["positions"][tk] = {
                "qty": qty, "buy_price": px, "buy_date": today, "missing_days": 0,
                "entry_cost_krw": total, "buy_cost_krw": cost,
                "signal_snapshot": od.get("signal_snapshot"), "fill_source": fill_source,
            }
            state["trades"] = int(state.get("trades") or 0) + 1
            base._append_ledger(ledger_path, {
                "type": "fill_buy", "ticker": tk, "price": px, "qty": qty,
                "gross_krw": round(gross), "cost_krw": round(cost, 2),
                "fill_source": fill_source, "market_clock_state": market_clock_state,
                "order": od,
            })
        else:
            _sell_position(state, ledger_path, tk, px, today, fill_source,
                           str(od.get("reason") or "scheduled_exit"), market_clock_state)
    state["pending"] = still_pending

    # 보유 위험·순위 이탈 청산 판정
    for tk, pos in list((state.get("positions") or {}).items()):
        r = by_tk.get(tk)
        queued = any(o.get("ticker") == tk and o.get("side") == "sell" for o in state.get("pending", []))
        if r is None:
            pos["missing_days"] = int(pos.get("missing_days") or 0) + 1
            if not queued and pos["missing_days"] >= base.MISSING_DAYS_EXIT:
                state["pending"].append({"side": "sell", "ticker": tk,
                                         "reason": "x4_coverage_lost", "created": today})
                base._append_ledger(ledger_path, {"type": "exit_signal", "ticker": tk, "rule": "X4"})
            continue
        pos["missing_days"] = 0
        px = base._price(r)
        badge = str((r.get("display_verdict") or {}).get("final") or r.get("recommendation") or "")
        if badge == "AVOID":
            live = live_px.get(tk)
            exit_price = live if live is not None else px
            if exit_price is not None:
                _sell_position(state, ledger_path, tk, exit_price, today,
                               "live_quote" if live is not None else "run_snapshot",
                               "x2_avoid_immediate", market_clock_state)
            elif not queued:
                state["pending"].append({"side": "sell", "ticker": tk,
                                         "reason": "x2_avoid_price_wait", "created": today})
                base._append_ledger(ledger_path, {"type": "exit_signal", "ticker": tk,
                                                  "rule": "X2", "reason": "price_unavailable"})
            continue
        if not queued and badge == "CAUTION":
            state["pending"].append({"side": "sell", "ticker": tk,
                                     "reason": "x1_badge_demote", "created": today})
            base._append_ledger(ledger_path, {"type": "exit_signal", "ticker": tk,
                                              "rule": "X1", "badge": badge})
        elif not queued and px and px <= float(pos.get("buy_price") or 0) * (1 - base.STOP_PCT):
            state["pending"].append({"side": "sell", "ticker": tk,
                                     "reason": "x3_hard_stop", "created": today})
            base._append_ledger(ledger_path, {"type": "exit_signal", "ticker": tk,
                                              "rule": "X3", "price": px,
                                              "buy_price": pos.get("buy_price")})

    if rebalance_due:
        for tk in list((state.get("positions") or {}).keys()):
            queued = any(o.get("ticker") == tk and o.get("side") == "sell" for o in state.get("pending", []))
            if tk not in target_set and not queued:
                state["pending"].append({"side": "sell", "ticker": tk,
                                         "reason": "rank_rebalance", "created": today})
                base._append_ledger(ledger_path, {"type": "exit_signal", "ticker": tk,
                                                  "rule": "rank_rebalance"})

    # 목표 포트폴리오를 하루 2건씩 구성
    equity = _equity_value(state, by_tk)
    exposure_cap_krw = equity * exposure
    held_value = equity - float(state.get("cash") or 0)
    reserved = sum(float(o.get("alloc_krw") or 0) for o in state.get("pending", []) if o.get("side") == "buy")
    entered = 0
    for tk in state.get("target_tickers", []):
        if entered >= base.MAX_DAILY_ENTRIES:
            break
        if tk in (state.get("positions") or {}) or any(o.get("ticker") == tk for o in state.get("pending", [])):
            continue
        current = by_tk.get(tk)
        if current is None or base._candidate_reason(current) is not None:
            flags.append("target_temporarily_ineligible")
            continue
        snap = (state.get("target_snapshots") or {}).get(tk) or {}
        ref_price = base._price(current) or base._price(snap)
        target_n = max(1, len(state.get("target_tickers") or []))
        alloc = equity * exposure / target_n
        if held_value + reserved + alloc > exposure_cap_krw:
            alloc = max(0.0, exposure_cap_krw - held_value - reserved)
            flags.append("s1_exposure_scaled")
        if alloc < 10_000 or ref_price is None:
            continue
        if ref_price * (1 + base.FILL_BAND) * (1 + base.ONE_WAY_COST_RATE) > alloc:
            flags.append("target_currently_unaffordable")
            continue
        order = {
            "side": "buy", "ticker": tk, "created": today,
            "ref_price": ref_price, "alloc_krw": round(alloc),
            "signal_snapshot": {
                "formula_version": base.FORMULA_VERSION,
                "brain": snap.get("brain_score"),
                "fact": snap.get("fact"),
                "grade": snap.get("grade"),
                "rank": snap.get("rank"),
                "candidate_pool_n": snap.get("candidate_pool_n"),
                "eligible_n": snap.get("eligible_n"),
                "target_exposure": exposure,
                "price_as_of": snap.get("price_as_of"),
                "market_clock_state": snap.get("market_clock_state"),
            },
        }
        state["pending"].append(order)
        reserved += alloc
        entered += 1
        base._append_ledger(ledger_path, {"type": "entry_signal", "ticker": tk,
                                          "rule": "E1_brain_rank_top10", "order": order})

    state["last_date"] = today
    state["last_flags"] = sorted(set(flags))
    _record_equity(state, by_tk, today, benchmark, new_session)
    _save(state_path, state)
    return _summary(state, by_tk, flags, now_fn, entered)
