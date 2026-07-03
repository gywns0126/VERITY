"""업종(섹터) 진입 뷰 — AlphaNest 탐색 진입로 Phase 1a.

"종목명을 몰라도 업종으로 진입" — 섹터별 사실 집계 카드(중앙값 PER/PBR/ROE + 대표주 + 외/기 수급 + 평균 등락).
클릭 → PublicDiscovery `?sector=X` 딥링크 / 대표주 → StockReport.

입력(read-only): data/stock_report_public.json (sector=peer.sector, facts) + data/kr_sector_map.json (sector_ko 보강)
              + data/krx_mktcap.json (시총 numeric·등락) + data/stock_flow_5d.json (외/기 순매매)
출력: data/sector_overview.json

규율: 점수/랭킹/추천 0, 사실·중앙값만(RULE 7). LLM 0(RULE 6). 섹터 N>=5 만(노이즈 컷).
"""
import json
import os
from datetime import datetime, timezone, timedelta
from statistics import median
from typing import Any, Dict, List, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPORT_PATH = os.path.join(_ROOT, "data", "stock_report_public.json")
SECTOR_MAP_PATH = os.path.join(_ROOT, "data", "kr_sector_map.json")
MKTCAP_PATH = os.path.join(_ROOT, "data", "krx_mktcap.json")
FLOW_PATH = os.path.join(_ROOT, "data", "stock_flow_5d.json")
OUTPUT_PATH = os.path.join(_ROOT, "data", "sector_overview.json")

KST = timezone(timedelta(hours=9))
MIN_N = 5            # 섹터 최소 종목 수 (중앙값 노이즈 컷, stock_report_public_builder._sector_medians 정합)
LEADERS_N = 5        # 섹터별 대표주(시총 상위)


def _now_kst() -> datetime:
    return datetime.now(KST)


def _num(v: Any) -> Optional[float]:
    """'16.9' / '5.7%' / 16.9 → float. None/'' → None."""
    if v is None:
        return None
    try:
        s = str(v).replace("%", "").replace(",", "").strip()
        if not s:
            return None
        return float(s)
    except (TypeError, ValueError):
        return None


def _med(vals: List[Optional[float]]) -> Optional[float]:
    xs = [x for x in vals if x is not None]
    if not xs:
        return None
    return round(median(xs), 2)


def _load(path: str) -> Any:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    report = _load(REPORT_PATH)
    if not report or not report.get("stocks"):
        print(f"[sector_overview] 입력 부재: {REPORT_PATH} — skip")
        return 0
    stocks = report["stocks"]

    smap_doc = _load(SECTOR_MAP_PATH) or {}
    smap = smap_doc.get("map") or smap_doc or {}
    mkt = (_load(MKTCAP_PATH) or {}).get("map") or {}
    flows = (_load(FLOW_PATH) or {}).get("flows") or {}

    # 섹터별 누적
    buckets: Dict[str, Dict[str, Any]] = {}
    for s in stocks:
        tk = str(s.get("ticker") or "")
        if not tk:
            continue
        # 섹터 = peer.sector (클린 11) → kr_sector_map.sector_ko 보강. PublicDiscovery sectorOf 정합.
        sector = (s.get("peer") or {}).get("sector") or (smap.get(tk) or {}).get("sector_ko")
        if not sector:
            continue
        b = buckets.setdefault(sector, {"per": [], "pbr": [], "roe": [],
                                        "foreign": 0.0, "inst": 0.0, "members": []})
        facts = s.get("facts") or {}
        b["per"].append(_num(facts.get("PER")))
        b["pbr"].append(_num(facts.get("PBR")))
        b["roe"].append(_num(facts.get("ROE")))

        mrow = mkt.get(tk) or {}

        frow = (flows.get(tk) or [])
        if frow:
            last = frow[-1]
            b["foreign"] += float(last.get("foreign_net") or 0)
            b["inst"] += float(last.get("inst_net") or 0)

        b["members"].append({"ticker": tk, "name": s.get("name") or "",
                             "market": s.get("market") or "",
                             "mktcap": int(mrow.get("mktcap") or 0)})

    sectors = []
    for name, b in buckets.items():
        n = len(b["members"])
        if n < MIN_N:
            continue
        leaders = sorted(b["members"], key=lambda m: m.get("mktcap") or 0, reverse=True)[:LEADERS_N]
        sectors.append({
            "sector": name,
            "n": n,
            "median_per": _med(b["per"]),
            "median_pbr": _med(b["pbr"]),
            "median_roe": _med(b["roe"]),
            # avg_chg(KRX 당일 등락 평균) + leaders[].chg = 2026-07-03 컴플라이언스 필드수술로 제거 — KRX raw 재배포.
            # DART 파생 medians·수급(flow)은 유지. ExploreHub 표시도 이미 제거됨.
            "flow_foreign": round(b["foreign"]),    # 외국인 순매매 합(최근일, 주)
            "flow_inst": round(b["inst"]),          # 기관 순매매 합
            "leaders": [{"ticker": m["ticker"], "name": m["name"]} for m in leaders],
        })
    sectors.sort(key=lambda x: x["n"], reverse=True)

    out = {
        "_meta": {
            "generated_at": _now_kst().isoformat(),
            "track": "kr_sector_overview",
            "sector_count": len(sectors),
            "min_n": MIN_N,
            "disclaimer": "업종별 사실 집계(중앙값·대표주·수급). 점수/순위/추천 아님. 섹터 N>=5 한정.",
            "rule": "RULE 7 (사실만) / RULE 6 (LLM 0)",
        },
        "sectors": sectors,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    summary = " / ".join(f"{s['sector']} {s['n']}" for s in sectors[:6])
    print(f"[sector_overview] 적재 OK | {len(sectors)} 섹터 | {summary} | out={OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
