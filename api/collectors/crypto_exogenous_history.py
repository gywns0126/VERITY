#!/usr/bin/env python3
"""크립토 외생 요인 시계열 수집 — 주식에 없는 축만.

## 왜 (PM 2026-08-17)

"외부 세력에 의해 영향받는 경우가 있던데, 주식과 달리 여타 영향 요소가 있는지 확인 후 검증"

TIDE 검정을 지금까지 **가격만으로** 해왔다. 그런데 크립토에는 주식에 없는 구조적 외생 축이
있고, 우리는 그걸 **스냅샷으로만** 갖고 있어 백테스트에 못 썼다:
`data/crypto_macro.json` 은 `funding_rate`·`kimchi_premium`·`btc_nasdaq_corr` 를 담지만
**현재값 1개뿐**이고, `crypto_regime_trail.jsonl` 은 55일(2026-06-24~)에 불과하다.

여기서 외부 원본에서 **전 구간 시계열**을 받아 백테스트 가능한 형태로 만든다.

## 주식에 없는 축 (수집 대상)

| 축 | 주식에 없는 이유 | 출처 |
|---|---|---|
| 김치 프리미엄 | 국내 거래소가 글로벌과 분리된 원화 시장. **TIDE 는 업비트 KRW 로 거래**하므로 직격 | Upbit KRW-BTC ÷ (Binance BTCUSDT × Upbit KRW-USDT) |
| 무기한선물 펀딩비 | 주식에 만기 없는 영구 레버리지 계약이 없다 | Binance fapi fundingRate |
| 공포탐욕지수(FNG) | 크립토 전용 합성 심리지수 (2018-02~) | alternative.me |
| 반감기 사이클 | 공급 스케줄이 코드로 고정 — 주식에 대응물 없음 | 알려진 날짜 |
| 현물 ETF 시대 | 2024-01-11 구조 전환 | 알려진 날짜 |

## 안 하는 것

- 청산(liquidation) 캐스케이드 = Coinglass 유료. 펀딩비 극단값을 프록시로 쓴다.
- 온체인(활성주소·SSR·NVT) = TIDE regime layer 가 이미 관측 중이나 시계열 이력이 짧다.
- 🚨 수집만 한다. 신호 배선은 별건이며 RULE 7 사전등록 대상이다.

산출 = `data/crypto_exogenous_history.json` (일별, 백테스트 직접 소비 가능).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
import urllib.parse
import urllib.request

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(_ROOT, "data", "crypto_exogenous_history.json")

HALVINGS = ["2016-07-09", "2020-05-11", "2024-04-20"]
ETF_SPOT_BTC = "2024-01-11"          # 미국 현물 BTC ETF 상장일
UA = {"Accept": "application/json", "User-Agent": "verity-research/1.0"}


def _get(url: str, timeout: int = 25, retries: int = 4):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception:
            if i == retries - 1:
                return None
            time.sleep(0.8 * (i + 1))
    return None


# ── ① 공포탐욕지수 ────────────────────────────────────────────────────────
def fetch_fng() -> dict:
    d = _get("https://api.alternative.me/fng/?limit=0&format=json")
    if not d or "data" not in d:
        return {}
    out = {}
    for row in d["data"]:
        day = dt.datetime.utcfromtimestamp(int(row["timestamp"])).strftime("%Y-%m-%d")
        out[day] = int(row["value"])
    return out


# ── ② 무기한선물 펀딩비 (8시간 → 일 합계) ────────────────────────────────
def fetch_funding(symbol: str = "BTCUSDT") -> dict:
    """fundingRate 는 8h 마다. 하루 3회를 더해 일간 비용률로 만든다."""
    out: dict[str, float] = {}
    start = int(dt.datetime(2019, 9, 1).timestamp() * 1000)
    now = int(time.time() * 1000)
    while start < now:
        q = urllib.parse.urlencode({"symbol": symbol, "startTime": start, "limit": 1000})
        d = _get(f"https://fapi.binance.com/fapi/v1/fundingRate?{q}")
        if not d:
            break
        for row in d:
            day = dt.datetime.utcfromtimestamp(row["fundingTime"] / 1000).strftime("%Y-%m-%d")
            out[day] = out.get(day, 0.0) + float(row["fundingRate"])
        start = d[-1]["fundingTime"] + 1
        if len(d) < 1000:
            break
        time.sleep(0.25)
    return out


# ── ③ 김치 프리미엄 ──────────────────────────────────────────────────────
def fetch_binance_daily(symbol: str) -> dict:
    out: dict[str, float] = {}
    start = int(dt.datetime(2018, 1, 1).timestamp() * 1000)
    now = int(time.time() * 1000)
    while start < now:
        q = urllib.parse.urlencode({"symbol": symbol, "interval": "1d",
                                    "startTime": start, "limit": 1000})
        d = _get(f"https://api.binance.com/api/v3/klines?{q}")
        if not d:
            break
        for row in d:
            day = dt.datetime.utcfromtimestamp(row[0] / 1000).strftime("%Y-%m-%d")
            out[day] = float(row[4])                    # 종가
        start = d[-1][0] + 86400000
        if len(d) < 1000:
            break
        time.sleep(0.25)
    return out


def fetch_upbit_daily(market: str) -> dict:
    """업비트 일봉 종가 (KST 기준일)."""
    out: dict[str, float] = {}
    to = None
    for _ in range(20):
        q = {"market": market, "count": 200}
        if to:
            q["to"] = to
        d = _get("https://api.upbit.com/v1/candles/days?" + urllib.parse.urlencode(q))
        if not d:
            break
        for row in d:
            out[row["candle_date_time_kst"][:10]] = float(row["trade_price"])
        to = d[-1]["candle_date_time_utc"]
        if len(d) < 200:
            break
        time.sleep(0.15)
    return out


def main() -> int:
    print("[crypto_exogenous] 외생 요인 시계열 수집 — 주식에 없는 축만", flush=True)

    fng = fetch_fng()
    print(f"  ① FNG {len(fng)}일", flush=True)

    fund_btc = fetch_funding("BTCUSDT")
    fund_eth = fetch_funding("ETHUSDT")
    print(f"  ② 펀딩비 BTC {len(fund_btc)}일 · ETH {len(fund_eth)}일", flush=True)

    gl_btc = fetch_binance_daily("BTCUSDT")
    up_btc = fetch_upbit_daily("KRW-BTC")
    up_usdt = fetch_upbit_daily("KRW-USDT")
    print(f"  ③ 글로벌 BTC {len(gl_btc)}일 · 업비트 BTC {len(up_btc)}일 · KRW-USDT {len(up_usdt)}일",
          flush=True)

    kimchi = {}
    for day, krw in up_btc.items():
        usd, rate = gl_btc.get(day), up_usdt.get(day)
        if usd and rate and rate > 0:
            kimchi[day] = round((krw / (usd * rate) - 1.0) * 100, 3)
    print(f"  → 김치 프리미엄 {len(kimchi)}일 산출", flush=True)

    days = sorted(set(fng) | set(fund_btc) | set(kimchi))
    rows = []
    for d0 in days:
        rows.append({
            "date": d0,
            "fng": fng.get(d0),
            "funding_btc_daily": round(fund_btc[d0], 8) if d0 in fund_btc else None,
            "funding_eth_daily": round(fund_eth[d0], 8) if d0 in fund_eth else None,
            "kimchi_premium_pct": kimchi.get(d0),
            "days_since_halving": min(
                ((dt.date.fromisoformat(d0) - dt.date.fromisoformat(h)).days
                 for h in HALVINGS
                 if dt.date.fromisoformat(d0) >= dt.date.fromisoformat(h)), default=None),
            "etf_era": d0 >= ETF_SPOT_BTC,
        })

    payload = {
        "collected_at": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec="seconds"),
        "schema_version": "v0",
        "purpose": "TIDE 백테스트용 외생 요인 시계열. 주식에 없는 축만. 신호 배선은 RULE 7 사전등록 별건.",
        "sources": {
            "fng": "alternative.me/fng",
            "funding": "binance fapi fundingRate (8h 3회 합계 = 일간)",
            "kimchi": "upbit KRW-BTC / (binance BTCUSDT × upbit KRW-USDT)",
            "halving": "고정 날짜 " + ",".join(HALVINGS),
            "etf_era": f"미국 현물 BTC ETF {ETF_SPOT_BTC}",
        },
        "coverage": {
            "days": len(rows),
            "fng": len(fng), "funding_btc": len(fund_btc), "kimchi": len(kimchi),
            "range": [days[0], days[-1]] if days else None,
        },
        "rows": rows,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    print(f"[crypto_exogenous] 저장 {OUT} — {len(rows)}일 ({days[0]}~{days[-1]})", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
