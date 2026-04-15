"""
국내 ETF 시세·수익률 수집 (KRX OpenAPI etf_bydd_trd)
  - 주요 ETF 시세 (종가, 등락률, 거래량, 시총)
  - 카테고리 분류 (국내주식 / 해외주식 / 채권 / 원자재 / 레버리지·인버스 / 섹터)
  - 기간별 수익률: KRX가 단일 일자 스냅샷이므로 당일 등락률만 제공 (1M/3M/1Y는 None)
"""
from datetime import timedelta
from typing import Any, Dict, List, Optional

import requests

from api.config import KRX_API_KEY, now_kst

_BASE_URL = "https://data-dbg.krx.co.kr/svc/apis"
_TIMEOUT = 12

# 관심 ETF 목록: (ticker, name_fallback, category)
_KR_TOP_ETFS = [
    ("069500", "KODEX 200", "equity_domestic"),
    ("229200", "KODEX 코스닥150", "equity_domestic"),
    ("102110", "TIGER 200", "equity_domestic"),
    ("371460", "TIGER 차이나전기차SOLACTIVE", "equity_foreign"),
    ("305720", "KODEX 2차전지산업", "thematic"),
    ("091160", "KODEX 반도체", "thematic"),
    ("381180", "TIGER 미국S&P500", "equity_foreign"),
    ("379800", "KODEX 미국S&P500TR", "equity_foreign"),
    ("379810", "KODEX 미국나스닥100TR", "equity_foreign"),
    ("133690", "TIGER 미국나스닥100", "equity_foreign"),
    ("148070", "KOSEF 국고채10년", "bond_kr"),
    ("152380", "KODEX 국고채3년", "bond_kr"),
    ("304660", "KODEX 미국채울트라30년선물(H)", "bond_us"),
    ("261240", "KODEX 미국채10년선물", "bond_us"),
    ("132030", "KODEX 골드선물(H)", "commodity_gold"),
    ("130680", "TIGER 원유선물Enhanced(H)", "commodity"),
    ("122630", "KODEX 레버리지", "leverage"),
    ("252670", "KODEX 200선물인버스2X", "inverse"),
    ("114800", "KODEX 인버스", "inverse"),
    ("091170", "KODEX 은행", "sector_financial"),
    ("139260", "TIGER 200 IT", "sector_tech"),
    ("117700", "KODEX 건설", "sector"),
    ("143860", "TIGER 헬스케어", "sector"),
    ("266370", "KODEX 배당성장", "dividend"),
    ("364690", "KODEX 미국빅테크10", "thematic"),
]

_TICKER_SET = {t for t, _, _ in _KR_TOP_ETFS}
_TICKER_META = {t: (n, c) for t, n, c in _KR_TOP_ETFS}


def _recent_business_day(offset: int = 0) -> str:
    """KST 기준 최근 평일 YYYYMMDD. offset=1이면 하루 더 앞으로."""
    d = now_kst().date()
    found = 0
    for _ in range(20):
        if d.weekday() < 5:
            if found >= offset:
                return d.strftime("%Y%m%d")
            found += 1
        d -= timedelta(days=1)
    return now_kst().strftime("%Y%m%d")


def _fetch_etf_day(bas_dd: str) -> Dict[str, Dict[str, Any]]:
    """KRX etf_bydd_trd 조회 → {ticker: row_dict}"""
    if not KRX_API_KEY:
        return {}
    try:
        resp = requests.get(
            f"{_BASE_URL}/etp/etf_bydd_trd",
            params={"AUTH_KEY": KRX_API_KEY, "basDd": bas_dd},
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            return {}
        rows = resp.json().get("OutBlock_1", [])
    except Exception:
        return {}

    result: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        raw_cd = str(row.get("ISU_CD") or "").strip()
        ticker = raw_cd[-6:].zfill(6) if len(raw_cd) >= 6 else raw_cd
        result[ticker] = row
    return result


def _parse_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def get_top_etf_summary() -> List[Dict[str, Any]]:
    """
    국내 주요 ETF 시세 요약 (KRX OpenAPI).
    반환: [{ticker, name, category, close, change_pct, volume, aum, nav, returns, updated_at}, ...]
    """
    ts = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")

    # 당일 → 전일 순으로 최대 5거래일 시도
    today_rows: Dict[str, Dict[str, Any]] = {}
    bas_dd_used = ""
    for offset in range(5):
        bas_dd = _recent_business_day(offset)
        today_rows = _fetch_etf_day(bas_dd)
        if today_rows:
            bas_dd_used = bas_dd
            break

    if not today_rows:
        return []

    results: List[Dict[str, Any]] = []
    seen: set = set()

    for ticker, (name_fallback, category) in _TICKER_META.items():
        if ticker in seen:
            continue
        seen.add(ticker)

        row = today_rows.get(ticker)
        if not row:
            continue

        close = _parse_float(row.get("TDD_CLSPRC"))
        if close is None or close <= 0:
            continue

        change_pct = _parse_float(row.get("FLUC_RT"))
        volume = int(_parse_float(row.get("ACC_TRDVOL")) or 0)
        aum = _parse_float(row.get("MKTCAP"))
        nav = _parse_float(row.get("NAV"))
        name = str(row.get("ISU_NM") or name_fallback).strip() or name_fallback

        results.append({
            "ticker": ticker,
            "name": name,
            "category": category,
            "close": close,
            "change_pct": change_pct,
            "volume": volume,
            "aum": int(aum) if aum else None,
            "nav": nav,
            "returns": {"1M": None, "3M": None, "1Y": None},
            "bas_dd": bas_dd_used,
            "updated_at": ts,
        })

    return results


if __name__ == "__main__":
    import json
    data = get_top_etf_summary()
    print(f"수집 ETF: {len(data)}개")
    print(json.dumps(data[:3], ensure_ascii=False, indent=2))
