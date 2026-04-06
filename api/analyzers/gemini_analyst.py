"""
Gemini API 기반 최종 의사결정 모듈 (Sprint 9: Verity Brain 통합)
- DART 재무제표(현금흐름) 데이터 통합
- 15년 차 펀드매니저 말투 프롬프트
- Gold/Silver 데이터 분류
- Verity Brain 종합 판단 결과를 system_instruction + 프롬프트에 주입
"""
import json
import os
import time
from typing import List, Optional
from google import genai
from api.config import GEMINI_API_KEY, RISK_KEYWORDS, DATA_DIR

_CONSTITUTION_PATH = os.path.join(DATA_DIR, "verity_constitution.json")


def init_gemini():
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
    return genai.Client(api_key=GEMINI_API_KEY)


def _load_system_instruction() -> str:
    """verity_constitution.json에서 system_instruction 로드."""
    try:
        with open(_CONSTITUTION_PATH, "r", encoding="utf-8") as f:
            const = json.load(f)
        si = const.get("gemini_system_instruction", {})
        role = si.get("role", "너는 15년 차 까칠한 한국 펀드매니저다.")
        tone = si.get("tone", "짧고 굵게. 숫자로 증명. 서론 금지.")
        principles = si.get("principles", [])
        p_lines = "\n".join(f"- {p}" for p in principles)
        return f"{role}\n{tone}\n\n원칙:\n{p_lines}"
    except Exception:
        return (
            "너는 15년 차 까칠한 한국 펀드매니저다.\n"
            "짧고 굵게. 숫자로 증명. 서론 금지. 반말 OK."
        )


def _build_prompt(stock: dict, macro: Optional[dict] = None) -> str:
    tech = stock.get("technical", {})
    sent = stock.get("sentiment", {})
    flow = stock.get("flow", {})
    mf = stock.get("multi_factor", {})
    pred = stock.get("prediction", {})
    bt = stock.get("backtest", {})
    dart = stock.get("dart_financials", {})
    cf = dart.get("cashflow", {})

    macro_block = ""
    if macro:
        mood = macro.get("market_mood", {})
        fr = macro.get("fred") or {}
        fr_lines = ""
        if fr.get("dgs10"):
            d = fr["dgs10"]
            fr_lines += f"\n- FRED DGS10: {d.get('value')}% (as_of {d.get('date', '?')}, 5d Δ{d.get('change_5d_pp', '?')}%p)"
        if fr.get("core_cpi"):
            c = fr["core_cpi"]
            fr_lines += f"\n- 근원 CPI(CPILFESL): 지수 {c.get('index')} | YoY {c.get('yoy_pct')}% ({c.get('date')})"
        if fr.get("m2"):
            m = fr["m2"]
            fr_lines += f"\n- M2(M2SL): {m.get('billions_usd')}bn USD | YoY {m.get('yoy_pct')}% ({m.get('date')})"
        if fr.get("vix_close"):
            vx = fr["vix_close"]
            fr_lines += f"\n- VIXCLS: {vx.get('value')} (5d Δ{vx.get('change_5d', '?')}pt, {vx.get('date')})"
        if fr.get("korea_policy_rate"):
            kp = fr["korea_policy_rate"]
            fr_lines += (
                f"\n- 한국은행 기준금리(ECOS): {kp.get('value')}% "
                f"({kp.get('date')})"
            )
        if fr.get("korea_gov_10y"):
            k = fr["korea_gov_10y"]
            src = k.get("source_note") or "OECD/IMF 대체"
            fr_lines += (
                f"\n- 한국 국고10Y: {k.get('value')}% | YoYΔ{k.get('yoy_pp', '?')}%p "
                f"({k.get('date')}) — {src}"
            )
        if fr.get("korea_discount_rate"):
            kd = fr["korea_discount_rate"]
            fr_lines += f"\n- 한국 IMF할인율: {kd.get('value')}% ({kd.get('date')})"
        if fr.get("us_recession_smoothed_prob"):
            rp = fr["us_recession_smoothed_prob"]
            fr_lines += f"\n- 미 리세션확률(RECPRO): {rp.get('pct')}% | MoMΔ{rp.get('mom_change_pp', '?')}%p ({rp.get('date')})"
        if not fr_lines:
            fr_lines = "\n- FRED: 키 미설정 또는 수집 스킵"
        u10 = macro.get("us_10y", {})
        macro_block = f"""
[매크로 환경]
- 시장 국면: {mf.get('regime', 'neutral')} | 분위기: {mood.get('label', '?')} ({mood.get('score', 0)}점)
- 미10년 표시: {u10.get('value', '?')}% (출처: {u10.get('source', '?')})
- USD/KRW: {macro.get('usd_krw', {}).get('value', '?')}원
- VIX: {macro.get('vix', {}).get('value', '?')}
- WTI: ${macro.get('wti_oil', {}).get('value', '?')}
- S&P500: {macro.get('sp500', {}).get('change_pct', 0):+.1f}%
- 동적 가중치: {mf.get('weights_used', {})}
[FRED 거시]{fr_lines}
"""

    cashflow_block = ""
    if cf.get("operating") or cf.get("free_cashflow"):
        op = cf.get("operating", 0)
        inv = cf.get("investing", 0)
        fin = cf.get("financing", 0)
        fcf = cf.get("free_cashflow", 0)
        cashflow_block = f"""
[DART 현금흐름표]
- 영업CF: {op/1e8:+,.0f}억 | 투자CF: {inv/1e8:+,.0f}억 | 재무CF: {fin/1e8:+,.0f}억
- FCF(영업+투자): {fcf/1e8:+,.0f}억 {'⚠️ 현금 소진 위험' if fcf < 0 else '✓ 현금 창출'}
"""
    dart_debt = dart.get("financials", {})
    if dart_debt.get("debt_ratio_pct"):
        cashflow_block += f"- DART 부채비율: {dart_debt['debt_ratio_pct']}% | 자본: {dart_debt.get('equity', 0)/1e8:,.0f}억\n"

    flow_detail = []
    fn = flow.get('foreign_net', 0)
    in_ = flow.get('institution_net', 0)
    flow_detail.append(f"외국인 당일 {fn:+,}주 | 5일합산 {flow.get('foreign_5d_sum', 0):+,}주")
    if flow.get('foreign_consec_buy', 0) >= 2:
        flow_detail.append(f"외국인 {flow['foreign_consec_buy']}일 연속매수")
    elif flow.get('foreign_consec_sell', 0) >= 2:
        flow_detail.append(f"외국인 {flow['foreign_consec_sell']}일 연속매도")
    flow_detail.append(f"기관 당일 {in_:+,}주 | 5일합산 {flow.get('institution_5d_sum', 0):+,}주")
    if flow.get('inst_consec_buy', 0) >= 2:
        flow_detail.append(f"기관 {flow['inst_consec_buy']}일 연속매수")
    elif flow.get('inst_consec_sell', 0) >= 2:
        flow_detail.append(f"기관 {flow['inst_consec_sell']}일 연속매도")
    flow_block = "\n".join(f"- {d}" for d in flow_detail)

    sent_detail_block = ""
    for h in sent.get("detail", [])[:3]:
        sent_detail_block += f"\n  [{h.get('label','?')}] {h.get('title','')}"

    cons = stock.get("consensus", {})
    cons_block = ""
    if cons:
        src = cons.get("score_source", "?")
        cs = cons.get("consensus_score", "?")
        up = cons.get("upside_pct")
        up_s = f"{up:+.1f}%" if up is not None else "N/A"
        opg = cons.get("operating_profit_yoy_est_pct")
        opg_s = f"{opg:+.1f}%" if opg is not None else "N/A"
        fb = cons.get("flow_fallback_note") or ""
        cons_block = f"""
[증권사 컨센서스/기관 심리] 점수 {cs} ({src}) | 목표 대비 현재가 여력 {up_s}
올해 영업이익 추정 전년비 {opg_s} | 의견 {cons.get('investment_opinion', '?')}
{fb}"""
        for cw in cons.get("warnings", [])[:2]:
            cons_block += f"\n⚠️ {cw}"

    cm = stock.get("commodity_margin") or {}
    pr = cm.get("primary") or {}
    cm_block = ""
    if pr.get("commodity_ticker"):
        cm_block = f"""
[원자재·마진] 연동 {pr.get('commodity_ticker')} | 60일 r {pr.get('correlation_60d', 'n/a')}
20일: 원자재 {pr.get('commodity_20d_pct', '?')}% / 주가 {pr.get('stock_20d_pct', '?')}% | 국면 {pr.get('spread_regime', '?')}
마진안심(가공) {pr.get('margin_safety_score', '?')} (판가력 {pr.get('pricing_power', '?')} vs 원가변동성 {pr.get('raw_material_volatility_score', '?')})
"""

    x_sent = stock.get("x_sentiment", {})
    x_block = ""
    if x_sent.get("tweets"):
        x_block = f"""
[X(트위터) 감성] (점수: {x_sent.get('score', 50)})
- 수집: {x_sent.get('tweet_count', 0)}건 | 긍정 {x_sent.get('positive', 0)} / 부정 {x_sent.get('negative', 0)}
- 주요 트윗: {', '.join(t[:40] for t in x_sent.get('tweets', [])[:2]) or '없음'}
"""

    brain = stock.get("verity_brain", {})
    brain_block = ""
    if brain.get("brain_score") is not None:
        vci_info = brain.get("vci", {})
        rf = brain.get("red_flags", {})
        brain_block = f"""
[배리티 브레인 사전 판단]
브레인점수: {brain.get('brain_score', '?')} | 등급: {brain.get('grade_label', '?')} ({brain.get('grade', '?')})
팩트: {brain.get('fact_score', {}).get('score', '?')} | 심리: {brain.get('sentiment_score', {}).get('score', '?')}
VCI(괴리율): {vci_info.get('vci', '?'):+d} → {vci_info.get('label', '')}
근거: {brain.get('reasoning', '')}"""
        if rf.get("auto_avoid"):
            brain_block += f"\n⛔ 레드플래그: {'; '.join(rf['auto_avoid'])}"
        if rf.get("downgrade"):
            brain_block += f"\n⚠️ 하향조정: {'; '.join(rf['downgrade'])}"
        brain_block += "\n"

    return f"""[종목]
{stock['name']} ({stock['ticker']}) / {stock['market']}
현재가 {stock['price']:,.0f}원 ({tech.get('price_change_pct', 0):+.1f}%) | 시총 {stock.get('market_cap', 0)/1e12:.1f}조
PER {stock.get('per', 0):.1f} | PBR {stock.get('pbr', 0):.2f} | 배당 {stock.get('div_yield', 0):.1f}%
52주 고점대비 {stock.get('drop_from_high_pct', 0):.1f}% | 거래대금 {stock.get('trading_value', 0)/1e8:,.0f}억
부채 {stock.get('debt_ratio', 0):.0f}% | 영업이익률 {stock.get('operating_margin', 0):.1f}% | ROE {stock.get('roe', 0):.1f}%
{cashflow_block}
[기술적]
RSI {tech.get('rsi', '?')} | MACD히스토 {tech.get('macd_hist', '?')} | 볼린저 {tech.get('bb_position', '?')}%
거래량비 {tech.get('vol_ratio', '?')}x | 추세강도 {tech.get('trend_strength', 0)} | 시그널: {', '.join(tech.get('signals', [])) or '없음'}

[뉴스] {sent.get('score', 50)}점 ({sent.get('headline_count', 0)}건){sent_detail_block or ' 없음'}
{cm_block}{x_block}
[수급] {flow.get('flow_score', 50)}점
{flow_block}
외국인지분 {flow.get('foreign_ratio', 0):.1f}%
{cons_block}
[멀티팩터] {mf.get('multi_score', 0)}점 ({mf.get('grade', '?')})
기여: {mf.get('factor_contribution', {{}})}
{macro_block}
[AI예측] XGBoost {pred.get('up_probability', '?')}% ({pred.get('method', '?')})
[백테스트] 승률 {bt.get('win_rate', 0)}% | 샤프 {bt.get('sharpe_ratio', 0)} | {bt.get('total_trades', 0)}회
{brain_block}
규칙:
1. gold_insight = 재무/차트 핵심 한 줄. 구체적 숫자 필수. 군더더기 빼.
2. recommendation: 배리티 브레인 등급을 존중하되, 정성적 판단으로 조정 가능. 조정 시 이유 명시.
3. risk_flags: 실제 데이터에서 확인된 것만. 레드플래그 있으면 반드시 포함.
4. ai_verdict: 사장님한테 보고하듯 짧게. "~입니다" 금지. 반말 OK. VCI 괴리 있으면 언급.
5. 현금흐름이 마이너스면 반드시 risk_flags에 포함.

JSON만:
{{
  "ai_verdict": "40자 이내. 숫자 근거. 서론 없이 핵심만",
  "recommendation": "BUY/WATCH/AVOID",
  "risk_flags": ["확인된 리스크만"],
  "confidence": 0~100,
  "gold_insight": "재무/차트 팩트 1줄",
  "silver_insight": "수급/뉴스/매크로 1줄"
}}"""


def analyze_stock(client, stock: dict, macro: Optional[dict] = None) -> dict:
    prompt = _build_prompt(stock, macro)
    sys_instr = _load_system_instruction()

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config={"system_instruction": sys_instr},
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0]

        result = json.loads(text)

        detected_risks = []
        for kw in RISK_KEYWORDS:
            if kw in result.get("ai_verdict", "") or kw in str(result.get("risk_flags", [])):
                detected_risks.append(kw)
        result["detected_risk_keywords"] = detected_risks

        return result

    except json.JSONDecodeError:
        return {
            "ai_verdict": "AI 분석 파싱 실패 - 수동 확인 필요",
            "recommendation": "WATCH",
            "risk_flags": [],
            "confidence": 0,
            "gold_insight": "데이터 확인 필요",
            "silver_insight": "데이터 확인 필요",
            "detected_risk_keywords": [],
        }
    except Exception as e:
        return {
            "ai_verdict": f"AI 분석 오류: {str(e)[:50]}",
            "recommendation": "WATCH",
            "risk_flags": [],
            "confidence": 0,
            "gold_insight": "분석 실패",
            "silver_insight": "분석 실패",
            "detected_risk_keywords": [],
        }


def generate_daily_report(macro: dict, candidates: List[dict], sectors: list, headlines: list, verity_brain: Optional[dict] = None) -> dict:
    """AI 일일 시장 종합 리포트 생성 (Verity Brain 결과 포함)"""
    try:
        client = init_gemini()
    except Exception:
        return _fallback_report(macro, candidates, sectors)

    mood = macro.get("market_mood", {})
    diags = macro.get("macro_diagnosis", [])
    top_buys = [s for s in candidates if s.get("recommendation") == "BUY"][:5]
    top_sectors = sectors[:5] if sectors else []
    top_news = headlines[:5] if headlines else []

    brain_block = ""
    if verity_brain:
        mb = verity_brain.get("market_brain", {})
        ov = verity_brain.get("macro_override")
        dist = mb.get("grade_distribution", {})
        top_picks = mb.get("top_picks", [])
        rf_stocks = mb.get("red_flag_stocks", [])
        brain_block = f"""
[배리티 브레인 시장 종합]
시장 평균: 브레인 {mb.get('avg_brain_score', '?')}점 | 팩트 {mb.get('avg_fact_score', '?')} / 심리 {mb.get('avg_sentiment_score', '?')} / VCI {mb.get('avg_vci', 0):+d}
등급 분포: 강매수 {dist.get('STRONG_BUY', 0)} | 매수 {dist.get('BUY', 0)} | 관망 {dist.get('WATCH', 0)} | 주의 {dist.get('CAUTION', 0)} | 회피 {dist.get('AVOID', 0)}"""
        if ov:
            brain_block += f"\n매크로 오버라이드: {ov.get('label', '?')} — {ov.get('message', '')}"
        if top_picks:
            top_str = ", ".join(f"{t['name']}({t['score']})" for t in top_picks[:3])
            brain_block += f"\n브레인 TOP: {top_str}"
        if rf_stocks:
            rf_str = ", ".join(f["name"] for f in rf_stocks[:3])
            brain_block += f"\n레드플래그: {rf_str}"

    fr = macro.get("fred") or {}
    dgs = fr.get("dgs10") or {}
    cpi = fr.get("core_cpi") or {}
    m2b = fr.get("m2") or {}
    vxf = fr.get("vix_close") or {}
    kr10f = fr.get("korea_gov_10y") or {}
    krdf = fr.get("korea_discount_rate") or {}
    rpf = fr.get("us_recession_smoothed_prob") or {}
    fred_daily = ""
    if dgs:
        fred_daily = f" | FRED DGS10 {dgs.get('value')}% ({dgs.get('date', '')})"
    if cpi:
        fred_daily += f" | 근원CPI YoY {cpi.get('yoy_pct')}%"
    if m2b:
        fred_daily += f" | M2 YoY {m2b.get('yoy_pct')}%"
    if vxf:
        fred_daily += f" | VIXCLS {vxf.get('value')}"
    if kr10f:
        fred_daily += f" | 한국10Y {kr10f.get('value')}%"
    if krdf:
        fred_daily += f" | IMF할인율 {krdf.get('value')}%"
    if rpf:
        fred_daily += f" | 리세션확률 {rpf.get('pct')}%"

    prompt = f"""[오늘 시장]
분위기: {mood.get('label', '?')} ({mood.get('score', 0)}점)
VIX: {macro.get('vix', {}).get('value', '?')} ({macro.get('vix', {}).get('change_pct', 0):+.1f}%)
원달러: {macro.get('usd_krw', {}).get('value', '?')}원 | WTI: ${macro.get('wti_oil', {}).get('value', '?')}
금: ${macro.get('gold', {}).get('value', '?')} | 스프레드: {macro.get('yield_spread', {}).get('value', '?')}%p ({macro.get('yield_spread', {}).get('signal', '?')})
미10년: {macro.get('us_10y', {}).get('value', '?')}% ({macro.get('us_10y', {}).get('source', '?')}){fred_daily}

[매크로]
{chr(10).join(f'- {d.get("text","")}' for d in diags) if diags else '별거 없음'}

[핫 섹터]
{chr(10).join(f'- {s["name"]}: {s["change_pct"]:+.2f}%' for s in top_sectors) if top_sectors else '없음'}

[뉴스]
{chr(10).join(f'- [{n.get("sentiment","?")}] {n["title"][:60]}' for n in top_news) if top_news else '없음'}

[찍은 종목]
{chr(10).join(f'- {s["name"]} ({s.get("multi_factor",{}).get("multi_score",0)}점)' for s in top_buys) if top_buys else '오늘 살 만한 거 없음'}
{brain_block}

JSON만:
{{
  "market_summary": "시장 한줄 (30자 이내, 서론 없이)",
  "market_analysis": "상황 분석 (150자 이내, 반말 OK, 숫자 근거, VCI 괴리 있으면 언급)",
  "strategy": "오늘 전략 (80자 이내, 실행 가능한 것만, 브레인 등급 분포 참고)",
  "risk_watch": "지금 위험한 것 (80자 이내, 레드플래그 종목 있으면 명시)",
  "hot_theme": "관심 테마/섹터 + 이유 (80자 이내)",
  "tomorrow_outlook": "내일 전망 (30자 이내)"
}}"""

    sys_instr = _load_system_instruction()
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config={"system_instruction": sys_instr},
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0]
        return json.loads(text)
    except Exception:
        return _fallback_report(macro, candidates, sectors)


def _fallback_report(macro: dict, candidates: list, sectors: list) -> dict:
    mood = macro.get("market_mood", {})
    top_buys = [s["name"] for s in candidates if s.get("recommendation") == "BUY"][:3]
    top_sec = [s["name"] for s in sectors[:3]] if sectors else []
    return {
        "market_summary": f"시장 분위기 {mood.get('label', '?')} ({mood.get('score', 0)}점)",
        "market_analysis": f"VIX {macro.get('vix', {}).get('value', '?')}, 원달러 {macro.get('usd_krw', {}).get('value', '?')}원 수준에서 거래 중",
        "strategy": f"매수 후보: {', '.join(top_buys)}" if top_buys else "관망 전략 유지",
        "risk_watch": "구체적 리스크 분석은 Gemini API 연결 시 제공됩니다",
        "hot_theme": f"금일 강세 섹터: {', '.join(top_sec)}" if top_sec else "특별한 테마 없음",
        "tomorrow_outlook": "장중 변동성에 주의하며 대응",
    }


def analyze_batch(candidates: List[dict], macro_context: Optional[dict] = None) -> List[dict]:
    """후보 종목 일괄 분석"""
    if not candidates:
        return []

    client = init_gemini()
    results = []

    for i, stock_info in enumerate(candidates):
        if i > 0:
            time.sleep(6)
        print(f"  [Gemini] ({i+1}/{len(candidates)}): {stock_info['name']}")

        analysis = None
        for attempt in range(3):
            analysis = analyze_stock(client, stock_info, macro_context)
            if "429" not in analysis.get("ai_verdict", ""):
                break
            wait = 15 * (attempt + 1)
            print(f"    ⏳ 속도 제한 → {wait}초 대기 후 재시도 ({attempt+2}/3)")
            time.sleep(wait)

        results.append({**stock_info, **analysis})

    results.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    return results


def generate_periodic_report(analysis_data: dict) -> dict:
    """
    정기 리포트(주간/월간/분기/반기/연간)용 Gemini 자연어 생성.
    periodic_report.py가 만든 구조화 데이터를 받아 통찰을 작성.
    """
    try:
        client = init_gemini()
    except Exception:
        return _fallback_periodic(analysis_data)

    period_label = analysis_data.get("period_label", "정기")
    days = analysis_data.get("days_available", 0)
    date_range = analysis_data.get("date_range", {})

    recs = analysis_data.get("recommendations", {})
    sectors = analysis_data.get("sectors", {})
    macro_t = analysis_data.get("macro", {})
    brain_acc = analysis_data.get("brain_accuracy", {})
    meta = analysis_data.get("meta_analysis", {})
    news_kw = analysis_data.get("news_keywords", {})
    portfolio = analysis_data.get("portfolio", {})

    prompt = f"""[{period_label} 종합 분석 리포트 작성]
기간: {date_range.get('start', '?')} ~ {date_range.get('end', '?')} ({days}일간)

[추천 성과]
총 BUY 추천: {recs.get('total_buy_recs', 0)}개
적중률(Hit Rate): {recs.get('hit_rate_pct', 0)}%
평균 수익률: {recs.get('avg_return_pct', 0)}%
고점수(70+) 적중률: {recs.get('high_score_hit_rate_pct', 0)}%
최고 종목: {json.dumps(recs.get('best_picks', [])[:3], ensure_ascii=False)}
최악 종목: {json.dumps(recs.get('worst_picks', [])[:3], ensure_ascii=False)}

[섹터 동향]
TOP 3 섹터: {json.dumps(sectors.get('top3_sectors', []), ensure_ascii=False)}
BOTTOM 3 섹터: {json.dumps(sectors.get('bottom3_sectors', []), ensure_ascii=False)}
자금 유입: {sectors.get('rotation_in', [])}
자금 유출: {sectors.get('rotation_out', [])}

[매크로]
분위기 추이: {macro_t.get('mood_trend', '?')} (평균 {macro_t.get('mood_avg', 0)}점)
VIX: {json.dumps(macro_t.get('indicators', {}).get('vix', {}), ensure_ascii=False)}
환율: {json.dumps(macro_t.get('indicators', {}).get('usd_krw', {}), ensure_ascii=False)}
금: {json.dumps(macro_t.get('indicators', {}).get('gold', {}), ensure_ascii=False)}

[브레인 정확도]
등급별 실적: {json.dumps(brain_acc.get('grades', {}), ensure_ascii=False)}
평가: {brain_acc.get('insight', '')}

[데이터 소스 메타 분석]
정확도 순위: {json.dumps(meta.get('findings', []), ensure_ascii=False)}
결론: {meta.get('best_predictor', '')}

[뉴스 키워드]
상위 키워드: {json.dumps(news_kw.get('top_keywords', [])[:10], ensure_ascii=False)}

[포트폴리오]
기간 수익률: {portfolio.get('period_return_pct', 0)}%
최대 낙폭: {portfolio.get('max_drawdown_pct', 0)}%

규칙:
1. 단순 숫자 나열 금지. "왜?"를 분석. 메타 분석 포함.
2. 어떤 데이터 소스가 정확했고 어떤 게 틀렸는지 명시.
3. 브레인의 오판 사례가 있으면 원인 추론.
4. 다음 {period_label} 전략 제안 포함.
5. 섹터 자금 흐름의 방향성과 이유 분석.

JSON만:
{{
  "title": "{period_label} 종합 분석 리포트 제목 (20자 이내)",
  "executive_summary": "3줄 핵심 요약",
  "performance_review": "추천 성과 복기 (승률, 수익률, 오판 원인 분석)",
  "sector_analysis": "섹터 동향 분석 + 자금 흐름 방향",
  "macro_outlook": "매크로 환경 변화와 향후 전망",
  "brain_review": "AI 브레인 정확도 평가 + 개선 포인트",
  "meta_insight": "데이터 소스 메타 분석 — 어떤 지표가 가장 정확했고 왜 그런지",
  "strategy": "다음 {period_label} 투자 전략 제안",
  "risk_watch": "주의해야 할 리스크 요인"
}}"""

    sys_instr = _load_system_instruction()

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config={"system_instruction": sys_instr},
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0]

        result = json.loads(text)
        result["_period"] = analysis_data.get("period", "unknown")
        result["_period_label"] = period_label
        result["_date_range"] = date_range
        result["_raw_stats"] = {
            "hit_rate_pct": recs.get("hit_rate_pct", 0),
            "avg_return_pct": recs.get("avg_return_pct", 0),
            "total_buy_recs": recs.get("total_buy_recs", 0),
            "best_picks": recs.get("best_picks", [])[:5],
            "worst_picks": recs.get("worst_picks", [])[:3],
            "top3_sectors": sectors.get("top3_sectors", []),
            "brain_grades": brain_acc.get("grades", {}),
            "meta_findings": meta.get("findings", []),
            "portfolio_return": portfolio.get("period_return_pct", 0),
            "max_drawdown": portfolio.get("max_drawdown_pct", 0),
        }
        return result

    except Exception as e:
        return _fallback_periodic(analysis_data, str(e))


def _fallback_periodic(data: dict, error: str = "") -> dict:
    """Gemini 실패 시 숫자 기반 폴백."""
    recs = data.get("recommendations", {})
    period_label = data.get("period_label", "정기")
    return {
        "title": f"{period_label} 분석 리포트",
        "executive_summary": f"적중률 {recs.get('hit_rate_pct', 0)}%, 평균 수익률 {recs.get('avg_return_pct', 0)}%",
        "performance_review": f"BUY 추천 {recs.get('total_buy_recs', 0)}건 중 적중 {recs.get('hit_rate_pct', 0)}%",
        "sector_analysis": "AI 분석 실패 — 섹터 데이터 참조",
        "macro_outlook": "AI 분석 실패 — 매크로 데이터 참조",
        "brain_review": data.get("brain_accuracy", {}).get("insight", ""),
        "meta_insight": data.get("meta_analysis", {}).get("best_predictor", ""),
        "strategy": "데이터 기반 판단 필요",
        "risk_watch": "AI 리포트 생성 실패" + (f" ({error})" if error else ""),
        "_period": data.get("period", "unknown"),
        "_period_label": period_label,
        "_raw_stats": {},
    }
