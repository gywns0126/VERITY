"""코인/프로토콜 펀더멘털 — 매출(revenue)/수수료(fees)/TVL 팩트 수집.

주식의 재무제표(매출·이익)에 대응하는 코인 쪽 "펀더멘털" 갭을 메우는 collector.
DefiLlama 무료 API(api.llama.fi, 무인증)에서 프로토콜 수수료/매출과 체인 TVL을 수집한다.

🚨 RULE 7 (자기 산식 노출 = 가설): 여기서는 **사실 숫자만** 적재한다.
   점수·등급·매수신호 0. fees/revenue/TVL 는 DefiLlama 가 발표하는 외부 1차 수치 그대로.

소스 (모두 실호출 schema 검증 완료, 2026-06-24):
  - 프로토콜 수수료: https://api.llama.fi/overview/fees?excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true
      → protocols[] 각 항목에 total24h / total7d / name / category / chains
  - 프로토콜 매출:   같은 endpoint + &dataType=dailyRevenue  (별도 호출, name/slug 로 조인)
  - 프로토콜 TVL:    https://api.llama.fi/protocols  (slug → tvl 룩업 맵)
  - 체인 TVL:        https://api.llama.fi/v2/chains   (list[{name, tvl, ...}])

Attribution: 데이터 출처 = DefiLlama (https://defillama.com), 무료 공개 API.
  DefiLlama 데이터는 비상업 attribution 전제 공개. 캐싱/표시 시 출처 표기 의무.

기존 crypto_macro.py / crypto_news.py collector 계약 정합:
  표준 라이브러리 + requests 만, 외부 의존 추가 없음. 항상 dict 반환, 절대 raise 안 함.
"""
from __future__ import annotations

from typing import Any, Dict, List

import requests

# DefiLlama 무료 공개 API (무인증). 출처 표기 의무.
_BASE = "https://api.llama.fi"
_TIMEOUT = 15
_HEADERS = {"User-Agent": "Verity-Terminal/1.0"}
_ATTRIBUTION = "DefiLlama (defillama.com)"


def _num(v: Any) -> float:
    """None / 비숫자 → 0.0 으로 안전 변환."""
    try:
        if v is None:
            return 0.0
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _fetch_fees(data_type: str = "") -> List[Dict[str, Any]]:
    """fees overview 의 protocols 배열을 반환. data_type='dailyRevenue' 시 매출.

    실패 시 빈 리스트(부분 실패 graceful — 호출부가 흡수).
    """
    url = (
        f"{_BASE}/overview/fees"
        "?excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true"
    )
    if data_type:
        url += f"&dataType={data_type}"
    try:
        r = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json().get("protocols", []) or []
    except Exception:  # noqa: BLE001
        return []


def _fetch_tvl_map() -> Dict[str, float]:
    """slug → TVL 룩업 맵 (https://api.llama.fi/protocols). 실패 시 빈 맵."""
    try:
        r = requests.get(f"{_BASE}/protocols", headers=_HEADERS, timeout=_TIMEOUT)
        r.raise_for_status()
        out: Dict[str, float] = {}
        for p in r.json() or []:
            slug = p.get("slug")
            if slug:
                out[slug] = _num(p.get("tvl"))
        return out
    except Exception:  # noqa: BLE001
        return {}


def _fetch_chains(top_n: int) -> Dict[str, Any]:
    """체인 TVL 상위 (https://api.llama.fi/v2/chains).

    반환 {"chains": 상위 top_n, "total": 원본 체인 수}. 실패 시 {"chains": [], "total": 0}.
    """
    try:
        r = requests.get(f"{_BASE}/v2/chains", headers=_HEADERS, timeout=_TIMEOUT)
        r.raise_for_status()
        rows = r.json() or []
        chains = [
            {"name": c.get("name", ""), "tvl": _num(c.get("tvl"))}
            for c in rows
            if c.get("name")
        ]
        chains.sort(key=lambda x: x["tvl"], reverse=True)
        return {"chains": chains[:top_n], "total": len(chains)}
    except Exception:  # noqa: BLE001
        return {"chains": [], "total": 0}


def collect_crypto_defillama(top_n: int = 20) -> Dict[str, Any]:
    """코인/프로토콜 펀더멘털 수집 (수수료·매출·TVL).

    항상 dict 반환, 절대 raise 안 함. 부분 실패는 graceful (있는 데이터만 채움).

    반환:
      ok          : bool — 데이터(프로토콜 또는 체인) 1개라도 있으면 True
      source      : str  — DefiLlama 출처 attribution
      protocols   : list — fees_24h 기준 상위 top_n
                    [{name, category, chains, fees_24h, fees_7d, revenue_24h, tvl}]
      chains      : list — TVL 기준 상위 top_n  [{name, tvl}]
      counts      : dict — 원본 모집단 크기(디버그/관측용)
      실패 시       : {"ok": False, "error": "<짧은 사유>"}
    """
    try:
        fee_protos = _fetch_fees()             # 수수료 모집단
        rev_protos = _fetch_fees("dailyRevenue")  # 매출 모집단
        tvl_map = _fetch_tvl_map()             # slug → tvl
        chains_res = _fetch_chains(top_n)
        chains = chains_res["chains"]

        # 매출 룩업 맵: name / slug 양쪽으로 키 (조인 누락 최소화)
        rev_map: Dict[str, float] = {}
        for p in rev_protos:
            v24 = _num(p.get("total24h"))
            nm = p.get("name")
            sl = p.get("slug")
            if nm:
                rev_map[nm] = v24
            if sl:
                rev_map.setdefault(sl, v24)

        protocols: List[Dict[str, Any]] = []
        for p in fee_protos:
            name = p.get("name")
            if not name:
                continue
            slug = p.get("slug")
            chains_list = p.get("chains") or []
            protocols.append({
                "name": name,
                "category": p.get("category"),
                "chains": chains_list,
                "fees_24h": _num(p.get("total24h")),
                "fees_7d": _num(p.get("total7d")),
                "revenue_24h": rev_map.get(name, rev_map.get(slug, 0.0)),
                "tvl": tvl_map.get(slug, 0.0) if slug else 0.0,
            })

        # 수수료 24h 기준 정렬 → 상위 top_n
        protocols.sort(key=lambda x: x["fees_24h"], reverse=True)
        protocols = protocols[:top_n]

        ok = bool(protocols or chains)
        if not ok:
            return {"ok": False, "error": "no_data_from_defillama"}

        return {
            "ok": True,
            "source": _ATTRIBUTION,
            "protocols": protocols,
            "chains": chains,
            "counts": {
                "fee_protocols_total": len(fee_protos),
                "revenue_protocols_total": len(rev_protos),
                "chains_total": chains_res["total"],
                "tvl_map_size": len(tvl_map),
            },
        }
    except Exception as e:  # noqa: BLE001  — 최종 안전망: 절대 raise 안 함
        return {"ok": False, "error": str(e)[:120]}
