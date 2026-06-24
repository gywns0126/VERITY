#!/usr/bin/env python3
"""fetch_us_volume — 미장 거래대금/거래량 (Polygon grouped daily 1콜).

소형주 유동성 지표 — '방치' 코너의 핵심(거래대금 작으면 못 사고 못 팜). 거래대금 = volume × vwap.
Polygon grouped daily(/v2/aggs/grouped) 1콜로 전 종목(~12,000). 무료 tier 당일 403 → 역순 탐색
(최근 거래일). 산출: data/us_volume.json {generated_at, trade_date, volumes:{TICKER:{volume, dollar_volume_musd}}}.

무료(Polygon 보유 키). corner builder 가 join. usage: python3 scripts/us/fetch_us_volume.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_PATH = _ROOT / "data" / "us_volume.json"


def _get(url: str, timeout: int = 25) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "verity-volume"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def main() -> int:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:  # noqa: BLE001
        pass
    from api.config import now_kst

    key = os.environ.get("POLYGON_API_KEY")
    if not key:
        sys.stderr.write("[us_volume] POLYGON_API_KEY 부재 — 중단\n")
        return 1

    results = None
    used = None
    for back in range(7):  # 무료 tier 당일/전일 403 → 최근 거래일까지 역순 탐색
        dt = (now_kst().date() - timedelta(days=back)).isoformat()
        try:
            d = _get(f"https://api.polygon.io/v2/aggs/grouped/locale/us/market/stocks/{dt}"
                     f"?adjusted=true&apiKey={key}")
        except Exception:  # noqa: BLE001 — 403(미개장/지연) skip
            time.sleep(13)
            continue
        r = d.get("results") or []
        if r:
            results = r
            used = dt
            break
        time.sleep(13)
    if not results:
        sys.stderr.write("[us_volume] grouped 빈 응답(7일) — 기존 보존\n")
        return 1

    vol = {}
    for x in results:
        tk = str(x.get("T", "")).upper().replace(".", "-")
        v = x.get("v")
        vw = x.get("vw") or x.get("c")
        if tk and v and vw:
            vol[tk] = {"volume": int(v), "dollar_volume_musd": round(v * vw / 1e6, 2)}

    payload = {
        "schema_version": "v0",
        "generated_at": now_kst().isoformat(timespec="seconds"),
        "trade_date": used,
        "count": len(vol),
        "source": "Polygon grouped daily (volume × vwap)",
        "volumes": vol,
    }
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")  # 큰 파일 — indent 생략
    print(f"[us_volume] {len(vol)} tickers (date {used}) -> {OUT_PATH.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(_ROOT))
    sys.exit(main())
