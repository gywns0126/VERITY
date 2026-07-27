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


def _row_cells(tr) -> List[str]:
    """행 전체 셀 텍스트 (연간 + 분기)."""
    return [td.get_text(" ", strip=True) for td in tr.find_all("td")]


def _parse_period_headers(table) -> Tuple[List[str], List[str]]:
    """기업실적분석 thead 에서 (연간 라벨, 분기 라벨) 분리.

    실측 구조 (2026-07-28, 4종목 동일):
      row0: ['주요재무정보', '최근 연간 실적', '최근 분기 실적']   ← colspan 그룹
      row1: ['2023.12','2024.12','2025.12','2026.12 (E)',        ← 연간 4
             '2025.03','2025.06','2025.09','2025.12','2026.03','2026.06 (E)']  ← 분기 6
    그룹 헤더의 colspan 으로 경계를 잡는다 (컬럼 수 하드코딩 회피 — 분기 개수는 종목/시점별 변동 가능).
    """
    thead = table.find("thead")
    if not thead:
        return [], []
    rows = thead.find_all("tr")
    if len(rows) < 2:
        return [], []

    annual_n = None
    for th in rows[0].find_all("th"):
        label = th.get_text(" ", strip=True)
        if "연간" in label:
            try:
                annual_n = int(th.get("colspan") or 0)
            except (TypeError, ValueError):
                annual_n = None
            break

    periods = [h.get_text(" ", strip=True) for h in rows[1].find_all("th")]
    if not annual_n or annual_n <= 0 or annual_n > len(periods):
        return periods, []          # 경계 불명 = 기존 연간 경로만 (안전 degrade)
    return periods[:annual_n], periods[annual_n:]


def _is_estimate_label(label: str) -> bool:
    """'2026.06 (E)' 처럼 추정 표기가 붙은 기간 라벨."""
    return bool(re.search(r"\(\s*E\s*\)", label or ""))


def _parse_financial_estimates(soup: BeautifulSoup) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "sales_prior_year_bn": None,
        "sales_estimate_bn": None,
        "operating_profit_prior_year_bn": None,
        "operating_profit_estimate_bn": None,
        "estimate_year_label": None,
        # 2026-07-28 분기 확장 — 표 부재/구조 변경 시에도 키는 유지(소비처 KeyError 방지).
        "annual_period_labels": [],
        "quarter_period_labels": [],
        "quarter_estimate_labels": [],
        "quarters": [],
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

    # ── 🚨 2026-07-28 — 분기 컬럼 파싱 추가 ──────────────────────────────────
    # 같은 표에 분기 실적/추정이 이미 들어 있는데 _annual_estimate_cells 의 tds[:4] 가 잘라내
    # 버리고 있었음. 신규 소스 0 — 매 run 이미 받던 동일 페이지·동일 요청.
    # earnings_surprise.py 헤더의 KR 차단 사유 2건이 이 실측으로 뒤집힘:
    #   "ConsensusScout 추정치가 연간(E)-only" → 분기 (E) 컬럼 존재 (예: 2026.06 (E))
    #   "순이익 추정 필드도 부재"              → 당기순이익 행 존재
    # 실측 2026-07-28 (000660/005930/035900/100840 4종목 전부 10컬럼 동일 구조).
    # [[feedback_coverage_check_collector_filter_first]] 정합 — 소스가 아니라 수집기 필터 문제.
    annual_labels, quarter_labels = _parse_period_headers(table)
    out["annual_period_labels"] = annual_labels
    out["quarter_period_labels"] = quarter_labels
    out["quarter_estimate_labels"] = [q for q in quarter_labels if _is_estimate_label(q)]

    n_annual = len(annual_labels)
    _ROW_KEYS = {"매출액": "sales", "영업이익": "operating_profit", "당기순이익": "net_income"}
    quarters: Dict[str, Dict[str, Any]] = {}

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

        key = _ROW_KEYS.get(name)
        if key and quarter_labels:
            cells = _row_cells(tr)
            q_cells = cells[n_annual:n_annual + len(quarter_labels)]
            for label, raw in zip(quarter_labels, q_cells):
                quarters.setdefault(
                    label, {"period": label, "is_estimate": _is_estimate_label(label)}
                )[f"{key}_bn"] = _clean_int(raw)

    # 표기 순서(과거→미래) 보존. 값이 전부 None 인 기간은 제외 — 빈 칸을 실측 0 으로 오인 금지.
    out["quarters"] = [
        quarters[l] for l in quarter_labels
        if l in quarters and any(
            quarters[l].get(f"{k}_bn") is not None for k in _ROW_KEYS.values()
        )
    ]

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
