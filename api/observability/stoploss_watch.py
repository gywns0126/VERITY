"""stoploss_watch — 손절 캡 변경(−5%→−20%)의 사후 감시. 2026-08-09 신설.

사전등록 `docs/PREREG_STOPLOSS_CAP_2026_08_09.md` 의 §4(적용 후 측정)·§5(되돌림 조건)를
사람이 기억하지 않아도 되게 자동화한다. PM 요구(2026-08-09): "20거래 쌓이면 자동으로 보고".

두 가지가 주기가 다르다:
  · **되돌림 감시(MDD)** — 매 run. 20거래를 기다리면 늦다. 조건은 "20거래 **내**" 이므로
    그 창 안에서는 언제든 걸릴 수 있다.
  · **측정 보고** — N ≥ 20 도달 시 1회. 그 전에는 진행률만 남긴다.

🚨 이 모듈은 **판정만 하고 아무것도 되돌리지 않는다.** 자동 원복은 하지 않는다 —
   되돌림은 PM 결정이고, 자동화하면 일시적 변동으로 규칙이 뒤집힌다.

🚨 [[feedback_silent_total_failure_guard]] — 규칙 변경 기록이 없으면 "감시 중" 이 아니라
   `no_rule_change` 로 명시한다. 조용히 통과시키지 않는다.

출력: data/metadata/stoploss_watch.json
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.config import DATA_DIR, now_kst  # noqa: E402

OUT_PATH = os.path.join(DATA_DIR, "metadata", "stoploss_watch.json")
# 🚨 규칙 변경 원장은 **전용 파일**이다. portfolio.json 에 두면 안 된다 —
#   2026-08-09 실측: 손절 커밋 13분 뒤 weekend_news 워크플로가 portfolio.json 을 덮어
#   rule_change_log 가 사라졌다. 그 파일은 여러 워크플로가 rebase 로 쓰는 공유 산출물이다.
# env 우회는 `fx_hedge_regime.RULE_LOG_PATH` 와 같은 변수를 읽는다 (2026-08-17, 테스트 격리).
RULE_LOG_PATH = os.environ.get("VERITY_RULE_LOG_PATH") or os.path.join(
    DATA_DIR, "metadata", "rule_change_log.jsonl")
PREREG = "docs/PREREG_STOPLOSS_CAP_2026_08_09.md"

# 사전등록 §4·§5 등록값 — 여기서 임의로 바꾸지 않는다.
TARGET_TRADES = 20          # 측정 보고 시점
MDD_REVERT_PCT = -17.0      # 되돌림 트리거 (현행 −8.58% 의 2배)
BASELINE = {                # 변경 전 22건 (정본 = trade_ledger 원장 재생)
    "trades": 22, "win_rate": 0.2273, "pl_ratio": 0.814,
    "expectancy_krw": -23538, "fixed_stop_avg_pct": -7.75, "mdd_pct": -8.58,
    "individual_atr_fires": 0,
}


def _load(path: str, default: Any) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _rule_change_at(vams: Dict[str, Any]) -> Optional[str]:
    """규칙 변경 시각. 전용 jsonl 우선, portfolio.json 은 legacy 폴백."""
    cands: List[str] = []
    try:
        with open(RULE_LOG_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                if r.get("prereg") == PREREG and r.get("at"):
                    cands.append(str(r["at"]))
    except (OSError, json.JSONDecodeError):
        pass
    for r in (vams.get("rule_change_log") or []):      # legacy 폴백
        if isinstance(r, dict) and r.get("prereg") == PREREG and r.get("at"):
            cands.append(str(r["at"]))
    return sorted(cands)[-1][:10] if cands else None


def build() -> Dict[str, Any]:
    pf = _load(os.path.join(DATA_DIR, "portfolio.json"), {}) or {}
    vams = pf.get("vams") or {}
    changed_at = _rule_change_at(vams)
    now = now_kst().isoformat(timespec="seconds")

    if not changed_at:
        return {"status": "no_rule_change", "checked_at": now, "prereg": PREREG,
                "detail": "vams.rule_change_log 에 해당 사전등록 기록이 없다 — 변경 미적용이거나 기록 누락"}

    # 정본 = 원장 재생(phantom 배제). exit_log 를 세면 틀린다(58건 phantom 전례).
    try:
        from api.vams.engine import load_history
        from api.vams.trade_ledger import reconstruct
        hist = load_history()
        led = reconstruct(hist, since=changed_at)
        eps: List[Dict[str, Any]] = led.get("episodes") or []
    except Exception as e:  # noqa: BLE001 — 감시 실패가 파이프라인을 죽이지 않는다
        return {"status": "ledger_error", "checked_at": now, "prereg": PREREG,
                "detail": f"{type(e).__name__}: {e}"}

    n = len(eps)
    wins = [e for e in eps if float(e.get("pnl") or 0) > 0]
    losses = [e for e in eps if float(e.get("pnl") or 0) <= 0]
    avg_w = (sum(float(e["pnl"]) for e in wins) / len(wins)) if wins else 0.0
    avg_l = (sum(float(e["pnl"]) for e in losses) / len(losses)) if losses else 0.0
    total = sum(float(e.get("pnl") or 0) for e in eps)

    # % 기대값 병기 (2026-08-11, FX 헤지 등록 §4) — 헤지 축소로 가용 현금이 늘면 신규
    # 포지션이 커져 원화 기대값이 크기만으로 부풀 수 있다. 크기 불변 지표를 같이 낸다.
    # 에피소드에는 cost 가 없어 history BUY 기록과 (ticker, 직전 매수) 조인으로 구한다.
    buy_cost: Dict[str, List] = {}
    for hrec in (hist or []):
        if str(hrec.get("action") or "").upper() != "BUY":
            continue
        tk, c = str(hrec.get("ticker") or ""), hrec.get("total_cost") or hrec.get("cost")
        if tk and c:
            buy_cost.setdefault(tk, []).append((str(hrec.get("date") or ""), float(c)))
    pcts: List[float] = []
    for e in eps:
        cands = [c for d0, c in buy_cost.get(str(e.get("ticker")), [])
                 if d0[:10] <= str(e.get("date") or "9999")[:10]]
        if cands:
            pcts.append(float(e.get("pnl") or 0) / cands[-1] * 100.0)
    expectancy_pct = (round(sum(pcts) / len(pcts), 3) if pcts else None)
    cost_join_coverage = round(len(pcts) / n, 3) if n else None

    # MDD — 규칙 변경 이후 자산 곡선. simulation_stats 는 창이 달라 쓰지 않는다.
    mdd = None
    ss = vams.get("simulation_stats") or {}
    if isinstance(ss.get("max_drawdown_pct"), (int, float)):
        mdd = float(ss["max_drawdown_pct"])

    # stop_method 분포 — individual_atr 이 실제로 발동하는지가 이 변경의 성패다.
    methods: Dict[str, int] = {}
    try:
        p = os.path.join(DATA_DIR, "vams", "exit_log.jsonl")
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                if str(r.get("date") or "")[:10] >= changed_at:
                    reason = str(r.get("reason") or "")
                    if "individual_atr" in reason:
                        methods["individual_atr"] = methods.get("individual_atr", 0) + 1
                    elif "profile_cap" in reason:
                        methods["profile_cap"] = methods.get("profile_cap", 0) + 1
                    elif "고정 손절" in reason:
                        methods["fixed_other"] = methods.get("fixed_other", 0) + 1
    except (OSError, json.JSONDecodeError):
        pass

    revert = bool(mdd is not None and mdd <= MDD_REVERT_PCT and n <= TARGET_TRADES)
    ready = n >= TARGET_TRADES

    doc: Dict[str, Any] = {
        "status": "revert_trigger" if revert else ("ready_to_report" if ready else "watching"),
        "checked_at": now,
        "prereg": PREREG,
        "rule_change_at": changed_at,
        "progress": {"trades": n, "target": TARGET_TRADES,
                     "pct": round(min(n / TARGET_TRADES, 1.0) * 100, 1)},
        "metrics": {
            "trades": n,
            "wins": len(wins), "losses": len(losses),
            "win_rate": round(len(wins) / n, 4) if n else None,
            "avg_win_krw": round(avg_w) if wins else None,
            "avg_loss_krw": round(avg_l) if losses else None,
            "pl_ratio": round(abs(avg_w / avg_l), 3) if (wins and losses and avg_l) else None,
            "expectancy_krw": round(total / n) if n else None,
            # 크기 불변 병기 — expectancy_krw 단독 비교 금지(헤지 축소 후 포지션 크기 오염)
            "expectancy_pct": expectancy_pct,
            "cost_join_coverage": cost_join_coverage,
            "mdd_pct": mdd,
            "stop_methods": methods,
        },
        "baseline_before_change": BASELINE,
        "revert": {
            "triggered": revert,
            "threshold_mdd_pct": MDD_REVERT_PCT,
            "action": ("🚨 즉시 원복 후 PM 보고 — 사전등록 §5" if revert
                       else "조건 미충족 — 감시 계속"),
        },
        "note": ("판정만 한다. 자동 원복하지 않는다(되돌림은 PM 결정). "
                 "N<20 구간의 수치는 참고값이며 RULE 7 상 '통계 무의미'."),
    }
    if ready:
        doc["report"] = {
            "headline": f"손절 캡 변경 후 {n}거래 도달 — 사전등록 §4 측정 시점",
            "compare": {
                "win_rate": [BASELINE["win_rate"], doc["metrics"]["win_rate"]],
                "pl_ratio": [BASELINE["pl_ratio"], doc["metrics"]["pl_ratio"]],
                "expectancy_krw": [BASELINE["expectancy_krw"], doc["metrics"]["expectancy_krw"]],
                "individual_atr_fires": [BASELINE["individual_atr_fires"],
                                         methods.get("individual_atr", 0)],
            },
            "🚨": "결과로 캡을 다시 만지지 않는다(사전등록 §4). 재조정 = 곡선 맞추기.",
        }
    return doc


def main() -> int:
    doc = build()
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    tmp = OUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    os.replace(tmp, OUT_PATH)

    st = doc["status"]
    if st == "watching":
        p = doc["progress"]
        print(f"[stoploss_watch] 감시 중 — {p['trades']}/{p['target']}거래 ({p['pct']}%) "
              f"· MDD {doc['metrics']['mdd_pct']} · ATR발동 {doc['metrics']['stop_methods'].get('individual_atr', 0)}")
    elif st == "ready_to_report":
        m = doc["metrics"]
        print(f"[stoploss_watch] 🔔 {m['trades']}거래 도달 — 보고 시점. "
              f"승률 {BASELINE['win_rate']:.3f}→{m['win_rate']} · 손익비 {BASELINE['pl_ratio']}→{m['pl_ratio']} "
              f"· 기대값 {BASELINE['expectancy_krw']:,}→{m['expectancy_krw']:,}원 "
              f"· ATR발동 0→{m['stop_methods'].get('individual_atr', 0)}")
    elif st == "revert_trigger":
        print(f"[stoploss_watch] 🚨 되돌림 트리거 — MDD {doc['metrics']['mdd_pct']}% "
              f"≤ {MDD_REVERT_PCT}% · 사전등록 §5 즉시 원복 검토", file=sys.stderr)
    else:
        print(f"[stoploss_watch] {st} — {doc.get('detail', '')}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
