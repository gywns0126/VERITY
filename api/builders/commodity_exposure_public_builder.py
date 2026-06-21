"""commodity_exposure_public_builder — 원자재 → KR 노출 산업/종목 (공개 터미널 시세 보드 엣지).

2026-06-21 신설. 글로벌 시세 보드(PublicMarketBoard)의 원자재 카드 차별화 — 가격 나열(commodity)이
아니라 "이 원자재에 원가·매출이 연관된 KR 상장 산업/종목"을 연결(토스·증권사 없는 KR 홈그라운드 cross-link).

🚨 RULE 7 = **산업 멤버십 사실만**. 수혜주·추천·자체 점수 0. 방향(상승 시 +/−)은 종목별 상이하므로
   "노출(원가·매출 연관)"으로만 표기, "수혜"라는 단어 금지. 시총 desc 정렬은 가시성 보조(점수 아님).
🚨 RULE 6 = 큐레이션 = 사전정의 산업 매핑(일반 산업지식, LLM 0).

입력: data/kr_sector_map.json (ticker→industry, yfinance .info) ⋈ data/stock_report_public.json (ticker→name·시총).
출력: data/commodity_exposure.json (action.yml publish 등재). 거의 정적 — daily_analysis_full 부산물로 갱신.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SECTOR_MAP_PATH = os.path.join(_ROOT, "data", "kr_sector_map.json")
REPORT_PATH = os.path.join(_ROOT, "data", "stock_report_public.json")
OUTPUT_PATH = os.path.join(_ROOT, "data", "commodity_exposure.json")
MAX_PER = 12  # 원자재별 노출 종목 상위 N (시총순)

# 원자재 key = macro_snapshot.macro / PublicMarketBoard GROUPS 와 동일. industry = kr_sector_map yfinance 정확 문자열.
COMMODITY_INDUSTRIES: Dict[str, Dict[str, Any]] = {
    "wti_oil": {
        "label": "WTI 원유",
        "industries": ["Oil & Gas Refining & Marketing", "Oil & Gas E&P", "Oil & Gas Integrated",
                       "Airlines", "Airports & Air Services", "Specialty Chemicals", "Chemicals"],
        "note": "정유(원료)·항공(연료 원가)·석유화학(원료) — 원유 가격에 원가·매출이 연관. 방향은 종목별 상이(수혜 아님).",
    },
    "copper": {
        "label": "구리",
        "industries": ["Copper", "Aluminum", "Other Industrial Metals & Mining", "Metal Fabrication"],
        "note": "비철금속·금속가공 — 구리 등 산업금속 가격에 원가·매출이 연관(경기 민감).",
    },
    "gold": {
        "label": "금",
        "industries": ["Gold", "Other Precious Metals & Mining", "Other Industrial Metals & Mining"],
        "note": "귀금속·광물 — KR 상장 금 채굴사는 매우 제한적(노출 종목 적음).",
    },
    "silver": {
        "label": "은",
        "industries": ["Silver", "Other Precious Metals & Mining"],
        "note": "귀금속 — KR 상장 은 채굴사는 매우 제한적(노출 종목 적음).",
    },
}


def _now_kst() -> datetime:
    return datetime.now(KST)


def _parse_cap(s: Any) -> float:
    if not s:
        return 0.0
    txt = str(s)
    v = 0.0
    m = re.search(r"([\d.]+)\s*조", txt)
    if m:
        v += float(m.group(1)) * 1e4
    m = re.search(r"([\d.]+)\s*억", txt)
    if m:
        v += float(m.group(1))
    return v


def _load_sector_map() -> Dict[str, Dict[str, Any]]:
    try:
        with open(SECTOR_MAP_PATH, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    mp = doc.get("map") if isinstance(doc, dict) and "map" in doc else doc
    return mp if isinstance(mp, dict) else {}


def _load_report() -> Dict[str, Dict[str, Any]]:
    """ticker → {name, cap}. 시총·이름 출처(공개 universe)."""
    try:
        with open(REPORT_PATH, "r", encoding="utf-8") as f:
            doc = json.load(f)
        arr = doc.get("stocks") if isinstance(doc, dict) else doc
    except (OSError, json.JSONDecodeError):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for s in (arr or []):
        tk = str(s.get("ticker") or "").strip()
        if not tk:
            continue
        out[tk] = {"name": s.get("name") or tk, "cap": _parse_cap((s.get("facts") or {}).get("시가총액"))}
    return out


def main() -> int:
    ok = False
    try:
        smap = _load_sector_map()
        report = _load_report()
        if not smap:
            print("[commodity_exposure] kr_sector_map 부재 — skip", file=sys.stderr)
            return 0

        # industry → [tickers]
        by_industry: Dict[str, List[str]] = {}
        for tk, v in smap.items():
            if not isinstance(v, dict):
                continue
            ind = v.get("industry")
            if ind:
                by_industry.setdefault(ind, []).append(str(tk))

        out_commodities: Dict[str, Any] = {}
        for ckey, cfg in COMMODITY_INDUSTRIES.items():
            seen = set()
            rows: List[Dict[str, Any]] = []
            for ind in cfg["industries"]:
                for tk in by_industry.get(ind, []):
                    if tk in seen:
                        continue
                    seen.add(tk)
                    rep = report.get(tk) or {}
                    rows.append({
                        "ticker": tk,
                        "name": rep.get("name") or tk,
                        "industry": ind,
                        "cap": rep.get("cap", 0.0),
                    })
            rows.sort(key=lambda r: -float(r.get("cap") or 0))
            out_commodities[ckey] = {
                "label": cfg["label"],
                "note": cfg["note"],
                "count": len(rows),
                "stocks": [{"ticker": r["ticker"], "name": r["name"], "industry": r["industry"]} for r in rows[:MAX_PER]],
            }

        out = {
            "_meta": {
                "generated_at": _now_kst().isoformat(),
                "source": "kr_sector_map(yfinance industry) ⋈ stock_report_public(name·시총)",
                "note": "원자재 가격에 원가·매출이 연관된 KR 상장 산업/종목 (산업 멤버십 사실). 수혜·추천·자체 점수 0 (RULE 7). 방향은 종목별 상이.",
                "max_per": MAX_PER,
            },
            "commodities": out_commodities,
        }
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
        tot = sum(c["count"] for c in out_commodities.values())
        print(f"[commodity_exposure] logged=True · {len(out_commodities)} 원자재 · 노출 {tot}종목 누적 -> "
              f"{os.path.relpath(OUTPUT_PATH, _ROOT)}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[commodity_exposure] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[commodity_exposure] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
