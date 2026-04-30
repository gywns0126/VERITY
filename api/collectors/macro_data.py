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

from api.collectors.fred_macro import get_fred_macro_block
from api.collectors.ecos_macro import get_ecos_macro_block, merge_ecos_into_fred
from api.config import MACRO_DGS10_DEFENSE_PCT


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

    fred = get_fred_macro_block()
    ecos = get_ecos_macro_block()
    merge_ecos_into_fred(fred, ecos)
    result["fred"] = fred
    result["ecos"] = ecos
    if fred.get("available") and fred.get("dgs10"):
        d = fred["dgs10"]
        v = float(d["value"])
        ch5 = d.get("change_5d_pp")
        prev = (v - float(ch5)) if ch5 is not None else None
        chg_pct = (
            round((float(ch5) / prev) * 100, 2)
            if prev is not None and prev > 0 and ch5 is not None
            else result["us_10y"].get("change_pct", 0)
        )
        result["us_10y"] = {
            "value": round(v, 3),
            "change_pct": chg_pct,
            "source": "fred",
            "as_of": d.get("date"),
        }

    spread_10_2 = _calc_yield_spread(result)
    result["yield_spread"] = spread_10_2

    # Sprint 11 결함 6 후속 (2026-05-01): leading indicator 최상위 promote.
    # _classify_regime 은 macro.hy_spread / breakeven_inflation 직접 참조 — 최상위 평탄화.
    # fred 블록 내부 키와 형식 다르니 표준화 ({value, date, ...}).
    if fred.get("available"):
        hy = fred.get("hy_spread")
        if isinstance(hy, dict) and isinstance(hy.get("pct"), (int, float)):
            result["hy_spread"] = {
                "value": hy["pct"],
                "date": hy.get("date"),
                "change_5d_pp": hy.get("change_5d_pp"),
                "source": "fred",
                "series_id": "BAMLH0A0HYM2",
            }
        be = fred.get("breakeven_inflation_10y")
        if isinstance(be, dict) and isinstance(be.get("pct"), (int, float)):
            result["breakeven_inflation_10y"] = {
                "value": be["pct"],
                "date": be.get("date"),
                "change_5d_pp": be.get("change_5d_pp"),
                "source": "fred",
                "series_id": "T10YIE",
            }
        fb = fred.get("fed_balance_sheet")
        if isinstance(fb, dict) and isinstance(fb.get("trillions_usd"), (int, float)):
            result["fed_balance_sheet"] = {
                "value": fb["trillions_usd"],
                "date": fb.get("date"),
                "change_4w_pct": fb.get("change_4w_pct"),
                "source": "fred",
                "series_id": "WALCL",
                "unit": "trillions_usd",
            }

    result["market_mood"] = _assess_market_mood(result, market="kr")
    result["macro_diagnosis"] = _build_diagnosis(result, market="kr")
    result["market_mood_us"] = _assess_market_mood(result, market="us")
    result["macro_diagnosis_us"] = _build_diagnosis(result, market="us")
    result["micro_signals"] = _get_micro_signals()
    result["capital_flow"] = _compute_capital_flow(result)

    if "source" not in result.get("us_10y", {}):
        result["us_10y"]["source"] = "yfinance"

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


def _assess_market_mood(data: dict, market: str = "kr") -> dict:
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

    if market == "us":
        usd_jpy_chg = data.get("usd_jpy", {}).get("change_pct", 0)
        if usd_jpy_chg > 0.7:
            mood_score -= 6
        elif usd_jpy_chg < -0.7:
            mood_score += 6
    else:
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

    # FRED/ECOS 매크로 팩터
    fred = data.get("fred") or {}
    ecos = data.get("ecos") or {}

    rec_prob = (fred.get("us_recession_smoothed_prob") or {}).get("pct")
    if rec_prob is not None:
        if float(rec_prob) >= 35:
            mood_score -= 15
        elif float(rec_prob) >= 18:
            mood_score -= 7

    m2_yoy = (fred.get("m2") or {}).get("yoy_pct")
    if m2_yoy is not None:
        if float(m2_yoy) > 8:
            mood_score += 5
        elif float(m2_yoy) < -2:
            mood_score -= 8

    cpi_yoy = (fred.get("core_cpi") or {}).get("yoy_pct")
    if cpi_yoy is not None:
        if float(cpi_yoy) >= 4.5:
            mood_score -= 5
        elif float(cpi_yoy) <= 1.5:
            mood_score += 5

    if market == "kr":
        kr_rate = (ecos.get("korea_policy_rate") or {}).get("value")
        if kr_rate is not None:
            if float(kr_rate) >= 4.0:
                mood_score -= 5
            elif float(kr_rate) <= 1.5:
                mood_score += 5

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


def _build_diagnosis(data: dict, market: str = "kr") -> list:
    """현재 매크로 상황을 한줄씩 요약하는 진단 리스트"""
    diags = []

    vix = data.get("vix", {}).get("value", 0)
    if vix > 30:
        diags.append({"type": "risk", "text": f"VIX {vix} — 시장 공포 극심, 현금 비중 확대 권고"})
    elif vix > 25:
        diags.append({"type": "warning", "text": f"VIX {vix} — 변동성 높음, 보수적 접근"})
    elif vix < 15:
        diags.append({"type": "positive", "text": f"VIX {vix} — 시장 안정, 위험자산 우호적"})

    if market == "us":
        uj = data.get("usd_jpy", {})
        uj_val = uj.get("value", 0)
        if uj_val >= 155:
            diags.append({"type": "warning", "text": f"USD/JPY {uj_val} — 달러 강세·엔 약세, 글로벌 자금 변동성 확대"})
        elif uj_val <= 140 and uj_val > 0:
            diags.append({"type": "positive", "text": f"USD/JPY {uj_val} — 달러 부담 완화, 위험자산 선호 우호"})
    else:
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

    fred = data.get("fred") or {}
    dgs = fred.get("dgs10") or {}
    if dgs.get("value") is not None:
        dv = float(dgs["value"])
        if dv >= MACRO_DGS10_DEFENSE_PCT:
            diags.append({
                "type": "risk",
                "text": (
                    f"FRED DGS10 {dv:.2f}% (≥{MACRO_DGS10_DEFENSE_PCT}%) — "
                    "고금리·할인율 압력, 현금 비중 확대·신규 매수 보수"
                ),
            })
        elif dgs.get("change_5d_pp") is not None and float(dgs["change_5d_pp"]) >= 0.12:
            diags.append({
                "type": "warning",
                "text": f"FRED DGS10 5영업일 +{float(dgs['change_5d_pp']):.2f}%p 급등 — 채권 금리 모멘텀 주의",
            })

    cpi = fred.get("core_cpi") or {}
    if cpi.get("yoy_pct") is not None:
        y = float(cpi["yoy_pct"])
        if y >= 3.5:
            diags.append({
                "type": "warning",
                "text": f"근원 CPI YoY {y:+.1f}% — 물가 끈기, 금리 인하 속도 제약 가능",
            })
        elif y <= 1.5:
            diags.append({
                "type": "positive",
                "text": f"근원 CPI YoY {y:+.1f}% — 물가 완화 국면 신호",
            })

    m2 = fred.get("m2") or {}
    if m2.get("yoy_pct") is not None:
        my = float(m2["yoy_pct"])
        if my < 0:
            diags.append({
                "type": "warning",
                "text": f"M2 YoY {my:+.1f}% — 유동성 축소 추세, 수익률 기대 하향·방어 우선",
            })

    vix_f = fred.get("vix_close") or {}
    if vix_f.get("change_5d") is not None and float(vix_f["change_5d"]) >= 5:
        diags.append({
            "type": "warning",
            "text": (
                f"FRED VIXCLS 5영업일 +{float(vix_f['change_5d']):.1f}pt — "
                "변동성 급팽창(공포), 체결·레버리지 점검"
            ),
        })

    if market == "kr":
        kr10 = fred.get("korea_gov_10y") or {}
        if kr10.get("yoy_pp") is not None and float(kr10["yoy_pp"]) >= 0.5:
            diags.append({
                "type": "warning",
                "text": (
                    f"한국 10Y(OECD) 전년 대비(근사) +{float(kr10['yoy_pp']):.2f}%p — "
                    "국내 금리·채권 수급 압력, 방어·듀레이션 주의"
                ),
            })

        if dgs.get("value") is not None and kr10.get("value") is not None:
            gap = round(float(kr10["value"]) - float(dgs["value"]), 2)
            if abs(gap) >= 0.75:
                t = "warning" if gap < -1.25 else "positive" if gap > 1.25 else "neutral"
                diags.append({
                    "type": t,
                    "text": (
                        f"한국10Y−미10Y = {gap:+.2f}%p — "
                        f"{'미국 금리 우위·외화 유출 압력' if gap < -1.25 else '국내 금리 프리미엄' if gap > 1.25 else '금리차 중간대'}"
                    ),
                })

    rp = fred.get("us_recession_smoothed_prob") or {}
    if rp.get("pct") is not None:
        p = float(rp["pct"])
        if p >= 35:
            diags.append({
                "type": "risk",
                "text": f"미국 리세션 스무딩 확률 {p:.1f}% — 생존·현금 비중·저베타 우선",
            })
        elif p >= 18:
            diags.append({
                "type": "warning",
                "text": f"미국 리세션 스무딩 확률 {p:.1f}% — 경기 하방 시나리오 염두",
            })

    if not diags:
        diags.append({"type": "neutral", "text": "특이 매크로 이벤트 없음 — 개별 종목 중심 접근"})

    return diags


def _compute_capital_flow(data: dict) -> dict:
    """3-섹터(원자재/채권·달러/주식) 자금 흐름 방향 추정
    ECOS 기준금리·국고채, FRED M2·CPI를 가중 반영."""

    def _avg(keys):
        vals = [data.get(k, {}).get("change_pct", 0) for k in keys]
        valid = [v for v in vals if v is not None]
        return round(sum(valid) / len(valid), 3) if valid else 0

    def _dominant(keys):
        best_k, best_v = keys[0], abs(data.get(keys[0], {}).get("change_pct", 0))
        for k in keys[1:]:
            v = abs(data.get(k, {}).get("change_pct", 0))
            if v > best_v:
                best_k, best_v = k, v
        return best_k

    comm_keys = ["gold", "silver", "copper", "wti_oil"]
    bond_keys = ["us_10y", "us_2y"]
    eq_keys = ["sp500", "nasdaq"]

    comm_chg = _avg(comm_keys)
    bond_chg = _avg(bond_keys)
    eq_chg = _avg(eq_keys)

    def _to_score(chg):
        return max(0, min(100, round(50 + chg * 8)))

    comm_score = _to_score(comm_chg)
    bond_score = _to_score(bond_chg)
    eq_score = _to_score(eq_chg)

    # --- ECOS/FRED 보정 ---
    ecos = data.get("ecos") or {}
    fred = data.get("fred") or {}
    ecos_note = []

    kr_rate = ecos.get("korea_policy_rate") or {}
    kr_rate_val = kr_rate.get("value")
    kr10 = (ecos.get("korea_gov_10y") or fred.get("korea_gov_10y") or {})
    kr10_yoy = kr10.get("yoy_pp")

    if kr10_yoy is not None:
        # 한국 10Y 금리 YoY 상승 → 채권 수익률 매력 ↑ → bond_score 가산
        adj = max(-8, min(8, round(float(kr10_yoy) * 4)))
        bond_score = max(0, min(100, bond_score + adj))
        ecos_note.append(f"KR10Y_yoy={kr10_yoy:+.2f}pp→bond{adj:+d}")

    if kr_rate_val is not None:
        if float(kr_rate_val) >= 3.5:
            bond_score = min(100, bond_score + 5)
            eq_score = max(0, eq_score - 3)
            ecos_note.append(f"기준금리{kr_rate_val}%≥3.5→bond+5,eq-3")
        elif float(kr_rate_val) <= 2.0:
            eq_score = min(100, eq_score + 5)
            bond_score = max(0, bond_score - 3)
            ecos_note.append(f"기준금리{kr_rate_val}%≤2.0→eq+5,bond-3")

    m2 = fred.get("m2") or {}
    m2_yoy = m2.get("yoy_pct")
    if m2_yoy is not None:
        # M2 YoY 양수(유동성 확대) → 주식·원자재 유리
        if float(m2_yoy) > 5:
            eq_score = min(100, eq_score + 4)
            comm_score = min(100, comm_score + 3)
            ecos_note.append(f"M2_yoy={m2_yoy}%>5→eq+4,comm+3")
        elif float(m2_yoy) < -2:
            eq_score = max(0, eq_score - 4)
            bond_score = min(100, bond_score + 3)
            ecos_note.append(f"M2_yoy={m2_yoy}%<-2→eq-4,bond+3")

    cpi = fred.get("core_cpi") or {}
    cpi_yoy = cpi.get("yoy_pct")
    if cpi_yoy is not None:
        # CPI 높으면 원자재·금 선호, 주식 할인율 부담
        if float(cpi_yoy) >= 4.0:
            comm_score = min(100, comm_score + 4)
            eq_score = max(0, eq_score - 3)
            ecos_note.append(f"CPI_yoy={cpi_yoy}%≥4→comm+4,eq-3")
        elif float(cpi_yoy) <= 1.5:
            eq_score = min(100, eq_score + 3)
            ecos_note.append(f"CPI_yoy={cpi_yoy}%≤1.5→eq+3")

    sectors = [
        ("commodities", comm_chg, comm_score),
        ("bonds", bond_chg, bond_score),
        ("equities", eq_chg, eq_score),
    ]
    sectors_sorted = sorted(sectors, key=lambda x: x[2], reverse=True)
    strongest = sectors_sorted[0][0]
    weakest = sectors_sorted[-1][0]

    flow_dir = f"{weakest}_to_{strongest}"

    mood = data.get("market_mood", {}).get("score", 50)
    if strongest == "commodities" and mood < 45:
        interp = "안전자산(원자재) 쏠림 — 주식 신규 진입 자제"
    elif strongest == "bonds" and mood < 45:
        interp = "채권·달러 선호 — 위험자산 회피 국면"
    elif strongest == "equities" and mood >= 55:
        interp = "위험자산 선호 — 주식 적극 검토 구간"
    elif strongest == "equities" and mood < 45:
        interp = "주식 반등 시도 중이나 매크로 불안 지속"
    elif strongest == "commodities" and mood >= 55:
        interp = "인플레이션 수혜 자산 강세 — 원자재·자원주 주목"
    else:
        interp = "3-섹터 균형 — 특정 방향 쏠림 미약"

    usd_chg = data.get("usd_krw", {}).get("change_pct", 0)

    return {
        "commodities": {
            "score": comm_score,
            "change_pct": comm_chg,
            "dominant": _dominant(comm_keys),
        },
        "bonds": {
            "score": bond_score,
            "change_pct": bond_chg,
            "dominant": _dominant(bond_keys),
            "usd_change_pct": round(usd_chg, 3) if usd_chg else 0,
            "kr_policy_rate": kr_rate_val,
            "kr_10y": kr10.get("value"),
        },
        "equities": {
            "score": eq_score,
            "change_pct": eq_chg,
            "dominant": _dominant(eq_keys),
        },
        "flow_direction": flow_dir,
        "interpretation": interp,
        "ecos_adjustments": ecos_note or None,
    }


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
