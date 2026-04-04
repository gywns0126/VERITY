"""
네이버 증권 종목 메인 페이지에서 증권사 컨센서스(투자의견·목표주가·연간 실적 추정)만 추출.
전체 HTML이 아니라 해당 테이블만 파싱.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

NAVER_ITEM_MAIN = "https://finance.naver.com/item/main.naver"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}


def _clean_int(text: str) -> Optional[int]:
    s = re.sub(r"[^\d\-]", "", text.replace(",", ""))
    if not s or s == "-":
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _clean_float(text: str) -> Optional[float]:
    s = text.replace(",", "").strip()
    if not s or s == "-" or s.upper() == "N/A":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_opinion_target(td) -> Tuple[Optional[float], str, Optional[int]]:
    """투자의견 행의 단일 <td>에서 의견 점수·라벨·목표가 파싱."""
    text = td.get_text(" ", strip=True)
    if re.search(r"N/A", text, re.I) and not re.search(r"\d{2,}", text.replace(",", "")):
        return None, "N/A", None

    target = None
    m_price = re.search(r"([\d,]+)\s*$", text.replace("l", " "))
    if m_price:
        target = _clean_int(m_price.group(1))

    opinion_num: Optional[float] = None
    label = "N/A"
    m_op = re.search(
        r"([\d.]+)\s*(매수|매도|중립|보유|강력매수|강력 매수)",
        text,
    )
    if m_op:
        opinion_num = _clean_float(m_op.group(1))
        label = m_op.group(2).replace(" ", "")
    else:
        for kw in ("매수", "매도", "중립", "보유"):
            if kw in text:
                label = kw
                break

    if label == "N/A" and target is None:
        return None, "N/A", None
    return opinion_num, label, target


def _find_analysis_table(soup: BeautifulSoup):
    for table in soup.find_all("table"):
        cap = table.find("caption")
        if cap and "기업실적분석" in cap.get_text():
            return table
    return None


def _annual_estimate_cells(tr) -> List[str]:
    """매출/영업이익 행에서 연간 4컬럼(실적 3 + 추정 E 1) 셀 텍스트."""
    tds = tr.find_all("td")
    if len(tds) < 4:
        return []
    return [td.get_text(" ", strip=True) for td in tds[:4]]


def _parse_financial_estimates(soup: BeautifulSoup) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "sales_prior_year_bn": None,
        "sales_estimate_bn": None,
        "operating_profit_prior_year_bn": None,
        "operating_profit_estimate_bn": None,
        "estimate_year_label": None,
    }
    table = _find_analysis_table(soup)
    if not table:
        return out

    for tr in table.find_all("thead"):
        for row in tr.find_all("tr"):
            texts = [h.get_text(" ", strip=True) for h in row.find_all("th")]
            for t in texts:
                if "E" in t and re.search(r"20\d{2}", t):
                    out["estimate_year_label"] = re.sub(r"\s+", " ", t)
                    break
            if out["estimate_year_label"]:
                break
        if out["estimate_year_label"]:
            break

    for tr in table.find_all("tr"):
        th = tr.find("th")
        if not th:
            continue
        name = th.get_text(" ", strip=True)
        if name == "매출액":
            cells = _annual_estimate_cells(tr)
            if len(cells) >= 4:
                out["sales_prior_year_bn"] = _clean_int(cells[2])
                out["sales_estimate_bn"] = _clean_int(cells[3])
        elif name == "영업이익":
            cells = _annual_estimate_cells(tr)
            if len(cells) >= 4:
                out["operating_profit_prior_year_bn"] = _clean_int(cells[2])
                out["operating_profit_estimate_bn"] = _clean_int(cells[3])

    return out


def _parse_investment_table(soup: BeautifulSoup) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "investment_opinion_numeric": None,
        "investment_opinion": "N/A",
        "target_price": None,
    }
    for table in soup.find_all("table", summary=True):
        if "투자의견 정보" not in (table.get("summary") or ""):
            continue
        trs = table.find_all("tr")
        for tr in trs:
            th = tr.find("th")
            td = tr.find("td")
            if not th or not td:
                continue
            if "투자의견" in th.get_text() and "목표주가" in th.get_text():
                num, label, tgt = _parse_opinion_target(td)
                out["investment_opinion_numeric"] = num
                out["investment_opinion"] = label
                out["target_price"] = tgt
                return out
    return out


def scout_consensus(ticker: str) -> Dict[str, Any]:
    """
    네이버 종목 메인에서 컨센서스 관련 필드만 수집.
    ticker: 6자리 문자열 (예 '005930')
    """
    base: Dict[str, Any] = {
        "ticker": ticker,
        "ok": False,
        "error": None,
        "investment_opinion": "N/A",
        "investment_opinion_numeric": None,
        "target_price": None,
        "sales_prior_year_bn": None,
        "sales_estimate_bn": None,
        "operating_profit_prior_year_bn": None,
        "operating_profit_estimate_bn": None,
        "estimate_year_label": None,
    }

    code = re.sub(r"\D", "", ticker)[:6].zfill(6)
    if len(code) != 6:
        base["error"] = "invalid_ticker"
        return base

    try:
        r = requests.get(
            NAVER_ITEM_MAIN,
            params={"code": code},
            headers=HEADERS,
            timeout=12,
        )
        r.raise_for_status()
    except Exception as e:
        base["error"] = str(e)[:200]
        return base

    soup = BeautifulSoup(r.text, "html.parser")
    inv = _parse_investment_table(soup)
    base.update(inv)
    fin = _parse_financial_estimates(soup)
    for k, v in fin.items():
        if v is not None or k in (
            "sales_prior_year_bn",
            "sales_estimate_bn",
            "operating_profit_prior_year_bn",
            "operating_profit_estimate_bn",
        ):
            base[k] = v

    base["ok"] = True
    return base


def save_consensus_batch(rows: List[Dict[str, Any]], path: str) -> None:
    """수집 결과를 JSON으로 저장 (api.config.DATA_DIR 권장)."""
    import json

    from api.config import now_kst

    out = {
        "updated_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "stocks": rows,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
