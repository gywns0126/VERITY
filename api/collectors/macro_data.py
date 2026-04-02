"""
매크로 경제 지표 수집 모듈 v2
거시/미시 동향을 종합 수집:
  거시: VIX, 금리(미10Y/한3Y), 환율, 유가, 금, 글로벌 지수
  미시: 코스피/코스닥 업종 등락, 투자자별 수급, 신용잔고 추이
"""
import yfinance as yf
import requests
import re
from bs4 import BeautifulSoup


def get_macro_indicators() -> dict:
    """주요 매크로 지표 수집"""
    result = {
        "usd_krw": _get_usd_krw(),
        "usd_jpy": _get_fx("JPY=X", "USD/JPY"),
        "eur_usd": _get_fx("EURUSD=X", "EUR/USD"),
        "wti_oil": _get_commodity("CL=F", "WTI 원유"),
        "gold": _get_commodity_with_history("GC=F", "금"),
        "silver": _get_commodity_with_history("SI=F", "은"),
        "copper": _get_commodity("HG=F", "구리"),
        "vix": _get_commodity("^VIX", "VIX 공포지수"),
        "us_10y": _get_commodity("^TNX", "미국 10년물"),
        "us_2y": _get_commodity("^IRX", "미국 2년물"),
        "sp500": _get_index_change("^GSPC", "S&P500"),
        "nasdaq": _get_index_change("^IXIC", "나스닥"),
        "dji": _get_index_change("^DJI", "다우"),
        "nikkei": _get_index_change("^N225", "닛케이"),
        "sse": _get_index_change("000001.SS", "상해종합"),
        "dax": _get_index_change("^GDAXI", "DAX"),
    }

    spread_10_2 = _calc_yield_spread(result)
    result["yield_spread"] = spread_10_2

    result["market_mood"] = _assess_market_mood(result)
    result["macro_diagnosis"] = _build_diagnosis(result)
    result["micro_signals"] = _get_micro_signals()

    return result


def _get_usd_krw() -> dict:
    try:
        t = yf.Ticker("KRW=X")
        hist = t.history(period="5d")
        if len(hist) >= 2:
            current = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2])
            change = round(current - prev, 2)
            pct = round((current - prev) / prev * 100, 2) if prev else 0
            week_high = round(float(hist["Close"].max()), 2)
            week_low = round(float(hist["Close"].min()), 2)
            return {"value": round(current, 2), "change": change, "change_pct": pct, "week_high": week_high, "week_low": week_low}
        elif len(hist) == 1:
            v = round(float(hist["Close"].iloc[-1]), 2)
            return {"value": v, "change": 0, "change_pct": 0, "week_high": v, "week_low": v}
    except Exception:
        pass
    return {"value": 0, "change": 0, "change_pct": 0, "week_high": 0, "week_low": 0}


def _get_fx(ticker: str, name: str) -> dict:
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if len(hist) >= 2:
            current = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2])
            pct = round((current - prev) / prev * 100, 2) if prev else 0
            return {"value": round(current, 4), "change_pct": pct}
    except Exception:
        pass
    return {"value": 0, "change_pct": 0}


def _get_commodity(ticker: str, name: str) -> dict:
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if len(hist) >= 2:
            current = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2])
            change_pct = round(((current - prev) / prev) * 100, 2)
            return {"value": round(current, 2), "change_pct": change_pct}
        elif len(hist) == 1:
            return {"value": round(float(hist["Close"].iloc[-1]), 2), "change_pct": 0}
    except Exception:
        pass
    return {"value": 0, "change_pct": 0}


def _get_commodity_with_history(ticker: str, name: str) -> dict:
    """원자재 시세 + 30일 가격 히스토리 (차트용)"""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1mo")
        if len(hist) >= 2:
            current = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2])
            change_pct = round(((current - prev) / prev) * 100, 2)
            sparkline = [round(float(v), 2) for v in hist["Close"].tolist()]
            high_30d = round(float(hist["Close"].max()), 2)
            low_30d = round(float(hist["Close"].min()), 2)
            return {
                "value": round(current, 2),
                "change_pct": change_pct,
                "sparkline": sparkline[-30:],
                "high_30d": high_30d,
                "low_30d": low_30d,
            }
        elif len(hist) == 1:
            v = round(float(hist["Close"].iloc[-1]), 2)
            return {"value": v, "change_pct": 0, "sparkline": [v], "high_30d": v, "low_30d": v}
    except Exception:
        pass
    return {"value": 0, "change_pct": 0, "sparkline": [], "high_30d": 0, "low_30d": 0}


def _get_index_change(ticker: str, name: str) -> dict:
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if len(hist) >= 2:
            current = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2])
            change_pct = round(((current - prev) / prev) * 100, 2)
            return {"value": round(current, 2), "change_pct": change_pct}
    except Exception:
        pass
    return {"value": 0, "change_pct": 0}


def _calc_yield_spread(data: dict) -> dict:
    """10Y-2Y 금리 스프레드 (경기침체 선행지표)"""
    y10 = data.get("us_10y", {}).get("value", 0)
    y2 = data.get("us_2y", {}).get("value", 0)
    spread = round(y10 - y2, 3) if y10 and y2 else 0
    signal = "정상"
    if spread < 0:
        signal = "역전 (침체 경고)"
    elif spread < 0.3:
        signal = "축소 (경기둔화 신호)"
    return {"value": spread, "signal": signal}


def _assess_market_mood(data: dict) -> dict:
    mood_score = 50

    vix = data.get("vix", {}).get("value", 0)
    if vix > 30:
        mood_score -= 20
    elif vix > 25:
        mood_score -= 10
    elif vix < 15:
        mood_score += 10
    elif vix < 20:
        mood_score += 5

    usd_change = data.get("usd_krw", {}).get("change", 0)
    if usd_change > 10:
        mood_score -= 10
    elif usd_change < -10:
        mood_score += 10

    sp500_chg = data.get("sp500", {}).get("change_pct", 0)
    if sp500_chg > 1:
        mood_score += 10
    elif sp500_chg < -1:
        mood_score -= 10

    us10y = data.get("us_10y", {}).get("change_pct", 0)
    if us10y > 3:
        mood_score -= 5
    elif us10y < -3:
        mood_score += 5

    spread = data.get("yield_spread", {}).get("value", 0.5)
    if spread < 0:
        mood_score -= 10
    elif spread < 0.3:
        mood_score -= 5

    copper_chg = data.get("copper", {}).get("change_pct", 0)
    if copper_chg > 2:
        mood_score += 5
    elif copper_chg < -2:
        mood_score -= 5

    mood_score = max(0, min(100, mood_score))

    if mood_score >= 70:
        label = "강세"
    elif mood_score >= 55:
        label = "낙관"
    elif mood_score >= 45:
        label = "중립"
    elif mood_score >= 30:
        label = "비관"
    else:
        label = "공포"

    return {"score": mood_score, "label": label}


def _build_diagnosis(data: dict) -> list:
    """현재 매크로 상황을 한줄씩 요약하는 진단 리스트"""
    diags = []

    vix = data.get("vix", {}).get("value", 0)
    if vix > 30:
        diags.append({"type": "risk", "text": f"VIX {vix} — 시장 공포 극심, 현금 비중 확대 권고"})
    elif vix > 25:
        diags.append({"type": "warning", "text": f"VIX {vix} — 변동성 높음, 보수적 접근"})
    elif vix < 15:
        diags.append({"type": "positive", "text": f"VIX {vix} — 시장 안정, 위험자산 우호적"})

    usd = data.get("usd_krw", {})
    if usd.get("value", 0) > 1400:
        diags.append({"type": "warning", "text": f"원달러 {usd['value']}원 — 원화약세, 수출주 주목"})
    elif usd.get("value", 0) < 1250:
        diags.append({"type": "positive", "text": f"원달러 {usd['value']}원 — 원화강세, 내수/수입주 유리"})

    spread = data.get("yield_spread", {})
    if spread.get("value", 0.5) < 0:
        diags.append({"type": "risk", "text": f"장단기 금리 역전({spread['value']}%p) — 경기침체 선행 신호"})

    oil = data.get("wti_oil", {})
    if oil.get("change_pct", 0) > 3:
        diags.append({"type": "warning", "text": f"유가 급등 {oil['change_pct']}% — 인플레이션 압력 증가"})
    elif oil.get("change_pct", 0) < -3:
        diags.append({"type": "positive", "text": f"유가 급락 {oil['change_pct']}% — 원가 하락 수혜"})

    sp = data.get("sp500", {})
    nq = data.get("nasdaq", {})
    if sp.get("change_pct", 0) > 1.5 or nq.get("change_pct", 0) > 1.5:
        diags.append({"type": "positive", "text": f"미국증시 강세 (S&P {sp.get('change_pct', 0):+.1f}%, 나스닥 {nq.get('change_pct', 0):+.1f}%) — 글로벌 위험선호"})
    elif sp.get("change_pct", 0) < -1.5 or nq.get("change_pct", 0) < -1.5:
        diags.append({"type": "risk", "text": f"미국증시 급락 (S&P {sp.get('change_pct', 0):+.1f}%, 나스닥 {nq.get('change_pct', 0):+.1f}%) — 글로벌 위험회피"})

    gold = data.get("gold", {})
    if gold.get("change_pct", 0) > 2:
        diags.append({"type": "warning", "text": f"금 가격 급등 {gold['change_pct']}% — 안전자산 선호 증가"})

    if not diags:
        diags.append({"type": "neutral", "text": "특이 매크로 이벤트 없음 — 개별 종목 중심 접근"})

    return diags


def _get_micro_signals() -> list:
    """미시 지표: 네이버 금융에서 업종/투자자 동향 스크래핑"""
    signals = []
    try:
        url = "https://finance.naver.com/sise/sise_group.naver?type=upjong"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=5)
        resp.encoding = "euc-kr"
        soup = BeautifulSoup(resp.text, "html.parser")
        rows = soup.select("table.type_1 tr")
        sectors = []
        for row in rows:
            cols = row.select("td")
            if len(cols) >= 4:
                name_tag = cols[0].select_one("a")
                if not name_tag:
                    continue
                name = name_tag.text.strip()
                try:
                    change_text = cols[1].text.strip().replace(",", "").replace("%", "")
                    change = float(change_text)
                except (ValueError, IndexError):
                    continue
                sectors.append({"name": name, "change_pct": change})

        if sectors:
            sectors.sort(key=lambda x: x["change_pct"], reverse=True)
            top3 = sectors[:3]
            bottom3 = sectors[-3:]
            signals.append({"type": "hot_sector", "label": "상승 업종 TOP3", "data": top3})
            signals.append({"type": "cold_sector", "label": "하락 업종 TOP3", "data": bottom3})
    except Exception:
        pass

    return signals
