#!/usr/bin/env python3
"""
fetch_us_smallcap_universe.py — 미장 소형주 트랙 universe 소싱 (Polygon 전 CS active).

배경 (2026-06-24 PM): Russell 2000 신선 무료 멤버십 소스 부재 — iShares ajax=Akamai 봇차단,
FTSE=index 값만, GitHub ikoniaris=49% stale(5년 전 스냅샷). 유료 검토 → FMP/Finnhub 무료 tier
는 constituent/holdings 차단. **Polygon 보유 키 = 전 CS(보통주) active 신선 리스트(stale 0)**.
→ Russell 2000 "멤버십" 대신 시총 기반 소형주를 자체 정의(RULE 7, FTSE 라이선스 회피).
시총 컷은 다운스트림(fetch_us_market_caps yfinance → us_smallcap_corner_builder).

소스: Polygon /v3/reference/tickers?type=CS&active=true (페이징 1000/page, rate-limit sleep).
병합: 기존 us_universe_sp1500.json tier_map 유지(sp500/sp400/sp600), 순증=tier 'polygon_cs'.
산출: data/us_universe_combined.json {_meta, tickers, names, tier_map}.
세이프가드: < 2000 수집 시 기존 파일 보존(Polygon 장애 방어, fetch_sp1500 패턴).
무료(Polygon 보유 키). usage: python3 scripts/us/fetch_us_smallcap_universe.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
SP1500_PATH = _ROOT / "data" / "us_universe_sp1500.json"
OUT_PATH = _ROOT / "data" / "us_universe_combined.json"
POLY = "https://api.polygon.io/v3/reference/tickers"


def _get(url: str, timeout: int = 25) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "verity-universe"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def fetch_polygon_cs(api_key: str, max_pages: int = 12) -> tuple[dict, int]:
    """전 CS active 종목 {ticker: name}. 페이징 + rate-limit sleep(제한 tier ~5/min)."""
    out: dict[str, str] = {}
    url = f"{POLY}?type=CS&active=true&market=stocks&limit=1000&apiKey={api_key}"
    pages = 0
    while url and pages < max_pages:
        d = _get(url)
        pages += 1
        for r in d.get("results", []):
            tk = str(r.get("ticker", "")).strip().upper().replace(".", "-")
            if tk and tk.replace("-", "").isalnum():
                out[tk] = r.get("name") or ""
        nxt = d.get("next_url")
        url = (nxt + f"&apiKey={api_key}") if nxt else None
        if url:
            time.sleep(13)  # Polygon 제한 tier ~5/min 안전 마진
    return out, pages


def main() -> int:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:  # noqa: BLE001
        pass
    from api.config import now_kst

    key = os.environ.get("POLYGON_API_KEY")
    if not key:
        sys.stderr.write("[us_universe] POLYGON_API_KEY 부재 — 중단\n")
        return 1
    try:
        cs, pages = fetch_polygon_cs(key)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[us_universe] Polygon fetch 실패(기존 보존): {type(e).__name__}: {e}\n")
        return 1
    if len(cs) < 2000:
        sys.stderr.write(f"[us_universe] 수집 {len(cs)} < 2000 — Polygon 장애 의심, 기존 보존(미덮음)\n")
        return 1

    # sp1500 tier_map 병합 (기존 tier 우선, 순증=polygon_cs)
    sp_tier: dict[str, str] = {}
    if SP1500_PATH.exists():
        try:
            spd = json.loads(SP1500_PATH.read_text(encoding="utf-8"))
            sp_tier = spd.get("tier_map", {}) or {}
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f"[us_universe] sp1500 parse 실패(무시): {e!r}\n")

    tier_map = dict(sp_tier)
    names: dict[str, str] = {}
    for tk, nm in cs.items():
        names[tk] = nm
        tier_map.setdefault(tk, "polygon_cs")  # sp1500 겹침은 기존 tier 유지

    tickers = sorted(set(tier_map))
    per: dict[str, int] = {}
    for t in tier_map.values():
        per[t] = per.get(t, 0) + 1

    payload = {
        "_meta": {
            "generated_at": now_kst().isoformat(timespec="seconds"),
            "source": "Polygon /v3/reference/tickers (CS active) ∪ S&P 1500",
            "count": len(tickers),
            "per_tier": per,
            "polygon_pages": pages,
            "note": "전 미국 보통주(CS) active + S&P 1500. Russell 2000 멤버십 아님 — 시총 기반 "
                    "소형주 자체 정의(RULE 7). stale 0(Polygon 실시간). 시총 컷=다운스트림(yfinance). "
                    "분기/월 refresh.",
        },
        "tickers": tickers,
        "names": names,
        "tier_map": tier_map,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[us_universe] {len(tickers)} tickers (CS={len(cs)}, pages={pages}) "
          f"-> {OUT_PATH.relative_to(_ROOT)} (per {per})")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(_ROOT))
    sys.exit(main())
