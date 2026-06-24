"""스테이블코인 공급/흐름 — 발행사 직접 피드 (USDT + USDC).

스테이블코인 공급량은 크립토 유동성 레짐의 1차 신호다. "발행사 직접 피드"의
provenance 는 최강(공급 숫자 = 발행사가 스스로 보고하는 사실). CoinGecko/DefiLlama
같은 어그리게이터 한 단계를 건너뛰고 발행사 원천을 직접 읽는다.

🚨 RULE 7 (자기 산식 노출 = 가설): 여기서는 **사실 숫자만** 적재한다.
   점수·등급·매수신호 0. 공급량/체인별 분포는 발행사가 발표하는 1차 수치 그대로.

소스 (둘 다 무인증, 2026-06-24 실호출 schema 검증 완료):
  - Tether USDT: https://app.tether.to/transparency.json
      → data.usdt = 평면 dict. 체인별 `totaltokens_<chain>` 키 +
        total_assets / total_liabilities / shareholder_eq. 타임스탬프 필드 없음.
        circulating(유통량)의 가장 정확한 값은 total_liabilities (체인 합산은
        reserve/미발행 토큰 때문에 과대계상됨). data 에는 usdt 외 cnht/xaut/mxnt
        도 있어 usdt 만 사용.
  - Circle USDC: https://api.circle.com/v1/stablecoins
      → data = list. 항목별 {name, symbol, chains:[{amount, chain, updateDate}],
        totalAmount}. EUROC + USDC 둘 다 옴 — symbol == "USDC" 만 사용.
        체인별 updateDate(ISO8601) 존재 → 가장 최신값을 as_of 로 채택.

🚨 라이선스 주의:
   발행사 ToS(Tether / Circle)는 데이터 사용을 비상업(NC) 으로 프레이밍하는 문구를
   포함한다. 다만 공급 숫자 그 자체는 사실(fact) 로서 저작권 대상이 아니며, 여기서는
   파생 집계(체인별/합계) + 명시적 출처표기 형태로만 노출한다. 상업적 재배포 여부는
   PM 판단 영역으로 남긴다(이 모듈은 사실 수집까지만 책임).
   Attribution 표기 의무: Tether (tether.to) / Circle (circle.com).

기존 crypto_macro.py / crypto_defillama.py collector 계약 정합:
  표준 라이브러리 + requests 만, 외부 의존 추가 없음. 항상 dict 반환, 절대 raise 안 함.
"""
from __future__ import annotations

from typing import Any, Dict, List

import requests

_TIMEOUT = 12
_HEADERS = {"User-Agent": "Verity-Terminal/1.0"}

_TETHER_URL = "https://app.tether.to/transparency.json"
_CIRCLE_URL = "https://api.circle.com/v1/stablecoins"

# 출처 attribution (표기 의무 — 라이선스 docstring 참조)
_ATTR_TETHER = "Tether (tether.to)"
_ATTR_CIRCLE = "Circle (circle.com)"

# 체인별 raw 가 많아( USDC 30+ 체인 ) 상위 N개만 노출
_TOP_CHAINS = 12


def _num(v: Any) -> float:
    """None / 비숫자 / 문자열 숫자 → float, 실패 시 0.0."""
    try:
        if v is None:
            return 0.0
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _top_by_chain(rows: List[Dict[str, Any]], top_n: int) -> List[Dict[str, Any]]:
    """supply 내림차순 정렬 후 상위 top_n. 0 공급 체인은 제외."""
    rows = [r for r in rows if r.get("supply", 0) > 0]
    rows.sort(key=lambda x: x["supply"], reverse=True)
    return rows[:top_n]


def _fetch_usdt() -> Dict[str, Any]:
    """Tether USDT 공급 — 발행사 transparency 직접 피드.

    체인별 supply = totaltokens_<chain>. 합계 = total_liabilities(유통량,
    circulating 의 가장 정확한 값). 실패 시 {"ok": False, "error": ...}.
    """
    try:
        r = requests.get(_TETHER_URL, headers=_HEADERS, timeout=_TIMEOUT)
        r.raise_for_status()
        usdt = (r.json().get("data") or {}).get("usdt") or {}
        if not usdt:
            return {"ok": False, "error": "tether_usdt_missing"}

        by_chain: List[Dict[str, Any]] = []
        for k, v in usdt.items():
            if k.startswith("totaltokens_"):
                by_chain.append({"chain": k[len("totaltokens_"):].upper(), "supply": _num(v)})

        # total_liabilities = 유통량(circulating). 체인 합산은 reserve/미발행으로 과대계상.
        liabilities = _num(usdt.get("total_liabilities"))
        chain_sum = sum(c["supply"] for c in by_chain)
        total_supply = liabilities if liabilities > 0 else chain_sum

        return {
            "ok": True,
            "total_supply_usd": total_supply,
            "by_chain": _top_by_chain(by_chain, _TOP_CHAINS),
            "chain_count": len([c for c in by_chain if c["supply"] > 0]),
            "total_assets_usd": _num(usdt.get("total_assets")),
            "total_liabilities_usd": liabilities,
            "chain_sum_usd": chain_sum,  # 참고용(과대계상) — total_supply 와 차이 = reserve/미발행
            "as_of": None,  # Tether transparency.json 은 타임스탬프 미제공
            "source": _ATTR_TETHER,
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:120]}


def _fetch_usdc() -> Dict[str, Any]:
    """Circle USDC 공급 — 발행사 직접 피드.

    data list 에서 symbol == "USDC" 항목만(EUROC 제외). 체인별 updateDate 의
    최신값을 as_of 로 채택. 실패 시 {"ok": False, "error": ...}.
    """
    try:
        r = requests.get(_CIRCLE_URL, headers=_HEADERS, timeout=_TIMEOUT)
        r.raise_for_status()
        items = r.json().get("data") or []
        usdc = next((i for i in items if (i.get("symbol") or "").upper() == "USDC"), None)
        if not usdc:
            return {"ok": False, "error": "circle_usdc_missing"}

        by_chain: List[Dict[str, Any]] = []
        as_of = None
        for c in usdc.get("chains") or []:
            by_chain.append({"chain": (c.get("chain") or "").upper(), "supply": _num(c.get("amount"))})
            ud = c.get("updateDate")
            if ud and (as_of is None or ud > as_of):
                as_of = ud

        total_amount = _num(usdc.get("totalAmount"))
        chain_sum = sum(c["supply"] for c in by_chain)
        total_supply = total_amount if total_amount > 0 else chain_sum

        return {
            "ok": True,
            "total_supply_usd": total_supply,
            "by_chain": _top_by_chain(by_chain, _TOP_CHAINS),
            "chain_count": len([c for c in by_chain if c["supply"] > 0]),
            "as_of": as_of,  # ISO8601, 체인별 updateDate 의 최신값
            "source": _ATTR_CIRCLE,
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:120]}


def collect_crypto_stablecoins() -> Dict[str, Any]:
    """스테이블코인 공급/흐름 수집 (USDT + USDC 발행사 직접 피드).

    항상 dict 반환, 절대 raise 안 함. 부분 실패 graceful — 한쪽만 성공해도 그 데이터는 채움.

    반환:
      ok               : bool — 발행사 1개라도 성공하면 True
      ok_count         : int  — 성공한 발행사 수 (0~2)
      total            : int  — 시도한 발행사 수 (2 고정)
      total_supply_usd : float — 성공한 발행사 total_supply_usd 합 (USDT+USDC 유동성 풀)
      usdt             : dict — {total_supply_usd, by_chain, as_of, ...} 또는 {ok:False,...}
      usdc             : dict — {total_supply_usd, by_chain, as_of, ...} 또는 {ok:False,...}
      sources          : list — attribution (표기 의무)
      전부 실패 시        : {"ok": False, "error": "..."} (+ usdt/usdc 진단 포함)
    """
    usdt = _fetch_usdt()
    usdc = _fetch_usdc()

    ok_count = sum(1 for v in (usdt, usdc) if v.get("ok"))
    total_supply = sum(
        v.get("total_supply_usd", 0.0) for v in (usdt, usdc) if v.get("ok")
    )

    if ok_count == 0:
        return {
            "ok": False,
            "error": "all_issuers_failed",
            "ok_count": 0,
            "total": 2,
            "usdt": usdt,
            "usdc": usdc,
        }

    return {
        "ok": True,
        "ok_count": ok_count,
        "total": 2,
        "total_supply_usd": total_supply,
        "usdt": usdt,
        "usdc": usdc,
        "sources": [_ATTR_TETHER, _ATTR_CIRCLE],
    }
