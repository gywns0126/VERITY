"""us_smart_money_13f_public_builder — 공개 터미널 美 스마트머니(집중형 13F) 빌더.

2026-06-22 신설. 13F 완전판([[project_us_financials_sec_edgar]] (b) / [[feedback_us_expansion_settled_no_relitigate]]).
유명 집중형 액티브 매니저의 13F 보유 → CUSIP→ticker(OpenFIGI) → sp1500 per-stock 스마트머니 신호.
"이 종목을 어떤 거장 펀드가 보유/신규/증액/감액했나" = 증권사·토스에 없는 forensics.

🚨 인덱스펀드(Vanguard/BlackRock/State Street) 제외 — sp1500 전부 수동보유라 신호 0 + CUSIP 수천 비용.
   집중형 액티브(Berkshire/Bridgewater/Renaissance/Pershing/Third Point/Tiger)만 = 신호+비용 bounded.

QoQ: 각 펀드 최근 2개 13F-HR 비교 → NEW/INCREASED/DECREASED/HELD. 분기 1회 갱신(13F = 분기말+45일).
🚨 RULE 7 = 보유 사실(펀드·주식수·평가액·QoQ 변동)만. 자체 점수 0 (기존 brain inst_13f_bonus 와 별개·불간섭).
   [[feedback_us_expansion_settled_no_relitigate]] / [[project_brain_v5_self_attribution]].
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

from api.collectors.sec_13f_collector import (
    TRACKED_INSTITUTIONS, get_recent_13f_filings, parse_13f_holdings,
)
from api.collectors.cusip_resolver import resolve_cusips
from api.builders.us_insider_trades_public_builder import _now_kst, _universe

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_PATH = os.path.join(_ROOT, "data", "us_smart_money_13f.json")

# 집중형 액티브 매니저만 (인덱스펀드 제외 — 신호 희석·비용 회피).
ACTIVE_MANAGERS = {
    "1067983":  "Berkshire Hathaway",
    "1350694":  "Bridgewater Associates",
    "1037389":  "Renaissance Technologies",
    "1336528":  "Pershing Square",
    "1040273":  "Third Point LLC",
    "1423053":  "Tiger Global",
}
TOP_HOLDINGS_PER_FUND = 300   # 펀드당 평가액 상위 N (롱테일 컷 — CUSIP 비용·노이즈 bound)


def _holdings_with_change(curr: List[dict], prev: List[dict]) -> List[dict]:
    """현 보유 + QoQ change_type (직전 분기 대비)."""
    pm = {h["cusip"]: h for h in prev if h.get("cusip")}
    out = []
    for h in curr:
        c = h.get("cusip")
        if not c:
            continue
        if c not in pm:
            ct, vc = "NEW", h["value_usd"]
        else:
            ds = h["shares"] - pm[c]["shares"]
            ct = "INCREASED" if ds > 0 else "DECREASED" if ds < 0 else "HELD"
            vc = h["value_usd"] - pm[c]["value_usd"]
        out.append({**h, "change_type": ct, "value_change_usd": vc})
    return out


def main() -> int:
    ok = False
    try:
        sp1500 = {t for t in _universe()}  # sp1500 ticker set (대문자)
        # 1) 각 펀드 최근 2분기 보유 + QoQ
        fund_holdings: Dict[str, List[dict]] = {}
        for cik, name in ACTIVE_MANAGERS.items():
            recent = get_recent_13f_filings(cik, n=2)
            if not recent:
                print(f"[smart_money] {name}: 13F-HR 부재 skip", file=sys.stderr)
                continue
            curr = parse_13f_holdings(recent[0].get("accession_no", ""), cik)[:TOP_HOLDINGS_PER_FUND]
            prev = parse_13f_holdings(recent[1].get("accession_no", ""), cik) if len(recent) > 1 else []
            fund_holdings[name] = _holdings_with_change(curr, prev)
            print(f"[smart_money] {name}: 현 {len(curr)} 보유 (filed {recent[0].get('filed_at')})", file=sys.stderr)

        if not fund_holdings:
            print("[smart_money] 펀드 0 — 기존 보존", file=sys.stderr)
            ok = os.path.isfile(OUTPUT_PATH)
            return 0

        # 2) CUSIP → ticker (OpenFIGI, 캐시)
        all_cusips = {h["cusip"] for hs in fund_holdings.values() for h in hs if h.get("cusip")}
        cmap = resolve_cusips(all_cusips)

        # 3) sp1500 per-ticker 집계
        agg: Dict[str, Dict[str, Any]] = {}
        for fund, hs in fund_holdings.items():
            for h in hs:
                tk = cmap.get(str(h["cusip"]).upper())
                if not tk or tk not in sp1500:
                    continue
                e = agg.setdefault(tk, {
                    "ticker": tk, "name": tk,
                    "total_value_usd": 0.0, "holder_count": 0, "holders": [],
                })
                e["total_value_usd"] += h["value_usd"]
                e["holder_count"] += 1
                e["holders"].append({
                    "fund": fund,
                    "shares": int(h["shares"]),
                    "value_usd": round(h["value_usd"]),
                    "change_type": h["change_type"],            # NEW/INCREASED/DECREASED/HELD
                    "value_change_usd": round(h["value_change_usd"]),
                })

        for e in agg.values():
            e["holders"].sort(key=lambda x: -x["value_usd"])
            e["total_value_usd"] = round(e["total_value_usd"])

        stocks = sorted(agg.values(), key=lambda s: (s["holder_count"], s["total_value_usd"]), reverse=True)

        out = {
            "_meta": {
                "generated_at": _now_kst().isoformat(),
                "source": "SEC EDGAR 13F-HR (집중형 액티브 매니저 보유) + OpenFIGI CUSIP→ticker",
                "managers": list(ACTIVE_MANAGERS.values()),
                "count": len(stocks),
                "note": "보유 사실만 — 펀드·주식수·평가액·QoQ 변동(NEW/INCREASED/DECREASED/HELD). 자체 점수·매매신호 아님 (RULE 7). 13F=분기말+45일 지연 공시. 인덱스펀드 제외(집중형만).",
            },
            "stocks": stocks,
        }
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
        print(f"[smart_money] logged=True · {len(stocks)} 종목 · 펀드 {len(fund_holdings)} -> {os.path.relpath(OUTPUT_PATH, _ROOT)}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[smart_money] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[smart_money] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
