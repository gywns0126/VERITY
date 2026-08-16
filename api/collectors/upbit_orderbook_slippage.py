"""업비트 호가 스냅샷 → 주문금액별 슬리피지 실측. 2026-08-16 신설 (PM 지시).

**왜 필요한가.** TIDE 백테스트가 슬리피지를 **0 으로 두고** 수수료 0.1% 만 반영한다
(`research/*_results.json` 의 `fee_rate: 0.001`). 외부 검증(2026-08-16)에서
"시장가 매수는 최우선 매도호가부터 순차 체결되므로 매수 VWAP ≥ 최우선 호가이고,
슬리피지를 0 으로 두는 것은 구조적으로 틀렸다" 는 지적을 받았다.

**그런데 첫 실측은 반대로 나왔다.** 2026-08-16 15:35 스냅샷 기준 BTC·ETH 모두
500만원까지 **최우선 호가만으로 흡수**되어 체결충격이 0.0000% 였다. 우리 주문 크기
(TIDE 총자산 약 50만원)에서 진짜 비용은 체결충격이 아니라 **스프레드**다.

    BTC 스프레드 0.0168% · ETH 0.0376%  (2026-08-16 15:35 실측 1건)

🚨 **단 이 1건은 조용한 장(BTC 전일 −0.05%)의 스냅샷이다.** 급락일에는 스프레드가
벌어지고 호가가 얇아지는데, 그때가 정확히 TSM 이 청산하는 순간이다. 최선의 경우
1건으로 비용 모델을 확정하면 백테스트가 낙관 편향된다. 그래서 **분포**를 쌓는다.

수집 주기 = `crypto_collect` 워크플로에 얹는다(Vercel Cron dispatch, SLA 90분).
전용 크론을 새로 만들지 않는 이유 = TIDE repo 는 무료 2000분/월 제약이 있고
(heartbeat 를 매시→6시간으로 줄인 이력), VERITY 크립토 수집은 이미 돌고 있어
마진 비용이 0 이다.

산출 = `data/upbit_orderbook_slippage.jsonl` (append). 분석은
`scripts/analyze_orderbook_slippage.py` 가 p50/p75/p95 를 낸다.

의존성 0 (urllib). 업비트 quotation API 는 무인증이며 호가는 최대 30단을 준다.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

_KST = timezone(timedelta(hours=9))
_URL = "https://api.upbit.com/v1/orderbook?markets={markets}"
_TIMEOUT = 10

# TIDE 실제 주문 규모(총자산 약 50만원)를 중심에 두되, 계좌가 커졌을 때를 위해
# 위쪽도 함께 잰다. 지금 500만원이 무의미해 보여도 나중에 소급 측정이 불가능하다.
ORDER_SIZES_KRW = (50_000, 100_000, 300_000, 500_000, 1_000_000, 5_000_000)
MARKETS = ("KRW-BTC", "KRW-ETH")


def _fetch(markets: List[str]) -> Optional[List[Dict[str, Any]]]:
    url = _URL.format(markets=",".join(markets))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VERITY/1.0"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            doc = json.loads(r.read())
        return doc if isinstance(doc, list) else None
    except Exception:
        return None


def _walk_book(levels: List[Dict[str, Any]], krw: float, side: str) -> Dict[str, Any]:
    """주문금액 `krw` 를 호가에 순차 체결시켜 VWAP 와 슬리피지를 낸다.

    side="buy"  → ask 를 최우선부터 소진. 슬리피지 = (VWAP − ask1) / ask1
    side="sell" → bid 를 최우선부터 소진. 슬리피지 = (bid1 − VWAP) / bid1
    둘 다 **양수가 불리**하도록 부호를 맞춘다.
    """
    pk, sk = ("ask_price", "ask_size") if side == "buy" else ("bid_price", "bid_size")
    if not levels:
        return {"slip_pct": None, "filled": False, "levels_used": 0}
    top = float(levels[0][pk])
    remaining, notional, qty, used = float(krw), 0.0, 0.0, 0
    for lv in levels:
        px, sz = float(lv[pk]), float(lv[sk])
        cap = px * sz
        if cap <= 0:
            continue
        take = min(remaining, cap)
        notional += take
        qty += take / px
        remaining -= take
        used += 1
        if remaining <= 1.0:      # 1원 미만 잔량은 체결로 본다
            break
    if qty <= 0:
        return {"slip_pct": None, "filled": False, "levels_used": used}
    vwap = notional / qty
    slip = (vwap / top - 1.0) if side == "buy" else (top / vwap - 1.0)
    return {
        "slip_pct": round(slip * 100, 6),
        # 🚨 30단을 다 써도 남으면 미체결이다. 업비트는 반대편 호가 총액을 넘는
        #    시장가 주문을 거부할 수 있으므로 이 플래그가 곧 "그 크기는 못 친다" 다.
        "filled": remaining <= 1.0,
        "levels_used": used,
    }


def collect_orderbook_slippage() -> Dict[str, Any]:
    """호가 스냅샷 1회 → 마켓별 슬리피지 레코드. 실패 시 rows 빈 리스트."""
    now = datetime.now(_KST)
    books = _fetch(list(MARKETS))
    out: Dict[str, Any] = {
        "collected_at": now.isoformat(timespec="seconds"),
        "source": "upbit:orderbook (무인증 · 최대 30단)",
        "order_sizes_krw": list(ORDER_SIZES_KRW),
        "rows": [],
    }
    if not books:
        out["error"] = "orderbook fetch 실패"
        return out

    for b in books:
        units = b.get("orderbook_units") or []
        if not units:
            continue
        ask1 = float(units[0]["ask_price"])
        bid1 = float(units[0]["bid_price"])
        mid = (ask1 + bid1) / 2.0
        row: Dict[str, Any] = {
            "ts": now.isoformat(timespec="seconds"),
            "market": b.get("market"),
            "ask1": ask1,
            "bid1": bid1,
            "mid": mid,
            # 스프레드가 우리 크기에서 실제 지배 비용이다(체결충격이 아니라).
            "spread_bps": round((ask1 - bid1) / mid * 10000, 4) if mid else None,
            "depth_ask_krw": round(sum(float(u["ask_price"]) * float(u["ask_size"]) for u in units)),
            "depth_bid_krw": round(sum(float(u["bid_price"]) * float(u["bid_size"]) for u in units)),
            "levels": len(units),
            "buy": {},
            "sell": {},
        }
        for q in ORDER_SIZES_KRW:
            row["buy"][str(q)] = _walk_book(units, q, "buy")
            row["sell"][str(q)] = _walk_book(units, q, "sell")
        out["rows"].append(row)
    return out


def append_jsonl(path: str, doc: Dict[str, Any]) -> int:
    """마켓별로 한 줄씩 append. 스냅샷 단위가 아니라 행 단위여야 분석이 쉽다."""
    rows = doc.get("rows") or []
    if not rows:
        return 0
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows)


if __name__ == "__main__":  # 수동 확인용
    d = collect_orderbook_slippage()
    print(json.dumps(d, ensure_ascii=False, indent=2)[:2000])
