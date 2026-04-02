"""
업종(섹터) 분석 모듈
네이버 금융 업종별 등락률 + 대표종목 수집
"""
import requests
import re
from bs4 import BeautifulSoup


def get_sector_rankings() -> list:
    """코스피 업종별 등락률 + 대표 종목 수집"""
    sectors = _scrape_sector_page("https://finance.naver.com/sise/sise_group.naver?type=upjong", "KOSPI")

    seen = set()
    unique = []
    for s in sectors:
        if s["name"] not in seen:
            seen.add(s["name"])
            unique.append(s)

    unique.sort(key=lambda x: x.get("change_pct", 0), reverse=True)

    for i, s in enumerate(unique):
        if s["change_pct"] > 1.5:
            s["heat"] = "hot"
        elif s["change_pct"] > 0.3:
            s["heat"] = "warm"
        elif s["change_pct"] > -0.3:
            s["heat"] = "neutral"
        elif s["change_pct"] > -1.5:
            s["heat"] = "cool"
        else:
            s["heat"] = "cold"
        s["rank"] = i + 1

    return unique


def _scrape_sector_page(url: str, market: str) -> list:
    sectors = []
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=5)
        resp.encoding = "euc-kr"
        soup = BeautifulSoup(resp.text, "html.parser")

        rows = soup.select("table.type_1 tr")
        for row in rows:
            cols = row.select("td")
            if len(cols) < 4:
                continue
            name_tag = cols[0].select_one("a")
            if not name_tag:
                continue

            name = name_tag.text.strip()
            link = name_tag.get("href", "")
            sector_no = ""
            if "no=" in link:
                sector_no = link.split("no=")[-1]

            try:
                change_text = cols[1].text.strip().replace(",", "").replace("%", "")
                change_pct = float(change_text)
            except (ValueError, IndexError):
                continue

            top_stocks = _get_sector_top_stocks(sector_no) if sector_no else []

            sectors.append({
                "name": name,
                "market": market,
                "change_pct": round(change_pct, 2),
                "top_stocks": top_stocks[:3],
            })
    except Exception:
        pass
    return sectors


def _get_sector_top_stocks(sector_no: str) -> list:
    """업종 상세에서 등락률 상위 종목 3개 추출"""
    stocks = []
    try:
        url = f"https://finance.naver.com/sise/sise_group_detail.naver?type=upjong&no={sector_no}"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=5)
        resp.encoding = "euc-kr"
        soup = BeautifulSoup(resp.text, "html.parser")
        rows = soup.select("table.type_5 tr")
        for row in rows:
            cols = row.select("td")
            if len(cols) < 6:
                continue
            name_tag = cols[0].select_one("a")
            if not name_tag:
                continue
            name = name_tag.text.strip()
            try:
                price_text = cols[1].text.strip().replace(",", "")
                price = int(price_text) if price_text else 0
                chg_text = cols[3].text.strip().replace(",", "").replace("%", "")
                chg = float(chg_text) if chg_text else 0
            except (ValueError, IndexError):
                continue
            stocks.append({"name": name, "price": price, "change_pct": round(chg, 2)})
            if len(stocks) >= 3:
                break
    except Exception:
        pass
    return stocks
