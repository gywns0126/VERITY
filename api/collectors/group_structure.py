"""
GroupStructureScout — 관계회사 지배구조 트리 + 지분가치(NAV) 분석

양방향 데이터 결합:
  상향: hyslrSttus.json  (누가 이 회사를 소유하는가)
  하향: otcprSttus.json  (이 회사가 어디에 투자했는가)

실시간 시가총액 연동 → 지분가치·NAV 할인/할증·sensitivity 계산.
"""
import os
import sys
import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from api.config import DART_API_KEY, DATA_DIR, now_kst
from api.collectors.dart_corp_code import get_corp_code
from api.collectors.DartScout import (
    fetch_major_shareholders,
    fetch_subsidiary_investments,
)
from api.collectors.stock_data import (
    ALL_STOCKS,
    get_equity_last_price,
)

GROUP_STRUCTURE_PATH = os.path.join(DATA_DIR, "group_structure.json")


# ── 상장사 역매핑 (회사명 → ticker_yf) ───────────────────

def _build_name_to_ticker() -> Dict[str, str]:
    """ALL_STOCKS 이름 → yfinance 티커 역매핑.
    'LG전자' → '066570.KS', '에코프로' → '086520.KQ' 등.
    """
    out: Dict[str, str] = {}
    for ticker_yf, name in ALL_STOCKS.items():
        out[name] = ticker_yf
        cleaned = re.sub(r"\s+", "", name)
        if cleaned != name:
            out[cleaned] = ticker_yf
    return out


_NAME_TO_TICKER: Optional[Dict[str, str]] = None


def _get_name_to_ticker() -> Dict[str, str]:
    global _NAME_TO_TICKER
    if _NAME_TO_TICKER is None:
        _NAME_TO_TICKER = _build_name_to_ticker()
    return _NAME_TO_TICKER


def _resolve_ticker(name: str) -> Optional[str]:
    """회사명에서 yfinance 티커를 추론. 매칭 실패 시 None."""
    n2t = _get_name_to_ticker()
    if name in n2t:
        return n2t[name]
    cleaned = re.sub(r"\s+", "", name)
    if cleaned in n2t:
        return n2t[cleaned]
    stripped = re.sub(r"\(주\)|\(유\)|주식회사", "", name).strip()
    if stripped in n2t:
        return n2t[stripped]
    for stock_name, ticker in n2t.items():
        if stripped and stripped in stock_name:
            return ticker
    return None


def _get_market_cap(ticker_yf: str) -> Optional[float]:
    """시가총액(억원) 조회. yfinance info 우선, 실패 시 가격*발행주식수 근사."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker_yf)
        info = t.info or {}
        mc = info.get("marketCap")
        if mc and mc > 0:
            return round(mc / 1e8, 1)
    except Exception:
        pass
    price = get_equity_last_price(ticker_yf)
    if price and price > 0:
        try:
            import yfinance as yf
            t = yf.Ticker(ticker_yf)
            info = t.info or {}
            shares = info.get("sharesOutstanding", 0) or 0
            if shares > 0:
                return round(price * shares / 1e8, 1)
        except Exception:
            pass
    return None


# ── 엔티티 외부 링크 자동 생성 (best-effort) ─────────────

def _build_entity_links(name: str, ticker_yf: Optional[str] = None) -> Dict[str, str]:
    """대주주/자회사 이름 → 공식 사이트·나무위키·프로필 링크."""
    links: Dict[str, str] = {}
    from urllib.parse import quote

    links["namuwiki"] = f"https://namu.wiki/w/{quote(name)}"

    if ticker_yf:
        symbol = ticker_yf.split(".")[0]
        corp_code = get_corp_code(ticker_yf)
        if corp_code:
            links["profile"] = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo=&dcmNo=&command=searchCompanyInfoDetail&corpCode={corp_code}"
        if ticker_yf.endswith((".KS", ".KQ")):
            links["official"] = f"https://finance.naver.com/item/main.naver?code={symbol}"
        else:
            links["official"] = f"https://finance.yahoo.com/quote/{ticker_yf}"

    return links


# ── 단일 종목 관계회사 구조 수집 ─────────────────────────

def build_group_structure(
    ticker_yf: str,
    bsns_year: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """단일 종목의 관계회사 구조도 + NAV 분석을 반환.

    Returns:
        {
          "ticker": "005930",
          "name": "삼성전자",
          "group_name": "삼성",
          "parent": {...} or None,
          "subsidiaries": [...],
          "nav_analysis": {...},
          "collected_at": "..."
        }
    """
    if not DART_API_KEY:
        return None

    corp_code = get_corp_code(ticker_yf)
    if not corp_code:
        return None

    now = now_kst()
    if bsns_year is None:
        bsns_year = str(now.year - 1)

    ticker_6 = ticker_yf.split(".")[0]
    name = ALL_STOCKS.get(ticker_yf, ticker_yf)

    # 상향: 대주주 현황 — 상위 5명
    parent_info = None
    major_shareholders: List[Dict[str, Any]] = []
    group_name = None
    try:
        shareholders = fetch_major_shareholders(corp_code, bsns_year)
        if shareholders:
            seen_names: set = set()
            for sh in shareholders:
                sh_name = (sh.get("nm") or "").strip()
                if not sh_name or sh_name in seen_names:
                    continue
                seen_names.add(sh_name)
                sh_relate = (sh.get("relate") or "").strip()
                rate_str = (sh.get("stock_rate") or "0").replace(",", "").strip()
                try:
                    rate = float(rate_str)
                except ValueError:
                    rate = 0.0
                if rate <= 0:
                    continue

                sh_ticker = _resolve_ticker(sh_name)
                sh_mcap = _get_market_cap(sh_ticker) if sh_ticker else None
                links = _build_entity_links(sh_name, sh_ticker)

                entry = {
                    "name": sh_name,
                    "relate": sh_relate,
                    "ownership_pct": round(rate, 2),
                    "symbol": sh_ticker.split(".")[0] if sh_ticker else None,
                    "ticker_yf": sh_ticker,
                    "market_cap": sh_mcap,
                    "links": links,
                }
                major_shareholders.append(entry)
                if len(major_shareholders) >= 5:
                    break

            major_shareholders.sort(key=lambda x: x["ownership_pct"], reverse=True)
            if major_shareholders:
                parent_info = major_shareholders[0]

            group_candidates = [major_shareholders[0]["name"]] if major_shareholders else []
            for sh in shareholders:
                r = (sh.get("relate") or "").strip()
                if "최대주주" in r or "계열회사" in r:
                    group_candidates.append((sh.get("nm") or "").strip())
            group_name = _infer_group_name(group_candidates, name)
    except Exception:
        pass

    # 하향: 타법인 출자 현황
    subsidiaries: List[Dict[str, Any]] = []
    try:
        investments = fetch_subsidiary_investments(corp_code, bsns_year)
        for inv in investments:
            inv_name = inv.get("inv_corp_name", "")
            if not inv_name:
                continue
            sub_ticker = _resolve_ticker(inv_name)
            sub_market_cap = None
            sub_price = None
            is_listed = False

            if sub_ticker:
                is_listed = True
                sub_market_cap = _get_market_cap(sub_ticker)
                sub_price = get_equity_last_price(sub_ticker)

            ownership_pct = inv.get("ownership_pct", 0.0)
            book_val = inv.get("book_value", 0)
            fair_val = inv.get("fair_value", 0)

            stake_value = None
            if is_listed and sub_market_cap and ownership_pct > 0:
                stake_value = round(sub_market_cap * ownership_pct / 100, 1)
            elif fair_val and fair_val > 0:
                stake_value = round(fair_val / 1e8, 1)
            elif book_val and book_val > 0:
                stake_value = round(book_val / 1e8, 1)

            sub_links = _build_entity_links(inv_name, sub_ticker)
            subsidiaries.append({
                "name": inv_name,
                "symbol": sub_ticker.split(".")[0] if sub_ticker else None,
                "ticker_yf": sub_ticker,
                "is_listed": is_listed,
                "ownership_pct": round(ownership_pct, 2),
                "end_balance_qty": inv.get("end_balance_qty", 0),
                "book_value_억": round(book_val / 1e8, 1) if book_val else 0,
                "fair_value_억": round(fair_val / 1e8, 1) if fair_val else 0,
                "market_cap_억": sub_market_cap,
                "stake_value_억": stake_value,
                "price": sub_price,
                "revenue_억": round(inv.get("recent_biz_year_revenue", 0) / 1e8, 1),
                "profit_억": round(inv.get("recent_biz_year_profit", 0) / 1e8, 1),
                "links": sub_links,
            })
    except Exception:
        pass

    if not parent_info and not subsidiaries:
        return None

    subsidiaries.sort(key=lambda s: s.get("stake_value_억") or 0, reverse=True)

    # NAV 분석
    my_market_cap = _get_market_cap(ticker_yf)
    nav_analysis = _compute_nav_analysis(my_market_cap, subsidiaries)

    return {
        "ticker": ticker_6,
        "name": name,
        "group_name": group_name,
        "parent": parent_info,
        "major_shareholders": major_shareholders,
        "subsidiaries": subsidiaries,
        "nav_analysis": nav_analysis,
        "market_cap_억": my_market_cap,
        "collected_at": now.isoformat(),
    }


# ── 그룹명 추론 ─────────────────────────────────────────

_GROUP_PREFIXES = [
    "삼성", "SK", "LG", "현대", "롯데", "한화", "GS", "CJ", "LS",
    "HD", "두산", "카카오", "네이버", "KT", "포스코", "셀트리온",
    "에코프로", "한진", "효성", "대한항공", "미래에셋", "신세계",
]


def _infer_group_name(
    names: List[str], company_name: str
) -> Optional[str]:
    all_names = names + [company_name]
    for prefix in _GROUP_PREFIXES:
        for n in all_names:
            if n.startswith(prefix):
                return prefix
    if names:
        first = names[0]
        if len(first) <= 10:
            return first
    return None


# ── NAV 분석 엔진 ────────────────────────────────────────

def _compute_nav_analysis(
    my_market_cap: Optional[float],
    subsidiaries: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """지분가치 합산(Sum-of-Parts) NAV 분석.

    Returns:
        {
          "sum_of_parts_억": float,
          "listed_stake_value_억": float,
          "unlisted_stake_value_억": float,
          "current_market_cap_억": float or None,
          "nav_discount_pct": float or None,   (음수=할인, 양수=할증)
          "sensitivity": [{subsidiary, impact_per_1pct}, ...]
        }
    """
    listed_total = 0.0
    unlisted_total = 0.0
    sensitivity: List[Dict[str, Any]] = []

    for sub in subsidiaries:
        sv = sub.get("stake_value_억") or 0
        if sub.get("is_listed"):
            listed_total += sv
            if my_market_cap and my_market_cap > 0 and sv > 0:
                impact = round(sv / my_market_cap * 0.01 * 100, 4)
                sensitivity.append({
                    "subsidiary": sub["name"],
                    "symbol": sub.get("symbol"),
                    "stake_value_억": sv,
                    "impact_per_1pct": round(impact, 4),
                })
        else:
            unlisted_total += sv

    sop = round(listed_total + unlisted_total, 1)

    discount_pct = None
    if my_market_cap and my_market_cap > 0 and sop > 0:
        discount_pct = round((my_market_cap - sop) / sop * 100, 1)

    sensitivity.sort(key=lambda x: abs(x.get("impact_per_1pct", 0)), reverse=True)

    return {
        "sum_of_parts_억": sop,
        "listed_stake_value_억": round(listed_total, 1),
        "unlisted_stake_value_억": round(unlisted_total, 1),
        "current_market_cap_억": my_market_cap,
        "nav_discount_pct": discount_pct,
        "sensitivity": sensitivity[:10],
    }


# ── 배치 수집 ────────────────────────────────────────────

def collect_group_structures(
    candidates: List[Dict[str, Any]],
    bsns_year: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """후보 종목 리스트에 대해 관계회사 구조를 수집.

    Args:
        candidates: main.py의 추천 후보 리스트 (ticker, ticker_yf, name 키 필요)
        bsns_year: 사업연도 (기본 전년도)

    Returns:
        { "005930": { ...group_structure... }, ... }
    """
    results: Dict[str, Dict[str, Any]] = {}
    total = len(candidates)

    for i, stock in enumerate(candidates, 1):
        ticker_yf = stock.get("ticker_yf", "")
        if not ticker_yf:
            ticker_6 = stock.get("ticker", "")
            market = stock.get("market", "KOSPI")
            suffix = ".KS" if market == "KOSPI" else ".KQ"
            ticker_yf = f"{ticker_6}{suffix}"

        name = stock.get("name", ticker_yf)
        print(f"  [{i}/{total}] {name} 관계회사 구조 수집...", end="")

        try:
            gs = build_group_structure(ticker_yf, bsns_year)
            if gs:
                results[gs["ticker"]] = gs
                n_sub = len(gs.get("subsidiaries") or [])
                grp = gs.get("group_name") or "?"
                print(f" OK (그룹: {grp}, 자회사: {n_sub}개)")
            else:
                print(" 관계회사 없음")
        except Exception as e:
            print(f" 오류: {e}")

    return results


def save_group_structures(data: Dict[str, Dict[str, Any]]) -> str:
    """group_structure.json으로 저장."""
    output = {
        "updated_at": now_kst().isoformat(),
        "count": len(data),
        "structures": data,
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(GROUP_STRUCTURE_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    return GROUP_STRUCTURE_PATH


def load_group_structures() -> Dict[str, Dict[str, Any]]:
    """저장된 group_structure.json 로드. 없으면 빈 dict."""
    if not os.path.exists(GROUP_STRUCTURE_PATH):
        return {}
    try:
        with open(GROUP_STRUCTURE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("structures", {})
    except Exception:
        return {}


def attach_group_structure_to_candidates(
    candidates: List[Dict[str, Any]],
    structures: Dict[str, Dict[str, Any]],
) -> int:
    """candidates 각 종목에 group_structure 키를 삽입. 반환: 매칭 건수."""
    count = 0
    for stock in candidates:
        ticker_6 = stock.get("ticker", "")
        gs = structures.get(ticker_6)
        if gs:
            stock["group_structure"] = {
                "group_name": gs.get("group_name"),
                "parent": gs.get("parent"),
                "major_shareholders": gs.get("major_shareholders", []),
                "subsidiaries": gs.get("subsidiaries", []),
                "nav_analysis": gs.get("nav_analysis", {}),
                "market_cap_억": gs.get("market_cap_억"),
            }
            count += 1
    return count
