"""랭킹 보드 — AlphaNest 탐색 진입로 Phase 1b.

"모를 때 시작" 다축 랭킹: 거래대금/등락(상승·하락)/외국인 순매수/시총. 행 클릭 → StockReport.

입력(read-only): data/trending_kr.json (거래대금 top) + data/krx_mktcap.json (시총·등락)
              + data/stock_flow_5d.json (외/기 순매매) + data/universe_search_kr.json (종목명)
출력: data/ranking_board.json

규율: 외부 사실 랭킹만(거래대금·등락·순매매·시총), 자체 점수/추천 0(RULE 7). LLM 0(RULE 6).
등락 보드는 시총 하한(노이즈·페니 컷) 적용.
"""
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TRENDING_PATH = os.path.join(_ROOT, "data", "trending_kr.json")
MKTCAP_PATH = os.path.join(_ROOT, "data", "krx_mktcap.json")
FLOW_PATH = os.path.join(_ROOT, "data", "stock_flow_5d.json")
UNIVERSE_PATH = os.path.join(_ROOT, "data", "universe_search_kr.json")
OUTPUT_PATH = os.path.join(_ROOT, "data", "ranking_board.json")

KST = timezone(timedelta(hours=9))
TOP_N = 20
CHG_MIN_MKTCAP = 50_000_000_000   # 등락 보드 시총 하한 500억 (페니·초저유동 노이즈 컷)


def _now_kst() -> datetime:
    return datetime.now(KST)


def _load(path: str) -> Any:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    mkt = (_load(MKTCAP_PATH) or {}).get("map") or {}
    if not mkt:
        print(f"[ranking_board] krx_mktcap 부재 — skip")
        return 0
    flows = (_load(FLOW_PATH) or {}).get("flows") or {}
    uni_doc = _load(UNIVERSE_PATH) or {}
    name_map: Dict[str, Dict[str, str]] = {}
    for r in (uni_doc.get("stocks") or []):
        tk = str(r.get("ticker") or "")
        if tk:
            name_map[tk] = {"name": r.get("name") or "", "market": r.get("market") or ""}

    def nm(tk: str) -> Dict[str, str]:
        return name_map.get(tk) or {"name": "", "market": ""}

    boards: List[Dict[str, Any]] = []

    # 1) 거래대금 상위 — trending_kr (이름·거래대금 보유)
    trend = (_load(TRENDING_PATH) or {}).get("top") or []
    if trend:
        rows = [{"ticker": str(t.get("ticker")), "name": t.get("name") or nm(str(t.get("ticker")))["name"],
                 "value": t.get("trdval"), "chg": t.get("chg")} for t in trend[:TOP_N] if t.get("ticker")]
        boards.append({"key": "trdval", "label": "거래대금 상위", "unit": "원", "rows": rows})

    # 2/3) 등락 상위/하위 — krx_mktcap chg (시총 하한 적용)
    chg_rows = [{"ticker": tk, "name": nm(tk)["name"], "market": nm(tk)["market"],
                 "value": v.get("chg"), "chg": v.get("chg"), "mktcap": v.get("mktcap")}
                for tk, v in mkt.items()
                if v.get("chg") is not None and (v.get("mktcap") or 0) >= CHG_MIN_MKTCAP and nm(tk)["name"]]
    up = sorted(chg_rows, key=lambda r: r["value"], reverse=True)[:TOP_N]
    down = sorted(chg_rows, key=lambda r: r["value"])[:TOP_N]
    boards.append({"key": "gainers", "label": "상승률 상위", "unit": "%", "note": "시총 500억+ 한정", "rows": up})
    boards.append({"key": "losers", "label": "하락률 상위", "unit": "%", "note": "시총 500억+ 한정", "rows": down})

    # 4) 외국인 순매수 상위 — stock_flow_5d 최근일 foreign_net
    fr_rows = []
    for tk, arr in flows.items():
        if not arr:
            continue
        fn = arr[-1].get("foreign_net")
        if fn is None:
            continue
        info = nm(str(tk))
        fr_rows.append({"ticker": str(tk), "name": info["name"], "value": round(float(fn)),
                        "chg": (mkt.get(str(tk)) or {}).get("chg")})
    fr_rows = [r for r in fr_rows if r["name"]]
    foreign_top = sorted(fr_rows, key=lambda r: r["value"], reverse=True)[:TOP_N]
    boards.append({"key": "foreign_buy", "label": "외국인 순매수 상위", "unit": "주", "note": "최근 거래일", "rows": foreign_top})

    # 5) 시총 상위
    cap_rows = sorted(
        [{"ticker": tk, "name": nm(tk)["name"], "value": v.get("mktcap"), "chg": v.get("chg")}
         for tk, v in mkt.items() if v.get("mktcap") and nm(tk)["name"]],
        key=lambda r: r["value"], reverse=True)[:TOP_N]
    boards.append({"key": "mktcap", "label": "시가총액 상위", "unit": "원", "rows": cap_rows})

    out = {
        "_meta": {
            "generated_at": _now_kst().isoformat(),
            "track": "kr_ranking_board",
            "board_count": len(boards),
            "top_n": TOP_N,
            "disclaimer": "외부 사실 랭킹(거래대금·등락·순매매·시총). 자체 점수/추천 아님. 등락 보드 시총 500억+ 한정.",
            "rule": "RULE 7 (사실만) / RULE 6 (LLM 0)",
        },
        "boards": boards,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    summary = " / ".join(f"{b['label']} {len(b['rows'])}" for b in boards)
    print(f"[ranking_board] 적재 OK | {summary} | out={OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
