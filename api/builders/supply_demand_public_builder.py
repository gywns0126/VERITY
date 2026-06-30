"""수급 종합 (공매도·신용잔고) — AlphaNest 루프 분석 단계 Phase 2.

종목 분석에서 외/기 5일(stock_flow_5d)·대차잔고(securities_lending)는 이미 노출 중.
여기서 KRX가 무료 차단하는 **공매도·신용잔고**를 보강 — KIS 스냅샷(이미 수집·portfolio.json 공개)에서 추출.

🚨 RULE 1 무관 — KIS 호출 0. 로컬 portfolio.json(이미 적재됨) 읽기만.
입력(read-only): data/portfolio.json (kis_snapshots[ticker].brain.{short_sale, credit_balance, investor})
출력: data/supply_demand.json (스냅샷 universe ~11종목)

규율: KIS/KRX 외부 사실(공매도 비중·신용잔고율·순매매)만, 자체 점수/판단 0(RULE 7). LLM 0(RULE 6).
"""
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PORTFOLIO_PATH = os.path.join(_ROOT, "data", "portfolio.json")
OUTPUT_PATH = os.path.join(_ROOT, "data", "supply_demand.json")

KST = timezone(timedelta(hours=9))


def _now_kst() -> datetime:
    return datetime.now(KST)


def _num(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def main() -> int:
    if not os.path.exists(PORTFOLIO_PATH):
        print(f"[supply_demand] portfolio 부재: {PORTFOLIO_PATH} — skip")
        return 0
    with open(PORTFOLIO_PATH, encoding="utf-8") as f:
        pf = json.load(f)
    snaps = pf.get("kis_snapshots") or {}

    stocks: Dict[str, Any] = {}
    for tk, snap in snaps.items():
        brain = (snap or {}).get("brain") or {}
        ss = brain.get("short_sale") or {}
        cb = brain.get("credit_balance") or {}
        inv = brain.get("investor") or {}
        row: Dict[str, Any] = {}
        # 공매도 (KRX 무료 차단 → KIS)
        if ss:
            row["short_ratio_5d"] = _num(ss.get("avg_short_ratio_5d"))   # 5일 평균 공매도 비중 %
            row["short_qty"] = _num(ss.get("latest_short_qty"))          # 최근 공매도량(주)
        # 신용잔고
        if cb:
            row["credit_qty"] = _num(cb.get("credit_balance_qty"))       # 신용잔고 수량(주)
            row["credit_rate"] = _num(cb.get("credit_rate"))             # 신용잔고율 %
        # 투자자별 순매매 (KIS 최근, stock_flow_5d 외/기 보강)
        if inv:
            row["foreign_net"] = _num(inv.get("foreign_net"))
            row["inst_net"] = _num(inv.get("institution_net"))
        # 의미 있는 값(0 초과/비None)이 하나라도 있어야 등재
        meaningful = any(v not in (None, 0, 0.0) for v in row.values())
        if meaningful:
            stocks[str(tk)] = row

    out = {
        "_meta": {
            "generated_at": _now_kst().isoformat(),
            "track": "kr_supply_demand",
            "count": len(stocks),
            "source": "KIS 종목별 스냅샷 (공매도 FHPST04830000 · 신용잔고 FHPST04760000 · 투자자별). portfolio.json 추출, KIS 호출 0.",
            "disclaimer": "공매도 비중·신용잔고율·순매매 = 외부 사실(KRX/KIS). 자체 점수/판단 아님. 스냅샷 universe 한정.",
            "rule": "RULE 7 (사실만) / RULE 6 (LLM 0) / RULE 1 무관(로컬 읽기)",
        },
        "stocks": stocks,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[supply_demand] 적재 OK | {len(stocks)} 종목 (공매도·신용·투자자별) | out={OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
