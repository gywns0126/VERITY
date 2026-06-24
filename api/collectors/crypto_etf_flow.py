"""
크립토 현물 ETF 자금흐름 센서 — 주식 ETFFlow 대응 (자금흐름 갭 메움).

목적: BTC / ETH 현물 ETF 순자금흐름(net inflow) + 누적 순유입 + 운용자산(AUM).
      주식 ETF 자금흐름 렌즈(PublicETFFlow)의 크립토 대응물.

소스: SoSoValue OpenAPI (https://openapi.sosovalue.com/openapi/v1).
  · 공식 문서: https://sosovalue.gitbook.io/soso-value-api-doc (2.-etf/etf.md)
  · 인증: 헤더 `x-soso-api-key: <KEY>` (무료 plan 발급 가능)
  · 무료 plan = 히스토리 최근 1개월 한정. 매일 cron 누적으로 자체 trail 화 의도.

확정 endpoint (문서 verbatim, 2026-06-24 WebFetch 확인):
  GET /etfs/summary-history?symbol=BTC&country_code=US&limit=50
    응답: [{date, total_net_inflow, total_value_traded, total_net_assets, cum_net_inflow}, ...]
      · date              : "yyyy-MM-dd" (거래일)
      · total_net_inflow  : 당일 전체 ETF 순유입 USD (음수=순유출)
      · total_net_assets  : 전체 ETF 순자산(AUM) USD
      · cum_net_inflow    : ETF 출시 이후 누적 순유입 USD
    · symbol 허용값: BTC, ETH, SOL, LTC, HBAR, XRP, DOGE, LINK, AVAX, DOT
    · country_code 허용값: "US" | "HK"
    · 파라미터는 query string (POST/JSON body 아님 — 문서 확정)

미확정 (추측 금지 — TODO verify 로 표시):
  · by_issuer (발행사별 순유입/AUM): /etfs (GET) 응답은 ticker/name/exchange 만 제공,
    발행사별 flow 수치 없음. 발행사별 수치는 /etfs/{ticker}/market-snapshot 를 ticker 마다
    호출해야 하나, ticker 식별자 enum 이 문서에 명시되지 않음. 미구현(아래 _fetch_by_issuer 참조).
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests

_TIMEOUT = 12
_BASE = "https://openapi.sosovalue.com/openapi/v1"
_HEADERS = {
    "User-Agent": "Verity-Terminal/1.0",
    "Accept": "application/json",
}

# 정렬 응답이 오래된→최신인지 최신→오래된인지 문서 미명시.
# date 문자열("yyyy-MM-dd") 로 직접 max 를 취해 "가장 최신 행" 을 안전하게 선택한다.
_SYMBOLS = {"btc": "BTC", "eth": "ETH"}


def collect_crypto_etf_flow() -> Dict[str, Any]:
    """BTC/ETH 현물 ETF 순자금흐름 수집. 항상 dict 반환, raise 0, graceful.

    반환 schema:
      {
        "ok": bool,                      # 1개 자산이라도 성공하면 True
        "error": str (실패/키없음 시),
        "btc": {daily_net_inflow_usd, cumulative_net_inflow_usd,
                total_aum_usd, as_of},   # 개별 실패 시 {"ok": False, ...}
        "eth": {동일},
        "by_issuer": [...] | None,       # 현재 미구현(소스 enum 미확정) — None
        "source": "sosovalue",
      }
    """
    api_key = os.environ.get("SOSOVALUE_API_KEY")
    if not api_key:
        # 가드: 키 없으면 라이브 호출 자체를 시도하지 않는다.
        return {"ok": False, "error": "no_api_key"}

    result: Dict[str, Any] = {"source": "sosovalue"}

    btc = _fetch_summary(api_key, _SYMBOLS["btc"])
    eth = _fetch_summary(api_key, _SYMBOLS["eth"])
    result["btc"] = btc
    result["eth"] = eth

    # by_issuer: 소스 enum 미확정으로 미구현. 거짓 데이터 대신 None.
    result["by_issuer"] = _fetch_by_issuer(api_key)

    ok_count = sum(1 for v in (btc, eth) if v.get("ok"))
    result["ok"] = ok_count >= 1
    result["ok_count"] = ok_count
    if ok_count == 0:
        # 둘 다 실패했을 때 상위 레벨 error 노출(상세는 각 자산 dict 에 보존).
        result["error"] = btc.get("error") or eth.get("error") or "all_failed"
    return result


def _fetch_summary(api_key: str, symbol: str) -> Dict[str, Any]:
    """단일 자산(BTC/ETH) 현물 ETF summary-history 의 최신 1행을 가져온다.

    GET /etfs/summary-history?symbol=<symbol>&country_code=US&limit=50
    응답 배열에서 date 가 가장 큰(=가장 최신) 행을 선택.
    """
    headers = dict(_HEADERS)
    headers["x-soso-api-key"] = api_key
    try:
        r = requests.get(
            f"{_BASE}/etfs/summary-history",
            params={"symbol": symbol, "country_code": "US", "limit": 50},
            headers=headers,
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        payload = r.json()

        # TODO verify: 문서 예시는 최상위가 배열이나, 실제 응답이
        # {"data": [...]} 또는 {"code":..,"data":[...]} 래퍼일 가능성.
        # 라이브 키 없어 미검증 — 배열/래퍼 양쪽을 모두 허용한다.
        rows = _extract_rows(payload)
        if not rows:
            return {"ok": False, "error": "empty", "symbol": symbol}

        latest = _latest_row(rows)
        if latest is None:
            return {"ok": False, "error": "no_dated_row", "symbol": symbol}

        return {
            "ok": True,
            "symbol": symbol,
            "daily_net_inflow_usd": _num(latest.get("total_net_inflow")),
            "cumulative_net_inflow_usd": _num(latest.get("cum_net_inflow")),
            "total_aum_usd": _num(latest.get("total_net_assets")),
            "as_of": latest.get("date"),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:120], "symbol": symbol}


def _fetch_by_issuer(api_key: str) -> Optional[List[Dict[str, Any]]]:
    """발행사별 순유입/AUM breakdown.

    TODO verify: SoSoValue 무료 plan 에서 발행사별 flow 를 한 번에 주는 endpoint
    미확인. /etfs (GET) 는 ticker/name/exchange 만 제공(수치 없음).
    /etfs/{ticker}/market-snapshot 를 ticker 마다 호출하면 net_inflow/cum_inflow/
    net_assets 를 얻을 수 있으나, ticker 식별자 enum 이 문서 미명시.
    추측으로 ticker 목록을 하드코딩하지 않는다. 확정 전까지 None 반환.
    """
    return None


def _extract_rows(payload: Any) -> List[Dict[str, Any]]:
    """응답을 행 리스트로 정규화. 배열/래퍼({"data":[...]}) 양쪽 허용."""
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        # 단일 객체 응답이면 그대로 1행 취급.
        if data is None and payload.get("date"):
            return [payload]
    return []


def _latest_row(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """date("yyyy-MM-dd") 문자열 최대값 행을 최신으로 선택(정렬 방향 무관)."""
    dated = [r for r in rows if r.get("date")]
    if not dated:
        return None
    return max(dated, key=lambda r: str(r.get("date")))


def _num(v: Any) -> Optional[float]:
    """숫자 안전 변환 — 실패 시 None."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
