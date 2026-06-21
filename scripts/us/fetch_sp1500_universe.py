#!/usr/bin/env python3
"""
fetch_sp1500_universe.py — S&P Composite 1500 (500 대형 + 400 중형 + 600 소형) 종목 리스트 수집.

2026-06-21 신설. 미장 유니버스 확대(15→1500) 정적 소스. 위키피디아 3 리스트(공식 유지) →
data/us_universe_sp1500.json (committed). 빌더(us_financials_builder --universe sp1500)가 읽음.
kr_stock_names.json 패턴 — 런타임 스크래핑 의존 0, 정적 파일, 주기 수동/분기 refresh.

🚨 ticker 정규화: 위키 BRK.B → SEC/yfinance 호환 BRK-B (. → -). graceful per-list(1개 실패해도 진행).
무료(위키), no auth. usage: python3 scripts/us/fetch_sp1500_universe.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_PATH = _ROOT / "data" / "us_universe_sp1500.json"

_LISTS = {
    "sp500": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
    "sp400": "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
    "sp600": "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies",
}


def _fetch_list(url: str):
    """위키 테이블에서 Symbol/Ticker 컬럼 추출 → 정규화 ticker list. 실패 시 []."""
    import pandas as pd
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 verity-universe"})
    html = urllib.request.urlopen(req, timeout=25).read()
    for t in pd.read_html(html):
        cols = [str(c).lower() for c in t.columns]
        if any("symbol" in c or "ticker" in c for c in cols):
            sc = [c for c in t.columns if "symbol" in str(c).lower() or "ticker" in str(c).lower()][0]
            out = []
            for x in t[sc].tolist():
                s = str(x).strip().upper().replace(".", "-")
                if s and s != "NAN" and s.replace("-", "").isalnum():
                    out.append(s)
            return out
    return []


def main() -> int:
    from api.config import now_kst  # repo 루트 sys.path 가정

    members = {}  # ticker → tier(첫 등장 tier)
    per = {}
    for tier, url in _LISTS.items():
        try:
            lst = _fetch_list(url)
        except Exception as e:  # noqa: BLE001 — list 1개 실패해도 나머지 진행
            sys.stderr.write(f"[sp1500] {tier} 실패 (graceful): {type(e).__name__}: {e}\n")
            lst = []
        per[tier] = len(lst)
        for tk in lst:
            members.setdefault(tk, tier)
    tickers = sorted(members)
    if len(tickers) < 1000:
        sys.stderr.write(f"[sp1500] 수집 {len(tickers)} < 1000 — 위키 파싱 의심, 기존 파일 보존(미덮음)\n")
        return 1

    payload = {
        "_meta": {
            "generated_at": now_kst().isoformat(timespec="seconds"),
            "source": "Wikipedia S&P 500/400/600 (S&P Composite 1500)",
            "count": len(tickers),
            "per_list": per,
            "note": "미장 유니버스 정적 소스. ticker '.'→'-' 정규화(SEC/yfinance 호환). 분기 refresh 권장.",
        },
        "tickers": tickers,
        "tier_map": members,  # ticker → sp500/sp400/sp600
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[sp1500] {len(tickers)} tickers → {OUT_PATH.relative_to(_ROOT)} (per {per})")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(_ROOT))
    sys.exit(main())
