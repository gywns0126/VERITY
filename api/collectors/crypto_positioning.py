"""크립토 선물 포지셔닝 — BTC/ETH 미결제약정(OI) + 롱숏 비율 팩트 수집.

기존 펀딩비(crypto_macro._fetch_funding_rate)가 "가격 압력"이라면, 이 collector 는
"포지션 깊이/방향" — 무기한 선물에 얼마나 많은 자본이 묶여 있고(OI), 개미가 롱/숏 어느
쪽으로 쏠려 있는지(롱숏 account ratio) — 를 보강한다.

Coinglass(유료) 대체로 Bybit + OKX raw 2거래소를 직접 집계한다.

🚨 Binance(fapi/api.binance.com) 절대 호출 금지 — GitHub US-IP 에서 451 지역차단(crypto_macro.py
   2026-06 학습). Bybit + OKX 만 사용(둘 다 무인증, US-IP OK).

🚨 RULE 7 (자기 산식 노출 = 가설): 여기서는 거래소가 발표하는 **사실 숫자만** 적재한다.
   점수·등급·매수신호 0. OI/롱숏비는 Bybit/OKX 1차 raw 그대로.

🚨 거래소별 OI 단위 차이 (raw 정합 — 변환/합산 시 주의):
  - Bybit `open-interest` endpoint = **코인 단위**(BTC 수량). `tickers` endpoint 의
    `openInterestValue` = **USD 명목가치**. 여기서는 USD 직접 노출되는 tickers 를 1차로
    쓰고, 코인 단위 OI 도 함께 노출(oi_bybit_coin).
  - OKX `open-interest` endpoint = `oi`(계약 수), `oiCcy`(코인 단위), `oiUsd`(USD 명목가치)
    3종 동시 제공. 여기서는 oiUsd 를 1차로 노출.
  → 두 거래소 OI(USD)는 동일 단위(명목 USD)라 합산 가능하나, **합산은 호출부 책임**으로 남기고
    여기서는 거래소별 raw 만 분리 노출한다(집계 가설 회피).

롱숏 비율 = (롱 비중 / 숏 비중). >1 = 롱 우위, <1 = 숏 우위.
  - Bybit account-ratio: buyRatio/sellRatio (합=1) → buyRatio/sellRatio
  - OKX rubik long-short-account-ratio: 이미 비율값(롱/숏) 배열, newest-first

소스 (모두 실호출 schema 검증 완료, 2026-06-24):
  - Bybit OI(USD+코인): https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT
      → result.list[0].openInterestValue(USD), openInterest(코인)
  - Bybit 롱숏:         https://api.bybit.com/v5/market/account-ratio?category=linear&symbol=BTCUSDT&period=1h&limit=1
      → result.list[0].buyRatio / sellRatio
  - OKX OI:            https://www.okx.com/api/v5/public/open-interest?instType=SWAP&instId=BTC-USDT-SWAP
      → data[0].oiUsd / oiCcy / oi
  - OKX 롱숏:          https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio?ccy=BTC&period=1H
      → data[][1] (newest-first, [ts, ratio])

기존 crypto_macro.py / crypto_defillama.py collector 계약 정합:
  표준 라이브러리 + requests 만, 외부 의존 추가 없음. 항상 dict 반환, 절대 raise 안 함.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import requests

_TIMEOUT = 10
_HEADERS = {"User-Agent": "Verity-Terminal/1.0"}
_SOURCE = "bybit+okx"

# 자산별 거래소 심볼 매핑 (Binance 제외)
_ASSETS = {
    "btc": {"bybit": "BTCUSDT", "okx_inst": "BTC-USDT-SWAP", "okx_ccy": "BTC"},
    "eth": {"bybit": "ETHUSDT", "okx_inst": "ETH-USDT-SWAP", "okx_ccy": "ETH"},
}


def _to_float(v: Any) -> Optional[float]:
    """문자열/None → float. 실패 시 None (raw 결측 보존)."""
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _fetch_bybit_oi(symbol: str) -> Dict[str, Any]:
    """Bybit linear tickers → OI(USD 명목가치) + OI(코인 단위).

    openInterestValue = USD 명목, openInterest = 코인 수량. 실패 시 빈 dict.
    """
    try:
        r = requests.get(
            "https://api.bybit.com/v5/market/tickers",
            params={"category": "linear", "symbol": symbol},
            headers=_HEADERS, timeout=_TIMEOUT,
        )
        r.raise_for_status()
        lst = ((r.json().get("result") or {}).get("list")) or []
        if not lst:
            return {}
        row = lst[0]
        return {
            "oi_bybit_usd": _to_float(row.get("openInterestValue")),
            "oi_bybit_coin": _to_float(row.get("openInterest")),
        }
    except Exception:  # noqa: BLE001
        return {}


def _fetch_bybit_long_short(symbol: str) -> Dict[str, Any]:
    """Bybit account-ratio → 롱숏 비율(buyRatio/sellRatio) + 원시 롱/숏 비중.

    buyRatio + sellRatio = 1. ratio = buyRatio/sellRatio (>1 롱 우위). 실패 시 빈 dict.
    """
    try:
        r = requests.get(
            "https://api.bybit.com/v5/market/account-ratio",
            params={"category": "linear", "symbol": symbol, "period": "1h", "limit": 1},
            headers=_HEADERS, timeout=_TIMEOUT,
        )
        r.raise_for_status()
        lst = ((r.json().get("result") or {}).get("list")) or []
        if not lst:
            return {}
        row = lst[0]
        buy = _to_float(row.get("buyRatio"))
        sell = _to_float(row.get("sellRatio"))
        ratio = (buy / sell) if (buy is not None and sell not in (None, 0)) else None
        return {
            "long_short_ratio_bybit": round(ratio, 4) if ratio is not None else None,
            "long_account_pct_bybit": buy,
            "short_account_pct_bybit": sell,
            "ls_ts_bybit": row.get("timestamp"),
        }
    except Exception:  # noqa: BLE001
        return {}


def _fetch_okx_oi(inst_id: str) -> Dict[str, Any]:
    """OKX SWAP open-interest → oiUsd(USD 명목) + oiCcy(코인) + oi(계약). 실패 시 빈 dict."""
    try:
        r = requests.get(
            "https://www.okx.com/api/v5/public/open-interest",
            params={"instType": "SWAP", "instId": inst_id},
            headers=_HEADERS, timeout=_TIMEOUT,
        )
        r.raise_for_status()
        data = (r.json().get("data")) or []
        if not data:
            return {}
        row = data[0]
        return {
            "oi_okx_usd": _to_float(row.get("oiUsd")),
            "oi_okx_coin": _to_float(row.get("oiCcy")),
            "oi_okx_contracts": _to_float(row.get("oi")),
            "oi_okx_ts": row.get("ts"),
        }
    except Exception:  # noqa: BLE001
        return {}


def _fetch_okx_long_short(ccy: str) -> Dict[str, Any]:
    """OKX rubik long-short-account-ratio → 최신 롱숏 비율(이미 롱/숏 값). newest-first 배열.

    실패 시 빈 dict (롱숏비는 Bybit 만으로도 충분 — graceful).
    """
    try:
        r = requests.get(
            "https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio",
            params={"ccy": ccy, "period": "1H"},
            headers=_HEADERS, timeout=_TIMEOUT,
        )
        r.raise_for_status()
        data = (r.json().get("data")) or []
        if not data:
            return {}
        # data: [[ts, ratio], ...] newest-first
        first = data[0]
        ratio = _to_float(first[1]) if len(first) >= 2 else None
        return {
            "long_short_ratio_okx": round(ratio, 4) if ratio is not None else None,
            "ls_ts_okx": first[0] if first else None,
        }
    except Exception:  # noqa: BLE001
        return {}


def _collect_asset(cfg: Dict[str, str]) -> Dict[str, Any]:
    """단일 자산(BTC/ETH) 의 OI + 롱숏 4 source 집계. 부분 실패 graceful."""
    asset: Dict[str, Any] = {}
    asset.update(_fetch_bybit_oi(cfg["bybit"]))
    asset.update(_fetch_okx_oi(cfg["okx_inst"]))
    asset.update(_fetch_bybit_long_short(cfg["bybit"]))
    asset.update(_fetch_okx_long_short(cfg["okx_ccy"]))

    # 대표 롱숏 비율 = Bybit 1차(account-ratio), 없으면 OKX 폴백
    ls = asset.get("long_short_ratio_bybit")
    if ls is None:
        ls = asset.get("long_short_ratio_okx")
    asset["long_short_ratio"] = ls

    # 거래소별 OI(USD)가 둘 다 있으면 합산 명목(USD) 함께 노출 (raw 합산, 동일 단위 검증됨)
    bybit_usd = asset.get("oi_bybit_usd")
    okx_usd = asset.get("oi_okx_usd")
    if bybit_usd is not None or okx_usd is not None:
        asset["oi_combined_usd"] = (bybit_usd or 0.0) + (okx_usd or 0.0)

    # 데이터 한 조각이라도 있으면 ok
    asset["ok"] = any(
        asset.get(k) is not None
        for k in ("oi_bybit_usd", "oi_okx_usd", "long_short_ratio")
    )
    asset["as_of"] = asset.get("oi_okx_ts") or asset.get("ls_ts_bybit")
    return asset


def collect_crypto_positioning() -> Dict[str, Any]:
    """BTC/ETH 선물 포지셔닝(OI + 롱숏 비율) 수집.

    항상 dict 반환, 절대 raise 안 함. 부분 실패는 graceful (있는 데이터만 채움).

    반환:
      ok        : bool — BTC/ETH 중 1개라도 데이터 있으면 True
      ok_count  : int  — 데이터 확보한 자산 수 (0~2)
      source    : str  — "bybit+okx"
      btc / eth : dict — 자산별 포지셔닝
          oi_bybit_usd       : Bybit OI 명목가치(USD)
          oi_bybit_coin      : Bybit OI 코인 단위
          oi_okx_usd         : OKX OI 명목가치(USD)
          oi_okx_coin        : OKX OI 코인 단위(oiCcy)
          oi_okx_contracts   : OKX OI 계약 수
          oi_combined_usd    : Bybit+OKX OI(USD) 합산 명목(raw, 동일 단위)
          long_short_ratio   : 대표 롱숏 비율 (Bybit 1차 → OKX 폴백)
          long_short_ratio_bybit / _okx : 거래소별 롱숏 비율
          long_account_pct_bybit / short_account_pct_bybit : Bybit 원시 롱/숏 비중
          as_of              : 최신 타임스탬프(ms, 거래소 raw)
      실패 시     : {"ok": False, "ok_count": 0, "error": "<짧은 사유>", "source": "bybit+okx"}
    """
    try:
        result: Dict[str, Any] = {"source": _SOURCE}
        ok_count = 0
        for name, cfg in _ASSETS.items():
            asset = _collect_asset(cfg)
            result[name] = asset
            if asset.get("ok"):
                ok_count += 1

        result["ok_count"] = ok_count
        result["ok"] = ok_count >= 1
        if ok_count == 0:
            return {"ok": False, "ok_count": 0, "error": "all_sources_failed", "source": _SOURCE}
        return result
    except Exception as e:  # noqa: BLE001  — 최종 안전망: 절대 raise 안 함
        return {"ok": False, "ok_count": 0, "error": str(e)[:120], "source": _SOURCE}
