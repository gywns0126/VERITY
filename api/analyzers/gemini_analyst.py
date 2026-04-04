"""
Gemini API 기반 최종 의사결정 모듈 (Sprint 8: 까칠한 펀드매니저)
- DART 재무제표(현금흐름) 데이터 통합
- 15년 차 펀드매니저 말투 프롬프트
- Gold/Silver 데이터 분류
"""
import json
import time
from typing import List, Optional
from google import genai
from api.config import GEMINI_API_KEY, RISK_KEYWORDS


def init_gemini():
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
    return genai.Client(api_key=GEMINI_API_KEY)


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
        macro_block = f"""
[매크로 환경]
- 시장 국면: {mf.get('regime', 'neutral')} | 분위기: {mood.get('label', '?')} ({mood.get('score', 0)}점)
- USD/KRW: {macro.get('usd_krw', {}).get('value', '?')}원
- VIX: {macro.get('vix', {}).get('value', '?')}
- WTI: ${macro.get('wti_oil', {}).get('value', '?')}
- S&P500: {macro.get('sp500', {}).get('change_pct', 0):+.1f}%
- 동적 가중치: {mf.get('weights_used', {})}
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

    return f"""너는 15년 차 까칠한 한국 펀드매니저다.
말은 짧고 굵게. 헛소리 싫어함. 숫자로 찍어. "분석 결과에 따르면" 같은 서론 절대 금지.
투자자가 돈을 잃지 않게 하는 게 최우선이다. 위험하면 직설적으로 까라.
데이터에 없는 건 모른다고 해. 뇌피셜 금지.

[종목]
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

규칙:
1. gold_insight = 재무/차트 핵심 한 줄. 구체적 숫자 필수. 군더더기 빼.
2. recommendation: 멀티팩터 ≥65 BUY, 45~64 WATCH, <45 AVOID
3. risk_flags: 실제 데이터에서 확인된 것만.
4. ai_verdict: 사장님한테 보고하듯 짧게. "~입니다" 금지. 반말 OK.
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

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
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


def generate_daily_report(macro: dict, candidates: List[dict], sectors: list, headlines: list) -> dict:
    """AI 일일 시장 종합 리포트 생성"""
    try:
        client = init_gemini()
    except Exception:
        return _fallback_report(macro, candidates, sectors)

    mood = macro.get("market_mood", {})
    diags = macro.get("macro_diagnosis", [])
    top_buys = [s for s in candidates if s.get("recommendation") == "BUY"][:5]
    top_sectors = sectors[:5] if sectors else []
    top_news = headlines[:5] if headlines else []

    prompt = f"""너는 15년 차 까칠한 펀드매니저다. 매일 아침 사장님한테 시장 브리핑하는 놈이야.
군더더기 싫어함. "분석 결과에 따르면" 금지. 숫자로 찍고 끝내.
핵심만 짧게. 위험하면 직설적으로.

[오늘 시장]
분위기: {mood.get('label', '?')} ({mood.get('score', 0)}점)
VIX: {macro.get('vix', {}).get('value', '?')} ({macro.get('vix', {}).get('change_pct', 0):+.1f}%)
원달러: {macro.get('usd_krw', {}).get('value', '?')}원 | WTI: ${macro.get('wti_oil', {}).get('value', '?')}
금: ${macro.get('gold', {}).get('value', '?')} | 스프레드: {macro.get('yield_spread', {}).get('value', '?')}%p ({macro.get('yield_spread', {}).get('signal', '?')})

[매크로]
{chr(10).join(f'- {d.get("text","")}' for d in diags) if diags else '별거 없음'}

[핫 섹터]
{chr(10).join(f'- {s["name"]}: {s["change_pct"]:+.2f}%' for s in top_sectors) if top_sectors else '없음'}

[뉴스]
{chr(10).join(f'- [{n.get("sentiment","?")}] {n["title"][:60]}' for n in top_news) if top_news else '없음'}

[찍은 종목]
{chr(10).join(f'- {s["name"]} ({s.get("multi_factor",{}).get("multi_score",0)}점)' for s in top_buys) if top_buys else '오늘 살 만한 거 없음'}

JSON만:
{{
  "market_summary": "시장 한줄 (30자 이내, 서론 없이)",
  "market_analysis": "상황 분석 (150자 이내, 반말 OK, 숫자 근거)",
  "strategy": "오늘 전략 (80자 이내, 실행 가능한 것만)",
  "risk_watch": "지금 위험한 것 (80자 이내)",
  "hot_theme": "관심 테마/섹터 + 이유 (80자 이내)",
  "tomorrow_outlook": "내일 전망 (30자 이내)"
}}"""

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
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
